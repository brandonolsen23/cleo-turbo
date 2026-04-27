# Explorer — 4/5/6+ N-grams + Containment Navigation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Builds on:** `2026-04-24-explorer-layer-1-silos.md` (shipped — Brands 1/2/3-gram, Phones, Addresses, Contacts).

**Goal:** Complete the Brand-silo n-gram coverage so no operator identifier is missed, and stitch the n-gram levels together with containment navigation so the user can walk the hierarchy from any token to any phrase that contains it (and back).

**Why:**
- 1-gram catches concise distinctive tokens (kingsett, metrus, fieldgate)
- 2-gram catches phrases where neither token is alone-distinctive (regional group, real estate)
- 3-gram surfaces sub-identifiers and parsing artifacts (kingsett capital gp, creo mail code 01)
- 4-gram is needed for **institutional entities** (toronto catholic school board, ontario superior court justice)
- 5-gram captures the long-form government / sovereign names where the operator's identity only emerges at 5 tokens (her majesty queen right ontario)
- 6+ catches the **long tail** — anything 6 tokens or longer in one bucket so nothing escapes the index

**Out of scope:** Layer 2 canonical-identifier inference (which n-gram represents the canonical operator name for a given group), variant matching, fuzzy/phonetic. Those are separate later plans.

---

## 1. The 6+ silo — design

Three options were considered:

1. **Sliding 6-gram, 7-gram, 8-gram, … as separate silos.** Storage explodes; most long brand_phrases don't have meaningful internal sub-phrase variation. **Rejected.**
2. **Sliding 6-gram only, then everything ≥7 lumped.** Asymmetric. **Rejected.**
3. **Single "6+ long-form" silo: each row is the full normalized brand_phrase whenever it has ≥ 6 tokens after stopword stripping.** Each long-form phrase is one row, with an `n_tokens` column showing the actual length. **Chosen.**

This means: a 12-token phrase like *"her majesty the queen in right of the province of ontario represented by the minister of natural resources"* tokenizes (after dropping stopwords) to ~10 tokens and lands as one row in the long-form silo. Any 5-token sub-window of it lands in the 5-gram silo. Any 4-token sub-window in the 4-gram silo. Etc. The user can find this entity from any of those levels.

## 2. Containment navigation — design

Each n-gram detail page (and the long-form detail page) gains two sections:

- **Contains:** the immediate `(n-1)`-gram level constituents.
  - For a 3-gram `kingsett capital gp`, this lists 2-grams `kingsett capital` and `capital gp`.
  - For a 5-gram, lists 4-grams. For long-form, lists the 5-grams it contains.
- **Extended by:** the immediate `(n+1)`-level entries that contain this one.
  - For a 1-gram `kingsett`, lists 2-grams that contain it (`kingsett capital`, `kingsett mortgage`, `ks gp`, etc.).
  - For a 5-gram, lists long-form phrases that contain it.
  - For long-form, this section doesn't render (no longer level exists).

Containment data comes back **in the existing detail-endpoint response** (single round-trip per page load).

## 3. URL + tab additions

Existing tabs: `1-gram | 2-gram | 3-gram`. New tabs after them:

```
1-gram | 2-gram | 3-gram | 4-gram | 5-gram | 6+
```

URL structure:

```
/explorer/brands/4gram                → 4-gram list
/explorer/brands/4gram/:fourgram      → 4-gram detail
/explorer/brands/5gram                → 5-gram list
/explorer/brands/5gram/:fivegram      → 5-gram detail
/explorer/brands/long-form            → 6+ long-form list
/explorer/brands/long-form/:phrase    → 6+ long-form detail
```

API:

```
GET /api/explorer/brands/4grams
GET /api/explorer/brands/4grams/:fourgram
GET /api/explorer/brands/5grams
GET /api/explorer/brands/5grams/:fivegram
GET /api/explorer/brands/long-phrases
GET /api/explorer/brands/long-phrases/:phrase
```

---

## File Structure

**Created:**
- `cleo/database/migrations/012_brand_4gram_5gram_longform.py`
- `frontend/src/pages/ExplorerBrands4gram.tsx`
- `frontend/src/pages/ExplorerBrand4gramDetail.tsx`
- `frontend/src/pages/ExplorerBrands5gram.tsx`
- `frontend/src/pages/ExplorerBrand5gramDetail.tsx`
- `frontend/src/pages/ExplorerBrandsLongForm.tsx`
- `frontend/src/pages/ExplorerBrandLongFormDetail.tsx`
- `frontend/src/components/explorer/NgramContainment.tsx`

