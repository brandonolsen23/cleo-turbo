"""
Activities API — structured activity logging across all CRM entities.

Replaces simple notes for opportunity/mandate tracking. Activities feed the
decay clock — logging an activity updates last_activity_at on the parent entity.
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from typing import Optional
from ...web.deps import get_db, get_current_user

router = APIRouter()

ACTIVITY_TYPES = ["call", "email", "meeting", "note"]
OUTCOMES = ["connected", "voicemail", "no_answer", "email_sent", "meeting_held", None]
ENTITY_TYPES = ["sell_opportunity", "buy_mandate", "deal", "contact", "group"]


class ActivityCreate(BaseModel):
    entity_type: str
    entity_id: str
    activity_type: str
    outcome: Optional[str] = None
    summary: Optional[str] = None
    next_step: Optional[str] = None


@router.get("")
def list_activities(
    entity_type: str = None,
    entity_id: str = None,
    activity_type: str = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """List activities, optionally filtered by entity or type."""
    conditions = []
    params = []

    if entity_type and entity_id:
        conditions.append("entity_type = ? AND entity_id = ?")
        params.extend([entity_type, entity_id])
    elif entity_type:
        conditions.append("entity_type = ?")
        params.append(entity_type)

    if activity_type:
        conditions.append("activity_type = ?")
        params.append(activity_type)

    where = " AND ".join(conditions) if conditions else "1=1"
    offset = (page - 1) * per_page

    total = db.execute(f"SELECT COUNT(*) FROM activities WHERE {where}", params).fetchone()[0]
    rows = db.execute(
        f"SELECT * FROM activities WHERE {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        params + [per_page, offset]
    ).fetchall()

    return {
        "results": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": max(1, (total + per_page - 1) // per_page),
    }


@router.get("/entity/{entity_type}/{entity_id}")
def entity_activities(
    entity_type: str,
    entity_id: str,
    limit: int = Query(50, ge=1, le=200),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Get all activities for a specific entity."""
    rows = db.execute(
        "SELECT * FROM activities WHERE entity_type = ? AND entity_id = ? "
        "ORDER BY created_at DESC LIMIT ?",
        (entity_type, entity_id, limit)
    ).fetchall()
    return [dict(r) for r in rows]


@router.post("")
def create_activity(body: ActivityCreate, db=Depends(get_db), user=Depends(get_current_user)):
    if body.entity_type not in ENTITY_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid entity_type. Must be one of: {', '.join(ENTITY_TYPES)}"
        )
    if body.activity_type not in ACTIVITY_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid activity_type. Must be one of: {', '.join(ACTIVITY_TYPES)}"
        )

    created_by = user.get("display_name", user.get("username"))

    cursor = db.execute(
        "INSERT INTO activities (entity_type, entity_id, activity_type, outcome, summary, next_step, created_by) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (body.entity_type, body.entity_id, body.activity_type,
         body.outcome, body.summary, body.next_step, created_by)
    )

    # Update last_activity_at on the parent entity to reset decay clock
    _update_last_activity(db, body.entity_type, body.entity_id)

    # If activity is on a contact or group, also update associated opportunities/mandates
    if body.entity_type == "contact":
        _propagate_activity_to_contact_entities(db, body.entity_id)
    elif body.entity_type == "group":
        _propagate_activity_to_group_entities(db, body.entity_id)

    db.commit()
    return {"id": cursor.lastrowid, "status": "created"}


@router.get("/stale")
def stale_entities(db=Depends(get_db), user=Depends(get_current_user)):
    """Get all stale sell opportunities and buy mandates."""
    stale_sell = db.execute(
        "SELECT so.id, so.property_id, so.status, so.owner, so.deal_value, "
        "so.last_activity_at, so.decay_days, "
        "p.display_address, p.city, "
        "CAST(julianday('now') - julianday(so.last_activity_at) AS INTEGER) AS days_since_activity "
        "FROM sell_opportunities so "
        "JOIN properties p ON so.property_id = p.id "
        "WHERE so.status = 'active' "
        "AND julianday('now') - julianday(so.last_activity_at) > so.decay_days "
        "ORDER BY days_since_activity DESC"
    ).fetchall()

    stale_buy = db.execute(
        "SELECT bm.id, bm.contact_id, bm.group_id, bm.status, bm.owner, "
        "bm.criteria_json, bm.last_activity_at, bm.decay_days, "
        "c.display_name AS contact_name, g.display_name AS group_name, "
        "CAST(julianday('now') - julianday(bm.last_activity_at) AS INTEGER) AS days_since_activity "
        "FROM buy_mandates bm "
        "LEFT JOIN contacts c ON bm.contact_id = c.id "
        "LEFT JOIN groups g ON bm.group_id = g.id "
        "WHERE bm.status = 'active' "
        "AND julianday('now') - julianday(bm.last_activity_at) > bm.decay_days "
        "ORDER BY days_since_activity DESC"
    ).fetchall()

    return {
        "sell_opportunities": [dict(r) for r in stale_sell],
        "buy_mandates": [dict(r) for r in stale_buy],
        "total_stale": len(stale_sell) + len(stale_buy),
    }


def _update_last_activity(db, entity_type: str, entity_id: str):
    """Update last_activity_at on the parent entity."""
    table_map = {
        "sell_opportunity": "sell_opportunities",
        "buy_mandate": "buy_mandates",
    }
    table = table_map.get(entity_type)
    if table:
        db.execute(
            f"UPDATE {table} SET last_activity_at = datetime('now'), updated_at = datetime('now') WHERE id = ?",
            (entity_id,)
        )


def _propagate_activity_to_contact_entities(db, contact_id: str):
    """When activity is logged on a contact, also refresh their opportunities/mandates."""
    db.execute(
        "UPDATE sell_opportunities SET last_activity_at = datetime('now') "
        "WHERE seller_contact_id = ? AND status = 'active'",
        (contact_id,)
    )
    db.execute(
        "UPDATE buy_mandates SET last_activity_at = datetime('now') "
        "WHERE contact_id = ? AND status = 'active'",
        (contact_id,)
    )


def _propagate_activity_to_group_entities(db, group_id: str):
    """When activity is logged on a group, also refresh their opportunities/mandates."""
    db.execute(
        "UPDATE sell_opportunities SET last_activity_at = datetime('now') "
        "WHERE seller_group_id = ? AND status = 'active'",
        (group_id,)
    )
    db.execute(
        "UPDATE buy_mandates SET last_activity_at = datetime('now') "
        "WHERE group_id = ? AND status = 'active'",
        (group_id,)
    )
