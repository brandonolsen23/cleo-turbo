"""
POI Importer -- imports V3 OSM POI data into Turbo.

Copies pre-normalized POI JSON files from V3's osm_pois/v002/ into
clean-data/osm/, and the master brands CSV into engines/osm/brands.csv.

The V3 pipeline already handled:
  - Overpass fetch (~50K branded POIs in Ontario)
  - Filtering to 136 master brands (21K POIs)
  - Brand normalization (tracked_brand + category from CSV)
  - Stable ID assignment (OSM_00001..OSM_21012)

This importer validates and copies that output into Turbo's directory
structure so the parcel resolver and compiler can consume it.

Usage:
    python engines/osm/import_pois.py
    python engines/osm/import_pois.py --dry-run
    python engines/osm/import_pois.py --force       (overwrite existing files)
    python engines/osm/import_pois.py --source /path/to/v3/osm_pois/v002
"""

import json
import os
import shutil
import sys
import argparse

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

# Output directories
OSM_DIR = os.path.join(PROJECT_ROOT, 'clean-data', 'osm')
BRANDS_CSV_DEST = os.path.join(PROJECT_ROOT, 'engines', 'osm', 'brands.csv')

# Default V3 source paths
DEFAULT_V3_POI_DIR = os.path.join(
    os.path.expanduser('~'),
    'Library', 'Mobile Documents', 'com~apple~CloudDocs',
    '01_Personal', '01_Brandon', '07_Development',
    '2026-02-08 - Cleo Mini V3', 'data', 'osm_pois', 'v002',
)

DEFAULT_BRANDS_CSV = os.path.join(
    os.path.expanduser('~'),
    'Library', 'CloudStorage', 'OneDrive-CanadianCommercial',
    '00_Prospecting', 'Master Retail Sheet - All Brands.csv',
)


def validate_poi(poi):
    """Validate a POI record. Returns (ok, reason)."""
    poi_id = poi.get('id', '')
    if not poi_id or not poi_id.startswith('OSM_'):
        return False, 'missing/invalid id'

    brand = poi.get('brand', '').strip()
    if not brand:
        return False, 'missing brand'

    coords = poi.get('coords', {})
    lat = coords.get('lat')
    lng = coords.get('lng')
    if lat is None or lng is None:
        return False, 'missing coords'

    # Sanity check: Ontario lat/lng bounds
    if not (41.0 <= lat <= 57.0):
        return False, f'lat {lat} outside Ontario range'
    if not (-96.0 <= lng <= -74.0):
        return False, f'lng {lng} outside Ontario range'

    return True, None


