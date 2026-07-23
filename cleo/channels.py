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


def _clean_label(raw_type):
    """Datanyze `type` — drop the useless 'unknown' placeholder, keep real labels."""
    if not raw_type or str(raw_type).strip().lower() in ("unknown", ""):
        return None
    return str(raw_type).strip()


def upsert_datanyze_channels(conn, contact_id, datanyze):
    """Insert a contact's Datanyze phones/emails as channel rows (source=datanyze,
    status=unverified), deduped on the normalized value via INSERT OR IGNORE.

    Additive and idempotent — NEVER deletes or overwrites. A Datanyze number that
    equals an already-stored value (RT or otherwise) is silently skipped, so this
    deduplicates rather than duplicating. `datanyze` is the parsed datanyze_raw
    dict ({"phones": [{value, type}], "emails": [{value, type}]}).

    Returns (phones_inserted, emails_inserted)."""
    if not datanyze:
        return (0, 0)
    phones = emails = 0
    for p in (datanyze.get("phones") or []):
        value = normalize_phone(p.get("value"))
        if not value:
            continue
        cur = conn.execute(
            "INSERT OR IGNORE INTO contact_phones "
            "(contact_id, value, value_raw, label, source, status) "
            "VALUES (?, ?, ?, ?, 'datanyze', 'unverified')",
            (contact_id, value, p.get("value"), _clean_label(p.get("type"))),
        )
        phones += cur.rowcount
    for e in (datanyze.get("emails") or []):
        value = normalize_email(e.get("value"))
        if not value:
            continue
        cur = conn.execute(
            "INSERT OR IGNORE INTO contact_emails "
            "(contact_id, value, value_raw, label, source, status) "
            "VALUES (?, ?, ?, ?, 'datanyze', 'unverified')",
            (contact_id, value, e.get("value"), _clean_label(e.get("type"))),
        )
        emails += cur.rowcount
    return (phones, emails)
