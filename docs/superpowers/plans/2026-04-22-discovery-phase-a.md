# Atom-Based Portfolio Discovery — Phase A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-04-22-atom-based-portfolio-discovery-architecture.md`

**Goal:** Ship the exact-match layer of atom-based portfolio discovery: blocking → scoring → Group/Contact graphs → entity assignment → timelines → eval harness, running end-to-end against the 249,084 party-sides already in `party_fingerprints`/`party_atoms`, calibrated against the 8 audit-file portfolios. No variant matching (nickname/phonetic/fuzzy) — that's Phase B.

**Architecture:** New tables prefixed `atom_*` (coexist with legacy `groups`/`discovery_*` tables until Phase G retires them). Entity IDs use new prefixes `AGR_NNNNN` (atom-discovered Groups) and `ACN_NNNNN` (atom-discovered Contacts) to avoid collision with the still-live legacy compiler-produced `GRP_`/`CON_`. Module entry point `python -m cleo.discovery_v2` for developer workflow — no user-facing CLI. Admin UI lands in Phase E.

**Tech Stack:** Python 3.12, SQLite, existing `cleo/atoms/` normalize + fingerprint, pytest. No new deps.

---

## File Structure

**Created:**
- `cleo/database/migrations/007_atom_discovery_tables.py` — new schema
- `cleo/discovery_v2/__init__.py` — package init
- `cleo/discovery_v2/__main__.py` — `python -m cleo.discovery_v2` dev entry
- `cleo/discovery_v2/config.py` — calibration knobs
- `cleo/discovery_v2/idf.py` — inverse-document-frequency computation
- `cleo/discovery_v2/blocking.py` — candidate pair generation
- `cleo/discovery_v2/scoring.py` — tier + effective confidence
- `cleo/discovery_v2/graph.py` — union-find for Group + Contact graphs
- `cleo/discovery_v2/entities.py` — GRP/CON entity assignment
- `cleo/discovery_v2/timelines.py` — materialize timeline tables
- `cleo/discovery_v2/relationships.py` — JV edge derivation
- `cleo/discovery_v2/runner.py` — orchestrator
- `cleo/discovery_v2/eval.py` — audit recall/purity metrics
- `tests/test_discovery_v2_idf.py`
- `tests/test_discovery_v2_blocking.py`
- `tests/test_discovery_v2_scoring.py`
- `tests/test_discovery_v2_graph.py`
- `tests/test_discovery_v2_entities.py`
- `tests/test_discovery_v2_timelines.py`
- `tests/test_discovery_v2_relationships.py`
- `tests/test_discovery_v2_runner.py`
- `tests/test_discovery_v2_eval.py`

**Modified:**
- `cleo/database/schema.py` — add `DERIVED_TABLES`/`DERIVED_INDEXES` entries; add `postal_raw` column to `party_fingerprints`
- `cleo/atoms/normalize.py` — `normalize_postal` returns `None` on invalid format; French street suffixes added
- `cleo/atoms/fingerprint.py` — populate `postal_raw`
- `tests/test_atoms_normalize.py` — update postal tests for new behavior

**Not touched in Phase A:**
- `cleo/discovery/` (legacy — retired in Phase G)
- `cleo/web/` (admin UI lands in Phase E)
- `frontend/` (UI lands in Phase E)
- Any CRM table

---

## Task 1: Schema migration for atom discovery tables

**Files:**
- Create: `cleo/database/migrations/007_atom_discovery_tables.py`
- Modify: `cleo/database/schema.py`

- [ ] **Step 1: Write the migration file**

Create `cleo/database/migrations/007_atom_discovery_tables.py`:

```python
"""
Migration 007: Create atom-based portfolio discovery tables.

All tables are prefixed atom_* to coexist with legacy discovery_*/groups
tables until Phase G retirement. These are DERIVED tables — rebuilt by
`cleo.discovery_v2.runner` on every run. Never contain user CRM data.

Run:
    python -m cleo.database.migrations.007_atom_discovery_tables
"""

import sqlite3
import os


def migrate(conn):
    print("Migration 007: Creating atom-based discovery tables...")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS atom_groups (
            id               TEXT PRIMARY KEY,
            canonical_brand  TEXT NOT NULL,
            display_name     TEXT NOT NULL,
            first_seen       TEXT,
            last_seen        TEXT,
            party_side_count INTEGER NOT NULL,
            discovered_at    TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS atom_contacts (
            id                TEXT PRIMARY KEY,
            canonical_name    TEXT NOT NULL,
            display_name      TEXT NOT NULL,
            first_seen        TEXT,
            last_seen         TEXT,
            party_side_count  INTEGER NOT NULL,
            discovered_at     TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS atom_party_entities (
            source_id          TEXT NOT NULL,
            side               TEXT NOT NULL CHECK (side IN ('buyer','seller')),
            group_id           TEXT REFERENCES atom_groups(id),
            contact_id         TEXT REFERENCES atom_contacts(id),
            group_link_tier    TEXT,
            contact_link_tier  TEXT,
            PRIMARY KEY (source_id, side)
        );
        CREATE INDEX IF NOT EXISTS idx_ape_group ON atom_party_entities(group_id);
        CREATE INDEX IF NOT EXISTS idx_ape_contact ON atom_party_entities(contact_id);

        CREATE TABLE IF NOT EXISTS atom_group_addresses (
            group_id       TEXT NOT NULL REFERENCES atom_groups(id),
            postal         TEXT, street_number TEXT, street_name TEXT, street_suffix TEXT,
            first_seen     TEXT, last_seen TEXT,
            n_observations INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_aga_group ON atom_group_addresses(group_id);

        CREATE TABLE IF NOT EXISTS atom_group_phones (
            group_id       TEXT NOT NULL REFERENCES atom_groups(id),
            phone          TEXT NOT NULL,
            first_seen     TEXT, last_seen TEXT,
            n_observations INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_agp_group ON atom_group_phones(group_id);

        CREATE TABLE IF NOT EXISTS atom_group_contacts (
            group_id       TEXT NOT NULL REFERENCES atom_groups(id),
            contact_id     TEXT NOT NULL REFERENCES atom_contacts(id),
            first_seen     TEXT, last_seen TEXT,
            n_observations INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_agc_group ON atom_group_contacts(group_id);

        CREATE TABLE IF NOT EXISTS atom_contact_groups (
            contact_id     TEXT NOT NULL REFERENCES atom_contacts(id),
            group_id       TEXT NOT NULL REFERENCES atom_groups(id),
            first_seen     TEXT, last_seen TEXT,
            n_observations INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_acg_contact ON atom_contact_groups(contact_id);

        CREATE TABLE IF NOT EXISTS atom_contact_addresses (
            contact_id     TEXT NOT NULL REFERENCES atom_contacts(id),
            postal         TEXT, street_number TEXT, street_name TEXT, street_suffix TEXT,
            first_seen     TEXT, last_seen TEXT,
            n_observations INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_aca_contact ON atom_contact_addresses(contact_id);

        CREATE TABLE IF NOT EXISTS atom_group_relationships (
            group_a_id     TEXT NOT NULL REFERENCES atom_groups(id),
            group_b_id     TEXT NOT NULL REFERENCES atom_groups(id),
            kind           TEXT NOT NULL CHECK (kind IN ('jv','parent_subsidiary','successor')),
            first_seen     TEXT, last_seen TEXT,
            n_party_sides  INTEGER,
            PRIMARY KEY (group_a_id, group_b_id, kind)
        );

        CREATE TABLE IF NOT EXISTS atom_discovery_runs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            config_version  TEXT NOT NULL,
            config_snapshot TEXT NOT NULL,
            ran_at          TEXT DEFAULT (datetime('now')),
            n_party_sides   INTEGER,
            n_groups        INTEGER,
            n_contacts      INTEGER,
            audit_metrics   TEXT,
            notes           TEXT
        );
    """)

    # Seed feature flag (legacy stays authoritative in Phase A).
    conn.execute(
        "INSERT OR IGNORE INTO app_meta (key, value, updated_at) "
        "VALUES ('discovery_engine', 'legacy', datetime('now'))"
    )
    conn.commit()
    print("Migration 007 complete.")


if __name__ == "__main__":
    db_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "cleo.db")
    conn = sqlite3.connect(db_path)
    migrate(conn)
    conn.close()
```

- [ ] **Step 2: Register the new tables in `schema.py`**

Open `cleo/database/schema.py`. Find the `DERIVED_TABLES` section. Add the atom_* tables to the list so `drop_derived_tables()` knows to drop them between full recompiles.

