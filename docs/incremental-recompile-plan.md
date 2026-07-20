# Incremental Recompile Plan — stop the daily full rebuild

Status: in progress (started 2026-07-20)
Owner: Brandon + Claude

## Problem

Every day the RT watcher fires, `engines/rt/process.py --new` runs the upstream
stages incrementally (extract → dedup → classify → normalize → resolve, all in
`new` mode) and then calls `run_compile()` + `run_rebuild()` **unconditionally**.
`run_rebuild()` invokes the master compiler (`cleo.compiler`), which rebuilds the
*entire* database from scratch — all 126k transactions, 138k groups, group
analytics, ~1M party fingerprints, and every `gw_assessments` row — regardless of
whether the day brought in any new records.

Evidence (2026-07-20 run): `extract/dedup/classify/normalize/resolve` each
processed 0 records, yet `compile` rebuilt all 126,383 transactions and the full
derived layer (~18 min). The code comment still calls compile+rebuild "fast,"
which was true when the DB was small.

Two consequences:

1. **Wasted work.** The heavy rebuild runs on days with zero net-new data. The RT
   scraper downloads result pages even when every transaction on them is already
   known; the watcher sees new page folders and that alone triggers the rebuild.
2. **`created_at` is a rebuild timestamp, not a first-seen timestamp.** Because the
   rebuild recreates every table, all `gw_assessments` and `transactions` rows get
   `created_at = now`. The dashboard "Recent Records" panel sorts by `created_at`,
   so it shows the same records re-dated to today every day. GW sorts to the top
   because it is written last. The underlying GW source captures are static — GW is
   NOT being re-scraped (confirmed: `source_file` capture times span Dec 2025–May
   2026, 963 stable rows).

Note: GW already has the right incremental model. `engines/gw/watcher.py` watches
`~/Downloads/GeoWarehouse/gw-ingest-data/`, detects only new `geowarehouse-*.html`
files, processes just those, and does an incremental DB update. It is undermined by
RT's full rebuild wiping `gw_assessments`, and it does not appear to be scheduled
(no launchd agent).

## Design principle

Recompile when there is **new resolved data to fold in, OR an engine/schema
change** — not on a timer. New data must still trigger a rebuild because this is a
global entity-resolution system: one new transaction can change group membership,
brand attribution, and analytics for *existing* records. "Only recompile on code
change" would strand new data in the raw tables. Keep `--full` / `--from STAGE` as
the explicit "engine changed / field added" path (already exists).

## Phases

### Phase 0 — Safety net + baseline
- Branch `fix/incremental-recompile-gating` off `feature/portfolio-capture-m1`.
- Record regression baselines: row counts (transactions, properties, groups,
  gw_assessments, party_fingerprints) and a few known records (a group, a property,
  a GW row) to diff after changes.
- Confirm the master rebuild is reproducible from `clean-data/` (it is), so a full
  rebuild is always the recovery path.

### Phase 1 — Gate compile + rebuild on a dirty marker (biggest win)
- Add a persistent marker `data/pipeline-dirty.json` (`{dirty, reason, since}`).
- In `process.py`, the `--new` path only:
  - Set dirty = true if any upstream stage (`extract/dedup/classify/normalize/
    resolve`) produced > 0 new records this run, OR resolve was skipped-locked with
    pending work.
  - Run `run_compile()` + `run_rebuild()` only if the marker is dirty (or an
    explicit force). On a clean marker, skip both and log `compile: skipped_clean`.
  - Clear the marker only after a **successful** rebuild (so a failed/locked run
    retries next cycle; the flag accumulates across runs — a deferred resolve still
    compiles later).
- Leave the `--full` / `--from` / targeted-reprocess paths always compiling.
- Add `--force-compile` escape hatch and a way to manually set the marker.
- Tests: gate logic (new work → compiles + clears; no work → skips; dirty persists
  across a skipped run; force overrides). Dry-run on a real no-op day (seconds, not
  minutes) and on a seeded new record (compiles).

### Phase 2 — Schedule GW as its own daily job
- Wire `engines/gw/watcher.py --once` into the morning run (a `com.cleo.gw-daily`
  launchd agent, or a step in `rt-daily-run.sh`). It already ingests only new HTML
  and skips when nothing is pending.
- New GW data sets the Phase 1 dirty flag so a rebuild reconciles it only when
  needed. Confirm whether GW feeds group analytics or only enriches properties —
  that decides full rebuild vs. a lighter targeted update.

### Phase 3 — Make "Added" truthful
- Add a persistent first-seen store (keyed by `source_id` / `gw_id`) that survives
  rebuilds. The master rebuild reads it to set `created_at`; only genuinely new rows
  get `now`. Backfill from the best signal: GW `source_file` capture time; RT
  daily-run date; everything older stamped once at backfill (honest — we don't know
  first-seen before today).
- Recent Records then reflects genuinely new records. Verify two back-to-back
  rebuilds leave unchanged rows' `created_at` fixed.

### Phase 4 — Incremental master compile (optional, later)
- Recompute only affected groups/analytics/fingerprints instead of all 138k. Large
  effort; defer. A full rebuild on real new-data days is acceptable once Phases 1–2
  remove the empty-day rebuilds.

## Guardrails
- Compiler is the shared spine with known drop-risks — each phase lands as its own
  commit on the branch with tests and a dry-run; diff regression baselines before
  merging.
- `--full` / `--from` remain the deliberate full-recompile path for engine/schema
  changes.
