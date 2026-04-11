# Early Deduplication Plan — RT Pipeline

## Problem

The RT pipeline currently carries **31,450 duplicate records** (20.2%) through every stage after assembly. The same transaction appears multiple times because Realtrack lists it under multiple property type categories (e.g., `comm-ind-land` and `industrial`). All 155,988 assembled files get classified, normalized, and resolved individually — but only 124,538 are unique RT IDs. The duplicates are only eliminated at compile time.

This wastes processing time at every stage, particularly resolve (which makes external API calls for geocoding/parcel lookup). Moving dedup to immediately after assembly saves ~20% of all downstream work.

### Duplicate distribution (current)

| Copies | RT IDs   | Files  |
|--------|----------|--------|
| 1      | 98,588   | 98,588 |
| 2      | 20,837   | 41,674 |
| 3      | 4,782    | 14,346 |
| 4      | 294      | 1,176  |
| 5      | 36       | 180    |
| 24     | 1        | 24     |
| **Total** | **124,538** | **155,988** |

### Root cause of duplicates

1. **Cross-type duplicates (vast majority):** Same transaction listed under multiple property types in Realtrack search results. E.g., RT100004 appears in both `comm-ind-land/p008/pos035` and `industrial/p033/pos007`. The detail page content is identical — both point to the same RT detail URL.

2. **Cross-page duplicates within same type (rare, e.g., RT17788):** Some RT IDs appear at multiple positions on the same or adjacent pages. Investigation shows these are sometimes genuinely different transactions sharing the same RT ID (different cities, different data). This is a Realtrack data quality issue, not a dedup issue. These should NOT be blindly deduped — the scoring function handles them correctly.

## Design

### New stage: `dedup` — runs between `extract` and `classify`

After assembly produces `pipeline/assembled/*.json`, a new dedup step groups files by RT ID (from the filename prefix before `__`) and picks the best candidate for each group. The winner is symlinked (or copied) into a new `pipeline/deduped/` directory. All downstream stages read from `deduped/` instead of `assembled/`.

### Scoring at dedup time

The current compile-time `score_record()` reads classified + addresses + parcel_link data. At dedup time (pre-classify), we only have the raw assembled JSON. We need a simpler scoring function that works on assembled data:

```python
def score_assembled(data):
    """Score an assembled record for early dedup. Higher = better."""
    score = 0
    
    # Prefer join-verified records (detail page was successfully matched)
    if data.get('join_verified'):
        score += 10
    
    # Prefer records with detail data (richer than results-only)
    if data.get('detail'):
        score += 5
    
    # Prefer records with export data
    if data.get('export'):
        score += 3
    
    # Prefer records where results + detail cities match (data consistency)
    results_city = (data.get('results', {}).get('city_region') or '').split(':')[0].strip()
    detail_city = (data.get('detail', {}).get('header', {}).get('city_region') or '').split(':')[0].strip()
    if results_city and detail_city and results_city.lower() == detail_city.lower():
        score += 2
    
    # Prefer records with more non-empty fields (richer data)
    export = data.get('export', {})
    for field in ['municipality', 'postal_code', 'sale_price', 'acreage']:
        if export.get(field):
            score += 1
    
    return score
```

This doesn't need to be perfect — it just needs to consistently pick the better record when two assembled files represent the same transaction. For the typical cross-type duplicate, the records are nearly identical and any pick is fine.

### Output directory: `pipeline/deduped/`

The dedup step writes one file per unique RT ID to `pipeline/deduped/`. The filename is simplified to just `{RT_ID}.json` (dropping the region/type/page/pos suffix) since we've already picked the best variant.

**Why rename?** Downstream stages (classify, normalize, resolve) don't use the filename metadata — they read the RT ID from inside the JSON. The long filenames only exist because of how extract writes them. Simplifying to `RT{id}.json` makes everything cleaner and avoids the awkward `fname.split('__')[0]` pattern in compile.py.

### What changes downstream

| Component | Change |
|-----------|--------|
| `run_classifier.py` | Read from `deduped/` instead of `assembled/` |
| `address_normalizer/run.py` | Read from `deduped/` instead of (it reads classified, no change) |
| `compile.py` | Remove dedup logic entirely — input is already deduped. Read classified/addresses/parcel_links and compile 1:1. Filenames are now `RT{id}.json`. |
| `process.py` | Add `dedup` stage between extract and classify. Update pending-file checks. |
| `watcher.py` | No change (delegates to process.py) |
| `admin.py` API | Add `deduped` count to orchestrator status |
| `PipelineOverviewPage.tsx` | Add `deduped` stage to the pipeline flow display |

### Incremental behavior

- **New records mode (`--new`):** Dedup only runs on assembled files that don't have a counterpart in `deduped/`. Since filenames change (from long to `RT{id}.json`), the pending check is: "for each unique RT ID in assembled/, does `deduped/{RT_ID}.json` exist?"
  
- **Reprocess mode (`--from dedup`):** Re-score all assembled files and rewrite all deduped outputs. This is fast (pure local file I/O, no API calls) and takes a few seconds.

