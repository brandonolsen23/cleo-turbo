"""
Reader — loads Clean Records from clean-data/rt/.
"""

import json
import os


CLEAN_DATA_RT = os.path.join(os.path.dirname(__file__), '..', '..', 'clean-data', 'rt')
CLEAN_DATA_RT = os.path.abspath(CLEAN_DATA_RT)

CLEAN_DATA_PARCELS = os.path.join(os.path.dirname(__file__), '..', '..', 'clean-data', 'parcels')
CLEAN_DATA_PARCELS = os.path.abspath(CLEAN_DATA_PARCELS)

CLEAN_DATA_OSM = os.path.join(os.path.dirname(__file__), '..', '..', 'clean-data', 'osm')
CLEAN_DATA_OSM = os.path.abspath(CLEAN_DATA_OSM)

CLEAN_DATA_GW = os.path.join(os.path.dirname(__file__), '..', '..', 'clean-data', 'gw')
CLEAN_DATA_GW = os.path.abspath(CLEAN_DATA_GW)


def iter_clean_records(data_dir=None):
    """Yield (source_id, record_dict) for each Clean Record."""
    data_dir = data_dir or CLEAN_DATA_RT
    files = sorted(f for f in os.listdir(data_dir) if f.endswith('.json'))
    for fname in files:
        with open(os.path.join(data_dir, fname)) as f:
            record = json.load(f)
        yield record.get('source_id', fname.replace('.json', '')), record


def count_clean_records(data_dir=None):
    """Count Clean Records without loading them."""
    data_dir = data_dir or CLEAN_DATA_RT
    return len([f for f in os.listdir(data_dir) if f.endswith('.json')])


def iter_osm_records(data_dir=None):
    """Yield (poi_id, record_dict) for each OSM POI file."""
    data_dir = data_dir or CLEAN_DATA_OSM
    if not os.path.isdir(data_dir):
        return
    files = sorted(
        f for f in os.listdir(data_dir)
        if f.endswith('.json') and not f.startswith('_')
    )
    for fname in files:
        with open(os.path.join(data_dir, fname)) as f:
            record = json.load(f)
        yield record.get('id', fname.replace('.json', '')), record


def count_osm_records(data_dir=None):
    """Count OSM POI records without loading them."""
    data_dir = data_dir or CLEAN_DATA_OSM
    if not os.path.isdir(data_dir):
        return 0
    return len([
        f for f in os.listdir(data_dir)
        if f.endswith('.json') and not f.startswith('_')
    ])


def iter_gw_records(data_dir=None):
    """Yield (gw_id, record_dict) for each GW clean record."""
    data_dir = data_dir or CLEAN_DATA_GW
    if not os.path.isdir(data_dir):
        return
    files = sorted(
        f for f in os.listdir(data_dir)
        if f.endswith('.json') and not f.startswith('_')
    )
    for fname in files:
        with open(os.path.join(data_dir, fname)) as f:
            record = json.load(f)
        yield record.get('source_id', fname.replace('.json', '')), record


def count_gw_records(data_dir=None):
    """Count GW clean records without loading them."""
    data_dir = data_dir or CLEAN_DATA_GW
    if not os.path.isdir(data_dir):
        return 0
    return len([
        f for f in os.listdir(data_dir)
        if f.endswith('.json') and not f.startswith('_')
    ])


def read_parcel(arn):
    """Read a parcel polygon from the parcel cache. Returns dict or None."""
    path = os.path.join(CLEAN_DATA_PARCELS, f'{arn}.json')
    if not os.path.isfile(path):
        return None
    with open(path) as f:
        return json.load(f)
