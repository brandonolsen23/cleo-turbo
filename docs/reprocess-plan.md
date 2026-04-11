# Targeted Reprocess Plan — RT Pipeline

## Problem

The RT pipeline has no way to reprocess a specific RT ID without reprocessing all 124K records. This means:

- **Bad scrapes** (like RT198249, where Realtrack served $0 and empty parties) can't be fixed without either a full rerun or manual file surgery.
- **Re-scraping a single record** requires manually deleting artifacts across 7 directories, then re-downloading, then running `--new` — error-prone and ad-hoc.
- Each pipeline stage (dedup, classify, normalize, resolve) checks for existing output by filename and **skips** if it already exists. Overwriting a source file upstream doesn't cascade — downstream artifacts persist with stale data.

We need a reliable, repeatable way to reprocess one or more RT IDs from any starting point in the pipeline.

## Scenarios This Must Handle

| Scenario | Starting Point | Example |
|----------|---------------|---------|
| Bad scrape — need fresh HTML from Realtrack | `scrape` | RT198249 downloaded with $0 and no parties |
| Bad extract — HTML is fine but assembler had a bug | `extract` | Assembler wasn't parsing a new field |
| Classifier fix — parser logic changed | `classify` | Fixed how mortgage charges are parsed |
| Normalizer fix | `normalize` | Fixed address normalization edge case |
| Resolver retry — want to re-resolve one record | `resolve` | Record failed geocoding, want to retry |

**Note:** Bulk reprocessing (all 124K records from classify onward after a parser fix) is already handled by the existing `--from classify` mode. This plan covers **targeted** reprocessing of specific RT IDs only.

## Design

### New CLI mode on `process.py`

```bash
# Reprocess one RT ID from a specific stage
python process.py --reprocess RT198249 --from classify

# Reprocess multiple RT IDs
python process.py --reprocess RT198249,RT198246 --from normalize

# Re-scrape: download fresh HTML from Realtrack, then full reprocess
python process.py --reprocess RT198249 --from scrape

# Dry run — show what would be deleted, don't do it
python process.py --reprocess RT198249 --from classify --dry-run
```

### How It Works

**Step 1: Delete downstream artifacts for the target RT IDs.**

Each stage stores files with the RT ID as the filename prefix (`RT198249__*.json` or `RT198249.json` for clean records). Deletion is a simple glob per stage.

The stages and their directories:

| Stage | Directory | Filename Pattern |
|-------|-----------|-----------------|
| assembled | `pipeline/assembled/` | `RT{id}__*.json` (may be multiple) |
| deduped | `pipeline/deduped/` | `RT{id}__*.json` (exactly one) |
| classified | `pipeline/classified/` | `RT{id}__*.json` |
| addresses | `pipeline/addresses/` | `RT{id}__*.json` |
| parcel_links | `pipeline/parcel_links/` | `RT{id}__*.json` |
| clean | `clean-data/rt/` | `RT{id}.json` |

When `--from classify` is specified, delete files from **classified, addresses, parcel_links, and clean** — everything from the target stage onward. Leave assembled and deduped intact (those are the source data for classify).

When `--from scrape` is specified, delete **everything** including assembled and deduped, then also handle the re-download (see Step 2).

**Step 2 (scrape mode only): Re-download the detail page from Realtrack.**

This is the tricky part. Realtrack doesn't have a direct URL like `/detail?rt_id=RT198249`. Detail pages are accessed via a `skip` index from a search results page: `/?page=details&skip=73`.

To re-download a specific RT ID:

1. Search Realtrack with a narrow date range containing the transaction. We know the sale date from the existing assembled record (before we delete it — read it first).
2. Page through results until we find the RT ID in the detail page footer.
3. Download and **overwrite the original HTML file in place** at `raw-data/rt/pages/{source_folder}/detail_{position:03d}.html`.

Overwriting in place is critical — it means any future bulk rerun (`--from classify`, `--from extract`) will use the corrected HTML. The fix is permanent.

**Implementation:** Add a `rescrape_rt_id(rt_id, session)` function to `engines/rt/scraper/shared.py` (or a new `engines/rt/scraper/rescrape.py` module) that:

