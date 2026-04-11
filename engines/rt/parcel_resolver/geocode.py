"""
Geocoder — geocodes RT addresses via Mapbox and resolves to parcels spatially.

Two modes:
  --preflight  : Builds and reports the geocode queue (ZERO API calls)
  --run        : Executes geocoding on the approved queue

Rate limiting: 5 req/sec (half Mapbox's 600/min limit)
On 429: STOPS immediately (our rate is wrong, fix it)
Incremental saves every 100 geocodes. Fully resumable.

Usage:
    python -m parcel_resolver.geocode --preflight
    python -m parcel_resolver.geocode --run
    python -m parcel_resolver.geocode --run --limit 100
"""

import json
import os
import re
import sys
import time
import argparse

import requests

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, PROJECT_ROOT)
from engines.shared.io import safe_write_json, safe_read_json

ADDRESSES_DIR = os.path.join(PROJECT_ROOT, 'engines', 'rt', 'pipeline', 'addresses')
PARCEL_LINKS_DIR = os.path.join(PROJECT_ROOT, 'engines', 'rt', 'pipeline', 'parcel_links')
GEOCODED_DIR = os.path.join(PROJECT_ROOT, 'engines', 'rt', 'pipeline', 'geocoded')
QUEUE_FILE = os.path.join(PROJECT_ROOT, 'engines', 'rt', 'pipeline', 'geocode_queue.json')

# Mapbox config
MAPBOX_TOKEN = os.environ.get('MAPBOX_TOKEN', '')
MAPBOX_ENDPOINT = 'https://api.mapbox.com/geocoding/v5/mapbox.places'
RATE_LIMIT = 0.2  # 200ms between requests = 5/sec
MIN_RELEVANCE = 0.6

# Ontario bounding box for Mapbox
ONTARIO_BBOX = '-96,41,-74,57'

# Garbage address patterns — skip these
GARBAGE_PATTERNS = [
    r'^Conc\s', r'^Con\s', r'^Sr\s', r'^Lot\s', r'^Part\s',
    r'^Plan\s', r'^Block\s', r'^Twp\s', r'^Rr\s\d', r'^Highway\s\d+$',
    r'^Hwy\s\d+$', r'^County Road\s\d+$',
]


def _load_mapbox_token():
    """Load Mapbox token from env or frontend .env file."""
    token = MAPBOX_TOKEN
    if token:
        return token

    # Try frontend .env
    env_path = os.path.join(PROJECT_ROOT, 'frontend', '.env')
    if os.path.isfile(env_path):
        with open(env_path) as f:
            for line in f:
                if line.startswith('VITE_MAPBOX_TOKEN='):
                    return line.split('=', 1)[1].strip()

    return ''


def _is_geocodable_address(addr_record):
    """Check if an address record is worth geocoding (tier 1 only)."""
    if not addr_record.get('geocodable'):
        return False
    if not addr_record.get('geocode_string'):
        return False

    display = addr_record.get('display', '')
    if not display:
        return False

    # Check for garbage patterns
    for pattern in GARBAGE_PATTERNS:
        if re.match(pattern, display, re.IGNORECASE):
            return False

    # Must have street number
    components = addr_record.get('components', {})
    if not components.get('street_number', '').strip():
        return False

    # Reject lot continuations: street_name is only numbers/commas/ampersands/dashes
    street_name = components.get('street_name', '').strip()
    if street_name and re.match(r'^[-,&\s\d]+$', street_name):
        return False

    return True


