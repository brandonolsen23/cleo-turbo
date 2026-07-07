"""
Realtrack Historical Category Backfill — evidence-only label capture.

~29k historical transactions were collected via the "All Property Types"
search and carry no RT category. This script re-runs per-category searches
over historical date windows and appends each category's export rows to
raw-data/rt/category_evidence.jsonl in the EXACT same line format the
daily scraper's verify pass writes (export row fields + rt_category,
window {start, end}, captured_at) so downstream joins treat daily and
backfill evidence identically.

It does NOTHING else: no detail-page downloads, no raw page saves, no DB
writes, no edits to existing files (doctrine D1: evidence is append-only).

Resumable: raw-data/rt/category_backfill_state.json records every
(window, category) with status done/failed, rows captured, and timestamps.
Re-running skips done work; state is written atomically after each category.

Usage:
    # One explicit month window
    python -m engines.rt.scraper.backfill_categories --from 2019-06 --to 2019-06

    # See what would run (no network, no login)
    python -m engines.rt.scraper.backfill_categories --auto --dry-run

    # Nightly batch: auto-pick pending windows, stop after 40
    python -m engines.rt.scraper.backfill_categories --auto --limit-windows 40
"""

import argparse
import atexit
import json
import logging
import math
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .shared import (
    PROJECT_ROOT,
    RAW_DIR,
    RESULTS_PER_PAGE,
    KNOWN_SF3_VALUES,
    RealtrackSession,
    atomic_write,
    extract_total,
    extract_skip_indices,
    parse_export_tsv,
    retry,
    load_credentials,
    discover_property_types,
)
from .daily_scraper import _make_search_params, _last_day

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("rt.backfill")

EVIDENCE_PATH = RAW_DIR / "category_evidence.jsonl"
STATE_PATH = RAW_DIR / "category_backfill_state.json"
LOCK_PATH = RAW_DIR / "category_backfill.lock"
DB_PATH = PROJECT_ROOT / "data" / "cleo.db"
DEFAULT_DELAY = 0.5


# ---------------------------------------------------------------------------
# Window generation
# ---------------------------------------------------------------------------

def _parse_ym(s: str) -> Tuple[int, int]:
    """Parse 'YYYY-MM' into (year, month)."""
    try:
        year, month = s.split("-")
        year, month = int(year), int(month)
        assert 1 <= month <= 12
        return year, month
    except Exception:
        raise argparse.ArgumentTypeError(
            f"Expected YYYY-MM (e.g. 2019-06), got {s!r}"
        )


def build_windows(
    from_ym: Tuple[int, int],
    to_ym: Tuple[int, int],
    window_days: Optional[int] = None,
) -> List[Tuple[datetime, datetime]]:
    """Build inclusive (start, end) date windows covering the month range.

    Default: one window per calendar month. With --window-days N: N-day
    chunks from the 1st of the from-month to the last day of the to-month.
    """
    fy, fm = from_ym
    ty, tm = to_ym
    if (fy, fm) > (ty, tm):
        raise SystemExit(f"--from {fy}-{fm:02d} is after --to {ty}-{tm:02d}")

    range_start = datetime(fy, fm, 1)
    range_end = datetime(ty, tm, _last_day(tm, ty))

    windows: List[Tuple[datetime, datetime]] = []
    if window_days is None:
        y, m = fy, fm
        while (y, m) <= (ty, tm):
            windows.append(
                (datetime(y, m, 1), datetime(y, m, _last_day(m, y)))
            )
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    else:
        if window_days < 1:
            raise SystemExit("--window-days must be >= 1")
        cur = range_start
        step = timedelta(days=window_days)
        while cur <= range_end:
            end = min(cur + step - timedelta(days=1), range_end)
            windows.append((cur, end))
            cur = end + timedelta(days=1)
    return windows


def window_id(start: datetime, end: datetime) -> str:
    return f"{start:%Y-%m-%d}..{end:%Y-%m-%d}"


