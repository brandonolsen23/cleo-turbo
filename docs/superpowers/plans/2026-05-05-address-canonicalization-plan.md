# Address Canonicalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-05-05-address-canonicalization-design.md`

**Goal:** Add two parallel canonical address keys to `party_fingerprints` so every downstream Layer 2 builder, every API surface, and every frontend tag groups deterministically across Ontario city amalgamations and suite-type/suite-number formatting noise — without merging across genuinely different suites.

**Architecture:** A new helper module `cleo/resolver/address_canonical.py` exports `canonicalize_address(...)`, backed by three JSON reference files in a new `cleo/resolver/resources/` directory (city amalgamations, suite-type synonyms, knobs). The fingerprint pass (`cleo/atoms/fingerprint.py:run_fingerprint_pass`) computes `property_canonical_id` (joined from `transactions.property_id` per `(source_id, side)`) and `party_address_canonical` (via the helper) at write time. Migration 019 adds the two columns + indexes. Layer 2 builders that today reconstruct the noisy 7-tuple inline (`stems`, `seeding`, `expansion`, `contact_brand_tenures`, `address_unit_summary`, `anchor_uniqueness` via `timelines`/`anchor_scores`) switch to reading `pf.party_address_canonical` directly. The two address-explorer endpoints (`/addresses/units/{key}` and `/addresses/units/{key}/timeline`) gain a one-line shim that runs incoming 7-tuple URLs through `canonicalize_address` before lookup, so external links continue to resolve. Refresh is a single compiler run + a single Layer 2 run — no bespoke migration scripts. Idempotent end to end.

**Tech Stack:** Python 3.12, SQLite, FastAPI, React 19 + Vite + TypeScript + Radix UI Themes (jade/slate). Existing patterns per `CLAUDE.md`. Backend port 8099, frontend port 5174.

**Migration:** 019 (next number after 018_contact_brand_tenures).

---

## Glossary (locked from spec — used strictly)

| Term | Meaning |
|---|---|
| **`property_canonical_id`** | A `PRO_NNNNN` value stored on `party_fingerprints` linking the party-side to the parcel its transaction resolved to. Granularity: building/parcel. NULL when the transaction's parcel was never resolved. |
| **`party_address_canonical`** | A pipe-joined string `canonical_city|street_number|street_name|street_suffix|street_direction|canonical_suite_type|canonical_suite_number` stored on `party_fingerprints`. Granularity: suite. Always non-NULL (empty components yield empty fragments — `||||||` is a legitimate value when every input field was empty). |
| **Canonical city** | The post-amalgamation municipality name from `city_amalgamation.json` (lowercase). `scarborough → toronto`, `nepean → ottawa`. Treated as retroactive: pre-1998 records still roll up. |
| **Canonical suite_type** | The synonym-group canonical from `suite_type_synonyms.json` (lowercase). `unit, ste, u, #, no, "" → suite`. Anything outside any synonym group maps to itself (lowercased). |
| **Canonical suite_number** | The raw suite_number with leading zeros stripped and any letter suffix uppercased (`0212 → 212`, `212a → 212A`). Empty stays empty. |
| **The "7-tuple"** | The legacy address key shape used everywhere today: `(city, street_number, street_name, street_suffix, street_direction, suite_type, suite_number)`. The new column replaces inline 7-tuple constructions. |
| **Strict on empty components** | If a component is empty in the input (None or `""`), it stays empty in the output. We never invent components from neighbours. |

Do not invent alternate names. If you need a new concept, surface it as a question rather than shipping new terminology.

---

## Resolved open questions

The spec deferred several implementation questions to this plan. They are resolved here:

