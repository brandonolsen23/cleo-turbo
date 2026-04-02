"""
Resolution chain — resolves a record to a parcel with cross-validation.

When both ARN and geocoded coordinates are available, the chain validates
the ARN result against the spatial result. If they disagree, spatial wins
(the address is ground truth).

Methods returned:
  - arn_verified:     ARN resolved AND spatial confirmed same parcel
  - arn_unverified:   ARN resolved but no geocoded coords to validate
  - spatial_override: ARN and spatial disagreed — spatial result used
  - spatial_geocode:  No ARN, resolved via geocoded coordinates
  - unresolved:       Neither method worked
"""

import math

from .cache import cache_has, cache_read, cache_write
from .agmaps import AgMapsClient, TokenExpiredError


def _haversine_m(lat1, lng1, lat2, lng2):
    """Haversine distance in meters between two lat/lng points."""
    R = 6_371_000
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlng / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _resolve_by_arn(arn, client):
    """Try to resolve by ARN. Returns (parcel, method) or (None, None)."""
    if not arn:
        return None, None

    # Cache check
    if cache_has(arn):
        parcel = cache_read(arn)
        return parcel, 'arn_cache'

    # API query
    parcel = client.query_by_arn(arn)
    if parcel and parcel.get('geometry'):
        cache_write(arn, parcel)
        return parcel, 'arn_api'

    return None, None


def _resolve_by_spatial(geocode_coords, client):
    """Try to resolve by spatial point query. Returns (parcel, arn) or (None, None)."""
    if not geocode_coords or not geocode_coords.get('lat') or not geocode_coords.get('lng'):
        return None, None

    parcel = client.query_by_point(geocode_coords['lat'], geocode_coords['lng'])
    if parcel and parcel.get('arn') and parcel.get('geometry'):
        resolved_arn = parcel['arn']
        if not all(c == '0' for c in resolved_arn):
            cache_write(resolved_arn, parcel)
            return parcel, resolved_arn

    return None, None


def resolve_record(arn, geocode_coords, client):
    """Resolve a single record to a parcel with cross-validation.

    Args:
        arn: 20-digit ARN string, or empty string if unavailable.
        geocode_coords: dict with 'lat' and 'lng' from pre-geocoded results, or None.
        client: AgMapsClient instance (with valid token).

    Returns:
        dict with keys:
            resolved_arn: str or None
            method: str (see module docstring)
            reason: str or None (only set for unresolved)

    Raises:
        TokenExpiredError: If the API token has expired (caller should refresh).
    """
    has_arn = bool(arn)
    has_coords = bool(geocode_coords and geocode_coords.get('lat'))

    # --- Case 1: Both ARN and geocoded coords available → cross-validate ---
    if has_arn and has_coords:
        arn_parcel, arn_method = _resolve_by_arn(arn, client)
        spatial_parcel, spatial_arn = _resolve_by_spatial(geocode_coords, client)

        if arn_parcel and spatial_parcel:
            # Both resolved — compare ARNs
            if arn == spatial_arn:
                # Same parcel — high confidence
                return {
                    "resolved_arn": arn,
                    "method": "arn_verified",
                    "reason": None,
                }
            else:
                # Different parcels — trust spatial (address is ground truth)
                return {
                    "resolved_arn": spatial_arn,
                    "method": "spatial_override",
                    "reason": f"arn_was_{arn}",
                }

        if arn_parcel and not spatial_parcel:
            # Only ARN resolved — validate distance if possible
            centroid = arn_parcel.get('centroid')
            if centroid:
                dist = _haversine_m(
                    geocode_coords['lat'], geocode_coords['lng'],
                    centroid[0], centroid[1],
                )
                if dist > 500:
                    # Parcel centroid is >500m from geocoded address — suspicious
                    return {
                        "resolved_arn": None,
                        "method": "unresolved",
                        "reason": f"arn_too_far_{int(dist)}m",
                    }
            return {
                "resolved_arn": arn,
                "method": arn_method,
                "reason": None,
            }

        if spatial_parcel and not arn_parcel:
            # Only spatial resolved — use it
            return {
                "resolved_arn": spatial_arn,
                "method": "spatial_geocode",
                "reason": None,
            }

        # Neither resolved
        return {
            "resolved_arn": None,
            "method": "unresolved",
            "reason": "both_failed",
        }

    # --- Case 2: ARN only (no geocoded coords) ---
    if has_arn:
        arn_parcel, arn_method = _resolve_by_arn(arn, client)
        if arn_parcel:
            return {
                "resolved_arn": arn,
                "method": "arn_unverified",
                "reason": None,
            }
        return {
            "resolved_arn": None,
            "method": "unresolved",
            "reason": "arn_api_miss",
        }

    # --- Case 3: Geocoded coords only (no ARN) ---
    if has_coords:
        spatial_parcel, spatial_arn = _resolve_by_spatial(geocode_coords, client)
        if spatial_parcel:
            return {
                "resolved_arn": spatial_arn,
                "method": "spatial_geocode",
                "reason": None,
            }
        return {
            "resolved_arn": None,
            "method": "unresolved",
            "reason": "spatial_miss",
        }

    # --- Case 4: Neither ---
    return {
        "resolved_arn": None,
        "method": "unresolved",
        "reason": "no_identifiers",
    }
