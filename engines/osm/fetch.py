"""
OSM POI Fetcher -- downloads all branded POIs in Ontario with full building geometry.

Two-phase fetch:
  1. All branded POIs with full way geometry (out geom tags)
  2. Enclosing building polygons for node POIs (batched around queries)

Output: raw-data/osm/branded_pois.json + raw-data/osm/building_lookups.json

Usage:
    python engines/osm/fetch.py
    python engines/osm/fetch.py --skip-buildings   (skip building lookup phase)
    python engines/osm/fetch.py --buildings-only    (only run building lookups)
"""

import json
import os
import sys
import time
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

import httpx

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
RAW_DIR = os.path.join(PROJECT_ROOT, 'raw-data', 'osm')

OVERPASS_SERVERS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]

BRANDED_QUERY = """
[out:json][timeout:180];
area["name"="Ontario"]["admin_level"="4"]->.ontario;
(
  node["brand"](area.ontario);
  way["brand"](area.ontario);
);
out geom tags;
"""


def query_overpass(query, timeout=240):
    """Run an Overpass query with server failover."""
    for server_url in OVERPASS_SERVERS:
        try:
            print(f'  Querying {server_url.split("//")[1].split("/")[0]}...')
            client = httpx.Client(timeout=timeout)
            resp = client.post(server_url, data={"data": query})
            resp.raise_for_status()
            data = resp.json()
            client.close()
            return data
        except Exception as e:
            print(f'  Failed: {e}')
            continue

    raise RuntimeError("All Overpass servers failed")


def fetch_branded_pois():
    """Phase 1: Fetch all branded POIs in Ontario with full geometry."""
    out_path = os.path.join(RAW_DIR, 'branded_pois.json')

    print('Phase 1: Fetching all branded POIs in Ontario...')
    start = time.time()

    data = query_overpass(BRANDED_QUERY, timeout=240)

    elements = data.get('elements', [])
    elapsed = time.time() - start
    print(f'  Got {len(elements):,} elements in {elapsed:.0f}s')

    # Count nodes vs ways
    nodes = sum(1 for e in elements if e['type'] == 'node')
    ways = sum(1 for e in elements if e['type'] == 'way')
    print(f'  Nodes: {nodes:,}  Ways: {ways:,}')

    with open(out_path, 'w') as f:
        json.dump(data, f)
    print(f'  Saved to {out_path}')

    return elements


def _match_node_to_building(n_lat, n_lng, buildings):
    """Find the building that contains a point."""
    best_building = None
    best_dist = float('inf')

    for bldg in buildings:
        if bldg['type'] != 'way' or 'geometry' not in bldg:
            continue
        geom = bldg['geometry']
        lats = [p['lat'] for p in geom]
        lngs = [p['lon'] for p in geom]
        if min(lats) <= n_lat <= max(lats) and min(lngs) <= n_lng <= max(lngs):
            c_lat = sum(lats) / len(lats)
            c_lng = sum(lngs) / len(lngs)
            dist = abs(n_lat - c_lat) + abs(n_lng - c_lng)
            if dist < best_dist:
                best_dist = dist
                best_building = bldg

    if not best_building:
        return None

    tags = best_building.get('tags', {})
    geom = best_building['geometry']
    polygon = [[p['lon'], p['lat']] for p in geom]
    return {
        'building_osm_id': f"way/{best_building['id']}",
        'polygon': polygon,
        'tags': {
            'addr:housenumber': tags.get('addr:housenumber', ''),
            'addr:street': tags.get('addr:street', ''),
            'addr:city': tags.get('addr:city', ''),
            'addr:postcode': tags.get('addr:postcode', ''),
        },
    }


def _query_with_retry(query, max_retries=3, timeout=60):
    """Query Overpass with retry and exponential backoff."""
    for attempt in range(max_retries):
        for server_url in OVERPASS_SERVERS:
            try:
                client = httpx.Client(timeout=timeout)
                resp = client.post(server_url, data={"data": query})
                resp.raise_for_status()
                data = resp.json()
                client.close()
                return data
            except Exception:
                continue
        # All servers failed this attempt — backoff
        if attempt < max_retries - 1:
            time.sleep(5 * (attempt + 1))
    return None


