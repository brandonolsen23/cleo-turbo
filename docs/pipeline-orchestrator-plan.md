# RT Pipeline Orchestrator Plan

## Problem

The RT pipeline has 6 stages that process Realtrack transaction data from raw HTML to a SQLite database. Currently each stage is a standalone script that reprocesses the entire dataset (155K+ records) every time it runs. There's no central system that tracks what's been processed, decides what needs reprocessing, or allows selective stage control.

This means:
- Adding 20 daily transactions triggers 30+ minutes of redundant reprocessing
- There's no way to say "I fixed the classifier — reclassify everything but don't re-resolve"
- The watcher tries to orchestrate stages but can't do incremental processing for classify/normalize
- Stage outputs can drift out of sync (285 records assembled, 256 classified, 0 normalized)

## Design

### Two Processing Modes

The pipeline has exactly two modes of operation:

**Mode 1: New Records ("the system is working, process new data")**
Process only records that haven't been through a stage yet. This is what the daily runner uses. The orchestrator looks for assembled files that don't have a classified counterpart, classified files that don't have a normalized counterpart, etc. Nothing gets deleted — it only processes what's missing.

**Mode 2: Reprocess ("we fixed something, rerun everything")**
Reprocess all records from a specific stage onward. The orchestrator writes a marker file that tells each stage to overwrite its existing output in place — no deletion of old files. If the run crashes halfway, the marker stays and the next run continues from where it left off. Old output files that haven't been overwritten yet remain valid.

### The Stage Chain

```
raw HTML → [extract] → assembled/ → [classify] → classified/ → [normalize] → addresses/ → [resolve] → parcel_links/ → [compile] → clean-data/rt/ → [rebuild] → cleo.db
```

Each stage reads from the previous stage's output directory and writes to its own output directory, using identical filenames.

### Processing Log

Every time the orchestrator runs a stage, it appends a line to `pipeline/_processing_log.jsonl`:

```json
{"timestamp": "2026-04-09T18:30:00Z", "stage": "classify", "mode": "new", "files_processed": 285, "files_skipped": 155418, "elapsed_seconds": 2.1, "errors": 0}
{"timestamp": "2026-04-09T18:30:02Z", "stage": "normalize", "mode": "new", "files_processed": 285, "files_skipped": 155418, "elapsed_seconds": 3.4, "errors": 0}
{"timestamp": "2026-04-10T14:00:00Z", "stage": "classify", "mode": "reprocess_from_classify", "files_processed": 155703, "files_skipped": 0, "elapsed_seconds": 1140.0, "errors": 3}
{"timestamp": "2026-04-10T14:19:00Z", "stage": "normalize", "mode": "reprocess_from_classify", "files_processed": 155703, "files_skipped": 0, "elapsed_seconds": 840.0, "errors": 0}
```

This gives you full visibility: how many times each stage has run, how many records were processed each time, how long it took, and whether it was a daily run or a full reprocess. The log is append-only and never affects processing decisions — it's purely for tracking and auditing.

### Reprocess Marker

When you run a reprocess command, the orchestrator writes `pipeline/_reprocess.json`:

```json
{
  "created": "2026-04-10T14:00:00Z",
  "from_stage": "classify",
  "skip_stages": ["resolve"],
  "reason": "Fixed consideration parsing bug",
  "progress": {
    "classify": {"total": 155703, "completed": 89420, "started_at": "2026-04-10T14:00:00Z"},
    "normalize": {"total": 0, "completed": 0, "started_at": null}
  }
}
```

This marker serves three purposes:
1. **Tells each stage to process ALL records** (overwrite in place) instead of only new ones
2. **Tracks progress** so a crashed run resumes where it left off — the stage reads the marker, sees it already finished 89,420 files, and continues from 89,421
3. **Gets deleted when the full reprocess completes** — after that, the system is back in "new only" mode

No files are ever deleted. During a reprocess, stages overwrite their output files in place. If the run crashes after reclassifying 89K of 155K files, those 89K have fresh output and the remaining 66K still have their old (valid) output. Nothing is lost.

### The Orchestrator: `process.py`

A single script in `engines/rt/` that replaces running individual stage scripts.

#### CLI Interface

