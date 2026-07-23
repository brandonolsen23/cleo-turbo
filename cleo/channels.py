"""
Contact-channel normalization (phones + emails).

Shared by the seeding migration (042) and the channels API so that dedupe on
`(contact_id, value)` is computed identically in both places — if these two ever
drift, re-imports would create duplicate rows instead of being idempotent.

`value` is the normalized dedupe key; the caller keeps the original string in
`value_raw` for display. Both functions return None when there is nothing usable
to store, so callers can skip empty source fields.
"""

import re


def normalize_phone(raw):
    """Digits-only key, with the North-American '1' country code dropped so that
    '(416) 555-1234', '4165551234', and '14165551234' all dedupe together.
    Returns None when the input has no digits."""
    if not raw:
        return None
    digits = re.sub(r"\D", "", str(raw))
    if not digits:
        return None
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits


def normalize_email(raw):
    """Lowercased, trimmed. Returns None when empty or missing an '@'."""
    if not raw:
        return None
    value = str(raw).strip().lower()
    if not value or "@" not in value:
        return None
    return value
