# Layer 2 Plan H2 — Timelines and Tenures Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-04-29-layer-2-plan-h-timeline-aware-attribution-design.md` (Plan H2 section).

**Goal:** Replace the timeless anchor model with a time-windowed one. Every anchor-to-group attachment carries `(start_date, end_date)`. Contact tenures are inferred from the data. Conflicts are surfaced as discrete events for human review, not silent confidence drops.

**Architecture:** A new Stage A0 (`cleo/discovery_v2/timelines.py`) builds chronological event lists per anchor. Stage A2 walks each timeline to detect tenure boundaries (stem changes, long gaps), emitting one row per tenure into the new `auto_group_anchor_tenures` table. Stage A3 seeds groups from tenures rather than static anchors. Stage A4 attaches a party only when its `sale_date` falls inside a tenure window for exactly one group; ambiguity emits a conflict flag instead of attaching. A new Stage A6 (`cleo/discovery_v2/conflicts.py`) scans tenures after A2 for the four conflict types (`anchor_reassignment`, `contact_overlap`, `abrupt_tenure_end`, `transient_tenure`) and writes them to `auto_conflict_flags` for the future Conflicts UI.

**Tech Stack:** Python 3.12, SQLite, FastAPI, pytest. No frontend changes — those belong to Plan H3.

**Migration:** Migration 017 adds three tables (`auto_group_anchor_tenures`, `auto_contact_tenures`, `auto_conflict_flags`). The existing `auto_group_anchors` is kept (rebuilt by H2 as a denormalized "current state" snapshot of the most-recent tenure per anchor) so downstream API code keeps working without per-route rewrites. The source of truth is the new tenure tables.

---

## Glossary (locked from the spec — used strictly)

| Term | Meaning |
|---|---|
| **Timeline** | Chronological list of party events for a single anchor or contact, ordered by `sale_date`. In-memory; not stored. |
| **Tenure** | A time window during which a single dominant stem characterized an anchor. Has `start_date`, `end_date` (NULL = ongoing), `n_party_sides_in_window`, `dominance_share_in_window`, `score`. |
| **Run** | The in-progress tenure being built as the timeline walker advances. Becomes a tenure when closed by a stem change or large gap. |
| **Conflict flag** | One of `anchor_reassignment`, `contact_overlap`, `abrupt_tenure_end`, `transient_tenure`. Surfaces for human review only — never auto-resolves. |
| **Anchor** | Same definition from H1: phone, address_unit, contact_fingerprint. Address_unit keys are 7-pipe-delimited. |
| **Active tenure** | A tenure whose `end_date` is NULL (ongoing) or within the last `RECENT_TENURE_DAYS` (3 years). |
| **Dormant tenure** | A tenure whose `end_date` is older than `RECENT_TENURE_DAYS`. |
| **Orphan party** | A party whose anchors don't intersect any group's tenure containing the party's sale_date. |

---

## File Structure

**Backend (new):**
- `cleo/database/migrations/017_tenure_tables.py` — schema migration.
- `cleo/discovery_v2/timelines.py` — Stage A0 timeline builders (per-anchor and per-contact).
- `cleo/discovery_v2/conflicts.py` — Stage A6 conflict detector.

**Backend (modified):**
- `cleo/discovery_v2/constants.py` — add tenure-related knobs.
- `cleo/discovery_v2/anchor_scores.py` — Stage A2 walks timelines and emits tenures (not just static anchor_uniqueness rows).
- `cleo/discovery_v2/seeding.py` — Stage A3 reads tenures, writes `auto_group_anchor_tenures`. Also computes `auto_contact_tenures` per seeded group.
- `cleo/discovery_v2/expansion.py` — Stage A4 attaches based on tenure window containing the party's sale_date.
- `cleo/discovery_v2/auto_groups.py` — wire A0/A6 into the orchestrator.

**Tests (new):**
- `tests/test_migration_017_tenure_tables.py`
- `tests/test_discovery_v2_timelines.py`
- `tests/test_discovery_v2_conflicts.py`

**Tests (modified):**
- `tests/test_discovery_v2_anchor_scores.py` — extend for windowed dominance.
- `tests/test_discovery_v2_seeding.py` — extend for tenure rows + contact tenures.
- `tests/test_discovery_v2_expansion.py` — extend for time-aware attachment.

---

## Pre-flight context for the implementer

**Source of truth shift.** After H2 lands:
- `auto_group_anchor_tenures` (NEW) is the source of truth for which anchors back which groups, with windows.
- `auto_group_anchors` (existing) is rebuilt as a denormalized snapshot — for each (auto_group_id, anchor_type, anchor_value), one row carrying the most recent tenure's `score`. This keeps API code that reads `auto_group_anchors` working unchanged.
- `anchor_uniqueness` (existing) is rebuilt as a snapshot of the most recent tenure per anchor.

**Date format.** All dates are ISO `YYYY-MM-DD` strings. SQLite stores them as TEXT and string-compares lexicographically (works for ISO format). When `end_date` is NULL it means "ongoing."

**Date containment.** A party's sale_date is in a tenure when:
```
tenure.start_date <= party.sale_date AND
party.sale_date <= COALESCE(tenure.end_date, '9999-12-31')
```

**Run-detection algorithm (the heart of A2).** Given a chronological list of events for one anchor, each carrying its side's dominant stem (or NULL):

```
for each event in chronological order:
    if no current run:
        start a new run with this event's stem (or skip if stem is NULL until we see one)
    else:
        if event.sale_date - last_event_in_run.sale_date > MAX_TENURE_GAP_DAYS:
            close current run; start a new run with this event
        elif event.stem != current_run.dominant_stem:
            buffer the off-stem events
            if buffer.length > RUN_GRACE_EVENTS:
                close current run (end_date = last on-stem event in run)
                start a new run with the buffered off-stem events
            else:
                continue accumulating (off-stem events will dilute dominance but stay in the run)
        else:
            extend current run with this event
close the final run
```

Tenures with `n_party_sides_in_window < MIN_TENURE_PARTY_COUNT` or `dominance_share_in_window < STEM_PROMOTION_DOMINANCE` are still emitted, but flagged as `transient_tenure` by Stage A6.

**Tunable knobs added to constants.py.** All five are needed:
- `MAX_TENURE_GAP_DAYS = 730` (2 years; gap larger than this splits a run)
- `RECENT_TENURE_DAYS = 1095` (3 years; tenure ended later than this counts as active)
- `MIN_PERMANENT_TENURE_DAYS = 365` (1 year; shorter is transient)
- `MIN_TENURE_PARTY_COUNT = 3` (at least 3 parties to count as a real tenure)
- `RUN_GRACE_EVENTS = 3` (how many off-stem events to tolerate before splitting)

**Compatibility with H1.** H2 inherits the H1 anchor types (phone / address_unit / contact). The `address_unit` key shape is unchanged — still 7-pipe-delimited.

**Stage A4 behavior on no tenures.** A side with no anchors at all is an orphan (already H1 behavior). A side with anchors that don't match any tenure for its sale_date is also an orphan. Don't fall back to "any anchor in any group" — that defeats the point.

**Stage A4 conflict path.** If two anchors on the same party point to two different groups whose tenures both contain the sale_date, the party is NOT attached, and one `auto_conflict_flags` row is emitted with `conflict_type='contact_overlap'` (if a contact is what's shared) or `'anchor_reassignment'` (if it's a phone/address_unit being reassigned over time).

**Performance.** Spec target: full Layer 2 rebuild in < 5 minutes (currently ~30s pre-H2). Stage A2 is the most expensive step. Building timelines is one ORDER BY query per anchor (~250k anchors); chunked iteration is fine.

---

## Tasks

### Task 1: Migration 017 — tenure tables + conflict flags

**Files:**
- Create: `cleo/database/migrations/017_tenure_tables.py`
- Test: `tests/test_migration_017_tenure_tables.py`

- [ ] **Step 1: Write failing test**

`tests/test_migration_017_tenure_tables.py`:

```python
import importlib
import sqlite3


_m = importlib.import_module('cleo.database.migrations.017_tenure_tables')


def _empty_db():
    return sqlite3.connect(':memory:')


def test_migration_creates_auto_group_anchor_tenures():
    conn = _empty_db()
    _m.migrate(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(auto_group_anchor_tenures)")}
    assert cols >= {
        'id', 'auto_group_id', 'anchor_type', 'anchor_value',
        'start_date', 'end_date',
        'n_party_sides_in_window', 'dominance_share_in_window',
        'score', 'discovered_at',
    }


def test_migration_creates_auto_contact_tenures():
    conn = _empty_db()
    _m.migrate(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(auto_contact_tenures)")}
    assert cols >= {
        'id', 'contact_fingerprint', 'auto_group_id',
        'start_date', 'end_date',
        'n_party_sides_in_window', 'discovered_at',
    }


def test_migration_creates_auto_conflict_flags():
    conn = _empty_db()
    _m.migrate(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(auto_conflict_flags)")}
    assert cols >= {
        'id', 'conflict_type', 'entity_type', 'entity_value', 'entity_subtype',
        'group_a', 'group_b', 'date_observed', 'description', 'discovered_at',
    }


def test_migration_anchor_tenures_check_constraint():
    """anchor_type must be one of phone / address_unit / contact."""
    conn = _empty_db()
    _m.migrate(conn)
    # Valid value succeeds
    conn.execute(
        "INSERT INTO auto_group_anchor_tenures "
        "(auto_group_id, anchor_type, anchor_value, start_date, end_date, "
        " n_party_sides_in_window, dominance_share_in_window, score) "
        "VALUES ('AGRP_00001', 'address_unit', 'toronto|180|shorting|road|||', "
        "        '2018-01-01', NULL, 12, 0.85, 4.2)"
    )
    # Invalid anchor_type (the now-extinct address_root) raises
    import pytest
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO auto_group_anchor_tenures "
            "(auto_group_id, anchor_type, anchor_value, start_date, "
            " n_party_sides_in_window, dominance_share_in_window, score) "
            "VALUES ('AGRP_00002', 'address_root', '180|shorting', "
            "        '2018-01-01', 12, 0.85, 4.2)"
        )


def test_migration_conflict_flags_check_constraint():
    conn = _empty_db()
    _m.migrate(conn)
    # Valid conflict_type
    conn.execute(
        "INSERT INTO auto_conflict_flags "
        "(conflict_type, entity_type, entity_value, description) "
        "VALUES ('anchor_reassignment', 'anchor', '4162655055', 'test')"
    )
    # Invalid conflict_type raises
    import pytest
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO auto_conflict_flags "
            "(conflict_type, entity_type, entity_value, description) "
            "VALUES ('made_up_thing', 'anchor', 'X', 'test')"
        )


def test_migration_indexes_exist():
    conn = _empty_db()
    _m.migrate(conn)
    idx = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
    )}
    assert 'idx_agat_group' in idx
    assert 'idx_agat_anchor' in idx
    assert 'idx_act_contact' in idx
    assert 'idx_act_group' in idx
    assert 'idx_acf_type' in idx
    assert 'idx_acf_entity' in idx


def test_migration_is_idempotent():
    conn = _empty_db()
    _m.migrate(conn)
    _m.migrate(conn)  # should not raise
    n = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master "
        "WHERE type='table' AND name='auto_group_anchor_tenures'"
    ).fetchone()[0]
    assert n == 1
```

- [ ] **Step 2: Run, confirm fail**

```bash
PYTHONPATH=. pytest tests/test_migration_017_tenure_tables.py -v
# Expected: ImportError on the missing migration module
```

