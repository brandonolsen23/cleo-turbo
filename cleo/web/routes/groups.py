"""
Groups API — browse, search, detail, promote, analytics, create.
"""

import json
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from typing import Optional
from ...web.deps import get_db, get_current_user, fts_query
from ...analytics.groups import refresh_group_analytics
from ...web.audit import log_action
from ...compiler.reconciler import normalize_group_name

router = APIRouter()


class HQAddressRequest(BaseModel):
    address: str


class CreateGroupRequest(BaseModel):
    display_name: str
    notes: Optional[str] = None


@router.get("/filters")
def group_filters(db=Depends(get_db), user=Depends(get_current_user)):
    """Available filter values for the Groups page."""
    asset_classes = db.execute(
        "SELECT DISTINCT asset_class FROM properties WHERE asset_class IS NOT NULL ORDER BY asset_class"
    ).fetchall()
    regions = db.execute(
        "SELECT DISTINCT region FROM properties WHERE region != '' ORDER BY region"
    ).fetchall()
    brands = db.execute(
        "SELECT DISTINCT brand FROM pois WHERE brand != '' ORDER BY brand"
    ).fetchall()
    return {
        "asset_classes": [r[0] for r in asset_classes],
        "regions": [r[0] for r in regions],
        "brands": [r[0] for r in brands],
    }


