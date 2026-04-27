# Brand Family View + Cross-Silo Search

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Builds on:** `2026-04-27-explorer-ngrams-456plus-and-containment.md` (shipped — full 1/2/3/4/5/long-form silos with containment links).

**Goal:** Stop forcing the user to walk the n-gram hierarchy one level at a time. Add three things that match how the user actually browses:

1. A **Family view** on every n-gram detail page that surfaces the entire related-data set (Tight + Loose) across all 6 silos, in one place.
2. A **top-level Brand search bar** that queries all 6 silos at once and shows results grouped by level.
3. A **position-anchor flag** on 1-grams that have clean prefix/suffix patterns but get filtered out by the wordfreq/place/industry signals (the `dh` case). Surfaces them as browseable seeds without changing `is_distinctive`.

**Out of scope:** Layer 2 work — operator canonicalization, alias resolution, cross-silo address/phone/contact triangulation. None of that lands here. This plan is purely about making the existing Layer 1 data more browseable.

---

## 1. The Family view — Tight + Loose

For any n-gram detail page (kingsett 1-gram, canadian commercial 2-gram, dufferin peel catholic district school board long-form), render a "Family" section showing related n-grams across all six brand silos.

### Tight family

> n-grams that contain the seed string as a contiguous word run.

For seed `canadian commercial` (2-gram): every n-gram (3-gram and above) whose string contains `canadian commercial` as adjacent words. Catches `canadian commercial development`, `canadian commercial capital`, `canadian commercial development windsor inc`, etc. Excludes `canadian development corp` (token-shared but not contiguous).

For seed `kingsett` (1-gram, single token): every n-gram (2-gram and above) containing `kingsett` as a token.

For long-form seeds: same word-run rule. Probably small or empty (no longer level above long-form).

### Loose family

> n-grams that contain ANY of the seed's constituent tokens, regardless of position or co-occurrence.

For seed `canadian commercial`: two stacked sections.
- **via `canadian`** — every n-gram of any level containing `canadian` as a token. Sorted by `n_party_sides` desc. Default-collapsed (will be ~5K entries).
- **via `commercial`** — same shape. Default-collapsed.

For 1-gram seeds: only one constituent token → only one section, AND it's identical to the Tight family. The Loose section just doesn't render in that case.

For seed `dh management`: two sections — `via dh` (~30 entries) and `via management` (~5K entries).

### UI shape

Place the Family section **after** "Constituent token signals" and **before** "Brand phrases containing this token" on every detail page. Replaces the current "Contains" / "Extended by" cards (those become redundant — a Tight family naturally includes immediate-and-distant descendants).

```
┌────────────────────────────────────────────────────────────┐
│ Family (Tight)                                             │
│  canonical word-run match across 6 silos                   │
├────────────────────────────────────────────────────────────┤
│  level | value                              | sides | go  │
│  3-gram  canadian commercial development      16      [→] │
│  4-gram  canadian commercial development gr.. 5       [→] │
│  3-gram  canadian commercial capital          5       [→] │
│  ...                                                       │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│ Family (Loose)                              [Expand all]   │
│  any constituent token, all silos                          │
├────────────────────────────────────────────────────────────┤
│ ▶ via "canadian" (4,832 entries)                           │
│ ▶ via "commercial" (3,109 entries)                         │
└────────────────────────────────────────────────────────────┘
```

### Backend: `GET /api/explorer/brands/family`

Query params: `seed_value`, `seed_level` (one of `1gram`/`2gram`/.../long-form). Optional `loose_token` to fetch a specific Loose section's contents (paginated).

Response shape:

```json
{
  "seed_value": "canadian commercial",
  "seed_level": "2gram",
  "tight": [
    {"value": "canadian commercial development", "level": "3gram", "n_party_sides": 16},
    {"value": "canadian commercial development group", "level": "4gram", "n_party_sides": 5},
    ...
  ],
  "loose_sections": [
    {"token": "canadian", "n_total": 4832, "preview": [first 50]},
    {"token": "commercial", "n_total": 3109, "preview": [first 50]}
  ]
}
```

The detail page renders Tight in full, Loose-section previews collapsed; expanding a Loose section fetches the full token's family via a separate paginated call. Saves on initial page weight (Loose sections can be huge).

For implementation, the Tight query is one SQL per silo, filtered with `WHERE <silo_value_col> LIKE '% ' || ? || ' %'` (with leading-trailing space pad for word-boundary safety). Loose queries are similar but check the constituent token column directly (`WHERE token = ?` for 1-gram silo, `WHERE token_a = ? OR token_b = ? OR ...` for n-gram silos).

## 2. Cross-silo Brand search bar

A persistent search bar at the top of every Brand sub-tab. Queries all 6 silos at once, returns results grouped by level.

### Backend: `GET /api/explorer/brands/search`

Query params: `q` (substring), `per_level` (max results per level, default 25).

Response:

```json
{
  "q": "canadian commercial",
  "results_by_level": {
    "1gram":     [{"value": "canadian", "n_party_sides": 10956, "is_distinctive": 0, "is_position_anchor": 0}, ...],
    "2gram":     [{"value": "canadian commercial", "n_party_sides": 94, "is_distinctive": 1}, ...],
    "3gram":     [...],
    "4gram":     [...],
    "5gram":     [...],
    "long-form": [...]
  }
}
```

