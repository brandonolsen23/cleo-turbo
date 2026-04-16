"""
Shared address normalization functions.

Title case, suffix expansion, direction expansion, ordinal normalization,
and saint name handling. Used by all pipelines (RT, GW, OSM) and the compiler.
"""

import re
from .dictionaries import (
    SUFFIX_MAP, DIRECTION_MAP, UPPERCASE_TOKENS, SAINT_NAMES,
    ORDINAL_WORD_TO_DIGIT, ORDINAL_DIGIT_TO_WORD,
    ORDINAL_WORD_RANGE, ORDINAL_WORD_FORMS,
)


def to_title_case(text):
    """Convert text to Title Case, preserving UPPERCASE_TOKENS like PO, RR.

    Respects mixed case (e.g., "McGregor" stays as-is).
    """
    words = text.split()
    result = []
    for word in words:
        upper = word.upper()
        if upper in UPPERCASE_TOKENS:
            result.append(upper)
        elif word.isupper() or word.islower():
            result.append(word.capitalize())
        else:
            # Mixed case -- respect it (e.g., "McGregor")
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


def normalize_street_name(name):
    """Normalize an ordinal street name to canonical numeric form.

    Policy: ALL ordinals use numeric form with lowercase suffix.

    Examples:
        "10th"      -> "10th"
        "10Th"      -> "10th"
        "TENTH"     -> "10th"
        "tenth"     -> "10th"
        "First"     -> "1st"
        "Eleventh"  -> "11th"
        "TWELFTH"   -> "12th"
        "14Th"      -> "14th"
        "King"      -> "King"  (not an ordinal, unchanged)
    """
    if not name:
        return name

    lower = name.lower().strip()

    # Check if it's a word ordinal (like "tenth", "first", "eleventh")
    if lower in ORDINAL_WORD_TO_DIGIT:
        return ORDINAL_WORD_TO_DIGIT[lower]

    # Check if it's a digit ordinal (like "10th", "10Th", "14TH")
    m = re.match(r'^(\d+)(st|nd|rd|th)$', lower)
    if m:
        num = int(m.group(1))
        return _make_ordinal(num)

    # Not an ordinal -- return as-is
    return name


def _make_ordinal(n):
    """Convert integer to ordinal string: 1->'1st', 2->'2nd', 11->'11th', etc."""
    if 11 <= (n % 100) <= 13:
        return f'{n}th'
    suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
    return f'{n}{suffix}'
