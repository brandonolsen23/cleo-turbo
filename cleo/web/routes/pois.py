"""
POIs API -- browse, filter, and list branded points of interest.
"""

from fastapi import APIRouter, Depends, Query
from ...web.deps import get_db, get_current_user

router = APIRouter()


@router.get("")
def browse_pois(
    brand: str = None,
    category: str = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Paginated POI list with optional brand/category filters."""
    conditions = []
    params = []

    if brand:
        conditions.append("brand = ?")
        params.append(brand)
    if category:
        conditions.append("category = ?")
        params.append(category)

    where = " AND ".join(conditions) if conditions else "1=1"
    offset = (page - 1) * per_page

    total = db.execute(
        f"SELECT COUNT(*) FROM pois WHERE {where}", params
    ).fetchone()[0]

    rows = db.execute(
        f"SELECT id, source, brand, category, name, lat, lng, "
        f"address, city, phone, website, property_id, arn "
        f"FROM pois WHERE {where} ORDER BY brand, id LIMIT ? OFFSET ?",
        params + [per_page, offset]
    ).fetchall()

    return {
        "results": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if total > 0 else 0,
    }


@router.get("/brands")
def poi_brands(db=Depends(get_db), user=Depends(get_current_user)):
    """All brands with POI counts and categories."""
    rows = db.execute(
        "SELECT brand, category, COUNT(*) as count "
        "FROM pois GROUP BY brand, category ORDER BY count DESC"
    ).fetchall()
    return {
        "brands": [
            {"brand": r["brand"], "category": r["category"], "count": r["count"]}
            for r in rows
        ],
        "total_brands": len(rows),
    }


@router.get("/categories")
def poi_categories(db=Depends(get_db), user=Depends(get_current_user)):
    """All categories with POI counts."""
    rows = db.execute(
        "SELECT category, COUNT(*) as count "
        "FROM pois WHERE category != '' GROUP BY category ORDER BY count DESC"
    ).fetchall()
    return {
        "categories": [
            {"category": r["category"], "count": r["count"]}
            for r in rows
        ],
    }


@router.get("/tenant-map")
def poi_tenant_map(db=Depends(get_db), user=Depends(get_current_user)):
    """Property ID -> brand list lookup for table display."""
    rows = db.execute(
        "SELECT property_id, brand FROM pois WHERE property_id IS NOT NULL ORDER BY property_id, brand"
    ).fetchall()
    result = {}
    for r in rows:
        pid = r["property_id"]
        if pid not in result:
            result[pid] = []
        brand = r["brand"]
        if brand not in result[pid]:
            result[pid].append(brand)
    return result


@router.get("/stats")
def poi_stats(db=Depends(get_db), user=Depends(get_current_user)):
    """POI summary stats."""
    total = db.execute("SELECT COUNT(*) FROM pois").fetchone()[0]
    linked = db.execute("SELECT COUNT(*) FROM pois WHERE property_id IS NOT NULL").fetchone()[0]
    unlinked = total - linked

    return {
        "total_pois": total,
        "linked_to_property": linked,
        "unlinked": unlinked,
    }