**Modified:**
- `cleo/discovery_v2/brand_index.py` — call `build_brand_ngram_index` for n=4, 5; add `build_long_phrase_index`
- `cleo/web/routes/explorer.py` — 6 new endpoints + add `contains` / `extended_by` to all n-gram detail responses
- `cleo/discovery_v2/__main__.py` — `build_all_indexes` already calls `build_brand_ngram_index` for n=2, 3 — add 4, 5, and long-form
- `frontend/src/types/index.ts` — types for 4gram, 5gram, long-form, containment
- `frontend/src/components/explorer/ExplorerTabs.tsx` — add 4-gram / 5-gram / 6+ sub-tabs
- `frontend/src/App.tsx` — lazy imports + routes for 6 new pages
- `frontend/src/pages/ExplorerBrandUnigramDetail.tsx` — render `<NgramContainment>` (extended_by only)
- `frontend/src/pages/ExplorerBrandBigramDetail.tsx` — render containment (both directions)
- `frontend/src/pages/ExplorerBrandTrigramDetail.tsx` — render containment (both directions)

---

## Task 1 — Schema migration 012

**Files:**
- Create: `cleo/database/migrations/012_brand_4gram_5gram_longform.py`

Mirror migration 011's pattern. Three new pairs of tables:
- `brand_fourgram_index` + `brand_fourgram_summary` (with `token_a`, `token_b`, `token_c`, `token_d`)
- `brand_fivegram_index` + `brand_fivegram_summary` (with `token_a`–`token_e`)
- `brand_long_phrase_index` + `brand_long_phrase_summary` (with `n_tokens INTEGER` instead of fixed token columns)

Schema for the long-form summary:

```sql
CREATE TABLE IF NOT EXISTS brand_long_phrase_summary (
    phrase                 TEXT PRIMARY KEY,    -- joined stripped tokens
    n_tokens               INTEGER NOT NULL,    -- 6, 7, 8, …
    idf                    REAL NOT NULL,
    n_party_sides          INTEGER NOT NULL,
    n_distinct_source_phrases INTEGER NOT NULL, -- usually 1; >1 if multiple raw phrases tokenize to the same form
    any_token_distinctive  INTEGER NOT NULL,
    any_token_excluded     INTEGER NOT NULL,
    all_english            INTEGER NOT NULL,
    all_place              INTEGER NOT NULL,
    all_industry           INTEGER NOT NULL,
    is_distinctive         INTEGER NOT NULL,
    discovered_at          TEXT DEFAULT (datetime('now'))
);
```

All others mirror `brand_bigram_summary` / `brand_trigram_summary`. Idempotent (CREATE TABLE IF NOT EXISTS).

Verify with `sqlite3 data/cleo.db "SELECT name FROM sqlite_master WHERE name LIKE 'brand_four%' OR name LIKE 'brand_five%' OR name LIKE 'brand_long%';"`. Six tables expected.

## Task 2 — Builders

**Files:**
- Modify: `cleo/discovery_v2/brand_index.py`

The existing `build_brand_ngram_index(conn, n)` already handles arbitrary n (the helper is parameterized on n=2/3). Extend it to n=4 and n=5 — should be one parameter change in the assertion at the top of the function:

```python
assert n in (2, 3, 4, 5), f"only n=2..5 supported, got {n}"
```

Also generalize the dispatch on table name:
```python
table_word = {2: "bigram", 3: "trigram", 4: "fourgram", 5: "fivegram"}[n]
```

And the `summary_rows.append(...)` block needs to fan out tokens for n=4 (4 token columns) and n=5 (5 token columns) instead of the special-case `if n == 2 ... else` currently there.

Add new function `build_long_phrase_index(conn, *, min_idf=None, verbose=True)`. Same shape as `build_brand_ngram_index` but:
- Iterate brand_phrases, tokenize, **only emit when `len(tokens) >= 6`**
- The "ngram" key is the full token-joined phrase (no sliding window)
- `n_tokens` column stored
- Token-flag rollups computed across ALL tokens in the phrase (any_token_distinctive = at least one is distinctive, all_english = every token is is_english_common, etc.)

Update `build_all_indexes` to call all of:
```python
build_brand_ngram_index(conn, 2, ...)
build_brand_ngram_index(conn, 3, ...)
build_brand_ngram_index(conn, 4, ...)
build_brand_ngram_index(conn, 5, ...)
build_long_phrase_index(conn, ...)
```

Add tests in `tests/test_discovery_v2_layer1_silos.py`:
- `test_build_brand_ngram_index_n4_emits_consecutive_quadruples`
- `test_build_brand_ngram_index_n5_emits_consecutive_quintuples`
- `test_build_long_phrase_index_captures_phrases_with_6_or_more_tokens`
- `test_build_long_phrase_index_skips_phrases_with_fewer_than_6_tokens`

Run `python3 -m pytest tests/test_discovery_v2_layer1_silos.py -v` — all should pass.

Run `python3 -m cleo.discovery_v2` against the real DB. Capture counts:

```bash
sqlite3 -header -column data/cleo.db "
SELECT 'brand_fourgram' AS silo, COUNT(*) FROM brand_fourgram_summary
UNION ALL SELECT 'brand_fivegram', COUNT(*) FROM brand_fivegram_summary
UNION ALL SELECT 'brand_long_phrase', COUNT(*) FROM brand_long_phrase_summary;
"
```

Expected ranges (best-guess):
- 4-gram: 25K–40K distinct
- 5-gram: 8K–15K distinct
- long-form: 5K–15K distinct

## Task 3 — API endpoints (lists, details, containment)

**Files:**
- Modify: `cleo/web/routes/explorer.py`
- Modify: `tests/test_routes_explorer.py`

### 3a. New list + detail endpoints (mirror existing 2/3-gram pattern)

```
GET /brands/4grams           → paginated list
GET /brands/4grams/:fourgram → detail
GET /brands/5grams           → paginated list
GET /brands/5grams/:fivegram → detail
GET /brands/long-phrases     → paginated list
GET /brands/long-phrases/:phrase → detail
```

The `_list_brand_ngrams` helper is already factored — generalize it to accept `n=4` and `n=5` (more token columns in the SELECT). For long-phrases, write a parallel `_list_long_phrases` since the column shape differs (`phrase`, `n_tokens` instead of `token_a`/`token_b`/...).

Detail endpoints reuse `_hydrate_party_sides(db, ps_keys, highlight_token=...)`.

### 3b. Add containment fields to ALL n-gram detail responses

Every n-gram detail response gains two new arrays:
- `contains`: the immediate `(n-1)`-level constituents
- `extended_by`: a sample of the immediate `(n+1)`-level entries that contain this one (limit ~50 to avoid exploding the response)

Example for `GET /brands/bigrams/kingsett%20capital`:

```json
{
  ...existing fields...,
  "contains": [
    {"value": "kingsett", "level": "1gram", "n_party_sides": 367},
    {"value": "capital", "level": "1gram", "n_party_sides": 2915}
  ],
  "extended_by": [
    {"value": "kingsett capital gp", "level": "3gram", "n_party_sides": 50},
    {"value": "kingsett capital inc", "level": "3gram", "n_party_sides": 80},
    ...
  ]
}
```

Containment lookups are SQL-driven:

- **1-gram contains:** none.
- **1-gram extended_by:** `SELECT bigram, n_party_sides FROM brand_bigram_summary WHERE token_a = ? OR token_b = ? ORDER BY n_party_sides DESC LIMIT 50`. Decorate with `level: "2gram"`.
- **2-gram contains:** the two `token_a`, `token_b` columns from the row, joined to brand_token_summary for n_party_sides.
- **2-gram extended_by:** `SELECT trigram, n_party_sides FROM brand_trigram_summary WHERE (token_a = a AND token_b = b) OR (token_b = a AND token_c = b) ORDER BY n_party_sides DESC LIMIT 50`.
- Same pattern up through 5-gram → long-phrase.
- **5-gram extended_by:** check long_phrase via word-boundary substring: `SELECT phrase, n_party_sides, n_tokens FROM brand_long_phrase_summary WHERE (' ' || phrase || ' ') LIKE '% ' || ? || ' %' LIMIT 50`.
- **long-phrase contains:** for each consecutive 5-token window, look up the corresponding 5-gram. (Compute windows in Python; query each with a single SELECT.) Long-form to 5-gram is the only "contains" level we surface for long-form.
- **long-phrase extended_by:** none.

### 3c. Tests

Add to `tests/test_routes_explorer.py`:
- `test_list_4grams`
- `test_4gram_detail_includes_containment`
- Same for 5-gram, long-form
- `test_2gram_detail_now_includes_containment` (extends existing test)

Run `python3 -m pytest tests/test_routes_explorer.py -v`.

## Task 4 — Frontend tabs + 4-gram + 5-gram + long-form pages

**Files:**
- Modify: `frontend/src/components/explorer/ExplorerTabs.tsx` — add 3 sub-tabs
- Modify: `frontend/src/types/index.ts` — types for `BrandFourgramSummary`, `BrandFivegramSummary`, `BrandLongPhraseSummary`, plus their list / detail variants and a `NgramContainmentEntry` interface
- Create: `ExplorerBrands4gram.tsx`, `ExplorerBrand4gramDetail.tsx`
- Create: `ExplorerBrands5gram.tsx`, `ExplorerBrand5gramDetail.tsx`
- Create: `ExplorerBrandsLongForm.tsx`, `ExplorerBrandLongFormDetail.tsx`
- Modify: `frontend/src/App.tsx` — 6 lazy imports + 6 routes

ExplorerTabs gets three new sub-tab entries (after `3-gram`):

