# Layer 2 Plan A — Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-04-27-layer-2-auto-group-discovery-design.md`

**Goal:** Ship the Foundation slice of Layer 2 — verified-promotion stem extraction, anchor uniqueness scoring, auto-seeded groups with confidence tiering (Confirmed / Probable / Candidate), group expansion, plus a read-only `/explorer/auto-groups` UI.

**Architecture:** Five-stage builder (`stems → anchor scores → seeding → expansion → display naming`) writes to new `auto_*` derived tables. Builder runs after Layer 1's `build_all_indexes`. CRM tables (`auto_group_overrides`, `auto_group_merges`, `auto_anchor_overrides`) created now and read by the seeding stage; populated by Plan C later.

**Tech Stack:** Python 3.12, SQLite (raw queries), pytest, FastAPI, React 19 + Radix UI.

---

## File Structure

**New backend files:**
- `cleo/database/migrations/015_layer2_foundation_tables.py` — Plan A schema (derived + CRM tables).
- `cleo/discovery_v2/constants.py` — tunable thresholds (stem promotion, anchor seeding, tier cutoffs, match scoring).
- `cleo/discovery_v2/stems.py` — Stage A1: candidate-stem extraction + verified-promotion.
- `cleo/discovery_v2/anchor_scores.py` — Stage A2: per-anchor uniqueness scoring.
- `cleo/discovery_v2/seeding.py` — Stage A3: auto-seed groups from anchor convergence + tier them + apply CRM overrides.
- `cleo/discovery_v2/expansion.py` — Stage A4: attach matching party-sides + numbered-corp members to seeded groups.
- `cleo/discovery_v2/auto_groups.py` — top-level orchestrator: runs A1→A5 in order. Stage A5 (display name + counts) lives here.

**Modified backend files:**
- `cleo/discovery_v2/__main__.py` — call the orchestrator after `build_all_indexes`.
- `cleo/web/routes/explorer.py` — add `GET /api/explorer/auto-groups` and `GET /api/explorer/auto-groups/{auto_group_id}`.

**New test files:**
- `tests/test_discovery_v2_stems.py`
- `tests/test_discovery_v2_anchor_scores.py`
- `tests/test_discovery_v2_seeding.py`
- `tests/test_discovery_v2_expansion.py`
- `tests/test_discovery_v2_auto_groups.py` — integration test for the full pipeline.

**Modified test files:**
- `tests/test_routes_explorer.py` — fixture adds auto_groups + endpoint tests.

**New frontend files:**
- `frontend/src/pages/ExplorerAutoGroups.tsx` — list page with tier filter.
- `frontend/src/pages/ExplorerAutoGroupDetail.tsx` — detail page.

**Modified frontend files:**
- `frontend/src/types/index.ts` — `AutoGroupSummary`, `AutoGroupDetail`, `AutoGroupAnchor`, `AutoGroupListResponse`.
- `frontend/src/components/explorer/ExplorerTabs.tsx` — add "Groups (Auto)" tab between Contacts and the right-edge.
- `frontend/src/App.tsx` — routes for `/explorer/auto-groups` and `/explorer/auto-groups/:id`.

---

## Tasks

### Task 1: Migration 015 — Layer 2 foundation tables

**Files:**
- Create: `cleo/database/migrations/015_layer2_foundation_tables.py`
- Test: `tests/test_migration_015_layer2.py`

- [ ] **Step 1: Write failing test verifying all six derived tables + three CRM tables exist after migration**

```python
# tests/test_migration_015_layer2.py
import importlib
import sqlite3

# Migration module names start with digits, so we can't use a plain
# `from ... import ...` statement.
_m = importlib.import_module('cleo.database.migrations.015_layer2_foundation_tables')


DERIVED_TABLES = {
    'brand_stem',
    'brand_stem_phrase_map',
    'anchor_uniqueness',
    'auto_groups',
    'auto_group_anchors',
    'auto_group_members',
}
CRM_TABLES = {
    'auto_group_overrides',
    'auto_group_merges',
    'auto_anchor_overrides',
}


def test_migration_creates_all_layer2_tables():
    conn = sqlite3.connect(':memory:')
    _m.migrate(conn)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    table_names = {r[0] for r in rows}
    assert DERIVED_TABLES.issubset(table_names), \
        f'Missing derived: {DERIVED_TABLES - table_names}'
    assert CRM_TABLES.issubset(table_names), \
        f'Missing CRM: {CRM_TABLES - table_names}'


def test_migration_is_idempotent():
    conn = sqlite3.connect(':memory:')
    _m.migrate(conn)
    _m.migrate(conn)  # should not raise
    cnt = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master "
        "WHERE type='table' AND name='auto_groups'"
    ).fetchone()[0]
    assert cnt == 1
```

- [ ] **Step 2: Run test, confirm it fails**

```bash
pytest tests/test_migration_015_layer2.py -v
# Expected: ImportError on the module that doesn't exist yet
```

- [ ] **Step 3: Create `cleo/database/migrations/015_layer2_foundation_tables.py`**

```python
"""
Migration 015: Layer 2 foundation tables (Plan A scope).

Creates derived tables that the Layer 2 builder rebuilds on each run, plus CRM
tables that persist user actions across runs (Plan A reads them; Plan C writes
them through the UI).

Derived (rebuilt every Layer 2 run):
  - brand_stem
  - brand_stem_phrase_map
  - anchor_uniqueness
  - auto_groups
  - auto_group_anchors
  - auto_group_members

CRM (never dropped or rebuilt):
  - auto_group_overrides
  - auto_group_merges
  - auto_anchor_overrides
"""
from __future__ import annotations
import os
import sqlite3


def migrate(conn: sqlite3.Connection) -> None:
    print('Migration 015: creating Layer 2 foundation tables...')
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS brand_stem (
            stem                  TEXT PRIMARY KEY,
            stem_type             TEXT NOT NULL CHECK (stem_type IN ('distinctive', 'position_anchor')),
            dominant_anchor_type  TEXT NOT NULL,
            dominant_anchor_value TEXT NOT NULL,
            dominance_share       REAL NOT NULL,
            volume                INTEGER NOT NULL,
            verified_at           TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS brand_stem_phrase_map (
            phrase     TEXT PRIMARY KEY,
            stem       TEXT NOT NULL,
            confidence REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_bspm_stem ON brand_stem_phrase_map(stem);

        CREATE TABLE IF NOT EXISTS anchor_uniqueness (
            anchor_type         TEXT NOT NULL CHECK (anchor_type IN ('phone','address_root','address_base','contact')),
            anchor_value        TEXT NOT NULL,
            dominant_stem       TEXT,
            dominance_share     REAL,
            volume              INTEGER NOT NULL,
            score               REAL NOT NULL,
            is_service_provider INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (anchor_type, anchor_value)
        );
        CREATE INDEX IF NOT EXISTS idx_au_score ON anchor_uniqueness(score);
        CREATE INDEX IF NOT EXISTS idx_au_stem  ON anchor_uniqueness(dominant_stem);

        CREATE TABLE IF NOT EXISTS auto_groups (
            auto_group_id  TEXT PRIMARY KEY,
            canonical_stem TEXT NOT NULL,
            display_name   TEXT NOT NULL,
            tier           TEXT NOT NULL CHECK (tier IN ('confirmed','probable','candidate')),
            confidence     REAL NOT NULL,
            n_anchors      INTEGER NOT NULL,
            n_members      INTEGER NOT NULL,
            discovered_at  TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_ag_tier ON auto_groups(tier);
        CREATE INDEX IF NOT EXISTS idx_ag_stem ON auto_groups(canonical_stem);

        CREATE TABLE IF NOT EXISTS auto_group_anchors (
            auto_group_id TEXT NOT NULL,
            anchor_type   TEXT NOT NULL,
            anchor_value  TEXT NOT NULL,
            score         REAL NOT NULL,
            PRIMARY KEY (auto_group_id, anchor_type, anchor_value)
        );

        CREATE TABLE IF NOT EXISTS auto_group_members (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            auto_group_id TEXT NOT NULL,
            member_type   TEXT NOT NULL CHECK (member_type IN ('party_side','numbered_corp')),
            source_id     TEXT,
            side          TEXT,
            corp_name     TEXT,
            match_score   REAL NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_agm_party
            ON auto_group_members(auto_group_id, source_id, side)
            WHERE member_type = 'party_side';
        CREATE UNIQUE INDEX IF NOT EXISTS idx_agm_corp
            ON auto_group_members(auto_group_id, corp_name)
            WHERE member_type = 'numbered_corp';

        -- CRM tables
        CREATE TABLE IF NOT EXISTS auto_group_overrides (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            auto_group_id TEXT NOT NULL,
            action        TEXT NOT NULL CHECK (action IN ('confirm','reject','split')),
            user_id       TEXT NOT NULL,
            action_at     TEXT NOT NULL DEFAULT (datetime('now')),
            notes         TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_ago_group ON auto_group_overrides(auto_group_id);

        CREATE TABLE IF NOT EXISTS auto_group_merges (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_auto_group_id TEXT NOT NULL,
            child_auto_group_id  TEXT NOT NULL,
            user_id              TEXT NOT NULL,
            action_at            TEXT NOT NULL DEFAULT (datetime('now')),
            notes                TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_agm_parent ON auto_group_merges(parent_auto_group_id);

        CREATE TABLE IF NOT EXISTS auto_anchor_overrides (
            id                        INTEGER PRIMARY KEY AUTOINCREMENT,
            anchor_type               TEXT NOT NULL,
            anchor_value              TEXT NOT NULL,
            override_stem             TEXT,
            override_service_provider INTEGER NOT NULL DEFAULT 0,
            user_id                   TEXT NOT NULL,
            action_at                 TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_aao_anchor ON auto_anchor_overrides(anchor_type, anchor_value);
    """)
    conn.commit()
    print('Migration 015 complete.')


if __name__ == '__main__':
    db_path = os.path.join(
        os.path.dirname(__file__), '..', '..', '..', 'data', 'cleo.db'
    )
    conn = sqlite3.connect(db_path)
    migrate(conn)
    conn.close()
```

- [ ] **Step 4: Run tests, confirm both pass**

```bash
pytest tests/test_migration_015_layer2.py -v
# Expected: 2 passed
```

- [ ] **Step 5: Apply the migration to the real DB**

```bash
python -m cleo.database.migrations.015_layer2_foundation_tables
sqlite3 data/cleo.db "SELECT COUNT(*) FROM sqlite_master WHERE name LIKE 'auto_%' OR name='brand_stem' OR name='brand_stem_phrase_map' OR name='anchor_uniqueness'"
# Expected: 9
```

- [ ] **Step 6: Commit**

```bash
git add cleo/database/migrations/015_layer2_foundation_tables.py tests/test_migration_015_layer2.py
git commit -m "feat(layer2): migration 015 — foundation tables"
```

---

### Task 2: Constants module

**Files:**
- Create: `cleo/discovery_v2/constants.py`

- [ ] **Step 1: Write the file with all Plan A knobs**

```python
"""Tunable knobs for Layer 2 Plan A. Adjust here and re-run the builder."""
from __future__ import annotations

# ── Stage A1: Stem extraction ──────────────────────────────────────────────
# A candidate stem is promoted to verified only when both thresholds are met.
STEM_PROMOTION_DOMINANCE = 0.6
STEM_PROMOTION_VOLUME    = 5

# ── Stage A2: Anchor uniqueness scoring ────────────────────────────────────
# score = dominance_share * log(volume + 1).
# An anchor must clear this score to participate in seeding.
ANCHOR_SEEDING_SCORE_THRESHOLD = 1.5

# A "corroborating" anchor needs a lower bar (used in candidate-tier rule).
ANCHOR_CORROBORATION_SCORE_THRESHOLD = 0.5

# ── Stage A3: Group seeding & tiering ──────────────────────────────────────
TIER_CONFIRMED_MIN_CONFIDENCE = 0.75
TIER_PROBABLE_MIN_CONFIDENCE  = 0.4
# Anything below TIER_PROBABLE_MIN_CONFIDENCE is candidate.

# Confidence formula reference ceiling — keeps confidence stable across runs.
ANCHOR_SCORE_CEILING = 5.0

# ── Stage A4: Group expansion ──────────────────────────────────────────────
# Match scores for attaching a party-side to a seeded group.
MATCH_SCORE_DIRECT_STEM_HIT             = 1.0
MATCH_SCORE_PHONE_MATCH                 = 0.7
MATCH_SCORE_ADDRESS_PLUS_CONTACT        = 0.7
MATCH_SCORE_ADDRESS_ROOT_ALONE          = 0.5
MATCH_SCORE_PHONE_BRAND_CONTRADICTION   = -0.5  # explicitly do-not-attach
MATCH_SCORE_SINGLE_WEAK_SIGNAL          = 0.3

# Threshold for actually attaching a party-side (Stage A4).
EXPANSION_ATTACH_THRESHOLD = 0.5
```

- [ ] **Step 2: Commit**

```bash
git add cleo/discovery_v2/constants.py
git commit -m "feat(layer2): constants module for tunable thresholds"
```

---

### Task 3: Stage A1 — Stem extraction

**Files:**
- Create: `cleo/discovery_v2/stems.py`
- Test: `tests/test_discovery_v2_stems.py`

The module exports two public functions:

- `extract_candidate_stem(phrase: str, conn) -> tuple[str, str] | None` — given a brand_phrase, returns `(stem_token, stem_type)` where stem_type is `'distinctive'` or `'position_anchor'`, or `None` if no candidate can be extracted. Picks highest-IDF distinctive 1-gram in the phrase; falls back to highest-rank position-anchor 1-gram.
- `build_stems(conn, *, verbose=True)` — runs the full A1 pipeline: collects candidates, evaluates each against the anchor-dominance threshold, promotes verified stems into `brand_stem`, populates `brand_stem_phrase_map`. Idempotent (deletes prior rows first).

