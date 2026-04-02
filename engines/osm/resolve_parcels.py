"""
POI Parcel Resolver -- resolves OSM POIs to provincial parcels via spatial lookup.

For each POI with lat/lng coordinates:
  1. Query AgMaps by spatial point -> find intersecting parcel
  2. If found: cache parcel geometry, enrich POI record with ARN
  3. If not found: mark as unresolved

The parcel cache (clean-data/parcels/) is shared across all data sources.
New parcels discovered here benefit RT and future sources too.

Resumable: skips POIs that already have a 'parcel_status' field.

Usage:
    python engines/osm/resolve_parcels.py
    python engines/osm/resolve_parcels.py --limit 100
    python engines/osm/resolve_parcels.py --dry-run
    python engines/osm/resolve_parcels.py --retry   (re-process unresolved/errors)
"""

import json
import os
import sys
import time
import argparse

# Add engines/rt to path so we can import shared parcel infrastructure
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'engines', 'rt'))
from engines.shared.io import safe_write_json

from parcel_resolver.agmaps import AgMapsClient, TokenExpiredError
from parcel_resolver.token import load_token, refresh_token
from parcel_resolver.cache import cache_has, cache_write


OSM_DIR = os.path.join(PROJECT_ROOT, 'clean-data', 'osm')


def load_poi(path):
    with open(path) as f:
        return json.load(f)


def save_poi(path, poi):
    safe_write_json(path, poi)


def is_pending(poi, retry):
    """Check if a POI still needs resolution."""
    if 'parcel_status' not in poi:
        return True
    if retry and poi['parcel_status'] in ('unresolved', 'no_parcel'):
        return True
    if retry and isinstance(poi.get('parcel_status'), str) and poi['parcel_status'].startswith('error'):
        return True
    return False


def scan_files(retry=False):
    """Scan OSM directory and categorize POI files."""
    if not os.path.isdir(OSM_DIR):
        print(f'ERROR: OSM data directory not found: {OSM_DIR}')
        print(f'Run the POI importer first (Step 2).')
        sys.exit(1)

    all_files = sorted(
        f for f in os.listdir(OSM_DIR)
        if f.endswith('.json') and not f.startswith('_')
    )

    if not all_files:
        print(f'ERROR: No POI files in {OSM_DIR}')
        print(f'Run the POI importer first (Step 2).')
        sys.exit(1)

    pending = []
    done = 0

    for fname in all_files:
        poi = load_poi(os.path.join(OSM_DIR, fname))
        if is_pending(poi, retry):
            pending.append(fname)
        else:
            done += 1

    return all_files, pending, done


