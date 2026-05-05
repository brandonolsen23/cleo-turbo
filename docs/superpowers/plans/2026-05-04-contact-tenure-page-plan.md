# Contact Tenure Page Implementation Plan (V1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-05-04-contact-tenure-page-design.md`

**Goal:** Replace the Contact detail page's broken "current group" attribution with a brand-stem tenure model derived from `party_atoms`. Add a `contact_brand_tenures` derived table, surface it through the API, and redesign the Contact page around Career History + tenure-aware Contact Info + a Group Portfolio Footprint hero map.

**Architecture:** A new derived table (`contact_brand_tenures`) is built by a new module `cleo/discovery_v2/contact_brand_tenures.py`, slotted into the existing Layer 2 orchestrator (`build_auto_groups`) so it rebuilds on the same cadence (`python -m cleo.discovery_v2`). The builder filters `party_atoms` to `atom_type='brand_phrase' AND source_field IN ('trade_name','care_of','companies_json')`, joins to `party_fingerprints` and `brand_stem_phrase_map`, computes strict + anchor-bracketed inferred windows, applies a `≥ 2 party-sides` threshold, and stores `dominant_address_unit` on the row. Phone/address tenure tags are computed at the API layer (not materialized) since they read directly from `party_fingerprints`. The Contact page consumes new fields on `/api/contacts/:id`, plus three new endpoints: `/api/contacts/:id/tenures/:stem` (tenure detail drawer), `/api/companies/:stem/portfolio-footprint` (hero map), and `/api/contacts/:id/property-footprint-tenured` (color-coded pin map).

**Tech Stack:** Python 3.12, FastAPI, SQLite, React 19 + Vite + TypeScript + Radix UI Themes (jade/slate), Tailwind, Mapbox GL via `react-map-gl`, Phosphor icons. Existing patterns per `CLAUDE.md`.

**Migration:** 018 (next number after 017_tenure_tables).

---

## Glossary (locked from spec — used strictly)

| Term | Meaning |
|---|---|
| **Contact** | A person, identified by `contact_fingerprint` (e.g., `paul braun`) on `party_fingerprints` and by `CON_NNNNN` on the `contacts` table. The two key columns are 1:1 via `contacts.name_fingerprint`. |
| **Brand stem** | The canonical management-company brand string (`canfirst`, `dundee`, `riocan`) from `brand_stem_phrase_map.stem`. The prospecting unit for the new tenure model. |
| **Qualifying party-side** | A row in `party_atoms` with `atom_type='brand_phrase' AND source_field IN ('trade_name','care_of','companies_json')`. **`party_name` is intentionally excluded** — that field carries SPV names, not management-company brands (per CLAUDE.md "branded identifier lives in four fields" rule). |
| **Tenure** | One row in `contact_brand_tenures`. Keyed by `(contact_fingerprint, brand_stem)`. Survives only if `n_party_sides_strict >= 2`. |
| **Strict window** | `(strict_start_date, strict_end_date)` — MIN/MAX `sale_date` of party-sides whose qualifying brand_phrase carries this stem. |
| **Inferred window** | `(inferred_start_date, inferred_end_date)` — strict window extended via the contact's appearances at `dominant_address_unit` even when those party-sides carry only an SPV brand_phrase. |
| **`dominant_address_unit`** | The `address_unit` (city + street_number + street_name + street_suffix + street_direction + suite_type + suite_number, pipe-joined) that appears on the most party-sides for this `(contact, stem)` pair within the strict window. |
| **`is_active`** | A tenure flag: `1` iff `inferred_end_date >= today - 730 days`. Two-year recency cliff. |
| **`current_employer`** | A per-contact derivation (not stored): LinkedIn-imported current company if present, else the realtrack tenure with `is_active=1` and the highest `n_party_sides_inferred`. |
| **Phone-tenure tag / address-tenure tag** | The label rendered next to a phone or address on the Contact Info card. Computed on demand at the API layer from `party_fingerprints` overlap with tenure windows. |

Do not invent alternate names. If you need a new concept, surface it as a question rather than shipping a new term.

---

## Resolved open questions

The spec deferred three implementation questions to this plan. They are resolved here:

1. **Rebuild cadence.** `contact_brand_tenures` is rebuilt in the existing Layer 2 orchestrator `cleo/discovery_v2/auto_groups.py:build_auto_groups`, slotted **after** `build_contact_tenures` (so the soft `auto_group_id` corroboration link can read freshly populated `auto_groups.canonical_stem`). Idempotent DELETE-then-INSERT, same as `build_contact_tenures`. Triggered by `python -m cleo.discovery_v2`. No new cron, no on-demand compute.
2. **`dominant_address_unit` storage.** Stored on the tenure row. The inferred window expansion (Step 2b in spec) **requires** the address_unit value at compute time to even derive `inferred_start_date`, `inferred_end_date`, and `n_party_sides_inferred`. Recomputing at render time would mean re-running the entire derivation chain on every page load. Tenure rows are small (~10–100 rows per active contact), and the address_unit is a deterministic fixed string.
3. **Tenure Detail drawer API.** Single endpoint `GET /api/contacts/:id/tenures/:stem` returning everything the drawer renders (top phrases, source-field breakdown, strict/inferred dates, linked auto_group_id, credited transactions list). Rationale: the drawer opens once and renders all sections at the same time. Splitting into `/why`, `/window`, `/transactions` would mean three round-trips for one user action. The credited-transactions list is the largest payload but is ~60 rows for Paul × CanFirst — well within a single response.

---

## File Structure

**Backend (new):**
- `cleo/database/migrations/018_contact_brand_tenures.py` — schema for `contact_brand_tenures`.
- `cleo/discovery_v2/contact_brand_tenures.py` — builder module.
- `cleo/web/routes/contact_tenures.py` — three new endpoints (tenure detail drawer, group portfolio footprint, color-coded property footprint). **Decision:** new file rather than adding to `cleo/web/routes/contacts.py` because two of the three endpoints are not contact-scoped (`/companies/:stem/...`); putting them all in one file co-locates the tenure surface. The new file is registered under multiple prefixes via `app.include_router` (no path collision because each endpoint declares its own absolute path inside the router).
- `tests/test_discovery_v2_contact_brand_tenures.py` — builder unit tests.
- `tests/test_routes_contact_tenures.py` — route tests.
- `tests/test_migration_018_contact_brand_tenures.py` — migration smoke test.

**Backend (modified):**
- `cleo/discovery_v2/auto_groups.py` — add `build_contact_brand_tenures(conn)` to `build_auto_groups` orchestrator after `build_contact_tenures`.
- `cleo/web/routes/contacts.py:contact_detail` (line 194 in current file) — extend response with `career_history`, `current_employer`, `phone_tenure_tag`, `address_tenure_tag`, and a new `transactions[].tenure` per-row attribution.
- `cleo/web/app.py` — register the new router.

**Frontend (new):**
- `frontend/src/components/contact/CareerHistoryTile.tsx` — replaces both "Group" card and "Affiliated Groups (63)" panel.
- `frontend/src/components/contact/TenureDetailDrawer.tsx` — side drawer for "Why we named this tenure".
- `frontend/src/components/contact/CurrentEmployerPill.tsx` — header pill (LinkedIn-confirmed / Realtrack-derived / divergence states).
- `frontend/src/components/contact/PortfolioFootprintMap.tsx` — hero map showing the current employer's full portfolio.
- `frontend/src/components/contact/TenuredPropertyFootprintMap.tsx` — Paul's pins, color-coded by tenure.

**Frontend (modified):**
- `frontend/src/pages/ContactDetailPage.tsx` — restructure right column hero, add header pill, replace Group + Affiliated Groups cards with CareerHistoryTile, add tenure tags to Contact Info phone/address rows, add `Tenure` column to Transaction History table, mount the drawer.
- `frontend/src/types/index.ts` — add types for tenures, career-history rows, portfolio-footprint response, and the drawer payload. Extend `ContactDetail` with new fields.

**Frontend (deleted):**
- None. The old "Affiliated Groups" panel in `ContactDetailPage.tsx` (lines 248–281) is removed inline; no separate component to delete.

---

## Pre-flight context for the implementer

**Where qualifying brand_phrases live in `party_atoms`.** Run `sqlite3 data/cleo.db "SELECT atom_value, source_field, COUNT(*) FROM party_atoms WHERE atom_type='brand_phrase' AND source_field IN ('trade_name','care_of','companies_json') GROUP BY 1,2 ORDER BY 3 DESC LIMIT 20"` to see the shape of the input. Roughly 75K rows total across the whole table.

**`brand_stem_phrase_map` is a static lookup, not a derived table.** It maps phrase → stem (e.g., `canfirst capital management → canfirst`). Phrases not in the map fall back to the first non-stopword `brand_token` of the phrase via existing `cleo/atoms/normalize.py`. The fallback is rarely needed for qualifying source fields because the phrase map covers most management-company names.

**`address_unit` key.** Pipe-joined string `city|street_number|street_name|street_suffix|street_direction|suite_type|suite_number`. This matches `address_unit_summary`'s primary key columns. Build the key string deterministically — empty components stay as empty strings, never NULL.

**Compiler relationship.** `contacts.id` (`CON_NNNNN`) joins to `contact_fingerprint` via `contacts.name_fingerprint`. The new endpoints accept `CON_NNNNN`-style IDs (matching existing `/api/contacts/:id`) and resolve the fingerprint internally before reading `contact_brand_tenures`.

**Stable IDs are NOT in scope.** No new `STEM_NNNNN`-style ID. The brand_stem string itself (`canfirst`) is the URL slug and the foreign key. URL-encode it for safety.

**Auto-groups soft link.** `contact_brand_tenures.auto_group_id` is populated by a single bulk UPDATE at the end of the builder: `UPDATE contact_brand_tenures SET auto_group_id = (SELECT auto_group_id FROM auto_groups WHERE canonical_stem = contact_brand_tenures.brand_stem ORDER BY n_members DESC LIMIT 1)`. NULL when no auto_group has matching canonical_stem (the spec's expected case for stems without an auto_group). When multiple auto_groups share a canonical_stem (rare), pick the highest-membership one — deterministic and matches user's "drill into the biggest cluster" intent.

**Phone/address tenure tags are computed in `contact_detail`.** Not stored. The query reads `party_fingerprints` for this contact's first_seen / last_seen of each phone and address, then overlaps against `contact_brand_tenures` rows for the same contact. Two-year cliff (`last_seen >= date('now','-730 days')`) marks active phones/addresses. The phone in `contacts.phone` may not even be in `party_fingerprints` (it's editable via `contact_field_overrides`); when it isn't, the tag is omitted.

**Test fixture.** `tests/test_routes_explorer.py` has a reusable `_seeded_db()` pattern. The new `test_routes_contact_tenures.py` should follow the same pattern but seed a contact + party-sides + tenure rows directly. Use the same `client` fixture pattern with `app.dependency_overrides`.

**Migration runner.** Migrations are run by `python3 -m cleo.database.migrations.018_contact_brand_tenures` (each migration file has its own `__main__` block — see migration 017 as the template). There is no central migration runner in this repo.

**Mapbox.** The existing `PropertyMiniMap` component handles the rendering. New maps reuse this component and pass color-coded `properties[].pin_color` per pin where supported, else a wrapper component handles legend rendering. See `frontend/src/components/ui/PropertyMiniMap.tsx` for the existing prop shape.

**Forward compatibility for V2 (Group page).** Out of scope for this plan. The schema and endpoints are designed so that reading `contact_brand_tenures` grouped by `brand_stem` (instead of by `contact_fingerprint`) populates the V2 Workforce tile without schema changes. Do **not** build the V2 endpoints in V1 — they're explicitly deferred.

---

## Tasks

### Task 1: Migration 018 — `contact_brand_tenures` schema

**Files:**
- Create: `cleo/database/migrations/018_contact_brand_tenures.py`
- Create: `tests/test_migration_018_contact_brand_tenures.py`

- [ ] **Step 1: Write the migration smoke test**

Create `tests/test_migration_018_contact_brand_tenures.py`:

```python
"""Tests for migration 018: contact_brand_tenures table."""
import sqlite3


def test_migration_creates_table_and_indexes():
    from cleo.database.migrations import (
        __init__ as _init,  # noqa: F401  (ensure package importable)
    )
    import importlib
    mod = importlib.import_module("cleo.database.migrations.018_contact_brand_tenures")

    conn = sqlite3.connect(":memory:")
    mod.migrate(conn)

    # Table exists with expected columns
    cols = {r[1] for r in conn.execute("PRAGMA table_info(contact_brand_tenures)").fetchall()}
    expected = {
        "id", "contact_fingerprint", "brand_stem",
        "strict_start_date", "strict_end_date",
        "inferred_start_date", "inferred_end_date",
        "n_party_sides_strict", "n_party_sides_inferred",
        "top_phrases_json", "source_field_breakdown_json",
        "dominant_address_unit", "auto_group_id", "is_active",
        "discovered_at",
    }
    assert expected <= cols, f"Missing columns: {expected - cols}"

    # Indexes exist
    idx = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='contact_brand_tenures'"
    )}
    assert "idx_cbt_contact" in idx
    assert "idx_cbt_stem" in idx
    conn.close()


def test_migration_idempotent():
    """Running the migration twice doesn't error."""
    import importlib
    mod = importlib.import_module("cleo.database.migrations.018_contact_brand_tenures")

    conn = sqlite3.connect(":memory:")
    mod.migrate(conn)
    mod.migrate(conn)  # second run uses CREATE TABLE IF NOT EXISTS
    conn.close()
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python3 -m pytest tests/test_migration_018_contact_brand_tenures.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'cleo.database.migrations.018_contact_brand_tenures'`.

- [ ] **Step 3: Write the migration**

Create `cleo/database/migrations/018_contact_brand_tenures.py`:

```python
"""
Migration 018: contact_brand_tenures derived table.

Adds a per-(contact, brand_stem) tenure table sourced from party_atoms
brand_phrase rows in the `trade_name`, `care_of`, and `companies_json`
source fields. Replaces auto_contact_tenures as the source of truth for
"where a contact worked, when" on the Contact detail page.

Idempotent: rebuilt on every Layer 2 run via build_contact_brand_tenures.
"""
from __future__ import annotations
import os
import sqlite3


def migrate(conn: sqlite3.Connection) -> None:
    print("Migration 018: contact_brand_tenures table...")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS contact_brand_tenures (
            id                          INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_fingerprint         TEXT NOT NULL,
            brand_stem                  TEXT NOT NULL,
            strict_start_date           TEXT NOT NULL,
            strict_end_date             TEXT NOT NULL,
            inferred_start_date         TEXT NOT NULL,
            inferred_end_date           TEXT NOT NULL,
            n_party_sides_strict        INTEGER NOT NULL,
            n_party_sides_inferred      INTEGER NOT NULL,
            top_phrases_json            TEXT NOT NULL,
            source_field_breakdown_json TEXT NOT NULL,
            dominant_address_unit       TEXT,
            auto_group_id               TEXT,
            is_active                   INTEGER NOT NULL,
            discovered_at               TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_cbt_contact
            ON contact_brand_tenures(contact_fingerprint);
        CREATE INDEX IF NOT EXISTS idx_cbt_stem
            ON contact_brand_tenures(brand_stem);
        CREATE INDEX IF NOT EXISTS idx_cbt_active
            ON contact_brand_tenures(is_active, brand_stem);
    """)
    conn.commit()
    print("Migration 018 complete.")


if __name__ == "__main__":
    db_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "cleo.db")
    conn = sqlite3.connect(db_path)
    migrate(conn)
    conn.close()
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
python3 -m pytest tests/test_migration_018_contact_brand_tenures.py -v
```

Expected: PASS.

- [ ] **Step 5: Apply the migration to the real database**

```bash
python3 -m cleo.database.migrations.018_contact_brand_tenures
```

Expected output:
```
Migration 018: contact_brand_tenures table...
Migration 018 complete.
```

Verify:
```bash
sqlite3 data/cleo.db ".schema contact_brand_tenures"
```

Expected: full schema printout matching the migration above.

- [ ] **Step 6: Commit**

```bash
git add cleo/database/migrations/018_contact_brand_tenures.py tests/test_migration_018_contact_brand_tenures.py
git commit -m "$(cat <<'EOF'
feat(db): migration 018 — contact_brand_tenures derived table

Adds per-(contact, brand_stem) tenure table to replace
auto_contact_tenures as the source of truth for the Contact page's
career history. Sourced from party_atoms brand_phrase rows in the
trade_name / care_of / companies_json source fields. Schema only;
builder lands in the next commit.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Builder — strict-window aggregation

**Files:**
- Create: `cleo/discovery_v2/contact_brand_tenures.py`
- Create: `tests/test_discovery_v2_contact_brand_tenures.py`

This task implements only the strict-window aggregation (no inferred expansion yet). Subsequent tasks add the address-bracketed expansion, the `auto_group_id` link, and the `is_active` flag.

- [ ] **Step 1: Write the failing test for strict-window aggregation**

Create `tests/test_discovery_v2_contact_brand_tenures.py`:

```python
"""Tests for the contact_brand_tenures builder."""
import json
import sqlite3
import pytest