1. **Where exactly the new columns are computed and written.** Not in `cleo/compiler/writer.py`. The `party_fingerprints` rows are written in `cleo/atoms/fingerprint.py:run_fingerprint_pass()` (called at the end of the compiler — see `writer.py:1267-1270`). That is the single insert site. Both new columns get computed and appended to the per-row tuple inside the `for r in conn.execute(query)` loop in `run_fingerprint_pass`, and the bulk `executemany(INSERT INTO party_fingerprints …)` statement is extended with the two extra columns. The `DROP TABLE / CREATE TABLE` blocks at the top of that function (which redundantly redeclare the schema — see lines 62-104) are also extended so an isolated `run_fingerprint_pass()` call (e.g. in tests) creates the new columns.
2. **How `property_canonical_id` is looked up per party-side.** There is no `parcel_links` table in `data/cleo.db` — `parcel_links` is a directory of JSON files in `engines/rt/pipeline/parcel_links/`. The compiler already resolves them and writes `transactions.property_id`. The fingerprint pass joins `transaction_parties tp → transactions t ON t.source_id = tp.source_id` (see `fingerprint.py:142-147`), and `t.property_id` is already in scope on the same JOIN. We add `t.property_id AS property_canonical_id` to the SELECT and pass through to the row tuple. A NULL means the transaction's parcel was unresolved (~11% of party-sides per the domain fact); that is normal and surfaces as `NULL` on `party_fingerprints.property_canonical_id`.
3. **Does `address_unit_summary` keep its current schema or get a new column?** Keeps its current schema. Its primary key columns (`city, street_number, street_name, street_suffix, street_direction, suite_type, suite_number`) are still its primary key — but those columns are now populated from the canonical 7-tuple split apart, not the raw 7-tuple. The builder (`cleo/discovery_v2/brand_index.py:build_address_unit_summary`) groups on `pf.party_address_canonical` and parses the canonical key back into its 7 components for the INSERT. No schema migration needed; the table just rebuilds with deduplicated rows.
4. **Does Layer 2 need a hard dependency on a fresh compiler run?** Yes — flagged as the first verification gate in Task 11. If Layer 2 runs against a `party_fingerprints` table where `party_address_canonical IS NULL` (because the compiler hasn't been re-run since the schema migration), every builder breaks loudly: `address_unit_summary` produces zero rows, `anchor_uniqueness` of `address_unit` anchors disappears, `contact_brand_tenures.dominant_address_unit` becomes NULL. The orchestrator (`build_auto_groups`) gets a guard at the top that asserts `SELECT COUNT(*) FROM party_fingerprints WHERE party_address_canonical IS NOT NULL` is non-zero, with a clear error message ("Run the compiler before building Layer 2 — see migration 019."). The frontend operator never runs Layer 2 directly, but Claude does, and we want a fast failure mode rather than silent regression.
5. **Frontend mailing-addresses card rendering.** Yes, surface the suite info. The current rendering on `frontend/src/pages/ContactDetailPage.tsx:218` is `a.address_unit.split("|").slice(1, 5).filter(Boolean).join(" ")` — that strips the city (index 0) AND the suite_type+suite_number (indices 5+6). Since canonical keys collapse city noise, the city becomes safe to surface. And since canonical keys keep distinct suite_numbers distinct, the user must see suite info to tell `212` from `222`. New rendering: `street_number street_name street_suffix street_direction[, Suite suite_number][, City]`. The component title also changes from "Mailing Addresses" to "Mailing Addresses" (no rename — but the canonicalization makes the count drop, which is the user-visible change).

The remaining spec questions (suite_type empty-mapping, retroactivity, postal-as-secondary-signal) were resolved in the spec itself — see the spec's Decision Log #4–#10.

---

## File Structure

**Backend (new):**
- `cleo/resolver/resources/__init__.py` — empty marker.
- `cleo/resolver/resources/city_amalgamation.json` — Ontario amalgamations table.
- `cleo/resolver/resources/suite_type_synonyms.json` — suite_type synonym groups.
- `cleo/resolver/resources/address_normalization_config.json` — suite_number rule flags.
- `cleo/resolver/address_canonical.py` — `canonicalize_address(...)` helper, JSON loaders, in-memory dicts.
- `cleo/database/migrations/019_address_canonicalization.py` — adds the two columns + indexes.
- `tests/test_address_canonical.py` — unit tests for every rule (city, suite_type, suite_number, empty-handling, integration round-trip).
- `tests/test_migration_019_address_canonicalization.py` — migration smoke test.
- `tests/test_atoms_fingerprint_canonical.py` — covers the fingerprint pass writing the two new columns.

**Backend (modified):**
- `cleo/atoms/fingerprint.py` — extend `DROP/CREATE TABLE` block to include the two new columns + indexes; extend the `SELECT` query to include `t.property_id`; extend the per-row tuple to call `canonicalize_address(...)`; extend the `INSERT INTO party_fingerprints` statement to write the two new columns.
- `cleo/database/schema.py:224-248` — add the two columns to the `CREATE TABLE party_fingerprints` declaration so a from-scratch DB matches the migration; add the two indexes (`idx_pf_property_canonical`, `idx_pf_party_addr_canonical`).
- `cleo/discovery_v2/brand_index.py:477-552` (`build_address_unit_summary`) — switch from inline 7-tuple grouping (lines 511-517) to grouping on `pf.party_address_canonical`, parsing the canonical key back into its 7 components for the INSERT.
- `cleo/discovery_v2/timelines.py:24-29` (`_anchor_pf_clause`) — change the `address_unit` clause from inline `(COALESCE … COALESCE …) = ?` to `pf.party_address_canonical = ?`. Also change the address-unit pre-load query (lines 137-140) to `SELECT party_address_canonical AS av, …`.
- `cleo/discovery_v2/expansion.py:67-73` — switch from inline `f"{r['city']}|{r['street_number']}|…"` to reading `r['party_address_canonical']` directly.
- `cleo/discovery_v2/contact_brand_tenures.py:51-83` — replace the seven `COALESCE(pf.<comp>,'') AS …` and the `_address_unit_key(...)` call with `pf.party_address_canonical AS address_unit`. The same applies to the inferred-window expansion query at lines 134-153 — replace the seven address columns and `_address_unit_key(...)` with `pf.party_address_canonical AS address_unit`. The `_address_unit_key` helper at line 213 can stay (no harm) but is no longer called.
- `cleo/web/routes/contacts.py:498-543` (mailing-addresses tag block) — change the SELECT to read `pf.party_address_canonical AS address_unit, MIN(sale_date), MAX(sale_date)` grouped on `party_address_canonical`. Remove the inline `addr_unit = "|".join(...)` reconstruction and use `ar["address_unit"]` directly. The match against `career_history t["dominant_address_unit"]` continues to work because both sides now use the canonical key.
- `cleo/web/routes/explorer.py:1427-1508` (`address_unit_detail`, `address_unit_timeline`) — add a one-line canonicalization shim at the top of each handler: `key = _canonicalize_unit_key(key)`. Define `_canonicalize_unit_key` near the other URL helpers in the file. The pf-match clause inside `address_unit_timeline` (lines 1464-1468) also switches to `pf.party_address_canonical = ?`.
- `cleo/discovery_v2/auto_groups.py:14-31` (`build_auto_groups`) — add a guard at the top: assert `party_fingerprints.party_address_canonical` is populated for ≥ 1 row, else raise with a clear message.

**Frontend (modified):**
- `frontend/src/pages/ContactDetailPage.tsx:212-234` (mailing-addresses card) — change the rendering helper from the current `slice(1, 5)` (strips city + suite) to a small inline formatter that emits `<street_number> <street_name> <street_suffix> <street_direction>[, Suite <suite_number>][, <City>]`. Indexes from `party_address_canonical.split("|")`: 0=city, 1=street_number, 2=street_name, 3=street_suffix, 4=street_direction, 5=suite_type, 6=suite_number.

**Frontend (no change):**
- `frontend/src/types/index.ts` — `address_tenure_tags[].address_unit` stays a string. Its content shape is unchanged at the type level (still a 7-segment pipe-joined string). The migration is purely in the value, not the contract.

---

## Pre-flight context for the implementer

- **The user does not use a CLI.** Every existing surface remains UI-driven; the compiler and Layer 2 reruns are Claude-internal operator actions performed once during the rollout.
- **Derived vs CRM tables.** `party_fingerprints` is a derived table (rebuilt by the compiler — `cleo/atoms/fingerprint.py:62` drops and recreates it on every run). Migration 019 adds two columns to its schema declaration; the next compiler run repopulates them. `address_unit_summary`, `anchor_uniqueness`, `contact_brand_tenures` are also derived. No CRM tables touched.
- **The address tuple lives in two schema declarations today.** `cleo/database/schema.py:224` is the canonical declaration, but `cleo/atoms/fingerprint.py:62-104` redundantly drops and recreates `party_fingerprints` at the top of every fingerprint run. Both blocks must be updated, otherwise the next isolated `run_fingerprint_pass()` call (in tests, or if someone runs just that pass) drops the canonical columns. Every test that imports `run_fingerprint_pass` runs against a fresh in-memory DB and depends on the in-function CREATE block.
- **The branded identifier lives in four fields.** Already correctly handled by `fingerprint.py` (it reads `trade_name`, `care_of`, `companies_json`, `party_name`). The address canonicalization does not change the brand-extraction path; this plan only changes the address columns. But: a Layer 2 builder that joins party-sides by canonical address could surface SPV-style portfolios where the brand is in `trade_name`/`care_of` rather than `party_name`. The plan does not retune that joinery, but we surface it here so the implementer doesn't get distracted by SPV-related questions during testing.
- **Strict on empty components.** A party-side with `street_direction = "east"` and another with `street_direction = ""` produce different `party_address_canonical` keys. This is intentional — see spec §"Strict on empty fields". The unit tests in Task 3 lock this in.
- **Don't merge differing suite_numbers.** `212` and `222` are kept distinct. The override workflow for typo merges is V2 (out of scope per spec §"Non-goals").
- **`property_canonical_id` is just `transactions.property_id`.** No new computation. The compiler already resolves parcels and writes `property_id` on transactions; we copy that value onto each fingerprint row keyed by the same `source_id`. Per the domain fact, ~11% of transactions are unresolved → `property_canonical_id IS NULL`. That is correct, do not flag it as a data issue.
- **Layer 2 orchestrator entry point.** `cleo/discovery_v2/__main__.py` calls `build_auto_groups`. The orchestrator already runs `address_unit_summary` (via `build_address_unit_summary` inside `brand_index.build_layer1_silos`, called from `__main__.py` not `build_auto_groups`). The Task 9 changes are scoped to wherever the inline 7-tuple is reconstructed; we don't need to change the orchestrator's stage order.
- **Test fixture pattern.** Existing tests under `tests/test_discovery_v2_*.py` use an in-memory SQLite DB seeded directly via `conn.execute("INSERT INTO …")`. New tests follow the same pattern. The `cleo.database.schema` module's `DERIVED_TABLES` SQL block is `executescript`-ed onto a fresh `:memory:` connection.
- **Migration runner.** Migrations are run by `python3 -m cleo.database.migrations.019_address_canonicalization` (each migration file has its own `__main__` block — see migration 018 as the template). There is no central migration runner.
- **Production DB path.** `data/cleo.db` (gitignored, ~250K party_fingerprints rows). The compiler rerun in Task 5 takes ~20–30 minutes; the Layer 2 rerun in Task 8 takes ~5–10 minutes. Both must complete cleanly before the verification gate.
- **Backend port 8099, frontend port 5174.** Never use other ports.

---

## Tasks

### Task 1: Migration 019 — add canonical columns to `party_fingerprints`

**Files:**
- Create: `cleo/database/migrations/019_address_canonicalization.py`
- Create: `tests/test_migration_019_address_canonicalization.py`

- [ ] **Step 1: Write the migration smoke test**

Create `tests/test_migration_019_address_canonicalization.py` (following the exact pattern of `tests/test_migration_018_contact_brand_tenures.py`):

```python
"""Tests for migration 019: address canonicalization columns."""
import importlib
import sqlite3


def _fresh_pf_db():
    """Mock a stripped-down party_fingerprints schema (pre-migration)."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE party_fingerprints (
            source_id TEXT NOT NULL,
            side TEXT NOT NULL,
            street_number TEXT,
            street_name TEXT,
            street_suffix TEXT,
            street_direction TEXT,
            suite_type TEXT,
            suite_number TEXT,
            city TEXT,
            province TEXT,
            postal TEXT,
            postal_raw TEXT,
            country TEXT,
            phone TEXT,
            contact_fingerprint TEXT,
            sale_date TEXT,
            computed_at TEXT,
            PRIMARY KEY (source_id, side)
        );
        """
    )
    return conn


def test_migration_adds_columns_and_indexes():
    mod = importlib.import_module(
        "cleo.database.migrations.019_address_canonicalization"
    )
    conn = _fresh_pf_db()
    mod.migrate(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(party_fingerprints)")}
    assert "property_canonical_id" in cols
    assert "party_address_canonical" in cols
    indexes = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='party_fingerprints'"
    )}
    assert "idx_pf_property_canonical" in indexes
    assert "idx_pf_party_addr_canonical" in indexes
    conn.close()


def test_migration_is_idempotent():
    mod = importlib.import_module(
        "cleo.database.migrations.019_address_canonicalization"
    )
    conn = _fresh_pf_db()
    mod.migrate(conn)
    mod.migrate(conn)  # second run must not raise
    cols = {r[1] for r in conn.execute("PRAGMA table_info(party_fingerprints)")}
    assert "property_canonical_id" in cols
    conn.close()
```

Note on importing leading-digit modules: a `from cleo.database.migrations.019_… import …` statement is a syntax error because `019_…` is not a valid Python identifier. `importlib.import_module(...)` works because it takes a string. This matches the existing pattern in `tests/test_migration_018_contact_brand_tenures.py`.

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_migration_019_address_canonicalization.py -v`
Expected: FAIL with `ModuleNotFoundError` or "no such file `019_address_canonicalization.py`".

- [ ] **Step 3: Write the migration**

Create `cleo/database/migrations/019_address_canonicalization.py`:

```python
"""
Migration 019: address canonicalization columns on party_fingerprints.

Adds:
  - property_canonical_id  TEXT  — joins to properties.id (parcel-level
    identity). NULL when the transaction's parcel was unresolved.
  - party_address_canonical TEXT — pipe-joined string of canonicalized
    7-tuple components (city/suite-type/suite-number normalized via
    cleo/resolver/resources/*.json). Always non-NULL once populated by
    the compiler (empty components yield empty fragments).

Both columns are populated by the next run of the compiler's fingerprint
pass (cleo/atoms/fingerprint.py). This migration only adds the schema —
it does NOT backfill. Backfill = compiler rerun.

Idempotent.
"""
from __future__ import annotations
import os
import sqlite3


def migrate(conn: sqlite3.Connection) -> None:
    print("Migration 019: address canonicalization columns...")
    existing_cols = {r[1] for r in conn.execute("PRAGMA table_info(party_fingerprints)")}
    if "property_canonical_id" not in existing_cols:
        conn.execute(
            "ALTER TABLE party_fingerprints ADD COLUMN property_canonical_id TEXT"
        )
    if "party_address_canonical" not in existing_cols:
        conn.execute(
            "ALTER TABLE party_fingerprints ADD COLUMN party_address_canonical TEXT"
        )
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_pf_property_canonical
            ON party_fingerprints(property_canonical_id);
        CREATE INDEX IF NOT EXISTS idx_pf_party_addr_canonical
            ON party_fingerprints(party_address_canonical);
        """
    )
    conn.commit()
    print("Migration 019 complete.")


if __name__ == "__main__":
    db_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "data", "cleo.db"
    )
    conn = sqlite3.connect(db_path)
    migrate(conn)
    conn.close()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_migration_019_address_canonicalization.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Apply the migration to the production DB**

Run: `python3 -m cleo.database.migrations.019_address_canonicalization`
Expected output: `Migration 019: address canonicalization columns... Migration 019 complete.`

Verify by running:

```bash
sqlite3 data/cleo.db "PRAGMA table_info(party_fingerprints)" | grep canonical
```

Expected: two rows mentioning `property_canonical_id` and `party_address_canonical`.

- [ ] **Step 6: Update `cleo/database/schema.py` to keep schema in sync**

Edit `cleo/database/schema.py:224-248` (the `CREATE TABLE IF NOT EXISTS party_fingerprints` block). Add the two columns just before `computed_at`:

```sql
    property_canonical_id   TEXT,
    party_address_canonical TEXT,
    computed_at             TEXT DEFAULT (datetime('now')),
```

Edit `cleo/database/schema.py:344-347` (the `DERIVED_INDEXES` block) — append the two indexes after `idx_pfp_contact`:

```sql
CREATE INDEX IF NOT EXISTS idx_pf_property_canonical ON party_fingerprints(property_canonical_id);
CREATE INDEX IF NOT EXISTS idx_pf_party_addr_canonical ON party_fingerprints(party_address_canonical);
```

- [ ] **Step 7: Commit**

```bash
git add cleo/database/migrations/019_address_canonicalization.py \
        tests/test_migration_019_address_canonicalization.py \
        cleo/database/schema.py
git commit -m "feat(schema): migration 019 — canonical address columns on party_fingerprints"
```

---

### Task 2: Reference data — JSON files

**Files:**
- Create: `cleo/resolver/resources/__init__.py`
- Create: `cleo/resolver/resources/city_amalgamation.json`
- Create: `cleo/resolver/resources/suite_type_synonyms.json`
- Create: `cleo/resolver/resources/address_normalization_config.json`

- [ ] **Step 1: Verify the directory does not already exist**

Run: `ls cleo/resolver/resources 2>&1 || echo "OK — does not exist"`
Expected: `OK — does not exist` (despite spec wording, the directory does not yet exist).

- [ ] **Step 2: Create the directory and an empty `__init__.py`**

Run: `mkdir -p cleo/resolver/resources && touch cleo/resolver/resources/__init__.py`

- [ ] **Step 3: Create `city_amalgamation.json`**

Verbatim from spec:

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

- [ ] **Step 4: Create `suite_type_synonyms.json`**

Verbatim from spec:

```json
{
  "comment": "Synonym groups for suite_type. Each group's `canonical` is what gets stored. Anything not listed maps to itself (i.e., 'lobby' stays 'lobby'). The empty string is in the suite group: missing suite_type with populated suite_number is most commonly a suite.",
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

- [ ] **Step 5: Create `address_normalization_config.json`**

Verbatim from spec:

```json
{
  "comment": "Knobs for non-tabular normalization. Suite-number leading zeros are stripped; letter suffix is uppercased.",
  "suite_number": {
    "strip_leading_zeros": true,
    "uppercase_letter_suffix": true
  }
}
```

- [ ] **Step 6: Commit**

```bash
git add cleo/resolver/resources/
git commit -m "feat(resolver): JSON reference data for address canonicalization"
```

---

### Task 3: `cleo/resolver/address_canonical.py` — the helper module (TDD)

**Files:**
- Create: `cleo/resolver/address_canonical.py`
- Create: `tests/test_address_canonical.py`

The helper exports `canonicalize_address(...)` and three private loaders. Reference data is loaded once at import time into in-memory dicts (a flat `legacy → canonical` lookup for cities, a flat `synonym → canonical` lookup for suite types, plus the small config dict).

- [ ] **Step 1: Write failing tests for every rule**

Create `tests/test_address_canonical.py`:

```python
"""Unit tests for cleo.resolver.address_canonical.canonicalize_address."""
import pytest

from cleo.resolver.address_canonical import canonicalize_address


# ──────────────────────── city amalgamation ────────────────────────

def test_city_scarborough_rolls_up_to_toronto():
    assert canonicalize_address(
        "scarborough", "2555", "eglinton", "ave", "east", "suite", "212"
    ) == "toronto|2555|eglinton|ave|east|suite|212"


def test_city_north_york_rolls_up_to_toronto():
    assert canonicalize_address(
        "North York", "100", "Yonge", "st", "", "", ""
    ) == "toronto|100|yonge|st||suite|"


def test_city_nepean_rolls_up_to_ottawa():
    assert canonicalize_address(
        "Nepean", "1", "Foo", "rd", "", "", ""
    ) == "ottawa|1|foo|rd||suite|"


def test_city_unknown_passes_through_lowercased():
    assert canonicalize_address(
        "Burlington", "100", "lakeshore", "rd", "", "suite", "1"
    ) == "burlington|100|lakeshore|rd||suite|1"


def test_city_already_canonical_unchanged():
    assert canonicalize_address(
        "toronto", "2555", "eglinton", "ave", "east", "suite", "212"
    ) == "toronto|2555|eglinton|ave|east|suite|212"


# ──────────────────────── suite_type synonyms ────────────────────────

def test_suite_type_unit_canonicalizes_to_suite():
    assert canonicalize_address(
        "toronto", "1", "main", "st", "", "unit", "5"
    ) == "toronto|1|main|st||suite|5"


def test_suite_type_ste_canonicalizes_to_suite():
    assert canonicalize_address(
        "toronto", "1", "main", "st", "", "Ste", "5"
    ) == "toronto|1|main|st||suite|5"


def test_suite_type_hash_canonicalizes_to_suite():
    assert canonicalize_address(
        "toronto", "1", "main", "st", "", "#", "5"
    ) == "toronto|1|main|st||suite|5"


def test_suite_type_empty_with_number_becomes_suite():
    # Per spec §suite_type_synonyms.json: "" is in the suite group.
    assert canonicalize_address(
        "toronto", "1", "main", "st", "", "", "5"
    ) == "toronto|1|main|st||suite|5"


def test_suite_type_floor_canonicalizes_to_floor():
    assert canonicalize_address(
        "toronto", "1", "main", "st", "", "FL", "12"
    ) == "toronto|1|main|st||floor|12"


def test_suite_type_apt_canonicalizes_to_apartment():
    assert canonicalize_address(
        "toronto", "1", "main", "st", "", "apt", "5"
    ) == "toronto|1|main|st||apartment|5"


def test_suite_type_unknown_passes_through_lowercased():
    assert canonicalize_address(
        "toronto", "1", "main", "st", "", "Lobby", ""
    ) == "toronto|1|main|st||lobby|"


# ──────────────────────── suite_number normalization ────────────────────────

def test_suite_number_strips_leading_zeros():
    assert canonicalize_address(
        "toronto", "1", "main", "st", "", "suite", "0212"
    ) == "toronto|1|main|st||suite|212"


def test_suite_number_uppercases_letter_suffix():
    assert canonicalize_address(
        "toronto", "1", "main", "st", "", "suite", "212a"
    ) == "toronto|1|main|st||suite|212A"


def test_suite_number_combined_zeros_and_letter():
    assert canonicalize_address(
        "toronto", "1", "main", "st", "", "suite", "0212a"
    ) == "toronto|1|main|st||suite|212A"


def test_suite_number_empty_stays_empty():
    assert canonicalize_address(
        "toronto", "1", "main", "st", "", "suite", ""
    ) == "toronto|1|main|st||suite|"


def test_suite_number_pure_letters_unchanged_except_case():
    assert canonicalize_address(
        "toronto", "1", "main", "st", "", "suite", "ph"
    ) == "toronto|1|main|st||suite|PH"


# ──────────────────────── strict empty handling ────────────────────────

def test_empty_street_direction_does_not_borrow():
    a = canonicalize_address("toronto", "1", "main", "st", "east", "suite", "5")
    b = canonicalize_address("toronto", "1", "main", "st", "",     "suite", "5")
    assert a != b
    assert a.endswith("|east|suite|5")
    assert b.endswith("||suite|5")


def test_none_components_treated_as_empty():
    assert canonicalize_address(
        None, "1", None, "st", None, None, None
    ) == "|1||st||suite|"


def test_whitespace_only_components_treated_as_empty():
    assert canonicalize_address(
        "  ", "1", "  ", "st", "  ", "  ", "  "
    ) == "|1||st||suite|"


# ──────────────────────── Dan Hagler dedup integration ────────────────────────

def test_dan_hagler_eglinton_212_collapses_to_one_key():
    a = canonicalize_address("scarborough", "2555", "eglinton", "avenue", "east", "suite", "212")
    b = canonicalize_address("toronto",     "2555", "eglinton", "avenue", "east", "suite", "212")
    c = canonicalize_address("toronto",     "2555", "eglinton", "avenue", "east", "unit",  "212")
    d = canonicalize_address("scarborough", "2555", "eglinton", "avenue", "east", "suite", "0212")
    assert a == b == c == d == "toronto|2555|eglinton|avenue|east|suite|212"


def test_dan_hagler_eglinton_212_vs_222_kept_distinct():
    twelve = canonicalize_address("scarborough", "2555", "eglinton", "avenue", "east", "suite", "212")
    twenty_two = canonicalize_address("scarborough", "2555", "eglinton", "avenue", "east", "suite", "222")
    assert twelve != twenty_two


# ──────────────────────── deterministic / stable ────────────────────────

def test_function_is_deterministic():
    args = ("scarborough", "2555", "eglinton", "avenue", "east", "unit", "0212a")
    result_1 = canonicalize_address(*args)
    result_2 = canonicalize_address(*args)
    assert result_1 == result_2 == "toronto|2555|eglinton|avenue|east|suite|212A"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_address_canonical.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cleo.resolver.address_canonical'`.

- [ ] **Step 3: Implement the helper module**

Create `cleo/resolver/address_canonical.py`:

```python
"""Address canonicalization helper.

Folds Ontario city amalgamations, suite-type synonyms, and suite-number
formatting noise into a single deterministic key. Strict on empty
components: we never invent data.

Reference data is JSON in cleo/resolver/resources/. Loaded once at module
import into in-memory dicts. To extend the rules, edit the JSON.

Public API:
    canonicalize_address(city, street_number, street_name, street_suffix,
                         street_direction, suite_type, suite_number) -> str

Returns a pipe-joined 7-segment string. Always non-empty (an all-empty
input produces "|||||suite|" (6 pipes, 7 segments) — the suite_type empty-mapping is
intentional per spec §suite_type_synonyms.json).
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Optional

_RESOURCE_DIR = Path(__file__).parent / "resources"


def _load_city_lookup() -> dict[str, str]:
    """Flatten city_amalgamation.json into a legacy → canonical dict."""
    path = _RESOURCE_DIR / "city_amalgamation.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    lookup: dict[str, str] = {}
    for group in data["amalgamations"]:
        canonical = group["canonical"].lower()
        # Canonical maps to itself (idempotent for already-canonical inputs).
        lookup[canonical] = canonical
        for absorbed in group["absorbed"]:
            lookup[absorbed.lower()] = canonical
    return lookup


def _load_suite_type_lookup() -> dict[str, str]:
    """Flatten suite_type_synonyms.json into a synonym → canonical dict."""
    path = _RESOURCE_DIR / "suite_type_synonyms.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    lookup: dict[str, str] = {}
    for group in data["groups"]:
        canonical = group["canonical"].lower()
        for synonym in group["synonyms"]:
            lookup[synonym.lower()] = canonical
    return lookup


def _load_config() -> dict:
    path = _RESOURCE_DIR / "address_normalization_config.json"
    return json.loads(path.read_text(encoding="utf-8"))


_CITY = _load_city_lookup()
_SUITE_TYPE = _load_suite_type_lookup()
_CONFIG = _load_config()

_LETTER_SUFFIX_RE = re.compile(r"^(\d+)([A-Za-z]+)$")


def _norm_text(value: Optional[str]) -> str:
    """Lowercase + strip; treat None / whitespace-only as empty."""
    if value is None:
        return ""
    s = str(value).strip().lower()
    return s


def _canon_city(value: Optional[str]) -> str:
    s = _norm_text(value)
    if not s:
        return ""
    return _CITY.get(s, s)


def _canon_suite_type(value: Optional[str]) -> str:
    """Map synonym → canonical. Unknown values pass through lowercased."""
    s = _norm_text(value)
    # The lookup contains the empty string ("" → "suite") per the spec.
    if s in _SUITE_TYPE:
        return _SUITE_TYPE[s]
    return s


def _canon_suite_number(value: Optional[str]) -> str:
    s = _norm_text(value)
    if not s:
        return ""
    cfg = _CONFIG.get("suite_number", {})

    # Strip leading zeros from any leading digit run.
    if cfg.get("strip_leading_zeros", True):
        m = _LETTER_SUFFIX_RE.match(s)
        if m:
            digits = m.group(1).lstrip("0") or "0"
            s = digits + m.group(2)
        else:
            stripped = s.lstrip("0")
            # If the value was all zeros, lstrip kills it — preserve a single 0.
            if stripped == "" and s != "":
                stripped = "0"
            # Only replace if the input was purely numeric (don't lstrip "00ph").
            if s.isdigit():
                s = stripped

    # Uppercase any letter suffix.
    if cfg.get("uppercase_letter_suffix", True):
        s = s.upper()

    return s


def canonicalize_address(
    city: Optional[str],
    street_number: Optional[str],
    street_name: Optional[str],
    street_suffix: Optional[str],
    street_direction: Optional[str],
    suite_type: Optional[str],
    suite_number: Optional[str],
) -> str:
    """Return the pipe-joined party_address_canonical key.

    Empty / None / whitespace-only components stay empty in the output
    (with one exception: empty suite_type maps to "suite" via the
    synonyms table — see spec).
    """
    return "|".join([
        _canon_city(city),
        _norm_text(street_number),
        _norm_text(street_name),
        _norm_text(street_suffix),
        _norm_text(street_direction),
        _canon_suite_type(suite_type),
        _canon_suite_number(suite_number),
    ])
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_address_canonical.py -v`
Expected: PASS (all tests).

If any test fails, fix the helper and re-run. Do not edit the tests except to fix typos.

- [ ] **Step 5: Commit**

```bash
git add cleo/resolver/address_canonical.py tests/test_address_canonical.py
git commit -m "feat(resolver): canonicalize_address helper + reference data loaders"
```

---

### Task 4: Compiler change — populate the canonical columns at fingerprint time (TDD)

**Files:**
- Modify: `cleo/atoms/fingerprint.py:62-104` (DROP/CREATE block) and `cleo/atoms/fingerprint.py:132-216` (SELECT + per-row build + INSERT)
- Create: `tests/test_atoms_fingerprint_canonical.py`

- [ ] **Step 1: Write a failing fingerprint-pass test**

Create `tests/test_atoms_fingerprint_canonical.py`:

```python
"""Tests that the fingerprint pass populates the canonical address columns."""
import sqlite3

import pytest

from cleo.atoms.fingerprint import run_fingerprint_pass


def _seed_minimal_db() -> sqlite3.Connection:
    """Tiny DB with two transactions, two parties each, sharing an ARN.

    Both transactions resolve to the same property_id (PRO_00001) but the
    party-side mailing addresses use noisy variants:
      - source RT001 buyer side: scarborough / suite / 0212
      - source RT002 buyer side: toronto / unit / 212
    Both should canonicalize to the same party_address_canonical.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE transactions (
            source_id TEXT PRIMARY KEY,
            property_id TEXT,
            arn TEXT,
            sale_date TEXT,
            seller_trade_name TEXT, seller_care_of TEXT,
            seller_law_firms_json TEXT, seller_companies_json TEXT,
            buyer_trade_name TEXT, buyer_care_of TEXT,
            buyer_law_firms_json TEXT, buyer_companies_json TEXT
        );
        CREATE TABLE transaction_parties (
            source_id TEXT, side TEXT, party_name TEXT,
            phone TEXT, contact_id TEXT
        );
        CREATE TABLE transaction_mailing_addresses (
            source_id TEXT, side TEXT,
            street_number TEXT, street_name TEXT, street_suffix TEXT,
            street_direction TEXT, suite_type TEXT, suite_number TEXT,
            city TEXT, province TEXT, postal TEXT, country TEXT
        );
        CREATE TABLE contacts (
            id TEXT PRIMARY KEY, first_name TEXT, last_name TEXT
        );
        INSERT INTO transactions VALUES
            ('RT001', 'PRO_00001', '12345', '2024-01-01',
             '', '', '[]', '[]', '', '', '[]', '[]'),
            ('RT002', 'PRO_00001', '12345', '2024-06-01',
             '', '', '[]', '[]', '', '', '[]', '[]');
        INSERT INTO transaction_parties VALUES
            ('RT001', 'buyer', 'Acme Corp', '4165550001', NULL),
            ('RT002', 'buyer', 'Acme Corp', '4165550001', NULL);
        INSERT INTO transaction_mailing_addresses VALUES
            ('RT001', 'buyer', '2555', 'eglinton', 'avenue', 'east',
             'suite', '0212', 'scarborough', 'on', 'M1K0A0', 'ca'),
            ('RT002', 'buyer', '2555', 'eglinton', 'avenue', 'east',
             'unit', '212', 'toronto', 'on', 'M1K0A0', 'ca');
        """
    )
    conn.commit()
    return conn


