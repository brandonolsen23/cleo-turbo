# Unified Brand System — Implementation Plan

## Problem Statement

The current OSM POI / brand / tenant pipeline has three structural issues:

1. **Lossy pipeline.** The Overpass fetch pulls ~50,778 branded POIs with ~1,619 unique brands in Ontario. The `process.py` filter keeps only 136 brands from `brands.csv`, discarding 66% of the data. Of the 136 tracked brands, 32 silently fail due to alias mismatches (e.g., "Scotiabank" in OSM vs "Scotia Bank" in CSV, "McDonald's" vs "McDonalds"). Only ~104 brands actually make it through.

2. **Three disconnected brand definitions.** Brand-to-category mappings are maintained in three places that must stay in sync manually:
   - `engines/osm/brands.csv` (136 brands — pipeline source of truth)
   - Hardcoded aliases in `engines/osm/process.py` (~25 aliases)
   - `frontend/src/lib/brandCategories.ts` (128 brands — frontend source of truth)

3. **No user customization.** The set of "important" brands is baked into code. Adding a brand requires editing files in three places and rerunning the pipeline. There's no way for users to choose which brands matter to them.

## Design Goals

- **Let all branded POIs through the pipeline.** Store everything; filter at the UI layer.
- **Single source of truth for brand metadata.** One place where brand → category mappings live, queryable by the frontend via API.
- **User-level favorites.** Each user can curate which brands appear in their default filter views. The current ~136 curated brands become the default starter set.
- **Manual category assignment.** Users can assign or change the category for any brand from a Settings page — including long-tail brands that weren't in the original CSV.
- **Future-proof.** The same pattern (registry + overrides + favorites) can extend to other classification dimensions later.

---

## Architecture

### Data Model

Three new tables, fitting cleanly into the existing derived/CRM split:

```
┌─────────────────────────────────────────────────────┐
│ brand_registry (DERIVED — rebuilt by compiler)       │
│                                                      │
│  brand TEXT PRIMARY KEY    -- canonical name          │
│  category TEXT             -- from CSV, or NULL       │
│  poi_count INTEGER         -- how many POIs           │
│  is_curated BOOLEAN        -- true if in CSV          │
│  sample_osm_tags TEXT      -- JSON: shop, amenity,    │
│                               cuisine from OSM        │
│  created_at TEXT                                      │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────┐
│ brand_overrides (CRM — never rebuilt)                │
│                                                      │
│  brand TEXT PRIMARY KEY    -- matches brand_registry  │
│  category TEXT             -- user-assigned category  │
│  updated_by TEXT           -- user who made the edit  │
│  updated_at TEXT                                      │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ user_brand_favorites (CRM — never rebuilt)           │
│                                                      │
│  user_id INTEGER           -- FK → users             │
│  brand TEXT                -- FK → brand_registry     │
│  created_at TEXT                                      │
│  PRIMARY KEY (user_id, brand)                        │
└─────────────────────────────────────────────────────┘
```

**Why three tables instead of one:**

- `brand_registry` is derived — the compiler rebuilds it every run by scanning all POIs. This keeps `poi_count` accurate and auto-discovers new brands when OSM data is refreshed. It gets dropped and recreated like other derived tables.
- `brand_overrides` is CRM — manual category edits persist across compiler runs. The compiler never touches it.
- `user_brand_favorites` is CRM — per-user preference data. The compiler never touches it.

**Category resolution priority:**
```
effective_category = brand_overrides.category ?? brand_registry.category ?? NULL
```

Manual override wins. Then CSV default. Then uncategorized.

### Retail Categories (Fixed Set — 10 values)

These stay as a fixed set defined in code (both backend and frontend). They need colors, they affect filter grouping, and they're a structural/design decision. The current 10 are:

| Category | Color (Radix) | Description |
|----------|---------------|-------------|
| Grocery | lime | Supermarkets, convenience |
| Big-Box Retail | blue | Walmart, Costco, Canadian Tire |
| Discount Retail | amber | Dollarama, Giant Tiger |
| Specialty Retail | plum | Best Buy, LCBO, furniture |
| QSR | orange | Quick-service restaurants |
| Full-Service | violet | Sit-down restaurants |
| Take-out | pink | Pizza, subs, juice bars |
| Fuel | indigo | Gas stations |
| Financial Services | cyan | Bank branches |
| Automotive | tomato | Dealerships |

Adding a new category in the future = add one row to the category color map in `theme.ts` and one constant in the backend. Low-frequency change, fine to keep in code.

### Relationship to Property Types

Property types (retail, industrial, multifamily, etc.) and brand categories (Grocery, QSR, Fuel, etc.) answer different questions:

- **Property type:** "What is this building?" → derived from RT scraper folder structure
- **Brand category:** "What business operates here?" → derived from OSM brand tags + user overrides

They correlate (a QSR tenant is almost always in a retail property) but aren't the same thing. A Starbucks can be in a strip mall, an office lobby, or a standalone pad.

**All branded POIs are retail properties.** The Overpass query fetches `brand`-tagged OSM elements, which are consumer-facing retail locations (the Scotiabank branch, not the Scotiabank office tower). The existing hardcoded `primary_property_type = 'retail'` and `asset_class = 'retail'` for POI-created properties is correct and stays as-is.

---

## Implementation Steps

### Step 1: Fix Brand Aliases (Quick Win)

**Goal:** Recover the 32 tracked brands that silently fail due to naming mismatches.

**What changes:**
- Create `engines/osm/brand_aliases.json` — a proper alias lookup table replacing the hardcoded dict in `process.py`
- Structure: `{ "OSM raw value": "Canonical name", ... }`
- Include all known mismatches:

```json
{
  "McDonald's": "McDonalds",
  "Scotiabank": "Scotia Bank",
  "Domino's": "Dominos Pizza",
  "The Beer Store": "Beer Store",
  "Petro-Canada": "Petro Can",
  "The Home Depot": "Home Depot",
  "No Frills": "NoFrills",
  "Your Independent Grocer": "Independant",
  "Popeyes": "Popeyes Louisiana Kitchen",
  "Mary Brown's": "Mary Brown's Chicken",
  "Baskin-Robbins": "Baskin Robbins",
  "Kelsey's": "Kelseys Original Roadhouse",
  "Montana's": "Montana's BBQ & Bar",
  "Milestones": "Milestones Grill & Bar",
  "PetSmart": "Pet Smart",
  "Ren's Pets": "Rens Pets",
  "Indigo": "Indigo / Chapters",
  "Chapters": "Indigo / Chapters",
  "Ultramar": "Ultrimar",
  "JYSK": "Jysk"
}
```

- Update `process.py` to load aliases from JSON file instead of hardcoded dict
- The alias file becomes the single place to add new name mappings

**Files touched:**
- `engines/osm/brand_aliases.json` (new)
- `engines/osm/process.py` (load aliases from JSON)

**Verification:** Reprocess OSM data. Compare brand counts before/after. The 32 zero-match brands should now have POI counts.

---

### Step 2: Open the Pipeline — Process All Branded POIs

**Goal:** Stop filtering to 136 brands. Let all ~50K branded POIs through.

**What changes in `engines/osm/process.py`:**

Currently the flow is:
```
raw POI → normalize brand → lookup in CSV → if not found: SKIP
```

New flow:
```
raw POI → apply alias mapping → normalize brand name → lookup in CSV
  → if found: set category from CSV, mark is_curated=true
  → if not found: set category=NULL, mark is_curated=false
  → ALWAYS write to clean-data/osm/
```

**Brand normalization rules (applied to all POIs):**
1. Apply alias mapping (brand_aliases.json)
2. Trim whitespace, normalize Unicode
3. Title-case for display consistency
4. The result becomes `tracked_brand` (canonical name)