def build_preflight_queue():
    """Scan all unresolved RT records and build the geocode queue.

    Zero API calls. Reports exactly what would be geocoded.
    """
    all_files = sorted(f for f in os.listdir(ADDRESSES_DIR) if f.endswith('.json'))
    existing_links = {}
    if os.path.isdir(PARCEL_LINKS_DIR):
        for f in os.listdir(PARCEL_LINKS_DIR):
            if f.endswith('.json'):
                existing_links[f] = True

    # Track already-geocoded results for resume
    already_geocoded = set()
    if os.path.isdir(GEOCODED_DIR):
        for f in os.listdir(GEOCODED_DIR):
            if f.endswith('.json'):
                already_geocoded.add(f)

    queue = []  # (filename, rt_id, geocode_string)
    geocode_strings = {}  # dedup: geocode_string -> first filename

    stats = {
        'total': 0,
        'already_resolved': 0,
        'already_geocoded': 0,
        'no_geocodable_addr': 0,
        'queued': 0,
        'dedup_saved': 0,
    }

    for fname in all_files:
        stats['total'] += 1

        with open(os.path.join(ADDRESSES_DIR, fname)) as f:
            rec = json.load(f)

        # Skip already resolved
        if fname in existing_links:
            try:
                with open(os.path.join(PARCEL_LINKS_DIR, fname)) as f:
                    link = json.load(f)
                if link.get('resolved_arn'):
                    stats['already_resolved'] += 1
                    continue
            except (json.JSONDecodeError, OSError):
                pass  # corrupted file — re-process

        # Skip already geocoded
        if fname in already_geocoded:
            stats['already_geocoded'] += 1
            continue

        # Find best geocodable address
        rt_id = rec.get('rt_id', fname.split('__')[0])
        addrs = rec.get('property', {}).get('addresses', [])

        best_geocode = None
        for addr in addrs:
            if _is_geocodable_address(addr):
                best_geocode = addr.get('geocode_string')
                break

        if not best_geocode:
            stats['no_geocodable_addr'] += 1
            continue

        # Dedup by geocode_string
        if best_geocode in geocode_strings:
            stats['dedup_saved'] += 1
            # Still add to queue but mark as dedup (will reuse result)
            queue.append({
                'filename': fname,
                'rt_id': rt_id,
                'geocode_string': best_geocode,
                'dedup_of': geocode_strings[best_geocode],
            })
        else:
            geocode_strings[best_geocode] = fname
            queue.append({
                'filename': fname,
                'rt_id': rt_id,
                'geocode_string': best_geocode,
                'dedup_of': None,
            })

        stats['queued'] += 1

    unique_addresses = len(geocode_strings)
    return queue, stats, unique_addresses


def run_preflight():
    """Build and report the geocode queue. Zero API calls."""
    print('Cleo Engine — Geocode Pre-flight')
    print()

    queue, stats, unique_addresses = build_preflight_queue()

    print(f'Scan results:')
    print(f'  Total address files:  {stats["total"]:,}')
    print(f'  Already resolved:     {stats["already_resolved"]:,}')
    print(f'  Already geocoded:     {stats["already_geocoded"]:,}')
    print(f'  No geocodable addr:   {stats["no_geocodable_addr"]:,}')
    print(f'  Queued for geocoding: {stats["queued"]:,}')
    print(f'  Dedup savings:        {stats["dedup_saved"]:,}')
    print()
    print(f'  Unique addresses to geocode: {unique_addresses:,}')
    print(f'  Estimated Mapbox API calls:  {unique_addresses:,}')
    print(f'  At 5 req/sec:                ~{unique_addresses // 5 // 60} min')
    print()

    # Save queue
    os.makedirs(os.path.dirname(QUEUE_FILE), exist_ok=True)
    safe_write_json(QUEUE_FILE, {
        'stats': stats,
        'unique_addresses': unique_addresses,
        'queue': queue,
    })

    print(f'Queue saved to {QUEUE_FILE}')
    print(f'Review the queue, then run with --run to start geocoding.')


def geocode_address(geocode_string, token):
    """Geocode a single address via Mapbox. Returns (lat, lng, relevance) or None."""
    url = f'{MAPBOX_ENDPOINT}/{requests.utils.quote(geocode_string)}.json'
    params = {
        'access_token': token,
        'country': 'ca',
        'bbox': ONTARIO_BBOX,
        'types': 'address',
        'limit': 1,
    }

    resp = requests.get(url, params=params, timeout=10)

    if resp.status_code == 429:
        print('\n  ERROR: 429 Rate Limited. STOPPING. Fix the rate limit.', flush=True)
        sys.exit(1)

    if resp.status_code >= 500:
        return None  # Server error, caller will retry

    resp.raise_for_status()
    data = resp.json()

    features = data.get('features', [])
    if not features:
        return None

    feature = features[0]
    relevance = feature.get('relevance', 0)

    if relevance < MIN_RELEVANCE:
        return None

    # Validate it's in Ontario
    context = feature.get('context', [])
    in_ontario = any('Ontario' in c.get('text', '') for c in context)
    if not in_ontario:
        # Check place_name as fallback
        if 'Ontario' not in feature.get('place_name', ''):
            return None

    coords = feature.get('center', [])
    if len(coords) != 2:
        return None

    lng, lat = coords
    return {
        'lat': lat,
        'lng': lng,
        'relevance': relevance,
        'place_name': feature.get('place_name', ''),
    }