- [ ] **Step 3: Create the migration**

`cleo/database/migrations/017_tenure_tables.py`:

```python
"""
Migration 017: Layer 2 tenure tables + conflict flags.

Adds three new derived tables that replace the static-anchor model with a
time-windowed one:

- auto_group_anchor_tenures: one row per (auto_group_id, anchor, time-window).
  Source of truth for which anchors back which groups, with start/end dates.
- auto_contact_tenures: one row per (contact_fingerprint, auto_group_id, window).
  When a person was associated with a group.
- auto_conflict_flags: one row per detected anomaly (anchor reassigned, contact
  overlap across groups, etc.). Surfaces for human review only.

The existing auto_group_anchors and anchor_uniqueness tables continue to exist
and are rebuilt by Layer 2 as denormalized "current state" snapshots so
downstream API code keeps working without per-route rewrites.
"""
from __future__ import annotations
import os
import sqlite3


def migrate(conn: sqlite3.Connection) -> None:
    print('Migration 017: tenure tables + conflict flags...')

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS auto_group_anchor_tenures (
            id                          INTEGER PRIMARY KEY AUTOINCREMENT,
            auto_group_id               TEXT NOT NULL,
            anchor_type                 TEXT NOT NULL
                CHECK (anchor_type IN ('phone','address_unit','contact')),
            anchor_value                TEXT NOT NULL,
            start_date                  TEXT NOT NULL,
            end_date                    TEXT,
            n_party_sides_in_window     INTEGER NOT NULL,
            dominance_share_in_window   REAL NOT NULL,
            score                       REAL NOT NULL,
            discovered_at               TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_agat_group
            ON auto_group_anchor_tenures(auto_group_id);
        CREATE INDEX IF NOT EXISTS idx_agat_anchor
            ON auto_group_anchor_tenures(anchor_type, anchor_value);

        CREATE TABLE IF NOT EXISTS auto_contact_tenures (
            id                       INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_fingerprint      TEXT NOT NULL,
            auto_group_id            TEXT NOT NULL,
            start_date               TEXT NOT NULL,
            end_date                 TEXT,
            n_party_sides_in_window  INTEGER NOT NULL,
            discovered_at            TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_act_contact
            ON auto_contact_tenures(contact_fingerprint);
        CREATE INDEX IF NOT EXISTS idx_act_group
            ON auto_contact_tenures(auto_group_id);

        CREATE TABLE IF NOT EXISTS auto_conflict_flags (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            conflict_type   TEXT NOT NULL
                CHECK (conflict_type IN
                       ('anchor_reassignment','contact_overlap',
                        'abrupt_tenure_end','transient_tenure')),
            entity_type     TEXT NOT NULL
                CHECK (entity_type IN ('anchor','contact')),
            entity_value    TEXT NOT NULL,
            entity_subtype  TEXT,
            group_a         TEXT,
            group_b         TEXT,
            date_observed   TEXT,
            description     TEXT NOT NULL,
            discovered_at   TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_acf_type
            ON auto_conflict_flags(conflict_type);
        CREATE INDEX IF NOT EXISTS idx_acf_entity
            ON auto_conflict_flags(entity_type, entity_value);
    """)
    conn.commit()
    print('Migration 017 complete.')


if __name__ == '__main__':
    db_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'data', 'cleo.db')
    conn = sqlite3.connect(db_path)
    migrate(conn)
    conn.close()
```

- [ ] **Step 4: Run tests, confirm pass**

```bash
PYTHONPATH=. pytest tests/test_migration_017_tenure_tables.py -v
# Expected: 7 passed
```

- [ ] **Step 5: Apply to real DB**

```bash
python -m cleo.database.migrations.017_tenure_tables
sqlite3 data/cleo.db "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'auto_%tenure%' OR name='auto_conflict_flags'"
# Expected: 3 rows — auto_group_anchor_tenures, auto_contact_tenures, auto_conflict_flags
```

- [ ] **Step 6: Commit**

```bash
git add cleo/database/migrations/017_tenure_tables.py \
        tests/test_migration_017_tenure_tables.py
git commit -m "feat(layer2): migration 017 — tenure tables + conflict flags"
```

---

### Task 2: Constants — tenure knobs

**Files:**
- Modify: `cleo/discovery_v2/constants.py`

- [ ] **Step 1: Add the five new constants**

Append to `cleo/discovery_v2/constants.py` (at the end of the file):

```python
# ── Plan H2: Tenure detection ──────────────────────────────────────────────
# Gap larger than this between consecutive events on the same anchor splits
# the run into two tenures (operator likely changed offices / phones).
MAX_TENURE_GAP_DAYS = 730  # 2 years

# Tenure with end_date later than (today - this) counts as "active" for
# seeding purposes. Anchors whose latest tenure ended before this fall into
# "dormant" (still seedable, but flagged as historical).
RECENT_TENURE_DAYS = 1095  # 3 years

# A tenure shorter than this with low volume gets a 'transient_tenure'
# conflict flag.
MIN_PERMANENT_TENURE_DAYS = 365  # 1 year

# Tenures with fewer events than this are flagged as transient (4950 Yonge
# one-off case).
MIN_TENURE_PARTY_COUNT = 3

# How many off-stem events to buffer before splitting a run into a new
# tenure. Smaller value = stricter tenure boundaries.
RUN_GRACE_EVENTS = 3
```

- [ ] **Step 2: Sanity-check by importing**

```bash
python -c "from cleo.discovery_v2.constants import MAX_TENURE_GAP_DAYS, RECENT_TENURE_DAYS, MIN_PERMANENT_TENURE_DAYS, MIN_TENURE_PARTY_COUNT, RUN_GRACE_EVENTS; print(MAX_TENURE_GAP_DAYS, RECENT_TENURE_DAYS, MIN_PERMANENT_TENURE_DAYS, MIN_TENURE_PARTY_COUNT, RUN_GRACE_EVENTS)"
# Expected: 730 1095 365 3 3
```

- [ ] **Step 3: Commit**

```bash
git add cleo/discovery_v2/constants.py
git commit -m "feat(layer2): tunable knobs for Plan H2 tenure detection"
```

---

### Task 3: Stage A0 — Timeline builder

**Files:**
- Create: `cleo/discovery_v2/timelines.py`
- Test: `tests/test_discovery_v2_timelines.py`

- [ ] **Step 1: Write failing test**

`tests/test_discovery_v2_timelines.py`:

```python
import sqlite3
import pytest
from cleo.discovery_v2.timelines import (
    build_anchor_timeline,
    iter_all_anchor_timelines,
)


def _make_db():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE party_fingerprints (
            source_id TEXT, side TEXT, phone TEXT, contact_fingerprint TEXT,
            city TEXT,
            street_number TEXT, street_name TEXT, street_suffix TEXT,
            street_direction TEXT, suite_type TEXT, suite_number TEXT,
            sale_date TEXT,
            PRIMARY KEY (source_id, side)
        );
        CREATE TABLE party_atoms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT, side TEXT, atom_type TEXT, atom_value TEXT, source_field TEXT
        );
        CREATE TABLE brand_stem_phrase_map (
            phrase TEXT PRIMARY KEY, stem TEXT NOT NULL, confidence REAL NOT NULL
        );
    """)
    return conn


def _seed(conn, sid, side, phrase=None, *, phone=None, contact=None,
          city=None, street_number=None, street_name=None,
          sale_date=None):
    conn.execute(
        """INSERT INTO party_fingerprints
            (source_id, side, phone, contact_fingerprint,
             city, street_number, street_name, sale_date)
           VALUES (?,?,?,?,?,?,?,?)""",
        (sid, side, phone, contact, city, street_number, street_name, sale_date),
    )
    if phrase:
        conn.execute(
            "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
            "VALUES (?, ?, 'brand_phrase', ?, 'party_name')",
            (sid, side, phrase),
        )


def _map(conn, phrase, stem):
    conn.execute(
        "INSERT OR IGNORE INTO brand_stem_phrase_map (phrase, stem, confidence) VALUES (?,?,1.0)",
        (phrase, stem),
    )


def test_anchor_timeline_returns_events_in_chronological_order():
    conn = _make_db()
    _seed(conn, 'RT3', 'seller', 'kingsett capital', phone='P1', sale_date='2020-05-01')
    _seed(conn, 'RT1', 'seller', 'kingsett capital', phone='P1', sale_date='2018-03-01')
    _seed(conn, 'RT2', 'seller', 'kingsett capital', phone='P1', sale_date='2019-07-15')
    _map(conn, 'kingsett capital', 'kingsett')

    events = build_anchor_timeline(conn, 'phone', 'P1')

    dates = [e['sale_date'] for e in events]
    assert dates == sorted(dates)
    assert all(e['stem'] == 'kingsett' for e in events)


def test_anchor_timeline_includes_unmapped_events_with_null_stem():
    conn = _make_db()
    _seed(conn, 'RT1', 'seller', 'kingsett capital', phone='P1', sale_date='2018-03-01')
    _seed(conn, 'RT2', 'seller', 'random co', phone='P1', sale_date='2019-07-15')
    _map(conn, 'kingsett capital', 'kingsett')
    # 'random co' is unmapped — phrase exists in atoms but no stem mapping

    events = build_anchor_timeline(conn, 'phone', 'P1')
    by_id = {e['source_id']: e for e in events}

    assert by_id['RT1']['stem'] == 'kingsett'
    assert by_id['RT2']['stem'] is None  # unmapped


def test_anchor_timeline_excludes_events_without_sale_date():
    conn = _make_db()
    _seed(conn, 'RT1', 'seller', 'kingsett capital', phone='P1', sale_date='2018-03-01')
    _seed(conn, 'RT2', 'seller', 'kingsett capital', phone='P1', sale_date=None)
    _map(conn, 'kingsett capital', 'kingsett')

    events = build_anchor_timeline(conn, 'phone', 'P1')
    assert len(events) == 1
    assert events[0]['source_id'] == 'RT1'


def test_anchor_timeline_address_unit_anchor():
    """Timeline for an address_unit anchor uses the 7-field key."""
    conn = _make_db()
    for sid, dt in (('RT1', '2018-01-01'), ('RT2', '2019-01-01')):
        _seed(conn, sid, 'seller', 'dh management',
              city='toronto', street_number='180', street_name='shorting',
              sale_date=dt)
    _map(conn, 'dh management', 'dh')

    key = 'toronto|180|shorting||||'
    events = build_anchor_timeline(conn, 'address_unit', key)
    assert len(events) == 2
    assert all(e['stem'] == 'dh' for e in events)


def test_iter_all_anchor_timelines_yields_each_anchor_once():
    conn = _make_db()
    # Two phones, three contacts, one address_unit
    _seed(conn, 'RT1', 'seller', 'a', phone='P1', sale_date='2018-01-01')
    _seed(conn, 'RT2', 'seller', 'a', phone='P2', sale_date='2019-01-01')
    _seed(conn, 'RT3', 'seller', 'a', contact='C1', sale_date='2020-01-01')
    _seed(conn, 'RT4', 'seller', 'a',
          city='toronto', street_number='180', street_name='shorting',
          sale_date='2018-06-01')
    _map(conn, 'a', 'alpha')

    timelines = list(iter_all_anchor_timelines(conn))

    types = sorted({(t, v) for t, v, events in timelines})
    assert ('phone', 'P1') in types
    assert ('phone', 'P2') in types
    assert ('contact', 'C1') in types
    assert ('address_unit', 'toronto|180|shorting||||') in types
    assert len(timelines) == 4


def test_iter_all_anchor_timelines_skips_anchors_with_no_dated_events():
    """An anchor whose every party has no sale_date is skipped (Stage A2 cannot
    place it in time anyway)."""
    conn = _make_db()
    _seed(conn, 'RT1', 'seller', 'a', phone='P1', sale_date=None)
    _map(conn, 'a', 'alpha')

    timelines = list(iter_all_anchor_timelines(conn))
    assert len(timelines) == 0


def test_anchor_timeline_returns_empty_for_unknown_anchor():
    conn = _make_db()
    events = build_anchor_timeline(conn, 'phone', 'UNKNOWN_PHONE')
    assert events == []
```

