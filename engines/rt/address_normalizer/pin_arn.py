"""
PIN and ARN normalization for Ontario provincial API queries.

PIN: Strip dash → 9-digit string.
ARN: Strip spaces → right-pad zeros → 20-digit string.

Reference: schema/address_normalization_plan.md
"""

import re


def normalize_pin(raw):
    """Normalize a PIN to 9-digit format for API queries.

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
    """Strip dashes and non-digit chars, return 9-digit string."""
    digits = re.sub(r'\D', '', text)
    if not digits:
        return ''
    # Pad or truncate to 9 digits
    return digits.ljust(9, '0')[:9]


def normalize_arn(raw):
    """Normalize an ARN to 20-digit zero-padded format for API queries.

    Input:  '21 10 100 025 27110'
    Output: {'original': '21 10 100 025 27110', 'display': '21 10 100 025 27110', 'api_format': '21101000252711000000'}
    """
    if not raw or not raw.strip():
        return {'original': '', 'display': '', 'api_format': ''}

    original = raw.strip()
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