- **New daily files arriving:** When the daily scraper deposits new HTML and they flow through extract → assemble, the dedup step checks if the RT ID already exists in `deduped/`. If it does, it re-scores the existing deduped record against the new one and keeps the better. If the new one wins, it overwrites. If the existing one wins, the new file is skipped.

### Edge case: RT ID collision (different transactions, same ID)

The RT17788 case shows that some RT IDs map to genuinely different transactions (different cities, different data). The scoring function handles this implicitly — it picks the richest record. But we should log when we encounter an RT ID group where the underlying data appears to be different transactions (e.g., different cities or sale prices). This is a data quality flag, not a dedup failure.

Detection heuristic:
```python
# After scoring, check if "losers" had materially different data
for loser_data in non_winners:
    winner_city = winner.get('export', {}).get('municipality', '')
    loser_city = loser_data.get('export', {}).get('municipality', '')
    if winner_city and loser_city and winner_city.lower() != loser_city.lower():
        log_data_issue(rt_id, 'rt_id_collision', 
                       f'Same RT ID, different cities: {winner_city} vs {loser_city}')
```

These get logged to `data_issues` table (already exists) for manual review.

## Implementation Plan

### Phase 1: Build the dedup script (~30 min)

Create `engines/rt/dedup.py`:
- Read all files from `assembled/`, group by RT ID
- Score each candidate with `score_assembled()`
- For single-file groups (76% of IDs): copy directly to `deduped/{RT_ID}.json`
- For multi-file groups: pick highest scorer, copy to `deduped/{RT_ID}.json`
- Log collisions (same RT ID, different data) to stdout
- CLI: `--dry-run` (show stats, don't write), `--all` (reprocess), default incremental
- Stats output: total assembled, unique IDs, duplicates eliminated, collisions detected

### Phase 2: Update downstream stages (~20 min)

1. **`run_classifier.py`**: Change input dir from `assembled/` to `deduped/`
2. **`compile.py`**: Remove the grouping/scoring logic. Each file in classified/ now maps 1:1 to an RT ID. Simplify the main loop to iterate directly without grouping.
3. **`process.py`**: Insert `dedup` between extract and classify in `STAGE_ORDER`. Add `run_dedup()` function. Update dry-run stats.

### Phase 3: Backfill deduped/ (~5 min)

Run `python dedup.py` once to populate `deduped/` from existing assembled files. This is a one-time operation. After this, the pipeline is ready.

Since downstream stages already have their outputs (classified/, addresses/, parcel_links/), those don't need to be rerun. The existing outputs use the old long filenames. We have two options:

**Option A — Clean cut (recommended):** Run `dedup.py` to create `deduped/`. Then do a full reprocess (`process.py --from classify`) to regenerate all downstream outputs with the new `RT{id}.json` filenames. This is clean but takes time (classify + normalize are fast, resolve would re-resolve everything unless we `--skip resolve`).

**Option B — Backward compatibility:** Keep dedup writing the *original* winning filename to `deduped/` (not renaming to `RT{id}.json`). Downstream stages continue to work with old filenames. compile.py keeps its grouping logic but now only sees 1 file per group. Zero reprocessing needed, but the code stays messier.

**Recommendation: Option A with `--skip resolve`.** Run `process.py --from dedup --skip resolve` to reclassify + renormalize with clean filenames. Existing parcel_links stay untouched (they were already deduped by RT ID internally). Compile gets updated to work with the new filenames.

Wait — parcel_links filenames also need to match. If we rename at dedup time, the parcel_link files won't match the new classified/addresses filenames. So we'd need to rename parcel_links too, or rerun resolve.

**Revised recommendation: Option B for now.** Keep the original filenames flowing through. The dedup step just copies the winning file to `deduped/` with its original filename. The only change is that `deduped/` has ~124K files instead of `assembled/`'s ~156K. Downstream stages work exactly as before. compile.py can optionally drop its grouping logic (since groups will now be size 1) but doesn't have to — it's harmless.

This is the lowest-risk approach. The filename cleanup can happen later as a separate task.

### Phase 4: Wire up UI and verify (~15 min)

1. Add `deduped` count to `admin.py` orchestrator status endpoint
2. Add `deduped` stage to the Pipeline Overview page
3. Run dry-run from app, verify counts show ~124K at classify stage instead of ~156K
4. Verify compile output is identical (same number of clean-data RT files)

## Safety

- **No data loss:** Dedup only copies files — never deletes from assembled/. The assembled/ directory remains the source of truth for what was extracted.
- **Reversible:** Delete deduped/ and revert code changes to go back to the old behavior.
- **Crash safe:** If dedup crashes mid-run, the next incremental run picks up where it left off (only writes missing files).
- **No API calls:** Dedup is pure local I/O. No risk of rate limiting or external service issues.
- **Compile stays correct:** Even if dedup has a bug, compile.py can keep its grouping logic as a safety net. Belt and suspenders.

## Expected Impact

- **~31K fewer files** through classify, normalize, and resolve
- **Resolve savings:** ~31K fewer geocoding/parcel API calls on full reprocess
- **Compile simplification:** Grouping/scoring loop becomes a simple 1:1 iteration
- **Pipeline Inspector:** Stage counts will show the real unique record count at each stage instead of the inflated 156K
