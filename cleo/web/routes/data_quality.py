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
