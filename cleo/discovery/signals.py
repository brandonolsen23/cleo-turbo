"""
Signal Extraction — Step 0 of the Group Discovery Algorithm.

Extracts raw signals from the main database that link groups together:
  - address:   shared mailing address used by a group in a transaction
  - contact:   a named individual who appeared alongside a group
  - phone:     phone number from contacts table, attributed to current group
  - trade_name: seller_trade_name / buyer_trade_name from transactions
  - care_of:   seller_care_of / buyer_care_of from transactions
  - entity:    two or more groups appearing on the same side of a transaction

Usage:
    from cleo.discovery.signals import extract_signals
    signals = extract_signals(db)   # db is a sqlite3 connection
"""

import re
from itertools import combinations

from .types import Signal
from cleo.compiler.reconciler import normalize_group_name


def _normalize_address(street_number, street_name, street_suffix, city, postal):
    """Produce a canonical address key: 'STREET_NUM STREET_NAME [SUFFIX]|CITY|POSTAL'.

    All components are upper-cased; postal codes have whitespace stripped.
    Returns an empty string if critical components are missing.
    """
    num = (street_number or "").strip().upper()
    name = (street_name or "").strip().upper()
    suffix = (street_suffix or "").strip().upper()
    city_clean = (city or "").strip().upper()
    postal_clean = re.sub(r"\s+", "", (postal or "").strip().upper())

    if not num or not name or not city_clean:
        return ""

    street_part = f"{num} {name}"
    if suffix:
        street_part = f"{street_part} {suffix}"

    return f"{street_part}|{city_clean}|{postal_clean}"


def _normalize_phone(raw):
    """Normalize a phone number to 10 digits.

    Strips all non-digit characters. If the result is 11 digits and starts
    with '1', strips the leading '1'.  Returns '' if not a valid 10-digit
    result.
    """
    if not raw:
        return ""
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) == 10:
        return digits
    return ""


def _load_exclusions(db):
    """Return a set of (exclusion_type, exclusion_value) tuples from discovery_exclusions."""
    try:
        rows = db.execute(
            "SELECT exclusion_type, exclusion_value FROM discovery_exclusions"
        ).fetchall()
        return {(r[0], r[1]) for r in rows}
    except Exception:
        return set()