Add to `DERIVED_TABLES` list (somewhere near the other derived entries — keep alphabetical if that's the pattern, otherwise append):

```python
"atom_groups",
"atom_contacts",
"atom_party_entities",
"atom_group_addresses",
"atom_group_phones",
"atom_group_contacts",
"atom_contact_groups",
"atom_contact_addresses",
"atom_group_relationships",
```

**Do NOT add** `atom_discovery_runs` to `DERIVED_TABLES` — it's a run-history table (semi-derived, not dropped between runs).

- [ ] **Step 3: Run the migration and verify**

```bash
python -m cleo.database.migrations.007_atom_discovery_tables
```

Expected output: `Migration 007: Creating atom-based discovery tables...` then `Migration 007 complete.`

Verify:
```bash
sqlite3 data/cleo.db "SELECT name FROM sqlite_master WHERE name LIKE 'atom_%' ORDER BY name;"
```

Expected: 10 table names.

- [ ] **Step 4: Commit**

```bash
git add cleo/database/migrations/007_atom_discovery_tables.py cleo/database/schema.py
git commit -m "feat(discovery-v2): schema for atom-based portfolio discovery"
```

---

## Task 2: Data-quality fix — invalid postal codes → NULL, raw preserved

**Files:**
- Modify: `cleo/atoms/normalize.py`
- Modify: `cleo/atoms/fingerprint.py`
- Modify: `cleo/database/schema.py` (add `postal_raw` column to `party_fingerprints`)
- Modify: `tests/test_atoms_normalize.py`

- [ ] **Step 1: Write the failing tests**

Open `tests/test_atoms_normalize.py`. Add:

```python
def test_normalize_postal_returns_none_for_invalid_format():
    from cleo.atoms.normalize import normalize_postal
    # 61 such values exist in the current corpus per the exploration report.
    assert normalize_postal("M4W 3E23") is None
    assert normalize_postal("L4L-1N4") is None
    assert normalize_postal("BB15006") is None
    assert normalize_postal("K2G 12E4") is None

def test_normalize_postal_still_accepts_valid_ca_and_us():
    from cleo.atoms.normalize import normalize_postal
    assert normalize_postal("m5k 1h6") == "M5K1H6"
    assert normalize_postal("M5K1H6") == "M5K1H6"
    assert normalize_postal("90210") == "90210"
    assert normalize_postal("90210-1234") == "90210-1234"
```

Run: `pytest tests/test_atoms_normalize.py -v -k postal`

Expected: the new "invalid returns None" test fails (current fallthrough returns uppercased raw).

- [ ] **Step 2: Change `normalize_postal` to drop the fallthrough**

Open `cleo/atoms/normalize.py`. Find `normalize_postal`. Replace the fallthrough:

```python
def normalize_postal(raw: Optional[str]) -> Optional[str]:
    """Canonicalize a Canadian postal code or US ZIP, or None if the value
    doesn't match either format.

    Canadian: UPPERCASE, strip internal spaces. "M5K 1H6" -> "M5K1H6".
    US ZIP: preserve hyphen for ZIP+4. Strip surrounding whitespace.
    Non-matching: return None (caller should preserve via postal_raw if needed).

    Examples:
      "m5k 1h6" -> "M5K1H6"
      "M4W 3E23" -> None  (invalid — 4 chars in second half)
      "" / None -> None
    """
    s = _strip_or_none(raw)
    if s is None:
        return None

    upper = s.upper().strip()

    if _POSTAL_CA.match(upper):
        return upper.replace(" ", "")

    stripped = s.strip()
    if _POSTAL_US.match(stripped):
        return stripped

    return None
```

Run: `pytest tests/test_atoms_normalize.py -v -k postal`

Expected: both tests pass.

- [ ] **Step 3: Add `postal_raw` column to schema**

Open `cleo/database/schema.py`. Find the `CREATE TABLE IF NOT EXISTS party_fingerprints` block. Add `postal_raw TEXT` directly after the `postal TEXT` line.

Apply the matching change to the inline CREATE statement in `cleo/atoms/fingerprint.py` (the `executescript` block that recreates the table). Add `postal_raw TEXT,` right after `postal TEXT,`.

- [ ] **Step 4: Populate `postal_raw` in the fingerprint pass**

Open `cleo/atoms/fingerprint.py`. Find the `fp_rows.append((...))` block in `run_fingerprint_pass`. Modify to include the raw postal value alongside the normalized one:

```python
        fp_rows.append((
            r['source_id'],
            r['side'],
            normalize_street_number(r['street_number']),
            normalize_street_name(r['street_name']),
            normalize_street_suffix(r['street_suffix']),
            normalize_street_direction(r['street_direction']),
            normalize_suite_type(r['suite_type']),
            normalize_suite_number(r['suite_number']),
            normalize_city(r['city']),
            normalize_province(r['province']),
            normalize_postal(r['postal']),
            r['postal'],  # postal_raw — preserve source string verbatim
            normalize_country(r['country']),
            phone,
            contact_fp,
            r['sale_date'],
        ))
```

Update the matching `INSERT INTO party_fingerprints` statement lower down:

```python
    conn.executemany(
        """INSERT INTO party_fingerprints
           (source_id, side, street_number, street_name, street_suffix, street_direction,
            suite_type, suite_number, city, province, postal, postal_raw, country,
            phone, contact_fingerprint, sale_date)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        fp_rows,
    )
```

- [ ] **Step 5: Re-run the fingerprint pass and verify**

```bash
python -c "
from cleo.database.connection import get_connection
from cleo.atoms.fingerprint import run_fingerprint_pass
conn = get_connection()
run_fingerprint_pass(conn)
conn.close()
"
```

Verify malformed values now go to `postal_raw`, not `postal`:

```bash
sqlite3 data/cleo.db \
  "SELECT postal, postal_raw FROM party_fingerprints
   WHERE postal_raw = 'M4W 3E23' OR postal_raw = 'L4L-1N4' LIMIT 5;"
```

Expected: `postal` column empty (NULL), `postal_raw` shows the source value.

Also verify the former 61-malformed count is now NULL-postal:

```bash
sqlite3 data/cleo.db \
  "SELECT COUNT(*) FROM party_fingerprints
   WHERE postal IS NULL AND postal_raw IS NOT NULL AND postal_raw != '';"
```

Expected: ≥ 61.

- [ ] **Step 6: Commit**

```bash
git add cleo/atoms/normalize.py cleo/atoms/fingerprint.py cleo/database/schema.py tests/test_atoms_normalize.py
git commit -m "fix(atoms): invalid postals → NULL, preserve raw in postal_raw column"
```

---

## Task 3: Data-quality fix — French street suffixes

**Files:**
- Modify: `cleo/atoms/normalize.py`
- Modify: `tests/test_atoms_normalize.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_atoms_normalize.py`:

```python
def test_normalize_street_suffix_french():
    from cleo.atoms.normalize import normalize_street_suffix
    # rue and chemin appear 422 and 207 times in the corpus
    assert normalize_street_suffix("rue") == "rue"
    assert normalize_street_suffix("Rue") == "rue"
    assert normalize_street_suffix("chemin") == "chemin"
    assert normalize_street_suffix("Chemin") == "chemin"
    assert normalize_street_suffix("ch") == "chemin"
    assert normalize_street_suffix("ch.") == "chemin"
```

Run: `pytest tests/test_atoms_normalize.py -v -k street_suffix_french`

Expected: fails (rue/chemin currently fall through to lowercased-stripped; `ch` would return `ch` not `chemin`).

- [ ] **Step 2: Add French suffixes to the map**

Open `cleo/atoms/normalize.py`. Find `_STREET_SUFFIX_MAP`. Add within the existing dict:

```python
    # French Canadian
    "rue": "rue",
    "chemin": "chemin", "ch": "chemin",
    "boul": "boulevard",  # already maps via "bl"/"bld" but add explicit
```

(Note: `boul` may already be mapped — check. If so, skip it.)

- [ ] **Step 3: Run tests to verify they pass**

Run: `pytest tests/test_atoms_normalize.py -v -k street_suffix`

Expected: all street-suffix tests pass.

- [ ] **Step 4: Commit**

```bash
git add cleo/atoms/normalize.py tests/test_atoms_normalize.py
git commit -m "feat(atoms): recognize French street suffixes (rue, chemin, ch)"
```

---

## Task 4: Discovery config module

**Files:**
- Create: `cleo/discovery_v2/__init__.py`
- Create: `cleo/discovery_v2/config.py`

- [ ] **Step 1: Create the package**

```bash
mkdir -p cleo/discovery_v2
touch cleo/discovery_v2/__init__.py
```

- [ ] **Step 2: Write the config module**

Create `cleo/discovery_v2/config.py`:

```python
"""Calibration knobs for atom-based portfolio discovery.

Every matching rule is a knob. Phase A ships with the exact-match tier
only — subsequent phases add nickname/phonetic/fuzzy/subset.

Changes here are real. Check the eval harness output (docs/discovery-audit/)
after every knob turn.
"""

from __future__ import annotations

CALIBRATION_VERSION = "2026-04-22-phase-a-v1"

CALIBRATION = {
    "version": CALIBRATION_VERSION,

    # Tier 1 — exact brand_token match (Group graph's primary signal)
    "exact_brand_token": {
        "enabled": True,
        "min_idf": 3.0,
        "reason": (
            "Tokens on ≳5,000 party-sides have IDF under 3.0 (N=249,084). "
            "Above that floor: rasenberg (IDF ~8.5) allowed, kingsett "
            "(IDF ~6.5) allowed, holdings (IDF ~2.7) blocked, ontario (IDF "
            "~1.4) blocked. Generic corporate vocabulary gets dampened to "
            "blocking-only; distinctive tokens drive links."
        ),
    },

    # Tier 1 — exact address-triple (street_number + street_name + street_suffix)
    "exact_address_triple": {
        "enabled": True,
        "require_all_three_parts": True,
        "reason": (
            "Full triple match is strong alone (median count ≤ 5 per "
            "triple). Individual parts (street_name='king') are too common."
        ),
    },

    # Tier 1 — exact phone (only Strong when a brand OR address co-signal agrees)
    "exact_phone": {
        "enabled": True,
        "require_co_signal": True,
        "co_signal_atoms": ["brand_token", "address_triple"],
        "reason": (
            "Phones alias: management-company main lines appear across "
            "unrelated operator portfolios. Rarity ≠ precision. Upgrade "
            "phone to Strong only when a brand or address corroborates."
        ),
    },

    # Tier 1 — exact contact fingerprint (drives Contact graph)
    "exact_contact_fingerprint": {
        "enabled": True,
        "reason": (
            "First+last exact match is Strong for Contact-entity linking. "
            "Does NOT merge Groups — a person can work at many Groups."
        ),
    },

    # Categorical exclusions (never used as link atoms; see spec §9).
    "excluded_brand_tokens": frozenset({
        "named", "individual",  # Named Individual(s) suppressed-name artifact
    }),
    "excluded_brand_phrases": frozenset({
        "named individual s",
        "creo mail code 01 86",  # RT scraping artifact
    }),

    # Audit inputs for eval harness
    "audit_docs_root": "docs/discovery-audit",
}
```

- [ ] **Step 3: Commit**

```bash
git add cleo/discovery_v2/__init__.py cleo/discovery_v2/config.py
git commit -m "feat(discovery-v2): calibration config for Phase A"
```

---

## Task 5: IDF computation utility

**Files:**
- Create: `cleo/discovery_v2/idf.py`
- Create: `tests/test_discovery_v2_idf.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_discovery_v2_idf.py`:

```python
"""Tests for IDF computation."""
import math
import sqlite3


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE party_fingerprints (
            source_id TEXT, side TEXT, phone TEXT,
            PRIMARY KEY (source_id, side)
        );
        CREATE TABLE party_atoms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT, side TEXT,
            atom_type TEXT, atom_value TEXT, source_field TEXT
        );
    """)
    return conn


def test_idf_common_token_low_rare_token_high():
    from cleo.discovery_v2.idf import compute_idf_map

    conn = _make_db()
    # 100 party-sides; 'ontario' on 80; 'rasenberg' on 2
    for i in range(100):
        conn.execute(
            "INSERT INTO party_fingerprints (source_id, side) VALUES (?, 'buyer')",
            (f"RT{i}",),
        )
    for i in range(80):
        conn.execute(
            "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
            "VALUES (?, 'buyer', 'brand_token', 'ontario', 'party_name')",
            (f"RT{i}",),
        )
    for i in range(2):
        conn.execute(
            "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
            "VALUES (?, 'buyer', 'brand_token', 'rasenberg', 'party_name')",
            (f"RT{i}",),
        )
    conn.commit()

    idf_map = compute_idf_map(conn)
    ontario_idf = idf_map[("brand_token", "ontario")]
    rasenberg_idf = idf_map[("brand_token", "rasenberg")]

    assert ontario_idf < 1.0, f"common token IDF too high: {ontario_idf}"
    assert rasenberg_idf > 3.0, f"rare token IDF too low: {rasenberg_idf}"
    # Sanity: match the log(N / (1 + df)) formula
    assert math.isclose(ontario_idf, math.log(100 / 81), rel_tol=1e-6)


def test_idf_covers_singleton_atoms_too():
    """IDF is computed for phone (singleton, from party_fingerprints) too."""
    from cleo.discovery_v2.idf import compute_idf_map

    conn = _make_db()
    for i in range(50):
        conn.execute(
            "INSERT INTO party_fingerprints (source_id, side, phone) "
            "VALUES (?, 'buyer', ?)",
            (f"RT{i}", "4166876700" if i < 30 else "9055555555"),
        )
    conn.commit()

    idf_map = compute_idf_map(conn)
    assert ("phone", "4166876700") in idf_map
    assert ("phone", "9055555555") in idf_map
```

Run: `pytest tests/test_discovery_v2_idf.py -v`

Expected: fails with import error (module doesn't exist).

- [ ] **Step 2: Write `cleo/discovery_v2/idf.py`**

```python
"""IDF (inverse document frequency) computation over atoms.

IDF answers: "how many party-sides share this atom value out of the total?"
Low IDF = common = weak signal. High IDF = rare = strong signal.
Formula: IDF(v) = log(N / (1 + df(v))) where N is total party-sides
and df(v) is count carrying that (atom_type, atom_value).
"""

from __future__ import annotations
import math
from typing import Dict, Tuple


def compute_idf_map(conn) -> Dict[Tuple[str, str], float]:
    """Return a dict keyed by (atom_type, atom_value) with IDF values.

    Covers both multi-valued atoms (from party_atoms) and singleton atoms
    (from party_fingerprints columns — phone, contact_fingerprint, postal).
    """
    n = conn.execute(
        "SELECT COUNT(*) FROM party_fingerprints"
    ).fetchone()[0]
    if n == 0:
        return {}

    idf: Dict[Tuple[str, str], float] = {}

    # Multi-valued atoms — count distinct party-sides per (atom_type, atom_value)
    for row in conn.execute(
        """SELECT atom_type, atom_value, COUNT(DISTINCT source_id || '|' || side) AS df
           FROM party_atoms
           GROUP BY atom_type, atom_value"""
    ):
        idf[(row[0], row[1])] = math.log(n / (1 + row[2]))

    # Singleton atoms — count non-NULL occurrences per column
    for col in ("phone", "contact_fingerprint", "postal"):
        for row in conn.execute(
            f"""SELECT {col} AS v, COUNT(*) AS df
                FROM party_fingerprints
                WHERE {col} IS NOT NULL AND {col} != ''
                GROUP BY {col}"""
        ):
            idf[(col, row[0])] = math.log(n / (1 + row[1]))

    return idf
```

Run: `pytest tests/test_discovery_v2_idf.py -v`

Expected: both tests pass.

- [ ] **Step 3: Commit**

```bash
git add cleo/discovery_v2/idf.py tests/test_discovery_v2_idf.py
git commit -m "feat(discovery-v2): IDF computation over atoms"
```

---

## Task 6: Blocking module — candidate pair generation

**Files:**
- Create: `cleo/discovery_v2/blocking.py`
- Create: `tests/test_discovery_v2_blocking.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_discovery_v2_blocking.py`:

```python
"""Tests for candidate pair blocking."""
import sqlite3


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE party_fingerprints (
            source_id TEXT, side TEXT,
            street_number TEXT, street_name TEXT, street_suffix TEXT,
            phone TEXT, contact_fingerprint TEXT,
            PRIMARY KEY (source_id, side)
        );
        CREATE TABLE party_atoms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT, side TEXT,
            atom_type TEXT, atom_value TEXT, source_field TEXT
        );
    """)
    return conn


def test_blocks_on_rare_brand_token():
    from cleo.discovery_v2.blocking import generate_candidate_pairs
    from cleo.discovery_v2.idf import compute_idf_map

    conn = _make_db()
    # Two party-sides sharing 'kingsett' — only one occurrence of the token
    # per side, so it's rare.
    conn.execute("INSERT INTO party_fingerprints (source_id, side) VALUES ('RT1', 'buyer')")
    conn.execute("INSERT INTO party_fingerprints (source_id, side) VALUES ('RT2', 'buyer')")
    for sid in ("RT1", "RT2"):
        conn.execute(
            "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
            "VALUES (?, 'buyer', 'brand_token', 'kingsett', 'party_name')",
            (sid,),
        )
    conn.commit()

    idf = compute_idf_map(conn)
    pairs = list(generate_candidate_pairs(conn, idf, min_idf=0.0))
    keys = {(p[0], p[1], p[2], p[3], p[4]) for p in pairs}

    assert ("RT1", "buyer", "RT2", "buyer", "brand_token") in keys \
        or ("RT2", "buyer", "RT1", "buyer", "brand_token") in keys


def test_does_not_block_on_generic_brand_token_below_min_idf():
    """A token that's common (below min_idf) does not generate candidate pairs."""
    from cleo.discovery_v2.blocking import generate_candidate_pairs
    from cleo.discovery_v2.idf import compute_idf_map

    conn = _make_db()
    # 10 party-sides all carrying 'ontario' — IDF ~ log(10/11) < 0
    for i in range(10):
        conn.execute(
            "INSERT INTO party_fingerprints (source_id, side) VALUES (?, 'buyer')",
            (f"RT{i}",),
        )
        conn.execute(
            "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
            "VALUES (?, 'buyer', 'brand_token', 'ontario', 'party_name')",
            (f"RT{i}",),
        )
    conn.commit()

    idf = compute_idf_map(conn)
    # min_idf = 3.0 blocks 'ontario' entirely.
    pairs = list(generate_candidate_pairs(conn, idf, min_idf=3.0))
    brand_pairs = [p for p in pairs if p[4] == "brand_token"]
    assert brand_pairs == []


def test_blocks_on_exact_phone_and_address_triple_and_contact():
    from cleo.discovery_v2.blocking import generate_candidate_pairs
    from cleo.discovery_v2.idf import compute_idf_map

    conn = _make_db()
    conn.execute(
        "INSERT INTO party_fingerprints "
        "(source_id, side, street_number, street_name, street_suffix, phone, contact_fingerprint) "
        "VALUES ('RT1', 'buyer', '66', 'wellington', 'street', '4166876700', 'rob kumer')"
    )
    conn.execute(
        "INSERT INTO party_fingerprints "
        "(source_id, side, street_number, street_name, street_suffix, phone, contact_fingerprint) "
        "VALUES ('RT2', 'buyer', '66', 'wellington', 'street', '4166876700', 'rob kumer')"
    )
    conn.commit()

    idf = compute_idf_map(conn)
    pairs = list(generate_candidate_pairs(conn, idf, min_idf=0.0))
    atom_types = {p[4] for p in pairs}

    assert "phone" in atom_types
    assert "address_triple" in atom_types
    assert "contact_fingerprint" in atom_types
```

Run: `pytest tests/test_discovery_v2_blocking.py -v`

Expected: fails with import error.

- [ ] **Step 2: Write `cleo/discovery_v2/blocking.py`**

```python
"""Candidate pair blocking — generate pairs that share at least one
non-generic atom. Prevents O(N²) comparisons.
"""

from __future__ import annotations
from itertools import combinations
from typing import Dict, Generator, Tuple

from .config import CALIBRATION

PartySide = Tuple[str, str]  # (source_id, side)
CandidatePair = Tuple[str, str, str, str, str, str]
# (source_id_a, side_a, source_id_b, side_b, atom_type, atom_value)


def _canonical_pair(a: PartySide, b: PartySide) -> Tuple[PartySide, PartySide]:
    """Order-independent pair key so we emit each pair once."""
    return (a, b) if a < b else (b, a)


def generate_candidate_pairs(
    conn, idf_map: Dict[Tuple[str, str], float], *, min_idf: float = None,
) -> Generator[CandidatePair, None, None]:
    """Yield candidate pairs sharing at least one non-generic atom.

    Atom types scanned:
      - brand_token (multi-valued; IDF-gated by min_idf)
      - phone (singleton)
      - address_triple (synthesized from street_number + street_name + street_suffix)
      - contact_fingerprint (singleton)

    Yields (source_id_a, side_a, source_id_b, side_b, atom_type, atom_value),
    ordered so (a_key) < (b_key).
    Deduplicated across atom types.
    """
    if min_idf is None:
        min_idf = CALIBRATION["exact_brand_token"]["min_idf"]

    excluded_tokens = CALIBRATION["excluded_brand_tokens"]
    seen_pairs: set = set()

    def _emit(a: PartySide, b: PartySide, atom_type: str, atom_value: str):
        if a == b:
            return
        a_sorted, b_sorted = _canonical_pair(a, b)
        key = (a_sorted, b_sorted, atom_type, atom_value)
        if key in seen_pairs:
            return
        seen_pairs.add(key)
        yield (a_sorted[0], a_sorted[1], b_sorted[0], b_sorted[1], atom_type, atom_value)

    # 1. brand_token — gated by IDF threshold and exclusion list
    rows = conn.execute(
        "SELECT atom_value, source_id, side FROM party_atoms "
        "WHERE atom_type = 'brand_token' ORDER BY atom_value"
    ).fetchall()
    bucket: Dict[str, list] = {}
    for r in rows:
        val = r["atom_value"]
        if val in excluded_tokens:
            continue
        if idf_map.get(("brand_token", val), 0.0) < min_idf:
            continue
        bucket.setdefault(val, []).append((r["source_id"], r["side"]))
    for val, sides in bucket.items():
        if len(sides) < 2:
            continue
        uniq = sorted(set(sides))
        for a, b in combinations(uniq, 2):
            yield from _emit(a, b, "brand_token", val)

    # 2. phone — no IDF gate in Phase A (require_co_signal handled in scoring)
    for row in conn.execute(
        "SELECT phone, COUNT(*) AS c FROM party_fingerprints "
        "WHERE phone IS NOT NULL AND phone != '' GROUP BY phone HAVING c >= 2"
    ):
        phone = row["phone"]
        sides = [
            (r["source_id"], r["side"]) for r in conn.execute(
                "SELECT source_id, side FROM party_fingerprints WHERE phone = ?",
                (phone,),
            )
        ]
        for a, b in combinations(sorted(set(sides)), 2):
            yield from _emit(a, b, "phone", phone)

    # 3. address_triple — full match only
    for row in conn.execute(
        """SELECT street_number, street_name, street_suffix,
                  GROUP_CONCAT(source_id || '|' || side, ';') AS sides_csv,
                  COUNT(*) AS c
           FROM party_fingerprints
           WHERE street_number IS NOT NULL AND street_number != ''
             AND street_name IS NOT NULL AND street_name != ''
             AND street_suffix IS NOT NULL AND street_suffix != ''
           GROUP BY street_number, street_name, street_suffix
           HAVING c >= 2"""
    ):
        triple = f"{row['street_number']}|{row['street_name']}|{row['street_suffix']}"
        sides = [tuple(s.split("|")) for s in row["sides_csv"].split(";")]
        for a, b in combinations(sorted(set(sides)), 2):
            yield from _emit(a, b, "address_triple", triple)

    # 4. contact_fingerprint — exact
    for row in conn.execute(
        "SELECT contact_fingerprint, COUNT(*) AS c FROM party_fingerprints "
        "WHERE contact_fingerprint IS NOT NULL AND contact_fingerprint != '' "
        "GROUP BY contact_fingerprint HAVING c >= 2"
    ):
        cf = row["contact_fingerprint"]
        sides = [
            (r["source_id"], r["side"]) for r in conn.execute(
                "SELECT source_id, side FROM party_fingerprints WHERE contact_fingerprint = ?",
                (cf,),
            )
        ]
        for a, b in combinations(sorted(set(sides)), 2):
            yield from _emit(a, b, "contact_fingerprint", cf)
```

Run: `pytest tests/test_discovery_v2_blocking.py -v`

Expected: all three tests pass.

- [ ] **Step 3: Commit**

```bash
git add cleo/discovery_v2/blocking.py tests/test_discovery_v2_blocking.py
git commit -m "feat(discovery-v2): blocking — candidate pair generation"
```

---

## Task 7: Scoring module — tier + effective confidence (exact-only)

**Files:**
- Create: `cleo/discovery_v2/scoring.py`
- Create: `tests/test_discovery_v2_scoring.py`

Phase A only emits **Strong** or **nothing**. Medium-tier is reserved for Phase B (variants) and the labeling-tool review queue.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_discovery_v2_scoring.py`:

```python
"""Tests for pair scoring — exact-tier only in Phase A."""


def test_exact_rare_brand_token_is_strong_group_edge():
    from cleo.discovery_v2.scoring import score_pair
    # IDF 7.0 > min_idf 3.0
    match_atoms = [("brand_token", "kingsett", 7.0)]
    result = score_pair(match_atoms)
    assert result["group_tier"] == "strong"
    assert result["contact_tier"] is None


def test_generic_brand_token_is_not_a_link():
    """A token below min_idf shouldn't even appear in match_atoms, but
    belt-and-suspenders: scoring rejects it if it slips through."""
    from cleo.discovery_v2.scoring import score_pair
    match_atoms = [("brand_token", "holdings", 2.0)]  # below min_idf=3.0
    result = score_pair(match_atoms)
    assert result["group_tier"] is None


def test_address_triple_alone_is_strong_group_edge():
    from cleo.discovery_v2.scoring import score_pair
    match_atoms = [("address_triple", "66|wellington|street", 5.0)]
    result = score_pair(match_atoms)
    assert result["group_tier"] == "strong"


def test_phone_alone_is_not_a_strong_edge():
    """Phones alias across unrelated portfolios (management company lines).
    Phone-only stays medium (not auto-linked in Phase A)."""
    from cleo.discovery_v2.scoring import score_pair
    match_atoms = [("phone", "4162348444", 5.0)]
    result = score_pair(match_atoms)
    assert result["group_tier"] != "strong"


def test_phone_plus_brand_cosignal_is_strong():
    from cleo.discovery_v2.scoring import score_pair
    match_atoms = [
        ("phone", "4166876700", 5.0),
        ("brand_token", "kingsett", 7.0),
    ]
    result = score_pair(match_atoms)
    assert result["group_tier"] == "strong"


def test_phone_plus_address_cosignal_is_strong():
    from cleo.discovery_v2.scoring import score_pair
    match_atoms = [
        ("phone", "4166876700", 5.0),
        ("address_triple", "66|wellington|street", 5.0),
    ]
    result = score_pair(match_atoms)
    assert result["group_tier"] == "strong"


def test_exact_contact_fingerprint_is_strong_contact_edge_not_group_edge():
    """Same person can work at many different Groups. Contact-only match
    drives the Contact graph, NOT the Group graph."""
    from cleo.discovery_v2.scoring import score_pair
    match_atoms = [("contact_fingerprint", "rob kumer", 6.0)]
    result = score_pair(match_atoms)
    assert result["contact_tier"] == "strong"
    assert result["group_tier"] is None
```

Run: `pytest tests/test_discovery_v2_scoring.py -v`

Expected: fails with import error.

- [ ] **Step 2: Write `cleo/discovery_v2/scoring.py`**

```python
"""Pair scoring — compute Group-graph and Contact-graph tier per pair.

Phase A: exact-tier only. A pair carries one or more match atoms
(from the blocking pass). Scoring decides whether the pair is a
Strong edge in the Group graph, the Contact graph, both, or neither.

Phase A rules (see spec §6):
  - Exact non-generic brand_token alone → Strong Group edge
  - Exact address_triple alone → Strong Group edge
  - Exact phone alone → not Strong (alias risk); Strong only when
    brand or address co-signal agrees
  - Exact contact_fingerprint → Strong Contact edge (never a Group edge
    by itself — people move between Groups)
"""

from __future__ import annotations
from typing import List, Optional, Tuple, TypedDict

from .config import CALIBRATION

MatchAtom = Tuple[str, str, float]  # (atom_type, atom_value, idf)


class PairScore(TypedDict):
    group_tier: Optional[str]   # 'strong' | None
    contact_tier: Optional[str]
    match_atoms: List[MatchAtom]


def score_pair(match_atoms: List[MatchAtom]) -> PairScore:
    """Given the match atoms for a pair, return the Group and Contact tiers.

    Phase A outputs: 'strong' or None. No medium tier in Phase A.
    """
    result: PairScore = {"group_tier": None, "contact_tier": None, "match_atoms": match_atoms}
    if not match_atoms:
        return result

    min_idf = CALIBRATION["exact_brand_token"]["min_idf"]

    brand_token_hit = any(
        a[0] == "brand_token" and a[2] >= min_idf for a in match_atoms
    )
    address_triple_hit = any(a[0] == "address_triple" for a in match_atoms)
    phone_hit = any(a[0] == "phone" for a in match_atoms)
    contact_hit = any(a[0] == "contact_fingerprint" for a in match_atoms)

    # Group-graph tier
    if brand_token_hit or address_triple_hit:
        result["group_tier"] = "strong"
    elif phone_hit and (brand_token_hit or address_triple_hit):
        # unreachable given the above, but explicit about the co-signal rule
        result["group_tier"] = "strong"

    # Contact-graph tier — exact contact fingerprint → Strong
    if contact_hit:
        result["contact_tier"] = "strong"

    return result


def aggregate_match_atoms(pair_rows) -> List[MatchAtom]:
    """Given multiple candidate-pair rows for the same (source_a, source_b),
    aggregate their (atom_type, atom_value) into a single match_atoms list.

    Called by the runner to compress blocking output before scoring.
    """
    seen = set()
    result = []
    for row in pair_rows:
        key = (row["atom_type"], row["atom_value"])
        if key in seen:
            continue
        seen.add(key)
        result.append((row["atom_type"], row["atom_value"], row.get("idf", 0.0)))
    return result
```

Run: `pytest tests/test_discovery_v2_scoring.py -v`

Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add cleo/discovery_v2/scoring.py tests/test_discovery_v2_scoring.py
git commit -m "feat(discovery-v2): exact-tier pair scoring with co-signal rule for phone"
```

---

## Task 8: Graph construction — union-find for Group and Contact graphs

**Files:**
- Create: `cleo/discovery_v2/graph.py`
- Create: `tests/test_discovery_v2_graph.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_discovery_v2_graph.py`:

```python
"""Tests for union-find graph construction."""


def test_three_nodes_one_component_via_transitive_closure():
    from cleo.discovery_v2.graph import build_components

    # A-B strong, B-C strong → {A, B, C} is one component
    edges = [
        (("RT1", "buyer"), ("RT2", "buyer"), "strong"),
        (("RT2", "buyer"), ("RT3", "buyer"), "strong"),
    ]
    components = build_components(edges)
    comp_of = {node: comp_id for comp_id, nodes in components.items() for node in nodes}
    assert comp_of[("RT1", "buyer")] == comp_of[("RT2", "buyer")]
    assert comp_of[("RT2", "buyer")] == comp_of[("RT3", "buyer")]
    assert len(components) == 1


def test_separate_strong_components_stay_separate():
    from cleo.discovery_v2.graph import build_components

    edges = [
        (("RT1", "buyer"), ("RT2", "buyer"), "strong"),
        (("RT3", "buyer"), ("RT4", "buyer"), "strong"),
    ]
    components = build_components(edges)
    assert len(components) == 2


def test_singleton_nodes_get_their_own_components():
    """Phase A: isolated party-sides (no edges) become singleton Groups
    (and singleton Contacts) so every party-side has an entity."""
    from cleo.discovery_v2.graph import build_components, seed_singletons

    edges = [(("RT1", "buyer"), ("RT2", "buyer"), "strong")]
    components = build_components(edges)
    # RT3 has no edges — add it as a singleton.
    components = seed_singletons(components, [("RT3", "buyer")])
    assert len(components) == 3
```

Run: `pytest tests/test_discovery_v2_graph.py -v`

Expected: fails with import error.

- [ ] **Step 2: Write `cleo/discovery_v2/graph.py`**

```python
"""Union-find clustering for Group and Contact graphs.

Strong edges form connected components. Each component becomes one
Group entity (for the Group graph) or one Contact entity (for the
Contact graph). Isolated party-sides become singleton components.
"""

from __future__ import annotations
from collections import defaultdict
from typing import Dict, Iterable, List, Set, Tuple

PartySide = Tuple[str, str]
Edge = Tuple[PartySide, PartySide, str]


class _UnionFind:
    def __init__(self):
        self.parent: Dict[PartySide, PartySide] = {}
        self.rank: Dict[PartySide, int] = {}

    def add(self, x: PartySide):
        if x not in self.parent:
            self.parent[x] = x
            self.rank[x] = 0

    def find(self, x: PartySide) -> PartySide:
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        # path compression
        while self.parent[x] != root:
            nxt = self.parent[x]
            self.parent[x] = root
            x = nxt
        return root

    def union(self, a: PartySide, b: PartySide):
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1


def build_components(
    edges: Iterable[Edge], *, tier: str = "strong",
) -> Dict[int, List[PartySide]]:
    """Build connected components from edges of the given tier.

    Returns {component_id: [party_side, ...]}. Component IDs are integers
    assigned in discovery order (stable within a run, NOT across runs —
    entity ID assignment happens in `entities.py`).
    """
    uf = _UnionFind()
    for a, b, t in edges:
        if t != tier:
            continue
        uf.add(a)
        uf.add(b)
        uf.union(a, b)

    groups: Dict[PartySide, List[PartySide]] = defaultdict(list)
    for node in uf.parent:
        groups[uf.find(node)].append(node)

    return {i: sorted(nodes) for i, nodes in enumerate(groups.values())}


def seed_singletons(
    components: Dict[int, List[PartySide]], all_sides: Iterable[PartySide],
) -> Dict[int, List[PartySide]]:
    """Add any party-sides that weren't in any edge as singleton components."""
    covered: Set[PartySide] = {n for nodes in components.values() for n in nodes}
    next_id = max(components.keys(), default=-1) + 1
    out = dict(components)
    for side in all_sides:
        if side in covered:
            continue
        out[next_id] = [side]
        next_id += 1
    return out
```

Run: `pytest tests/test_discovery_v2_graph.py -v`

Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add cleo/discovery_v2/graph.py tests/test_discovery_v2_graph.py
git commit -m "feat(discovery-v2): union-find for Group and Contact graphs"
```

---

## Task 9: Entity assignment — AGR/ACN IDs + canonical display names

**Files:**
- Create: `cleo/discovery_v2/entities.py`
- Create: `tests/test_discovery_v2_entities.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_discovery_v2_entities.py`:

```python
"""Tests for entity assignment."""
import sqlite3


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE app_meta (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT);
        CREATE TABLE party_fingerprints (
            source_id TEXT, side TEXT, sale_date TEXT,
            PRIMARY KEY (source_id, side)
        );
        CREATE TABLE party_atoms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT, side TEXT,
            atom_type TEXT, atom_value TEXT, source_field TEXT
        );
        CREATE TABLE atom_groups (
            id TEXT PRIMARY KEY,
            canonical_brand TEXT, display_name TEXT,
            first_seen TEXT, last_seen TEXT,
            party_side_count INTEGER, discovered_at TEXT
        );
        CREATE TABLE atom_contacts (
            id TEXT PRIMARY KEY,
            canonical_name TEXT, display_name TEXT,
            first_seen TEXT, last_seen TEXT,
            party_side_count INTEGER, discovered_at TEXT
        );
        CREATE TABLE atom_party_entities (
            source_id TEXT, side TEXT, group_id TEXT, contact_id TEXT,
            group_link_tier TEXT, contact_link_tier TEXT,
            PRIMARY KEY (source_id, side)
        );
    """)
    return conn


def test_group_canonical_brand_is_most_common_nongeneric_phrase():
    from cleo.discovery_v2.entities import assign_group_entities

    conn = _make_db()
    # 3 party-sides, all in one Group component. brand_phrases:
    #  RT1: "kingsett capital" (non-generic)
    #  RT2: "kingsett capital" (non-generic)
    #  RT3: "holdings"         (generic — below idf threshold)
    for sid, date in [("RT1", "2020-01-01"), ("RT2", "2022-06-15"), ("RT3", "2023-03-01")]:
        conn.execute(
            "INSERT INTO party_fingerprints (source_id, side, sale_date) VALUES (?, 'buyer', ?)",
            (sid, date),
        )
    for sid, phrase in [
        ("RT1", "kingsett capital"), ("RT2", "kingsett capital"), ("RT3", "holdings"),
    ]:
        conn.execute(
            "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
            "VALUES (?, 'buyer', 'brand_phrase', ?, 'party_name')",
            (sid, phrase),
        )

    components = {0: [("RT1", "buyer"), ("RT2", "buyer"), ("RT3", "buyer")]}
    # Mock IDF: kingsett capital high, holdings low
    idf_map = {
        ("brand_phrase", "kingsett capital"): 7.0,
        ("brand_phrase", "holdings"): 1.0,
    }
    min_idf = 3.0

    ids = assign_group_entities(conn, components, idf_map, min_idf, tier_by_pair={})
    row = conn.execute(
        "SELECT id, canonical_brand, display_name, first_seen, last_seen, party_side_count "
        "FROM atom_groups"
    ).fetchone()
    assert row is not None
    assert row["canonical_brand"] == "kingsett capital"
    assert row["first_seen"] == "2020-01-01"
    assert row["last_seen"] == "2023-03-01"
    assert row["party_side_count"] == 3
    assert row["id"].startswith("AGR_")


def test_group_id_counter_persists_via_app_meta():
    from cleo.discovery_v2.entities import assign_group_entities

    conn = _make_db()
    conn.execute(
        "INSERT INTO app_meta (key, value, updated_at) VALUES ('next_agr_id', '1000', datetime('now'))"
    )
    # One party-side, one Group
    conn.execute("INSERT INTO party_fingerprints (source_id, side, sale_date) VALUES ('RT1', 'buyer', '2020-01-01')")
    conn.execute(
        "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
        "VALUES ('RT1', 'buyer', 'brand_phrase', 'kingsett capital', 'party_name')"
    )

    components = {0: [("RT1", "buyer")]}
    assign_group_entities(conn, components, {("brand_phrase", "kingsett capital"): 7.0}, 3.0, tier_by_pair={})
    row = conn.execute("SELECT id FROM atom_groups").fetchone()
    assert row["id"] == "AGR_01000"
    next_counter = conn.execute(
        "SELECT value FROM app_meta WHERE key = 'next_agr_id'"
    ).fetchone()[0]
    assert int(next_counter) == 1001
```

Run: `pytest tests/test_discovery_v2_entities.py -v`

Expected: fails.

- [ ] **Step 2: Write `cleo/discovery_v2/entities.py`**

```python
"""Entity assignment — convert components into atom_groups / atom_contacts rows.

Assigns stable IDs via app_meta counters (next_agr_id, next_acn_id)
so subsequent runs can reuse IDs. In Phase A the mapping is by the
party-side membership fingerprint; collisions produce a new ID.
v2 will add a stability layer with split/merge events.
"""

from __future__ import annotations
from collections import Counter
from typing import Dict, List, Tuple

from .config import CALIBRATION

PartySide = Tuple[str, str]


def _next_counter(conn, key: str, *, seed: int = 1) -> int:
    row = conn.execute(
        "SELECT value FROM app_meta WHERE key = ?", (key,),
    ).fetchone()
    return int(row[0]) if row else seed


def _save_counter(conn, key: str, value: int):
    conn.execute(
        "INSERT OR REPLACE INTO app_meta (key, value, updated_at) "
        "VALUES (?, ?, datetime('now'))",
        (key, str(value)),
    )


def _load_party_metadata(conn, sides: List[PartySide]):
    """Load sale_date per party-side, grouped."""
    if not sides:
        return {}
    placeholders = ",".join("(?,?)" for _ in sides)
    flat = [x for s in sides for x in s]
    rows = conn.execute(
        f"SELECT source_id, side, sale_date FROM party_fingerprints "
        f"WHERE (source_id, side) IN (VALUES {placeholders})",
        flat,
    ).fetchall()
    return {(r["source_id"], r["side"]): r["sale_date"] for r in rows}


def _load_brand_phrases(conn, sides: List[PartySide]):
    if not sides:
        return {}
    placeholders = ",".join("(?,?)" for _ in sides)
    flat = [x for s in sides for x in s]
    rows = conn.execute(
        f"SELECT source_id, side, atom_value FROM party_atoms "
        f"WHERE atom_type = 'brand_phrase' AND (source_id, side) IN (VALUES {placeholders})",
        flat,
    ).fetchall()
    out: Dict[PartySide, List[str]] = {}
    for r in rows:
        out.setdefault((r["source_id"], r["side"]), []).append(r["atom_value"])
    return out


def _load_contact_fingerprints(conn, sides: List[PartySide]):
    if not sides:
        return {}
    placeholders = ",".join("(?,?)" for _ in sides)
    flat = [x for s in sides for x in s]
    rows = conn.execute(
        f"SELECT source_id, side, contact_fingerprint FROM party_fingerprints "
        f"WHERE (source_id, side) IN (VALUES {placeholders})",
        flat,
    ).fetchall()
    return {(r["source_id"], r["side"]): r["contact_fingerprint"] for r in rows}


def _pick_canonical_brand(
    sides: List[PartySide],
    brand_phrases_by_side: Dict[PartySide, List[str]],
    idf_map: Dict[Tuple[str, str], float],
    min_idf: float,
    excluded_phrases: frozenset,
) -> str:
    """Return the most common non-generic brand_phrase across the sides,
    tie-broken by the longer phrase (more information)."""
    phrase_counter = Counter()
    for side in sides:
        for phrase in brand_phrases_by_side.get(side, []):
            if phrase in excluded_phrases:
                continue
            if idf_map.get(("brand_phrase", phrase), 0.0) < min_idf:
                continue
            phrase_counter[phrase] += 1
    if phrase_counter:
        return max(
            phrase_counter.items(), key=lambda kv: (kv[1], len(kv[0]))
        )[0]
    # All phrases were generic or excluded — fall back to any phrase we saw.
    for side in sides:
        for phrase in brand_phrases_by_side.get(side, []):
            if phrase not in excluded_phrases:
                return phrase
    return "(unlabeled)"


def assign_group_entities(
    conn, components: Dict[int, List[PartySide]],
    idf_map: Dict[Tuple[str, str], float], min_idf: float,
    tier_by_pair: Dict[Tuple[PartySide, PartySide], str],
) -> Dict[int, str]:
    """Write atom_groups + atom_party_entities rows for each component.

    Returns {component_id: agr_id}. Idempotent: caller is expected to have
    cleared the derived tables before this runs (done by the runner).
    """
    cfg = CALIBRATION
    excluded = cfg["excluded_brand_phrases"]
    counter = _next_counter(conn, "next_agr_id", seed=1)
    comp_to_id: Dict[int, str] = {}

    # Gather metadata for all sides in all components
    all_sides = [s for nodes in components.values() for s in nodes]
    dates = _load_party_metadata(conn, all_sides)
    brand_phrases = _load_brand_phrases(conn, all_sides)

    for comp_id, sides in components.items():
        canonical = _pick_canonical_brand(
            sides, brand_phrases, idf_map, min_idf, excluded,
        )
        display = canonical.title()
        agr_id = f"AGR_{counter:05d}"
        counter += 1
        comp_to_id[comp_id] = agr_id

        sale_dates = sorted(
            d for d in (dates.get(s) for s in sides) if d
        )
        first_seen = sale_dates[0] if sale_dates else None
        last_seen = sale_dates[-1] if sale_dates else None

        conn.execute(
            "INSERT INTO atom_groups "
            "(id, canonical_brand, display_name, first_seen, last_seen, party_side_count) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (agr_id, canonical, display, first_seen, last_seen, len(sides)),
        )
        # Write atom_party_entities for each member (group half only here;
        # contact half populated by assign_contact_entities).
        for (source_id, side) in sides:
            conn.execute(
                "INSERT OR IGNORE INTO atom_party_entities "
                "(source_id, side, group_id, group_link_tier) "
                "VALUES (?, ?, ?, 'strong')",
                (source_id, side, agr_id),
            )
            conn.execute(
                "UPDATE atom_party_entities SET group_id = ?, group_link_tier = 'strong' "
                "WHERE source_id = ? AND side = ?",
                (agr_id, source_id, side),
            )

    _save_counter(conn, "next_agr_id", counter)
    conn.commit()
    return comp_to_id


def assign_contact_entities(
    conn, components: Dict[int, List[PartySide]],
    tier_by_pair: Dict[Tuple[PartySide, PartySide], str],
) -> Dict[int, str]:
    """Write atom_contacts + update atom_party_entities.contact_id for each component.

    Canonical name = most common contact_fingerprint in the component.
    """
    counter = _next_counter(conn, "next_acn_id", seed=1)
    comp_to_id: Dict[int, str] = {}

    all_sides = [s for nodes in components.values() for s in nodes]
    fingerprints = _load_contact_fingerprints(conn, all_sides)
    dates = _load_party_metadata(conn, all_sides)

    for comp_id, sides in components.items():
        fps = [fingerprints.get(s) for s in sides]
        fps = [fp for fp in fps if fp]
        if not fps:
            continue  # singleton with no contact — skip; party still has a Group
        counter_fp = Counter(fps).most_common(1)[0][0]
        display = " ".join(w.capitalize() for w in counter_fp.split())
        acn_id = f"ACN_{counter:05d}"
        counter += 1
        comp_to_id[comp_id] = acn_id

        sale_dates = sorted(d for d in (dates.get(s) for s in sides) if d)
        first_seen = sale_dates[0] if sale_dates else None
        last_seen = sale_dates[-1] if sale_dates else None

        conn.execute(
            "INSERT INTO atom_contacts "
            "(id, canonical_name, display_name, first_seen, last_seen, party_side_count) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (acn_id, counter_fp, display, first_seen, last_seen, len(sides)),
        )
        for (source_id, side) in sides:
            conn.execute(
                "INSERT OR IGNORE INTO atom_party_entities "
                "(source_id, side) VALUES (?, ?)",
                (source_id, side),
            )
            conn.execute(
                "UPDATE atom_party_entities SET contact_id = ?, contact_link_tier = 'strong' "
                "WHERE source_id = ? AND side = ?",
                (acn_id, source_id, side),
            )

    _save_counter(conn, "next_acn_id", counter)
    conn.commit()
    return comp_to_id
```

Run: `pytest tests/test_discovery_v2_entities.py -v`

Expected: both tests pass.

- [ ] **Step 3: Commit**

```bash
git add cleo/discovery_v2/entities.py tests/test_discovery_v2_entities.py
git commit -m "feat(discovery-v2): entity assignment with persistent AGR/ACN IDs"
```

---

## Task 10: Timeline materialization

**Files:**
- Create: `cleo/discovery_v2/timelines.py`
- Create: `tests/test_discovery_v2_timelines.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_discovery_v2_timelines.py`:

```python
"""Tests for timeline materialization."""
import sqlite3


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE party_fingerprints (
            source_id TEXT, side TEXT, sale_date TEXT,
            street_number TEXT, street_name TEXT, street_suffix TEXT,
            postal TEXT, phone TEXT, contact_fingerprint TEXT,
            PRIMARY KEY (source_id, side)
        );
        CREATE TABLE atom_party_entities (
            source_id TEXT, side TEXT, group_id TEXT, contact_id TEXT,
            group_link_tier TEXT, contact_link_tier TEXT,
            PRIMARY KEY (source_id, side)
        );
        CREATE TABLE atom_group_addresses (
            group_id TEXT, postal TEXT,
            street_number TEXT, street_name TEXT, street_suffix TEXT,
            first_seen TEXT, last_seen TEXT, n_observations INTEGER
        );
        CREATE TABLE atom_group_phones (
            group_id TEXT, phone TEXT,
            first_seen TEXT, last_seen TEXT, n_observations INTEGER
        );
        CREATE TABLE atom_group_contacts (
            group_id TEXT, contact_id TEXT,
            first_seen TEXT, last_seen TEXT, n_observations INTEGER
        );
        CREATE TABLE atom_contact_groups (
            contact_id TEXT, group_id TEXT,
            first_seen TEXT, last_seen TEXT, n_observations INTEGER
        );
        CREATE TABLE atom_contact_addresses (
            contact_id TEXT, postal TEXT,
            street_number TEXT, street_name TEXT, street_suffix TEXT,
            first_seen TEXT, last_seen TEXT, n_observations INTEGER
        );
    """)
    return conn


