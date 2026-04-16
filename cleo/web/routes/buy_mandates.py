"""
Buy Mandates API — a contact/group is looking to acquire properties matching criteria.
"""

import json
import uuid
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from typing import Optional
from ...web.deps import get_db, get_current_user
from ...web.audit import log_action

router = APIRouter()

BUY_MANDATE_STATUSES = ["active", "on_hold", "stale", "fulfilled"]


class BuyMandateCriteria(BaseModel):
    # Property type
    asset_classes: Optional[list[str]] = None
    asset_subclasses: Optional[list[str]] = None
    zoning_notes: Optional[str] = None

    # Tenant preferences
    tenant_quality: Optional[str] = None           # national_credit, regional_credit, local, any
    tenant_categories: Optional[list[str]] = None   # IDs from tenant_categories table
    occupancy_type: Optional[str] = None            # single, multi, either
    anchored_preference: Optional[str] = None       # grocery, big_box, none

    # Location
    regions: Optional[list[str]] = None
    cities: Optional[list[str]] = None
    market_tiers: Optional[list[str]] = None        # primary, secondary, tertiary

    # Financial
    price_min: Optional[int] = None
    price_max: Optional[int] = None
    cap_rate_min: Optional[float] = None
    cap_rate_max: Optional[float] = None
    noi_min: Optional[int] = None
    noi_max: Optional[int] = None

    # Size & physical
    sqft_min: Optional[int] = None
    sqft_max: Optional[int] = None
    acreage_min: Optional[float] = None
    acreage_max: Optional[float] = None
    unit_count_min: Optional[int] = None
    unit_count_max: Optional[int] = None

    # Investment profile
    investment_strategy: Optional[str] = None       # core, core_plus, value_add, opportunistic
    vacancy_tolerance: Optional[str] = None         # fully_leased, some_vacancy, high_vacancy

    # Timing & priority
    priority: Optional[str] = None                  # primary, secondary, exploratory
    timeline: Optional[str] = None                  # immediate, near_term, medium, long_term

    # Deprecated (kept for backward compat with old criteria JSON)
    market_type: Optional[str] = None
    max_distance_from_city_km: Optional[int] = None


class BuyMandateCreate(BaseModel):
    contact_id: Optional[str] = None
    group_id: Optional[str] = None
    criteria: BuyMandateCriteria
    owner: Optional[str] = None
    notes: Optional[str] = None
    decay_days: int = 14


class BuyMandateUpdate(BaseModel):
    contact_id: Optional[str] = None
    group_id: Optional[str] = None
    criteria: Optional[BuyMandateCriteria] = None
    status: Optional[str] = None
    owner: Optional[str] = None
    notes: Optional[str] = None
    decay_days: Optional[int] = None


@router.get("/filters")
def buy_mandate_filters(db=Depends(get_db), user=Depends(get_current_user)):
    """Available filter values for buy mandates."""
    owners = [r[0] for r in db.execute(
        "SELECT DISTINCT owner FROM buy_mandates WHERE owner IS NOT NULL ORDER BY owner"
    ).fetchall()]
    return {"owners": owners}


