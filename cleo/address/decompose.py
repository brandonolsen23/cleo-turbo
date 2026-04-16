"""
Lightweight address decomposer for GW and OSM raw strings.

This handles the common case of a simple address string like "121 CONCESSION ST E"
and breaks it into structured components that format_display() can process.

For complex patterns (units, ranges, saints, French addresses, compound roads),
the RT pipeline's full 11-step decomposer handles those during the RT normalize
stage. This module is intentionally simpler -- it covers the patterns seen in
GW (MPAC) and OSM data without duplicating RT's full complexity.
"""

import re
from .dictionaries import (
    SUFFIX_MAP, DIRECTION_MAP, COMPOUND_ROAD_PREFIXES,
    FRENCH_PREFIX_SUFFIXES, SAINT_NAMES,
)
from .normalize import to_title_case, expand_suffix, expand_direction


def decompose_simple(raw_address):
    """Decompose a raw address string into structured components.

    Designed for GW and OSM addresses which are simpler than RT addresses.
    Handles: street number, street name, suffix expansion, direction expansion,
    saint name protection, compound road guards, and French prefix suffixes.

    Args:
        raw_address: Raw address string, e.g., "121 CONCESSION ST E"
                     or "678 BROADWAY ST" or "275 Laurier Avenue East"

    Returns:
        dict with keys: street_number, street_name, street_suffix,
                        street_direction, suite_type, suite_number, special_type
    """
    result = {
        'street_number': '',
        'street_name': '',
        'street_suffix': '',
        'street_direction': '',
        'suite_type': '',
        'suite_number': '',
        'special_type': '',
    }

    if not raw_address or not raw_address.strip():
        return result

    text = raw_address.strip()

    # Protect saint names: "ST CATHARINES" -> "__SAINT__ CATHARINES"
    text = _protect_saints_simple(text)

    # Extract leading unit: "UNIT 5 100 MAIN ST" -> unit=5, rest="100 MAIN ST"
    text, suite_type, suite_number = _extract_leading_unit(text)
    result['suite_type'] = suite_type
    result['suite_number'] = suite_number

    # Also check trailing unit after comma: "100 MAIN ST, UNIT 5"
    if not suite_type:
        text, suite_type, suite_number = _extract_trailing_unit(text)
        result['suite_type'] = suite_type
        result['suite_number'] = suite_number

    words = text.split()
    if not words:
        return result

    # Extract street number (first token if it starts with a digit)
    if words and re.match(r'^\d', words[0]):
        # Handle ranges: "732-746"
        m = re.match(r'^(\d+(?:-\d+)?[A-Za-z]?)$', words[0])
        if m:
            result['street_number'] = m.group(1)
            words = words[1:]

    if not words:
        return result

    # Extract direction (last word)
    if words:
        last = words[-1].rstrip('.,')
        dir_expanded = expand_direction(last)
        if dir_expanded and len(words) > 1:
            result['street_direction'] = dir_expanded
            words = words[:-1]

    # Extract suffix (last word after direction removed)
    compound_suffixes = {'Road', 'Line', 'Sideroad', 'Concession'}

    if words:
        last = words[-1].rstrip('.,')
        suffix_expanded = expand_suffix(last)
        if suffix_expanded:
            # Compound road guard: only skip suffix extraction when the
            # preceding word is a compound prefix AND the suffix is one
            # that typically appears in compound names (Road, Line, Sideroad).
            # "Concession Street" is a real street, not a compound road.
            if (len(words) >= 2
                    and words[-2].lower() in COMPOUND_ROAD_PREFIXES
                    and suffix_expanded in compound_suffixes):
                # Don't extract as suffix, but expand the abbreviation in-place
                # so "County Rd 93" -> "County Road 93" (not extracted, just expanded)
                words[-1] = suffix_expanded
            else:
                result['street_suffix'] = suffix_expanded
                words = words[:-1]
        elif not suffix_expanded and len(words) >= 1:
            # Check for French prefix suffix at the beginning
            if words[0].lower() in FRENCH_PREFIX_SUFFIXES:
                french_suffix = expand_suffix(words[0])
                if french_suffix:
                    result['street_suffix'] = french_suffix
                    words = words[1:]

    # Compound road with trailing route number: "County Rd 93"
    # When suffix isn't at the end because a route number follows it
    if not result['street_suffix'] and len(words) >= 2:
        for i in range(len(words) - 1, 0, -1):
            candidate = expand_suffix(words[i].rstrip('.,'))
            if (candidate and candidate in compound_suffixes
                    and i >= 1 and words[i - 1].lower() in COMPOUND_ROAD_PREFIXES):
                # Expand in-place: "County Rd 93" -> "County Road 93"
                words[i] = candidate
                break

    # Remaining words = street name
    street_name = ' '.join(words).strip()

    # Restore saint names
    street_name = street_name.replace('__SAINT__', 'St.')

    # Apply title case
    street_name = to_title_case(street_name)

    result['street_name'] = street_name
    return result


def _protect_saints_simple(text):
    """Simple saint protection for GW/OSM strings."""
    words = text.split()
    protected = []
    i = 0
    while i < len(words):
        word = words[i]
        bare = word.rstrip('.').rstrip(',').lower()
        if bare == 'st' and i + 1 < len(words):
            next_bare = words[i + 1].rstrip('.,').lower()
            if next_bare in SAINT_NAMES:
                protected.append('__SAINT__')
                protected.append(words[i + 1])
                i += 2
                continue
        protected.append(word)
        i += 1
    return ' '.join(protected)


def _extract_leading_unit(text):
    """Extract leading unit pattern: 'UNIT 5 100 MAIN ST' -> ('100 MAIN ST', 'Unit', '5')."""
    for kw in ['unit', 'suite', 'ste', 'apt']:
        m = re.match(rf'^{kw}\.?\s+(\S+)\s*[,-]?\s*(.+)', text, re.IGNORECASE)
        if m:
            unit_val = m.group(1).rstrip(',')
            remainder = m.group(2).strip()
            label = kw.capitalize() if kw != 'ste' else 'Suite'
            return remainder, label, unit_val
    return text, '', ''


def _extract_trailing_unit(text):
    """Extract trailing unit: '100 MAIN ST, UNIT 5' -> ('100 MAIN ST', 'Unit', '5')."""
    for kw in ['unit', 'suite', 'ste', 'apt', 'floor', 'flr']:
        m = re.match(rf'^(.+?)\s*,\s*{kw}\.?\s+(.+?)$', text, re.IGNORECASE)
        if m:
            label = kw.capitalize() if kw != 'ste' else 'Suite'
            if kw == 'flr':
                label = 'Floor'
            return m.group(1).strip(), label, m.group(2).strip().rstrip(',')

    # Trailing hash: "100 MAIN ST, #5"
    m = re.match(r'^(.+?)\s*,\s*#\s*(\S+)\s*$', text)
    if m:
        return m.group(1).strip(), '#', m.group(2)

    return text, '', ''
