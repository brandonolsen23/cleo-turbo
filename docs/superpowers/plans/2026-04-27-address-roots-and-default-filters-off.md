# Address Roots Hierarchy + Brand Default-Filters-Off

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Builds on:** `2026-04-24-explorer-layer-1-silos.md` (Addresses base silo shipped) + `2026-04-27-brand-family-view-and-search.md` (Brand Family + Search shipped).

**Goal:** Make Layer 1 address data show the same kind of hierarchy the Brand silo got. Add an Address **Root** layer (`street_number + street_name`, no suffix) above the existing Base layer (`street_number + street_name + street_suffix`). Within each root, surface breakdowns by suffix / suite / postal so the user can see how a big bucket like "66 wellington" splits across its variants.

**Plus a small companion change**: flip the default filter toggles on the Brand list pages OFF, so users land on the full unfiltered view by default. Toggles stay available for narrowing.

**No filters at the Address Root level.** Show every distinct (street_number, street_name) pair, sorted by party-side count.

---

## 1. Address Root design

### Schema

New table parallel to `address_base_summary`, one level shallower (drops suffix):

```sql
CREATE TABLE address_root_summary (
    street_number          TEXT NOT NULL,
    street_name            TEXT NOT NULL,
    n_party_sides          INTEGER NOT NULL,
    n_distinct_suffixes    INTEGER NOT NULL,
    n_distinct_directions  INTEGER NOT NULL,
    n_distinct_suites      INTEGER NOT NULL,
    n_distinct_postals     INTEGER NOT NULL,
    discovered_at          TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (street_number, street_name)
);
CREATE INDEX idx_ars_n ON address_root_summary(n_party_sides);
```

### Builder

```python
def build_address_root_summary(conn, *, verbose=True):
    conn.execute("DELETE FROM address_root_summary")
    conn.execute("""
        INSERT INTO address_root_summary
            (street_number, street_name, n_party_sides, n_distinct_suffixes,
             n_distinct_directions, n_distinct_suites, n_distinct_postals)
        SELECT street_number, street_name,
               COUNT(*),
               COUNT(DISTINCT COALESCE(street_suffix, '')),
               COUNT(DISTINCT COALESCE(street_direction, '')),
               COUNT(DISTINCT COALESCE(suite_type, '') || '|' || COALESCE(suite_number, '')),
               COUNT(DISTINCT COALESCE(postal, ''))
        FROM party_fingerprints
        WHERE street_number IS NOT NULL AND street_number != ''
          AND street_name IS NOT NULL AND street_name != ''
        GROUP BY street_number, street_name
    """)
    n = conn.execute("SELECT COUNT(*) FROM address_root_summary").fetchone()[0]
    conn.commit()
    if verbose:
        print(f"Layer 1 Silo C (address roots): {n:,} distinct roots", flush=True)
    return {"n_roots": n}
```

Wired into `build_all_indexes` after `build_address_base_summary`.

### API

```
GET /api/explorer/addresses/roots?q=&page=&per_page=
GET /api/explorer/addresses/roots/{key}    # key = "<number>|<name>"
```

List endpoint accepts `q` (substring on number or name) and pagination. No filter toggles.

Detail endpoint returns:

```json
{
  "street_number": "66",
  "street_name": "wellington",
  "key": "66|wellington",
  "n_party_sides": 291,
  "n_distinct_suffixes": 2,
  "n_distinct_directions": 1,
  "n_distinct_suites": 18,
  "n_distinct_postals": 3,
  "by_suffix": [
    {"value": "street", "n_party_sides": 280, "base_key": "66|wellington|street"},
    {"value": "(none)",  "n_party_sides": 11,  "base_key": "66|wellington|"}
  ],
  "by_suite": [
    {"suite_type": "suite", "suite_number": "4400", "n_party_sides": 38},
    {"suite_type": "suite", "suite_number": "4500", "n_party_sides": 12},
    {"suite_type": null,    "suite_number": null,    "n_party_sides": 201},
    ...
  ],
  "by_postal": [
    {"postal": "M5K1H6", "n_party_sides": 198},
    {"postal": "M5K1A2", "n_party_sides": 23},
    ...
  ],
  "party_sides": [ ... full hydrated party-side cards with brand_phrases, phone, contact ... ]
}
```

Each breakdown section is sorted by `n_party_sides` desc and capped at 50 entries (with `n_distinct_*` showing the full count so the user knows when truncation happened). Party-sides list isn't capped — same shape as the existing Base detail.

### URL structure

