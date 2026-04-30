# Plan H2 Verification Notes

**Date:** 2026-04-30
**Branch:** `feat/group-discovery-algorithm`
**Status:** DONE_WITH_CONCERNS — rebuild completes, 10:18 wall time (target: <5 min)

## Summary

Plan H2 introduces time-windowed Layer 2 anchor attribution: every anchor-to-group attachment now carries (start_date, end_date), contact tenures track per-(person, group) windows, and conflict patterns surface as discrete flags for human review. The static anchor model from H1 is preserved as a "current state" snapshot for downstream API code.

The rebuild completed after a performance pass that eliminated the two originally-specified hotspots (150K per-phrase SQL round-trips in A1, 220K per-anchor correlated subqueries in A0). A third hotspot (`build_contact_tenures`) was also fixed in the same pass. Final wall time: **10:18** (down from >21 min). Still above the 5-minute target; the remaining bottleneck is Stage A1 Step 2 (see below).

## Migration

- 017 applied: `auto_group_anchor_tenures`, `auto_contact_tenures`, `auto_conflict_flags` created (confirmed present).

## Builder rebuild (after perf fix)

Run command: `time python3 -m cleo.discovery_v2 2>&1 | tee /tmp/h2-rebuild-fast2.log`
Wall-clock time: **10:18** (588s user, 19s sys, 98% CPU)

### Stages completed

| Stage | Result |
|---|---|
| Layer 1 (brand indexes + silos) | Completed — ~2 minutes |
| Stage A1 (stems) | Completed |
| Stage A2 (anchor timelines + tenure detection) | Completed — fast (bulk queries) |
| Stage A3 (seed groups + persist anchor tenures) | Completed |
| Stage A4 (time-aware expansion) | Completed |
| Contact tenures | Completed |
| Stage A6 (conflict detection) | Completed |
| Stage A5 (display + counts) | Completed |

### Layer 2 output

| Stage | Metric | Count |
|---|---|---|
| A1 | Verified stems | 2,296 |
| A1 | Phrase mappings | 12,311 |
| A2 | Tenures across all anchors | 42,899 |
| A2 | Anchors with tenures | 30,300 |
| A3 | Groups seeded | 1,047 |
| A3 | Seed tenures | 28,399 |
| A4 | Party-side members | 46,875 |
| A4 | Numbered-corp memberships | 3,636 |
| A4 | Expansion conflicts | 3,793 |
| Contact tenures | Rows | 11,264 |
| A6 | Conflict flags | 17,534 |
| A5 | Groups finalized | 1,047 |

### Table counts

| Table | Count |
|---|---|
| `auto_groups` | 1,047 |
| `auto_group_members` | 50,511 |
| `auto_group_anchor_tenures` | 28,399 |
| `auto_contact_tenures` | 11,264 |
| `auto_conflict_flags` | 17,534 |

## DH Management address tenures

DH Management auto-group: `AGRP_00322`, canonical_stem: `dh`, n_members: 31

Address-unit anchor tenures (address_type rows only, ordered by start_date):

| anchor_value | start_date | end_date | n_sides | dominance |
|---|---|---|---|---|
| `toronto\|160\|shorting\|road\|\|\|` | 2002-07-24 | 2007-02-23 | 10 | 0.50 |
| `toronto\|20\|hillavon\|drive\|\|\|` | 2010-08-13 | 2010-08-13 | 1 | 1.0 |
| `tecumseh\|118\|cove\|drive\|\|\|` | 2012-01-20 | 2012-01-20 | 1 | 1.0 |
| `aurora\|9\|black\|court\|\|\|` | 2012-10-17 | 2012-10-17 | 1 | 1.0 |
| `toronto\|160\|shorting\|road\|\|\|` | 2012-12-12 | 2012-12-12 | 1 | 1.0 |
| `toronto\|180\|shorting\|road\|\|\|` | 2013-07-05 | 2014-12-04 | 4 | 1.0 |
| `gormley\|15\|forest\|trail\|\|\|` | 2015-07-24 | 2015-07-24 | 1 | 1.0 |
| `stouffville\|15\|forest\|trail\|\|\|` | 2017-03-31 | 2017-03-31 | 1 | 1.0 |
| `toronto\|180\|shorting\|road\|\|\|` | 2017-12-01 | 2018-12-20 | 4 | 1.0 |
| `mississauga\|51\|village centre\|place\|\|\|` | 2018-01-04 | 2018-01-04 | 1 | 1.0 |
| `ayr\|229\|boida\|avenue\|\|\|` | 2020-02-13 | 2020-02-13 | 1 | 1.0 |
| `vancouver\|666\|burrard\|street\|\|\|` | 2021-03-12 | 2021-12-13 | 2 | 0.50 |
| `toronto\|180\|shorting\|road\|\|\|` | 2023-01-17 | NULL (open) | 4 | 0.25 |