@router.get("")
def browse_groups(
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    status: str = None,
    min_properties: int = None,
    max_properties: int = None,
    # Analytics range filters
    min_portfolio_value: int = None,
    max_portfolio_value: int = None,
    min_radius_km: float = None,
    max_radius_km: float = None,
    min_max_distance_km: float = None,
    min_velocity: float = None,
    max_velocity: float = None,
    min_net_acquisitions: int = None,
    max_net_acquisitions: int = None,
    # Asset class filter — groups that own N..M properties of this class
    asset_class: str = None,
    min_asset_class_count: int = Query(None, ge=1),
    max_asset_class_count: int = Query(None, ge=1),
    # Brand filter — groups that own at least N properties with this brand
    brand: str = None,
    min_brand_count: int = Query(None, ge=1),
    # Region filter
    region: str = None,
    # Search
    q: str = None,
    # Sort
    sort: str = "transaction_count",
    order: str = "desc",
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Paginated group browse with rich filtering.

    All filters are AND-combined. Range filters accept min, max, or both.
    """
    # Always join analytics for rich data
    conditions = ["g.status != 'merged'"]
    params = []

    # Base group filters
    if status:
        conditions.append("g.status = ?")
        params.append(status)
    if min_properties is not None:
        conditions.append("g.property_count >= ?")
        params.append(min_properties)
    if max_properties is not None:
        conditions.append("g.property_count <= ?")
        params.append(max_properties)

    # Text search
    if q and q.strip():
        conditions.append("g.display_name LIKE ?")
        params.append(f"%{q.strip()}%")

    # Analytics range filters
    if min_portfolio_value is not None:
        conditions.append("ga.total_assessed_value >= ?")
        params.append(min_portfolio_value)
    if max_portfolio_value is not None:
        conditions.append("ga.total_assessed_value <= ?")
        params.append(max_portfolio_value)
    if min_radius_km is not None:
        conditions.append("ga.geographic_radius_km >= ?")
        params.append(min_radius_km)
    if max_radius_km is not None:
        conditions.append("ga.geographic_radius_km <= ?")
        params.append(max_radius_km)
    if min_max_distance_km is not None:
        conditions.append("ga.max_distance_from_hq_km >= ?")
        params.append(min_max_distance_km)
    if min_velocity is not None:
        conditions.append("ga.txns_per_year >= ?")
        params.append(min_velocity)
    if max_velocity is not None:
        conditions.append("ga.txns_per_year <= ?")
        params.append(max_velocity)
    if min_net_acquisitions is not None:
        conditions.append("ga.net_acquisitions >= ?")
        params.append(min_net_acquisitions)
    if max_net_acquisitions is not None:
        conditions.append("ga.net_acquisitions <= ?")
        params.append(max_net_acquisitions)

    # Asset class filter: groups that own N..M properties of asset_class X
    if asset_class:
        min_ac = min_asset_class_count or 1
        having = "HAVING COUNT(*) >= ?"
        ac_params = [asset_class, min_ac]
        if max_asset_class_count is not None:
            having += " AND COUNT(*) <= ?"
            ac_params.append(max_asset_class_count)
        conditions.append(
            f"g.id IN (SELECT current_owner_group_id FROM properties "
            f"WHERE asset_class = ? AND current_owner_group_id IS NOT NULL "
            f"GROUP BY current_owner_group_id {having})"
        )
        params.extend(ac_params)

    # Brand filter: groups that own >= N properties with brand X
    if brand:
        min_bc = min_brand_count or 1
        conditions.append(
            "g.id IN (SELECT p.current_owner_group_id FROM properties p "
            "JOIN pois poi ON poi.property_id = p.id "
            "WHERE poi.brand = ? AND p.current_owner_group_id IS NOT NULL "
            "GROUP BY p.current_owner_group_id HAVING COUNT(DISTINCT p.id) >= ?)"
        )
        params.extend([brand, min_bc])

    # Region filter: groups that own properties in this region
    if region:
        conditions.append(
            "g.id IN (SELECT current_owner_group_id FROM properties "
            "WHERE region = ? AND current_owner_group_id IS NOT NULL)"
        )
        params.append(region)

    where = " AND ".join(conditions)
    offset = (page - 1) * per_page

    # Sort validation
    analytics_sorts = {
        "total_buys", "total_sells", "avg_buy_price", "median_buy_price",
        "avg_sell_price", "net_acquisitions", "txns_per_year",
        "buys_last_12m", "sells_last_12m", "buys_last_36m", "sells_last_36m",
        "total_assessed_value", "region_count", "geographic_radius_km",
        "avg_distance_from_hq_km", "max_distance_from_hq_km",
    }
    base_sorts = {"transaction_count", "property_count", "contact_count", "display_name"}

    if sort not in base_sorts and sort not in analytics_sorts:
        sort = "transaction_count"
    if order not in ("asc", "desc"):
        order = "desc"

    sort_col = f"ga.{sort}" if sort in analytics_sorts else f"g.{sort}"

    total = db.execute(
        f"SELECT COUNT(*) FROM groups g LEFT JOIN group_analytics ga ON g.id = ga.group_id WHERE {where}",
        params
    ).fetchone()[0]

    rows = db.execute(
        f"SELECT g.id, g.display_name, g.status, g.property_count, g.transaction_count, "
        f"g.contact_count, "
        f"ga.total_assessed_value, ga.total_buys, ga.total_sells, ga.avg_buy_price, "
        f"ga.net_acquisitions, ga.txns_per_year, ga.buys_last_12m, ga.sells_last_12m, "
        f"ga.geographic_radius_km, ga.region_count, ga.max_distance_from_hq_km "
        f"FROM groups g LEFT JOIN group_analytics ga ON g.id = ga.group_id "
        f"WHERE {where} ORDER BY {sort_col} {order} NULLS LAST LIMIT ? OFFSET ?",
        params + [per_page, offset]
    ).fetchall()

    return {
        "results": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    }


@router.get("/search")
def search_groups(
    q: str = Query(..., min_length=1),
    limit: int = Query(25, ge=1, le=100),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    like_val = f"%{q.strip()}%"
    rows = db.execute(
        "SELECT g.id, g.display_name, g.status, g.property_count, g.transaction_count, g.contact_count "
        "FROM groups g "
        "WHERE g.display_name LIKE ? "
        "AND g.status != 'merged' "
        "LIMIT ?",
        (like_val, limit)
    ).fetchall()
    return {"results": [dict(r) for r in rows], "total": len(rows)}


@router.post("")
def create_group(req: CreateGroupRequest, db=Depends(get_db), user=Depends(get_current_user)):
    """Create a manually-defined group that persists across recompiles via group_overrides."""
    normalized = normalize_group_name(req.display_name)
    if not normalized:
        raise HTTPException(400, "Invalid group name")

    # Check if this normalized name already exists
    existing = db.execute(
        "SELECT id FROM groups WHERE normalized_name = ?", (normalized,)
    ).fetchone()
    if existing:
        raise HTTPException(409, f"Group already exists: {existing['id']}")

    # Allocate a stable ID through the counter
    counter_row = db.execute("SELECT value FROM app_meta WHERE key = 'next_grp_id'").fetchone()
    next_id = int(counter_row[0]) if counter_row else 1
    group_id = f"GRP_{next_id:05d}"
    db.execute(
        "INSERT OR REPLACE INTO app_meta (key, value, updated_at) VALUES ('next_grp_id', ?, datetime('now'))",
        (str(next_id + 1),)
    )

    # Write to id_mappings (permanent — survives recompiles)
    db.execute(
        "INSERT INTO id_mappings (entity_type, anchor_key, entity_id) VALUES ('group', ?, ?)",
        (normalized, group_id)
    )

    # Write to group_overrides (permanent — compiler injects these in Pass 1b)
    db.execute(
        "INSERT INTO group_overrides (group_id, display_name, normalized_name, created_by, notes) "
        "VALUES (?, ?, ?, ?, ?)",
        (group_id, req.display_name, normalized, user["username"], req.notes)
    )

    # Write to groups (derived — so it's usable immediately without recompile)
    db.execute(
        "INSERT INTO groups (id, display_name, normalized_name, status, property_count, transaction_count, contact_count) "
        "VALUES (?, ?, ?, 'pool', 0, 0, 0)",
        (group_id, req.display_name, normalized)
    )

    log_action(db, user, "group.create", "group", group_id, {
        "display_name": req.display_name, "manual": True
    })
    db.commit()

    return {"id": group_id, "display_name": req.display_name, "normalized_name": normalized}


@router.get("/{group_id}")
def group_detail(group_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    row = db.execute("SELECT * FROM groups WHERE id = ?", (group_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Group not found")

    result = dict(row)

    # Analytics
    analytics_row = db.execute(
        "SELECT * FROM group_analytics WHERE group_id = ?", (group_id,)
    ).fetchone()
    if analytics_row:
        analytics = dict(analytics_row)
        # Parse JSON fields
        for field in ("property_type_mix", "regions"):
            if analytics.get(field):
                try:
                    analytics[field] = json.loads(analytics[field])
                except (json.JSONDecodeError, TypeError):
                    pass
        result["analytics"] = analytics
    else:
        result["analytics"] = None

    # Known names
    names = db.execute(
        "SELECT name, normalized, source_id FROM group_names WHERE group_id = ?",
        (group_id,)
    ).fetchall()
    result["known_names"] = [dict(n) for n in names]

    # Associated contacts
    contacts = db.execute(
        "SELECT id, display_name, phone, job_title, status, transaction_count "
        "FROM contacts WHERE current_group_id = ? ORDER BY transaction_count DESC",
        (group_id,)
    ).fetchall()
    result["contacts"] = [dict(c) for c in contacts]

    # Transactions where this group appears
    txns = db.execute(
        "SELECT DISTINCT t.source_id, t.sale_date, t.sale_price, t.display_address, t.city, "
        "tp.side, tp.party_name "
        "FROM transaction_parties tp "
        "JOIN transactions t ON tp.source_id = t.source_id "
        "WHERE tp.group_id = ? ORDER BY t.sale_date DESC LIMIT 100",
        (group_id,)
    ).fetchall()
    result["transactions"] = [dict(t) for t in txns]

    # Properties owned (where group is buyer on most recent transaction)
    props = db.execute(
        "SELECT id, display_address, city, most_recent_sale_date, most_recent_sale_price, "
        "most_recent_sale_source, lat, lng, asset_class "
        "FROM properties WHERE current_owner_group_id = ? ORDER BY most_recent_sale_date DESC",
        (group_id,)
    ).fetchall()
    result["properties"] = [dict(p) for p in props]

    return result


@router.post("/{group_id}/promote")
def promote_group(group_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    row = db.execute("SELECT status FROM groups WHERE id = ?", (group_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Group not found")
    db.execute("UPDATE groups SET status = 'engaged', updated_at = datetime('now') WHERE id = ?", (group_id,))
    # Persist status override so it survives recompiles
    db.execute(
        "INSERT INTO group_field_overrides (group_id, status, updated_by) VALUES (?, 'engaged', ?) "
        "ON CONFLICT(group_id) DO UPDATE SET status = 'engaged', updated_by = ?, updated_at = datetime('now')",
        (group_id, user["username"], user["username"])
    )
    log_action(db, user, "group.promote", "group", group_id, {"from_status": row["status"]})
    db.commit()
    return {"id": group_id, "status": "engaged"}


@router.post("/{group_id}/hq-address")
def set_hq_address(group_id: str, body: HQAddressRequest, db=Depends(get_db), user=Depends(get_current_user)):
    """Set or update a group's HQ address. Stores the address and triggers analytics refresh."""
    row = db.execute("SELECT id FROM groups WHERE id = ?", (group_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Group not found")

    db.execute(
        "UPDATE groups SET hq_address = ?, updated_at = datetime('now') WHERE id = ?",
        (body.address, group_id)
    )
    # Persist HQ address override so it survives recompiles
    db.execute(
        "INSERT INTO group_field_overrides (group_id, hq_address, updated_by) VALUES (?, ?, ?) "
        "ON CONFLICT(group_id) DO UPDATE SET hq_address = ?, updated_by = ?, updated_at = datetime('now')",
        (group_id, body.address, user["username"], body.address, user["username"])
    )
    db.commit()

    # TODO: geocode address to lat/lng and store in group_analytics
    # For now, just refresh the non-geographic metrics
    refresh_group_analytics(db, group_ids=[group_id])

    return {"id": group_id, "hq_address": body.address}


@router.post("/{group_id}/refresh-analytics")
def refresh_single_group(group_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    """Refresh analytics for a single group."""
    row = db.execute("SELECT id FROM groups WHERE id = ?", (group_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Group not found")
    count = refresh_group_analytics(db, group_ids=[group_id])
    return {"refreshed": count, "group_id": group_id}


# ── Group-Contact Management ───────────────────────────────

class LinkContactRequest(BaseModel):
    contact_id: str
    role: Optional[str] = None
    notes: Optional[str] = None
    is_current: bool = True


class UpdateLinkRequest(BaseModel):
    is_current: Optional[bool] = None
    role: Optional[str] = None
    notes: Optional[str] = None


@router.get("/{group_id}/contacts")
def group_contacts(group_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    """All contacts linked to a group — both auto-derived (current_group_id) and manually linked."""
    row = db.execute("SELECT id FROM groups WHERE id = ?", (group_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Group not found")

    # Auto-derived contacts (from transaction data)
    derived = db.execute(
        "SELECT c.id, c.display_name, c.phone, c.email, c.job_title, c.status, "
        "c.transaction_count, c.contact_type "
        "FROM contacts c WHERE c.current_group_id = ? ORDER BY c.transaction_count DESC",
        (group_id,)
    ).fetchall()

    # Manually linked contacts (from group_contacts CRM table)
    manual = db.execute(
        "SELECT gc.contact_id, gc.is_current, gc.role, gc.notes, gc.linked_at, "
        "c.display_name, c.phone, c.email, c.job_title, c.status, c.transaction_count, c.contact_type "
        "FROM group_contacts gc "
        "JOIN contacts c ON gc.contact_id = c.id "
        "WHERE gc.group_id = ? ORDER BY gc.is_current DESC, gc.linked_at DESC",
        (group_id,)
    ).fetchall()

    derived_ids = {r["id"] for r in derived}
    manual_ids = {r["contact_id"] for r in manual}

    results = []
    # Add derived contacts first
    for c in derived:
        entry = dict(c)
        entry["link_type"] = "derived"
        entry["is_current"] = True
        entry["role"] = None
        entry["link_notes"] = None
        # Check if also manually linked (merge data)
        for m in manual:
            if m["contact_id"] == c["id"]:
                entry["role"] = m["role"]
                entry["link_notes"] = m["notes"]
                entry["is_current"] = bool(m["is_current"])
                entry["link_type"] = "both"
                break
        results.append(entry)

    # Add manually linked contacts that aren't in derived
    for m in manual:
        if m["contact_id"] not in derived_ids:
            results.append({
                "id": m["contact_id"],
                "display_name": m["display_name"],
                "phone": m["phone"],
                "email": m["email"],
                "job_title": m["job_title"],
                "status": m["status"],
                "transaction_count": m["transaction_count"],
                "contact_type": m["contact_type"],
                "link_type": "manual",
                "is_current": bool(m["is_current"]),
                "role": m["role"],
                "link_notes": m["notes"],
            })

    return {"contacts": results, "total": len(results)}


@router.post("/{group_id}/contacts")
def link_contact(group_id: str, body: LinkContactRequest, db=Depends(get_db), user=Depends(get_current_user)):
    """Manually link a contact to a group."""
    if not db.execute("SELECT 1 FROM groups WHERE id = ?", (group_id,)).fetchone():
        raise HTTPException(status_code=404, detail="Group not found")
    if not db.execute("SELECT 1 FROM contacts WHERE id = ?", (body.contact_id,)).fetchone():
        raise HTTPException(status_code=404, detail="Contact not found")

    existing = db.execute(
        "SELECT 1 FROM group_contacts WHERE group_id = ? AND contact_id = ?",
        (group_id, body.contact_id)
    ).fetchone()
    if existing:
        raise HTTPException(status_code=409, detail="Contact already linked to this group")

    db.execute(
        "INSERT INTO group_contacts (group_id, contact_id, is_current, role, notes) VALUES (?, ?, ?, ?, ?)",
        (group_id, body.contact_id, 1 if body.is_current else 0, body.role, body.notes)
    )
    log_action(db, user, "group.link_contact", "group", group_id, {"contact_id": body.contact_id, "role": body.role})
    db.commit()
    return {"status": "linked", "group_id": group_id, "contact_id": body.contact_id}


@router.patch("/{group_id}/contacts/{contact_id}")
def update_contact_link(group_id: str, contact_id: str, body: UpdateLinkRequest, db=Depends(get_db), user=Depends(get_current_user)):
    """Update a manual contact-group link (role, is_current, notes)."""
    existing = db.execute(
        "SELECT 1 FROM group_contacts WHERE group_id = ? AND contact_id = ?",
        (group_id, contact_id)
    ).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Link not found")

    updates = {}
    if body.is_current is not None:
        updates["is_current"] = 1 if body.is_current else 0
    if body.role is not None:
        updates["role"] = body.role
    if body.notes is not None:
        updates["notes"] = body.notes

    if updates:
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        db.execute(
            f"UPDATE group_contacts SET {set_clause} WHERE group_id = ? AND contact_id = ?",
            list(updates.values()) + [group_id, contact_id]
        )
        db.commit()

    return {"status": "updated", "updated": list(updates.keys())}


@router.delete("/{group_id}/contacts/{contact_id}")
def unlink_contact(group_id: str, contact_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    """Remove a manual contact-group link."""
    existing = db.execute(
        "SELECT 1 FROM group_contacts WHERE group_id = ? AND contact_id = ?",
        (group_id, contact_id)
    ).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Link not found")

    db.execute("DELETE FROM group_contacts WHERE group_id = ? AND contact_id = ?", (group_id, contact_id))
    log_action(db, user, "group.unlink_contact", "group", group_id, {"contact_id": contact_id})
    db.commit()
    return {"status": "unlinked"}
