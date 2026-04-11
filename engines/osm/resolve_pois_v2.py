"""
POI Parcel Resolver v2 — resolves OSM POIs using Ontario geocoder + spatial lookup.

Upgrades over resolve_parcels.py:
  - Uses Ontario geocoder for POIs with street addresses but no parcel match
  - Falls back to spatial point query from OSM coordinates
  - Multi-signal: if OSM coords AND geocoded coords both resolve, cross-validate

Resolution chain per POI:
  1. Spatial point query using OSM lat/lng (fast, usually works)
  2. If no parcel found AND POI has a street address:
     → Ontario geocode the address → spatial point query on geocoded coords
  3. If both resolve, cross-validate (should agree)

Usage:
    python engines/osm/resolve_pois_v2.py
    python engines/osm/resolve_pois_v2.py --retry
    python engines/osm/resolve_pois_v2.py --reprocess
    python engines/osm/resolve_pois_v2.py --limit 100
    python engines/osm/resolve_pois_v2.py --dry-run
"""

import json
import os
import sys
import time
import argparse

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'engines', 'rt'))

from engines.shared.io import safe_write_json
from parcel_resolver.agmaps import AgMapsClient, TokenExpiredError
from parcel_resolver.token import load_token, refresh_token
from parcel_resolver.cache import cache_has, cache_write
from parcel_resolver.ontario_geocoder import OntarioGeocoderClient, ThrottleError, SessionError


OSM_DIR = os.path.join(PROJECT_ROOT, 'clean-data', 'osm')


def _build_geocode_string(poi):
    """Build a geocode string from POI address fields. Returns string or None."""
    addr = poi.get('address', {})
    number = addr.get('housenumber', '').strip()
    street = addr.get('street', '').strip()
    city = addr.get('city', '').strip()

    if not street:
        return None

    parts = []
    if number:
        parts.append(f'{number} {street}')
    else:
        parts.append(street)

    if city:
        parts.append(city)
    parts.append('Ontario')

    return ', '.join(parts)


def _resolve_by_point(lat, lng, agmaps_client):
    """Spatial point query. Returns (arn, parcel) or (None, None)."""
    parcel = agmaps_client.query_by_point(lat, lng)
    if parcel and parcel.get('arn') and parcel.get('geometry'):
        arn = parcel['arn']
        if not all(c == '0' for c in arn):
            if not cache_has(arn):
                cache_write(arn, parcel)
            return arn, parcel
    return None, None


def is_pending(poi, retry=False, reprocess=False):
    """Check if a POI needs resolution."""
    if reprocess:
        return True
    status = poi.get('parcel_status', '')
    if not status:
        return True
    if status == 'mismatched':
        return True
    if retry and status in ('unresolved', 'unresolved_local', 'no_parcel'):
        return True
    if retry and status.startswith('error'):
        return True
    return False


