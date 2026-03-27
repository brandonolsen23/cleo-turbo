"""
Reader — loads Clean Records from clean-data/rt/.
"""

import json
import os


CLEAN_DATA_RT = os.path.join(os.path.dirname(__file__), '..', '..', 'clean-data', 'rt')
CLEAN_DATA_RT = os.path.abspath(CLEAN_DATA_RT)

CLEAN_DATA_PARCELS = os.path.join(os.path.dirname(__file__), '..', '..', 'clean-data', 'parcels')
CLEAN_DATA_PARCELS = os.path.abspath(CLEAN_DATA_PARCELS)


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


def read_parcel(arn):
    """Read a parcel polygon from the parcel cache. Returns dict or None."""
    path = os.path.join(CLEAN_DATA_PARCELS, f'{arn}.json')
    if not os.path.isfile(path):
        return None
    with open(path) as f:
        return json.load(f)