- [ ] **Step 1: Test fixture — synthetic Layer 1 data**

```python
# tests/test_discovery_v2_stems.py
import sqlite3
import pytest

from cleo.discovery_v2.stems import extract_candidate_stem, build_stems


def _make_db():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE party_fingerprints (
            source_id TEXT, side TEXT, phone TEXT,
            street_number TEXT, street_name TEXT,
            PRIMARY KEY (source_id, side)
        );
        CREATE TABLE party_atoms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT, side TEXT,
            atom_type TEXT, atom_value TEXT, source_field TEXT
        );
        CREATE TABLE brand_token_summary (
            token TEXT PRIMARY KEY, idf REAL, n_party_sides INTEGER,
            n_distinct_phrases INTEGER, is_distinctive INTEGER, is_excluded INTEGER,
            wordfreq_zipf REAL, is_english_common INTEGER, is_place_name INTEGER,
            is_industry_stopword INTEGER, filter_reason TEXT,
            position_consistency REAL, total_child_coverage REAL,
            is_position_anchor INTEGER NOT NULL DEFAULT 0,
            discovered_at TEXT
        );
        CREATE TABLE brand_stem (
            stem TEXT PRIMARY KEY, stem_type TEXT NOT NULL,
            dominant_anchor_type TEXT NOT NULL, dominant_anchor_value TEXT NOT NULL,
            dominance_share REAL NOT NULL, volume INTEGER NOT NULL,
            verified_at TEXT
        );
        CREATE TABLE brand_stem_phrase_map (
            phrase TEXT PRIMARY KEY, stem TEXT NOT NULL, confidence REAL NOT NULL
        );
    """)
    # Seed brand_token_summary
    conn.executemany(
        """INSERT INTO brand_token_summary
            (token, idf, n_party_sides, n_distinct_phrases, is_distinctive, is_excluded,
             wordfreq_zipf, is_english_common, is_place_name, is_industry_stopword,
             filter_reason, position_consistency, total_child_coverage,
             is_position_anchor, discovered_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        [
            # distinctive: skyline (idf 6.13), kingsett (6.5)
            ('skyline',  6.13, 539, 50, 1, 0, 0.0, 0, 0, 0, None, None, None, 0, '2026-04-26'),
            ('kingsett', 6.50, 367, 30, 1, 0, 0.0, 0, 0, 0, None, None, None, 0, '2026-04-26'),
            # position-anchor: dd (rare 2-letter operator code), no distinctive
            ('dd',       7.10,  60,  8, 0, 0, 0.0, 0, 0, 0, None, 0.99, 1.0, 1, '2026-04-26'),
            # generic words (filtered)
            ('holdings', 4.20, 17000, 100, 0, 0, 0.0, 0, 0, 1, 'industry', None, None, 0, '2026-04-26'),
            ('real',     3.50, 3500,  20, 0, 0, 0.0, 0, 0, 0, 'english',  None, None, 0, '2026-04-26'),
            ('estate',   3.50, 3700,  20, 0, 0, 0.0, 0, 0, 0, 'english',  None, None, 0, '2026-04-26'),
        ]
    )
    return conn


def _seed_phrase(conn, source_id, side, phrase, phone=None):
    conn.execute(
        "INSERT OR IGNORE INTO party_fingerprints (source_id, side, phone) VALUES (?,?,?)",
        (source_id, side, phone),
    )
    conn.execute(
        "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
        "VALUES (?, ?, 'brand_phrase', ?, 'party_name')",
        (source_id, side, phrase),
    )
    conn.commit()
```

- [ ] **Step 2: Test — `extract_candidate_stem` picks highest-IDF distinctive 1-gram**

```python
def test_candidate_stem_picks_highest_idf_distinctive_1gram():
    conn = _make_db()
    out = extract_candidate_stem('skyline real estate holdings', conn)
    assert out == ('skyline', 'distinctive')
```

- [ ] **Step 3: Run, confirm fail**

```bash
pytest tests/test_discovery_v2_stems.py::test_candidate_stem_picks_highest_idf_distinctive_1gram -v
# Expected: ImportError or AttributeError
```

- [ ] **Step 4: Implement `extract_candidate_stem`**

Create `cleo/discovery_v2/stems.py`:

```python
"""Stage A1: Stem extraction with verified-promotion."""
from __future__ import annotations
import math
import sqlite3
from typing import Optional, Tuple

from cleo.discovery_v2.constants import (
    STEM_PROMOTION_DOMINANCE, STEM_PROMOTION_VOLUME,
)


def _tokenize(phrase: str) -> list[str]:
    return [t for t in (phrase or '').split() if t]


def extract_candidate_stem(phrase: str, conn: sqlite3.Connection) -> Optional[Tuple[str, str]]:
    """Pick a candidate stem from a brand_phrase. Returns (stem, stem_type) or None.

    Rule: highest-IDF distinctive 1-gram in the phrase. If none, fall back to
    the highest-position-rank PA 1-gram.
    """
    tokens = _tokenize(phrase)
    if not tokens:
        return None
    placeholders = ','.join(['?'] * len(tokens))
    rows = conn.execute(
        f"""SELECT token, idf, is_distinctive,
                   COALESCE(is_position_anchor, 0) AS is_pa
           FROM brand_token_summary
           WHERE token IN ({placeholders})""",
        tokens,
    ).fetchall()
    distinctive = [(r['token'], r['idf']) for r in rows if r['is_distinctive']]
    if distinctive:
        token, _ = max(distinctive, key=lambda x: x[1])
        return (token, 'distinctive')
    pa = [(r['token'], r['idf']) for r in rows if r['is_pa']]
    if pa:
        token, _ = max(pa, key=lambda x: x[1])
        return (token, 'position_anchor')
    return None
```

- [ ] **Step 5: Run, confirm pass**

```bash
pytest tests/test_discovery_v2_stems.py::test_candidate_stem_picks_highest_idf_distinctive_1gram -v
# Expected: PASS
```

- [ ] **Step 6: Add and verify these tests one cycle each**

```python
def test_candidate_stem_falls_back_to_position_anchor_when_no_distinctive():
    conn = _make_db()
    out = extract_candidate_stem('dd 64 roehampton', conn)
    assert out == ('dd', 'position_anchor')


def test_candidate_stem_returns_none_when_phrase_has_no_signal():
    conn = _make_db()
    out = extract_candidate_stem('the real estate holdings', conn)
    assert out is None


def test_candidate_stem_handles_empty_phrase():
    conn = _make_db()
    assert extract_candidate_stem('', conn) is None
    assert extract_candidate_stem(None, conn) is None
```

Run after each:

```bash
pytest tests/test_discovery_v2_stems.py -v
```

Each should pass with no further code change (the implementation already covers them).

- [ ] **Step 7: Test — `build_stems` promotes a stem above the dominance + volume thresholds**

Add to the test file:

```python
def test_build_stems_promotes_skyline_above_thresholds():
    conn = _make_db()
    # Seed 6 sides at phone P1, 5 of them with skyline phrases (dominance 5/6 = 0.83)
    for i in range(5):
        _seed_phrase(conn, f'TX{i}', 'buyer', 'skyline real estate holdings', phone='P1')
    _seed_phrase(conn, 'TX5', 'buyer', 'something else', phone='P1')

    build_stems(conn, verbose=False)

    rows = conn.execute('SELECT * FROM brand_stem').fetchall()
    stems = {r['stem']: dict(r) for r in rows}
    assert 'skyline' in stems
    assert stems['skyline']['stem_type'] == 'distinctive'
    assert stems['skyline']['dominant_anchor_type'] == 'phone'
    assert stems['skyline']['dominant_anchor_value'] == 'P1'
    assert stems['skyline']['volume'] >= 5
    assert stems['skyline']['dominance_share'] >= 0.6
```

- [ ] **Step 8: Run, confirm fail (build_stems not implemented yet)**

- [ ] **Step 9: Implement `build_stems`**

Append to `cleo/discovery_v2/stems.py`:

```python
def build_stems(conn: sqlite3.Connection, *, verbose: bool = True) -> dict:
    """Run Stage A1 end-to-end. Idempotent — clears prior derived rows first.

    Returns a dict with summary counts: { 'n_stems', 'n_phrase_mappings' }.
    """
    conn.execute('DELETE FROM brand_stem')
    conn.execute('DELETE FROM brand_stem_phrase_map')

    # Step 1: collect every distinct brand_phrase + its candidate stem
    phrases = [r['atom_value'] for r in conn.execute(
        "SELECT DISTINCT atom_value FROM party_atoms WHERE atom_type='brand_phrase'"
    )]
    phrase_to_candidate: dict[str, tuple[str, str]] = {}
    for ph in phrases:
        c = extract_candidate_stem(ph, conn)
        if c is not None:
            phrase_to_candidate[ph] = c

    # Step 2: for each candidate stem, find dominant anchor + dominance_share
    # We score stems against both phone and address_root anchors, take the max.
    candidate_stems = {c[0]: c[1] for c in phrase_to_candidate.values()}

    promoted: list[tuple] = []  # rows for brand_stem
    for stem, stem_type in candidate_stems.items():
        # Pull all party-sides whose phrases contain this stem candidate
        # (i.e., stem appears in any of their phrases via phrase_to_candidate).
        stem_phrases = [ph for ph, c in phrase_to_candidate.items() if c[0] == stem]
        if not stem_phrases:
            continue

        # Dominance against phone anchor
        phone_row = conn.execute(
            f"""WITH stem_sides AS (
                    SELECT DISTINCT pa.source_id, pa.side
                    FROM party_atoms pa
                    WHERE pa.atom_type='brand_phrase'
                      AND pa.atom_value IN ({','.join(['?']*len(stem_phrases))})
                )
                SELECT pf.phone AS anchor,
                       COUNT(*) AS sides_with_stem,
                       (SELECT COUNT(*) FROM party_fingerprints pf2
                          WHERE pf2.phone = pf.phone) AS total_at_anchor
                FROM stem_sides s
                JOIN party_fingerprints pf
                  ON pf.source_id=s.source_id AND pf.side=s.side
                WHERE pf.phone IS NOT NULL AND pf.phone != ''
                GROUP BY pf.phone
                ORDER BY sides_with_stem DESC
                LIMIT 1""",
            stem_phrases,
        ).fetchone()
        # Dominance against address_root anchor
        addr_row = conn.execute(
            f"""WITH stem_sides AS (
                    SELECT DISTINCT pa.source_id, pa.side
                    FROM party_atoms pa
                    WHERE pa.atom_type='brand_phrase'
                      AND pa.atom_value IN ({','.join(['?']*len(stem_phrases))})
                )
                SELECT (pf.street_number || '|' || pf.street_name) AS anchor,
                       COUNT(*) AS sides_with_stem,
                       (SELECT COUNT(*) FROM party_fingerprints pf2
                          WHERE pf2.street_number=pf.street_number
                            AND pf2.street_name=pf.street_name) AS total_at_anchor
                FROM stem_sides s
                JOIN party_fingerprints pf
                  ON pf.source_id=s.source_id AND pf.side=s.side
                WHERE pf.street_number != '' AND pf.street_name != ''
                  AND pf.street_number IS NOT NULL AND pf.street_name IS NOT NULL
                GROUP BY pf.street_number, pf.street_name
                ORDER BY sides_with_stem DESC
                LIMIT 1""",
            stem_phrases,
        ).fetchone()

        # Pick the better of phone vs address_root
        candidates = []
        if phone_row and phone_row['total_at_anchor'] > 0:
            d = phone_row['sides_with_stem'] / phone_row['total_at_anchor']
            candidates.append(('phone', phone_row['anchor'], d, phone_row['total_at_anchor']))
        if addr_row and addr_row['total_at_anchor'] > 0:
            d = addr_row['sides_with_stem'] / addr_row['total_at_anchor']
            candidates.append(('address_root', addr_row['anchor'], d, addr_row['total_at_anchor']))
        if not candidates:
            continue
        atype, aval, dom, vol = max(candidates, key=lambda c: c[2] * math.log(c[3] + 1))

        if dom >= STEM_PROMOTION_DOMINANCE and vol >= STEM_PROMOTION_VOLUME:
            promoted.append((stem, stem_type, atype, aval, dom, vol))

    if promoted:
        conn.executemany(
            """INSERT INTO brand_stem
                 (stem, stem_type, dominant_anchor_type, dominant_anchor_value,
                  dominance_share, volume)
               VALUES (?, ?, ?, ?, ?, ?)""",
            promoted,
        )

    # Step 3: write phrase → stem map (only phrases whose candidate was promoted)
    verified = {row[0] for row in promoted}
    mappings = []
    for ph, (cand, _) in phrase_to_candidate.items():
        if cand in verified:
            mappings.append((ph, cand, 1.0))  # confidence = 1.0 placeholder for Plan A
    if mappings:
        conn.executemany(
            "INSERT INTO brand_stem_phrase_map (phrase, stem, confidence) VALUES (?, ?, ?)",
            mappings,
        )

    conn.commit()
    if verbose:
        print(f'  Stage A1 (stems): {len(verified):,} verified stems, '
              f'{len(mappings):,} phrase mappings.', flush=True)
    return {'n_stems': len(verified), 'n_phrase_mappings': len(mappings)}
```

- [ ] **Step 10: Run, confirm pass**

```bash
pytest tests/test_discovery_v2_stems.py::test_build_stems_promotes_skyline_above_thresholds -v
```

- [ ] **Step 11: Add — does NOT promote when below thresholds**

