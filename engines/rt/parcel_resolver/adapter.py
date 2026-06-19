"""
RT pipeline adapter for the unified resolver.

Translates between the RT pipeline's file format (addresses → parcel_links)
and the unified resolver's ResolutionInput/ResolutionResult types.

This is a THIN LAYER — all resolution logic lives in cleo.resolver.
"""

from __future__ import annotations

import sys
import os

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..', '..')
)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from cleo.resolver.types import (
    ResolutionInput,
    ResolutionResult,
    GeocodableAddress,
)
from cleo.resolver import verify


def addresses_to_input(addr_record: dict) -> ResolutionInput:
    """Convert an RT addresses file into a ResolutionInput.

    Args:
        addr_record: Parsed JSON from pipeline/addresses/{filename}.json

    Returns:
        ResolutionInput ready for resolve().

    The addresses file has this shape:
        rt_id: str
        property.addresses[]: list of normalized address dicts
        pin: {original, display, api_format}
        arn: {original, display, api_format}
    """
    rt_id = addr_record.get('rt_id', '')

    # ARN: 20-digit api_format
    arn_data = addr_record.get('arn', {})
    arn = None
    if isinstance(arn_data, dict):
        arn = arn_data.get('api_format', '').strip() or None
    elif isinstance(arn_data, str):
        arn = arn_data.strip() or None

    # PIN: 9-digit api_format
    pin_data = addr_record.get('pin', {})
    pin = None
    if isinstance(pin_data, dict):
        pin = pin_data.get('api_format', '').strip() or None
    elif isinstance(pin_data, str):
        pin = pin_data.strip() or None

    # Addresses: collect all geocodable property addresses
    addresses = []
    prop = addr_record.get('property', {})
    for i, addr in enumerate(prop.get('addresses', [])):
        gs = (addr.get('geocode_string') or '').strip()
        if not gs or not addr.get('geocodable', True):
            continue

        components = addr.get('components', {})
        addresses.append(GeocodableAddress(
            geocode_string=gs,
            is_primary=(i == 0),
            original=addr.get('original', ''),
            display=addr.get('display', ''),
            street_number=components.get('street_number', ''),
            street_name=components.get('street_name', ''),
            street_suffix=components.get('street_suffix', ''),
            city=components.get('city', ''),
            province='ON',
            postal_code=components.get('postal', ''),
        ))

        # Also include range-expanded variations as additional variants
        for variation in addr.get('variations', []):
            vgs = (variation.get('geocode_string') or '').strip()
            if vgs and vgs != gs:
                addresses.append(GeocodableAddress(
                    geocode_string=vgs,
                    is_primary=False,
                    original=variation.get('original', ''),
                    display=variation.get('display', ''),
                ))

    return ResolutionInput(
        source='rt',
        source_id=rt_id,
        arn=arn,
        pin=pin,
        addresses=addresses,
        coords=None,  # RT records don't have prior coordinates
    )


def result_to_parcel_link(result: ResolutionResult, rt_id: str,
                          input: ResolutionInput | None = None) -> dict:
    """Convert a ResolutionResult into RT parcel_links JSON format.

    Args:
        result: Output from cleo.resolver.resolve()
        rt_id: RT record ID for the output

    Returns:
        Dict matching the existing parcel_links schema (backward compatible).
        Downstream compile.py reads: resolved_arn, method, parcel_file, geocode.
        New fields (confidence, pip_verified, signals, reason) are additive.
    """
    link = {
        'rt_id': rt_id,
        'resolved_arn': result.resolved_arn,
        'method': result.method,
        'parcel_file': result.parcel_file,
        'reason': result.reason,
        'confidence': result.confidence,
        'pip_verified': result.pip_verified,
    }

    # Geocode in old format (backward compat with compile.py)
    if result.geocode:
        link['geocode'] = {
            'lat': result.geocode.lat,
            'lng': result.geocode.lng,
            'score': result.geocode.score,
            'addr_type': result.geocode.addr_type,
            'match_addr': result.geocode.match_addr,
        }
        # Extended geocode data (new — additive)
        if result.geocode.comp_score:
            link['geocode']['comp_score'] = result.geocode.comp_score
        if result.geocode.loc_name:
            link['geocode']['loc_name'] = result.geocode.loc_name

    # Signals (new — additive, for audit trail)
    if result.signals:
        link['signals'] = [s.to_dict() for s in result.signals]

    # ── Stage-1 verification provenance (flat keys for compile/writer) ──
    geo = result.geocode
    link['containment'] = result.containment
    link['geocode_addr_type'] = geo.addr_type if geo else None
    link['geocode_score'] = geo.score if geo else None
    link['loc_name'] = geo.loc_name if geo else None

    fmatch = False
    if geo is not None and input is not None and input.addresses:
        prim = next((a for a in input.addresses if a.is_primary), input.addresses[0])
        rt_street = f"{prim.street_name} {prim.street_suffix}".strip()
        geo_street = f"{geo.street_name} {geo.suf_type}".strip()
        fmatch = verify.field_match(
            prim.street_number, rt_street, prim.city,
            geo.house, geo_street, geo.city,
        )
    link['field_match'] = 1 if fmatch else 0
    link['parcel_tier'] = verify.tier_for(
        result.method,
        geo.loc_name if geo else None,
        geo.addr_type if geo else None,
        result.containment,
        fmatch,
    )

    return link
