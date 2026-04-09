# Daily Auto-Scraper Architecture Plan

## Problem Statement

The existing `search_scraper.py` does bulk historical scraping — all 50 regions, 1996–2026, one property type filter at a time. It takes hours. We need a lightweight daily scraper that:

1. Catches new transactions within minutes, not hours
2. Guarantees no RT IDs are missed
3. Runs safely even while the 155K resolve_v2 is still processing
4. Auto-feeds into the watcher → pipeline → database flow

## Key Finding: sf3="" Is a True Superset

**Tested live on Realtrack (Apr 9 2026).** Three open questions, all answered:

### Q1: Does sf1="" (blank region) search all regions?
**YES.** The region field is a textbox with placeholder "all regions & municipalities". Leaving it blank returns results from all 50 regions in one search. No need for 50 per-region searches.

### Q2: What are the actual sf3 form values?
**Confirmed from the live `<select>` element:**
```
"" → "All Property Types"
"multiRes" → "Multi Residential"
"indBldg" → "Industrial Buildings"
"officeBldg" → "Office Buildings"
"retailBldg" → "Retail Buildings"
"hotelMotel" → "Hotels/Motels"
"restaurantBar" → "Restaurants/Bars"
"otherImprv" → "Other Buildings"
"comIndLand" → "Com/Ind Land"
"resLand" → "Res/Rural Land"
"farmLand" → "Farms/Farmland"
"otherLand" → "Other Land"
```

### Q3: Does "All Property Types" (sf3="") return truly ALL transactions?
**YES — it's a true superset.** Verified by fetching RT IDs from detail pages:

- **Retail search** (sf3="retailBldg"): 3 results → RT198155, RT198137, RT198151
- **"All" search** (sf3=""): ~70 results including ALL 3 retail RT IDs
- **Sum of all individual categories**: 56 results
- **"All" total**: ~70 results (56 categorized + ~14 uncategorized)

Every RT ID from every individual category search appears in the "All" search. "All Property Types" = categorized + uncategorized = everything.

**This means the daily scraper only needs ONE search per run.** No multi-filter sweep required.

The old V2 scraper missed ~60K records because it only searched individual categories (which exclude uncategorized transactions). The search_scraper found those 60K by using sf3="" — but it was actually getting everything, not just uncategorized.

## Architecture

### New File: `engines/rt/scraper/daily_scraper.py`

Single entry point with three run modes:

```
python -m engines.rt.scraper.daily_scraper --daily    # Fast daily sweep (~2-5 min)
python -m engines.rt.scraper.daily_scraper --audit    # Broader catch-up (~30-60 min)
python -m engines.rt.scraper.daily_scraper --gaps     # RT ID gap hunter (monthly)
```

### Mode 1: Daily Sweep (`--daily`)

**Goal:** Catch all new transactions from the last 14 days.

**Strategy:**
1. Login to Realtrack via httpx (reuses `RealtrackSession` from search_scraper)
2. Parse search form to discover current sf3 values (property type discovery)
3. **One search:** sf1="" (all regions), sf3="" (all types), date range = last 14 days, 50/page, sort by regDate descending
4. Page through ALL results
5. For each result, check RT ID against known inventory (clean-data/ + raw-data/)
6. Download new detail + export pages into `raw-data/rt/pages/_daily/YYYY-MM-DD/`
7. **Verification pass:** sum individual category counts for the same date range, compare against "All" total. Alert if any category has results not in "All" (should never happen, but catches regressions).
8. Log summary: total found, new downloaded, categories verified

**Why 14 days:** Transactions can appear a few days after registration. The 14-day overlap ensures late arrivals are caught. Dedup handles the overlap at zero cost.

**Expected runtime:** One search + a few pages of results + ~50-100 detail page downloads + 11 verification count checks = **2-5 minutes.**

### Mode 2: Audit Sweep (`--audit`)

**Goal:** Catch backdated entries that appeared outside the daily window.

**Strategy:**
- Same single-search approach as daily, but with a 90-day window
- Run weekly (e.g., Sunday night)
- Also checks for RT IDs in raw-data/ that never made it through the pipeline
- More results to page through, but still just one search

**Expected runtime:** 30-60 minutes depending on result counts.

### Mode 3: Gap Hunter (`--gaps`)

**Goal:** Find RT IDs that slipped through every search.

**Strategy:**
1. Load all known RT IDs from clean-data/ and raw-data/
2. Extract numeric portion, find min and max
3. Identify every gap in the sequence
4. Report gap statistics: total gaps, gap clusters, estimated date ranges
5. For small gap clusters: attempt targeted date-range searches to surface them
6. Run monthly

**Key insight:** RT IDs are sequential (RT100001, RT100002...). A gap means either:
- Deleted/removed from Realtrack (legitimate)
- Missed by our scraping (needs investigation)
- Residential transaction (we skip these, but they still occupy RT IDs)

### Property Type Discovery

On every run, the scraper parses the search form's `<select name="sf3">` element:

```python
def discover_property_types(session):
    resp = session.get("/?page=search")
    # Parse <select name="sf3"> options via regex
    # Compare against known types (KNOWN_SF3_VALUES constant)
    # If new type found: log WARNING + continue
    return types_dict  # {value: label}
```

