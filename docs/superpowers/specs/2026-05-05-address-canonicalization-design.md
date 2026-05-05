# Address Canonicalization Design

**Date:** 2026-05-05
**Status:** Design approved, ready for implementation planning
**Related:** Surfaced while implementing the Contact Tenure Page (`2026-05-04-contact-tenure-page-design.md`). The visible "4 duplicate `2555 eglinton avenue east` rows on Dan Hagler's contact page" was the symptom; the underlying canonicalization gap affects far more than one page.

---

## Problem

Cleo treats every distinct `(city, street_number, street_name, street_suffix, street_direction, suite_type, suite_number)` 7-tuple as a different address. Source data fragments the same logical address into multiple tuples for three distinct reasons:

1. **City amalgamation.** Toronto absorbed Scarborough, North York, Etobicoke, York, and East York in 1998. Hamilton absorbed Stoney Creek, Ancaster, Dundas, Flamborough, and Glanbrook in 2001. Ottawa absorbed Nepean, Kanata, Gloucester, Cumberland, Goulbourn, Osgoode, Rideau, Rockcliffe Park, Vanier, and West Carleton in 2001. Source data preserves the historical city the deed was registered against; we treat them as different cities. So `(scarborough, 2555, eglinton, ave, east, suite, 212)` and `(toronto, 2555, eglinton, ave, east, suite, 212)` are stored as two distinct addresses despite being legally and physically the same place.

2. **Suite-type synonyms.** `"suite"`, `"unit"`, `"ste"`, `"u"`, `""`, `"#"` are interchangeable in Canadian non-residential addressing. The deed uses whatever the drafter typed. So `(toronto, 2555, eglinton, ave, east, suite, 212)` and `(toronto, 2555, eglinton, ave, east, unit, 212)` are stored as two distinct addresses despite being the same suite.

3. **Suite-number formatting.** `0212` vs `212` (leading zeros), `212a` vs `212A` (case). Same registered suite, different stored value.

The fragmentation is silently degrading multiple Layer 2 surfaces:

- **`auto_groups` dominant-stem scoring.** When canfirst's party-sides at 30 St Clair split across `suite|300`, `suite|400`, `unit|300` etc., no single tuple dominates. The stem fails its dominance threshold and the group misses a confirmed seeding even when the brand is unmistakable in the data.
- **`address_unit_summary`** has multiple rows for the same logical address. Counts are split, dominant_stem is noise.
- **`anchor_uniqueness`** (which `auto_groups` uses to seed) misses real unique anchors because their sides are split across the stale-name key and the current-name key.
- **`contact_brand_tenures.dominant_address_unit`** is keyed on the noisy tuple, so the inferred-window expansion logic (which extends backward/forward via address bracketing) only finds party-sides at the same noisy tuple — losing real bracketed sides at synonymous tuples.
- **The Contact page Mailing Addresses card** renders 4 rows that look like duplicates because the city + suite-type info is hidden by the rendering format.

This isn't an address-page issue. It's a foundational data-model gap that shows up everywhere addresses are joined.

---

## Goals

