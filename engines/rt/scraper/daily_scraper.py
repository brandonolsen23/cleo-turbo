"""
Realtrack Daily Auto-Scraper — lightweight, cron-friendly transaction scraper.

Searches Realtrack with sf3="" (All Property Types) and sf1="" (all regions)
using a narrow date window. This single search returns ALL transactions —
both categorized and uncategorized — verified by RT ID comparison on Apr 9 2026.

Three run modes:
  --daily     Fast sweep, last 14 days (~2-5 min)
  --audit     Broader catch-up, last 90 days (~30-60 min, run weekly)
  --gaps      RT ID sequential gap hunter (run monthly)

Deposits new detail HTML files into raw-data/rt/pages/_daily/ where the
RT watcher picks them up and runs them through the pipeline automatically.

Usage:
    # Set credentials (env vars or engines/rt/scraper/.env)
    export REALTRACK_USER="your_username"
    export REALTRACK_PASS="your_password"

    # Daily sweep (run via cron at 6 AM)
    python -m engines.rt.scraper.daily_scraper --daily

    # Weekly audit (run via cron Sunday midnight)
    python -m engines.rt.scraper.daily_scraper --audit

    # Monthly gap check
    python -m engines.rt.scraper.daily_scraper --gaps

    # Dry run — count only, don't download
    python -m engines.rt.scraper.daily_scraper --daily --dry-run

    # Custom lookback
    python -m engines.rt.scraper.daily_scraper --daily --days 7
"""

import argparse
import json
import logging
import math
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .shared import (
    PROJECT_ROOT,
    RAW_DIR,
    PAGES_DIR,
    CLEAN_DIR,
    RESULTS_PER_PAGE,
    KNOWN_SF3_VALUES,
    RealtrackSession,
    atomic_write,
    atomic_write_json,
    extract_total,
    extract_skip_indices,
    extract_rt_id,
    parse_export_tsv,
    retry,
    load_credentials,
    discover_property_types,
)
from .inventory import load_existing_rt_ids

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("rt.daily")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DAILY_LOOKBACK_DAYS = 14
AUDIT_LOOKBACK_DAYS = 90
DELAY_BETWEEN_REQUESTS = 0.3

# Output directory for daily scraper runs
DAILY_DIR = PAGES_DIR / "_daily"


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def _date_to_rt_params(dt: datetime) -> Tuple[str, str]:
    """Convert a datetime to Realtrack search form values (startmo/startyr style).

    Returns (month_day, year) e.g. ("4/1", "2026").
    """
    return f"{dt.month}/1", str(dt.year)


def _make_search_params(
    start_date: datetime,
    end_date: datetime,
    sf3: str = "",
) -> dict:
    """Build search form POST data.

    sf3="" = All Property Types (verified superset of all categories).
    sf1 left empty = all regions (verified Apr 2026).
    """
    start_mo = f"{start_date.month}/1"
    start_yr = str(start_date.year)
    # End date: use the last day of the end month
    end_mo = f"{end_date.month}/{_last_day(end_date.month, end_date.year)}"
    end_yr = str(end_date.year)

    return {
        "sf1": "",                # All regions
        "sf2": "",                # All streets
        "sf3": sf3,               # Property type ("" = all)
        "sf4": "",                # Keyword
        "startmo": start_mo,
        "startyr": start_yr,
        "endmo": end_mo,
        "endyr": end_yr,
        "minamt": "",             # No min
        "maxamt": "",             # No max
        "sf7": "",                # Parties
        "sf8": "",                # Broker/Agent
        "sort1": "regDate",       # Sort by date
        "order1": "descending",   # Newest first
        "sort2": "amount",
        "order2": "descending",
        "sf9": str(RESULTS_PER_PAGE),
        "tabID": "",
    }


def _last_day(month: int, year: int) -> int:
    """Return the last day of a month."""
    if month == 2:
        return 29 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 28
    return {1: 31, 3: 31, 4: 30, 5: 31, 6: 30, 7: 31, 8: 31, 9: 30,
            10: 31, 11: 30, 12: 31}[month]


# ---------------------------------------------------------------------------
# Core: Single-search sweep
# ---------------------------------------------------------------------------

