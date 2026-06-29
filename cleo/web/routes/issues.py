"""
Issues API — in-app structured bug/data-quality tracker.

Each issue is anchored to:
  - a page entity: (entity_type, entity_id)  e.g. property PRO_26073
  - optionally a UI component: free-form `component` string + JSON blob of
    component-specific data (e.g. {"source_id": "RT196173"} for a row in the
    transactions table)

Categories is a JSON array (multi-select). The 11 allowed values:

    rt_property_mismatch    — RT transaction linked to wrong parcel
    parcel_geometry_wrong   — map outline / photos don't match the real site
    wrong_owner             — current_owner_group_id is incorrect
    group_clustering_issue  — auto-group includes / excludes wrong SPVs
    parsing_error           — field has a wrong-type value (address in
                              contact slot, sale price in phone, etc.)
    missing_data            — expected field is null when source has it
    duplicate_entity        — same record exists twice
    formatting_issue        — pipes in HQ address, raw values, bad date format
    layout_issue            — table overflowing, card squished, etc.
    wrong_calculation       — counts/sums don't reconcile, derivation looks off
    other                   — catch-all (incl. feature requests)
"""

import json
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field

from ...web.deps import get_db, get_current_user
from ...web.audit import log_action

router = APIRouter()


# ── Allowed values ─────────────────────────────────────────────────────────

ALLOWED_ENTITY_TYPES = {
    "property", "contact", "group", "transaction", "auto_group", "general",
}

ALLOWED_CATEGORIES = {
    "rt_property_mismatch",
    "parcel_geometry_wrong",
    "wrong_owner",
    "group_clustering_issue",
    "parsing_error",
    "missing_data",
    "duplicate_entity",
    "formatting_issue",
    "layout_issue",
    "wrong_calculation",
    "other",
}

ALLOWED_STATUSES = {"open", "in_progress", "resolved", "wontfix", "duplicate"}

ALLOWED_SEVERITIES = {"low", "medium", "high", "critical"}

# Auto-derived severity per category — used when the reporter doesn't supply one.
# Picked the highest severity across the categories list.
CATEGORY_DEFAULT_SEVERITY = {
    "rt_property_mismatch":   "high",
    "parcel_geometry_wrong":  "high",
    "wrong_owner":            "high",
    "group_clustering_issue": "medium",
    "parsing_error":          "medium",
    "missing_data":           "medium",
    "duplicate_entity":       "medium",
    "wrong_calculation":      "medium",
    "formatting_issue":       "low",
    "layout_issue":           "low",
    "other":                  "low",
}

_SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def _derive_severity(categories: list[str]) -> str:
    """Highest default severity across the picked categories."""
    if not categories:
        return "medium"
    best = "low"
    for c in categories:
        cand = CATEGORY_DEFAULT_SEVERITY.get(c, "medium")
        if _SEVERITY_RANK[cand] > _SEVERITY_RANK[best]:
            best = cand
    return best


# ── Request models ─────────────────────────────────────────────────────────

class CreateIssueRequest(BaseModel):
    entity_type: str
    entity_id: Optional[str] = None
    component: Optional[str] = None
    component_data: Optional[dict] = None
    categories: list[str] = Field(min_length=1)
    title: str
    description: str
    severity: Optional[str] = None   # auto-derived if missing


class UpdateIssueRequest(BaseModel):
    status: Optional[str] = None
    severity: Optional[str] = None
    categories: Optional[list[str]] = None
    title: Optional[str] = None
    description: Optional[str] = None
    resolution_notes: Optional[str] = None
    fixed_in_commit: Optional[str] = None


# ── Helpers ────────────────────────────────────────────────────────────────

def _validate_categories(cats: list[str]):
    bad = [c for c in cats if c not in ALLOWED_CATEGORIES]
    if bad:
        raise HTTPException(400, f"Invalid categories: {bad}. "
                                 f"Allowed: {sorted(ALLOWED_CATEGORIES)}")
    if not cats:
        raise HTTPException(400, "At least one category is required")


