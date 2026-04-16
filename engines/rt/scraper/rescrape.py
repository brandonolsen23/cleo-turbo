"""
Re-scrape a single RT detail page from Realtrack.

Searches for the transaction by date range, pages through results until
the target RT ID is found, then overwrites the original HTML file in place.

Usage:
    python -m engines.rt.scraper.rescrape RT198249
    python -m engines.rt.scraper.rescrape RT198249 --source-folder _daily/2026-04-09_154735/p002 --position 23
    python -m engines.rt.scraper.rescrape RT198249 --dry-run

The --source-folder and --position args tell the script where the original
HTML lives so it can overwrite in place. If not provided, it saves to a
new _daily/_rescrape/ folder instead.
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from engines.rt.scraper.shared import (
    PAGES_DIR,
    RealtrackSession,
    atomic_write,
    atomic_write_json,
    extract_rt_id,
    extract_skip_indices,
    extract_total,
    load_credentials,
    parse_export_tsv,
    retry,
    RESULTS_PER_PAGE,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("rt.rescrape")

DELAY = 1.5  # seconds between requests


def _make_search_params(start_date, end_date):
    """Build search form params for a date range."""
    start_mo = f"{start_date.month}/1"
    start_yr = str(start_date.year)
    last_day_map = {1:31,2:28,3:31,4:30,5:31,6:30,7:31,8:31,9:30,10:31,11:30,12:31}
    end_day = last_day_map.get(end_date.month, 30)
    if end_date.month == 2 and (end_date.year % 4 == 0 and (end_date.year % 100 != 0 or end_date.year % 400 == 0)):
        end_day = 29
    end_mo = f"{end_date.month}/{end_day}"
    end_yr = str(end_date.year)

    return {
        "sf1": "", "sf2": "", "sf3": "", "sf4": "",
        "startmo": start_mo, "startyr": start_yr,
        "endmo": end_mo, "endyr": end_yr,
        "minamt": "", "maxamt": "",
        "sf7": "", "sf8": "",
        "sort1": "regDate", "order1": "descending",
        "sort2": "amount", "order2": "descending",
        "sf9": str(RESULTS_PER_PAGE), "tabID": "",
    }


def rescrape_rt_id(rt_id, session, source_folder=None, position=None, dry_run=False):
    """Re-download a single RT detail page from Realtrack.

    Strategy:
    1. Search a broad date range (last 120 days) to find the RT ID.
    2. Page through results, fetching each detail page until we find ours.
    3. Overwrite the original HTML file if source_folder/position are known.
       Otherwise save to _daily/_rescrape/.

    Returns the path to the saved HTML file, or None on failure.
    """
    log.info("Re-scraping %s...", rt_id)

    # Search a broad window — we don't know exact date
    end_date = datetime.now()
    start_date = end_date - timedelta(days=120)

    # Establish session on search page
    session.get("/?page=search")
    time.sleep(DELAY)

    # POST the search
    params = _make_search_params(start_date, end_date)
    resp = session.post("/?page=results", data=params)
    results_html = resp.text
    time.sleep(DELAY)

    total = extract_total(results_html)
    if total is None:
        skips = extract_skip_indices(results_html)
        total = len(skips) if skips else 0

    if total == 0:
        log.error("Search returned 0 results")
        return None

    total_pages = max(1, -(-total // RESULTS_PER_PAGE))  # ceil division
    log.info("Search returned %d results across %d pages", total, total_pages)

    # Page through and look for our RT ID
    for page_num in range(1, total_pages + 1):
        if page_num > 1:
            try:
                resp = retry(
                    lambda p=page_num: session.get(f"/?page=results&tabID={p - 1}"),
                    label=f"results p{page_num}",
                )
                results_html = resp.text
                time.sleep(DELAY)
            except Exception as e:
                log.warning("Failed to navigate to page %d: %s", page_num, e)
                continue

        skips = extract_skip_indices(results_html)
        if not skips:
            continue

        for i, skip_idx in enumerate(skips):
            try:
                detail_resp = retry(
                    lambda s=skip_idx: session.get(f"/?page=details&skip={s}"),
                    label=f"detail p{page_num}#{i}",
                )
                detail_html = detail_resp.text
                time.sleep(DELAY)

                found_id = extract_rt_id(detail_html)
                if found_id == rt_id:
                    log.info("Found %s on page %d, skip=%d", rt_id, page_num, skip_idx)

                    if dry_run:
                        log.info("DRY RUN — would save HTML (%d bytes)", len(detail_html))
                        return "dry-run"

                    # Determine save path
                    if source_folder and position is not None:
                        # Overwrite original file in place
                        save_path = PAGES_DIR / source_folder / f"detail_{int(position):03d}.html"
                    else:
                        # Save to _rescrape/ folder
                        rescrape_dir = PAGES_DIR / "_daily" / "_rescrape"
                        rescrape_dir.mkdir(parents=True, exist_ok=True)
                        save_path = rescrape_dir / f"{rt_id}.html"

                    atomic_write(save_path, detail_html)
                    log.info("Saved to %s (%d bytes)", save_path, len(detail_html))

                    # Also try to grab the export data for this page
                    try:
                        export_resp = session.get("/?page=export")
                        export_rows = parse_export_tsv(export_resp.text)
                        if source_folder:
                            export_path = PAGES_DIR / source_folder / "export.json"
                            atomic_write_json(export_path, export_rows)
                            log.info("Updated export.json (%d rows)", len(export_rows))
                    except Exception as e:
                        log.warning("Could not update export: %s", e)

                    return str(save_path)

            except Exception as e:
                log.warning("Failed detail p%d #%d (skip=%d): %s", page_num, i, skip_idx, e)
                continue

    log.error("RT ID %s not found in %d pages of results", rt_id, total_pages)
    return None


def main():
    parser = argparse.ArgumentParser(description="Re-scrape a single RT detail page")
    parser.add_argument("rt_id", help="RT ID to re-scrape (e.g., RT198249)")
    parser.add_argument("--source-folder", help="Original source folder path for in-place overwrite")
    parser.add_argument("--position", type=int, help="Original position number for in-place overwrite")
    parser.add_argument("--dry-run", action="store_true", help="Search but don't save")
    args = parser.parse_args()

    rt_id = args.rt_id.strip().upper()
    if not rt_id.startswith("RT") or not rt_id[2:].isdigit():
        print(f"Invalid RT ID: {rt_id}")
        sys.exit(1)

    username, password = load_credentials()
    session = RealtrackSession(username, password)

    result = rescrape_rt_id(
        rt_id=rt_id,
        session=session,
        source_folder=args.source_folder,
        position=args.position,
        dry_run=args.dry_run,
    )

    if result:
        print(f"OK: {result}")
    else:
        print(f"FAILED: Could not find {rt_id}")
        sys.exit(1)


if __name__ == "__main__":
    main()