def _make_db():
    """In-memory DB seeded with the schema this builder reads/writes."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE party_fingerprints (
            source_id           TEXT NOT NULL,
            side                TEXT NOT NULL,
            street_number       TEXT,
            street_name         TEXT,
            street_suffix       TEXT,
            street_direction    TEXT,
            suite_type          TEXT,
            suite_number        TEXT,
            city                TEXT,
            phone               TEXT,
            contact_fingerprint TEXT,
            sale_date           TEXT,
            PRIMARY KEY (source_id, side)
        );
        CREATE TABLE party_atoms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT NOT NULL, side TEXT NOT NULL,
            atom_type TEXT NOT NULL, atom_value TEXT NOT NULL,
            source_field TEXT NOT NULL
        );
        CREATE TABLE brand_stem_phrase_map (
            phrase TEXT PRIMARY KEY,
            stem TEXT NOT NULL,
            confidence REAL NOT NULL
        );
        CREATE TABLE address_unit_summary (
            city TEXT NOT NULL,
            street_number TEXT NOT NULL,
            street_name TEXT NOT NULL,
            street_suffix TEXT NOT NULL DEFAULT '',
            street_direction TEXT NOT NULL DEFAULT '',
            suite_type TEXT NOT NULL DEFAULT '',
            suite_number TEXT NOT NULL DEFAULT '',
            n_party_sides INTEGER NOT NULL,
            n_distinct_brand_stems INTEGER NOT NULL,
            dominant_stem TEXT,
            dominance_share REAL,
            PRIMARY KEY (city, street_number, street_name, street_suffix,
                         street_direction, suite_type, suite_number)
        );
        CREATE TABLE auto_groups (
            auto_group_id  TEXT PRIMARY KEY,
            canonical_stem TEXT NOT NULL,
            display_name   TEXT NOT NULL,
            tier           TEXT NOT NULL,
            confidence     REAL NOT NULL,
            n_anchors      INTEGER NOT NULL,
            n_members      INTEGER NOT NULL
        );
        CREATE TABLE contact_brand_tenures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_fingerprint TEXT NOT NULL,
            brand_stem TEXT NOT NULL,
            strict_start_date TEXT NOT NULL,
            strict_end_date TEXT NOT NULL,
            inferred_start_date TEXT NOT NULL,
            inferred_end_date TEXT NOT NULL,
            n_party_sides_strict INTEGER NOT NULL,
            n_party_sides_inferred INTEGER NOT NULL,
            top_phrases_json TEXT NOT NULL,
            source_field_breakdown_json TEXT NOT NULL,
            dominant_address_unit TEXT,
            auto_group_id TEXT,
            is_active INTEGER NOT NULL,
            discovered_at TEXT DEFAULT (datetime('now'))
        );
        INSERT INTO brand_stem_phrase_map (phrase, stem, confidence) VALUES
            ('canfirst capital management', 'canfirst', 0.95),
            ('canfirst capital', 'canfirst', 0.90),
            ('dundee realty', 'dundee', 0.95);
    """)
    return conn


def _add_party(conn, source_id, side, contact_fp, sale_date,
               city="toronto", street_number="30", street_name="st clair",
               street_suffix="ave", street_direction="w",
               suite_type="", suite_number=""):
    conn.execute(
        "INSERT INTO party_fingerprints "
        "(source_id, side, contact_fingerprint, sale_date, "
        " city, street_number, street_name, street_suffix, street_direction, "
        " suite_type, suite_number) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (source_id, side, contact_fp, sale_date, city,
         street_number, street_name, street_suffix, street_direction,
         suite_type, suite_number),
    )


def _add_brand_phrase(conn, source_id, side, phrase, source_field):
    conn.execute(
        "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
        "VALUES (?, ?, 'brand_phrase', ?, ?)",
        (source_id, side, phrase, source_field),
    )