def _validate_entity_type(et: str):
    if et not in ALLOWED_ENTITY_TYPES:
        raise HTTPException(400, f"Invalid entity_type: {et}. "
                                 f"Allowed: {sorted(ALLOWED_ENTITY_TYPES)}")


def _row_to_issue(r) -> dict:
    d = dict(r)
    try:
        d["categories"] = json.loads(d.get("categories") or "[]")
    except (json.JSONDecodeError, TypeError):
        d["categories"] = []
    if d.get("component_data_json"):
        try:
            d["component_data"] = json.loads(d["component_data_json"])
        except (json.JSONDecodeError, TypeError):
            d["component_data"] = None
    else:
        d["component_data"] = None
    d.pop("component_data_json", None)
    return d


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.get("")
def list_issues(
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    entity_id: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    sort: str = Query("reported_at"),
    order: str = Query("desc"),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Paginated list of issues. Default: open issues sorted newest-first."""
    conditions = []
    params: list = []

    if status:
        if status not in ALLOWED_STATUSES:
            raise HTTPException(400, f"Invalid status: {status}")
        conditions.append("status = ?")
        params.append(status)
    if category:
        if category not in ALLOWED_CATEGORIES:
            raise HTTPException(400, f"Invalid category: {category}")
        # JSON array membership via LIKE — safe because category names are alphanumeric
        conditions.append("categories LIKE ?")
        params.append(f'%"{category}"%')
    if severity:
        if severity not in ALLOWED_SEVERITIES:
            raise HTTPException(400, f"Invalid severity: {severity}")
        conditions.append("severity = ?")
        params.append(severity)
    if entity_type:
        _validate_entity_type(entity_type)
        conditions.append("entity_type = ?")
        params.append(entity_type)
    if entity_id:
        conditions.append("entity_id = ?")
        params.append(entity_id)
    if q and q.strip():
        like = f"%{q.strip()}%"
        conditions.append("(title LIKE ? OR description LIKE ?)")
        params.extend([like, like])

    where = " AND ".join(conditions) if conditions else "1=1"

    sort_col = {
        "reported_at":  "reported_at",
        "severity":     "CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 "
                        "             WHEN 'medium' THEN 2 ELSE 3 END",
        "status":       "status",
        "id":           "id",
        "updated_at":   "updated_at",
    }.get(sort, "reported_at")
    if order not in ("asc", "desc"):
        order = "desc"

    total = db.execute(f"SELECT COUNT(*) FROM issues WHERE {where}", params).fetchone()[0]
    rows = db.execute(
        f"SELECT * FROM issues WHERE {where} "
        f"ORDER BY {sort_col} {order}, id DESC "
        f"LIMIT ? OFFSET ?",
        params + [per_page, (page - 1) * per_page],
    ).fetchall()

    return {
        "results": [_row_to_issue(r) for r in rows],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if total else 0,
    }


@router.get("/stats")
def issue_stats(db=Depends(get_db), user=Depends(get_current_user)):
    """Counts by status, severity, and category. Used by the Dashboard widget."""
    by_status = {r["status"]: r["n"] for r in db.execute(
        "SELECT status, COUNT(*) AS n FROM issues GROUP BY status"
    )}
    by_severity = {r["severity"]: r["n"] for r in db.execute(
        "SELECT severity, COUNT(*) AS n FROM issues WHERE status='open' GROUP BY severity"
    )}
    # category counts require unpacking the JSON arrays
    cat_counts: dict[str, int] = {}
    for r in db.execute("SELECT categories FROM issues WHERE status='open'"):
        try:
            for c in json.loads(r["categories"] or "[]"):
                cat_counts[c] = cat_counts.get(c, 0) + 1
        except (json.JSONDecodeError, TypeError):
            pass
    return {
        "by_status": by_status,
        "open_by_severity": by_severity,
        "open_by_category": cat_counts,
    }


@router.get("/{issue_id}")
def get_issue(issue_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    r = db.execute("SELECT * FROM issues WHERE id = ?", (issue_id,)).fetchone()
    if not r:
        raise HTTPException(404, "Issue not found")
    return _row_to_issue(r)


@router.post("")
def create_issue(body: CreateIssueRequest, db=Depends(get_db), user=Depends(get_current_user)):
    _validate_entity_type(body.entity_type)
    _validate_categories(body.categories)
    if body.severity and body.severity not in ALLOWED_SEVERITIES:
        raise HTTPException(400, f"Invalid severity: {body.severity}")

    severity = body.severity or _derive_severity(body.categories)
    title = (body.title or "").strip()
    description = (body.description or "").strip()
    if not title:
        raise HTTPException(400, "title is required")
    if not description:
        raise HTTPException(400, "description is required")

    reporter = user.get("display_name") or user.get("username") or "unknown"
    component_data_json = (
        json.dumps(body.component_data) if body.component_data is not None else None
    )

    cur = db.execute(
        """INSERT INTO issues
             (entity_type, entity_id, component, component_data_json,
              categories, severity, title, description,
              status, reported_by)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)""",
        (body.entity_type, body.entity_id, body.component, component_data_json,
         json.dumps(body.categories), severity, title, description, reporter),
    )
    issue_id = cur.lastrowid
    log_action(db, user, "issue.create", "issue", str(issue_id), {
        "entity_type": body.entity_type, "entity_id": body.entity_id,
        "categories": body.categories, "severity": severity,
    })
    db.commit()

    r = db.execute("SELECT * FROM issues WHERE id = ?", (issue_id,)).fetchone()
    return _row_to_issue(r)


@router.patch("/{issue_id}")
def update_issue(issue_id: int, body: UpdateIssueRequest,
                 db=Depends(get_db), user=Depends(get_current_user)):
    existing = db.execute("SELECT * FROM issues WHERE id = ?", (issue_id,)).fetchone()
    if not existing:
        raise HTTPException(404, "Issue not found")

    updates: dict = {}
    if body.status is not None:
        if body.status not in ALLOWED_STATUSES:
            raise HTTPException(400, f"Invalid status: {body.status}")
        updates["status"] = body.status
        # Auto-stamp resolved_at / resolved_by when transitioning into a closed state.
        if body.status in ("resolved", "wontfix", "duplicate") and not existing["resolved_at"]:
            updates["resolved_at"] = "datetime('now')"   # SQL literal — handled below
            updates["resolved_by"] = user.get("display_name") or user.get("username") or "unknown"

    if body.severity is not None:
        if body.severity not in ALLOWED_SEVERITIES:
            raise HTTPException(400, f"Invalid severity: {body.severity}")
        updates["severity"] = body.severity
    if body.categories is not None:
        _validate_categories(body.categories)
        updates["categories"] = json.dumps(body.categories)
    if body.title is not None:
        title = body.title.strip()
        if not title:
            raise HTTPException(400, "title cannot be empty")
        updates["title"] = title
    if body.description is not None:
        desc = body.description.strip()
        if not desc:
            raise HTTPException(400, "description cannot be empty")
        updates["description"] = desc
    if body.resolution_notes is not None:
        updates["resolution_notes"] = body.resolution_notes.strip()
    if body.fixed_in_commit is not None:
        updates["fixed_in_commit"] = body.fixed_in_commit.strip()

    if not updates:
        return _row_to_issue(existing)

    # Build SET clause; handle the SQL-literal datetime sentinel
    set_parts = []
    params: list = []
    for k, v in updates.items():
        if v == "datetime('now')":
            set_parts.append(f"{k} = datetime('now')")
        else:
            set_parts.append(f"{k} = ?")
            params.append(v)
    set_parts.append("updated_at = datetime('now')")

    db.execute(f"UPDATE issues SET {', '.join(set_parts)} WHERE id = ?", params + [issue_id])
    log_action(db, user, "issue.update", "issue", str(issue_id), {
        k: (v if v != "datetime('now')" else "now") for k, v in updates.items()
    })
    db.commit()

    r = db.execute("SELECT * FROM issues WHERE id = ?", (issue_id,)).fetchone()
    return _row_to_issue(r)
