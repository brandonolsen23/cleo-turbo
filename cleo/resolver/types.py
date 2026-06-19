"""
Unified parcel resolution types.

Defines the input/output contracts for the resolver. All pipelines
(RT, GW, OSM) use these types to interact with the unified service.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GeocodableAddress:
    """An address that can be geocoded.

    Created from RT normalized addresses, GW MPAC addresses,
    or OSM partial addresses.
    """
    geocode_string: str        # Full address for geocoding
    is_primary: bool = True    # First address = primary, rest = variants
    original: str = ""         # Raw address from source
    display: str = ""          # Cleaned display form

    # Parsed components (for cross-validation against geocoder output)
    street_number: str = ""
    street_name: str = ""
    street_suffix: str = ""
    city: str = ""
    province: str = "ON"
    postal_code: str = ""


@dataclass
class ResolutionInput:
    """Input to the unified resolver.

    All fields are optional — the resolver works with whatever the
    caller provides. Each pipeline passes what it has:
      - RT: arn, pin, addresses (from normalized stage)
      - GW: arn, pin, addresses (from MPAC)
      - OSM: coords, addresses (partial)
    """
    source: str                     # "rt", "gw", or "osm"
    source_id: str                  # RT_ID, GW_ID, or OSM_ID

    arn: Optional[str] = None       # 20-digit ARN (may be all zeros = missing)
    pin: Optional[str] = None       # 9-digit PIN
    addresses: list[GeocodableAddress] = field(default_factory=list)
    coords: Optional[tuple[float, float]] = None  # (lat, lng) — OSM rooftop or prior geocode

    def has_arn(self) -> bool:
        """True if ARN is present and not all zeros."""
        return bool(self.arn) and not all(c == "0" for c in self.arn)

    def has_pin(self) -> bool:
        """True if PIN is present and not all zeros."""
        return bool(self.pin) and not all(c == "0" for c in self.pin)

    def has_geocodable_addresses(self) -> bool:
        """True if at least one address has a geocode string."""
        return any(a.geocode_string for a in self.addresses)

    def has_coords(self) -> bool:
        """True if coordinates are provided."""
        return self.coords is not None


@dataclass
class GeocodeResult:
    """Full geocode result from Ontario Address Locator.

    Captures all 44 attributes from the GeocodeServer response,
    not just the 6 we used to keep.
    """
    lat: float
    lng: float
    score: int
    addr_type: str              # PointAddress, StreetAddress, StreetName, Postal
    match_addr: str             # Geocoder's canonical address form
    loc_name: str               # Source locator (e.g., "PARCEL_PCCF")

    # Component-level scoring — the gold field from schema discovery.
    # e.g., "House=100; StName=100; suftype=100; City=100"
    comp_score: str = ""

    # Parsed address components from geocoder (cross-check against input)
    house: str = ""             # Street number
    street_name: str = ""       # Street name
    suf_type: str = ""          # Street suffix (Street, Drive, etc.)
    pre_dir: str = ""           # Directional prefix
    suf_dir: str = ""           # Directional suffix
    city: str = ""              # City name
    state: str = ""             # Province
    postal: str = ""            # Postal code (ZIP field)
    county: str = ""            # County (often empty)
    side: str = ""              # Side of street (often empty)

    # Sub-address components
    sub_addr_type: str = ""     # Unit type
    sub_addr_unit: str = ""     # Unit number
    bldg_sub_addr_type: str = ""
    bldg_sub_addr_unit: str = ""

    # All candidates (for debugging and fallback analysis)
    all_candidates: list[dict] = field(default_factory=list)

    @classmethod
    def from_raw_candidate(cls, candidate: dict) -> "GeocodeResult":
        """Create from a raw GeocodeServer candidate dict."""
        loc = candidate.get("location", {})
        attrs = candidate.get("attributes", {})

        return cls(
            lat=loc.get("y", 0),
            lng=loc.get("x", 0),
            score=candidate.get("score", 0),
            addr_type=attrs.get("Addr_type", ""),
            match_addr=candidate.get("address", ""),
            loc_name=attrs.get("Loc_name", ""),
            comp_score=attrs.get("Comp_score", ""),
            house=attrs.get("House", ""),
            street_name=attrs.get("StreetName", ""),
            suf_type=attrs.get("SufType", ""),
            pre_dir=attrs.get("PreDir", ""),
            suf_dir=attrs.get("SufDir", ""),
            city=attrs.get("City", ""),
            state=attrs.get("State", ""),
            postal=attrs.get("ZIP", ""),
            county=attrs.get("County", ""),
            side=attrs.get("Side", ""),
            sub_addr_type=attrs.get("SubAddrType", ""),
            sub_addr_unit=attrs.get("SubAddrUnit", ""),
            bldg_sub_addr_type=attrs.get("BldgSubAddrType", ""),
            bldg_sub_addr_unit=attrs.get("BldgSubAddrUnit", ""),
        )

    def to_dict(self) -> dict:
        """Serialize for JSON storage in parcel_links files."""
        d = {
            "lat": self.lat,
            "lng": self.lng,
            "score": self.score,
            "addr_type": self.addr_type,
            "match_addr": self.match_addr,
            "loc_name": self.loc_name,
            "comp_score": self.comp_score,
            "city": self.city,
            "state": self.state,
        }
        # Include parsed components only if non-empty
        for key in ("house", "street_name", "suf_type", "pre_dir", "suf_dir",
                     "postal", "county", "side", "sub_addr_type", "sub_addr_unit"):
            val = getattr(self, key)
            if val:
                d[key] = val
        return d


@dataclass
class Signal:
    """A single resolution signal collected during the chain.

    The resolver collects multiple signals (ARN lookup, geocode,
    spatial PIP, etc.) and then makes a weighted decision.
    """
    source: str                # "arn_cache", "arn_api", "pin_bridge",
                               # "geocode_primary", "geocode_variant",
                               # "coords_pip", "pip_verify"
    candidate_arn: Optional[str] = None
    confidence: float = 0.0
    geocode: Optional[GeocodeResult] = None
    details: str = ""          # Human-readable diagnostic

    def to_dict(self) -> dict:
        d = {
            "source": self.source,
            "candidate_arn": self.candidate_arn,
            "confidence": self.confidence,
            "details": self.details,
        }
        if self.geocode:
            d["geocode"] = self.geocode.to_dict()
        return d


# ── Method names (standardized across all sources) ──────────────────

class Method:
    """Resolution method constants.

    These are the values that appear in parcel_links.method and
    in the database. Standardized across RT, GW, and OSM.
    """
    VERIFIED = "verified"                     # ARN + geocode + PIP agree
    SPATIAL_CONSENSUS = "spatial_consensus"   # Multiple address variants agree
    SPATIAL_GEOCODE = "spatial_geocode"       # Single geocode + PIP
    SPATIAL_OVERRIDE = "spatial_override"     # Geocode overrode ARN
    SPATIAL_COORDS = "spatial_coords"         # Direct coords PIP (OSM)
    ARN_ONLY = "arn_only"                     # ARN resolved, no geocode validation
    PIN_BRIDGE = "pin_bridge"                 # PIN→ARN via GW lookup
    UNRESOLVED = "unresolved"                 # All methods failed
    ERROR = "error"                           # Exception during resolution


# ── Confidence base scores ──────────────────────────────────────────

BASE_CONFIDENCE = {
    Method.VERIFIED: 0.95,
    Method.SPATIAL_CONSENSUS: 0.90,
    Method.SPATIAL_COORDS: 0.90,        # OSM rooftop coords
    Method.SPATIAL_GEOCODE: 0.85,       # PointAddress; adjusted down for StreetAddress
    Method.SPATIAL_OVERRIDE: 0.80,
    Method.ARN_ONLY: 0.50,
    Method.PIN_BRIDGE: 0.40,
    Method.UNRESOLVED: 0.00,
    Method.ERROR: 0.00,
}

# Adjustments
STREET_ADDRESS_PENALTY = -0.15   # StreetAddress geocode is less precise
PIP_VERIFIED_BONUS = 0.05        # Final PIP verification passed
CONFIDENCE_CAP = 1.0


@dataclass
class ResolutionResult:
    """Output from the unified resolver.

    This is the contract that all downstream consumers depend on.
    The format is a strict superset of the old parcel_links schema —
    existing fields preserved, new fields additive.
    """
    resolved_arn: Optional[str]     # 20-digit ARN, or None if unresolved
    method: str                     # One of Method.* constants
    confidence: float               # 0.0–1.0
    parcel_file: Optional[str]      # "{arn}.json" reference to cache
    reason: Optional[str]           # Diagnostic if unresolved/overridden
    geocode: Optional[GeocodeResult]  # Best geocode result (if any)
    signals: list[Signal]           # All signals collected
    pip_verified: bool              # Did final PIP verification pass?
    containment: Optional[str] = None  # resolved parcel containment:
                                        # contained / nearest_centroid / features0 / None

    def to_dict(self) -> dict:
        """Serialize for JSON storage in parcel_links files.

        Backward compatible with current schema: resolved_arn, method,
        parcel_file, reason, geocode are preserved. New fields
        (confidence, pip_verified, signals) are additive.
        """
        d = {
            "resolved_arn": self.resolved_arn,
            "method": self.method,
            "confidence": round(self.confidence, 3),
            "parcel_file": self.parcel_file,
            "reason": self.reason,
            "pip_verified": self.pip_verified,
            "containment": self.containment,
        }
        if self.geocode:
            d["geocode"] = self.geocode.to_dict()
        if self.signals:
            d["signals"] = [s.to_dict() for s in self.signals]
        return d

    @staticmethod
    def unresolved(reason: str, signals: list[Signal] = None) -> "ResolutionResult":
        """Convenience constructor for unresolved results."""
        return ResolutionResult(
            resolved_arn=None,
            method=Method.UNRESOLVED,
            confidence=0.0,
            parcel_file=None,
            reason=reason,
            geocode=None,
            signals=signals or [],
            pip_verified=False,
        )

    @staticmethod
    def error(reason: str) -> "ResolutionResult":
        """Convenience constructor for error results."""
        return ResolutionResult(
            resolved_arn=None,
            method=Method.ERROR,
            confidence=0.0,
            parcel_file=None,
            reason=reason[:200],
            geocode=None,
            signals=[],
            pip_verified=False,
        )