def extract_signals(db) -> list:
    """Extract all raw signals from the database.

    Parameters
    ----------
    db : sqlite3.Connection
        Open connection to the Cleo SQLite database.

    Returns
    -------
    list[Signal]
        One Signal per (type, value, group) observation.  Signals whose
        (type, value) appears in discovery_exclusions are omitted.
    """
    exclusions = _load_exclusions(db)
    signals = []

    def _excluded(sig_type, sig_value):
        return (sig_type, sig_value) in exclusions

    # ── 1. Address signals ────────────────────────────────────────────────────
    # Join transaction_mailing_addresses with transaction_parties to find
    # which group(s) were on each side and what mailing address they used.
    addr_rows = db.execute("""
        SELECT
            tma.source_id,
            tma.side,
            tma.street_number,
            tma.street_name,
            tma.street_suffix,
            tma.city,
            tma.postal,
            tma.display,
            tp.group_id
        FROM transaction_mailing_addresses tma
        JOIN transaction_parties tp
            ON tp.source_id = tma.source_id
            AND tp.side     = tma.side
            AND tp.group_id IS NOT NULL
    """).fetchall()

    for row in addr_rows:
        source_id, side, street_num, street_name, street_suffix, city, postal, display, group_id = row
        norm = _normalize_address(street_num, street_name, street_suffix, city, postal)
        if not norm:
            continue
        if _excluded("address", norm):
            continue
        signals.append(Signal(
            signal_type="address",
            signal_value=norm,
            group_id=group_id,
            source_id=source_id,
            side=side,
            raw_value=display or "",
        ))

    # ── 2. Contact signals ────────────────────────────────────────────────────
    # For each transaction_parties row that has a contact_id, find which
    # group(s) are on the same side of the same transaction.
    contact_rows = db.execute("""
        SELECT
            tp_contact.source_id,
            tp_contact.side,
            c.name_fingerprint,
            tp_group.group_id,
            tp_contact.party_name
        FROM transaction_parties tp_contact
        JOIN contacts c ON c.id = tp_contact.contact_id
        JOIN transaction_parties tp_group
            ON tp_group.source_id = tp_contact.source_id
            AND tp_group.side     = tp_contact.side
            AND tp_group.group_id IS NOT NULL
        WHERE tp_contact.contact_id IS NOT NULL
          AND c.name_fingerprint   IS NOT NULL
    """).fetchall()

    for row in contact_rows:
        source_id, side, fingerprint, group_id, party_name = row
        if _excluded("contact", fingerprint):
            continue
        signals.append(Signal(
            signal_type="contact",
            signal_value=fingerprint,
            group_id=group_id,
            source_id=source_id,
            side=side,
            raw_value=party_name or "",
        ))

    # ── 3. Phone signals ──────────────────────────────────────────────────────
    # From the contacts table directly; attributed to current_group_id.
    phone_rows = db.execute("""
        SELECT id, phone, current_group_id, display_name
        FROM contacts
        WHERE phone IS NOT NULL AND current_group_id IS NOT NULL
    """).fetchall()

    for row in phone_rows:
        contact_id, raw_phone, group_id, display_name = row
        norm_phone = _normalize_phone(raw_phone)
        if not norm_phone:
            continue
        if _excluded("phone", norm_phone):
            continue
        signals.append(Signal(
            signal_type="phone",
            signal_value=norm_phone,
            group_id=group_id,
            source_id="",   # not transaction-derived
            side="",
            raw_value=raw_phone,
        ))

    # ── 4. Trade name signals ─────────────────────────────────────────────────
    # seller_trade_name / buyer_trade_name; attributed to the first group on
    # that side of the transaction.
    trade_rows = db.execute("""
        SELECT t.source_id, t.seller_trade_name, t.buyer_trade_name
        FROM transactions t
        WHERE t.seller_trade_name IS NOT NULL OR t.buyer_trade_name IS NOT NULL
    """).fetchall()

    for row in trade_rows:
        source_id, seller_trade, buyer_trade = row
        for side, raw_val in [("seller", seller_trade), ("buyer", buyer_trade)]:
            if not raw_val:
                continue
            norm = normalize_group_name(raw_val)
            if not norm:
                continue
            if _excluded("trade_name", norm):
                continue
            # Find the first group on this side
            grp = db.execute("""
                SELECT group_id FROM transaction_parties
                WHERE source_id = ? AND side = ? AND group_id IS NOT NULL
                ORDER BY id LIMIT 1
            """, (source_id, side)).fetchone()
            if not grp:
                continue
            signals.append(Signal(
                signal_type="trade_name",
                signal_value=norm,
                group_id=grp[0],
                source_id=source_id,
                side=side,
                raw_value=raw_val,
            ))

    # ── 5. Care-of signals ────────────────────────────────────────────────────
    # seller_care_of / buyer_care_of; attributed to the first group on that side.
    care_rows = db.execute("""
        SELECT t.source_id, t.seller_care_of, t.buyer_care_of
        FROM transactions t
        WHERE t.seller_care_of IS NOT NULL OR t.buyer_care_of IS NOT NULL
    """).fetchall()

    for row in care_rows:
        source_id, seller_care, buyer_care = row
        for side, raw_val in [("seller", seller_care), ("buyer", buyer_care)]:
            if not raw_val:
                continue
            norm = normalize_group_name(raw_val)
            if not norm:
                continue
            if _excluded("care_of", norm):
                continue
            grp = db.execute("""
                SELECT group_id FROM transaction_parties
                WHERE source_id = ? AND side = ? AND group_id IS NOT NULL
                ORDER BY id LIMIT 1
            """, (source_id, side)).fetchone()
            if not grp:
                continue
            signals.append(Signal(
                signal_type="care_of",
                signal_value=norm,
                group_id=grp[0],
                source_id=source_id,
                side=side,
                raw_value=raw_val,
            ))

    # ── 6. Entity co-occurrence signals ───────────────────────────────────────
    # When 2+ groups appear on the same side of a transaction, create pairwise
    # signals: for each pair (A, B), emit one signal for A (value=B) and one
    # for B (value=A).
    cooc_rows = db.execute("""
        SELECT source_id, side, group_id
        FROM transaction_parties
        WHERE group_id IS NOT NULL
        ORDER BY source_id, side, id
    """).fetchall()

    # Group by (source_id, side)
    from collections import defaultdict
    side_groups: dict = defaultdict(list)
    for row in cooc_rows:
        source_id, side, group_id = row
        side_groups[(source_id, side)].append(group_id)

    for (source_id, side), group_ids in side_groups.items():
        if len(group_ids) < 2:
            continue
        for gid_a, gid_b in combinations(group_ids, 2):
            # Signal for gid_a: co-occurred with gid_b
            if not _excluded("entity", gid_b):
                signals.append(Signal(
                    signal_type="entity",
                    signal_value=gid_b,
                    group_id=gid_a,
                    source_id=source_id,
                    side=side,
                    raw_value="",
                ))
            # Signal for gid_b: co-occurred with gid_a
            if not _excluded("entity", gid_a):
                signals.append(Signal(
                    signal_type="entity",
                    signal_value=gid_a,
                    group_id=gid_b,
                    source_id=source_id,
                    side=side,
                    raw_value="",
                ))

    return signals