**Stable ID assignment:**
- Existing OSM_00001–OSM_21012 stay stable (keyed by OSM element ID in the reconciler)
- New POIs get OSM_21013+ 
- The reconciler already handles this via `id_mappings` table

**Category field in POI JSON:**
- Curated brands: category from CSV (e.g., "Grocery", "QSR")
- Non-curated brands: `category: null`
- The compiler writes whatever category the POI has into the `pois` table
- The `brand_registry` table (Step 3) aggregates this

**POI count impact:** ~21K → ~50K POIs. SQLite handles this trivially.

**Parcel resolution impact:** The ~29K new POIs need parcel resolution. This is the expensive part (AgMaps API calls). Options:
- Run `resolve_pois_v2.py` on all new POIs (may take a few hours due to API throttling)
- Or defer resolution of non-curated brands initially and resolve incrementally
- Recommendation: resolve all at once. It's a one-time cost, and having parcel links for all POIs makes them linkable to properties immediately.

**Files touched:**
- `engines/osm/process.py` (remove brand filter gate, add is_curated flag)
- `engines/osm/brands.csv` (unchanged — still serves as curated list)
- POI JSON schema gets `is_curated` field

---

### Step 3: Database — New Tables + Compiler Changes

**Goal:** Create the `brand_registry`, `brand_overrides`, and `user_brand_favorites` tables. Update the compiler to populate `brand_registry`.

#### 3a. Schema Changes

Add to `DERIVED_TABLES` in `schema.py`:
```sql
CREATE TABLE IF NOT EXISTS brand_registry (
    brand           TEXT PRIMARY KEY,
    category        TEXT,
    poi_count       INTEGER DEFAULT 0,
    is_curated      INTEGER DEFAULT 0,
    sample_osm_tags TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_brand_registry_category ON brand_registry(category);
CREATE INDEX IF NOT EXISTS idx_brand_registry_curated ON brand_registry(is_curated);
```

Add to `CRM_TABLES` in `schema.py`:
```sql
CREATE TABLE IF NOT EXISTS brand_overrides (
    brand           TEXT PRIMARY KEY,
    category        TEXT NOT NULL,
    updated_by      TEXT,
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS user_brand_favorites (
    user_id         INTEGER NOT NULL REFERENCES users(id),
    brand           TEXT NOT NULL,
    created_at      TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, brand)
);

CREATE INDEX IF NOT EXISTS idx_user_brand_favorites_user ON user_brand_favorites(user_id);
```

Add `brand_registry` to `drop_derived_tables()`.

#### 3b. Compiler Changes — Writer Pass 5: Brand Registry

After Pass 4 (POIs), add a new pass that scans the `pois` table and populates `brand_registry`:

```python
# Pass 5: Brand Registry
rows = conn.execute("""
    SELECT brand, category, COUNT(*) as cnt
    FROM pois
    WHERE brand != ''
    GROUP BY brand
""").fetchall()

for brand, category, count in rows:
    is_curated = 1 if brand in curated_brands else 0
    conn.execute(
        "INSERT OR REPLACE INTO brand_registry (brand, category, poi_count, is_curated) "
        "VALUES (?, ?, ?, ?)",
        (brand, category, count, is_curated)
    )
```

The `curated_brands` set is loaded from `brands.csv` at the start of compilation.

#### 3c. Seed User Favorites on First Login

When a user first accesses the brand favorites system (or on account creation), seed their favorites from all `brand_registry` rows where `is_curated = 1`. This is handled in the API layer (Step 4), not the compiler.

**Files touched:**
- `cleo/database/schema.py` (new tables, update drop_derived_tables)
- `cleo/compiler/writer.py` (Pass 5: brand registry population)
- `cleo/compiler/reader.py` (load curated_brands set from CSV)

---

### Step 4: Backend API — Brand Endpoints

**Goal:** Serve brand data with favorites and overrides merged. Provide CRUD for favorites and overrides.

#### New Route File: `cleo/web/routes/brands.py`