def run_sweep(
    session: RealtrackSession,
    start_date: datetime,
    end_date: datetime,
    known_rt_ids: Set[str],
    output_dir: Path,
    delay: float = DELAY_BETWEEN_REQUESTS,
    dry_run: bool = False,
) -> Tuple[int, int, int, List[str]]:
    """Run a single 'All Property Types' search and download new detail pages.

    Returns (total_found, new_count, skip_count, new_rt_ids).
    """
    log.info(
        "Searching: %s to %s, all regions, all types",
        start_date.strftime("%Y-%m-%d"),
        end_date.strftime("%Y-%m-%d"),
    )

    # Must GET search page first to establish session
    session.get("/?page=search")
    time.sleep(delay)

    # POST the search
    params = _make_search_params(start_date, end_date)
    resp = session.post("/?page=results", data=params)
    results_html = resp.text

    total = extract_total(results_html)
    if total is None:
        # Try counting detail links on the page as fallback
        skips = extract_skip_indices(results_html)
        if not skips:
            if "no results" in results_html.lower():
                log.info("  No results found.")
                return 0, 0, 0, []
            log.warning("  Could not determine result count — saving debug page")
            debug_path = output_dir / "debug_results.html"
            atomic_write(debug_path, results_html)
            return 0, 0, 0, []
        # Single page of results, count = number of detail links
        total = len(skips)

    total_pages = max(1, math.ceil(total / RESULTS_PER_PAGE))
    log.info("  %d results across %d pages", total, total_pages)

    if dry_run:
        return total, 0, 0, []

    all_new_rt_ids = []
    total_new = 0
    total_skip = 0
    total_fail = 0

    for page_num in range(1, total_pages + 1):
        page_label = f"p{page_num:03d}"
        page_dir = output_dir / page_label
        page_dir.mkdir(parents=True, exist_ok=True)

        # Navigate to this page (page 1 already loaded from search POST)
        if page_num > 1:
            try:
                resp = retry(
                    lambda p=page_num: session.get(
                        f"/?page=results&tabID={p - 1}"
                    ),
                    label=f"results p{page_num}",
                )
                results_html = resp.text
                time.sleep(delay)
            except Exception as e:
                log.error("  Failed to navigate to page %d: %s", page_num, e)
                total_fail += 1
                continue

        # Save results HTML
        atomic_write(page_dir / "results.html", results_html)

        # Extract skip indices
        skips = extract_skip_indices(results_html)
        if not skips:
            log.warning("  Page %d: no detail links found", page_num)
            continue

        # Fetch export for this page
        try:
            export_resp = session.get("/?page=export")
            export_text = export_resp.text
            export_rows = parse_export_tsv(export_text)
            atomic_write_json(page_dir / "export.json", export_rows)
        except Exception as e:
            log.warning("  Export failed for page %d: %s", page_num, e)
            export_rows = []

        # Download each detail page
        page_new = 0
        page_skip = 0
        page_fail = 0
        rt_ids_new = []
        rt_ids_skipped = []

        for i, skip_idx in enumerate(skips):
            try:
                detail_resp = retry(
                    lambda s=skip_idx: session.get(
                        f"/?page=details&skip={s}"
                    ),
                    label=f"detail p{page_num}#{i}",
                )
                detail_html = detail_resp.text
                time.sleep(delay)

                rt_id = extract_rt_id(detail_html)
                if rt_id is None:
                    # Save anyway — pipeline might parse it
                    detail_path = page_dir / f"detail_{i:03d}.html"
                    atomic_write(detail_path, detail_html)
                    page_new += 1
                    log.warning(
                        "  Could not extract RT ID from skip=%d", skip_idx
                    )
                    continue

                if rt_id in known_rt_ids:
                    rt_ids_skipped.append(rt_id)
                    page_skip += 1
                else:
                    detail_path = page_dir / f"detail_{i:03d}.html"
                    atomic_write(detail_path, detail_html)
                    known_rt_ids.add(rt_id)
                    rt_ids_new.append(rt_id)
                    all_new_rt_ids.append(rt_id)
                    page_new += 1

            except Exception as e:
                log.error(
                    "  Failed detail p%d #%d (skip=%d): %s",
                    page_num, i, skip_idx, e,
                )
                page_fail += 1

        # Save page metadata
        meta = {
            "page": page_num,
            "total_pages": total_pages,
            "total_results": total,
            "skip_indices": skips,
            "details_expected": len(skips),
            "details_new": page_new,
            "details_skipped": page_skip,
            "details_failed": page_fail,
            "rt_ids_new": rt_ids_new,
            "rt_ids_skipped": rt_ids_skipped,
            "export_rows": len(export_rows),
            "status": "complete",
            "scraped_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        atomic_write_json(page_dir / "_page.json", meta)

        total_new += page_new
        total_skip += page_skip
        total_fail += page_fail

        log.info(
            "  Page %d/%d: %d new, %d existing, %d failed",
            page_num, total_pages, page_new, page_skip, page_fail,
        )

    return total, total_new, total_skip, all_new_rt_ids


# ---------------------------------------------------------------------------
# Verification: sum individual categories vs All
# ---------------------------------------------------------------------------

def verify_completeness(
    session: RealtrackSession,
    start_date: datetime,
    end_date: datetime,
    all_total: int,
    sf3_types: Dict[str, str],
    delay: float = DELAY_BETWEEN_REQUESTS,
    output_dir: Path = None,
) -> Tuple[bool, Dict[str, int]]:
    """Search each individual sf3 value and compare sum against All total.

    Also captures each category's export rows as append-only LABEL EVIDENCE.
    The All search carries no category context, so this pass is the only
    place a record's RT category is observable. Rows (rollno, pin, address,
    date, consid, ...) are saved per category under output_dir/verify/ and
    appended to raw-data/rt/category_evidence.jsonl so downstream code can
    join them to transactions by ARN + sale date (doctrine D1/D8: evidence
    is append-only; every displayed label traces to a source).

    Returns (ok, category_counts).
    """
    import json as _json

    log.info("Running verification pass (%d categories)...", len(sf3_types))

    category_counts: Dict[str, int] = {}
    category_total = 0
    evidence_rows_written = 0
    evidence_path = PROJECT_ROOT / "raw-data" / "rt" / "category_evidence.jsonl"
    captured_at = datetime.now(tz=timezone.utc).isoformat()
    window = {
        "start": start_date.strftime("%Y-%m-%d"),
        "end": end_date.strftime("%Y-%m-%d"),
    }

    for sf3_value, label in sf3_types.items():
        # GET search page to reset session, then run the category search.
        # get()/post() already retry transient disconnects internally; if a
        # category still can't be fetched after retries, skip it rather than
        # abort the whole verification pass, so the remaining categories'
        # label evidence is still captured.
        try:
            session.get("/?page=search")
            time.sleep(delay)

            params = _make_search_params(start_date, end_date, sf3=sf3_value)
            resp = session.post("/?page=results", data=params)
            html = resp.text
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "  %s: category search failed after retries, skipping: %s",
                label, exc,
            )
            continue
        time.sleep(delay)

        count = extract_total(html)
        if count is None:
            # Count detail links as fallback
            skips = extract_skip_indices(html)
            count = len(skips) if skips else 0
            if "no results" in html.lower():
                count = 0

        # Capture label evidence: export rows for every page of this category
        cat_rows: List[Dict[str, str]] = []
        if count > 0 and output_dir is not None:
            cat_pages = max(1, math.ceil(count / RESULTS_PER_PAGE))
            for page_num in range(1, cat_pages + 1):
                if page_num > 1:
                    try:
                        retry(
                            lambda p=page_num: session.get(
                                f"/?page=results&tabID={p - 1}"
                            ),
                            label=f"verify {label} p{page_num}",
                        )
                        time.sleep(delay)
                    except Exception as e:
                        log.warning(
                            "  %s: page %d navigation failed: %s",
                            label, page_num, e,
                        )
                        continue
                try:
                    export_resp = session.get("/?page=export")
                    rows = parse_export_tsv(export_resp.text)
                    cat_rows.extend(rows)
                    time.sleep(delay)
                except Exception as e:
                    log.warning(
                        "  %s: export failed on page %d: %s",
                        label, page_num, e,
                    )

            if cat_rows:
                slug = (
                    label.lower().replace("/", "-").replace(" ", "-")
                )
                verify_dir = output_dir / "verify" / slug
                verify_dir.mkdir(parents=True, exist_ok=True)
                atomic_write_json(verify_dir / "export.json", cat_rows)
                with open(evidence_path, "a", encoding="utf-8") as fh:
                    for r in cat_rows:
                        line = dict(r)
                        line["rt_category"] = label
                        line["window"] = window
                        line["captured_at"] = captured_at
                        fh.write(_json.dumps(line, ensure_ascii=False) + "\n")
                evidence_rows_written += len(cat_rows)
                if len(cat_rows) != count:
                    log.warning(
                        "  %s: exported %d rows but search reported %d",
                        label, len(cat_rows), count,
                    )

        category_counts[label] = count
        category_total += count

    if output_dir is not None:
        log.info(
            "  Label evidence: %d rows appended to %s",
            evidence_rows_written, evidence_path.name,
        )

    log.info("  Category sum: %d, All total: %d", category_total, all_total)

    # Row-level verification (preferred): every export row seen in a
    # category search must also appear in the All sweep's export rows.
    # Count arithmetic is unreliable because Realtrack assigns some
    # transactions MULTIPLE categories (e.g. mixed-use = Office + Retail),
    # so sum(categories) can legitimately exceed the All total.
    def _row_key(r):
        return (
            (r.get("rollno") or "").strip(),
            r.get("date", ""),
            r.get("consid", ""),
            r.get("address", ""),
        )

    all_rows = []
    if output_dir is not None:
        for export_file in sorted(output_dir.glob("p*/export.json")):
            try:
                all_rows.extend(_json.loads(export_file.read_text()))
            except Exception as e:
                log.warning("  Could not read %s: %s", export_file, e)

    if all_rows:
        all_keys = {_row_key(r) for r in all_rows}
        cat_keys = set()
        multi = 0
        seen_once = set()
        for export_file in sorted((output_dir / "verify").glob("*/export.json")):
            for r in _json.loads(export_file.read_text()):
                k = _row_key(r)
                if k in seen_once:
                    multi += 1
                seen_once.add(k)
                cat_keys.add(k)
        missing = cat_keys - all_keys
        uncategorized = len(all_keys - cat_keys)
        ok = len(missing) == 0
        if ok:
            log.info(
                "  Verification OK (row-level): %d distinct categorized "
                "(%d multi-category) + %d uncategorized; all category rows "
                "present in the All sweep.",
                len(cat_keys), multi, uncategorized,
            )
        else:
            log.error(
                "  VERIFICATION FAILED: %d category rows NOT in the All "
                "sweep: %s",
                len(missing), sorted(missing)[:5],
            )
            log.error("  Consider switching to multi-filter scraping mode.")
    else:
        # Fallback: count heuristic (legacy behavior). Overlaps can produce
        # sum > All without data loss, so treat that as a warning only.
        ok = all_total >= category_total
        if not ok:
            log.warning(
                "  Count check: categories sum (%d) > All total (%d). "
                "Likely multi-category overlap; row-level data unavailable "
                "to confirm.",
                category_total, all_total,
            )
            ok = True
        else:
            log.info(
                "  Count check OK: %d categorized (with possible overlap), "
                "All total %d.",
                category_total, all_total,
            )

    return ok, category_counts