```python
def rescrape_rt_id(rt_id: str, session: RealtrackSession, assembled_data: dict) -> Path:
    """Re-download a single RT detail page from Realtrack.
    
    Strategy:
    1. Read the sale_date from assembled_data to narrow the search window.
    2. Search a ±7 day window around that date (small enough to avoid huge result sets).
    3. Page through results, fetching each detail page until we find the one
       whose footer contains our RT ID.
    4. Overwrite the original HTML file at:
       raw-data/rt/pages/{source_folder}/detail_{position:03d}.html
    
    Returns the path to the overwritten HTML file.
    Raises if RT ID not found in search results.
    """
```

This reuses `RealtrackSession`, `extract_rt_id()`, and `_make_search_params()` from the existing scraper code. The only new logic is the "search, page, and match by RT ID" loop.

**Why not use `sf4` (keyword field)?** The Realtrack search form has a keyword field (`sf4`), and it's tempting to search for the RT ID directly. However, I don't know if `sf4` accepts RT IDs or what it searches against. This would need testing on the live site. If it works, the rescrape could be a single search + single detail fetch instead of paginating through results. Worth testing, but the pagination approach works regardless.

**Step 3: Run `--new` for the target RT IDs only.**

After deletion, the target RT IDs are "pending" at the target stage and every stage downstream. Now run the pipeline — but only for the target RT IDs, not all 124K.

For most stages, this means invoking the stage script with a `--files` glob pattern:

| Stage | How to Run Targeted |
|-------|-------------------|
| extract | `run_pipeline.py --folder {source_folder}` (re-extracts the page folder containing the target RT) |
| dedup | `dedup.py` in incremental mode — automatically picks up only RT IDs not in deduped/ |
| classify | `run_classifier.py --files "RT198249__*.json"` (already supports `--files` pattern) |
| normalize | `address_normalizer/run.py --files "RT198249__*.json"` (already supports `--files` pattern) |
| resolve | Needs enhancement — currently no `--files` flag. Options: (a) add `--files` support, or (b) just run incremental mode which processes any addresses/ files without a parcel_links/ counterpart |
| compile | Currently always processes all RT IDs. For targeted reprocess, we have two options: (a) add `--rt-ids` flag, or (b) just run the full compile (it's fast, ~2 min for 124K records, and produces correct output regardless) |
| rebuild | Always full. No change needed. Same as compile — runs the compiler against all clean-data/. Fast enough that targeting isn't necessary. |

**Resolve stage detail:** Running resolve in incremental mode (the default) will pick up any addresses/ files that don't have a parcel_links/ counterpart. Since we deleted the parcel_links file for our target RT IDs, incremental mode will reprocess just those. This works without any code changes. The only concern is that it also starts the full resolver machinery (Playwright browser, token management) for potentially just 1-2 records. Acceptable for targeted reprocessing but not ideal. A `--files` flag would be cleaner but isn't strictly necessary for v1.

**Compile + rebuild:** These are fast enough (~2-3 min each) that running them in full is fine. No targeting needed. The compile reads all classified + addresses + parcel_links, groups by RT ID, picks the best, and writes clean records. One stale clean record gets overwritten by the fresh data. Rebuild reads all clean-data/ and regenerates the database.

### New API Endpoint

```
POST /api/pipeline/reprocess
{
    "rt_ids": ["RT198249"],
    "from_stage": "scrape",   // scrape | extract | dedup | classify | normalize | resolve
    "dry_run": false
}
```

**Response:**
```json
{
    "success": true,
    "rt_ids": ["RT198249"],
    "from_stage": "scrape",
    "deleted": {
        "assembled": 1,
        "deduped": 1,
        "classified": 1,
        "addresses": 1,
        "parcel_links": 1,
        "clean": 1
    },
    "pid": 12345,
    "message": "Reprocessing RT198249 from scrape. Artifacts deleted, pipeline started."
}
```

The endpoint:
1. Validates the RT IDs exist in the pipeline (at least one artifact found)
2. For `from_stage: "scrape"`, reads assembled data first (to get sale_date and source_folder for re-download)
3. Deletes artifacts from the target stage onward
4. Spawns process in background:
   - For scrape: rescrape → extract → dedup → classify → normalize → resolve → compile → rebuild
   - For classify: classify (--files) → normalize (--files) → resolve (incremental) → compile → rebuild
5. Returns immediately with PID for status polling

### Frontend UI — RT Trace Page

Add a **Reprocess** dropdown button to the RT Trace page header (next to the RT ID and source badge):

```
RT198249  [daily / 2026-04-09_154735]  [Reprocess ▾]
                                         ├─ Re-scrape & Reprocess
                                         ├─ From Classify
                                         ├─ From Normalize
                                         └─ From Resolve
```

Clicking an option shows a confirmation dialog:

> **Reprocess RT198249 from scrape?**
> 
> This will:
> - Re-download the detail page from Realtrack (overwriting the original HTML)
> - Delete all pipeline artifacts (assembled → clean)
> - Reprocess through the full pipeline
>
> [Cancel] [Reprocess]

After confirmation, calls `POST /api/pipeline/reprocess`, then polls for completion. When done, refreshes the trace data so you see the updated pipeline output immediately.

**Status while running:** Show a small inline status indicator next to the Reprocess button: "Reprocessing..." with a spinner. Disappears when complete.

## Implementation Order

### Phase 1: Core Deletion + Pipeline (backend only, CLI)

**File: `engines/rt/process.py`**

Add `--reprocess` argument that accepts comma-separated RT IDs. Add `delete_artifacts(rt_ids, from_stage)` function that globs and deletes files from target stage onward. Wire into the main function to run targeted pipeline after deletion.

Changes:
- New function: `delete_artifacts(rt_ids: list[str], from_stage: str) -> dict` — returns count of deleted files per stage
- New function: `run_targeted(rt_ids: list[str], from_stage: str)` — runs each stage with file targeting
- New argparse group: `--reprocess RT_IDS` + existing `--from` flag reused for stage selection
- `--dry-run` support: show what would be deleted without doing it

Estimated scope: ~80 lines added to process.py.

### Phase 2: Re-scrape for single RT ID

**File: `engines/rt/scraper/rescrape.py` (new)**

Single-purpose script to re-download one RT detail page from Realtrack by searching for it. Uses existing `RealtrackSession` and search infrastructure from `shared.py`.

Key function: `rescrape_rt_id(rt_id, session, sale_date, source_folder, position)` — searches a narrow date window, pages through results, finds the RT ID, overwrites the original HTML file in place.

Callable as: `python -m engines.rt.scraper.rescrape RT198249`

Also callable from `process.py --reprocess RT198249 --from scrape` — process.py reads the assembled data to get sale_date/source_folder/position, then invokes rescrape.

Estimated scope: ~120 lines in new file.

### Phase 3: API Endpoint

**File: `cleo/web/routes/admin.py`**

New endpoint: `POST /admin/pipeline/reprocess` — validates input, performs deletion, spawns targeted pipeline as background process. Follows same pattern as existing orchestrator run endpoint.

Estimated scope: ~60 lines added to admin.py.

### Phase 4: Frontend UI

**File: `frontend/src/pages/PipelineTracePage.tsx`**

Add Reprocess dropdown button with confirmation dialog. Calls API, polls for completion, refreshes trace data.

Estimated scope: ~100 lines added to PipelineTracePage.tsx, new types in types/index.ts.

## What Survives a Full Rerun?

This is the critical question. Here's the answer for each `--from` option:

| Reprocess Mode | What Happens on Next `--from classify` (bulk) |
|---------------|-----------------------------------------------|
| `--from scrape` | **Survives.** The corrected HTML was overwritten in place. Extract reads the good HTML, produces a good assembled record. Everything downstream rebuilds from good data. |
| `--from extract` | **Survives.** Same as scrape — the assembled record is rebuilt from the (presumably corrected) HTML. |
| `--from classify` | **Survives.** The deduped file (input to classify) still exists with the same filename. Bulk `--from classify` reclassifies it along with everything else. |
| `--from normalize` | **Partially survives.** The classified file still exists, so `--from normalize` picks it up. But `--from classify` would reclassify from deduped, which also works. |
| `--from resolve` | **Partially survives.** The addresses file still exists, so `--from resolve` re-resolves it. But `--from classify` or `--from normalize` also works since upstream files persist. |

**The key principle:** Targeted reprocessing deletes *downstream* artifacts and regenerates them from the *upstream* source that was already corrected or still intact. Since bulk reruns always regenerate from upstream, the targeted fix persists.

**The one exception:** If someone manually edits a classified or addresses file (not through the pipeline), that edit would be lost on the next `--from classify`. But that's expected — manual overrides are a separate system (not part of this plan).
