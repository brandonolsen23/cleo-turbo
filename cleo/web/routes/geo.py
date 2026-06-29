"""
Geo API — GeoJSON endpoints for map rendering.
"""

import json
from fastapi import APIRouter, Depends, Query
from ...web.deps import get_db, get_current_user

router = APIRouter()


@router.get("/properties")
def geo_properties(db=Depends(get_db), user=Depends(get_current_user)):
    """
    All properties with coordinates as a GeoJSON FeatureCollection.
    Includes tenant brand/category arrays from POIs for map filtering.
    Client-side clustering is handled by Mapbox GL.
    """
    rows = db.execute(
        "SELECT id, display_address, city, current_owner_name, "
        "most_recent_sale_price, most_recent_sale_date, transaction_count, "
        "primary_property_type, lat, lng, "
        "building_size_raw, building_size_value, building_size_unit, "
        "ROUND((julianday('now') - julianday(most_recent_sale_date)) / 365.25, 1) AS ownership_years "
        "FROM properties "
        "WHERE lat IS NOT NULL AND lng IS NOT NULL"
    ).fetchall()

    # Build tenant brand/category lookup: property_id -> {brands, categories}
    poi_rows = db.execute(
        "SELECT property_id, brand, category FROM pois WHERE property_id IS NOT NULL"
    ).fetchall()
    tenant_map = {}
    for pr in poi_rows:
        pid = pr["property_id"]
        if pid not in tenant_map:
            tenant_map[pid] = {"brands": set(), "categories": set()}
        tenant_map[pid]["brands"].add(pr["brand"])
        if pr["category"]:
            tenant_map[pid]["categories"].add(pr["category"])

    features = []
    for r in rows:
        tenants = tenant_map.get(r["id"])
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [r["lng"], r["lat"]],
            },
            "properties": {
                "id": r["id"],
                "address": r["display_address"],
                "city": r["city"],
                "owner": r["current_owner_name"],
                "latest_price": r["most_recent_sale_price"],
                "latest_date": r["most_recent_sale_date"],
                "transaction_count": r["transaction_count"],
                "ownership_years": r["ownership_years"],
                "primary_property_type": r["primary_property_type"] or "",
                "tenant_brands": sorted(tenants["brands"]) if tenants else [],
                "tenant_categories": sorted(tenants["categories"]) if tenants else [],
                "building_size_raw": r["building_size_raw"],
                "building_size_sf": r["building_size_value"] if r["building_size_unit"] == "sf" else None,
            },
        })

    return {
        "type": "FeatureCollection",
        "features": features,
        "total": len(features),
    }


@router.get("/pois")
def geo_pois(
    category: str = None,
    brand: str = None,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """
    All POIs as a GeoJSON FeatureCollection of Points.
    Separate map layer from properties, with optional category/brand filter.
    """
    conditions = ["lat IS NOT NULL AND lng IS NOT NULL"]
    params = []

    if category:
        conditions.append("category = ?")
        params.append(category)
    if brand:
        conditions.append("brand = ?")
        params.append(brand)

    where = " AND ".join(conditions)

    rows = db.execute(
        f"SELECT id, brand, category, name, lat, lng, address, city, property_id "
        f"FROM pois WHERE {where}",
        params,
    ).fetchall()

    features = []
    for r in rows:
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [r["lng"], r["lat"]],
            },
            "properties": {
                "id": r["id"],
                "brand": r["brand"],
                "category": r["category"] or "",
                "name": r["name"],
                "address": r["address"],
                "city": r["city"],
                "property_id": r["property_id"],
            },
        })

    return {
        "type": "FeatureCollection",
        "features": features,
        "total": len(features),
    }


@router.get("/parcels")
def geo_parcels(
    south: float = Query(...),
    west: float = Query(...),
    north: float = Query(...),
    east: float = Query(...),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """
    Parcel polygons within a bounding box, returned as a GeoJSON
    FeatureCollection. Called on-demand when the map zooms to
    detail level (zoom >= 14).
    """
    rows = db.execute(
        "SELECT id, display_address, city, current_owner_name, "
        "most_recent_sale_price, most_recent_sale_date, transaction_count, "
        "primary_property_type, lat, lng, parcel_geojson "
        "FROM properties "
        "WHERE lat BETWEEN ? AND ? "
        "AND lng BETWEEN ? AND ? "
        "AND parcel_geojson IS NOT NULL",
        (south, north, west, east)
    ).fetchall()

    # Build tenant brand lookup for parcels in this bbox
    property_ids = [r["id"] for r in rows]
    tenant_map = {}
    if property_ids:
        placeholders = ",".join("?" for _ in property_ids)
        poi_rows = db.execute(
            f"SELECT property_id, brand FROM pois "
            f"WHERE property_id IN ({placeholders})",
            property_ids,
        ).fetchall()
        for pr in poi_rows:
            pid = pr["property_id"]
            if pid not in tenant_map:
                tenant_map[pid] = set()
            tenant_map[pid].add(pr["brand"])

    features = []
    for r in rows:
        try:
            geom = json.loads(r["parcel_geojson"])
        except (json.JSONDecodeError, TypeError):
            continue

        tenants = tenant_map.get(r["id"])
        features.append({
            "type": "Feature",
            "geometry": geom,
            "properties": {
                "id": r["id"],
                "address": r["display_address"],
                "city": r["city"],
                "owner": r["current_owner_name"],
                "latest_price": r["most_recent_sale_price"],
                "latest_date": r["most_recent_sale_date"],
                "transaction_count": r["transaction_count"],
                "primary_property_type": r["primary_property_type"] or "",
                "lat": r["lat"],
                "lng": r["lng"],
                "tenant_brands": sorted(tenants) if tenants else [],
            },
        })

    return {
        "type": "FeatureCollection",
        "features": features,
        "total": len(features),
    }