# ---------------------------------------------------------------------------
# State file (atomic, resumable)
# ---------------------------------------------------------------------------

def load_state() -> dict:
    if STATE_PATH.is_file():
        try:
            return json.loads(STATE_PATH.read_text())
        except Exception as e:
            raise SystemExit(
                f"State file {STATE_PATH} is corrupt ({e}); refusing to run. "
                "Fix or move it aside."
            )
    return {"windows": {}}


def save_state(state: dict) -> None:
    atomic_write(STATE_PATH, json.dumps(state, indent=2))


def window_pending_categories(
    state: dict, wid: str, sf3_types: Dict[str, str]
) -> List[str]:
    """Return sf3 values in this window not yet marked done."""
    cats = state["windows"].get(wid, {}).get("categories", {})
    return [
        v for v in sf3_types
        if cats.get(v, {}).get("status") != "done"
    ]


# ---------------------------------------------------------------------------
# Lockfile (single-instance safety)
# ---------------------------------------------------------------------------

def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def acquire_lock() -> None:
    if LOCK_PATH.exists():
        pid = None
        try:
            pid = int(LOCK_PATH.read_text().strip())
        except Exception:
            pass
        if pid is not None and _pid_alive(pid):
            raise SystemExit(
                f"Another backfill instance appears to be running "
                f"(pid {pid}, lockfile {LOCK_PATH}). Refusing to run."
            )
        log.warning("Removing stale lockfile (pid %s not running)", pid)
        LOCK_PATH.unlink()
    LOCK_PATH.write_text(str(os.getpid()))
    atexit.register(release_lock)


def release_lock() -> None:
    try:
        if LOCK_PATH.is_file() and LOCK_PATH.read_text().strip() == str(os.getpid()):
            LOCK_PATH.unlink()
    except OSError:
        pass


# ---------------------------------------------------------------------------
# --auto: derive month range from the DB (read-only, plain SELECT)
# ---------------------------------------------------------------------------

def db_sale_date_range() -> Tuple[Tuple[int, int], Tuple[int, int]]:
    """Read MIN/MAX sale_date of RT transactions from data/cleo.db.

    Read-only intent: only a single SELECT is issued. Tries a mode=ro URI
    connection first, falls back to a default connection if the OS refuses.
    """
    con = None
    try:
        con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        con.execute("SELECT 1")
    except sqlite3.OperationalError:
        if con is not None:
            con.close()
        con = sqlite3.connect(str(DB_PATH))
    try:
        row = con.execute(
            "SELECT MIN(sale_date), MAX(sale_date) FROM transactions "
            "WHERE source_id LIKE 'RT%'"
        ).fetchone()
    finally:
        con.close()
    if not row or not row[0]:
        raise SystemExit("No RT transactions found in data/cleo.db")
    lo, hi = row
    return (int(lo[:4]), int(lo[5:7])), (int(hi[:4]), int(hi[5:7]))


# ---------------------------------------------------------------------------
# Per-category fetch: search + paginate exports (evidence only)
# ---------------------------------------------------------------------------

