"""
Activities API — structured activity logging across CRM entities.

Phase 1 changes:
- 'property' added to the entity_type whitelist
- created_by_user_id FK populated from JWT 'sub'
- Primary entity FK (contact_id / property_id / group_id) auto-populated
  from entity_type/entity_id, with parent-record derivation for
  sell_opportunity / buy_mandate / deal types
- Auto-engage rule: any activity with a non-null contact_id or group_id
  flips that entity's status from 'pool' to 'engaged'
- Star auto-remove rule: when the current user logs an activity, any of
  their stars on the entities referenced by that activity are removed
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from typing import Optional
from ..deps import get_db, get_current_user

router = APIRouter()

ACTIVITY_TYPES = ["call", "email", "meeting", "note"]
OUTCOMES = ["connected", "voicemail", "no_answer", "email_sent", "meeting_held", None]
ENTITY_TYPES = ["sell_opportunity", "buy_mandate", "deal", "contact", "group", "property"]


class ActivityCreate(BaseModel):
    entity_type: str
    entity_id: str
    activity_type: str
    outcome: Optional[str] = None
    summary: Optional[str] = None
    next_step: Optional[str] = None
    happened_at: Optional[str] = None  # default now
    source: Optional[str] = None  # default 'manual'
    external_id: Optional[str] = None


def _user_id(user) -> int:
    return int(user["sub"])


def _resolve_fks(db, entity_type: str, entity_id: str):
    """Return (contact_id, property_id, group_id) for an activity's primary entity."""
    if entity_type == "contact":
        return entity_id, None, None
    if entity_type == "property":
        return None, entity_id, None
    if entity_type == "group":
        return None, None, entity_id
    if entity_type == "sell_opportunity":
        row = db.execute(
            "SELECT seller_contact_id, property_id, seller_group_id "
            "FROM sell_opportunities WHERE id = ?",
            (entity_id,),
        ).fetchone()
        if row:
            return row["seller_contact_id"], row["property_id"], row["seller_group_id"]
    elif entity_type == "buy_mandate":
        row = db.execute(
            "SELECT contact_id, group_id FROM buy_mandates WHERE id = ?",
            (entity_id,),
        ).fetchone()
        if row:
            return row["contact_id"], None, row["group_id"]
    elif entity_type == "deal":
        row = db.execute(
            "SELECT property_id, group_id FROM deals WHERE id = ?",
            (entity_id,),
        ).fetchone()
        if row:
            return None, row["property_id"], row["group_id"]
    return None, None, None


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
        f"SELECT * FROM activities WHERE {where} ORDER BY happened_at DESC, id DESC LIMIT ? OFFSET ?",
        params + [per_page, offset],
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
    rows = db.execute(
        "SELECT * FROM activities WHERE entity_type = ? AND entity_id = ? "
        "ORDER BY happened_at DESC, id DESC LIMIT ?",
        (entity_type, entity_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


@router.post("")
def create_activity(body: ActivityCreate, db=Depends(get_db), user=Depends(get_current_user)):
    if body.entity_type not in ENTITY_TYPES:
        raise HTTPException(status_code=400,
                            detail=f"Invalid entity_type. Must be one of: {', '.join(ENTITY_TYPES)}")
    if body.activity_type not in ACTIVITY_TYPES:
        raise HTTPException(status_code=400,
                            detail=f"Invalid activity_type. Must be one of: {', '.join(ACTIVITY_TYPES)}")

    me = _user_id(user)
    created_by = user.get("display_name") or user.get("username") or "unknown"
    contact_id, property_id, group_id = _resolve_fks(db, body.entity_type, body.entity_id)
    happened_at = body.happened_at  # None -> SQL DEFAULT (datetime('now'))
    source = body.source or "manual"

    # Insert activity
    cursor = db.execute(
        """
        INSERT INTO activities
          (entity_type, entity_id, activity_type, outcome, summary, next_step,
           created_by, created_by_user_id, source, external_id, happened_at,
           contact_id, property_id, group_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, datetime('now')), ?, ?, ?)
        """,
        (body.entity_type, body.entity_id, body.activity_type, body.outcome,
         body.summary, body.next_step, created_by, me, source, body.external_id,
         happened_at, contact_id, property_id, group_id),
    )

    # Auto-engage rule
    if contact_id:
        db.execute(
            "UPDATE contacts SET status='engaged', last_engaged_date=COALESCE(?, datetime('now')) "
            "WHERE id=? AND status='pool'",
            (happened_at, contact_id),
        )
    if group_id:
        db.execute(
            "UPDATE groups SET status='engaged' WHERE id=? AND status='pool'",
            (group_id,),
        )

    # Star auto-remove rule (current user only)
    fks = []
    if contact_id:
        fks.append(("contact", contact_id))
    if property_id:
        fks.append(("property", property_id))
    if group_id:
        fks.append(("group", group_id))
    if fks:
        where = " OR ".join("(entity_type=? AND entity_id=?)" for _ in fks)
        params = [me] + [v for pair in fks for v in pair]
        db.execute(f"DELETE FROM user_stars WHERE user_id=? AND ({where})", params)

    # last_activity_at propagation (existing behavior)
    if body.entity_type == "sell_opportunity":
        db.execute(
            "UPDATE sell_opportunities SET last_activity_at=datetime('now'), updated_at=datetime('now') WHERE id=?",
            (body.entity_id,),
        )
    elif body.entity_type == "buy_mandate":
        db.execute(
            "UPDATE buy_mandates SET last_activity_at=datetime('now'), updated_at=datetime('now') WHERE id=?",
            (body.entity_id,),
        )

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