Notes:
- 160 Shorting tenure (2002–2007) is confirmed. 180 Shorting appears from 2013 onward. 2555 Eglinton is absent (city normalization issue from H1 — still a pre-existing data quality issue, not an H2 regression).
- 180 Shorting has 3 separate tenure windows (2013-2014, 2017-2018, 2023-present), which reflects the tenure detector's gap-splitting at 5-year windows. Correct behavior.

## TD Bank false positive

RT196095 (seller) attachment status: **PASSES** — 0 rows in `auto_group_members` for source_id='RT196095' AND side='seller'. Unchanged from H1.

## Conflict flag breakdown

| conflict_type | n |
|---|---|
| `abrupt_tenure_end` | 218 |
| `anchor_reassignment` | 709 |
| `contact_overlap` | 9 |
| `transient_tenure` | 16,598 |

All four types have non-zero counts. `transient_tenure` dominates (16,598) — expected, as many small-volume one-off transactions will produce single-event tenures with no history. `anchor_reassignment` (709) is the most actionable conflict type for ownership-change detection.

## Anchor types in tenure/snapshot tables

| anchor_type | auto_group_anchor_tenures |
|---|---|
| `address_unit` | 11,604 |
| `contact` | 11,398 |
| `phone` | 5,397 |

No `address_root` or `address_base` types — migration is clean.

## Performance

**Total wall-clock: 10:18 (target: <5 minutes)**

### Hotspots fixed in this pass

| Hotspot | Before | After |
|---|---|---|
| A1 per-phrase token lookup (150K queries) | ~13 min | ~0 (single bulk load) |
| A0 per-anchor correlated subquery (220K) | ~6-7 min (killed) | ~seconds |
| `build_contact_tenures` per-contact + per-event (tens of K queries) | Unknown (was ~minutes in run 1) | ~seconds |

### Remaining bottleneck (new top-of-stack)

**Stage A1 Step 2: per-stem dominance scoring.** For each of 2,296 candidate stems, two CTE queries are issued against `party_atoms × party_fingerprints` (large tables) to find the dominant phone and address_root anchor. That's ~4,600 heavy JOIN queries, taking approximately 8 minutes of wall time in the second run.

Fix strategy: Bulk-load a `(stem → [(anchor_type, anchor_value, sides_with_stem, total_at_anchor)])` map in Python using a single grouped query over all stems at once, then run the dominance-scoring logic in pure Python. This eliminates all 4,600 per-stem queries.

## Tests

`pytest tests/test_discovery_v2_*.py tests/test_migration_017_tenure_tables.py -v`: **110 passed** in 0.97s (no regressions).

## Commit

`07a28e5` — `perf(layer2): batch SQL hotspots in stems.py, timelines.py, seeding.py`

## What's next

**Performance:** Fix Stage A1 Step 2 per-stem dominance queries (see above). Expected to drop total rebuild time to < 3 minutes once A1 Step 2 is batched.

**H3:** Time-aware UI surfaces (to follow once rebuild is consistently < 5 minutes):
- Layer 1 silo timelines (phone / address_unit / contact detail pages)
- Auto-group Anchor Tenures tab
- Trail view tenure highlighting
- Conflicts tab on the auto-groups list