- [ ] **Step 2: Run, confirm fail**

```bash
PYTHONPATH=. pytest tests/test_discovery_v2_timelines.py -v
# Expected: ImportError on cleo.discovery_v2.timelines
```

- [ ] **Step 3: Create the module**

`cleo/discovery_v2/timelines.py`:

```python
"""Stage A0: per-anchor timeline builder.

Given an anchor (phone, address_unit, or contact), returns a chronological
list of party events with their dominant stem (or None if the side has no
stem-mapped brand phrases).

Used by Stage A2 (windowed dominance) to detect tenure boundaries and by
Stage A6 (conflict detection) to scan for reassignments. Not stored — the
timeline is rebuilt per-run.
"""
from __future__ import annotations
import sqlite3
from typing import Iterator


# SQL fragment that filters party_fingerprints (aliased pf) for the given
# anchor_type. Expects exactly one bind param: the anchor_value.
def _anchor_pf_clause(anchor_type: str) -> str:
    if anchor_type == 'phone':
        return "pf.phone = ?"
    if anchor_type == 'contact':
        return "pf.contact_fingerprint = ?"
    if anchor_type == 'address_unit':
        return (
            "(COALESCE(pf.city,'') || '|' || COALESCE(pf.street_number,'') || '|' || "
            "COALESCE(pf.street_name,'') || '|' || COALESCE(pf.street_suffix,'') || '|' || "
            "COALESCE(pf.street_direction,'') || '|' || COALESCE(pf.suite_type,'') || '|' || "
            "COALESCE(pf.suite_number,'')) = ?"
        )
    raise ValueError(f"Unknown anchor_type: {anchor_type!r}")


def build_anchor_timeline(
    conn: sqlite3.Connection, anchor_type: str, anchor_value: str,
) -> list[dict]:
    """Return chronologically-ordered events for the given anchor.

    Each event is a dict: {sale_date, source_id, side, stem}. The stem is
    the most-common stem across the side's brand_phrase atoms; None if the
    side has no stem-mapped phrases.
    """
    pf_clause = _anchor_pf_clause(anchor_type)
    rows = conn.execute(
        f"""
        SELECT pf.source_id, pf.side, pf.sale_date,
               (SELECT m.stem
                  FROM party_atoms pa
                  JOIN brand_stem_phrase_map m ON m.phrase = pa.atom_value
                 WHERE pa.source_id = pf.source_id
                   AND pa.side      = pf.side
                   AND pa.atom_type = 'brand_phrase'
                 GROUP BY m.stem
                 ORDER BY COUNT(*) DESC, m.stem ASC
                 LIMIT 1) AS stem
        FROM party_fingerprints pf
        WHERE {pf_clause}
          AND pf.sale_date IS NOT NULL AND pf.sale_date != ''
        ORDER BY pf.sale_date ASC, pf.source_id ASC, pf.side ASC
        """,
        (anchor_value,),
    ).fetchall()
    return [
        {
            'sale_date': r['sale_date'],
            'source_id': r['source_id'],
            'side':      r['side'],
            'stem':      r['stem'],
        }
        for r in rows
    ]


def iter_all_anchor_timelines(
    conn: sqlite3.Connection,
) -> Iterator[tuple[str, str, list[dict]]]:
    """Yield (anchor_type, anchor_value, timeline) for every anchor with at
    least one dated event."""
    # Pre-collect all anchor values per type, then build timelines.
    # Each branch issues two queries — list anchors, build timelines — but
    # both are bounded by the count of dated party_fingerprints rows.

    # Phones
    phones = [r[0] for r in conn.execute(
        "SELECT DISTINCT phone FROM party_fingerprints "
        "WHERE phone IS NOT NULL AND phone != '' "
        "  AND sale_date IS NOT NULL AND sale_date != ''"
    )]
    for v in phones:
        events = build_anchor_timeline(conn, 'phone', v)
        if events:
            yield ('phone', v, events)

    # Contacts
    contacts = [r[0] for r in conn.execute(
        "SELECT DISTINCT contact_fingerprint FROM party_fingerprints "
        "WHERE contact_fingerprint IS NOT NULL AND contact_fingerprint != '' "
        "  AND sale_date IS NOT NULL AND sale_date != ''"
    )]
    for v in contacts:
        events = build_anchor_timeline(conn, 'contact', v)
        if events:
            yield ('contact', v, events)

    # Address units (require the three load-bearing fields to compute a key)
    units = [r[0] for r in conn.execute(
        "SELECT DISTINCT ("
        "  COALESCE(city,'') || '|' || COALESCE(street_number,'') || '|' || "
        "  COALESCE(street_name,'') || '|' || COALESCE(street_suffix,'') || '|' || "
        "  COALESCE(street_direction,'') || '|' || COALESCE(suite_type,'') || '|' || "
        "  COALESCE(suite_number,'')"
        ") FROM party_fingerprints "
        "WHERE city IS NOT NULL AND city != '' "
        "  AND street_number IS NOT NULL AND street_number != '' "
        "  AND street_name IS NOT NULL AND street_name != '' "
        "  AND sale_date IS NOT NULL AND sale_date != ''"
    )]
    for v in units:
        events = build_anchor_timeline(conn, 'address_unit', v)
        if events:
            yield ('address_unit', v, events)
```

- [ ] **Step 4: Run tests, confirm pass**

```bash
PYTHONPATH=. pytest tests/test_discovery_v2_timelines.py -v
# Expected: 7 passed
```

- [ ] **Step 5: Commit**

```bash
git add cleo/discovery_v2/timelines.py tests/test_discovery_v2_timelines.py
git commit -m "feat(layer2): Stage A0 timeline builder"
```

---

### Task 4: Stage A2 — windowed-dominance tenure detector

This task replaces the static `anchor_uniqueness` logic with a tenure-emitting walker. After this task: `anchor_uniqueness` is rebuilt as a "current state" snapshot of the most-recent tenure per anchor, but the underlying tenure data is captured in a new in-memory return value that Stage A3 will consume in Task 5.

**Files:**
- Create: `cleo/discovery_v2/tenures.py` — pure-Python tenure detector (testable without DB).
- Modify: `cleo/discovery_v2/anchor_scores.py` — call into the detector, populate `anchor_uniqueness` from latest tenures, and persist tenures to a new staging table that Stage A3 reads.
- Test: `tests/test_discovery_v2_tenures.py` (new)
- Modify: `tests/test_discovery_v2_anchor_scores.py`

- [ ] **Step 1: Write failing tests for the pure-Python detector**

`tests/test_discovery_v2_tenures.py`:

```python
import pytest
from cleo.discovery_v2.tenures import detect_tenures


def _evt(date, sid, stem):
    return {'sale_date': date, 'source_id': sid, 'side': 'seller', 'stem': stem}


def test_detect_tenures_single_dominant_stem_is_one_tenure():
    timeline = [
        _evt('2018-01-01', 'RT1', 'kingsett'),
        _evt('2019-06-01', 'RT2', 'kingsett'),
        _evt('2021-03-01', 'RT3', 'kingsett'),
    ]
    tenures = detect_tenures(timeline)
    assert len(tenures) == 1
    t = tenures[0]
    assert t['dominant_stem'] == 'kingsett'
    assert t['start_date'] == '2018-01-01'
    assert t['end_date'] == '2021-03-01'
    assert t['n_party_sides'] == 3
    assert t['dominance_share'] == pytest.approx(1.0)


def test_detect_tenures_long_gap_splits_run():
    """A gap > MAX_TENURE_GAP_DAYS (730) splits."""
    timeline = [
        _evt('2010-01-01', 'A', 'kingsett'),
        _evt('2011-01-01', 'B', 'kingsett'),
        # 2-year+1-day gap — should split
        _evt('2013-01-02', 'C', 'kingsett'),
        _evt('2014-01-01', 'D', 'kingsett'),
    ]
    tenures = detect_tenures(timeline)
    assert len(tenures) == 2
    assert tenures[0]['start_date'] == '2010-01-01'
    assert tenures[0]['end_date'] == '2011-01-01'
    assert tenures[1]['start_date'] == '2013-01-02'
    assert tenures[1]['end_date'] == '2014-01-01'


def test_detect_tenures_stem_change_with_grace_buffer():
    """3 off-stem events in a row don't split (grace=3); 4 do."""
    timeline = [
        _evt('2018-01-01', 'A', 'dh'),
        _evt('2018-06-01', 'B', 'dh'),
        _evt('2019-01-01', 'C', 'dh'),
        _evt('2019-06-01', 'D', 'dh'),
        _evt('2020-01-01', 'E', 'dh'),
        # Three off-stem events — within grace, don't split yet
        _evt('2020-03-01', 'F', 'midland'),
        _evt('2020-04-01', 'G', 'midland'),
        _evt('2020-05-01', 'H', 'midland'),
        # Fourth off-stem event — exceeds grace, split here
        _evt('2020-06-01', 'I', 'midland'),
        _evt('2020-07-01', 'J', 'midland'),
    ]
    tenures = detect_tenures(timeline)
    assert len(tenures) == 2
    assert tenures[0]['dominant_stem'] == 'dh'
    assert tenures[1]['dominant_stem'] == 'midland'
    # First tenure should end at the LAST on-stem event before the split,
    # not the start of the off-stem run.
    assert tenures[0]['end_date'] == '2020-01-01'
    assert tenures[1]['start_date'] == '2020-03-01'


def test_detect_tenures_unmapped_events_count_in_volume_but_not_dominance():
    """Unmapped (stem=None) events are part of the tenure's window but
    dilute its dominance share."""
    timeline = [
        _evt('2018-01-01', 'A', 'kingsett'),
        _evt('2018-06-01', 'B', 'kingsett'),
        _evt('2019-01-01', 'C', None),  # unmapped
        _evt('2019-06-01', 'D', 'kingsett'),
    ]
    tenures = detect_tenures(timeline)
    assert len(tenures) == 1
    t = tenures[0]
    assert t['dominant_stem'] == 'kingsett'
    assert t['n_party_sides'] == 4
    assert t['dominance_share'] == pytest.approx(0.75)


def test_detect_tenures_empty_timeline_returns_empty():
    assert detect_tenures([]) == []


def test_detect_tenures_all_unmapped_yields_no_tenures():
    """If we never see a mapped stem, there's no tenure to anchor on."""
    timeline = [_evt('2018-01-01', 'A', None), _evt('2019-01-01', 'B', None)]
    tenures = detect_tenures(timeline)
    assert tenures == []


def test_detect_tenures_open_tenure_when_recent():
    """A tenure with the latest event within RECENT_TENURE_DAYS of `today`
    can be passed `now` as a hint and emit end_date=None (ongoing)."""
    timeline = [
        _evt('2024-01-01', 'A', 'kingsett'),
        _evt('2025-01-01', 'B', 'kingsett'),
        _evt('2026-04-01', 'C', 'kingsett'),
    ]
    tenures = detect_tenures(timeline, now='2026-04-30')
    assert len(tenures) == 1
    assert tenures[0]['end_date'] is None  # ongoing


def test_detect_tenures_closed_tenure_when_dormant():
    """A tenure whose last event is older than RECENT_TENURE_DAYS gets a
    fixed end_date (the last event's date)."""
    timeline = [
        _evt('2018-01-01', 'A', 'kingsett'),
        _evt('2019-01-01', 'B', 'kingsett'),
    ]
    tenures = detect_tenures(timeline, now='2026-04-30')
    assert len(tenures) == 1
    assert tenures[0]['end_date'] == '2019-01-01'
```

