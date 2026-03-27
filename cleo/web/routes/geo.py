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
    Client-side clustering is handled by Mapbox GL.
    """
    rows = db.execute(
        "SELECT id, display_address, city, current_owner_name, "
        "most_recent_sale_price, most_recent_sale_date, transaction_count, "
        "lat, lng "
        "FROM properties "
        "WHERE lat IS NOT NULL AND lng IS NOT NULL"
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
                "address": r["display_address"],
                "city": r["city"],
                "owner": r["current_owner_name"],
                "latest_price": r["most_recent_sale_price"],
                "latest_date": r["most_recent_sale_date"],
                "transaction_count": r["transaction_count"],
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
        "lat, lng, parcel_geojson "
        "FROM properties "
        "WHERE lat BETWEEN ? AND ? "
        "AND lng BETWEEN ? AND ? "
        "AND parcel_geojson IS NOT NULL",
        (south, north, west, east)
    ).fetchall()

    features = []
    for r in rows:
        try:
            geom = json.loads(r["parcel_geojson"])
        except (json.JSONDecodeError, TypeError):
            continue

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
                "lat": r["lat"],
                "lng": r["lng"],
            },
        })

    return {
        "type": "FeatureCollection",
        "features": features,
        "total": len(features),
    }