**`GET /api/brands`** — Browse all brands with effective category and favorite status

Query params:
- `search` (text filter — searches brand name, case-insensitive)
- `category` (filter by effective category)
- `favorites_only` (boolean — only return user's favorites)
- `curated_only` (boolean — only return curated brands)
- `page`, `per_page` (pagination)

SQL (conceptual):
```sql
SELECT
    br.brand,
    COALESCE(bo.category, br.category) AS effective_category,
    br.poi_count,
    br.is_curated,
    CASE WHEN ubf.brand IS NOT NULL THEN 1 ELSE 0 END AS is_favorite
FROM brand_registry br
LEFT JOIN brand_overrides bo ON bo.brand = br.brand
LEFT JOIN user_brand_favorites ubf ON ubf.brand = br.brand AND ubf.user_id = ?
WHERE br.brand LIKE ?  -- search filter
ORDER BY br.poi_count DESC
```

Response:
```json
{
  "brands": [
    {
      "brand": "Starbucks",
      "category": "QSR",
      "poi_count": 412,
      "is_curated": true,
      "is_favorite": true
    },
    {
      "brand": "GoodLife Fitness",
      "category": null,
      "poi_count": 119,
      "is_curated": false,
      "is_favorite": false
    }
  ],
  "total": 1619,
  "page": 1,
  "per_page": 50,
  "pages": 33
}
```

**`GET /api/brands/favorites`** — Return only the current user's favorites (lightweight, for filter dropdowns)

Response:
```json
{
  "favorites": [
    { "brand": "Starbucks", "category": "QSR" },
    { "brand": "Loblaws", "category": "Grocery" }
  ]
}
```

If the user has no favorites yet (first login), auto-seed from curated brands and return those.

**`POST /api/brands/favorites`** — Add brands to favorites

Body: `{ "brands": ["IKEA", "Rexall"] }`
Response: `{ "added": 2 }`

**`DELETE /api/brands/favorites`** — Remove brands from favorites

Body: `{ "brands": ["Rexall"] }`
Response: `{ "removed": 1 }`

**`PUT /api/brands/category`** — Set/change category for a brand (writes to `brand_overrides`)

Body: `{ "brand": "IKEA", "category": "Big-Box Retail" }`
Response: `{ "brand": "IKEA", "category": "Big-Box Retail", "source": "override" }`

**`DELETE /api/brands/category`** — Remove a category override (reverts to CSV default or NULL)

Body: `{ "brand": "IKEA" }`
Response: `{ "brand": "IKEA", "category": null, "source": "default" }`

**`GET /api/brands/categories`** — Return the fixed category list with colors

Response:
```json
{
  "categories": [
    { "id": "Grocery", "color": "lime" },
    { "id": "QSR", "color": "orange" },
    ...
  ]
}
```

#### Modified Existing Endpoints

**`GET /api/properties/filters`** — Currently returns distinct brands from `pois` table. Change to return the user's favorite brands (with effective categories) instead of all brands. This keeps the filter dropdown manageable.

**`GET /api/groups/filters`** — Same change: return favorite brands instead of all brands.

**`GET /api/pois/brands`** — Keep as-is (returns all brands with counts from the raw pois table). This is a data endpoint, not a UI filter endpoint.

**Files touched:**
- `cleo/web/routes/brands.py` (new)
- `cleo/web/app.py` (register new router)
- `cleo/web/routes/properties.py` (update filters endpoint)
- `cleo/web/routes/groups.py` (update filters endpoint)

---

### Step 5: Frontend — Settings Page

**Goal:** A new `/settings` page where users manage their brand favorites and assign categories.

#### Page Layout

```
┌──────────────────────────────────────────────────────────┐
│ Settings                                                  │
│                                                           │
│ ┌─ Brand Favorites ────────────────────────────────────┐ │
│ │                                                       │ │
│ │  Your favorite brands appear in filter dropdowns      │ │
│ │  across the app. You have 136 favorites.              │ │
│ │                                                       │ │
│ │  ┌─ Search all brands... ──────────────────────────┐ │ │
│ │  └─────────────────────────────────────────────────┘ │ │
│ │                                                       │ │
│ │  [Show: All ▾]  [Category: All ▾]                    │ │
│ │                                                       │ │
│ │  ┌────────────────────────────────────────────────┐  │ │
│ │  │ ★ Loblaws          Grocery (17)     [Edit ▾]  │  │ │
│ │  │ ★ McDonalds         QSR (516)       [Edit ▾]  │  │ │
│ │  │ ★ Starbucks         QSR (412)       [Edit ▾]  │  │ │
│ │  │ ☆ GoodLife Fitness  —  (119)        [Set ▾]   │  │ │
│ │  │ ☆ Rexall            —  (226)        [Set ▾]   │  │ │
│ │  │ ☆ IKEA              —  (3)          [Set ▾]   │  │ │
│ │  │ ...                                            │  │ │
│ │  └────────────────────────────────────────────────┘  │ │
│ │                                                       │ │
│ │  ★ = favorited (shown in filters)                    │ │
│ │  ☆ = not favorited (click star to add)               │ │
│ │  (N) = POI count in Ontario                          │ │
│ │                                                       │ │
│ └───────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

#### Interactions

- **Star toggle:** Click ★/☆ to add/remove a brand from favorites. Calls `POST/DELETE /api/brands/favorites`.
- **Category dropdown:** Click "Edit ▾" or "Set ▾" to assign/change category from the 10-option list. Calls `PUT /api/brands/category`. The dropdown shows category names with color dots.
- **Search:** Text input filters the brand list client-side (with server-side search for the full 1,600+ if needed).
- **Show filter:** "All", "Favorites only", "Uncategorized only" — helps find brands that need attention.
- **Category filter:** Filter the list by category to see all QSR brands, all Grocery brands, etc.
- **Bulk actions (nice-to-have):** "Add all in category" button to favorite an entire category at once.

#### Route Setup

- Add `/settings` route in `App.tsx`
- Add "Settings" link in sidebar navigation (bottom section, with gear icon)
- Page component: `frontend/src/pages/SettingsPage.tsx`

**Files touched:**
- `frontend/src/pages/SettingsPage.tsx` (new)
- `frontend/src/App.tsx` (add route)
- `frontend/src/components/layout/Sidebar.tsx` (add nav link)

---

### Step 6: Frontend — Update Filter Dropdowns

**Goal:** Filter dropdowns read from the API (user's favorites) instead of hardcoded `brandCategories.ts`.

#### What Changes

**Map page (`MapPage.tsx`):**
- Brand/category filter data fetched from `GET /api/brands/favorites` instead of importing from `brandCategories.ts`
- The `MultiSelectDropdown` for brands shows favorited brands grouped by category
- Search box in the dropdown searches all brands (calls `GET /api/brands?search=...`) — if a user types a brand not in their favorites, it appears as a selectable option with a subtle "not in favorites" indicator
- `expandBrandFilter()` function still works the same way, but reads from API data instead of hardcoded maps

**Properties page (`PropertiesPage.tsx`):**
- Tenant brand dropdown populated from `GET /api/brands/favorites` instead of hardcoded list
- Same search-across-all behavior as map page

**Groups page (`GroupsPage.tsx`):**
- Same pattern: favorites from API, search across all

#### What Stays

- `theme.ts` category colors — these are display constants, fine in code
- `propertyTypeMatchExpression()` — unrelated to brands
- The `expandBrandFilter()` logic — just needs to read from API data instead of hardcoded constants

#### Migration Path for `brandCategories.ts`

This file gets replaced, not deleted all at once:

1. First, create a new hook: `useBrandData()` that fetches from the API and provides the same interface (`BRAND_TO_CATEGORY`, `CATEGORY_TO_BRANDS`, `ALL_BRANDS`, `expandBrandFilter`)
2. Update each page to use the hook instead of the import
3. Once all consumers are migrated, delete `brandCategories.ts`

**Files touched:**
- `frontend/src/hooks/useBrandData.ts` (new — API-backed brand data hook)
- `frontend/src/pages/MapPage.tsx` (use hook instead of hardcoded import)
- `frontend/src/pages/PropertiesPage.tsx` (same)
- `frontend/src/pages/GroupsPage.tsx` (same)
- `frontend/src/components/ui/MultiSelectDropdown.tsx` (add search-all-brands behavior)
- `frontend/src/lib/brandCategories.ts` (eventually deleted)

---

### Step 7: Cleanup & Verification

**Goal:** Remove dead code, verify data integrity, confirm everything works end-to-end.

#### Cleanup

- Delete `brandCategories.ts` after all consumers migrated
- Remove hardcoded `BRAND_ALIASES` dict from `process.py` (replaced by JSON file)
- Update `CLAUDE.md` to document the new brand system

#### Verification Checklist

- [ ] All 136 curated brands have non-zero POI counts (alias fixes working)
- [ ] Total POI count is ~50K (pipeline processing all brands)
- [ ] `brand_registry` table has ~1,600 rows
- [ ] New user gets 136+ favorites auto-seeded on first login
- [ ] Settings page loads, search works, star toggle persists
- [ ] Category override persists across compiler runs
- [ ] Map page brand filter shows favorites by default
- [ ] Map page brand search finds non-favorited brands
- [ ] Properties page brand filter works with API data
- [ ] Groups page brand filter works with API data
- [ ] Property detail page tenant badges show correct categories (including overrides)
- [ ] No TypeScript errors (`cd frontend && npx tsc`)
- [ ] Frontend builds cleanly (`cd frontend && npm run build`)

---

## Sequencing & Dependencies

```
Step 1 ─── Fix aliases ──────────────────────► Can ship independently
   │
Step 2 ─── Open pipeline ───────────────────► Depends on Step 1
   │                                            (needs good aliases before
   │                                             processing all brands)
   │
Step 3 ─── Database tables + compiler ──────► Depends on Step 2
   │                                            (compiler needs all POIs
   │                                             to build full registry)
   │
Step 4 ─── Backend API ────────────────────► Depends on Step 3
   │                                            (API reads from new tables)
   │
Step 5 ─── Settings page ─────────────────► Depends on Step 4
   │                                            (page calls new API)
   │
Step 6 ─── Update filter dropdowns ────────► Depends on Step 4 + 5
   │                                            (filters read from API,
   │                                             settings page should exist
   │                                             so users can manage brands)
   │
Step 7 ─── Cleanup & verification ─────────► After all steps complete
```

Steps 1–4 are backend/pipeline work. Steps 5–6 are frontend. Step 7 is cleanup.

Steps 1 and 2 could be tested independently by reprocessing OSM data and recompiling. Steps 3–4 are the core schema/API work. Steps 5–6 are the user-facing UI.

---

## What This Enables in the Future

**More brand categories.** If "Pharmacy", "Fitness", "Telecom" etc. become useful, add them to the category list (one line in `theme.ts`, one in the backend constant). Users can immediately start assigning brands to the new category from Settings.

**Industrial / MF tenant tracking.** The same `brand` → `category` pattern works for non-retail tenants. If industrial POIs are ever imported (warehouses, logistics centers), they'd go through the same pipeline, get their own categories (e.g., "Logistics", "Manufacturing"), and appear in the brand registry. The favorites system works identically.

**Cross-user brand intelligence.** Since `brand_overrides` is global (not per-user), one user's category assignment benefits everyone. Over time the community of users builds out the category taxonomy for long-tail brands.

**Brand-based analytics.** With all ~50K POIs in the database and proper categorization, you can answer questions like "which groups own the most QSR-tenanted properties" or "show me all properties within 500m of a Starbucks" — without the answer being limited to a pre-selected 136 brands.
