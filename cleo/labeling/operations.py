"""Write operations + search for the labeling tool.

Called by the FastAPI routes — keep these functions free of FastAPI
imports so they can be tested standalone with an in-memory DB.
"""

from __future__ import annotations
from typing import List, Optional

from .party_view import get_party_view
from .seed_harvester import harvest_seeds


class VerdictValidationError(ValueError):
    pass


# ── Formatters ──────────────────────────────────────────────────

def format_session_id(n: int) -> str:
    return f"LBL_{n:05d}"


def parse_session_id(raw) -> int:
    """Accept either the integer form or 'LBL_NNNNN'."""
    if isinstance(raw, int):
        return raw
    s = str(raw).strip()
    if s.upper().startswith("LBL_"):
        s = s[4:]
    return int(s)


# ── Session lifecycle ──────────────────────────────────────────

def create_session(
    db, anchor_source_id: str, anchor_side: str,
    name: str, audit_slug: Optional[str], created_by: str,
) -> int:
    """Create a new session and auto-harvest anchor fields into seeds.

    Returns the new session id (integer).
    """
    assert anchor_side in ("buyer", "seller")
    view = get_party_view(db, anchor_source_id, anchor_side)
    if not view:
        raise ValueError(
            f"Anchor party not found: source_id={anchor_source_id}, side={anchor_side}"
        )

    cur = db.execute(
        "INSERT INTO labeling_sessions "
        "(name, audit_slug, anchor_source_id, anchor_side, status, created_by) "
        "VALUES (?, ?, ?, ?, 'active', ?)",
        (name, audit_slug, anchor_source_id, anchor_side, created_by),
    )
    session_id = cur.lastrowid

    _insert_seeds(db, session_id, harvest_seeds(view),
                  anchor_source_id, anchor_side)
    db.commit()
    return session_id


def mark_session_status(db, session_id: int, status: str):
    assert status in ("active", "paused", "done")
    completed_at_clause = ", completed_at = datetime('now')" if status == "done" else ""
    db.execute(
        f"UPDATE labeling_sessions SET status = ?, updated_at = datetime('now'){completed_at_clause} "
        "WHERE id = ?",
        (status, session_id),
    )
    db.commit()


# ── Verdicts ────────────────────────────────────────────────────

def record_verdict(
    db, *, session_id: int, source_id: str, side: str, verdict: str,
    left_source_id: str, left_side: str,
    seed_id: Optional[int], rationale: Optional[str],
    links: List[dict], created_by: str,
) -> int:
    """Record a verdict. Validates shape, inserts links, auto-harvests seeds on confirm.

    Returns the new verdict id.
    """
    if verdict not in ("confirmed", "rejected"):
        raise VerdictValidationError(f"Invalid verdict: {verdict}")
    if verdict == "confirmed" and not links:
        raise VerdictValidationError("Confirmed verdict requires at least one link")
    if verdict == "rejected" and links:
        raise VerdictValidationError("Rejected verdict must have no links")
    if verdict == "rejected" and not (rationale and rationale.strip()):
        raise VerdictValidationError("Rejected verdict requires a rationale")

    cur = db.execute(
        "INSERT INTO labeling_verdicts "
        "(session_id, source_id, side, verdict, left_source_id, left_side, "
        "seed_id, rationale, created_by) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (session_id, source_id, side, verdict, left_source_id, left_side,
         seed_id, rationale, created_by),
    )
    verdict_id = cur.lastrowid

    for link in links:
        db.execute(
            "INSERT INTO labeling_links "
            "(verdict_id, from_field_type, from_field_value, "
            "to_field_type, to_field_value, kind) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (verdict_id, link["from_field_type"], link["from_field_value"],
             link["to_field_type"], link["to_field_value"], link["kind"]),
        )

    # Auto-harvest seeds on confirm; reviewed_index always updated
    mark_reviewed(db, session_id, source_id, side, commit=False)
    if verdict == "confirmed":
        view = get_party_view(db, source_id, side)
        if view:
            _insert_seeds(db, session_id, harvest_seeds(view), source_id, side)

    db.commit()
    return verdict_id


def delete_verdict(db, verdict_id: int):
    db.execute("DELETE FROM labeling_verdicts WHERE id = ?", (verdict_id,))
    # labeling_links cascade via FK
    # Seeds are intentionally NOT rolled back (see spec)
    db.commit()


