# Plan H2 Verification Notes

**Date:** 2026-04-30
**Branch:** `feat/group-discovery-algorithm`
**Status:** BLOCKED — performance threshold exceeded

## Summary

Plan H2 introduces time-windowed Layer 2 anchor attribution: every anchor-to-group attachment now carries (start_date, end_date), contact tenures track per-(person, group) windows, and conflict patterns surface as discrete flags for human review. The static anchor model from H1 is preserved as a "current state" snapshot for downstream API code.

The rebuild did NOT complete. It was stopped at the 20-minute wall-time threshold specified in the task spec. The bottleneck is Stage A1 (`build_stems`) which fires one SQL query per distinct brand phrase (150,044 phrases), taking ~13 minutes. Stage A2 (220K anchor timelines) began but was still running when the process was killed at 21+ minutes elapsed.

## Migration

- 017 applied: `auto_group_anchor_tenures`, `auto_contact_tenures`, `auto_conflict_flags` created (confirmed present before rebuild).

## Builder rebuild

Run command: `python3 -m cleo.discovery_v2 2>&1 | tee /tmp/h2-rebuild.log`
Start time: 11:32:42 EDT
Kill time: ~11:53:30 EDT (~21 minutes wall time)
Exit code: process killed (SIGTERM)

### Stages completed

| Stage | Result |
|---|---|
| Layer 1 (brand indexes) | Completed — ~2 minutes |
| Layer 1 (silos: phones, address_units, contacts) | Completed |
| Stage A1 (stems) | Completed — **~13 minutes** |
| Stage A2 (anchor timelines + tenure detection) | **Did not complete** — still running at kill time |
| Stage A3 (seed groups + persist anchor tenures) | Did not run |
| Contact tenures | Did not run |
| Stage A6 (conflict detection) | Did not run |
| Stage A5 (display + counts) | Did not run |

### Layer 1 output (completed)

| Silo | Metric | Count |
|---|---|---|
| A brand tokens | party-sides | 249,084 |
| A brand tokens | distinct tokens | 99,984 |
| A brand tokens | index rows | 737,903 |
| A brand bigrams | distinct bigrams | 177,468 |
| A brand trigrams | distinct trigrams | 71,274 |
| A brand fourgrams | distinct fourgrams | 22,232 |
| A brand fivegrams | distinct fivegrams | 6,103 |
| A brand long-form | distinct phrases | 1,162 |
| B phones | distinct phones | 37,201 |
| C address bases | distinct bases | 74,364 |
| C address roots | distinct roots | 81,494 |
| E address units | distinct units | 100,544 |
| D contact fingerprints | distinct contacts | 82,308 |

### Stage A1 output (completed)

| Metric | Count |
|---|---|
| Verified stems | 2,297 |
| Phrase mappings | 12,309 |

### Table counts after killed rebuild

| Table | Count | Note |
|---|---|---|
| `auto_groups` | 1,676 | From previous H1 run (not overwritten) |
| `auto_group_members` | 60,750 | From previous H1 run |
| `auto_group_anchor_tenures` | **0** | Stage A3 never ran |
| `auto_contact_tenures` | **0** | Contact tenure stage never ran |
| `auto_conflict_flags` | **0** | Stage A6 never ran |
| `auto_group_anchors` (snapshot) | 24,301 | From previous H1 run |
| `anchor_uniqueness` | 220,053 | Layer 1 rows (all anchors) |
| `_pending_tenures` (staging) | **0** | Stage A2 never committed |

## DH Management address tenures

**Not verifiable** — `auto_group_anchor_tenures` is empty (Stage A3 never ran).

The DH Management auto-group exists and is intact from the previous H1 run:
- `auto_group_id`: AGRP_00196
- `canonical_stem`: dh
- `display_name`: dh management
- `n_members`: 34

Address tenure windows (2555 Eglinton 2009-2015, 160 Shorting 2014-2021, 180 Shorting 2018-present) cannot be verified until the rebuild completes.

## TD Bank false positive

