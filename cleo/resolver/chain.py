"""
Unified resolution chain — the core logic that resolves any record
to an Ontario land parcel.

Collects multiple signals (ARN lookup, geocoding, spatial PIP) and
makes a confidence-weighted decision. Never trusts a single signal.

The chain:
  1. PIN→ARN bridge (zero API calls)
  2. ARN lookup (cache → API)
  3. Address geocoding (Ontario geocoder → spatial PIP)
  4. Coordinate PIP (direct spatial query from OSM/prior coords)
  5. Cross-validation (compare all signals)
  6. PIP verification (local grid-based check, zero API calls)
"""

from __future__ import annotations

import math
from typing import Optional

from .types import (
    ResolutionInput,
    ResolutionResult,
    GeocodeResult,
    Signal,
    Method,
    BASE_CONFIDENCE,
    STREET_ADDRESS_PENALTY,
    PIP_VERIFIED_BONUS,
    CONFIDENCE_CAP,
)
from .cache import cache_has, cache_read_safe, cache_write
from .pin_bridge import lookup_pin
from .pip import pip_test_parcel, verify_pip


def _haversine_m(lat1, lng1, lat2, lng2):
    """Approximate distance in meters between two WGS84 points."""
    R = 6_371_000
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2))
         * math.sin(dlng / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class ResolverContext:
    """Shared state for a resolution session.

    Holds references to the AgMaps client, Ontario geocoder, and
    PIN→ARN lookup table. Created once per batch run, reused across
    all records in the batch.
    """

    def __init__(
        self,
        agmaps_client=None,
        geocoder_client=None,
        pin_to_arn: dict[str, str] | None = None,
        verbose: bool = True,
    ):
        self.agmaps = agmaps_client
        self.geocoder = geocoder_client
        self.pin_to_arn = pin_to_arn or {}
        self.verbose = verbose

    @property
    def has_agmaps(self) -> bool:
        return self.agmaps is not None

    @property
    def has_geocoder(self) -> bool:
        return self.geocoder is not None


def resolve(
    input: ResolutionInput,
    ctx: ResolverContext | None = None,
) -> ResolutionResult:
    """Resolve a single record to a parcel.

    This is the public API. All pipelines call this function.

    Args:
        input: What we know about the record (ARN, PIN, addresses, coords).
        ctx: Shared resolver context with API clients. If None, only
             cache-based resolution is available (no geocoding).

    Returns:
        ResolutionResult with the resolved ARN, method, confidence,
        and all collected signals.
    """
    if ctx is None:
        ctx = ResolverContext()

    signals: list[Signal] = []
    arn_candidate: str | None = None
    arn_parcel: dict | None = None
    best_geocode: GeocodeResult | None = None
    geocode_candidates: list[tuple[str | None, GeocodeResult]] = []

    # ── Step 1: PIN→ARN bridge ───────────────────────────────────
    if not input.has_arn() and input.has_pin():
        bridged = lookup_pin(input.pin, ctx.pin_to_arn)
        if bridged:
            input.arn = bridged  # Promote for step 2
            signals.append(Signal(
                source="pin_bridge",
                candidate_arn=bridged,
                confidence=0.4,
                details=f"PIN {input.pin} bridged to ARN {bridged} via GW",
            ))

    # ── Step 2: ARN lookup ───────────────────────────────────────
    if input.has_arn():
        arn = input.arn

        # Cache first
        if cache_has(arn):
            arn_parcel = cache_read_safe(arn)
            arn_candidate = arn
            signals.append(Signal(
                source="arn_cache",
                candidate_arn=arn,
                confidence=0.5,
                details=f"ARN {arn} found in parcel cache",
            ))
        elif ctx.has_agmaps:
            # API query
            try:
                parcel = ctx.agmaps.query_by_arn(arn)
                if parcel:
                    cache_write(arn, parcel)
                    arn_parcel = parcel
                    arn_candidate = arn
                    signals.append(Signal(
                        source="arn_api",
                        candidate_arn=arn,
                        confidence=0.5,
                        details=f"ARN {arn} resolved via AgMaps API",
                    ))
                else:
                    signals.append(Signal(
                        source="arn_api",
                        candidate_arn=None,
                        confidence=0.0,
                        details=f"ARN {arn} not found in AgMaps",
                    ))
            except Exception as e:
                signals.append(Signal(
                    source="arn_api",
                    candidate_arn=None,
                    confidence=0.0,
                    details=f"ARN query error: {str(e)[:100]}",
                ))
                # Re-raise errors that the caller needs to handle
                # (token expiry, network errors, etc.). The caller
                # owns the AgMaps client and knows how to refresh.
                # We detect token errors by class name to avoid
                # importing from the engine layer.
                if type(e).__name__ in ('TokenExpiredError', 'SessionError'):
                    raise

    # ── Step 3: Address geocoding ────────────────────────────────
    if input.has_geocodable_addresses() and ctx.has_geocoder:
        for i, addr in enumerate(input.addresses):
            if not addr.geocode_string:
                continue

            geo = _geocode_address(addr.geocode_string, ctx)
            if geo is None:
                continue

            # Skip Postal-level matches (too imprecise)
            if geo.addr_type == "Postal":
                continue

            # Spatial PIP query to find containing parcel
            geo_arn = None
            if ctx.has_agmaps:
                try:
                    parcel = ctx.agmaps.query_by_point(geo.lat, geo.lng)
                    if parcel:
                        geo_arn = parcel.get("arn")
                        if geo_arn and not cache_has(geo_arn):
                            cache_write(geo_arn, parcel)
                except Exception:
                    pass  # Geocode succeeded but spatial query failed

            is_primary = addr.is_primary or i == 0
            signal_source = "geocode_primary" if is_primary else "geocode_variant"

            conf = 0.85 if geo.addr_type == "PointAddress" else 0.70
            signals.append(Signal(
                source=signal_source,
                candidate_arn=geo_arn,
                confidence=conf,
                geocode=geo,
                details=(
                    f"{'Primary' if is_primary else 'Variant'} address geocoded: "
                    f"{geo.addr_type} score={geo.score} → ARN {geo_arn}"
                ),
            ))

            geocode_candidates.append((geo_arn, geo))

            if is_primary or best_geocode is None:
                best_geocode = geo

    # ── Step 4: Coordinate PIP (OSM rooftop / prior coords) ─────
    if input.has_coords() and ctx.has_agmaps:
        lat, lng = input.coords
        try:
            parcel = ctx.agmaps.query_by_point(lat, lng)
            if parcel:
                coords_arn = parcel.get("arn")
                if coords_arn and not cache_has(coords_arn):
                    cache_write(coords_arn, parcel)
                conf = 0.90 if input.source == "osm" else 0.80
                signals.append(Signal(
                    source="coords_pip",
                    candidate_arn=coords_arn,
                    confidence=conf,
                    details=f"Coords ({lat:.6f}, {lng:.6f}) → ARN {coords_arn}",
                ))
        except Exception:
            pass

    # ── Step 5: Cross-validation and decision ────────────────────
    return _decide(input, signals, arn_candidate, arn_parcel,
                   best_geocode, geocode_candidates)


def _geocode_address(address: str, ctx: ResolverContext) -> GeocodeResult | None:
    """Geocode a single address via the Ontario geocoder.

    Captures all 44 response attributes.
    """
    result = ctx.geocoder.geocode(address)
    if result is None:
        return None

    # The existing geocoder returns our old dict format.
    # Convert to GeocodeResult, capturing the extra fields if available.
    # The geocoder currently returns: lat, lng, score, addr_type,
    # match_addr, loc_name, all_candidates

    return GeocodeResult(
        lat=result["lat"],
        lng=result["lng"],
        score=result["score"],
        addr_type=result["addr_type"],
        match_addr=result["match_addr"],
        loc_name=result.get("loc_name", ""),
        # New fields — available after geocoder upgrade
        comp_score=result.get("comp_score", ""),
        house=result.get("house", ""),
        street_name=result.get("street_name", ""),
        suf_type=result.get("suf_type", ""),
        pre_dir=result.get("pre_dir", ""),
        suf_dir=result.get("suf_dir", ""),
        city=result.get("city", ""),
        state=result.get("state", ""),
        postal=result.get("postal", ""),
        county=result.get("county", ""),
        side=result.get("side", ""),
        all_candidates=result.get("all_candidates", []),
    )


def _decide(
    input: ResolutionInput,
    signals: list[Signal],
    arn_candidate: str | None,
    arn_parcel: dict | None,
    best_geocode: GeocodeResult | None,
    geocode_candidates: list[tuple[str | None, GeocodeResult]],
) -> ResolutionResult:
    """Make the final resolution decision from collected signals.

    Decision hierarchy (highest to lowest trust):
      1. OSM rooftop coordinates (coords_pip signal)
      2. PointAddress geocode (score ≥ 90, PIP passes)
      3. Multi-address consensus (≥ 2 variants agree)
      4. StreetAddress geocode (score ≥ 80, PIP passes)
      5. ARN from source data
      6. PIN-bridged ARN
    """
    # Collect ARN votes from geocode signals
    geo_arns = [arn for arn, _ in geocode_candidates if arn]
    coords_signal = _find_signal(signals, "coords_pip")

    # Consensus: do multiple geocode variants agree?
    consensus_arn, consensus_count = _consensus(geo_arns)

    # Best geocode signal (primary address preferred)
    best_geo_signal = _find_signal(signals, "geocode_primary")
    if not best_geo_signal:
        best_geo_signal = _find_signal(signals, "geocode_variant")
    best_geo_arn = best_geo_signal.candidate_arn if best_geo_signal else None

    # ── Decision logic ───────────────────────────────────────────

    resolved_arn = None
    method = Method.UNRESOLVED
    reason = None
    confidence = 0.0

    # Priority 1: OSM rooftop coordinates
    if coords_signal and coords_signal.candidate_arn:
        resolved_arn = coords_signal.candidate_arn
        method = Method.SPATIAL_COORDS
        confidence = coords_signal.confidence

        # If ARN also resolved and agrees, boost confidence
        if arn_candidate and arn_candidate == resolved_arn:
            method = Method.VERIFIED
            confidence = BASE_CONFIDENCE[Method.VERIFIED]

    # Priority 2+3+4: Geocode-based resolution
    elif best_geo_arn or consensus_arn:
        # Check if ARN and geocode agree → VERIFIED (highest confidence)
        if arn_candidate and best_geo_arn and arn_candidate == best_geo_arn:
            resolved_arn = arn_candidate
            method = Method.VERIFIED
            confidence = BASE_CONFIDENCE[Method.VERIFIED]

        # Check consensus (≥2 variants agree on same parcel)
        elif consensus_arn and consensus_count >= 2:
            # Does consensus agree with ARN?
            if arn_candidate and arn_candidate == consensus_arn:
                resolved_arn = consensus_arn
                method = Method.VERIFIED
                confidence = BASE_CONFIDENCE[Method.VERIFIED]
            else:
                resolved_arn = consensus_arn
                method = Method.SPATIAL_CONSENSUS
                confidence = BASE_CONFIDENCE[Method.SPATIAL_CONSENSUS]
                if arn_candidate:
                    reason = f"consensus_overrode_arn_{arn_candidate}"

        # PointAddress geocode overrides ARN (rooftop precision)
        elif (best_geocode and best_geocode.addr_type == "PointAddress"
              and best_geocode.score >= 90 and best_geo_arn):
            if arn_candidate and arn_candidate != best_geo_arn:
                resolved_arn = best_geo_arn
                method = Method.SPATIAL_OVERRIDE
                confidence = BASE_CONFIDENCE[Method.SPATIAL_OVERRIDE]
                reason = f"geocode_overrode_arn_{arn_candidate}"
            else:
                resolved_arn = best_geo_arn
                method = Method.SPATIAL_GEOCODE
                confidence = BASE_CONFIDENCE[Method.SPATIAL_GEOCODE]

        # StreetAddress geocode (lower confidence)
        elif best_geo_arn and best_geocode:
            if arn_candidate and arn_candidate != best_geo_arn:
                # StreetAddress disagrees with ARN — trust ARN unless
                # we have consensus or the ARN is unvalidated
                if arn_parcel:
                    resolved_arn = arn_candidate
                    method = Method.ARN_ONLY
                    confidence = BASE_CONFIDENCE[Method.ARN_ONLY]
                    reason = f"street_geocode_disagrees_{best_geo_arn}"
                else:
                    resolved_arn = best_geo_arn
                    method = Method.SPATIAL_GEOCODE
                    confidence = (BASE_CONFIDENCE[Method.SPATIAL_GEOCODE]
                                  + STREET_ADDRESS_PENALTY)
            else:
                resolved_arn = best_geo_arn
                method = Method.SPATIAL_GEOCODE
                confidence = (BASE_CONFIDENCE[Method.SPATIAL_GEOCODE]
                              + STREET_ADDRESS_PENALTY)

    # Priority 5: ARN from source data (no geocode validation)
    elif arn_candidate and arn_parcel:
        resolved_arn = arn_candidate
        method = Method.ARN_ONLY
        confidence = BASE_CONFIDENCE[Method.ARN_ONLY]

        # Distance check if we have any geocoded coords
        if best_geocode:
            centroid = arn_parcel.get("centroid")
            if centroid:
                dist = _haversine_m(
                    best_geocode.lat, best_geocode.lng,
                    centroid[0], centroid[1]
                )
                if dist > 500:
                    # Geocoded point is far from ARN parcel — suspicious
                    resolved_arn = None
                    method = Method.UNRESOLVED
                    confidence = 0.0
                    reason = f"arn_too_far_{int(dist)}m"

    # Priority 6: PIN-bridged ARN (lowest confidence)
    elif arn_candidate:
        # ARN came from PIN bridge but no parcel geometry found
        resolved_arn = arn_candidate
        method = Method.PIN_BRIDGE
        confidence = BASE_CONFIDENCE[Method.PIN_BRIDGE]

    # ── Step 6: PIP verification ─────────────────────────────────
    pip_verified = False
    if resolved_arn:
        # Get best available coordinates for verification
        verify_lat, verify_lng = _best_coords(input, best_geocode, coords_signal)

        if verify_lat is not None and verify_lng is not None:
            pip_verified = verify_pip(verify_lat, verify_lng, resolved_arn)

            if pip_verified:
                confidence = min(confidence + PIP_VERIFIED_BONUS, CONFIDENCE_CAP)
                signals.append(Signal(
                    source="pip_verify",
                    candidate_arn=resolved_arn,
                    confidence=PIP_VERIFIED_BONUS,
                    details=f"PIP verified: ({verify_lat:.6f}, {verify_lng:.6f}) inside {resolved_arn}",
                ))
            else:
                signals.append(Signal(
                    source="pip_verify",
                    candidate_arn=resolved_arn,
                    confidence=0.0,
                    details=f"PIP FAILED: ({verify_lat:.6f}, {verify_lng:.6f}) not inside {resolved_arn}",
                ))
                # PIP failure doesn't override the decision — it's a flag.
                # The record keeps its resolution but pip_verified=False
                # signals that manual review may be needed.

    # ── Build unresolved reason ──────────────────────────────────
    if resolved_arn is None and reason is None:
        parts = []
        if not input.has_arn() and not input.has_pin():
            parts.append("no_arn_no_pin")
        elif input.has_arn():
            parts.append("arn_miss")
        if not input.has_geocodable_addresses():
            parts.append("no_address")
        elif not best_geocode:
            parts.append("geocode_miss")
        elif not best_geo_arn:
            parts.append("spatial_miss")
        reason = "_".join(parts) if parts else "unknown"

    # ── Assemble result ──────────────────────────────────────────
    return ResolutionResult(
        resolved_arn=resolved_arn,
        method=method,
        confidence=round(confidence, 3),
        parcel_file=f"{resolved_arn}.json" if resolved_arn else None,
        reason=reason,
        geocode=best_geocode,
        signals=signals,
        pip_verified=pip_verified,
    )


# ── Helpers ──────────────────────────────────────────────────────────

def _find_signal(signals: list[Signal], source: str) -> Signal | None:
    """Find the first signal with the given source name."""
    for s in signals:
        if s.source == source:
            return s
    return None


def _consensus(arns: list[str]) -> tuple[str | None, int]:
    """Find the ARN that appears most frequently.

    Returns (arn, count) if any ARN appears ≥ 2 times, else (None, 0).
    """
    if not arns:
        return None, 0

    counts: dict[str, int] = {}
    for arn in arns:
        counts[arn] = counts.get(arn, 0) + 1

    best_arn = max(counts, key=counts.get)
    best_count = counts[best_arn]

    if best_count >= 2:
        return best_arn, best_count
    return None, 0


def _best_coords(
    input: ResolutionInput,
    geocode: GeocodeResult | None,
    coords_signal: Signal | None,
) -> tuple[float | None, float | None]:
    """Get the best available coordinates for PIP verification.

    Priority:
      1. Input coords (OSM rooftop — most accurate)
      2. Geocoded coords (Ontario geocoder)
      3. None
    """
    if input.has_coords():
        return input.coords

    if geocode:
        return geocode.lat, geocode.lng

    return None, None
