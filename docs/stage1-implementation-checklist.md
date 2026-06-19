# Stage 1 — Verification Capture & Full Re-Geocode (Implementation Checklist)

> Goal: capture the geocoder signals we currently discard (`Loc_name`, parsed fields, containment),
> compute a per-transaction confidence **tier**, re-geocode all distinct addresses once (cached),
> and surface mismatches in a review queue — **without changing where anything is placed yet.**
> This turns "I think things land wrong" into an exact, measured, auditable list before any
> structural change. **Non-breaking and measurement-only.** Nothing here is built until approved.
> Companion to `parcel-resolution-spec.md` (this is its Stage 1).

## Principles
- **Additive only.** New cache, new columns, new flags, new issues rows. No change to which parcel a
  transaction resolves to. Where a fresh PARCEL-level geocode disagrees with the current placement,
  we **record it as Review** (a candidate better placement for Stage 3 to promote) — we do not flip it.
- **Idempotent + resumable.** Re-running recomputes from cache; safe to stop/restart.
- **Asset-class-agnostic.** Applies to all 124,544 transactions, not retail.

## Prereqs (already true)
- `.venv` has Playwright + Chromium; Ontario geocoder + AgMaps verified working.
- `geocode()` returns a dict with `loc_name, addr_type, score, comp_score, house, street_name, suf_type, city, all_candidates`.
- Caches exist: `clean-data/parcels/` (124,430), `clean-data/reverse_geocode/`.

---

## 1.1 Forward-geocode cache  ☐
- **What:** persist every geocode result keyed by normalized address, so re-runs are free and
  deterministic; only new/changed addresses hit the network.
- **Where:** new `cleo/resolver/geocode_cache.py` (mirror `cleo/resolver/cache.py` parcel-cache
  pattern: atomic write, `cache_read_safe`). Store under `clean-data/geocodes/`. Key = canonical
  address string from `cleo/address` (lowercased number+street+suffix+city). Value = the full
  geocode dict (incl. `loc_name`, `comp_score`, `all_candidates`).
- **Wire in:** `engines/rt/parcel_resolver/ontario_geocoder.py` (or the resolve_v2 loop) checks the
  cache before calling the locator; writes on miss.
- **Acceptance:** second run over the same address set makes **0** network calls; cache file count
  ≈ distinct addresses geocoded.

## 1.2 Containment flag from `query_by_point`  ☐
- **What:** make the spatial query report HOW it chose the parcel, instead of hiding the fallback.
- **Where:** `engines/rt/parcel_resolver/agmaps.py:149-198`. Return an extra field
  `containment ∈ {contained, nearest_centroid, features0, none}` alongside the parcel (additive —
  the returned parcel is unchanged in Stage 1).
- **Acceptance:** every resolved record carries a `containment` value; we can count how often
  `nearest_centroid`/`features0` fired (the silent neighbour-grab).

