"""
PIN and ARN normalization for Ontario provincial API queries.

PIN: Strip dash → 9-digit string (or longer if input is 10+ digits).
ARN: Validate format → strip spaces → right-pad zeros → 20-digit string.

Validation rejects non-ARN identifiers (registry numbers, decimals, garbage)
so they fall through to geocoding instead of producing wrong parcel linkages.
"""

import re


# Letter prefixes that indicate land registry numbers, not ARNs
_REGISTRY_PREFIXES = re.compile(r'^[A-Z]{2,3}[\s-]', re.IGNORECASE)


def normalize_pin(raw):
    """Normalize a PIN to API format.

    Input:  '14024-0032', '08074-0030', '140240032'
    Output: {'original': '14024-0032', 'display': '14024-0032', 'api_format': '140240032', 'multiple': False}
    """
    if not raw or not raw.strip():
        return {'original': '', 'display': '', 'api_format': '', 'multiple': False}

    original = raw.strip()

    # Check for multiple PINs (comma-separated, semicolon-separated, or "and")
    separators = re.split(r'[;,]|\band\b', original, flags=re.IGNORECASE)
    if len(separators) > 1:
        pins = [_format_single_pin(p.strip()) for p in separators if p.strip()]
        return {
            'original': original,
            'display': original,
            'api_format': [p for p in pins if p],
            'multiple': True,
        }

    api_format = _format_single_pin(original)
    return {
        'original': original,
        'display': original,
        'api_format': api_format,
        'multiple': False,
    }


def _format_single_pin(text):
    """Strip dashes and non-digit chars, return digit string.

    Standard PINs are 9 digits. Some are 10. Don't truncate.
    """
    digits = re.sub(r'\D', '', text)
    if not digits:
        return ''
    # Pad to 9 if shorter, but never truncate longer PINs
    if len(digits) < 9:
        return digits.ljust(9, '0')
    return digits


def _validate_arn_input(raw):
    """Check if a raw string looks like a valid Ontario ARN.

    Returns True if it should be normalized, False if it should be rejected.
    Rejects: registry numbers (HR-120738), decimal numbers (61.14769),
    strings with fewer than 13 digits, and other garbage.
    """
    # Reject letter-prefixed registry numbers (HR-, AT-, MT-, WR-, KL-)
    if _REGISTRY_PREFIXES.match(raw):
        return False

    # Reject if it contains a decimal point (not an ARN)
    if '.' in raw:
        return False

    # Extract digits
    digits = re.sub(r'\D', '', raw)

    # Reject if fewer than 13 digits (real ARNs are 15 digits, some have 14)
    if len(digits) < 13:
        return False

    # Reject if more than 20 digits (garbage)
    if len(digits) > 20:
        return False

    return True


def normalize_arn(raw):
    """Normalize an ARN to 20-digit zero-padded format for API queries.

    Validates the input first — rejects registry numbers, decimals, and
    short digit strings. Invalid inputs return empty api_format so the
    record falls through to geocoding.

    Input:  '21 10 100 025 27110'
    Output: {'original': '21 10 100 025 27110', 'display': '21 10 100 025 27110', 'api_format': '21101000252711000000'}
    """
    if not raw or not raw.strip():
        return {'original': '', 'display': '', 'api_format': ''}

    original = raw.strip()

    # Validate before normalizing
    if not _validate_arn_input(original):
        return {'original': original, 'display': original, 'api_format': ''}

    digits = re.sub(r'\D', '', original)

    if not digits:
        return {'original': original, 'display': original, 'api_format': ''}

    # Right-pad with zeros to exactly 20 digits
    api_format = digits.ljust(20, '0')[:20]

    return {
        'original': original,
        'display': original,
        'api_format': api_format,
    }