```
/explorer/addresses                       → redirect to /explorer/addresses/roots
/explorer/addresses/roots                 → roots list (new, default landing)
/explorer/addresses/roots/:key            → root detail (new) — key = "<number>|<name>"
/explorer/addresses/bases                 → bases list (existing, just rerouted from /addresses)
/explorer/addresses/bases/:key            → base detail (existing)
```

Sub-tab bar under Addresses: `Roots | Bases`. Roots active by default.

### UI shape — Root detail page

Reuses the same `PartySideCard` component everywhere else uses. The four breakdown panels render above the party-sides list:

```
┌─────────────────────────────────────────────────────────────────────┐
│ ← Address Roots                                                      │
│                                                                      │
│ 66 wellington                                                        │
│                                                                      │
│ ┌─────────────┬─────────────┬─────────────┬─────────────┬─────────┐ │
│ │ party-sides │ suffixes    │ suites      │ postals     │ direc.. │ │
│ │     291     │      2      │     18      │      3      │    1    │ │
│ └─────────────┴─────────────┴─────────────┴─────────────┴─────────┘ │
│                                                                      │
│ By suffix (2 distinct)                                               │
│   street    280 sides  → /explorer/addresses/bases/66|wellington|street│
│   (none)     11 sides  → (no Base entry — partial address)           │
│                                                                      │
│ By suite (18 distinct, top 50 shown)                                 │
│   suite 4400   38 sides                                              │
│   suite 4500   12 sides                                              │
│   (no suite)  201 sides                                              │
│   …                                                                  │
│                                                                      │
│ By postal (3 distinct)                                               │
│   M5K1H6     198 sides                                               │
│   M5K1A2      23 sides                                               │
│   M5K1B7      18 sides                                               │
│                                                                      │
│ Party-sides (291)                                                    │
│   [PartySideCard …] × 291                                            │
└─────────────────────────────────────────────────────────────────────┘
```

The `By suffix` rows that have a base_key link through to the existing Base detail page; the `(none)` row has no link target since there's no `address_base_summary` row for partial addresses. The `By suite` and `By postal` rows are display-only for now (not clickable — clicking them would mean filtering the party-sides list inline, which is more UI work than this plan covers).

## 2. Brand default-filters-off

Change the default state of the existing filter toggles on Brand list pages so the user lands on the full unfiltered view:

- `ExplorerBrandsUnigram.tsx` — `distinctiveOnly` defaults to `false`. `includeAnchors` stays `true` (it doesn't filter anything when distinctiveOnly is off; just makes sure PA-flagged tokens are visible alongside everything else).
- `ExplorerBrandsBigram.tsx`, `Trigram`, `4gram`, `5gram`, `LongForm` — `distinctiveOnly` defaults to `false`.

Backend doesn't need changes — these are frontend-only default flips.

The filter UI elements stay in place so the user can opt-in to narrowing when they want.

---

## File Structure

**Created:**
- `cleo/database/migrations/014_address_root_summary.py`
- `frontend/src/pages/ExplorerAddressRoots.tsx`
- `frontend/src/pages/ExplorerAddressRootDetail.tsx`
- `frontend/src/components/explorer/AddressTabs.tsx` — sub-tab bar `Roots | Bases`

**Modified:**
- `cleo/discovery_v2/brand_index.py` — add `build_address_root_summary` and call it from `build_all_indexes`
- `cleo/web/routes/explorer.py` — add `/addresses/roots` list + detail endpoints
- `cleo/web/routes/explorer.py` — also keep `/addresses` and `/addresses/{key}` working (no breakage for existing paths)
- `frontend/src/types/index.ts` — types for `AddressRootSummary`, `AddressRootListResponse`, `AddressRootDetail`, breakdown entries
- `frontend/src/App.tsx` — routes for `/explorer/addresses/roots` (list + detail), redirect from `/explorer/addresses` to `/explorer/addresses/roots`, route for `/explorer/addresses/bases` (existing pages renamed/rerouted)
- `frontend/src/pages/ExplorerAddresses.tsx` — re-route under `/explorer/addresses/bases`, embed `<AddressTabs />` sub-tab bar
- `frontend/src/pages/ExplorerAddressDetail.tsx` — re-route under `/explorer/addresses/bases/:key`
- `frontend/src/pages/ExplorerBrandsUnigram.tsx` — `distinctiveOnly` default to `false`
- `frontend/src/pages/ExplorerBrandsBigram.tsx` — same
- `frontend/src/pages/ExplorerBrandsTrigram.tsx` — same
- `frontend/src/pages/ExplorerBrands4gram.tsx` — same
- `frontend/src/pages/ExplorerBrands5gram.tsx` — same
- `frontend/src/pages/ExplorerBrandsLongForm.tsx` — same
- `tests/test_routes_explorer.py` — coverage for `/addresses/roots` list + detail
- `tests/test_discovery_v2_layer1_silos.py` — coverage for `build_address_root_summary`

---

## Tasks

### Task 1 — Migration 014 + builder

- [ ] Create migration 014 adding `address_root_summary` table + `idx_ars_n` index.
- [ ] Add `build_address_root_summary` to `cleo/discovery_v2/brand_index.py`. Call it from `build_all_indexes` after `build_address_base_summary`.
- [ ] Add tests covering: distinct (number, name) pairs aggregated correctly; n_distinct_suffixes/suites/postals computed correctly; partial-suffix rows still counted.
- [ ] Run migration + full discovery_v2 build. Capture: total root count + top 10 roots by sides.
- [ ] Commit.

### Task 2 — API endpoints

- [ ] Add `GET /api/explorer/addresses/roots` (list, with `q` substring on number or name, pagination, sorted by `n_party_sides` desc).
- [ ] Add `GET /api/explorer/addresses/roots/{key}` (detail with by_suffix / by_suite / by_postal breakdowns + hydrated party_sides).
- [ ] Decode `key` as `"<number>|<name>"`. Return 400 on malformed key, 404 on unknown root.
- [ ] Each breakdown query SELECTs from `party_fingerprints` directly (no need to denormalize into the summary table). Cap each breakdown at 50 entries; total counts come from `address_root_summary`.
- [ ] `by_suffix` entries with a non-empty suffix include a `base_key` field (`"<number>|<name>|<suffix>"`); the no-suffix entry has `base_key = null`.
- [ ] Tests for: list pagination, detail with multiple suffixes/suites/postals, 404 on unknown.
- [ ] Smoke test against real DB.
- [ ] Commit.

### Task 3 — Frontend tab restructure + new Roots pages

- [ ] Create `AddressTabs.tsx` — sub-tab bar with `Roots | Bases`. Pattern mirrors `ExplorerTabs` but only addresses-scoped.
- [ ] Create `ExplorerAddressRoots.tsx` — list page. Search input (substring), paginated table with columns: root address (formatted), n_party_sides, n_distinct_suffixes, n_distinct_suites, n_distinct_postals. Click row → root detail.
- [ ] Create `ExplorerAddressRootDetail.tsx` — detail with stat-card row, three breakdown sections (by_suffix / by_suite / by_postal), and the standard PartySideCard list. By_suffix rows that have a base_key link to the Base detail; the no-suffix row is text-only.
- [ ] Move existing `ExplorerAddresses.tsx` and `ExplorerAddressDetail.tsx` under the `/explorer/addresses/bases` route prefix. Add `<AddressTabs />` to the top of both.
- [ ] App.tsx: add redirects + new routes. `/explorer/addresses` → `/explorer/addresses/roots`. New routes for `/explorer/addresses/roots` + `/explorer/addresses/roots/:key`. Existing paths re-rerouted under `/bases`.
- [ ] TypeScript check + browser smoke test (root list loads, click into 66 wellington shows breakdowns).
- [ ] Commit.

### Task 4 — Brand default-filters-off

- [ ] In each of the 6 Brand list pages, change the initial state of `distinctiveOnly` from `true` to `false`. Leave the toggle UI in place — only the default flips.
- [ ] On the 1-gram page, `includeAnchors` stays at `true`.
- [ ] Browser smoke test: open `/explorer/brands/1gram` — see ALL tokens (not just distinctive). Toggle "Distinctive only" ON → narrows to distinctive + position-anchor.
- [ ] Commit.

### Task 5 — Rebuild + verification

- [ ] Run `python3 -m cleo.discovery_v2`. Confirm address-root build line in output.
- [ ] Spot-check: top 10 roots by sides include "1 yonge", "100 king", "66 wellington" or similar downtown towers.
- [ ] Click "66 wellington" → detail loads with `By suffix`, `By suite`, `By postal` breakdowns visible.
- [ ] Click `street` row in `By suffix` → Base detail loads (existing page).
- [ ] Open each Brand silo list page — confirm filter toggles default to OFF.
- [ ] No code changes — verification only.

---

## Self-Review Checklist

- [x] No filters on Address Roots (only a search input).
- [x] Brand list pages default to unfiltered (matches the no-filter principle).
- [x] Existing Address Base pages still work — just re-routed under `/bases`.
- [x] No new top-level Address search bar (existing per-list search is sufficient — addresses don't have the cross-level structure that Brand n-grams do).
- [x] Phones / Contacts unchanged — atomic data, no hierarchy to add.
- [x] No clustering, no inference, no Layer 2 work.

---

## Execution Handoff

5 tasks. Subagent-Driven Development.
