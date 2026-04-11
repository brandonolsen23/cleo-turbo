"""
Realtrack Uncategorized Transaction Scraper — captures the ~60K transactions
that the category-based scraper missed.

The original V2 scraper browsed each region × property-type combo (sf3 = specific
type value like "retailBldg", "indBldg", etc.). This captured 126K transactions
across 594 combos — but only transactions Realtrack assigned to a category.

Searching with sf3="" returns UNCATEGORIZED transactions — ones Realtrack hasn't
assigned to any property type. These ~60K records include transactions like
RT158755 (1014 Talbot St, St Thomas) that simply don't appear in any category list.

This scraper uses httpx (same as the original V2 scraper) to:
  1. Log in to Realtrack with your credentials
  2. For each region: POST search with sf3="" (uncategorized), Jan 1996 – Dec 2026
  3. Page through results sequentially (RT requires server-side session state)
  4. For each detail page: extract RT ID, skip if already in clean-data/
  5. Save new details into raw-data/rt/pages/{Region}/all/pNNN/

Resumable: tracks progress in raw-data/rt/search_progress.json.

Usage:
    # Set credentials as environment variables
    export REALTRACK_USER="your_username"
    export REALTRACK_PASS="your_password"

    # Full run — all regions
    python3 -m engines.rt.scraper.search_scraper

    # Specific regions only
    python3 -m engines.rt.scraper.search_scraper --regions "08,27,50"

    # Resume from where you left off
    python3 -m engines.rt.scraper.search_scraper --resume

    # Dry run — count results per region, don't download details
    python3 -m engines.rt.scraper.search_scraper --dry-run

    # Faster/slower throttle
    python3 -m engines.rt.scraper.search_scraper --delay 0.3
"""

import argparse
import json
import logging
import math
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import httpx

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
RAW_DIR = PROJECT_ROOT / "raw-data" / "rt"
PAGES_DIR = RAW_DIR / "pages"
PROGRESS_FILE = RAW_DIR / "search_progress.json"
CLEAN_DIR = PROJECT_ROOT / "clean-data" / "rt"

REALTRACK_BASE = "https://realtrack.com"
RESULTS_PER_PAGE = 50

# Pagination total: .pagination(15750, {
_TOTAL_PATTERN = re.compile(r"\.pagination\((\d+),")
# RT ID from detail footer
_RT_ID_PATTERN = re.compile(r"RT\d+")
# Detail link skip indices
_SKIP_PATTERN = re.compile(r'href="\?page=details&(?:amp;)?skip=(\d+)"')

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("rt.search_scraper")