### Verification Pass

After the main search, the daily scraper runs a quick count check:

```python
def verify_completeness(session, start_date, end_date, all_rt_ids):
    """Search each individual sf3 value, count results, compare against All."""
    for sf3_value, label in KNOWN_SF3_VALUES.items():
        count = search_and_count(session, sf3_value, start_date, end_date)
        # No need to download details — just count
    # Sum of categories should be <= All total
    # If any category RT ID is NOT in all_rt_ids, raise alert
```

This is cheap (11 POST requests, no detail page downloads) and catches any future regression where "All" stops being a superset.

### File Output Structure

```
raw-data/rt/pages/_daily/
  2026-04-09/
    p001/
      results.html      # Search results page 1
      export.json        # Parsed TSV export
      detail_000.html    # Detail page for each new result
      detail_001.html
      _page.json         # Page metadata (RT IDs found, new vs skipped, timestamps)
    p002/
      ...
    _run.json            # Run metadata (mode, date range, totals, verification results)
```

### Integration Flow

```
┌─────────────────┐     ┌──────────────────┐     ┌────────────────┐
│  daily_scraper   │────▶│   raw-data/rt/    │────▶│   RT Watcher   │
│  (cron, 2-5 min) │     │  pages/_daily/    │     │  (daemon, 60s) │
└─────────────────┘     └──────────────────┘     └───────┬────────┘
                                                          │
                         ┌────────────────────────────────┘
                         ▼
              ┌─────────────────────────┐
              │  Pipeline (incremental) │
              │  extract → classify →   │
              │  normalize → resolve →  │
              │  compile → rebuild      │
              └─────────────────────────┘
```

**Concurrency safety:**
- The daily scraper ONLY writes to raw-data/ — no conflict with anything
- The watcher runs extract → normalize stages — these write to their own dirs, safe alongside resolve_v2
- When resolve_v2's lockfile is present, the watcher runs extract → normalize only and queues resolve for the next poll cycle
- Compile + rebuild only runs after resolve completes

### Watcher Modification

The watcher needs one small change: when resolve_v2's lockfile is present, run extract → normalize only, don't block.

```python
def process_new_records(dry_run=False):
    # Check if resolve_v2 is already running
    lockfile = os.path.join(PARCEL_LINKS_DIR, '.resolve_v2.lock')
    resolve_running = _check_lock(lockfile)
    
    if resolve_running:
        # Run only the safe stages (extract through normalize)
        stages = stages[:3]  # assemble, classify, normalize
        log.info('resolve_v2 is running — processing through normalize only')
```

### Configuration

```python
DAILY_LOOKBACK_DAYS = 14      # Daily mode: search last 14 days
AUDIT_LOOKBACK_DAYS = 90      # Audit mode: search last 90 days
DELAY_BETWEEN_REQUESTS = 0.3  # Seconds between HTTP requests
RESULTS_PER_PAGE = 50

KNOWN_SF3_VALUES = {
    "multiRes": "Multi Residential",
    "indBldg": "Industrial Buildings",
    "officeBldg": "Office Buildings",
    "retailBldg": "Retail Buildings",
    "hotelMotel": "Hotels/Motels",
    "restaurantBar": "Restaurants/Bars",
    "otherImprv": "Other Buildings",
    "comIndLand": "Com/Ind Land",
    "resLand": "Res/Rural Land",
    "farmLand": "Farms/Farmland",
    "otherLand": "Other Land",
}
```

### Scheduling

```bash
# Daily at 6 AM — catch overnight transactions
0 6 * * * cd ~/cleo-turbo && python -m engines.rt.scraper.daily_scraper --daily >> /tmp/rt_daily.log 2>&1

# Weekly audit Sunday at midnight
0 0 * * 0 cd ~/cleo-turbo && python -m engines.rt.scraper.daily_scraper --audit >> /tmp/rt_audit.log 2>&1

# Monthly gap check, 1st of month at 3 AM
0 3 1 * * cd ~/cleo-turbo && python -m engines.rt.scraper.daily_scraper --gaps >> /tmp/rt_gaps.log 2>&1

# Watcher daemon (runs continuously via launchd or tmux)
python engines/rt/watcher.py --interval 60
```

### Reuse from Existing Code

From `search_scraper.py`:
- `RealtrackSession` — login + authenticated httpx client
- `_extract_total()`, `_extract_skip_indices()`, `_extract_rt_id()` — HTML parsers
- `_parse_export_tsv()` — export parser
- `_atomic_write()`, `_atomic_write_json()` — safe file writes
- `_retry()` — retry wrapper

From `inventory.py`:
- `load_existing_rt_ids()` — full inventory scan

New code is only: date windowing, single-search orchestration, verification pass, gap detection, property type discovery.

### Summary of New/Modified Files

| File | Action | Description |
|------|--------|-------------|
| `engines/rt/scraper/daily_scraper.py` | CREATE | Daily scraper with --daily/--audit/--gaps modes |
| `engines/rt/scraper/search_scraper.py` | MODIFY | Extract shared utilities into importable functions |
| `engines/rt/watcher.py` | MODIFY | Add lockfile-aware staging |
| `CLAUDE.md` | MODIFY | Document daily scraper and scheduling |
