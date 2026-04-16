"""
Discovery API — cluster browsing, detail, run history, ground truth, exclusions.
"""

import json
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
from ...web.deps import get_db, get_current_user

router = APIRouter()


# ── Models ───────────────────────────────────────────────────

class ExclusionRequest(BaseModel):
    exclusion_type: str
    exclusion_value: str
    reason: Optional[str] = None


# ── Helpers ──────────────────────────────────────────────────

def _get_latest_run_id(db) -> Optional[str]:
    """Return the run_id from the most recent completed discovery run, or None."""
    row = db.execute(
        "SELECT run_id FROM discovery_runs ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    return row["run_id"] if row else None


# ── Endpoints ────────────────────────────────────────────────

@router.get("")
def browse_clusters(
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    status: Optional[str] = Query(None),
    min_members: Optional[int] = Query(None, ge=1),
    sort: str = Query("member_count"),
    order: str = Query("desc"),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Browse clusters from the most recent discovery run.

    Groups evidence by target_group_id (the anchor) to reconstruct clusters.
    Each cluster shows anchor info, member count, and portfolio value.
    """
    run_id = _get_latest_run_id(db)
    if not run_id:
        return {
            "results": [],
            "total": 0,
            "page": page,
            "per_page": per_page,
            "pages": 0,
            "run": None,
        }

    # Fetch run metadata
    run_row = db.execute(
        "SELECT run_id, mode, started_at, completed_at, stats_json FROM discovery_runs WHERE run_id = ?",
        (run_id,)
    ).fetchone()
    run_info = dict(run_row)
    if run_info.get("stats_json"):
        try:
            run_info["stats"] = json.loads(run_info.pop("stats_json"))
        except (json.JSONDecodeError, TypeError):
            run_info.pop("stats_json", None)
            run_info["stats"] = None
    else:
        run_info.pop("stats_json", None)
        run_info["stats"] = None

    # Aggregate evidence into clusters with group details in a single query
    cluster_rows = db.execute(
        """
        SELECT
            e.target_group_id as anchor_group_id,
            COUNT(DISTINCT e.source_group_id) + 1 as member_count,
            AVG(e.confidence) as avg_confidence,
            MAX(e.confidence) as max_confidence,
            g.display_name as anchor_display_name,
            g.normalized_name as anchor_normalized_name,
            g.status as anchor_status,
            g.transaction_count as anchor_transaction_count,
            g.property_count as anchor_property_count,
            ga.total_assessed_value as portfolio_value
        FROM discovery_evidence e
        JOIN groups g ON g.id = e.target_group_id
        LEFT JOIN group_analytics ga ON ga.group_id = e.target_group_id
        WHERE e.run_id = ?
        GROUP BY e.target_group_id
        """,
        (run_id,)
    ).fetchall()

    # Build cluster list with filters
    clusters = []
    for cr in cluster_rows:
        member_count = cr["member_count"]

        if status and cr["anchor_status"] != status:
            continue
        if min_members is not None and member_count < min_members:
            continue

        confidence = cr["max_confidence"] or 0
        clusters.append({
            "anchor_group_id": cr["anchor_group_id"],
            "anchor_name": cr["anchor_display_name"],
            "member_count": member_count,
            "portfolio_value": cr["portfolio_value"],
            "confidence": confidence,
            "signal_count": member_count - 1,  # evidence links = members minus anchor
            "status": "auto_confirmed" if confidence >= 0.9 else "needs_review",
        })

    # Sort
    valid_sorts = {"member_count", "confidence", "anchor_name", "portfolio_value"}
    if sort not in valid_sorts:
        sort = "member_count"
    if order not in ("asc", "desc"):
        order = "desc"

    reverse = order == "desc"
    if sort == "member_count":
        clusters.sort(key=lambda x: (x["member_count"] or 0), reverse=reverse)
    elif sort == "confidence":
        clusters.sort(key=lambda x: (x["confidence"] or 0), reverse=reverse)
    elif sort == "anchor_name":
        clusters.sort(key=lambda x: (x["anchor_name"] or ""), reverse=reverse)
    elif sort == "portfolio_value":
        clusters.sort(key=lambda x: (x["portfolio_value"] or 0), reverse=reverse)

    total = len(clusters)
    offset = (page - 1) * per_page
    page_clusters = clusters[offset: offset + per_page]

    return {
        "results": page_clusters,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if total > 0 else 0,
        "run": run_info,
    }


@router.get("/runs")
def list_runs(
    limit: int = Query(20, ge=1, le=100),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """List recent discovery runs ordered by started_at DESC."""
    rows = db.execute(
        "SELECT run_id, mode, started_at, completed_at, stats_json FROM discovery_runs "
        "ORDER BY started_at DESC LIMIT ?",
        (limit,)
    ).fetchall()

    results = []
    for r in rows:
        d = dict(r)
        if d.get("stats_json"):
            try:
                d["stats"] = json.loads(d.pop("stats_json"))
            except (json.JSONDecodeError, TypeError):
                d.pop("stats_json", None)
                d["stats"] = None
        else:
            d.pop("stats_json", None)
            d["stats"] = None
        results.append(d)

    return {"results": results, "total": len(results)}


@router.get("/ground-truth")
def list_ground_truth(
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """List ground truth portfolios."""
    rows = db.execute(
        "SELECT id, portfolio_name, anchor_group_id, member_group_ids_json, notes "
        "FROM discovery_ground_truth ORDER BY portfolio_name"
    ).fetchall()

    results = []
    for r in rows:
        d = dict(r)
        raw = d.pop("member_group_ids_json", None)
        try:
            d["member_group_ids"] = json.loads(raw) if raw else []
        except (json.JSONDecodeError, TypeError):
            d["member_group_ids"] = []
        results.append(d)

    return {"results": results, "total": len(results)}


@router.get("/exclusions")
def list_exclusions(
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """List all discovery exclusions."""
    rows = db.execute(
        "SELECT id, exclusion_type, exclusion_value, reason, created_by, created_at "
        "FROM discovery_exclusions ORDER BY created_at DESC"
    ).fetchall()
    return {"results": [dict(r) for r in rows], "total": len(rows)}


@router.post("/exclusions")
def add_exclusion(
    body: ExclusionRequest,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Add a discovery exclusion."""
    db.execute(
        "INSERT INTO discovery_exclusions (exclusion_type, exclusion_value, reason, created_by) "
        "VALUES (?, ?, ?, ?)",
        (body.exclusion_type, body.exclusion_value, body.reason, user["username"])
    )
    db.commit()
    row = db.execute(
        "SELECT id, exclusion_type, exclusion_value, reason, created_by, created_at "
        "FROM discovery_exclusions WHERE rowid = last_insert_rowid()"
    ).fetchone()
    return dict(row)


@router.delete("/exclusions/{exclusion_id}")
def delete_exclusion(
    exclusion_id: int,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Remove a discovery exclusion."""
    row = db.execute(
        "SELECT id FROM discovery_exclusions WHERE id = ?", (exclusion_id,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Exclusion not found")
    db.execute("DELETE FROM discovery_exclusions WHERE id = ?", (exclusion_id,))
    db.commit()
    return {"deleted": True, "id": exclusion_id}


@router.get("/clusters/{anchor_group_id}")
def cluster_detail(
    anchor_group_id: str,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Cluster detail — all evidence for this anchor from the latest run.

    Returns anchor info, all member group details, evidence list, and a
    signal_summary keyed by signal_type.
    """
    run_id = _get_latest_run_id(db)
    if not run_id:
        raise HTTPException(status_code=404, detail="No discovery runs found")

    # Anchor group
    anchor_row = db.execute(
        "SELECT id, display_name, normalized_name, status, transaction_count, property_count "
        "FROM groups WHERE id = ?",
        (anchor_group_id,)
    ).fetchone()
    if not anchor_row:
        raise HTTPException(status_code=404, detail="Group not found")

    # Evidence for this anchor in the latest run
    evidence_rows = db.execute(
        "SELECT id, signal_type, signal_value, source_group_id, target_group_id, "
        "source_id, rule_id, confidence, iteration, created_at "
        "FROM discovery_evidence "
        "WHERE run_id = ? AND target_group_id = ? "
        "ORDER BY confidence DESC, signal_type",
        (run_id, anchor_group_id)
    ).fetchall()

    if not evidence_rows:
        raise HTTPException(status_code=404, detail="No discovery evidence for this group in the latest run")

    # Collect all member group IDs (anchor + all source_group_ids)
    member_ids = {anchor_group_id}
    for ev in evidence_rows:
        member_ids.add(ev["source_group_id"])

    # Fetch member group details
    placeholders = ",".join("?" for _ in member_ids)
    member_rows = db.execute(
        f"SELECT id, display_name, normalized_name, status, transaction_count, property_count "
        f"FROM groups WHERE id IN ({placeholders}) ORDER BY transaction_count DESC",
        list(member_ids)
    ).fetchall()

    # Build signal_summary: {signal_type: [signal_values]}
    signal_summary: dict = {}
    for ev in evidence_rows:
        stype = ev["signal_type"]
        if stype not in signal_summary:
            signal_summary[stype] = []
        val = ev["signal_value"]
        if val not in signal_summary[stype]:
            signal_summary[stype].append(val)

    # ── For each member, find the actual transactions that produced the linking signals ──
    # This lets the frontend link to source HTML via the pipeline trace page
    member_transactions = {}
    for member_id in member_ids:
        if member_id == anchor_group_id:
            continue

        # Get the evidence signals for this member
        member_evidence = [ev for ev in evidence_rows if ev["source_group_id"] == member_id]
        shared_contacts = set()
        shared_addresses = set()
        for ev in member_evidence:
            if ev["signal_type"] == "contact":
                shared_contacts.add(ev["signal_value"])
            elif ev["signal_type"] == "address":
                shared_addresses.add(ev["signal_value"])

        # Find transactions where this member appears as a party
        txn_rows = db.execute(
            """
            SELECT DISTINCT t.source_id, t.sale_date, t.sale_price,
                   t.display_address, t.city, tp.side, tp.party_name
            FROM transaction_parties tp
            JOIN transactions t ON t.source_id = tp.source_id
            WHERE tp.group_id = ?
            ORDER BY t.sale_date DESC
            LIMIT 10
            """,
            (member_id,)
        ).fetchall()

        member_transactions[member_id] = [dict(r) for r in txn_rows]

    # Also get anchor transactions
    anchor_txns = db.execute(
        """
        SELECT DISTINCT t.source_id, t.sale_date, t.sale_price,
               t.display_address, t.city, tp.side, tp.party_name
        FROM transaction_parties tp
        JOIN transactions t ON t.source_id = tp.source_id
        WHERE tp.group_id = ?
        ORDER BY t.sale_date DESC
        LIMIT 10
        """,
        (anchor_group_id,)
    ).fetchall()
    member_transactions[anchor_group_id] = [dict(r) for r in anchor_txns]

    return {
        "anchor": dict(anchor_row),
        "members": [dict(r) for r in member_rows],
        "member_count": len(member_ids),
        "evidence": [dict(ev) for ev in evidence_rows],
        "signal_summary": signal_summary,
        "member_transactions": member_transactions,
    }
