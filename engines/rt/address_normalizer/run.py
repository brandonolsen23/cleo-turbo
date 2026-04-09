"""
Orchestrator — reads classified JSON, normalizes all addresses, writes to pipeline/addresses/.

Modes:
    Default:      Only normalize classified files that don't have an addresses
                  counterpart yet (incremental — safe for daily use).
    --all:        Normalize ALL classified files, overwriting existing output.
                  Use after fixing the normalizer to reprocess everything.
    --files:      Normalize only the specified files (comma-separated or glob).

Usage:
    python -m address_normalizer.run                    # incremental (new only)
    python -m address_normalizer.run --all              # reprocess everything
    python -m address_normalizer.run --files "RT198*.json"  # specific files

Reads:  pipeline/classified/*.json
Writes: pipeline/addresses/*.json   (one per RT, same filename)

Reference: schema/address_normalization_plan.md
"""

import json
import fnmatch
import os
import sys
import argparse

from .decompose import decompose
from .expand import (
    generate_search_keys, expand_range, build_geocode_string,
    build_street_only, classify_address_type, is_geocodable,
)
from .normalize import expand_province, expand_country, normalize_postal, to_title_case
from .pin_arn import normalize_pin, normalize_arn


CLASSIFIED_DIR = os.path.join(os.path.dirname(__file__), '..', 'pipeline', 'classified')
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'pipeline', 'addresses')


def process_header_address(entry, city='', region='', postal_from_export=''):
    """Process a single header address entry (property address)."""
    results = []
    for line in entry.get('lines', []):
        if not line.strip():
            continue
        components = decompose(line)
        search_keys = generate_search_keys(components)
        variations = expand_range(components)

        # Add each variation's search key to the main list
        # And give each variation its own geocode string
        for v in variations:
            if v['search_key'] not in search_keys:
                search_keys.append(v['search_key'])
            if is_geocodable(components):
                v['geocode_string'] = build_geocode_string(
                    v['display'],
                    city=city,
                    province='Ontario',
                    postal=postal_from_export,
                )

        # Main geocode string: street-level only (no suite)
        # For multi-number addresses, use the first individual number
        geocode_str = None
        if is_geocodable(components):
            if variations and len(variations) > 1:
                geocode_str = variations[1].get('geocode_string')
            else:
                geocode_str = build_geocode_string(
                    build_street_only(components),
                    city=city,
                    province='Ontario',
                    postal=postal_from_export,
                )

        results.append({
            'original': line,
            'display': components['display'],
            'components': {
                'street_number': components['street_number'],
                'street_name': components['street_name'],
                'street_suffix': components['street_suffix'],
                'street_direction': components['street_direction'],
                'suite_type': components['suite_type'],
                'suite_number': components['suite_number'],
            },
            'search_keys': search_keys,
            'variations': variations,
            'geocode_string': geocode_str,
            'geocodable': is_geocodable(components),
            'type': classify_address_type(components),
        })
    return results


def process_contact_address(addr_data):
    """Process a seller or buyer address block."""
    lines = addr_data.get('lines', [])
    city = addr_data.get('city', '')
    province = addr_data.get('province', '')
    postal = addr_data.get('postal', '')
    country = addr_data.get('country', '')
    modifiers = addr_data.get('modifiers', [])
    building_names = addr_data.get('building_names', [])

    # Normalize city, province, postal, country
    if city:
        city = to_title_case(city)
    if province:
        province = expand_province(province)
    if postal:
        postal = normalize_postal(postal)
    if country:
        country = expand_country(country)

    # Decompose address lines
    if not lines or not any(l.strip() for l in lines):
        return {
            'original_lines': lines,
            'display': '',
            'components': {
                'street_number': '', 'street_name': '', 'street_suffix': '',
                'street_direction': '', 'suite_type': '', 'suite_number': '',
            },
            'search_keys': [],
            'geocode_string': None,
            'modifiers': modifiers,
            'building_names': building_names,
            'city': city,
            'province': province,
            'postal': postal,
            'country': country,
        }

    # Decompose each line individually to find the best street address
    # This prevents PO Box / RR lines from polluting the street decomposition
    line_results = []
    for l in lines:
        if l.strip():
            line_results.append(decompose(l.strip()))

    # Find the best geocodable line (street address beats PO Box/RR)
    best = None
    supplementary = []
    for lr in line_results:
        if is_geocodable(lr) and best is None:
            best = lr
        else:
            supplementary.append(lr)

    # If no geocodable line, use the first one as the primary
    if best is None and line_results:
        best = line_results[0]
        supplementary = line_results[1:]

    components = best if best else decompose('')

    # Merge suite info from supplementary lines (e.g., "2nd Floor" on its own line)
    for sup in supplementary:
        if sup.get('suite_type') and not components.get('suite_type'):
            components['suite_type'] = sup['suite_type']
            components['suite_number'] = sup['suite_number']
        # Rebuild display if suite was added
        if sup.get('special_type') in ('po_box', 'rural_route'):
            # Keep PO Box/RR info for display but NOT for geocoding
            if components.get('display'):
                components['display'] += f", {sup['display']}"

    search_keys = generate_search_keys(components)

    geocode_str = None
    if is_geocodable(components):
        geocode_str = build_geocode_string(
            build_street_only(components),
            city=city,
            province=province,
            postal=postal,
            country=country,
        )

    return {
        'original_lines': lines,
        'display': components['display'],
        'components': {
            'street_number': components['street_number'],
            'street_name': components['street_name'],
            'street_suffix': components['street_suffix'],
            'street_direction': components['street_direction'],
            'suite_type': components['suite_type'],
            'suite_number': components['suite_number'],
        },
        'search_keys': search_keys,
        'geocode_string': geocode_str,
        'modifiers': modifiers,
        'building_names': building_names,
        'city': city,
        'province': province,
        'postal': postal,
        'country': country,
    }


