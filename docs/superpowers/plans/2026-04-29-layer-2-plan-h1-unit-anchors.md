# Layer 2 Plan H1 — Unit-level Address Anchors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-04-29-layer-2-plan-h-timeline-aware-attribution-design.md` (Plan H1 section).

**Goal:** Replace `address_root` and `address_base` Layer 2 anchors with a finer-grained `address_unit` anchor that includes city, street_direction, suite_type, and suite_number. Surface unit-by-unit brand-stem breakdowns under each address root in the Layer 1 UI. Eliminates the multi-tenant building false positives (RT196095 / TD Bank @ 66 Wellington floor 30 attaching to KingSett).

**Architecture:** New `address_unit_summary` Layer 1 table built from `party_fingerprints`. New `address_unit` anchor type replaces `address_root`/`address_base` in the Layer 2 algorithm — Stage A2 (anchor_scores.py) and Stage A4 (expansion.py) update accordingly. `anchor_uniqueness` CHECK constraint loosened (drop the enum check; builder controls valid types). The "no-anchor party with no stem" path → score 0.0 (don't attach), eliminating address-root-alone false positives. Layer 1 root detail page gets a "Units at this root" section with per-unit dominance.

**Tech Stack:** Python 3.12, SQLite, FastAPI, React 19 + Radix UI Themes, TypeScript.

**Migration:** Migration 016 adds `address_unit_summary`, recreates `anchor_uniqueness` without the CHECK constraint. The Layer 2 algorithm is re-run after schema migration to rebuild auto_groups with the new anchors.

---

## Glossary (locked from the spec — used strictly)

| Term | Meaning |
|---|---|
| **Address root** | `(city?, street_number, street_name)`. **Layer 1 only.** Discovery net. Never sufficient for Layer 2 attachment. (City staying out of the existing root_summary key for H1 — addressed in a later plan.) |
| **Address base** | `(city?, street_number, street_name, street_suffix)`. **Layer 1 only.** |
| **Address unit** | `(city, street_number, street_name, street_suffix, street_direction, suite_type, suite_number)`. **Layer 2's only address anchor.** Encoded as pipe-delimited: `"toronto\|180\|shorting\|road\|\|\|"`. |
| **Anchor** | Phone, address_unit, or contact_fingerprint. Only these three types feed Layer 2 attribution. |
| **Group** | An `auto_groups` row. |
| **Stem** | Canonical operator label (e.g., `kingsett`). |
| **Dominant stem at a unit** | Most-common stem (per `brand_stem_phrase_map`) across party-sides at that unit. |
| **Orphan party** | A party with no anchor matching any group's anchors AND no brand-phrase stem hit. Stays unattached. |

H1 does **not** introduce timelines or tenures — those come in H2. H1 keeps the existing static-anchor model but with the right granularity.

---

## File Structure

**Backend (new):**
- `cleo/database/migrations/016_address_unit_summary.py` — new migration.

**Backend (modified):**
- `cleo/discovery_v2/brand_index.py` — add `build_address_unit_summary`, wire into `build_all_indexes`.
- `cleo/discovery_v2/anchor_scores.py` — replace `address_root`+`address_base` queries with `address_unit`.
- `cleo/discovery_v2/expansion.py` — `_anchor_pf_clause` updated for `address_unit`; `_score_match` rules updated.
- `cleo/web/routes/explorer.py` — add `/api/explorer/addresses/roots/{key}/units` and `/api/explorer/addresses/units/{key}` endpoints. Update `_anchor_pf_clause` and `_COVERAGE_SQL_BY_TYPE` for `address_unit`.
- `tests/test_routes_explorer.py` — fixture extensions + tests.
- `tests/test_discovery_v2_anchor_scores.py` — update for the new anchor types.
- `tests/test_discovery_v2_expansion.py` — update match-score tests for new rules.

**Frontend (new):**
- `frontend/src/pages/ExplorerAddressUnitDetail.tsx` — single unit detail page.
- `frontend/src/components/explorer/AddressUnitsAtRoot.tsx` — units-section component, embedded in the root detail page.

**Frontend (modified):**
- `frontend/src/types/index.ts` — types for new endpoints.
- `frontend/src/pages/ExplorerAddressRootDetail.tsx` — add the `<AddressUnitsAtRoot />` section.
- `frontend/src/App.tsx` — register the new unit detail route.

---

## Pre-flight context for the implementer

**Anchor encoding format**: 7 fields pipe-delimited: `city|street_number|street_name|street_suffix|street_direction|suite_type|suite_number`. Empty fields are empty strings (not NULL). Examples:
- `"toronto|180|shorting|road|||"` — single-tenant building, no direction, no suite.
- `"toronto|66|wellington|street|west|suite|4400"` — KingSett's main suite.
- `"toronto|66|wellington|street|west|floor|30th flr"` — TD Bank's floor.

**Existing anchor types**: `anchor_uniqueness` currently has a `CHECK (anchor_type IN ('phone','address_root','address_base','contact'))` constraint. Migration 016 drops this CHECK so we can add `address_unit` without recreating the table on every type change.

**`auto_group_anchors` has no CHECK constraint** — no schema change needed there. Just stop populating the old types via Stage A2 and the next builder run will replace existing rows.

**Pattern for backend route — `address_unit` URL key encoding**: same as existing root/base keys — pipe-delimited, URL-encoded. The 6 internal pipes become `%7C`. The frontend uses `encodeURIComponent` everywhere.

**Real-DB testing:** RT196095 should NOT attach to KingSett after this ships. The 90 false-positive parties at 66 Wellington with no other anchors lose their attachment.

**Key test fixture caveat**: `tests/test_routes_explorer.py` and several discovery_v2 tests have fixture seeds that use `'address_root'` and `'address_base'` anchor types. Those fixtures need updating to `'address_unit'` where appropriate. Each affected test gets touched in the relevant task.

---

## Tasks

### Task 1: Migration 016 — `address_unit_summary` + drop anchor_uniqueness CHECK

**Files:**
- Create: `cleo/database/migrations/016_address_unit_summary.py`
- Test: `tests/test_migration_016_address_unit_summary.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_migration_016_address_unit_summary.py
import importlib
import sqlite3


_m = importlib.import_module('cleo.database.migrations.016_address_unit_summary')


def _setup_pre_migration_db():
    """Simulate the pre-016 state: anchor_uniqueness exists with the old CHECK."""
    conn = sqlite3.connect(':memory:')
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS anchor_uniqueness (
            anchor_type TEXT NOT NULL CHECK (anchor_type IN ('phone','address_root','address_base','contact')),
            anchor_value TEXT NOT NULL,
            dominant_stem TEXT,
            dominance_share REAL,
            volume INTEGER NOT NULL,
            score REAL NOT NULL,
            is_service_provider INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (anchor_type, anchor_value)
        );
    """)
    return conn


def test_migration_creates_address_unit_summary():
    conn = _setup_pre_migration_db()
    _m.migrate(conn)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='address_unit_summary'"
    ).fetchall()
    assert len(rows) == 1


def test_migration_address_unit_summary_columns():
    conn = _setup_pre_migration_db()
    _m.migrate(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(address_unit_summary)")}
    assert cols >= {
        'city', 'street_number', 'street_name', 'street_suffix', 'street_direction',
        'suite_type', 'suite_number',
        'n_party_sides', 'n_distinct_brand_stems', 'dominant_stem', 'dominance_share',
        'discovered_at',
    }


def test_migration_drops_anchor_uniqueness_check():
    """After migration, inserting anchor_type='address_unit' must succeed (the old CHECK forbade it)."""
    conn = _setup_pre_migration_db()
    _m.migrate(conn)
    conn.execute(
        "INSERT INTO anchor_uniqueness (anchor_type, anchor_value, volume, score) "
        "VALUES ('address_unit', 'toronto|180|shorting|road|||', 5, 1.5)"
    )
    cnt = conn.execute(
        "SELECT COUNT(*) FROM anchor_uniqueness WHERE anchor_type='address_unit'"
    ).fetchone()[0]
    assert cnt == 1


def test_migration_is_idempotent():
    conn = _setup_pre_migration_db()
    _m.migrate(conn)
    _m.migrate(conn)  # no error
    rows = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='address_unit_summary'"
    ).fetchone()[0]
    assert rows == 1
```

- [ ] **Step 2: Run, confirm fail**

```bash
PYTHONPATH=. pytest tests/test_migration_016_address_unit_summary.py -v
# Expected: ImportError on the migration module that doesn't exist yet
```

- [ ] **Step 3: Create the migration**

`cleo/database/migrations/016_address_unit_summary.py`:

```python
"""
Migration 016: Layer 1 address_unit_summary + drop anchor_uniqueness CHECK.

Adds a new Layer 1 silo `address_unit_summary` keyed on the full physical address
including city, suffix, direction, suite_type, suite_number. Used to surface
unit-by-unit brand-stem breakdowns and to back the `address_unit` anchor type
in Layer 2.

Drops the CHECK constraint on `anchor_uniqueness.anchor_type` to allow the new
`address_unit` value (and future additions). The builder enforces valid types.
"""
from __future__ import annotations
import os
import sqlite3


def migrate(conn: sqlite3.Connection) -> None:
    print('Migration 016: address_unit_summary + relax anchor_uniqueness CHECK...')

    # Step 1: create address_unit_summary if missing.
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS address_unit_summary (
            city                   TEXT NOT NULL,
            street_number          TEXT NOT NULL,
            street_name            TEXT NOT NULL,
            street_suffix          TEXT NOT NULL DEFAULT '',
            street_direction       TEXT NOT NULL DEFAULT '',
            suite_type             TEXT NOT NULL DEFAULT '',
            suite_number           TEXT NOT NULL DEFAULT '',
            n_party_sides          INTEGER NOT NULL,
            n_distinct_brand_stems INTEGER NOT NULL,
            dominant_stem          TEXT,
            dominance_share        REAL,
            discovered_at          TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (city, street_number, street_name, street_suffix,
                         street_direction, suite_type, suite_number)
        );
        CREATE INDEX IF NOT EXISTS idx_aus_root
            ON address_unit_summary(city, street_number, street_name);
        CREATE INDEX IF NOT EXISTS idx_aus_dominant
            ON address_unit_summary(dominant_stem);
    """)

    # Step 2: drop the CHECK constraint on anchor_uniqueness by recreating the table.
    # SQLite can't ALTER a CHECK; we recreate the table preserving data.
    # Detect whether the CHECK is present before recreating (idempotent).
    sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='anchor_uniqueness'"
    ).fetchone()
    if sql and 'CHECK (anchor_type IN' in (sql[0] or ''):
        conn.executescript("""
            CREATE TABLE anchor_uniqueness__new (
                anchor_type TEXT NOT NULL,
                anchor_value TEXT NOT NULL,
                dominant_stem TEXT,
                dominance_share REAL,
                volume INTEGER NOT NULL,
                score REAL NOT NULL,
                is_service_provider INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (anchor_type, anchor_value)
            );
            INSERT INTO anchor_uniqueness__new
            SELECT * FROM anchor_uniqueness;
            DROP TABLE anchor_uniqueness;
            ALTER TABLE anchor_uniqueness__new RENAME TO anchor_uniqueness;
            CREATE INDEX IF NOT EXISTS idx_au_score ON anchor_uniqueness(score);
            CREATE INDEX IF NOT EXISTS idx_au_stem ON anchor_uniqueness(dominant_stem);
        """)
    conn.commit()
    print('Migration 016 complete.')


if __name__ == '__main__':
    db_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'data', 'cleo.db')
    conn = sqlite3.connect(db_path)
    migrate(conn)
    conn.close()
```

- [ ] **Step 4: Run tests, confirm pass**

```bash
PYTHONPATH=. pytest tests/test_migration_016_address_unit_summary.py -v
# Expected: 4 passed
```

- [ ] **Step 5: Apply to real DB**

```bash
python -m cleo.database.migrations.016_address_unit_summary
sqlite3 data/cleo.db "SELECT COUNT(*) FROM sqlite_master WHERE name='address_unit_summary'"
# Expected: 1
```

- [ ] **Step 6: Commit**

```bash
git add cleo/database/migrations/016_address_unit_summary.py tests/test_migration_016_address_unit_summary.py
git commit -m "feat(layer2): migration 016 — address_unit_summary + relax anchor_uniqueness CHECK"
```

---

### Task 2: Builder — `build_address_unit_summary`

Populates `address_unit_summary` from `party_fingerprints` joined to brand_stem_phrase_map. Computes per-unit dominant_stem and dominance_share.

**Files:**
- Modify: `cleo/discovery_v2/brand_index.py`
- Test: `tests/test_discovery_v2_address_unit.py` (new)

- [ ] **Step 1: Write failing test**

`tests/test_discovery_v2_address_unit.py`:

```python
import sqlite3
import pytest
from cleo.discovery_v2.brand_index import build_address_unit_summary


def _make_db():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE party_fingerprints (
            source_id TEXT, side TEXT, city TEXT,
            street_number TEXT, street_name TEXT, street_suffix TEXT,
            street_direction TEXT, suite_type TEXT, suite_number TEXT,
            phone TEXT, contact_fingerprint TEXT,
            PRIMARY KEY (source_id, side)
        );
        CREATE TABLE party_atoms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT, side TEXT, atom_type TEXT, atom_value TEXT, source_field TEXT
        );
        CREATE TABLE brand_stem_phrase_map (
            phrase TEXT PRIMARY KEY, stem TEXT NOT NULL, confidence REAL NOT NULL
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
            discovered_at TEXT,
            PRIMARY KEY (city, street_number, street_name, street_suffix,
                         street_direction, suite_type, suite_number)
        );
    """)
    return conn


def _seed_party(conn, sid, side, **fields):
    base = dict(city=None, street_number=None, street_name=None, street_suffix=None,
                street_direction=None, suite_type=None, suite_number=None,
                phone=None, contact_fingerprint=None)
    base.update(fields)
    conn.execute(
        """INSERT INTO party_fingerprints
            (source_id, side, city, street_number, street_name, street_suffix,
             street_direction, suite_type, suite_number, phone, contact_fingerprint)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (sid, side, base['city'], base['street_number'], base['street_name'],
         base['street_suffix'], base['street_direction'],
         base['suite_type'], base['suite_number'],
         base['phone'], base['contact_fingerprint']),
    )


def _seed_phrase(conn, sid, side, phrase, stem):
    conn.execute(
        "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
        "VALUES (?, ?, 'brand_phrase', ?, 'party_name')",
        (sid, side, phrase),
    )
    conn.execute(
        "INSERT OR IGNORE INTO brand_stem_phrase_map (phrase, stem, confidence) VALUES (?, ?, 1.0)",
        (phrase, stem),
    )


def test_build_address_unit_summary_aggregates_by_full_unit_key():
    conn = _make_db()
    # Two parties at the same unit, one mapped, one unmapped
    _seed_party(conn, 'RT1', 'buyer', city='toronto', street_number='66',
                street_name='wellington', street_suffix='street',
                street_direction='west', suite_type='suite', suite_number='4400')
    _seed_party(conn, 'RT2', 'buyer', city='toronto', street_number='66',
                street_name='wellington', street_suffix='street',
                street_direction='west', suite_type='suite', suite_number='4400')
    _seed_phrase(conn, 'RT1', 'buyer', 'kingsett capital', 'kingsett')

    build_address_unit_summary(conn, verbose=False)

    rows = conn.execute(
        """SELECT city, street_number, street_name, street_suffix, street_direction,
                  suite_type, suite_number, n_party_sides, dominant_stem
           FROM address_unit_summary"""
    ).fetchall()
    assert len(rows) == 1
    r = dict(rows[0])
    assert r['n_party_sides'] == 2
    assert r['dominant_stem'] == 'kingsett'


def test_build_address_unit_summary_distinct_units_at_same_root():
    conn = _make_db()
    _seed_party(conn, 'RT1', 'buyer', city='toronto', street_number='66',
                street_name='wellington', street_suffix='street',
                street_direction='west', suite_type='suite', suite_number='4400')
    _seed_party(conn, 'RT2', 'buyer', city='toronto', street_number='66',
                street_name='wellington', street_suffix='street',
                street_direction='west', suite_type='suite', suite_number='4100')
    _seed_party(conn, 'RT3', 'buyer', city='toronto', street_number='66',
                street_name='wellington', street_suffix='street',
                street_direction='west', suite_type='floor', suite_number='30th flr')
    _seed_phrase(conn, 'RT1', 'buyer', 'kingsett capital', 'kingsett')
    _seed_phrase(conn, 'RT2', 'buyer', 'weirfoulds llp', 'weirfoulds')

    build_address_unit_summary(conn, verbose=False)

    rows = conn.execute('SELECT * FROM address_unit_summary ORDER BY suite_number').fetchall()
    assert len(rows) == 3  # 3 distinct units at same root


def test_build_address_unit_summary_dominance_calculation():
    """Suite 4400: 4 parties total. 3 map to kingsett, 1 to other. Dominance = 3/4 = 0.75."""
    conn = _make_db()
    for sid in ('RT1', 'RT2', 'RT3'):
        _seed_party(conn, sid, 'buyer', city='toronto', street_number='66',
                    street_name='wellington', street_suffix='street',
                    street_direction='west', suite_type='suite', suite_number='4400')
        _seed_phrase(conn, sid, 'buyer', 'kingsett capital', 'kingsett')
    _seed_party(conn, 'RT4', 'buyer', city='toronto', street_number='66',
                street_name='wellington', street_suffix='street',
                street_direction='west', suite_type='suite', suite_number='4400')
    _seed_phrase(conn, 'RT4', 'buyer', 'random other corp', 'random')

    build_address_unit_summary(conn, verbose=False)

    row = conn.execute(
        "SELECT * FROM address_unit_summary WHERE suite_number='4400'"
    ).fetchone()
    assert row['n_party_sides'] == 4
    assert row['dominant_stem'] == 'kingsett'
    assert row['dominance_share'] == pytest.approx(0.75)
    assert row['n_distinct_brand_stems'] == 2


def test_build_address_unit_summary_skips_parties_without_city_or_street():
    """A party with no city or no street_number should NOT be in the summary."""
    conn = _make_db()
    _seed_party(conn, 'RT1', 'buyer', city='toronto', street_number='66', street_name='wellington')
    _seed_party(conn, 'RT2', 'buyer', street_number='66', street_name='wellington')  # no city
    _seed_party(conn, 'RT3', 'buyer', city='toronto', street_name='wellington')  # no street_number

    build_address_unit_summary(conn, verbose=False)
    rows = conn.execute('SELECT * FROM address_unit_summary').fetchall()
    assert len(rows) == 1
    assert rows[0]['street_number'] == '66'


def test_build_address_unit_summary_idempotent():
    conn = _make_db()
    _seed_party(conn, 'RT1', 'buyer', city='toronto', street_number='66',
                street_name='wellington', street_suffix='street')
    build_address_unit_summary(conn, verbose=False)
    build_address_unit_summary(conn, verbose=False)
    cnt = conn.execute('SELECT COUNT(*) FROM address_unit_summary').fetchone()[0]
    assert cnt == 1
```

- [ ] **Step 2: Run, confirm fail**

```bash
PYTHONPATH=. pytest tests/test_discovery_v2_address_unit.py -v
# Expected: ImportError or AttributeError on build_address_unit_summary
```

- [ ] **Step 3: Implement `build_address_unit_summary`**

In `cleo/discovery_v2/brand_index.py`, add this function after `build_address_root_summary` (line ~450):

```python
def build_address_unit_summary(conn, *, verbose: bool = True):
    """Layer 1 silo: per-unit brand-stem dominance.

    A 'unit' is the full physical address: city + street_number + street_name +
    street_suffix + street_direction + suite_type + suite_number. Empty fields
    (NULL or '') are normalized to empty string in the key.
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
        if prev is None or r['n'] > prev[1]:
            side_stems[key] = (r['stem'], r['n'])

    # Step 2: aggregate parties by unit-key, computing stem counts.
    by_unit: dict = {}
    for r in conn.execute("""
        SELECT source_id, side, city, street_number, street_name,
               street_suffix, street_direction, suite_type, suite_number
        FROM party_fingerprints
        WHERE city IS NOT NULL AND city != ''
          AND street_number IS NOT NULL AND street_number != ''
          AND street_name IS NOT NULL AND street_name != ''
    """):
        key = (
            r['city'], r['street_number'], r['street_name'],
            r['street_suffix'] or '',
            r['street_direction'] or '',
            r['suite_type'] or '',
            r['suite_number'] or '',
        )
        bucket = by_unit.setdefault(key, {'sides': 0, 'stem_counts': {}})
        bucket['sides'] += 1
        st = side_stems.get((r['source_id'], r['side']))
        if st is not None:
            bucket['stem_counts'][st[0]] = bucket['stem_counts'].get(st[0], 0) + 1

    # Step 3: insert rows, computing dominant stem + share.
    rows_to_insert = []
    for (city, num, name, suf, dir_, stype, snum), bucket in by_unit.items():
        n_parties = bucket['sides']
        stem_counts = bucket['stem_counts']
        n_distinct = len(stem_counts)
        if stem_counts:
            dom_stem, dom_n = max(stem_counts.items(), key=lambda kv: kv[1])
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
        print(f'  Layer 1 silo (address units): {len(rows_to_insert):,} distinct units', flush=True)
    return {'n_units': len(rows_to_insert)}
```

Also wire into `build_all_indexes`. Find it (around line 575) and add the call after `build_address_root_summary`:

```python
build_address_root_summary(conn, verbose=verbose)
build_address_unit_summary(conn, verbose=verbose)        # ← Plan H1
```

- [ ] **Step 4: Run tests, confirm pass**

```bash
PYTHONPATH=. pytest tests/test_discovery_v2_address_unit.py -v
# Expected: 5 passed
```

- [ ] **Step 5: Commit**

```bash
git add cleo/discovery_v2/brand_index.py tests/test_discovery_v2_address_unit.py
git commit -m "feat(layer2): build_address_unit_summary — per-unit brand-stem dominance"
```

---

### Task 3: Stage A2 — replace address_root/address_base with address_unit

**Files:**
- Modify: `cleo/discovery_v2/anchor_scores.py`
- Modify: `tests/test_discovery_v2_anchor_scores.py`

- [ ] **Step 1: Update the test fixture**

`tests/test_discovery_v2_anchor_scores.py` currently has a `_make_db` that creates a party_fingerprints schema WITHOUT `city` and `street_direction` columns. Update the fixture's `executescript` for `party_fingerprints` to include them:

```python
CREATE TABLE party_fingerprints (
    source_id TEXT, side TEXT, phone TEXT, contact_fingerprint TEXT,
    city TEXT,
    street_number TEXT, street_name TEXT, street_suffix TEXT, street_direction TEXT,
    suite_type TEXT, suite_number TEXT,
    PRIMARY KEY (source_id, side)
);
```

Update the existing `_seed` helper to include the new fields:

```python
def _seed(conn, source_id, side, phrase, *, phone=None, contact=None,
          city=None, street_number=None, street_name=None, street_suffix=None,
          street_direction=None, suite_type=None, suite_number=None):
    conn.execute(
        """INSERT OR IGNORE INTO party_fingerprints
             (source_id, side, phone, contact_fingerprint, city,
              street_number, street_name, street_suffix, street_direction,
              suite_type, suite_number)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (source_id, side, phone, contact, city, street_number, street_name,
         street_suffix, street_direction, suite_type, suite_number),
    )
    if phrase:
        conn.execute(
            "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
            "VALUES (?, ?, 'brand_phrase', ?, 'party_name')",
            (source_id, side, phrase),
        )
```

Update existing tests that use `_seed(...)` with address fields — they need to also pass `city='toronto'` (or some city) so the new `address_unit` query has data to work with.

Specifically, the existing test `test_phone_anchor_scores_correctly_when_stem_dominates` uses `phone='P1'` with no address — that's fine, address_unit just won't fire for those parties.

For tests that exercise address anchors, replace `address_root` / `address_base` assertions with `address_unit` assertions.

- [ ] **Step 2: Add a new test for address_unit**

Append to `tests/test_discovery_v2_anchor_scores.py`:

```python
def test_address_unit_anchor_scores_with_dominant_stem():
    """6 parties at toronto|66|wellington|street|west|suite|4400, all skyline.
    address_unit anchor score should reflect dominance and volume."""
    conn = _make_db()
    for i in range(6):
        _seed(conn, f'TX{i}', 'buyer', 'skyline real estate holdings',
              city='toronto', street_number='66', street_name='wellington',
              street_suffix='street', street_direction='west',
              suite_type='suite', suite_number='4400')
    build_stems(conn, verbose=False)
    build_anchor_scores(conn, verbose=False)
    row = conn.execute(
        """SELECT * FROM anchor_uniqueness
           WHERE anchor_type='address_unit' AND anchor_value=?""",
        ('toronto|66|wellington|street|west|suite|4400',),
    ).fetchone()
    assert row is not None
    assert row['dominant_stem'] == 'skyline'
    assert row['volume'] == 6
    assert row['dominance_share'] == pytest.approx(1.0)


def test_address_root_and_base_no_longer_in_anchor_uniqueness():
    """After Plan H1, anchor_uniqueness should not contain address_root or address_base rows."""
    conn = _make_db()
    for i in range(6):
        _seed(conn, f'TX{i}', 'buyer', 'skyline real estate holdings',
              city='toronto', street_number='66', street_name='wellington',
              street_suffix='street', street_direction='west',
              suite_type='suite', suite_number='4400')
    build_stems(conn, verbose=False)
    build_anchor_scores(conn, verbose=False)
    types = {r['anchor_type'] for r in conn.execute('SELECT DISTINCT anchor_type FROM anchor_uniqueness')}
    assert 'address_unit' in types
    assert 'address_root' not in types
    assert 'address_base' not in types
```

- [ ] **Step 3: Run, confirm fail**

```bash
PYTHONPATH=. pytest tests/test_discovery_v2_anchor_scores.py -v
# Expected: failures (address_unit not produced; address_root/base still produced)
```

- [ ] **Step 4: Update `anchor_scores.py`**

Replace the `_ANCHOR_QUERIES` dict in `cleo/discovery_v2/anchor_scores.py`:

```python
# Note: address_unit is the only address anchor type Layer 2 tracks. Layer 1
# silos (address_root_summary, address_base_summary, address_unit_summary)
# remain available for browsing but are not Layer 2 anchors.
_ANCHOR_QUERIES = {
    # anchor_type → SQL that yields (anchor_value, source_id, side) for each
    # party-side, with anchor_value being the canonical key for that type.
    'phone': """
        SELECT phone AS anchor_value, source_id, side
        FROM party_fingerprints
        WHERE phone IS NOT NULL AND phone != ''
    """,
    'address_unit': """
        SELECT (
            COALESCE(city,'') || '|' ||
            COALESCE(street_number,'') || '|' ||
            COALESCE(street_name,'') || '|' ||
            COALESCE(street_suffix,'') || '|' ||
            COALESCE(street_direction,'') || '|' ||
            COALESCE(suite_type,'') || '|' ||
            COALESCE(suite_number,'')
        ) AS anchor_value, source_id, side
        FROM party_fingerprints
        WHERE city IS NOT NULL AND city != ''
          AND street_number IS NOT NULL AND street_number != ''
          AND street_name IS NOT NULL AND street_name != ''
    """,
    'contact': """
        SELECT contact_fingerprint AS anchor_value, source_id, side
        FROM party_fingerprints
        WHERE contact_fingerprint IS NOT NULL AND contact_fingerprint != ''
    """,
}
```

Update the docstring at the top of the file:

```python
"""Stage A2: Anchor uniqueness scoring.

For each anchor (phone, address_unit, contact), computes the dominant
brand_stem and a score = dominance_share * log(volume + 1).
"""
```

- [ ] **Step 5: Run tests, confirm pass**

```bash
PYTHONPATH=. pytest tests/test_discovery_v2_anchor_scores.py -v
# Expected: existing + 2 new tests all pass
```

- [ ] **Step 6: Commit**

```bash
git add cleo/discovery_v2/anchor_scores.py tests/test_discovery_v2_anchor_scores.py
git commit -m "feat(layer2): Stage A2 produces address_unit anchors (drops address_root/base)"
```

---

### Task 4: Stage A4 — expansion match-scoring updated

**Files:**
- Modify: `cleo/discovery_v2/expansion.py`
- Modify: `tests/test_discovery_v2_expansion.py`

- [ ] **Step 1: Update the test fixture**

In `tests/test_discovery_v2_expansion.py`, update the `_make_db()` schema for `party_fingerprints` to include `city` and `street_direction`:

```python
CREATE TABLE party_fingerprints (
    source_id TEXT, side TEXT, phone TEXT, contact_fingerprint TEXT,
    city TEXT,
    street_number TEXT, street_name TEXT, street_suffix TEXT, street_direction TEXT,
    suite_type TEXT, suite_number TEXT,
    PRIMARY KEY (source_id, side)
);
```

Update `_seed()` helper signature (same as Task 3 Step 1).

- [ ] **Step 2: Add new tests for the no-anchor + no-stem rule (the TD Bank case)**

Append to `tests/test_discovery_v2_expansion.py`:

```python
def test_no_anchor_no_stem_party_does_not_attach_via_address_alone():
    """The TD Bank case: a party at a multi-tenant building's root has no phone,
    no contact, no stem-mapped brand. Should NOT attach to any group via
    address-root-alone matching (which is now disallowed)."""
    conn = _make_db()
    # Seed a Skyline group with anchors
    for i in range(8):
        _seed(conn, f'STRONG{i}', 'buyer', 'skyline real estate holdings',
              phone='P1', contact='jc',
              city='toronto', street_number='66', street_name='wellington',
              street_suffix='street', street_direction='west',
              suite_type='suite', suite_number='4400')
    # Add a party at the SAME ROOT but DIFFERENT UNIT, no phone, no contact, no stem-mapped brand.
    _seed(conn, 'TD_LIKE', 'seller', 'the toronto dominion bank',
          city='toronto', street_number='66', street_name='wellington',
          street_suffix='street', street_direction='west',
          suite_type='floor', suite_number='30th flr')
    _build_pipeline(conn)
    build_expansion(conn, verbose=False)

    # Should NOT be attached to the Skyline group.
    skyline = [r for r in conn.execute(
        "SELECT auto_group_id FROM auto_groups WHERE canonical_stem='skyline'"
    )]
    if skyline:
        rows = conn.execute(
            "SELECT * FROM auto_group_members WHERE auto_group_id=? AND source_id='TD_LIKE'",
            (skyline[0]['auto_group_id'],),
        ).fetchall()
        assert len(rows) == 0


def test_address_unit_match_attaches_to_group():
    """A party at the SAME unit as a group's address_unit anchor attaches via
    that anchor (no other identifying data needed because the unit is
    uniquely tenanted)."""
    conn = _make_db()
    for i in range(8):
        _seed(conn, f'STRONG{i}', 'buyer', 'skyline real estate holdings',
              phone='P1', contact='jc',
              city='toronto', street_number='66', street_name='wellington',
              street_suffix='street', street_direction='west',
              suite_type='suite', suite_number='4400')
    # Add a party at the same UNIT (suite 4400) but no phone, no contact, no brand.
    _seed(conn, 'EXTRA', 'seller', None,
          city='toronto', street_number='66', street_name='wellington',
          street_suffix='street', street_direction='west',
          suite_type='suite', suite_number='4400')
    _build_pipeline(conn)
    build_expansion(conn, verbose=False)

    skyline = [r for r in conn.execute(
        "SELECT auto_group_id FROM auto_groups WHERE canonical_stem='skyline'"
    )]
    assert len(skyline) >= 1
    gid = skyline[0]['auto_group_id']
    rows = conn.execute(
        "SELECT * FROM auto_group_members WHERE auto_group_id=? AND source_id='EXTRA'",
        (gid,),
    ).fetchall()
    assert len(rows) == 1
    # MATCH_SCORE_ADDRESS_UNIT_ALONE = 0.7 (from the new constants)
    assert rows[0]['match_score'] >= 0.5
```

If the existing tests reference `address_root` or `address_base` anchor matching specifically (the `test_phone_match_*` tests should still work since they use phone, not address — verify), update them where needed to use `address_unit` keys.

- [ ] **Step 3: Run, confirm fail**

```bash
PYTHONPATH=. pytest tests/test_discovery_v2_expansion.py -v
# Expected: new tests fail
```

- [ ] **Step 4: Update `expansion.py`**

Replace the `_anchor_pf_clause` reference (which already lives in `cleo/web/routes/explorer.py:1831`) — but `expansion.py` has its OWN inline anchor-matching logic in `_score_match`. Find that function and update:

In `cleo/discovery_v2/expansion.py`, locate `_score_match` and the address-related logic. Replace the existing address checks with unit-only logic.

The `_score_match` function currently checks `addr_root` and `addr_base` against group anchors. Replace with `addr_unit`:

```python
def _score_match(info: dict, anchors: dict, *, group_canonical_stem: str) -> float:
    """Score a single (party-side, group) pair using constants.py rules."""
    score = 0.0
    has_phone_match = ('phone', info['phone']) in anchors if info['phone'] else False
    has_unit_match = ('address_unit', info['addr_unit']) in anchors if info['addr_unit'] else False
    has_contact_match = ('contact', info['contact']) in anchors if info['contact'] else False
    has_direct_stem = group_canonical_stem in info['stems']

    # Strong: direct stem hit
    if has_direct_stem:
        score = max(score, MATCH_SCORE_DIRECT_STEM_HIT)

    # Phone match — but only if no contradicting stem on the side
    if has_phone_match:
        contradicting = info['stems'] - {group_canonical_stem}
        if contradicting:
            return MATCH_SCORE_PHONE_BRAND_CONTRADICTION
        score = max(score, MATCH_SCORE_PHONE_MATCH)

    if has_unit_match and has_contact_match:
        score = max(score, MATCH_SCORE_ADDRESS_PLUS_CONTACT)
    elif has_unit_match:
        score = max(score, MATCH_SCORE_ADDRESS_UNIT_ALONE)

    # Single weak signal: contact only, common-name risk
    if has_contact_match and not (has_phone_match or has_unit_match or has_direct_stem):
        score = max(score, MATCH_SCORE_SINGLE_WEAK_SIGNAL)

    # No-anchor party with no stem hit and no phone/unit/contact → 0.0 (don't attach).
    # This is the TD Bank case: address_root would have matched in the old algorithm,
    # but address_root is no longer a Layer 2 anchor.
    return score
```

Find the call site that builds `info['addr_root']` and `info['addr_base']` in `build_expansion`. Replace with `info['addr_unit']`:

```python
addr_unit = (
    f"{r['city'] or ''}|{r['street_number'] or ''}|{r['street_name'] or ''}|"
    f"{r['street_suffix'] or ''}|{r['street_direction'] or ''}|"
    f"{r['suite_type'] or ''}|{r['suite_number'] or ''}"
    if r['city'] and r['street_number'] and r['street_name'] else None
)
side_data[(r['source_id'], r['side'])] = {
    'phone':     r['phone'] or None,
    'addr_unit': addr_unit,
    'contact':   r['contact_fingerprint'] or None,
    'stems':     set(),
    'phrases':   [],
}
```

Update the SQL in `build_expansion` that fetches party_fingerprints to include the new fields:

```python
for r in conn.execute("""
    SELECT source_id, side, phone, contact_fingerprint, city,
           street_number, street_name, street_suffix, street_direction,
           suite_type, suite_number
    FROM party_fingerprints
"""):
```

Update `cleo/discovery_v2/constants.py` — rename `MATCH_SCORE_ADDRESS_ROOT_ALONE` to `MATCH_SCORE_ADDRESS_UNIT_ALONE` (semantic change reflecting unit-level matching):

```python
MATCH_SCORE_ADDRESS_UNIT_ALONE          = 0.7
```

(0.7 instead of the old 0.5 — unit-level matches are a stronger signal than root-level matches were.)

Search the codebase for `MATCH_SCORE_ADDRESS_ROOT_ALONE` and update the import in `expansion.py`.

- [ ] **Step 5: Run tests, confirm pass**

```bash
PYTHONPATH=. pytest tests/test_discovery_v2_expansion.py -v
# Expected: all pass including 2 new
```

- [ ] **Step 6: Commit**

```bash
git add cleo/discovery_v2/expansion.py cleo/discovery_v2/constants.py tests/test_discovery_v2_expansion.py
git commit -m "feat(layer2): Stage A4 expansion uses address_unit (drops root/base, fixes TD Bank case)"
```

---

### Task 5: Backend — `/addresses/roots/{key}/units` endpoint

**Files:**
- Modify: `cleo/web/routes/explorer.py`
- Modify: `tests/test_routes_explorer.py`

- [ ] **Step 1: Extend the test fixture**

In `tests/test_routes_explorer.py`, find `_seeded_db` and update the `party_fingerprints` schema to include `city` and `street_direction`:

```python
CREATE TABLE IF NOT EXISTS party_fingerprints (
    source_id TEXT NOT NULL,
    side TEXT NOT NULL,
    city TEXT,
    street_number TEXT, street_name TEXT, street_suffix TEXT, street_direction TEXT,
    suite_type TEXT, suite_number TEXT,
    phone TEXT, contact_fingerprint TEXT,
    sale_date TEXT,
    PRIMARY KEY (source_id, side)
);
```

Add the address_unit_summary table to the fixture:

```python
CREATE TABLE IF NOT EXISTS address_unit_summary (
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
    discovered_at TEXT,
    PRIMARY KEY (city, street_number, street_name, street_suffix,
                 street_direction, suite_type, suite_number)
);
```

Append seed data to `_seeded_db` after the existing inserts:

```python
# Seed address_unit_summary for 66 wellington (toronto): three units
conn.execute("""
    INSERT INTO address_unit_summary
       (city, street_number, street_name, street_suffix, street_direction,
        suite_type, suite_number, n_party_sides, n_distinct_brand_stems,
        dominant_stem, dominance_share)
    VALUES
       ('toronto', '66', 'wellington', 'street', 'west', 'suite', '4400', 156, 3, 'kingsett', 0.88),
       ('toronto', '66', 'wellington', 'street', 'west', 'suite', '4100', 11, 2, 'weirfoulds', 0.82),
       ('toronto', '66', 'wellington', 'street', 'west', 'floor', '30th flr', 3, 0, NULL, 0.0)
""")
```

- [ ] **Step 2: Write failing tests**

Append to `tests/test_routes_explorer.py`:

```python
def test_units_at_root_returns_unit_breakdown(client):
    """For root toronto|66|wellington, return the 3 seeded units."""
    resp = client.get('/api/explorer/addresses/roots/toronto%7C66%7Cwellington/units')
    assert resp.status_code == 200
    body = resp.json()
    assert len(body['results']) == 3
    suite_4400 = next((u for u in body['results']
                       if u['suite_type'] == 'suite' and u['suite_number'] == '4400'), None)
    assert suite_4400 is not None
    assert suite_4400['dominant_stem'] == 'kingsett'
    assert suite_4400['n_party_sides'] == 156
    assert suite_4400['dominance_share'] == pytest.approx(0.88)


def test_units_at_root_sorted_by_n_party_sides(client):
    resp = client.get('/api/explorer/addresses/roots/toronto%7C66%7Cwellington/units')
    counts = [u['n_party_sides'] for u in resp.json()['results']]
    assert counts == sorted(counts, reverse=True)


def test_units_at_root_404_on_unknown(client):
    resp = client.get('/api/explorer/addresses/roots/toronto%7C99%7Cnowhere/units')
    assert resp.status_code == 200  # endpoint returns empty list, not 404
    assert resp.json()['results'] == []
```

- [ ] **Step 3: Run, confirm fail**

```bash
PYTHONPATH=. pytest tests/test_routes_explorer.py -v -k units_at_root
# Expected: 3 failures — endpoint doesn't exist
```

- [ ] **Step 4: Add the endpoint**

Insert into `cleo/web/routes/explorer.py` near the existing `/addresses/roots/{key}` endpoint (find `def address_root_detail` or similar; insert after it):

```python
@router.get('/addresses/roots/{key}/units')
def address_root_units(
    key: str, db=Depends(get_db), user=Depends(get_current_user),
):
    """Units within an address root. Key format: 'city|street_number|street_name'."""
    parts = key.split('|', 2)
    if len(parts) != 3:
        raise HTTPException(status_code=400, detail=f'Invalid root key: {key!r}')
    city, snum, sname = parts

    rows = [dict(r) for r in db.execute(
        """SELECT city, street_number, street_name, street_suffix, street_direction,
                  suite_type, suite_number, n_party_sides, n_distinct_brand_stems,
                  dominant_stem, dominance_share
           FROM address_unit_summary
           WHERE city = ? AND street_number = ? AND street_name = ?
           ORDER BY n_party_sides DESC, suite_number ASC""",
        (city, snum, sname),
    )]
    return {'results': rows}
```

- [ ] **Step 5: Run tests, confirm pass**

```bash
PYTHONPATH=. pytest tests/test_routes_explorer.py -v -k units_at_root
# Expected: 3 passed
```

- [ ] **Step 6: Update the docstring**

Add to the endpoint list at the top of `cleo/web/routes/explorer.py`:

```
GET /api/explorer/addresses/roots/:key/units  — units within a root with brand-stem dominance
```

- [ ] **Step 7: Commit**

```bash
git add cleo/web/routes/explorer.py tests/test_routes_explorer.py
git commit -m "feat(layer2): /addresses/roots/:key/units endpoint"
```

---

### Task 6: Backend — `/addresses/units/{key}` detail endpoint

Returns a single unit detail with parties, top brand phrases, contacts, phones — analogous to existing root detail but at the unit level.

**Files:**
- Modify: `cleo/web/routes/explorer.py`
- Modify: `tests/test_routes_explorer.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_routes_explorer.py`:

```python
def test_unit_detail_returns_summary(client):
    """Unit key format: 'city|num|name|suffix|direction|suite_type|suite_number'."""
    key = 'toronto|66|wellington|street|west|suite|4400'
    encoded = '%7C'.join(key.split('|'))
    resp = client.get(f'/api/explorer/addresses/units/{encoded}')
    assert resp.status_code == 200
    body = resp.json()
    assert body['city'] == 'toronto'
    assert body['street_number'] == '66'
    assert body['street_name'] == 'wellington'
    assert body['suite_type'] == 'suite'
    assert body['suite_number'] == '4400'
    assert body['dominant_stem'] == 'kingsett'
    assert body['n_party_sides'] == 156


def test_unit_detail_404_on_unknown(client):
    key = 'toronto|99|nowhere|||||'
    encoded = '%7C'.join(key.split('|'))
    resp = client.get(f'/api/explorer/addresses/units/{encoded}')
    assert resp.status_code == 404


def test_unit_detail_400_on_malformed_key(client):
    resp = client.get('/api/explorer/addresses/units/notenoughparts')
    assert resp.status_code == 400
```

- [ ] **Step 2: Run, confirm fail**

```bash
PYTHONPATH=. pytest tests/test_routes_explorer.py -v -k unit_detail
# Expected: 3 failures
```

- [ ] **Step 3: Add the endpoint**

Insert into `cleo/web/routes/explorer.py` after the previous endpoint:

```python
@router.get('/addresses/units/{key}')
def address_unit_detail(
    key: str, db=Depends(get_db), user=Depends(get_current_user),
):
    """Unit detail. Key format: 'city|num|name|suffix|direction|suite_type|suite_number'."""
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

- [ ] **Step 4: Run tests, confirm pass**

```bash
PYTHONPATH=. pytest tests/test_routes_explorer.py -v -k unit_detail
# Expected: 3 passed
```

- [ ] **Step 5: Update the docstring**

```
GET /api/explorer/addresses/units/:key  — single unit detail
```

- [ ] **Step 6: Commit**

```bash
git add cleo/web/routes/explorer.py tests/test_routes_explorer.py
git commit -m "feat(layer2): /addresses/units/:key detail endpoint"
```

---

### Task 7: Frontend — types + Units section on root detail page

**Files:**
- Modify: `frontend/src/types/index.ts`
- Create: `frontend/src/components/explorer/AddressUnitsAtRoot.tsx`
- Modify: `frontend/src/pages/ExplorerAddressRootDetail.tsx`

- [ ] **Step 1: Add types**

Append to `frontend/src/types/index.ts`:

```typescript
// ============================================================
// Explorer — Address Units (Plan H1)
// ============================================================

export interface AddressUnitSummary {
  city: string;
  street_number: string;
  street_name: string;
  street_suffix: string;
  street_direction: string;
  suite_type: string;
  suite_number: string;
  n_party_sides: number;
  n_distinct_brand_stems: number;
  dominant_stem: string | null;
  dominance_share: number;
}

export interface AddressUnitsAtRootResponse {
  results: AddressUnitSummary[];
}
```

- [ ] **Step 2: Create the AddressUnitsAtRoot component**

`frontend/src/components/explorer/AddressUnitsAtRoot.tsx`:

```typescript
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Heading, Text } from "@radix-ui/themes";
import { fetchApi } from "../../api/client";
import type { AddressUnitsAtRootResponse, AddressUnitSummary } from "../../types";


