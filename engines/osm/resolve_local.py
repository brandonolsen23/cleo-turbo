"""
Local POI parcel re-resolver — uses cached parcel geometries only, no API calls.

For each POI with status 'mismatched', tests the POI's lat/lng against all
cached parcel polygons to find the correct containing parcel.

Uses a simple grid-based spatial index to avoid testing all 84K parcels for
each POI. Parcels are bucketed by their bounding box into ~0.01° grid cells.

Usage:
    python engines/osm/resolve_local.py
    python engines/osm/resolve_local.py --dry-run
"""

import json
import os
import sys
import time
from collections import defaultdict

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
PARCEL_DIR = os.path.join(PROJECT_ROOT, 'clean-data', 'parcels')
OSM_DIR = os.path.join(PROJECT_ROOT, 'clean-data', 'osm')

# Grid cell size in degrees (~1.1km at Ontario latitudes)
GRID_SIZE = 0.01


def point_in_polygon(x, y, polygon):
    """Ray-casting point-in-polygon test."""
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def grid_key(lng, lat):
    """Return grid cell key for a coordinate."""
    return (int(lng / GRID_SIZE), int(lat / GRID_SIZE))


def load_parcel_index():
    """Load all cached parcels into a spatial grid index."""
    print("Loading parcel cache into spatial index...")
    index = defaultdict(list)  # grid_key → [(arn, ring)]
    count = 0
    errors = 0

    for fname in os.listdir(PARCEL_DIR):
        if not fname.endswith('.json'):
            continue
        arn = fname[:-5]  # strip .json

        try:
            with open(os.path.join(PARCEL_DIR, fname)) as f:
                parcel = json.load(f)
        except (json.JSONDecodeError, OSError):
            errors += 1
            continue

        geom = parcel.get('geometry', {})
        coords = geom.get('coordinates', [[]])
        if not coords or not coords[0] or len(coords[0]) < 3:
            continue

        ring = coords[0]

        # Compute bounding box
        lngs = [p[0] for p in ring]
        lats = [p[1] for p in ring]
        min_lng, max_lng = min(lngs), max(lngs)
        min_lat, max_lat = min(lats), max(lats)

        # Insert into all grid cells the bbox overlaps
        for gx in range(int(min_lng / GRID_SIZE) - 1, int(max_lng / GRID_SIZE) + 2):
            for gy in range(int(min_lat / GRID_SIZE) - 1, int(max_lat / GRID_SIZE) + 2):
                index[(gx, gy)].append((arn, ring))

        count += 1
        if count % 20000 == 0:
            print(f"  {count:,} parcels loaded...")

    print(f"  {count:,} parcels indexed into {len(index):,} grid cells ({errors} errors)")
    return index


def find_containing_parcel(lng, lat, index):
    """Find the parcel that contains the given point using the grid index."""
    key = grid_key(lng, lat)

    # Check the cell the point falls in
    candidates = index.get(key, [])

    for arn, ring in candidates:
        if point_in_polygon(lng, lat, ring):
            return arn

    return None


def run(dry_run=False):
    """Re-resolve mismatched POIs using cached parcel geometries."""
    # Scan for mismatched POIs
    pending = []
    resolved = 0
    other = 0

    for fname in sorted(os.listdir(OSM_DIR)):
        if not fname.endswith('.json'):
            continue
        with open(os.path.join(OSM_DIR, fname)) as f:
            poi = json.load(f)
        if poi.get('parcel_status') == 'mismatched':
            pending.append(fname)
        elif poi.get('parcel_status') == 'resolved':
            resolved += 1
        else:
            other += 1

    print("Cleo Engine -- Local POI Parcel Re-resolver")
    print(f"  Already resolved:  {resolved:,}")
    print(f"  Mismatched:        {len(pending):,}")
    print(f"  Other:             {other:,}")
    print()

    if not pending:
        print("Nothing to do.")
        return

    if dry_run:
        print(f"Would re-resolve {len(pending):,} POIs against cached parcels.")
        return

    # Build spatial index
    index = load_parcel_index()
    print()

    # Re-resolve
    stats = {'resolved': 0, 'unresolved': 0, 'no_coords': 0}
    start = time.time()

    for i, fname in enumerate(pending):
        filepath = os.path.join(OSM_DIR, fname)
        with open(filepath) as f:
            poi = json.load(f)

        coords = poi.get('coords', {})
        lat = coords.get('lat')
        lng = coords.get('lng')

        if not lat or not lng:
            poi['parcel_status'] = 'no_coords'
            with open(filepath, 'w') as f:
                json.dump(poi, f, indent=2)
            stats['no_coords'] += 1
            continue

        arn = find_containing_parcel(lng, lat, index)

        if arn and not all(c == '0' for c in arn):
            poi['arn'] = arn
            poi['parcel_status'] = 'resolved'
            stats['resolved'] += 1
        else:
            poi['arn'] = None
            poi['parcel_status'] = 'unresolved_local'
            stats['unresolved'] += 1

        with open(filepath, 'w') as f:
            json.dump(poi, f, indent=2)

        if (i + 1) % 1000 == 0 or (i + 1) == len(pending):
            elapsed = time.time() - start
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            print(
                f"  [{i+1:,}/{len(pending):,}] "
                f"resolved: {stats['resolved']:,}  "
                f"unresolved: {stats['unresolved']:,}  "
                f"({rate:.0f} rec/s, {elapsed:.1f}s)"
            )

    elapsed = time.time() - start
    print()
    print(f"Done in {elapsed:.1f}s")
    print(f"  resolved:    {stats['resolved']:,}")
    print(f"  unresolved:  {stats['unresolved']:,}")
    print(f"  no_coords:   {stats['no_coords']:,}")
    if stats['resolved'] + stats['unresolved'] > 0:
        total = stats['resolved'] + stats['unresolved']
        print(f"  hit rate:    {stats['resolved']*100/total:.1f}%")

    if stats['unresolved'] > 0:
        print(f"\n  {stats['unresolved']} POIs still unresolved — these need the AgMaps API")
        print(f"  Run: python engines/osm/resolve_parcels.py --retry")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Re-resolve mismatched POIs using cached parcels')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    run(dry_run=args.dry_run)