RT196095 (seller) attachment status: **PASSES** — no auto_group_members row exists for `source_id='RT196095'` AND `side='seller'`. This result is from the H1-era membership data, which is still intact. The H2 stages (A4 expansion) would re-derive this, but the test verifies the H1 result holds and KingSett did not absorb TD Bank.

## Conflict flag breakdown

| conflict_type | n |
|---|---|
| anchor_reassignment | 0 |
| contact_overlap | 0 |
| transient_tenure | 0 |
| abrupt_tenure_end | 0 |

All zero — Stage A6 never ran. **Cannot verify non-zero counts.**

## Anchor types in tenure/snapshot tables

Tenure tables empty. `anchor_uniqueness` (Layer 1, not tenure-derived) shows:

| anchor_type | anchor_uniqueness | auto_group_anchor_tenures |
|---|---|---|
| phone | 37,201 | 0 |
| address_unit | 100,544 | 0 |
| contact | 82,308 | 0 |

No leftover `address_root` or `address_base` types in `anchor_uniqueness` — correct.

## Performance

**Total elapsed: ~21 minutes (exceeded 20-minute threshold)**

Stage breakdown:
- Layer 1 (brand indexes + silos): ~2 minutes
- Stage A1 (stems): **~13 minutes** — bottleneck confirmed
- Stage A2 (timeline building): ~6-7 minutes elapsed at kill time, not yet complete

### Root cause

Stage A1 (`build_stems` in `stems.py`) fires:
1. One SQL query per distinct brand phrase (150,044 phrases) in `extract_candidate_stem`
2. Two SQL queries per candidate stem for dominance scoring (phone + address_root)

This is O(N) in Python with per-row SQL round-trips on a 150K-phrase dataset. The spec target was < 5 minutes; observed was > 13 minutes for A1 alone.

Stage A2 (`build_anchor_scores` in `anchor_scores.py`) iterates 220,053 anchors via `iter_all_anchor_timelines`, firing one parameterized SQL query per anchor. At the pace observed, A2 would add another 10-15+ minutes.

**Combined estimated rebuild time: 25-40 minutes.** Well above the 5-minute target.

## Findings

1. Stage A1 is the primary bottleneck: 150K Python → SQL round-trips take ~13 minutes. This is the exact O(N²) pattern the spec warned to check for. The fix is to batch-fetch the token lookup table into memory and run `extract_candidate_stem` in pure Python.

2. Stage A2 has a similar per-anchor SQL pattern (220K queries). Even if A1 is fixed, A2 needs a bulk timeline-building query to hit the 5-minute target.

3. The tenure tables (`auto_group_anchor_tenures`, `auto_contact_tenures`, `auto_conflict_flags`) are empty. The H2 algorithm is fully implemented but has never completed a production run.

4. TD Bank (RT196095) correctly has no seller group membership — the H1 precision fix holds.

5. The `anchor_uniqueness` table correctly shows only the three H2-valid anchor types (phone, address_unit, contact) — no address_root or address_base leakage.

## What's next

**Before Task 10 can pass verification, a performance fix is required:**

- Batch the `brand_token_summary` lookup in `build_stems` into a single `SELECT` and run `extract_candidate_stem` in pure Python (no per-phrase SQL calls).
- Similarly, batch the timeline queries in `iter_all_anchor_timelines` into bulk SQL (one query per anchor_type, not one query per anchor value).
- Once the fix is in, re-run `python3 -m cleo.discovery_v2` and verify it completes in < 5 minutes.

After performance is fixed, re-run the verification steps:
- DH Management address tenures visible
- TD Bank still does not attach
- Conflict flags non-zero across at least anchor_reassignment and transient_tenure
- Anchor types in tenures: phone, address_unit, contact only

**Plan H3:** Time-aware UI surfaces (to follow once H2 rebuild completes cleanly).
- Layer 1 silo timelines (phone / address_unit / contact detail pages)
- Auto-group Anchor Tenures tab
- Trail view tenure highlighting
- Conflicts tab on the auto-groups list
