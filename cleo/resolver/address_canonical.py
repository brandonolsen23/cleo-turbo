"""Address canonicalization helper.

Folds Ontario city amalgamations, suite-type synonyms, and suite-number
formatting noise into a single deterministic key. Strict on empty
components: we never invent data.

Reference data is JSON in cleo/resolver/resources/. Loaded once at module
import into in-memory dicts. To extend the rules, edit the JSON.

Public API:
    canonicalize_address(city, street_number, street_name, street_suffix,
                         street_direction, suite_type, suite_number) -> str

Returns a pipe-joined 7-segment string. Always non-empty (an all-empty
input produces "|||||suite|" (6 pipes, 7 segments) — the suite_type empty-mapping is
intentional per spec §suite_type_synonyms.json).
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Optional

_RESOURCE_DIR = Path(__file__).parent / "resources"


def _load_city_lookup() -> dict[str, str]:
    """Flatten city_amalgamation.json into a legacy → canonical dict."""
    path = _RESOURCE_DIR / "city_amalgamation.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    lookup: dict[str, str] = {}
    for group in data["amalgamations"]:
        canonical = group["canonical"].lower()
        # Canonical maps to itself (idempotent for already-canonical inputs).
        lookup[canonical] = canonical
        for absorbed in group["absorbed"]:
            lookup[absorbed.lower()] = canonical
    return lookup


def _load_suite_type_lookup() -> dict[str, str]:
    """Flatten suite_type_synonyms.json into a synonym → canonical dict."""
    path = _RESOURCE_DIR / "suite_type_synonyms.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    lookup: dict[str, str] = {}
    for group in data["groups"]:
        canonical = group["canonical"].lower()
        for synonym in group["synonyms"]:
            lookup[synonym.lower()] = canonical
    return lookup


def _load_config() -> dict:
    path = _RESOURCE_DIR / "address_normalization_config.json"
    return json.loads(path.read_text(encoding="utf-8"))


_CITY = _load_city_lookup()
_SUITE_TYPE = _load_suite_type_lookup()
_CONFIG = _load_config()

_LETTER_SUFFIX_RE = re.compile(r"^(\d+)([A-Za-z]+)$")


def _norm_text(value: Optional[str]) -> str:
    """Lowercase + strip; treat None / whitespace-only as empty."""
    if value is None:
        return ""
    s = str(value).strip().lower()
    return s


def _canon_city(value: Optional[str]) -> str:
    s = _norm_text(value)
    if not s:
        return ""
    return _CITY.get(s, s)


def _canon_suite_type(value: Optional[str]) -> str:
    """Map synonym → canonical. Unknown values pass through lowercased."""
    s = _norm_text(value)
    # The lookup contains the empty string ("" → "suite") per the spec.
    if s in _SUITE_TYPE:
        return _SUITE_TYPE[s]
    return s


def _canon_suite_number(value: Optional[str]) -> str:
    s = _norm_text(value)
    if not s:
        return ""
    cfg = _CONFIG.get("suite_number", {})

    # Strip leading zeros from any leading digit run.
    if cfg.get("strip_leading_zeros", True):
        m = _LETTER_SUFFIX_RE.match(s)
        if m:
            digits = m.group(1).lstrip("0") or "0"
            s = digits + m.group(2)
        else:
            stripped = s.lstrip("0")
            # If the value was all zeros, lstrip kills it — preserve a single 0.
            if stripped == "" and s != "":
                stripped = "0"
            # Only replace if the input was purely numeric (don't lstrip "00ph").
            if s.isdigit():
                s = stripped

    # Uppercase any letter suffix.
    if cfg.get("uppercase_letter_suffix", True):
        s = s.upper()

    return s


def canonicalize_address(
    city: Optional[str],
    street_number: Optional[str],
    street_name: Optional[str],
    street_suffix: Optional[str],
    street_direction: Optional[str],
    suite_type: Optional[str],
    suite_number: Optional[str],
) -> str:
    """Return the pipe-joined party_address_canonical key.

    Empty / None / whitespace-only components stay empty in the output
    (with one exception: empty suite_type maps to "suite" via the
    synonyms table — see spec).
    """
    return "|".join([
        _canon_city(city),
        _norm_text(street_number),
        _norm_text(street_name),
        _norm_text(street_suffix),
        _norm_text(street_direction),
        _canon_suite_type(suite_type),
        _canon_suite_number(suite_number),
    ])