def fetch_category_rows(
    session: RealtrackSession,
    start: datetime,
    end: datetime,
    sf3_value: str,
    label: str,
    delay: float,
) -> Tuple[int, List[Dict[str, str]]]:
    """Run one per-category search and collect export rows from every page.

    Mirrors daily_scraper.verify_completeness pagination exactly.
    Returns (reported_count, rows). Downloads NOTHING else.
    """
    session.get("/?page=search")
    time.sleep(delay)

    params = _make_search_params(start, end, sf3=sf3_value)
    # _make_search_params rounds to month boundaries; honor exact days for
    # non-month-aligned windows (--window-days mode).
    if start.day != 1 or end.day != _last_day(end.month, end.year):
        params["startmo"] = f"{start.month}/{start.day}"
        params["endmo"] = f"{end.month}/{end.day}"

    resp = session.post("/?page=results", data=params)
    html = resp.text
    time.sleep(delay)

    count = extract_total(html)
    if count is None:
        skips = extract_skip_indices(html)
        count = len(skips) if skips else 0
        if "no results" in html.lower():
            count = 0

    rows: List[Dict[str, str]] = []
    if count > 0:
        pages = max(1, math.ceil(count / RESULTS_PER_PAGE))
        for page_num in range(1, pages + 1):
            if page_num > 1:
                retry(
                    lambda p=page_num: session.get(
                        f"/?page=results&tabID={p - 1}"
                    ),
                    label=f"{label} p{page_num}",
                )
                time.sleep(delay)
            export_resp = retry(
                lambda: session.get("/?page=export"),
                label=f"{label} export p{page_num}",
            )
            rows.extend(parse_export_tsv(export_resp.text))
            time.sleep(delay)
        if len(rows) != count:
            log.warning(
                "  %s: exported %d rows but search reported %d",
                label, len(rows), count,
            )
    return count, rows


def append_evidence(
    rows: List[Dict[str, str]],
    label: str,
    window: Dict[str, str],
    captured_at: str,
) -> int:
    """Append export rows to category_evidence.jsonl (daily-scraper schema)."""
    if not rows:
        return 0
    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(EVIDENCE_PATH, "a", encoding="utf-8") as fh:
        for r in rows:
            line = dict(r)
            line["rt_category"] = label
            line["window"] = window
            line["captured_at"] = captured_at
            fh.write(json.dumps(line, ensure_ascii=False) + "\n")
    return len(rows)


# ---------------------------------------------------------------------------
# Main run
# ---------------------------------------------------------------------------

