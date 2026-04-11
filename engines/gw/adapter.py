"""
GW pipeline adapter for the unified resolver.

Translates between the GW pipeline's file format (normalized → parcel_links)
and the unified resolver's ResolutionInput/ResolutionResult types.

GW records can have multiple assessments, each with its own ARN.
Each assessment gets resolved independently.

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


def normalized_to_inputs(normalized: dict) -> list[tuple[str, ResolutionInput]]:
    """Convert a GW normalized record into ResolutionInputs (one per assessment).

    Args:
        normalized: Parsed JSON from engines/gw/pipeline/normalized/{GW_ID}.json

    Returns:
        List of (arn_api, ResolutionInput) tuples. The arn_api string is needed
        to map results back to the correct assessment in the output.
        If there are no assessments, returns an empty list.
    """
    gw_id = normalized.get('gw_id', '')
    pin = normalized.get('pin_api', '').strip() or None

    inputs = []
    for assessment in normalized.get('assessments', []):
        arn_api = assessment.get('arn_api', '').strip()

        # Build a ResolutionInput for this single assessment ARN.
        # GW records are ARN-primary — we typically don't geocode them
        # (they already have authoritative ARNs from MPAC). But the
        # unified resolver handles the case where the ARN doesn't resolve.
        ri = ResolutionInput(
            source='gw',
            source_id=gw_id,
            arn=arn_api or None,
            pin=pin,
            addresses=[],   # GW doesn't provide geocodable addresses
            coords=None,    # GW doesn't provide coordinates
        )
        inputs.append((arn_api, ri))

    return inputs


def results_to_gw_parcel_link(
    gw_id: str,
    pin: str,
    assessment_results: list[tuple[str, ResolutionResult]],
) -> dict:
    """Convert ResolutionResults back into GW parcel_links JSON format.

    Args:
        gw_id: GW record ID
        pin: PIN from the normalized record
        assessment_results: List of (arn_api, ResolutionResult) pairs,
                           one per assessment.

    Returns:
        Dict matching the existing GW parcel_links schema:
        {gw_id, pin, resolutions: [{arn, method, parcel_file}]}
    """
    resolutions = []
    for arn_api, result in assessment_results:
        resolution = {
            'arn': arn_api,
            'method': _map_method_to_gw(result),
            'parcel_file': result.parcel_file,
        }
        resolutions.append(resolution)

    return {
        'gw_id': gw_id,
        'pin': pin or '',
        'resolutions': resolutions,
    }


def _map_method_to_gw(result: ResolutionResult) -> str:
    """Map unified method names to GW-compatible method names.

    GW compile.py currently understands: arn_cache, arn_api, arn_api_miss, no_arn.
    We map the unified names back to these for backward compatibility,
    but also pass through new method names so they degrade gracefully.
    """
    m = result.method

    # Direct mappings for GW's existing method vocabulary
    if m == Method.UNRESOLVED:
        # Check reason to distinguish no_arn from arn_api_miss
        reason = result.reason or ''
        if 'no_arn' in reason:
            return 'no_arn'
        return 'arn_api_miss'

    if m == Method.ERROR:
        return 'error'

    # The unified resolver may have resolved via cache or API.
    # Check signals to determine which path was taken.
    for signal in result.signals:
        if signal.source == 'arn_cache':
            return 'arn_cache'
        if signal.source == 'arn_api' and signal.candidate_arn:
            return 'arn_api'

    # Fallback: use the unified method name directly.
    # GW compile.py checks for parcel_file presence, so new method
    # names will still work — they just won't match the old vocabulary.
    return m
