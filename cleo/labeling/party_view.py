"""Party view aggregator — builds the full side-of-transaction block
used by the labeling UI's left/right panes.
"""

from __future__ import annotations
import json
from typing import Optional


def _parse_json_array(raw: Optional[str]) -> list:
    if not raw:
        return []
    try:
        val = json.loads(raw)
        return [str(x) for x in val] if isinstance(val, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def get_party_view(db, source_id: str, side: str) -> Optional[dict]:
    """Return aggregated party view for (source_id, side).

    Returns None if the transaction doesn't exist.
    """
    assert side in ("buyer", "seller")

    tx = db.execute(
        "SELECT * FROM transactions WHERE source_id = ?",
        (source_id,)
    ).fetchone()
    if not tx:
        return None

    sale_date = tx["sale_date"] if "sale_date" in tx.keys() else None

    prefix = f"{side}_"
    trade_name = tx[f"{prefix}trade_name"]
    care_of = tx[f"{prefix}care_of"]
    law_firms = _parse_json_array(tx[f"{prefix}law_firms_json"])
    companies_other = _parse_json_array(tx[f"{prefix}companies_json"])

    party_rows = [dict(r) for r in db.execute(
        "SELECT id, source_id, side, party_name, phone, contact_id "
        "FROM transaction_parties WHERE source_id = ? AND side = ? "
        "ORDER BY id",
        (source_id, side)
    )]

    # Contacts: look up each contact_id referenced by party rows
    contact_ids = [r["contact_id"] for r in party_rows if r["contact_id"]]
    contacts = []
    if contact_ids:
        placeholders = ",".join("?" for _ in contact_ids)
        contacts = [dict(r) for r in db.execute(
            f"SELECT id, display_name, phone, job_title FROM contacts WHERE id IN ({placeholders})",
            contact_ids
        )]
    contacts_out = [
        {"id": c["id"], "name": c["display_name"], "role": c.get("job_title"),
         "phone": c.get("phone"), "job_title": c.get("job_title")}
        for c in contacts
    ]

    mailing_row = db.execute(
        "SELECT display, city, province, postal "
        "FROM transaction_mailing_addresses "
        "WHERE source_id = ? AND side = ? LIMIT 1",
        (source_id, side)
    ).fetchone()
    mailing = dict(mailing_row) if mailing_row else None

    # Union of phones across party rows + contacts (deduped, preserving order)
    phones: list = []
    seen = set()
    for p in party_rows:
        ph = (p.get("phone") or "").strip()
        if ph and ph not in seen:
            phones.append(ph)
            seen.add(ph)
    for c in contacts_out:
        ph = (c.get("phone") or "").strip()
        if ph and ph not in seen:
            phones.append(ph)
            seen.add(ph)

    return {
        "source_id": source_id,
        "side": side,
        "sale_date": sale_date,
        "party_rows": party_rows,
        "trade_name": trade_name,
        "care_of": care_of,
        "companies_other": companies_other,
        "law_firms": law_firms,
        "contacts": contacts_out,
        "mailing": mailing,
        "phones": phones,
    }