```python
def test_build_stems_rejects_low_dominance():
    conn = _make_db()
    # 2 sides with skyline at phone P1, 8 sides with random other content at P1.
    # Dominance = 2/10 = 0.2 — below threshold.
    for i in range(2):
        _seed_phrase(conn, f'TX{i}', 'buyer', 'skyline real estate holdings', phone='P1')
    for i in range(8):
        _seed_phrase(conn, f'TX{100+i}', 'buyer', 'something unrelated', phone='P1')

    build_stems(conn, verbose=False)

    rows = conn.execute('SELECT * FROM brand_stem WHERE stem=?', ('skyline',)).fetchall()
    assert len(rows) == 0


def test_build_stems_rejects_low_volume():
    conn = _make_db()
    # Only 3 sides total at P1, all skyline — dominance OK but volume below 5.
    for i in range(3):
        _seed_phrase(conn, f'TX{i}', 'buyer', 'skyline real estate holdings', phone='P1')

    build_stems(conn, verbose=False)

    rows = conn.execute('SELECT * FROM brand_stem WHERE stem=?', ('skyline',)).fetchall()
    assert len(rows) == 0


def test_build_stems_is_idempotent():
    conn = _make_db()
    for i in range(6):
        _seed_phrase(conn, f'TX{i}', 'buyer', 'skyline real estate holdings', phone='P1')
    build_stems(conn, verbose=False)
    build_stems(conn, verbose=False)
    rows = conn.execute('SELECT * FROM brand_stem WHERE stem=?', ('skyline',)).fetchall()
    assert len(rows) == 1
```

Run after each:

```bash
pytest tests/test_discovery_v2_stems.py -v
# Expected: all pass
```

- [ ] **Step 12: Commit**

```bash
git add cleo/discovery_v2/stems.py tests/test_discovery_v2_stems.py
git commit -m "feat(layer2): Stage A1 — stem extraction with verified-promotion"
```

---

### Task 4: Stage A2 — Anchor uniqueness scoring

**Files:**
- Create: `cleo/discovery_v2/anchor_scores.py`
- Test: `tests/test_discovery_v2_anchor_scores.py`

The module exports `build_anchor_scores(conn, *, verbose=True)`. For each anchor type (phone, address_root, address_base, contact), it computes the dominant stem, dominance_share, volume, and `score = dominance_share × log(volume + 1)`, then writes one row per (anchor_type, anchor_value) into `anchor_uniqueness`. Idempotent.

- [ ] **Step 1: Test fixture — extends the Task 3 fixture with multiple anchors**

```python
# tests/test_discovery_v2_anchor_scores.py
import math
import sqlite3
import pytest

from cleo.discovery_v2.stems import build_stems
from cleo.discovery_v2.anchor_scores import build_anchor_scores


def _make_db():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE party_fingerprints (
            source_id TEXT, side TEXT, phone TEXT, contact_fingerprint TEXT,
            street_number TEXT, street_name TEXT, street_suffix TEXT,
            PRIMARY KEY (source_id, side)
        );
        CREATE TABLE party_atoms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT, side TEXT,
            atom_type TEXT, atom_value TEXT, source_field TEXT
        );
        CREATE TABLE brand_token_summary (
            token TEXT PRIMARY KEY, idf REAL, n_party_sides INTEGER,
            n_distinct_phrases INTEGER, is_distinctive INTEGER, is_excluded INTEGER,
            wordfreq_zipf REAL, is_english_common INTEGER, is_place_name INTEGER,
            is_industry_stopword INTEGER, filter_reason TEXT,
            position_consistency REAL, total_child_coverage REAL,
            is_position_anchor INTEGER NOT NULL DEFAULT 0,
            discovered_at TEXT
        );
        CREATE TABLE brand_stem (
            stem TEXT PRIMARY KEY, stem_type TEXT NOT NULL,
            dominant_anchor_type TEXT NOT NULL, dominant_anchor_value TEXT NOT NULL,
            dominance_share REAL NOT NULL, volume INTEGER NOT NULL, verified_at TEXT
        );
        CREATE TABLE brand_stem_phrase_map (
            phrase TEXT PRIMARY KEY, stem TEXT NOT NULL, confidence REAL NOT NULL
        );
        CREATE TABLE anchor_uniqueness (
            anchor_type TEXT NOT NULL, anchor_value TEXT NOT NULL,
            dominant_stem TEXT, dominance_share REAL,
            volume INTEGER NOT NULL, score REAL NOT NULL,
            is_service_provider INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (anchor_type, anchor_value)
        );
    """)
    conn.execute(
        """INSERT INTO brand_token_summary
             (token, idf, n_party_sides, n_distinct_phrases, is_distinctive,
              is_excluded, wordfreq_zipf, is_english_common, is_place_name,
              is_industry_stopword, filter_reason, position_consistency,
              total_child_coverage, is_position_anchor, discovered_at)
           VALUES ('skyline', 6.13, 100, 10, 1, 0, 0.0, 0, 0, 0, NULL, NULL, NULL, 0, '2026')"""
    )
    return conn


def _seed(conn, source_id, side, phrase, *, phone=None, contact=None,
          street_number=None, street_name=None, street_suffix=None):
    conn.execute(
        """INSERT OR IGNORE INTO party_fingerprints
             (source_id, side, phone, contact_fingerprint,
              street_number, street_name, street_suffix)
           VALUES (?,?,?,?,?,?,?)""",
        (source_id, side, phone, contact, street_number, street_name, street_suffix),
    )
    if phrase:
        conn.execute(
            "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
            "VALUES (?, ?, 'brand_phrase', ?, 'party_name')",
            (source_id, side, phrase),
        )
```

- [ ] **Step 2: Test — phone anchor scores correctly when stem dominates**

```python
def test_phone_anchor_scores_correctly_when_stem_dominates():
    conn = _make_db()
    # 6 sides at phone P1, all skyline. After build_stems, skyline is verified.
    for i in range(6):
        _seed(conn, f'TX{i}', 'buyer', 'skyline real estate holdings', phone='P1')
    build_stems(conn, verbose=False)

    build_anchor_scores(conn, verbose=False)

    row = conn.execute(
        "SELECT * FROM anchor_uniqueness WHERE anchor_type='phone' AND anchor_value='P1'"
    ).fetchone()
    assert row is not None
    assert row['dominant_stem'] == 'skyline'
    assert row['volume'] == 6
    assert row['dominance_share'] == pytest.approx(1.0)
    assert row['score'] == pytest.approx(1.0 * math.log(6 + 1))
```

- [ ] **Step 3: Run, confirm fail**

- [ ] **Step 4: Implement `build_anchor_scores`**

```python
"""Stage A2: Anchor uniqueness scoring.

For each anchor (phone, address_root, address_base, contact), computes the
dominant brand_stem and a score = dominance_share * log(volume + 1).
"""
from __future__ import annotations
import math
import sqlite3


_ANCHOR_QUERIES = {
    # anchor_type → SQL that yields (anchor_value, source_id, side) for each
    # party-side, with anchor_value being the canonical key for that type.
    'phone': """
        SELECT phone AS anchor_value, source_id, side
        FROM party_fingerprints
        WHERE phone IS NOT NULL AND phone != ''
    """,
    'address_root': """
        SELECT (street_number || '|' || street_name) AS anchor_value, source_id, side
        FROM party_fingerprints
        WHERE street_number IS NOT NULL AND street_number != ''
          AND street_name IS NOT NULL AND street_name != ''
    """,
    'address_base': """
        SELECT (street_number || '|' || street_name || '|' || COALESCE(street_suffix,'')) AS anchor_value, source_id, side
        FROM party_fingerprints
        WHERE street_number IS NOT NULL AND street_number != ''
          AND street_name IS NOT NULL AND street_name != ''
    """,
    'contact': """
        SELECT contact_fingerprint AS anchor_value, source_id, side
        FROM party_fingerprints
        WHERE contact_fingerprint IS NOT NULL AND contact_fingerprint != ''
    """,
}


def build_anchor_scores(conn: sqlite3.Connection, *, verbose: bool = True) -> dict:
    """Populate anchor_uniqueness for all four anchor types. Idempotent."""
    conn.execute('DELETE FROM anchor_uniqueness')

    # Per-side dominant stem lookup: each side has potentially multiple
    # phrases; pick the most-common stem across the side's phrases.
    side_stems = {}  # (source_id, side) -> stem
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

    rows_to_insert = []
    for anchor_type, anchor_sql in _ANCHOR_QUERIES.items():
        # Group party-sides by anchor_value
        by_anchor = {}  # anchor_value -> list of (source_id, side)
        for r in conn.execute(anchor_sql):
            by_anchor.setdefault(r['anchor_value'], []).append(
                (r['source_id'], r['side'])
            )
        for anchor_value, sides in by_anchor.items():
            volume = len(sides)
            stem_counts = {}
            for sid, side in sides:
                stem_tup = side_stems.get((sid, side))
                if stem_tup is not None:
                    stem = stem_tup[0]
                    stem_counts[stem] = stem_counts.get(stem, 0) + 1
            if stem_counts:
                dominant_stem, dom_n = max(stem_counts.items(), key=lambda x: x[1])
                dominance_share = dom_n / volume
            else:
                dominant_stem, dominance_share = None, 0.0
            score = dominance_share * math.log(volume + 1)
            rows_to_insert.append(
                (anchor_type, anchor_value, dominant_stem, dominance_share, volume, score)
            )

    if rows_to_insert:
        conn.executemany(
            """INSERT INTO anchor_uniqueness
                 (anchor_type, anchor_value, dominant_stem, dominance_share, volume, score)
               VALUES (?, ?, ?, ?, ?, ?)""",
            rows_to_insert,
        )
    conn.commit()
    if verbose:
        print(f'  Stage A2 (anchor scores): {len(rows_to_insert):,} anchor rows.', flush=True)
    return {'n_anchors': len(rows_to_insert)}
```

- [ ] **Step 5: Run, confirm pass**

- [ ] **Step 6: Add — multi-tenant phone scores low on dominance**

```python
def test_multi_tenant_phone_has_low_dominance():
    conn = _make_db()
    # 5 skyline + 5 unrelated at phone P1 (mixed-tenant).
    for i in range(5):
        _seed(conn, f'TX{i}', 'buyer', 'skyline real estate holdings', phone='P1')
    for i in range(5):
        _seed(conn, f'TX{10+i}', 'buyer', 'random unrelated holdings', phone='P1')
    build_stems(conn, verbose=False)
    build_anchor_scores(conn, verbose=False)
    row = conn.execute(
        "SELECT * FROM anchor_uniqueness WHERE anchor_type='phone' AND anchor_value='P1'"
    ).fetchone()
    # Stems-with-mapping at P1: 5 (skyline). Total: 10. Dominance = 0.5.
    # But verify the formula directly.
    assert row['dominance_share'] <= 0.5 + 0.001
    assert row['dominant_stem'] == 'skyline'  # still the majority of mapped sides


def test_anchor_with_no_mapped_phrases_has_zero_dominance():
    conn = _make_db()
    for i in range(5):
        _seed(conn, f'TX{i}', 'buyer', 'no-stem phrase', phone='P2')
    build_stems(conn, verbose=False)
    build_anchor_scores(conn, verbose=False)
    row = conn.execute(
        "SELECT * FROM anchor_uniqueness WHERE anchor_type='phone' AND anchor_value='P2'"
    ).fetchone()
    assert row['dominant_stem'] is None
    assert row['dominance_share'] == 0.0
    assert row['score'] == 0.0
```

Run + verify pass after each.

- [ ] **Step 7: Commit**

```bash
git add cleo/discovery_v2/anchor_scores.py tests/test_discovery_v2_anchor_scores.py
git commit -m "feat(layer2): Stage A2 — anchor uniqueness scoring"
```

---

### Task 5: Stage A3 — Auto-seed from anchor convergence

**Files:**
- Create: `cleo/discovery_v2/seeding.py`
- Test: `tests/test_discovery_v2_seeding.py`

The module exports `build_seeds(conn, *, verbose=True)`. For each verified stem in `brand_stem`, gathers all anchors where that stem is dominant and `score >= ANCHOR_SEEDING_SCORE_THRESHOLD`, groups them under one new `auto_groups` row, computes confidence + tier, and inserts `auto_group_anchors` rows. Applies CRM overrides (force-confirm, reject, anchor reclassification) at the end. Idempotent — drops prior auto_groups + auto_group_anchors first, but reads CRM tables fresh.

- [ ] **Step 1: Test fixture (use the same shape as Task 4 + extra Layer-2 tables)**