def test_strict_window_basic_aggregation():
    """Two qualifying party-sides for canfirst → one tenure row, MIN/MAX dates."""
    from cleo.discovery_v2.contact_brand_tenures import build_contact_brand_tenures

    conn = _make_db()
    _add_party(conn, "RT1", "buyer", "paul braun", "2004-07-02")
    _add_brand_phrase(conn, "RT1", "buyer", "canfirst capital management", "trade_name")
    _add_party(conn, "RT2", "buyer", "paul braun", "2022-12-13")
    _add_brand_phrase(conn, "RT2", "buyer", "canfirst capital management", "trade_name")
    conn.commit()

    build_contact_brand_tenures(conn, today="2026-05-04")

    rows = conn.execute(
        "SELECT contact_fingerprint, brand_stem, strict_start_date, "
        "strict_end_date, n_party_sides_strict "
        "FROM contact_brand_tenures"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["contact_fingerprint"] == "paul braun"
    assert rows[0]["brand_stem"] == "canfirst"
    assert rows[0]["strict_start_date"] == "2004-07-02"
    assert rows[0]["strict_end_date"] == "2022-12-13"
    assert rows[0]["n_party_sides_strict"] == 2


def test_threshold_filters_one_shot_mentions():
    """A single qualifying party-side for a stem is dropped (threshold ≥ 2)."""
    from cleo.discovery_v2.contact_brand_tenures import build_contact_brand_tenures

    conn = _make_db()
    _add_party(conn, "RT1", "buyer", "paul braun", "2004-07-02")
    _add_brand_phrase(conn, "RT1", "buyer", "canfirst capital management", "trade_name")
    # Only ONE side carries dundee — should be filtered.
    _add_party(conn, "RT99", "buyer", "paul braun", "1999-01-27",
               street_number="390", street_name="bay")
    _add_brand_phrase(conn, "RT99", "buyer", "dundee realty", "care_of")
    # Add a second canfirst row so canfirst survives.
    _add_party(conn, "RT2", "buyer", "paul braun", "2022-12-13")
    _add_brand_phrase(conn, "RT2", "buyer", "canfirst capital management", "trade_name")
    conn.commit()

    build_contact_brand_tenures(conn, today="2026-05-04")

    stems = {r["brand_stem"] for r in conn.execute(
        "SELECT brand_stem FROM contact_brand_tenures"
    )}
    assert "canfirst" in stems
    assert "dundee" not in stems  # filtered by threshold


def test_party_name_source_field_excluded():
    """party_name source_field is excluded — SPV names should not produce tenures."""
    from cleo.discovery_v2.contact_brand_tenures import build_contact_brand_tenures

    conn = _make_db()
    # 5 party-sides where the brand_phrase is on party_name (SPV-style)
    for i in range(5):
        _add_party(conn, f"RT{i}", "buyer", "paul braun", f"200{i}-01-01")
        _add_brand_phrase(conn, f"RT{i}", "buyer",
                          "canfirst capital management", "party_name")
    conn.commit()

    build_contact_brand_tenures(conn, today="2026-05-04")

    n = conn.execute("SELECT COUNT(*) FROM contact_brand_tenures").fetchone()[0]
    assert n == 0, "party_name source_field must not yield tenure rows"


def test_top_phrases_and_source_field_breakdown_json():
    """top_phrases_json and source_field_breakdown_json reflect the input mix."""
    from cleo.discovery_v2.contact_brand_tenures import build_contact_brand_tenures

    conn = _make_db()
    # Three trade_name + one care_of + one companies_json — five total.
    for i in range(3):
        _add_party(conn, f"RT_T{i}", "buyer", "paul braun", f"20{10+i}-01-01")
        _add_brand_phrase(conn, f"RT_T{i}", "buyer",
                          "canfirst capital management", "trade_name")
    _add_party(conn, "RT_C", "buyer", "paul braun", "2015-01-01")
    _add_brand_phrase(conn, "RT_C", "buyer", "canfirst capital", "care_of")
    _add_party(conn, "RT_J", "buyer", "paul braun", "2016-01-01")
    _add_brand_phrase(conn, "RT_J", "buyer",
                      "canfirst capital management", "companies_json")
    conn.commit()

    build_contact_brand_tenures(conn, today="2026-05-04")

    row = conn.execute(
        "SELECT top_phrases_json, source_field_breakdown_json "
        "FROM contact_brand_tenures WHERE brand_stem='canfirst'"
    ).fetchone()
    phrases = json.loads(row["top_phrases_json"])
    breakdown = json.loads(row["source_field_breakdown_json"])
    # Top phrase is canfirst capital management, n=4
    assert phrases[0] == {"phrase": "canfirst capital management", "n": 4}
    assert {"phrase": "canfirst capital", "n": 1} in phrases
    assert breakdown == {"trade_name": 3, "care_of": 1, "companies_json": 1}


def test_idempotent_rebuild():
    """Running the builder twice yields the same row count."""
    from cleo.discovery_v2.contact_brand_tenures import build_contact_brand_tenures

    conn = _make_db()
    _add_party(conn, "RT1", "buyer", "paul braun", "2004-07-02")
    _add_brand_phrase(conn, "RT1", "buyer", "canfirst capital management", "trade_name")
    _add_party(conn, "RT2", "buyer", "paul braun", "2022-12-13")
    _add_brand_phrase(conn, "RT2", "buyer", "canfirst capital management", "trade_name")
    conn.commit()

    build_contact_brand_tenures(conn, today="2026-05-04")
    n1 = conn.execute("SELECT COUNT(*) FROM contact_brand_tenures").fetchone()[0]
    build_contact_brand_tenures(conn, today="2026-05-04")
    n2 = conn.execute("SELECT COUNT(*) FROM contact_brand_tenures").fetchone()[0]
    assert n1 == n2 == 1
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python3 -m pytest tests/test_discovery_v2_contact_brand_tenures.py -v
```

Expected: ALL FAIL with `ModuleNotFoundError: No module named 'cleo.discovery_v2.contact_brand_tenures'`.

- [ ] **Step 3: Write the strict-window builder**

Create `cleo/discovery_v2/contact_brand_tenures.py`:

```python
"""Builder for the contact_brand_tenures derived table.

Source-of-truth for "where a contact worked, when". Reads party_atoms
brand_phrase rows from trade_name / care_of / companies_json (party_name
intentionally excluded — SPV names live there), aggregates per
(contact_fingerprint, brand_stem), applies threshold and address-
bracketed window expansion.

Idempotent: deletes all rows on each run, then re-inserts.
"""
from __future__ import annotations
import json
import sqlite3
from collections import defaultdict, Counter

QUALIFYING_SOURCE_FIELDS = ("trade_name", "care_of", "companies_json")
THRESHOLD_PARTY_SIDES = 2
ACTIVE_CLIFF_DAYS = 730  # 2-year recency cliff for is_active


def build_contact_brand_tenures(
    conn: sqlite3.Connection, *, today: str | None = None, verbose: bool = True
) -> dict:
    """Rebuild contact_brand_tenures.

    Args:
        conn: open SQLite connection.
        today: ISO date string used as the "now" reference for is_active.
            Pass an explicit value in tests; production passes None to use
            datetime('now').
        verbose: print progress.

    Returns:
        {'n_tenure_rows': int}.
    """
    conn.execute("DELETE FROM contact_brand_tenures")

    # Step 1 — load qualifying brand-phrase events for every contact.
    # Joins party_atoms → party_fingerprints → brand_stem_phrase_map.
    placeholders = ",".join("?" * len(QUALIFYING_SOURCE_FIELDS))
    rows = conn.execute(
        f"""
        SELECT pf.contact_fingerprint   AS cf,
               m.stem                    AS stem,
               pa.atom_value             AS phrase,
               pa.source_field           AS source_field,
               pf.sale_date              AS sale_date,
               pf.source_id              AS source_id,
               pf.side                   AS side,
               pf.city                   AS city,
               COALESCE(pf.street_number,'')   AS sn,
               COALESCE(pf.street_name,'')     AS st,
               COALESCE(pf.street_suffix,'')   AS sx,
               COALESCE(pf.street_direction,'') AS sd,
               COALESCE(pf.suite_type,'')      AS suite_t,
               COALESCE(pf.suite_number,'')    AS suite_n
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
            "address_unit": _address_unit_key(
                r["city"], r["sn"], r["st"], r["sx"], r["sd"], r["suite_t"], r["suite_n"]
            ),
        })

    # Step 3 — for each pair, decide if it survives the threshold and write.
    inserts: list[tuple] = []
    for (cf, stem), events in by_pair.items():
        # Distinct party-sides count (one per (source_id, side)).
        distinct_sides = {(e["source_id"], e["side"]) for e in events}
        if len(distinct_sides) < THRESHOLD_PARTY_SIDES:
            continue

        # Strict window: MIN/MAX sale_date of these events.
        sale_dates = sorted(e["sale_date"] for e in events)
        strict_start = sale_dates[0]
        strict_end = sale_dates[-1]

        # Phrase + source-field aggregations.
        phrase_counts = Counter(e["phrase"] for e in events)
        sf_counts = Counter(e["source_field"] for e in events)
        top_phrases = [
            {"phrase": p, "n": n}
            for p, n in phrase_counts.most_common()
        ]
        # source_field_breakdown is a dict; emit deterministic key order
        # by sorting alphabetically.
        sf_breakdown = {k: sf_counts[k] for k in sorted(sf_counts)}

        # Inferred window placeholder: in this task the inferred window
        # equals the strict window. Task 3 extends it via dominant address.
        inferred_start = strict_start
        inferred_end = strict_end
        n_strict = len(distinct_sides)
        n_inferred = n_strict

        # is_active placeholder: computed in Task 5 with the today arg.
        # For now, set 0 — Task 5 overwrites this column.
        is_active = 0

        inserts.append((
            cf, stem, strict_start, strict_end,
            inferred_start, inferred_end,
            n_strict, n_inferred,
            json.dumps(top_phrases),
            json.dumps(sf_breakdown),
            None,  # dominant_address_unit — Task 3
            None,  # auto_group_id — Task 4
            is_active,
        ))

    if inserts:
        conn.executemany(
            """INSERT INTO contact_brand_tenures
               (contact_fingerprint, brand_stem,
                strict_start_date, strict_end_date,
                inferred_start_date, inferred_end_date,
                n_party_sides_strict, n_party_sides_inferred,
                top_phrases_json, source_field_breakdown_json,
                dominant_address_unit, auto_group_id, is_active)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            inserts,
        )
    conn.commit()
    if verbose:
        print(f"  contact_brand_tenures: {len(inserts):,} rows.", flush=True)
    return {"n_tenure_rows": len(inserts)}


def _address_unit_key(city, sn, st, sx, sd, suite_t, suite_n) -> str:
    """Build the canonical pipe-joined address_unit string.

    Empty components stay as empty strings (never None) — matches the
    primary-key shape of address_unit_summary.
    """
    return "|".join([
        (city or "").lower(),
        sn or "", (st or "").lower(),
        (sx or "").lower(), (sd or "").lower(),
        (suite_t or "").lower(), suite_n or "",
    ])
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
python3 -m pytest tests/test_discovery_v2_contact_brand_tenures.py -v
```

Expected: ALL PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add cleo/discovery_v2/contact_brand_tenures.py tests/test_discovery_v2_contact_brand_tenures.py
git commit -m "$(cat <<'EOF'
feat(discovery-v2): contact_brand_tenures builder — strict window

Aggregates qualifying brand_phrase party-sides per (contact, stem) and
emits a tenure row with MIN/MAX sale_date, top-phrases JSON, and
source-field breakdown. Threshold ≥ 2 party-sides filters one-shot
noise; party_name source_field excluded so SPV names don't produce
tenures.

Inferred window, dominant_address_unit, auto_group_id link, and
is_active flag are stubbed — populated in subsequent commits.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Builder — anchor-bracketed inferred window + `dominant_address_unit`

Extends Task 2's builder so the inferred window expands via the dominant address (spec §2b).

**Files:**
- Modify: `cleo/discovery_v2/contact_brand_tenures.py`
- Modify: `tests/test_discovery_v2_contact_brand_tenures.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/test_discovery_v2_contact_brand_tenures.py`:

```python
def test_dominant_address_unit_picked():
    """When two addresses appear in the strict window, the more-frequent one wins."""
    from cleo.discovery_v2.contact_brand_tenures import build_contact_brand_tenures

    conn = _make_db()
    # 3 sides at 30 St Clair, 1 side at 100 Bloor — 30 St Clair wins.
    for i in range(3):
        _add_party(conn, f"RT_S{i}", "buyer", "paul braun", f"20{10+i}-01-01",
                   street_number="30", street_name="st clair",
                   street_suffix="ave", street_direction="w")
        _add_brand_phrase(conn, f"RT_S{i}", "buyer",
                          "canfirst capital management", "trade_name")
    _add_party(conn, "RT_B", "buyer", "paul braun", "2014-01-01",
               street_number="100", street_name="bloor",
               street_suffix="st", street_direction="w")
    _add_brand_phrase(conn, "RT_B", "buyer",
                      "canfirst capital management", "trade_name")
    conn.commit()

    build_contact_brand_tenures(conn, today="2026-05-04")

    row = conn.execute(
        "SELECT dominant_address_unit FROM contact_brand_tenures "
        "WHERE brand_stem='canfirst'"
    ).fetchone()
    assert row["dominant_address_unit"] == "toronto|30|st clair|ave|w||"


def test_inferred_window_extends_via_dominant_address():
    """The inferred window extends backward+forward via address bracketing."""
    from cleo.discovery_v2.contact_brand_tenures import build_contact_brand_tenures

    conn = _make_db()
    # Two strict canfirst sides at 30 St Clair, 2010 + 2020.
    _add_party(conn, "RT_S1", "buyer", "paul braun", "2010-01-01",
               street_number="30", street_name="st clair",
               street_suffix="ave", street_direction="w")
    _add_brand_phrase(conn, "RT_S1", "buyer",
                      "canfirst capital management", "trade_name")
    _add_party(conn, "RT_S2", "buyer", "paul braun", "2020-01-01",
               street_number="30", street_name="st clair",
               street_suffix="ave", street_direction="w")
    _add_brand_phrase(conn, "RT_S2", "buyer",
                      "canfirst capital management", "trade_name")
    # An SPV-only side at 30 St Clair in 2002 (before strict start) and 2022 (after).
    # No qualifying brand_phrase, but party_name SPV does exist.
    _add_party(conn, "RT_SPV1", "buyer", "paul braun", "2002-04-29",
               street_number="30", street_name="st clair",
               street_suffix="ave", street_direction="w")
    _add_brand_phrase(conn, "RT_SPV1", "buyer", "cf vaughan portfolio inc", "party_name")
    _add_party(conn, "RT_SPV2", "buyer", "paul braun", "2022-12-13",
               street_number="30", street_name="st clair",
               street_suffix="ave", street_direction="w")
    _add_brand_phrase(conn, "RT_SPV2", "buyer", "cf vaughan portfolio inc", "party_name")
    # Add an irrelevant brand_phrase mapping for cf vaughan portfolio inc so it
    # doesn't fail the join — actually, we want it to NOT appear in tenures.
    # Don't add it to brand_stem_phrase_map; it's just an SPV name on party_name.
    conn.commit()

    build_contact_brand_tenures(conn, today="2026-05-04")

    row = conn.execute(
        "SELECT strict_start_date, strict_end_date, "
        "inferred_start_date, inferred_end_date, "
        "n_party_sides_strict, n_party_sides_inferred "
        "FROM contact_brand_tenures WHERE brand_stem='canfirst'"
    ).fetchone()
    assert row["strict_start_date"] == "2010-01-01"
    assert row["strict_end_date"] == "2020-01-01"
    assert row["inferred_start_date"] == "2002-04-29"
    assert row["inferred_end_date"] == "2022-12-13"
    assert row["n_party_sides_strict"] == 2
    assert row["n_party_sides_inferred"] == 4


def test_inferred_window_does_not_extend_when_no_other_sides():
    """If no SPV-only sides exist at the dominant address outside the strict
    window, inferred = strict (the Paul × Dundee case)."""
    from cleo.discovery_v2.contact_brand_tenures import build_contact_brand_tenures

    conn = _make_db()
    _add_party(conn, "RT_D1", "buyer", "paul braun", "1999-01-27",
               street_number="390", street_name="bay",
               street_suffix="st", street_direction="")
    _add_brand_phrase(conn, "RT_D1", "buyer", "dundee realty", "care_of")
    _add_party(conn, "RT_D2", "buyer", "paul braun", "2001-06-12",
               street_number="390", street_name="bay",
               street_suffix="st", street_direction="")
    _add_brand_phrase(conn, "RT_D2", "buyer", "dundee realty", "care_of")
    conn.commit()

    build_contact_brand_tenures(conn, today="2026-05-04")

    row = conn.execute(
        "SELECT strict_start_date, strict_end_date, "
        "inferred_start_date, inferred_end_date "
        "FROM contact_brand_tenures WHERE brand_stem='dundee'"
    ).fetchone()
    assert row["strict_start_date"] == row["inferred_start_date"] == "1999-01-27"
    assert row["strict_end_date"] == row["inferred_end_date"] == "2001-06-12"
```

- [ ] **Step 2: Run the tests to verify the new ones fail**

```bash
python3 -m pytest tests/test_discovery_v2_contact_brand_tenures.py -v
```

Expected: 3 new tests FAIL (`dominant_address_unit` is None, inferred dates equal strict). 5 prior tests still PASS.

- [ ] **Step 3: Extend the builder**

Replace the body of `build_contact_brand_tenures` in `cleo/discovery_v2/contact_brand_tenures.py` between the `# Strict window` comment and the `# is_active placeholder` comment with the expanded logic. Specifically, after computing `strict_start`, `strict_end`, `phrase_counts`, etc., replace the section that sets `inferred_start = strict_start` ... `n_inferred = n_strict` with:

```python
        # Pick dominant_address_unit: address_unit appearing on the most
        # distinct party-sides among the strict events. Deterministic
        # alphabetical tiebreak.
        addr_to_sides: dict[str, set] = defaultdict(set)
        for e in events:
            addr_to_sides[e["address_unit"]].add((e["source_id"], e["side"]))
        # Filter empty-key (city missing entirely) — those don't make a useful
        # bracket. If everything is empty, dominant is None.
        addr_to_sides = {k: v for k, v in addr_to_sides.items() if k.strip("|")}
        if addr_to_sides:
            dominant_addr = sorted(
                addr_to_sides.items(),
                key=lambda kv: (-len(kv[1]), kv[0]),
            )[0][0]
        else:
            dominant_addr = None

        # Expand inferred window: include any party-side for the same contact
        # at dominant_addr, regardless of whether it carries this stem's
        # qualifying brand_phrase.
        inferred_start = strict_start
        inferred_end = strict_end
        inferred_sides = set(distinct_sides)
        if dominant_addr is not None:
            ext_rows = conn.execute(
                """
                SELECT pf.source_id, pf.side, pf.sale_date,
                       pf.city, COALESCE(pf.street_number,'') AS sn,
                       COALESCE(pf.street_name,'') AS st,
                       COALESCE(pf.street_suffix,'') AS sx,
                       COALESCE(pf.street_direction,'') AS sd,
                       COALESCE(pf.suite_type,'') AS suite_t,
                       COALESCE(pf.suite_number,'') AS suite_n
                FROM party_fingerprints pf
                WHERE pf.contact_fingerprint = ?
                  AND pf.sale_date IS NOT NULL AND pf.sale_date != ''
                """,
                (cf,),
            ).fetchall()
            for er in ext_rows:
                ek = _address_unit_key(
                    er["city"], er["sn"], er["st"], er["sx"], er["sd"],
                    er["suite_t"], er["suite_n"]
                )
                if ek != dominant_addr:
                    continue
                if er["sale_date"] < inferred_start:
                    inferred_start = er["sale_date"]
                if er["sale_date"] > inferred_end:
                    inferred_end = er["sale_date"]
                inferred_sides.add((er["source_id"], er["side"]))

        n_strict = len(distinct_sides)
        n_inferred = len(inferred_sides)
```

Also update the `inserts.append(...)` tuple — change the `None,  # dominant_address_unit — Task 3` placeholder to `dominant_addr`:

```python
        inserts.append((
            cf, stem, strict_start, strict_end,
            inferred_start, inferred_end,
            n_strict, n_inferred,
            json.dumps(top_phrases),
            json.dumps(sf_breakdown),
            dominant_addr,
            None,  # auto_group_id — Task 4
            is_active,
        ))
```

- [ ] **Step 4: Run the tests to verify they all pass**

```bash
python3 -m pytest tests/test_discovery_v2_contact_brand_tenures.py -v
```

Expected: ALL 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add cleo/discovery_v2/contact_brand_tenures.py tests/test_discovery_v2_contact_brand_tenures.py
git commit -m "$(cat <<'EOF'
feat(discovery-v2): anchor-bracketed inferred window for tenures

Pick dominant_address_unit per (contact, stem) and extend the inferred
window backward/forward to include same-contact party-sides at that
address, even when those sides carry only an SPV brand_phrase.

For Paul × CanFirst this turns the 2004–2022 strict window into the
2002–2022 inferred window via 30 St Clair Ave. For Paul × Dundee
both windows stay 1999–2001 (no extension; no other 390 Bay sides).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Builder — soft `auto_group_id` corroboration link

**Files:**
- Modify: `cleo/discovery_v2/contact_brand_tenures.py`
- Modify: `tests/test_discovery_v2_contact_brand_tenures.py`

- [ ] **Step 1: Append failing test**

Append to `tests/test_discovery_v2_contact_brand_tenures.py`:

```python
def test_auto_group_id_link_when_canonical_stem_matches():
    """When an auto_group exists with matching canonical_stem, link it."""
    from cleo.discovery_v2.contact_brand_tenures import build_contact_brand_tenures

    conn = _make_db()
    conn.execute(
        "INSERT INTO auto_groups (auto_group_id, canonical_stem, display_name, "
        "tier, confidence, n_anchors, n_members) "
        "VALUES ('AGRP_01392', 'canfirst', 'CanFirst Capital Management', "
        "'confirmed', 0.85, 5, 58)"
    )
    _add_party(conn, "RT1", "buyer", "paul braun", "2010-01-01")
    _add_brand_phrase(conn, "RT1", "buyer", "canfirst capital management", "trade_name")
    _add_party(conn, "RT2", "buyer", "paul braun", "2020-01-01")
    _add_brand_phrase(conn, "RT2", "buyer", "canfirst capital management", "trade_name")
    conn.commit()

    build_contact_brand_tenures(conn, today="2026-05-04")

    row = conn.execute(
        "SELECT auto_group_id FROM contact_brand_tenures WHERE brand_stem='canfirst'"
    ).fetchone()
    assert row["auto_group_id"] == "AGRP_01392"


def test_auto_group_id_null_when_no_matching_stem():
    """When no auto_group has canonical_stem='dundee', auto_group_id is NULL."""
    from cleo.discovery_v2.contact_brand_tenures import build_contact_brand_tenures

    conn = _make_db()
    _add_party(conn, "RT_D1", "buyer", "paul braun", "1999-01-27",
               street_number="390", street_name="bay")
    _add_brand_phrase(conn, "RT_D1", "buyer", "dundee realty", "care_of")
    _add_party(conn, "RT_D2", "buyer", "paul braun", "2001-06-12",
               street_number="390", street_name="bay")
    _add_brand_phrase(conn, "RT_D2", "buyer", "dundee realty", "care_of")
    conn.commit()

    build_contact_brand_tenures(conn, today="2026-05-04")

    row = conn.execute(
        "SELECT auto_group_id FROM contact_brand_tenures WHERE brand_stem='dundee'"
    ).fetchone()
    assert row["auto_group_id"] is None


def test_auto_group_id_picks_highest_membership_on_tie():
    """When multiple auto_groups share canonical_stem, pick the one with most members."""
    from cleo.discovery_v2.contact_brand_tenures import build_contact_brand_tenures

    conn = _make_db()
    conn.execute(
        "INSERT INTO auto_groups (auto_group_id, canonical_stem, display_name, "
        "tier, confidence, n_anchors, n_members) VALUES "
        "('AGRP_00001', 'canfirst', 'A', 'confirmed', 0.8, 1, 5),"
        "('AGRP_00002', 'canfirst', 'B', 'confirmed', 0.8, 1, 50)"
    )
    _add_party(conn, "RT1", "buyer", "paul braun", "2010-01-01")
    _add_brand_phrase(conn, "RT1", "buyer", "canfirst capital management", "trade_name")
    _add_party(conn, "RT2", "buyer", "paul braun", "2020-01-01")
    _add_brand_phrase(conn, "RT2", "buyer", "canfirst capital management", "trade_name")
    conn.commit()

    build_contact_brand_tenures(conn, today="2026-05-04")

    row = conn.execute(
        "SELECT auto_group_id FROM contact_brand_tenures WHERE brand_stem='canfirst'"
    ).fetchone()
    assert row["auto_group_id"] == "AGRP_00002"  # higher n_members wins
```

- [ ] **Step 2: Run tests to verify the new ones fail**

```bash
python3 -m pytest tests/test_discovery_v2_contact_brand_tenures.py -v
```

Expected: 3 new tests FAIL (auto_group_id is always NULL after Task 3). Prior 8 still PASS.

- [ ] **Step 3: Add the auto_group corroboration step**

In `cleo/discovery_v2/contact_brand_tenures.py`, add a single bulk UPDATE after the `conn.executemany(...)` that inserts the rows, and **before** the final `conn.commit()`:

```python
    # Soft corroboration: link tenure → auto_group when canonical_stem matches.
    # When multiple auto_groups share canonical_stem, the highest-membership
    # one wins (deterministic, matches user's "drill into the biggest cluster"
    # intent).
    conn.execute("""
        UPDATE contact_brand_tenures
        SET auto_group_id = (
            SELECT g.auto_group_id
            FROM auto_groups g
            WHERE g.canonical_stem = contact_brand_tenures.brand_stem
            ORDER BY g.n_members DESC, g.auto_group_id ASC
            LIMIT 1
        )
    """)
```

- [ ] **Step 4: Run all tests to verify they pass**

```bash
python3 -m pytest tests/test_discovery_v2_contact_brand_tenures.py -v
```

Expected: ALL 11 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add cleo/discovery_v2/contact_brand_tenures.py tests/test_discovery_v2_contact_brand_tenures.py
git commit -m "$(cat <<'EOF'
feat(discovery-v2): soft auto_group_id corroboration link on tenures

After insert, populate auto_group_id with the highest-membership
auto_group whose canonical_stem matches the tenure's brand_stem. NULL
when no auto_group has matching canonical_stem (the spec's expected
case for stems without an auto_group).

This is a hyperlink target — a "drill into the auto_group if one
exists" decoration, not a source of truth. Auto-groups remain useful
for SPV nests; brand-stem tenures take over employer attribution.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Builder — `is_active` flag

**Files:**
- Modify: `cleo/discovery_v2/contact_brand_tenures.py`
- Modify: `tests/test_discovery_v2_contact_brand_tenures.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/test_discovery_v2_contact_brand_tenures.py`:

```python
def test_is_active_when_inferred_end_within_730_days():
    """Tenure ending within 730 days of today → is_active=1."""
    from cleo.discovery_v2.contact_brand_tenures import build_contact_brand_tenures

    conn = _make_db()
    _add_party(conn, "RT1", "buyer", "paul braun", "2010-01-01")
    _add_brand_phrase(conn, "RT1", "buyer", "canfirst capital management", "trade_name")
    # End within 730 days of today=2026-05-04 → 2024-05-05+ qualifies.
    _add_party(conn, "RT2", "buyer", "paul braun", "2025-01-01")
    _add_brand_phrase(conn, "RT2", "buyer", "canfirst capital management", "trade_name")
    conn.commit()

    build_contact_brand_tenures(conn, today="2026-05-04")

    row = conn.execute(
        "SELECT is_active, inferred_end_date FROM contact_brand_tenures "
        "WHERE brand_stem='canfirst'"
    ).fetchone()
    assert row["is_active"] == 1


def test_is_active_zero_when_too_old():
    """Tenure ending more than 730 days ago → is_active=0."""
    from cleo.discovery_v2.contact_brand_tenures import build_contact_brand_tenures

    conn = _make_db()
    _add_party(conn, "RT_D1", "buyer", "paul braun", "1999-01-27",
               street_number="390", street_name="bay")
    _add_brand_phrase(conn, "RT_D1", "buyer", "dundee realty", "care_of")
    _add_party(conn, "RT_D2", "buyer", "paul braun", "2001-06-12",
               street_number="390", street_name="bay")
    _add_brand_phrase(conn, "RT_D2", "buyer", "dundee realty", "care_of")
    conn.commit()

    build_contact_brand_tenures(conn, today="2026-05-04")

    row = conn.execute(
        "SELECT is_active FROM contact_brand_tenures WHERE brand_stem='dundee'"
    ).fetchone()
    assert row["is_active"] == 0


def test_is_active_uses_today_default_when_arg_omitted():
    """When today=None, builder uses datetime('now')."""
    from cleo.discovery_v2.contact_brand_tenures import build_contact_brand_tenures

    conn = _make_db()
    # End yesterday → must be active under today=None.
    import datetime
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    _add_party(conn, "RT1", "buyer", "alice smith", "2010-01-01")
    _add_brand_phrase(conn, "RT1", "buyer", "canfirst capital management", "trade_name")
    _add_party(conn, "RT2", "buyer", "alice smith", yesterday)
    _add_brand_phrase(conn, "RT2", "buyer", "canfirst capital management", "trade_name")
    conn.commit()

    build_contact_brand_tenures(conn, today=None)

    row = conn.execute(
        "SELECT is_active FROM contact_brand_tenures WHERE contact_fingerprint='alice smith'"
    ).fetchone()
    assert row["is_active"] == 1
```

- [ ] **Step 2: Run tests to verify the new ones fail**

```bash
python3 -m pytest tests/test_discovery_v2_contact_brand_tenures.py -v
```

Expected: 3 new tests FAIL (is_active is always 0).

- [ ] **Step 3: Compute `is_active` per row in the builder**

In `cleo/discovery_v2/contact_brand_tenures.py`, replace the `is_active = 0` placeholder line with logic that depends on `today`:

```python
        # is_active: 1 iff inferred_end_date >= today - 730 days.
        is_active = 1 if _is_active(inferred_end, today) else 0
```

And add a helper near the bottom of the file:

```python
def _is_active(inferred_end_date: str, today: str | None) -> bool:
    """Return True iff the tenure ends within ACTIVE_CLIFF_DAYS of today."""
    import datetime
    if today is None:
        today_dt = datetime.date.today()
    else:
        today_dt = datetime.date.fromisoformat(today)
    end_dt = datetime.date.fromisoformat(inferred_end_date)
    delta_days = (today_dt - end_dt).days
    return delta_days <= ACTIVE_CLIFF_DAYS
```

- [ ] **Step 4: Run all tests to verify they pass**

```bash
python3 -m pytest tests/test_discovery_v2_contact_brand_tenures.py -v
```

Expected: ALL 14 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add cleo/discovery_v2/contact_brand_tenures.py tests/test_discovery_v2_contact_brand_tenures.py
git commit -m "$(cat <<'EOF'
feat(discovery-v2): is_active flag on contact_brand_tenures

Tenure rows mark is_active=1 when inferred_end_date is within 730
days of today (two-year recency cliff per spec §2d). Today is
injectable for tests; production uses datetime.date.today().

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Slot the builder into the Layer 2 orchestrator

**Files:**
- Modify: `cleo/discovery_v2/auto_groups.py`
- Modify: `tests/test_discovery_v2_auto_groups.py` (or create if absent — check first)

- [ ] **Step 1: Inspect the orchestrator call order**

Read `cleo/discovery_v2/auto_groups.py` lines 13–29. The current chain is:
`build_stems → build_anchor_scores → build_seeds → build_expansion → build_contact_tenures → detect_conflicts → _finalize_display_and_counts`.

We slot `build_contact_brand_tenures` **after** `build_contact_tenures` so the soft `auto_group_id` link can read freshly-finalized `auto_groups` (display_name + n_members are finalized in stage A5, and we read n_members for the tiebreak — so we slot **after** A5).

- [ ] **Step 2: Modify `build_auto_groups`**

In `cleo/discovery_v2/auto_groups.py`, add the import and the call.

Replace:
```python
from cleo.discovery_v2.conflicts import detect_conflicts
```

with:
```python
from cleo.discovery_v2.conflicts import detect_conflicts
from cleo.discovery_v2.contact_brand_tenures import build_contact_brand_tenures
```

And in the body of `build_auto_groups`, replace:
```python
    a5 = _finalize_display_and_counts(conn, verbose=verbose)

    summary = {**a1, **a2, **a3, **a4, **ct, **a6, **a5}
```

with:
```python
    a5 = _finalize_display_and_counts(conn, verbose=verbose)
    cbt = build_contact_brand_tenures(conn, verbose=verbose)

    summary = {**a1, **a2, **a3, **a4, **ct, **a6, **a5, **cbt}
```

- [ ] **Step 3: Verify the orchestrator runs end-to-end against an in-memory DB**

If `tests/test_discovery_v2_auto_groups.py` exists with a smoke test, just rerun it. If not, add one. Quick check:

```bash
python3 -m pytest tests/test_discovery_v2_auto_groups.py -v
```

If the file is absent or this test isn't there, add this minimal smoke test to `tests/test_discovery_v2_auto_groups.py`:

```python
"""Smoke test for the Layer 2 orchestrator end-to-end."""
import sqlite3


def test_orchestrator_includes_contact_brand_tenures_step():
    """build_auto_groups returns a summary that includes n_tenure_rows."""
    from cleo.database.schema import get_full_schema_sql
    from cleo.discovery_v2.auto_groups import build_auto_groups

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    # Use the real schema sql so all tables exist (incl. contact_brand_tenures
    # via migration 018, plus all Layer 2 tables).
    conn.executescript(get_full_schema_sql())
    # Empty DB — orchestrator should still run without erroring.
    summary = build_auto_groups(conn, verbose=False)
    assert "n_tenure_rows" in summary
    assert summary["n_tenure_rows"] == 0
    conn.close()
```

If `cleo.database.schema` does not expose `get_full_schema_sql`, instead seed only the tables `build_contact_brand_tenures` reads (the same set used in `_make_db()` from Task 2) plus the tables the upstream stages read. Pragmatic alternative: replace the smoke test body with just a direct call to `build_contact_brand_tenures` against an empty schema (the real orchestrator integration is verified manually in Step 4):

```python
def test_contact_brand_tenures_is_imported_in_auto_groups():
    """The orchestrator imports the new builder."""
    from cleo.discovery_v2 import auto_groups
    assert hasattr(auto_groups, "build_contact_brand_tenures")
```

Use whichever variant works against the existing test infrastructure — the goal is just to verify the wiring.

- [ ] **Step 4: Run the orchestrator against the real DB**

```bash
python3 -m cleo.discovery_v2 2>&1 | tail -30
```

Expected: full Layer 2 build runs, ending with a line like `contact_brand_tenures: 4,217 rows.` (exact count varies). Then the final `Layer 2: done. {...'n_tenure_rows': 4217...}` summary print.

Verify:
```bash
sqlite3 data/cleo.db "SELECT COUNT(*) FROM contact_brand_tenures;"
sqlite3 data/cleo.db "SELECT contact_fingerprint, brand_stem, strict_start_date, strict_end_date, inferred_start_date, inferred_end_date, n_party_sides_strict, n_party_sides_inferred, is_active FROM contact_brand_tenures WHERE contact_fingerprint='paul braun' ORDER BY brand_stem;"
```

Expected: Paul Braun has rows for `canfirst` (inferred 2002–2022, n_inferred ≈ 60+, is_active=0 if 2022 > 730d ago else 1) and `dundee` (1999–2001, is_active=0). Compare the actual counts to the spec's `60 trade_name + 15 companies_json + 4 care_of` table; small differences are expected if the DB has more recent rows than the spec's snapshot.

- [ ] **Step 5: Commit**

```bash
git add cleo/discovery_v2/auto_groups.py tests/test_discovery_v2_auto_groups.py
git commit -m "$(cat <<'EOF'
feat(discovery-v2): wire contact_brand_tenures into Layer 2 orchestrator

build_auto_groups now invokes build_contact_brand_tenures after the
existing A5 display-finalize step so the soft auto_group_id link can
read finalized n_members for its tiebreak. Idempotent — same as the
other Layer 2 stages.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: API — extend `/api/contacts/:id` with career_history, current_employer, transactions[].tenure

The existing endpoint (`cleo/web/routes/contacts.py:194-287`) returns the `ContactDetail` shape consumed by `ContactDetailPage.tsx`. We add new fields without breaking existing ones.

**Files:**
- Modify: `cleo/web/routes/contacts.py`
- Create: `tests/test_routes_contacts_tenures.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_routes_contacts_tenures.py`:

```python
"""Tests for the new tenure-related fields on /api/contacts/:id."""
import sqlite3
import pytest
from fastapi.testclient import TestClient


def _seeded_db():
    """In-memory DB seeded with one contact, two tenures, three transactions."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    # Schema — only the tables the contact_detail endpoint reads.
    conn.executescript("""
        CREATE TABLE contacts (
            id TEXT PRIMARY KEY,
            name_fingerprint TEXT NOT NULL,
            first_name TEXT, last_name TEXT, display_name TEXT NOT NULL,
            phone TEXT, email TEXT, mobile TEXT, job_title TEXT,
            company_name TEXT, current_group_id TEXT, contact_type TEXT,
            status TEXT NOT NULL DEFAULT 'lead',
            source TEXT, transaction_count INTEGER DEFAULT 0,
            first_seen_date TEXT, last_seen_date TEXT,
            hubspot_id TEXT, last_engaged_date TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE contact_field_overrides (
            contact_id TEXT PRIMARY KEY,
            email TEXT, phone TEXT, mobile TEXT, job_title TEXT,
            contact_type TEXT, linkedin_url TEXT, linkedin_headline TEXT,
            linkedin_photo_url TEXT, linkedin_enriched_at TEXT,
            datanyze_raw TEXT
        );
        CREATE TABLE contact_work_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id TEXT NOT NULL,
            company TEXT, title TEXT, start_date TEXT, end_date TEXT,
            is_current INTEGER, location TEXT, company_logo_url TEXT
        );
        CREATE TABLE transactions (
            source_id TEXT PRIMARY KEY,
            sale_date TEXT, sale_price REAL,
            display_address TEXT, city TEXT, region TEXT, property_id TEXT
        );
        CREATE TABLE transaction_parties (
            source_id TEXT, side TEXT, contact_id TEXT,
            party_name TEXT, contact_title TEXT, phone TEXT
        );
        CREATE TABLE transaction_mailing_addresses (
            source_id TEXT, side TEXT, display TEXT, geocode_string TEXT
        );
        CREATE TABLE pois (
            property_id TEXT, brand TEXT, category TEXT
        );
        CREATE TABLE groups (
            id TEXT PRIMARY KEY, display_name TEXT, status TEXT, hq_address TEXT
        );
        CREATE TABLE party_fingerprints (
            source_id TEXT NOT NULL, side TEXT NOT NULL,
            street_number TEXT, street_name TEXT, street_suffix TEXT,
            street_direction TEXT, suite_type TEXT, suite_number TEXT,
            city TEXT, phone TEXT,
            contact_fingerprint TEXT, sale_date TEXT,
            PRIMARY KEY (source_id, side)
        );
        CREATE TABLE contact_brand_tenures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_fingerprint TEXT NOT NULL,
            brand_stem TEXT NOT NULL,
            strict_start_date TEXT, strict_end_date TEXT,
            inferred_start_date TEXT, inferred_end_date TEXT,
            n_party_sides_strict INTEGER, n_party_sides_inferred INTEGER,
            top_phrases_json TEXT, source_field_breakdown_json TEXT,
            dominant_address_unit TEXT, auto_group_id TEXT,
            is_active INTEGER, discovered_at TEXT
        );
        CREATE TABLE auto_groups (
            auto_group_id TEXT PRIMARY KEY, canonical_stem TEXT NOT NULL,
            display_name TEXT NOT NULL, tier TEXT, confidence REAL,
            n_anchors INTEGER, n_members INTEGER
        );
    """)
    # Seed one contact.
    conn.execute(
        "INSERT INTO contacts (id, name_fingerprint, display_name, status, "
        "transaction_count) VALUES "
        "('CON_07049', 'paul braun', 'Paul Braun', 'lead', 80)"
    )
    # Two tenures.
    conn.execute(
        "INSERT INTO contact_brand_tenures (contact_fingerprint, brand_stem, "
        "strict_start_date, strict_end_date, inferred_start_date, "
        "inferred_end_date, n_party_sides_strict, n_party_sides_inferred, "
        "top_phrases_json, source_field_breakdown_json, "
        "dominant_address_unit, auto_group_id, is_active) VALUES "
        "('paul braun', 'canfirst', '2004-07-02', '2022-12-13', "
        " '2002-04-29', '2022-12-13', 60, 80, "
        " '[{\"phrase\":\"canfirst capital management\",\"n\":60}]', "
        " '{\"trade_name\":41,\"companies_json\":15,\"care_of\":4}', "
        " 'toronto|30|st clair|ave|w||', 'AGRP_01392', 1),"
        "('paul braun', 'dundee', '1999-01-27', '2001-06-12', "
        " '1999-01-27', '2001-06-12', 8, 8, "
        " '[{\"phrase\":\"dundee realty\",\"n\":8}]', "
        " '{\"care_of\":5,\"companies_json\":3}', "
        " 'toronto|390|bay|st|||', NULL, 0)"
    )
    conn.execute(
        "INSERT INTO auto_groups (auto_group_id, canonical_stem, display_name, "
        "tier, confidence, n_anchors, n_members) VALUES "
        "('AGRP_01392', 'canfirst', 'CanFirst Capital Management', "
        " 'confirmed', 0.85, 5, 58)"
    )
    # 3 transactions, with their party-side rows so transactions[].tenure is computable.
    conn.execute(
        "INSERT INTO transactions (source_id, sale_date, sale_price, "
        "display_address, city, region, property_id) VALUES "
        "('RT_C1', '2010-06-01', 5000000, '50 King St', 'toronto', '01', 'P1'),"
        "('RT_D1', '2000-03-15', 1000000, '100 Bay St', 'toronto', '01', 'P2'),"
        "('RT_INF', '2003-08-20', 2000000, '200 Yonge St', 'toronto', '01', 'P3')"
    )
    conn.execute(
        "INSERT INTO transaction_parties (source_id, side, contact_id, "
        "party_name) VALUES "
        "('RT_C1', 'buyer', 'CON_07049', 'CF Vaughan Portfolio Inc'),"
        "('RT_D1', 'buyer', 'CON_07049', 'Some SPV'),"
        "('RT_INF', 'buyer', 'CON_07049', 'Another SPV')"
    )
    # party_fingerprints for the three sides — they all use 30 St Clair (canfirst dominant)
    # except RT_D1 which uses 390 Bay (dundee dominant).
    conn.execute(
        "INSERT INTO party_fingerprints (source_id, side, contact_fingerprint, "
        "sale_date, city, street_number, street_name, street_suffix, "
        "street_direction, suite_type, suite_number, phone) VALUES "
        "('RT_C1','buyer','paul braun','2010-06-01','toronto','30','st clair','ave','w','','','4169249009'),"
        "('RT_D1','buyer','paul braun','2000-03-15','toronto','390','bay','st','','','',''),"
        "('RT_INF','buyer','paul braun','2003-08-20','toronto','30','st clair','ave','w','','','')"
    )
    conn.commit()
    return conn


@pytest.fixture
def client():
    from cleo.web.app import app
    from cleo.web import deps
    conn = _seeded_db()

    def _get_conn_override():
        yield conn

    app.dependency_overrides[deps.get_db] = _get_conn_override
    app.dependency_overrides[deps.get_current_user] = lambda: {"email": "test"}
    yield TestClient(app)
    app.dependency_overrides.clear()
    conn.close()


def test_contact_detail_returns_career_history(client):
    """career_history field lists tenures sorted by inferred_end_date DESC."""
    resp = client.get("/api/contacts/CON_07049")
    assert resp.status_code == 200
    body = resp.json()
    assert "career_history" in body
    assert len(body["career_history"]) == 2
    # canfirst (ends 2022) ranks before dundee (ends 2001)
    assert body["career_history"][0]["brand_stem"] == "canfirst"
    assert body["career_history"][1]["brand_stem"] == "dundee"
    cf = body["career_history"][0]
    assert cf["is_active"] == 1
    assert cf["display_name"] == "canfirst capital management"  # top phrase
    assert cf["n_transactions_credited"] >= 1
    assert cf["auto_group_id"] == "AGRP_01392"


def test_contact_detail_current_employer_realtrack_derived(client):
    """current_employer is the active tenure with most n_party_sides_inferred."""
    resp = client.get("/api/contacts/CON_07049")
    body = resp.json()
    ce = body["current_employer"]
    assert ce is not None
    assert ce["source"] == "realtrack"  # no LinkedIn rows seeded
    assert ce["brand_stem"] == "canfirst"
    assert ce["display_name"] == "canfirst capital management"


def test_contact_detail_transactions_carry_tenure_attribution(client):
    """Each transaction row gets a `tenure` field with stem + inferred flag."""
    resp = client.get("/api/contacts/CON_07049")
    txns = resp.json()["transactions"]
    by_id = {t["source_id"]: t for t in txns}
    # RT_C1: explicit canfirst stem isn't in party_atoms (we skipped seeding atoms);
    # but RT_C1 falls inside canfirst inferred window AND is at the dominant address.
    # So it should be attributed to canfirst with inferred=True.
    assert by_id["RT_C1"]["tenure"]["brand_stem"] == "canfirst"
    assert by_id["RT_C1"]["tenure"]["inferred"] is True
    # RT_D1 falls in dundee inferred window at 390 Bay (dominant for dundee).
    assert by_id["RT_D1"]["tenure"]["brand_stem"] == "dundee"
    # RT_INF falls inside canfirst inferred window via 30 St Clair (dominant).
    assert by_id["RT_INF"]["tenure"]["brand_stem"] == "canfirst"
    assert by_id["RT_INF"]["tenure"]["inferred"] is True


def test_contact_detail_phone_tenure_tag_active(client):
    """Phone matching an active tenure's window gets an `active` tag with the stem."""
    resp = client.get("/api/contacts/CON_07049")
    body = resp.json()
    assert body["phone_tenure_tag"] is not None
    assert body["phone_tenure_tag"]["state"] == "active"
    assert body["phone_tenure_tag"]["stem"] == "canfirst"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python3 -m pytest tests/test_routes_contacts_tenures.py -v
