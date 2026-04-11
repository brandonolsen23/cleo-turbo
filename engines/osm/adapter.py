"""
OSM pipeline adapter for the unified resolver.

Translates between the OSM POI file format (clean-data/osm/) and the
unified resolver's ResolutionInput/ResolutionResult types.

OSM POIs are resolved IN-PLACE — the arn, parcel_status, and parcel_method
fields are written directly back into the POI file.

This is a THIN LAYER — all resolution logic lives in cleo.resolver.
"""

from __future__ import annotations

import sys
import os

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..')
)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from cleo.resolver.types import (
    ResolutionInput,
    ResolutionResult,
    GeocodableAddress,
    Method,
)


def poi_to_input(poi: dict) -> ResolutionInput:
    """Convert an OSM POI record into a ResolutionInput.

    Args:
        poi: Parsed JSON from clean-data/osm/{OSM_ID}.json

    Returns:
        ResolutionInput ready for resolve().

    POIs have coords (lat, lng) and optional partial addresses.
    Coords are ground truth — most reliable signal for where things are.
    """
    osm_id = poi.get('id', '')

    # Coordinates — the POI's primary signal
    coords = None
    coords_data = poi.get('coords', {})
    lat = coords_data.get('lat')
    lng = coords_data.get('lng')
    if lat is not None and lng is not None:
        coords = (float(lat), float(lng))

    # Address — optional, used as fallback for geocoding
    addresses = []
    geocode_str = _build_geocode_string(poi)
    if geocode_str:
        addr = poi.get('address', {})
        addresses.append(GeocodableAddress(
            geocode_string=geocode_str,
            is_primary=True,
            street_number=addr.get('housenumber', ''),
            street_name=addr.get('street', ''),
            city=addr.get('city', ''),
            province='ON',
            postal_code=addr.get('postcode', ''),
        ))

    return ResolutionInput(
        source='osm',
        source_id=str(osm_id),
        arn=poi.get('arn'),  # May have been previously resolved
        pin=None,            # OSM POIs don't have PINs
        addresses=addresses,
        coords=coords,
    )


def apply_result_to_poi(poi: dict, result: ResolutionResult) -> dict:
    """Apply a ResolutionResult back to an OSM POI record (in-place update).

    Args:
        poi: The original POI dict. Will be MODIFIED and returned.
        result: Output from cleo.resolver.resolve()

    Returns:
        The same poi dict with resolution fields updated.
        Preserves all existing POI fields (name, brand, coords, address, etc.)
    """
    if result.resolved_arn:
        poi['arn'] = result.resolved_arn
        poi['parcel_status'] = 'resolved'
        poi['parcel_method'] = _map_method_to_osm(result)
    else:
        poi['arn'] = None
        poi['parcel_method'] = None
        # Map unresolved reason to OSM-compatible status
        if not poi.get('coords', {}).get('lat'):
            poi['parcel_status'] = 'no_coords'
        elif result.method == Method.ERROR:
            poi['parcel_status'] = f'error: {(result.reason or "unknown")[:100]}'
        else:
            poi['parcel_status'] = 'no_parcel'

    # Add geocode data if available (additive — new field)
    if result.geocode:
        poi['geocode'] = {
            'lat': result.geocode.lat,
            'lng': result.geocode.lng,
            'score': result.geocode.score,
            'addr_type': result.geocode.addr_type,
        }
    elif 'geocode' not in poi:
        # Don't remove existing geocode data from prior runs
        pass

    # New fields (additive — won't break existing consumers)
    poi['resolution_confidence'] = result.confidence
    poi['pip_verified'] = result.pip_verified

    return poi


def _build_geocode_string(poi: dict) -> str | None:
    """Build a geocode string from POI address fields.

    Same logic as the original resolve_pois_v2._build_geocode_string(),
    kept in sync for compatibility.
    """
    addr = poi.get('address', {})
    number = addr.get('housenumber', '').strip()
    street = addr.get('street', '').strip()
    city = addr.get('city', '').strip()

    if not street:
        return None

    parts = []
    if number:
        parts.append(f'{number} {street}')
    else:
        parts.append(street)

    if city:
        parts.append(city)
    parts.append('Ontario')

    return ', '.join(parts)


def _map_method_to_osm(result: ResolutionResult) -> str:
    """Map unified method to OSM-compatible parcel_method string.

    OSM currently uses: spatial_osm, geocode_ontario.
    We map back for backward compatibility but allow new method names.
    """
    m = result.method

    # If resolved via direct coords PIP → spatial_osm
    if m == Method.SPATIAL_COORDS:
        return 'spatial_osm'

    # If resolved via geocoding → geocode_ontario
    if m in (Method.SPATIAL_GEOCODE, Method.SPATIAL_OVERRIDE, Method.SPATIAL_CONSENSUS):
        return 'geocode_ontario'

    # If verified (coords + geocode + ARN agree) → spatial_osm (coords drove it)
    if m == Method.VERIFIED:
        return 'spatial_osm'

    # Pass through for any other method
    return m
