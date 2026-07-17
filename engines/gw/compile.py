"""
GeoWarehouse Compiler -- merges all pipeline stages into clean records.

Input:  engines/gw/pipeline/{parsed,normalized,parcel_links}/{GW_ID}.json
Output: clean-data/gw/{GW_ID}.json

Usage:
    python engines/gw/compile.py
    python engines/gw/compile.py --dry-run
"""

import json
import os
import sys
import argparse
from datetime import datetime, timezone

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)
from engines.shared.io import safe_write_json

PARSED_DIR = os.path.join(PROJECT_ROOT, 'engines', 'gw', 'pipeline', 'parsed')
NORMALIZED_DIR = os.path.join(PROJECT_ROOT, 'engines', 'gw', 'pipeline', 'normalized')
PARCEL_LINKS_DIR = os.path.join(PROJECT_ROOT, 'engines', 'gw', 'pipeline', 'parcel_links')
CLEAN_DIR = os.path.join(PROJECT_ROOT, 'clean-data', 'gw')


def load_json(directory, fname):
    """Load a JSON file, return None if missing."""
    path = os.path.join(directory, fname)
    if not os.path.isfile(path):
        return None
    with open(path) as f:
        return json.load(f)


def compile_record(parsed, normalized, parcel_link):
    """Merge pipeline stages into a single clean record."""
    gw_id = parsed.get('gw_id', '')
    addr = normalized.get('address') or {}
    norm_assessments = normalized.get('assessments', [])
    resolutions = parcel_link.get('resolutions', []) if parcel_link else []

    # Build resolution lookup by ARN
    resolution_map = {}
    for r in resolutions:
        if r.get('arn'):
            resolution_map[r['arn']] = r

    # Build assessments with parcel info
    assessments = []
    primary_arn = None
    for a in norm_assessments:
        arn_api = a.get('arn_api', '')
        res = resolution_map.get(arn_api, {})

        assessment = {
            'arn': a.get('arn', ''),
            'arn_api': arn_api,
            'zoning': a.get('zoning', ''),
            'assessed_value': a.get('assessed_value'),
            'valuation_date': a.get('valuation_date', ''),
            'property_code': a.get('property_code', ''),
            'property_description': a.get('property_description', ''),
            'frontage_ft': a.get('frontage_ft'),
            'depth_ft': a.get('depth_ft'),
            'site_area_sqft': a['site_area']['value'] if a.get('site_area') and a['site_area'].get('unit') == 'sqft' else None,
            'acreage': a.get('acreage'),
            'municipality': a.get('municipality', ''),
            'owner_names_mpac': a.get('owner_names_mpac', ''),
            'owner_mailing_address': a.get('owner_mailing_address', ''),
            'legal_description': a.get('legal_description', ''),
            'parcel_resolved': res.get('method') in ('arn_cache', 'arn_api'),
            'parcel_method': res.get('method', ''),
            'parcel_file': res.get('parcel_file'),
        }
        assessments.append(assessment)

        if not primary_arn and arn_api:
            primary_arn = arn_api

    # Find primary resolution
    primary_res = resolution_map.get(primary_arn, {})

    record = {
        'source_id': gw_id,
        'source': 'gw',
        'source_file': parsed.get('source_file', ''),
        'compiled_at': datetime.now(timezone.utc).isoformat(),
        'pin': normalized.get('pin_api', '') or parsed.get('pin', ''),
        'property': {
            'display_address': addr.get('display_street', ''),
            'city': addr.get('display_city', ''),
            'province': addr.get('province', 'ON'),
            'postal': addr.get('postal_code', ''),
            'municipality': (norm_assessments[0].get('municipality', '') if norm_assessments else ''),
            'geocode_string': addr.get('geocode_string'),
            'components': addr.get('components'),
        },
        'owner': {
            'name': (norm_assessments[0].get('owner_names_mpac', '') if norm_assessments
                     else parsed.get('summary', {}).get('owner_names', '')),
            'mailing_address': (norm_assessments[0].get('owner_mailing_address', '') if norm_assessments else ''),
        },
        'registry': {
            'ownership_type': parsed.get('registry', {}).get('ownership_type', ''),
            'property_type': parsed.get('registry', {}).get('property_type', ''),
            'land_registry_status': parsed.get('registry', {}).get('land_registry_status', ''),
            'registration_type': parsed.get('registry', {}).get('registration_type', ''),
            'lro': parsed.get('registry', {}).get('land_registry_office', ''),
        },
        'assessments': assessments,
        'sales_history': normalized.get('sales_history', []),
        'parcel': {
            'resolved_arn': primary_arn if primary_res.get('parcel_file') else None,
            'method': primary_res.get('method', ''),
            'parcel_file': primary_res.get('parcel_file'),
        },
        'quality': {
            'has_mpac_data': parsed.get('has_mpac_data', False),
            'is_active': parsed.get('is_active', True),
            'address_parsed': addr is not None and bool(addr.get('street')),
            'parcel_resolved': bool(primary_res.get('parcel_file')),
            'issues': normalized.get('issues', []),
        },
    }

    return record


def run(dry_run=False):
    """Compile all GW pipeline stages into clean records."""
    if not os.path.isdir(PARSED_DIR):
        print(f'ERROR: Parsed directory not found: {PARSED_DIR}')
        sys.exit(1)

    files = sorted(f for f in os.listdir(PARSED_DIR)
                   if f.endswith('.json') and not f.startswith('_'))

    print('Cleo Engine -- Compile GeoWarehouse Records')
    print(f'Records: {len(files):,}')
    print()

    os.makedirs(CLEAN_DIR, exist_ok=True)

    stats = {'compiled': 0, 'resolved': 0, 'unresolved': 0, 'errors': 0}

    for fname in files:
        try:
            parsed = load_json(PARSED_DIR, fname)
            normalized = load_json(NORMALIZED_DIR, fname)
            parcel_link = load_json(PARCEL_LINKS_DIR, fname)

            if not parsed or not normalized:
                stats['errors'] += 1
                continue

            record = compile_record(parsed, normalized, parcel_link)

            if record['parcel']['resolved_arn']:
                stats['resolved'] += 1
            else:
                stats['unresolved'] += 1

            if not dry_run:
                safe_write_json(os.path.join(CLEAN_DIR, fname), record)

            stats['compiled'] += 1

        except Exception as e:
            stats['errors'] += 1
            print(f'  ERROR {fname}: {e}')

    print(f'Compiled:   {stats["compiled"]:,}')
    print(f'Resolved:   {stats["resolved"]:,}')
    print(f'Unresolved: {stats["unresolved"]:,}')
    print(f'Errors:     {stats["errors"]:,}')

    final = len([f for f in os.listdir(CLEAN_DIR) if f.endswith('.json') and not f.startswith('_')]) if not dry_run else 0
    if not dry_run:
        print(f'\nTotal in clean-data/gw/: {final:,}')


def main():
    parser = argparse.ArgumentParser(description='Compile GeoWarehouse clean records')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    run(dry_run=args.dry_run)


if __name__ == '__main__':
    main()