```bash
# MODE 1: NEW RECORDS — process only what's missing
python process.py --new                        # daily mode, all stages
python process.py --new --skip resolve         # daily mode, resolve later

# MODE 2: REPROCESS — rerun everything from a stage onward
python process.py --from classify              # reclassify + renormalize + compile + rebuild
python process.py --from classify --skip resolve  # common: fixed parser, keep parcel links
python process.py --from normalize             # renormalize + compile + rebuild
python process.py --from resolve               # re-resolve + compile + rebuild
python process.py --full                       # everything from extract onward

# RESOLVE-SPECIFIC — fine-grained resolve control
python process.py --resolve-unresolved         # retry only previously-failed resolutions
python process.py --resolve-method spatial_geocode  # re-resolve a specific method

# TARGET — limit to specific records (works with --new or --from)
python process.py --new --target "_daily/2026-04-09"
python process.py --from classify --target "RT198119"

# UTILITIES
python process.py --status                     # show pipeline state + processing history
python process.py --new --dry-run              # show what would be processed
python process.py --from classify --dry-run    # show what would be reprocessed
```

#### How Each Mode Works

**`--new` (daily mode):**
1. Check for unprocessed page folders in `raw-data/rt/pages/` — extract any new ones
2. Find assembled files with no classified counterpart → classify those
3. Find classified files with no normalized counterpart → normalize those
4. Find normalized files with no parcel_links counterpart → resolve those (if not locked)
5. Run compile (full — reads everything, deduplicates, fast)
6. Run rebuild (full — rebuilds database, fast)
7. Append to processing log

Nothing gets deleted. Nothing gets overwritten. Only missing output files are created.

**`--from classify` (reprocess mode):**
1. Write reprocess marker: `{"from_stage": "classify", "skip_stages": [], "progress": {...}}`
2. Classify ALL assembled files → overwrite classified/ in place, updating progress in marker
3. Normalize ALL classified files → overwrite addresses/ in place, updating progress
4. If resolve not skipped: resolve ALL addresses → overwrite parcel_links/ in place
5. Compile + rebuild
6. Delete reprocess marker (reprocess complete)
7. Append to processing log

If the run crashes at step 2 after processing 89K files, the marker still exists with `"completed": 89420`. The next `process.py` invocation sees the marker, resumes from 89,421. No data lost, no files deleted.

**`--from classify --skip resolve` (the common parser fix):**
Same as above but step 4 is skipped entirely. Existing parcel_links stay untouched. This works because compile reads classified + addresses + parcel_links independently — the parcel data from the previous run is still valid even if classify/normalize output was refreshed.

**`--resolve-unresolved` (targeted retry):**
1. Scan parcel_links/ for files where `method = "unresolved"`
2. Write a marker listing just those specific files
3. Re-resolve only those files (overwrite in place)
4. Compile + rebuild
5. Delete marker

### Extract Stage — Separate Concern

Extract/assemble (`run_pipeline.py`) is different from the other stages because it works on raw HTML page folders, not individual record files.