# Region ID → (label, folder_name)
# Sourced from the original manifest. The sf1 field uses region IDs (01-50).
REGIONS: Dict[str, Tuple[str, str]] = {
    "01": ("ALGOMA", "Algoma"),
    "02": ("BRANT", "Brant"),
    "03": ("BRUCE", "Bruce"),
    "04": ("COCHRANE", "Cochrane"),
    "05": ("DUFFERIN COUNTY", "Dufferin_County"),
    "06": ("DUNDAS COUNTY", "Dundas_County"),
    "07": ("DURHAM REGION", "Durham_Region"),
    "08": ("ELGIN COUNTY", "Elgin_County"),
    "09": ("ESSEX COUNTY", "Essex_County"),
    "10": ("FRONTENAC COUNTY", "Frontenac_County"),
    "11": ("GLENGARRY COUNTY", "Glengarry_County"),
    "12": ("GRENVILLE COUNTY", "Grenville_County"),
    "13": ("GREY COUNTY", "Grey_County"),
    "14": ("HALDIMAND COUNTY", "Haldimand_County"),
    "15": ("HALIBURTON", "Haliburton"),
    "16": ("HALTON REGION", "Halton_Region"),
    "17": ("HAMILTON-WENTWORTH", "Hamilton-Wentworth"),
    "18": ("HASTINGS COUNTY", "Hastings_County"),
    "19": ("HURON COUNTY", "Huron_County"),
    "20": ("KENORA", "Kenora"),
    "21": ("KENT COUNTY", "Kent_County"),
    "22": ("KITCHENER-WATERLOO", "Kitchener-Waterloo"),
    "23": ("LAMBTON", "Lambton"),
    "24": ("LANARK COUNTY", "Lanark_County"),
    "25": ("LEEDS", "Leeds"),
    "26": ("LENNOX COUNTY", "Lennox_County"),
    "27": ("METRO TORONTO", "Metro_Toronto"),
    "28": ("MUSKOKA", "Muskoka"),
    "29": ("NIPISSING DISTRICT", "Nipissing_District"),
    "30": ("NORFOLK", "Norfolk"),
    "31": ("NORTHUMBERLAND", "Northumberland"),
    "32": ("OTTAWA-CARLETON", "Ottawa-Carleton"),
    "33": ("OXFORD COUNTY", "Oxford_County"),
    "34": ("PARRY SOUND", "Parry_Sound"),
    "35": ("PEEL REGION", "Peel_Region"),
    "36": ("PERTH COUNTY", "Perth_County"),
    "37": ("PETERBOROUGH COUNTY", "Peterborough_County"),
    "38": ("PRESCOTT", "Prescott"),
    "39": ("PRINCE EDWARD", "Prince_Edward"),
    "40": ("RENFREW", "Renfrew"),
    "41": ("RUSSELL TOWNSHIP", "Russell_Township"),
    "42": ("SIMCOE COUNTY", "Simcoe_County"),
    "43": ("STORMONT", "Stormont"),
    "44": ("SUDBURY", "Sudbury"),
    "45": ("THUNDER BAY", "Thunder_Bay"),
    "46": ("TIMISKAMING", "Timiskaming"),
    "47": ("VICTORIA", "Victoria"),
    "48": ("WATERLOO REGION", "Waterloo_Region"),
    "49": ("WELLINGTON", "Wellington"),
    "50": ("YORK REGION", "York_Region"),
}


# ---------------------------------------------------------------------------
# Atomic file writes (same pattern as V2 scraper)
# ---------------------------------------------------------------------------

def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, str(path))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _atomic_write_json(path: Path, data) -> None:
    _atomic_write(path, json.dumps(data, indent=2))


# ---------------------------------------------------------------------------
# Progress tracking
# ---------------------------------------------------------------------------

def _load_progress() -> dict:
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {
        "started_at": datetime.now(tz=timezone.utc).isoformat(),
        "regions_done": [],
        "current_region": None,
        "current_page": 0,
        "stats": {
            "regions_scraped": 0,
            "pages_scraped": 0,
            "details_new": 0,
            "details_skipped": 0,
            "details_failed": 0,
        },
    }


def _save_progress(progress: dict) -> None:
    _atomic_write_json(PROGRESS_FILE, progress)


# ---------------------------------------------------------------------------
# Inventory: what RT IDs do we already have?
# ---------------------------------------------------------------------------

def _load_known_rt_ids() -> set:
    """Load all known RT IDs from clean-data/rt/ filenames."""
    known = set()
    if CLEAN_DIR.is_dir():
        for f in CLEAN_DIR.iterdir():
            if f.suffix == ".json" and f.stem.startswith("RT"):
                known.add(f.stem)
    return known


def _load_known_from_raw() -> set:
    """Also check raw-data detail files for RT IDs we scraped but haven't compiled."""
    known = set()
    # Check the 'all' (search) folders specifically
    for region_dir in PAGES_DIR.iterdir():
        all_dir = region_dir / "all"
        if not all_dir.is_dir():
            continue
        for page_dir in all_dir.iterdir():
            meta_file = page_dir / "_page.json"
            if meta_file.exists():
                try:
                    with open(meta_file) as f:
                        meta = json.load(f)
                    for rt_id in meta.get("rt_ids_new", []):
                        known.add(rt_id)
                    for rt_id in meta.get("rt_ids_skipped", []):
                        known.add(rt_id)
                except (json.JSONDecodeError, OSError):
                    pass
    return known


# ---------------------------------------------------------------------------
# HTML parsing helpers
# ---------------------------------------------------------------------------

