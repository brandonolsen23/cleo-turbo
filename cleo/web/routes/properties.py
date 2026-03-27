"""
Properties API — browse, search, detail, stats.
"""

import json
from fastapi import APIRouter, Depends, Query
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
        conditions.append("city = ?")
        params.append(city)
    if region:
        conditions.append("region = ?")
        params.append(region)
    if min_price is not None:
        conditions.append("most_recent_sale_price >= ?")
        params.append(min_price)
    if max_price is not None:
        conditions.append("most_recent_sale_price <= ?")
        params.append(max_price)

    where = " AND ".join(conditions) if conditions else "1=1"
    offset = (page - 1) * per_page

    # Count
    count_row = db.execute(f"SELECT COUNT(*) FROM properties WHERE {where}", params).fetchone()
    total = count_row[0]

    # Results
    rows = db.execute(
        f"SELECT id, arn, display_address, city, region, most_recent_sale_date, "
        f"most_recent_sale_price, current_owner_name, transaction_count, lat, lng "
        f"FROM properties WHERE {where} ORDER BY {sort} {order} LIMIT ? OFFSET ?",
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

    # Recent transactions
    recent = db.execute(
        "SELECT source_id, display_address, city, sale_date, sale_price "
        "FROM transactions WHERE sale_date IS NOT NULL ORDER BY sale_date DESC LIMIT 10"
    ).fetchall()
    stats["recent_transactions"] = [dict(r) for r in recent]

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
    return {
        "cities": [r[0] for r in cities],
        "regions": [r[0] for r in regions],
    }


@router.get("/{property_id}")
def property_detail(property_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    """Full property detail with transaction history."""
    prop = db.execute("SELECT * FROM properties WHERE id = ?", (property_id,)).fetchone()
    if not prop:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Property not found")

    result = dict(prop)

    # Parse parcel GeoJSON
    if result.get("parcel_geojson"):
        result["parcel_geojson"] = json.loads(result["parcel_geojson"])

    # Transaction history
    txns = db.execute(
        "SELECT source_id, sale_date, sale_price, display_address, transaction_note, "
        "seller_parties, buyer_parties, seller_phone, buyer_phone "
        "FROM transactions WHERE property_id = ? ORDER BY sale_date DESC",
        (property_id,)
    ).fetchall()
    result["transactions"] = []
    for t in txns:
        td = dict(t)
        td["seller_parties"] = json.loads(td.get("seller_parties") or "[]")
        td["buyer_parties"] = json.loads(td.get("buyer_parties") or "[]")
        result["transactions"].append(td)

    return result
