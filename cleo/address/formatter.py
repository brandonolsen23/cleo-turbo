"""
Shared display address formatter.

Takes structured address components and produces a canonical display string.
This is the SINGLE source of truth for how addresses look in the UI.

All pipelines (RT, GW, OSM) and the compiler call format_display() to ensure
consistent address formatting regardless of data source.
"""

from .normalize import normalize_street_name


def format_display(components):
    """Build a canonical display string from structured address components.

    Args:
        components: dict with keys:
            street_number, street_name, street_suffix, street_direction,
            suite_type, suite_number, special_type (optional)

    Returns:
        Canonical display string, e.g., "732-746 Tenth Street East, Suite 200"
    """
    if not components:
        return ''

    # Handle special types
    special = components.get('special_type', '')
    if special == 'po_box':
        return f"PO Box {components.get('suite_number', '')}"
    if special == 'rural_route':
        return f"RR {components.get('suite_number', '')}"
    if special == 'general_delivery':
        return 'General Delivery'
    if special == 'legal_description':
        return components.get('street_name', '')

    # Normalize ordinal street names
    street_name = components.get('street_name', '')
    if street_name:
        street_name = normalize_street_name(street_name)

    # Build the main address parts
    parts = []
    street_number = components.get('street_number', '')
    if street_number:
        parts.append(street_number)
    if street_name:
        parts.append(street_name)

    street_suffix = components.get('street_suffix', '')
    if street_suffix:
        parts.append(street_suffix)

    street_direction = components.get('street_direction', '')
    if street_direction:
        parts.append(street_direction)

    display = ' '.join(parts)

    # Append suite/unit
    suite_type = components.get('suite_type', '')
    suite_number = components.get('suite_number', '')
    if suite_type and suite_number:
        if suite_type == '#':
            display += f", #{suite_number}"
        else:
            display += f", {suite_type} {suite_number}"

    return display