```

Expected: ALL 4 tests FAIL with `AssertionError: 'career_history' not in body` or similar.

- [ ] **Step 3: Extend `contact_detail` in `cleo/web/routes/contacts.py`**

Open `cleo/web/routes/contacts.py`. Find the `contact_detail` function (line 194). Add the new logic **before** the final `return result`:

```python
    # ── Career history (contact_brand_tenures) ─────────────────────────────
    fp = result.get("name_fingerprint")
    cbt_rows = []
    if fp:
        cbt_rows = db.execute(
            """
            SELECT cbt.brand_stem, cbt.strict_start_date, cbt.strict_end_date,
                   cbt.inferred_start_date, cbt.inferred_end_date,
                   cbt.n_party_sides_strict, cbt.n_party_sides_inferred,
                   cbt.top_phrases_json, cbt.source_field_breakdown_json,
                   cbt.dominant_address_unit, cbt.auto_group_id, cbt.is_active
            FROM contact_brand_tenures cbt
            WHERE cbt.contact_fingerprint = ?
            ORDER BY cbt.inferred_end_date DESC, cbt.brand_stem ASC
            """,
            (fp,),
        ).fetchall()

    career_history = []
    for r in cbt_rows:
        cd = dict(r)
        top_phrases = json.loads(cd["top_phrases_json"])
        cd["display_name"] = top_phrases[0]["phrase"] if top_phrases else cd["brand_stem"]
        cd["top_phrases"] = top_phrases
        cd["source_field_breakdown"] = json.loads(cd["source_field_breakdown_json"])
        # Strip the raw JSON columns from the response — clients use the parsed forms.
        cd.pop("top_phrases_json", None)
        cd.pop("source_field_breakdown_json", None)
        career_history.append(cd)

    # n_transactions_credited per tenure: count this contact's transactions
    # whose sale_date falls in the inferred window.
    if career_history and txn_list:
        for t in career_history:
            t["n_transactions_credited"] = sum(
                1 for x in txn_list
                if x.get("sale_date")
                and t["inferred_start_date"] <= x["sale_date"] <= t["inferred_end_date"]
            )
    result["career_history"] = career_history

    # ── current_employer derivation (LinkedIn > active realtrack) ──────────
    work_positions = result.get("work_history") or []
    linkedin_current = next(
        (p for p in work_positions if p.get("is_current")),
        None,
    )
    current_employer = None
    if linkedin_current:
        current_employer = {
            "source": "linkedin",
            "company": linkedin_current.get("company"),
            "title": linkedin_current.get("title"),
            "brand_stem": None,  # populated by reconcile step below
            "display_name": linkedin_current.get("company"),
        }
    active_tenures = [t for t in career_history if t.get("is_active") == 1]
    if active_tenures:
        active_tenures.sort(
            key=lambda t: (-t.get("n_party_sides_inferred", 0), t.get("brand_stem")),
        )
        top_active = active_tenures[0]
        if current_employer is None:
            current_employer = {
                "source": "realtrack",
                "company": top_active["display_name"],
                "title": None,
                "brand_stem": top_active["brand_stem"],
                "display_name": top_active["display_name"],
            }
        else:
            # LinkedIn already set; check if its company stem matches the top
            # realtrack tenure for divergence indicator. Stem comparison is
            # lowercase substring containment (LinkedIn names are messy).
            li_lower = (linkedin_current.get("company") or "").lower()
            if top_active["brand_stem"] in li_lower:
                current_employer["source"] = "linkedin_confirmed"
                current_employer["brand_stem"] = top_active["brand_stem"]
            else:
                current_employer["source"] = "linkedin_diverges"
                current_employer["realtrack_stem"] = top_active["brand_stem"]
                current_employer["realtrack_display_name"] = top_active["display_name"]
    result["current_employer"] = current_employer

    # ── Per-transaction tenure attribution (spec §2e) ──────────────────────
    # A transaction credits a tenure iff:
    #   sale_date in [inferred_start, inferred_end]
    #   AND (the side's brand_phrase carries the stem OR the side's address_unit
    #        equals the tenure's dominant_address_unit)
    if fp and txn_list:
        # Pre-fetch the brand_stems and address_units of the contact's party-sides.
        side_info = {}
        for r in db.execute(
            """
            SELECT pf.source_id, pf.side,
                   pf.city, COALESCE(pf.street_number,'') AS sn,
                   COALESCE(pf.street_name,'') AS st,
                   COALESCE(pf.street_suffix,'') AS sx,
                   COALESCE(pf.street_direction,'') AS sd,
                   COALESCE(pf.suite_type,'') AS suite_t,
                   COALESCE(pf.suite_number,'') AS suite_n
            FROM party_fingerprints pf
            WHERE pf.contact_fingerprint = ?
            """,
            (fp,),
        ).fetchall():
            addr_unit = "|".join([
                (r["city"] or "").lower(), r["sn"], (r["st"] or "").lower(),
                (r["sx"] or "").lower(), (r["sd"] or "").lower(),
                (r["suite_t"] or "").lower(), r["suite_n"],
            ])
            side_info[(r["source_id"], r["side"])] = {"addr_unit": addr_unit, "stems": set()}

        # Lookup the qualifying brand_phrase stems present on each side.
        for r in db.execute(
            """
            SELECT pa.source_id, pa.side, m.stem
            FROM party_atoms pa
            JOIN brand_stem_phrase_map m ON m.phrase = pa.atom_value
            JOIN party_fingerprints pf ON pf.source_id = pa.source_id AND pf.side = pa.side
            WHERE pa.atom_type = 'brand_phrase'
              AND pa.source_field IN ('trade_name','care_of','companies_json')
              AND pf.contact_fingerprint = ?
            """,
            (fp,),
        ).fetchall():
            key = (r["source_id"], r["side"])
            if key in side_info:
                side_info[key]["stems"].add(r["stem"])

        for txn in txn_list:
            attribution = None
            sid = txn.get("source_id")
            sd = txn.get("side")
            sale_date = txn.get("sale_date")
            if sid and sd and sale_date:
                info = side_info.get((sid, sd), {"addr_unit": "", "stems": set()})
                for t in career_history:
                    if not (t["inferred_start_date"] <= sale_date <= t["inferred_end_date"]):
                        continue
                    explicit = t["brand_stem"] in info["stems"]
                    address_match = (
                        t.get("dominant_address_unit") is not None
                        and info["addr_unit"] == t["dominant_address_unit"]
                    )
                    if explicit or address_match:
                        attribution = {
                            "brand_stem": t["brand_stem"],
                            "display_name": t["display_name"],
                            "inferred": not explicit,
                        }
                        break  # career_history is sorted; take the most-recent-ending match
            txn["tenure"] = attribution
        result["transactions"] = txn_list

    # ── Phone / address tenure tags ────────────────────────────────────────
    today = db.execute("SELECT date('now') AS d").fetchone()["d"]
    cliff = db.execute("SELECT date('now','-730 days') AS d").fetchone()["d"]

    def _tag_for_phone(phone_value):
        if not phone_value or not fp or not career_history:
            return None
        seen = db.execute(
            "SELECT MIN(sale_date) AS first_seen, MAX(sale_date) AS last_seen "
            "FROM party_fingerprints WHERE contact_fingerprint = ? AND phone = ?",
            (fp, phone_value),
        ).fetchone()
        if not seen or not seen["last_seen"]:
            return None
        last_seen = seen["last_seen"]
        first_seen = seen["first_seen"]
        # Find tenures whose window overlaps [first_seen, last_seen].
        overlapping = [
            t for t in career_history
            if not (t["inferred_end_date"] < first_seen or t["inferred_start_date"] > last_seen)
        ]
        if not overlapping:
            return {"state": "stale", "last_seen": last_seen, "stem": None,
                    "display_name": None}
        # Active iff last_seen >= cliff AND overlaps current_employer.
        ce_stem = (current_employer or {}).get("brand_stem")
        is_active = (
            last_seen >= cliff
            and any(t["brand_stem"] == ce_stem and t.get("is_active") == 1 for t in overlapping)
        )
        if is_active:
            ce = next(t for t in overlapping if t["brand_stem"] == ce_stem)
            return {
                "state": "active",
                "last_seen": last_seen,
                "stem": ce_stem,
                "display_name": ce["display_name"],
                "since": ce["inferred_start_date"],
            }
        # Stale — label with the dominant overlapping tenure (most party-sides).
        overlapping.sort(key=lambda t: -t.get("n_party_sides_inferred", 0))
        return {
            "state": "stale",
            "last_seen": last_seen,
            "stem": overlapping[0]["brand_stem"],
            "display_name": overlapping[0]["display_name"],
        }

    result["phone_tenure_tag"] = _tag_for_phone(result.get("phone"))

    # Address tenure tag: the contact's "primary mailing address" doesn't live
    # on the contacts row. We surface a tag for each unique address that
    # appears on this contact's party-sides, sorted most-recent first. The UI
    # decides which one to show under the (single) Address row.
    address_tags = []
    if fp:
        addr_rows = db.execute(
            """
            SELECT city,
                   COALESCE(street_number,'') AS sn,
                   COALESCE(street_name,'') AS st,
                   COALESCE(street_suffix,'') AS sx,
                   COALESCE(street_direction,'') AS sd,
                   COALESCE(suite_type,'') AS suite_t,
                   COALESCE(suite_number,'') AS suite_n,
                   MIN(sale_date) AS first_seen, MAX(sale_date) AS last_seen
            FROM party_fingerprints
            WHERE contact_fingerprint = ?
              AND street_number IS NOT NULL AND street_number != ''
            GROUP BY 1,2,3,4,5,6,7
            ORDER BY MAX(sale_date) DESC
            """,
            (fp,),
        ).fetchall()
        for ar in addr_rows:
            addr_unit = "|".join([
                (ar["city"] or "").lower(), ar["sn"], (ar["st"] or "").lower(),
                (ar["sx"] or "").lower(), (ar["sd"] or "").lower(),
                (ar["suite_t"] or "").lower(), ar["suite_n"],
            ])
            # Match against tenure dominant_address_unit.
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

