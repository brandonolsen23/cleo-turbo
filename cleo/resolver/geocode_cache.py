"""
Forward-geocode cache — read/write geocode results in clean-data/geocodes/.

One JSON file per normalized address string. Stores the FULL geocoder result
(lat/lng, score, addr_type, loc_name, comp_score, parsed fields, all_candidates)
so re-resolution reuses geocodes instead of re-calling the provincial locator.
Misses are cached too (result=None) so known-empty addresses aren't re-tried.

Mirrors cleo/resolver/cache.py (the parcel cache). Stage 1.
"""

import json
import os
import re
import hashlib

CACHE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..', 'clean-data', 'geocodes')
)


def canonical_key(address: str) -> str:
    """Normalize a geocode query string to a stable, comparable cache key."""
    if not address:
        return ''
    s = str(address).strip().lower()
    s = re.sub(r'[.,]', ' ', s)        # drop commas / periods
    s = re.sub(r'\s+', ' ', s).strip()  # collapse whitespace
    return s


def _path(address: str) -> str:
    h = hashlib.sha1(canonical_key(address).encode('utf-8')).hexdigest()
    return os.path.join(CACHE_DIR, f'{h}.json')


def cache_has(address: str) -> bool:
    """True if this address (hit or cached-miss) is already in the cache."""
    return os.path.isfile(_path(address))


def cache_read_safe(address: str):
    """Return the cached geocode result dict, or None if absent/corrupt.

    NOTE: a cached MISS is stored as {'result': None}; callers should use
    cache_has() to distinguish 'never geocoded' from 'geocoded, no match'.
    """
    path = _path(address)
    if not os.path.isfile(path):
        return None
    try:
        with open(path) as f:
            return json.load(f).get('result')
    except (json.JSONDecodeError, OSError, AttributeError):
        return None


def cache_write(address: str, result) -> None:
    """Write a geocode result atomically. `result` may be None (cache a miss)."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = _path(address)
    tmp = path + '.tmp'
    payload = {'query': address, 'key': canonical_key(address), 'result': result}
    with open(tmp, 'w') as f:
        json.dump(payload, f, separators=(',', ':'))
    os.replace(tmp, path)