The orchestrator handles extract separately:
- `process.py --new` first checks for unprocessed page folders (folders in raw-data/rt/pages/ where `extracted/{folder}/` doesn't exist yet)
- It runs `run_pipeline.py --folder <folder>` for each new folder
- THEN proceeds to classify/normalize/resolve on the newly assembled files

### Resolve Stage — Special Handling

Resolve is the expensive, API-dependent stage. It gets special treatment:

1. **Lockfile-aware.** If resolve_v2 is already running (lockfile with live PID), the orchestrator runs all other stages but skips resolve. It logs: "Resolve skipped — already running (PID XXXXX)."

2. **Auto-skip when locked.** The daily runner doesn't block because a long resolve is in progress. New records get classified and normalized, then sit in addresses/ waiting. Next cycle picks them up.

3. **Already incremental.** Resolve skips records that already have a parcel_links file. Running resolve after a daily batch only processes new records.

4. **Rate limit safety.** If resolve hits a ThrottleError, it stops immediately. The orchestrator catches this, logs it, and continues with compile/rebuild. Unresolved records retry next run.

### Compile + Rebuild — Always Full

These stages always process the complete dataset:
- **Compile** reads all classified + addresses + parcel_links, deduplicates by RT ID, writes one clean JSON per transaction. ~3 minutes for 155K records.
- **Rebuild** reads all clean-data/rt/ and rebuilds the SQLite database. ~5-10 minutes.

This is intentional. These stages are fast and correctness matters more than speed. A full compile ensures deduplication is always correct. A full rebuild ensures the database always matches clean-data.

### Pipeline Status

`process.py --status` reads the processing log and filesystem to show:

```
Pipeline Status
  Assembled:     155,703
  Classified:    155,703  (0 pending)
  Normalized:    155,703  (0 pending)
  Resolved:      155,418  (285 pending)
  Clean-data:    155,418
  Database:      rebuilt 2026-04-09 18:35

  Resolve lock:  INACTIVE
  Reprocess:     NONE ACTIVE

Processing History (last 7 days)
  2026-04-09 18:30  --new          classify: 285, normalize: 285       (10m 12s)
  2026-04-09 06:00  --new          classify: 23, normalize: 23         (8m 41s)
  2026-04-08 14:00  --from classify --skip resolve   classify: 155K, normalize: 155K  (38m 20s)

Total Runs: 47  |  Total Records Processed: 1,247,832  |  Errors: 12
```

## Implementation Plan

### Phase 1: Make Classify and Normalize Incremental

The minimal change that unlocks daily processing. Modify `run_classifier.py` and `address_normalizer/run.py` to accept a list of specific files to process (instead of always processing everything).

Changes:
- `run_classifier.py`: Add `--files` flag that accepts a list of filenames or a glob pattern. When set, only process those files. Add `--all` flag to explicitly process everything (overwrite mode for reprocessing). Keep existing `--limit` and `--workers` flags.
- `address_normalizer/run.py`: Same — add `--files` and `--all` flags.

These are surgical changes to existing scripts — no new files, no new architecture. The existing full-reprocess behavior becomes `--all`.

**Safety:** These changes don't affect resolve_v2. They don't touch any files that resolve reads from. Zero risk to a running resolve.

### Phase 2: Build the Orchestrator

Create `engines/rt/process.py` — the single entry point described above.

The orchestrator is purely a coordination layer. It:
1. Checks for a reprocess marker (resume interrupted reprocess if found)
2. Determines which files need processing (missing output for --new, everything for --from)
3. Calls existing stage scripts with the right file lists
4. Updates reprocess marker progress after each stage
5. Appends to the processing log

Changes:
- New file: `engines/rt/process.py`
- Modify `watcher.py` to call `process.py --new` instead of running stages manually

**Safety:** The orchestrator only calls existing scripts. It doesn't modify any stage logic. Lockfile check prevents resolve conflicts.

### Phase 3: Wire Up Daily Runner

Connect the daily scraper → watcher → orchestrator flow:

1. Daily scraper deposits HTML in `raw-data/rt/pages/_daily/YYYY-MM-DD/`
2. Watcher detects new files, calls `process.py --new`
3. Orchestrator extracts, classifies, normalizes new records
4. If resolve isn't locked, resolves new records
5. Compile + rebuild refresh the database
6. New transactions go from HTML to searchable in ~10-15 minutes

### Phase 4: Update CLAUDE.md and Cron

Document the new `process.py` interface in CLAUDE.md. Set up cron:

```bash
# Daily: scrape + process new
0 6 * * *   cd ~/cleo-turbo && python -m engines.rt.scraper.daily_scraper --daily && cd engines/rt && python process.py --new

# Weekly: retry unresolved parcels
0 2 * * 0   cd ~/cleo-turbo/engines/rt && python process.py --resolve-unresolved
```

## What NOT to Change

- **resolve_v2.py** — already incremental. Don't touch it.
- **compile.py** — keep as full reprocess. Fast and correctness matters.
- **rebuild.py** — keep as full rebuild. Same reasoning.
- **run_pipeline.py** — extract/assemble already has `--folder`. Don't change it.
- **Stage directory structure** — assembled/, classified/, addresses/, parcel_links/ stay as-is.

## Migration Safety

The biggest risk is interfering with a running resolve_v2:

1. **Phase 1 only touches classify and normalize.** These write to classified/ and addresses/. Resolve reads from addresses/ but only files that existed when it started. Adding new files to addresses/ while resolve is running is safe — resolve built its file list at startup.

2. **Phase 2's orchestrator checks the lockfile** before running resolve. If resolve is running, it skips resolve and logs it. New records sit in addresses/ until the next cycle.

3. **Reprocess mode never deletes files.** It overwrites in place. If resolve is running and you start a `--from classify` reprocess, the classifier overwrites classified/ files and the normalizer overwrites addresses/ files. Resolve is reading from its startup snapshot and isn't affected. When resolve finishes and the reprocess finishes, everything is consistent.

4. **Compile is safe to run anytime.** It reads from all three directories independently. Records without parcel_links just appear in clean-data without parcel data. The next compile after resolve finishes picks up the parcel links.