function unitKey(u: AddressUnitSummary): string {
  return [u.city, u.street_number, u.street_name, u.street_suffix,
          u.street_direction, u.suite_type, u.suite_number].join('|');
}

function unitLabel(u: AddressUnitSummary): string {
  const suite = [u.suite_type, u.suite_number].filter(Boolean).join(' ');
  const dir = u.street_direction;
  if (!suite && !dir) return '(no unit)';
  return [suite, dir].filter(Boolean).join(' ');
}


export default function AddressUnitsAtRoot({ rootKey }: { rootKey: string }) {
  const [data, setData] = useState<AddressUnitsAtRootResponse | null>(null);

  useEffect(() => {
    fetchApi<AddressUnitsAtRootResponse>(
      `/explorer/addresses/roots/${encodeURIComponent(rootKey)}/units`,
    ).then(setData).catch(console.error);
  }, [rootKey]);

  if (!data) return null;
  if (data.results.length === 0) {
    return (
      <div className="mt-6">
        <Heading size="3" mb="2">Units at this root</Heading>
        <Text size="2" style={{ color: "var(--gray-9)" }}>No units recorded.</Text>
      </div>
    );
  }

  return (
    <div className="mt-6">
      <Heading size="3" mb="2">Units at this root ({data.results.length})</Heading>
      <Text size="1" style={{ color: "var(--gray-9)" }} className="block mb-2">
        Each row is a distinct physical unit (suite/floor/PO box). Click to drill into a unit's detail.
      </Text>
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
        <table className="w-full text-[13px]">
          <thead className="bg-[var(--gray-2)]">
            <tr style={{ color: "var(--gray-9)" }}>
              <th className="text-left p-2 font-medium">unit</th>
              <th className="text-right p-2 font-medium">parties</th>
              <th className="text-left p-2 font-medium">dominant stem</th>
              <th className="text-right p-2 font-medium">dominance</th>
              <th className="text-right p-2 font-medium">distinct stems</th>
            </tr>
          </thead>
          <tbody>
            {data.results.map((u, i) => (
              <tr key={i} className="border-t border-[var(--gray-4)] hover:bg-[var(--gray-2)]">
                <td className="p-2">
                  <Link to={`/explorer/addresses/units/${encodeURIComponent(unitKey(u))}`}
                        className="no-underline" style={{ color: "var(--accent-11)" }}>
                    {unitLabel(u)}
                  </Link>
                </td>
                <td className="p-2 text-right">{u.n_party_sides.toLocaleString()}</td>
                <td className="p-2 font-mono">
                  {u.dominant_stem || <Text size="1" style={{ color: "var(--gray-9)" }}>—</Text>}
                </td>
                <td className="p-2 text-right">
                  {u.dominance_share != null ? `${(u.dominance_share * 100).toFixed(0)}%` : '—'}
                </td>
                <td className="p-2 text-right">{u.n_distinct_brand_stems}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Wire into root detail page**

Modify `frontend/src/pages/ExplorerAddressRootDetail.tsx`. Add the import:

```typescript
import AddressUnitsAtRoot from "../components/explorer/AddressUnitsAtRoot";
```

Find the existing render body (after the breakdowns, before the party-sides list). Insert the new component. The root key passed to the component must include city — but the existing root pages use `<num>|<name>` keys WITHOUT city. **For H1 we ship a transitional behavior**: the AddressUnitsAtRoot component constructs its own city-aware key by reading the city of the root's parties. Since H1 doesn't add city to the root_summary, the simplest approach is:

Read the `useParams` `key` (which is `<num>|<name>`). The component will need a city to make the API call. For now, if city is missing from the root key, default to the most common city across the root's parties.

A simpler approach for H1: assume city = "toronto" (the dominant city in our data) when constructing the root-units key. Document this as a known H1 limitation; H2 or a later plan will add city to the root_summary key proper.

Actually the cleanest approach: the new endpoint accepts a 3-part key `city|num|name`. The frontend calls it with the city from one of the parties at the root. Easiest: extend the existing root detail endpoint to also return the city of its parties (`SELECT DISTINCT city FROM party_fingerprints WHERE street_number=? AND street_name=?`).

For H1's scope: pass the rootKey (num|name) and let the AddressUnitsAtRoot component fetch the city itself or fall back to "toronto". To avoid more refactoring of the root page, do the SIMPLEST thing:

In `AddressUnitsAtRoot`, derive the city by calling `/api/explorer/addresses/roots/{key}` first to get its city, then call `/units`. **Or** add city as a prop and have the parent page provide it.

For H1, **add city as a prop** and update the parent root detail page to also accept city via URL params (optional `?city=toronto`). If absent, the AddressUnitsAtRoot section just shows nothing or an empty state.

Concrete: Update `<AddressUnitsAtRoot />` to:

```typescript
<AddressUnitsAtRoot rootKey={`${city}|${num}|${name}`} />
```

Where `city` comes from a separate fetch or URL query param. The simplest path: parse the `key` param in the root detail page, then make a side fetch to get the city.

**For this task's scope**: render the AddressUnitsAtRoot section ONLY if city can be determined. Read it from the URL query param `?city=toronto`. If absent, render a small "Specify ?city=... in URL to see unit breakdowns" message.

```typescript
import { useParams, useSearchParams } from "react-router-dom";

export default function ExplorerAddressRootDetail() {
  const { key } = useParams<{ key: string }>();
  const [searchParams] = useSearchParams();
  const city = searchParams.get('city') || '';
  // ... existing code ...

  // After the existing breakdowns, before parties list:
  {city && key && (
    <AddressUnitsAtRoot rootKey={`${city}|${key}`} />
  )}
  {!city && (
    <Text size="1" style={{ color: "var(--gray-9)" }} className="mt-4 block">
      Tip: append <span className="font-mono">?city=toronto</span> to the URL to see the unit-by-unit breakdown.
    </Text>
  )}
}
```

This keeps H1 narrow. A follow-up plan will properly add city to the root summary keys.

- [ ] **Step 4: TypeScript check + browser smoke**

```bash
cd frontend && npx tsc --noEmit
# Expected: no errors
```

Visit `http://localhost:5174/explorer/addresses/roots/66%7Cwellington?city=toronto` — verify the units table renders with the seeded data.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/index.ts \
        frontend/src/components/explorer/AddressUnitsAtRoot.tsx \
        frontend/src/pages/ExplorerAddressRootDetail.tsx
git commit -m "feat(layer2): Units-at-root section on Address Root detail page"
```

---

### Task 8: Frontend — Address Unit detail page

**Files:**
- Create: `frontend/src/pages/ExplorerAddressUnitDetail.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create the page**

`frontend/src/pages/ExplorerAddressUnitDetail.tsx`:

```typescript
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Heading, Text, Badge } from "@radix-ui/themes";
import { fetchApi } from "../api/client";
import type { AddressUnitSummary } from "../types";
import ExplorerTabs from "../components/explorer/ExplorerTabs";
import AddressTabs from "../components/explorer/AddressTabs";


function unitTitle(u: AddressUnitSummary): string {
  const parts = [
    u.street_number,
    u.street_name,
    u.street_suffix,
    u.street_direction,
    u.suite_type,
    u.suite_number,
  ].filter(Boolean);
  return parts.join(' ');
}


export default function ExplorerAddressUnitDetail() {
  const { key } = useParams<{ key: string }>();
  const [data, setData] = useState<AddressUnitSummary | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!key) return;
    fetchApi<AddressUnitSummary>(`/explorer/addresses/units/${encodeURIComponent(key)}`)
      .then(setData).catch((e) => setErr(String(e)));
  }, [key]);

  if (err) return <div className="p-6"><Text color="tomato">{err}</Text></div>;
  if (!data) return <div className="p-6"><Text size="2" style={{ color: "var(--gray-9)" }}>Loading…</Text></div>;

  // Reconstruct the root key for the back link
  const rootKey = `${data.street_number}|${data.street_name}`;
  const rootHref = `/explorer/addresses/roots/${encodeURIComponent(rootKey)}?city=${encodeURIComponent(data.city)}`;

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <ExplorerTabs />
      <AddressTabs />
      <Link to={rootHref} className="text-[13px] no-underline"
            style={{ color: "var(--accent-11)" }}>
        ← Address Root: {data.street_number} {data.street_name}
      </Link>

      <div className="flex items-baseline gap-3 mt-2 mb-5 flex-wrap">
        <Heading size="6" className="font-mono">{unitTitle(data)}</Heading>
        <Text size="2" style={{ color: "var(--gray-9)" }}>{data.city}</Text>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Parties" value={data.n_party_sides.toLocaleString()} />
        <StatCard label="Distinct stems" value={data.n_distinct_brand_stems.toLocaleString()} />
        <StatCard label="Dominant stem"
                  value={data.dominant_stem ? data.dominant_stem : '—'} />
        <StatCard label="Dominance share"
                  value={data.dominance_share != null
                    ? `${(data.dominance_share * 100).toFixed(0)}%`
                    : '—'} />
      </div>

      {data.dominant_stem && data.dominance_share >= 0.6 && (
        <div className="mt-4">
          <Badge color="jade">
            uniquely tenanted → {data.dominant_stem}
          </Badge>
        </div>
      )}
    </div>
  );
}


function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
      <Text size="1" style={{ color: "var(--gray-9)" }}>{label}</Text>
      <Heading size="5" mt="2">{value}</Heading>
    </div>
  );
}
```

- [ ] **Step 2: Register the route in App.tsx**

In `frontend/src/App.tsx`, add the lazy import:

```typescript
const ExplorerAddressUnitDetail = lazy(() => import("./pages/ExplorerAddressUnitDetail"));
```

Add the route alongside the existing addresses routes:

```typescript
<Route path="/explorer/addresses/units/:key" element={<ExplorerAddressUnitDetail />} />
```

- [ ] **Step 3: TypeScript check + browser smoke**

```bash
cd frontend && npx tsc --noEmit
```

Click the unit row from the root detail page → verify the unit detail page renders.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/ExplorerAddressUnitDetail.tsx frontend/src/App.tsx
git commit -m "feat(layer2): Address Unit detail page"
```

---

### Task 9: Real-DB rebuild + verification

**Files:** none (run + verify only)

- [ ] **Step 1: Apply the migration to the real DB**

```bash
python -m cleo.database.migrations.016_address_unit_summary
sqlite3 data/cleo.db "SELECT COUNT(*) FROM sqlite_master WHERE name='address_unit_summary'"
# Expected: 1
```

- [ ] **Step 2: Run the full Layer 1 + Layer 2 builder**

```bash
python -m cleo.discovery_v2 2>&1 | tee /tmp/h1-rebuild.log
```

Expected: builder completes; `address_unit_summary` populated with thousands of rows; `auto_groups` rebuilt with `address_unit` anchors.

- [ ] **Step 3: Verify TD Bank false positive eliminated**

```bash
sqlite3 data/cleo.db "
SELECT agm.auto_group_id, ag.canonical_stem, agm.match_score
FROM auto_group_members agm
JOIN auto_groups ag ON ag.auto_group_id = agm.auto_group_id
WHERE agm.source_id = 'RT196095' AND agm.side = 'seller'
"
```

Expected: empty result OR a low-score attachment to a group whose canonical_stem is NOT 'kingsett'.

- [ ] **Step 4: Verify the 90 false positives at 66 Wellington are cleaned up**

```bash
sqlite3 data/cleo.db "
SELECT COUNT(*) AS n
FROM auto_group_members agm
JOIN party_fingerprints pf ON pf.source_id=agm.source_id AND pf.side=agm.side
JOIN auto_groups ag ON ag.auto_group_id=agm.auto_group_id
WHERE ag.canonical_stem='kingsett'
  AND pf.street_number='66' AND pf.street_name='wellington'
  AND (pf.phone IS NULL OR pf.phone='')
  AND (pf.contact_fingerprint IS NULL OR pf.contact_fingerprint='')
  AND (pf.suite_number IS NULL OR pf.suite_number='' OR
       LOWER(pf.suite_number) NOT IN ('4400'))
"
# Expected: a much smaller number than the 90 we saw pre-H1.
```

- [ ] **Step 5: Verify KingSett's anchors now reference suite-level units**

```bash
sqlite3 -column -header data/cleo.db "
SELECT anchor_type, anchor_value, score
FROM auto_group_anchors
WHERE auto_group_id IN (
  SELECT auto_group_id FROM auto_groups WHERE canonical_stem='kingsett' LIMIT 1
)
AND anchor_type='address_unit'
ORDER BY score DESC LIMIT 10
"
# Expected: anchors like 'toronto|66|wellington|street|west|suite|4400',
# 'toronto|40|king|street|east|suite|3700', etc.
```

- [ ] **Step 6: Verify DH Management's three address tenures are visible**

```bash
sqlite3 -column -header data/cleo.db "
SELECT anchor_type, anchor_value
FROM auto_group_anchors
WHERE auto_group_id IN (
  SELECT auto_group_id FROM auto_groups WHERE canonical_stem='dh' LIMIT 1
)
AND anchor_type='address_unit'
ORDER BY score DESC LIMIT 10
"
# Expected: distinct anchors for 180 Shorting, 160 Shorting, and 2555 Eglinton.
```

- [ ] **Step 7: Capture verification notes**

Write to `docs/superpowers/run-notes/2026-04-29-layer-2-plan-h1-verification.md`:

```markdown
# Plan H1 Verification Notes

Date: 2026-04-29

## Migration
- 016 applied: address_unit_summary table populated with N rows.
- anchor_uniqueness CHECK constraint dropped.

## TD Bank false positive
- RT196095 attachment status: <empty / attached to which group>
- 90 false positives at 66 Wellington reduced to: <new count>

## Address-unit anchors visible
- KingSett anchors include: <list of unit anchors>
- DH Management anchors include: <list of unit anchors>

## Algorithm rebuild
- Total auto_groups: <count>
- Tier breakdown: confirmed=<>, probable=<>, candidate=<>
- Total auto_group_anchors: <count>
- Total auto_group_members: <count>
```

- [ ] **Step 8: Commit verification notes**

```bash
git add docs/superpowers/run-notes/2026-04-29-layer-2-plan-h1-verification.md
git commit -m "docs: Plan H1 verification notes"
```

---

## Self-Review

**Spec coverage check** (against `docs/superpowers/specs/2026-04-29-layer-2-plan-h-timeline-aware-attribution-design.md` Plan H1 section):

- ✅ **New `address_unit` anchor type with city in the key** — Task 1 (migration), Task 3 (Stage A2 produces it), Task 4 (Stage A4 uses it).
- ✅ **Drop `address_root` and `address_base` from auto_group_anchors** — Task 3 (anchor_scores stops producing them; the auto_group_anchors table will repopulate without them on next builder run).
- ✅ **Layer 1 UI: Units at this root** — Task 5 (backend endpoint), Task 7 (frontend section).
- ✅ **Match-score updates** — Task 4 (no-anchor + no-stem → 0.0; address_unit + contact → 0.85; etc.).
- ✅ **Migration safety** — Task 1 drops the CHECK constraint; existing data preserved.
- ✅ **Real-DB verification** — Task 9 confirms TD Bank case fixed.

Type consistency: `AddressUnitSummary` defined in Task 7, used in Task 8. `address_unit_summary` table schema defined in Task 1, populated by Task 2, queried by Tasks 5/6.

**Known limitation deferred**: city is NOT added to `address_root_summary` or `address_base_summary` keys in H1 (deferred to a future plan). The Layer 1 root pages still use `<num>|<name>` keys; the new units endpoint takes `<city>|<num>|<name>` keys, and the frontend root detail uses a `?city=` query param to bridge. This is sufficient for Toronto-heavy data but creates a known UX wart for cross-city searches. Will be cleaned up when H2 lands or a separate "city-everywhere" plan ships.

No placeholders. Code in every step.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-29-layer-2-plan-h1-unit-anchors.md`. 9 tasks. Two execution options:

**1. Subagent-Driven (recommended)** — Fresh subagent per task with two-stage review.

**2. Inline Execution** — In this session with checkpoints.

Which approach?