def test_fingerprint_pass_writes_canonical_columns():
    conn = _seed_minimal_db()
    run_fingerprint_pass(conn)
    rows = conn.execute(
        "SELECT source_id, party_address_canonical, property_canonical_id "
        "FROM party_fingerprints ORDER BY source_id"
    ).fetchall()
    assert len(rows) == 2
    # Both noisy inputs collapse to the same canonical key.
    assert rows[0]["party_address_canonical"] == rows[1]["party_address_canonical"]
    assert rows[0]["party_address_canonical"] == \
        "toronto|2555|eglinton|avenue|east|suite|212"
    # Both rows share property_canonical_id from transactions.property_id.
    assert rows[0]["property_canonical_id"] == "PRO_00001"
    assert rows[1]["property_canonical_id"] == "PRO_00001"


def test_fingerprint_pass_handles_unresolved_property_id():
    conn = _seed_minimal_db()
    conn.execute("UPDATE transactions SET property_id = NULL WHERE source_id='RT001'")
    run_fingerprint_pass(conn)
    rows = conn.execute(
        "SELECT source_id, property_canonical_id FROM party_fingerprints ORDER BY source_id"
    ).fetchall()
    assert rows[0]["property_canonical_id"] is None
    assert rows[1]["property_canonical_id"] == "PRO_00001"


