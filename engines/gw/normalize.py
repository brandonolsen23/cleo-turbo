"""
GeoWarehouse Normalizer -- cleans addresses, dates, prices, and PIN/ARN formats.

Input:  engines/gw/pipeline/parsed/{GW_ID}.json
Output: engines/gw/pipeline/normalized/{GW_ID}.json

Usage:
    python engines/gw/normalize.py
    python engines/gw/normalize.py --dry-run
"""

import json
import os
import re
import sys
import argparse
from datetime import datetime

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

PARSED_DIR = os.path.join(PROJECT_ROOT, 'engines', 'gw', 'pipeline', 'parsed')
NORMALIZED_DIR = os.path.join(PROJECT_ROOT, 'engines', 'gw', 'pipeline', 'normalized')


# ================================================================
# Address parsing
# ================================================================

from cleo.address.decompose import decompose_simple
from cleo.address.formatter import format_display
from cleo.address.normalize import to_title_case


def parse_mpac_address(property_address, municipality=''):
    """Parse MPAC property address into components.

    Input:  "121 CONCESSION ST E TILLSONBURG ON N4G4W4"
    Output: {street, city, province, postal_code, display_street, display_city,
             geocode_string, components}
    """
    if not property_address:
        return None

    raw = property_address.strip()

    # Extract postal code
    postal_match = re.search(r'([A-Z]\d[A-Z])\s?(\d[A-Z]\d)\s*$', raw)
    postal = ''
    if postal_match:
        postal = f'{postal_match.group(1)} {postal_match.group(2)}'
        raw = raw[:postal_match.start()].strip()

    # Strip trailing province
    raw = re.sub(r'\s+ON\s*$', '', raw).strip()

    # Use municipality as anchor to split street from city
    street = raw
    city = municipality.strip() if municipality else ''

    if municipality:
        muni_upper = municipality.upper().strip()
        idx = raw.upper().rfind(muni_upper)
        if idx > 0:
            street = raw[:idx].strip()
            city = raw[idx:idx + len(muni_upper)]

    # Use shared decomposer + formatter for consistent display
    components = decompose_simple(street)
    display_street = format_display(components)
    display_city = to_title_case(city) if city else ''

    return {
        'street': street,
        'city': city,
        'province': 'ON',
        'postal_code': postal,
        'display_street': display_street,
        'display_city': display_city,
        'geocode_string': f'{display_street}, {display_city}, Ontario {postal}, Canada'.strip(', ') if display_street else None,
        'components': components,
    }


# ================================================================
# Price/date/area normalization
# ================================================================

def parse_price(raw):
    """Parse "$3,700,000" → 3700000"""
    if not raw:
        return None
    digits = re.sub(r'[^\d]', '', raw)
    return int(digits) if digits else None