def test_group_addresses_timeline_captures_date_ranges():
    from cleo.discovery_v2.timelines import materialize_timelines

    conn = _make_db()
    # Same Group: 3 party-sides at 161 Bay (2000-2010), 4 at 66 Wellington (2012-2020)
    rows = [
        ("RT1", "buyer", "2000-01-01", "161", "bay", "street", "M5J2S1"),
        ("RT2", "buyer", "2005-06-15", "161", "bay", "street", "M5J2S1"),
        ("RT3", "buyer", "2010-03-30", "161", "bay", "street", "M5J2S1"),
        ("RT4", "buyer", "2012-04-01", "66", "wellington", "street", "M5K1H6"),
        ("RT5", "buyer", "2015-08-01", "66", "wellington", "street", "M5K1H6"),
        ("RT6", "buyer", "2018-11-30", "66", "wellington", "street", "M5K1H6"),
        ("RT7", "buyer", "2020-06-01", "66", "wellington", "street", "M5K1H6"),
    ]
    for sid, side, date, num, name, suf, postal in rows:
        conn.execute(
            "INSERT INTO party_fingerprints "
            "(source_id, side, sale_date, street_number, street_name, street_suffix, postal) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (sid, side, date, num, name, suf, postal),
        )
        conn.execute(
            "INSERT INTO atom_party_entities (source_id, side, group_id) VALUES (?, ?, 'AGR_00001')",
            (sid, side),
        )
    conn.commit()

    materialize_timelines(conn)

    rows = conn.execute(
        "SELECT street_number, first_seen, last_seen, n_observations "
        "FROM atom_group_addresses WHERE group_id = 'AGR_00001' "
        "ORDER BY first_seen"
    ).fetchall()
    assert len(rows) == 2
    assert rows[0]["street_number"] == "161"
    assert rows[0]["first_seen"] == "2000-01-01"
    assert rows[0]["last_seen"] == "2010-03-30"
    assert rows[0]["n_observations"] == 3
    assert rows[1]["street_number"] == "66"
    assert rows[1]["n_observations"] == 4