- [ ] **Step 2: Run, confirm fail**

```bash
PYTHONPATH=. pytest tests/test_discovery_v2_tenures.py -v
# Expected: ImportError on cleo.discovery_v2.tenures
```

- [ ] **Step 3: Implement the detector**

`cleo/discovery_v2/tenures.py`:

```python
"""Pure-Python tenure detector. Walks a chronological timeline and emits
one tenure per stable run of events.

Tenures are emitted with: dominant_stem, start_date, end_date (None if
ongoing), n_party_sides, dominance_share, score. The score uses Stage A2's
existing formula (dominance_share * log(volume + 1)) computed within the
tenure window.
"""
from __future__ import annotations
import math
from datetime import date, timedelta

from cleo.discovery_v2.constants import (
    MAX_TENURE_GAP_DAYS,
    RECENT_TENURE_DAYS,
    RUN_GRACE_EVENTS,
)


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def _days_between(a: str, b: str) -> int:
    return (_parse_date(b) - _parse_date(a)).days


def _dominant_stem(stem_counts: dict) -> tuple[str | None, int]:
    """Return (stem_name, count). Deterministic alphabetical tiebreak."""
    if not stem_counts:
        return None, 0
    return sorted(stem_counts.items(), key=lambda kv: (-kv[1], kv[0]))[0]


def _emit_tenure(events: list[dict], now: str | None) -> dict | None:
    """Build one tenure record from a list of events. Returns None if no
    event in the run had a mapped stem."""
    stem_counts: dict[str, int] = {}
    for e in events:
        if e['stem']:
            stem_counts[e['stem']] = stem_counts.get(e['stem'], 0) + 1
    dominant_stem, dom_n = _dominant_stem(stem_counts)
    if dominant_stem is None:
        return None
    n = len(events)
    dom_share = dom_n / n
    score = dom_share * math.log(n + 1)
    last_event_date = events[-1]['sale_date']
    end_date: str | None = last_event_date
    if now is not None:
        days_since = _days_between(last_event_date, now)
        if days_since <= RECENT_TENURE_DAYS:
            end_date = None  # ongoing
    return {
        'dominant_stem':   dominant_stem,
        'start_date':      events[0]['sale_date'],
        'end_date':        end_date,
        'n_party_sides':   n,
        'dominance_share': dom_share,
        'score':           score,
    }


def detect_tenures(timeline: list[dict], *, now: str | None = None) -> list[dict]:
    """Walk a chronological timeline and emit one tenure per stable run.

    timeline: list of {sale_date, source_id, side, stem} dicts in date order.
              `stem` is None for unmapped sides.
    now: ISO date string. If the latest event is within RECENT_TENURE_DAYS of
         `now`, the tenure is emitted with end_date=None (ongoing).

    Returns a list of tenure dicts (see _emit_tenure for shape).
    """
    if not timeline:
        return []

    tenures: list[dict] = []
    run: list[dict] = []
    off_buffer: list[dict] = []
    run_dominant_stem: str | None = None

    def close_run(end_with: str | None = None):
        """Close current run, emit tenure, reset state."""
        nonlocal run, off_buffer, run_dominant_stem
        if run:
            t = _emit_tenure(run, now=now if end_with is None else None)
            if t is not None:
                if end_with is not None:
                    t['end_date'] = end_with
                tenures.append(t)
        run = []
        off_buffer = []
        run_dominant_stem = None

    for ev in timeline:
        # Gap-based split.
        if run:
            last_date = (off_buffer[-1] if off_buffer else run[-1])['sale_date']
            if _days_between(last_date, ev['sale_date']) > MAX_TENURE_GAP_DAYS:
                # Gap: close anything pending and restart.
                close_run(end_with=run[-1]['sale_date'])
                run = [ev]
                off_buffer = []
                run_dominant_stem = ev['stem']
                continue

        # No run yet — initialize.
        if not run:
            run = [ev]
            off_buffer = []
            run_dominant_stem = ev['stem']  # may be None; set when first mapped event arrives
            continue

        # If the run's dominant stem is still None (we haven't seen a mapped
        # event yet), upgrade as soon as we do.
        if run_dominant_stem is None and ev['stem'] is not None:
            run.append(ev)
            run_dominant_stem = ev['stem']
            continue

        # Off-stem event handling.
        if ev['stem'] is not None and run_dominant_stem is not None and \
                ev['stem'] != run_dominant_stem:
            off_buffer.append(ev)
            if len(off_buffer) > RUN_GRACE_EVENTS:
                # Exceeds grace — split. Tenure ends at last on-stem event.
                close_run(end_with=run[-1]['sale_date'])
                # Start new run from the buffer's first event.
                run = list(off_buffer)
                # Recompute its dominant stem from the buffer.
                stems = [e['stem'] for e in off_buffer if e['stem']]
                run_dominant_stem = max(set(stems), key=stems.count) if stems else None
                off_buffer = []
        else:
            # Same stem (or unmapped) — extend the run, drain buffer back into run.
            run.extend(off_buffer)
            run.append(ev)
            off_buffer = []

    # End of timeline — drain buffer back into run, then close.
    run.extend(off_buffer)
    close_run()
    return tenures
```

- [ ] **Step 4: Run tenure detector tests, confirm pass**

```bash
PYTHONPATH=. pytest tests/test_discovery_v2_tenures.py -v
# Expected: 8 passed
```

- [ ] **Step 5: Plumb tenures into anchor_scores.py**

The orchestration: build timelines for every anchor; detect tenures; persist tenures to `auto_group_anchor_tenures` (keyed on a SENTINEL group id `''` for now — Stage A3 will move them to real group IDs) AND populate `anchor_uniqueness` from the most-recent tenure per anchor for backward compatibility with existing API code.

**Important:** at this stage we don't yet have `auto_group_id` for each tenure (groups are seeded in A3). Use a staging table `_pending_tenures` that A3 will read and translate.

Update `cleo/discovery_v2/anchor_scores.py` — replace the body of `build_anchor_scores`:

```python
"""Stage A2: Windowed-dominance tenure detection.

For each anchor (phone, address_unit, contact), walks the chronological
timeline of party events and emits one tenure per stable run of events
sharing a dominant stem. Persists tenures to `_pending_tenures` for Stage A3
to associate with auto_group_ids. Also populates `anchor_uniqueness` from
the most-recent tenure per anchor (for backward compat with downstream
API code that still reads the static snapshot).
"""
from __future__ import annotations
import sqlite3
from datetime import datetime

from cleo.discovery_v2.timelines import iter_all_anchor_timelines
from cleo.discovery_v2.tenures import detect_tenures


def build_anchor_scores(conn: sqlite3.Connection, *, verbose: bool = True) -> dict:
    """Detect tenures for every anchor; populate _pending_tenures and
    anchor_uniqueness.
    """
    # Ensure the staging table exists (created here, not in migration —
    # it's purely an internal A2→A3 handoff).
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS _pending_tenures (
            anchor_type TEXT NOT NULL,
            anchor_value TEXT NOT NULL,
            dominant_stem TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT,
            n_party_sides INTEGER NOT NULL,
            dominance_share REAL NOT NULL,
            score REAL NOT NULL
        );
        DELETE FROM _pending_tenures;
    """)
    conn.execute('DELETE FROM anchor_uniqueness')

    today = datetime.utcnow().date().isoformat()

    pending_rows: list[tuple] = []
    snapshot_rows: list[tuple] = []  # for anchor_uniqueness

    n_tenures = 0
    for anchor_type, anchor_value, timeline in iter_all_anchor_timelines(conn):
        tenures = detect_tenures(timeline, now=today)
        if not tenures:
            continue
        for t in tenures:
            pending_rows.append((
                anchor_type, anchor_value, t['dominant_stem'],
                t['start_date'], t['end_date'],
                t['n_party_sides'], t['dominance_share'], t['score'],
            ))
            n_tenures += 1
        # Snapshot: pick the latest tenure (the one with end_date=None, or
        # the largest end_date if none are ongoing).
        latest = max(
            tenures,
            key=lambda t: (t['end_date'] is None, t['end_date'] or t['start_date']),
        )
        snapshot_rows.append((
            anchor_type, anchor_value,
            latest['dominant_stem'],
            latest['dominance_share'],
            latest['n_party_sides'],
            latest['score'],
        ))

    if pending_rows:
        conn.executemany(
            """INSERT INTO _pending_tenures
                (anchor_type, anchor_value, dominant_stem,
                 start_date, end_date,
                 n_party_sides, dominance_share, score)
              VALUES (?,?,?,?,?,?,?,?)""",
            pending_rows,
        )
    if snapshot_rows:
        conn.executemany(
            """INSERT INTO anchor_uniqueness
                (anchor_type, anchor_value, dominant_stem,
                 dominance_share, volume, score)
              VALUES (?,?,?,?,?,?)""",
            snapshot_rows,
        )
    conn.commit()
    if verbose:
        print(
            f'  Stage A2 (tenures): {n_tenures:,} tenures across '
            f'{len(snapshot_rows):,} anchors.', flush=True
        )
    return {'n_tenures': n_tenures, 'n_anchors': len(snapshot_rows)}
```

- [ ] **Step 6: Update anchor_scores tests for the new shape**

The existing tests in `tests/test_discovery_v2_anchor_scores.py` insert `party_fingerprints` rows without `sale_date`. The new behavior requires `sale_date` because tenures are only built from dated events.

Update each `_seed` call in the existing tests to include a `sale_date` (any reasonable date works — pick a recent one like `'2025-01-01'`). Add a `sale_date` parameter to the `_seed` helper:

```python
def _seed(conn, source_id, side, phrase, *, phone=None, contact=None,
          city=None, street_number=None, street_name=None, street_suffix=None,
          street_direction=None, suite_type=None, suite_number=None,
          sale_date='2025-01-01'):
    conn.execute(
        """INSERT OR IGNORE INTO party_fingerprints
             (source_id, side, phone, contact_fingerprint, city,
              street_number, street_name, street_suffix, street_direction,
              suite_type, suite_number, sale_date)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (source_id, side, phone, contact, city, street_number, street_name,
         street_suffix, street_direction, suite_type, suite_number, sale_date),
    )
    if phrase:
        conn.execute(
            "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
            "VALUES (?, ?, 'brand_phrase', ?, 'party_name')",
            (source_id, side, phrase),
        )
```

Update the `_make_db` schema for `party_fingerprints` to include `sale_date TEXT`.

The existing tests assert on `volume`, `dominance_share`, `score` columns of `anchor_uniqueness`. After H2's snapshot logic, these become the values from the *latest tenure* — for tests where all events share one stem and date, the values match what they used to.

Add three new tests for tenure-aware behavior:

```python
def test_anchor_scores_emits_two_tenures_on_stem_change(_make_db, _seed):
    conn = _make_db()
    # 5 dh events 2018-2020, then 5 midland events 2022-2024 (>730 day gap)
    for i in range(5):
        _seed(conn, f'DH{i}', 'seller', 'dh management',
              phone='P1', sale_date=f'2018-0{i+1}-01')
    for i in range(5):
        _seed(conn, f'MD{i}', 'seller', 'midland industries',
              phone='P1', sale_date=f'2022-0{i+1}-01')
    build_stems(conn, verbose=False)
    build_anchor_scores(conn, verbose=False)

    pendings = conn.execute(
        "SELECT dominant_stem, start_date, end_date FROM _pending_tenures "
        "WHERE anchor_type='phone' AND anchor_value='P1' "
        "ORDER BY start_date"
    ).fetchall()
    assert len(pendings) == 2
    assert pendings[0]['dominant_stem'] == 'dh'
    assert pendings[1]['dominant_stem'] == 'midland'


def test_anchor_uniqueness_snapshot_picks_latest_tenure(_make_db, _seed):
    """anchor_uniqueness reflects the most recent tenure (snapshot semantics)."""
    conn = _make_db()
    for i in range(5):
        _seed(conn, f'DH{i}', 'seller', 'dh management',
              phone='P1', sale_date=f'2018-0{i+1}-01')
    for i in range(5):
        _seed(conn, f'MD{i}', 'seller', 'midland industries',
              phone='P1', sale_date=f'2025-0{i+1}-01')
    build_stems(conn, verbose=False)
    build_anchor_scores(conn, verbose=False)

    row = conn.execute(
        "SELECT dominant_stem FROM anchor_uniqueness "
        "WHERE anchor_type='phone' AND anchor_value='P1'"
    ).fetchone()
    assert row['dominant_stem'] == 'midland'  # latest


def test_anchor_scores_skips_anchors_without_dated_events(_make_db, _seed):
    conn = _make_db()
    _seed(conn, 'X1', 'seller', 'kingsett capital',
          phone='P_NODATE', sale_date=None)
    build_stems(conn, verbose=False)
    build_anchor_scores(conn, verbose=False)
    rows = conn.execute(
        "SELECT * FROM _pending_tenures WHERE anchor_value='P_NODATE'"
    ).fetchall()
    assert rows == []
```

(The existing tests that assert specific `volume` and `score` values may need their assertions relaxed — under the new model, `volume` becomes the count of party-sides in the latest tenure. For a single-stem single-tenure case those numbers match; for multi-stem cases they reflect just the latest run.)

- [ ] **Step 7: Run all anchor_scores tests, confirm pass**

```bash
PYTHONPATH=. pytest tests/test_discovery_v2_anchor_scores.py tests/test_discovery_v2_tenures.py -v
# Expected: existing 5 + new 3 + 8 tenure-detector tests all pass
```

- [ ] **Step 8: Commit**

```bash
git add cleo/discovery_v2/tenures.py cleo/discovery_v2/anchor_scores.py \
        tests/test_discovery_v2_tenures.py tests/test_discovery_v2_anchor_scores.py
git commit -m "feat(layer2): Stage A2 windowed-dominance tenure detector"
```

---

### Task 5: Stage A3 — seed groups + persist anchor tenures

After A2, we have a staging table `_pending_tenures` keyed on (anchor_type, anchor_value, dominant_stem, …). A3's job is:
1. Group tenures by `dominant_stem` → seed one auto_group per stem (existing behavior).
2. For each seeded group, copy its tenures from `_pending_tenures` into `auto_group_anchor_tenures` with the new `auto_group_id`.
3. Also rebuild the existing `auto_group_anchors` snapshot from the latest tenure per (group, anchor) so downstream API code keeps working.

**Files:**
- Modify: `cleo/discovery_v2/seeding.py`
- Modify: `tests/test_discovery_v2_seeding.py`

- [ ] **Step 1: Update existing seeding tests for new schema**

The fixtures need: `auto_group_anchor_tenures` table, `_pending_tenures` table. Update `_make_db` in `tests/test_discovery_v2_seeding.py`:

```python
# Add to the executescript:
CREATE TABLE _pending_tenures (
    anchor_type TEXT NOT NULL,
    anchor_value TEXT NOT NULL,
    dominant_stem TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT,
    n_party_sides INTEGER NOT NULL,
    dominance_share REAL NOT NULL,
    score REAL NOT NULL
);
CREATE TABLE auto_group_anchor_tenures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    auto_group_id TEXT NOT NULL,
    anchor_type TEXT NOT NULL,
    anchor_value TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT,
    n_party_sides_in_window INTEGER NOT NULL,
    dominance_share_in_window REAL NOT NULL,
    score REAL NOT NULL
);
```

If existing tests seed `anchor_uniqueness` directly (bypassing A2), they should now ALSO seed `_pending_tenures` to mirror what A2 produces. Inspect the test file and add the corresponding inserts wherever `anchor_uniqueness` is hand-seeded.

- [ ] **Step 2: Add new tests for tenure persistence**

Append:

```python
def test_seeding_populates_auto_group_anchor_tenures():
    conn = _make_db()
    # Seed _pending_tenures directly with a single tenure
    conn.execute(
        """INSERT INTO _pending_tenures
            (anchor_type, anchor_value, dominant_stem,
             start_date, end_date,
             n_party_sides, dominance_share, score)
           VALUES ('phone', '4162655055', 'dh',
                   '2010-01-01', NULL, 22, 0.95, 6.2)"""
    )
    # Plus the matching anchor_uniqueness snapshot row
    conn.execute(
        """INSERT INTO anchor_uniqueness
            (anchor_type, anchor_value, dominant_stem,
             dominance_share, volume, score)
           VALUES ('phone', '4162655055', 'dh', 0.95, 22, 6.2)"""
    )
    # Also seed brand_stem so downstream lookups work; needs at least one
    # anchor that meets the seeding threshold
    build_seeds(conn, verbose=False)

    rows = conn.execute(
        "SELECT * FROM auto_group_anchor_tenures WHERE anchor_value='4162655055'"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]['auto_group_id'].startswith('AGRP_')


def test_seeding_creates_one_tenure_row_per_pending_tenure():
    """If A2 emitted two tenures for the same anchor (different stems / time
    windows), A3 must create two auto_group_anchor_tenures rows — one in each
    group."""
    conn = _make_db()
    conn.execute(
        """INSERT INTO _pending_tenures VALUES
            ('phone', '4162655055', 'dh',
             '2010-01-01', '2014-12-31', 18, 0.95, 5.5),
            ('phone', '4162655055', 'midland',
             '2016-01-01', NULL, 22, 0.90, 6.1)"""
    )
    # Two anchor_uniqueness rows wouldn't normally exist (snapshot is
    # latest-only), but the seeder reads _pending_tenures, not anchor_uniqueness.
    conn.execute(
        """INSERT INTO anchor_uniqueness VALUES
            ('phone', '4162655055', 'midland', 0.90, 22, 6.1, 0)"""
    )
    build_seeds(conn, verbose=False)

    rows = conn.execute(
        "SELECT auto_group_id, dominant_stem_or_none FROM ("
        "  SELECT agt.auto_group_id, ag.canonical_stem AS dominant_stem_or_none "
        "  FROM auto_group_anchor_tenures agt "
        "  JOIN auto_groups ag ON ag.auto_group_id = agt.auto_group_id "
        "  WHERE agt.anchor_value = '4162655055')"
    ).fetchall()
    stems = {r['dominant_stem_or_none'] for r in rows}
    assert stems == {'dh', 'midland'}
```

- [ ] **Step 3: Run, confirm fail**

```bash
PYTHONPATH=. pytest tests/test_discovery_v2_seeding.py -v
```

- [ ] **Step 4: Update seeding.py**

In `cleo/discovery_v2/seeding.py`, after the existing seeding logic that inserts into `auto_groups` and `auto_group_anchors`, add a step that copies `_pending_tenures` rows for the seeded anchors into `auto_group_anchor_tenures`:

```python
def build_seeds(conn: sqlite3.Connection, *, verbose: bool = True) -> dict:
    """Run Stage A3. Idempotent — drops prior derived rows first."""
    conn.execute('DELETE FROM auto_group_anchors')
    conn.execute('DELETE FROM auto_groups')
    conn.execute('DELETE FROM auto_group_anchor_tenures')  # NEW

    # … existing logic to read anchor_uniqueness, group by stem,
    # decide tier, write auto_groups + auto_group_anchors …

    # NEW: persist tenure rows.
    # Build a (anchor_type, anchor_value) → group_id index from the rows we
    # just inserted into auto_group_anchors.
    anchor_to_group: dict[tuple[str, str], str] = {
        (r['anchor_type'], r['anchor_value']): r['auto_group_id']
        for r in conn.execute(
            "SELECT auto_group_id, anchor_type, anchor_value FROM auto_group_anchors"
        )
    }

    tenure_rows: list[tuple] = []
    for r in conn.execute(
        """SELECT anchor_type, anchor_value, dominant_stem,
                  start_date, end_date,
                  n_party_sides, dominance_share, score
           FROM _pending_tenures"""
    ):
        # Look up the group seeded for this stem at this anchor.
        gid = anchor_to_group.get((r['anchor_type'], r['anchor_value']))
        if gid is None:
            continue  # Tenure exists but its anchor didn't make it into any seed
        # Confirm that the group's canonical_stem matches the tenure's stem;
        # only attach tenures to the matching group.
        # (One anchor can have multiple tenures across different stems — each
        # tenure goes to its own stem's group, not the latest one.)
        target_group = conn.execute(
            "SELECT auto_group_id FROM auto_groups "
            "WHERE canonical_stem = ?",
            (r['dominant_stem'],),
        ).fetchone()
        if target_group is None:
            continue
        tenure_rows.append((
            target_group['auto_group_id'], r['anchor_type'], r['anchor_value'],
            r['start_date'], r['end_date'],
            r['n_party_sides'], r['dominance_share'], r['score'],
        ))

    if tenure_rows:
        conn.executemany(
            """INSERT INTO auto_group_anchor_tenures
                (auto_group_id, anchor_type, anchor_value,
                 start_date, end_date,
                 n_party_sides_in_window, dominance_share_in_window, score)
               VALUES (?,?,?,?,?,?,?,?)""",
            tenure_rows,
        )

    # … existing _apply_crm_overrides + commit logic …

    if verbose:
        print(
            f'  Stage A3 (seeds): {len(seeded):,} groups, '
            f'{len(tenure_rows):,} tenures.', flush=True
        )
    return {'n_groups': len(seeded), 'n_tenures': len(tenure_rows)}
```

- [ ] **Step 5: Run, confirm pass**

```bash
PYTHONPATH=. pytest tests/test_discovery_v2_seeding.py -v
# Expected: existing + 2 new pass
```

- [ ] **Step 6: Commit**

```bash
git add cleo/discovery_v2/seeding.py tests/test_discovery_v2_seeding.py
git commit -m "feat(layer2): Stage A3 persists anchor tenures to auto_group_anchor_tenures"
```

---

### Task 6: Contact tenures

`auto_contact_tenures` is per-(contact, group) — it answers "when was contact X part of group G's roster?" Built by walking the contact's timeline and detecting per-group tenures.

**Files:**
- Modify: `cleo/discovery_v2/seeding.py` — add a contact-tenures step.
- Modify: `tests/test_discovery_v2_seeding.py`.

- [ ] **Step 1: Write failing test**

Add to `tests/test_discovery_v2_seeding.py`:

