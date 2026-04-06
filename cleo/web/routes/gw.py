"""
GeoWarehouse API -- browse and view GW assessment data.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from ...web.deps import get_db, get_current_user

router = APIRouter()


@router.get("")
def browse_assessments(
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    zoning: str = None,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Paginated GW assessment browse."""
    conditions = []
    params = []

    if zoning:
        conditions.append("zoning = ?")
        params.append(zoning)

    where = " AND ".join(conditions) if conditions else "1=1"
    offset = (page - 1) * per_page

    total = db.execute(
        f"SELECT COUNT(*) FROM gw_assessments WHERE {where}", params
    ).fetchone()[0]

    rows = db.execute(
        f"SELECT id, gw_id, property_id, arn, pin, assessed_value, valuation_date, "
        f"zoning, property_code, property_description, ownership_type, "
        f"frontage_ft, depth_ft, site_area_sqft, acreage, owner_name, owner_mailing, "
        f"land_registry_status, registration_type, lro, municipality, "
        f"has_mpac_data, is_active, address_parsed, parcel_resolved, "
        f"legal_description "
        f"FROM gw_assessments WHERE {where} ORDER BY gw_id LIMIT ? OFFSET ?",
        params + [per_page, offset]
    ).fetchall()

    return {
        "results": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if total > 0 else 0,
    }


@router.get("/stats")
def gw_stats(db=Depends(get_db), user=Depends(get_current_user)):
    """GW assessment summary stats."""
    total = db.execute("SELECT COUNT(*) FROM gw_assessments").fetchone()[0]
    linked = db.execute("SELECT COUNT(*) FROM gw_assessments WHERE property_id IS NOT NULL").fetchone()[0]
    avg_value = db.execute("SELECT AVG(assessed_value) FROM gw_assessments WHERE assessed_value > 0").fetchone()[0]

    return {
        "total_assessments": total,
        "linked_to_property": linked,
        "avg_assessed_value": int(avg_value) if avg_value else 0,
    }


@router.get("/zoning")
def gw_zoning(db=Depends(get_db), user=Depends(get_current_user)):
    """All zoning codes with counts."""
    rows = db.execute(
        "SELECT zoning, COUNT(*) as count FROM gw_assessments "
        "WHERE zoning != '' GROUP BY zoning ORDER BY count DESC"
    ).fetchall()
    return {"zones": [{"zoning": r["zoning"], "count": r["count"]} for r in rows]}


@router.get("/{gw_id}")
def gw_detail(gw_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    """Single GW assessment detail with sales history."""
    row = db.execute("SELECT * FROM gw_assessments WHERE id = ?", (gw_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="GW assessment not found")

    result = dict(row)

    # Get sales history for this GW record
    sales = db.execute(
        "SELECT sale_date, amount, sale_type, party_to, notes FROM gw_sales_history "
        "WHERE gw_id = ? ORDER BY sale_date DESC",
        (result["gw_id"],)
    ).fetchall()
    result["sales_history"] = [dict(s) for s in sales]

    return result