def test_contact_groups_timeline_bridges_multiple_groups():
    """Same Contact appearing at RioCan 2004-2020 and First Capital 2000-2003."""
    from cleo.discovery_v2.timelines import materialize_timelines

    conn = _make_db()
    # RT1 at First Capital (AGR_01), RT2 at RioCan (AGR_02) — both Andrew Duncan
    for sid, date, group, cfp in [
        ("RT1", "2000-01-01", "AGR_01", "andrew duncan"),
        ("RT2", "2003-06-15", "AGR_01", "andrew duncan"),
        ("RT3", "2004-03-01", "AGR_02", "andrew duncan"),
        ("RT4", "2020-06-01", "AGR_02", "andrew duncan"),
    ]:
        conn.execute(
            "INSERT INTO party_fingerprints "
            "(source_id, side, sale_date, contact_fingerprint) VALUES (?, 'buyer', ?, ?)",
            (sid, date, cfp),
        )
        conn.execute(
            "INSERT INTO atom_party_entities (source_id, side, group_id, contact_id) "
            "VALUES (?, 'buyer', ?, 'ACN_0001')",
            (sid, group),
        )
    conn.commit()

    materialize_timelines(conn)

    rows = conn.execute(
        "SELECT group_id, first_seen, last_seen, n_observations "
        "FROM atom_contact_groups WHERE contact_id = 'ACN_0001' "
        "ORDER BY first_seen"
    ).fetchall()
    assert len(rows) == 2
    assert rows[0]["group_id"] == "AGR_01"
    assert rows[0]["first_seen"] == "2000-01-01"
    assert rows[0]["last_seen"] == "2003-06-15"
    assert rows[1]["group_id"] == "AGR_02"
    assert rows[1]["first_seen"] == "2004-03-01"