def run(source_dir=None, brands_csv=None, dry_run=False, force=False):
    """Import V3 POI data into Turbo."""
    source_dir = source_dir or DEFAULT_V3_POI_DIR
    brands_csv = brands_csv or DEFAULT_BRANDS_CSV

    # --- Validate source paths ---
    if not os.path.isdir(source_dir):
        print(f'ERROR: Source directory not found: {source_dir}')
        sys.exit(1)

    if not os.path.isfile(brands_csv):
        print(f'WARNING: Master brands CSV not found: {brands_csv}')
        print(f'  Continuing without brands CSV')
        brands_csv = None

    # --- Scan source ---
    all_source = sorted(
        f for f in os.listdir(source_dir)
        if f.endswith('.json') and f.startswith('OSM_')
    )
    meta_file = '_meta.json' if os.path.isfile(os.path.join(source_dir, '_meta.json')) else None

    print('Cleo Engine -- Import OSM POIs')
    print(f'Source:       {source_dir}')
    print(f'Destination:  {OSM_DIR}')
    print(f'Brands CSV:   {brands_csv or "(not found)"}')
    print(f'POI files:    {len(all_source):,}')
    if meta_file:
        with open(os.path.join(source_dir, meta_file)) as f:
            meta = json.load(f)
        print(f'Source ver:   {meta.get("version", "unknown")}')
    print()

    # Check existing files
    os.makedirs(OSM_DIR, exist_ok=True)
    existing = set(os.listdir(OSM_DIR))
    if not force:
        new_files = [f for f in all_source if f not in existing]
        skip_count = len(all_source) - len(new_files)
        if skip_count > 0:
            print(f'Existing:     {skip_count:,} (skipping, use --force to overwrite)')
        files_to_copy = new_files
    else:
        files_to_copy = all_source

    print(f'To import:    {len(files_to_copy):,}')
    print()

    if not files_to_copy and not brands_csv:
        print('Nothing to do.')
        return

    if dry_run:
        # Validate a sample
        valid = 0
        invalid = 0
        reasons = {}
        sample_size = min(len(files_to_copy), 1000)
        for fname in files_to_copy[:sample_size]:
            with open(os.path.join(source_dir, fname)) as f:
                poi = json.load(f)
            ok, reason = validate_poi(poi)
            if ok:
                valid += 1
            else:
                invalid += 1
                reasons[reason] = reasons.get(reason, 0) + 1

        print(f'Validation sample ({sample_size:,} files):')
        print(f'  valid:   {valid:,}')
        print(f'  invalid: {invalid:,}')
        if reasons:
            for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
                print(f'    {reason}: {count}')
        return

    # --- Copy brands CSV ---
    if brands_csv:
        shutil.copy2(brands_csv, BRANDS_CSV_DEST)
        print(f'Copied brands CSV -> {BRANDS_CSV_DEST}')

    # --- Copy meta file ---
    if meta_file:
        shutil.copy2(
            os.path.join(source_dir, meta_file),
            os.path.join(OSM_DIR, meta_file),
        )

    # --- Copy and validate POI files ---
    stats = {'copied': 0, 'skipped_invalid': 0, 'errors': 0}
    invalid_ids = []

    for i, fname in enumerate(files_to_copy):
        src_path = os.path.join(source_dir, fname)
        dst_path = os.path.join(OSM_DIR, fname)

        try:
            with open(src_path) as f:
                poi = json.load(f)

            ok, reason = validate_poi(poi)
            if not ok:
                stats['skipped_invalid'] += 1
                invalid_ids.append((poi.get('id', fname), reason))
                continue

            with open(dst_path, 'w') as f:
                json.dump(poi, f, indent=2, ensure_ascii=False)

            stats['copied'] += 1

        except Exception as e:
            stats['errors'] += 1
            invalid_ids.append((fname, str(e)))

        if (i + 1) % 5000 == 0 or (i + 1) == len(files_to_copy):
            print(f'  [{i+1:,}/{len(files_to_copy):,}] copied: {stats["copied"]:,}')

    # --- Summary ---
    print()
    print(f'Done')
    print(f'  copied:          {stats["copied"]:,}')
    print(f'  skipped_invalid: {stats["skipped_invalid"]:,}')
    print(f'  errors:          {stats["errors"]:,}')

    if invalid_ids:
        print(f'\nInvalid records ({len(invalid_ids)}):')
        for poi_id, reason in invalid_ids[:20]:
            print(f'  {poi_id}: {reason}')
        if len(invalid_ids) > 20:
            print(f'  ... and {len(invalid_ids) - 20} more')

    # Verify final count
    final_count = len([
        f for f in os.listdir(OSM_DIR)
        if f.endswith('.json') and f.startswith('OSM_')
    ])
    print(f'\nTotal POIs in clean-data/osm/: {final_count:,}')


def main():
    parser = argparse.ArgumentParser(
        description='Import V3 OSM POI data into Turbo'
    )
    parser.add_argument('--source', type=str,
                        help=f'Source directory (default: V3 osm_pois/v002)')
    parser.add_argument('--brands-csv', type=str,
                        help=f'Master brands CSV path')
    parser.add_argument('--dry-run', action='store_true',
                        help='Validate source data without copying')
    parser.add_argument('--force', action='store_true',
                        help='Overwrite existing files in clean-data/osm/')
    args = parser.parse_args()

    run(
        source_dir=args.source,
        brands_csv=args.brands_csv,
        dry_run=args.dry_run,
        force=args.force,
    )


if __name__ == '__main__':
    main()