def run(limit=None, dry_run=False, retry=False):
    """Run POI parcel resolution."""
    all_files, pending, done = scan_files(retry)

    if limit:
        pending = pending[:limit]

    print('Cleo Engine -- Resolve POI Parcels')
    print(f'Total POI files:   {len(all_files):,}')
    print(f'Already resolved:  {done:,}')
    print(f'Pending:           {len(pending):,}')
    if retry:
        print(f'Mode:              retry (re-processing unresolved/errors)')
    print()

    if not pending:
        print('Nothing to do.')
        return

    if dry_run:
        has_coords = 0
        no_coords = 0
        sample_size = min(len(pending), 1000)
        for fname in pending[:sample_size]:
            poi = load_poi(os.path.join(OSM_DIR, fname))
            coords = poi.get('coords', {})
            if coords.get('lat') and coords.get('lng'):
                has_coords += 1
            else:
                no_coords += 1
        print(f'Sample of {sample_size:,} pending POIs:')
        print(f'  has_coords: {has_coords:,} ({has_coords*100/sample_size:.1f}%)')
        print(f'  no_coords:  {no_coords:,} ({no_coords*100/sample_size:.1f}%)')

        # Estimate time
        api_calls = int(has_coords * len(pending) / sample_size)
        est_seconds = api_calls * 0.4
        est_minutes = est_seconds / 60
        est_hours = est_minutes / 60
        if est_hours >= 1:
            print(f'\n  Estimated API calls: ~{api_calls:,}')
            print(f'  Estimated time:      ~{est_hours:.1f} hours (at 0.4s throttle)')
        else:
            print(f'\n  Estimated API calls: ~{api_calls:,}')
            print(f'  Estimated time:      ~{est_minutes:.0f} minutes (at 0.4s throttle)')
        return

    # --- Token ---
    print('Loading token...')
    token = load_token()
    if token:
        print('  Using saved token (validated)')
    else:
        print('  No saved token -- fetching fresh token via browser...')
        token = refresh_token()
        print('  Token fetched and saved')
    print()

    client = AgMapsClient(token)

    stats = {
        'resolved': 0,
        'no_parcel': 0,
        'no_coords': 0,
        'errors': 0,
    }
    start_time = time.time()

    for i, fname in enumerate(pending):
        filepath = os.path.join(OSM_DIR, fname)

        try:
            poi = load_poi(filepath)

            coords = poi.get('coords', {})
            lat = coords.get('lat')
            lng = coords.get('lng')

            if not lat or not lng:
                poi['arn'] = None
                poi['parcel_status'] = 'no_coords'
                save_poi(filepath, poi)
                stats['no_coords'] += 1
                continue

            # Spatial query -- find parcel containing this point
            try:
                parcel = client.query_by_point(lat, lng)
            except TokenExpiredError:
                print(f'\n  Token expired at record {i+1}. Refreshing...')
                client.close()
                token = refresh_token()
                client = AgMapsClient(token)
                print('  Token refreshed. Retrying...')
                parcel = client.query_by_point(lat, lng)

            if parcel and parcel.get('arn') and parcel.get('geometry'):
                arn = parcel['arn']

                # Filter out all-zeros ARN (invalid)
                if all(c == '0' for c in arn):
                    poi['arn'] = None
                    poi['parcel_status'] = 'no_parcel'
                    save_poi(filepath, poi)
                    stats['no_parcel'] += 1
                    continue

                # Cache the parcel geometry (shared across all data sources)
                if not cache_has(arn):
                    cache_write(arn, parcel)

                poi['arn'] = arn
                poi['parcel_status'] = 'resolved'
                save_poi(filepath, poi)
                stats['resolved'] += 1
            else:
                poi['arn'] = None
                poi['parcel_status'] = 'no_parcel'
                save_poi(filepath, poi)
                stats['no_parcel'] += 1

        except Exception as e:
            stats['errors'] += 1
            try:
                poi = load_poi(filepath)
                poi['arn'] = None
                poi['parcel_status'] = f'error: {e}'
                save_poi(filepath, poi)
            except Exception:
                pass

        # Progress
        if (i + 1) % 500 == 0 or (i + 1) == len(pending):
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            print(
                f'  [{i+1:,}/{len(pending):,}] '
                f'resolved: {stats["resolved"]:,}  '
                f'no_parcel: {stats["no_parcel"]:,}  '
                f'no_coords: {stats["no_coords"]:,}  '
                f'errors: {stats["errors"]:,}  '
                f'({rate:.1f} rec/s, {elapsed:.0f}s)'
            )

    client.close()

    # Summary
    elapsed = time.time() - start_time
    print()
    print(f'Done in {elapsed:.1f}s')
    print(f'  resolved:   {stats["resolved"]:,}')
    print(f'  no_parcel:  {stats["no_parcel"]:,}')
    print(f'  no_coords:  {stats["no_coords"]:,}')
    print(f'  errors:     {stats["errors"]:,}')

    total = sum(stats.values())
    if total > 0:
        print(f'  resolution rate: {stats["resolved"]*100/total:.1f}%')


def main():
    parser = argparse.ArgumentParser(
        description='Resolve OSM POIs to parcels via spatial lookup'
    )
    parser.add_argument('--limit', type=int,
                        help='Process only the first N pending POIs')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be processed without making API calls')
    parser.add_argument('--retry', action='store_true',
                        help='Re-process POIs that were unresolved or errored')
    args = parser.parse_args()

    run(limit=args.limit, dry_run=args.dry_run, retry=args.retry)


if __name__ == '__main__':
    main()
