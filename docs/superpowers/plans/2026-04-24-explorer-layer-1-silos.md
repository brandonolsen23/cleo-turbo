# Explorer — Layer 1 Multi-Silo Extension

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Builds on:**
- `2026-04-23-discovery-layer-1-brand-silo.md` — shipped: 1-gram brand tokens
- `2026-04-24-explorer-external-signals.md` — shipped: wordfreq/places/industry signals + curation UI

**Goal:** Extend the Explorer from a single-silo brand-token view into a unified Layer 1 data-collection hub with four parallel raw-data silos — **Brands** (1/2/3-grams), **Phones**, **Addresses**, **Contacts**. Every silo produces the same shape of data: an inverted index from a raw-data value to the party-sides carrying it, plus a summary with corpus-level stats. No clustering, no entity merging, no inference. Pure base-level observation sets the user can browse to understand what's in the data.

**Out of scope:** cross-silo triangulation, entity identification, variant clustering, same-operator detection, anything that draws conclusions from multiple silos together. That's all Layer 2 territory, starts only once the user has browsed every silo and feels confident about the raw data.

**Tech stack:** existing Python 3.12 / FastAPI / SQLite / React 19 + Radix Themes. No new dependencies.

---

## 1. What "Layer 1 silo" means

A silo is a single-dimensional index over the party-side corpus. Each silo answers one question:

- **Brands:** which brand-tokens / bigrams / trigrams appear on which party-sides?
- **Phones:** which phones appear on which party-sides?
- **Addresses:** which base addresses (street# + street_name + suffix) appear on which party-sides, and what suite/postal variants exist per base?
- **Contacts:** which first+last contact fingerprints appear on which party-sides?

**Silo rules:**
- Each silo produces a **summary table** (one row per distinct value, with corpus-level counts).
- Each silo produces an **index table** (one row per (value, party-side) pair) for fast lookup.
  - Exception: singleton-valued atoms (phone, contact_fingerprint, address) already live in `party_fingerprints`; we don't duplicate them.
- Each silo exposes a **list endpoint** and a **detail endpoint**.
- Each silo gets a **tab** in the Explorer UI.
- Every silo's detail page uses the **same layout pattern** (see §3).

The unigram brand silo shipped this pattern already. This plan extends it to 3 more silos plus bigrams/trigrams inside the brands silo.

---

## 2. Explorer UI reorganization

### 2.1 Sidebar

Rename the existing sidebar entry:
- **Before:** `Explorer — Brands` (single silo)
- **After:** `Explorer` (multi-silo hub)

Icon and placement stay (Pipeline group, between Discovery and Labeling).

### 2.2 URL structure

```
/explorer                    → redirect to /explorer/brands/1gram (default landing)
/explorer/brands/1gram       → 1-gram list (current /explorer/brands)
/explorer/brands/2gram       → 2-gram list (new)
/explorer/brands/3gram       → 3-gram list (new)
/explorer/brands/1gram/:token    → unigram detail (current /explorer/brands/:token)
/explorer/brands/2gram/:bigram   → bigram detail (path-encoded)
/explorer/brands/3gram/:trigram  → trigram detail
/explorer/phones             → phones list
/explorer/phones/:phone      → phone detail
/explorer/addresses          → address-base list
/explorer/addresses/:key     → address-base detail (key = "number|name|suffix")
/explorer/contacts           → contacts list
/explorer/contacts/:fp       → contact-fingerprint detail
```

### 2.3 Explorer tab bar

A persistent tab row at the top of every Explorer page:

```
[ Brands ]  [ Phones ]  [ Addresses ]  [ Contacts ]
  ↓
  1-gram | 2-gram | 3-gram
```

Brands has sub-tabs for the three n-gram levels. Other silos are single-view for now (contacts will get variant views in a future plan).

### 2.4 Shared list-page layout

Across every list page (brands-1gram, brands-2gram, phones, addresses, contacts):
- Top tab row + silo-specific sub-tabs
- Search input
- "Distinctive only" toggle (brands only — other silos have all values visible)
- Per-signal filter checkboxes (brands only, for now)
- Table: value, IDF (if applicable), n_party_sides, n_distinct_phrases (brands only), silo-specific columns, action column
- Pagination

### 2.5 Shared detail-page layout

**This is the pattern the user called out as a keeper.** Every silo's detail page follows it:

```
← Explorer

[value]  [distinctive badge]  [Mark as X]  [Mark as Y]   ← header: value + action buttons

┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│  stat 1  │ │  stat 2  │ │  stat 3  │ │  stat 4  │ │  stat 5  │
└──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘

Signals           (badges: common/place/industry/excluded or "no filter")

Related values containing this    (phrase badges for brands; variant list for addresses; empty for phones/contacts)

Party-sides (N)
┌───────────────────────────────────────────────────────────────┐
│ RT12345 · buyer · 2020-01-01     30 floral pkwy · L4K4R1 · … │
│ [party_name]  1233543 ontario                                │
│ [trade_name]  metrus developments   ← contains "metrus"      │
│ [care_of]     kingsett capital                               │
└───────────────────────────────────────────────────────────────┘
┌───────────────────────────────────────────────────────────────┐
│ RT12346 · buyer · 2021-03-15     30 floral pkwy · …          │
│ ...                                                           │
└───────────────────────────────────────────────────────────────┘
```

**Per-party-side card content varies by silo:**

| Silo | "Highlighted" content | Card body content |
|---|---|---|
| Brands (any gram) | phrase containing the token/bigram/trigram | all brand_phrases on that party-side, with source_field labels |
| Phones | phone number (implicit) | address + contact + brand_phrases on that side |
| Addresses | address base (highlighted) + suite variants shown per-side | phone + contact + brand_phrases on that side |
| Contacts | contact fingerprint (implicit) | address + phone + brand_phrases on that side |

The core idea: **the user, when looking at any value, sees all the other raw-data signals on each party-side where that value appears.** Detecting co-occurrences is the user's job across silos — the UI just surfaces them clearly.

---

## 3. Per-silo specifications

### 3.1 Brands — 2-gram + 3-gram

Schema (migration 011):

```sql
CREATE TABLE brand_bigram_index (
    bigram TEXT NOT NULL,                 -- "kingsett capital"
    source_id TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('buyer','seller')),
    PRIMARY KEY (bigram, source_id, side)
);
CREATE INDEX idx_bbi_side ON brand_bigram_index(source_id, side);

CREATE TABLE brand_bigram_summary (
    bigram              TEXT PRIMARY KEY, -- "kingsett capital"
    token_a             TEXT NOT NULL,    -- "kingsett"
    token_b             TEXT NOT NULL,    -- "capital"
    idf                 REAL NOT NULL,    -- log(N / (1 + df))
    n_party_sides       INTEGER NOT NULL,
    n_distinct_phrases  INTEGER NOT NULL, -- distinct brand_phrases containing this bigram
    any_token_distinctive INTEGER NOT NULL,   -- at least one constituent token.is_distinctive=1
    any_token_excluded    INTEGER NOT NULL,   -- any constituent is in excluded_brand_tokens
    all_english           INTEGER NOT NULL,
    all_place             INTEGER NOT NULL,
    all_industry          INTEGER NOT NULL,
    is_distinctive      INTEGER NOT NULL,     -- idf >= min_idf AND NOT any_token_excluded
    discovered_at       TEXT DEFAULT (datetime('now'))
);
CREATE INDEX idx_bbs_n ON brand_bigram_summary(n_party_sides);
CREATE INDEX idx_bbs_idf ON brand_bigram_summary(idf);

-- Same schema shape for brand_trigram_index / brand_trigram_summary, plus token_c column.
```

**Builder logic (in `brand_index.py`):**

For each distinct `brand_phrase` in `party_atoms`, re-tokenize with `tokenize_brand`, then emit:
- Bigrams: every consecutive pair of tokens (`tokens[i], tokens[i+1]`) as `" ".join(...)`
- Trigrams: every consecutive triple of tokens

The emission is joined on the party-side that carries the phrase. If a party-side has phrase "kingsett capital holdings" it emits bigrams `kingsett capital` and `capital holdings`, plus trigram `kingsett capital holdings`. Each bigram/trigram on each party-side emits exactly one row to the index table (PK ensures no dupes).

Summary rows computed after index is populated:
- `idf = log(N / (1 + df))` where N=total party-sides, df=distinct party-sides in this bigram/trigram's index rows
- Constituent flag rollups: look up each `token_a`, `token_b` (and `_c`) in `brand_token_summary` to get their `is_distinctive`, `is_excluded`, `is_english_common`, `is_place_name`, `is_industry_stopword`. Compute `all_english = token_a.is_english_common AND token_b.is_english_common`, etc.
- `is_distinctive = (idf >= min_idf) AND NOT any_token_excluded`. Purely IDF-gated (catches "regional group" cases).

**Distinctiveness rule** (confirmed with user):
- An n-gram's distinctiveness is driven by its own corpus IDF, NOT by whether its constituent tokens are distinctive.
- `regional group` (both common tokens) can still be distinctive if the bigram is rare in the corpus.
- `kingsett capital` is distinctive via high bigram IDF AND high constituent IDF.
- `real estate` (if it's on thousands of party-sides) fails the IDF gate and is non-distinctive.

**API endpoints:**

```
GET /api/explorer/brands/bigrams?q=&distinctive_only=&page=&per_page=
GET /api/explorer/brands/bigrams/:bigram
GET /api/explorer/brands/trigrams?q=&distinctive_only=&page=&per_page=
GET /api/explorer/brands/trigrams/:trigram
```

Response shapes mirror the existing unigram endpoints. Detail response includes:
- Summary row (idf, n_party_sides, flags)
- `phrases` = distinct brand_phrases in `party_atoms` that contain the bigram/trigram as consecutive tokens (word-boundary match)
- `party_sides` = same per-side grouped structure as unigram, with the phrase(s) containing the bigram/trigram highlighted

### 3.2 Phones

Phones are already normalized and stored in `party_fingerprints.phone`. No index table needed (one phone per party-side).

Schema (migration 011, continued):

```sql
CREATE TABLE phone_summary (
    phone               TEXT PRIMARY KEY,
    n_party_sides       INTEGER NOT NULL,
    is_distinctive      INTEGER NOT NULL,  -- always 1 for Phase 1; kept for consistency
    discovered_at       TEXT DEFAULT (datetime('now'))
);
CREATE INDEX idx_ps_n ON phone_summary(n_party_sides);
```

**Builder:**
```sql
INSERT INTO phone_summary (phone, n_party_sides, is_distinctive)
SELECT phone, COUNT(*), 1
FROM party_fingerprints
WHERE phone IS NOT NULL AND phone != ''
GROUP BY phone;
```

Rebuilt on every `python -m cleo.discovery_v2`.

**API:**
```
GET /api/explorer/phones?q=&page=&per_page=
GET /api/explorer/phones/:phone
```

Detail response:
- Summary row
- `party_sides` — party-sides with this phone, each with their brand_phrases, address, contact_fingerprint (same per-side card structure)

No "Related values containing this" section for phones (phones don't have variants).

### 3.3 Addresses

Address key is the base triple `(street_number, street_name, street_suffix)`. Variations per base include different suite numbers, suite types, street directions, postal codes.

Schema (migration 011, continued):

```sql
CREATE TABLE address_base_summary (
    street_number       TEXT NOT NULL,
    street_name         TEXT NOT NULL,
    street_suffix       TEXT NOT NULL,
    n_party_sides       INTEGER NOT NULL,
    n_distinct_suites   INTEGER NOT NULL,     -- distinct (suite_type, suite_number) pairs at this base
    n_distinct_postals  INTEGER NOT NULL,     -- distinct postal codes at this base
    is_distinctive      INTEGER NOT NULL,     -- always 1 for Phase 1
    discovered_at       TEXT DEFAULT (datetime('now'))
);
CREATE INDEX idx_abs_key ON address_base_summary(street_number, street_name, street_suffix);
CREATE INDEX idx_abs_n ON address_base_summary(n_party_sides);
```

Primary key is the composite of the 3 columns. Key-in-URL encoding: `"{street_number}|{street_name}|{street_suffix}"` URL-encoded.

**Builder:**
```sql
INSERT INTO address_base_summary (...)
SELECT street_number, street_name, street_suffix,
       COUNT(*) AS n_party_sides,
       COUNT(DISTINCT COALESCE(suite_type,'') || '|' || COALESCE(suite_number,'')) AS n_distinct_suites,
       COUNT(DISTINCT COALESCE(postal,'')) AS n_distinct_postals,
       1 AS is_distinctive
FROM party_fingerprints
WHERE street_number IS NOT NULL AND street_number != ''
  AND street_name IS NOT NULL AND street_name != ''
  AND street_suffix IS NOT NULL AND street_suffix != ''
GROUP BY street_number, street_name, street_suffix;
```

**API:**
```
GET /api/explorer/addresses?q=&page=&per_page=
GET /api/explorer/addresses/:key       # key = "66|wellington|street"
```

Detail response:
- Summary row
- `suite_variants`: list of `{suite_type, suite_number, postal, n_party_sides}` — the variations at this base
- `party_sides`: every party-side at this base, with their suite/postal shown prominently, plus phone + contact + brand_phrases

**Detail header for addresses** shows the formatted address ("66 Wellington Street") and below it a list of suite variants with counts — e.g., "Suite 4400 (38), Suite 4500 (12), No suite (8)". Lets the user see at a glance what variations exist for this base.

### 3.4 Contacts

Contact fingerprint (`first last`, lowercase) is already in `party_fingerprints.contact_fingerprint`. No index table needed.

Schema (migration 011, continued):

```sql
CREATE TABLE contact_fingerprint_summary (
    contact_fingerprint TEXT PRIMARY KEY,
    n_party_sides       INTEGER NOT NULL,
    is_distinctive      INTEGER NOT NULL,  -- always 1 for Phase 1
    discovered_at       TEXT DEFAULT (datetime('now'))
);
CREATE INDEX idx_cfs_n ON contact_fingerprint_summary(n_party_sides);
```

**Builder:**
```sql
INSERT INTO contact_fingerprint_summary (...)
SELECT contact_fingerprint, COUNT(*), 1
FROM party_fingerprints
WHERE contact_fingerprint IS NOT NULL AND contact_fingerprint != ''
GROUP BY contact_fingerprint;
```

**API:**
```
GET /api/explorer/contacts?q=&page=&per_page=
GET /api/explorer/contacts/:fingerprint
```

Detail response:
- Summary row
- `party_sides` — party-sides with this contact, each with address + phone + brand_phrases

**Phase 2 (not in this plan):** fuzzy / phonetic / nickname variants. Detail page would show "likely variants" for the user to vet. Deferred.

---

## 4. Implementation tasks

### Task 1 — Schema migration 011

**Files:**
- Create: `cleo/database/migrations/011_layer1_silo_tables.py`

Create all five new summary tables and both bigram/trigram index tables. Idempotent (CREATE TABLE IF NOT EXISTS).

Run migration, verify tables exist.

### Task 2 — Backend: builders for all silos

**Files:**
- Modify: `cleo/discovery_v2/brand_index.py` — factor into `build_all_indexes(conn)` that calls:
  - `build_brand_token_index(conn)` (existing; rename)
  - `build_brand_ngram_index(conn, n=2)` (new)
  - `build_brand_ngram_index(conn, n=3)` (new)
  - `build_phone_summary(conn)` (new)
  - `build_address_base_summary(conn)` (new)
  - `build_contact_fingerprint_summary(conn)` (new)
- Modify: `cleo/discovery_v2/__main__.py` — call `build_all_indexes`
- Create: `tests/test_discovery_v2_layer1_silos.py` — integration tests for each silo

### Task 3 — Backend: new API endpoints

**Files:**
- Modify: `cleo/web/routes/explorer.py`
- Modify: `tests/test_routes_explorer.py`

Add endpoints:
- `GET /api/explorer/brands/bigrams`, `GET /api/explorer/brands/bigrams/:bigram`
- `GET /api/explorer/brands/trigrams`, `GET /api/explorer/brands/trigrams/:trigram`
- `GET /api/explorer/phones`, `GET /api/explorer/phones/:phone`
- `GET /api/explorer/addresses`, `GET /api/explorer/addresses/:key`
- `GET /api/explorer/contacts`, `GET /api/explorer/contacts/:fingerprint`

Detail endpoints for phones/addresses/contacts include `party_sides` array with per-side brand_phrases joined in (same shape as the current brand-token detail).

Existing `/api/explorer/brands` endpoint stays as the alias for `/api/explorer/brands/1gram` to avoid breaking the current UI.

### Task 4 — Frontend shell: tabs + sidebar rename

**Files:**
- Modify: `frontend/src/components/layout/Sidebar.tsx` — rename `Explorer — Brands` to `Explorer`
- Modify: `frontend/src/App.tsx` — new routes + redirect from `/explorer` to `/explorer/brands/1gram`
- Create: `frontend/src/components/explorer/ExplorerTabs.tsx` — tab bar component (Brands / Phones / Addresses / Contacts) with nested sub-tabs for Brands
- Move: rename `ExplorerBrands.tsx` → `ExplorerBrandsUnigram.tsx` and `ExplorerBrandDetail.tsx` → `ExplorerBrandUnigramDetail.tsx`. Wire up to new route structure. Keep code identical otherwise.

### Task 5 — Frontend: shared per-party-side card component

**Files:**
- Create: `frontend/src/components/explorer/PartySideCard.tsx`

Extract the per-party-side card layout from `ExplorerBrandDetail.tsx` into a reusable component:

```typescript
interface PartySideCardProps {
  partySide: ExplorerPartySide;
  highlightFn: (brandPhrase: string) => boolean;  // caller decides what's highlighted
  contextFields: ("address" | "phone" | "contact" | "brand_phrases")[];
  // or just always show all fields; highlightFn controls the visual emphasis
}
```

Used on all silo detail pages. For a brand-token detail, `highlightFn` checks if the phrase contains the token. For a phone detail, `highlightFn` returns false (phone is highlighted via its own header, not via a phrase). Etc.

### Task 6 — Frontend: 2-gram + 3-gram tabs and detail pages

**Files:**
- Create: `frontend/src/pages/ExplorerBrandsBigram.tsx`
- Create: `frontend/src/pages/ExplorerBrandBigramDetail.tsx`
- Create: `frontend/src/pages/ExplorerBrandsTrigram.tsx`
- Create: `frontend/src/pages/ExplorerBrandTrigramDetail.tsx`
- Modify: `frontend/src/types/index.ts` — add `BrandNgramSummary`, `BrandNgramDetail` interfaces

List pages use the same shape as the unigram page, minus some unigram-specific flags (wordfreq Zipf, mark as place/industry). Keep `is_distinctive` filter and search.

### Task 7 — Frontend: Phones tab

**Files:**
- Create: `frontend/src/pages/ExplorerPhones.tsx`
- Create: `frontend/src/pages/ExplorerPhoneDetail.tsx`
- Modify: `frontend/src/types/index.ts` — add `PhoneSummary`, `PhoneDetail`

List: table of phones sorted by n_party_sides desc, search box. Detail: stat card, party-side cards showing address + contact + brand_phrases.

### Task 8 — Frontend: Addresses tab

**Files:**
- Create: `frontend/src/pages/ExplorerAddresses.tsx`
- Create: `frontend/src/pages/ExplorerAddressDetail.tsx`
- Modify: `frontend/src/types/index.ts` — add `AddressBaseSummary`, `AddressBaseDetail`

List: address bases with n_party_sides, n_distinct_suites, n_distinct_postals. Detail: header shows "66 Wellington Street" prominently, suite variants listed below, then per-party-side cards with suite/postal highlighted.

### Task 9 — Frontend: Contacts tab

**Files:**
- Create: `frontend/src/pages/ExplorerContacts.tsx`
- Create: `frontend/src/pages/ExplorerContactDetail.tsx`
- Modify: `frontend/src/types/index.ts` — add `ContactFingerprintSummary`, `ContactFingerprintDetail`

List: contact fingerprints with n_party_sides. Detail: party-side cards showing address + phone + brand_phrases.

### Task 10 — End-to-end rebuild + spot-check

**Files:**
- Run: `python3 -m cleo.discovery_v2` — populates all Layer 1 silos
- Verify: counts across all silos make sense
  - phone_summary: ~37K distinct phones
  - address_base_summary: ~60K+ distinct bases
  - contact_fingerprint_summary: ~82K
  - brand_bigram_summary: ~200K (estimate)
  - brand_trigram_summary: ~80K
- Browse: every silo's list page loads; every detail page renders party-side cards with cross-silo context

No code changes in Task 10 — just verification.

---

## 5. Design principles (hold throughout)

1. **Each silo is independent.** No silo references another's summary table in SQL (they only reference `party_fingerprints` / `party_atoms`). Aggregation rule holds: ALWAYS aggregate from the index joined to `party_fingerprints`, never from `party_atoms` directly (prevents double-counting from multi-phrase party-sides).

2. **Detail pages surface cross-silo context per party-side, but don't draw conclusions.** The user sees that RT123 at `66 Wellington` has phone `4166876700` and contact `rob kumer` — they draw the conclusion that those things co-occur. The UI doesn't.

3. **No clustering, no entity merging.** Not in this plan. Every silo's `is_distinctive = 1` is simply "this value is meaningful to surface." Never "this value identifies an entity."

4. **The unigram brand silo stays untouched.** All existing signals (wordfreq, places, industry, excluded) remain only on unigrams. Bigrams/trigrams roll them up for display only. Phones/addresses/contacts don't have those signals.

5. **Shared detail-page pattern everywhere.** The user loves the metrus-detail layout. Every silo uses it.

---

## Self-Review Checklist

- [x] Every silo has schema + builder + API + UI list + UI detail tasks
- [x] Shared detail-page pattern is extracted into a reusable component (Task 5) before being used (Tasks 6–9)
- [x] Unigram brand silo is untouched — just renamed
- [x] URL structure is defined explicitly
- [x] Distinctiveness rule for n-grams (IDF-gated, catches "regional group") is documented
- [x] No cross-silo queries; aggregation rule enforced
- [x] Migration is idempotent
- [x] Full build is one command (`python3 -m cleo.discovery_v2`)

---

## Execution Handoff

Two options:

**1. Subagent-Driven (recommended)** — Fresh subagent per task with two-stage review.
**2. Inline Execution** — Execute all 10 tasks in this session.

Which approach?