def run_geocoding(limit=None):
    """Execute geocoding on the approved queue."""
    token = _load_mapbox_token()
    if not token:
        print('ERROR: No Mapbox token found. Set MAPBOX_TOKEN env var or check frontend/.env')
        sys.exit(1)

    if not os.path.isfile(QUEUE_FILE):
        print('ERROR: No geocode queue. Run --preflight first.')
        sys.exit(1)

    with open(QUEUE_FILE) as f:
        queue_data = json.load(f)

    queue = queue_data.get('queue', [])
    unique_addresses = queue_data.get('unique_addresses', 0)

    print('Cleo Engine — Geocode Addresses')
    print(f'Queue size:       {len(queue):,}')
    print(f'Unique addresses: {unique_addresses:,}')
    print()

    os.makedirs(GEOCODED_DIR, exist_ok=True)

    # Build unique address list (skip dedup entries)
    unique_queue = [q for q in queue if q.get('dedup_of') is None]

    # Filter already geocoded
    already = set(f for f in os.listdir(GEOCODED_DIR) if f.endswith('.json'))
    pending = [q for q in unique_queue if q['filename'] not in already]

    if limit:
        pending = pending[:limit]

    print(f'Already geocoded: {len(already):,}')
    print(f'Pending:          {len(pending):,}')
    print(f'Rate: 5 req/sec (200ms between)')
    print()

    if not pending:
        print('Nothing to geocode.')
        return

    stats = {'geocoded': 0, 'failed': 0, 'low_relevance': 0, 'errors': 0}
    start = time.time()

    # Geocode results cache (for dedup reuse)
    results_cache = {}

    for i, item in enumerate(pending):
        geocode_string = item['geocode_string']
        fname = item['filename']

        # Check results cache (dedup)
        if geocode_string in results_cache:
            result = results_cache[geocode_string]
        else:
            try:
                result = geocode_address(geocode_string, token)
                time.sleep(RATE_LIMIT)
            except Exception as e:
                stats['errors'] += 1
                result = None

            results_cache[geocode_string] = result

        # Write result
        output = {
            'rt_id': item['rt_id'],
            'geocode_string': geocode_string,
            'result': result,
        }

        safe_write_json(os.path.join(GEOCODED_DIR, fname), output)

        if result:
            stats['geocoded'] += 1
        else:
            stats['failed'] += 1

        # Progress
        if (i + 1) % 100 == 0 or (i + 1) == len(pending):
            elapsed = time.time() - start
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            remaining = (len(pending) - i - 1) / rate if rate > 0 else 0
            print(
                f'  [{i+1:,}/{len(pending):,}] '
                f'geocoded: {stats["geocoded"]:,}  '
                f'failed: {stats["failed"]:,}  '
                f'errors: {stats["errors"]:,}  '
                f'({elapsed:.0f}s, ~{remaining/60:.0f}m left)',
                flush=True,
            )

    # Now apply dedup results — copy geocode results for dedup entries
    dedup_entries = [q for q in queue if q.get('dedup_of') is not None]
    dedup_applied = 0
    for item in dedup_entries:
        source_fname = item['dedup_of']
        target_fname = item['filename']
        source_path = os.path.join(GEOCODED_DIR, source_fname)
        if os.path.isfile(source_path) and target_fname not in already:
            with open(source_path) as f:
                source_result = json.load(f)
            output = {
                'rt_id': item['rt_id'],
                'geocode_string': item['geocode_string'],
                'result': source_result.get('result'),
            }
            with open(os.path.join(GEOCODED_DIR, target_fname), 'w') as f:
                json.dump(output, f, indent=2)
            dedup_applied += 1

    elapsed = time.time() - start
    print(f'\nDone in {elapsed:.0f}s')
    print(f'  Geocoded:      {stats["geocoded"]:,}')
    print(f'  Failed:        {stats["failed"]:,}')
    print(f'  Errors:        {stats["errors"]:,}')
    print(f'  Dedup applied: {dedup_applied:,}')


def main():
    parser = argparse.ArgumentParser(description='Geocode RT addresses via Mapbox')
    parser.add_argument('--preflight', action='store_true',
                        help='Build and report geocode queue (zero API calls)')
    parser.add_argument('--run', action='store_true',
                        help='Execute geocoding on approved queue')
    parser.add_argument('--limit', type=int,
                        help='Geocode only first N addresses')
    args = parser.parse_args()

    if args.preflight:
        run_preflight()
    elif args.run:
        run_geocoding(limit=args.limit)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
