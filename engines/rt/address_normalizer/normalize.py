"""
Text normalization for addresses.

Converts abbreviations to long form, applies Title Case, normalizes
provinces, directions, and street suffixes. Does NOT decompose —
that's decompose.py's job.

Reference: schema/address_normalization_plan.md
"""

import re
from .dictionaries import (
    SUFFIX_MAP, DIRECTION_MAP, PROVINCE_MAP, COUNTRY_MAP,
    SAINT_NAMES, UPPERCASE_TOKENS,
)


def to_title_case(text):
    """Convert text to Title Case, preserving UPPERCASE_TOKENS like PO, RR."""
    words = text.split()
    result = []
    for word in words:
        upper = word.upper()
        if upper in UPPERCASE_TOKENS:
            result.append(upper)
        elif word.isupper() or word.islower():
            result.append(word.capitalize())
        else:
            # Mixed case — respect it (e.g., "McGregor")
            result.append(word)
    return ' '.join(result)


def expand_suffix(word):
    """Expand a street suffix abbreviation to long form.

    Returns the long form if it's a known suffix, otherwise returns None.
    """
    lookup = word.lower().rstrip('.')
    if lookup in SUFFIX_MAP:
        return SUFFIX_MAP[lookup]
    return None


def expand_direction(word):
    """Expand a direction abbreviation to long form.

    Returns the long form if it's a known direction, otherwise returns None.
    """
    lookup = word.lower().rstrip('.')
    if lookup in DIRECTION_MAP:
        return DIRECTION_MAP[lookup]
    return None


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


def is_saint_name(word_after_st):
    """Check if the word following 'St' is a known saint name."""
    return word_after_st.lower().rstrip('.') in SAINT_NAMES


def protect_saints(text):
    """Replace 'St.' / 'St' before saint names with a placeholder.

    Returns (modified_text, list_of_saint_positions) so we can restore later.
    """
    words = text.split()
    protected = []
    saints_found = []
    i = 0
    while i < len(words):
        word = words[i]
        bare = word.rstrip('.').rstrip(',')
        if bare.lower() == 'st' and i + 1 < len(words):
            next_word = words[i + 1].rstrip('.,')
            if is_saint_name(next_word):
                saints_found.append(i)
                protected.append('__SAINT__')
                protected.append(words[i + 1])
                i += 2
                continue
        protected.append(word)
        i += 1
    return ' '.join(protected), saints_found


def restore_saints(text):
    """Replace __SAINT__ placeholder back with 'St.'"""
    return text.replace('__SAINT__', 'St.')


def collapse_possessives(text):
    """Collapse possessives: Queen's → Queens, John's → Johns.

    Only removes 's and 's at end of words. Preserves O'Neill style apostrophes.
    """
    # Smart quotes and straight quotes
    text = re.sub(r"(\w)'s\b", r'\1s', text)
    text = re.sub(r"(\w)\u2019s\b", r'\1s', text)
    return text


def normalize_highway_hash(text):
    """Strip # from highway route numbers: Highway #7 → Highway 7."""
    return re.sub(r'(Highway|Hwy|Hwy\.?)\s*,?\s*#(\d)', r'\1 \2', text, flags=re.IGNORECASE)


def strip_preamble(text):
    """Strip descriptive preamble before actual address.

    'LOCATED AT 6301 Silver Dart Dr' → '6301 Silver Dart Dr'
    """
    match = re.search(r'LOCATED\s+AT\s+(\d)', text, re.IGNORECASE)
    if match:
        return text[match.start(1):]
    return text