```tsx
{ label: "4-gram",       href: "/explorer/brands/4gram",     matches: (p) => p.startsWith("/explorer/brands/4gram") },
{ label: "5-gram",       href: "/explorer/brands/5gram",     matches: (p) => p.startsWith("/explorer/brands/5gram") },
{ label: "6+ long-form", href: "/explorer/brands/long-form", matches: (p) => p.startsWith("/explorer/brands/long-form") },
```

The list pages mirror `ExplorerBrandsBigram.tsx`. The 4-gram and 5-gram pages have a column-count difference (4 token cells / 5 token cells) but the visible columns shown to the user are the same: `phrase | IDF | n_party_sides | n_phrases | flag-rollup columns`. Token columns aren't shown in the list — only on detail.

The long-form list adds an `n_tokens` column right after the phrase column, since phrase length varies per row.

Detail pages mirror `ExplorerBrandBigramDetail.tsx`. Long-form detail page shows the variable token count in a "tokens" sub-row beneath the heading: `tokens (N): t1 + t2 + … + tN`.

All detail pages render `<PartySideCard>` with `highlightToken={data.<the-ngram-string>}` so the matching n-gram gets jade-highlighted in each phrase the user sees.

## Task 5 — Containment component on ALL n-gram detail pages

**Files:**
- Create: `frontend/src/components/explorer/NgramContainment.tsx`
- Modify: `ExplorerBrandUnigramDetail.tsx` — render `<NgramContainment>` (extended_by only)
- Modify: `ExplorerBrandBigramDetail.tsx` — render full
- Modify: `ExplorerBrandTrigramDetail.tsx` — render full
- Modify: `ExplorerBrand4gramDetail.tsx`, `ExplorerBrand5gramDetail.tsx`, `ExplorerBrandLongFormDetail.tsx` — render full (or contains-only for long-form)

The `NgramContainment` component takes:

```typescript
interface NgramContainmentProps {
  contains: NgramContainmentEntry[];   // empty array means hide section
  extended_by: NgramContainmentEntry[]; // empty array means hide section
}

interface NgramContainmentEntry {
  value: string;       // the n-gram or long-form phrase
  level: "1gram" | "2gram" | "3gram" | "4gram" | "5gram" | "long-form";
  n_party_sides: number;
}
```

Each entry renders as a clickable link to the detail page for that level + value. The component picks the right route based on `level`:

```ts
function detailHref(entry: NgramContainmentEntry): string {
  const path = entry.level === "long-form" ? "long-form" : entry.level;
  return `/explorer/brands/${path}/${encodeURIComponent(entry.value)}`;
}
```

Layout (one card per direction):

```
Contains                                           Extended by
┌───────────────────────────────────────┐  ┌───────────────────────────────────────┐
│ kingsett (1gram, 367 sides)           │  │ kingsett capital gp (3gram, 50 sides) │
│ capital (1gram, 2915 sides)           │  │ kingsett capital inc (3gram, 80 sides)│
└───────────────────────────────────────┘  └───────────────────────────────────────┘
```

Place between the existing "Constituent token signals" section and "Brand phrases containing this token" section.

## Task 6 — Rebuild + smoke check

- Run `python3 -m cleo.discovery_v2` to populate the new tables.
- Open `/explorer/brands/4gram` — confirm list loads with reasonable top entries (likely school boards, court phrases, government departments, longer brand variants).
- Click a 4-gram → detail loads with stat cards + signals + containment (3-grams contained, 5-grams extending) + party-side cards.
- `/explorer/brands/5gram` — same drill.
- `/explorer/brands/long-form` — confirm n_tokens column shows variable lengths (6, 7, 8, 9, 10+).
- Click a long-form → detail loads with the multi-token list, containment to 5-grams, party-side cards.
- Navigate from a 1-gram → 2-gram via `Extended by` → 3-gram → 4-gram → 5-gram → long-form. Confirm the chain works in both directions.

Capture in the report: filter-bucket counts for the new silos and a top-10-distinctive sample for each.

---

## Self-Review Checklist

- [x] 4-gram + 5-gram silos match the existing 2/3-gram pattern (same schema shape, same builder logic)
- [x] 6+ "long-form" silo captures full phrase per row, with `n_tokens` for visibility
- [x] Containment surfaces on every n-gram detail page bidirectionally (except endpoints — 1-gram has no `contains`, long-form has no `extended_by`)
- [x] No new dependencies
- [x] Existing pages (1/2/3-gram detail) are extended with containment but otherwise unchanged
- [x] Distinctiveness for 4/5-gram + long-form is gated on the n-gram's own corpus IDF (consistent with bi/trigram)

---

## Execution Handoff

5 tasks (schema, builders, API, frontend pages, containment + smoke).

**Subagent-Driven** is recommended (default).