def test_fingerprint_pass_canonical_column_never_null():
    """Even an all-empty mailing address yields a non-NULL canonical key."""
    conn = _seed_minimal_db()
    conn.execute(
        """UPDATE transaction_mailing_addresses
           SET street_number='', street_name='', street_suffix='',
               street_direction='', suite_type='', suite_number='', city=''"""
    )
    run_fingerprint_pass(conn)
    rows = conn.execute(
        "SELECT party_address_canonical FROM party_fingerprints"
    ).fetchall()
    for r in rows:
        assert r["party_address_canonical"] is not None
        # All-empty input → "|||||suite|" (empty suite_type maps to suite).
        assert r["party_address_canonical"] == "|||||suite|"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_atoms_fingerprint_canonical.py -v`
Expected: FAIL with "no such column: party_address_canonical" or similar.

- [ ] **Step 3: Update the in-function `CREATE TABLE` block in `fingerprint.py`**

Edit `cleo/atoms/fingerprint.py:62-104`. Add the two new columns to the `CREATE TABLE party_fingerprints` block (after `sale_date`, before `computed_at`):

```python
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS party_fingerprints (
            source_id           TEXT NOT NULL,
            side                TEXT NOT NULL CHECK (side IN ('buyer','seller')),
            street_number       TEXT,
            street_name         TEXT,
            street_suffix       TEXT,
            street_direction    TEXT,
            suite_type          TEXT,
            suite_number        TEXT,
            city                TEXT,
            province            TEXT,
            postal              TEXT,
            postal_raw          TEXT,
            country             TEXT,
            phone               TEXT,
            contact_fingerprint TEXT,
            sale_date           TEXT,
            property_canonical_id   TEXT,
            party_address_canonical TEXT,
            computed_at         TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (source_id, side)
        );
        CREATE TABLE IF NOT EXISTS party_atoms (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id    TEXT NOT NULL,
            side         TEXT NOT NULL CHECK (side IN ('buyer','seller')),
            atom_type    TEXT NOT NULL,
            atom_value   TEXT NOT NULL,
            source_field TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_pfp_street_key ON party_fingerprints(street_number, street_name, street_suffix);
        CREATE INDEX IF NOT EXISTS idx_pfp_postal ON party_fingerprints(postal);
        CREATE INDEX IF NOT EXISTS idx_pfp_phone ON party_fingerprints(phone);
        CREATE INDEX IF NOT EXISTS idx_pfp_contact ON party_fingerprints(contact_fingerprint);
        CREATE INDEX IF NOT EXISTS idx_pf_property_canonical ON party_fingerprints(property_canonical_id);
        CREATE INDEX IF NOT EXISTS idx_pf_party_addr_canonical ON party_fingerprints(party_address_canonical);
        CREATE INDEX IF NOT EXISTS idx_pa_lookup ON party_atoms(atom_type, atom_value);
        CREATE INDEX IF NOT EXISTS idx_pa_party ON party_atoms(source_id, side);
    """)
```

- [ ] **Step 4: Add the `canonicalize_address` import**

Edit the top of `cleo/atoms/fingerprint.py` (around line 13):

```python
from cleo.atoms.normalize import (
    normalize_brand, tokenize_brand, normalize_contact_name,
    normalize_phone, normalize_street_number, normalize_street_name,
    normalize_street_suffix, normalize_street_direction,
    normalize_suite_type, normalize_suite_number, normalize_city,
    normalize_province, normalize_postal, normalize_country,
)
from cleo.resolver.address_canonical import canonicalize_address
```

- [ ] **Step 5: Extend the SELECT to include `t.property_id`**

Edit the `query` string (`cleo/atoms/fingerprint.py:132-147`) to include `t.property_id AS property_id`:

```python
    query = """
        SELECT DISTINCT
            tp.source_id,
            tp.side,
            t.sale_date,
            t.property_id,
            CASE tp.side WHEN 'buyer' THEN t.buyer_trade_name ELSE t.seller_trade_name END AS trade_name,
            CASE tp.side WHEN 'buyer' THEN t.buyer_care_of ELSE t.seller_care_of END AS care_of,
            CASE tp.side WHEN 'buyer' THEN t.buyer_companies_json ELSE t.seller_companies_json END AS companies_json,
            CASE tp.side WHEN 'buyer' THEN t.buyer_law_firms_json ELSE t.seller_law_firms_json END AS law_firms_json,
            tma.street_number, tma.street_name, tma.street_suffix, tma.street_direction,
            tma.suite_type, tma.suite_number, tma.city, tma.province, tma.postal, tma.country
        FROM transaction_parties tp
        JOIN transactions t ON t.source_id = tp.source_id
        LEFT JOIN transaction_mailing_addresses tma
            ON tma.source_id = tp.source_id AND tma.side = tp.side
    """
```

- [ ] **Step 6: Build the per-row tuple with the two new values**

Edit the `fp_rows.append((...))` block (`cleo/atoms/fingerprint.py:170-187`). Compute the canonical address key from the **normalized** atom outputs (so the canonicalization stacks on top of the existing atom-level normalization rather than competing with it), and append the property_id:

```python
        norm_street_number = normalize_street_number(r['street_number'])
        norm_street_name = normalize_street_name(r['street_name'])
        norm_street_suffix = normalize_street_suffix(r['street_suffix'])
        norm_street_direction = normalize_street_direction(r['street_direction'])
        norm_suite_type = normalize_suite_type(r['suite_type'])
        norm_suite_number = normalize_suite_number(r['suite_number'])
        norm_city = normalize_city(r['city'])

        party_address_canonical = canonicalize_address(
            norm_city,
            norm_street_number,
            norm_street_name,
            norm_street_suffix,
            norm_street_direction,
            norm_suite_type,
            norm_suite_number,
        )

        fp_rows.append((
            r['source_id'],
            r['side'],
            norm_street_number,
            norm_street_name,
            norm_street_suffix,
            norm_street_direction,
            norm_suite_type,
            norm_suite_number,
            norm_city,
            normalize_province(r['province']),
            normalize_postal(r['postal']),
            r['postal'],  # postal_raw — preserve source string verbatim
            normalize_country(r['country']),
            phone,
            contact_fp,
            r['sale_date'],
            r['property_id'],            # property_canonical_id
            party_address_canonical,     # party_address_canonical
        ))
```

- [ ] **Step 7: Extend the INSERT to write the two new columns**

Edit the `executemany(INSERT INTO party_fingerprints ...)` block (`cleo/atoms/fingerprint.py:208-216`):

```python
    conn.executemany(
        """INSERT INTO party_fingerprints
           (source_id, side, street_number, street_name, street_suffix, street_direction,
            suite_type, suite_number, city, province, postal, postal_raw, country,
            phone, contact_fingerprint, sale_date,
            property_canonical_id, party_address_canonical)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        fp_rows,
    )
