"""
Resolve OSM POIs to parcels using local Point-in-Polygon only.

Uses each POI's exact rooftop coordinates (the most accurate location data
we have) and checks which cached parcel polygon they fall inside. Zero API
calls — fully local, uses the grid-indexed PIP from cleo/resolver/pip.py.

Usage:
    python -m engines.osm.resolve_pip                  # resolve all unresolved
    python -m engines.osm.resolve_pip --reprocess      # redo all POIs
    python -m engines.osm.resolve_pip --limit 100      # test with N POIs
    python -m engines.osm.resolve_pip --dry-run        # count only, don't write
"""

import argparse
import json
import os
import sys
import time

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from cleo.resolver.pip import ParcelGrid

OSM_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "clean-data", "osm")


def resolve_pois(reprocess: bool = False, limit: int = 0, dry_run: bool = False):
    """Resolve POI coordinates to parcel ARNs via Point-in-Polygon."""

    # Collect POI files
    files = sorted(f for f in os.listdir(OSM_DIR) if f.endswith(".json"))
    print(f"Found {len(files):,} POI files")

    # Load the parcel grid (one-time cost)
    print()
    grid = ParcelGrid()
    grid.load(verbose=True)
    print()

    resolved = 0
    no_coords = 0
    no_parcel = 0
    skipped = 0
    errors = 0
    total = 0

    t0 = time.time()

    for i, fname in enumerate(files):
        if limit and total >= limit:
            break

        fpath = os.path.join(OSM_DIR, fname)
        try:
            with open(fpath) as f:
                poi = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            errors += 1
            continue

        # Skip already-resolved unless reprocessing
        if not reprocess and poi.get("arn"):
            skipped += 1
            continue

        total += 1

        coords = poi.get("coords", {})
        lat = coords.get("lat")
        lng = coords.get("lng")

        if not lat or not lng:
            no_coords += 1
            if not dry_run:
                poi["parcel_status"] = "no_coords"
                poi["arn"] = None
                with open(fpath, "w") as f:
                    json.dump(poi, f, indent=2)
            continue

        # PIP lookup
        arn = grid.find_containing_parcel(lat, lng)

        if arn:
            resolved += 1
            if not dry_run:
                poi["arn"] = arn
                poi["parcel_status"] = "resolved"
                with open(fpath, "w") as f:
                    json.dump(poi, f, indent=2)
        else:
            no_parcel += 1
            if not dry_run:
                poi["parcel_status"] = "no_parcel"
                poi["arn"] = None
                with open(fpath, "w") as f:
                    json.dump(poi, f, indent=2)

        # Progress
        if (total % 5000) == 0:
            elapsed = time.time() - t0
            rate = total / elapsed if elapsed > 0 else 0
            print(f"  {total:,} processed ({resolved:,} resolved, {no_parcel:,} no parcel) — {rate:.0f}/sec")

    elapsed = time.time() - t0

    print()
    print(f"{'DRY RUN — ' if dry_run else ''}Done in {elapsed:.1f}s")
    print(f"  Processed:  {total:,}")
    print(f"  Resolved:   {resolved:,}")
    print(f"  No parcel:  {no_parcel:,}")
    print(f"  No coords:  {no_coords:,}")
    print(f"  Skipped:    {skipped:,}")
    print(f"  Errors:     {errors:,}")
    if total > 0:
        print(f"  Hit rate:   {resolved / total * 100:.1f}%")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Resolve POIs to parcels via local PIP")
    parser.add_argument("--reprocess", action="store_true", help="Re-resolve all POIs")
    parser.add_argument("--limit", type=int, default=0, help="Process only N POIs")
    parser.add_argument("--dry-run", action="store_true", help="Count only, don't write")
    args = parser.parse_args()

    resolve_pois(reprocess=args.reprocess, limit=args.limit, dry_run=args.dry_run)