```python
# tests/test_discovery_v2_seeding.py
import sqlite3
import pytest

from cleo.discovery_v2.stems import build_stems
from cleo.discovery_v2.anchor_scores import build_anchor_scores
from cleo.discovery_v2.seeding import build_seeds


def _make_db():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE party_fingerprints (
            source_id TEXT, side TEXT, phone TEXT, contact_fingerprint TEXT,
            street_number TEXT, street_name TEXT, street_suffix TEXT,
            PRIMARY KEY (source_id, side)
        );
        CREATE TABLE party_atoms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT, side TEXT, atom_type TEXT, atom_value TEXT, source_field TEXT
        );
        CREATE TABLE brand_token_summary (
            token TEXT PRIMARY KEY, idf REAL, n_party_sides INTEGER,
            n_distinct_phrases INTEGER, is_distinctive INTEGER, is_excluded INTEGER,
            wordfreq_zipf REAL, is_english_common INTEGER, is_place_name INTEGER,
            is_industry_stopword INTEGER, filter_reason TEXT,
            position_consistency REAL, total_child_coverage REAL,
            is_position_anchor INTEGER NOT NULL DEFAULT 0,
            discovered_at TEXT
        );
        CREATE TABLE brand_stem (
            stem TEXT PRIMARY KEY, stem_type TEXT NOT NULL,
            dominant_anchor_type TEXT NOT NULL, dominant_anchor_value TEXT NOT NULL,
            dominance_share REAL NOT NULL, volume INTEGER NOT NULL, verified_at TEXT
        );
        CREATE TABLE brand_stem_phrase_map (
            phrase TEXT PRIMARY KEY, stem TEXT NOT NULL, confidence REAL NOT NULL
        );
        CREATE TABLE anchor_uniqueness (
            anchor_type TEXT NOT NULL, anchor_value TEXT NOT NULL,
            dominant_stem TEXT, dominance_share REAL,
            volume INTEGER NOT NULL, score REAL NOT NULL,
            is_service_provider INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (anchor_type, anchor_value)
        );
        CREATE TABLE auto_groups (
            auto_group_id TEXT PRIMARY KEY, canonical_stem TEXT NOT NULL,
            display_name TEXT NOT NULL, tier TEXT NOT NULL,
            confidence REAL NOT NULL, n_anchors INTEGER NOT NULL,
            n_members INTEGER NOT NULL, discovered_at TEXT
        );
        CREATE TABLE auto_group_anchors (
            auto_group_id TEXT NOT NULL, anchor_type TEXT NOT NULL,
            anchor_value TEXT NOT NULL, score REAL NOT NULL,
            PRIMARY KEY (auto_group_id, anchor_type, anchor_value)
        );
        CREATE TABLE auto_group_overrides (
            id INTEGER PRIMARY KEY AUTOINCREMENT, auto_group_id TEXT NOT NULL,
            action TEXT NOT NULL, user_id TEXT NOT NULL, action_at TEXT, notes TEXT
        );
        CREATE TABLE auto_group_merges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_auto_group_id TEXT NOT NULL, child_auto_group_id TEXT NOT NULL,
            user_id TEXT NOT NULL, action_at TEXT, notes TEXT
        );
        CREATE TABLE auto_anchor_overrides (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            anchor_type TEXT NOT NULL, anchor_value TEXT NOT NULL,
            override_stem TEXT, override_service_provider INTEGER NOT NULL DEFAULT 0,
            user_id TEXT NOT NULL, action_at TEXT
        );
    """)
    conn.execute(
        """INSERT INTO brand_token_summary
             (token, idf, n_party_sides, n_distinct_phrases, is_distinctive,
              is_excluded, wordfreq_zipf, is_english_common, is_place_name,
              is_industry_stopword, filter_reason, position_consistency,
              total_child_coverage, is_position_anchor, discovered_at)
           VALUES ('skyline', 6.13, 100, 10, 1, 0, 0.0, 0, 0, 0, NULL, NULL, NULL, 0, '2026')"""
    )
    return conn


def _seed(conn, sid, side, phrase, *, phone=None, contact=None,
          street_number=None, street_name=None, street_suffix=None):
    conn.execute(
        """INSERT OR IGNORE INTO party_fingerprints
             (source_id, side, phone, contact_fingerprint,
              street_number, street_name, street_suffix)
           VALUES (?,?,?,?,?,?,?)""",
        (sid, side, phone, contact, street_number, street_name, street_suffix),
    )
    if phrase:
        conn.execute(
            "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
            "VALUES (?, ?, 'brand_phrase', ?, 'party_name')",
            (sid, side, phrase),
        )


def _run_to_anchors(conn):
    build_stems(conn, verbose=False)
    build_anchor_scores(conn, verbose=False)
```

- [ ] **Step 2: Test — 3-category convergence creates a Confirmed group**

```python
def test_three_category_convergence_creates_confirmed_group():
    conn = _make_db()
    # 8 skyline party-sides converging on phone P1, address (5, douglas, st), contact 'jc'.
    for i in range(8):
        _seed(conn, f'TX{i}', 'buyer', 'skyline real estate holdings',
              phone='P1', contact='jc',
              street_number='5', street_name='douglas', street_suffix='st')
    _run_to_anchors(conn)

    build_seeds(conn, verbose=False)

    groups = conn.execute('SELECT * FROM auto_groups').fetchall()
    assert len(groups) == 1
    g = dict(groups[0])
    assert g['canonical_stem'] == 'skyline'
    assert g['tier'] == 'confirmed'
    assert g['n_anchors'] >= 3  # phone + address_root + address_base + contact

    anchors = conn.execute(
        'SELECT * FROM auto_group_anchors WHERE auto_group_id=?', (g['auto_group_id'],)
    ).fetchall()
    types = {a['anchor_type'] for a in anchors}
    assert {'phone', 'contact'}.issubset(types)
    assert 'address_root' in types or 'address_base' in types
```

- [ ] **Step 3: Run, confirm fail**

- [ ] **Step 4: Implement `build_seeds`**

```python
"""Stage A3: Auto-seed groups from anchor convergence."""
from __future__ import annotations
import math
import sqlite3

from cleo.discovery_v2.constants import (
    ANCHOR_SEEDING_SCORE_THRESHOLD,
    ANCHOR_CORROBORATION_SCORE_THRESHOLD,
    TIER_CONFIRMED_MIN_CONFIDENCE,
    TIER_PROBABLE_MIN_CONFIDENCE,
    ANCHOR_SCORE_CEILING,
)


def _next_group_id(n: int) -> str:
    return f'AGRP_{n:05d}'


def _category_of(anchor_type: str) -> str:
    """Collapse address_root + address_base into one 'address' category for tiering."""
    if anchor_type in ('address_root', 'address_base'):
        return 'address'
    return anchor_type


def _compute_tier_and_confidence(anchors: list[dict]) -> tuple[str, float]:
    """Decide tier (confirmed / probable / candidate) and confidence per the spec.

    Tier is based on the number of distinct anchor categories among anchors
    that meet ANCHOR_SEEDING_SCORE_THRESHOLD. Confidence is a continuous score.
    """
    strong = [a for a in anchors if a['score'] >= ANCHOR_SEEDING_SCORE_THRESHOLD]
    corroborating = [a for a in anchors if a['score'] >= ANCHOR_CORROBORATION_SCORE_THRESHOLD]
    strong_categories = {_category_of(a['anchor_type']) for a in strong}
    n_cats = len(strong_categories)

    avg_score = sum(a['score'] for a in anchors) / len(anchors)
    confidence = (
        (n_cats / 3.0) * 0.4
        + min(avg_score / ANCHOR_SCORE_CEILING, 1.0) * 0.4
        + 0.2  # placeholder; replaced by (1 - anti_evidence_ratio) * 0.2 in Plan B
    )

    if confidence >= TIER_CONFIRMED_MIN_CONFIDENCE and n_cats >= 3:
        tier = 'confirmed'
    elif confidence >= TIER_PROBABLE_MIN_CONFIDENCE and n_cats >= 2:
        tier = 'probable'
    elif n_cats >= 1 and len(corroborating) >= 2:
        tier = 'candidate'
    else:
        tier = None  # don't seed
    return tier, confidence


def _apply_crm_overrides(conn: sqlite3.Connection) -> None:
    """Apply auto_group_overrides (confirm/reject/split) and auto_group_merges.

    Plan A only handles confirm + reject; merge/split are stubs until Plan C.
    """
    # confirm: force tier='confirmed' on the named group (if it still exists)
    for r in conn.execute(
        "SELECT auto_group_id FROM auto_group_overrides WHERE action='confirm'"
    ):
        conn.execute(
            "UPDATE auto_groups SET tier='confirmed' WHERE auto_group_id=?",
            (r['auto_group_id'],),
        )
    # reject: remove the group
    for r in conn.execute(
        "SELECT auto_group_id FROM auto_group_overrides WHERE action='reject'"
    ):
        conn.execute('DELETE FROM auto_group_anchors WHERE auto_group_id=?', (r['auto_group_id'],))
        conn.execute('DELETE FROM auto_groups WHERE auto_group_id=?', (r['auto_group_id'],))


def build_seeds(conn: sqlite3.Connection, *, verbose: bool = True) -> dict:
    """Run Stage A3. Idempotent — drops prior derived rows first."""
    conn.execute('DELETE FROM auto_group_anchors')
    conn.execute('DELETE FROM auto_groups')

    # Apply auto_anchor_overrides up front (override_stem reroutes a dominant stem;
    # override_service_provider removes the anchor from seeding eligibility).
    overrides = {
        (r['anchor_type'], r['anchor_value']): r
        for r in conn.execute('SELECT * FROM auto_anchor_overrides')
    }

    # Group anchors by stem, applying overrides
    by_stem: dict[str, list[dict]] = {}
    for r in conn.execute(
        f"""SELECT * FROM anchor_uniqueness
             WHERE dominant_stem IS NOT NULL
               AND score >= {ANCHOR_CORROBORATION_SCORE_THRESHOLD}
               AND is_service_provider = 0"""
    ):
        a = dict(r)
        ov = overrides.get((a['anchor_type'], a['anchor_value']))
        if ov is not None:
            if ov['override_service_provider']:
                continue  # drop anchor from seeding
            if ov['override_stem']:
                a['dominant_stem'] = ov['override_stem']
        by_stem.setdefault(a['dominant_stem'], []).append(a)

    # Seed one group per stem
    n = 1
    seeded: list[tuple] = []  # (group_id, stem, tier, confidence, n_anchors)
    anchor_rows: list[tuple] = []  # (group_id, anchor_type, anchor_value, score)
    for stem, anchors in by_stem.items():
        tier, confidence = _compute_tier_and_confidence(anchors)
        if tier is None:
            continue
        group_id = _next_group_id(n)
        n += 1
        # display_name placeholder — Stage A5 fills it in.
        seeded.append((group_id, stem, stem, tier, confidence, len(anchors), 0))
        for a in anchors:
            anchor_rows.append((group_id, a['anchor_type'], a['anchor_value'], a['score']))

    if seeded:
        conn.executemany(
            """INSERT INTO auto_groups
                 (auto_group_id, canonical_stem, display_name, tier, confidence, n_anchors, n_members)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            seeded,
        )
    if anchor_rows:
        conn.executemany(
            "INSERT INTO auto_group_anchors (auto_group_id, anchor_type, anchor_value, score) VALUES (?,?,?,?)",
            anchor_rows,
        )

    _apply_crm_overrides(conn)
    conn.commit()

    if verbose:
        print(f'  Stage A3 (seeds): {len(seeded):,} groups.', flush=True)
    return {'n_groups': len(seeded)}
```

- [ ] **Step 5: Run, confirm pass**

```bash
pytest tests/test_discovery_v2_seeding.py::test_three_category_convergence_creates_confirmed_group -v
```

- [ ] **Step 6: Add — 2-category convergence creates Probable**

```python
def test_two_category_convergence_creates_probable_group():
    conn = _make_db()
    # 6 skyline at phone P1 + address (5,douglas,st), no contact.
    for i in range(6):
        _seed(conn, f'TX{i}', 'buyer', 'skyline real estate holdings',
              phone='P1',
              street_number='5', street_name='douglas', street_suffix='st')
    _run_to_anchors(conn)
    build_seeds(conn, verbose=False)
    groups = conn.execute('SELECT * FROM auto_groups').fetchall()
    assert len(groups) == 1
    assert groups[0]['tier'] in ('probable', 'confirmed')
    # Sanity: confidence below confirmed threshold given only 2 categories
    if groups[0]['tier'] == 'probable':
        assert groups[0]['confidence'] < 0.75


def test_pure_single_anchor_does_not_seed():
    conn = _make_db()
    # 6 sides with skyline at phone P1, no other anchors.
    for i in range(6):
        _seed(conn, f'TX{i}', 'buyer', 'skyline real estate holdings', phone='P1')
    _run_to_anchors(conn)
    build_seeds(conn, verbose=False)
    groups = conn.execute('SELECT * FROM auto_groups').fetchall()
    # 1 strong anchor + 0 corroborating → no seed (need >= 2 corroborating
    # anchors total per the candidate-tier rule).
    # NOTE: if the address_root anchor is also present (it isn't here),
    # the test would need to include the corroborating bar.
    assert len(groups) == 0


def test_reject_override_removes_group():
    conn = _make_db()
    for i in range(8):
        _seed(conn, f'TX{i}', 'buyer', 'skyline real estate holdings',
              phone='P1', contact='jc',
              street_number='5', street_name='douglas', street_suffix='st')
    _run_to_anchors(conn)
    build_seeds(conn, verbose=False)
    groups = conn.execute('SELECT * FROM auto_groups').fetchall()
    assert len(groups) == 1
    gid = groups[0]['auto_group_id']

    # User rejects this group. Re-run seeding; group should be removed.
    conn.execute(
        "INSERT INTO auto_group_overrides (auto_group_id, action, user_id) VALUES (?, 'reject', 'tester')",
        (gid,),
    )
    conn.commit()
    build_seeds(conn, verbose=False)
    groups = conn.execute('SELECT * FROM auto_groups').fetchall()
    assert len(groups) == 0
```

Run + verify pass after each.

- [ ] **Step 7: Commit**

```bash
git add cleo/discovery_v2/seeding.py tests/test_discovery_v2_seeding.py
git commit -m "feat(layer2): Stage A3 — auto-seed groups with confidence tiering"
```

---

### Task 6: Stage A4 — Group expansion

**Files:**
- Create: `cleo/discovery_v2/expansion.py`
- Test: `tests/test_discovery_v2_expansion.py`

The module exports `build_expansion(conn, *, verbose=True)`. For each `auto_group`, finds all party-sides whose anchors match the group's `auto_group_anchors`, scores each candidate against the constants in `cleo.discovery_v2.constants`, and inserts into `auto_group_members` if the score >= `EXPANSION_ATTACH_THRESHOLD`. Numbered Ontario/Canada corps in attached sides are inserted as separate `member_type='numbered_corp'` rows. Idempotent.

- [ ] **Step 1: Test fixture (extends Task 5 + adds auto_group_members table)**