def run(args) -> None:
    if args.auto:
        db_lo, db_hi = db_sale_date_range()
        from_ym = args.from_ym or db_lo
        to_ym = args.to_ym or db_hi
        log.info(
            "Auto range from DB sale_date span: %04d-%02d .. %04d-%02d",
            *from_ym, *to_ym,
        )
    else:
        if not args.from_ym or not args.to_ym:
            raise SystemExit("--from and --to are required (or use --auto)")
        from_ym, to_ym = args.from_ym, args.to_ym

    windows = build_windows(from_ym, to_ym, args.window_days)
    state = load_state()

    # Dry-run and estimation use known sf3 values (no login needed);
    # live runs re-discover from the search form.
    sf3_types = dict(KNOWN_SF3_VALUES)

    pending = []
    for start, end in windows:
        wid = window_id(start, end)
        if window_pending_categories(state, wid, sf3_types):
            pending.append((start, end))

    if args.dry_run:
        print(f"\n{'WINDOW':<26} {'STATE':<10} CATEGORIES PENDING")
        for start, end in windows:
            wid = window_id(start, end)
            todo = window_pending_categories(state, wid, sf3_types)
            if not todo:
                st = "done"
            elif len(todo) < len(sf3_types):
                st = "partial"
            else:
                st = "pending"
            print(f"{wid:<26} {st:<10} {len(todo)}/{len(sf3_types)}")
        n_run = min(len(pending), args.limit_windows or len(pending))
        print(f"\nTotal windows:   {len(windows)}")
        print(f"Pending windows: {len(pending)}")
        print(f"Would run now:   {n_run} (--limit-windows)")
        print(
            f"Est. requests:   >= {n_run * len(sf3_types) * 3:,} "
            f"({len(sf3_types)} categories x ~3 requests/category/window, "
            f"more if a category spans multiple pages)"
        )
        return

    if args.limit_windows:
        pending = pending[: args.limit_windows]
    if not pending:
        print("Nothing to do — all windows in range are done.")
        return

    est = len(pending) * len(sf3_types) * 3
    print()
    print("=" * 60)
    print("Cleo Turbo — RT Category Backfill (evidence only)")
    print("=" * 60)
    print(f"  Windows this run:  {len(pending)} of {len(windows)} in range")
    print(f"  Categories:        {len(sf3_types)}")
    print(f"  Delay:             {args.delay}s")
    print(f"  Est. requests:     >= {est:,} (3+/category/window)")
    print(f"  Evidence file:     {EVIDENCE_PATH.relative_to(PROJECT_ROOT)}")
    print(f"  State file:        {STATE_PATH.relative_to(PROJECT_ROOT)}")
    print()

    acquire_lock()
    username, password = load_credentials()
    session = RealtrackSession(username, password)
    try:
        sf3_types = discover_property_types(session)
        log.info("%d property types on search form", len(sf3_types))

        total_rows = 0
        for w_idx, (start, end) in enumerate(pending, 1):
            wid = window_id(start, end)
            window = {"start": f"{start:%Y-%m-%d}", "end": f"{end:%Y-%m-%d}"}
            entry = state["windows"].setdefault(
                wid, {"categories": {}, "started_at": None}
            )
            if entry.get("started_at") is None:
                entry["started_at"] = datetime.now(tz=timezone.utc).isoformat()

            todo = window_pending_categories(state, wid, sf3_types)
            log.info(
                "Window %d/%d %s — %d categories to fetch",
                w_idx, len(pending), wid, len(todo),
            )

            window_rows = 0
            for sf3_value in todo:
                label = sf3_types[sf3_value]
                captured_at = datetime.now(tz=timezone.utc).isoformat()
                try:
                    count, rows = fetch_category_rows(
                        session, start, end, sf3_value, label, args.delay,
                    )
                    n = append_evidence(rows, label, window, captured_at)
                    entry["categories"][sf3_value] = {
                        "label": label,
                        "status": "done",
                        "reported_count": count,
                        "rows": n,
                        "completed_at": datetime.now(tz=timezone.utc).isoformat(),
                    }
                    window_rows += n
                    log.info("  %-22s %5d rows", label, n)
                except Exception as e:
                    entry["categories"][sf3_value] = {
                        "label": label,
                        "status": "failed",
                        "error": str(e)[:300],
                        "failed_at": datetime.now(tz=timezone.utc).isoformat(),
                    }
                    log.error("  %-22s FAILED: %s", label, e)
                save_state(state)

            still_todo = window_pending_categories(state, wid, sf3_types)
            entry["status"] = "done" if not still_todo else "partial"
            entry["rows"] = sum(
                c.get("rows", 0) for c in entry["categories"].values()
            )
            entry["completed_at"] = datetime.now(tz=timezone.utc).isoformat()
            save_state(state)
            total_rows += window_rows
            log.info(
                "Window %s %s: %d evidence rows appended",
                wid, entry["status"].upper(), window_rows,
            )
    finally:
        session.close()
        release_lock()

    print()
    print("=" * 60)
    print(f"COMPLETE: {len(pending)} window(s), {total_rows:,} evidence rows appended")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Realtrack historical category backfill (evidence only)",
    )
    parser.add_argument(
        "--from", dest="from_ym", type=_parse_ym, default=None,
        metavar="YYYY-MM", help="First month to cover (inclusive)",
    )
    parser.add_argument(
        "--to", dest="to_ym", type=_parse_ym, default=None,
        metavar="YYYY-MM", help="Last month to cover (inclusive)",
    )
    parser.add_argument(
        "--window-days", type=int, default=None,
        help="Window size in days (default: one calendar month per window)",
    )
    parser.add_argument(
        "--delay", type=float, default=DEFAULT_DELAY,
        help=f"Seconds between requests (default: {DEFAULT_DELAY})",
    )
    parser.add_argument(
        "--limit-windows", type=int, default=None,
        help="Stop after N windows this run (for overnight batching)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="List windows with pending/done state; no network, no login",
    )
    parser.add_argument(
        "--auto", action="store_true",
        help="Derive month range from data/cleo.db sale_date span (read-only) "
             "and skip windows already covered in the state file",
    )
    run(parser.parse_args())


if __name__ == "__main__":
    main()
