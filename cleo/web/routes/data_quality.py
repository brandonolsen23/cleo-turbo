"""
Data Quality API — browse issues, update status, trigger scans.
"""

import sys
import os
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from typing import Optional
from ...web.deps import get_db, get_current_user

router = APIRouter()


@router.get("/summary")
def quality_summary(db=Depends(get_db), user=Depends(get_current_user)):
    """Overview stats for the data quality dashboard."""
    total = db.execute("SELECT COUNT(*) FROM data_issues").fetchone()[0]
    open_count = db.execute("SELECT COUNT(*) FROM data_issues WHERE status = 'open'").fetchone()[0]

    by_rule = {}
    for row in db.execute("SELECT rule, COUNT(*) as cnt FROM data_issues WHERE status = 'open' GROUP BY rule ORDER BY cnt DESC"):
        by_rule[row["rule"]] = row["cnt"]

    by_severity = {}
    for row in db.execute("SELECT severity, COUNT(*) as cnt FROM data_issues WHERE status = 'open' GROUP BY severity"):
        by_severity[row["severity"]] = row["cnt"]

    by_status = {}
    for row in db.execute("SELECT status, COUNT(*) as cnt FROM data_issues GROUP BY status"):
        by_status[row["status"]] = row["cnt"]

    by_origin = {}
    for row in db.execute("SELECT introduced_at, COUNT(*) as cnt FROM data_issues WHERE status = 'open' GROUP BY introduced_at ORDER BY cnt DESC"):
        by_origin[row["introduced_at"] or "unknown"] = row["cnt"]

    last_scan = db.execute("SELECT MAX(created_at) FROM data_issues").fetchone()[0]

    return {
        "total_issues": total,
        "open_issues": open_count,
        "by_rule": by_rule,
        "by_severity": by_severity,
        "by_status": by_status,
        "by_origin_stage": by_origin,
        "last_scan": last_scan,
    }


