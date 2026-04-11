"""
OSM POI Processor -- transforms raw Overpass data into enriched POI records.

Reads raw-data/osm/branded_pois.json + building_lookups.json, processes ALL
branded POIs (not just curated ones), enriches with building geometry + approx
SF, and writes individual records to clean-data/osm/.

Brands from brands.csv are marked is_curated=true and get their category
assigned. All other brands pass through with category=null.

Usage:
    python engines/osm/process.py
    python engines/osm/process.py --dry-run
"""

import csv
import json
import math
import os
import re
import sys
import argparse

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

RAW_DIR = os.path.join(PROJECT_ROOT, 'raw-data', 'osm')
OSM_DIR = os.path.join(PROJECT_ROOT, 'clean-data', 'osm')
BRANDS_CSV = os.path.join(PROJECT_ROOT, 'engines', 'osm', 'brands.csv')
ALIASES_JSON = os.path.join(PROJECT_ROOT, 'engines', 'osm', 'brand_aliases.json')


# ================================================================
# Brand normalization
# ================================================================

def _normalize(name):
    return re.sub(r'[^A-Z0-9]', '', name.upper())


def load_aliases():
    """Load brand alias mappings from JSON file.

    Returns dict: raw_name -> canonical_name (exact string, not normalized).
    """
    if not os.path.isfile(ALIASES_JSON):
        return {}
    with open(ALIASES_JSON, encoding='utf-8') as f:
        return json.load(f)


