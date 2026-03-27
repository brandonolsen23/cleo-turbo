"""
Header classifier — parses date, price, city/region, note,
and classifies address lines with geocodability flags.

Reference: schema/engine_reference.md — HEADER SECTION
"""

import re
from classifier.dictionaries import (
    MONTH_MAP, LEGAL_DESC_START_REGEX, UNIT_SUITE_START_REGEX,
    HIGHWAY_START_REGEX, STREET_SUFFIX_REGEX,
)


def classify_header(header, site_data=None):
    """Classify header fields from structural extraction.

    Args:
        header: dict with address_lines, city_region, date_text, price_text, note
        site_data: optional dict with site_lines for PIN/ARN context

    Returns:
        dict with classified header fields
    """
    result = {
        'sale_date': _parse_date(header.get('date_text', '')),
        'sale_price': _parse_price(header.get('price_text', '')),
        'city': '',
        'region': '',
        'transaction_note': header.get('note', ''),
        'address_entries': _classify_address_lines(header.get('address_lines', [])),
    }

    # Split city : region
    city_region = header.get('city_region', '')
    if ' : ' in city_region:
        parts = city_region.split(' : ', 1)
        result['city'] = parts[0].strip()
        result['region'] = parts[1].strip()
    else:
        result['city'] = city_region.strip()

    return result


def _parse_date(date_text):
    """Parse 'DD Mon YYYY' → 'YYYY-MM-DD' ISO format."""
    if not date_text:
        return ''
    match = re.match(r'(\d{1,2})\s+(\w{3})\s+(\d{4})', date_text)
    if not match:
        return date_text  # Return as-is if can't parse
    day = match.group(1).zfill(2)
    month = MONTH_MAP.get(match.group(2), '00')
    year = match.group(3)
    return f'{year}-{month}-{day}'


def _parse_price(price_text):
    """Parse '$2,550,000' → 2550000 integer."""
    if not price_text:
        return None
    digits = re.sub(r'[^\d]', '', price_text)
    if digits:
        return int(digits)
    return None


def _classify_address_lines(address_lines):
    """Classify each address line and group into address entries.

    Geocodability rule: starts with a digit = geocodable. Otherwise not.

    Grouping:
    - New numbered/range address starts a new entry
    - UNIT/SUITE attaches to the entry above
    - Consecutive legal descriptions belong together
    - Everything else is its own entry
    """
    if not address_lines:
        return []

    entries = []
    current_entry = None

    for line in address_lines:
        line = line.strip()
        if not line:
            continue

        line_type = _get_address_line_type(line)
        geocodable = line_type in ('numbered_address', 'range_address')

        if line_type in ('numbered_address', 'range_address'):
            # New geocodable address starts a new entry
            current_entry = {
                'lines': [line],
                'type': 'street_address',
                'geocodable': True,
            }
            entries.append(current_entry)

        elif line_type == 'unit_suite':
            # Attach to the entry above
            if current_entry:
                current_entry['lines'].append(line)
            else:
                # No address above — standalone unit
                entries.append({
                    'lines': [line],
                    'type': 'unit_only',
                    'geocodable': False,
                })

        elif line_type == 'legal_description':
            # Consecutive legal lines belong together
            if current_entry and current_entry['type'] == 'legal_description':
                current_entry['lines'].append(line)
            else:
                current_entry = {
                    'lines': [line],
                    'type': 'legal_description',
                    'geocodable': False,
                }
                entries.append(current_entry)

        else:
            # Street name only, highway, location, name only — own entry
            current_entry = {
                'lines': [line],
                'type': line_type,
                'geocodable': False,
            }
            entries.append(current_entry)

    return entries


def _get_address_line_type(line):
    """Determine the type of a header address line."""
    # Range address: 69 - 71 SELBY RD, 10 & 20 WOODSLEE AVE
    if re.match(r'^\d+\s*[-&]\s*\d+\s+', line):
        return 'range_address'

    # Numbered address: starts with digit
    if re.match(r'^\d+\s+', line):
        return 'numbered_address'

    # Unit/Suite
    if UNIT_SUITE_START_REGEX.match(line):
        return 'unit_suite'

    # Legal description
    if LEGAL_DESC_START_REGEX.match(line):
        return 'legal_description'

    # Highway/County Road
    if HIGHWAY_START_REGEX.match(line):
        return 'highway'

    # Location qualifier in parentheses
    if line.startswith('('):
        return 'location_qualifier'

    # Street name with suffix but no number
    if STREET_SUFFIX_REGEX.search(line):
        return 'street_name'

    # Everything else — subdivision name, area name, etc.
    return 'name_only'