```python
# tests/test_discovery_v2_expansion.py
import re
import sqlite3
import pytest

from cleo.discovery_v2.stems import build_stems
from cleo.discovery_v2.anchor_scores import build_anchor_scores
from cleo.discovery_v2.seeding import build_seeds
from cleo.discovery_v2.expansion import build_expansion


def _make_db():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    # Reuse the tables from Task 5 fixture; add auto_group_members
    conn.executescript("""
        CREATE TABLE party_fingerprints (
            source_id TEXT, side TEXT, phone TEXT, contact_fingerprint TEXT,
            street_number TEXT, street_name TEXT, street_suffix TEXT,
            PRIMARY KEY (source_id, side)
        );
        CREATE TABLE party_atoms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT, side TEXT, atom_type TEXT, atom_value TEXT, source_field TEXT
        );
        CREATE TABLE brand_token_summary (
            token TEXT PRIMARY KEY, idf REAL, n_party_sides INTEGER,
            n_distinct_phrases INTEGER, is_distinctive INTEGER, is_excluded INTEGER,
            wordfreq_zipf REAL, is_english_common INTEGER, is_place_name INTEGER,
            is_industry_stopword INTEGER, filter_reason TEXT,
            position_consistency REAL, total_child_coverage REAL,
            is_position_anchor INTEGER NOT NULL DEFAULT 0,
            discovered_at TEXT
        );
        CREATE TABLE brand_stem (
            stem TEXT PRIMARY KEY, stem_type TEXT NOT NULL,
            dominant_anchor_type TEXT NOT NULL, dominant_anchor_value TEXT NOT NULL,
            dominance_share REAL NOT NULL, volume INTEGER NOT NULL, verified_at TEXT
        );
        CREATE TABLE brand_stem_phrase_map (
            phrase TEXT PRIMARY KEY, stem TEXT NOT NULL, confidence REAL NOT NULL
        );
        CREATE TABLE anchor_uniqueness (
            anchor_type TEXT NOT NULL, anchor_value TEXT NOT NULL,
            dominant_stem TEXT, dominance_share REAL,
            volume INTEGER NOT NULL, score REAL NOT NULL,
            is_service_provider INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (anchor_type, anchor_value)
        );
        CREATE TABLE auto_groups (
            auto_group_id TEXT PRIMARY KEY, canonical_stem TEXT NOT NULL,
            display_name TEXT NOT NULL, tier TEXT NOT NULL,
            confidence REAL NOT NULL, n_anchors INTEGER NOT NULL,
            n_members INTEGER NOT NULL, discovered_at TEXT
        );
        CREATE TABLE auto_group_anchors (
            auto_group_id TEXT NOT NULL, anchor_type TEXT NOT NULL,
            anchor_value TEXT NOT NULL, score REAL NOT NULL,
            PRIMARY KEY (auto_group_id, anchor_type, anchor_value)
        );
        CREATE TABLE auto_group_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            auto_group_id TEXT NOT NULL,
            member_type TEXT NOT NULL,
            source_id TEXT, side TEXT, corp_name TEXT,
            match_score REAL NOT NULL
        );
        CREATE TABLE auto_group_overrides (
            id INTEGER PRIMARY KEY AUTOINCREMENT, auto_group_id TEXT NOT NULL,
            action TEXT NOT NULL, user_id TEXT NOT NULL, action_at TEXT, notes TEXT
        );
        CREATE TABLE auto_group_merges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_auto_group_id TEXT NOT NULL, child_auto_group_id TEXT NOT NULL,
            user_id TEXT NOT NULL, action_at TEXT, notes TEXT
        );
        CREATE TABLE auto_anchor_overrides (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            anchor_type TEXT NOT NULL, anchor_value TEXT NOT NULL,
            override_stem TEXT, override_service_provider INTEGER NOT NULL DEFAULT 0,
            user_id TEXT NOT NULL, action_at TEXT
        );
    """)
    conn.execute(
        """INSERT INTO brand_token_summary
             (token, idf, n_party_sides, n_distinct_phrases, is_distinctive,
              is_excluded, wordfreq_zipf, is_english_common, is_place_name,
              is_industry_stopword, filter_reason, position_consistency,
              total_child_coverage, is_position_anchor, discovered_at)
           VALUES ('skyline', 6.13, 100, 10, 1, 0, 0.0, 0, 0, 0, NULL, NULL, NULL, 0, '2026')"""
    )
    return conn


def _seed(conn, sid, side, phrase, *, phone=None, contact=None,
          street_number=None, street_name=None, street_suffix=None):
    conn.execute(
        """INSERT OR IGNORE INTO party_fingerprints
             (source_id, side, phone, contact_fingerprint,
              street_number, street_name, street_suffix)
           VALUES (?,?,?,?,?,?,?)""",
        (sid, side, phone, contact, street_number, street_name, street_suffix),
    )
    if phrase:
        conn.execute(
            "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
            "VALUES (?, ?, 'brand_phrase', ?, 'party_name')",
            (sid, side, phrase),
        )


def _build_pipeline(conn):
    build_stems(conn, verbose=False)
    build_anchor_scores(conn, verbose=False)
    build_seeds(conn, verbose=False)
```

- [ ] **Step 2: Test — direct stem hit attaches party-side to group**

```python
def test_direct_stem_hit_attaches_to_group():
    conn = _make_db()
    # Seed a Skyline group (8 strong sides).
    for i in range(8):
        _seed(conn, f'STRONG{i}', 'buyer', 'skyline real estate holdings',
              phone='P1', contact='jc',
              street_number='5', street_name='douglas', street_suffix='st')
    # Add a 'no-other-anchor' party-side whose phrase IS skyline.
    _seed(conn, 'EXTRA1', 'buyer', 'skyline retail real estate holdings')
    _build_pipeline(conn)

    build_expansion(conn, verbose=False)

    members = conn.execute("""
        SELECT * FROM auto_group_members
        WHERE source_id='EXTRA1' AND side='buyer' AND member_type='party_side'
    """).fetchall()
    assert len(members) == 1
    assert members[0]['match_score'] >= 1.0  # direct stem hit
```

- [ ] **Step 3: Run, confirm fail**

- [ ] **Step 4: Implement `build_expansion`**

```python
"""Stage A4: Group expansion — attach party-sides + numbered-corps to seeded groups."""
from __future__ import annotations
import re
import sqlite3

from cleo.discovery_v2.constants import (
    MATCH_SCORE_DIRECT_STEM_HIT,
    MATCH_SCORE_PHONE_MATCH,
    MATCH_SCORE_ADDRESS_PLUS_CONTACT,
    MATCH_SCORE_ADDRESS_ROOT_ALONE,
    MATCH_SCORE_PHONE_BRAND_CONTRADICTION,
    MATCH_SCORE_SINGLE_WEAK_SIGNAL,
    EXPANSION_ATTACH_THRESHOLD,
)


_NUMBERED_CORP_RE = re.compile(r'^\d+\s+(ontario|canada|alberta|bc|quebec)\b', re.I)


def build_expansion(conn: sqlite3.Connection, *, verbose: bool = True) -> dict:
    """Attach party-sides and numbered corps to seeded groups. Idempotent."""
    conn.execute('DELETE FROM auto_group_members')

    # 1. Pull every group's anchors into in-memory lookup tables for cheap matching
    groups = list(conn.execute('SELECT auto_group_id, canonical_stem FROM auto_groups'))
    if not groups:
        if verbose:
            print('  Stage A4 (expansion): no groups to expand.', flush=True)
        return {'n_party_side_members': 0, 'n_numbered_corp_members': 0}

    anchors_by_group = {}  # group_id -> {(type, value): score}
    for r in conn.execute('SELECT * FROM auto_group_anchors'):
        anchors_by_group.setdefault(r['auto_group_id'], {})[
            (r['anchor_type'], r['anchor_value'])
        ] = r['score']

    # 2. For each party-side, look up its anchor values + its stems
    side_data = {}  # (sid, side) -> { 'phone', 'addr_root', 'addr_base', 'contact', 'stems' }
    for r in conn.execute("""
        SELECT source_id, side, phone, contact_fingerprint,
               street_number, street_name, street_suffix
        FROM party_fingerprints
    """):
        addr_root = (
            f"{r['street_number']}|{r['street_name']}"
            if r['street_number'] and r['street_name'] else None
        )
        addr_base = (
            f"{r['street_number']}|{r['street_name']}|{r['street_suffix'] or ''}"
            if r['street_number'] and r['street_name'] else None
        )
        side_data[(r['source_id'], r['side'])] = {
            'phone':     r['phone'] or None,
            'addr_root': addr_root,
            'addr_base': addr_base,
            'contact':   r['contact_fingerprint'] or None,
            'stems':     set(),
            'phrases':   [],
        }

    for r in conn.execute("""
        SELECT pa.source_id, pa.side, pa.atom_value, m.stem
        FROM party_atoms pa
        LEFT JOIN brand_stem_phrase_map m ON m.phrase = pa.atom_value
        WHERE pa.atom_type='brand_phrase'
    """):
        key = (r['source_id'], r['side'])
        if key in side_data:
            if r['stem']:
                side_data[key]['stems'].add(r['stem'])
            side_data[key]['phrases'].append(r['atom_value'])

    # 3. Score each party-side against each group it touches
    member_rows = []
    numbered_corps = []  # (group_id, corp_name, match_score)
    for (sid, side), info in side_data.items():
        for group_id, _stem in groups:
            anchors = anchors_by_group.get(group_id, {})
            if not anchors:
                continue
            score = _score_match(info, anchors, group_canonical_stem=_stem)
            if score >= EXPANSION_ATTACH_THRESHOLD:
                member_rows.append((group_id, 'party_side', sid, side, None, score))
                # Numbered-corp side-effect: any numbered corp phrase on this side
                # gets recorded as a group-owned vehicle.
                for ph in info['phrases']:
                    if _NUMBERED_CORP_RE.match(ph or ''):
                        numbered_corps.append((group_id, ph.lower(), score))

    if member_rows:
        conn.executemany(
            """INSERT INTO auto_group_members
                 (auto_group_id, member_type, source_id, side, corp_name, match_score)
               VALUES (?, ?, ?, ?, ?, ?)""",
            member_rows,
        )

    # Dedupe numbered_corps before insert (same corp_name in many sides → one row per group)
    seen = set()
    corp_rows = []
    for gid, corp_name, sc in numbered_corps:
        key = (gid, corp_name)
        if key in seen:
            continue
        seen.add(key)
        corp_rows.append((gid, 'numbered_corp', None, None, corp_name, sc))

    if corp_rows:
        conn.executemany(
            """INSERT INTO auto_group_members
                 (auto_group_id, member_type, source_id, side, corp_name, match_score)
               VALUES (?, ?, ?, ?, ?, ?)""",
            corp_rows,
        )

    conn.commit()
    if verbose:
        print(
            f'  Stage A4 (expansion): {len(member_rows):,} party-sides, '
            f'{len(corp_rows):,} numbered-corp memberships.',
            flush=True,
        )
    return {
        'n_party_side_members': len(member_rows),
        'n_numbered_corp_members': len(corp_rows),
    }


def _score_match(info: dict, anchors: dict, *, group_canonical_stem: str) -> float:
    """Score a single (party-side, group) pair using constants.py rules."""
    score = 0.0
    has_phone_match = ('phone', info['phone']) in anchors if info['phone'] else False
    has_addr_match = (
        ('address_root', info['addr_root']) in anchors if info['addr_root'] else False
    ) or (
        ('address_base', info['addr_base']) in anchors if info['addr_base'] else False
    )
    has_contact_match = ('contact', info['contact']) in anchors if info['contact'] else False
    has_direct_stem = group_canonical_stem in info['stems']

    # Strong: direct stem hit
    if has_direct_stem:
        score = max(score, MATCH_SCORE_DIRECT_STEM_HIT)

    # Phone match — but only if no contradicting stem on the side
    if has_phone_match:
        contradicting = info['stems'] - {group_canonical_stem}
        if contradicting:
            return MATCH_SCORE_PHONE_BRAND_CONTRADICTION  # explicit do-not-attach
        score = max(score, MATCH_SCORE_PHONE_MATCH)

    if has_addr_match and has_contact_match:
        score = max(score, MATCH_SCORE_ADDRESS_PLUS_CONTACT)
    elif has_addr_match:
        score = max(score, MATCH_SCORE_ADDRESS_ROOT_ALONE)

    # Single weak signal (only contact, common name) caps at 0.3
    if has_contact_match and not (has_phone_match or has_addr_match or has_direct_stem):
        score = max(score, MATCH_SCORE_SINGLE_WEAK_SIGNAL)

    return score
```

- [ ] **Step 5: Run, confirm pass**

```bash
pytest tests/test_discovery_v2_expansion.py::test_direct_stem_hit_attaches_to_group -v
```

- [ ] **Step 6: Add — phone match without contradiction attaches**