def _extract_total(html: str) -> Optional[int]:
    match = _TOTAL_PATTERN.search(html)
    return int(match.group(1)) if match else None


def _extract_skip_indices(html: str) -> List[int]:
    """Extract detail skip indices from results page links."""
    matches = _SKIP_PATTERN.findall(html)
    return sorted(set(int(s) for s in matches))


def _extract_rt_id(html: str) -> Optional[str]:
    """Extract RT ID from detail page footer."""
    # Fast regex approach first (faster than BeautifulSoup)
    match = re.search(
        r'<font color="#848484">(\d+\s*/\s*\d+)(?:&nbsp;|\s)+(RT\d+)</font>',
        html,
    )
    if match:
        return match.group(2)
    # Fallback: find any RT ID pattern near end of page
    all_matches = _RT_ID_PATTERN.findall(html[-500:])
    return all_matches[-1] if all_matches else None


def _parse_export_tsv(text: str) -> List[Dict[str, str]]:
    """Parse export page TSV into list of dicts."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").strip().split("\n")
    if not lines:
        return []
    headers = [h.strip().lower() for h in lines[0].split("\t")]
    if len(headers) < 5:
        return []
    records = []
    for line in lines[1:]:
        if not line.strip():
            continue
        cells = line.split("\t")
        record = {headers[i]: cells[i].strip() if i < len(cells) else "" for i in range(len(headers))}
        records.append(record)
    return records


# ---------------------------------------------------------------------------
# Search form parameters
# ---------------------------------------------------------------------------

def _make_search_params(region_id: str) -> dict:
    """Build search form POST data for 'All Property Types' in a region.

    Uses sf3="" (empty) which returns all types — the key to finding
    transactions that per-type browsing misses.
    """
    return {
        "sf1": region_id,       # Region (ID from autocomplete)
        "sf2": "",              # Street: all
        "sf3": "",              # Property type: ALL (this is the key difference!)
        "sf4": "",              # Keyword: none
        "startmo": "1/1",       # Period start: Jan 1
        "startyr": "1996",      # Match V2 scraper range
        "endmo": "12/31",       # Period end: Dec 31
        "endyr": "2026",
        "minamt": "",           # Min price: none
        "maxamt": "",           # Max price: none
        "sf7": "",              # Parties: none
        "sf8": "",              # Broker/Agent: none
        "sort1": "regDate",     # Sort by registration date
        "order1": "descending", # Newest first
        "sort2": "amount",      # Secondary sort
        "order2": "descending",
        "sf9": "50",            # 50 per page
        "tabID": "",            # Required hidden field
    }


# ---------------------------------------------------------------------------
# Core session
# ---------------------------------------------------------------------------

class RealtrackSession:
    """Authenticated httpx session for Realtrack.com."""

    def __init__(self, username: str, password: str):
        self.client = httpx.Client(
            base_url=REALTRACK_BASE,
            follow_redirects=True,
            timeout=60.0,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
            },
        )
        self._login(username, password)

    def _login(self, username: str, password: str) -> None:
        log.info("Logging in to Realtrack...")
        resp = self.client.post(
            "/?page=login",
            data={"username": username, "password": password, "function": "login"},
        )
        resp.raise_for_status()
        if "page=signout" in resp.text and "Successful Login" in resp.text:
            log.info("Login successful.")
        else:
            log.error("Login failed — check credentials.")
            sys.exit(1)

    def get(self, path: str) -> httpx.Response:
        resp = self.client.get(path)
        resp.raise_for_status()
        return resp

    def post(self, path: str, data: dict) -> httpx.Response:
        resp = self.client.post(path, data=data)
        resp.raise_for_status()
        return resp

    def close(self):
        self.client.close()


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------

def _retry(fn, retries=3, label="request"):
    for attempt in range(retries):
        try:
            return fn()
        except Exception as e:
            wait = (attempt + 1) * 5
            if attempt < retries - 1:
                log.warning("%s attempt %d/%d failed: %s — retrying in %ds", label, attempt + 1, retries, e, wait)
                time.sleep(wait)
            else:
                raise


# ---------------------------------------------------------------------------
# Scraper core
# ---------------------------------------------------------------------------

def scrape_region(
    session: RealtrackSession,
    region_id: str,
    region_label: str,
    folder_name: str,
    known_rt_ids: set,
    progress: dict,
    delay: float,
    dry_run: bool,
) -> Tuple[int, int, int]:
    """Scrape all search results for one region.

    Returns (new_count, skip_count, fail_count).
    """
    log.info("--- %s (region %s) ---", region_label, region_id)

    # Submit search — must GET search page first, then POST
    session.get("/?page=search")
    params = _make_search_params(region_id)
    resp = session.post("/?page=results", data=params)
    results_html = resp.text

    total = _extract_total(results_html)
    if total is None or total == 0:
        if "no results" in results_html.lower() or total == 0:
            log.info("  No results for %s", region_label)
            return 0, 0, 0
        log.warning("  Could not determine total for %s — saving debug page", region_label)
        debug_dir = RAW_DIR / "debug"
        debug_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write(debug_dir / f"results_{folder_name}.html", results_html)
        return 0, 0, 0

    total_pages = max(1, math.ceil(total / RESULTS_PER_PAGE))
    log.info("  %d results across %d pages", total, total_pages)

    if dry_run:
        return 0, 0, 0

    # Resume: skip to last page if we were interrupted mid-region
    start_page = 1
    if progress.get("current_region") == region_id:
        start_page = max(1, progress.get("current_page", 1))
        if start_page > 1:
            log.info("  Resuming from page %d", start_page)

    region_dir = PAGES_DIR / folder_name / "all"
    region_dir.mkdir(parents=True, exist_ok=True)

    new_total = 0
    skip_total = 0
    fail_total = 0

    for page_num in range(start_page, total_pages + 1):
        # Update progress
        progress["current_region"] = region_id
        progress["current_page"] = page_num
        _save_progress(progress)

        page_label = f"p{page_num:03d}"
        page_dir = region_dir / page_label

        # Skip already-complete pages (have _page.json)
        meta_path = page_dir / "_page.json"
        if meta_path.exists():
            try:
                with open(meta_path) as f:
                    existing_meta = json.load(f)
                if existing_meta.get("status") == "complete":
                    # Still need to navigate forward to maintain session state
                    if page_num < total_pages:
                        session.get(f"/?page=results&tabID={page_num}")
                        time.sleep(0.3)
                    new_total += existing_meta.get("details_new", 0)
                    skip_total += existing_meta.get("details_skipped", 0)
                    continue
            except (json.JSONDecodeError, OSError):
                pass

        # Navigate to this page (page 1 already loaded from search POST)
        if page_num > 1 or start_page > 1:
            try:
                # tabID is zero-indexed: page 2 = tabID=1
                resp = _retry(
                    lambda p=page_num: session.get(f"/?page=results&tabID={p - 1}"),
                    label=f"results p{page_num}",
                )
                results_html = resp.text
            except Exception as e:
                log.error("  Failed to navigate to page %d: %s", page_num, e)
                fail_total += 1
                continue

        time.sleep(delay)

        # Extract skip indices
        skips = _extract_skip_indices(results_html)
        if not skips:
            log.warning("  Page %d: no detail links found", page_num)
            continue

        # Save results HTML
        page_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write(page_dir / "results.html", results_html)

        # Fetch export for this page
        try:
            export_resp = session.get("/?page=export")
            export_rows = _parse_export_tsv(export_resp.text)
            _atomic_write_json(page_dir / "export.json", export_rows)
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
            detail_path = page_dir / f"detail_{i:03d}.html"

            # Resume: skip if file already exists with content
            if detail_path.exists() and detail_path.stat().st_size > 100:
                # Try to read RT ID from existing file
                try:
                    existing_html = detail_path.read_text()
                    existing_rt_id = _extract_rt_id(existing_html)
                    if existing_rt_id:
                        if existing_rt_id in known_rt_ids:
                            rt_ids_skipped.append(existing_rt_id)
                            page_skip += 1
                        else:
                            rt_ids_new.append(existing_rt_id)
                            known_rt_ids.add(existing_rt_id)
                            page_new += 1
                        continue
                except Exception:
                    pass

            try:
                detail_resp = _retry(
                    lambda s=skip_idx: session.get(f"/?page=details&skip={s}"),
                    label=f"detail p{page_num}#{i}",
                )
                detail_html = detail_resp.text
                time.sleep(delay)

                rt_id = _extract_rt_id(detail_html)
                if rt_id is None:
                    # Still save — might be parseable by the pipeline
                    _atomic_write(detail_path, detail_html)
                    page_new += 1
                    log.warning("  Could not extract RT ID from skip=%d", skip_idx)
                    continue

                if rt_id in known_rt_ids:
                    # Already have this one — don't save detail (save disk space)
                    rt_ids_skipped.append(rt_id)
                    page_skip += 1
                else:
                    _atomic_write(detail_path, detail_html)
                    known_rt_ids.add(rt_id)
                    rt_ids_new.append(rt_id)
                    page_new += 1

            except Exception as e:
                log.error("  Failed detail p%d #%d (skip=%d): %s", page_num, i, skip_idx, e)
                page_fail += 1

        # Save page metadata
        meta = {
            "region": region_id,
            "region_label": region_label,
            "prop_type": "all",
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
        _atomic_write_json(meta_path, meta)

        new_total += page_new
        skip_total += page_skip
        fail_total += page_fail

        progress["stats"]["pages_scraped"] += 1
        progress["stats"]["details_new"] += page_new
        progress["stats"]["details_skipped"] += page_skip
        progress["stats"]["details_failed"] += page_fail

        log.info(
            "  Page %d/%d: %d new, %d existing, %d failed",
            page_num, total_pages, page_new, page_skip, page_fail,
        )

    return new_total, skip_total, fail_total


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(
    region_filter: Optional[List[str]] = None,
    resume: bool = False,
    delay: float = 0.5,
    dry_run: bool = False,
):
    # Credentials — check env vars first, then .env files
    username = os.environ.get("REALTRACK_USER", "").strip()
    password = os.environ.get("REALTRACK_PASS", "").strip()
    if not username or not password:
        # Try loading from .env files
        for env_path in [
            PROJECT_ROOT / "engines" / "rt" / "scraper" / ".env",
            PROJECT_ROOT / ".env",
            Path.home() / "cleo-turbo" / ".env",
        ]:
            if env_path.is_file():
                with open(env_path) as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("#") or "=" not in line:
                            continue
                        key, val = line.split("=", 1)
                        key, val = key.strip(), val.strip()
                        if key == "REALTRACK_USER" and not username:
                            username = val
                        elif key == "REALTRACK_PASS" and not password:
                            password = val
                if username and password:
                    break
    if not username or not password:
        log.error("Set REALTRACK_USER and REALTRACK_PASS environment variables,")
        log.error("or create engines/rt/scraper/.env with:")
        log.error("  REALTRACK_USER=your_username")
        log.error("  REALTRACK_PASS=your_password")
        sys.exit(1)

    # Build region list
    if region_filter:
        region_list = []
        for rid in region_filter:
            rid = rid.strip()
            if rid in REGIONS:
                label, folder = REGIONS[rid]
                region_list.append((rid, label, folder))
            else:
                # Try matching by label
                for r, (l, f) in REGIONS.items():
                    if l.lower() == rid.lower() or f.lower() == rid.lower().replace(" ", "_"):
                        region_list.append((r, l, f))
                        break
                else:
                    log.warning("Unknown region: %s (skipping)", rid)
        if not region_list:
            log.error("No valid regions specified.")
            sys.exit(1)
    else:
        region_list = [(r, l, f) for r, (l, f) in REGIONS.items()]

    # Load progress
    progress = _load_progress()
    if not resume:
        progress = _load_progress()  # Fresh start

    # Skip already-done regions if resuming
    if resume and progress.get("regions_done"):
        done_set = set(progress["regions_done"])
        before = len(region_list)
        region_list = [(r, l, f) for r, l, f in region_list if r not in done_set]
        if before > len(region_list):
            log.info("Resuming: skipping %d already-completed regions", before - len(region_list))

    # Load known RT IDs
    log.info("Loading existing RT IDs from clean-data/...")
    known = _load_known_rt_ids()
    raw_known = _load_known_from_raw()
    known.update(raw_known)
    log.info("  %d RT IDs already known (%d from clean, %d from raw search)", len(known), len(known) - len(raw_known), len(raw_known))

    # Login
    session = RealtrackSession(username, password)

    print()
    print("=" * 60)
    print("Cleo Turbo — RT Search Gap Scraper")
    print("=" * 60)
    print(f"  Regions to scrape:  {len(region_list)}")
    print(f"  Known RT IDs:       {len(known):,}")
    print(f"  Delay:              {delay}s")
    if dry_run:
        print(f"  MODE:               DRY RUN (count only)")
    print()

    # Dry run: just count results per region
    if dry_run:
        grand_total = 0
        for rid, label, folder in region_list:
            try:
                session.get("/?page=search")
                params = _make_search_params(rid)
                resp = session.post("/?page=results", data=params)
                total = _extract_total(resp.text)
                if total:
                    grand_total += total
                    print(f"  {label:25s}  {total:>7,} results")
                else:
                    print(f"  {label:25s}        0 results")
                time.sleep(0.5)
            except Exception as e:
                print(f"  {label:25s}  ERROR: {e}")

        # Compare with what we have
        print(f"\n  {'TOTAL':25s}  {grand_total:>7,}")
        print(f"  Already have:             {len(known):>7,}")
        print(f"  Estimated new:            {grand_total - len(known):>7,}")
        est_hours = (grand_total - len(known)) * delay / 3600
        print(f"  Estimated time:           ~{est_hours:.1f} hours (at {delay}s/detail)")
        session.close()
        return

    # Scrape
    total_new = 0
    total_skip = 0
    total_fail = 0

    try:
        for rid, label, folder in region_list:
            try:
                new, skip, fail = scrape_region(
                    session, rid, label, folder,
                    known, progress, delay, dry_run,
                )
                total_new += new
                total_skip += skip
                total_fail += fail

                progress.setdefault("regions_done", []).append(rid)
                progress["current_region"] = None
                progress["current_page"] = 0
                progress["stats"]["regions_scraped"] += 1
                _save_progress(progress)

            except KeyboardInterrupt:
                raise
            except Exception as e:
                log.error("Error on %s: %s", label, e)
                _save_progress(progress)
                continue

    except KeyboardInterrupt:
        log.info("\nInterrupted! Progress saved. Resume with --resume")
        _save_progress(progress)

    session.close()

    # Summary
    print()
    print("=" * 60)
    print("SCRAPING COMPLETE")
    print("=" * 60)
    print(f"  New transactions downloaded:   {total_new:,}")
    print(f"  Already had (skipped):         {total_skip:,}")
    print(f"  Failed:                        {total_fail:,}")
    print(f"  Regions completed:             {progress['stats']['regions_scraped']}")
    print(f"  Pages scraped:                 {progress['stats']['pages_scraped']:,}")
    print()
    if total_new > 0:
        print("Next steps:")
        print("  1. Run the pipeline on new data:")
        print("     cd ~/cleo-turbo/engines/rt && python3 run_pipeline.py")
        print("  2. Compile + rebuild database:")
        print("     python3 run_all.py --from compile")
        print("  3. Restart the backend to pick up new data")


def main():
    parser = argparse.ArgumentParser(
        description="Search-based Realtrack scraper — fills gaps from category browsing"
    )
    parser.add_argument(
        "--regions", type=str,
        help="Comma-separated region IDs or labels (default: all)",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="Resume from last saved progress",
    )
    parser.add_argument(
        "--delay", type=float, default=0.5,
        help="Seconds between detail page fetches (default: 0.5)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Count results per region, don't download details",
    )
    args = parser.parse_args()

    regions = args.regions.split(",") if args.regions else None
    run(region_filter=regions, resume=args.resume, delay=args.delay, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
