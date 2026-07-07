"""
Text normalization for addresses.

Shared functions (to_title_case, expand_suffix, expand_direction, saint name
handling) are re-exported from cleo.address.normalize. RT-specific functions
(province/country expansion, postal normalization, etc.) remain here.

Reference: schema/address_normalization_plan.md
"""

import re

# Re-export shared normalization functions
# (collapse_possessives, normalize_highway_hash, strip_preamble moved to
# cleo.address.normalize with the decomposer promotion, 2026-07-07)
from cleo.address.normalize import (  # noqa: F401
    to_title_case,
    expand_suffix,
    expand_direction,
    is_saint_name,
    protect_saints,
    restore_saints,
    normalize_street_name,
    collapse_possessives,
    normalize_highway_hash,
    strip_preamble,
)

from .dictionaries import (
    PROVINCE_MAP, COUNTRY_MAP, SAINT_NAMES, UPPERCASE_TOKENS,
)


def expand_province(text):
    """Expand a province/state abbreviation or typo to long form.

    Accepts full text (may be multi-word like "British Columbia").
    Returns long form if recognized, otherwise returns the input Title-Cased.
    """
    lookup = text.strip().lower()
    if lookup in PROVINCE_MAP:
        return PROVINCE_MAP[lookup]
    return to_title_case(text.strip())


def expand_country(text):
    """Expand a country abbreviation to long form."""
    lookup = text.strip().lower()
    if lookup in COUNTRY_MAP:
        return COUNTRY_MAP[lookup]
    return to_title_case(text.strip())


def normalize_postal(postal):
    """Normalize Canadian postal code format: A1A 1A1 (uppercase, with space)."""
    if not postal:
        return ''
    clean = postal.strip().upper().replace(' ', '')
    if len(clean) == 6 and re.match(r'^[A-Z]\d[A-Z]\d[A-Z]\d$', clean):
        return clean[:3] + ' ' + clean[3:]
    # Return as-is for US ZIPs and other formats
    return postal.strip().upper()
