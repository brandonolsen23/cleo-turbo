"""
Range expansion, search key generation, and geocode string assembly.

Reference: schema/address_normalization_plan.md
"""

import re
from .dictionaries import (
    CANADIAN_PROVINCES_LONG, US_STATES_LONG,
    ORDINAL_WORD_TO_DIGIT, ORDINAL_DIGIT_TO_WORD,
)
from .normalize import expand_province, expand_country, normalize_postal


def generate_search_keys(components):
    """Generate search keys from decomposed address components.

    Returns a list of search keys (lowercase). The first key includes the
    suffix, the second (partial) omits it for fuzzy matching.
    """
    if components.get('special_type'):
        # PO Box, RR, General Delivery
        display = components.get('display', '')
        if display:
            return [display.lower()]
        return []

    parts = []
    if components['street_number']:
        parts.append(components['street_number'])
    if components['street_name']:
        parts.append(components['street_name'])

    # Full key: number + name + suffix + direction
    full_parts = list(parts)
    if components['street_suffix']:
        full_parts.append(components['street_suffix'])
    if components['street_direction']:
        full_parts.append(components['street_direction'])
    full_key = ' '.join(full_parts).lower()

    # Partial key: number + name (no suffix, no direction)
    partial_key = ' '.join(parts).lower()

    keys = []
    if full_key:
        keys.append(full_key)
    if partial_key and partial_key != full_key:
        keys.append(partial_key)

    # Generate alternate ordinal keys: "third line" ↔ "3rd line"
    alt_keys = _ordinal_alternates(keys)
    for ak in alt_keys:
        if ak not in keys:
            keys.append(ak)

    return keys


def _ordinal_alternates(keys):
    """For each key, swap ordinal words↔digits to produce an alternate.

    "5523 third line" → "5523 3rd line"
    "5523 3rd line"   → "5523 third line"
    """
    alternates = []
    for key in keys:
        words = key.split()
        swapped = False
        new_words = []
        for w in words:
            if w in ORDINAL_WORD_TO_DIGIT:
                new_words.append(ORDINAL_WORD_TO_DIGIT[w])
                swapped = True
            elif w in ORDINAL_DIGIT_TO_WORD:
                new_words.append(ORDINAL_DIGIT_TO_WORD[w])
                swapped = True
            else:
                new_words.append(w)
        if swapped:
            alternates.append(' '.join(new_words))
    return alternates


def expand_range(components):
    """Expand a multi-number address into individual search variations.

    Handles three patterns:
      Dash range:   "69-71"      → [69-71, 69, 71]
      Comma list:   "4,14,34,44" → [4, 14, 34, 44]
      Slash list:   "245/251"    → [245, 251]

    Each individual number gets its own searchable/geocodable variation.
    Returns empty list if the street_number is a single number.
    """
    number = components.get('street_number', '')
    if not number:
        return []

    # Build the street portion (without number)
    street_parts = []
    if components['street_name']:
        street_parts.append(components['street_name'])
    if components['street_suffix']:
        street_parts.append(components['street_suffix'])
    if components['street_direction']:
        street_parts.append(components['street_direction'])
    street = ' '.join(street_parts)

    individual_numbers = []

    # Dash range: "69-71"
    m = re.match(r'^(\d+)-(\d+)$', number)
    if m:
        individual_numbers = [m.group(1), m.group(2)]

    # Comma list: "4,14,34,44"
    elif ',' in number:
        individual_numbers = [n.strip() for n in number.split(',') if n.strip()]

    # Slash list: "245/251"
    elif '/' in number and re.match(r'^\d+(/\d+)+$', number):
        individual_numbers = [n.strip() for n in number.split('/') if n.strip()]

    if not individual_numbers:
        return []

    variations = []

    # First: the canonical combined form
    canonical_display = f'{number} {street}'
    variations.append({
        'display': canonical_display,
        'search_key': canonical_display.lower(),
    })

    # Then: each individual number as its own address
    for num in individual_numbers:
        num_display = f'{num} {street}'
        variations.append({
            'display': num_display,
            'search_key': num_display.lower(),
        })

    return variations


def build_street_only(components):
    """Build the street-level address from components, WITHOUT suite/unit.

    "66 Wellington Street West" — no "Suite 4200".
    This is what geocoders need.
    """
    parts = []
    if components.get('street_number'):
        parts.append(components['street_number'])
    if components.get('street_name'):
        parts.append(components['street_name'])
    if components.get('street_suffix'):
        parts.append(components['street_suffix'])
    if components.get('street_direction'):
        parts.append(components['street_direction'])
    return ' '.join(parts)


def build_geocode_string(display, city='', province='', postal='', country=''):
    """Assemble a geocode-ready string from address parts.

    Format: "{display}, {city}, {province} {postal}, {country}"
    The display passed in should be street-level only (no suite).
    """
    if not display:
        return None

    # Normalize province
    if province:
        province = expand_province(province)

    # Normalize postal code
    if postal:
        postal = normalize_postal(postal)

    # Determine country from province if not explicitly set
    if not country:
        if province in CANADIAN_PROVINCES_LONG:
            country = 'Canada'
        elif province in US_STATES_LONG:
            country = 'United States'
    elif country:
        country = expand_country(country)

    parts = [display]
    if city:
        parts.append(city)

    # Province and postal together
    prov_postal = ''
    if province and postal:
        prov_postal = f'{province} {postal}'
    elif province:
        prov_postal = province
    elif postal:
        prov_postal = postal
    if prov_postal:
        parts.append(prov_postal)

    if country:
        parts.append(country)

    return ', '.join(parts)


def classify_address_type(components):
    """Determine what type of address this is.

    Returns: 'street_address', 'po_box', 'rural_route', 'general_delivery',
             'legal_description', or 'unknown'.
    """
    special = components.get('special_type', '')
    if special:
        return special

    if components.get('street_number') and components.get('street_name'):
        return 'street_address'

    if components.get('street_name') and not components.get('street_number'):
        return 'street_name_only'

    return 'unknown'


def is_geocodable(components):
    """Check if this address can be geocoded."""
    addr_type = classify_address_type(components)
    return addr_type in ('street_address',)