def parse_date(raw):
    """Parse "Oct 28, 2020" → "2020-10-28" """
    if not raw:
        return None
    for fmt in ('%b %d, %Y', '%B %d, %Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(raw.strip(), fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return raw  # return original if unparseable


def parse_site_area(raw):
    """Parse site area from MPAC format.

    "104963.55F" → {value: 104963.55, unit: "sqft", acres: 2.41}
    "50,806  ft²" → {value: 50806, unit: "sqft", acres: 1.17}
    """
    if not raw or raw.strip() in ('', 'N/A'):
        return None

    text = raw.strip()

    # MPAC format: "104963.55F" or "500M"
    mpac_match = re.match(r'^([\d,.]+)\s*([FM])\s*$', text)
    if mpac_match:
        value = float(mpac_match.group(1).replace(',', ''))
        unit = 'sqft' if mpac_match.group(2) == 'F' else 'sqm'
        acres = value / 43560 if unit == 'sqft' else value / 4046.86
        return {'value': round(value, 2), 'unit': unit, 'acres': round(acres, 2)}

    # Display format: "50,806  ft²" or "1.2  acres"
    display_match = re.match(r'^([\d,.]+)\s*(ft²|sq\s*ft|acres?|ac|m²|hectares?|ha)', text, re.IGNORECASE)
    if display_match:
        value = float(display_match.group(1).replace(',', ''))
        unit_raw = display_match.group(2).lower()
        if 'ft' in unit_raw:
            return {'value': round(value, 2), 'unit': 'sqft', 'acres': round(value / 43560, 2)}
        elif 'acre' in unit_raw or unit_raw == 'ac':
            return {'value': round(value, 2), 'unit': 'acres', 'acres': round(value, 2)}
        elif 'm' in unit_raw:
            return {'value': round(value, 2), 'unit': 'sqm', 'acres': round(value / 4046.86, 2)}
        elif 'hectare' in unit_raw or unit_raw == 'ha':
            return {'value': round(value, 2), 'unit': 'hectares', 'acres': round(value * 2.471, 2)}

    return None


def parse_dimension(raw):
    """Parse "237.84 ft" → 237.84 (float in feet), or None."""
    if not raw or raw.strip() in ('', 'N/A'):
        return None
    m = re.match(r'^([\d,.]+)', raw.strip())
    if m:
        return float(m.group(1).replace(',', ''))
    return None


def format_pin(raw):
    """Normalize PIN to 9-digit api_format."""
    if not raw:
        return ''
    digits = re.sub(r'[^\d]', '', raw)
    if not digits:
        return ''
    return digits.zfill(9)


def format_arn(raw):
    """Normalize ARN to 20-digit api_format."""
    if not raw:
        return ''
    digits = re.sub(r'[^\d]', '', raw)
    if not digits:
        return ''
    return digits.ljust(20, '0')[:20]


# ================================================================
# Record normalizer
# ================================================================

def normalize_record(record):
    """Normalize a parsed GW record."""
    normalized = dict(record)  # shallow copy base fields
    issues = []

    # --- Address ---
    # Try MPAC address first (most structured), fall back to summary
    best_address = None
    for assessment in record.get('assessments', []):
        addr = parse_mpac_address(
            assessment.get('property_address', ''),
            assessment.get('municipality', ''),
        )
        if addr and addr.get('street'):
            best_address = addr
            break

    if not best_address:
        # Fall back to summary address
        summary_addr = record.get('summary', {}).get('address', '')
        if summary_addr:
            # Summary format: "121 CONCESSION ST E, TILLSONBURG, N4G4W4"
            parts = [p.strip() for p in summary_addr.split(',')]
            street = parts[0] if parts else ''
            city = parts[1] if len(parts) > 1 else ''
            postal = parts[2] if len(parts) > 2 else ''
            best_address = {
                'street': street,
                'city': city,
                'province': 'ON',
                'postal_code': postal if re.match(r'^[A-Z]\d[A-Z]', postal) else '',
                'display_street': _title_case_street(street),
                'display_city': city.title() if city else '',
                'geocode_string': f'{_title_case_street(street)}, {city.title()}, Ontario, Canada' if street else None,
            }

    if not best_address:
        issues.append('address_parse_failed')

    normalized['address'] = best_address

    # --- PIN/ARN formatting ---
    normalized['pin_api'] = format_pin(record.get('pin', ''))

    # --- Assessments normalization ---
    norm_assessments = []
    for a in record.get('assessments', []):
        norm_a = {
            'arn': a.get('arn', ''),
            'arn_api': format_arn(a.get('arn', '')),
            'zoning': a.get('zoning', ''),
            'assessed_value': parse_price(a.get('assessed_value', '')),
            'valuation_date': a.get('valuation_date', ''),
            'property_code': a.get('property_code', ''),
            'property_description': a.get('property_description', ''),
            'frontage_ft': parse_dimension(a.get('frontage', '')),
            'depth_ft': parse_dimension(a.get('depth', '')),
            'site_area': parse_site_area(a.get('site_area', '')),
            'acreage': None,
            'municipality': a.get('municipality', ''),
            'owner_names_mpac': a.get('owner_names_mpac', ''),
            'owner_mailing_address': a.get('owner_mailing_address', ''),
            'legal_description': a.get('legal_description', ''),
            'property_address': a.get('property_address', ''),
        }
        # Compute acreage
        if norm_a['site_area']:
            norm_a['acreage'] = norm_a['site_area'].get('acres')
        norm_assessments.append(norm_a)

    normalized['assessments'] = norm_assessments

    # --- Sales history normalization ---
    norm_sales = []
    for sale in record.get('sales_history', []):
        norm_sales.append({
            'date': parse_date(sale.get('sale_date', '')),
            'amount': parse_price(sale.get('sale_amount', '')),
            'type': sale.get('type', ''),
            'party_to': sale.get('party_to', '').rstrip(';').strip(),
            'notes': sale.get('notes', ''),
        })
    normalized['sales_history'] = norm_sales

    # --- Quality tracking ---
    if not normalized.get('pin'):
        issues.append('no_pin')
    if not norm_assessments:
        issues.append('no_arn')
    if not best_address:
        issues.append('no_address')
    if best_address and not best_address.get('postal_code'):
        issues.append('no_postal')

    normalized['issues'] = issues

    return normalized


# ================================================================
# Pipeline runner
# ================================================================

def run(dry_run=False):
    """Normalize all parsed GW records."""
    if not os.path.isdir(PARSED_DIR):
        print(f'ERROR: Parsed directory not found: {PARSED_DIR}')
        sys.exit(1)

    files = sorted(f for f in os.listdir(PARSED_DIR)
                   if f.endswith('.json') and not f.startswith('_'))

    print('Cleo Engine -- Normalize GeoWarehouse Records')
    print(f'Parsed records: {len(files):,}')
    print()

    if not files:
        print('Nothing to normalize.')
        return

    os.makedirs(NORMALIZED_DIR, exist_ok=True)

    stats = {'normalized': 0, 'issues': {}}

    for i, fname in enumerate(files):
        with open(os.path.join(PARSED_DIR, fname)) as f:
            record = json.load(f)

        normalized = normalize_record(record)

        for issue in normalized.get('issues', []):
            stats['issues'][issue] = stats['issues'].get(issue, 0) + 1

        if not dry_run:
            with open(os.path.join(NORMALIZED_DIR, fname), 'w') as f:
                json.dump(normalized, f, indent=2, ensure_ascii=False)

        stats['normalized'] += 1

    print(f'Normalized: {stats["normalized"]:,}')
    if stats['issues']:
        print(f'Issues:')
        for issue, count in sorted(stats['issues'].items(), key=lambda x: -x[1]):
            print(f'  {issue}: {count}')


def main():
    parser = argparse.ArgumentParser(description='Normalize GeoWarehouse parsed records')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    run(dry_run=args.dry_run)


if __name__ == '__main__':
    main()