@router.get("")
def list_buy_mandates(
    status: str = None,
    owner: str = None,
    asset_class: str = None,
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
        conditions.append("bm.status = ?")
        params.append(status)
    if owner:
        conditions.append("bm.owner = ?")
        params.append(owner)
    if stale_only:
        conditions.append(
            "bm.status = 'active' AND "
            "julianday('now') - julianday(bm.last_activity_at) > bm.decay_days"
        )

    where = " AND ".join(conditions) if conditions else "1=1"

    sort_cols = {
        "created_at": "bm.created_at",
        "last_activity_at": "bm.last_activity_at",
        "status": "bm.status",
    }
    sort_col = sort_cols.get(sort, "bm.created_at")
    order_dir = "ASC" if order == "asc" else "DESC"

    offset = (page - 1) * per_page

    total = db.execute(
        f"SELECT COUNT(*) FROM buy_mandates bm WHERE {where}", params
    ).fetchone()[0]

    rows = db.execute(
        f"SELECT bm.*, "
        f"c.display_name AS contact_name, "
        f"g.display_name AS group_name, "
        f"CASE WHEN bm.status = 'active' AND julianday('now') - julianday(bm.last_activity_at) > bm.decay_days "
        f"  THEN 1 ELSE 0 END AS is_stale, "
        f"CAST(julianday('now') - julianday(bm.last_activity_at) AS INTEGER) AS days_since_activity "
        f"FROM buy_mandates bm "
        f"LEFT JOIN contacts c ON bm.contact_id = c.id "
        f"LEFT JOIN groups g ON bm.group_id = g.id "
        f"WHERE {where} ORDER BY {sort_col} {order_dir} LIMIT ? OFFSET ?",
        params + [per_page, offset]
    ).fetchall()

    results = []
    for r in rows:
        d = dict(r)
        # Parse criteria for display
        d["criteria"] = json.loads(d.get("criteria_json") or "{}")
        results.append(d)

    # Filter by asset_class in criteria (post-filter since it's in JSON)
    if asset_class:
        results = [r for r in results if asset_class in (r.get("criteria", {}).get("asset_classes") or [])]
        total = len(results)

    return {
        "results": results,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": max(1, (total + per_page - 1) // per_page),
    }


@router.get("/{mandate_id}")
def buy_mandate_detail(mandate_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    row = db.execute(
        "SELECT bm.*, "
        "c.display_name AS contact_name, c.phone AS contact_phone, c.email AS contact_email, "
        "g.display_name AS group_name, "
        "CASE WHEN bm.status = 'active' AND julianday('now') - julianday(bm.last_activity_at) > bm.decay_days "
        "  THEN 1 ELSE 0 END AS is_stale, "
        "CAST(julianday('now') - julianday(bm.last_activity_at) AS INTEGER) AS days_since_activity "
        "FROM buy_mandates bm "
        "LEFT JOIN contacts c ON bm.contact_id = c.id "
        "LEFT JOIN groups g ON bm.group_id = g.id "
        "WHERE bm.id = ?",
        (mandate_id,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Buy mandate not found")

    result = dict(row)
    result["criteria"] = json.loads(result.get("criteria_json") or "{}")

    # Get activities
    activities = db.execute(
        "SELECT * FROM activities WHERE entity_type = 'buy_mandate' AND entity_id = ? "
        "ORDER BY created_at DESC LIMIT 50",
        (mandate_id,)
    ).fetchall()
    result["activities"] = [dict(a) for a in activities]

    # Find matching properties
    matches = _find_matching_properties(db, result["criteria"])
    result["matching_properties"] = matches

    return result


@router.post("")
def create_buy_mandate(body: BuyMandateCreate, db=Depends(get_db), user=Depends(get_current_user)):
    if not body.contact_id and not body.group_id:
        raise HTTPException(status_code=400, detail="Must provide contact_id or group_id")

    mandate_id = f"BM_{uuid.uuid4().hex[:8].upper()}"
    criteria_json = json.dumps(body.criteria.model_dump(exclude_none=True))

    db.execute(
        "INSERT INTO buy_mandates (id, contact_id, group_id, criteria_json, "
        "owner, notes, decay_days) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (mandate_id, body.contact_id, body.group_id, criteria_json,
         body.owner, body.notes, body.decay_days)
    )
    log_action(db, user, "buy_mandate.create", "buy_mandate", mandate_id,
               {"contact_id": body.contact_id, "group_id": body.group_id,
                "criteria": body.criteria.model_dump(exclude_none=True)})
    db.commit()
    return {"id": mandate_id, "status": "created"}


@router.patch("/{mandate_id}")
def update_buy_mandate(mandate_id: str, body: BuyMandateUpdate, db=Depends(get_db), user=Depends(get_current_user)):
    if not db.execute("SELECT 1 FROM buy_mandates WHERE id = ?", (mandate_id,)).fetchone():
        raise HTTPException(status_code=404, detail="Buy mandate not found")

    if body.status and body.status not in BUY_MANDATE_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {', '.join(BUY_MANDATE_STATUSES)}")

    updates = {}
    for field in ["contact_id", "group_id", "status", "owner", "notes", "decay_days"]:
        val = getattr(body, field)
        if val is not None:
            updates[field] = val

    if body.criteria is not None:
        updates["criteria_json"] = json.dumps(body.criteria.model_dump(exclude_none=True))

    if updates:
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values())
        db.execute(
            f"UPDATE buy_mandates SET {set_clause}, updated_at = datetime('now') WHERE id = ?",
            values + [mandate_id]
        )
        log_action(db, user, "buy_mandate.update", "buy_mandate", mandate_id, updates)
        db.commit()

    return {"id": mandate_id, "updated": list(updates.keys())}


@router.delete("/{mandate_id}")
def delete_buy_mandate(mandate_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    mandate = db.execute("SELECT contact_id, group_id FROM buy_mandates WHERE id = ?", (mandate_id,)).fetchone()
    if not mandate:
        raise HTTPException(status_code=404, detail="Buy mandate not found")
    db.execute("DELETE FROM buy_mandates WHERE id = ?", (mandate_id,))
    log_action(db, user, "buy_mandate.delete", "buy_mandate", mandate_id,
               {"contact_id": mandate["contact_id"], "group_id": mandate["group_id"]})
    db.commit()
    return {"id": mandate_id, "status": "deleted"}


def _find_matching_properties(db, criteria: dict, limit: int = 50) -> list:
    """Find properties that match buy mandate criteria with match scoring."""
    if not criteria:
        return []

    conditions = []
    params = []
    joins = []

    # ── Hard filters (must match) ──
    if criteria.get("asset_classes"):
        placeholders = ",".join("?" * len(criteria["asset_classes"]))
        conditions.append(f"p.asset_class IN ({placeholders})")
        params.extend(criteria["asset_classes"])

    if criteria.get("asset_subclasses"):
        placeholders = ",".join("?" * len(criteria["asset_subclasses"]))
        conditions.append(f"p.asset_subclass IN ({placeholders})")
        params.extend(criteria["asset_subclasses"])

    if criteria.get("regions"):
        placeholders = ",".join("?" * len(criteria["regions"]))
        conditions.append(f"p.region IN ({placeholders})")
        params.extend(criteria["regions"])

    if criteria.get("cities"):
        placeholders = ",".join("?" * len(criteria["cities"]))
        conditions.append(f"LOWER(p.city) IN ({placeholders})")
        params.extend([c.lower() for c in criteria["cities"]])

    if criteria.get("price_min"):
        conditions.append("p.most_recent_sale_price >= ?")
        params.append(criteria["price_min"])

    if criteria.get("price_max"):
        conditions.append("p.most_recent_sale_price <= ?")
        params.append(criteria["price_max"])

    if criteria.get("sqft_min") or criteria.get("sqft_max"):
        joins.append("LEFT JOIN gw_assessments gw ON gw.property_id = p.id")
        if criteria.get("sqft_min"):
            conditions.append("gw.site_area_sqft >= ?")
            params.append(criteria["sqft_min"])
        if criteria.get("sqft_max"):
            conditions.append("gw.site_area_sqft <= ?")
            params.append(criteria["sqft_max"])

    if criteria.get("acreage_min"):
        conditions.append("p.acreage >= ?")
        params.append(criteria["acreage_min"])

    if criteria.get("acreage_max"):
        conditions.append("p.acreage <= ?")
        params.append(criteria["acreage_max"])

    # Need at least one filter to avoid returning everything
    if not conditions:
        return []

    where = " AND ".join(conditions)
    join_clause = " ".join(joins)

    rows = db.execute(
        f"SELECT p.id, p.display_address, p.city, p.region, p.asset_class, "
        f"p.asset_subclass, p.acreage, "
        f"p.most_recent_sale_price, p.most_recent_sale_date, p.lat, p.lng, "
        f"p.current_owner_name, p.current_owner_group_id, "
        f"so.id AS sell_opportunity_id, so.status AS sell_opportunity_status, "
        f"so.deal_value, so.noi AS sell_opp_noi, so.expected_cap_rate AS sell_opp_cap_rate, "
        f"pe.noi AS enrichment_noi, pe.unit_count, pe.vacancy_pct "
        f"FROM properties p "
        f"LEFT JOIN sell_opportunities so ON so.property_id = p.id AND so.status = 'active' "
        f"LEFT JOIN property_enrichment pe ON pe.property_id = p.id "
        f"{join_clause} "
        f"WHERE {where} AND p.lat IS NOT NULL "
        f"ORDER BY p.most_recent_sale_date DESC NULLS LAST "
        f"LIMIT ?",
        params + [limit]
    ).fetchall()

    results = []
    for r in rows:
        d = dict(r)
        # Use enrichment NOI first, fall back to sell opportunity NOI
        noi = d.get("enrichment_noi") or d.get("sell_opp_noi")
        d["noi"] = noi
        # Compute implied cap rate if we have NOI and a sale price
        price = d.get("most_recent_sale_price")
        if noi and price and price > 0:
            d["implied_cap_rate"] = round(noi / price * 100, 2)
        else:
            d["implied_cap_rate"] = None
        results.append(d)

    return results
