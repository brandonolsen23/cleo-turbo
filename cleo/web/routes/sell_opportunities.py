"""
Sell Opportunities API — a property is potentially available for sale.
"""

import json
import uuid
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from typing import Optional
from ...web.deps import get_db, get_current_user
from ...web.audit import log_action

router = APIRouter()

SELL_OPP_STATUSES = ["active", "on_hold", "stale", "matched", "closed_won", "closed_lost"]


class SellOpportunityCreate(BaseModel):
    property_id: str
    seller_contact_id: Optional[str] = None
    seller_group_id: Optional[str] = None
    deal_value: Optional[int] = None
    owner: Optional[str] = None
    notes: Optional[str] = None
    decay_days: int = 14


class SellOpportunityUpdate(BaseModel):
    seller_contact_id: Optional[str] = None
    seller_group_id: Optional[str] = None
    deal_value: Optional[int] = None
    status: Optional[str] = None
    owner: Optional[str] = None
    notes: Optional[str] = None
    decay_days: Optional[int] = None


@router.get("/filters")
def sell_opp_filters(db=Depends(get_db), user=Depends(get_current_user)):
    """Available filter values for sell opportunities."""
    regions = [r[0] for r in db.execute(
        "SELECT DISTINCT p.region FROM sell_opportunities so "
        "JOIN properties p ON so.property_id = p.id WHERE p.region IS NOT NULL ORDER BY p.region"
    ).fetchall()]
    asset_classes = [r[0] for r in db.execute(
        "SELECT DISTINCT p.asset_class FROM sell_opportunities so "
        "JOIN properties p ON so.property_id = p.id WHERE p.asset_class IS NOT NULL ORDER BY p.asset_class"
    ).fetchall()]
    owners = [r[0] for r in db.execute(
        "SELECT DISTINCT owner FROM sell_opportunities WHERE owner IS NOT NULL ORDER BY owner"
    ).fetchall()]
    return {"regions": regions, "asset_classes": asset_classes, "owners": owners}