# ── Seeds ──────────────────────────────────────────────────────

def _insert_seeds(db, session_id: int, seeds: List[dict],
                  contributor_source_id: str, contributor_side: str):
    """Insert seeds (deduped via UNIQUE constraint — OR IGNORE)."""
    for s in seeds:
        db.execute(
            "INSERT OR IGNORE INTO labeling_seeds "
            "(session_id, term, field_type, state, "
            "first_contributed_by_source_id, first_contributed_by_side) "
            "VALUES (?, ?, ?, 'pending', ?, ?)",
            (session_id, s["term"], s["field_type"],
             contributor_source_id, contributor_side),
        )


def set_seed_state(db, seed_id: int, state: str):
    assert state in ("pending", "in_progress", "done", "skipped")
    completed_clause = ", completed_at = datetime('now')" if state in ("done", "skipped") else ""
    db.execute(
        f"UPDATE labeling_seeds SET state = ?{completed_clause} WHERE id = ?",
        (state, seed_id),
    )
    db.commit()


# ── Reviewed index ─────────────────────────────────────────────

def mark_reviewed(db, session_id: int, source_id: str, side: str, commit: bool = True):
    db.execute(
        "INSERT OR IGNORE INTO labeling_reviewed_index "
        "(session_id, source_id, side) VALUES (?, ?, ?)",
        (session_id, source_id, side),
    )
    if commit:
        db.commit()


# ── Search ─────────────────────────────────────────────────────

def search_candidates(
    db, session_id: int, *, term: str, field_type: Optional[str] = None, limit: int = 200,
) -> List[dict]:
    """Search RT parties for `term` across labelable fields, excluding reviewed.

    Returns list of {source_id, side, match_fields} dicts.
    `field_type` is an optional hint — currently unused for ranking but accepted
    for API symmetry and future use.
    """
    like = f"%{term}%"
    rows = db.execute(
        """
        WITH hits AS (
            SELECT source_id, 'buyer' AS side, 'trade_name' AS mf FROM transactions WHERE buyer_trade_name LIKE ?
            UNION
            SELECT source_id, 'buyer', 'care_of' FROM transactions WHERE buyer_care_of LIKE ?
            UNION
            SELECT source_id, 'buyer', 'company_other' FROM transactions WHERE buyer_companies_json LIKE ?
            UNION
            SELECT source_id, 'buyer', 'law_firm' FROM transactions WHERE buyer_law_firms_json LIKE ?
            UNION
            SELECT source_id, 'seller', 'trade_name' FROM transactions WHERE seller_trade_name LIKE ?
            UNION
            SELECT source_id, 'seller', 'care_of' FROM transactions WHERE seller_care_of LIKE ?
            UNION
            SELECT source_id, 'seller', 'company_other' FROM transactions WHERE seller_companies_json LIKE ?
            UNION
            SELECT source_id, 'seller', 'law_firm' FROM transactions WHERE seller_law_firms_json LIKE ?
            UNION
            SELECT source_id, side, 'party_name' FROM transaction_parties WHERE party_name LIKE ?
            UNION
            SELECT source_id, side, 'phone' FROM transaction_parties WHERE phone LIKE ?
            UNION
            SELECT source_id, side, 'address' FROM transaction_mailing_addresses WHERE display LIKE ?
            UNION
            SELECT tp.source_id, tp.side, 'contact_name'
              FROM transaction_parties tp JOIN contacts c ON c.id = tp.contact_id
              WHERE c.display_name LIKE ?
        )
        SELECT h.source_id, h.side,
               GROUP_CONCAT(DISTINCT h.mf) AS match_fields
        FROM hits h
        LEFT JOIN labeling_reviewed_index r
            ON r.session_id = ? AND r.source_id = h.source_id AND r.side = h.side
        WHERE r.source_id IS NULL
        GROUP BY h.source_id, h.side
        LIMIT ?
        """,
        (like, like, like, like, like, like, like, like,
         like, like, like, like, session_id, limit),
    ).fetchall()

    return [{"source_id": r["source_id"], "side": r["side"],
             "match_fields": (r["match_fields"] or "").split(",")}
            for r in rows]
