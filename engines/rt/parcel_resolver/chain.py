"""
Resolution chain — takes one record's identifiers and resolves to a parcel.

Tries methods in confidence order:
  1. ARN → cache check → API fallback
  2. Spatial → geocode address → API point query → cache the result

PIN is NOT queryable on the AgMaps parcel layer (the service has no PIN field).
Records with PIN-only must be resolved via spatial (geocode the address, then
point-in-polygon query). PIN-to-ARN bridging may be possible via a different
service in the future, but is not supported by this endpoint.

Returns a resolution result dict for every record (resolved or not).
"""

from .cache import cache_has, cache_read, cache_write
from .agmaps import AgMapsClient, TokenExpiredError


def resolve_record(arn, geocode_string, client):
    """Resolve a single record to a parcel.

    Args:
        arn: 20-digit ARN string, or empty string if unavailable.
        geocode_string: Full geocodable address string, or None.
        client: AgMapsClient instance (with valid token).

    Returns:
        dict with keys:
            resolved_arn: str or None
            method: 'arn_cache' | 'arn_api' | 'spatial_api' | 'unresolved'
            reason: str or None (only set for unresolved)

    Raises:
        TokenExpiredError: If the API token has expired (caller should refresh).
    """

    # --- Step 1: Try ARN ---
    if arn:
        # Check cache first
        if cache_has(arn):
            return {
                "resolved_arn": arn,
                "method": "arn_cache",
                "reason": None,
            }

        # Cache miss — query API by ARN
        parcel = client.query_by_arn(arn)
        if parcel and parcel.get("geometry"):
            cache_write(arn, parcel)
            return {
                "resolved_arn": arn,
                "method": "arn_api",
                "reason": None,
            }

        # ARN not found in API — fall through to spatial

    # --- Step 2: Try spatial (geocode + point query) ---
    # TODO: Implement geocoding (Mapbox/Geocodio) to get lat/lng from geocode_string,
    # then query AgMaps by spatial point. For now, records without a cached/API-resolvable
    # ARN are marked unresolved.

    # --- Unresolved ---
    if not arn:
        reason = "no_arn"
    else:
        reason = "arn_api_miss"

    return {
        "resolved_arn": None,
        "method": "unresolved",
        "reason": reason,
    }