```

Run: `pytest tests/test_discovery_v2_timelines.py -v`

Expected: fails with import error.

- [ ] **Step 2: Write `cleo/discovery_v2/timelines.py`**

```python
"""Materialize per-Group and per-Contact timelines from atom_party_entities.

Drops and rebuilds every run. Called after entities are assigned.
"""

from __future__ import annotations


def materialize_timelines(conn):
    """Rebuild all timeline tables from atom_party_entities."""
    # Wipe
    for tbl in (
        "atom_group_addresses", "atom_group_phones", "atom_group_contacts",
        "atom_contact_groups", "atom_contact_addresses",
    ):
        conn.execute(f"DELETE FROM {tbl}")

    # Group-level timelines
    conn.execute("""
        INSERT INTO atom_group_addresses
            (group_id, postal, street_number, street_name, street_suffix,
             first_seen, last_seen, n_observations)
        SELECT ape.group_id,
               pf.postal, pf.street_number, pf.street_name, pf.street_suffix,
               MIN(pf.sale_date), MAX(pf.sale_date), COUNT(*)
        FROM atom_party_entities ape
        JOIN party_fingerprints pf
            ON pf.source_id = ape.source_id AND pf.side = ape.side
        WHERE ape.group_id IS NOT NULL
          AND (pf.street_number IS NOT NULL OR pf.postal IS NOT NULL)
        GROUP BY ape.group_id, pf.postal, pf.street_number, pf.street_name, pf.street_suffix
    """)

    conn.execute("""
        INSERT INTO atom_group_phones
            (group_id, phone, first_seen, last_seen, n_observations)
        SELECT ape.group_id, pf.phone, MIN(pf.sale_date), MAX(pf.sale_date), COUNT(*)
        FROM atom_party_entities ape
        JOIN party_fingerprints pf
            ON pf.source_id = ape.source_id AND pf.side = ape.side
        WHERE ape.group_id IS NOT NULL AND pf.phone IS NOT NULL AND pf.phone != ''
        GROUP BY ape.group_id, pf.phone
    """)

    conn.execute("""
        INSERT INTO atom_group_contacts
            (group_id, contact_id, first_seen, last_seen, n_observations)
        SELECT ape.group_id, ape.contact_id,
               MIN(pf.sale_date), MAX(pf.sale_date), COUNT(*)
        FROM atom_party_entities ape
        JOIN party_fingerprints pf
            ON pf.source_id = ape.source_id AND pf.side = ape.side
        WHERE ape.group_id IS NOT NULL AND ape.contact_id IS NOT NULL
        GROUP BY ape.group_id, ape.contact_id
    """)

    # Contact-level timelines
    conn.execute("""
        INSERT INTO atom_contact_groups
            (contact_id, group_id, first_seen, last_seen, n_observations)
        SELECT ape.contact_id, ape.group_id,
               MIN(pf.sale_date), MAX(pf.sale_date), COUNT(*)
        FROM atom_party_entities ape
        JOIN party_fingerprints pf
            ON pf.source_id = ape.source_id AND pf.side = ape.side
        WHERE ape.contact_id IS NOT NULL AND ape.group_id IS NOT NULL
        GROUP BY ape.contact_id, ape.group_id
    """)

    conn.execute("""
        INSERT INTO atom_contact_addresses
            (contact_id, postal, street_number, street_name, street_suffix,
             first_seen, last_seen, n_observations)
        SELECT ape.contact_id,
               pf.postal, pf.street_number, pf.street_name, pf.street_suffix,
               MIN(pf.sale_date), MAX(pf.sale_date), COUNT(*)
        FROM atom_party_entities ape
        JOIN party_fingerprints pf
            ON pf.source_id = ape.source_id AND pf.side = ape.side
        WHERE ape.contact_id IS NOT NULL
          AND (pf.street_number IS NOT NULL OR pf.postal IS NOT NULL)
        GROUP BY ape.contact_id, pf.postal, pf.street_number, pf.street_name, pf.street_suffix
    """)

    conn.commit()