def process_file(filepath):
    """Process a single classified JSON file and return the address output."""
    with open(filepath) as f:
        data = json.load(f)

    rt_id = data['rt_id']
    header = data.get('header', {})
    seller = data.get('seller', {})
    buyer = data.get('buyer', {})
    site = data.get('site', {})
    export = data.get('export', {})

    # Header property addresses
    city = header.get('city', '')
    region = header.get('region', '')
    postal_from_export = export.get('postcode', '')

    property_addresses = []
    for entry in header.get('address_entries', []):
        property_addresses.extend(
            process_header_address(entry, city=city, region=region,
                                   postal_from_export=postal_from_export)
        )

    # Deduplicate property addresses by original text
    seen = set()
    deduped = []
    for addr in property_addresses:
        if addr['original'] not in seen:
            seen.add(addr['original'])
            deduped.append(addr)
    property_addresses = deduped

    # Normalize city for property display
    if city:
        city = to_title_case(city)

    # PIN / ARN
    pin_raw = site.get('pin', '') or export.get('pin', '')
    arn_raw = data.get('arn', '') or export.get('rollno', '')
    pin = normalize_pin(pin_raw)
    arn = normalize_arn(arn_raw)

    output = {
        'rt_id': rt_id,
        'property': {
            'addresses': property_addresses,
            'city': city,
            'region': region,
            'postal_from_export': normalize_postal(postal_from_export),
        },
        'seller': {
            'address': process_contact_address(seller.get('address', {})),
        },
        'buyer': {
            'address': process_contact_address(buyer.get('address', {})),
        },
        'pin': pin,
        'arn': arn,
    }

    return output


def find_pending_files(input_dir, output_dir):
    """Find classified files that don't have a normalized counterpart yet."""
    classified_files = set(f for f in os.listdir(input_dir) if f.endswith('.json'))
    address_files = set(f for f in os.listdir(output_dir) if f.endswith('.json'))
    return sorted(classified_files - address_files)


def run(input_dir=None, output_dir=None, file_list=None, process_all=False):
    """Process classified files and write normalized addresses.

    Args:
        input_dir: Directory containing classified JSON files.
        output_dir: Directory to write normalized address files.
        file_list: If set, only process these specific filenames.
        process_all: If True, reprocess all files (overwrite existing).
    """
    input_dir = input_dir or CLASSIFIED_DIR
    output_dir = output_dir or OUTPUT_DIR

    input_dir = os.path.abspath(input_dir)
    output_dir = os.path.abspath(output_dir)

    os.makedirs(output_dir, exist_ok=True)

    # Determine which files to process
    if file_list is not None:
        files = file_list
        mode = 'files'
    elif process_all:
        files = sorted(f for f in os.listdir(input_dir) if f.endswith('.json'))
        mode = 'all'
    else:
        files = find_pending_files(input_dir, output_dir)
        mode = 'new'

    total = len(files)
    skipped = 0
    if mode == 'new':
        total_classified = len([f for f in os.listdir(input_dir) if f.endswith('.json')])
        skipped = total_classified - total

    if total == 0:
        print(f'Cleo Engine — Address Normalizer')
        print(f'Nothing to normalize (0 pending records)')
        return 0, []

    print(f'Cleo Engine — Address Normalizer')
    print(f'Mode: {mode}')
    print(f'Records to process: {total}' + (f'  (skipped {skipped} already normalized)' if skipped else ''))
    print()

    success = 0
    errors = []

    for i, filename in enumerate(files):
        filepath = os.path.join(input_dir, filename)
        try:
            result = process_file(filepath)

            # Write with same filename
            out_path = os.path.join(output_dir, filename)
            with open(out_path, 'w') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)

            success += 1
        except Exception as e:
            errors.append((filename, str(e)))

        if (i + 1) % 500 == 0 or i + 1 == total:
            print(f'  [{i + 1}/{total}] processed')

    print(f'\nDone: {success}/{total} files normalized')
    if errors:
        print(f'Errors ({len(errors)}):')
        for fname, err in errors[:10]:
            print(f'  {fname}: {err}')
        if len(errors) > 10:
            print(f'  ... and {len(errors) - 10} more')

    return success, errors


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Normalize addresses from classified records')
    parser.add_argument('--all', action='store_true', help='Reprocess ALL records (overwrite existing)')
    parser.add_argument('--files', type=str, help='Process only these files (comma-separated names or glob pattern)')
    args = parser.parse_args()

    file_list = None
    if args.files:
        all_classified = sorted(f for f in os.listdir(CLASSIFIED_DIR) if f.endswith('.json'))
        parts = [p.strip() for p in args.files.split(',')]
        file_list = []
        for pattern in parts:
            matched = fnmatch.filter(all_classified, pattern)
            file_list.extend(matched)
        file_list = sorted(set(file_list))

    run(file_list=file_list, process_all=args.all)
