"""
Text normalization for addresses.

Shared functions (to_title_case, expand_suffix, expand_direction, saint name
handling) are re-exported from cleo.address.normalize. RT-specific functions
(province/country expansion, postal normalization, etc.) remain here.

Reference: schema/address_normalization_plan.md
"""

import re

# Re-export shared normalization functions
from cleo.address.normalize import (  # noqa: F401
    to_title_case,
    expand_suffix,
    expand_direction,
    is_saint_name,
    protect_saints,
    restore_saints,
    normalize_street_name,
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


def collapse_possessives(text):
    """Collapse possessives: Queen's -> Queens, John's -> Johns.

    Only removes 's and 's at end of words. Preserves O'Neill style apostrophes.
    """
    # Smart quotes and straight quotes
    text = re.sub(r"(\w)'s\b", r'\1s', text)
    text = re.sub(r"(\w)\u2019s\b", r'\1s', text)
    return text


def normalize_highway_hash(text):
    """Strip # from highway route numbers: Highway #7 -> Highway 7."""
    return re.sub(r'(Highway|Hwy|Hwy\.?)\s*,?\s*#(\d)', r'\1 \2', text, flags=re.IGNORECASE)


def strip_preamble(text):
    """Strip descriptive preamble before actual address.

    'LOCATED AT 6301 Silver Dart Dr' -> '6301 Silver Dart Dr'
    """
    match = re.search(r'LOCATED\s+AT\s+(\d)', text, re.IGNORECASE)
    if match:
        return text[match.start(1):]
    return text