@router.get("")
def list_sell_opportunities(
    status: str = None,
    owner: str = None,
    region: str = None,
    asset_class: str = None,
    min_value: int = None,
    max_value: int = None,
    stale_only: bool = False,
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    sort: str = "created_at",
    order: str = "desc",
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    conditions = []
    params = []

    if status:
        conditions.append("so.status = ?")
        params.append(status)
    if owner:
        conditions.append("so.owner = ?")
        params.append(owner)
    if region:
        conditions.append("p.region = ?")
        params.append(region)
    if asset_class:
        conditions.append("p.asset_class = ?")
        params.append(asset_class)
    if min_value is not None:
        conditions.append("so.deal_value >= ?")
        params.append(min_value)
    if max_value is not None:
        conditions.append("so.deal_value <= ?")
        params.append(max_value)
    if stale_only:
        conditions.append(
            "so.status = 'active' AND "
            "julianday('now') - julianday(so.last_activity_at) > so.decay_days"
        )

    where = " AND ".join(conditions) if conditions else "1=1"

    # Validate sort column
    sort_cols = {
        "created_at": "so.created_at",
        "deal_value": "so.deal_value",
        "last_activity_at": "so.last_activity_at",
        "status": "so.status",
    }
    sort_col = sort_cols.get(sort, "so.created_at")
    order_dir = "ASC" if order == "asc" else "DESC"

    offset = (page - 1) * per_page

    total = db.execute(
        f"SELECT COUNT(*) FROM sell_opportunities so "
        f"JOIN properties p ON so.property_id = p.id WHERE {where}",
        params
    ).fetchone()[0]

    rows = db.execute(
        f"SELECT so.*, "
        f"p.display_address, p.city, p.region, p.asset_class, p.lat, p.lng, "
        f"p.most_recent_sale_price, p.most_recent_sale_date, "
        f"c.display_name AS seller_contact_name, "
        f"g.display_name AS seller_group_name, "
        f"CASE WHEN so.status = 'active' AND julianday('now') - julianday(so.last_activity_at) > so.decay_days "
        f"  THEN 1 ELSE 0 END AS is_stale, "
        f"CAST(julianday('now') - julianday(so.last_activity_at) AS INTEGER) AS days_since_activity "
        f"FROM sell_opportunities so "
        f"JOIN properties p ON so.property_id = p.id "
        f"LEFT JOIN contacts c ON so.seller_contact_id = c.id "
        f"LEFT JOIN groups g ON so.seller_group_id = g.id "
        f"WHERE {where} ORDER BY {sort_col} {order_dir} LIMIT ? OFFSET ?",
        params + [per_page, offset]
    ).fetchall()

    return {
        "results": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": max(1, (total + per_page - 1) // per_page),
    }


@router.get("/{opp_id}")
def sell_opportunity_detail(opp_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    row = db.execute(
        "SELECT so.*, "
        "p.display_address, p.city, p.region, p.asset_class, p.lat, p.lng, "
        "p.most_recent_sale_price, p.most_recent_sale_date, p.acreage, "
        "p.current_owner_name, p.current_owner_group_id, "
        "c.display_name AS seller_contact_name, c.phone AS seller_contact_phone, "
        "c.email AS seller_contact_email, "
        "g.display_name AS seller_group_name, "
        "CASE WHEN so.status = 'active' AND julianday('now') - julianday(so.last_activity_at) > so.decay_days "
        "  THEN 1 ELSE 0 END AS is_stale, "
        "CAST(julianday('now') - julianday(so.last_activity_at) AS INTEGER) AS days_since_activity "
        "FROM sell_opportunities so "
        "JOIN properties p ON so.property_id = p.id "
        "LEFT JOIN contacts c ON so.seller_contact_id = c.id "
        "LEFT JOIN groups g ON so.seller_group_id = g.id "
        "WHERE so.id = ?",
        (opp_id,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Sell opportunity not found")

    result = dict(row)

    # Get activities
    activities = db.execute(
        "SELECT * FROM activities WHERE entity_type = 'sell_opportunity' AND entity_id = ? "
        "ORDER BY created_at DESC LIMIT 50",
        (opp_id,)
    ).fetchall()
    result["activities"] = [dict(a) for a in activities]

    # Get matching buy mandates (criteria-based)
    property_data = db.execute(
        "SELECT asset_class, region, city, most_recent_sale_price FROM properties WHERE id = ?",
        (result["property_id"],)
    ).fetchone()
    if property_data:
        matches = _find_matching_mandates(db, dict(property_data))
        result["matching_mandates"] = matches

    return result


@router.post("")
def create_sell_opportunity(body: SellOpportunityCreate, db=Depends(get_db), user=Depends(get_current_user)):
    # Verify property exists
    if not db.execute("SELECT 1 FROM properties WHERE id = ?", (body.property_id,)).fetchone():
        raise HTTPException(status_code=400, detail="Property not found")

    opp_id = f"SO_{uuid.uuid4().hex[:8].upper()}"

    db.execute(
        "INSERT INTO sell_opportunities (id, property_id, seller_contact_id, seller_group_id, "
        "deal_value, owner, notes, decay_days) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (opp_id, body.property_id, body.seller_contact_id, body.seller_group_id,
         body.deal_value, body.owner, body.notes, body.decay_days)
    )
    log_action(db, user, "sell_opportunity.create", "sell_opportunity", opp_id,
               {"property_id": body.property_id, "deal_value": body.deal_value})
    db.commit()
    return {"id": opp_id, "status": "created"}


@router.patch("/{opp_id}")
def update_sell_opportunity(opp_id: str, body: SellOpportunityUpdate, db=Depends(get_db), user=Depends(get_current_user)):
    if not db.execute("SELECT 1 FROM sell_opportunities WHERE id = ?", (opp_id,)).fetchone():
        raise HTTPException(status_code=404, detail="Sell opportunity not found")

    if body.status and body.status not in SELL_OPP_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {', '.join(SELL_OPP_STATUSES)}")

    updates = {}
    for field in ["seller_contact_id", "seller_group_id", "deal_value", "status", "owner", "notes", "decay_days"]:
        val = getattr(body, field)
        if val is not None:
            updates[field] = val

    if updates:
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values())
        db.execute(
            f"UPDATE sell_opportunities SET {set_clause}, updated_at = datetime('now') WHERE id = ?",
            values + [opp_id]
        )
        log_action(db, user, "sell_opportunity.update", "sell_opportunity", opp_id, updates)
        db.commit()

    return {"id": opp_id, "updated": list(updates.keys())}


@router.delete("/{opp_id}")
def delete_sell_opportunity(opp_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    opp = db.execute("SELECT property_id FROM sell_opportunities WHERE id = ?", (opp_id,)).fetchone()
    if not opp:
        raise HTTPException(status_code=404, detail="Sell opportunity not found")
    db.execute("DELETE FROM sell_opportunities WHERE id = ?", (opp_id,))
    log_action(db, user, "sell_opportunity.delete", "sell_opportunity", opp_id,
               {"property_id": opp["property_id"]})
    db.commit()
    return {"id": opp_id, "status": "deleted"}


def _find_matching_mandates(db, property_data: dict, limit: int = 20) -> list:
    """Find buy mandates whose criteria match this property."""
    mandates = db.execute(
        "SELECT bm.*, c.display_name AS contact_name, g.display_name AS group_name "
        "FROM buy_mandates bm "
        "LEFT JOIN contacts c ON bm.contact_id = c.id "
        "LEFT JOIN groups g ON bm.group_id = g.id "
        "WHERE bm.status = 'active'"
    ).fetchall()

    matches = []
    for m in mandates:
        m_dict = dict(m)
        criteria = json.loads(m_dict.get("criteria_json") or "{}")
        if not criteria:
            continue

        score = _score_match(criteria, property_data)
        if score > 0:
            m_dict["match_score"] = score
            matches.append(m_dict)

    matches.sort(key=lambda x: x["match_score"], reverse=True)
    return matches[:limit]


def _score_match(criteria: dict, property_data: dict) -> float:
    """Score how well a property matches buy mandate criteria. Returns 0 if no match."""
    score = 0.0
    checks = 0

    # Asset class match
    if criteria.get("asset_classes") and property_data.get("asset_class"):
        checks += 1
        if property_data["asset_class"] in criteria["asset_classes"]:
            score += 1.0
        else:
            return 0  # Hard filter — wrong asset class means no match

    # Region match
    if criteria.get("regions") and property_data.get("region"):
        checks += 1
        if property_data["region"] in criteria["regions"]:
            score += 1.0
        else:
            return 0  # Hard filter

    # City match (optional, bonus)
    if criteria.get("cities") and property_data.get("city"):
        checks += 1
        if property_data["city"] in criteria["cities"]:
            score += 1.0

    # Price range match
    price = property_data.get("most_recent_sale_price")
    if price and (criteria.get("price_min") or criteria.get("price_max")):
        checks += 1
        price_min = criteria.get("price_min", 0)
        price_max = criteria.get("price_max", float("inf"))
        if price_min <= price <= price_max:
            score += 1.0
        else:
            return 0  # Hard filter

    return score / max(checks, 1) if score > 0 else 0