```

- [ ] **Step 8: Run the test to verify it passes**

Run: `pytest tests/test_atoms_fingerprint_canonical.py -v`
Expected: PASS (all three tests).

- [ ] **Step 9: Run the existing fingerprint test suite to ensure no regressions**

Run: `pytest tests/test_atoms_fingerprint.py -v` (if the file exists; if not, skip).
Run: `pytest tests/test_atoms_normalize.py -v`
Expected: PASS for both.

- [ ] **Step 10: Commit**

```bash
git add cleo/atoms/fingerprint.py tests/test_atoms_fingerprint_canonical.py
git commit -m "feat(atoms): write property_canonical_id and party_address_canonical at fingerprint time"
```

---

### Task 5: Run the compiler against the production DB to backfill

**Files:** none modified — this is an operator step.

- [ ] **Step 1: Verify the compiler is runnable and the prior migration applied**

Run: `sqlite3 data/cleo.db "PRAGMA table_info(party_fingerprints)" | grep canonical`
Expected: two rows mentioning `property_canonical_id` and `party_address_canonical`.

If empty, return to Task 1 Step 5.

- [ ] **Step 2: Run the compiler**

Run: `python -m cleo.compiler`
Expected: long-running process (~20–30 minutes on production data). Tail output for errors. The fingerprint pass at the end should print `Fingerprint pass complete: <N>,000 party-sides, <M>,000 atoms.`

- [ ] **Step 3: Spot-check the canonical columns are populated**

Run:

```bash
sqlite3 data/cleo.db <<'SQL'
SELECT
  COUNT(*) AS total,
  SUM(CASE WHEN party_address_canonical IS NULL THEN 1 ELSE 0 END) AS null_addr,
  SUM(CASE WHEN property_canonical_id IS NULL THEN 1 ELSE 0 END) AS null_property
FROM party_fingerprints;
SQL
```

Expected: `null_addr` = 0 (the canonical key is always non-NULL by construction). `null_property` is roughly 11% of total (the unresolved-parcel domain fact).

- [ ] **Step 4: Spot-check Dan Hagler's specific case**

Run:

```bash
sqlite3 data/cleo.db <<'SQL'
SELECT party_address_canonical, COUNT(*) AS n
FROM party_fingerprints
WHERE contact_fingerprint = 'dan hagler'
  AND street_number = '2555' AND street_name = 'eglinton'
GROUP BY 1
ORDER BY n DESC;
SQL
```

Expected: ≤ 2 distinct canonical keys (one for suite 212, one for suite 222), summing to the same row count as before.

- [ ] **Step 5: No commit needed (data refresh, not code).**

---

### Task 6: Switch Layer 2 builders to read `party_address_canonical`

**Files:**
- Modify: `cleo/discovery_v2/timelines.py:24-29` and `:137-140`
- Modify: `cleo/discovery_v2/expansion.py:62-83`
- Modify: `cleo/discovery_v2/contact_brand_tenures.py:51-83` and `:134-153`
- Modify: `cleo/discovery_v2/brand_index.py:477-552` (`build_address_unit_summary`)

The goal is to replace every inline 7-tuple reconstruction with a direct read of `pf.party_address_canonical`. The canonical column contains exactly the same string shape as the old inline construction, so once the compiler has populated the column, the swap is mechanical and the existing tests pass without value changes.

- [ ] **Step 1: Run the existing discovery_v2 test suite to capture baseline**

Run: `pytest tests/test_discovery_v2_*.py -v`
Expected: PASS. Note any failures BEFORE making changes (so we know which failures are pre-existing).

- [ ] **Step 2: Update `cleo/discovery_v2/timelines.py`**

Edit `_anchor_pf_clause` (lines 16-30) — replace the inline `address_unit` clause:

```python
def _anchor_pf_clause(anchor_type: str) -> str:
    """SQL fragment that filters party_fingerprints (aliased pf) for the given
    anchor_type. Expects exactly one bind param: the anchor_value."""
    if anchor_type == 'phone':
        return "pf.phone = ?"
    if anchor_type == 'contact':
        return "pf.contact_fingerprint = ?"
    if anchor_type == 'address_unit':
        return "pf.party_address_canonical = ?"
    raise ValueError(f"Unknown anchor_type: {anchor_type!r}")
```

Edit the address-unit pre-load query in `iter_all_anchor_timelines` (lines 134-152) — switch from inline construction to reading the column:

```python
    # Address units
    for r in conn.execute(
        """
        SELECT party_address_canonical AS av, source_id, side, sale_date
        FROM party_fingerprints
        WHERE party_address_canonical IS NOT NULL
          AND party_address_canonical != ''
          AND city IS NOT NULL AND city != ''
          AND street_number IS NOT NULL AND street_number != ''
          AND street_name IS NOT NULL AND street_name != ''
          AND sale_date IS NOT NULL AND sale_date != ''
        ORDER BY sale_date, source_id, side
        """
    ):
        events_by_anchor.setdefault(('address_unit', r['av']), []).append(
            (r['sale_date'], r['source_id'], r['side'])
        )
```

The `WHERE city IS NOT NULL AND city != '' …` clauses stay — they exclude rows with no usable address (the canonical key still exists for those rows, but anchor_uniqueness shouldn't track empty-keyed anchors).

- [ ] **Step 3: Update `cleo/discovery_v2/expansion.py:62-83`**

Replace the inline reconstruction:

```python
    side_data: dict[tuple, dict] = {}  # (sid, side) -> info dict
    for r in conn.execute("""
        SELECT source_id, side, phone, contact_fingerprint,
               party_address_canonical, sale_date,
               city, street_number, street_name
        FROM party_fingerprints
    """):
        addr_unit = (
            r['party_address_canonical']
            if r['city'] and r['street_number'] and r['street_name']
            else None
        )
        side_data[(r['source_id'], r['side'])] = {
            'phone':     r['phone'] or None,
            'addr_unit': addr_unit,
            'contact':   r['contact_fingerprint'] or None,
            'sale_date': r['sale_date'] or None,
            'stems':     set(),
            'phrases':   [],
        }
