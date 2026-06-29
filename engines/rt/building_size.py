"""
Parser for the Realtrack ``bldg`` field.

RT publishes building size as a free-text string with mixed units across
property types: ``"12,500 sf"`` (square feet), ``"22 units"`` (multifamily),
``"200 rooms"`` (hotels), ``"137 beds"`` (care), and others. About 24% of
RT records have a non-empty value.

This module normalises that string into a (value, unit) pair while preserving
the original. The original string is always kept by the caller — this parser
returns ``(None, None)`` for garbage (PIN-leakage, addresses) so the caller
can flag the record without dropping the raw value.
"""

import re

KNOWN_UNITS = {
    "sf",
    "units",
    "rooms",
    "beds",
    "bdrms",
    "suites",
    "ac",
    "lots",
    "seats",
    "townhomes",
    "parcels",
    "sm",
}

UNIT_ALIASES = {
    "romms": "rooms",
    "bdrm": "bdrms",
    "bedrooms": "bdrms",
    "unis": "units",
    "uints": "units",
    "unjts": "units",
    "unitys": "units",
    "unit": "units",
    "apts": "units",
    "s": "sf",
    "sf sf": "sf",
    "sf i": "sf",
    "ft": "sf",
}

PIN_PATTERN = re.compile(r"^\d{5}-\d{4}\+?$")
NUMBER_UNIT_PATTERN = re.compile(r"^([\d,.\s]+?)\s*([a-zA-Z][a-zA-Z\s&#;0-9]*)?$")


def _strip_html_entities(s: str) -> str:
    return s.replace("&#160;", " ").replace("&nbsp;", " ")


def _collapse_number_whitespace(num_str: str) -> str:
    """``"61, 508"`` → ``"61508"``, ``"160 337"`` → ``"160337"``."""
    return re.sub(r"[\s,]+", "", num_str)


def _looks_like_address(s: str) -> bool:
    """Detect free-text address leakage (3+ alphabetic words)."""
    words = re.findall(r"[A-Za-z]{2,}", s)
    return len(words) >= 3


def parse_building_size(raw):
    """Parse an RT ``bldg`` field into a normalised value/unit pair.

    Returns ``(value, unit)`` where ``value`` is a float (or ``None``) and
    ``unit`` is one of ``KNOWN_UNITS`` (or ``None`` when no confident unit
    can be assigned, including garbage rows).
    """
    if raw is None:
        return None, None
    s = _strip_html_entities(str(raw)).strip()
    if not s:
        return None, None

    if PIN_PATTERN.match(s):
        return None, None
    if _looks_like_address(s):
        return None, None

    m = NUMBER_UNIT_PATTERN.match(s)
    if not m:
        return None, None

    num_str = _collapse_number_whitespace(m.group(1) or "")
    unit_str = (m.group(2) or "").strip().lower()
    unit_str = _strip_html_entities(unit_str).strip()
    unit_str = re.sub(r"\s+", " ", unit_str)

    try:
        value = float(num_str) if num_str else None
    except ValueError:
        value = None

    if value is None:
        return None, None

    if not unit_str:
        return value, None
    if unit_str in KNOWN_UNITS:
        return value, unit_str
    if unit_str in UNIT_ALIASES:
        return value, UNIT_ALIASES[unit_str]
    return value, None