```

Run: `pytest tests/test_discovery_v2_timelines.py -v`

Expected: both tests pass.

- [ ] **Step 3: Commit**

```bash
git add cleo/discovery_v2/timelines.py tests/test_discovery_v2_timelines.py
git commit -m "feat(discovery-v2): materialize Group and Contact timelines"
```

---

## Task 11: JV relationship detection (multi-brand party-sides)

**Files:**
- Create: `cleo/discovery_v2/relationships.py`
- Create: `tests/test_discovery_v2_relationships.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_discovery_v2_relationships.py`:

```python
"""Tests for JV relationship detection."""
import sqlite3


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE party_fingerprints (
            source_id TEXT, side TEXT, sale_date TEXT,
            PRIMARY KEY (source_id, side)
        );
        CREATE TABLE party_atoms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT, side TEXT,
            atom_type TEXT, atom_value TEXT, source_field TEXT
        );
        CREATE TABLE atom_party_entities (
            source_id TEXT, side TEXT, group_id TEXT, contact_id TEXT,
            group_link_tier TEXT, contact_link_tier TEXT,
            PRIMARY KEY (source_id, side)
        );
        CREATE TABLE atom_group_relationships (
            group_a_id TEXT, group_b_id TEXT, kind TEXT,
            first_seen TEXT, last_seen TEXT, n_party_sides INTEGER,
            PRIMARY KEY (group_a_id, group_b_id, kind)
        );
    """)
    return conn


def test_multi_brand_phrase_party_side_emits_jv_edge():
    from cleo.discovery_v2.relationships import detect_jv_relationships

    conn = _make_db()
    # RT1 has both "kingsett capital" and "canderel" brand_phrases; RT1's
    # primary Group is AGR_01 (kingsett). The JV edge should also link to
    # the canderel Group AGR_02 if canderel appears on any other party-side.
    conn.execute(
        "INSERT INTO party_fingerprints (source_id, side, sale_date) VALUES ('RT1', 'buyer', '2015-06-01')"
    )
    conn.execute(
        "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
        "VALUES ('RT1', 'buyer', 'brand_phrase', 'kingsett capital', 'party_name')"
    )
    conn.execute(
        "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
        "VALUES ('RT1', 'buyer', 'brand_phrase', 'canderel', 'companies_json')"
    )
    conn.execute(
        "INSERT INTO atom_party_entities (source_id, side, group_id) "
        "VALUES ('RT1', 'buyer', 'AGR_01')"
    )
    # Canderel exists as AGR_02 via another party-side
    conn.execute(
        "INSERT INTO party_fingerprints (source_id, side, sale_date) VALUES ('RT2', 'buyer', '2017-03-01')"
    )
    conn.execute(
        "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
        "VALUES ('RT2', 'buyer', 'brand_phrase', 'canderel', 'party_name')"
    )
    conn.execute(
        "INSERT INTO atom_party_entities (source_id, side, group_id) VALUES ('RT2', 'buyer', 'AGR_02')"
    )
    conn.commit()

    detect_jv_relationships(conn)

    rows = conn.execute(
        "SELECT group_a_id, group_b_id, kind, n_party_sides FROM atom_group_relationships"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["kind"] == "jv"
    assert {rows[0]["group_a_id"], rows[0]["group_b_id"]} == {"AGR_01", "AGR_02"}
    assert rows[0]["n_party_sides"] == 1


def test_single_brand_party_side_emits_no_jv():
    from cleo.discovery_v2.relationships import detect_jv_relationships

    conn = _make_db()
    conn.execute(
        "INSERT INTO party_fingerprints (source_id, side, sale_date) VALUES ('RT1', 'buyer', '2015-06-01')"
    )
    conn.execute(
        "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
        "VALUES ('RT1', 'buyer', 'brand_phrase', 'kingsett capital', 'party_name')"
    )
    conn.execute(
        "INSERT INTO atom_party_entities (source_id, side, group_id) VALUES ('RT1', 'buyer', 'AGR_01')"
    )
    conn.commit()

    detect_jv_relationships(conn)

    rows = conn.execute("SELECT * FROM atom_group_relationships").fetchall()
    assert rows == []
```

Run: `pytest tests/test_discovery_v2_relationships.py -v`

Expected: fails.

- [ ] **Step 2: Write `cleo/discovery_v2/relationships.py`**

```python
"""Derived Group-to-Group relationships.

Phase A handles JV only: a single party-side carrying two or more
distinct, non-generic brand_phrases that map to different atom_groups
→ JV edge between those Groups.

