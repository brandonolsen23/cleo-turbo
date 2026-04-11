"""
Audit Log API — browse and filter audit trail.
"""

import json
from fastapi import APIRouter, Depends, Query
from ...web.deps import get_db, get_current_user

router = APIRouter()


@router.get("")
def browse_audit_log(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    entity_type: str = None,
    entity_id: str = None,
    action: str = None,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Paginated audit log with optional filters."""
    conditions = []
    params = []

    if entity_type:
        conditions.append("a.entity_type = ?")
        params.append(entity_type)
    if entity_id:
        conditions.append("a.entity_id = ?")
        params.append(entity_id)
    if action:
        conditions.append("a.action LIKE ?")
        params.append(f"%{action}%")

    where = " AND ".join(conditions) if conditions else "1=1"
    offset = (page - 1) * per_page

    total = db.execute(
        f"SELECT COUNT(*) FROM audit_log a WHERE {where}", params
    ).fetchone()[0]

    rows = db.execute(
        f"SELECT a.id, a.user_id, a.action, a.entity_type, a.entity_id, "
        f"a.details_json, a.created_at, u.username, u.display_name "
        f"FROM audit_log a "
        f"LEFT JOIN users u ON a.user_id = u.id "
        f"WHERE {where} ORDER BY a.created_at DESC LIMIT ? OFFSET ?",
        params + [per_page, offset]
    ).fetchall()

    results = []
    for r in rows:
        entry = dict(r)
        if entry.get("details_json"):
            try:
                entry["details"] = json.loads(entry["details_json"])
            except (json.JSONDecodeError, TypeError):
                entry["details"] = None
        else:
            entry["details"] = None
        del entry["details_json"]
        results.append(entry)

    return {
        "results": results,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": max(1, (total + per_page - 1) // per_page),
    }


@router.get("/entity/{entity_type}/{entity_id}")
def entity_audit_log(
    entity_type: str,
    entity_id: str,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Get all audit log entries for a specific entity."""
    rows = db.execute(
        "SELECT a.id, a.user_id, a.action, a.entity_type, a.entity_id, "
        "a.details_json, a.created_at, u.username, u.display_name "
        "FROM audit_log a "
        "LEFT JOIN users u ON a.user_id = u.id "
        "WHERE a.entity_type = ? AND a.entity_id = ? "
        "ORDER BY a.created_at DESC LIMIT 100",
        (entity_type, entity_id)
    ).fetchall()

    results = []
    for r in rows:
        entry = dict(r)
        if entry.get("details_json"):
            try:
                entry["details"] = json.loads(entry["details_json"])
            except (json.JSONDecodeError, TypeError):
                entry["details"] = None
        else:
            entry["details"] = None
        del entry["details_json"]
        results.append(entry)

    return {"results": results, "total": len(results)}
