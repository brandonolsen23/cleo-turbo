"""Backfill POI street addresses via Ontario reverse-geocoding.

Targets every ``pois`` row whose ``address_source`` is NULL (or
``'reverse_geocode_failed'`` if ``--retry-failed`` is set), calls the
Ontario ``reverseGeocode`` endpoint via
:class:`OntarioGeocoderClient`, and writes the resulting address back
to the row plus a JSON cache file so re-runs and future compiler
passes don't re-spend geocoder calls.

Resumable: the script picks up wherever it left off based on the
``address_source`` column. Throttle-aware: hard-stops if
``OntarioGeocoderClient`` raises ``ThrottleError`` (CLAUDE.md rule).

Usage::

    # Spot-test a single POI by id
    python scripts/backfill_poi_reverse_geocode.py --poi-id OSM_48752

    # Backfill the next N POIs (handy for an exploratory run)
    python scripts/backfill_poi_reverse_geocode.py --limit 50

    # Full backfill (no limit). Run as a background job.
    python scripts/backfill_poi_reverse_geocode.py

    # Retry POIs that previously came back with no candidate
    python scripts/backfill_poi_reverse_geocode.py --retry-failed
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

import requests

# Make sure the engines/ package is importable.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "engines" / "rt"))

CACHE_DIR = ROOT / "clean-data" / "reverse_geocode"
LOG_PATH = CACHE_DIR / "_log.jsonl"
DB_PATH = ROOT / "data" / "cleo.db"


# ----------------------------------------------------------------
# Direct-HTTP Ontario reverseGeocode client.
#
# The public AgMaps proxy (`proxy.ashx`) accepts requests for the
# internal Ontario_Address_Locator GeocodeServer without requiring a
# session token, as long as the request carries the right Origin /
# Referer headers (the proxy whitelists those). This is ~10–20× faster
# than the Playwright-based OntarioGeocoderClient because there's no JS
# evaluation hop.
# ----------------------------------------------------------------

PROXY_URL = "https://www.lioapplications.lrc.gov.on.ca/services/proxy/proxy.ashx"
GEOCODER_BASE = (
    "https://intra.ws.lioservices.lrc.gov.on.ca/arcgis1/rest/services"
    "/Geocoders/Ontario_Address_Locator/GeocodeServer"
)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Referer": "https://www.lioapplications.lrc.gov.on.ca/AgMaps/Index.html",
    "Origin": "https://www.lioapplications.lrc.gov.on.ca",
    "Accept": "application/json, text/plain, */*",
}

REQUEST_DELAY = 0.6    # seconds between calls (~1.7 req/sec)
MAX_CONSECUTIVE_ERRORS = 5
ERROR_RATE_WINDOW = 100
MAX_ERROR_RATE = 0.10


class ThrottleError(Exception):
    """Raised when rate limiting is detected. Pipeline should STOP."""


class HttpReverseGeocoder:
    """Stateless direct-HTTP client for Ontario reverseGeocode."""

    def __init__(self, delay: float = REQUEST_DELAY) -> None:
        self.delay = delay
        self._session = requests.Session()
        self._session.headers.update(HEADERS)
        self._last_call_ts = 0.0
        self._consec_errors = 0
        self._error_window: list[bool] = []

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> "HttpReverseGeocoder":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    def _throttle(self) -> None:
        elapsed = time.time() - self._last_call_ts
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_call_ts = time.time()

    def _record(self, success: bool) -> None:
        if success:
            self._consec_errors = 0
        else:
            self._consec_errors += 1
        self._error_window.append(success)
        if len(self._error_window) > ERROR_RATE_WINDOW:
            self._error_window = self._error_window[-ERROR_RATE_WINDOW:]
        if self._consec_errors >= MAX_CONSECUTIVE_ERRORS:
            raise ThrottleError(
                f"{self._consec_errors} consecutive errors — geocoder hard-stop"
            )
        if len(self._error_window) >= ERROR_RATE_WINDOW:
            err_rate = 1.0 - (sum(self._error_window) / len(self._error_window))
            if err_rate > MAX_ERROR_RATE:
                raise ThrottleError(
                    f"error rate {err_rate:.0%} > {MAX_ERROR_RATE:.0%} — geocoder hard-stop"
                )

    def reverse_geocode(self, lat: float, lng: float) -> dict | None:
        self._throttle()
        inner = f"{GEOCODER_BASE}/reverseGeocode"
        params = {
            "location": f"{float(lng)},{float(lat)}",
            "outSR": "4326",
            "f": "json",
        }
        qs = "&".join(f"{k}={requests.utils.quote(str(v))}" for k, v in params.items())
        url = f"{PROXY_URL}?{inner}?{qs}"
        try:
            resp = self._session.get(url, timeout=20)
        except requests.RequestException as exc:
            print(f"  ✗ network error: {exc}")
            self._record(False)
            return None

        if resp.status_code != 200:
            print(f"  ✗ HTTP {resp.status_code}: {resp.text[:160]}")
            self._record(False)
            return None

        try:
            data = resp.json()
        except ValueError:
            print(f"  ✗ non-JSON response: {resp.text[:160]}")
            self._record(False)
            return None

        if "error" in data:
            err = data["error"] or {}
            msg = err.get("message", "")
            details = " ".join(err.get("details", []) or [])
            combined = f"{msg} {details}".lower()
            # "Unable to find address" is the standard ESRI no-result
            # signal — the API processed the request fine, there's just
            # nothing in the address grid at that point. Don't count
            # toward the throttle window.
            if (
                "unable to find" in combined
                or "no candidate" in combined
                or "no address" in combined
            ):
                self._record(True)
                return None
            print(f"  ✗ API error: {msg}")
            self._record(False)
            return None

        addr = data.get("address") or {}
        loc = data.get("location") or {}
        street = (
            addr.get("Match_addr")
            or addr.get("Address")
            or addr.get("Street")
            or ""
        ).strip() if addr else ""

        city = addr.get("City") or addr.get("Place") or ""
        state = addr.get("Region") or addr.get("State") or ""
        postal = addr.get("Postal") or addr.get("ZIP") or ""
        loc_name = addr.get("Loc_name", "") or ""

        # Accept postal-only results — even just a postal code lets the
        # user paste it into a property search. Only return None when we
        # have literally nothing usable.
        if not (street or postal or city):
            self._record(True)
            return None

        match_parts = [street] if street else []
        tail = ", ".join(p for p in (city, state, postal) if p)
        if tail:
            match_parts.append(tail)
        if loc_name.startswith("PARCEL"):
            score, addr_type = 95, "PointAddress"
        elif loc_name.startswith("Street"):
            score, addr_type = 85, "StreetAddress"
        elif "Postal" in loc_name:
            # Postal-only: lower score since it's just the postal area.
            score, addr_type = 50, "Postal"
        else:
            score, addr_type = 70, ""

        self._record(True)
        return {
            "match_addr": ", ".join(match_parts) if match_parts else postal,
            "addr_type": addr_type,
            "street": street,
            "city": city,
            "state": state,
            "postal": postal,
            "loc_name": loc_name,
            "lat": loc.get("y"),
            "lng": loc.get("x"),
            "score": score,
        }


def cache_key(lat: float, lng: float) -> str:
    return f"{round(float(lat), 6):.6f},{round(float(lng), 6):.6f}"


def cache_path(lat: float, lng: float) -> Path:
    return CACHE_DIR / f"{cache_key(lat, lng)}.json"


def cache_read(lat: float, lng: float) -> dict | None:
    p = cache_path(lat, lng)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def cache_write(lat: float, lng: float, payload: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path(lat, lng).write_text(json.dumps(payload))


def log_event(event: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a") as f:
        f.write(json.dumps(event) + "\n")


def format_address(rev: dict) -> str:
    """Build a single street-address string from a reverseGeocode result."""
    if not rev:
        return ""
    match = (rev.get("match_addr") or "").strip()
    if match:
        return match
    street = (rev.get("street") or "").strip()
    tail = ", ".join(p for p in (rev.get("city"), rev.get("state"), rev.get("postal")) if p)
    return f"{street}, {tail}".strip(", ").strip() if tail else street


def select_targets(
    conn: sqlite3.Connection,
    *,
    poi_id: str | None,
    retry_failed: bool,
    limit: int | None,
) -> list[tuple[str, float, float]]:
    if poi_id:
        rows = conn.execute(
            "SELECT id, lat, lng FROM pois WHERE id = ?", (poi_id,)
        ).fetchall()
        return [(r[0], r[1], r[2]) for r in rows if r[1] is not None and r[2] is not None]

    where = ["lat IS NOT NULL", "lng IS NOT NULL"]
    if retry_failed:
        where.append("address_source IS NULL OR address_source = 'reverse_geocode_failed'")
    else:
        where.append("address_source IS NULL")
    sql = f"SELECT id, lat, lng FROM pois WHERE {' AND '.join(where)} ORDER BY id"
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    return [(r[0], r[1], r[2]) for r in conn.execute(sql).fetchall()]


def apply_to_db(
    conn: sqlite3.Connection,
    poi_id: str,
    address: str,
    source: str,
    extra: dict | None = None,
) -> None:
    fields = ["address = ?", "address_source = ?"]
    args: list = [address, source]
    if extra and extra.get("city"):
        fields.append("city = COALESCE(NULLIF(city, ''), ?)")
        args.append(extra["city"])
    args.append(poi_id)
    conn.execute(f"UPDATE pois SET {', '.join(fields)} WHERE id = ?", args)


def run(args: argparse.Namespace) -> int:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    targets = select_targets(
        conn,
        poi_id=args.poi_id,
        retry_failed=args.retry_failed,
        limit=args.limit,
    )

    if not targets:
        print("Nothing to backfill.")
        return 0

    print(f"Backfill targets: {len(targets):,}")

    # Pre-populate from cache (zero geocoder calls).
    pre_hits = 0
    pending: list[tuple[str, float, float]] = []
    for poi_id, lat, lng in targets:
        cached = cache_read(lat, lng)
        if cached is None:
            pending.append((poi_id, lat, lng))
            continue
        rev = cached.get("result")
        if rev is None:
            apply_to_db(conn, poi_id, "", "reverse_geocode_failed")
        else:
            apply_to_db(conn, poi_id, format_address(rev), "reverse_geocoded", rev)
        pre_hits += 1
    if pre_hits:
        conn.commit()
        print(f"  cache hits applied: {pre_hits:,}")

    if not pending:
        return 0

    if args.dry_run:
        print(f"  --dry-run: would call geocoder for {len(pending):,} more POIs")
        return 0

    print(f"  geocoder calls needed: {len(pending):,}")

    start = time.time()
    processed = 0
    successes = 0
    failures = 0

    log_event({
        "event": "run_start",
        "ts": time.time(),
        "targets": len(targets),
        "pre_hits": pre_hits,
        "pending": len(pending),
    })

    try:
        with HttpReverseGeocoder() as client:
            for poi_id, lat, lng in pending:
                try:
                    rev = client.reverse_geocode(lat, lng)
                except ThrottleError as exc:
                    print(f"\n  ⚠ throttle hard-stop: {exc}")
                    log_event({"event": "throttle_stop", "ts": time.time(), "msg": str(exc)})
                    break

                cache_write(lat, lng, {
                    "lat": lat,
                    "lng": lng,
                    "result": rev,
                    "ts": time.time(),
                })

                if rev:
                    apply_to_db(conn, poi_id, format_address(rev), "reverse_geocoded", rev)
                    successes += 1
                else:
                    apply_to_db(conn, poi_id, "", "reverse_geocode_failed")
                    failures += 1
                processed += 1

                if processed % 200 == 0:
                    conn.commit()
                    elapsed = time.time() - start
                    rate = processed / elapsed if elapsed else 0
                    eta_min = (len(pending) - processed) / rate / 60 if rate else 0
                    print(
                        f"  [{processed:,}/{len(pending):,}] "
                        f"ok:{successes:,} fail:{failures:,} "
                        f"{rate:.2f}/s ETA:{eta_min:.0f}m"
                    )
                    log_event({
                        "event": "progress",
                        "ts": time.time(),
                        "processed": processed,
                        "successes": successes,
                        "failures": failures,
                    })
    finally:
        conn.commit()
        log_event({
            "event": "run_end",
            "ts": time.time(),
            "processed": processed,
            "successes": successes,
            "failures": failures,
        })

    elapsed = time.time() - start
    print(
        f"\nDone. processed={processed:,} ok={successes:,} fail={failures:,} "
        f"in {elapsed/60:.1f}m"
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--poi-id", help="Spot-test a single POI by id")
    parser.add_argument("--limit", type=int, help="Process at most N POIs")
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Also retry POIs marked reverse_geocode_failed",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Apply cache hits but don't call geocoder for misses",
    )
    args = parser.parse_args()
    sys.exit(run(args))


if __name__ == "__main__":
    main()
