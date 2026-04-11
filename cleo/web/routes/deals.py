"""
Deals API — CRUD + pipeline view.
"""

import uuid
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from typing import Optional
from ...web.deps import get_db, get_current_user
from ...web.audit import log_action

router = APIRouter()

DEAL_STAGES = [
    "long_shot", "priority_deal", "mandate", "viable_deal",
    "in_negotiation", "under_contract", "firm", "closed", "lost",
]


class DealCreate(BaseModel):
    name: str
    stage: str = "long_shot"
    amount: Optional[int] = None
    close_date: Optional[str] = None
    property_id: Optional[str] = None
    group_id: Optional[str] = None
    deal_owner: Optional[str] = None
    description: Optional[str] = None
    next_step: Optional[str] = None
    priority: Optional[str] = None


class DealUpdate(BaseModel):
    name: Optional[str] = None
    stage: Optional[str] = None
    amount: Optional[int] = None
    close_date: Optional[str] = None
    property_id: Optional[str] = None
    group_id: Optional[str] = None
    deal_owner: Optional[str] = None
    description: Optional[str] = None
    next_step: Optional[str] = None
    priority: Optional[str] = None
    lost_reason: Optional[str] = None


@router.get("")
def list_deals(
    stage: str = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    conditions = []
    params = []
    if stage:
        conditions.append("stage = ?")
        params.append(stage)

    where = " AND ".join(conditions) if conditions else "1=1"
    offset = (page - 1) * per_page

    total = db.execute(f"SELECT COUNT(*) FROM deals WHERE {where}", params).fetchone()[0]
    rows = db.execute(
        f"SELECT * FROM deals WHERE {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        params + [per_page, offset]
    ).fetchall()

    return {
        "results": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": max(1, (total + per_page - 1) // per_page),
    }


@router.get("/pipeline")
def deal_pipeline(db=Depends(get_db), user=Depends(get_current_user)):
    """Deals grouped by stage for kanban view."""
    rows = db.execute("SELECT * FROM deals ORDER BY created_at DESC").fetchall()
    deals = [dict(r) for r in rows]

    stages = []
    for stage in DEAL_STAGES:
        stage_deals = [d for d in deals if d["stage"] == stage]
        stages.append({"stage": stage, "deals": stage_deals})

    active = [d for d in deals if d["stage"] not in ("closed", "lost")]
    pipeline_value = sum(d["amount"] or 0 for d in active)

    return {
        "stages": stages,
        "stats": {
            "total": len(deals),
            "active": len(active),
            "pipeline_value": pipeline_value,
        },
    }


@router.get("/{deal_id}")
def deal_detail(deal_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    deal = db.execute("SELECT * FROM deals WHERE id = ?", (deal_id,)).fetchone()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    result = dict(deal)

    # Enrich with property/group names
    if result.get("property_id"):
        prop = db.execute(
            "SELECT display_address, city FROM properties WHERE id = ?",
            (result["property_id"],)
        ).fetchone()
        if prop:
            result["property_address"] = prop["display_address"]
            result["property_city"] = prop["city"]

    if result.get("group_id"):
        grp = db.execute(
            "SELECT display_name FROM groups WHERE id = ?",
            (result["group_id"],)
        ).fetchone()
        if grp:
            result["group_name"] = grp["display_name"]

    return result


@router.post("")
def create_deal(body: DealCreate, db=Depends(get_db), user=Depends(get_current_user)):
    deal_id = f"DEAL_{uuid.uuid4().hex[:8].upper()}"

    if body.stage not in DEAL_STAGES:
        raise HTTPException(status_code=400, detail=f"Invalid stage. Must be one of: {', '.join(DEAL_STAGES)}")

    db.execute(
        "INSERT INTO deals (id, name, stage, amount, close_date, property_id, group_id, "
        "deal_owner, description, next_step, priority) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (deal_id, body.name, body.stage, body.amount, body.close_date,
         body.property_id, body.group_id, body.deal_owner,
         body.description, body.next_step, body.priority)
    )
    log_action(db, user, "deal.create", "deal", deal_id, {"name": body.name, "stage": body.stage, "amount": body.amount})
    db.commit()
    return {"id": deal_id, "status": "created"}


@router.patch("/{deal_id}")
def update_deal(deal_id: str, body: DealUpdate, db=Depends(get_db), user=Depends(get_current_user)):
    if not db.execute("SELECT 1 FROM deals WHERE id = ?", (deal_id,)).fetchone():
        raise HTTPException(status_code=404, detail="Deal not found")

    updates = {}
    for field in ["name", "stage", "amount", "close_date", "property_id", "group_id",
                   "deal_owner", "description", "next_step", "priority", "lost_reason"]:
        val = getattr(body, field)
        if val is not None:
            updates[field] = val

    if body.stage and body.stage not in DEAL_STAGES:
        raise HTTPException(status_code=400, detail=f"Invalid stage.")

    if updates:
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values())
        db.execute(
            f"UPDATE deals SET {set_clause}, updated_at = datetime('now') WHERE id = ?",
            values + [deal_id]
        )
        log_action(db, user, "deal.update", "deal", deal_id, updates)
        db.commit()

    return {"id": deal_id, "updated": list(updates.keys())}


@router.delete("/{deal_id}")
def delete_deal(deal_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    deal = db.execute("SELECT name, stage FROM deals WHERE id = ?", (deal_id,)).fetchone()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    db.execute("DELETE FROM deals WHERE id = ?", (deal_id,))
    log_action(db, user, "deal.delete", "deal", deal_id, {"name": deal["name"], "stage": deal["stage"]})
    db.commit()
    return {"id": deal_id, "status": "deleted"}
