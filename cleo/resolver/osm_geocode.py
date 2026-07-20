"""
OSM / Nominatim forward-geocoder — a SECOND, independent geocoding source.

The resolver chain is built to weigh multiple signals ("never trust a single
signal"), but for an address-only record the Ontario Address Locator is today
the only geocoder feeding it. A single geocoder can be confidently wrong (the
Eastcourt Mall case: the provincial locator dropped the pin in the wrong part
of the municipality). This client geocodes the SAME address string through
OpenStreetMap's Nominatim so the two points can be compared — agreement earns
confidence, disagreement is a flag, not a silent wrong answer.

Interface mirrors OntarioGeocoderClient.geocode(address) -> dict | None so the
chain can treat it as a peer signal.

NOTE on scale: the public Nominatim endpoint allows ~1 req/sec and forbids
heavy bulk use. That's fine for the URL source (a handful of addresses) and as
a cross-check on RT primaries, but a full RT re-geocode (tens of thousands)
would need a self-hosted Nominatim or a commercial geocoder. Results are cached.
"""
from __future__ import annotations
import os
import time
import httpx

PUBLIC_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# Point at a local Nominatim (no rate limit) by setting CLEO_NOMINATIM_URL,
# e.g. http://localhost:8080/search. Falls back to the public endpoint.
DEFAULT_URL = os.environ.get("CLEO_NOMINATIM_URL", PUBLIC_NOMINATIM_URL)
USER_AGENT = "CleoTurbo/1.0 (commercial real estate parcel resolver; contact brandon.p.olsen@gmail.com)"
PUBLIC_DELAY = 1.1  # public Nominatim policy: <= 1 req/sec


def _is_local(url: str) -> bool:
    return any(h in url for h in ("localhost", "127.0.0.1", "0.0.0.0"))


class OSMGeocoderClient:
    """Nominatim forward-geocoder with dedup cache. Rate-limits the public
    endpoint; a local Nominatim (CLEO_NOMINATIM_URL) runs with no delay."""

    def __init__(self, base_url: str = DEFAULT_URL, delay: float | None = None, verbose: bool = False):
        self.base_url = base_url
        self.delay = (0.0 if _is_local(base_url) else PUBLIC_DELAY) if delay is None else delay
        self.verbose = verbose
        self._last_call = 0.0
        self._cache: dict[str, dict | None] = {}
        self.stats = {"calls": 0, "cache_hits": 0, "no_result": 0, "errors": 0}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def _throttle(self):
        elapsed = time.time() - self._last_call
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_call = time.time()

    def geocode(self, address: str) -> dict | None:
        """Geocode an address via Nominatim. Returns a dict shaped like the
        Ontario geocoder's (lat, lng, score, addr_type, match_addr, ...) or
        None. `score` is a 0-100 proxy derived from Nominatim importance; the
        raw fields are preserved under osm_* for auditing."""
        clean = (address or "").replace(", Canada", "").strip()
        if not clean:
            return None
        key = clean.upper()
        if key in self._cache:
            self.stats["cache_hits"] += 1
            return self._cache[key]

        self._throttle()
        try:
            with httpx.Client(timeout=20.0) as c:
                r = c.get(
                    self.base_url,
                    params={
                        "q": clean, "format": "jsonv2", "addressdetails": 1,
                        "limit": 3, "countrycodes": "ca",
                    },
                    headers={"User-Agent": USER_AGENT, "Accept-Language": "en-CA"},
                )
                r.raise_for_status()
                rows = r.json()
        except Exception as exc:  # noqa: BLE001
            self.stats["errors"] += 1
            if self.verbose:
                print(f"  OSM geocode error: {str(exc)[:120]}")
            self._cache[key] = None
            return None

        self.stats["calls"] += 1
        if not rows:
            self.stats["no_result"] += 1
            self._cache[key] = None
            return None

        result = self._to_result(clean, rows)
        self._cache[key] = result
        return result

    @staticmethod
    def _to_result(query: str, rows: list) -> dict:
        best = rows[0]
        addr = best.get("address", {}) or {}
        # Map Nominatim place type to an addr_type comparable to the Ontario one.
        osm_type = best.get("type", "")
        osm_class = best.get("category") or best.get("class", "")
        has_house = bool(addr.get("house_number"))
        if has_house and osm_class in ("place", "building", "shop", "amenity", "office"):
            addr_type = "PointAddress"
        elif has_house:
            addr_type = "PointAddress"
        elif osm_type in ("road", "residential", "living_street"):
            addr_type = "StreetName"
        elif osm_class == "highway":
            addr_type = "StreetAddress"
        else:
            addr_type = osm_type or osm_class or ""
        try:
            importance = float(best.get("importance", 0) or 0)
        except (TypeError, ValueError):
            importance = 0.0
        score = max(0, min(100, round(40 + importance * 100)))  # rough 0-100 proxy
        return {
            "lat": float(best["lat"]),
            "lng": float(best["lon"]),
            "score": score,
            "addr_type": addr_type,
            "match_addr": best.get("display_name", ""),
            "loc_name": f"osm:{osm_class}/{osm_type}",
            "city": addr.get("city") or addr.get("town") or addr.get("village") or "",
            "postal": addr.get("postcode", ""),
            "house": addr.get("house_number", ""),
            "street_name": addr.get("road", ""),
            "osm_importance": importance,
            "osm_class": osm_class,
            "osm_type": osm_type,
            "all_candidates": [
                {"lat": float(x["lat"]), "lng": float(x["lon"]),
                 "match_addr": x.get("display_name", ""),
                 "type": x.get("type", ""), "class": x.get("category") or x.get("class", "")}
                for x in rows
            ],
        }