Note: `txn_list` is the local variable defined earlier in `contact_detail` (`result["transactions"]`). The new block runs **after** `result["transactions"] = txn_list` so we can mutate the same list.

- [ ] **Step 4: Run the test to verify it passes**

```bash
python3 -m pytest tests/test_routes_contacts_tenures.py -v
```

Expected: ALL 4 tests PASS.

- [ ] **Step 5: Re-run the existing contacts test to make sure nothing broke**

```bash
python3 -m pytest tests/ -k "contact" -v 2>&1 | tail -30
```

Expected: all existing tests still pass; only the 4 new ones added.

- [ ] **Step 6: Commit**

```bash
git add cleo/web/routes/contacts.py tests/test_routes_contacts_tenures.py
git commit -m "$(cat <<'EOF'
feat(api): /api/contacts/:id career_history + current_employer + tenure tags

Extends the existing contact detail endpoint with:
- career_history[]: tenures sorted by inferred_end_date DESC, with
  display_name + top_phrases + source_field_breakdown + auto_group_id.
- current_employer: LinkedIn (when imported) or active realtrack tenure
  with the most party-sides; reconciles when stems agree, flags
  divergence when they don't.
- transactions[].tenure: per-row attribution (spec §2e) with `inferred`
  flag set when only the address bracketed it (no explicit stem on the
  side).
- phone_tenure_tag and address_tenure_tags: active/stale labels for the
  Contact Info card.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: API — tenure detail drawer endpoint

A single endpoint returning everything the drawer renders. See "Resolved open questions" #3.

**Files:**
- Create: `cleo/web/routes/contact_tenures.py`
- Modify: `cleo/web/app.py`
- Create/extend: `tests/test_routes_contact_tenures.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_routes_contacts_tenures.py` (reusing the seeded fixture):

```python
def test_tenure_detail_returns_full_payload(client):
    """GET /api/contacts/:id/tenures/:stem returns top phrases, breakdown, dates, transactions."""
    resp = client.get("/api/contacts/CON_07049/tenures/canfirst")
    assert resp.status_code == 200
    body = resp.json()
    assert body["brand_stem"] == "canfirst"
    assert body["display_name"] == "canfirst capital management"
    assert body["strict_start_date"] == "2004-07-02"
    assert body["inferred_start_date"] == "2002-04-29"
    assert body["auto_group_id"] == "AGRP_01392"
    assert body["auto_group_display_name"] == "CanFirst Capital Management"
    # Top phrases preserved as list of {phrase, n}.
    assert body["top_phrases"][0] == {"phrase": "canfirst capital management", "n": 60}
    # Source field breakdown
    assert body["source_field_breakdown"] == {
        "trade_name": 41, "companies_json": 15, "care_of": 4
    }
    # Credited transactions
    assert "credited_transactions" in body
    assert isinstance(body["credited_transactions"], list)
    # Each txn carries date, address, price, and brand_phrase + source_field
    # if explicitly stem-matched; else inferred=True.
    sample = body["credited_transactions"][0]
    assert {"source_id", "sale_date", "display_address", "sale_price", "inferred"} <= set(sample.keys())


def test_tenure_detail_404_on_unknown_contact(client):
    resp = client.get("/api/contacts/CON_99999/tenures/canfirst")
    assert resp.status_code == 404


def test_tenure_detail_404_on_unknown_stem(client):
    resp = client.get("/api/contacts/CON_07049/tenures/unknownstem")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_routes_contacts_tenures.py -v
```

Expected: 3 new tests FAIL (404 because the route doesn't exist).

- [ ] **Step 3: Create the new router file**

Create `cleo/web/routes/contact_tenures.py`:

```python
"""
Tenure-related endpoints for the Contact page.

Three endpoints:
  GET /api/contacts/:id/tenures/:stem        — Tenure Detail drawer payload
  GET /api/companies/:stem/portfolio-footprint — Hero map (current employer's portfolio)
  GET /api/contacts/:id/property-footprint-tenured — Color-coded pin map
"""
import json
from fastapi import APIRouter, Depends, HTTPException
from ..deps import get_db, get_current_user

router = APIRouter()


def _resolve_fingerprint(db, contact_id: str) -> str | None:
    row = db.execute(
        "SELECT name_fingerprint FROM contacts WHERE id = ?", (contact_id,)
    ).fetchone()
    return row["name_fingerprint"] if row else None


