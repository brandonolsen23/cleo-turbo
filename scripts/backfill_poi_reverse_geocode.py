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

# Make sure the engines/ package is importable.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "engines" / "rt"))

from parcel_resolver.ontario_geocoder import OntarioGeocoderClient, ThrottleError  # noqa: E402

CACHE_DIR = ROOT / "clean-data" / "reverse_geocode"
LOG_PATH = CACHE_DIR / "_log.jsonl"
DB_PATH = ROOT / "data" / "cleo.db"


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
        with OntarioGeocoderClient(headless=True, verbose=False) as client:
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

                if processed % 100 == 0:
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