def load_master_brands():
    """Load master brands CSV.

    Returns dict: normalized_name -> {csv_name, category}.
    Also loads aliases so they point to the same curated brand info.
    """
    if not os.path.isfile(BRANDS_CSV):
        print(f'ERROR: brands.csv not found: {BRANDS_CSV}')
        sys.exit(1)

    aliases = load_aliases()

    lookup = {}
    with open(BRANDS_CSV, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            csv_name = row.get('Brand Name', '').strip()
            category = row.get('Category', '').strip()
            if not csv_name:
                continue
            info = {'csv_name': csv_name, 'category': category}
            lookup[_normalize(csv_name)] = info

    # Build reverse alias lookup: for each alias that maps to a curated brand,
    # register the alias's normalized form pointing to the curated brand info
    for raw_name, canonical_name in aliases.items():
        norm_canonical = _normalize(canonical_name)
        if norm_canonical in lookup:
            lookup[_normalize(raw_name)] = lookup[norm_canonical]

    return lookup, aliases


# ================================================================
# Geometry / SF calculation
# ================================================================

def compute_centroid(polygon):
    """Compute centroid of a polygon [[lng, lat], ...]."""
    if not polygon:
        return None, None
    lngs = [p[0] for p in polygon]
    lats = [p[1] for p in polygon]
    return sum(lats) / len(lats), sum(lngs) / len(lngs)


def compute_sqft(polygon):
    """Compute approximate square footage from a lat/lng polygon using Shoelace.

    Projects lat/lng to meters using local latitude correction, then
    applies the Shoelace formula. Result is footprint area (single story).
    """
    if not polygon or len(polygon) < 3:
        return None

    # Get center latitude for projection
    lats = [p[1] for p in polygon]
    center_lat = sum(lats) / len(lats)

    # Project to meters
    cos_lat = math.cos(math.radians(center_lat))
    M_PER_DEG_LAT = 111_320
    M_PER_DEG_LNG = 111_320 * cos_lat

    projected = []
    for lng, lat in polygon:
        x = lng * M_PER_DEG_LNG
        y = lat * M_PER_DEG_LAT
        projected.append((x, y))

    # Shoelace formula
    n = len(projected)
    area = 0
    for i in range(n):
        j = (i + 1) % n
        area += projected[i][0] * projected[j][1]
        area -= projected[j][0] * projected[i][1]
    area_sqm = abs(area) / 2

    area_sqft = int(area_sqm * 10.764)
    return area_sqft if area_sqft > 0 else None


# ================================================================
# Element parsing
# ================================================================

def parse_element(el, building_lookups):
    """Parse an Overpass element into a POI record."""
    tags = el.get('tags', {})
    brand = tags.get('brand', '')
    name = tags.get('name', brand)
    if not brand:
        return None

    osm_type = el['type']
    osm_id = f"{osm_type}/{el['id']}"

    # Coordinates
    if osm_type == 'node':
        lat = el.get('lat')
        lng = el.get('lon')
    else:
        # Way — compute centroid from geometry
        geom = el.get('geometry', [])
        if geom:
            lats = [p['lat'] for p in geom]
            lngs = [p['lon'] for p in geom]
            lat = sum(lats) / len(lats)
            lng = sum(lngs) / len(lngs)
        else:
            lat = lng = None

    if lat is None or lng is None:
        return None

    # Building polygon
    polygon = None
    building_tags = {}

    if osm_type == 'way' and el.get('geometry'):
        polygon = [[p['lon'], p['lat']] for p in el['geometry']]
    elif osm_type == 'node' and osm_id in building_lookups:
        bldg = building_lookups[osm_id]
        polygon = bldg.get('polygon')
        building_tags = bldg.get('tags', {})

    approx_sqft = compute_sqft(polygon) if polygon else None

    # Address — POI tags first, then building tags as fallback
    housenumber = tags.get('addr:housenumber', '') or building_tags.get('addr:housenumber', '')
    street = tags.get('addr:street', '') or building_tags.get('addr:street', '')
    city = tags.get('addr:city', '') or building_tags.get('addr:city', '')
    postal = tags.get('addr:postcode', '') or building_tags.get('addr:postcode', '')

    # Capture extra OSM tags for category inference (stored as sample_osm_tags)
    osm_tags = {}
    for tag_key in ('shop', 'amenity', 'leisure', 'tourism', 'healthcare', 'office'):
        if tags.get(tag_key):
            osm_tags[tag_key] = tags[tag_key]

    return {
        'source': 'osm',
        'osm_type': osm_type,
        'osm_id': osm_id,
        'name': name,
        'brand': brand,
        'cuisine': tags.get('cuisine', ''),
        'operator': tags.get('operator', ''),
        'drive_through': tags.get('drive_through', '') or tags.get('drive_in', ''),
        'facebook': tags.get('contact:facebook', ''),
        'instagram': tags.get('contact:instagram', ''),
        'phone': tags.get('phone', '') or tags.get('contact:phone', ''),
        'website': tags.get('website', '') or tags.get('contact:website', ''),
        'coords': {'lat': lat, 'lng': lng},
        'address': {
            'housenumber': housenumber,
            'street': street,
            'city': city,
            'postal_code': postal,
        },
        'building': {
            'polygon': polygon,
            'approx_sqft': approx_sqft,
        } if polygon else None,
        'osm_tags': osm_tags if osm_tags else None,
    }


def _apply_alias(brand_raw, aliases):
    """Apply alias mapping to get canonical brand name.

    Tries exact match first, then case-insensitive.
    Returns the canonical name or the original if no alias found.
    """
    # Exact match
    if brand_raw in aliases:
        return aliases[brand_raw]

    # Case-insensitive match
    brand_lower = brand_raw.lower()
    for raw, canonical in aliases.items():
        if raw.lower() == brand_lower:
            return canonical

    return brand_raw


# ================================================================
# Pipeline
# ================================================================

def run(dry_run=False):
    pois_path = os.path.join(RAW_DIR, 'branded_pois.json')
    buildings_path = os.path.join(RAW_DIR, 'building_lookups.json')

    if not os.path.isfile(pois_path):
        print(f'ERROR: {pois_path} not found. Run fetch.py first.')
        sys.exit(1)

    print('Cleo Engine -- Process OSM POIs (all brands)')

    # Load raw data
    print('Loading raw data...')
    with open(pois_path) as f:
        raw = json.load(f)
    elements = raw.get('elements', [])
    print(f'  Raw elements: {len(elements):,}')

    building_lookups = {}
    if os.path.isfile(buildings_path):
        with open(buildings_path) as f:
            building_lookups = json.load(f)
        print(f'  Building lookups: {len(building_lookups):,}')

    # Load master brands + aliases
    master, aliases = load_master_brands()
    print(f'  Master brands (curated): {len(set(v["csv_name"] for v in master.values())):,}')
    print(f'  Aliases loaded: {len(aliases):,}')

    # Parse ALL branded POIs
    parsed = []
    brand_counts = {}
    curated_counts = {}
    uncurated_counts = {}
    seen_ids = set()

    for el in elements:
        record = parse_element(el, building_lookups)
        if not record:
            continue

        # Dedup by OSM ID
        if record['osm_id'] in seen_ids:
            continue
        seen_ids.add(record['osm_id'])

        # Apply alias mapping to get canonical name
        canonical = _apply_alias(record['brand'], aliases)

        # Check if this brand is curated (in CSV)
        norm = _normalize(canonical)
        info = master.get(norm)

        if info:
            # Curated brand — use CSV name and category
            record['tracked_brand'] = info['csv_name']
            record['category'] = info['category']
            record['is_curated'] = True
            curated_counts[info['csv_name']] = curated_counts.get(info['csv_name'], 0) + 1
        else:
            # Non-curated brand — pass through with null category
            record['tracked_brand'] = canonical
            record['category'] = None
            record['is_curated'] = False
            uncurated_counts[canonical] = uncurated_counts.get(canonical, 0) + 1

        brand_counts[record['tracked_brand']] = brand_counts.get(record['tracked_brand'], 0) + 1
        parsed.append(record)

    # Sort by OSM ID for stable ordering
    parsed.sort(key=lambda r: r['osm_id'])

    # Stats
    with_polygon = sum(1 for r in parsed if r.get('building'))
    with_sqft = sum(1 for r in parsed if r.get('building') and r['building'].get('approx_sqft'))
    with_address = sum(1 for r in parsed if r['address'].get('street'))
    curated_total = sum(1 for r in parsed if r.get('is_curated'))
    uncurated_total = sum(1 for r in parsed if not r.get('is_curated'))

    print(f'\nProcessed {len(parsed):,} POIs across {len(brand_counts):,} brands')
    print(f'  Curated brands: {len(curated_counts):,} brands, {curated_total:,} POIs')
    print(f'  Uncurated brands: {len(uncurated_counts):,} brands, {uncurated_total:,} POIs')
    print(f'  With building polygon: {with_polygon:,}')
    print(f'  With approx SF:        {with_sqft:,}')
    print(f'  With address:          {with_address:,}')

    if dry_run:
        print('\nTop 20 curated brands:')
        for brand, count in sorted(curated_counts.items(), key=lambda x: -x[1])[:20]:
            print(f'  {brand}: {count:,}')
        print('\nTop 20 uncurated brands:')
        for brand, count in sorted(uncurated_counts.items(), key=lambda x: -x[1])[:20]:
            print(f'  {brand}: {count:,}')
        # Check for curated brands with zero matches
        all_csv_names = set(v['csv_name'] for v in master.values())
        zero_match = all_csv_names - set(curated_counts.keys())
        if zero_match:
            print(f'\nWARNING: {len(zero_match)} curated brands with ZERO matches:')
            for name in sorted(zero_match):
                print(f'  {name}')
        return

    # Clear existing and write new records
    os.makedirs(OSM_DIR, exist_ok=True)

    # Remove old OSM_ files
    for f in os.listdir(OSM_DIR):
        if f.startswith('OSM_') and f.endswith('.json'):
            os.remove(os.path.join(OSM_DIR, f))

    # Assign IDs and write
    for i, record in enumerate(parsed, start=1):
        record['id'] = f'OSM_{i:05d}'
        out_path = os.path.join(OSM_DIR, f'{record["id"]}.json')
        with open(out_path, 'w') as f:
            json.dump(record, f, indent=2, ensure_ascii=False)

    # Write meta
    meta = {
        'total': len(parsed),
        'brands_total': len(brand_counts),
        'brands_curated': len(curated_counts),
        'brands_uncurated': len(uncurated_counts),
        'with_polygon': with_polygon,
        'with_address': with_address,
    }
    with open(os.path.join(OSM_DIR, '_meta.json'), 'w') as f:
        json.dump(meta, f, indent=2)

    print(f'\nWrote {len(parsed):,} records to {OSM_DIR}')


def main():
    parser = argparse.ArgumentParser(description='Process raw OSM POI data into clean records')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    run(dry_run=args.dry_run)


if __name__ == '__main__':
    main()