```python
def test_contact_tenures_built_per_group():
    """A contact appears at parties for a single group across two distinct
    time windows → 2 contact tenure rows."""
    conn = _make_db_with_full_pipeline()
    # Seed parties: 5 events 2010-2012 with contact dan_hagler at DH-tenured
    # phone P1; then a 3-year gap; then 5 events 2016-2018 also DH-tenured.
    # Expect: dh phone tenure has 2 windows; dan_hagler contact tenure has
    # 2 windows in DH group.
    # … detailed test setup …

    rows = conn.execute(
        "SELECT start_date, end_date FROM auto_contact_tenures "
        "WHERE contact_fingerprint='dan_hagler' "
        "ORDER BY start_date"
    ).fetchall()
    assert len(rows) == 2
```

(Detailed seed code follows the same pattern as Task 5 — seed `_pending_tenures` for the phone anchor + `party_fingerprints` rows linking the contact to each event.)

Add a complementary test for the simpler single-window case.

- [ ] **Step 2: Implement contact tenure builder**

Add to `cleo/discovery_v2/seeding.py` (called from `build_seeds` after the anchor-tenure persistence):

```python
def _build_contact_tenures(
    conn: sqlite3.Connection, anchor_to_group: dict
) -> int:
    """For each seeded group, walk the contacts that appear on its parties
    and emit per-(contact, group) tenures.

    Reuses the tenure detector from Stage A2 with the same date-gap rules.
    """
    from cleo.discovery_v2.timelines import build_anchor_timeline
    from cleo.discovery_v2.tenures import detect_tenures
    from datetime import datetime

    today = datetime.utcnow().date().isoformat()

    conn.execute('DELETE FROM auto_contact_tenures')

    # For each contact, find the groups that share at least one party with it.
    # For each (contact, group) pair, walk the contact's events filtered to
    # that group's parties and detect tenures.
    rows: list[tuple] = []
    for c in conn.execute(
        "SELECT DISTINCT contact_fingerprint FROM party_fingerprints "
        "WHERE contact_fingerprint IS NOT NULL AND contact_fingerprint != ''"
    ):
        cf = c['contact_fingerprint']
        timeline = build_anchor_timeline(conn, 'contact', cf)
        if not timeline:
            continue

        # Group events by which group their party belongs to (via auto_group_members).
        events_by_group: dict[str, list[dict]] = {}
        for ev in timeline:
            mem = conn.execute(
                "SELECT auto_group_id FROM auto_group_members "
                "WHERE source_id = ? AND side = ? AND member_type = 'party_side'",
                (ev['source_id'], ev['side']),
            ).fetchone()
            if mem is None:
                continue
            events_by_group.setdefault(mem['auto_group_id'], []).append(ev)

        for gid, events in events_by_group.items():
            tenures = detect_tenures(events, now=today)
            for t in tenures:
                rows.append((
                    cf, gid, t['start_date'], t['end_date'], t['n_party_sides'],
                ))

    if rows:
        conn.executemany(
            """INSERT INTO auto_contact_tenures
                (contact_fingerprint, auto_group_id,
                 start_date, end_date, n_party_sides_in_window)
               VALUES (?,?,?,?,?)""",
            rows,
        )
    return len(rows)
```

**Note:** this depends on `auto_group_members` being populated, which happens in Stage A4 (next task), NOT in A3. So contact tenures must be built AFTER Stage A4. We move the call out of `build_seeds` and into the orchestrator instead (Task 9).

For now, write the function and test it, but defer the orchestrator wiring to Task 9.

- [ ] **Step 3: Run tests, confirm pass**

```bash
PYTHONPATH=. pytest tests/test_discovery_v2_seeding.py -v
```

- [ ] **Step 4: Commit**

```bash
git add cleo/discovery_v2/seeding.py tests/test_discovery_v2_seeding.py
git commit -m "feat(layer2): contact tenure builder (per group, time-windowed)"
```

---

### Task 7: Stage A4 — time-aware expansion

A4 currently attaches a party to a group when its anchor matches any of the group's anchors and the match score clears the threshold. After H2, the rule is stricter:

- The party's `sale_date` must fall within at least one tenure for at least one of its anchors.
- If exactly one group surfaces across all tenured matches → attach.
- If multiple groups surface → don't attach; emit a `contact_overlap` or `anchor_reassignment` flag.
- If no group surfaces → orphan.

**Files:**
- Modify: `cleo/discovery_v2/expansion.py`
- Modify: `tests/test_discovery_v2_expansion.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_discovery_v2_expansion.py`:

```python
def test_party_within_tenure_window_attaches():
    """A party whose sale_date is inside a group's anchor tenure attaches."""
    conn = _make_db()
    # Seed DH group with phone P1 tenure 2010-2020
    _seed(conn, 'EARLY1', 'seller', 'dh management',
          phone='P1', sale_date='2012-05-01')
    # … plus 7 more strong DH events ending in 2020 …
    # Add a NEW party at P1 with sale_date 2015-06-01 (within tenure)
    _seed(conn, 'EXTRA', 'seller', None,
          phone='P1', sale_date='2015-06-01')
    _build_pipeline(conn)
    build_expansion(conn, verbose=False)

    members = conn.execute(
        "SELECT * FROM auto_group_members WHERE source_id='EXTRA'"
    ).fetchall()
    assert len(members) == 1


def test_party_outside_tenure_window_does_not_attach():
    """A party whose sale_date falls in a gap between tenures stays orphaned."""
    conn = _make_db()
    # Seed DH at P1 with two tenures: 2010-2014, 2018-2022 (gap 2015-2017).
    # … detailed setup …
    # Add a party at P1 with sale_date 2016-06-01 (in the gap)
    _seed(conn, 'GAP', 'seller', None,
          phone='P1', sale_date='2016-06-01')
    _build_pipeline(conn)
    build_expansion(conn, verbose=False)

    members = conn.execute(
        "SELECT * FROM auto_group_members WHERE source_id='GAP'"
    ).fetchall()
    assert len(members) == 0


def test_party_with_two_groups_in_window_emits_conflict_flag():
    """A party whose contact tenured for group A AND phone tenured for
    group B (overlapping windows) does NOT attach; emits a conflict flag."""
    conn = _make_db()
    # … set up two groups with overlapping tenure windows for the same party …
    _build_pipeline(conn)
    build_expansion(conn, verbose=False)

    flags = conn.execute(
        "SELECT * FROM auto_conflict_flags WHERE conflict_type='contact_overlap'"
    ).fetchall()
    assert len(flags) >= 1
```

- [ ] **Step 2: Run, confirm fail**

```bash
PYTHONPATH=. pytest tests/test_discovery_v2_expansion.py -v -k tenure
```

- [ ] **Step 3: Update expansion.py**

The new `_score_match` flow:
1. Build `addr_unit`, `phone`, `contact` for the side as before.
2. Look up anchors_by_group from `auto_group_anchor_tenures` instead of `auto_group_anchors`. For each anchor, only consider tenures that contain the side's `sale_date`.
3. Score each (party, group) pair the same way (using the H1 constants).
4. If exactly one group passes threshold → attach.
5. If multiple groups pass threshold → emit conflict flag (write to `auto_conflict_flags`); don't attach.

Replace the body of `build_expansion` to load tenured anchors:

```python
def build_expansion(conn: sqlite3.Connection, *, verbose: bool = True) -> dict:
    """Stage A4 — attach party-sides + numbered corps to seeded groups,
    using anchor tenure windows to gate attachment."""
    conn.execute('DELETE FROM auto_group_members')

    groups = list(conn.execute('SELECT auto_group_id, canonical_stem FROM auto_groups'))
    if not groups:
        if verbose:
            print('  Stage A4 (expansion): no groups to expand.', flush=True)
        return {'n_party_side_members': 0, 'n_numbered_corp_members': 0}

    # NEW: load tenures with start/end. Index by (anchor_type, anchor_value).
    # Each entry is a list of (auto_group_id, start_date, end_date, score) tuples.
    tenures_by_anchor: dict[tuple[str, str], list[tuple]] = {}
    for r in conn.execute(
        "SELECT auto_group_id, anchor_type, anchor_value, "
        "       start_date, end_date, score "
        "FROM auto_group_anchor_tenures"
    ):
        key = (r['anchor_type'], r['anchor_value'])
        tenures_by_anchor.setdefault(key, []).append((
            r['auto_group_id'], r['start_date'], r['end_date'], r['score'],
        ))

    # … existing side_data construction (city/street/phone/contact) …

    # … existing brand_phrase loop to populate side_data[…]['stems'] …

    member_rows = []
    numbered_corps = []
    conflict_rows: list[tuple] = []

    for (sid, side), info in side_data.items():
        sale_date = info.get('sale_date')
        if not sale_date:
            continue  # No date → can't place in any tenure window
        # For each anchor on the party, find which groups have a tenure
        # containing sale_date.
        candidate_groups: dict[str, dict] = {}  # group_id → {score, via_anchor_type, …}
        for (atype, aval) in (
            ('phone', info.get('phone')),
            ('address_unit', info.get('addr_unit')),
            ('contact', info.get('contact')),
        ):
            if not aval:
                continue
            for gid, sd, ed, anchor_score in tenures_by_anchor.get((atype, aval), []):
                if sd <= sale_date and (ed is None or sale_date <= ed):
                    rec = candidate_groups.setdefault(gid, {'anchors': [], 'best': 0.0})
                    rec['anchors'].append((atype, aval))

        if not candidate_groups:
            # Possible direct stem hit — fall back to the H1 _score_match for
            # this case, but only against groups whose canonical_stem matches.
            # … existing direct-stem-hit path …
            continue

        if len(candidate_groups) == 1:
            (gid, _) = next(iter(candidate_groups.items()))
            score = _score_match_h2(info, candidate_groups[gid], group_canonical_stem=…)
            if score >= EXPANSION_ATTACH_THRESHOLD:
                member_rows.append((gid, 'party_side', sid, side, None, score))
        else:
            # Multiple groups — emit a conflict flag.
            sorted_gids = sorted(candidate_groups.keys())
            conflict_rows.append((
                'contact_overlap' if any(
                    a[0] == 'contact' for cg in candidate_groups.values()
                    for a in cg['anchors']
                ) else 'anchor_reassignment',
                'anchor', f'{sid}|{side}', None,
                sorted_gids[0], sorted_gids[1],
                sale_date,
                f'Party {sid}/{side} on {sale_date} matches '
                f'{len(candidate_groups)} groups via anchor tenures.',
            ))
            # Don't attach.

    # … insert member_rows, numbered corps, conflict_rows …

    if conflict_rows:
        conn.executemany(
            """INSERT INTO auto_conflict_flags
                (conflict_type, entity_type, entity_value, entity_subtype,
                 group_a, group_b, date_observed, description)
              VALUES (?,?,?,?,?,?,?,?)""",
            conflict_rows,
        )

    conn.commit()
    if verbose:
        print(
            f'  Stage A4 (expansion): {len(member_rows):,} party-sides, '
            f'{len(corp_rows):,} numbered-corps, '
            f'{len(conflict_rows):,} conflicts.',
            flush=True,
        )
    return {
        'n_party_side_members': len(member_rows),
        'n_numbered_corp_members': len(corp_rows),
        'n_expansion_conflicts': len(conflict_rows),
    }
```

(The skeleton above is illustrative; fill in `_score_match_h2` with the same constants from H1, but only operating on the candidate_groups for the matching tenures.)

Also update the SELECT in `build_expansion` that fetches party_fingerprints to include `sale_date`.

- [ ] **Step 4: Run tests, confirm pass**

```bash
PYTHONPATH=. pytest tests/test_discovery_v2_expansion.py -v
```