@router.get("/issues")
def browse_issues(
    rule: str = None,
    severity: str = None,
    status: str = Query("open"),
    introduced_at: str = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Paginated issue list with filters."""
    conditions = []
    params = []

    if rule:
        conditions.append("rule = ?")
        params.append(rule)
    if severity:
        conditions.append("severity = ?")
        params.append(severity)
    if status:
        conditions.append("status = ?")
        params.append(status)
    if introduced_at:
        conditions.append("introduced_at = ?")
        params.append(introduced_at)

    where = " AND ".join(conditions) if conditions else "1=1"
    offset = (page - 1) * per_page

    total = db.execute(f"SELECT COUNT(*) FROM data_issues WHERE {where}", params).fetchone()[0]
    rows = db.execute(
        f"SELECT * FROM data_issues WHERE {where} ORDER BY severity ASC, created_at DESC LIMIT ? OFFSET ?",
        params + [per_page, offset]
    ).fetchall()

    return {
        "results": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": max(1, (total + per_page - 1) // per_page),
    }


@router.get("/issues/{issue_id}")
def issue_detail(issue_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    """Single issue detail."""
    row = db.execute("SELECT * FROM data_issues WHERE id = ?", (issue_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Issue not found")
    return dict(row)


class IssueUpdate(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None


@router.patch("/issues/{issue_id}")
def update_issue(issue_id: int, body: IssueUpdate, db=Depends(get_db), user=Depends(get_current_user)):
    """Update issue status or notes."""
    if not db.execute("SELECT 1 FROM data_issues WHERE id = ?", (issue_id,)).fetchone():
        raise HTTPException(status_code=404, detail="Issue not found")

    updates = {}
    if body.status:
        if body.status not in ("open", "resolved", "ignored", "false_positive"):
            raise HTTPException(status_code=400, detail="Invalid status")
        updates["status"] = body.status
        if body.status in ("resolved", "ignored", "false_positive"):
            updates["resolved_by"] = user.get("display_name", user.get("username"))
            updates["resolved_at"] = "datetime('now')"
    if body.notes is not None:
        updates["notes"] = body.notes

    if updates:
        set_parts = []
        values = []
        for k, v in updates.items():
            if v == "datetime('now')":
                set_parts.append(f"{k} = datetime('now')")
            else:
                set_parts.append(f"{k} = ?")
                values.append(v)
        set_clause = ", ".join(set_parts)
        db.execute(f"UPDATE data_issues SET {set_clause} WHERE id = ?", values + [issue_id])
        db.commit()

    return {"id": issue_id, "updated": list(updates.keys())}


@router.get("/rules")
def list_rules(db=Depends(get_db), user=Depends(get_current_user)):
    """List all rules with descriptions and issue counts."""
    # Import rule metadata
    PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
    sys.path.insert(0, PROJECT_ROOT)
    from engines.rt.scanner.rules import RULES

    # Get counts per rule
    counts = {}
    for row in db.execute("SELECT rule, COUNT(*) as cnt FROM data_issues WHERE status = 'open' GROUP BY rule"):
        counts[row["rule"]] = row["cnt"]

    result = []
    for rule_name, meta in RULES.items():
        result.append({
            "rule": rule_name,
            "description": meta["description"],
            "default_severity": meta["severity"],
            "open_count": counts.get(rule_name, 0),
        })

    return sorted(result, key=lambda r: -r["open_count"])


@router.post("/issues/{issue_id}/flag")
def flag_for_review(issue_id: int, body: IssueUpdate, db=Depends(get_db), user=Depends(get_current_user)):
    """Flag an issue for code review. Writes to a review file that persists as a worklist."""
    row = db.execute("SELECT * FROM data_issues WHERE id = ?", (issue_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Issue not found")

    issue = dict(row)

    # Update status in DB
    db.execute(
        "UPDATE data_issues SET status = 'flagged', notes = ?, resolved_by = ?, resolved_at = datetime('now') WHERE id = ?",
        (body.notes or "", user.get("display_name", user.get("username")), issue_id)
    )
    db.commit()

    # Write to review file
    import json
    review_path = os.path.join(
        os.path.dirname(__file__), '..', '..', '..', 'data', 'review-issues.json'
    )
    review_path = os.path.abspath(review_path)

    existing = []
    if os.path.exists(review_path):
        with open(review_path, 'r') as f:
            try:
                existing = json.load(f)
            except json.JSONDecodeError:
                existing = []

    entry = {
        "issue_id": issue["id"],
        "source_id": issue["source_id"],
        "rule": issue["rule"],
        "severity": issue["severity"],
        "field_path": issue["field_path"],
        "actual_value": issue["actual_value"],
        "message": issue["message"],
        "introduced_at": issue["introduced_at"],
        "origin_field": issue["origin_field"],
        "explanation": issue["explanation"],
        "code_location": issue["code_location"],
        "reviewer_notes": body.notes or "",
        "flagged_by": user.get("display_name", user.get("username")),
        "flagged_at": issue.get("resolved_at") or "",
    }

    # Don't duplicate
    if not any(e["issue_id"] == issue["id"] for e in existing):
        existing.append(entry)

    with open(review_path, 'w') as f:
        json.dump(existing, f, indent=2)

    return {"id": issue_id, "status": "flagged", "review_file": "data/review-issues.json"}


@router.post("/scan")
def trigger_scan(
    rt_id: str = Query(None),
    rule: str = Query(None),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Trigger a data quality scan."""
    PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
    sys.path.insert(0, PROJECT_ROOT)
    from engines.rt.scanner.run import run_scan

    results = run_scan(rt_id=rt_id, rule_filter=rule, trace=True)

    return {
        "status": "completed",
        "issues_found": len(results),
    }


# ── Stage 1: parcel-resolution tiers + review queue ─────────────────

def _review_reason(method, loc_name, containment, field_match, pip_verified):
    """Plain-English explanation of why a parcel join is uncertain.
    Returned to the UI verbatim — keep it human, not codey."""
    loc = (loc_name or "").upper()
    if method == "arn_only":
        return ("Resolved only by its assessment roll number (ARN), with no independent "
                "location check — the parcel wasn't confirmed by geocoding.")
    if method == "pin_bridge":
        return ("Resolved by bridging a PIN to an ARN via GeoWarehouse data — a weak, often "
                "ambiguous link (one PIN can map to several parcels).")
    if method in ("unresolved", "error") or not method:
        return "Could not be resolved to a parcel at all."
    if containment == "nearest_centroid":
        return ("The geocoded point wasn't inside any parcel, so the closest one was chosen "
                "— a guess that can land on a neighbour.")
    if containment and containment != "contained":
        return f"The geocoded point wasn't confirmed inside the chosen parcel ({containment})."
    if loc.startswith("ROAD") or loc.startswith("STREET"):
        return ("The address was interpolated along the street rather than matched to a parcel "
                "address point, so it may sit on a neighbouring lot.")
    if field_match == 0:
        return ("The parcel was found, but its address components didn't fully match the "
                "transaction's address — worth confirming it's the right property.")
    return "Flagged for review — the resolver's confidence in this parcel is low."


@router.get("/tier-summary")
def tier_summary(db=Depends(get_db), user=Depends(get_current_user)):
    """Counts of transactions by parcel verification tier (Stage 1).
    A NULL tier means the record hasn't been re-tagged by the verification pass yet."""
    counts = {"verified": 0, "probable": 0, "review": 0, "untagged": 0}
    total = db.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    for row in db.execute(
        "SELECT parcel_tier, COUNT(*) AS cnt FROM transactions GROUP BY parcel_tier"
    ):
        key = row["parcel_tier"] or "untagged"
        counts[key] = counts.get(key, 0) + row["cnt"]
    return {"total": total, "tiers": counts}


@router.get("/review-queue")
def review_queue(
    method: Optional[str] = None,
    containment: Optional[str] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Transactions whose parcel placement is uncertain (tier='review'), each with a
    plain-English reason and the IDs to link back to the source HTML, the pipeline
    trace, and the parcel on the map."""
    conditions = ["t.parcel_tier = 'review'"]
    params = []
    if method:
        conditions.append("t.parcel_method = ?")
        params.append(method)
    if containment:
        conditions.append("t.parcel_containment = ?")
        params.append(containment)
    where = " AND ".join(conditions)

    total = db.execute(
        f"SELECT COUNT(*) FROM transactions t WHERE {where}", params
    ).fetchone()[0]
    offset = (page - 1) * per_page
    rows = db.execute(
        f"""SELECT t.source_id, t.display_address, t.city, t.arn, t.property_id,
                   t.parcel_method, t.parcel_loc_name, t.parcel_addr_type,
                   t.parcel_geocode_score, t.parcel_field_match, t.parcel_containment,
                   t.parcel_confidence, t.pip_verified, t.parcel_tier,
                   p.display_address AS parcel_address
            FROM transactions t
            LEFT JOIN properties p ON p.id = t.property_id
            WHERE {where}
            ORDER BY t.parcel_confidence ASC, t.source_id
            LIMIT ? OFFSET ?""",
        params + [per_page, offset],
    ).fetchall()

    results = []
    for r in rows:
        d = dict(r)
        d["reason"] = _review_reason(
            d.get("parcel_method"), d.get("parcel_loc_name"),
            d.get("parcel_containment"), d.get("parcel_field_match"),
            d.get("pip_verified"),
        )
        d["source_html_url"] = f"/api/transactions/{d['source_id']}/html"
        d["trace_url"] = f"/pipeline/trace/{d['source_id']}"
        d["map_url"] = f"/properties/{d['property_id']}" if d.get("property_id") else None
        results.append(d)

    pages = (total + per_page - 1) // per_page
    return {"results": results, "total": total, "page": page,
            "per_page": per_page, "pages": pages}