def fetch_building_lookups(elements):
    """Phase 2: For node POIs, find enclosing buildings.

    Strategy: small batches of 5 nodes, each queried with around:15.
    Lightweight queries that Overpass handles easily.

    - Incremental saves every 50 batches (crash-safe)
    - Resumable: skips nodes already in building_lookups.json
    - Retry with backoff on failure
    """
    out_path = os.path.join(RAW_DIR, 'building_lookups.json')

    # Load existing lookups (for resume)
    all_lookups = {}
    if os.path.isfile(out_path):
        with open(out_path) as f:
            all_lookups = json.load(f)
        print(f'  Loaded {len(all_lookups):,} existing lookups (resuming)', flush=True)

    node_pois = [e for e in elements if e['type'] == 'node']
    pending_nodes = [n for n in node_pois if f"node/{n['id']}" not in all_lookups]

    print(f'\nPhase 2: Looking up enclosing buildings for node POIs', flush=True)
    print(f'  Total nodes:   {len(node_pois):,}', flush=True)
    print(f'  Already done:  {len(node_pois) - len(pending_nodes):,}', flush=True)
    print(f'  Pending:       {len(pending_nodes):,}', flush=True)

    if not pending_nodes:
        print('  Nothing to do.')
        return all_lookups

    BATCH_SIZE = 5
    SAVE_EVERY = 50

    batches = []
    for i in range(0, len(pending_nodes), BATCH_SIZE):
        batches.append(pending_nodes[i:i + BATCH_SIZE])

    print(f'  {len(batches):,} batches of {BATCH_SIZE}, saving every {SAVE_EVERY}', flush=True)

    start = time.time()
    failed = 0

    for batch_idx, batch in enumerate(batches):
        union_parts = []
        for node in batch:
            lat = node.get('lat')
            lng = node.get('lon')
            if lat and lng:
                union_parts.append(f'way["building"](around:15,{lat},{lng});')

        if not union_parts:
            continue

        query = f'[out:json][timeout:30];\n(\n  {chr(10).join(union_parts)}\n);\nout geom tags;'

        data = _query_with_retry(query, max_retries=2, timeout=45)

        if data:
            buildings = data.get('elements', [])
            for node in batch:
                osm_id = f"node/{node['id']}"
                result = _match_node_to_building(node['lat'], node['lon'], buildings)
                if result:
                    all_lookups[osm_id] = result
        else:
            failed += 1

        # Progress
        if (batch_idx + 1) % 20 == 0 or (batch_idx + 1) == len(batches):
            elapsed = time.time() - start
            rate = (batch_idx + 1) / elapsed if elapsed > 0 else 0
            remaining = (len(batches) - batch_idx - 1) / rate if rate > 0 else 0
            print(
                f'  [{batch_idx + 1:,}/{len(batches):,}] '
                f'buildings: {len(all_lookups):,}  '
                f'failed: {failed:,}  '
                f'({elapsed:.0f}s, ~{remaining / 60:.0f}m left)',
                flush=True,
            )

        # Incremental save
        if (batch_idx + 1) % SAVE_EVERY == 0:
            with open(out_path, 'w') as f:
                json.dump(all_lookups, f)

        # Rate limit — 1 request per second
        time.sleep(1)

    # Final save
    with open(out_path, 'w') as f:
        json.dump(all_lookups, f)

    elapsed = time.time() - start
    print(f'\n  Done in {elapsed:.0f}s — {len(all_lookups):,} buildings found for {len(node_pois):,} nodes')
    return all_lookups


def run(skip_buildings=False, buildings_only=False):
    os.makedirs(RAW_DIR, exist_ok=True)

    if buildings_only:
        # Load existing branded POIs
        pois_path = os.path.join(RAW_DIR, 'branded_pois.json')
        if not os.path.isfile(pois_path):
            print('ERROR: No branded_pois.json found. Run without --buildings-only first.')
            sys.exit(1)
        with open(pois_path) as f:
            elements = json.load(f).get('elements', [])
        fetch_building_lookups(elements)
        return

    elements = fetch_branded_pois()

    if not skip_buildings:
        fetch_building_lookups(elements)
    else:
        print('\nSkipping building lookups (--skip-buildings)')

    print('\nFetch complete.')


def main():
    parser = argparse.ArgumentParser(description='Fetch branded POIs from Overpass with geometry')
    parser.add_argument('--skip-buildings', action='store_true',
                        help='Skip the building lookup phase')
    parser.add_argument('--buildings-only', action='store_true',
                        help='Only run building lookups (requires previous branded fetch)')
    args = parser.parse_args()

    run(skip_buildings=args.skip_buildings, buildings_only=args.buildings_only)


if __name__ == '__main__':
    main()