- **Two parallel canonical keys**, computed at compile time and stored on `party_fingerprints`, each serving its own purpose.
- **Folding only definitive equivalences**: city amalgamation, suite-type synonyms, suite-number formatting. **Do not merge differing suite_numbers** (`212` and `222` stay distinct — we don't have ground truth, and silently merging risks the inverse error).
- **Lift downstream regressions**: `auto_groups`, `address_unit_summary`, `anchor_uniqueness`, `contact_brand_tenures` all benefit from grouping on the new canonical keys without each layer reinventing the canonicalization.
- **Reference data lives in JSON**, owned by us, easy to extend.
- **Strict on missing fields**. If `street_direction` is empty on one side and `"east"` on another, treat them as different. We never invent components; we only normalize ones that are definitively the same.

## Non-goals

- **Suite-number override workflow** (`212` vs `222` typo handling). Out of scope; future CRM `address_overrides` table will let analysts mark cases manually.
- **Fuzzy street-name matching** (`saint clair` vs `st. clair` vs `st clair`). Only the listed normalizations apply. Street-name fuzziness is its own problem with its own ambiguity.
- **Postal-code-based canonicalization**. Postals are missing on a lot of source data and don't carry suite info, so they're a weak signal here.
- **Retroactive cleanup of historical data**. The compiler rebuilds `party_fingerprints` from clean-data on every full run. Once the new columns are populated, all derived tables rebuild against them on the next Layer 2 run. No data migration needed.

---

## Architecture

### Two parallel canonical keys

**`property_canonical_id`** — asset identity.
- Foreign key to `properties.id`.
- Source of truth: the parcel resolver. Already computed for ~89% of party-sides via `parcel_links` / the unified resolver.
- Use cases: property page, footprint maps, "what got transacted," asset-level analytics, the Group Portfolio Footprint hero map.
- Granularity: building/parcel. Suite info irrelevant.
- Surfaced as: a new column on `party_fingerprints` that joins to `properties.id`.

**`party_address_canonical`** — operating-address identity.
- A pipe-joined string: `canonical_city|street_number|street_name|street_suffix|street_direction|canonical_suite_type|canonical_suite_number`.
- Source of truth: deterministic normalization of the raw 7-tuple via three reference tables.
- Use cases: contact mailing addresses, address-tenure attribution, anchor uniqueness, the dominant-address-unit signal in `auto_groups` and `contact_brand_tenures`.
- Granularity: suite-level. Different suites in the same building = different keys. Suite_number stays distinct after light normalization.
- Surfaced as: a new column on `party_fingerprints`, used as the join key wherever today's code joins on the raw 7-tuple.

A party-side has both keys. They're independent. A party-side at "2555 Eglinton Suite 212, Scarborough" gets:
- `property_canonical_id = PRO_NNNNN` (the parcel — same value for all 4 noisy suite tuples at that address)
- `party_address_canonical = "toronto|2555|eglinton|ave|east|suite|212"` (canonical city, canonical suite-type, distinct suite-number)

### Where the canonicalization runs

At **compile time**, in the compiler's `party_fingerprints` writer. The compiler already builds the row from clean-data; we add two more derived columns. Once. Idempotent. No runtime cost on read.

The new helper module — `cleo/resolver/address_canonical.py` — exports a single function:

```python
def canonicalize_address(
    city: str | None,
    street_number: str | None,
    street_name: str | None,
    street_suffix: str | None,
    street_direction: str | None,
    suite_type: str | None,
    suite_number: str | None,
) -> str:
    """Return the pipe-joined party_address_canonical key.

    Empty / None components stay empty in the output — never substituted.
    """
```

The function reads three small in-memory dicts (loaded once from the JSON resources at module import), applies the normalization, and emits the key.

### Reference data: JSON files in `cleo/resolver/resources/`

**`city_amalgamation.json`** — historical-name → canonical-name mapping.

```json
{
  "comment": "Ontario municipal amalgamations. Maps the legacy/borough name to the canonical post-amalgamation name. Lowercased on both sides. Extend as more municipalities merge.",
  "amalgamations": [
    {
      "canonical": "toronto",
      "effective_date": "1998-01-01",
      "absorbed": ["scarborough", "north york", "etobicoke", "york", "east york"]
    },
    {
      "canonical": "hamilton",
      "effective_date": "2001-01-01",
      "absorbed": ["stoney creek", "ancaster", "dundas", "flamborough", "glanbrook"]
    },
    {
      "canonical": "ottawa",
      "effective_date": "2001-01-01",
      "absorbed": [
        "nepean", "kanata", "gloucester", "cumberland",
        "goulbourn", "osgoode", "rideau", "rockcliffe park",
        "vanier", "west carleton"
      ]
    },
    {
      "canonical": "kawartha lakes",
      "effective_date": "2001-01-01",
      "absorbed": ["lindsay", "fenelon falls", "bobcaygeon", "omemee", "woodville"]
    }
  ]
}
```

A small loader produces a flat `legacy → canonical` lookup at module import. The `effective_date` field is metadata for explorer surfaces ("when did this amalgamation roll up"); the canonicalization itself just uses the lookup. We always treat amalgamations as retroactive — the deed says Scarborough but it's been Toronto since 1998 and we're treating it as Toronto now. (Records dated pre-1998 still get rolled up; pre-merger data is rare in our corpus and the resolver's job is "where is this place today.")

**`suite_type_synonyms.json`** — suite_type normalization.

```json
{
  "comment": "Synonym groups for suite_type. Each group's `canonical` is what gets stored. Anything not listed maps to itself (i.e., empty stays empty, 'lobby' stays 'lobby').",
  "groups": [
    {
      "canonical": "suite",
      "synonyms": ["suite", "unit", "ste", "u", "#", "no", ""]
    },
    {
      "canonical": "floor",
      "synonyms": ["floor", "fl", "flr"]
    },
    {
      "canonical": "po_box",
      "synonyms": ["po box", "pobox", "p.o. box", "p o box", "box"]
    },
    {
      "canonical": "apartment",
      "synonyms": ["apartment", "apt"]
    }
  ]
}
```

The empty string `""` is in the `suite` synonym group: a missing `suite_type` with a populated `suite_number` is most commonly a suite, and lumping it there matches what users mean. (Edge cases — like `suite_number = "1A"` with empty type meaning "1st floor unit A" — are rare and don't justify keeping `""` as its own bucket.)

**`address_normalization_config.json`** — small config, mostly suite-number rules.

```json
{
  "comment": "Knobs for non-tabular normalization. Suite-number leading zeros are stripped; letter suffix is uppercased.",
  "suite_number": {
    "strip_leading_zeros": true,
    "uppercase_letter_suffix": true
  }
}
```

Suite-number rules in code, not data, but config-flagged so we can disable a rule for testing.

### Normalization rules — definitive

For each component, the canonicalization either applies a deterministic rule or is a no-op:

| Component | Rule | Empty handling |
|---|---|---|
| `city` | lowercase + amalgamation lookup | empty → empty |
| `street_number` | strip whitespace | empty → empty |
| `street_name` | lowercase + strip whitespace | empty → empty |
| `street_suffix` | lowercase + strip whitespace | empty → empty |
| `street_direction` | lowercase + strip whitespace | empty → empty |
| `suite_type` | lowercase + synonym lookup | empty → `suite` (per group above) |
| `suite_number` | strip leading zeros + uppercase letter suffix | empty → empty |

**Strict on empty fields.** If one side has `street_direction = "east"` and another has `street_direction = ""`, they remain different canonical keys. We never invent components from neighboring sides — that's a fuzzy-merge problem with its own ambiguity, out of scope here.

### What this fixes for Dan Hagler's "2555 eglinton" rows

Before:
| city | sn | sname | sfx | dir | stype | snum |
|---|---|---|---|---|---|---|
| scarborough | 2555 | eglinton | avenue | east | suite | 212 |
| toronto | 2555 | eglinton | avenue | east | suite | 212 |
| toronto | 2555 | eglinton | avenue | east | unit | 212 |
| scarborough | 2555 | eglinton | avenue | east | suite | 222 |

After canonicalization (`party_address_canonical`):
- `toronto|2555|eglinton|avenue|east|suite|212` — 3 party-sides
- `toronto|2555|eglinton|avenue|east|suite|222` — 1 party-side

Two rows. Suite distinction preserved. No precision loss.

### What this fixes downstream

- **`auto_groups` Stage A1 (stems.py).** `phone_count_by_stem` and `addr_count_by_stem` group sides by `(phone, stem)` and `(addr_root, stem)`; the `addr_root` here is `"street_number|street_name"` so it's already coarser than the unit, but other surfaces (anchor seeding via `address_unit`) split. The dominant-stem scoring at 30 St Clair improves once canfirst's signal is concentrated.
- **`address_unit_summary`** rebuilds against the canonical key. Counts and dominant_stem become accurate.
- **`anchor_uniqueness`** for address_unit anchors: dominance shares climb because the denominator is no longer split.
- **`contact_brand_tenures.dominant_address_unit`** uses the canonical key. The inferred-window expansion picks up bracketed sides at synonymous tuples — Paul Braun's St Clair coverage stays the same (they were already mostly canonical), but contacts at messier addresses gain coverage.
- **Contact page Mailing Addresses tag**: 4 rows → 2.
- **Address Explorer / Address Unit pages**: lists are deduplicated; the same logical office surfaces once.

---

## Schema changes

### `party_fingerprints` — add two columns

```sql
ALTER TABLE party_fingerprints ADD COLUMN property_canonical_id TEXT;
ALTER TABLE party_fingerprints ADD COLUMN party_address_canonical TEXT;
CREATE INDEX idx_pf_property_canonical ON party_fingerprints(property_canonical_id);
CREATE INDEX idx_pf_party_addr_canonical ON party_fingerprints(party_address_canonical);
```

`property_canonical_id` populated from existing `parcel_links.property_id` lookups (resolver output). NULL when unresolved.

`party_address_canonical` populated by the new helper. Always non-NULL (empty components produce empty fragments, but the key string is never NULL).

### Reference data lives at `cleo/resolver/resources/`

The existing resolver already has a `resources/` directory. Three new files:
- `city_amalgamation.json`
- `suite_type_synonyms.json`
- `address_normalization_config.json`

### Downstream tables — no schema changes, just rebuild

`address_unit_summary`, `anchor_uniqueness`, `auto_group_anchors`, `auto_group_anchor_tenures`, `contact_brand_tenures`, `auto_contact_tenures` all rebuild from `party_fingerprints` on the next Layer 2 run. They get the new canonical keys for free if their derivation queries change to use `party_address_canonical` instead of constructing the 7-tuple inline.

---

## What "rebuild existing data" actually means

(Spec said in the open questions: "How to handle existing data" — clarifying here.)

The system already has full pipelines that rebuild derived tables from source data:

1. **Compiler rebuild** — `python -m cleo.compiler` reads clean-data and rewrites `party_fingerprints` (and all other compiler-derived tables). After this spec ships:
   - The compiler computes the two new columns when it writes each row.
   - `party_fingerprints` now has `property_canonical_id` + `party_address_canonical` populated for every row.

2. **Layer 2 rebuild** — `python -m cleo.discovery_v2` reads `party_fingerprints` and rebuilds `auto_groups`, `address_unit_summary`, `contact_brand_tenures`, etc. After this spec ships:
   - Each Layer 2 builder queries `party_fingerprints.party_address_canonical` instead of constructing the address tuple inline.
   - Derived tables get rebuilt against the canonical key. `address_unit_summary` becomes one row per canonical address. `auto_groups` dominant-stem signals concentrate.

So "rebuilding existing data" is just running these two pipelines once after the schema migration. No data copy/migrate scripts needed. Both pipelines are already idempotent and run in production cadence today.

---

## Backwards compatibility

(Open question #3 — my call.)

**Existing API endpoints that accept a 7-tuple `address_unit` key in URLs continue to work.** The endpoints that read `address_unit_summary` are: `/api/explorer/addresses/units/:key`, `/api/explorer/addresses/units/:key/timeline`. Today these accept the noisy 7-tuple. After this change:

- `address_unit_summary`'s primary key shifts to the canonical key. Old noisy URLs become 404 — but those URLs are internal explorer links, never user-shared, generated dynamically from the table itself. The next page render generates canonical URLs and old links naturally rot.
- The 7-tuple URL parser stays in place for any external link that arrives, but it routes through a one-line normalization (call `canonicalize_address`) before the lookup. So an external link to a noisy 7-tuple still resolves to the canonical row.

Net effect: no user-visible breakage. Internal noise rots naturally. External link compatibility is preserved by routing through canonicalization on read.

---

## Implementation phases

**V1 (this spec):**
- `cleo/resolver/address_canonical.py` helper module + JSON reference data.
- Migration to add the two new columns to `party_fingerprints`.
- Compiler change to populate them on write.
- Run the compiler once to backfill existing rows.
- Update each Layer 2 builder to use `party_address_canonical` instead of the inline 7-tuple construction.
- Run Layer 2 once to rebuild derived tables.
- Confirm: Dan Hagler's 4 mailing-address rows collapse to 2, Paul Braun's tenures and Mark Mandelbaum's tenures unaffected (their addresses were already canonical), 30 St Clair dominant-stem signal concentrates.

**V2 (deferred, separate spec):**
- `address_overrides` CRM table for analyst-marked typo merges (`212 ↔ 222`).
- Fuzzy street-name matching (`saint clair` ↔ `st clair`).
- Empty-component fill-in (when one side has `street_direction = "east"` and another has empty + same street_number+street_name+suite, fill in).
- Property-canonical-id-aware grouping in surfaces that today use party-canonical (e.g., a Group page that shows "all Dan Hagler's deals are at 4 properties" instead of "...at 4 buildings").

---

## Decision log

| # | Decision | Rationale |
|---|---|---|
| 1 | Two parallel canonical keys | Property identity (parcel) and party identity (operating address) serve different purposes. Conflating them costs precision in one direction or fragmentation in the other. |
| 2 | Both keys stored on `party_fingerprints` at compile time | One derivation, every downstream consumer uses the same key. No layer reinvents canonicalization. |
| 3 | Reference data in JSON, owned by us | Wikipedia / StatsCan-derivable. JSON is easy to vet, easy to extend, queryable from the explorer if needed. |
| 4 | Strict on empty components | Fuzzy fill-in is its own problem. We don't invent data. |
| 5 | Don't merge differing suite_numbers | No ground truth — silently folding a real difference is worse than preserving a typo. Override is V2. |
| 6 | Suite-number rules in code with config flags | Easier to test variants than to express in a tabular format. |
| 7 | Empty `suite_type` maps to `suite` | What users mean when the type is missing. The corner case (`"1A"` with empty type) is rare and the cost of misclassification is low. |
| 8 | Backwards-compat: route external 7-tuple URLs through canonicalization on read | No user-visible breakage. Internal noisy URLs rot naturally as pages re-render. |
| 9 | Property-canonical-id surfaced as a column even though it's already in `parcel_links` | Avoids a join on every read. The whole point is making canonical identity cheap to query. |
| 10 | "Rebuild existing data" = run compiler + Layer 2 once | Both are already idempotent and run in production cadence. No bespoke migration scripts. |