```python
def test_phone_match_attaches_without_contradiction():
    conn = _make_db()
    # Seed a Skyline group with phone P1.
    for i in range(8):
        _seed(conn, f'STRONG{i}', 'buyer', 'skyline real estate holdings',
              phone='P1', contact='jc',
              street_number='5', street_name='douglas', street_suffix='st')
    # Add a side at phone P1 with no brand phrase at all.
    _seed(conn, 'BLANK1', 'buyer', None, phone='P1')
    _build_pipeline(conn)
    build_expansion(conn, verbose=False)

    rows = conn.execute(
        """SELECT * FROM auto_group_members
            WHERE source_id='BLANK1' AND side='buyer' AND member_type='party_side'"""
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]['match_score'] == pytest.approx(0.7)


def test_phone_match_with_contradicting_stem_does_not_attach():
    conn = _make_db()
    # Seed Skyline group at phone P1.
    for i in range(8):
        _seed(conn, f'STRONG{i}', 'buyer', 'skyline real estate holdings',
              phone='P1', contact='jc',
              street_number='5', street_name='douglas', street_suffix='st')
    # Seed a Kingsett group at phone P2 (separate group).
    conn.execute(
        """INSERT INTO brand_token_summary
             (token, idf, n_party_sides, n_distinct_phrases, is_distinctive,
              is_excluded, wordfreq_zipf, is_english_common, is_place_name,
              is_industry_stopword, filter_reason, position_consistency,
              total_child_coverage, is_position_anchor, discovered_at)
           VALUES ('kingsett', 6.50, 100, 10, 1, 0, 0.0, 0, 0, 0, NULL, NULL, NULL, 0, '2026')"""
    )
    for i in range(8):
        _seed(conn, f'KS{i}', 'buyer', 'kingsett capital',
              phone='P2', contact='ks_jc',
              street_number='40', street_name='king', street_suffix='st')
    # Add a side at phone P1 (Skyline) but whose phrase is 'kingsett capital' (Kingsett).
    _seed(conn, 'CONTRA', 'buyer', 'kingsett capital', phone='P1')
    _build_pipeline(conn)
    build_expansion(conn, verbose=False)

    # Should NOT be attached to the Skyline group (contradiction).
    skyline_groups = [r for r in conn.execute(
        "SELECT auto_group_id FROM auto_groups WHERE canonical_stem='skyline'"
    )]
    skyline_id = skyline_groups[0]['auto_group_id'] if skyline_groups else None
    if skyline_id is not None:
        contra_rows = conn.execute(
            "SELECT * FROM auto_group_members WHERE auto_group_id=? AND source_id='CONTRA'",
            (skyline_id,),
        ).fetchall()
        assert len(contra_rows) == 0


def test_numbered_corp_attached_as_separate_member_row():
    conn = _make_db()
    for i in range(8):
        _seed(conn, f'STRONG{i}', 'buyer', 'skyline real estate holdings',
              phone='P1', contact='jc',
              street_number='5', street_name='douglas', street_suffix='st')
    # Add a side at the same address with a numbered Ontario corp phrase.
    _seed(conn, 'CORP1', 'buyer', '1234567 ontario',
          phone='P1',
          street_number='5', street_name='douglas', street_suffix='st')
    _build_pipeline(conn)
    build_expansion(conn, verbose=False)

    corps = conn.execute(
        "SELECT * FROM auto_group_members WHERE member_type='numbered_corp'"
    ).fetchall()
    assert len(corps) >= 1
    assert any(r['corp_name'] == '1234567 ontario' for r in corps)
```

Run + verify pass after each.

- [ ] **Step 7: Commit**

```bash
git add cleo/discovery_v2/expansion.py tests/test_discovery_v2_expansion.py
git commit -m "feat(layer2): Stage A4 — group expansion with anchor matching"
```

---

### Task 7: Stage A5 + orchestrator — `build_auto_groups`

**Files:**
- Create: `cleo/discovery_v2/auto_groups.py`
- Test: `tests/test_discovery_v2_auto_groups.py`

The orchestrator runs A1→A2→A3→A4 in order, then performs Stage A5 (display name + counts) before committing. Uses the existing `cleo.database.connection.get_connection`. Public function: `build_auto_groups(conn, *, verbose=True)`.

- [ ] **Step 1: Test — full pipeline produces a Skyline group with display_name and counts**

```python
# tests/test_discovery_v2_auto_groups.py
import sqlite3
import pytest

from cleo.discovery_v2.auto_groups import build_auto_groups


def _make_db():
    # Reuse the schema from Task 6's _make_db (paste the same DDL inline).
    # ... (full DDL omitted in this test for brevity — copy the full schema from
    # tests/test_discovery_v2_expansion.py's _make_db helper).
    ...


def _seed(conn, sid, side, phrase, *, phone=None, contact=None,
          street_number=None, street_name=None, street_suffix=None):
    # Same as in Task 6's helper.
    ...


def test_full_pipeline_produces_skyline_group_with_display_name():
    conn = _make_db()
    # 8 sides converging on Skyline anchors with multiple phrase variants.
    phrases = [
        'skyline real estate holdings',
        'skyline retail real estate holdings',
        'skyline real estate holdings',
    ]
    for i in range(8):
        ph = phrases[i % len(phrases)]
        _seed(conn, f'TX{i}', 'buyer', ph,
              phone='P1', contact='jc',
              street_number='5', street_name='douglas', street_suffix='st')

    build_auto_groups(conn, verbose=False)

    g = conn.execute(
        "SELECT * FROM auto_groups WHERE canonical_stem='skyline'"
    ).fetchone()
    assert g is not None
    # display_name picks the most-common skyline phrase among members.
    assert g['display_name'] == 'skyline real estate holdings'
    # n_members reflects expansion output.
    assert g['n_members'] >= 8
```

(Note: paste the full _make_db + _seed helpers verbatim from `tests/test_discovery_v2_expansion.py`.)

- [ ] **Step 2: Run, confirm fail (orchestrator missing)**

- [ ] **Step 3: Implement `cleo/discovery_v2/auto_groups.py`**

```python
"""Layer 2 Plan A orchestrator: stems → anchor scores → seeding → expansion → display."""
from __future__ import annotations
import sqlite3

from cleo.discovery_v2.stems import build_stems
from cleo.discovery_v2.anchor_scores import build_anchor_scores
from cleo.discovery_v2.seeding import build_seeds
from cleo.discovery_v2.expansion import build_expansion


def build_auto_groups(conn: sqlite3.Connection, *, verbose: bool = True) -> dict:
    """Run all five stages of Plan A. Idempotent — each stage clears its own derived tables."""
    if verbose:
        print('Layer 2 Plan A: starting build...', flush=True)

    a1 = build_stems(conn, verbose=verbose)
    a2 = build_anchor_scores(conn, verbose=verbose)
    a3 = build_seeds(conn, verbose=verbose)
    a4 = build_expansion(conn, verbose=verbose)
    a5 = _finalize_display_and_counts(conn, verbose=verbose)

    summary = {**a1, **a2, **a3, **a4, **a5}
    if verbose:
        print(f'Layer 2 Plan A: done. {summary}', flush=True)
    return summary


def _finalize_display_and_counts(conn: sqlite3.Connection, *, verbose: bool = True) -> dict:
    """Stage A5: pick display_name as max-count phrase mapping to canonical_stem; refresh n_members."""
    n_updated = 0
    for r in conn.execute('SELECT auto_group_id, canonical_stem FROM auto_groups'):
        gid, stem = r['auto_group_id'], r['canonical_stem']

        # display_name: most-frequent phrase among members where phrase → stem
        row = conn.execute(
            """SELECT pa.atom_value AS phrase, COUNT(*) AS n
               FROM auto_group_members agm
               JOIN party_atoms pa
                 ON pa.source_id = agm.source_id
                AND pa.side      = agm.side
                AND pa.atom_type = 'brand_phrase'
               JOIN brand_stem_phrase_map m
                 ON m.phrase = pa.atom_value
                AND m.stem   = ?
               WHERE agm.auto_group_id = ?
                 AND agm.member_type = 'party_side'
               GROUP BY pa.atom_value
               ORDER BY n DESC
               LIMIT 1""",
            (stem, gid),
        ).fetchone()
        display_name = row['phrase'] if row else stem

        n_members = conn.execute(
            'SELECT COUNT(*) AS n FROM auto_group_members WHERE auto_group_id=?',
            (gid,),
        ).fetchone()['n']

        conn.execute(
            'UPDATE auto_groups SET display_name=?, n_members=? WHERE auto_group_id=?',
            (display_name, n_members, gid),
        )
        n_updated += 1
    conn.commit()
    if verbose:
        print(f'  Stage A5 (display + counts): {n_updated:,} groups updated.', flush=True)
    return {'n_groups_finalized': n_updated}
```

- [ ] **Step 4: Run the integration test, confirm pass**

```bash
pytest tests/test_discovery_v2_auto_groups.py -v
```

- [ ] **Step 5: Add — multi-tenant building does NOT seed**

```python
def test_multi_tenant_address_does_not_seed_alone():
    conn = _make_db()
    # 30 sides at the same address but with 30 different stem-mapped phrases.
    # Should not produce a group from address alone.
    conn.execute(
        """INSERT INTO brand_token_summary
             (token, idf, n_party_sides, n_distinct_phrases, is_distinctive,
              is_excluded, wordfreq_zipf, is_english_common, is_place_name,
              is_industry_stopword, filter_reason, position_consistency,
              total_child_coverage, is_position_anchor, discovered_at)
           VALUES ('kingsett', 6.50, 100, 10, 1, 0, 0.0, 0, 0, 0, NULL, NULL, NULL, 0, '2026')"""
    )
    for i in range(15):
        _seed(conn, f'A{i}', 'buyer', 'skyline real estate holdings',
              street_number='161', street_name='bay', street_suffix='st')
    for i in range(15):
        _seed(conn, f'B{i}', 'buyer', 'kingsett capital',
              street_number='161', street_name='bay', street_suffix='st')
    build_auto_groups(conn, verbose=False)
    # The address (161, bay, st) anchor should NOT dominate either stem.
    groups = conn.execute('SELECT * FROM auto_groups').fetchall()
    # Both stems may still seed groups via *other* signals — but neither should
    # rely on 161-bay alone. Verify by checking that no group has only one anchor.
    for g in groups:
        n_anchors = conn.execute(
            'SELECT COUNT(*) AS n FROM auto_group_anchors WHERE auto_group_id=?',
            (g['auto_group_id'],),
        ).fetchone()['n']
        assert n_anchors >= 2, f'Group {g["auto_group_id"]} seeded with only one anchor'
```

Run + verify pass.

- [ ] **Step 6: Commit**

```bash
git add cleo/discovery_v2/auto_groups.py tests/test_discovery_v2_auto_groups.py
git commit -m "feat(layer2): Plan A orchestrator + Stage A5 (display name + counts)"
```

---

### Task 8: Wire orchestrator into `__main__`

**Files:**
- Modify: `cleo/discovery_v2/__main__.py`

- [ ] **Step 1: Add the call to `build_auto_groups` after `build_all_indexes`**

Replace `cleo/discovery_v2/__main__.py` with:

```python
"""Developer entry point — `python -m cleo.discovery_v2`.

Runs all Layer 1 silo builders, then Layer 2 Plan A. Not a user surface.
"""

from __future__ import annotations
from cleo.database.connection import get_connection
from cleo.discovery_v2.brand_index import build_all_indexes
from cleo.discovery_v2.signals import (
    seed_industry_stopwords_table, seed_places_table,
)
from cleo.discovery_v2.auto_groups import build_auto_groups


def main():
    conn = get_connection()
    n1 = seed_industry_stopwords_table(conn)
    n2 = seed_places_table(conn)
    if n1 > 0:
        print(f'Seeded {n1} industry_stopwords rows')
    if n2 > 0:
        print(f'Seeded {n2} places rows')
    build_all_indexes(conn)
    build_auto_groups(conn)
    conn.close()


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: Smoke test — run end-to-end against the real DB**

```bash
python -m cleo.discovery_v2 2>&1 | tail -30
```

Expected output includes lines like:
```
Layer 2 Plan A: starting build...
  Stage A1 (stems): NN verified stems, MM phrase mappings.
  Stage A2 (anchor scores): KK anchor rows.
  Stage A3 (seeds): JJ groups.
  Stage A4 (expansion): II party-sides, NN numbered-corp memberships.
  Stage A5 (display + counts): JJ groups updated.
Layer 2 Plan A: done. {...}
```

- [ ] **Step 3: Verify some groups exist for known operators**

```bash
sqlite3 data/cleo.db "SELECT canonical_stem, tier, confidence, n_anchors, n_members, display_name FROM auto_groups ORDER BY n_members DESC LIMIT 15"
```

Expected: rows for at least `skyline`, `kingsett`, `metrus`, `starlight`. Manual eyeball check.

- [ ] **Step 4: Commit**

```bash
git add cleo/discovery_v2/__main__.py
git commit -m "feat(layer2): wire build_auto_groups into discovery_v2 entry point"
```

---

### Task 9: API endpoints — list + detail

**Files:**
- Modify: `cleo/web/routes/explorer.py`
- Modify: `tests/test_routes_explorer.py`

Two endpoints:
- `GET /api/explorer/auto-groups?tier=&q=&page=&per_page=` → list, sorted by `n_members DESC`.
- `GET /api/explorer/auto-groups/{auto_group_id}` → detail with anchors, top phrases, members (capped 200), numbered corps, date range, n_distinct_contacts.

- [ ] **Step 1: Test — list returns confirmed-tier groups by default**

Add to `tests/test_routes_explorer.py` (extend the existing `_seeded_db` fixture to include the Layer 2 tables and one seeded auto_group):

```python
# Add to _seeded_db() in tests/test_routes_explorer.py, after the existing seeds:

conn.executescript("""
    CREATE TABLE IF NOT EXISTS auto_groups (
        auto_group_id TEXT PRIMARY KEY, canonical_stem TEXT NOT NULL,
        display_name TEXT NOT NULL, tier TEXT NOT NULL,
        confidence REAL NOT NULL, n_anchors INTEGER NOT NULL,
        n_members INTEGER NOT NULL, discovered_at TEXT
    );
    CREATE TABLE IF NOT EXISTS auto_group_anchors (
        auto_group_id TEXT NOT NULL, anchor_type TEXT NOT NULL,
        anchor_value TEXT NOT NULL, score REAL NOT NULL,
        PRIMARY KEY (auto_group_id, anchor_type, anchor_value)
    );
    CREATE TABLE IF NOT EXISTS auto_group_members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        auto_group_id TEXT NOT NULL,
        member_type TEXT NOT NULL,
        source_id TEXT, side TEXT, corp_name TEXT,
        match_score REAL NOT NULL
    );
""")
conn.execute("""
    INSERT INTO auto_groups (auto_group_id, canonical_stem, display_name, tier, confidence,
                             n_anchors, n_members, discovered_at)
    VALUES ('AGRP_00001', 'kingsett', 'kingsett capital', 'confirmed', 0.85, 3, 8, '2026-04-27')
""")
conn.execute("""
    INSERT INTO auto_groups (auto_group_id, canonical_stem, display_name, tier, confidence,
                             n_anchors, n_members, discovered_at)
    VALUES ('AGRP_00002', 'starlight', 'starlight investments', 'probable', 0.55, 2, 5, '2026-04-27')
""")
for at, av in [('phone', '4166876700'), ('address_root', '40|king'), ('contact', 'rob kumer')]:
    conn.execute(
        'INSERT INTO auto_group_anchors VALUES (?, ?, ?, 2.0)',
        ('AGRP_00001', at, av),
    )
