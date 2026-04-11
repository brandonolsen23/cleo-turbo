"""
Parcel cache — read/write/check parcel files in clean-data/parcels/.

Each parcel is one JSON file keyed by 20-digit ARN.
The cache grows permanently and is shared across all data sources.

This is the canonical location — engines/rt/parcel_resolver/cache.py
should import from here.
"""

import json
import os

# clean-data/parcels/ relative to project root
CACHE_DIR = os.path.join(
    os.path.dirname(__file__), '..', '..', 'clean-data', 'parcels'
)
CACHE_DIR = os.path.abspath(CACHE_DIR)


def cache_has(arn: str) -> bool:
    """Check if a parcel exists in the cache for this ARN."""
    return os.path.isfile(os.path.join(CACHE_DIR, f'{arn}.json'))


def cache_read(arn: str) -> dict | None:
    """Read a parcel from the cache. Returns dict or None if not found."""
    path = os.path.join(CACHE_DIR, f'{arn}.json')
    if not os.path.isfile(path):
        return None
    with open(path) as f:
        return json.load(f)


def cache_read_safe(arn: str) -> dict | None:
    """Read a parcel from cache with error handling for corrupted files."""
    path = os.path.join(CACHE_DIR, f'{arn}.json')
    if not os.path.isfile(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def cache_write(arn: str, parcel: dict) -> None:
    """Write a parcel to the cache atomically. Overwrites if exists."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f'{arn}.json')
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(parcel, f, separators=(',', ':'))
    os.replace(tmp, path)