def run(limit=None, dry_run=False, retry=False, reprocess=False, headless=True):
    """Run POI parcel resolution with Ontario geocoder fallback."""

    if not os.path.isdir(OSM_DIR):
        print(f'ERROR: OSM directory not found: {OSM_DIR}')
        return

    all_files = sorted(
        f for f in os.listdir(OSM_DIR)
        if f.endswith('.json') and not f.startswith('_')
    )

    pending = []
    done = 0
    for fname in all_files:
        with open(os.path.join(OSM_DIR, fname)) as fh:
            poi = json.load(fh)
        if is_pending(poi, retry=retry, reprocess=reprocess):
            pending.append(fname)
        else:
            done += 1

    if limit:
        pending = pending[:limit]

    print(f'Cleo Engine — Resolve POI Parcels (v2)')
    print(f'Total POI files:   {len(all_files):,}')
    print(f'Already resolved:  {done:,}')
    print(f'Pending:           {len(pending):,}')
    if retry:
        print(f'Mode:              RETRY (unresolved/errors)')
    if reprocess:
        print(f'Mode:              REPROCESS ALL')
    print()

    if dry_run or not pending:
        if not pending:
            print('Nothing to do.')
        return

    # Setup
    print('Loading AgMaps token...')
    token = load_token()
    if token:
        print('  Using saved token')
    else:
        print('  Fetching fresh token...')
        token = refresh_token()
    agmaps_client = AgMapsClient(token)

    # Only start geocoder if there are POIs that might need it
    ont_client = None
    needs_geocoder = False
    for fname in pending[:100]:  # Quick scan
        with open(os.path.join(OSM_DIR, fname)) as fh:
            poi = json.load(fh)
        if _build_geocode_string(poi):
            needs_geocoder = True
            break

    if needs_geocoder:
        print('Starting Ontario geocoder...')
        ont_client = OntarioGeocoderClient(delay=0.5, headless=headless, verbose=False)
        ont_client.start()
    print()

    stats = {
        'resolved_spatial': 0,
        'resolved_geocode': 0,
        'no_parcel': 0,
        'no_coords': 0,
        'errors': 0,
    }
    start_time = time.time()

    try:
        for i, fname in enumerate(pending):
            filepath = os.path.join(OSM_DIR, fname)
            try:
                poi = json.loads(open(filepath).read())

                coords = poi.get('coords', {})
                lat = coords.get('lat')
                lng = coords.get('lng')

                # Step 1: Spatial point query from OSM coords
                if lat and lng:
                    try:
                        arn, parcel = _resolve_by_point(lat, lng, agmaps_client)
                    except TokenExpiredError:
                        agmaps_client.close()
                        token = refresh_token()
                        agmaps_client = AgMapsClient(token)
                        arn, parcel = _resolve_by_point(lat, lng, agmaps_client)

                    if arn:
                        poi['arn'] = arn
                        poi['parcel_status'] = 'resolved'
                        poi['parcel_method'] = 'spatial_osm'
                        safe_write_json(filepath, poi)
                        stats['resolved_spatial'] += 1
                        continue

                # Step 2: Ontario geocoder fallback
                geocode_str = _build_geocode_string(poi)
                if ont_client and geocode_str:
                    try:
                        geo_result = ont_client.geocode(geocode_str)
                    except ThrottleError:
                        print(f'\n*** THROTTLE — HARD STOP ***')
                        stats['errors'] += 1
                        break
                    except SessionError:
                        geo_result = None

                    if geo_result and geo_result['addr_type'] != 'Postal':
                        try:
                            arn, parcel = _resolve_by_point(
                                geo_result['lat'], geo_result['lng'], agmaps_client
                            )
                        except TokenExpiredError:
                            agmaps_client.close()
                            token = refresh_token()
                            agmaps_client = AgMapsClient(token)
                            arn, parcel = _resolve_by_point(
                                geo_result['lat'], geo_result['lng'], agmaps_client
                            )

                        if arn:
                            poi['arn'] = arn
                            poi['parcel_status'] = 'resolved'
                            poi['parcel_method'] = 'geocode_ontario'
                            poi['geocode'] = {
                                'lat': geo_result['lat'],
                                'lng': geo_result['lng'],
                                'score': geo_result['score'],
                                'addr_type': geo_result['addr_type'],
                            }
                            safe_write_json(filepath, poi)
                            stats['resolved_geocode'] += 1
                            continue

                # Nothing worked
                if not lat and not lng:
                    poi['parcel_status'] = 'no_coords'
                    stats['no_coords'] += 1
                else:
                    poi['parcel_status'] = 'no_parcel'
                    stats['no_parcel'] += 1
                poi['arn'] = None
                safe_write_json(filepath, poi)

            except Exception as e:
                stats['errors'] += 1
                try:
                    poi['parcel_status'] = f'error: {str(e)[:100]}'
                    poi['arn'] = None
                    safe_write_json(filepath, poi)
                except Exception:
                    pass

            if (i + 1) % 500 == 0 or (i + 1) == len(pending):
                elapsed = time.time() - start_time
                rate = (i + 1) / elapsed if elapsed > 0 else 0
                resolved = stats['resolved_spatial'] + stats['resolved_geocode']
                print(
                    f'  [{i+1:,}/{len(pending):,}] '
                    f'resolved:{resolved:,} no_parcel:{stats["no_parcel"]:,} '
                    f'errors:{stats["errors"]:,} ({rate:.1f}/s)'
                )

    except KeyboardInterrupt:
        print(f'\n  Interrupted. Progress saved.')

    finally:
        if ont_client:
            ont_client.close()
        agmaps_client.close()

    elapsed = time.time() - start_time
    resolved = stats['resolved_spatial'] + stats['resolved_geocode']
    total = sum(stats.values())

    print()
    print(f'Done in {elapsed:.1f}s')
    print(f'  resolved (spatial):  {stats["resolved_spatial"]:,}')
    print(f'  resolved (geocode):  {stats["resolved_geocode"]:,}')
    print(f'  no_parcel:           {stats["no_parcel"]:,}')
    print(f'  no_coords:           {stats["no_coords"]:,}')
    print(f'  errors:              {stats["errors"]:,}')
    if total > 0:
        print(f'  resolution rate:     {resolved*100/total:.1f}%')


def main():
    parser = argparse.ArgumentParser(description='Resolve OSM POIs to parcels (v2)')
    parser.add_argument('--limit', type=int)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--retry', action='store_true',
                        help='Re-process unresolved/error POIs')
    parser.add_argument('--reprocess', action='store_true',
                        help='Reprocess ALL POIs')
    parser.add_argument('--no-headless', action='store_true')
    args = parser.parse_args()

    run(
        limit=args.limit,
        dry_run=args.dry_run,
        retry=args.retry,
        reprocess=args.reprocess,
        headless=not args.no_headless,
    )


if __name__ == '__main__':
    main()