```

The "city + number + name present" gate is preserved so we don't seed/match on empty-tuple address keys.

- [ ] **Step 4: Update `cleo/discovery_v2/contact_brand_tenures.py:41-84`**

Replace the seven `COALESCE(pf.<comp>,'') AS …` columns and the `_address_unit_key(...)` call with a direct read of `party_address_canonical`:

```python
    rows = conn.execute(
        f"""
        SELECT pf.contact_fingerprint   AS cf,
               m.stem                    AS stem,
               pa.atom_value             AS phrase,
               pa.source_field           AS source_field,
               pf.sale_date              AS sale_date,
               pf.source_id              AS source_id,
               pf.side                   AS side,
               pf.party_address_canonical AS address_unit
        FROM party_atoms pa
        JOIN party_fingerprints pf
          ON pf.source_id = pa.source_id AND pf.side = pa.side
        JOIN brand_stem_phrase_map m
          ON m.phrase = pa.atom_value
        WHERE pa.atom_type = 'brand_phrase'
          AND pa.source_field IN ({placeholders})
          AND pf.contact_fingerprint IS NOT NULL
          AND pf.contact_fingerprint != ''
          AND pf.sale_date IS NOT NULL
          AND pf.sale_date != ''
        """,
        QUALIFYING_SOURCE_FIELDS,
    ).fetchall()

    # Step 2 — group by (contact_fingerprint, stem) and aggregate.
    by_pair: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        by_pair[(r["cf"], r["stem"])].append({
            "phrase": r["phrase"],
            "source_field": r["source_field"],
            "sale_date": r["sale_date"],
            "source_id": r["source_id"],
            "side": r["side"],
            "address_unit": r["address_unit"] or "",
        })
```

Edit the inferred-window expansion query (lines 134-153) similarly:

```python
        if dominant_addr is not None:
            ext_rows = conn.execute(
                """
                SELECT pf.source_id, pf.side, pf.sale_date,
                       pf.party_address_canonical AS address_unit
                FROM party_fingerprints pf
                WHERE pf.contact_fingerprint = ?
                  AND pf.sale_date IS NOT NULL AND pf.sale_date != ''
                """,
                (cf,),
            ).fetchall()
            for er in ext_rows:
                if (er["address_unit"] or "") != dominant_addr:
                    continue
                if er["sale_date"] < inferred_start:
                    inferred_start = er["sale_date"]
                if er["sale_date"] > inferred_end:
                    inferred_end = er["sale_date"]
                inferred_sides.add((er["source_id"], er["side"]))
```

The `_address_unit_key` helper at line 213 stays (no longer called from this module, but small enough to leave as a documented utility — and nothing else imports it). Add a comment above it noting it is now legacy:

```python
def _address_unit_key(city, sn, st, sx, sd, suite_t, suite_n) -> str:
    """LEGACY: pre-canonicalization 7-tuple builder. Kept for reference and
    in case any external test fixture still calls it. Prefer reading
    party_fingerprints.party_address_canonical instead.
    """
