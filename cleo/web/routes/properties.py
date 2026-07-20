"""
Properties API — browse, search, detail, stats.
"""

import json
from fastapi import APIRouter, Depends, HTTPException, Query
from ...web.deps import get_db, get_current_user, fts_query
from ._attribution import attribution_for

router = APIRouter()


@router.get("")
def browse_properties(
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    city: str = None,
    region: str = None,
    min_price: int = None,
    max_price: int = None,
    brand: str = None,
    category: str = None,
    asset_class: str = None,
    min_ownership_years: float = None,
    max_ownership_years: float = None,
    building_size_min: float = None,
    building_size_max: float = None,
    q: str = None,
    sort: str = "most_recent_sale_date",
    order: str = "desc",
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Paginated property browse with filters."""
    allowed_sorts = {
        "most_recent_sale_date", "most_recent_sale_price",
        "display_address", "city", "transaction_count", "ownership_years",
    }
    if sort not in allowed_sorts:
        sort = "most_recent_sale_date"
    if order not in ("asc", "desc"):
        order = "desc"

    conditions = []
    params = []

    if city:
        conditions.append("p.city = ?")
        params.append(city)
    if region:
        conditions.append("p.region = ?")
        params.append(region)
    if min_price is not None:
        conditions.append("p.most_recent_sale_price >= ?")
        params.append(min_price)
    if max_price is not None:
        conditions.append("p.most_recent_sale_price <= ?")
        params.append(max_price)
    if brand:
        conditions.append("p.id IN (SELECT property_id FROM pois WHERE brand = ?)")
        params.append(brand)
    if category:
        conditions.append("p.id IN (SELECT property_id FROM pois WHERE category = ?)")
        params.append(category)
    if asset_class:
        conditions.append("p.asset_class = ?")
        params.append(asset_class)
    if min_ownership_years is not None:
        conditions.append("p.most_recent_sale_date IS NOT NULL AND (julianday('now') - julianday(p.most_recent_sale_date)) / 365.25 >= ?")
        params.append(min_ownership_years)
    if max_ownership_years is not None:
        conditions.append("p.most_recent_sale_date IS NOT NULL AND (julianday('now') - julianday(p.most_recent_sale_date)) / 365.25 <= ?")
        params.append(max_ownership_years)
    if building_size_min is not None or building_size_max is not None:
        conditions.append("p.building_size_unit = 'sf'")
        if building_size_min is not None:
            conditions.append("p.building_size_value >= ?")
            params.append(building_size_min)
        if building_size_max is not None:
            conditions.append("p.building_size_value <= ?")
            params.append(building_size_max)
    if q and q.strip():
        conditions.append(
            "(p.display_address LIKE ? OR p.city LIKE ? OR p.current_owner_name LIKE ?)"
        )
        like_val = f"%{q.strip()}%"
        params.extend([like_val, like_val, like_val])

    where = " AND ".join(conditions) if conditions else "1=1"
    offset = (page - 1) * per_page

    # Count
    count_row = db.execute(f"SELECT COUNT(*) FROM properties p WHERE {where}", params).fetchone()
    total = count_row[0]

    # Results
    ownership_expr = "ROUND((julianday('now') - julianday(p.most_recent_sale_date)) / 365.25, 1)"
    sort_col = ownership_expr if sort == "ownership_years" else f"p.{sort}"
    rows = db.execute(
        f"SELECT p.id, p.arn, p.display_address, p.city, p.region, p.most_recent_sale_date, "
        f"p.most_recent_sale_price, p.current_owner_name, p.current_owner_group_id, "
        f"p.transaction_count, p.lat, p.lng, p.asset_class, p.asset_subclass, "
        f"p.building_size_raw, p.building_size_value, p.building_size_unit, "
        f"{ownership_expr} AS ownership_years "
        f"FROM properties p WHERE {where} ORDER BY {sort_col} {order} LIMIT ? OFFSET ?",
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
def search_properties(
    q: str = Query(..., min_length=1),
    limit: int = Query(25, ge=1, le=100),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Full-text search on properties."""
    like_val = f"%{q.strip()}%"
    rows = db.execute(
        "SELECT p.id, p.arn, p.display_address, p.city, p.region, "
        "p.most_recent_sale_date, p.most_recent_sale_price, p.current_owner_name, p.transaction_count "
        "FROM properties p "
        "WHERE p.display_address LIKE ? OR p.city LIKE ? OR p.current_owner_name LIKE ? "
        "LIMIT ?",
        (like_val, like_val, like_val, limit)
    ).fetchall()
    return {"results": [dict(r) for r in rows], "total": len(rows)}


@router.get("/stats")
def property_stats(db=Depends(get_db), user=Depends(get_current_user)):
    """Aggregate stats for dashboard."""
    stats = {}
    stats["total_properties"] = db.execute("SELECT COUNT(*) FROM properties").fetchone()[0]
    stats["total_transactions"] = db.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    stats["total_contacts"] = db.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
    stats["total_groups"] = db.execute("SELECT COUNT(*) FROM groups").fetchone()[0]
    stats["engaged_contacts"] = db.execute("SELECT COUNT(*) FROM contacts WHERE status='engaged'").fetchone()[0]
    stats["engaged_groups"] = db.execute("SELECT COUNT(*) FROM groups WHERE status='engaged'").fetchone()[0]

    # Top cities by property count
    cities = db.execute(
        "SELECT city, COUNT(*) as count FROM properties WHERE city != '' "
        "GROUP BY city ORDER BY count DESC LIMIT 20"
    ).fetchall()
    stats["top_cities"] = [{"city": r[0], "count": r[1]} for r in cities]

    # Recent records (RT transactions + GW assessments, by obtained-date).
    # "Added" = when the source data was obtained (GW download date / RT scrape
    # date), derived deterministically from source_file/source_folder so it is
    # stable across rebuilds. We sort by that obtained-date and only include rows
    # that have one: historical bulk-imported RT rows carry no dated source path
    # (source_date IS NULL) and were not "recently added," so they are excluded
    # rather than floating to the top on created_at (the rebuild time), which
    # would re-introduce the churn this fixes. See docs/incremental-recompile-plan.md.
    recent_rt = db.execute(
        "SELECT t.source_id, 'rt' as source, t.property_id, t.display_address, t.city, "
        "t.source_date as added_at, t.sale_price as value "
        "FROM transactions t WHERE t.source_date IS NOT NULL "
        "ORDER BY t.source_date DESC LIMIT 10"
    ).fetchall()
    recent_gw = db.execute(
        "SELECT g.gw_id as source_id, 'gw' as source, g.property_id, "
        "COALESCE(p.display_address, '') as display_address, "
        "COALESCE(p.city, '') as city, "
        "g.source_date as added_at, g.assessed_value as value "
        "FROM gw_assessments g LEFT JOIN properties p ON g.property_id = p.id "
        "WHERE g.source_date IS NOT NULL "
        "ORDER BY g.source_date DESC LIMIT 10"
    ).fetchall()
    combined = sorted(
        [dict(r) for r in recent_rt] + [dict(r) for r in recent_gw],
        key=lambda r: r.get('added_at') or '', reverse=True
    )[:10]
    stats["recent_records"] = combined

    return stats


@router.get("/filters")
def property_filters(db=Depends(get_db), user=Depends(get_current_user)):
    """Available filter values."""
    cities = db.execute(
        "SELECT DISTINCT city FROM properties WHERE city != '' ORDER BY city"
    ).fetchall()
    regions = db.execute(
        "SELECT DISTINCT region FROM properties WHERE region != '' ORDER BY region"
    ).fetchall()
    brands = db.execute(
        "SELECT DISTINCT brand FROM pois WHERE brand != '' ORDER BY brand"
    ).fetchall()
    categories = db.execute(
        "SELECT DISTINCT category FROM pois WHERE category != '' ORDER BY category"
    ).fetchall()
    asset_classes = db.execute(
        "SELECT DISTINCT asset_class FROM properties WHERE asset_class IS NOT NULL ORDER BY asset_class"
    ).fetchall()
    return {
        "cities": [r[0] for r in cities],
        "regions": [r[0] for r in regions],
        "brands": [r[0] for r in brands],
        "categories": [r[0] for r in categories],
        "asset_classes": [r[0] for r in asset_classes],
    }


@router.get("/{property_id}/popup")
def property_popup(property_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    """Lightweight popup data for map — property info + first photo + tenants."""
    prop = db.execute(
        "SELECT id, display_address, city, current_owner_name, "
        "most_recent_sale_price, most_recent_sale_date, transaction_count, "
        "primary_property_type, acreage "
        "FROM properties WHERE id = ?", (property_id,)
    ).fetchone()
    if not prop:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Property not found")

    result = dict(prop)

    # First photo from most recent transaction
    photo_row = db.execute(
        "SELECT photos_json FROM transactions WHERE property_id = ? "
        "AND photos_json LIKE '%cachefly%' ORDER BY sale_date DESC LIMIT 1",
        (property_id,)
    ).fetchone()
    if photo_row:
        photos = json.loads(photo_row["photos_json"])
        street_photos = photos.get("street_photo_urls", [])
        result["photo_url"] = street_photos[0] if street_photos else None
        result["photo_count"] = len(street_photos)
    else:
        result["photo_url"] = None
        result["photo_count"] = 0

    # Tenant brands
    tenants = db.execute(
        "SELECT brand, category FROM pois WHERE property_id = ? ORDER BY brand",
        (property_id,)
    ).fetchall()
    result["tenants"] = [{"brand": t["brand"], "category": t["category"]} for t in tenants]

    # GW assessment (zoning, assessed value)
    gw = db.execute(
        "SELECT assessed_value, zoning, property_description FROM gw_assessments "
        "WHERE property_id = ? LIMIT 1", (property_id,)
    ).fetchone()
    if gw:
        result["assessed_value"] = gw["assessed_value"]
        result["zoning"] = gw["zoning"]
        result["property_description"] = gw["property_description"]

    return result


@router.get("/{property_id}")
def property_detail(property_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    """Full property detail with transaction history."""
    prop = db.execute("SELECT * FROM properties WHERE id = ?", (property_id,)).fetchone()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    result = dict(prop)

    # Parse parcel GeoJSON
    if result.get("parcel_geojson"):
        result["parcel_geojson"] = json.loads(result["parcel_geojson"])

    # Transaction history
    txns = db.execute(
        "SELECT source_id, sale_date, sale_price, display_address, transaction_note, "
        "seller_parties, buyer_parties, seller_phone, buyer_phone, "
        "cash, debt, chattels, other_consideration, charges_json, "
        "building_size_raw, building_size_value, building_size_unit, "
        "photos_json "
        "FROM transactions WHERE property_id = ? ORDER BY sale_date DESC",
        (property_id,)
    ).fetchall()
    result["transactions"] = []
    for t in txns:
        td = dict(t)
        td["seller_parties"] = json.loads(td.get("seller_parties") or "[]")
        td["buyer_parties"] = json.loads(td.get("buyer_parties") or "[]")
        td["photos_json"] = json.loads(td.get("photos_json") or "{}")
        td["charges_json"] = json.loads(td.get("charges_json") or "[]")

        # Contacts linked to this transaction via transaction_parties
        parties = db.execute(
            "SELECT tp.side, tp.party_name, tp.contact_title, tp.phone, "
            "tp.contact_id, tp.group_id, "
            "c.display_name as contact_name, c.phone as contact_phone, c.email as contact_email, "
            "c.status, c.last_engaged_date "
            "FROM transaction_parties tp "
            "LEFT JOIN contacts c ON tp.contact_id = c.id "
            "WHERE tp.source_id = ?",
            (td["source_id"],)
        ).fetchall()
        td["parties"] = [dict(p) for p in parties]

        # Mailing addresses per side
        addrs = db.execute(
            "SELECT side, display, city, province, postal "
            "FROM transaction_mailing_addresses WHERE source_id = ?",
            (td["source_id"],)
        ).fetchall()
        for a in addrs:
            ad = dict(a)
            td[f"{ad['side']}_mailing_address"] = ad

        result["transactions"].append(td)

    # POI tenants on this property
    pois = db.execute(
        "SELECT id, source, brand, category, name, lat, lng, address, city, phone, website, "
        "address_source "
        "FROM pois WHERE property_id = ? ORDER BY brand",
        (property_id,)
    ).fetchall()
    result["pois"] = [dict(p) for p in pois]

    # If properties.display_address is empty, fall back to the first POI
    # on the parcel that has an address (often reverse-geocoded). The
    # address_source on the POI tells the UI whether it's authoritative.
    if not (result.get("display_address") or "").strip():
        for p in result["pois"]:
            if (p.get("address") or "").strip():
                result["display_address"] = p["address"]
                result["display_address_source"] = p.get("address_source") or "poi"
                break

    # GW assessments (with sales history)
    gw = db.execute(
        "SELECT * FROM gw_assessments WHERE property_id = ? ORDER BY gw_id",
        (property_id,)
    ).fetchall()
    gw_list = []
    for g in gw:
        gd = dict(g)
        sales = db.execute(
            "SELECT sale_date, amount, sale_type, party_to, notes FROM gw_sales_history "
            "WHERE gw_id = ? ORDER BY sale_date DESC",
            (gd["gw_id"],)
        ).fetchall()
        gd["sales_history"] = [dict(s) for s in sales]
        gw_list.append(gd)
    result["gw_assessments"] = gw_list

    # GW sales history (all sales for this property, for convenience)
    all_sales = db.execute(
        "SELECT sale_date, amount, sale_type, party_to, notes FROM gw_sales_history "
        "WHERE property_id = ? ORDER BY sale_date DESC",
        (property_id,)
    ).fetchall()
    result["gw_sales_history"] = [dict(s) for s in all_sales]

    # Owner group HQ info (address + geocoded coords for map)
    if result.get("current_owner_group_id"):
        grp = db.execute(
            "SELECT g.hq_address, ga.hq_lat, ga.hq_lng "
            "FROM groups g "
            "LEFT JOIN group_analytics ga ON ga.group_id = g.id "
            "WHERE g.id = ?",
            (result["current_owner_group_id"],)
        ).fetchone()
        if grp:
            result["owner_hq_address"] = grp["hq_address"]
            result["owner_hq_lat"] = grp["hq_lat"]
            result["owner_hq_lng"] = grp["hq_lng"]

    # Fallback: buyer mailing address from most recent transaction
    if not result.get("owner_hq_address") and result.get("transactions"):
        latest_src = result["transactions"][0]["source_id"]
        ma = db.execute(
            "SELECT display, city, province, postal, geocode_string "
            "FROM transaction_mailing_addresses "
            "WHERE source_id = ? AND side = 'buyer'",
            (latest_src,)
        ).fetchone()
        if ma:
            result["owner_hq_address"] = ma["geocode_string"] or ma["display"]

    # Final fallback: GW assessment owner_mailing — the assessment-roll
    # mailing address is often the only owner-address signal for GW-only
    # parcels (no transactions, no group link).
    if not result.get("owner_hq_address") and result.get("gw_assessments"):
        for g in result["gw_assessments"]:
            m = (g.get("owner_mailing") or "").strip()
            if m and m.upper() != "N/A":
                result["owner_hq_address"] = m
                break

    return result


@router.get("/{property_id}/attribution")
def property_attribution(property_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    return attribution_for(db, "property_id", property_id)