- [ ] **Step 5: Commit**

```bash
git add cleo/discovery_v2/expansion.py tests/test_discovery_v2_expansion.py
git commit -m "feat(layer2): Stage A4 time-aware expansion (tenure-window gating)"
```

---

### Task 8: Stage A6 — conflict detector

A6 runs AFTER A4 and scans tenures for the four conflict types. Conflicts emitted by A4 (multiple-group ambiguity) are already written; A6 adds the static structural ones.

**Files:**
- Create: `cleo/discovery_v2/conflicts.py`
- Test: `tests/test_discovery_v2_conflicts.py`

- [ ] **Step 1: Write failing tests**

`tests/test_discovery_v2_conflicts.py`:

```python
import sqlite3
import pytest
from cleo.discovery_v2.conflicts import detect_conflicts


def _make_db():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE auto_group_anchor_tenures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            auto_group_id TEXT NOT NULL,
            anchor_type TEXT NOT NULL,
            anchor_value TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT,
            n_party_sides_in_window INTEGER NOT NULL,
            dominance_share_in_window REAL NOT NULL,
            score REAL NOT NULL
        );
        CREATE TABLE auto_contact_tenures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_fingerprint TEXT NOT NULL,
            auto_group_id TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT,
            n_party_sides_in_window INTEGER NOT NULL
        );
        CREATE TABLE auto_conflict_flags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conflict_type TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_value TEXT NOT NULL,
            entity_subtype TEXT,
            group_a TEXT,
            group_b TEXT,
            date_observed TEXT,
            description TEXT NOT NULL,
            discovered_at TEXT
        );
    """)
    return conn


def test_anchor_reassignment_flagged():
    """Same anchor with two non-overlapping tenures on different groups."""
    conn = _make_db()
    conn.execute(
        "INSERT INTO auto_group_anchor_tenures "
        "(auto_group_id, anchor_type, anchor_value, "
        " start_date, end_date, n_party_sides_in_window, "
        " dominance_share_in_window, score) VALUES "
        "('AGRP_DH', 'phone', '4162655055', "
        " '2010-01-01', '2014-12-31', 18, 0.95, 5.5)"
    )
    conn.execute(
        "INSERT INTO auto_group_anchor_tenures "
        "(auto_group_id, anchor_type, anchor_value, "
        " start_date, end_date, n_party_sides_in_window, "
        " dominance_share_in_window, score) VALUES "
        "('AGRP_BB', 'phone', '4162655055', "
        " '2016-01-01', NULL, 22, 0.92, 6.1)"
    )

    detect_conflicts(conn, verbose=False)

    flags = conn.execute(
        "SELECT * FROM auto_conflict_flags WHERE conflict_type='anchor_reassignment'"
    ).fetchall()
    assert len(flags) == 1
    assert flags[0]['group_a'] == 'AGRP_DH'
    assert flags[0]['group_b'] == 'AGRP_BB'
    assert flags[0]['entity_value'] == '4162655055'


def test_contact_overlap_flagged():
    conn = _make_db()
    # Same contact tenured at two groups with overlapping windows
    conn.execute(
        "INSERT INTO auto_contact_tenures "
        "(contact_fingerprint, auto_group_id, "
        " start_date, end_date, n_party_sides_in_window) VALUES "
        "('jane_smith', 'AGRP_A', '2015-01-01', '2020-12-31', 12), "
        "('jane_smith', 'AGRP_B', '2018-01-01', '2022-12-31', 8)"
    )
    detect_conflicts(conn, verbose=False)
    flags = conn.execute(
        "SELECT * FROM auto_conflict_flags WHERE conflict_type='contact_overlap'"
    ).fetchall()
    assert len(flags) == 1


def test_transient_tenure_flagged():
    conn = _make_db()
    # 1-event tenure at a low-volume anchor
    conn.execute(
        "INSERT INTO auto_group_anchor_tenures "
        "(auto_group_id, anchor_type, anchor_value, "
        " start_date, end_date, n_party_sides_in_window, "
        " dominance_share_in_window, score) VALUES "
        "('AGRP_X', 'address_unit', 'toronto|4950|yonge||||', "
        " '2014-06-01', '2014-06-01', 1, 1.0, 0.69)"
    )
    detect_conflicts(conn, verbose=False)
    flags = conn.execute(
        "SELECT * FROM auto_conflict_flags WHERE conflict_type='transient_tenure'"
    ).fetchall()
    assert len(flags) == 1


def test_abrupt_tenure_end_flagged():
    """Tenure with high volume that ended >1 year ago without a successor."""
    conn = _make_db()
    conn.execute(
        "INSERT INTO auto_group_anchor_tenures "
        "(auto_group_id, anchor_type, anchor_value, "
        " start_date, end_date, n_party_sides_in_window, "
        " dominance_share_in_window, score) VALUES "
        "('AGRP_X', 'phone', 'P_DEAD', '2018-01-01', '2022-12-31', 200, 0.95, 8.5)"
    )
    detect_conflicts(conn, verbose=False, now='2026-04-30')
    flags = conn.execute(
        "SELECT * FROM auto_conflict_flags WHERE conflict_type='abrupt_tenure_end'"
    ).fetchall()
    assert len(flags) == 1


def test_no_conflicts_for_clean_data():
    """Single tenure per anchor, single group per contact, recent activity → 0 flags."""
    conn = _make_db()
    conn.execute(
        "INSERT INTO auto_group_anchor_tenures "
        "(auto_group_id, anchor_type, anchor_value, "
        " start_date, end_date, n_party_sides_in_window, "
        " dominance_share_in_window, score) VALUES "
        "('AGRP_X', 'phone', 'P', '2024-01-01', NULL, 50, 0.95, 7.2)"
    )
    detect_conflicts(conn, verbose=False, now='2026-04-30')
    flags = conn.execute("SELECT COUNT(*) AS n FROM auto_conflict_flags").fetchone()
    assert flags['n'] == 0


def test_detect_conflicts_is_idempotent():
    """Running twice shouldn't double-emit flags."""
    conn = _make_db()
    conn.execute(
        "INSERT INTO auto_group_anchor_tenures "
        "(auto_group_id, anchor_type, anchor_value, "
        " start_date, end_date, n_party_sides_in_window, "
        " dominance_share_in_window, score) VALUES "
        "('AGRP_DH', 'phone', '4162655055', "
        " '2010-01-01', '2014-12-31', 18, 0.95, 5.5),"
        "('AGRP_BB', 'phone', '4162655055', "
        " '2016-01-01', NULL, 22, 0.92, 6.1)"
    )
    detect_conflicts(conn, verbose=False)
    detect_conflicts(conn, verbose=False)
    flags = conn.execute(
        "SELECT COUNT(*) AS n FROM auto_conflict_flags WHERE conflict_type='anchor_reassignment'"
    ).fetchone()
    assert flags['n'] == 1
```

- [ ] **Step 2: Run, confirm fail**

```bash
PYTHONPATH=. pytest tests/test_discovery_v2_conflicts.py -v
```

- [ ] **Step 3: Implement the detector**

`cleo/discovery_v2/conflicts.py`:

```python
"""Stage A6: Conflict detection.

Scans auto_group_anchor_tenures and auto_contact_tenures for four conflict
patterns:
  - anchor_reassignment: same anchor with non-overlapping tenures on
    different groups.
  - contact_overlap: same contact with overlapping tenures on different groups.
  - abrupt_tenure_end: high-volume tenure ended cleanly without a successor.
  - transient_tenure: single-party or short-window low-volume tenures.

These are surfaced for human review in the Conflicts UI (Plan H3); they
don't change the algorithm's outputs.
"""
from __future__ import annotations
import sqlite3
from datetime import datetime, date

from cleo.discovery_v2.constants import (
    MIN_PERMANENT_TENURE_DAYS,
    MIN_TENURE_PARTY_COUNT,
    RECENT_TENURE_DAYS,
)


def _days_between(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def detect_conflicts(
    conn: sqlite3.Connection, *, verbose: bool = True, now: str | None = None,
) -> dict:
    """Idempotent — clears prior flags and recomputes."""
    if now is None:
        now = datetime.utcnow().date().isoformat()

    conn.execute('DELETE FROM auto_conflict_flags')

    flag_rows: list[tuple] = []

    # ── 1. anchor_reassignment ────────────────────────────────────────────
    for r in conn.execute(
        """SELECT anchor_type, anchor_value
           FROM auto_group_anchor_tenures
           GROUP BY anchor_type, anchor_value
           HAVING COUNT(DISTINCT auto_group_id) > 1"""
    ):
        atype, aval = r['anchor_type'], r['anchor_value']
        ts = conn.execute(
            "SELECT auto_group_id, start_date, end_date "
            "FROM auto_group_anchor_tenures "
            "WHERE anchor_type=? AND anchor_value=? "
            "ORDER BY start_date",
            (atype, aval),
        ).fetchall()
        for i in range(len(ts) - 1):
            a = ts[i]
            b = ts[i + 1]
            if a['auto_group_id'] == b['auto_group_id']:
                continue
            # Non-overlapping check: a ends before b starts
            a_end = a['end_date'] or '9999-12-31'
            if a_end < b['start_date']:
                flag_rows.append((
                    'anchor_reassignment', 'anchor', aval, atype,
                    a['auto_group_id'], b['auto_group_id'], a['end_date'],
                    f'{atype} {aval} reassigned from {a["auto_group_id"]} '
                    f'(ended {a["end_date"]}) to {b["auto_group_id"]} '
                    f'(started {b["start_date"]}).',
                ))

    # ── 2. contact_overlap ────────────────────────────────────────────────
    for r in conn.execute(
        """SELECT contact_fingerprint
           FROM auto_contact_tenures
           GROUP BY contact_fingerprint
           HAVING COUNT(DISTINCT auto_group_id) > 1"""
    ):
        cf = r['contact_fingerprint']
        ts = conn.execute(
            "SELECT auto_group_id, start_date, end_date "
            "FROM auto_contact_tenures WHERE contact_fingerprint = ? "
            "ORDER BY start_date",
            (cf,),
        ).fetchall()
        # Overlapping windows on different groups → flag.
        for i in range(len(ts)):
            for j in range(i + 1, len(ts)):
                if ts[i]['auto_group_id'] == ts[j]['auto_group_id']:
                    continue
                a_end = ts[i]['end_date'] or '9999-12-31'
                b_end = ts[j]['end_date'] or '9999-12-31'
                if ts[j]['start_date'] <= a_end and ts[i]['start_date'] <= b_end:
                    flag_rows.append((
                        'contact_overlap', 'contact', cf, None,
                        ts[i]['auto_group_id'], ts[j]['auto_group_id'],
                        ts[j]['start_date'],
                        f'Contact {cf} held tenures at {ts[i]["auto_group_id"]} '
                        f'({ts[i]["start_date"]}–{ts[i]["end_date"] or "ongoing"}) '
                        f'and {ts[j]["auto_group_id"]} '
                        f'({ts[j]["start_date"]}–{ts[j]["end_date"] or "ongoing"}); '
                        f'either a service provider, a job change, or a name collision.',
                    ))

    # ── 3. transient_tenure ───────────────────────────────────────────────
    for r in conn.execute(
        "SELECT auto_group_id, anchor_type, anchor_value, "
        "       start_date, end_date, n_party_sides_in_window "
        "FROM auto_group_anchor_tenures "
        f"WHERE n_party_sides_in_window < {MIN_TENURE_PARTY_COUNT} "
        "  AND end_date IS NOT NULL"
    ):
        days = _days_between(r['start_date'], r['end_date']) if r['end_date'] else 0
        if days < MIN_PERMANENT_TENURE_DAYS:
            flag_rows.append((
                'transient_tenure', 'anchor', r['anchor_value'], r['anchor_type'],
                r['auto_group_id'], None, r['end_date'],
                f'{r["anchor_type"]} {r["anchor_value"]} had a transient '
                f'tenure on {r["auto_group_id"]} '
                f'({r["start_date"]}–{r["end_date"]}, '
                f'{r["n_party_sides_in_window"]} parties). Likely one-off.',
            ))

    # ── 4. abrupt_tenure_end ──────────────────────────────────────────────
    for r in conn.execute(
        "SELECT auto_group_id, anchor_type, anchor_value, "
        "       start_date, end_date, n_party_sides_in_window "
        "FROM auto_group_anchor_tenures "
        "WHERE end_date IS NOT NULL "
        "  AND n_party_sides_in_window >= 50"
    ):
        days_since_end = _days_between(r['end_date'], now)
        if days_since_end > RECENT_TENURE_DAYS:
            flag_rows.append((
                'abrupt_tenure_end', 'anchor', r['anchor_value'], r['anchor_type'],
                r['auto_group_id'], None, r['end_date'],
                f'{r["anchor_type"]} {r["anchor_value"]} had {r["n_party_sides_in_window"]} '
                f'parties through {r["end_date"]} on {r["auto_group_id"]} '
                f'and zero since. Likely operator wind-down or data gap.',
            ))

    if flag_rows:
        conn.executemany(
            """INSERT INTO auto_conflict_flags
                (conflict_type, entity_type, entity_value, entity_subtype,
                 group_a, group_b, date_observed, description)
              VALUES (?,?,?,?,?,?,?,?)""",
            flag_rows,
        )
    conn.commit()
    if verbose:
        print(f'  Stage A6 (conflicts): {len(flag_rows):,} flags emitted.', flush=True)
    return {'n_conflicts': len(flag_rows)}
```

