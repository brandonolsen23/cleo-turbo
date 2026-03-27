"""
Site classifier — extracts PIN, acreage, legal description, location.

Reference: schema/engine_reference.md — SITE SECTION
"""

import re


def classify_site(site_lines):
    """Classify site lines into structured fields.

    Args:
        site_lines: list of strings from structural extraction

    Returns:
        dict with pin, pin_multiple, acreage, legal_description, location,
        surface_rights_only
    """
    result = {
        'pin': '',
        'pin_multiple': False,
        'acreage': None,
        'legal_description': '',
        'location': '',
        'surface_rights_only': False,
    }

    if not site_lines:
        return result

    legal_parts = []
    location_parts = []

    for line in site_lines:
        line = line.strip()
        if not line:
            continue

        # PIN
        if line.startswith('PIN:'):
            pin_value = line[4:].strip()
            if pin_value.endswith('+'):
                result['pin_multiple'] = True
                pin_value = pin_value.rstrip('+').strip()
            result['pin'] = pin_value
            continue

        # Acreage
        acreage_match = re.search(r'(\d+\.?\d*)\s+acre', line, re.IGNORECASE)
        if acreage_match:
            try:
                result['acreage'] = float(acreage_match.group(1))
            except ValueError:
                pass
            continue

        # Surface rights
        if re.match(r'^Surface rights', line, re.IGNORECASE):
            result['surface_rights_only'] = True
            continue

        # Location description — contains directional/relative terms
        if re.search(r'\b(side|corner|of)\b', line, re.IGNORECASE) and \
           not re.match(r'^(Plan|Conc|Con |Lot |Part |As in|Except|Being)', line, re.IGNORECASE):
            location_parts.append(line)
            continue

        # Everything else is legal description
        legal_parts.append(line)

    result['legal_description'] = '\n'.join(legal_parts)
    result['location'] = '\n'.join(location_parts)

    return result
