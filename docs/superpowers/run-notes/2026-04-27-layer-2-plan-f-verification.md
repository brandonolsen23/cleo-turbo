# Plan F Verification Notes

**Date:** 2026-04-27
**Branch:** `feat/group-discovery-algorithm`

## Backend smoke (programmatic)

### 5 random parties tested

| Tier | Party | Group | Threads | All Groups | Notes |
|---|---|---|---|---|---|
| probable | RT114292 (seller) | grace farms | 1 | 1 | minimal anchor data — only one anchor type set |
| probable | RT42824 (seller) | resreit | 4 | 1 | **1 thread UNATTACHED** — one of its anchors isn't in any auto_group |
| probable | RT58916 (seller) | mizrahi development group | 4 | 1 | clean trail |
| probable | RT157738 (buyer) | enbridge gas | 4 | 1 | clean trail |
| candidate | RT77357 (buyer) | kelderview holsteins | 4 | 1 | clean trail |

### Conflict detection

**Anchors shared by 2+ groups: 0**

This confirms what came up in the spec review — the algorithm produces fully disjoint anchor sets per group. Real-data trails will essentially never show a conflict via shared anchors. The conflict path in the visualization only exercises against:
- The synthetic test fixture (AGRP_00004 deliberately sharing kingsett's phone).
- Future Plan B/C work that introduces overrides or tenure-aware merges.

This is a Plan B insight worth flagging — the disjoint-anchor invariant means tenure-driven conflict surfacing will be the primary pathway for the Trail view's value, not raw anchor sharing.

### Unattached anchors

Found a real case: **RT100506 (seller) at phone 4166357520 has all 4 threads UNATTACHED** — meaning none of its anchors (phone, contact, address_root, address_base) are registered to any auto_group. `primary_group: None`.

Phone 4166357520 is H&R Developments per Layer 1 phones silo (Plan A run notes flagged it as a top operator with 340 sides). Despite its clear phone signature, H&R didn't seed an auto_group at the current confidence thresholds. The Trail view surfaces this gap cleanly: all 4 edges render as gray dashed lines terminating in "(no group)" stub nodes.

This is the expected behavior — Plan F's Trail view makes algorithmic gaps visible per-party instead of buried in aggregate counts.

## Plan F scope coverage

- ✅ `/parties/:source_id/:side/trail` endpoint (Task 1) — 8 tests pass; real-DB smoke clean
- ✅ @xyflow/react installed + types added (Task 2)
- ✅ AutoGroupTrail React Flow visualization component (Task 3) — handles clean / conflict / unattached states
- ✅ AutoGroupTrailTab body with empty state + fetch (Task 4)
- ✅ Wired into detail page replacing Plan F placeholder (Task 5)
- ✅ Trail link on each row of the Parties tab (Task 6)
- ✅ Real-DB verification (this task)

## Test count
- Plan F backend tests: 8 (trail returns party data, threads per anchor, conflict detection, primary group, all_groups union, 404 unknown, 400 invalid side, no-primary case).
- Total `tests/test_routes_explorer.py`: 93 passing.

## Manual click-through (your turn)

Visit `http://localhost:5174/explorer/auto-groups/AGRP_00584?tab=trail` (KingSett, no source_id query):
- Should render the empty-state card ("Pick a party from the Parties tab").

Then `http://localhost:5174/explorer/auto-groups/AGRP_00584?tab=parties` (KingSett):
- Each row should have a "Trail →" link in the rightmost cell.
- Click "Trail →" on any row → URL changes to `?tab=trail&source_id=...&side=...` and the Trail tab renders with React Flow.
- A clean Confirmed-group party shows: party node on left, single group node on right with jade border (primary), 4 jade-colored edges labeled with anchor types.
- Try a row from a probable group whose anchors don't all match (find via the unattached cases) — should show gray dashed edges to "(no group)" stubs.
- Click on the row body (not the Trail link) → SourceViewerDrawer should still open (no regression).

## Findings worth flagging

1. **0 conflicts in real data.** The disjoint-anchor invariant is now visible. Plan B's tenure-aware logic will be where conflict surfacing becomes valuable — when a contact's tenure span at one operator overlaps with another, the Trail view should show split threads.

2. **H&R Developments isn't a verified group** despite having ~340 party-sides on phone 4166357520. Worth investigating in the Tuning page (Plan G) — likely a candidate at confidence 0.65–0.74 that would promote with a small threshold tweak.

3. **`grace farms` has only 1 thread** — that party only has 1 anchor populated. Many parties in the real DB have minimal anchor data (no phone or no address). The Trail view degrades gracefully — even a single-thread trail still tells you something.

## What's next

Plan E (Graph view) is the only verification UI plan left. Plans B (tenure) and C (cascade/user actions) are the algorithm extensions from the original Layer 2 design.
