"""
AgMaps API client — queries Ontario's provincial parcel service.

Supports two query types:
  - By ARN (20-digit Assessment Roll Number) → 0 or 1 result
  - By spatial point (lat/lng bounding box) → 0 or more results

PIN is NOT a queryable field on this service. The Assessment Parcel layer
(MapServer/0) only exposes: OGF_ID, ASSESSMENT_ROLL_NUMBER, and date fields.
Records with PIN-only must be resolved via spatial queries.

All queries return GeoJSON-formatted parcel data or None.
"""

import json
import time
import requests


BASE_URL = (
    "https://ws.lioservices.lrc.gov.on.ca/arcgis4/rest/services"
    "/AIA/Assessment_Parcel_Map/MapServer/0"
)

THROTTLE_SECONDS = 0.4
USER_AGENT = "Cleo/1.0 parcel-resolver"


class TokenExpiredError(Exception):
    """Raised when the AgMaps token is expired or invalid."""
    pass


def _point_in_polygon(x, y, polygon):
    """Ray-casting point-in-polygon test.

    Args:
        x, y: point coordinates (lng, lat)
        polygon: list of [x, y] coordinate pairs forming a closed ring

    Returns:
        True if point is inside the polygon.
    """
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


class AgMapsClient:
    """Client for the Ontario AgMaps Assessment Parcel Map service."""

    def __init__(self, token):
        self.token = token
        self._last_request_time = 0
        self._session = requests.Session()
        self._session.headers["User-Agent"] = USER_AGENT

    def close(self):
        self._session.close()

    def _throttle(self):
        """Enforce minimum delay between API requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < THROTTLE_SECONDS:
            time.sleep(THROTTLE_SECONDS - elapsed)
        self._last_request_time = time.time()

    def _query(self, params):
        """Execute a query against the parcel service. Returns parsed JSON."""
        self._throttle()
        params["token"] = self.token
        params["f"] = "json"

        url = f"{BASE_URL}/query"
        resp = self._session.get(url, params=params, timeout=30)

        # Token expiry: HTTP 498 or error in response body
        if resp.status_code == 498:
            raise TokenExpiredError("HTTP 498 — token expired")

        data = resp.json()

        if "error" in data:
            msg = data["error"].get("message", "")
            if "token" in msg.lower() or "invalid" in msg.lower():
                raise TokenExpiredError(f"API error: {msg}")
            # Other errors — log and return empty
            return {"features": []}

        return data

    def _feature_to_parcel(self, feature):
        """Convert an ArcGIS feature to our parcel cache format."""
        attrs = feature.get("attributes", {})
        geometry = feature.get("geometry", {})

        arn = attrs.get("ASSESSMENT_ROLL_NUMBER", "")
        pin = attrs.get("PIN", "")

        # Convert ArcGIS rings to GeoJSON Polygon
        rings = geometry.get("rings", [])
        geojson = {"type": "Polygon", "coordinates": rings} if rings else None

        # Compute centroid from first ring (simple average)
        centroid = None
        if rings and rings[0]:
            lngs = [pt[0] for pt in rings[0]]
            lats = [pt[1] for pt in rings[0]]
            centroid = [sum(lats) / len(lats), sum(lngs) / len(lngs)]

        # Filter out ArcGIS-internal fields from attributes
        filtered_attrs = {
            k: v for k, v in attrs.items()
            if k not in (
                "ASSESSMENT_ROLL_NUMBER", "PIN",
                "Shape", "Shape.STArea()", "Shape.STLength()",
            )
        }

        return {
            "arn": str(arn),
            "geometry": geojson,
            "centroid": centroid,
            "attributes": filtered_attrs,
        }

    def query_by_arn(self, arn):
        """Query parcel by 20-digit ARN. Returns parcel dict or None."""
        data = self._query({
            "where": f"ASSESSMENT_ROLL_NUMBER='{arn}'",
            "outFields": "*",
            "returnGeometry": "true",
            "outSR": "4326",
        })

        features = data.get("features", [])
        if not features:
            return None

        return self._feature_to_parcel(features[0])

    def query_by_point(self, lat, lng, buffer_deg=0.0002):
        """Query parcel by spatial point. Returns parcel dict or None.

        Creates a small bounding box (~15m) around the point, gets all
        intersecting parcels, then uses point-in-polygon to find the
        parcel that actually contains the point.
        """
        bbox = f"{lng - buffer_deg},{lat - buffer_deg},{lng + buffer_deg},{lat + buffer_deg}"

        data = self._query({
            "geometry": bbox,
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "*",
            "returnGeometry": "true",
            "outSR": "4326",
        })

        features = data.get("features", [])
        if not features:
            return None

        # Always validate with point-in-polygon, even for single results.
        # A bounding-box query can return a parcel that merely overlaps the
        # search envelope without actually containing the point.
        for feature in features:
            rings = feature.get("geometry", {}).get("rings", [])
            if rings and _point_in_polygon(lng, lat, rings[0]):
                return self._feature_to_parcel(feature)

        # Point not inside any returned polygon — retry with a larger buffer
        # to catch the correct parcel that the small bbox may have missed.
        if buffer_deg < 0.001:
            return self.query_by_point(lat, lng, buffer_deg=buffer_deg * 3)

        # After expanding, still no PIP match — pick closest centroid as fallback
        best = None
        best_dist = float('inf')
        for feature in features:
            rings = feature.get("geometry", {}).get("rings", [])
            if rings and rings[0]:
                cx = sum(p[0] for p in rings[0]) / len(rings[0])
                cy = sum(p[1] for p in rings[0]) / len(rings[0])
                dist = (cx - lng) ** 2 + (cy - lat) ** 2
                if dist < best_dist:
                    best_dist = dist
                    best = feature

        return self._feature_to_parcel(best) if best else self._feature_to_parcel(features[0])
