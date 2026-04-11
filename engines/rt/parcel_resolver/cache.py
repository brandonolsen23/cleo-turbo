"""
Parcel cache interface — REDIRECTS to the canonical location.

The canonical cache implementation lives at cleo/resolver/cache.py.
This file re-exports everything so existing imports continue to work.
"""

import sys
import os

# Ensure project root is on path so cleo.resolver is importable
PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..', '..')
)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from cleo.resolver.cache import (  # noqa: F401
    CACHE_DIR,
    cache_has,
    cache_read,
    cache_read_safe,
    cache_write,
)