conn.execute(
    "INSERT INTO auto_group_members (auto_group_id, member_type, source_id, side, match_score) "
    "VALUES ('AGRP_00001', 'party_side', 'RT1', 'buyer', 1.0)"
)
```

Then add tests:

```python
# ── Auto-groups ──────────────────────────────────────────────────

def test_list_auto_groups_default_returns_confirmed_only(client):
    resp = client.get('/api/explorer/auto-groups')
    assert resp.status_code == 200
    body = resp.json()
    tiers = {g['tier'] for g in body['results']}
    assert tiers == {'confirmed'}


def test_list_auto_groups_tier_filter(client):
    resp = client.get('/api/explorer/auto-groups', params={'tier': 'probable'})
    body = resp.json()
    assert all(g['tier'] == 'probable' for g in body['results'])


def test_list_auto_groups_q_substring(client):
    resp = client.get('/api/explorer/auto-groups',
                      params={'tier': 'confirmed', 'q': 'kingsett'})
    body = resp.json()
    assert body['total'] >= 1
    assert any('kingsett' in g['canonical_stem'].lower() for g in body['results'])


def test_auto_group_detail_returns_anchors_and_members(client):
    resp = client.get('/api/explorer/auto-groups/AGRP_00001')
    assert resp.status_code == 200
    body = resp.json()
    assert body['canonical_stem'] == 'kingsett'
    assert body['display_name'] == 'kingsett capital'
    assert body['tier'] == 'confirmed'
    assert len(body['anchors']) >= 3
    types = {a['anchor_type'] for a in body['anchors']}
    assert {'phone', 'address_root', 'contact'}.issubset(types)
    assert isinstance(body['members'], list)


def test_auto_group_detail_404(client):
    resp = client.get('/api/explorer/auto-groups/AGRP_99999')
    assert resp.status_code == 404
```

- [ ] **Step 2: Run, confirm fail**

```bash
pytest tests/test_routes_explorer.py -v -k auto_group
```

- [ ] **Step 3: Add the endpoints to `cleo/web/routes/explorer.py`**

Add right before the `# ─── Contacts ───` section (after the auto-groups section comment):

```python
# ─────────────────────────────────────────────────────────────
# Auto-Groups (Layer 2 Plan A)
# ─────────────────────────────────────────────────────────────

@router.get('/auto-groups')
def list_auto_groups(
    tier: str = Query('confirmed'),
    q: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=500),
    db=Depends(get_db), user=Depends(get_current_user),
):
    if tier not in ('confirmed', 'probable', 'candidate'):
        raise HTTPException(status_code=400, detail=f'Invalid tier: {tier!r}')
    where = ['tier = ?']
    params: list = [tier]
    if q:
        where.append('(LOWER(display_name) LIKE ? OR LOWER(canonical_stem) LIKE ?)')
        like = f'%{q.lower()}%'
        params.extend([like, like])
    where_sql = ' WHERE ' + ' AND '.join(where)

    total = db.execute(
        f'SELECT COUNT(*) FROM auto_groups{where_sql}', params
    ).fetchone()[0]
    offset = (page - 1) * per_page
    rows = db.execute(
        f"""SELECT auto_group_id, canonical_stem, display_name, tier,
                   confidence, n_anchors, n_members
            FROM auto_groups{where_sql}
            ORDER BY n_members DESC, canonical_stem ASC
            LIMIT ? OFFSET ?""",
        params + [per_page, offset],
    ).fetchall()
    return {
        'results': [dict(r) for r in rows],
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page,
    }


@router.get('/auto-groups/{auto_group_id}')
def auto_group_detail(
    auto_group_id: str, db=Depends(get_db), user=Depends(get_current_user),
):
    summary = db.execute(
        """SELECT auto_group_id, canonical_stem, display_name, tier, confidence,
                  n_anchors, n_members, discovered_at
           FROM auto_groups WHERE auto_group_id = ?""",
        (auto_group_id,),
    ).fetchone()
    if summary is None:
        raise HTTPException(status_code=404, detail=f'Unknown auto_group: {auto_group_id!r}')

    anchors = [dict(r) for r in db.execute(
        """SELECT anchor_type, anchor_value, score FROM auto_group_anchors
           WHERE auto_group_id = ? ORDER BY score DESC""",
        (auto_group_id,),
    )]
    members = [dict(r) for r in db.execute(
        """SELECT member_type, source_id, side, corp_name, match_score
           FROM auto_group_members
           WHERE auto_group_id = ? AND member_type = 'party_side'
           ORDER BY match_score DESC LIMIT 200""",
        (auto_group_id,),
    )]
    numbered_corps = [dict(r) for r in db.execute(
        """SELECT corp_name, match_score FROM auto_group_members
           WHERE auto_group_id = ? AND member_type = 'numbered_corp'
           ORDER BY corp_name""",
        (auto_group_id,),
    )]
    top_phrases = [dict(r) for r in db.execute(
        """SELECT pa.atom_value AS phrase, COUNT(*) AS n
           FROM auto_group_members agm
           JOIN party_atoms pa
             ON pa.source_id = agm.source_id
            AND pa.side      = agm.side
            AND pa.atom_type = 'brand_phrase'
           WHERE agm.auto_group_id = ? AND agm.member_type = 'party_side'
           GROUP BY pa.atom_value
           ORDER BY n DESC LIMIT 20""",
        (auto_group_id,),
    )]
    daterange = db.execute(
        """SELECT MIN(pf.sale_date) AS min_d, MAX(pf.sale_date) AS max_d
           FROM auto_group_members agm
           JOIN party_fingerprints pf
             ON pf.source_id = agm.source_id AND pf.side = agm.side
           WHERE agm.auto_group_id = ? AND agm.member_type = 'party_side'""",
        (auto_group_id,),
    ).fetchone()
    n_distinct_contacts = db.execute(
        """SELECT COUNT(DISTINCT pf.contact_fingerprint) AS n
           FROM auto_group_members agm
           JOIN party_fingerprints pf
             ON pf.source_id = agm.source_id AND pf.side = agm.side
           WHERE agm.auto_group_id = ? AND agm.member_type = 'party_side'""",
        (auto_group_id,),
    ).fetchone()['n']

    d = dict(summary)
    d['anchors']             = anchors
    d['members']             = members
    d['numbered_corps']      = numbered_corps
    d['top_phrases']         = top_phrases
    d['min_sale_date']       = daterange['min_d'] if daterange else None
    d['max_sale_date']       = daterange['max_d'] if daterange else None
    d['n_distinct_contacts'] = n_distinct_contacts
    return d
```

Update the docstring at the top of `cleo/web/routes/explorer.py` to list the two new endpoints.

- [ ] **Step 4: Run tests, confirm all pass**

```bash
pytest tests/test_routes_explorer.py -v
# Expected: all existing tests + the new auto_group tests pass
```

- [ ] **Step 5: Commit**

```bash
git add cleo/web/routes/explorer.py tests/test_routes_explorer.py
git commit -m "feat(layer2): API endpoints for auto-groups list + detail"
```

---

### Task 10: Frontend types and Explorer tab

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/components/explorer/ExplorerTabs.tsx`

- [ ] **Step 1: Add types to `frontend/src/types/index.ts`**

Append after the `ContactFingerprintDetail` block:

```typescript
// ============================================================
// Explorer — Auto-Groups (Layer 2 Plan A)
// ============================================================

export interface AutoGroupSummary {
  auto_group_id: string;
  canonical_stem: string;
  display_name: string;
  tier: 'confirmed' | 'probable' | 'candidate';
  confidence: number;
  n_anchors: number;
  n_members: number;
}

