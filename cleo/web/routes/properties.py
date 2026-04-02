"""
Properties API — browse, search, detail, stats.
"""

import json
from fastapi import APIRouter, Depends, HTTPException, Query
from ...web.deps import get_db, get_current_user

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
    sort: str = "most_recent_sale_date",
    order: str = "desc",
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Paginated property browse with filters."""
    allowed_sorts = {
        "most_recent_sale_date", "most_recent_sale_price",
        "display_address", "city", "transaction_count",
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

    where = " AND ".join(conditions) if conditions else "1=1"
    offset = (page - 1) * per_page

    # Count
    count_row = db.execute(f"SELECT COUNT(*) FROM properties p WHERE {where}", params).fetchone()
    total = count_row[0]

    # Results
    rows = db.execute(
        f"SELECT p.id, p.arn, p.display_address, p.city, p.region, p.most_recent_sale_date, "
        f"p.most_recent_sale_price, p.current_owner_name, p.current_owner_group_id, "
        f"p.transaction_count, p.lat, p.lng "
        f"FROM properties p WHERE {where} ORDER BY p.{sort} {order} LIMIT ? OFFSET ?",
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
    """FTS5 full-text search on properties."""
    rows = db.execute(
        "SELECT p.id, p.arn, p.display_address, p.city, p.region, "
        "p.most_recent_sale_date, p.most_recent_sale_price, p.current_owner_name, p.transaction_count "
        "FROM properties p "
        "WHERE p.rowid IN (SELECT rowid FROM properties_fts WHERE properties_fts MATCH ?) "
        "LIMIT ?",
        (q, limit)
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

    # Recent records (RT transactions + GW assessments, by created_at)
    recent_rt = db.execute(
        "SELECT t.source_id, 'rt' as source, t.property_id, t.display_address, t.city, "
        "t.created_at as added_at, t.sale_price as value "
        "FROM transactions t ORDER BY t.created_at DESC LIMIT 10"
    ).fetchall()
    recent_gw = db.execute(
        "SELECT g.gw_id as source_id, 'gw' as source, g.property_id, "
        "COALESCE(p.display_address, '') as display_address, "
        "COALESCE(p.city, '') as city, "
        "g.created_at as added_at, g.assessed_value as value "
        "FROM gw_assessments g LEFT JOIN properties p ON g.property_id = p.id "
        "ORDER BY g.created_at DESC LIMIT 10"
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
    return {
        "cities": [r[0] for r in cities],
        "regions": [r[0] for r in regions],
        "brands": [r[0] for r in brands],
        "categories": [r[0] for r in categories],
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

    # Transaction history (include consideration, broker, photos for detail view)
    txns = db.execute(
        "SELECT source_id, sale_date, sale_price, display_address, transaction_note, "
        "seller_parties, buyer_parties, seller_phone, buyer_phone, "
        "consideration_json, broker_json, photos_json "
        "FROM transactions WHERE property_id = ? ORDER BY sale_date DESC",
        (property_id,)
    ).fetchall()
    result["transactions"] = []
    for t in txns:
        td = dict(t)
        td["seller_parties"] = json.loads(td.get("seller_parties") or "[]")
        td["buyer_parties"] = json.loads(td.get("buyer_parties") or "[]")
        td["consideration_json"] = json.loads(td.get("consideration_json") or "{}")
        td["broker_json"] = json.loads(td.get("broker_json") or "{}")
        td["photos_json"] = json.loads(td.get("photos_json") or "{}")

        # Contacts linked to this transaction via transaction_parties
        parties = db.execute(
            "SELECT tp.side, tp.party_name, tp.contact_title, tp.phone, "
            "tp.contact_id, tp.group_id, "
            "c.display_name as contact_name, c.phone as contact_phone, c.email as contact_email "
            "FROM transaction_parties tp "
            "LEFT JOIN contacts c ON tp.contact_id = c.id "
            "WHERE tp.source_id = ?",
            (td["source_id"],)
        ).fetchall()
        td["parties"] = [dict(p) for p in parties]

        result["transactions"].append(td)

    # POI tenants on this property
    pois = db.execute(
        "SELECT id, source, brand, category, name, lat, lng, address, city, phone, website "
        "FROM pois WHERE property_id = ? ORDER BY brand",
        (property_id,)
    ).fetchall()
    result["pois"] = [dict(p) for p in pois]

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

    return result