## 1.3 Stop dropping provenance through the pipeline  ☐
- **What:** carry the signals from resolver → clean-data → DB (today they die at compile).
- **Where:**
  - `engines/rt/parcel_resolver/adapter.py` `result_to_parcel_link`: add `loc_name`, `comp_score`,
    `geocode_addr_type`, `containment`, `field_match`, `parcel_tier` (plus the already-present
    `confidence`, `pip_verified`, `reason`).
  - `engines/rt/compile.py:108-120`: the clean-record `parcel` block currently keeps only
    `resolved_arn/method/parcel_file` — extend it to carry the fields above (this is where they're lost).
  - `cleo/compiler/writer.py` Pass 3 (transactions insert ~`:667-687`): read the new fields from the
    clean record and write to the new columns (1.5).
- **Acceptance:** a transaction row in `cleo.db` shows `parcel_loc_name`, `parcel_tier`,
  `parcel_confidence`, `pip_verified`, `containment` populated.

## 1.4 Canonical field-match + tier computation  ☐
- **What:** field-match the RT address against the geocoder's parsed fields, then assign a tier.
- **Where:** new helper in `cleo/resolver/` (e.g. `verify.py`). Canonicalize both sides via
  `cleo/address` (suffix St↔Street, directionals, ordinals, Mc/Mac, saints) to close the
  "Mccordick" gap. `field_match = house== AND street== AND city==` (post-canonical).
  Tier rule:
  - **Verified** — `loc_name` starts `PARCEL_` AND `field_match` AND `containment=contained`.
  - **Probable** — `addr_type=PointAddress` AND `containment=contained`, but not parcel-locator/field-match.
  - **Review** — `loc_name` Roads/Street (interpolated), OR `containment≠contained`, OR field mismatch,
    OR the fresh PARCEL geocode disagrees with the current placement.
- **Acceptance:** unit tests (1.8) cover each branch; the 200-sample reproduces ~73% Verifiable.

## 1.5 Schema — new transactions columns (derived table, additive)  ☐
- **What:** columns to hold provenance. `transactions` is a derived table (dropped/rebuilt by the
  compiler), so editing the CREATE statement is sufficient — no data migration needed.
- **Where:** `cleo/database/schema.py` `CREATE TABLE transactions` (~`:51-97`): add
  `parcel_loc_name TEXT, parcel_addr_type TEXT, parcel_geocode_score REAL, parcel_field_match INTEGER,
  parcel_containment TEXT, parcel_confidence REAL, pip_verified INTEGER, parcel_tier TEXT`.
- **Acceptance:** after a rebuild, `PRAGMA table_info(transactions)` shows the new columns; CRM and
  other derived data unaffected.

## 1.6 Full re-geocode pass (all 95,444 distinct, cached, resumable)  ☐
- **What:** run resolution over every transaction capturing the new signals; annotate the current
  placement with tier/provenance; record disagreements as Review candidates. **Does not move
  placements.**
- **Where:** extend `engines/rt/parcel_resolver/resolve_v2.py` (it already has checkpoint/resume and
  the throttle hard-stop). Add a `--verify-only` mode that geocodes (via 1.1 cache), computes
  containment + field-match + tier, and writes them to parcel_links without changing `resolved_arn`.
- **Run:** unattended, ~1.5 days first time (free), resumable; subsequent runs instant from cache.
- **Acceptance:** every transaction has a tier; tier distribution reported; 0 network calls on re-run.

## 1.7 Review queue → issues + Data Quality UI  ☐
- **What:** make the Review-tier transactions visible and actionable.
- **Where:**
  - Compiler/verify writes Review records to the existing `issues` table (migration 036) with
    categories e.g. `parcel_interpolated`, `parcel_not_contained`, `parcel_low_confidence`,
    `parcel_geocode_disagrees`.
  - Frontend: extend `src/pages/DataQualityPage.tsx` (+ `/api/data-quality`) to filter/sort by the
    new categories and show tier counts. Read-only.
- **Acceptance:** Data Quality page shows tier distribution and a filterable Review list; clicking a
  row shows the RT address vs the geocoded parcel address + `loc_name`.

## 1.8 Tests  ☐
- **Where:** `tests/` (pytest already present). Add: field-match canonicalization cases (St/Street,
  Mc/Mac, ordinals, directionals); tier-assignment truth table; cache hit/miss + idempotency;
  containment-flag plumbing. Use a fixed fixture set incl. the St. Thomas pair.
- **Acceptance:** `pytest` green; St. Thomas SDM(107)/Rona(101) both classify correctly.

---

## Verification / acceptance (the measured result)
- **Metric:** tier distribution across all 124,544 (target context: ~73% of the old `spatial_geocode`
  bucket → Verified, ~25% → Review). Before/after counts persisted for comparison.
- **Spot-checks:** St. Thomas pair; a random 25 Review-tier rows hand-eyeballed against AgMaps.
- **Adversarial review:** run a subagent (or `pytest`) over the tier logic + a sample of outputs to
  confirm no Verified row is actually on the wrong parcel.

## Explicitly OUT of scope for Stage 1 (later stages)
- Using the tier to **change** placement; killing the nearest-centroid fallback as the live decision.
- First-class `parcels` table; repointing CRM (Stage 2).
- Promote-on-improvement re-resolution (Stage 3).
- OSM rooftop anchoring + brand-aware typing (Stage 4).
- Apify collector + GW extension (Stage 5).

## Safety / rollback
- All changes additive; a normal `rebuild.py` reproduces the DB. If anything looks wrong, the new
  columns/issues can be ignored — placement logic is untouched, so the app behaves exactly as today
  until we deliberately flip tiers into the decision in Stage 2/3.

## Suggested build order
1.5 (columns) → 1.1 (cache) → 1.2 (containment) → 1.4 (field-match/tier) → 1.3 (plumbing) →
1.8 (tests) → 1.6 (run) → 1.7 (surface). Each is a separate commit; 1.1–1.5 are safe no-ops until 1.6 runs.