- [ ] **Step 4: Run tests, confirm pass**

```bash
PYTHONPATH=. pytest tests/test_discovery_v2_conflicts.py -v
# Expected: 6 passed
```

- [ ] **Step 5: Commit**

```bash
git add cleo/discovery_v2/conflicts.py tests/test_discovery_v2_conflicts.py
git commit -m "feat(layer2): Stage A6 conflict detector"
```

---

### Task 9: Orchestrator wiring

Wire A0/A6 into `build_auto_groups`. The new pipeline order:
A1 → A2 (now produces tenures) → A3 (seeds + persists tenures) → A4 (time-aware expansion) → contact_tenures (after A4 because it needs `auto_group_members`) → A6 (conflict detection) → A5 (display + counts).

**Files:**
- Modify: `cleo/discovery_v2/auto_groups.py`

- [ ] **Step 1: Update orchestrator**

```python
"""Layer 2 orchestrator: A1 → A2 (tenures) → A3 (seed) → A4 (time-aware) →
contact_tenures → A6 (conflicts) → A5 (display)."""
from __future__ import annotations
import sqlite3

from cleo.discovery_v2.stems import build_stems
from cleo.discovery_v2.anchor_scores import build_anchor_scores
from cleo.discovery_v2.seeding import build_seeds, build_contact_tenures  # NEW import
from cleo.discovery_v2.expansion import build_expansion
from cleo.discovery_v2.conflicts import detect_conflicts


def build_auto_groups(conn: sqlite3.Connection, *, verbose: bool = True) -> dict:
    if verbose:
        print('Layer 2: starting build...', flush=True)

    a1 = build_stems(conn, verbose=verbose)
    a2 = build_anchor_scores(conn, verbose=verbose)
    a3 = build_seeds(conn, verbose=verbose)
    a4 = build_expansion(conn, verbose=verbose)
    ct = build_contact_tenures(conn, verbose=verbose)  # NEW
    a6 = detect_conflicts(conn, verbose=verbose)        # NEW
    a5 = _finalize_display_and_counts(conn, verbose=verbose)

    summary = {**a1, **a2, **a3, **a4, **ct, **a6, **a5}
    if verbose:
        print(f'Layer 2: done. {summary}', flush=True)
    return summary
```

(Promote `_build_contact_tenures` from Task 6 to a public `build_contact_tenures` in `seeding.py`.)

- [ ] **Step 2: Run full pipeline tests**

```bash
PYTHONPATH=. pytest tests/test_discovery_v2_auto_groups.py tests/test_discovery_v2_seeding.py tests/test_discovery_v2_expansion.py tests/test_discovery_v2_conflicts.py -v
# Expected: all green
```

- [ ] **Step 3: Commit**

```bash
git add cleo/discovery_v2/auto_groups.py cleo/discovery_v2/seeding.py
git commit -m "feat(layer2): wire timeline + conflict stages into orchestrator"
```

---

### Task 10: Real-DB rebuild + verification

**Files:** none (run + verify only — produces a run-notes file).

- [ ] **Step 1: Apply migration to real DB**

```bash
python -m cleo.database.migrations.017_tenure_tables
sqlite3 data/cleo.db "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'auto_%tenure%' OR name='auto_conflict_flags'"
# Expected: 3 rows
```

- [ ] **Step 2: Rebuild Layer 2**

```bash
python -m cleo.discovery_v2 2>&1 | tee /tmp/h2-rebuild.log
```

Expected: completes in < 5 minutes. Captures output for the verification notes.

- [ ] **Step 3: Verify DH Management's three address tenures**

```bash
sqlite3 -column -header data/cleo.db "
SELECT anchor_type, anchor_value, start_date, end_date, n_party_sides_in_window
FROM auto_group_anchor_tenures
WHERE auto_group_id IN (
  SELECT auto_group_id FROM auto_groups WHERE canonical_stem='dh' LIMIT 1
)
AND anchor_type='address_unit'
ORDER BY start_date
"
# Expected: distinct tenures for 2555 Eglinton, 160 Shorting, 180 Shorting
```

- [ ] **Step 4: Verify TD Bank still doesn't attach**

```bash
sqlite3 -column -header data/cleo.db "
SELECT agm.auto_group_id, ag.canonical_stem, agm.match_score
FROM auto_group_members agm
JOIN auto_groups ag ON ag.auto_group_id = agm.auto_group_id
WHERE agm.source_id = 'RT196095' AND agm.side = 'seller'
"
# Expected: empty (or non-kingsett group)
```

- [ ] **Step 5: Inspect conflict flags**

```bash
sqlite3 -column -header data/cleo.db "
SELECT conflict_type, COUNT(*) AS n
FROM auto_conflict_flags
GROUP BY conflict_type
"
# Expected: non-zero counts on at least anchor_reassignment and contact_overlap.

sqlite3 -column -header data/cleo.db "
SELECT conflict_type, entity_value, group_a, group_b, date_observed, description
FROM auto_conflict_flags
ORDER BY conflict_type, date_observed DESC
LIMIT 10
"
# Spot-check the descriptions are sensible.
```

- [ ] **Step 6: Capture runtime + counts**

```bash
sqlite3 -column -header data/cleo.db "
SELECT
  (SELECT COUNT(*) FROM auto_groups) AS n_groups,
  (SELECT COUNT(*) FROM auto_group_anchor_tenures) AS n_anchor_tenures,
  (SELECT COUNT(*) FROM auto_contact_tenures) AS n_contact_tenures,
  (SELECT COUNT(*) FROM auto_group_members) AS n_members,
  (SELECT COUNT(*) FROM auto_conflict_flags) AS n_conflicts
"
```

- [ ] **Step 7: Write verification notes**

Create `docs/superpowers/run-notes/2026-04-30-layer-2-plan-h2-verification.md`:

```markdown
# Plan H2 Verification Notes

**Date:** 2026-04-30
**Branch:** `feat/group-discovery-algorithm`

## Migration

- 017 applied: auto_group_anchor_tenures, auto_contact_tenures, auto_conflict_flags created.

## Builder rebuild

Run command: `python -m cleo.discovery_v2`
Total time: <observed>

- Total `auto_groups`: <count>
- Total `auto_group_anchor_tenures`: <count>
- Total `auto_contact_tenures`: <count>
- Total `auto_group_members`: <count>
- Total `auto_conflict_flags`: <count>

## DH Management three tenures

<list the three tenures captured>

## TD Bank false positive

RT196095 (seller) attachment status: <result>

## Conflict flag breakdown

| conflict_type | n |
|---|---|
| anchor_reassignment | <> |
| contact_overlap | <> |
| transient_tenure | <> |
| abrupt_tenure_end | <> |

## Findings

<3-5 specific observations>

## What's next

Plan H3: time-aware UI surfaces.
```

- [ ] **Step 8: Commit**

```bash
git add docs/superpowers/run-notes/2026-04-30-layer-2-plan-h2-verification.md
git commit -m "docs: Plan H2 verification notes"
```

---

## Self-Review

**Spec coverage check** (against the H2 section of `2026-04-29-layer-2-plan-h-timeline-aware-attribution-design.md`):

- ✅ **Migration 017** — Task 1 (three tables, CHECK constraints, indexes).
- ✅ **Constants** — Task 2 (5 knobs).
- ✅ **Stage A0 (timelines)** — Task 3.
- ✅ **Stage A2 (windowed dominance)** — Task 4 (pure-Python detector + DB plumbing).
- ✅ **Stage A3 (seeding update)** — Task 5 (auto_group_anchor_tenures persistence).
- ✅ **Contact tenures** — Task 6.
- ✅ **Stage A4 (time-aware expansion + conflict emission)** — Task 7.
- ✅ **Stage A6 (conflict detector)** — Task 8.
- ✅ **Orchestrator wiring** — Task 9.
- ✅ **Real-DB verification** — Task 10.

**Out of scope per spec, intentionally not in plan:**
- Frontend changes (Plan H3).
- Modifying the H1 explorer.py routes to read from tenure tables (anchor_uniqueness snapshot keeps them working).
- Auto-resolving conflicts (deferred to Plan C).

**Type consistency:**
- Tenure dict shape (used in `tenures.py` and `anchor_scores.py`): `{dominant_stem, start_date, end_date, n_party_sides, dominance_share, score}`.
- DB column shape: `auto_group_anchor_tenures(auto_group_id, anchor_type, anchor_value, start_date, end_date, n_party_sides_in_window, dominance_share_in_window, score)`. The Python→SQL mapping is `n_party_sides → n_party_sides_in_window`, `dominance_share → dominance_share_in_window`. This is intentional — the suffix `_in_window` makes it explicit at the DB level that the value is windowed, not lifetime.

**Open question (deliberately not covered, will surface during verification):** The interaction between H1's `_score_match` (using H1 constants like `MATCH_SCORE_DIRECT_STEM_HIT`, `MATCH_SCORE_PHONE_MATCH`, etc.) and H2's tenure-window gating. The plan's Stage A4 sketches `_score_match_h2` as a placeholder — the implementer should reuse the H1 constants and gating, just adding the tenure-window check as a prerequisite filter. If the H1 score logic produces a per-anchor signal and the candidate_groups dict already filters anchors to those with active tenures, the logic should compose cleanly.

No placeholders remain. Code in every step.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-30-layer-2-plan-h2-timelines.md`. 10 tasks. Two execution options:

**1. Subagent-Driven (recommended)** — Fresh subagent per task with two-stage review.

**2. Inline Execution** — In this session with checkpoints.

Which approach?