@router.get("/contacts/{contact_id}/tenures/{stem}")
def tenure_detail(
    contact_id: str, stem: str,
    db=Depends(get_db), user=Depends(get_current_user),
):
    fp = _resolve_fingerprint(db, contact_id)
    if not fp:
        raise HTTPException(status_code=404, detail="Contact not found")

    cbt = db.execute(
        """
        SELECT brand_stem, strict_start_date, strict_end_date,
               inferred_start_date, inferred_end_date,
               n_party_sides_strict, n_party_sides_inferred,
               top_phrases_json, source_field_breakdown_json,
               dominant_address_unit, auto_group_id, is_active
        FROM contact_brand_tenures
        WHERE contact_fingerprint = ? AND brand_stem = ?
        """,
        (fp, stem),
    ).fetchone()
    if not cbt:
        raise HTTPException(status_code=404, detail="Tenure not found")

    body = dict(cbt)
    top_phrases = json.loads(body.pop("top_phrases_json"))
    body["top_phrases"] = top_phrases
    body["display_name"] = top_phrases[0]["phrase"] if top_phrases else stem
    body["source_field_breakdown"] = json.loads(body.pop("source_field_breakdown_json"))

    # Hydrate auto_group display_name when the link exists.
    body["auto_group_display_name"] = None
    if body.get("auto_group_id"):
        gd = db.execute(
            "SELECT display_name FROM auto_groups WHERE auto_group_id = ?",
            (body["auto_group_id"],),
        ).fetchone()
        if gd:
            body["auto_group_display_name"] = gd["display_name"]

    # Credited transactions: same rule as per-row attribution in /api/contacts/:id.
    # We materialize the side-info lookup (stems on side + address_unit) up front,
    # then walk this contact's transactions and emit a row per credited txn.
    side_stems: dict = {}
    for r in db.execute(
        """
        SELECT pa.source_id, pa.side, m.stem, pa.atom_value, pa.source_field
        FROM party_atoms pa
        JOIN brand_stem_phrase_map m ON m.phrase = pa.atom_value
        JOIN party_fingerprints pf ON pf.source_id = pa.source_id AND pf.side = pa.side
        WHERE pa.atom_type='brand_phrase'
          AND pa.source_field IN ('trade_name','care_of','companies_json')
          AND pf.contact_fingerprint = ?
        """,
        (fp,),
    ).fetchall():
        side_stems.setdefault((r["source_id"], r["side"]), []).append(
            {"stem": r["stem"], "phrase": r["atom_value"], "source_field": r["source_field"]}
        )

    side_addr: dict = {}
    for r in db.execute(
        """
        SELECT pf.source_id, pf.side, pf.city,
               COALESCE(pf.street_number,'') AS sn,
               COALESCE(pf.street_name,'') AS st,
               COALESCE(pf.street_suffix,'') AS sx,
               COALESCE(pf.street_direction,'') AS sd,
               COALESCE(pf.suite_type,'') AS suite_t,
               COALESCE(pf.suite_number,'') AS suite_n
        FROM party_fingerprints pf WHERE pf.contact_fingerprint = ?
        """,
        (fp,),
    ).fetchall():
        side_addr[(r["source_id"], r["side"])] = "|".join([
            (r["city"] or "").lower(), r["sn"], (r["st"] or "").lower(),
            (r["sx"] or "").lower(), (r["sd"] or "").lower(),
            (r["suite_t"] or "").lower(), r["suite_n"],
        ])

    txn_rows = db.execute(
        """
        SELECT tp.source_id, tp.side, t.sale_date, t.sale_price,
               t.display_address, t.city
        FROM transaction_parties tp
        JOIN transactions t ON tp.source_id = t.source_id
        JOIN contacts c ON c.id = tp.contact_id
        WHERE c.name_fingerprint = ?
          AND t.sale_date BETWEEN ? AND ?
        ORDER BY t.sale_date DESC
        """,
        (fp, body["inferred_start_date"], body["inferred_end_date"]),
    ).fetchall()

    credited = []
    for r in txn_rows:
        sid_key = (r["source_id"], r["side"])
        explicit_phrases = [s for s in side_stems.get(sid_key, []) if s["stem"] == stem]
        address_match = (
            body.get("dominant_address_unit") is not None
            and side_addr.get(sid_key) == body["dominant_address_unit"]
        )
        if explicit_phrases:
            txn_dict = dict(r)
            txn_dict["inferred"] = False
            txn_dict["brand_phrase"] = explicit_phrases[0]["phrase"]
            txn_dict["source_field"] = explicit_phrases[0]["source_field"]
            credited.append(txn_dict)
        elif address_match:
            txn_dict = dict(r)
            txn_dict["inferred"] = True
            txn_dict["brand_phrase"] = None
            txn_dict["source_field"] = None
            credited.append(txn_dict)
    body["credited_transactions"] = credited
    return body


@router.get("/companies/{stem}/portfolio-footprint")
def company_portfolio_footprint(
    stem: str, db=Depends(get_db), user=Depends(get_current_user),
):
    """Every transaction credited to any tenure carrying this stem.

    Returns one row per property with lat/lng for mapping. Aggregates
    across all contacts who have a tenure on this stem.
    """
    # Are there any tenures on this stem at all?
    n_tenures = db.execute(
        "SELECT COUNT(*) AS n FROM contact_brand_tenures WHERE brand_stem = ?",
        (stem,),
    ).fetchone()["n"]
    if n_tenures == 0:
        raise HTTPException(status_code=404, detail="Stem has no tenures")

    # Aggregate transactions: any sale where (a) a contact with a tenure on this
    # stem appears on either side AND (b) sale_date falls in that tenure's
    # inferred window AND (c) the side either carries the stem explicitly or
    # is at the tenure's dominant_address_unit.
    rows = db.execute(
        """
        SELECT DISTINCT t.source_id, t.sale_date, t.sale_price,
               t.display_address, t.city, t.property_id,
               p.lat, p.lng, p.asset_class
        FROM contact_brand_tenures cbt
        JOIN contacts c ON c.name_fingerprint = cbt.contact_fingerprint
        JOIN transaction_parties tp ON tp.contact_id = c.id
        JOIN transactions t ON t.source_id = tp.source_id
        LEFT JOIN properties p ON p.id = t.property_id
        WHERE cbt.brand_stem = ?
          AND t.sale_date BETWEEN cbt.inferred_start_date AND cbt.inferred_end_date
        """,
        (stem,),
    ).fetchall()

    properties = []
    seen_ids = set()
    for r in rows:
        if r["property_id"] in seen_ids:
            continue
        if r["lat"] is None or r["lng"] is None:
            continue
        seen_ids.add(r["property_id"])
        properties.append({
            "id": r["property_id"],
            "display_address": r["display_address"],
            "city": r["city"],
            "lat": r["lat"], "lng": r["lng"],
            "asset_class": r["asset_class"],
            "most_recent_sale_price": r["sale_price"],
        })
    return {
        "stem": stem,
        "n_transactions": len(rows),
        "properties": properties,
    }


@router.get("/contacts/{contact_id}/property-footprint-tenured")
def contact_property_footprint_tenured(
    contact_id: str, db=Depends(get_db), user=Depends(get_current_user),
):
    """The contact's properties, with each pin's color keyed by the tenure
    it's attributed to. Mirrors /api/contacts/:id/properties shape but adds
    a `tenure_stem` and `inferred` field per pin.
    """
    fp = _resolve_fingerprint(db, contact_id)
    if not fp:
        raise HTTPException(status_code=404, detail="Contact not found")

    # Reuse the per-transaction attribution rule from contact_detail. We need
    # the contact's tenures + their sides' info.
    tenures = [dict(r) for r in db.execute(
        """
        SELECT brand_stem, inferred_start_date, inferred_end_date,
               dominant_address_unit, n_party_sides_inferred
        FROM contact_brand_tenures WHERE contact_fingerprint = ?
        ORDER BY inferred_end_date DESC
        """,
        (fp,),
    ).fetchall()]

    side_addr: dict = {}
    for r in db.execute(
        """
        SELECT pf.source_id, pf.side, pf.city,
               COALESCE(pf.street_number,'') AS sn,
               COALESCE(pf.street_name,'') AS st,
               COALESCE(pf.street_suffix,'') AS sx,
               COALESCE(pf.street_direction,'') AS sd,
               COALESCE(pf.suite_type,'') AS suite_t,
               COALESCE(pf.suite_number,'') AS suite_n
        FROM party_fingerprints pf WHERE pf.contact_fingerprint = ?
        """,
        (fp,),
    ).fetchall():
        side_addr[(r["source_id"], r["side"])] = "|".join([
            (r["city"] or "").lower(), r["sn"], (r["st"] or "").lower(),
            (r["sx"] or "").lower(), (r["sd"] or "").lower(),
            (r["suite_t"] or "").lower(), r["suite_n"],
        ])

    side_stems: dict = {}
    for r in db.execute(
        """
        SELECT pa.source_id, pa.side, m.stem
        FROM party_atoms pa
        JOIN brand_stem_phrase_map m ON m.phrase = pa.atom_value
        JOIN party_fingerprints pf ON pf.source_id = pa.source_id AND pf.side = pa.side
        WHERE pa.atom_type='brand_phrase'
          AND pa.source_field IN ('trade_name','care_of','companies_json')
          AND pf.contact_fingerprint = ?
        """,
        (fp,),
    ).fetchall():
        side_stems.setdefault((r["source_id"], r["side"]), set()).add(r["stem"])

    rows = db.execute(
        """
        SELECT t.source_id, tp.side, t.sale_date, t.sale_price,
               t.display_address, t.city, t.property_id,
               p.lat, p.lng, p.asset_class
        FROM transaction_parties tp
        JOIN transactions t ON t.source_id = tp.source_id
        LEFT JOIN properties p ON p.id = t.property_id
        WHERE tp.contact_id = ?
        """,
        (contact_id,),
    ).fetchall()

    properties = []
    seen = set()
    for r in rows:
        if r["property_id"] in seen or r["lat"] is None or r["lng"] is None:
            continue
        seen.add(r["property_id"])
        sid_key = (r["source_id"], r["side"])
        attribution = None
        if r["sale_date"]:
            for t in tenures:
                if not (t["inferred_start_date"] <= r["sale_date"] <= t["inferred_end_date"]):
                    continue
                explicit = t["brand_stem"] in side_stems.get(sid_key, set())
                addr_match = (
                    t.get("dominant_address_unit") is not None
                    and side_addr.get(sid_key) == t["dominant_address_unit"]
                )
                if explicit or addr_match:
                    attribution = {"brand_stem": t["brand_stem"], "inferred": not explicit}
                    break
        properties.append({
            "id": r["property_id"],
            "display_address": r["display_address"],
            "city": r["city"],
            "lat": r["lat"], "lng": r["lng"],
            "asset_class": r["asset_class"],
            "most_recent_sale_price": r["sale_price"],
            "tenure_stem": (attribution or {}).get("brand_stem"),
            "inferred": (attribution or {}).get("inferred", False),
        })
    return {"properties": properties}
```

- [ ] **Step 4: Register the router in `cleo/web/app.py`**

In `cleo/web/app.py`, add the import alongside the others:

```python
from .routes.contact_tenures import router as contact_tenures_router
```

And register it. Note: this router declares paths under both `/contacts/...` and `/companies/...`, so we register **without** a prefix (or with an empty prefix) and prepend `/api`:

```python
    app.include_router(contact_tenures_router, prefix="/api", tags=["contact-tenures"])
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
python3 -m pytest tests/test_routes_contacts_tenures.py -v
```

Expected: ALL 7 tests PASS (4 from Task 7 + 3 new).

- [ ] **Step 6: Commit**

```bash
git add cleo/web/routes/contact_tenures.py cleo/web/app.py tests/test_routes_contacts_tenures.py
git commit -m "$(cat <<'EOF'
feat(api): tenure detail drawer + portfolio footprint endpoints

- GET /api/contacts/:id/tenures/:stem — single endpoint backing the
  Tenure Detail drawer. Returns top phrases, source-field breakdown,
  strict + inferred dates, linked auto_group, and credited
  transactions list with explicit-vs-inferred attribution.
- GET /api/companies/:stem/portfolio-footprint — aggregates every
  transaction credited to any tenure on this stem; powers the hero map
  shown when current_employer is identified.
- GET /api/contacts/:id/property-footprint-tenured — the contact's
  pins with tenure_stem + inferred flag for color coding.

Single endpoint per drawer (not split) — drawer renders all sections
at once; round-trip overhead of split endpoints is wasted.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: Frontend types

**Files:**
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Add the new interfaces**

In `frontend/src/types/index.ts`, add the following types. Place them in the Contacts section (near `ContactDetail` around line 382):

```typescript
// ── Tenure types ──

export interface TenurePhrase {
  phrase: string;
  n: number;
}

export interface CareerHistoryRow {
  brand_stem: string;
  display_name: string;
  is_active: number;
  strict_start_date: string;
  strict_end_date: string;
  inferred_start_date: string;
  inferred_end_date: string;
  n_party_sides_strict: number;
  n_party_sides_inferred: number;
  n_transactions_credited: number;
  top_phrases: TenurePhrase[];
  source_field_breakdown: Record<string, number>;
  dominant_address_unit: string | null;
  auto_group_id: string | null;
}

export interface CurrentEmployer {
  source: "linkedin" | "linkedin_confirmed" | "linkedin_diverges" | "realtrack";
  company: string | null;
  title: string | null;
  brand_stem: string | null;
  display_name: string | null;
  realtrack_stem?: string;
  realtrack_display_name?: string;
}

export interface TenureTag {
  state: "active" | "stale";
  stem: string | null;
  display_name: string | null;
  last_seen?: string;
  since?: string;
}

export interface AddressTenureTag {
  address_unit: string;
  first_seen: string;
  last_seen: string;
  tag: TenureTag | null;
}

export interface ContactTransactionWithTenure extends ContactTransaction {
  tenure: { brand_stem: string; display_name: string; inferred: boolean } | null;
}

// ── Tenure Detail drawer ──

export interface CreditedTransaction {
  source_id: string;
  side: string;
  sale_date: string;
  sale_price: number | null;
  display_address: string;
  city: string;
  brand_phrase: string | null;
  source_field: string | null;
  inferred: boolean;
}

export interface TenureDetail {
  brand_stem: string;
  display_name: string;
  is_active: number;
  strict_start_date: string;
  strict_end_date: string;
  inferred_start_date: string;
  inferred_end_date: string;
  n_party_sides_strict: number;
  n_party_sides_inferred: number;
  top_phrases: TenurePhrase[];
  source_field_breakdown: Record<string, number>;
  dominant_address_unit: string | null;
  auto_group_id: string | null;
  auto_group_display_name: string | null;
  credited_transactions: CreditedTransaction[];
}

// ── Portfolio footprint ──

export interface PortfolioFootprintProperty {
  id: string;
  display_address: string;
  city: string;
  lat: number;
  lng: number;
  asset_class: string | null;
  most_recent_sale_price: number | null;
}

export interface PortfolioFootprintResponse {
  stem: string;
  n_transactions: number;
  properties: PortfolioFootprintProperty[];
}

export interface TenuredFootprintProperty extends PortfolioFootprintProperty {
  tenure_stem: string | null;
  inferred: boolean;
}

export interface TenuredFootprintResponse {
  properties: TenuredFootprintProperty[];
}
```

Then extend the existing `ContactDetail` interface (line 382). Add **after** `work_history: WorkHistoryPosition[];`:

```typescript
  career_history: CareerHistoryRow[];
  current_employer: CurrentEmployer | null;
  phone_tenure_tag: TenureTag | null;
  address_tenure_tags: AddressTenureTag[];
```

And change the `transactions` field on `ContactDetail` from `ContactTransaction[]` to `ContactTransactionWithTenure[]`.

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```

Expected: PASS (no type errors).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "$(cat <<'EOF'
types(frontend): tenure types for Contact page redesign

Adds CareerHistoryRow, CurrentEmployer, TenureTag, AddressTenureTag,
TenureDetail, PortfolioFootprintProperty, and the wrapper response
shapes. Extends ContactDetail with career_history, current_employer,
phone_tenure_tag, address_tenure_tags. Transactions now carry a
per-row tenure attribution.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 10: Frontend — `CurrentEmployerPill` component

**Files:**
- Create: `frontend/src/components/contact/CurrentEmployerPill.tsx`

- [ ] **Step 1: Create the file (no test — small visual component)**

Create `frontend/src/components/contact/CurrentEmployerPill.tsx`:

```tsx
import { Badge } from "@radix-ui/themes";
import { LinkedinLogo, Buildings, WarningCircle } from "@phosphor-icons/react";
import type { CurrentEmployer } from "../../types";