The frontend renders these as 6 collapsible sections. Each row clickable → routes to the appropriate detail page.

The query semantics: substring match on the n-gram value column, case-insensitive. Sorted by n_party_sides desc within each level.

## 3. Position-anchor flag

A new derived flag on `brand_token_summary` indicating: "this 1-gram's pattern of usage suggests it anchors an operator family even though distinctiveness filters knocked it out."

### Definition

A 1-gram qualifies as a position-anchor when ALL hold:

- `n_party_sides >= 10` (filter noise)
- `is_distinctive = 0` (already filtered — we're rescuing these)
- `is_excluded = 0` (excluded artifacts stay excluded)
- `position_consistency >= 0.95`, where `position_consistency = max(pos_a_count, pos_b_count) / (pos_a_count + pos_b_count)` measured across the token's appearances in 2-grams
- `total_child_coverage >= 0.85`, where `total_child_coverage = sum(n_party_sides of all 2-grams containing this token) / n_party_sides of this 1-gram`. (Capped at 1.0 — the same party-side may appear under multiple 2-grams.)
- `n_distinct_children >= 3` (at least three 2-grams contain it — single-child cases aren't strong enough signal)

### Schema change (migration 013)

```sql
ALTER TABLE brand_token_summary ADD COLUMN position_consistency REAL;
ALTER TABLE brand_token_summary ADD COLUMN total_child_coverage REAL;
ALTER TABLE brand_token_summary ADD COLUMN is_position_anchor INTEGER NOT NULL DEFAULT 0;
```

The two REAL columns are kept for visibility (so the user can see the actual numbers behind the flag, and so we can tune the threshold from data later).

### Builder change

In `cleo.discovery_v2.brand_index.build_brand_index`, after computing the existing per-token stats, run a second pass to compute position consistency and child coverage from `brand_bigram_summary` and `brand_bigram_index`. Update the summary rows.

This pass MUST run after `brand_bigram_index` is populated, so reorder `build_all_indexes`: build the 1-gram index first (without the position-anchor fields), then the 2-gram index, then back-fill position-anchor fields onto the 1-gram summary. Or compute it inline during the bigram build.

### UI change — 1-gram list page

Add a second toggle next to "Distinctive only":

```
☑ Distinctive only        ☑ Include position-anchors
```

When both ON (default): show 1-grams where `is_distinctive = 1 OR is_position_anchor = 1`. Position-anchor rows get a small `PA` badge in the flags column.

When "Distinctive only" OFF: show all 1-grams (current behavior).

When "Distinctive only" ON, "Include position-anchors" OFF: show only `is_distinctive = 1`.

Default state is both ON so the user sees the broadest legitimate-seed view by default.

### UI change — 1-gram detail page

In the existing "Signals" section, add a "Position-anchor" line showing `position_consistency`, `total_child_coverage`, and `n_distinct_children` if the flag is set. Lets the user understand why a non-distinctive token is being surfaced.

## File Structure

**Created:**
- `cleo/database/migrations/013_position_anchor_columns.py`
- `frontend/src/components/explorer/BrandFamily.tsx`
- `frontend/src/components/explorer/BrandSearchBar.tsx`

**Modified:**
- `cleo/discovery_v2/brand_index.py` — compute position_consistency, total_child_coverage, is_position_anchor in the unigram build
- `cleo/web/routes/explorer.py` — add `/brands/family`, `/brands/search`, return new fields in 1-gram list+detail
- `frontend/src/types/index.ts` — `BrandTokenSummary` gets new fields, new `BrandFamilyResponse`, `BrandSearchResponse` types
- `frontend/src/pages/ExplorerBrandsUnigram.tsx` — second toggle + PA badge column
- `frontend/src/pages/ExplorerBrandUnigramDetail.tsx` — render BrandFamily, drop the old NgramContainment
- `frontend/src/pages/ExplorerBrandBigramDetail.tsx` — same
- `frontend/src/pages/ExplorerBrandTrigramDetail.tsx` — same
- `frontend/src/pages/ExplorerBrand4gramDetail.tsx` — same
- `frontend/src/pages/ExplorerBrand5gramDetail.tsx` — same
- `frontend/src/pages/ExplorerBrandLongFormDetail.tsx` — same
- `frontend/src/pages/ExplorerBrands*.tsx` (all 6 list pages) — embed `<BrandSearchBar />` above the per-silo content
- `tests/test_routes_explorer.py` — coverage for the two new endpoints + position_anchor field
- `tests/test_discovery_v2_brand_index.py` — coverage for the position_anchor builder logic

---

## Tasks

### Task 1 — Migration 013 + builder changes

- [ ] Create migration `013_position_anchor_columns.py` adding 3 columns to `brand_token_summary`
- [ ] In `cleo/discovery_v2/brand_index.py`, after the unigram + bigram builds, compute and populate position_consistency, total_child_coverage, is_position_anchor for every 1-gram. Two ways: (a) inline in `build_brand_index` (clean if 2-gram is already built first), (b) a separate post-pass `_recompute_position_anchors(conn)` called from `build_all_indexes` after the bigram build. Pick (b) since the 1-gram build currently happens BEFORE the 2-gram build.
- [ ] Add tests covering: position-consistent prefix → flag set; mixed-position token → flag NOT set; single-child token → flag NOT set; already-distinctive token → flag stays 0 (we don't double-flag, only rescue).
- [ ] Run against real DB. Capture: how many tokens have `is_position_anchor = 1`? Top 20 by n_party_sides. Confirm `dh` is in there.
- [ ] Commit.

### Task 2 — `/brands/family` and `/brands/search` endpoints

- [ ] Add `_list_brand_ngrams_loose(conn, token, level)` helper for the per-token Loose lookup.
- [ ] Add `GET /api/explorer/brands/family` endpoint returning Tight + Loose-previews.
- [ ] Add `GET /api/explorer/brands/family/loose` endpoint for paginated single-token Loose fetches.
- [ ] Add `GET /api/explorer/brands/search` endpoint returning results grouped by level (capped at `per_level` entries each).
- [ ] Tests for: Tight contiguous-word match, Loose token match, Search across all 6 levels, position-anchor field present on 1-gram results.
- [ ] Smoke test against real DB.
- [ ] Commit.

### Task 3 — `BrandFamily` component + replace NgramContainment on all 6 detail pages

- [ ] Create `BrandFamily.tsx`. Props: `seed_value`, `seed_level`. On mount, fetch the family endpoint. Renders Tight section (table) + Loose sections (collapsible per token, lazy-load on expand).
- [ ] Replace `<NgramContainment>` with `<BrandFamily>` on all 6 detail pages.
- [ ] Delete `NgramContainment.tsx` and its imports — superseded.
- [ ] Update types in `frontend/src/types/index.ts`: add `BrandFamilyResponse`, `BrandFamilyEntry`. Drop `NgramContainmentEntry` (no longer used).
- [ ] Smoke test: navigate from `/explorer/brands/2gram/canadian%20commercial` → see Tight family with the SPV variants, Loose collapsed sections for `canadian` and `commercial`. Expand `canadian` → list paginates correctly.
- [ ] Commit.

### Task 4 — Top-level Brand search bar

- [ ] Create `BrandSearchBar.tsx`. Renders an always-visible input. On submit, hits `/brands/search`. Renders 6 grouped result sections; each row links to the appropriate detail page.
- [ ] Embed `<BrandSearchBar />` at the top of the 6 Brand list pages (above the per-silo search).
- [ ] Smoke test: type "kingsett" → see results from all 6 levels. Type "canadian commercial" → see the 2-gram and its descendants. Click any row → routes to the correct detail.
- [ ] Commit.

### Task 5 — Position-anchor toggle on 1-gram list + PA badge

- [ ] Update `ExplorerBrandsUnigram.tsx`. Add a second checkbox "Include position-anchors" defaulting ON, alongside the existing "Distinctive only" toggle.
- [ ] Pass `include_position_anchors=true` as a query param to `/brands` when set; backend filter switches accordingly. Backend addition: list endpoint accepts `include_position_anchors` (bool, default true), returns rows where `is_distinctive = 1 OR is_position_anchor = 1` when both filters active.
- [ ] Add `PA` badge in the flags column for rows with `is_position_anchor = 1`.
- [ ] Update `ExplorerBrandUnigramDetail.tsx` to show position_consistency, total_child_coverage, n_distinct_children numbers in the Signals section when `is_position_anchor = 1`.
- [ ] Smoke test: open 1-gram list with both toggles ON. Confirm `dh` appears with a PA badge. Click into it. Confirm signals show position-consistency stats.
- [ ] Commit.

### Task 6 — Rebuild + verification pass

- [ ] Run `python3 -m cleo.discovery_v2`. Confirm logs include the position-anchor pass count.
- [ ] Spot-check: Family view for `canadian commercial`, `dh management`, `kingsett`, `york region district school board`. Confirm Tight + Loose render correctly. Confirm `dh` appears in 1-gram list with PA badge.
- [ ] Cross-silo search: type "DH" → see 1-gram `dh` (PA), 2-grams `dh management` etc., 3-grams, all surfaced in one view.
- [ ] No code changes — verification only. If anything breaks, file specific tickets and stop.

---

## Self-Review Checklist

- [x] Family view replaces the existing Contains / Extended by cards (those become redundant — Tight family includes their data and more).
- [x] Loose mode is stacked-by-token to keep provenance clear.
- [x] Position-anchor flag doesn't change `is_distinctive`. It's a parallel signal.
- [x] Defaults shown to user surface the broadest legitimate set of seeds (distinctive + position-anchor).
- [x] No operator canonicalization. No alias resolution. No cross-silo work. Pure browsability + a missing-prefix flag.
- [x] Migration is idempotent (column adds use `ADD COLUMN` checked against `PRAGMA table_info` first).

---

## Execution Handoff

6 tasks. Subagent-Driven Development (default).