Relies on the brand_phrase → atom_groups mapping already established
by entities.assign_group_entities (where each Group's canonical_brand
is its dominant non-generic phrase).
"""

from __future__ import annotations
from collections import defaultdict
from typing import Dict, Set, Tuple

from .config import CALIBRATION


def _build_phrase_to_group_map(conn) -> Dict[str, str]:
    """Map each distinct brand_phrase to the Group whose canonical_brand
    most closely represents it. For Phase A we use exact phrase → Group
    via canonical_brand. Phrases that aren't anyone's canonical drop out."""
    return {
        row["canonical_brand"]: row["id"]
        for row in conn.execute(
            "SELECT id, canonical_brand FROM atom_groups WHERE canonical_brand IS NOT NULL"
        )
    }


def detect_jv_relationships(conn):
    """Find party-sides with 2+ distinct non-generic brand_phrases and
    emit pairwise JV edges between the Groups those phrases represent."""
    conn.execute("DELETE FROM atom_group_relationships")

    excluded = CALIBRATION["excluded_brand_phrases"]
    phrase_to_group = _build_phrase_to_group_map(conn)

    # Gather party-sides with their brand_phrase sets
    sides_phrases: Dict[Tuple[str, str], Set[str]] = defaultdict(set)
    for row in conn.execute(
        "SELECT source_id, side, atom_value FROM party_atoms WHERE atom_type = 'brand_phrase'"
    ):
        if row["atom_value"] in excluded:
            continue
        sides_phrases[(row["source_id"], row["side"])].add(row["atom_value"])

    # Aggregate pairwise (group_a, group_b) JV observations
    pair_stats: Dict[Tuple[str, str], Dict[str, object]] = defaultdict(
        lambda: {"n": 0, "first": None, "last": None}
    )
    dates = {
        (r["source_id"], r["side"]): r["sale_date"]
        for r in conn.execute("SELECT source_id, side, sale_date FROM party_fingerprints")
    }

    for (sid, side), phrases in sides_phrases.items():
        if len(phrases) < 2:
            continue
        groups = {phrase_to_group[p] for p in phrases if p in phrase_to_group}
        if len(groups) < 2:
            continue
        groups_sorted = sorted(groups)
        date = dates.get((sid, side))
        for i in range(len(groups_sorted)):
            for j in range(i + 1, len(groups_sorted)):
                key = (groups_sorted[i], groups_sorted[j])
                stats = pair_stats[key]
                stats["n"] += 1
                if date:
                    if stats["first"] is None or date < stats["first"]:
                        stats["first"] = date
                    if stats["last"] is None or date > stats["last"]:
                        stats["last"] = date

    for (a, b), stats in pair_stats.items():
        conn.execute(
            "INSERT INTO atom_group_relationships "
            "(group_a_id, group_b_id, kind, first_seen, last_seen, n_party_sides) "
            "VALUES (?, ?, 'jv', ?, ?, ?)",
            (a, b, stats["first"], stats["last"], stats["n"]),
        )
    conn.commit()
```

Run: `pytest tests/test_discovery_v2_relationships.py -v`

Expected: both tests pass.

- [ ] **Step 3: Commit**

```bash
git add cleo/discovery_v2/relationships.py tests/test_discovery_v2_relationships.py
git commit -m "feat(discovery-v2): JV relationship detection from multi-brand party-sides"
```

---

## Task 12: Runner — orchestrator + module entry point

**Files:**
- Create: `cleo/discovery_v2/runner.py`
- Create: `cleo/discovery_v2/__main__.py`
- Create: `tests/test_discovery_v2_runner.py`

- [ ] **Step 1: Write the failing integration test**

Create `tests/test_discovery_v2_runner.py`:

```python
"""End-to-end runner integration test."""
import sqlite3


def _make_db_with_two_kingsett_sides():
    """Minimal corpus: two party-sides sharing 'kingsett' brand_token."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    # Core derived tables from the compiler
    conn.executescript("""
        CREATE TABLE app_meta (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT);
        CREATE TABLE party_fingerprints (
            source_id TEXT, side TEXT,
            street_number TEXT, street_name TEXT, street_suffix TEXT,
            street_direction TEXT, suite_type TEXT, suite_number TEXT,
            city TEXT, province TEXT, postal TEXT, postal_raw TEXT,
            country TEXT, phone TEXT, contact_fingerprint TEXT,
            sale_date TEXT, computed_at TEXT,
            PRIMARY KEY (source_id, side)
        );
        CREATE TABLE party_atoms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT, side TEXT,
            atom_type TEXT, atom_value TEXT, source_field TEXT
        );
    """)
    # Apply migration 007's table creates (inline, subset)
    conn.executescript("""
        CREATE TABLE atom_groups (
            id TEXT PRIMARY KEY, canonical_brand TEXT, display_name TEXT,
            first_seen TEXT, last_seen TEXT, party_side_count INTEGER,
            discovered_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE atom_contacts (
            id TEXT PRIMARY KEY, canonical_name TEXT, display_name TEXT,
            first_seen TEXT, last_seen TEXT, party_side_count INTEGER,
            discovered_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE atom_party_entities (
            source_id TEXT, side TEXT, group_id TEXT, contact_id TEXT,
            group_link_tier TEXT, contact_link_tier TEXT,
            PRIMARY KEY (source_id, side)
        );
        CREATE TABLE atom_group_addresses (group_id TEXT, postal TEXT,
            street_number TEXT, street_name TEXT, street_suffix TEXT,
            first_seen TEXT, last_seen TEXT, n_observations INTEGER);
        CREATE TABLE atom_group_phones (group_id TEXT, phone TEXT,
            first_seen TEXT, last_seen TEXT, n_observations INTEGER);
        CREATE TABLE atom_group_contacts (group_id TEXT, contact_id TEXT,
            first_seen TEXT, last_seen TEXT, n_observations INTEGER);
        CREATE TABLE atom_contact_groups (contact_id TEXT, group_id TEXT,
            first_seen TEXT, last_seen TEXT, n_observations INTEGER);
        CREATE TABLE atom_contact_addresses (contact_id TEXT, postal TEXT,
            street_number TEXT, street_name TEXT, street_suffix TEXT,
            first_seen TEXT, last_seen TEXT, n_observations INTEGER);
        CREATE TABLE atom_group_relationships (
            group_a_id TEXT, group_b_id TEXT, kind TEXT,
            first_seen TEXT, last_seen TEXT, n_party_sides INTEGER,
            PRIMARY KEY (group_a_id, group_b_id, kind)
        );
        CREATE TABLE atom_discovery_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            config_version TEXT, config_snapshot TEXT,
            ran_at TEXT DEFAULT (datetime('now')),
            n_party_sides INTEGER, n_groups INTEGER, n_contacts INTEGER,
            audit_metrics TEXT, notes TEXT
        );
    """)
    # Seed two party-sides both carrying 'kingsett' token + 'kingsett capital' phrase
    for sid, date in [("RT1", "2020-01-01"), ("RT2", "2022-06-15")]:
        conn.execute(
            "INSERT INTO party_fingerprints (source_id, side, sale_date) "
            "VALUES (?, 'buyer', ?)",
            (sid, date),
        )
        conn.execute(
            "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
            "VALUES (?, 'buyer', 'brand_token', 'kingsett', 'party_name')",
            (sid,),
        )
        conn.execute(
            "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
            "VALUES (?, 'buyer', 'brand_phrase', 'kingsett capital', 'party_name')",
            (sid,),
        )
    conn.commit()
    return conn


def test_runner_produces_one_group_from_two_kingsett_sides():
    from cleo.discovery_v2.runner import run_discovery

    conn = _make_db_with_two_kingsett_sides()
    run_discovery(conn)

    groups = conn.execute("SELECT id, canonical_brand, party_side_count FROM atom_groups").fetchall()
    assert len(groups) == 1
    assert groups[0]["canonical_brand"] == "kingsett capital"
    assert groups[0]["party_side_count"] == 2

    party_sides = conn.execute("SELECT group_id FROM atom_party_entities").fetchall()
    assert len(party_sides) == 2
    assert all(p["group_id"] == groups[0]["id"] for p in party_sides)

    # Runs table logs the event
    runs = conn.execute("SELECT n_party_sides, n_groups FROM atom_discovery_runs").fetchall()
    assert len(runs) == 1
    assert runs[0]["n_party_sides"] == 2
    assert runs[0]["n_groups"] == 1
```

Run: `pytest tests/test_discovery_v2_runner.py -v`

Expected: fails.

- [ ] **Step 2: Write `cleo/discovery_v2/runner.py`**

```python
"""Orchestrator — run the full Phase A discovery pass.

Order:
  1. Wipe derived atom_* tables (except atom_discovery_runs).
  2. Compute IDF map.
  3. Generate candidate pairs (blocking).
  4. Score pairs → Strong Group and Contact edges.
  5. Union-find → components.
  6. Assign entities (atom_groups, atom_contacts).
  7. Materialize timelines.
  8. Detect JV relationships.
  9. Log the run to atom_discovery_runs.
"""

from __future__ import annotations
import json
from collections import defaultdict

from .config import CALIBRATION
from .idf import compute_idf_map
from .blocking import generate_candidate_pairs
from .scoring import score_pair
from .graph import build_components, seed_singletons
from .entities import assign_group_entities, assign_contact_entities
from .timelines import materialize_timelines
from .relationships import detect_jv_relationships


def _wipe_derived(conn):
    for tbl in (
        "atom_group_relationships",
        "atom_contact_addresses", "atom_contact_groups",
        "atom_group_contacts", "atom_group_phones", "atom_group_addresses",
        "atom_party_entities",
        "atom_contacts", "atom_groups",
    ):
        conn.execute(f"DELETE FROM {tbl}")


def _all_party_sides(conn):
    return [
        (r["source_id"], r["side"])
        for r in conn.execute("SELECT source_id, side FROM party_fingerprints")
    ]


def _pairs_from_blocking(conn, idf_map):
    """Aggregate candidate-pair rows by (a, b) into {pair: [(atom_type, value, idf), ...]}."""
    pairs = defaultdict(list)
    for (sid_a, side_a, sid_b, side_b, atom_type, atom_value) in generate_candidate_pairs(
        conn, idf_map
    ):
        a, b = (sid_a, side_a), (sid_b, side_b)
        if a > b:
            a, b = b, a
        idf = idf_map.get((atom_type, atom_value), 0.0)
        pairs[(a, b)].append((atom_type, atom_value, idf))
    return pairs


def run_discovery(conn, *, verbose: bool = True):
    if verbose:
        print(f"Phase A discovery run: config {CALIBRATION['version']}")

    _wipe_derived(conn)

    idf_map = compute_idf_map(conn)
    if verbose:
        print(f"  IDF map: {len(idf_map):,} (atom_type, value) entries")

    pairs = _pairs_from_blocking(conn, idf_map)
    if verbose:
        print(f"  Candidate pairs: {len(pairs):,}")

    group_edges = []
    contact_edges = []
    for (a, b), match_atoms in pairs.items():
        result = score_pair(match_atoms)
        if result["group_tier"] == "strong":
            group_edges.append((a, b, "strong"))
        if result["contact_tier"] == "strong":
            contact_edges.append((a, b, "strong"))
    if verbose:
        print(f"  Strong Group edges: {len(group_edges):,}")
        print(f"  Strong Contact edges: {len(contact_edges):,}")

    all_sides = _all_party_sides(conn)
    group_components = seed_singletons(build_components(group_edges), all_sides)
    contact_components = build_components(contact_edges)  # no singletons for contacts
    if verbose:
        print(f"  Group components: {len(group_components):,}")
        print(f"  Contact components: {len(contact_components):,}")

    assign_group_entities(
        conn, group_components, idf_map,
        min_idf=CALIBRATION["exact_brand_token"]["min_idf"],
        tier_by_pair={},
    )
    assign_contact_entities(conn, contact_components, tier_by_pair={})

    materialize_timelines(conn)
    detect_jv_relationships(conn)

    n_party_sides = conn.execute("SELECT COUNT(*) FROM party_fingerprints").fetchone()[0]
    n_groups = conn.execute("SELECT COUNT(*) FROM atom_groups").fetchone()[0]
    n_contacts = conn.execute("SELECT COUNT(*) FROM atom_contacts").fetchone()[0]

    conn.execute(
        "INSERT INTO atom_discovery_runs "
        "(config_version, config_snapshot, n_party_sides, n_groups, n_contacts) "
        "VALUES (?, ?, ?, ?, ?)",
        (CALIBRATION["version"], _safe_dumps(CALIBRATION),
         n_party_sides, n_groups, n_contacts),
    )
    conn.commit()

    if verbose:
        print(f"  Wrote {n_groups:,} Groups, {n_contacts:,} Contacts.")
    return {"n_party_sides": n_party_sides, "n_groups": n_groups, "n_contacts": n_contacts}


def _safe_dumps(obj):
    return json.dumps(obj, default=lambda v: list(v) if isinstance(v, (set, frozenset)) else str(v))
```

- [ ] **Step 3: Write `cleo/discovery_v2/__main__.py`**

```python
"""Developer entry point — `python -m cleo.discovery_v2`.

NOT a user surface. CLAUDE.md reserves user-facing operations for the UI
(admin panel lands in Phase E). This exists for developer workflow:
calibration, debugging, and one-off experiments.
"""

from __future__ import annotations
from cleo.database.connection import get_connection
from cleo.discovery_v2.runner import run_discovery


def main():
    conn = get_connection()
    run_discovery(conn)
    conn.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the integration test**

Run: `pytest tests/test_discovery_v2_runner.py -v`

Expected: passes.

- [ ] **Step 5: Commit**

```bash
git add cleo/discovery_v2/runner.py cleo/discovery_v2/__main__.py tests/test_discovery_v2_runner.py
git commit -m "feat(discovery-v2): runner orchestrator + dev entry point"
```

---

## Task 13: Eval harness — audit recall and purity metrics

**Files:**
- Create: `cleo/discovery_v2/eval.py`
- Create: `tests/test_discovery_v2_eval.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_discovery_v2_eval.py`:

```python
"""Tests for eval metrics against audit portfolios."""


def test_audit_recall_and_purity_perfect_match():
    """When every audit party-side lands in the same atom Group, and that
    Group contains only audit-members, recall and purity are both 100%."""
    from cleo.discovery_v2.eval import compute_audit_metrics

    party_entities = {
        ("RT1", "buyer"): "AGR_0001",
        ("RT2", "buyer"): "AGR_0001",
        ("RT3", "seller"): "AGR_0001",
    }
    audit_parties = [
        {"source_id": "RT1", "side": "buyer"},
        {"source_id": "RT2", "side": "buyer"},
        {"source_id": "RT3", "side": "seller"},
    ]
    metrics = compute_audit_metrics("test-audit", audit_parties, party_entities)
    assert metrics["recall"] == 1.0
    assert metrics["purity"] == 1.0
    assert metrics["dominant_group_id"] == "AGR_0001"
    assert metrics["dominant_group_size"] == 3


def test_audit_recall_less_than_1_when_members_split():
    from cleo.discovery_v2.eval import compute_audit_metrics

    party_entities = {
        ("RT1", "buyer"): "AGR_0001",
        ("RT2", "buyer"): "AGR_0001",
        ("RT3", "seller"): "AGR_0002",  # split off
    }
    audit_parties = [
        {"source_id": "RT1", "side": "buyer"},
        {"source_id": "RT2", "side": "buyer"},
        {"source_id": "RT3", "side": "seller"},
    ]
    metrics = compute_audit_metrics("test-audit", audit_parties, party_entities)
    assert metrics["recall"] == 2 / 3
    assert metrics["dominant_group_size"] == 2


def test_audit_purity_less_than_1_when_group_contains_nonaudit_members():
    from cleo.discovery_v2.eval import compute_audit_metrics

    party_entities = {
        ("RT1", "buyer"): "AGR_0001",
        ("RT2", "buyer"): "AGR_0001",
        ("RT_other", "buyer"): "AGR_0001",  # same group, non-audit member
    }
    audit_parties = [
        {"source_id": "RT1", "side": "buyer"},
        {"source_id": "RT2", "side": "buyer"},
    ]
    metrics = compute_audit_metrics("test-audit", audit_parties, party_entities)
    assert metrics["recall"] == 1.0
    assert metrics["purity"] == 2 / 3
```

Run: `pytest tests/test_discovery_v2_eval.py -v`

Expected: fails.

- [ ] **Step 2: Write `cleo/discovery_v2/eval.py`**

```python
"""Evaluation harness — measure discovery quality against the 8 audit portfolios.

Metrics per audit:
  - recall: fraction of audit party-sides landing in the dominant discovered Group
  - purity: fraction of the dominant Group that came from the audit
  - dominant_group_id, dominant_group_size

Also renders a markdown report to docs/discovery-audit/YYYY-MM-DD-run-N.md.
"""

from __future__ import annotations
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Dict, List, Tuple


def compute_audit_metrics(
    audit_slug: str,
    audit_parties: List[dict],
    party_entities: Dict[Tuple[str, str], str],
) -> dict:
    """Return recall/purity for one audit portfolio."""
    n_audit = len(audit_parties)
    if n_audit == 0:
        return {"audit_slug": audit_slug, "n_audit": 0, "recall": 0.0,
                "purity": 0.0, "dominant_group_id": None, "dominant_group_size": 0}

    audit_keys = {(p["source_id"], p["side"]) for p in audit_parties}
    group_of_audit = [party_entities.get(k) for k in audit_keys]
    group_of_audit = [g for g in group_of_audit if g]

    if not group_of_audit:
        return {"audit_slug": audit_slug, "n_audit": n_audit, "recall": 0.0,
                "purity": 0.0, "dominant_group_id": None, "dominant_group_size": 0}

    dominant_group_id, dominant_in_audit = Counter(group_of_audit).most_common(1)[0]
    recall = dominant_in_audit / n_audit

    # Purity: of everyone in the dominant group globally, how many are from this audit?
    dominant_total = sum(1 for g in party_entities.values() if g == dominant_group_id)
    purity = dominant_in_audit / dominant_total if dominant_total > 0 else 0.0

    return {
        "audit_slug": audit_slug,
        "n_audit": n_audit,
        "recall": recall,
        "purity": purity,
        "dominant_group_id": dominant_group_id,
        "dominant_group_size": dominant_total,
    }


def run_audit_eval(conn, audit_docs_root: str) -> List[dict]:
    """Run eval against all audits under `audit_docs_root`. Returns metrics list."""
    from cleo.labeling.audit_parser import list_audits

    audits = list_audits(Path(audit_docs_root))
    party_entities = {
        (r["source_id"], r["side"]): r["group_id"]
        for r in conn.execute(
            "SELECT source_id, side, group_id FROM atom_party_entities "
            "WHERE group_id IS NOT NULL"
        )
    }

    results = []
    for audit in audits:
        metrics = compute_audit_metrics(audit.slug, audit.parties, party_entities)
        results.append(metrics)
    return results


def render_report(metrics_list: List[dict], run_summary: dict, audit_docs_root: str) -> Path:
    """Write a markdown report to docs/discovery-audit/YYYY-MM-DD-run.md."""
    today = date.today().isoformat()
    out_dir = Path(audit_docs_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{today}-phase-a-eval.md"

    lines = [
        f"# Discovery Phase A Eval — {today}",
        "",
        f"- Party-sides: {run_summary['n_party_sides']:,}",
        f"- Groups: {run_summary['n_groups']:,}",
        f"- Contacts: {run_summary['n_contacts']:,}",
        "",
        "## Per-audit metrics",
        "",
        "| audit | n_audit | recall | purity | dominant_group | group_size |",
        "|---|---|---|---|---|---|",
    ]
    for m in metrics_list:
        lines.append(
            f"| {m['audit_slug']} | {m['n_audit']} | "
            f"{m['recall']:.0%} | {m['purity']:.0%} | "
            f"{m['dominant_group_id'] or '—'} | {m['dominant_group_size']} |"
        )
    out_path.write_text("\n".join(lines) + "\n")
    return out_path
```

Run: `pytest tests/test_discovery_v2_eval.py -v`

Expected: all three tests pass.

- [ ] **Step 3: Commit**

```bash
git add cleo/discovery_v2/eval.py tests/test_discovery_v2_eval.py
git commit -m "feat(discovery-v2): audit recall/purity eval harness + markdown report"
```

---

## Task 14: End-to-end run against real data + first eval report

**Files:**
- Modify: `cleo/discovery_v2/__main__.py` (tie in eval harness)
- New: `docs/discovery-audit/YYYY-MM-DD-phase-a-eval.md` (generated artifact — committed as the first calibration snapshot)

- [ ] **Step 1: Wire eval into the runner entry point**

Replace `cleo/discovery_v2/__main__.py` with:

```python
"""Developer entry point — `python -m cleo.discovery_v2`."""

from __future__ import annotations
from cleo.database.connection import get_connection
from cleo.discovery_v2.runner import run_discovery
from cleo.discovery_v2.eval import run_audit_eval, render_report
from cleo.discovery_v2.config import CALIBRATION


def main():
    conn = get_connection()
    summary = run_discovery(conn)
    print()
    print("Running eval harness against audit portfolios...")
    metrics = run_audit_eval(conn, CALIBRATION["audit_docs_root"])
    report_path = render_report(metrics, summary, CALIBRATION["audit_docs_root"])
    print(f"Eval report: {report_path}")
    for m in metrics:
        print(f"  {m['audit_slug']:<30} recall={m['recall']:.0%} "
              f"purity={m['purity']:.0%}  "
              f"group={m['dominant_group_id']} ({m['dominant_group_size']})")
    conn.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Make sure the database is up-to-date**

Confirm migration 007 has run and the fingerprint pass has populated tables with the new `postal_raw` column:

```bash
sqlite3 data/cleo.db "SELECT COUNT(*) FROM party_fingerprints;"
```

Expected: 249,084 (or close — may be slightly different after the postal fix).

If the count doesn't look right, re-run fingerprint:

```bash
python -c "
from cleo.database.connection import get_connection
from cleo.atoms.fingerprint import run_fingerprint_pass
conn = get_connection()
run_fingerprint_pass(conn)
conn.close()
"
```

- [ ] **Step 3: Run discovery end-to-end**

```bash
python -m cleo.discovery_v2
```

Expected output:
```
Phase A discovery run: config 2026-04-22-phase-a-v1
  IDF map: ... entries
  Candidate pairs: ...
  Strong Group edges: ...
  Strong Contact edges: ...
  Group components: ...
  Contact components: ...
  Wrote N Groups, M Contacts.

Running eval harness against audit portfolios...
Eval report: docs/discovery-audit/2026-04-22-phase-a-eval.md
  05-huntington                  recall=XX% purity=XX% group=AGR_NNNNN (N)
  ...
```

- [ ] **Step 4: Sanity-check counts in the DB**

```bash
sqlite3 data/cleo.db "SELECT COUNT(*) FROM atom_groups;"
sqlite3 data/cleo.db "SELECT COUNT(*) FROM atom_contacts;"
sqlite3 data/cleo.db "SELECT COUNT(*) FROM atom_party_entities WHERE group_id IS NOT NULL;"
sqlite3 data/cleo.db "SELECT COUNT(*) FROM atom_group_relationships;"
```

Expected roughly:
- `atom_groups`: tens of thousands (bounded by distinct brand phrases)
- `atom_contacts`: tens of thousands
- `atom_party_entities` with group_id: ≈ 249K (every party-side assigned)
- `atom_group_relationships`: a few thousand JV edges

- [ ] **Step 5: Spot-check the KingSett portfolio**

```bash
sqlite3 data/cleo.db \
  "SELECT id, canonical_brand, party_side_count, first_seen, last_seen
   FROM atom_groups WHERE canonical_brand LIKE '%kingsett%';"
```

Expected: one or two rows, party_side_count ≥ 300, first_seen near 1998, last_seen recent. If the count is near the exploration's 367 KingSett brand-token hit, Phase A's exact-match layer is working.

```bash
sqlite3 data/cleo.db \
  "SELECT postal, street_number, street_name, street_suffix,
          first_seen, last_seen, n_observations
   FROM atom_group_addresses
   WHERE group_id = (SELECT id FROM atom_groups WHERE canonical_brand = 'kingsett capital')
   ORDER BY n_observations DESC LIMIT 10;"
```

Expected: 66 Wellington and 161 Bay both present with date ranges reflecting the HQ move.

- [ ] **Step 6: Review the eval report**

Open `docs/discovery-audit/2026-04-22-phase-a-eval.md`. Verify:
- All 8 audits appear.
- Recall and purity columns have reasonable numbers (Phase A won't hit 95% on every audit — that's what Phase B adds variants for).

- [ ] **Step 7: Commit the eval artifact + any missing pieces**

```bash
git add docs/discovery-audit/2026-04-22-phase-a-eval.md cleo/discovery_v2/__main__.py
git commit -m "chore(discovery-v2): first end-to-end Phase A eval run"
```

---

## Self-Review Checklist

Before handing off to subagent-driven-development:

**Spec coverage:**
- [x] §2 Core model (party-side as fact, three entities, two graphs, disprove-based) — Tasks 7-11
- [x] §3 Atom taxonomy — uses existing `party_fingerprints`/`party_atoms`
- [ ] §4 Variant matching — **Phase B**, not here
- [ ] §5 Tiered confidence + context upgrade — Task 7 implements exact-only; context-upgrade is Phase C
- [x] §6 Pair scoring with phone co-signal rule — Task 7
- [x] §7 Knob calibration framework — Task 4 (config), Task 13 (eval harness)
- [ ] §8 Disprove tests — **Phase B+**
- [x] §9 Categorical exclusions — Task 4 (`excluded_brand_tokens`, `excluded_brand_phrases`)
- [x] §10 Timelines — Task 10
- [x] §10.3 JV relationships — Task 11
- [ ] §11 Self-improving nicknames — **Phase F**
- [x] §12 Schema — Task 1
- [ ] §13 UI surfaces — **Phase E**
- [x] §14 Data-quality fixes (postal, French suffixes) — Tasks 2-3
- [x] §15 Rollout — Phase A delivered by this plan
- [x] §16 Migration (feature flag stays `legacy` after Phase A) — Task 1 Step 1
- [x] §18 Open questions — Phase A uses starting defaults; Phase B revisits

**Placeholder scan:** no TBDs, no "implement appropriate", no "similar to Task N" — every step shows real code.

**Type consistency:** `PartySide = Tuple[str, str]` consistent across blocking, scoring, graph, entities. `MatchAtom = Tuple[str, str, float]` consistent across scoring and runner. Table names consistent (`atom_groups`, `atom_party_entities`, etc.).

**Commit discipline:** every task ends with a commit. Tests committed alongside code.

---

## Execution Handoff

Plan saved to `docs/superpowers/plans/2026-04-22-discovery-phase-a.md`. Two execution options:

**1. Subagent-Driven (recommended)** — Fresh subagent per task. Two-stage review (spec compliance + code quality) after each. Fast iteration.

**2. Inline Execution** — Batch through the 14 tasks in this session with checkpoints for review.

Which approach?
