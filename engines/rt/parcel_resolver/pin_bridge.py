"""
PIN→ARN Bridge — resolves RT records with PIN but no ARN using GW lookup data.

Loads all GW clean records to build a PIN→ARN mapping table, then updates
parcel_links for RT records that match.

Zero API calls — purely local data lookup.

Usage:
    python -m parcel_resolver.pin_bridge
    python -m parcel_resolver.pin_bridge --dry-run
"""

import json
import os
import sys
import argparse

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))

GW_DIR = os.path.join(PROJECT_ROOT, 'clean-data', 'gw')
ADDRESSES_DIR = os.path.join(PROJECT_ROOT, 'engines', 'rt', 'pipeline', 'addresses')
PARCEL_LINKS_DIR = os.path.join(PROJECT_ROOT, 'engines', 'rt', 'pipeline', 'parcel_links')

sys.path.insert(0, os.path.join(PROJECT_ROOT, 'engines', 'rt'))
from parcel_resolver.cache import cache_has, cache_read, cache_write


def build_gw_pin_to_arn():
    """Load GW clean records and build PIN → ARN lookup table."""
    pin_to_arn = {}

    if not os.path.isdir(GW_DIR):
        return pin_to_arn

    for fname in os.listdir(GW_DIR):
        if not fname.endswith('.json') or fname.startswith('_'):
            continue
        with open(os.path.join(GW_DIR, fname)) as f:
            gw = json.load(f)

        pin = gw.get('pin', '').strip()
        if not pin:
            continue

        for assessment in gw.get('assessments', []):
            arn = assessment.get('arn_api', '').strip()
            if arn and not all(c == '0' for c in arn):
                pin_to_arn[pin] = arn
                break  # Use first valid ARN

    return pin_to_arn


def run(dry_run=False):
    """Run PIN→ARN bridge on all unresolved RT records."""
    print('Cleo Engine — PIN→ARN Bridge')
    print()

    # Build lookup table
    pin_to_arn = build_gw_pin_to_arn()
    print(f'GW PIN→ARN pairs loaded: {len(pin_to_arn):,}')

    if not pin_to_arn:
        print('No GW data available for PIN bridging.')
        return

    # Scan addresses files for records with PIN but no ARN
    all_files = sorted(f for f in os.listdir(ADDRESSES_DIR) if f.endswith('.json'))
    existing_links = set(os.listdir(PARCEL_LINKS_DIR))

    stats = {
        'scanned': 0,
        'has_arn': 0,
        'has_pin_no_arn': 0,
        'pin_matched': 0,
        'pin_not_matched': 0,
        'already_resolved': 0,
        'updated': 0,
    }

    updates = []  # (filename, rt_id, arn)

    for fname in all_files:
        with open(os.path.join(ADDRESSES_DIR, fname)) as f:
            rec = json.load(f)

        stats['scanned'] += 1

        arn = rec.get('arn', {}).get('api_format', '').strip()
        if arn and not all(c == '0' for c in arn):
            stats['has_arn'] += 1
            continue

        pin = rec.get('pin', {}).get('api_format', '').strip()
        if not pin:
            continue

        stats['has_pin_no_arn'] += 1

        # Check if already resolved
        if fname in existing_links:
            with open(os.path.join(PARCEL_LINKS_DIR, fname)) as f:
                link = json.load(f)
            if link.get('resolved_arn'):
                stats['already_resolved'] += 1
                continue

        # Try GW bridge
        bridged_arn = pin_to_arn.get(pin)
        if bridged_arn:
            stats['pin_matched'] += 1
            rt_id = rec.get('rt_id', fname.split('__')[0])
            updates.append((fname, rt_id, bridged_arn))
        else:
            stats['pin_not_matched'] += 1

    print(f'\nScan results:')
    print(f'  Total scanned:     {stats["scanned"]:,}')
    print(f'  Has ARN (skip):    {stats["has_arn"]:,}')
    print(f'  Has PIN, no ARN:   {stats["has_pin_no_arn"]:,}')
    print(f'  Already resolved:  {stats["already_resolved"]:,}')
    print(f'  PIN matched (GW):  {stats["pin_matched"]:,}')
    print(f'  PIN not matched:   {stats["pin_not_matched"]:,}')
    print()

    if dry_run or not updates:
        if not updates:
            print('No new records to bridge.')
        return

    # Write parcel links for matched records
    for fname, rt_id, arn in updates:
        # Ensure parcel is cached
        if not cache_has(arn):
            # We know the ARN from GW but don't have the parcel geometry cached yet
            # Write a minimal link — the parcel resolver can fill geometry later
            pass

        link = {
            'rt_id': rt_id,
            'resolved_arn': arn,
            'method': 'pin_gw',
            'parcel_file': f'{arn}.json' if cache_has(arn) else None,
            'reason': None,
        }

        with open(os.path.join(PARCEL_LINKS_DIR, fname), 'w') as f:
            json.dump(link, f, indent=2)

        stats['updated'] += 1

    print(f'Updated {stats["updated"]:,} parcel links via PIN→ARN bridge')


def main():
    parser = argparse.ArgumentParser(description='PIN→ARN bridge via GW lookup')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    run(dry_run=args.dry_run)


if __name__ == '__main__':
    main()