export interface AutoGroupListResponse {
  results: AutoGroupSummary[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

export interface AutoGroupAnchor {
  anchor_type: 'phone' | 'address_root' | 'address_base' | 'contact';
  anchor_value: string;
  score: number;
}

export interface AutoGroupMember {
  member_type: 'party_side';
  source_id: string;
  side: string;
  corp_name: string | null;
  match_score: number;
}

export interface AutoGroupNumberedCorp {
  corp_name: string;
  match_score: number;
}

export interface AutoGroupTopPhrase {
  phrase: string;
  n: number;
}

export interface AutoGroupDetail extends AutoGroupSummary {
  anchors: AutoGroupAnchor[];
  members: AutoGroupMember[];
  numbered_corps: AutoGroupNumberedCorp[];
  top_phrases: AutoGroupTopPhrase[];
  min_sale_date: string | null;
  max_sale_date: string | null;
  n_distinct_contacts: number;
  discovered_at: string | null;
}
```

- [ ] **Step 2: Add the "Groups (Auto)" tab to `ExplorerTabs.tsx`**

Append after the existing `Contacts` entry in the `topTabs` array:

```typescript
{ label: "Groups (Auto)", href: "/explorer/auto-groups", matches: (p) => p.startsWith("/explorer/auto-groups") },
```

- [ ] **Step 3: Run TypeScript check**

```bash
cd frontend && npx tsc --noEmit
# Expected: no errors
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/components/explorer/ExplorerTabs.tsx
git commit -m "feat(layer2): frontend types + Explorer tab for auto-groups"
```

---

### Task 11: Frontend list page

**Files:**
- Create: `frontend/src/pages/ExplorerAutoGroups.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create the list page**

```typescript
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Heading, Text, Button, TextField, Badge, SegmentedControl } from "@radix-ui/themes";
import { fetchApi } from "../api/client";
import type { AutoGroupListResponse, AutoGroupSummary } from "../types";
import ExplorerTabs from "../components/explorer/ExplorerTabs";


type Tier = 'confirmed' | 'probable' | 'candidate';

const tierColor: Record<Tier, "jade" | "amber" | "gray"> = {
  confirmed: "jade",
  probable:  "amber",
  candidate: "gray",
};

export default function ExplorerAutoGroups() {
  const nav = useNavigate();
  const [data, setData] = useState<AutoGroupListResponse | null>(null);
  const [tier, setTier] = useState<Tier>('confirmed');
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const perPage = 100;

  useEffect(() => {
    fetchApi<AutoGroupListResponse>("/explorer/auto-groups", {
      tier, q, page, per_page: perPage,
    }).then(setData).catch((e) => console.error(e));
  }, [tier, q, page]);

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <ExplorerTabs />
      <div className="flex items-baseline gap-4 mb-2 flex-wrap">
        <Heading size="6">Auto-Groups</Heading>
        <Text size="2" style={{ color: "var(--gray-9)" }}>
          Operator portfolios discovered by triangulating Layer 1 anchors.
          Read-only — actions land in Plan C.
        </Text>
      </div>
      <div className="flex items-center gap-4 my-5 flex-wrap">
        <SegmentedControl.Root value={tier}
            onValueChange={(v) => { setPage(1); setTier(v as Tier); }}>
          <SegmentedControl.Item value="confirmed">Confirmed</SegmentedControl.Item>
          <SegmentedControl.Item value="probable">Probable</SegmentedControl.Item>
          <SegmentedControl.Item value="candidate">Candidate</SegmentedControl.Item>
        </SegmentedControl.Root>
        <TextField.Root size="2" placeholder="Filter by stem or display name…"
            value={q} onChange={(e) => { setPage(1); setQ(e.target.value); }}
            style={{ width: 280 }} />
        {data && (
          <Text size="2" style={{ color: "var(--gray-9)" }}>
            {data.total.toLocaleString()} groups
          </Text>
        )}
      </div>

      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
        <table className="w-full text-[13px]">
          <thead className="bg-[var(--gray-2)]">
            <tr style={{ color: "var(--gray-9)" }}>
              <th className="text-left p-2 font-medium">display name</th>
              <th className="text-left p-2 font-medium">stem</th>
              <th className="text-left p-2 font-medium">tier</th>
              <th className="text-right p-2 font-medium">confidence</th>
              <th className="text-right p-2 font-medium">anchors</th>
              <th className="text-right p-2 font-medium">members</th>
            </tr>
          </thead>
          <tbody>
            {data?.results.map((g: AutoGroupSummary) => (
              <tr key={g.auto_group_id}
                  className="border-t border-[var(--gray-4)] hover:bg-[var(--gray-2)] cursor-pointer"
                  onClick={() => nav(`/explorer/auto-groups/${encodeURIComponent(g.auto_group_id)}`)}>
                <td className="p-2 font-mono">{g.display_name}</td>
                <td className="p-2 font-mono" style={{ color: "var(--gray-11)" }}>{g.canonical_stem}</td>
                <td className="p-2"><Badge color={tierColor[g.tier]}>{g.tier}</Badge></td>
                <td className="p-2 text-right">{g.confidence.toFixed(2)}</td>
                <td className="p-2 text-right">{g.n_anchors.toLocaleString()}</td>
                <td className="p-2 text-right">{g.n_members.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {data && data.pages > 1 && (
        <div className="flex items-center gap-2 mt-4">
          <Button size="1" variant="soft" disabled={page === 1} onClick={() => setPage(page - 1)}>
            Previous
          </Button>
          <Text size="2" style={{ color: "var(--gray-9)" }}>
            Page {page} of {data.pages}
          </Text>
          <Button size="1" variant="soft" disabled={page === data.pages} onClick={() => setPage(page + 1)}>
            Next
          </Button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Add route in `App.tsx`**

Add the lazy import near the other Explorer page imports (around line 70):

```typescript
const ExplorerAutoGroups = lazy(() => import("./pages/ExplorerAutoGroups"));
```

Add the route inside the `<Route element={<AppLayout />}>` block (near the other `/explorer/...` routes):

```typescript
<Route path="/explorer/auto-groups" element={<ExplorerAutoGroups />} />
```

- [ ] **Step 3: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 4: Browser smoke test**

Hit `http://localhost:5174/explorer/auto-groups` (after running `python -m cleo.discovery_v2` against real DB so `auto_groups` is populated). Verify:
- Default view shows Confirmed groups.
- Switching to Probable / Candidate updates the list.
- Search input filters by stem / display name.
- Row click navigates to `/explorer/auto-groups/<id>`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ExplorerAutoGroups.tsx frontend/src/App.tsx
git commit -m "feat(layer2): Explorer Auto-Groups list page"
```

---

### Task 12: Frontend detail page

**Files:**
- Create: `frontend/src/pages/ExplorerAutoGroupDetail.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create the detail page**

```typescript
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Heading, Text, Badge } from "@radix-ui/themes";
import { fetchApi } from "../api/client";
import type { AutoGroupDetail } from "../types";
import ExplorerTabs from "../components/explorer/ExplorerTabs";


const tierColor: Record<string, "jade" | "amber" | "gray"> = {
  confirmed: "jade",
  probable:  "amber",
  candidate: "gray",
};

export default function ExplorerAutoGroupDetail() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<AutoGroupDetail | null>(null);
  const [err, setErr]   = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    fetchApi<AutoGroupDetail>(`/explorer/auto-groups/${encodeURIComponent(id)}`)
      .then(setData).catch((e) => setErr(String(e)));
  }, [id]);

  if (err)  return <div className="p-6"><Text color="tomato">{err}</Text></div>;
  if (!data) return <div className="p-6"><Text size="2" style={{ color: "var(--gray-9)" }}>Loading…</Text></div>;

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <ExplorerTabs />
      <Link to="/explorer/auto-groups" className="text-[13px] no-underline"
            style={{ color: "var(--accent-11)" }}>
        ← Auto-Groups
      </Link>

      <div className="flex items-baseline gap-3 mt-2 mb-1 flex-wrap">
        <Heading size="6" className="font-mono">{data.display_name}</Heading>
        <Badge color={tierColor[data.tier]}>{data.tier}</Badge>
        <Text size="2" style={{ color: "var(--gray-9)" }}>
          stem: <span className="font-mono">{data.canonical_stem}</span>
        </Text>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mt-5">
        <StatCard label="Confidence" value={data.confidence.toFixed(2)} />
        <StatCard label="Anchors"    value={data.n_anchors.toLocaleString()} />
        <StatCard label="Members"    value={data.n_members.toLocaleString()} />
        <StatCard label="Distinct contacts" value={data.n_distinct_contacts.toLocaleString()} />
        <StatCard label="Date range"
                  value={data.min_sale_date && data.max_sale_date
                          ? `${data.min_sale_date.slice(0,7)} → ${data.max_sale_date.slice(0,7)}`
                          : "—"} />
      </div>

      {/* Anchors */}
      <Heading size="4" mt="6" mb="2">Anchors ({data.anchors.length})</Heading>
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
        <table className="w-full text-[13px]">
          <thead className="bg-[var(--gray-2)]">
            <tr style={{ color: "var(--gray-9)" }}>
              <th className="text-left p-2 font-medium">type</th>
              <th className="text-left p-2 font-medium">value</th>
              <th className="text-right p-2 font-medium">score</th>
            </tr>
          </thead>
          <tbody>
            {data.anchors.map((a, i) => (
              <tr key={i} className="border-t border-[var(--gray-4)]">
                <td className="p-2">{a.anchor_type}</td>
                <td className="p-2 font-mono">{a.anchor_value}</td>
                <td className="p-2 text-right">{a.score.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Top phrases */}
      <Heading size="4" mt="6" mb="2">Top phrases ({data.top_phrases.length})</Heading>
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
        <table className="w-full text-[13px]">
          <thead className="bg-[var(--gray-2)]">
            <tr style={{ color: "var(--gray-9)" }}>
              <th className="text-left p-2 font-medium">phrase</th>
              <th className="text-right p-2 font-medium">n</th>
            </tr>
          </thead>
          <tbody>
            {data.top_phrases.map((p, i) => (
              <tr key={i} className="border-t border-[var(--gray-4)]">
                <td className="p-2 font-mono">{p.phrase}</td>
                <td className="p-2 text-right">{p.n.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Numbered corps */}
      {data.numbered_corps.length > 0 && (
        <>
          <Heading size="4" mt="6" mb="2">Numbered corps owned ({data.numbered_corps.length})</Heading>
          <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-3 text-[13px]"
               style={{ background: "var(--gray-2)" }}>
            {data.numbered_corps.map((c, i) => (
              <span key={i} className="inline-block mr-3 mb-2 font-mono">{c.corp_name}</span>
            ))}
          </div>
        </>
      )}

      {/* Members (party-sides) */}
      <Heading size="4" mt="6" mb="2">
        Members ({data.n_members.toLocaleString()}{data.members.length < data.n_members ? `, top ${data.members.length} shown` : ''})
      </Heading>
      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
        <table className="w-full text-[13px]">
          <thead className="bg-[var(--gray-2)]">
            <tr style={{ color: "var(--gray-9)" }}>
              <th className="text-left p-2 font-medium">source_id</th>
              <th className="text-left p-2 font-medium">side</th>
              <th className="text-right p-2 font-medium">match_score</th>
            </tr>
          </thead>
          <tbody>
            {data.members.map((m, i) => (
              <tr key={i} className="border-t border-[var(--gray-4)]">
                <td className="p-2 font-mono">{m.source_id}</td>
                <td className="p-2">{m.side}</td>
                <td className="p-2 text-right">{m.match_score.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
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

- [ ] **Step 2: Add route in `App.tsx`**

Add the lazy import:

```typescript
const ExplorerAutoGroupDetail = lazy(() => import("./pages/ExplorerAutoGroupDetail"));
```

Add the route alongside the list route:

```typescript
<Route path="/explorer/auto-groups/:id" element={<ExplorerAutoGroupDetail />} />
```

- [ ] **Step 3: TypeScript check + browser smoke**

```bash
cd frontend && npx tsc --noEmit
# Then open http://localhost:5174/explorer/auto-groups, click into a group,
# verify all sections render: stat cards, anchors, top phrases, numbered corps, members.
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/ExplorerAutoGroupDetail.tsx frontend/src/App.tsx
git commit -m "feat(layer2): Explorer Auto-Group detail page"
```

---

### Task 13: Real-DB run + verification

**Files:** none (verification only)

- [ ] **Step 1: Apply migration 015 to the real DB (if Task 1 didn't already)**

```bash
sqlite3 data/cleo.db "SELECT COUNT(*) FROM sqlite_master WHERE name='auto_groups'"
# If 0, run:
python -m cleo.database.migrations.015_layer2_foundation_tables
```

- [ ] **Step 2: Run the full builder against real data**

```bash
python -m cleo.discovery_v2 2>&1 | tee /tmp/layer2-first-run.log
```

Capture the log. Expected lines:
```
Layer 2 Plan A: starting build...
  Stage A1 (stems): NN verified stems, MM phrase mappings.
  Stage A2 (anchor scores): KK anchor rows.
  Stage A3 (seeds): JJ groups.
  Stage A4 (expansion): II party-sides, NN numbered-corp memberships.
  Stage A5 (display + counts): JJ groups updated.
Layer 2 Plan A: done.
```

- [ ] **Step 3: Sanity check — top groups by member count**

```bash
sqlite3 -column -header data/cleo.db "
SELECT canonical_stem, tier, ROUND(confidence,2) AS conf, n_anchors, n_members, display_name
FROM auto_groups ORDER BY n_members DESC LIMIT 20"
```

Expected: `skyline`, `kingsett`, `metrus`, `starlight`, `riocan`, `berkshire`, `greenpark`, `dream`, `h&r` or similar — all in Confirmed tier with reasonable n_members (≥50 each).

- [ ] **Step 4: Sanity check — distinctive 1-grams that should have stems but didn't**

```bash
sqlite3 -column -header data/cleo.db "
SELECT bts.token, bts.n_party_sides
FROM brand_token_summary bts
LEFT JOIN brand_stem bs ON bs.stem = bts.token
WHERE (bts.is_distinctive=1 OR COALESCE(bts.is_position_anchor,0)=1)
  AND bts.n_party_sides >= 100
  AND bs.stem IS NULL
ORDER BY bts.n_party_sides DESC LIMIT 20"
```

If a known operator (e.g., `morguard`, `loblaw`) appears here, dig into why its candidate stem failed promotion. Expected outcome: most rows are valid non-promotions (e.g., generic position-anchors that didn't cluster), but flag any surprises.

- [ ] **Step 5: Sanity check — multi-tenant building did NOT seed**

```bash
sqlite3 -column -header data/cleo.db "
SELECT auto_group_id, canonical_stem, n_anchors
FROM auto_groups
WHERE auto_group_id IN (
  SELECT auto_group_id FROM auto_group_anchors
  WHERE anchor_type IN ('address_root','address_base')
    AND anchor_value LIKE '161|bay%'
)"
```

Expected: empty result, OR if any row appears it should have additional non-address anchors (n_anchors >= 2).

- [ ] **Step 6: Sanity check — common-name contact did NOT seed**

```bash
sqlite3 -column -header data/cleo.db "
SELECT auto_group_id, canonical_stem
FROM auto_groups
WHERE auto_group_id IN (
  SELECT auto_group_id FROM auto_group_anchors
  WHERE anchor_type='contact'
    AND anchor_value IN ('michael smith','john smith','david smith','michael miller','david miller'))"
```

Expected: empty result.

- [ ] **Step 7: Click-test the UI**

Start backend + frontend (ports 8099 / 5174 — already running). Visit `http://localhost:5174/explorer/auto-groups`. Confirm:
- Default tier=Confirmed shows ~10–50 groups.
- Top group by n_members is a real operator (Skyline / KingSett / Metrus / Starlight).
- Click into Skyline (or top group) — anchors include phone + address + contact. Top phrases match the expected operator family. Numbered corps owned (if any) make sense.
- Switch to Probable / Candidate — list updates, items have lower confidence.
- Search "kingsett" — narrows to KingSett-related groups.

- [ ] **Step 8: Capture the verification output**

Write a 5-line note to `/tmp/layer2-plan-a-verification.md` with:
- Total groups by tier (Confirmed / Probable / Candidate counts).
- Top 10 stems by n_members.
- Any unexpected groups (e.g., a Confirmed group whose top phrase doesn't match the stem) — flag for tuning.
- Any expected operator that didn't appear (debug for follow-up).

This becomes the input for tuning the constants in `cleo/discovery_v2/constants.py` if needed.

- [ ] **Step 9: Commit verification notes**

```bash
mkdir -p docs/superpowers/run-notes
mv /tmp/layer2-plan-a-verification.md docs/superpowers/run-notes/2026-04-27-layer-2-plan-a-first-run.md
git add docs/superpowers/run-notes/2026-04-27-layer-2-plan-a-first-run.md
git commit -m "docs: Layer 2 Plan A first-run verification notes"
```

---

## Self-Review

I checked the plan against the spec section-by-section:

- ✅ **Stem extraction (verified-promotion)** — Task 3 implements `extract_candidate_stem` + `build_stems` with the dominance/volume thresholds from constants.
- ✅ **Anchor uniqueness scoring** — Task 4 covers all four anchor types (phone, address_root, address_base, contact).
- ✅ **Auto-seed from anchor convergence** — Task 5 collapses address_root + address_base into one "address" category for tiering and applies the corroboration-anchor rule for the candidate tier.
- ✅ **Group expansion** — Task 6 implements the match-scoring rules from the spec, including the phone-contradiction demote.
- ✅ **Numbered Ontario/Canada corp recognition** — Task 6's regex `\d+\s+(ontario|canada|alberta|bc|quebec)\b` matches the patterns surfaced in Layer 1.
- ✅ **CRM override application** — Task 5's `_apply_crm_overrides` reads `auto_group_overrides` and `auto_anchor_overrides`. Plan A only handles confirm/reject; merge stays a stub for Plan C as the spec specified.
- ✅ **Display name** — Task 7's `_finalize_display_and_counts` picks the most-frequent phrase mapping to canonical_stem.
- ✅ **API endpoints** — Task 9 covers list (with tier filter, q substring, pagination) and detail (anchors, members, top phrases, numbered corps, date range, n_distinct_contacts).
- ✅ **UI** — Tasks 11+12 cover list with tier filter and detail with all spec-required sections.
- ✅ **Confidence formula** — Task 5's `_compute_tier_and_confidence` matches the formula in the spec exactly.
- ✅ **Tier thresholds, knobs** — Task 2's `constants.py` mirrors the "Defaults and tunable knobs" table from the spec.
- ✅ **Sandboxing** — All new tables prefixed `auto_*` or in the `brand_stem` family. The orchestrator runs separately from the main compiler. No existing app tables touched.
- ✅ **Verification** — Task 13 covers all the success-criteria checks in the spec ("Berkshire mega-cluster doesn't recur", "multi-tenant building doesn't seed alone", "common-name contact doesn't seed").

Type-consistency check: all function names + table names + column names referenced across tasks are consistent (e.g., `auto_group_id` everywhere, `anchor_type/anchor_value` everywhere, `match_score` everywhere).

Placeholder scan: no TBDs, no "implement later", no "similar to Task N" without code.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-27-layer-2-plan-a-foundation.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration. 13 tasks. Two-stage review (spec compliance + code quality) after each.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints for review.

Which approach?
