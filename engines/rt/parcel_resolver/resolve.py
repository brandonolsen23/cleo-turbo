"""
Orchestrator — scans all addresses files, runs the resolution chain,
writes parcel_links.

Reads:  engines/rt/pipeline/addresses/*.json
Writes: engines/rt/pipeline/parcel_links/*.json   (one per addresses file)
Also:   clean-data/parcels/*.json                  (new parcels discovered)

Resumable: skips any record that already has a parcel_links file.

Usage:
    python -m parcel_resolver.resolve
    python -m parcel_resolver.resolve --limit 100
    python -m parcel_resolver.resolve --dry-run
"""

import json
import os
import sys
import time
import argparse

from .chain import resolve_record
from .agmaps import AgMapsClient, TokenExpiredError
from .token import load_token, refresh_token


ADDRESSES_DIR = os.path.join(os.path.dirname(__file__), '..', 'pipeline', 'addresses')
PARCEL_LINKS_DIR = os.path.join(os.path.dirname(__file__), '..', 'pipeline', 'parcel_links')
ADDRESSES_DIR = os.path.abspath(ADDRESSES_DIR)
PARCEL_LINKS_DIR = os.path.abspath(PARCEL_LINKS_DIR)


def extract_identifiers(addr_record):
    """Extract ARN and geocode_string from an addresses file."""
    arn = addr_record.get('arn', {}).get('api_format', '').strip()

    # Filter out all-zeros
    if arn and all(c == '0' for c in arn):
        arn = ''

    # Get first geocodable address string for spatial fallback
    geocode_string = None
    for addr in addr_record.get('property', {}).get('addresses', []):
        if addr.get('geocodable') and addr.get('geocode_string'):
            geocode_string = addr['geocode_string']
            break

    return arn, geocode_string


def run(limit=None, dry_run=False):
    """Run the Resolve Parcels stage."""

    os.makedirs(PARCEL_LINKS_DIR, exist_ok=True)

    # Build file list
    all_files = sorted(f for f in os.listdir(ADDRESSES_DIR) if f.endswith('.json'))

    # Filter to files that don't already have a parcel_links output (resumable)
    existing_links = set(os.listdir(PARCEL_LINKS_DIR))
    pending = [f for f in all_files if f not in existing_links]

    if limit:
        pending = pending[:limit]

    print(f'Cleo Engine — Resolve Parcels')
    print(f'Addresses files:   {len(all_files):,}')
    print(f'Already resolved:  {len(all_files) - len(pending):,}')
    print(f'Pending:           {len(pending):,}')
    print()

    if dry_run:
        # Categorize what we'd process
        categories = {'has_arn': 0, 'no_arn': 0}
        for fname in pending[:1000]:  # Sample first 1000
            with open(os.path.join(ADDRESSES_DIR, fname)) as f:
                rec = json.load(f)
            arn, geo = extract_identifiers(rec)
            if arn:
                categories['has_arn'] += 1
            else:
                categories['no_arn'] += 1
        sampled = min(len(pending), 1000)
        print(f'Sample of {sampled} pending records:')
        for cat, count in categories.items():
            print(f'  {cat}: {count} ({count*100/sampled:.1f}%)')
        return

    # Get token
    print('Loading token...')
    token = load_token()
    if token:
        print('  Using saved token (validated)')
    else:
        print('  No saved token — fetching fresh token via browser...')
        token = refresh_token()
        print('  Token fetched and saved')
    print()

    client = AgMapsClient(token)

    # Process records
    stats = {
        'arn_cache': 0,
        'arn_api': 0,
        'spatial_api': 0,
        'unresolved': 0,
        'errors': 0,
    }
    start_time = time.time()

    for i, fname in enumerate(pending):
        try:
            # Read addresses file
            with open(os.path.join(ADDRESSES_DIR, fname)) as f:
                rec = json.load(f)

            arn, geocode_string = extract_identifiers(rec)
            rt_id = rec.get('rt_id', fname.split('__')[0])

            # Resolve
            try:
                result = resolve_record(arn, geocode_string, client)
            except TokenExpiredError:
                print(f'\n  Token expired at record {i+1}. Refreshing...')
                client.close()
                token = refresh_token()
                client = AgMapsClient(token)
                print('  Token refreshed. Retrying...')
                result = resolve_record(arn, geocode_string, client)

            # Build parcel_links output
            link = {
                'rt_id': rt_id,
                'resolved_arn': result['resolved_arn'],
                'method': result['method'],
                'parcel_file': f"{result['resolved_arn']}.json" if result['resolved_arn'] else None,
                'reason': result.get('reason'),
            }

            # Write parcel_links file
            with open(os.path.join(PARCEL_LINKS_DIR, fname), 'w') as f:
                json.dump(link, f, indent=2)

            stats[result['method']] += 1

        except Exception as e:
            stats['errors'] += 1
            # Write an error link so we don't retry this file
            error_link = {
                'rt_id': fname.split('__')[0],
                'resolved_arn': None,
                'method': 'error',
                'parcel_file': None,
                'reason': str(e),
            }
            with open(os.path.join(PARCEL_LINKS_DIR, fname), 'w') as f:
                json.dump(error_link, f, indent=2)

        # Progress
        if (i + 1) % 500 == 0 or (i + 1) == len(pending):
            elapsed = time.time() - start_time
            resolved = stats['arn_cache'] + stats['arn_api'] + stats['spatial_api']
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            print(
                f'  [{i+1:,}/{len(pending):,}] '
                f'resolved: {resolved:,}  '
                f'unresolved: {stats["unresolved"]:,}  '
                f'errors: {stats["errors"]:,}  '
                f'({rate:.1f} rec/s, {elapsed:.0f}s)'
            )

    client.close()

    # Summary
    elapsed = time.time() - start_time
    print()
    print(f'Done in {elapsed:.1f}s')
    print(f'  arn_cache:   {stats["arn_cache"]:,}')
    print(f'  arn_api:     {stats["arn_api"]:,}')
    print(f'  spatial_api: {stats["spatial_api"]:,}')
    print(f'  unresolved:  {stats["unresolved"]:,}')
    print(f'  errors:      {stats["errors"]:,}')

    total_resolved = stats['arn_cache'] + stats['arn_api'] + stats['spatial_api']
    total = total_resolved + stats['unresolved'] + stats['errors']
    if total > 0:
        print(f'  resolution rate: {total_resolved*100/total:.1f}%')


def main():
    parser = argparse.ArgumentParser(description='Resolve parcels for all addresses records')
    parser.add_argument('--limit', type=int, help='Process only the first N pending records')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be processed')
    args = parser.parse_args()

    run(limit=args.limit, dry_run=args.dry_run)


if __name__ == '__main__':
    main()