```

- [ ] **Step 5: Update `cleo/discovery_v2/brand_index.py:477-552` (`build_address_unit_summary`)**

The current builder groups on the inline 7-tuple. Switch to grouping on `party_address_canonical` and parse the canonical key back into its 7 components for the INSERT (so `address_unit_summary`'s schema is unchanged):

```python
def build_address_unit_summary(conn, *, verbose: bool = True):
    """Layer 1 silo: per-unit brand-stem dominance.

    A 'unit' is the canonical address: party_address_canonical from
    party_fingerprints. The summary's 7 PK columns are split apart from
    the canonical key so the table schema is unchanged.
    """
    conn.execute('DELETE FROM address_unit_summary')

    # Step 1: build per-side dominant stem (most-common stem across the side's phrases).
    side_stems: dict = {}
    for r in conn.execute("""
        SELECT pa.source_id, pa.side, m.stem, COUNT(*) AS n
        FROM party_atoms pa
        JOIN brand_stem_phrase_map m ON m.phrase = pa.atom_value
        WHERE pa.atom_type = 'brand_phrase'
        GROUP BY pa.source_id, pa.side, m.stem
    """):
        key = (r['source_id'], r['side'])
        prev = side_stems.get(key)
        new_value = (r['stem'], r['n'])
        if prev is None or (r['n'] > prev[1]) or (r['n'] == prev[1] and r['stem'] < prev[0]):
            side_stems[key] = new_value

    # Step 2: aggregate parties by canonical-unit key, computing stem counts.
    by_unit: dict = {}
    for r in conn.execute("""
        SELECT source_id, side, party_address_canonical AS k
        FROM party_fingerprints
        WHERE city IS NOT NULL AND city != ''
          AND street_number IS NOT NULL AND street_number != ''
          AND street_name IS NOT NULL AND street_name != ''
          AND party_address_canonical IS NOT NULL
          AND party_address_canonical != ''
    """):
        key = r['k']
        bucket = by_unit.setdefault(key, {'sides': 0, 'stem_counts': {}})
        bucket['sides'] += 1
        st = side_stems.get((r['source_id'], r['side']))
        if st is not None:
            bucket['stem_counts'][st[0]] = bucket['stem_counts'].get(st[0], 0) + 1

    # Step 3: insert rows, computing dominant stem + share. Split the canonical
    # key back into its 7 components for the schema-stable INSERT.
    rows_to_insert = []
    for canonical_key, bucket in by_unit.items():
        parts = canonical_key.split('|', 6)
        if len(parts) != 7:
            # Defensive: any malformed key is skipped (should never happen).
            continue
        city, num, name, suf, dir_, stype, snum = parts
        n_parties = bucket['sides']
        stem_counts = bucket['stem_counts']
        n_distinct = len(stem_counts)
        if stem_counts:
            dom_stem, dom_n = sorted(stem_counts.items(), key=lambda kv: (-kv[1], kv[0]))[0]
            dom_share = dom_n / n_parties
        else:
            dom_stem, dom_share = None, 0.0
        rows_to_insert.append((
            city, num, name, suf, dir_, stype, snum,
            n_parties, n_distinct, dom_stem, dom_share,
        ))

    conn.executemany(
        """INSERT INTO address_unit_summary
            (city, street_number, street_name, street_suffix, street_direction,
             suite_type, suite_number, n_party_sides, n_distinct_brand_stems,
             dominant_stem, dominance_share)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows_to_insert,
    )
    conn.commit()
    if verbose:
        print(f'Layer 1 Silo E (address units): {len(rows_to_insert):,} distinct units', flush=True)
    return {'n_units': len(rows_to_insert)}
```

- [ ] **Step 6: Add the Layer 2 orchestrator guard**

Edit `cleo/discovery_v2/auto_groups.py:14-31` (`build_auto_groups`). At the top of the function:

```python
def build_auto_groups(conn: sqlite3.Connection, *, verbose: bool = True) -> dict:
    """Run all stages of Layer 2. Idempotent — each stage clears its own derived tables."""
    if verbose:
        print('Layer 2: starting build...', flush=True)

    # Guard: Layer 2 reads pf.party_address_canonical. If the compiler has not
    # been re-run since migration 019, every address-unit downstream produces
    # zero rows. Fail fast with a clear message instead of silent regression.
    n_canonical = conn.execute(
        "SELECT COUNT(*) FROM party_fingerprints "
        "WHERE party_address_canonical IS NOT NULL "
        "  AND party_address_canonical != ''"
    ).fetchone()[0]
    if n_canonical == 0:
        raise RuntimeError(
            "party_fingerprints.party_address_canonical is empty. "
            "Run the compiler ('python -m cleo.compiler') to repopulate "
            "fingerprints under migration 019 before building Layer 2."
        )

    a1 = build_stems(conn, verbose=verbose)
    # ...rest unchanged
```

- [ ] **Step 7: Run the discovery_v2 test suite to verify no regressions**

Run: `pytest tests/test_discovery_v2_*.py -v`
Expected: PASS (all tests that were passing before still pass; the canonical column is set in test fixtures via direct `INSERT INTO party_fingerprints` — see Step 8 if any test fixture needs updating).

If any test fails because its fixture didn't seed `party_address_canonical`, update the fixture to populate the column with the equivalent inline 7-tuple value (since the test's input was already canonical). Do NOT change the assertion side of the test.

- [ ] **Step 8: Commit**

```bash
git add cleo/discovery_v2/timelines.py cleo/discovery_v2/expansion.py \
        cleo/discovery_v2/contact_brand_tenures.py cleo/discovery_v2/brand_index.py \
        cleo/discovery_v2/auto_groups.py
git commit -m "feat(layer2): read party_address_canonical instead of inline 7-tuple"
```

---

### Task 7: Update the contacts-route mailing-addresses query

**Files:**
- Modify: `cleo/web/routes/contacts.py:498-543`

The current query reconstructs the address_unit from seven `COALESCE` columns and rebuilds the key with `"|".join([…])` in Python. After Task 4, the canonical key is on the row directly. Switch to it.

- [ ] **Step 1: Replace the address-tag SELECT block**

Edit `cleo/web/routes/contacts.py:498-543` (the `address_tags = []` block). Replace the inner query and the inline `addr_unit = "|".join(...)` reconstruction:

```python
    # Address tenure tag: the contact's "primary mailing address" doesn't live
    # on the contacts row. We surface a tag for each unique canonical address
    # that appears on this contact's party-sides, sorted most-recent first.
    # The UI decides which one to show under the (single) Address row.
    address_tags = []
    if fp:
        addr_rows = db.execute(
            """
            SELECT party_address_canonical AS address_unit,
                   MIN(sale_date) AS first_seen,
                   MAX(sale_date) AS last_seen
            FROM party_fingerprints
            WHERE contact_fingerprint = ?
              AND street_number IS NOT NULL AND street_number != ''
              AND party_address_canonical IS NOT NULL
              AND party_address_canonical != ''
            GROUP BY party_address_canonical
            ORDER BY MAX(sale_date) DESC
            """,
            (fp,),
        ).fetchall()
        for ar in addr_rows:
            addr_unit = ar["address_unit"]
            # Match against tenure dominant_address_unit. Both sides are
            # canonical keys post-migration 019.
            matching = [t for t in career_history if t.get("dominant_address_unit") == addr_unit]
            tag = None
            if matching:
                t = matching[0]
                if t.get("is_active") == 1 and ar["last_seen"] >= cliff:
                    tag = {"state": "active", "stem": t["brand_stem"],
                           "display_name": t["display_name"],
                           "since": t["inferred_start_date"]}
                else:
                    tag = {"state": "stale", "stem": t["brand_stem"],
                           "display_name": t["display_name"],
                           "last_seen": ar["last_seen"]}
            address_tags.append({
                "address_unit": addr_unit,
                "first_seen": ar["first_seen"],
                "last_seen": ar["last_seen"],
                "tag": tag,
            })
    result["address_tenure_tags"] = address_tags
```

- [ ] **Step 2: Run the contacts-route test suite (if any) to verify no regression**

Run: `pytest tests/test_routes_contacts.py -v 2>&1 || pytest tests/test_routes_contact_tenures.py -v`
Expected: PASS for whichever exists.

- [ ] **Step 3: Commit**

```bash
git add cleo/web/routes/contacts.py
git commit -m "feat(contacts): read canonical address key from party_fingerprints in mailing-tag block"
```

---

### Task 8: Run Layer 2 against the production DB

**Files:** none modified — operator step.

- [ ] **Step 1: Run the Layer 2 builder**

Run: `python -m cleo.discovery_v2`
Expected: ~5–10 minutes. Tail output for errors.

If the orchestrator guard (Task 6 Step 6) fires, return to Task 5 and run the compiler first.

- [ ] **Step 2: Spot-check `address_unit_summary` row counts**

Run:

```bash
sqlite3 data/cleo.db <<'SQL'
SELECT COUNT(*) FROM address_unit_summary;
SELECT * FROM address_unit_summary
WHERE city='toronto' AND street_number='30' AND street_name='st clair'
ORDER BY n_party_sides DESC LIMIT 10;
SQL
```

Expected: total count is materially LOWER than before (deduplication has happened). The 30 St Clair rows should show concentrated party-side counts under fewer suite_type+suite_number combinations.

- [ ] **Step 3: No commit needed.**

---

### Task 9: API canonicalization shim — explorer URL parsers

**Files:**
- Modify: `cleo/web/routes/explorer.py:1427-1508` (`address_unit_detail`, `address_unit_timeline`)

External links to noisy 7-tuple keys must continue to resolve.

- [ ] **Step 1: Add a helper near the other URL helpers**

Find a location near the existing `_parse_address_root_key` and `_parse_address_root2_key` helpers in `cleo/web/routes/explorer.py` (around line 1293-1301). Add a new helper just below them:

```python
def _canonicalize_unit_key(key: str) -> str:
    """Coerce an external 7-tuple URL into the canonical column form.

    Old links carry noisy values like 'scarborough|2555|eglinton|avenue|east|unit|0212'.
    Migration 019 stores 'toronto|2555|eglinton|avenue|east|suite|212'. To preserve
    external link compatibility, route every incoming key through canonicalize_address
    before lookup. Already-canonical keys are idempotent.
    """
    parts = key.split('|', 6)
    if len(parts) != 7:
        return key  # let the caller raise the 400 for malformed input
    from cleo.resolver.address_canonical import canonicalize_address
    city, snum, sname, suf, dir_, stype, snumber = parts
    return canonicalize_address(city, snum, sname, suf, dir_, stype, snumber)
```

- [ ] **Step 2: Apply the shim in `address_unit_detail`**

Edit `cleo/web/routes/explorer.py:1427-1449`:

```python
@router.get("/addresses/units/{key}")
def address_unit_detail(
    key: str, db=Depends(get_db), user=Depends(get_current_user),
):
    """Unit detail. Key format: 'city|num|name|suffix|direction|suite_type|suite_number'.
    External (legacy) keys are canonicalized on read so old links resolve."""
    key = _canonicalize_unit_key(key)
    parts = key.split('|', 6)
    if len(parts) != 7:
        raise HTTPException(status_code=400, detail=f'Invalid unit key: {key!r}')
    city, snum, sname, suf, dir_, stype, snumber = parts

    summary = db.execute(
        """SELECT city, street_number, street_name, street_suffix, street_direction,
                  suite_type, suite_number, n_party_sides, n_distinct_brand_stems,
                  dominant_stem, dominance_share
           FROM address_unit_summary
           WHERE city = ? AND street_number = ? AND street_name = ?
             AND street_suffix = ? AND street_direction = ?
             AND suite_type = ? AND suite_number = ?""",
        (city, snum, sname, suf, dir_, stype, snumber),
    ).fetchone()
    if summary is None:
        raise HTTPException(status_code=404, detail=f'Unknown unit: {key!r}')
    return dict(summary)
```

- [ ] **Step 3: Apply the shim and column swap in `address_unit_timeline`**

Edit `cleo/web/routes/explorer.py:1452-1508`:

```python
@router.get("/addresses/units/{key}/timeline")
def address_unit_timeline(
    key: str, db=Depends(get_db), user=Depends(get_current_user),
):
    """Chronological events for an address_unit anchor + tenure windows.

    Key format: 'city|num|name|suffix|direction|suite_type|suite_number' (7 fields).
    Legacy keys are canonicalized on read.
    """
    key = _canonicalize_unit_key(key)
    parts = key.split('|', 6)
    if len(parts) != 7:
        raise HTTPException(status_code=400, detail=f'Invalid unit key: {key!r}')

    exists = db.execute(
        "SELECT 1 FROM party_fingerprints pf "
        "WHERE pf.party_address_canonical = ? LIMIT 1",
        (key,),
    ).fetchone()
    if exists is None:
        raise HTTPException(status_code=404, detail=f'Unknown unit: {key!r}')

    events = [dict(r) for r in db.execute(
        """SELECT pf.sale_date, pf.source_id, pf.side,
                  (SELECT pa.atom_value FROM party_atoms pa
                    WHERE pa.source_id = pf.source_id AND pa.side = pf.side
                      AND pa.atom_type = 'brand_phrase'
                    ORDER BY pa.id ASC LIMIT 1) AS party_phrase,
                  agm.auto_group_id
           FROM party_fingerprints pf
           LEFT JOIN auto_group_members agm
             ON agm.source_id = pf.source_id AND agm.side = pf.side
            AND agm.member_type = 'party_side'
           WHERE pf.party_address_canonical = ?
             AND pf.sale_date IS NOT NULL AND pf.sale_date != ''
           ORDER BY pf.sale_date ASC, pf.source_id ASC, pf.side ASC""",
        (key,),
    )]

    tenures = [dict(r) for r in db.execute(
        """SELECT agt.auto_group_id, ag.canonical_stem,
                  agt.start_date, agt.end_date,
                  agt.n_party_sides_in_window,
                  agt.dominance_share_in_window,
                  agt.score,
                  CASE WHEN agt.end_date >= date('now', '-365 days') THEN 1 ELSE 0 END AS is_active
           FROM auto_group_anchor_tenures agt
           JOIN auto_groups ag ON ag.auto_group_id = agt.auto_group_id
           WHERE agt.anchor_type = 'address_unit' AND agt.anchor_value = ?
           ORDER BY agt.start_date ASC""",
        (key,),
    )]

    return {'value': key, 'anchor_type': 'address_unit', 'events': events, 'tenures': tenures}
```

- [ ] **Step 4: Add a route test that exercises the shim**

Add to `tests/test_routes_explorer.py` (or create a focused new test file `tests/test_routes_explorer_canonical.py` if the existing test file is large and you don't want to touch it):

```python
def test_address_unit_detail_canonicalizes_legacy_key(client):
    """A legacy URL with the noisy city+suite_type still resolves to the
    canonical row in address_unit_summary."""
    # The `client` fixture in tests/test_routes_explorer.py wraps a
    # _seeded_db() that you'll extend (in this same task) to include a
    # canonical row in address_unit_summary keyed
    # 'toronto|2555|eglinton|avenue|east|suite|212'. The URL below uses
    # the legacy noisy form ('scarborough' + 'unit'); the shim must
    # canonicalize before lookup.
    response = client.get(
        "/api/explorer/addresses/units/scarborough|2555|eglinton|avenue|east|unit|212"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["city"] == "toronto"
    assert data["suite_type"] == "suite"
```

Update `_seeded_db` in `tests/test_routes_explorer.py` to insert one canonical row in `address_unit_summary`:

```python
    conn.execute(
        """INSERT INTO address_unit_summary
            (city, street_number, street_name, street_suffix, street_direction,
             suite_type, suite_number, n_party_sides, n_distinct_brand_stems,
             dominant_stem, dominance_share)
           VALUES ('toronto','2555','eglinton','avenue','east','suite','212',
                   3, 1, 'dh management', 1.0)""",
    )
```

- [ ] **Step 5: Run the test**

Run: `pytest tests/test_routes_explorer_canonical.py -v` (or the file you edited).
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add cleo/web/routes/explorer.py tests/test_routes_explorer*.py
git commit -m "feat(api): canonicalize address_unit URL keys on read"
```

---

### Task 10: Frontend mailing-addresses card — surface suite + city

**Files:**
- Modify: `frontend/src/pages/ContactDetailPage.tsx:212-234`

The current rendering strips both the city (slice index 0) and the suite info (indices 5-6). With canonical keys, fewer rows show — and the user must see the suite info to tell `212` from `222` and the city to confirm the canonical fold.

- [ ] **Step 1: Replace the rendering block**

Edit `frontend/src/pages/ContactDetailPage.tsx:212-234`. Replace the inline `<span>{a.address_unit.split("|").slice(1, 5).filter(Boolean).join(" ")}</span>` with a small helper:

```tsx
              {contact.address_tenure_tags && contact.address_tenure_tags.length > 0 && (
                <div>
                  <Text size="1" style={{ color: "var(--gray-9)" }}>Mailing Addresses</Text>
                  <div className="flex flex-col gap-1.5 mt-1">
                    {contact.address_tenure_tags.map((a, i) => (
                      <div key={i} className="flex items-center justify-between gap-2 text-[13px]">
                        <span>{formatCanonicalAddress(a.address_unit)}</span>
                        {a.tag && (
                          <Badge
                            size="1"
                            color={a.tag.state === "active" ? "jade" : "gray"}
                            variant="soft"
                          >
                            {a.tag.state === "active"
                              ? `Active · ${a.tag.display_name}`
                              : `Last seen ${a.last_seen.slice(0, 10)}`}
                          </Badge>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
```

Add the helper near the top of the file (or co-locate with other formatters in the same file — match the existing style):

```tsx
function formatCanonicalAddress(canonical: string): string {
  // canonical = city|street_number|street_name|street_suffix|street_direction|suite_type|suite_number
  const parts = canonical.split("|");
  if (parts.length !== 7) return canonical;
  const [city, num, name, suf, dir_, stype, snum] = parts;
  const street = [num, name, suf, dir_].filter(Boolean).join(" ");
  const suite = snum ? `${stype === "po_box" ? "PO Box" : titleCase(stype)} ${snum}` : "";
  const cityPart = city ? titleCase(city) : "";
  return [street, suite, cityPart].filter(Boolean).join(", ");
}

function titleCase(s: string): string {
  return s.replace(/\b\w/g, (c) => c.toUpperCase());
}
```

(If the file already has a `titleCase` helper or imports one from `lib/utils.ts`, reuse it instead of redefining.)

- [ ] **Step 2: Type-check the frontend**

Run: `cd frontend && npx tsc`
Expected: no errors.

- [ ] **Step 3: Visually verify on the running dev server**

The user does not run dev servers — Claude does. If a dev server is not already running:

Run: `uvicorn cleo.web.app:app --reload --port 8099 &` then `cd frontend && npm run dev`

Visit `http://localhost:5174/contacts/CON_03868` (Dan Hagler). Expected: the Mailing Addresses card shows ≤ 2 rows. Each renders as `<street>, Suite <number>, <City>` (e.g., `2555 Eglinton Avenue East, Suite 212, Toronto`).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/ContactDetailPage.tsx
git commit -m "feat(contacts): render canonical address with suite + city in mailing card"
```

---

### Task 11: Verification gate

**Files:** none — manual verification.

This is the acceptance gate. All four checks must pass before merging.

- [ ] **Step 1: Dan Hagler's mailing addresses (4 → 2 expected)**

Run:

```bash
sqlite3 data/cleo.db <<'SQL'
SELECT party_address_canonical, COUNT(*) AS n_sides,
       MIN(sale_date) AS first_seen, MAX(sale_date) AS last_seen
FROM party_fingerprints
WHERE contact_fingerprint = 'dan hagler'
  AND street_number = '2555' AND street_name = 'eglinton'
GROUP BY party_address_canonical
ORDER BY n_sides DESC;
SQL
```

Expected: ≤ 2 rows. Both keys start with `toronto|2555|eglinton|avenue|east|suite|`. Suite numbers are `212` and `222` (or just `212` if `222` doesn't exist on this contact).

Visit `http://localhost:5174/contacts/CON_03868`. The Mailing Addresses card renders ≤ 2 rows.

- [ ] **Step 2: Paul Braun's tenures unchanged**

Run:

```bash
sqlite3 data/cleo.db <<'SQL'
SELECT brand_stem, strict_start_date, strict_end_date,
       inferred_start_date, inferred_end_date,
       n_party_sides_strict, n_party_sides_inferred,
       dominant_address_unit, is_active
FROM contact_brand_tenures cbt
WHERE contact_fingerprint = 'paul braun'
ORDER BY n_party_sides_inferred DESC;
SQL
```

Expected: tenure rows for `canfirst` and any other Braun stems are present, with the same n_party_sides values as before (his addresses were already canonical, so canonicalization is a no-op for him). `dominant_address_unit` for the canfirst tenure should be `toronto|30|st clair|...`.

Visit `http://localhost:5174/contacts/<paul-braun-id>` and confirm Career History tile is unchanged.

- [ ] **Step 3: 30 St Clair dominant-stem signal climb**

Run:

```bash
sqlite3 data/cleo.db <<'SQL'
SELECT suite_type, suite_number,
       n_party_sides, n_distinct_brand_stems,
       dominant_stem, dominance_share
FROM address_unit_summary
WHERE city='toronto' AND street_number='30' AND street_name='st clair'
ORDER BY n_party_sides DESC LIMIT 10;
SQL
```

Expected: rows for 30 St Clair are concentrated under canonical suite_type='suite' (no `unit`, no empty type). The dominant_stem for the highest-volume row should be `canfirst` with a higher `dominance_share` than before (the share denominator no longer split across `unit|300`, `suite|300`, etc.).

- [ ] **Step 4: End-to-end live API hit**

With backend running on 8099:

```bash
# Old noisy URL — should resolve via the shim
curl -s "http://localhost:8099/api/explorer/addresses/units/scarborough|2555|eglinton|avenue|east|unit|212" \
  -H "Authorization: Bearer <jwt>" | jq .city
# Expected: "toronto"

# Canonical URL — should work directly
curl -s "http://localhost:8099/api/explorer/addresses/units/toronto|2555|eglinton|avenue|east|suite|212" \
  -H "Authorization: Bearer <jwt>" | jq .city
# Expected: "toronto"
```

(Replace `<jwt>` with a valid token from localStorage — the user does not run curl; Claude runs this verification.)

- [ ] **Step 5: Run the full test suite once more**

Run: `pytest tests/ -v`
Expected: PASS.

Run: `cd frontend && npx tsc`
Expected: no errors.

- [ ] **Step 6: Final commit (only if Steps 1–5 produced any incidental fixes)**

If no further changes, no commit. If you made small fixes during verification:

```bash
git add <files>
git commit -m "fix: address canonicalization verification follow-ups"
```

---

## Self-review checklist (run before requesting review)

- [ ] Migration 019 applied and `party_fingerprints` has both new columns + indexes.
- [ ] `cleo/resolver/resources/` contains all three JSON files (verbatim from spec).
- [ ] `cleo/resolver/address_canonical.py` passes `tests/test_address_canonical.py` (every spec rule covered).
- [ ] `cleo/atoms/fingerprint.py` writes both new columns. The redundant in-function CREATE TABLE block is also updated.
- [ ] Compiler rerun completed; canonical columns populated for all party_fingerprints rows.
- [ ] Layer 2 builders (`timelines`, `expansion`, `contact_brand_tenures`, `brand_index.build_address_unit_summary`) read `party_address_canonical`.
- [ ] `auto_groups.build_auto_groups` guard refuses to run if canonical column is empty.
- [ ] Layer 2 rerun completed; `address_unit_summary` row count is materially LOWER than pre-migration.
- [ ] Contacts route mailing-addresses block uses `party_address_canonical`.
- [ ] Explorer URL handlers run external 7-tuple URLs through `_canonicalize_unit_key` before lookup.
- [ ] Frontend Mailing Addresses card surfaces suite + city in the rendered string.
- [ ] Dan Hagler's 4 rows collapsed to ≤ 2 (verified end-to-end).
- [ ] Paul Braun's tenures unchanged.
- [ ] 30 St Clair dominant_stem `canfirst` shows higher `dominance_share` than pre-migration.
- [ ] All Python tests pass (`pytest tests/`).
- [ ] Frontend type-checks (`cd frontend && npx tsc`).

---

## Open risks (flagged for the user)

1. **Compiler rerun duration.** The compiler rerun in Task 5 is 20–30 minutes on production data. During that time, `party_fingerprints.party_address_canonical` is partially populated (the fingerprint pass DROPs and recreates the table — see `fingerprint.py:62-65`). Any service hitting the DB during this window may see the table empty. The user already runs the compiler regularly; this is expected operator behaviour, but worth noting.
2. **Layer 2 lockout window.** Between the migration applying (Task 1) and the compiler completing (Task 5), Layer 2 builds against the production DB will fail loudly via the new orchestrator guard. This is intentional (better than silent regression) but means we should run the compiler immediately after the migration, in a single block.
3. **Test fixture migration.** Some `tests/test_discovery_v2_*.py` files seed `party_fingerprints` directly with INSERT statements that don't include `party_address_canonical`. After Task 4, those tests may fail with NULL canonical keys flowing through to assertions (e.g., `address_unit_summary` will skip those rows). Task 6 Step 7 calls this out, but the implementer needs to update fixtures to seed the new column with the equivalent canonical key. There may be 5-10 fixtures total.
4. **The `_address_unit_key` legacy helper in `contact_brand_tenures.py`.** Keeping it as a no-longer-called function is a small smell. If a future maintainer reads the module and expects symmetry with the SELECT, they may try to "fix" the inconsistency. The comment added in Task 6 Step 4 mitigates this, but a follow-up cleanup PR (out of scope) could just delete it.
5. **Suite_number edge cases.** The current rule strips leading zeros only when the value is purely numeric (or matches the `digits + letters` regex). A value like `00ph` would NOT have its zeros stripped (because it's not pure digits and doesn't match the regex). This matches the spec ("strip leading zeros + uppercase letter suffix"), but if the corpus contains exotic values like `00PH`, those won't dedupe with `0PH` or `PH`. Inspect the data after the rerun if dedupe rates look low; if there are unanticipated patterns, the fix is in `address_canonical.py`, not here.
6. **`fingerprint.py` runs after the compiler rebuild — it is the only writer.** The watcher path (`engines/gw/watcher.py` does incremental DB updates per CLAUDE.md) does NOT call `run_fingerprint_pass`. So GW-only updates won't refresh the canonical columns until the next full compiler run. This is consistent with current behavior (the watcher doesn't refresh other derived tables either), but worth flagging if a user reports "I added GW data and the canonical column is empty for the new rows."
7. **Property_canonical_id only joins via transactions.source_id.** A party-side that exists without a transactions row (shouldn't happen given the JOIN, but defensively) gets NULL. This matches expected behavior — the JOIN already filters those out.