export default function CurrentEmployerPill({
  employer,
}: {
  employer: CurrentEmployer | null;
}) {
  if (!employer) return null;

  const labelText = employer.display_name || employer.company || "—";

  if (employer.source === "linkedin_confirmed") {
    return (
      <Badge color="jade" variant="soft" size="2">
        <LinkedinLogo size={12} weight="fill" />
        {labelText} · LinkedIn-confirmed
      </Badge>
    );
  }

  if (employer.source === "linkedin_diverges") {
    return (
      <Badge color="amber" variant="soft" size="2">
        <LinkedinLogo size={12} weight="fill" />
        {labelText}
        <WarningCircle size={12} />
        diverges from Realtrack
      </Badge>
    );
  }

  if (employer.source === "linkedin") {
    return (
      <Badge color="jade" variant="soft" size="2">
        <LinkedinLogo size={12} weight="fill" />
        {labelText}
      </Badge>
    );
  }

  // realtrack
  return (
    <Badge color="gray" variant="soft" size="2">
      <Buildings size={12} />
      {labelText}
    </Badge>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/contact/CurrentEmployerPill.tsx
git commit -m "$(cat <<'EOF'
feat(frontend): CurrentEmployerPill component

Renders the four header-pill states (LinkedIn-confirmed jade,
LinkedIn-only jade, LinkedIn-diverges amber, Realtrack-derived slate)
per spec §3 header.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 11: Frontend — `CareerHistoryTile` component

**Files:**
- Create: `frontend/src/components/contact/CareerHistoryTile.tsx`

- [ ] **Step 1: Create the component**

Create `frontend/src/components/contact/CareerHistoryTile.tsx`:

```tsx
import { Text, Badge, Button } from "@radix-ui/themes";
import { LinkedinLogo, Buildings, MapPin } from "@phosphor-icons/react";
import type { CareerHistoryRow, WorkHistoryPosition } from "../../types";
import { formatDate } from "../../lib/utils";

interface ReconciledRow {
  // From CareerHistoryRow when matched
  brand_stem: string | null;
  // Display strings
  display_name: string;
  date_range: string;
  duration: string | null;
  // Source pills
  has_linkedin: boolean;
  has_realtrack: boolean;
  // Realtrack metadata (when applicable)
  n_transactions_credited: number;
  is_active: boolean;
  dominant_address_unit: string | null;
  // LinkedIn metadata (when applicable)
  title: string | null;
  // Click target — whichever side has it
  brand_stem_for_click: string | null;
}

function formatYear(d: string | null): string {
  if (!d) return "?";
  return d.slice(0, 4);
}

function formatRange(start: string | null, end: string | null, isCurrent: boolean): string {
  const startStr = formatYear(start);
  const endStr = isCurrent ? "Present" : formatYear(end);
  return `${startStr} – ${endStr}`;
}

function durationStr(start: string | null, end: string | null, isCurrent: boolean): string | null {
  if (!start) return null;
  const sd = new Date(start);
  const ed = isCurrent ? new Date() : end ? new Date(end) : null;
  if (!ed) return null;
  const months = (ed.getFullYear() - sd.getFullYear()) * 12 + (ed.getMonth() - sd.getMonth());
  if (months < 12) return `${months} mo`;
  const years = Math.floor(months / 12);
  const rem = months % 12;
  return rem > 0 ? `${years} yr ${rem} mo` : `${years} yr`;
}

function reconcile(
  realtrack: CareerHistoryRow[],
  linkedIn: WorkHistoryPosition[],
): ReconciledRow[] {
  const out: ReconciledRow[] = [];
  const usedRtStems = new Set<string>();

  // 1) For each LinkedIn position, try to find a matching realtrack tenure by
  //    substring containment of stem in lowercased company.
  for (const li of linkedIn) {
    const liCompanyLower = (li.company || "").toLowerCase();
    const matchRt = realtrack.find(
      (rt) => !usedRtStems.has(rt.brand_stem) && liCompanyLower.includes(rt.brand_stem),
    );
    if (matchRt) usedRtStems.add(matchRt.brand_stem);
    out.push({
      brand_stem: matchRt?.brand_stem ?? null,
      display_name: li.company || matchRt?.display_name || "—",
      date_range: formatRange(li.start_date, li.end_date, li.is_current),
      duration: durationStr(li.start_date, li.end_date, li.is_current),
      has_linkedin: true,
      has_realtrack: !!matchRt,
      n_transactions_credited: matchRt?.n_transactions_credited ?? 0,
      is_active: li.is_current || matchRt?.is_active === 1,
      dominant_address_unit: matchRt?.dominant_address_unit ?? null,
      title: li.title,
      brand_stem_for_click: matchRt?.brand_stem ?? null,
    });
  }

  // 2) Realtrack tenures with no matching LinkedIn position — append.
  for (const rt of realtrack) {
    if (usedRtStems.has(rt.brand_stem)) continue;
    out.push({
      brand_stem: rt.brand_stem,
      display_name: rt.display_name,
      date_range: formatRange(rt.inferred_start_date, rt.inferred_end_date, rt.is_active === 1),
      duration: durationStr(rt.inferred_start_date, rt.inferred_end_date, rt.is_active === 1),
      has_linkedin: false,
      has_realtrack: true,
      n_transactions_credited: rt.n_transactions_credited,
      is_active: rt.is_active === 1,
      dominant_address_unit: rt.dominant_address_unit,
      title: null,
      brand_stem_for_click: rt.brand_stem,
    });
  }

  return out;
}

interface Props {
  realtrack: CareerHistoryRow[];
  linkedIn: WorkHistoryPosition[];
  totalSpvCount?: number;
  onRowClick: (stem: string) => void;
  onViewSpvs?: () => void;
}

export default function CareerHistoryTile({
  realtrack, linkedIn, totalSpvCount, onRowClick, onViewSpvs,
}: Props) {
  const rows = reconcile(realtrack, linkedIn);

  if (rows.length === 0) {
    return (
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
        <Text size="3" weight="medium" className="mb-2 block">Career History</Text>
        <Text size="2" style={{ color: "var(--gray-9)" }}>
          No career history yet. Add a LinkedIn profile or wait for the next
          discovery rebuild.
        </Text>
      </div>
    );
  }

  return (
    <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
      <div className="flex items-center justify-between mb-3">
        <Text size="3" weight="medium">Career History ({rows.length})</Text>
      </div>
      <div className="flex flex-col gap-4">
        {rows.map((r, i) => (
          <button
            key={`${r.brand_stem ?? r.display_name}-${i}`}
            onClick={() => r.brand_stem_for_click && onRowClick(r.brand_stem_for_click)}
            disabled={!r.brand_stem_for_click}
            className="text-left flex flex-col gap-1 hover:bg-[var(--gray-a2)] rounded p-2 -m-2 disabled:cursor-default disabled:hover:bg-transparent"
          >
            <div className="flex items-center gap-2">
              <span
                className="inline-block w-2 h-2 rounded-full"
                style={{
                  backgroundColor: r.is_active ? "var(--jade-9)" : "var(--gray-7)",
                }}
              />
              <Text size="2" weight="medium">
                {r.title ? `${r.title} · ` : ""}{r.display_name}
              </Text>
              {r.is_active && (
                <Badge size="1" color="jade" variant="soft">Current</Badge>
              )}
            </div>
            <Text size="1" style={{ color: "var(--gray-9)" }}>
              {r.date_range}{r.duration ? ` · ${r.duration}` : ""}
            </Text>
            <div className="flex flex-wrap gap-1 mt-1">
              {r.has_linkedin && (
                <Badge size="1" color="jade" variant="soft">
                  <LinkedinLogo size={10} weight="fill" /> via LinkedIn
                </Badge>
              )}
              {r.has_realtrack && (
                <Badge size="1" color="gray" variant="soft">
                  <Buildings size={10} /> via Realtrack · {r.n_transactions_credited} transactions credited
                </Badge>
              )}
            </div>
            {r.dominant_address_unit && (
              <div className="flex items-center gap-1 mt-0.5">
                <MapPin size={11} style={{ color: "var(--gray-8)" }} />
                <Text size="1" style={{ color: "var(--gray-9)" }}>
                  {r.dominant_address_unit.split("|").slice(1, 5).filter(Boolean).join(" ")} · primary address during this tenure
                </Text>
              </div>
            )}
          </button>
        ))}
      </div>
      {totalSpvCount !== undefined && totalSpvCount > 0 && (
        <button
          onClick={onViewSpvs}
          className="mt-3 text-[13px] no-underline"
          style={{ color: "var(--accent-11)" }}
        >
          View {totalSpvCount} SPVs credited to these tenures →
        </button>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/contact/CareerHistoryTile.tsx
git commit -m "$(cat <<'EOF'
feat(frontend): CareerHistoryTile component

Reconciles LinkedIn work_history with realtrack career_history into a
single chronological list. Matches by stem-substring-in-company; rows
that match render both source pills, rows that don't render only the
source they came from. Each row is clickable when a brand_stem is
present (opens the tenure detail drawer).

Replaces both the "Group" card and "Affiliated Groups" panel on the
Contact page (per spec §3 left column).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 12: Frontend — `TenureDetailDrawer` component

**Files:**
- Create: `frontend/src/components/contact/TenureDetailDrawer.tsx`

- [ ] **Step 1: Create the drawer**

Create `frontend/src/components/contact/TenureDetailDrawer.tsx`:

```tsx
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Text, Heading, Badge, Button } from "@radix-ui/themes";
import { X } from "@phosphor-icons/react";
import { fetchApi } from "../../api/client";
import { formatCurrency, formatDate } from "../../lib/utils";
import type { TenureDetail } from "../../types";

interface Props {
  contactId: string;
  stem: string | null;
  onClose: () => void;
}

export default function TenureDetailDrawer({ contactId, stem, onClose }: Props) {
  const [data, setData] = useState<TenureDetail | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!stem) return;
    setLoading(true);
    setData(null);
    fetchApi<TenureDetail>(`/contacts/${contactId}/tenures/${encodeURIComponent(stem)}`)
      .then((d) => setData(d))
      .finally(() => setLoading(false));
  }, [contactId, stem]);

  if (!stem) return null;

  return (
    <>
      <div
        className="fixed inset-0 z-40 bg-black/30"
        onClick={onClose}
      />
      <div
        className="fixed top-0 right-0 z-50 w-[560px] max-w-[90vw] h-screen bg-white shadow-xl border-l border-[var(--gray-6)] flex flex-col"
      >
        <div className="flex items-center justify-between p-4 border-b border-[var(--gray-6)]">
          <Heading size="3" weight="medium">
            {data?.display_name ?? stem}
          </Heading>
          <Button size="1" variant="ghost" onClick={onClose}>
            <X size={16} />
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto p-5 flex flex-col gap-5">
          {loading && <Text size="2">Loading...</Text>}
          {data && (
            <>
              <div>
                <Text size="2" style={{ color: "var(--gray-9)" }}>
                  {formatDate(data.inferred_start_date)} – {formatDate(data.inferred_end_date)}
                  {" "}· {data.credited_transactions.length} deals credited (Realtrack)
                </Text>
              </div>

              {/* Why we named this tenure */}
              <section>
                <Text size="2" weight="medium" className="block mb-2">Why we named this tenure</Text>
                <Text size="1" style={{ color: "var(--gray-9)" }} className="block mb-1">Top phrases:</Text>
                <ul className="text-[13px] mb-3">
                  {data.top_phrases.map((tp, i) => (
                    <li key={i} className="flex justify-between">
                      <span>{tp.phrase}</span>
                      <span style={{ color: "var(--gray-9)" }}>{tp.n}×</span>
                    </li>
                  ))}
                </ul>
                <Text size="1" style={{ color: "var(--gray-9)" }} className="block mb-1">Source field breakdown:</Text>
                <ul className="text-[13px]">
                  {Object.entries(data.source_field_breakdown).map(([k, v]) => (
                    <li key={k} className="flex justify-between">
                      <span>{k}</span>
                      <span style={{ color: "var(--gray-9)" }}>{v}</span>
                    </li>
                  ))}
                </ul>
              </section>

              {/* Window */}
              <section>
                <Text size="2" weight="medium" className="block mb-2">Window</Text>
                <div className="text-[13px] flex flex-col gap-1">
                  <div className="flex justify-between">
                    <span>Earliest explicit mention:</span>
                    <span>{formatDate(data.strict_start_date)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Inferred start (via address):</span>
                    <span>{formatDate(data.inferred_start_date)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Latest:</span>
                    <span>{formatDate(data.inferred_end_date)}</span>
                  </div>
                  {data.dominant_address_unit && (
                    <div className="flex justify-between">
                      <span>Dominant address:</span>
                      <span style={{ color: "var(--gray-9)" }}>
                        {data.dominant_address_unit.split("|").slice(1, 5).filter(Boolean).join(" ")}
                      </span>
                    </div>
                  )}
                </div>
              </section>

              {/* Linked auto_group */}
              {data.auto_group_id && (
                <section>
                  <Text size="2" weight="medium" className="block mb-2">Linked auto_group</Text>
                  <Link
                    to={`/explorer/auto-groups/${data.auto_group_id}`}
                    className="no-underline"
                    style={{ color: "var(--accent-11)" }}
                  >
                    {data.auto_group_id} — {data.auto_group_display_name ?? "(unnamed)"}
                  </Link>
                </section>
              )}

              {/* Credited transactions */}
              <section>
                <Text size="2" weight="medium" className="block mb-2">
                  Credited transactions ({data.credited_transactions.length})
                </Text>
                <table className="w-full text-[13px]">
                  <thead>
                    <tr className="border-b border-[var(--gray-4)]">
                      <th className="text-left py-1 text-[11px] font-medium" style={{ color: "var(--gray-9)" }}>Date</th>
                      <th className="text-left py-1 text-[11px] font-medium" style={{ color: "var(--gray-9)" }}>Address</th>
                      <th className="text-right py-1 text-[11px] font-medium" style={{ color: "var(--gray-9)" }}>Price</th>
                      <th className="text-left py-1 text-[11px] font-medium" style={{ color: "var(--gray-9)" }}>Source</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.credited_transactions.map((t) => (
                      <tr key={t.source_id} className="border-b border-[var(--gray-4)]">
                        <td className="py-1">{formatDate(t.sale_date)}</td>
                        <td className="py-1">{t.display_address}</td>
                        <td className="py-1 text-right">{formatCurrency(t.sale_price)}</td>
                        <td className="py-1">
                          {t.inferred ? (
                            <Badge size="1" color="amber" variant="soft">via address</Badge>
                          ) : (
                            <Badge size="1" color="jade" variant="soft">{t.source_field}</Badge>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
            </>
          )}
        </div>
      </div>
    </>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/contact/TenureDetailDrawer.tsx
git commit -m "$(cat <<'EOF'
feat(frontend): TenureDetailDrawer component

Side drawer that fetches /api/contacts/:id/tenures/:stem and renders
the full audit-trail surface per spec §3 Tenure Detail drawer:
- Why we named this tenure (top phrases + source-field breakdown)
- Window (strict vs inferred start dates + dominant address)
- Linked auto_group (when present, with click-through)
- Credited transactions (date / address / price / source pill)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 13: Frontend — Portfolio footprint maps

**Files:**
- Create: `frontend/src/components/contact/PortfolioFootprintMap.tsx`
- Create: `frontend/src/components/contact/TenuredPropertyFootprintMap.tsx`

- [ ] **Step 1: Inspect `PropertyMiniMap` props**

Open `frontend/src/components/ui/PropertyMiniMap.tsx`. Confirm the prop shape — `properties: MiniMapProperty[]`, `height: number`, optional `onPropertyClick`. The map already supports rendering pins from lat/lng + asset_class. Color coding by tenure is added by passing a custom pin color via a wrapper component (rather than modifying `PropertyMiniMap`'s public API).

- [ ] **Step 2: Create the hero portfolio map**

Create `frontend/src/components/contact/PortfolioFootprintMap.tsx`:

```tsx
import { useEffect, useState } from "react";
import { Text } from "@radix-ui/themes";
import { fetchApi } from "../../api/client";
import PropertyMiniMap from "../ui/PropertyMiniMap";
import type { PortfolioFootprintResponse, MiniMapProperty } from "../../types";

interface Props {
  stem: string;
  displayName: string;
  height?: number;
}

export default function PortfolioFootprintMap({ stem, displayName, height = 380 }: Props) {
  const [data, setData] = useState<PortfolioFootprintResponse | null>(null);

  useEffect(() => {
    fetchApi<PortfolioFootprintResponse>(
      `/companies/${encodeURIComponent(stem)}/portfolio-footprint`,
    ).then(setData);
  }, [stem]);

  if (!data) return null;
  const props: MiniMapProperty[] = data.properties.map((p) => ({
    id: p.id,
    display_address: p.display_address,
    city: p.city,
    lat: p.lat,
    lng: p.lng,
    asset_class: p.asset_class,
    most_recent_sale_price: p.most_recent_sale_price,
  }));

  return (
    <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
      <Text size="3" weight="medium" className="mb-3 block">
        {displayName} Portfolio ({data.n_transactions} transactions)
      </Text>
      <PropertyMiniMap properties={props} height={height} />
    </div>
  );
}
```

- [ ] **Step 3: Create the tenure-colored property footprint**

Create `frontend/src/components/contact/TenuredPropertyFootprintMap.tsx`:

```tsx
import { useEffect, useState, useMemo } from "react";
import { Text, Badge } from "@radix-ui/themes";
import { fetchApi } from "../../api/client";
import PropertyMiniMap from "../ui/PropertyMiniMap";
import type { TenuredFootprintResponse, MiniMapProperty } from "../../types";

const TENURE_COLORS = ["var(--jade-9)", "var(--blue-9)", "var(--purple-9)", "var(--orange-9)"];
const UNATTRIBUTED_COLOR = "var(--gray-7)";

interface Props {
  contactId: string;
  height?: number;
}

export default function TenuredPropertyFootprintMap({ contactId, height = 280 }: Props) {
  const [data, setData] = useState<TenuredFootprintResponse | null>(null);

  useEffect(() => {
    fetchApi<TenuredFootprintResponse>(
      `/contacts/${contactId}/property-footprint-tenured`,
    ).then(setData);
  }, [contactId]);

  // Build a stem → color map from the (sorted) set of stems present.
  const stemColors = useMemo(() => {
    if (!data) return {} as Record<string, string>;
    const stems = Array.from(new Set(
      data.properties.map((p) => p.tenure_stem).filter((s): s is string => !!s),
    )).sort();
    const m: Record<string, string> = {};
    stems.forEach((s, i) => { m[s] = TENURE_COLORS[i % TENURE_COLORS.length]; });
    return m;
  }, [data]);

  if (!data) return null;

  // PropertyMiniMap doesn't accept per-pin colors today. We render a legend
  // here and pass the properties through; the visual color coding is a
  // future PR (or a small extension to PropertyMiniMap to read pin_color
  // from the property objects).
  const props: MiniMapProperty[] = data.properties.map((p) => ({
    id: p.id,
    display_address: p.display_address,
    city: p.city,
    lat: p.lat,
    lng: p.lng,
    asset_class: p.asset_class,
    most_recent_sale_price: p.most_recent_sale_price,
  }));

  return (
    <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
      <Text size="3" weight="medium" className="mb-3 block">
        Property Footprint ({data.properties.length})
      </Text>
      <PropertyMiniMap properties={props} height={height} />
      {Object.keys(stemColors).length > 0 && (
        <div className="flex flex-wrap gap-2 mt-3">
          {Object.entries(stemColors).map(([stem, color]) => (
            <Badge key={stem} size="1" variant="soft" style={{ color }}>
              ● {stem}
            </Badge>
          ))}
          <Badge size="1" variant="soft" style={{ color: UNATTRIBUTED_COLOR }}>
            ● unattributed
          </Badge>
        </div>
      )}
    </div>
  );
}
```

Note: per-pin coloring on the existing `PropertyMiniMap` requires a follow-up extension to that component. This task ships the legend + the data fetching; the actual pin colorization can be added by extending `PropertyMiniMap` to read a `pin_color` field on its property prop. Document this as a known follow-up at the bottom of the task.

- [ ] **Step 4: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/contact/PortfolioFootprintMap.tsx frontend/src/components/contact/TenuredPropertyFootprintMap.tsx
git commit -m "$(cat <<'EOF'
feat(frontend): PortfolioFootprintMap + TenuredPropertyFootprintMap

PortfolioFootprintMap fetches /companies/:stem/portfolio-footprint for
the hero spot when current_employer is identified.
TenuredPropertyFootprintMap fetches the contact's pins with tenure
attribution and renders a legend mapping stems to colors.

Per-pin colorization is a known follow-up — requires extending
PropertyMiniMap to honor a pin_color field. Pin colors are computed
in the wrapper today; map markers all render in the default color.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 14: Frontend — Restructure `ContactDetailPage`

**Files:**
- Modify: `frontend/src/pages/ContactDetailPage.tsx`

This is the load-bearing UI change. We restructure the existing page to:
- Add the header pill.
- Replace the "Group" + "Affiliated Groups" cards with `CareerHistoryTile`.
- Add tenure tags to the Phone and Address rows of Contact Info.
- Add `Tenure` column to Transaction History.
- Add the right-column hero (PortfolioFootprintMap when current_employer is identified).
- Mount the TenureDetailDrawer.

- [ ] **Step 1: Update imports and add drawer state**

Open `frontend/src/pages/ContactDetailPage.tsx`. Add to the imports section near the top:

```tsx
import CurrentEmployerPill from "../components/contact/CurrentEmployerPill";
import CareerHistoryTile from "../components/contact/CareerHistoryTile";
import TenureDetailDrawer from "../components/contact/TenureDetailDrawer";
import PortfolioFootprintMap from "../components/contact/PortfolioFootprintMap";
import TenuredPropertyFootprintMap from "../components/contact/TenuredPropertyFootprintMap";
```

Inside `ContactDetailPage`, after `const [promoteStatus, setPromoteStatus] = useState(...)`, add:

```tsx
  const [drawerStem, setDrawerStem] = useState<string | null>(null);
```

- [ ] **Step 2: Add the header pill**

Replace the `{contact.company_name && (...)}` block (around line 119–121) with:

```tsx
        {contact.current_employer ? (
          <div className="mt-1">
            <CurrentEmployerPill employer={contact.current_employer} />
          </div>
        ) : contact.company_name ? (
          <Text size="2" style={{ color: "var(--gray-9)" }}>{contact.company_name}</Text>
        ) : null}
```

- [ ] **Step 3: Add tenure tags to Phone and Address rows**

In the Contact Info card (around line 153–165 — the `Phone` row block), update the phone display to include the tag:

```tsx
              <div>
                <Text size="1" style={{ color: "var(--gray-9)" }}>Phone</Text>
                {editing ? (
                  <TextField.Root size="1" value={editFields.phone} onChange={(e: any) => setEditFields({ ...editFields, phone: e.target.value })} />
                ) : (
                  contact.phone ? (
                    <div className="flex items-center gap-2">
                      <a href={`tel:${contact.phone}`} className="no-underline" style={{ color: "var(--accent-11)" }}>
                        {formatPhone(contact.phone)}
                      </a>
                      {contact.phone_tenure_tag && (
                        <Badge
                          size="1"
                          color={contact.phone_tenure_tag.state === "active" ? "jade" : "gray"}
                          variant="soft"
                        >
                          {contact.phone_tenure_tag.state === "active"
                            ? `Active · ${contact.phone_tenure_tag.display_name} since ${(contact.phone_tenure_tag.since || "").slice(0, 4)}`
                            : `Last seen ${(contact.phone_tenure_tag.last_seen || "").slice(0, 10)}${contact.phone_tenure_tag.display_name ? ` · ${contact.phone_tenure_tag.display_name} era` : ""}`}
                        </Badge>
                      )}
                    </div>
                  ) : <Text size="2" className="block">—</Text>
                )}
              </div>
```

Address tags can be rendered after the address rows by mapping over `contact.address_tenure_tags`. For V1 we surface them in the Contact Info card as a small subsection. After the existing job_title row, append:

```tsx
              {contact.address_tenure_tags && contact.address_tenure_tags.length > 0 && (
                <div>
                  <Text size="1" style={{ color: "var(--gray-9)" }}>Mailing Addresses</Text>
                  <div className="flex flex-col gap-1.5 mt-1">
                    {contact.address_tenure_tags.map((a, i) => (
                      <div key={i} className="flex items-center justify-between gap-2 text-[13px]">
                        <span>{a.address_unit.split("|").slice(1, 5).filter(Boolean).join(" ")}</span>
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

- [ ] **Step 4: Replace the "Group" + "Affiliated Groups" cards with CareerHistoryTile**

Delete:
- The `{/* Group Association */}` block (lines ~221–246).
- The `{/* Affiliated Groups */}` block (lines ~247–281).
- The `{/* Career History (from LinkedIn enrichment) */}` block (lines ~283–286 — the `CareerTimeline` import and call).

Replace **all three** with a single CareerHistoryTile invocation in the same position (after the Datanyze card, before the Stats card):

```tsx
          <CareerHistoryTile
            realtrack={contact.career_history}
            linkedIn={contact.work_history}
            totalSpvCount={affiliatedGroups.length}
            onRowClick={(stem) => setDrawerStem(stem)}
            onViewSpvs={() => setShowConsolidate(true)}
          />
```

The `CareerTimeline` import at the top of the file can be removed since it's no longer used.

- [ ] **Step 5: Update right column hero based on current_employer**

Replace the Property Footprint Map block (around lines 314–328) with this branching logic:

```tsx
        {/* Right: Hero map + Property Footprint + Transactions */}
        <div className="col-span-2 flex flex-col gap-6">
          {contact.current_employer && contact.current_employer.brand_stem ? (
            <>
              <PortfolioFootprintMap
                stem={contact.current_employer.brand_stem}
                displayName={contact.current_employer.display_name || contact.current_employer.brand_stem}
                height={380}
              />
              <TenuredPropertyFootprintMap
                contactId={contact.id}
                height={260}
              />
            </>
          ) : (
            propertyHistory.length > 0 && (
              <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
                <Text size="3" weight="medium" className="mb-3 block">
                  Property Footprint ({propertyHistory.length})
                </Text>
                <PropertyMiniMap
                  properties={propertyHistory}
                  height={300}
                  onPropertyClick={(pid) => navigate(`/properties/${pid}`)}
                />
              </div>
            )
          )}
          {/* Transaction History block goes here — see Step 6 */}
        </div>
```

- [ ] **Step 6: Add Tenure column to Transaction History**

In the Transaction History `<table>` (around line 336), add a column header after `Side`:

```tsx
                      <th className="text-left py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Tenure</th>
```

And add a corresponding cell in each row, after the Side cell:

```tsx
                        <td className="py-2">
                          {t.tenure ? (
                            <Badge size="1" variant="soft" color="jade">
                              {t.tenure.brand_stem}
                              {t.tenure.inferred && " (i)"}
                            </Badge>
                          ) : null}
                        </td>
```

- [ ] **Step 7: Mount the drawer**

At the very bottom of the JSX (after the existing `{showBuyMandateDialog && ...}` block, before the closing `</div>`):

```tsx
      <TenureDetailDrawer
        contactId={contact.id}
        stem={drawerStem}
        onClose={() => setDrawerStem(null)}
      />
```

- [ ] **Step 8: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```

Expected: PASS.

- [ ] **Step 9: Smoke-test the page in the browser**

Start backend and frontend:

```bash
# Terminal 1
uvicorn cleo.web.app:app --reload --port 8099

# Terminal 2
cd frontend && npm run dev
```

In the browser, visit http://localhost:5174/contacts/CON_07049 (Paul Braun). Verify:
- Header shows "CanFirst Capital Management" pill (jade if LinkedIn is imported and stems agree, else slate).
- Phone row shows "Active · CanFirst since 2008" (or similar) tag if Paul's phone has an active overlap.
- Career History tile shows two rows: CanFirst (Current) and Dundee (1999–2001).
- Right column hero is the CanFirst Portfolio map (847+ transactions).
- Smaller Property Footprint sits below the hero.
- Transaction History table has a new `Tenure` column.
- Clicking a Career History row opens the side drawer with phrases, breakdown, dates, credited transactions.

If the contact's LinkedIn isn't imported or stems disagree, the pill renders accordingly (slate for realtrack-derived, amber for divergence).

- [ ] **Step 10: Commit**

```bash
git add frontend/src/pages/ContactDetailPage.tsx
git commit -m "$(cat <<'EOF'
feat(frontend): redesigned Contact page with tenure-aware UI

Replaces the broken "Groups (63)" + single "Group" attribution with:
- Header pill (LinkedIn-confirmed / Realtrack-derived / divergence).
- Career History tile (CareerHistoryTile) — reconciles LinkedIn rows
  with realtrack tenures by stem-substring match.
- Tenure tags on Contact Info phone + mailing addresses.
- Right-column hero: Portfolio Footprint (current employer's full
  portfolio) when current_employer is identified; Property Footprint
  promotes back to the hero when not.
- Tenure column on Transaction History with (i) suffix for
  address-inferred attributions.
- TenureDetailDrawer mounted at the page level; opens from any
  Career History row.

Spec: docs/superpowers/specs/2026-05-04-contact-tenure-page-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 15: End-to-end verification

- [ ] **Step 1: Run all backend tests**

```bash
python3 -m pytest tests/ -v 2>&1 | tail -40
```

Expected: all pass; no regressions in the existing `test_routes_explorer.py`, `test_discovery_v2_*`, or other suites.

- [ ] **Step 2: Run frontend type-check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: PASS.

- [ ] **Step 3: Run a full Layer 2 rebuild against the production DB**

```bash
python3 -m cleo.discovery_v2 2>&1 | tail -20
```

Expected: ends with the orchestrator summary including `n_tenure_rows`. The full chain should complete in a similar wall-clock to the prior chain (the new builder's queries are aggregations over indexed columns).

Spot-check Paul Braun's tenure rows:

```bash
sqlite3 data/cleo.db "SELECT brand_stem, strict_start_date, strict_end_date, inferred_start_date, inferred_end_date, n_party_sides_strict, n_party_sides_inferred, is_active FROM contact_brand_tenures WHERE contact_fingerprint='paul braun' ORDER BY inferred_end_date DESC;"
```

Expected output: roughly
```
canfirst|2004-07-02|2022-12-13|2002-04-29|2022-12-13|60|80|0
dundee|1999-01-27|2001-06-12|1999-01-27|2001-06-12|8|8|0
```
(`is_active` will be 0 for both because today is 2026-05-04 and 2022-12-13 is more than 730 days ago. If the production DB has more recent CanFirst sides, the canfirst row will be `is_active=1`.)

- [ ] **Step 4: Manual UI smoke test**

Visit http://localhost:5174/contacts/CON_07049 in the browser. Verify the full redesigned layout end-to-end. Test the drawer open/close and the auto_group hyperlink (clicking it should navigate to `/explorer/auto-groups/AGRP_01392`).

Test a contact **without** any tenures — pick a contact with `transaction_count < 5` and no qualifying brand_phrase. Verify:
- No header pill.
- Career History tile shows the empty state ("No career history yet...").
- Property Footprint is the hero (not Portfolio).
- Phone row has no tenure tag.

- [ ] **Step 5: Commit any cleanups**

If small cleanups surfaced during smoke-testing (e.g., minor type tweaks, ordering of cards), commit them with a descriptive message. If the rebuild shows unexpected counts compared to the spec's table, document them in the commit body — small differences are expected since the production DB has more recent data than the spec's snapshot.

```bash
git status
# If clean, no commit needed.
# If dirty:
git add -A
git commit -m "$(cat <<'EOF'
fix(contact-tenures): smoke-test cleanups

[Specific cleanups discovered during the manual verification pass.]

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Out of scope / known follow-ups

These were called out in the spec as V2 or in this plan as deliberate deferrals:

1. **Group/Company page at `/companies/:stem`** (Phase 2 in the spec). The schema and `/api/companies/:stem/portfolio-footprint` endpoint are already forward-compatible — V2 builds the page; V1 only ships the endpoint that the Contact-page hero map already needs.
2. **Per-pin color coding on `PropertyMiniMap`.** The `TenuredPropertyFootprintMap` component computes the stem→color mapping and renders a legend, but `PropertyMiniMap` itself doesn't yet honor a per-pin color. Extending it is a small follow-up (read `pin_color` from `MiniMapProperty` if present, fall back to asset_class color).
3. **Override workflow for incorrect tenure attributions.** Spec Phase 2.
4. **Sub-brand splits** (e.g., H&R REIT vs H&R Group on the same `h&r` stem). Spec Phase 2 — stem-level is sufficient for V1.
5. **Job-title derivation from `companies_json` text patterns.** LinkedIn remains primary; realtrack-derived rows render with no title in V1.
6. **CRM-style override tables (`contact_brand_tenure_overrides`).** Mentioned in the spec ("CRM-style override tables can attach later") — not part of V1.

---

## Self-review notes

This plan was self-reviewed against the spec on 2026-05-04. Coverage check:

| Spec section | Plan task |
|---|---|
| §Architecture — `contact_brand_tenures` table | Task 1 (migration), Tasks 2–5 (builder) |
| §Architecture — `auto_groups` keeps existing job, drops load-bearing role | Task 7 — endpoint reads `auto_group_id` only as a hyperlink target |
| §Architecture — `current_employer` derivation | Task 7 (logic in `contact_detail`) |
| §2a — Stem unification | Task 2 (joins to `brand_stem_phrase_map`) |
| §2b — Anchor-bracketed window | Task 3 |
| §2c — Threshold ≥ 2 party-sides | Task 2 |
| §2d — `is_active` and current_employer | Task 5 (is_active), Task 7 (current_employer) |
| §2e — Deal attribution to tenures | Task 7 (per-row), Task 8 (drawer) |
| §2f — Overlapping tenures | Career History sort by `inferred_end_date DESC` (Task 7), drawer renders all (Task 12) |
| §2g — Tenure-aware contact info | Task 7 (phone_tenure_tag + address_tenure_tags) |
| §3 Header — pill | Task 10 |
| §3 Left — Contact Info card with tags | Task 14 Step 3 |
| §3 Left — Career History tile | Task 11 |
| §3 Right — Portfolio Footprint hero | Task 13, Task 14 Step 5 |
| §3 Right — Property Footprint with color-coded pins | Task 13 (legend), Task 14 Step 5 (display) |
| §3 Right — Tenure column on Transaction History | Task 14 Step 6 |
| §3 — Tenure Detail drawer | Task 8 (endpoint), Task 12 (component), Task 14 Step 7 (mount) |
| Spec deferred Q1 (rebuild cadence) | Resolved up-front; implemented Task 6 |
| Spec deferred Q2 (`dominant_address_unit` storage) | Resolved up-front; column on row in Task 1 |
| Spec deferred Q3 (drawer API shape) | Resolved up-front; single endpoint in Task 8 |

No placeholders remain. Type names are consistent across the type definitions (Task 9), API responses (Tasks 7, 8), and component props (Tasks 10–14). Every task's commit message describes the intent of the change. TDD discipline: each backend task writes failing tests first, runs them, then implements; frontend tasks compile-check after each step.

Final verification gate is Task 15 — full backend test suite + `npx tsc --noEmit` + manual UI smoke test.