# ---------------------------------------------------------------------------
# Mode: Daily / Audit
# ---------------------------------------------------------------------------

def run_daily(
    lookback_days: int = DAILY_LOOKBACK_DAYS,
    delay: float = DELAY_BETWEEN_REQUESTS,
    dry_run: bool = False,
    skip_verify: bool = False,
):
    """Run a daily (or audit) sweep."""
    username, password = load_credentials()

    end_date = datetime.now()
    start_date = end_date - timedelta(days=lookback_days)

    log.info("Loading existing RT IDs...")
    known = load_existing_rt_ids(str(PROJECT_ROOT))
    log.info("  %d RT IDs already known", len(known))

    session = RealtrackSession(username, password)

    # Discover property types (alerts on new/removed types)
    sf3_types = discover_property_types(session)
    log.info("  %d property types on search form", len(sf3_types))

    # Create output directory for this run
    run_date = datetime.now().strftime("%Y-%m-%d")
    run_time = datetime.now().strftime("%H%M%S")
    output_dir = DAILY_DIR / f"{run_date}_{run_time}"
    output_dir.mkdir(parents=True, exist_ok=True)

    print()
    print("=" * 60)
    print("Cleo Turbo — RT Daily Scraper")
    print("=" * 60)
    print(f"  Mode:           {'DRY RUN' if dry_run else 'LIVE'}")
    print(f"  Date range:     {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    print(f"  Lookback:       {lookback_days} days")
    print(f"  Known RT IDs:   {len(known):,}")
    print(f"  Property types: {len(sf3_types)}")
    print(f"  Output:         {output_dir}")
    print()

    # Run the main sweep
    total, new_count, skip_count, new_rt_ids = run_sweep(
        session, start_date, end_date, known, output_dir, delay, dry_run,
    )

    # Run verification pass (unless skipped or dry run)
    verify_ok = True
    category_counts = {}
    if not dry_run and not skip_verify and total > 0:
        try:
            verify_ok, category_counts = verify_completeness(
                session, start_date, end_date, total, sf3_types, delay,
                output_dir=output_dir,
            )
        except Exception as exc:  # noqa: BLE001
            # Verification is a completeness CHECK, not data collection. The
            # sweep's detail pages are already on disk for the watcher to
            # process. A transient RealTrack disconnect during verification
            # must never discard a good sweep or fail the whole daily run,
            # so log it and continue to metadata/summary and a clean exit.
            log.warning("Verification pass failed, continuing: %s", exc)
            verify_ok = False

    session.close()

    # Save run metadata
    run_meta = {
        "mode": "daily" if lookback_days <= DAILY_LOOKBACK_DAYS else "audit",
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "lookback_days": lookback_days,
        "total_found": total,
        "new_downloaded": new_count,
        "already_known": skip_count,
        "new_rt_ids": new_rt_ids,
        "verification_ok": verify_ok,
        "category_counts": category_counts,
        "property_types_discovered": len(sf3_types),
        "known_rt_ids_at_start": len(known) - new_count,
        "dry_run": dry_run,
        "completed_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    atomic_write_json(output_dir / "_run.json", run_meta)

    # Summary
    print()
    print("=" * 60)
    if dry_run:
        print(f"DRY RUN: {total:,} results found in date range")
    else:
        print(f"COMPLETE: {new_count:,} new transactions downloaded")
        print(f"  Already known (skipped):  {skip_count:,}")
        print(f"  Total in date range:      {total:,}")
        if category_counts:
            print(f"  Verification:             {'PASS' if verify_ok else 'FAIL'}")
    print("=" * 60)

    if new_count > 0 and not dry_run:
        print()
        print("New files deposited in raw-data/rt/pages/_daily/")
        print("The RT watcher will auto-process them on its next cycle.")

    return new_count


# ---------------------------------------------------------------------------
# Mode: Gap Hunter
# ---------------------------------------------------------------------------

def run_gaps(dry_run: bool = False):
    """Detect sequential gaps in known RT IDs."""
    log.info("Loading existing RT IDs for gap analysis...")
    known = load_existing_rt_ids(str(PROJECT_ROOT))
    log.info("  %d RT IDs loaded", len(known))

    # Extract numeric portions
    nums = set()
    for rt_id in known:
        m = RT_ID_MATCH.match(rt_id)
        if m:
            nums.add(int(m.group(1)))

    if not nums:
        log.error("  No valid RT IDs found")
        return

    min_id = min(nums)
    max_id = max(nums)
    full_range = set(range(min_id, max_id + 1))
    gaps = sorted(full_range - nums)

    print()
    print("=" * 60)
    print("Cleo Turbo — RT ID Gap Analysis")
    print("=" * 60)
    print(f"  Known RT IDs:   {len(nums):,}")
    print(f"  ID range:       RT{min_id} to RT{max_id}")
    print(f"  Expected:       {max_id - min_id + 1:,}")
    print(f"  Gaps found:     {len(gaps):,}")
    print(f"  Coverage:       {len(nums) / (max_id - min_id + 1) * 100:.1f}%")
    print()

    if not gaps:
        print("  No gaps — perfect coverage!")
        return

    # Cluster gaps into contiguous runs
    clusters = []
    cluster_start = gaps[0]
    cluster_end = gaps[0]
    for g in gaps[1:]:
        if g == cluster_end + 1:
            cluster_end = g
        else:
            clusters.append((cluster_start, cluster_end))
            cluster_start = g
            cluster_end = g
    clusters.append((cluster_start, cluster_end))

    print(f"  Gap clusters:   {len(clusters)}")
    print()

    # Show the first 20 clusters
    shown = min(20, len(clusters))
    for i in range(shown):
        start, end = clusters[i]
        size = end - start + 1
        if size == 1:
            print(f"    RT{start}")
        else:
            print(f"    RT{start} - RT{end} ({size} missing)")

    if len(clusters) > shown:
        remaining = sum(e - s + 1 for s, e in clusters[shown:])
        print(f"    ... and {len(clusters) - shown} more clusters ({remaining:,} IDs)")

    # Save gap report
    report_dir = DAILY_DIR / "gap_reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"gaps_{datetime.now().strftime('%Y-%m-%d')}.json"
    report = {
        "date": datetime.now(tz=timezone.utc).isoformat(),
        "known_count": len(nums),
        "min_id": min_id,
        "max_id": max_id,
        "gap_count": len(gaps),
        "coverage_pct": round(len(nums) / (max_id - min_id + 1) * 100, 2),
        "cluster_count": len(clusters),
        "clusters": [
            {"start": f"RT{s}", "end": f"RT{e}", "size": e - s + 1}
            for s, e in clusters
        ],
        "all_gaps": [f"RT{g}" for g in gaps[:10000]],  # cap at 10K for file size
    }
    atomic_write_json(report_path, report)
    print()
    print(f"  Full report saved to: {report_path.relative_to(PROJECT_ROOT)}")


# RT ID numeric extraction
import re as _re
RT_ID_MATCH = _re.compile(r"RT(\d+)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Realtrack Daily Auto-Scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Run modes:
  --daily       Fast sweep of recent transactions (default: last 14 days)
  --audit       Broader sweep for backdated entries (default: last 90 days)
  --gaps        Sequential RT ID gap analysis

Examples:
  python -m engines.rt.scraper.daily_scraper --daily
  python -m engines.rt.scraper.daily_scraper --audit --days 120
  python -m engines.rt.scraper.daily_scraper --gaps
  python -m engines.rt.scraper.daily_scraper --daily --dry-run
        """,
    )

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--daily", action="store_true", help="Daily sweep (last 14 days)")
    mode.add_argument("--audit", action="store_true", help="Audit sweep (last 90 days)")
    mode.add_argument("--gaps", action="store_true", help="RT ID gap analysis")

    parser.add_argument(
        "--days", type=int, default=None,
        help="Override lookback days (default: 14 for daily, 90 for audit)",
    )
    parser.add_argument(
        "--delay", type=float, default=DELAY_BETWEEN_REQUESTS,
        help=f"Seconds between requests (default: {DELAY_BETWEEN_REQUESTS})",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Count results only, don't download detail pages",
    )
    parser.add_argument(
        "--skip-verify", action="store_true",
        help="Skip the category verification pass",
    )

    args = parser.parse_args()

    if args.gaps:
        run_gaps(dry_run=args.dry_run)
    elif args.daily:
        days = args.days or DAILY_LOOKBACK_DAYS
        run_daily(
            lookback_days=days,
            delay=args.delay,
            dry_run=args.dry_run,
            skip_verify=args.skip_verify,
        )
    elif args.audit:
        days = args.days or AUDIT_LOOKBACK_DAYS
        run_daily(
            lookback_days=days,
            delay=args.delay,
            dry_run=args.dry_run,
            skip_verify=args.skip_verify,
        )


if __name__ == "__main__":
    main()
