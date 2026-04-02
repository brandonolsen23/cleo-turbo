"""
GeoWarehouse Parcel Resolver -- resolves GW records to parcels via ARN/PIN.

Resolution chain:
  1. ARN → cache (fastest)
  2. ARN → API
  3. PIN → ARN bridge (scan cached parcels)
  4. Geocode → spatial (last resort)
  5. Unresolved

Most GW records have ARNs, so this is primarily cache lookups.

Input:  engines/gw/pipeline/normalized/{GW_ID}.json
Output: engines/gw/pipeline/parcel_links/{GW_ID}.json

Usage:
    python engines/gw/resolve_parcels.py
    python engines/gw/resolve_parcels.py --dry-run
"""

import json
import os
import sys
import time
import argparse

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'engines', 'rt'))

from parcel_resolver.agmaps import AgMapsClient, TokenExpiredError
from parcel_resolver.token import load_token, refresh_token
from parcel_resolver.cache import cache_has, cache_read, cache_write

NORMALIZED_DIR = os.path.join(PROJECT_ROOT, 'engines', 'gw', 'pipeline', 'normalized')
PARCEL_LINKS_DIR = os.path.join(PROJECT_ROOT, 'engines', 'gw', 'pipeline', 'parcel_links')


def resolve_arn(arn_api, client):
    """Resolve a single ARN. Returns (parcel_file, method) or (None, reason)."""
    if not arn_api or all(c == '0' for c in arn_api):
        return None, 'no_arn'

    # 1. Cache check
    if cache_has(arn_api):
        return f'{arn_api}.json', 'arn_cache'

    # 2. API query
    parcel = client.query_by_arn(arn_api)
    if parcel and parcel.get('geometry'):
        cache_write(arn_api, parcel)
        return f'{arn_api}.json', 'arn_api'

    return None, 'arn_api_miss'


def run(dry_run=False):
    """Resolve all normalized GW records to parcels."""
    if not os.path.isdir(NORMALIZED_DIR):
        print(f'ERROR: Normalized directory not found: {NORMALIZED_DIR}')
        sys.exit(1)

    files = sorted(f for f in os.listdir(NORMALIZED_DIR)
                   if f.endswith('.json') and not f.startswith('_'))

    # Check which ones already have parcel links
    os.makedirs(PARCEL_LINKS_DIR, exist_ok=True)
    existing = set(os.listdir(PARCEL_LINKS_DIR))
    pending = [f for f in files if f not in existing]

    print('Cleo Engine -- Resolve GW Parcels')
    print(f'Total records:    {len(files):,}')
    print(f'Already resolved: {len(files) - len(pending):,}')
    print(f'Pending:          {len(pending):,}')
    print()

    if not pending:
        print('Nothing to do.')
        return

    if dry_run:
        # Count how many need API calls
        cache_hits = 0
        need_api = 0
        no_arn = 0
        for fname in pending:
            with open(os.path.join(NORMALIZED_DIR, fname)) as f:
                rec = json.load(f)
            arns = [a.get('arn_api', '') for a in rec.get('assessments', [])]
            arns = [a for a in arns if a and not all(c == '0' for c in a)]
            if not arns:
                no_arn += 1
                continue
            for arn in arns:
                if cache_has(arn):
                    cache_hits += 1
                else:
                    need_api += 1
        print(f'Dry run:')
        print(f'  Cache hits:  {cache_hits:,}')
        print(f'  Need API:    {need_api:,}')
        print(f'  No ARN:      {no_arn:,}')
        return

    # Get token (only needed if we have cache misses)
    print('Loading token...')
    token = load_token()
    if token:
        print('  Using saved token')
    else:
        print('  Fetching fresh token...')
        token = refresh_token()
        print('  Token fetched')
    print()

    client = AgMapsClient(token)

    stats = {'arn_cache': 0, 'arn_api': 0, 'no_arn': 0, 'arn_api_miss': 0, 'errors': 0}
    start = time.time()

    for i, fname in enumerate(pending):
        try:
            with open(os.path.join(NORMALIZED_DIR, fname)) as f:
                rec = json.load(f)

            gw_id = rec.get('gw_id', fname.replace('.json', ''))
            resolutions = []

            for assessment in rec.get('assessments', []):
                arn_api = assessment.get('arn_api', '')

                try:
                    parcel_file, method = resolve_arn(arn_api, client)
                except TokenExpiredError:
                    print(f'\n  Token expired. Refreshing...')
                    client.close()
                    token = refresh_token()
                    client = AgMapsClient(token)
                    parcel_file, method = resolve_arn(arn_api, client)

                resolutions.append({
                    'arn': arn_api,
                    'method': method,
                    'parcel_file': parcel_file,
                })
                stats[method] = stats.get(method, 0) + 1

            # If no assessments, record has no ARN
            if not resolutions:
                stats['no_arn'] += 1

            link = {
                'gw_id': gw_id,
                'pin': rec.get('pin_api', ''),
                'resolutions': resolutions,
            }

            with open(os.path.join(PARCEL_LINKS_DIR, fname), 'w') as f:
                json.dump(link, f, indent=2)

        except Exception as e:
            stats['errors'] += 1
            print(f'  ERROR {fname}: {e}')

        if (i + 1) % 100 == 0 or (i + 1) == len(pending):
            elapsed = time.time() - start
            print(f'  [{i+1:,}/{len(pending):,}] '
                  f'cache: {stats["arn_cache"]:,}  '
                  f'api: {stats["arn_api"]:,}  '
                  f'miss: {stats["arn_api_miss"]:,}  '
                  f'no_arn: {stats["no_arn"]:,}  '
                  f'({elapsed:.0f}s)')

    client.close()

    elapsed = time.time() - start
    print(f'\nDone in {elapsed:.1f}s')
    for k, v in sorted(stats.items()):
        print(f'  {k}: {v:,}')


def main():
    parser = argparse.ArgumentParser(description='Resolve GW records to parcels')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    run(dry_run=args.dry_run)


if __name__ == '__main__':
    main()
