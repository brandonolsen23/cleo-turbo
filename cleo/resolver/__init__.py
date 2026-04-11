"""
Unified Parcel Resolution Service.

Single entry point for resolving any record (RT, GW, or OSM)
to an Ontario land parcel via ARN.

Usage:
    from cleo.resolver import resolve, ResolutionInput, GeocodableAddress

    result = resolve(ResolutionInput(
        source="rt",
        source_id="RT100001",
        arn="19080133200075000000",
        addresses=[GeocodableAddress(geocode_string="90 Signet Dr, North York, ON")],
    ))

    print(result.resolved_arn)   # "19080133200075000000"
    print(result.method)         # "verified"
    print(result.confidence)     # 0.95
"""

from .types import (
    ResolutionInput,
    ResolutionResult,
    GeocodableAddress,
    GeocodeResult,
    Signal,
    Method,
)
from .chain import resolve, ResolverContext

__all__ = [
    "resolve",
    "ResolverContext",
    "ResolutionInput",
    "ResolutionResult",
    "GeocodableAddress",
    "GeocodeResult",
    "Signal",
    "Method",
]
