# Group Discovery Algorithm — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a batch algorithm that identifies SPV portfolios (groups that belong to the same parent entity) by matching shared contacts, addresses, phones, and management company names across transactions, then executes merges automatically for high-confidence matches and surfaces suggestions for ambiguous ones.

**Architecture:** Evidence Layer + Merge Output (Approach C). The algorithm reads from the main DB, extracts signals, clusters groups, writes evidence trails to new `discovery_*` tables, and outputs real `group_merges` entries. No sandbox — merges are the same mechanism used by manual merges today. Four execution modes: `--validate` (compare to ground truth), `--execute` (bulk sort), `--incremental` (daily drip), `--dry-run` (preview).

**Tech Stack:** Python 3.12, SQLite, FastAPI, React 19, TypeScript, Radix UI Themes, Tailwind CSS, Phosphor Icons.

**Design Spec:** `docs/superpowers/specs/2026-04-15-group-discovery-algorithm-design.md`

---

## File Structure

### New Files (Backend)

| File | Responsibility |
|---|---|
| `cleo/discovery/__init__.py` | Public API: `run_discovery(mode, db)` |
| `cleo/discovery/types.py` | Dataclasses: Signal, Cluster, Evidence, RunResult |
| `cleo/discovery/signals.py` | Step 0: Extract signals (addresses, contacts, phones, trade names, entities) from DB |
| `cleo/discovery/clustering.py` | Steps 1-2: Exact match clustering + name fragment expansion |
| `cleo/discovery/contacts.py` | Step 3: Contact tenure establishment and distinctiveness |
| `cleo/discovery/rules.py` | Step 4: Rule hierarchy (4a-4j) matching engine |
| `cleo/discovery/engine.py` | Steps 5-7: Iterative expansion, cluster splitting, scoring, merge execution |
| `cleo/discovery/cli.py` | CLI entry point: `python -m cleo.discovery` |
| `cleo/discovery/analytics.py` | Signal analytics queries for surfacing unused patterns |
| `cleo/database/migrations/005_discovery_tables.py` | Migration: 4 new CRM-category tables |
| `cleo/web/routes/discovery.py` | API routes: cluster list, detail, ground truth, exclusions, run trigger |
| `tests/test_discovery_signals.py` | Tests for signal extraction |
| `tests/test_discovery_clustering.py` | Tests for exact match clustering |
| `tests/test_discovery_rules.py` | Tests for rule hierarchy matching |
| `tests/test_discovery_engine.py` | Tests for iterative expansion and end-to-end validation |

### New Files (Frontend)

| File | Responsibility |
|---|---|
| `frontend/src/pages/DiscoveryPage.tsx` | Cluster list view (browse all discovered portfolios) |
| `frontend/src/pages/DiscoveryClusterPage.tsx` | Cluster detail view (evidence chain, member groups, actions) |

### Modified Files

| File | Change |
|---|---|
| `cleo/database/schema.py` | Add discovery table DDL to `create_tables()` |
| `cleo/web/app.py` | Register discovery router |
| `frontend/src/types/index.ts` | Add DiscoveryCluster, DiscoveryEvidence interfaces |
| `frontend/src/App.tsx` | Add `/discovery` and `/discovery/:clusterId` routes |
| `frontend/src/components/layout/Sidebar.tsx` | Add Discovery nav item |

---

## Phase 1: Foundation (Tasks 1-8)

Signal extraction, exact match clustering, ground truth validation, basic review UI. This phase alone will surface thousands of confirmed entity-address pairs with zero risk of false matches.

---

### Task 1: Database Migration — Discovery Tables

**Files:**
- Create: `cleo/database/migrations/005_discovery_tables.py`
- Modify: `cleo/database/schema.py`

- [ ] **Step 1: Create the migration file**

```python
# cleo/database/migrations/005_discovery_tables.py
"""
Migration 005: Create discovery tables for portfolio clustering algorithm.

These are CRM-layer tables — never touched by the compiler.
The discovery engine writes evidence and run metadata here.
Confirmed clusters become real group_merges entries.

Run:
    cd cleo-turbo
    python -m cleo.database.migrations.005_discovery_tables
"""

import sqlite3
import os


def migrate(conn):
    print("Migration 005: Creating discovery tables...")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS discovery_evidence (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id          TEXT NOT NULL,
            signal_type     TEXT NOT NULL,
            signal_value    TEXT NOT NULL,
            source_group_id TEXT NOT NULL,
            target_group_id TEXT NOT NULL,
            source_id       TEXT,
            rule_id         TEXT,
            confidence      REAL,
            iteration       INTEGER DEFAULT 0,
            created_at      TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_disc_evidence_run ON discovery_evidence(run_id);
        CREATE INDEX IF NOT EXISTS idx_disc_evidence_source ON discovery_evidence(source_group_id);
        CREATE INDEX IF NOT EXISTS idx_disc_evidence_target ON discovery_evidence(target_group_id);
        CREATE INDEX IF NOT EXISTS idx_disc_evidence_type ON discovery_evidence(signal_type);

        CREATE TABLE IF NOT EXISTS discovery_runs (
            run_id          TEXT PRIMARY KEY,
            mode            TEXT NOT NULL,
            started_at      TEXT NOT NULL,
            completed_at    TEXT,
            stats_json      TEXT,
            diff_json       TEXT,
            config_json     TEXT
        );

        CREATE TABLE IF NOT EXISTS discovery_exclusions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            exclusion_type  TEXT NOT NULL,
            exclusion_value TEXT NOT NULL,
            reason          TEXT,
            created_by      TEXT,
            created_at      TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_disc_exclusions_type ON discovery_exclusions(exclusion_type);

        CREATE TABLE IF NOT EXISTS discovery_ground_truth (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            portfolio_name  TEXT NOT NULL,
            anchor_group_id TEXT NOT NULL,
            member_group_ids_json TEXT NOT NULL,
            notes           TEXT,
            created_at      TEXT DEFAULT (datetime('now')),
            updated_at      TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    print("  Created discovery_evidence, discovery_runs, discovery_exclusions, discovery_ground_truth.")

    # Verify
    for table in ['discovery_evidence', 'discovery_runs', 'discovery_exclusions', 'discovery_ground_truth']:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table} rows: {count}")
    print("Migration 005 complete.")


if __name__ == "__main__":
    db_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "cleo.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    migrate(conn)
    conn.close()
```

- [ ] **Step 2: Run the migration**

Run: `cd /Users/brandonolsen23/cleo-turbo && python -m cleo.database.migrations.005_discovery_tables`
Expected: "Migration 005 complete." with 0 rows in each table.

- [ ] **Step 3: Add DDL to schema.py for fresh installs**

In `cleo/database/schema.py`, add the four CREATE TABLE statements to the `create_tables()` function, after the existing `group_analytics` table creation (around line 639). Place them in a section commented `# ── Discovery tables ──`. Copy the exact DDL from the migration file.

- [ ] **Step 4: Verify tables exist in the database**

Run: `cd /Users/brandonolsen23/cleo-turbo && python -c "import sqlite3; conn = sqlite3.connect('data/cleo.db'); tables = [r[0] for r in conn.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'discovery_%'\").fetchall()]; print(tables)"`
Expected: `['discovery_evidence', 'discovery_exclusions', 'discovery_ground_truth', 'discovery_runs']`

- [ ] **Step 5: Commit**

```bash
git add cleo/database/migrations/005_discovery_tables.py cleo/database/schema.py
git commit -m "feat(discovery): add discovery tables migration"
```

---

### Task 2: Python Types Module

**Files:**
- Create: `cleo/discovery/__init__.py`
- Create: `cleo/discovery/types.py`
- Test: `tests/test_discovery_signals.py` (placeholder for now)

- [ ] **Step 1: Create the types module**

```python
# cleo/discovery/types.py
"""
Data types for the discovery algorithm.

Signal: a single piece of evidence linking two groups (shared address, contact, etc.)
Cluster: a set of groups believed to belong to the same portfolio
Evidence: a confirmed signal with rule attribution
RunConfig: parameters for a discovery run
RunResult: output of a complete run
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Signal:
    """A raw signal extracted from the database."""
    signal_type: str       # 'address', 'contact', 'phone', 'trade_name', 'care_of', 'entity', 'name_fragment'
    signal_value: str      # normalized value
    group_id: str          # GRP_ ID
    source_id: str         # transaction source_id where this signal was found
    side: str              # 'seller' or 'buyer'
    raw_value: str = ''    # original value before normalization


@dataclass
class Evidence:
    """A confirmed link between two groups with rule attribution."""
    signal_type: str
    signal_value: str
    source_group_id: str
    target_group_id: str
    source_id: str
    rule_id: str           # '4a', '4b', etc.
    confidence: float      # 0.0 - 1.0
    iteration: int = 0


@dataclass
class Cluster:
    """A discovered portfolio cluster."""
    cluster_id: str         # generated UUID or sequential ID
    anchor_group_id: str    # the "parent" group (highest tx count)
    anchor_name: str        # display name of anchor
    member_group_ids: set = field(default_factory=set)
    confirmed_addresses: set = field(default_factory=set)
    confirmed_contacts: set = field(default_factory=set)
    confirmed_phones: set = field(default_factory=set)
    confirmed_entities: set = field(default_factory=set)
    confirmed_name_fragments: set = field(default_factory=set)
    evidence: list = field(default_factory=list)  # list of Evidence
    confidence: float = 0.0
    status: str = 'pending'  # 'pending', 'auto_confirmed', 'needs_review', 'rejected'

    @property
    def member_count(self) -> int:
        return len(self.member_group_ids)


@dataclass
class ContactTenure:
    """A contact's tenure at a specific group/cluster."""
    contact_id: str
    contact_name: str
    group_id: str
    first_seen: str        # ISO date
    last_seen: str         # ISO date
    transaction_count: int
    is_distinctive: bool = False  # all appearances in one cluster?


@dataclass
class RunConfig:
    """Configuration for a discovery run."""
    mode: str = 'validate'  # 'validate', 'execute', 'incremental', 'dry_run'
    max_iterations: int = 5
    min_confidence_auto: float = 0.90   # auto-confirm threshold
    min_confidence_suggest: float = 0.50  # suggestion threshold


@dataclass
class RunResult:
    """Output of a complete discovery run."""
    run_id: str
    mode: str
    clusters_found: int = 0
    merges_executed: int = 0
    suggestions_created: int = 0
    groups_processed: int = 0
    iterations: int = 0
    ground_truth_results: Optional[dict] = None  # {portfolio_name: {precision, recall, missing, unexpected}}
```

- [ ] **Step 2: Create the package init**

```python
# cleo/discovery/__init__.py
"""
Group Discovery Algorithm — portfolio clustering for Ontario CRE entities.

Identifies SPVs belonging to the same parent entity by matching shared
contacts, addresses, phones, and management company names across transactions.
Outputs real group_merges entries for high-confidence matches and surfaces
suggestions for ambiguous ones.

Usage:
    python -m cleo.discovery --validate    # compare to ground truth
    python -m cleo.discovery --execute     # bulk sort, execute merges
    python -m cleo.discovery --incremental # process new transactions only
    python -m cleo.discovery --dry-run     # preview without merging
"""
```

- [ ] **Step 3: Verify imports work**

Run: `cd /Users/brandonolsen23/cleo-turbo && python -c "from cleo.discovery.types import Signal, Cluster, Evidence, RunConfig, RunResult; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add cleo/discovery/__init__.py cleo/discovery/types.py
git commit -m "feat(discovery): add data types module"
```

---

### Task 3: Signal Extraction (Step 0)

Extracts all raw signals from the main DB. This is the foundation everything else builds on.

**Files:**
- Create: `cleo/discovery/signals.py`
- Create: `tests/test_discovery_signals.py`

- [ ] **Step 1: Write the test for address signal extraction**

```python
# tests/test_discovery_signals.py
"""Tests for discovery signal extraction."""

import sqlite3
import pytest
from cleo.discovery.signals import extract_signals
from cleo.discovery.types import Signal


@pytest.fixture
def test_db():
    """Create an in-memory DB with minimal schema and test data."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE groups (
            id TEXT PRIMARY KEY, display_name TEXT, normalized_name TEXT,
            status TEXT DEFAULT 'pool', property_count INTEGER DEFAULT 0,
            transaction_count INTEGER DEFAULT 0, contact_count INTEGER DEFAULT 0
        );
        CREATE TABLE transactions (
            source_id TEXT PRIMARY KEY, property_id TEXT, sale_date TEXT,
            seller_trade_name TEXT, buyer_trade_name TEXT,
            seller_care_of TEXT, buyer_care_of TEXT
        );
        CREATE TABLE transaction_parties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT, contact_id TEXT, group_id TEXT,
            side TEXT, party_name TEXT, phone TEXT
        );
        CREATE TABLE transaction_mailing_addresses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT, side TEXT, display TEXT,
            street_number TEXT, street_name TEXT, street_suffix TEXT,
            city TEXT, province TEXT, postal TEXT
        );
        CREATE TABLE contacts (
            id TEXT PRIMARY KEY, name_fingerprint TEXT,
            display_name TEXT, phone TEXT, current_group_id TEXT
        );
        CREATE TABLE group_names (
            group_id TEXT, name TEXT, normalized TEXT, source_id TEXT,
            PRIMARY KEY (group_id, normalized)
        );
        CREATE TABLE discovery_exclusions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exclusion_type TEXT, exclusion_value TEXT, reason TEXT
        );

        -- Test data: two transactions for DH portfolio
        INSERT INTO groups VALUES ('GRP_00001', 'DH Management Inc', 'DH MANAGEMENT', 'pool', 0, 2, 0);
        INSERT INTO groups VALUES ('GRP_00002', 'Dan Hagler Investments Ltd', 'DAN HAGLER INVESTMENTS', 'pool', 0, 1, 0);
        INSERT INTO groups VALUES ('GRP_00003', 'Niagara Falls Shopping Centre Inc', 'NIAGARA FALLS SHOPPING CENTRE', 'pool', 0, 1, 0);

        INSERT INTO transactions VALUES ('RT184886', NULL, '2024-05-23', NULL, NULL, NULL, 'DH Management Inc');
        INSERT INTO transactions VALUES ('RT148276', NULL, '2019-12-18', NULL, 'DH Management Inc', NULL, NULL);

        -- RT184886: buyer side has Dan Hagler Investments Ltd + DH Management Inc
        INSERT INTO transaction_parties VALUES (1, 'RT184886', NULL, 'GRP_00002', 'buyer', 'Dan Hagler Investments Ltd', NULL);
        INSERT INTO transaction_parties VALUES (2, 'RT184886', NULL, 'GRP_00001', 'buyer', 'DH Management Inc', NULL);
        INSERT INTO transaction_parties VALUES (3, 'RT184886', 'CON_00001', NULL, 'buyer', '', 'Pres');

        -- RT148276: buyer side has Niagara Falls Shopping Centre Inc + DH Management Inc
        INSERT INTO transaction_parties VALUES (4, 'RT148276', NULL, 'GRP_00003', 'buyer', 'Niagara Falls Shopping Centre Inc', NULL);
        INSERT INTO transaction_parties VALUES (5, 'RT148276', NULL, 'GRP_00001', 'buyer', 'DH Management Inc', NULL);
        INSERT INTO transaction_parties VALUES (6, 'RT148276', 'CON_00001', NULL, 'buyer', '', 'Pres');

        INSERT INTO contacts VALUES ('CON_00001', 'DAN HAGLER', 'Dan Hagler', '416-265-5055', 'GRP_00002');

        INSERT INTO transaction_mailing_addresses VALUES (1, 'RT184886', 'buyer', '180 Shorting Rd, Toronto, Ontario, M1S 3S7', '180', 'Shorting', 'Rd', 'Toronto', 'Ontario', 'M1S 3S7');
        INSERT INTO transaction_mailing_addresses VALUES (2, 'RT148276', 'buyer', '180 Shorting Rd, Toronto, Ontario, M1S 3S7', '180', 'Shorting', 'Rd', 'Toronto', 'Ontario', 'M1S 3S7');
    """)
    return conn


class TestExtractSignals:
    def test_extracts_address_signals(self, test_db):
        signals = extract_signals(test_db)
        addr_signals = [s for s in signals if s.signal_type == 'address']
        # Both GRP_00002 and GRP_00003 should have address signals (they're the first party on each txn)
        assert len(addr_signals) >= 2
        assert all(s.signal_value for s in addr_signals)

    def test_extracts_contact_signals(self, test_db):
        signals = extract_signals(test_db)
        contact_signals = [s for s in signals if s.signal_type == 'contact']
        # Dan Hagler appears on both transactions
        assert len(contact_signals) >= 2
        assert any(s.signal_value == 'DAN HAGLER' for s in contact_signals)

    def test_extracts_phone_signals(self, test_db):
        signals = extract_signals(test_db)
        phone_signals = [s for s in signals if s.signal_type == 'phone']
        assert any(s.signal_value == '4162655055' for s in phone_signals)

    def test_extracts_care_of_signals(self, test_db):
        signals = extract_signals(test_db)
        care_of_signals = [s for s in signals if s.signal_type == 'care_of']
        # RT184886 has buyer_care_of = 'DH Management Inc'
        assert len(care_of_signals) >= 1

    def test_excludes_excluded_addresses(self, test_db):
        test_db.execute(
            "INSERT INTO discovery_exclusions (exclusion_type, exclusion_value, reason) VALUES (?, ?, ?)",
            ('address', '180 SHORTING RD|TORONTO|M1S 3S7', 'test exclusion')
        )
        signals = extract_signals(test_db)
        addr_signals = [s for s in signals if s.signal_type == 'address']
        assert len(addr_signals) == 0

    def test_extracts_entity_cooccurrence_signals(self, test_db):
        signals = extract_signals(test_db)
        entity_signals = [s for s in signals if s.signal_type == 'entity']
        # GRP_00001 (DH Management) co-occurs with GRP_00002 on RT184886
        # and co-occurs with GRP_00003 on RT148276
        assert len(entity_signals) >= 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/brandonolsen23/cleo-turbo && python -m pytest tests/test_discovery_signals.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cleo.discovery.signals'`

- [ ] **Step 3: Write the signal extraction implementation**

```python
# cleo/discovery/signals.py
"""
Step 0: Signal Extraction

Extracts raw signals from the main database:
  - Addresses from transaction_mailing_addresses
  - Contacts from transaction_parties (with contact_id)
  - Phones from contacts table
  - Trade names from transactions
  - Care-of entities from transactions
  - Entity co-occurrence from transaction_parties (multiple groups on same side)
  - Name fragments from group normalized names

Each signal is a (signal_type, signal_value, group_id, source_id, side) tuple.
The group_id is the FIRST party on that side (the SPV), not the management company.
"""

import re
from .types import Signal


def _normalize_phone(phone: str) -> str:
    """Strip all non-digit characters from a phone number."""
    if not phone:
        return ''
    digits = re.sub(r'\D', '', phone)
    # Canadian numbers: strip leading 1 if 11 digits
    if len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]
    return digits if len(digits) == 10 else ''


def _normalize_address_key(street_number: str, street_name: str, city: str, postal: str) -> str:
    """Create a normalized address key for matching.

    Format: 'STREET_NUM STREET_NAME|CITY|POSTAL'
    Example: '180 SHORTING RD|TORONTO|M1S 3S7'
    """
    parts = []
    num = (street_number or '').strip().upper()
    name = (street_name or '').strip().upper()
    if num and name:
        parts.append(f"{num} {name}")
    elif name:
        parts.append(name)
    else:
        return ''

    city_norm = (city or '').strip().upper()
    postal_norm = (postal or '').strip().upper()

    return f"{parts[0]}|{city_norm}|{postal_norm}"


def _normalize_trade_name(name: str) -> str:
    """Normalize a trade name for matching (same as group normalization)."""
    if not name:
        return ''
    from cleo.compiler.reconciler import normalize_group_name
    return normalize_group_name(name)


def _load_exclusions(db) -> dict:
    """Load all discovery exclusions, keyed by type."""
    exclusions = {'address': set(), 'contact': set(), 'phone': set(), 'entity': set()}
    rows = db.execute("SELECT exclusion_type, exclusion_value FROM discovery_exclusions").fetchall()
    for row in rows:
        etype = row['exclusion_type'] if isinstance(row, dict) else row[0]
        evalue = row['exclusion_value'] if isinstance(row, dict) else row[1]
        if etype in exclusions:
            exclusions[etype].add(evalue)
    return exclusions


def extract_signals(db) -> list:
    """Extract all raw signals from the database.

    Returns a list of Signal objects representing every detectable link
    between groups across transactions.
    """
    exclusions = _load_exclusions(db)
    signals = []

    # --- Address signals ---
    # For each transaction, find which groups are on each side and what address they used
    addr_rows = db.execute("""
        SELECT tma.source_id, tma.side, tma.display,
               tma.street_number, tma.street_name, tma.street_suffix,
               tma.city, tma.province, tma.postal,
               tp.group_id
        FROM transaction_mailing_addresses tma
        JOIN transaction_parties tp ON tp.source_id = tma.source_id AND tp.side = tma.side
        WHERE tp.group_id IS NOT NULL
          AND tma.street_name IS NOT NULL
          AND tma.street_name != ''
    """).fetchall()

    for row in addr_rows:
        street_with_suffix = row['street_name'] or ''
        if row['street_suffix']:
            street_with_suffix += ' ' + row['street_suffix']
        addr_key = _normalize_address_key(
            row['street_number'], street_with_suffix, row['city'], row['postal']
        )
        if not addr_key or addr_key in exclusions['address']:
            continue
        signals.append(Signal(
            signal_type='address',
            signal_value=addr_key,
            group_id=row['group_id'],
            source_id=row['source_id'],
            side=row['side'],
            raw_value=row['display'] or '',
        ))

    # --- Contact signals ---
    # Contacts linked to transactions via transaction_parties
    contact_rows = db.execute("""
        SELECT tp.source_id, tp.side, tp.contact_id, c.name_fingerprint, c.display_name
        FROM transaction_parties tp
        JOIN contacts c ON c.id = tp.contact_id
        WHERE tp.contact_id IS NOT NULL
    """).fetchall()

    # For each contact row, find which group(s) are on the same side of the same txn
    for row in contact_rows:
        fingerprint = row['name_fingerprint']
        if fingerprint in exclusions['contact']:
            continue
        # Find groups on the same side of this transaction
        group_rows = db.execute(
            "SELECT group_id FROM transaction_parties WHERE source_id = ? AND side = ? AND group_id IS NOT NULL",
            (row['source_id'], row['side'])
        ).fetchall()
        for gr in group_rows:
            signals.append(Signal(
                signal_type='contact',
                signal_value=fingerprint,
                group_id=gr['group_id'],
                source_id=row['source_id'],
                side=row['side'],
                raw_value=row['display_name'] or '',
            ))

    # --- Phone signals ---
    # Phones on contacts, attributed to their group
    phone_rows = db.execute("""
        SELECT DISTINCT c.id, c.phone, c.current_group_id, c.name_fingerprint
        FROM contacts c
        WHERE c.phone IS NOT NULL AND c.phone != ''
          AND c.current_group_id IS NOT NULL
    """).fetchall()

    for row in phone_rows:
        normalized = _normalize_phone(row['phone'])
        if not normalized or normalized in exclusions['phone']:
            continue
        signals.append(Signal(
            signal_type='phone',
            signal_value=normalized,
            group_id=row['current_group_id'],
            source_id='',  # phone is contact-level, not txn-level
            side='',
            raw_value=row['phone'],
        ))

    # --- Trade name signals ---
    # Trade names from transactions, attributed to the first group on that side
    trade_rows = db.execute("""
        SELECT t.source_id,
               t.seller_trade_name, t.buyer_trade_name
        FROM transactions t
        WHERE (t.seller_trade_name IS NOT NULL AND t.seller_trade_name != '')
           OR (t.buyer_trade_name IS NOT NULL AND t.buyer_trade_name != '')
    """).fetchall()

    for row in trade_rows:
        for side, field in [('seller', 'seller_trade_name'), ('buyer', 'buyer_trade_name')]:
            raw_name = row[field]
            if not raw_name:
                continue
            normalized = _normalize_trade_name(raw_name)
            if not normalized:
                continue
            # Find the first group on this side
            gp = db.execute(
                "SELECT group_id FROM transaction_parties WHERE source_id = ? AND side = ? AND group_id IS NOT NULL LIMIT 1",
                (row['source_id'], side)
            ).fetchone()
            if gp:
                signals.append(Signal(
                    signal_type='trade_name',
                    signal_value=normalized,
                    group_id=gp['group_id'],
                    source_id=row['source_id'],
                    side=side,
                    raw_value=raw_name,
                ))

    # --- Care-of signals ---
    care_of_rows = db.execute("""
        SELECT t.source_id,
               t.seller_care_of, t.buyer_care_of
        FROM transactions t
        WHERE (t.seller_care_of IS NOT NULL AND t.seller_care_of != '')
           OR (t.buyer_care_of IS NOT NULL AND t.buyer_care_of != '')
    """).fetchall()

    for row in care_of_rows:
        for side, field in [('seller', 'seller_care_of'), ('buyer', 'buyer_care_of')]:
            raw_name = row[field]
            if not raw_name:
                continue
            normalized = _normalize_trade_name(raw_name)
            if not normalized:
                continue
            gp = db.execute(
                "SELECT group_id FROM transaction_parties WHERE source_id = ? AND side = ? AND group_id IS NOT NULL LIMIT 1",
                (row['source_id'], side)
            ).fetchone()
            if gp:
                signals.append(Signal(
                    signal_type='care_of',
                    signal_value=normalized,
                    group_id=gp['group_id'],
                    source_id=row['source_id'],
                    side=side,
                    raw_value=raw_name,
                ))

    # --- Entity co-occurrence signals ---
    # When multiple groups appear on the same side of a transaction, they're co-parties
    cooccurrence_rows = db.execute("""
        SELECT source_id, side, GROUP_CONCAT(group_id) as group_ids
        FROM transaction_parties
        WHERE group_id IS NOT NULL
        GROUP BY source_id, side
        HAVING COUNT(DISTINCT group_id) >= 2
    """).fetchall()

    for row in cooccurrence_rows:
        group_ids = row['group_ids'].split(',')
        # Create pairwise entity signals
        for i, gid1 in enumerate(group_ids):
            for gid2 in group_ids[i + 1:]:
                signals.append(Signal(
                    signal_type='entity',
                    signal_value=gid2,  # the co-occurring group
                    group_id=gid1,
                    source_id=row['source_id'],
                    side=row['side'],
                ))
                signals.append(Signal(
                    signal_type='entity',
                    signal_value=gid1,
                    group_id=gid2,
                    source_id=row['source_id'],
                    side=row['side'],
                ))

    return signals
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/brandonolsen23/cleo-turbo && python -m pytest tests/test_discovery_signals.py -v`
Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add cleo/discovery/signals.py tests/test_discovery_signals.py
git commit -m "feat(discovery): signal extraction from DB (Step 0)"
```

---

### Task 4: Exact Match Clustering (Step 1)

Groups entities that share identical signals into initial clusters.

**Files:**
- Create: `cleo/discovery/clustering.py`
- Create: `tests/test_discovery_clustering.py`

- [ ] **Step 1: Write the test for exact match clustering**

```python
# tests/test_discovery_clustering.py
"""Tests for discovery clustering."""

import pytest
from cleo.discovery.types import Signal, Cluster
from cleo.discovery.clustering import build_exact_match_clusters


class TestExactMatchClustering:
    def _make_signals(self):
        """Create signals mimicking DH portfolio: 3 groups sharing address + contact."""
        return [
            # Address signals: all 3 groups at 180 Shorting Rd
            Signal('address', '180 SHORTING RD|TORONTO|M1S 3S7', 'GRP_00001', 'RT184886', 'buyer'),
            Signal('address', '180 SHORTING RD|TORONTO|M1S 3S7', 'GRP_00002', 'RT184886', 'buyer'),
            Signal('address', '180 SHORTING RD|TORONTO|M1S 3S7', 'GRP_00003', 'RT148276', 'buyer'),
            # Contact signals: Dan Hagler on all 3
            Signal('contact', 'DAN HAGLER', 'GRP_00001', 'RT184886', 'buyer'),
            Signal('contact', 'DAN HAGLER', 'GRP_00002', 'RT184886', 'buyer'),
            Signal('contact', 'DAN HAGLER', 'GRP_00003', 'RT148276', 'buyer'),
            # Phone: same phone on 2 groups
            Signal('phone', '4162655055', 'GRP_00001', '', ''),
            Signal('phone', '4162655055', 'GRP_00002', '', ''),
            # Unrelated group at different address
            Signal('address', '100 KING ST|TORONTO|M5H 1A1', 'GRP_00099', 'RT999999', 'buyer'),
        ]

    def test_clusters_groups_by_shared_signals(self):
        signals = self._make_signals()
        clusters = build_exact_match_clusters(signals)
        # Should find one cluster with GRP_00001, GRP_00002, GRP_00003
        dh_cluster = None
        for c in clusters:
            if 'GRP_00001' in c.member_group_ids:
                dh_cluster = c
                break
        assert dh_cluster is not None
        assert 'GRP_00002' in dh_cluster.member_group_ids
        assert 'GRP_00003' in dh_cluster.member_group_ids
        assert 'GRP_00099' not in dh_cluster.member_group_ids

    def test_isolated_groups_not_clustered(self):
        signals = self._make_signals()
        clusters = build_exact_match_clusters(signals)
        # GRP_00099 has no shared signals — should not form a cluster
        member_sets = [c.member_group_ids for c in clusters]
        for ms in member_sets:
            if 'GRP_00099' in ms:
                # If it's in a cluster, it should be alone
                assert len(ms) == 1

    def test_records_shared_signals_on_cluster(self):
        signals = self._make_signals()
        clusters = build_exact_match_clusters(signals)
        dh_cluster = next(c for c in clusters if 'GRP_00001' in c.member_group_ids)
        assert '180 SHORTING RD|TORONTO|M1S 3S7' in dh_cluster.confirmed_addresses
        assert 'DAN HAGLER' in dh_cluster.confirmed_contacts
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/brandonolsen23/cleo-turbo && python -m pytest tests/test_discovery_clustering.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the clustering implementation**

```python
# cleo/discovery/clustering.py
"""
Steps 1-2: Clustering

Step 1 — Exact Match Clustering:
  Build a graph where groups are nodes and shared signals are edges.
  Find connected components = initial clusters.

Step 2 — Name Fragment Expansion (Phase 2):
  Expand clusters using distinctive name fragments (first two words).
"""

from collections import defaultdict
from .types import Signal, Cluster


def build_exact_match_clusters(signals: list) -> list:
    """Step 1: Build clusters from groups that share identical signals.

    Uses Union-Find to efficiently group entities connected by shared signals.
    A shared signal = same (signal_type, signal_value) appearing on 2+ groups.

    Returns a list of Cluster objects, each containing 2+ member groups.
    Single-group "clusters" are excluded.
    """
    # Index: (signal_type, signal_value) -> set of group_ids
    signal_index = defaultdict(set)
    for s in signals:
        signal_index[(s.signal_type, s.signal_value)].add(s.group_id)

    # Union-Find
    parent = {}

    def find(x):
        if x not in parent:
            parent[x] = x
        while parent[x] != x:
            parent[x] = parent[parent[x]]  # path compression
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    # Connect groups that share any signal
    for (sig_type, sig_value), group_ids in signal_index.items():
        if len(group_ids) < 2:
            continue
        group_list = list(group_ids)
        for i in range(1, len(group_list)):
            union(group_list[0], group_list[i])

    # Build clusters from connected components
    components = defaultdict(set)
    for gid in parent:
        components[find(gid)].add(gid)

    # Create Cluster objects for components with 2+ members
    clusters = []
    for root, member_ids in components.items():
        if len(member_ids) < 2:
            continue

        cluster = Cluster(
            cluster_id='',  # assigned later
            anchor_group_id='',  # determined later
            anchor_name='',
            member_group_ids=member_ids,
        )

        # Record which signals are confirmed (shared by 2+ members)
        for (sig_type, sig_value), group_ids in signal_index.items():
            shared = group_ids & member_ids
            if len(shared) >= 2:
                if sig_type == 'address':
                    cluster.confirmed_addresses.add(sig_value)
                elif sig_type == 'contact':
                    cluster.confirmed_contacts.add(sig_value)
                elif sig_type == 'phone':
                    cluster.confirmed_phones.add(sig_value)
                elif sig_type in ('trade_name', 'care_of', 'entity'):
                    cluster.confirmed_entities.add(sig_value)

        clusters.append(cluster)

    return clusters
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/brandonolsen23/cleo-turbo && python -m pytest tests/test_discovery_clustering.py -v`
Expected: All 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add cleo/discovery/clustering.py tests/test_discovery_clustering.py
git commit -m "feat(discovery): exact match clustering (Step 1)"
```

---

### Task 5: Ground Truth and Validation Framework

**Files:**
- Create: `cleo/discovery/validation.py`
- Create: `tests/test_discovery_engine.py`

- [ ] **Step 1: Write the validation module**

```python
# cleo/discovery/validation.py
"""
Ground truth validation for the discovery algorithm.

Compares algorithm output (clusters) against known-correct portfolios
stored in discovery_ground_truth. Reports precision and recall per portfolio.
"""

import json


def load_ground_truth(db) -> list:
    """Load all ground truth portfolios from the database.

    Returns list of dicts: {portfolio_name, anchor_group_id, member_group_ids: set}
    """
    rows = db.execute(
        "SELECT portfolio_name, anchor_group_id, member_group_ids_json FROM discovery_ground_truth"
    ).fetchall()
    result = []
    for row in rows:
        result.append({
            'portfolio_name': row['portfolio_name'],
            'anchor_group_id': row['anchor_group_id'],
            'member_group_ids': set(json.loads(row['member_group_ids_json'])),
        })
    return result


def validate_clusters(clusters: list, ground_truth: list) -> dict:
    """Compare discovered clusters against ground truth.

    For each ground truth portfolio, find the best-matching cluster and compute:
      - precision: what fraction of the cluster's members are actually in the portfolio
      - recall: what fraction of the portfolio's members were found
      - missing: portfolio members not in any cluster
      - unexpected: cluster members not in the portfolio

    Returns: {portfolio_name: {precision, recall, missing, unexpected, matched_cluster_size}}
    """
    results = {}

    for gt in ground_truth:
        gt_members = gt['member_group_ids']
        portfolio_name = gt['portfolio_name']

        # Find the cluster with the most overlap with this ground truth
        best_cluster = None
        best_overlap = 0
        for cluster in clusters:
            overlap = len(cluster.member_group_ids & gt_members)
            if overlap > best_overlap:
                best_overlap = overlap
                best_cluster = cluster

        if best_cluster is None or best_overlap == 0:
            results[portfolio_name] = {
                'precision': 0.0,
                'recall': 0.0,
                'missing': list(gt_members),
                'unexpected': [],
                'matched_cluster_size': 0,
            }
            continue

        found = best_cluster.member_group_ids & gt_members
        missing = gt_members - best_cluster.member_group_ids
        unexpected = best_cluster.member_group_ids - gt_members

        precision = len(found) / len(best_cluster.member_group_ids) if best_cluster.member_group_ids else 0.0
        recall = len(found) / len(gt_members) if gt_members else 0.0

        results[portfolio_name] = {
            'precision': round(precision, 4),
            'recall': round(recall, 4),
            'missing': sorted(missing),
            'unexpected': sorted(unexpected),
            'matched_cluster_size': len(best_cluster.member_group_ids),
        }

    return results


def save_ground_truth(db, portfolio_name: str, anchor_group_id: str, member_group_ids: list, notes: str = ''):
    """Insert or update a ground truth portfolio."""
    existing = db.execute(
        "SELECT id FROM discovery_ground_truth WHERE portfolio_name = ?",
        (portfolio_name,)
    ).fetchone()

    member_json = json.dumps(sorted(member_group_ids))

    if existing:
        db.execute(
            "UPDATE discovery_ground_truth SET anchor_group_id = ?, member_group_ids_json = ?, notes = ?, updated_at = datetime('now') WHERE portfolio_name = ?",
            (anchor_group_id, member_json, notes, portfolio_name)
        )
    else:
        db.execute(
            "INSERT INTO discovery_ground_truth (portfolio_name, anchor_group_id, member_group_ids_json, notes) VALUES (?, ?, ?, ?)",
            (portfolio_name, anchor_group_id, member_json, notes)
        )
    db.commit()
```

- [ ] **Step 2: Write the validation test**

```python
# tests/test_discovery_engine.py
"""Tests for the discovery engine — end-to-end validation."""

import pytest
from cleo.discovery.types import Cluster
from cleo.discovery.validation import validate_clusters


class TestValidation:
    def test_perfect_match(self):
        gt = [{'portfolio_name': 'DH', 'anchor_group_id': 'GRP_00001',
               'member_group_ids': {'GRP_00001', 'GRP_00002', 'GRP_00003'}}]
        clusters = [Cluster(
            cluster_id='C1', anchor_group_id='GRP_00001', anchor_name='DH',
            member_group_ids={'GRP_00001', 'GRP_00002', 'GRP_00003'}
        )]
        results = validate_clusters(clusters, gt)
        assert results['DH']['precision'] == 1.0
        assert results['DH']['recall'] == 1.0
        assert results['DH']['missing'] == []
        assert results['DH']['unexpected'] == []

    def test_partial_recall(self):
        gt = [{'portfolio_name': 'DH', 'anchor_group_id': 'GRP_00001',
               'member_group_ids': {'GRP_00001', 'GRP_00002', 'GRP_00003'}}]
        clusters = [Cluster(
            cluster_id='C1', anchor_group_id='GRP_00001', anchor_name='DH',
            member_group_ids={'GRP_00001', 'GRP_00002'}  # missing GRP_00003
        )]
        results = validate_clusters(clusters, gt)
        assert results['DH']['recall'] == pytest.approx(2/3, abs=0.01)
        assert 'GRP_00003' in results['DH']['missing']

    def test_false_positive(self):
        gt = [{'portfolio_name': 'DH', 'anchor_group_id': 'GRP_00001',
               'member_group_ids': {'GRP_00001', 'GRP_00002'}}]
        clusters = [Cluster(
            cluster_id='C1', anchor_group_id='GRP_00001', anchor_name='DH',
            member_group_ids={'GRP_00001', 'GRP_00002', 'GRP_00099'}  # extra
        )]
        results = validate_clusters(clusters, gt)
        assert results['DH']['precision'] == pytest.approx(2/3, abs=0.01)
        assert 'GRP_00099' in results['DH']['unexpected']

    def test_no_match(self):
        gt = [{'portfolio_name': 'DH', 'anchor_group_id': 'GRP_00001',
               'member_group_ids': {'GRP_00001', 'GRP_00002'}}]
        clusters = [Cluster(
            cluster_id='C1', anchor_group_id='GRP_00050', anchor_name='Other',
            member_group_ids={'GRP_00050', 'GRP_00051'}
        )]
        results = validate_clusters(clusters, gt)
        assert results['DH']['recall'] == 0.0
```

- [ ] **Step 3: Run tests**

Run: `cd /Users/brandonolsen23/cleo-turbo && python -m pytest tests/test_discovery_engine.py -v`
Expected: All 4 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add cleo/discovery/validation.py tests/test_discovery_engine.py
git commit -m "feat(discovery): ground truth validation framework"
```

---

### Task 6: CLI Runner and Engine Orchestrator

Wires together signal extraction, clustering, and validation into a runnable entry point.

**Files:**
- Create: `cleo/discovery/engine.py`
- Create: `cleo/discovery/cli.py`
- Create: `cleo/discovery/__main__.py`

- [ ] **Step 1: Write the engine orchestrator**

```python
# cleo/discovery/engine.py
"""
Discovery Engine — orchestrates the full pipeline.

Phase 1: extract signals → exact match clustering → validate against ground truth.
Phase 2+ will add: name fragments, contact tenure, rule hierarchy, iteration.
"""

import json
import uuid
from datetime import datetime

from .types import RunConfig, RunResult
from .signals import extract_signals
from .clustering import build_exact_match_clusters
from .validation import load_ground_truth, validate_clusters


def run_discovery(db, config: RunConfig = None) -> RunResult:
    """Run the discovery algorithm.

    Args:
        db: SQLite connection with row_factory = sqlite3.Row
        config: RunConfig with mode and parameters

    Returns:
        RunResult with statistics and (if validate mode) ground truth comparison.
    """
    if config is None:
        config = RunConfig()

    run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    started_at = datetime.now().isoformat()

    result = RunResult(run_id=run_id, mode=config.mode)

    # Step 0: Extract signals
    print(f"[{run_id}] Step 0: Extracting signals...")
    signals = extract_signals(db)
    print(f"  Extracted {len(signals)} signals")

    # Count by type
    type_counts = {}
    for s in signals:
        type_counts[s.signal_type] = type_counts.get(s.signal_type, 0) + 1
    for stype, count in sorted(type_counts.items()):
        print(f"    {stype}: {count}")

    # Step 1: Exact match clustering
    print(f"[{run_id}] Step 1: Building exact match clusters...")
    clusters = build_exact_match_clusters(signals)
    result.clusters_found = len(clusters)
    print(f"  Found {len(clusters)} clusters with 2+ members")

    # Assign cluster IDs and determine anchors
    # (pick the group with highest tx count as anchor)
    for i, cluster in enumerate(clusters):
        cluster.cluster_id = f"DISC_{i + 1:05d}"
        # Look up transaction counts to find the anchor
        best_gid = None
        best_tx = -1
        for gid in cluster.member_group_ids:
            row = db.execute("SELECT transaction_count FROM groups WHERE id = ?", (gid,)).fetchone()
            tx_count = row['transaction_count'] if row else 0
            if tx_count > best_tx:
                best_tx = tx_count
                best_gid = gid
        cluster.anchor_group_id = best_gid or list(cluster.member_group_ids)[0]
        anchor_row = db.execute("SELECT display_name FROM groups WHERE id = ?", (cluster.anchor_group_id,)).fetchone()
        cluster.anchor_name = anchor_row['display_name'] if anchor_row else cluster.anchor_group_id

    # Count total groups in clusters
    all_clustered = set()
    for c in clusters:
        all_clustered.update(c.member_group_ids)
    result.groups_processed = len(all_clustered)

    # Validate mode: compare to ground truth
    if config.mode == 'validate':
        print(f"[{run_id}] Validating against ground truth...")
        ground_truth = load_ground_truth(db)
        if ground_truth:
            gt_results = validate_clusters(clusters, ground_truth)
            result.ground_truth_results = gt_results
            for name, r in gt_results.items():
                status = 'PASS' if r['precision'] == 1.0 and r['recall'] == 1.0 else 'FAIL'
                print(f"  [{status}] {name}: precision={r['precision']:.2%}, recall={r['recall']:.2%}, "
                      f"missing={len(r['missing'])}, unexpected={len(r['unexpected'])}")
        else:
            print("  No ground truth portfolios found. Add them with save_ground_truth().")

    # Write evidence to discovery_evidence (all modes)
    print(f"[{run_id}] Writing evidence...")
    evidence_count = 0
    for cluster in clusters:
        for gid in cluster.member_group_ids:
            if gid == cluster.anchor_group_id:
                continue
            # Record address evidence
            for addr in cluster.confirmed_addresses:
                db.execute(
                    "INSERT INTO discovery_evidence (run_id, signal_type, signal_value, source_group_id, target_group_id, rule_id, confidence, iteration) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (run_id, 'address', addr, gid, cluster.anchor_group_id, 'step1_exact', 0.5, 0)
                )
                evidence_count += 1
            # Record contact evidence
            for contact in cluster.confirmed_contacts:
                db.execute(
                    "INSERT INTO discovery_evidence (run_id, signal_type, signal_value, source_group_id, target_group_id, rule_id, confidence, iteration) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (run_id, 'contact', contact, gid, cluster.anchor_group_id, 'step1_exact', 0.5, 0)
                )
                evidence_count += 1
            # Record phone evidence
            for phone in cluster.confirmed_phones:
                db.execute(
                    "INSERT INTO discovery_evidence (run_id, signal_type, signal_value, source_group_id, target_group_id, rule_id, confidence, iteration) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (run_id, 'phone', phone, gid, cluster.anchor_group_id, 'step1_exact', 0.5, 0)
                )
                evidence_count += 1
            # Record entity evidence
            for entity in cluster.confirmed_entities:
                db.execute(
                    "INSERT INTO discovery_evidence (run_id, signal_type, signal_value, source_group_id, target_group_id, rule_id, confidence, iteration) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (run_id, 'entity', entity, gid, cluster.anchor_group_id, 'step1_exact', 0.5, 0)
                )
                evidence_count += 1

    # Log the run
    completed_at = datetime.now().isoformat()
    stats = {
        'clusters_found': result.clusters_found,
        'groups_processed': result.groups_processed,
        'evidence_written': evidence_count,
        'signal_counts': type_counts,
    }
    if result.ground_truth_results:
        stats['ground_truth'] = result.ground_truth_results

    db.execute(
        "INSERT INTO discovery_runs (run_id, mode, started_at, completed_at, stats_json) VALUES (?, ?, ?, ?, ?)",
        (run_id, config.mode, started_at, completed_at, json.dumps(stats))
    )
    db.commit()

    print(f"[{run_id}] Complete. {result.clusters_found} clusters, {evidence_count} evidence rows.")
    return result
```

- [ ] **Step 2: Write the CLI entry point**

```python
# cleo/discovery/cli.py
"""
CLI entry point for the discovery algorithm.

Usage:
    python -m cleo.discovery --validate
    python -m cleo.discovery --execute
    python -m cleo.discovery --incremental
    python -m cleo.discovery --dry-run
    python -m cleo.discovery --status
"""

import argparse
import sqlite3
import os
import json

from .types import RunConfig
from .engine import run_discovery
from .validation import save_ground_truth


def get_db():
    db_path = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'cleo.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def cmd_run(args):
    db = get_db()
    mode_map = {
        'validate': 'validate',
        'execute': 'execute',
        'incremental': 'incremental',
        'dry_run': 'dry_run',
    }
    mode = None
    for flag, mode_name in mode_map.items():
        if getattr(args, flag, False):
            mode = mode_name
            break
    if mode is None:
        mode = 'validate'  # default

    config = RunConfig(mode=mode)
    result = run_discovery(db, config)

    if result.ground_truth_results:
        print("\n=== Ground Truth Results ===")
        for name, r in result.ground_truth_results.items():
            print(f"\n{name}:")
            print(f"  Precision: {r['precision']:.2%}")
            print(f"  Recall:    {r['recall']:.2%}")
            if r['missing']:
                print(f"  Missing:   {r['missing']}")
            if r['unexpected']:
                print(f"  Unexpected: {r['unexpected']}")

    db.close()


def cmd_status(args):
    db = get_db()
    rows = db.execute(
        "SELECT run_id, mode, started_at, completed_at, stats_json FROM discovery_runs ORDER BY started_at DESC LIMIT 10"
    ).fetchall()
    if not rows:
        print("No discovery runs found.")
        return
    print(f"{'Run ID':<35} {'Mode':<12} {'Started':<20} {'Clusters':<10}")
    print("-" * 80)
    for row in rows:
        stats = json.loads(row['stats_json']) if row['stats_json'] else {}
        print(f"{row['run_id']:<35} {row['mode']:<12} {row['started_at']:<20} {stats.get('clusters_found', '?'):<10}")
    db.close()


def cmd_add_ground_truth(args):
    db = get_db()
    member_ids = [gid.strip() for gid in args.members.split(',')]
    save_ground_truth(db, args.name, args.anchor, member_ids, args.notes or '')
    print(f"Saved ground truth '{args.name}' with {len(member_ids)} members.")
    db.close()


def main():
    parser = argparse.ArgumentParser(description="Cleo Group Discovery Algorithm")
    subparsers = parser.add_subparsers(dest='command')

    # Run command (default)
    run_parser = subparsers.add_parser('run', help='Run the discovery algorithm')
    run_parser.add_argument('--validate', action='store_true', help='Compare to ground truth (default)')
    run_parser.add_argument('--execute', action='store_true', help='Execute merges for high-confidence clusters')
    run_parser.add_argument('--incremental', action='store_true', help='Process only new transactions')
    run_parser.add_argument('--dry-run', dest='dry_run', action='store_true', help='Preview without merging')
    run_parser.set_defaults(func=cmd_run)

    # Status command
    status_parser = subparsers.add_parser('status', help='Show recent run history')
    status_parser.set_defaults(func=cmd_status)

    # Ground truth command
    gt_parser = subparsers.add_parser('ground-truth', help='Manage ground truth portfolios')
    gt_parser.add_argument('--name', required=True, help='Portfolio name (e.g., "DH Property Management")')
    gt_parser.add_argument('--anchor', required=True, help='Anchor group ID (e.g., GRP_00001)')
    gt_parser.add_argument('--members', required=True, help='Comma-separated member group IDs')
    gt_parser.add_argument('--notes', help='Optional notes')
    gt_parser.set_defaults(func=cmd_add_ground_truth)

    args = parser.parse_args()
    if hasattr(args, 'func'):
        args.func(args)
    else:
        # Default: run in validate mode
        args.validate = True
        args.execute = False
        args.incremental = False
        args.dry_run = False
        cmd_run(args)


if __name__ == '__main__':
    main()
```

- [ ] **Step 3: Create the __main__.py**

```python
# cleo/discovery/__main__.py
"""Allow running as: python -m cleo.discovery"""
from .cli import main
main()
```

- [ ] **Step 4: Test the CLI runs**

Run: `cd /Users/brandonolsen23/cleo-turbo && python -m cleo.discovery status`
Expected: "No discovery runs found." (no runs yet)

- [ ] **Step 5: Run the algorithm in validate mode**

Run: `cd /Users/brandonolsen23/cleo-turbo && python -m cleo.discovery run --validate`
Expected: Extracts signals, builds clusters, prints "No ground truth portfolios found."

- [ ] **Step 6: Commit**

```bash
git add cleo/discovery/engine.py cleo/discovery/cli.py cleo/discovery/__main__.py
git commit -m "feat(discovery): CLI runner and engine orchestrator"
```

---

### Task 7: Populate DH Ground Truth

This task requires querying the live database to find the actual GRP_ IDs for the DH portfolio SPVs that have already been manually merged.

**Files:**
- No new files — uses existing CLI

- [ ] **Step 1: Find DH's merged group ID and all absorbed groups**

Run:
```bash
cd /Users/brandonolsen23/cleo-turbo && python -c "
import sqlite3
conn = sqlite3.connect('data/cleo.db')
conn.row_factory = sqlite3.Row

# Find DH Management group
rows = conn.execute(\"SELECT id, display_name, normalized_name, status, transaction_count FROM groups WHERE normalized_name LIKE '%DH MANAGEMENT%' OR normalized_name LIKE '%DH PROPERTY%' OR display_name LIKE '%DH Management%' OR display_name LIKE '%DH Property Management%'\").fetchall()
for r in rows:
    print(f'{r[\"id\"]} | {r[\"display_name\"]} | status={r[\"status\"]} | txns={r[\"transaction_count\"]}')

print()
print('=== Groups merged into DH ===')
# Check group_merges for any DH-related target
for r in rows:
    if r['status'] != 'merged':
        merges = conn.execute('SELECT source_group_id FROM group_merges WHERE target_group_id = ? AND unmerged_at IS NULL', (r['id'],)).fetchall()
        for m in merges:
            src = conn.execute('SELECT id, display_name FROM groups WHERE id = ?', (m[0],)).fetchone()
            if src:
                print(f'  {src[\"id\"]} | {src[\"display_name\"]}')
"
```

- [ ] **Step 2: Record the GRP_ IDs and add ground truth**

Using the IDs found in Step 1, run the ground-truth CLI command. Example (replace with actual IDs):

```bash
cd /Users/brandonolsen23/cleo-turbo && python -m cleo.discovery ground-truth \
  --name "DH Property Management" \
  --anchor GRP_XXXXX \
  --members "GRP_XXXXX,GRP_YYYYY,GRP_ZZZZZ,..." \
  --notes "30+ SPV portfolio. Dan Hagler + Nina Wine. 3 address eras: Eglinton (1997-2001), 160 Shorting (2002-2012), 180 Shorting (2013-present)."
```

- [ ] **Step 3: Run validate mode with ground truth**

Run: `cd /Users/brandonolsen23/cleo-turbo && python -m cleo.discovery run --validate`
Expected: Shows precision/recall for DH portfolio. Step 1 (exact match only) will likely have partial recall — that's expected. The full rule hierarchy in Phase 2+ will improve it.

- [ ] **Step 4: Commit**

```bash
git commit -m "feat(discovery): add DH Property Management ground truth"
```

---

### Task 8: API Routes for Discovery Review UI

**Files:**
- Create: `cleo/web/routes/discovery.py`
- Modify: `cleo/web/app.py`

- [ ] **Step 1: Write the discovery API routes**

```python
# cleo/web/routes/discovery.py
"""
Discovery API — cluster browsing, detail, ground truth, exclusions.
"""

import json
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
from ...web.deps import get_db, get_current_user

router = APIRouter()


# ── Browse Clusters ─────────────────────────────────────────

@router.get("")
def browse_clusters(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    status: Optional[str] = None,
    min_members: Optional[int] = None,
    sort: str = Query("member_count", regex="^(member_count|confidence|anchor_name)$"),
    order: str = Query("desc", regex="^(asc|desc)$"),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Browse discovered portfolio clusters from the most recent run."""
    # Get the latest run
    latest_run = db.execute(
        "SELECT run_id, mode, started_at, completed_at, stats_json FROM discovery_runs ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    if not latest_run:
        return {"results": [], "total": 0, "page": page, "per_page": per_page, "pages": 0, "run": None}

    run_id = latest_run['run_id']

    # Build clusters from evidence
    evidence_rows = db.execute("""
        SELECT DISTINCT source_group_id, target_group_id, signal_type, signal_value, rule_id, confidence
        FROM discovery_evidence
        WHERE run_id = ?
    """, (run_id,)).fetchall()

    # Group by target (anchor)
    clusters_map = {}
    for row in evidence_rows:
        target = row['target_group_id']
        if target not in clusters_map:
            clusters_map[target] = {
                'anchor_group_id': target,
                'member_group_ids': {target},
                'signals': [],
                'confidence': 0.0,
            }
        clusters_map[target]['member_group_ids'].add(row['source_group_id'])
        clusters_map[target]['signals'].append({
            'type': row['signal_type'],
            'value': row['signal_value'],
            'source_group_id': row['source_group_id'],
            'rule_id': row['rule_id'],
        })
        clusters_map[target]['confidence'] = max(clusters_map[target]['confidence'], row['confidence'] or 0)

    # Enrich with group display names
    cluster_list = []
    for anchor_id, cdata in clusters_map.items():
        anchor_row = db.execute("SELECT display_name, transaction_count FROM groups WHERE id = ?", (anchor_id,)).fetchone()
        anchor_name = anchor_row['display_name'] if anchor_row else anchor_id

        # Calculate portfolio value
        member_ids_tuple = tuple(cdata['member_group_ids'])
        placeholders = ','.join('?' * len(member_ids_tuple))
        portfolio_val = db.execute(
            f"SELECT COALESCE(SUM(ga.total_assessed_value), 0) as total "
            f"FROM group_analytics ga WHERE ga.group_id IN ({placeholders})",
            member_ids_tuple
        ).fetchone()

        member_count = len(cdata['member_group_ids'])
        if min_members and member_count < min_members:
            continue

        cluster_list.append({
            'anchor_group_id': anchor_id,
            'anchor_name': anchor_name,
            'member_count': member_count,
            'portfolio_value': portfolio_val['total'] if portfolio_val else 0,
            'confidence': cdata['confidence'],
            'signal_count': len(cdata['signals']),
            'status': 'auto_confirmed' if cdata['confidence'] >= 0.9 else 'needs_review',
        })

    # Sort
    reverse = order == 'desc'
    cluster_list.sort(key=lambda x: x.get(sort, 0) or 0, reverse=reverse)

    # Paginate
    total = len(cluster_list)
    pages = (total + per_page - 1) // per_page
    start = (page - 1) * per_page
    end = start + per_page

    return {
        "results": cluster_list[start:end],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
        "run": {
            "run_id": latest_run['run_id'],
            "mode": latest_run['mode'],
            "started_at": latest_run['started_at'],
            "completed_at": latest_run['completed_at'],
            "stats": json.loads(latest_run['stats_json']) if latest_run['stats_json'] else None,
        },
    }


# ── Cluster Detail ──────────────────────────────────────────

@router.get("/clusters/{anchor_group_id}")
def cluster_detail(
    anchor_group_id: str,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Get full detail for a discovered cluster, including all evidence."""
    # Get latest run
    latest_run = db.execute(
        "SELECT run_id FROM discovery_runs ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    if not latest_run:
        raise HTTPException(status_code=404, detail="No discovery runs found")

    run_id = latest_run['run_id']

    # Get all evidence for this cluster
    evidence_rows = db.execute("""
        SELECT source_group_id, target_group_id, signal_type, signal_value,
               source_id, rule_id, confidence, iteration
        FROM discovery_evidence
        WHERE run_id = ? AND target_group_id = ?
        ORDER BY confidence DESC, signal_type
    """, (run_id, anchor_group_id)).fetchall()

    if not evidence_rows:
        raise HTTPException(status_code=404, detail="Cluster not found in latest run")

    # Collect all member group IDs
    member_ids = {anchor_group_id}
    for row in evidence_rows:
        member_ids.add(row['source_group_id'])

    # Fetch member group details
    members = []
    for gid in sorted(member_ids):
        g = db.execute(
            "SELECT id, display_name, normalized_name, status, transaction_count, property_count FROM groups WHERE id = ?",
            (gid,)
        ).fetchone()
        if g:
            members.append(dict(g))

    # Fetch anchor detail
    anchor = db.execute(
        "SELECT id, display_name, normalized_name, status, transaction_count, property_count FROM groups WHERE id = ?",
        (anchor_group_id,)
    ).fetchone()

    # Build evidence list
    evidence = [dict(row) for row in evidence_rows]

    # Group evidence by signal type for summary
    signal_summary = {}
    for e in evidence:
        st = e['signal_type']
        if st not in signal_summary:
            signal_summary[st] = set()
        signal_summary[st].add(e['signal_value'])
    signal_summary = {k: sorted(v) for k, v in signal_summary.items()}

    return {
        "anchor": dict(anchor) if anchor else None,
        "members": members,
        "member_count": len(members),
        "evidence": evidence,
        "signal_summary": signal_summary,
    }


# ── Run History ─────────────────────────────────────────────

@router.get("/runs")
def list_runs(
    limit: int = Query(20, ge=1, le=100),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """List recent discovery runs."""
    rows = db.execute(
        "SELECT run_id, mode, started_at, completed_at, stats_json FROM discovery_runs ORDER BY started_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    return [
        {
            **dict(row),
            'stats': json.loads(row['stats_json']) if row['stats_json'] else None,
        }
        for row in rows
    ]


# ── Ground Truth ────────────────────────────────────────────

@router.get("/ground-truth")
def list_ground_truth(db=Depends(get_db), user=Depends(get_current_user)):
    """List all ground truth portfolios."""
    rows = db.execute("SELECT * FROM discovery_ground_truth ORDER BY portfolio_name").fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d['member_group_ids'] = json.loads(d['member_group_ids_json'])
        del d['member_group_ids_json']
        result.append(d)
    return result


# ── Exclusions ──────────────────────────────────────────────

class ExclusionRequest(BaseModel):
    exclusion_type: str  # 'address', 'contact', 'phone', 'entity'
    exclusion_value: str
    reason: str = ''


@router.post("/exclusions")
def add_exclusion(req: ExclusionRequest, db=Depends(get_db), user=Depends(get_current_user)):
    """Add a discovery exclusion (e.g., exclude a law firm address)."""
    db.execute(
        "INSERT INTO discovery_exclusions (exclusion_type, exclusion_value, reason, created_by) VALUES (?, ?, ?, ?)",
        (req.exclusion_type, req.exclusion_value, req.reason, user['username'])
    )
    db.commit()
    return {"status": "ok"}


@router.get("/exclusions")
def list_exclusions(db=Depends(get_db), user=Depends(get_current_user)):
    """List all discovery exclusions."""
    rows = db.execute("SELECT * FROM discovery_exclusions ORDER BY exclusion_type, created_at DESC").fetchall()
    return [dict(row) for row in rows]


@router.delete("/exclusions/{exclusion_id}")
def remove_exclusion(exclusion_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    """Remove a discovery exclusion."""
    db.execute("DELETE FROM discovery_exclusions WHERE id = ?", (exclusion_id,))
    db.commit()
    return {"status": "ok"}
```

- [ ] **Step 2: Register the router in app.py**

In `cleo/web/app.py`, add after the activities router import (line 33):

```python
from .routes.discovery import router as discovery_router
```

And add after the activities include_router (line 84):

```python
app.include_router(discovery_router, prefix="/api/discovery", tags=["discovery"])
```

- [ ] **Step 3: Verify the server starts**

Run: `cd /Users/brandonolsen23/cleo-turbo && timeout 5 python -c "from cleo.web.app import app; print('App created OK')" 2>&1 || true`
Expected: "App created OK"

- [ ] **Step 4: Commit**

```bash
git add cleo/web/routes/discovery.py cleo/web/app.py
git commit -m "feat(discovery): API routes for cluster browsing, detail, ground truth, exclusions"
```

---

### Task 9: Frontend — Discovery Page and Cluster Detail

**Files:**
- Create: `frontend/src/pages/DiscoveryPage.tsx`
- Create: `frontend/src/pages/DiscoveryClusterPage.tsx`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/layout/Sidebar.tsx`

- [ ] **Step 1: Add TypeScript interfaces**

Add to `frontend/src/types/index.ts`:

```typescript
// ── Discovery ──────────────────────────────────────────────

export interface DiscoveryClusterSummary {
  anchor_group_id: string;
  anchor_name: string;
  member_count: number;
  portfolio_value: number;
  confidence: number;
  signal_count: number;
  status: string;
}

export interface DiscoveryRun {
  run_id: string;
  mode: string;
  started_at: string;
  completed_at: string | null;
  stats: {
    clusters_found: number;
    groups_processed: number;
    evidence_written: number;
    signal_counts: Record<string, number>;
    ground_truth?: Record<string, { precision: number; recall: number; missing: string[]; unexpected: string[] }>;
  } | null;
}

export interface DiscoveryBrowseResponse {
  results: DiscoveryClusterSummary[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
  run: DiscoveryRun | null;
}

export interface DiscoveryEvidence {
  source_group_id: string;
  target_group_id: string;
  signal_type: string;
  signal_value: string;
  source_id: string;
  rule_id: string;
  confidence: number;
  iteration: number;
}

export interface DiscoveryClusterDetail {
  anchor: {
    id: string;
    display_name: string;
    normalized_name: string;
    status: string;
    transaction_count: number;
    property_count: number;
  } | null;
  members: {
    id: string;
    display_name: string;
    normalized_name: string;
    status: string;
    transaction_count: number;
    property_count: number;
  }[];
  member_count: number;
  evidence: DiscoveryEvidence[];
  signal_summary: Record<string, string[]>;
}
```

- [ ] **Step 2: Create the Discovery browse page**

```tsx
// frontend/src/pages/DiscoveryPage.tsx
import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Heading, Text, Badge } from "@radix-ui/themes";
import { MagnifyingGlass } from "@phosphor-icons/react";
import { fetchApi } from "../api/client";
import { formatCurrency } from "../lib/utils";
import type { DiscoveryBrowseResponse, DiscoveryClusterSummary } from "../types";

export default function DiscoveryPage() {
  const navigate = useNavigate();
  const [data, setData] = useState<DiscoveryBrowseResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);

  useEffect(() => {
    setLoading(true);
    fetchApi<DiscoveryBrowseResponse>("/discovery", { page, per_page: 50 })
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [page]);

  return (
    <div className="p-6 max-w-[1200px] mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <Heading size="6">Group Discovery</Heading>
          <Text size="2" style={{ color: "var(--gray-9)" }}>
            Portfolio clusters discovered by the algorithm
          </Text>
        </div>
        {data?.run && (
          <div className="text-right">
            <Text size="1" style={{ color: "var(--gray-9)" }}>
              Last run: {new Date(data.run.started_at).toLocaleString()} ({data.run.mode})
            </Text>
            {data.run.stats && (
              <div>
                <Text size="1" style={{ color: "var(--gray-9)" }}>
                  {data.run.stats.clusters_found} clusters, {data.run.stats.groups_processed} groups
                </Text>
              </div>
            )}
          </div>
        )}
      </div>

      {loading ? (
        <Text>Loading...</Text>
      ) : !data || data.results.length === 0 ? (
        <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-8 text-center">
          <MagnifyingGlass size={32} style={{ color: "var(--gray-8)" }} className="mx-auto mb-3" />
          <Text size="3" style={{ color: "var(--gray-9)" }}>
            No discovery results yet. Run the algorithm from the CLI:
          </Text>
          <pre className="mt-2 text-sm bg-[var(--gray-3)] p-3 rounded inline-block">
            python -m cleo.discovery run --validate
          </pre>
        </div>
      ) : (
        <>
          <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="bg-[var(--gray-2)] border-b border-[var(--gray-6)]">
                  <th className="text-left px-4 py-3 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Portfolio</th>
                  <th className="text-right px-4 py-3 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Members</th>
                  <th className="text-right px-4 py-3 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Portfolio Value</th>
                  <th className="text-right px-4 py-3 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Signals</th>
                  <th className="text-center px-4 py-3 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Status</th>
                </tr>
              </thead>
              <tbody>
                {data.results.map((cluster: DiscoveryClusterSummary) => (
                  <tr
                    key={cluster.anchor_group_id}
                    onClick={() => navigate(`/discovery/${cluster.anchor_group_id}`)}
                    className="border-b border-[var(--gray-4)] cursor-pointer hover:bg-[var(--gray-2)] transition-colors"
                  >
                    <td className="px-4 py-3">
                      <Text size="2" weight="medium">{cluster.anchor_name}</Text>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Text size="2">{cluster.member_count}</Text>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Text size="2">{cluster.portfolio_value ? formatCurrency(cluster.portfolio_value) : "-"}</Text>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Text size="2">{cluster.signal_count}</Text>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <Badge
                        color={cluster.status === "auto_confirmed" ? "green" : "amber"}
                        size="1"
                      >
                        {cluster.status === "auto_confirmed" ? "Confirmed" : "Review"}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {data.pages > 1 && (
            <div className="flex items-center justify-between mt-4">
              <Text size="2" style={{ color: "var(--gray-9)" }}>
                {data.total} clusters total
              </Text>
              <div className="flex gap-2">
                <button
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                  disabled={page <= 1}
                  className="px-3 py-1 text-sm rounded border border-[var(--gray-6)] disabled:opacity-50"
                >
                  Previous
                </button>
                <button
                  onClick={() => setPage(p => Math.min(data.pages, p + 1))}
                  disabled={page >= data.pages}
                  className="px-3 py-1 text-sm rounded border border-[var(--gray-6)] disabled:opacity-50"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Create the Cluster Detail page**

```tsx
// frontend/src/pages/DiscoveryClusterPage.tsx
import { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { Heading, Text, Badge } from "@radix-ui/themes";
import { ArrowLeft } from "@phosphor-icons/react";
import { fetchApi } from "../api/client";
import type { DiscoveryClusterDetail } from "../types";

const SIGNAL_LABELS: Record<string, string> = {
  address: "Shared Addresses",
  contact: "Shared Contacts",
  phone: "Shared Phones",
  trade_name: "Trade Names",
  care_of: "Care-of Entities",
  entity: "Co-occurring Entities",
};

const SIGNAL_COLORS: Record<string, "blue" | "green" | "orange" | "purple" | "red" | "amber"> = {
  address: "blue",
  contact: "green",
  phone: "orange",
  trade_name: "purple",
  care_of: "amber",
  entity: "red",
};

export default function DiscoveryClusterPage() {
  const { clusterId } = useParams<{ clusterId: string }>();
  const [data, setData] = useState<DiscoveryClusterDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!clusterId) return;
    fetchApi<DiscoveryClusterDetail>(`/discovery/clusters/${clusterId}`)
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [clusterId]);

  if (loading) return <div className="p-6"><Text>Loading...</Text></div>;
  if (!data) return <div className="p-6"><Text>Cluster not found.</Text></div>;

  return (
    <div className="p-6 max-w-[1200px] mx-auto">
      <Link to="/discovery" className="flex items-center gap-1 mb-4 text-sm no-underline" style={{ color: "var(--accent-11)" }}>
        <ArrowLeft size={14} /> Discovery
      </Link>

      <div className="mb-6">
        <Heading size="6">{data.anchor?.display_name || clusterId}</Heading>
        <Text size="2" style={{ color: "var(--gray-9)" }}>
          {data.member_count} member groups, {data.evidence.length} evidence signals
        </Text>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Signal Summary Card */}
        <div className="lg:col-span-1 rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
          <Heading size="3" className="mb-4">Signal Summary</Heading>
          {Object.entries(data.signal_summary).map(([type, values]) => (
            <div key={type} className="mb-4">
              <Text size="2" weight="medium" className="mb-1 block">
                {SIGNAL_LABELS[type] || type}
              </Text>
              <div className="flex flex-wrap gap-1">
                {values.map((v: string) => (
                  <Badge key={v} color={SIGNAL_COLORS[type] || "gray"} size="1">{v}</Badge>
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* Members Table */}
        <div className="lg:col-span-2 rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
          <div className="px-5 py-3 border-b border-[var(--gray-6)] bg-[var(--gray-2)]">
            <Heading size="3">Member Groups</Heading>
          </div>
          <table className="w-full">
            <thead>
              <tr className="border-b border-[var(--gray-6)]">
                <th className="text-left px-4 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Group</th>
                <th className="text-right px-4 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Transactions</th>
                <th className="text-right px-4 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Properties</th>
                <th className="text-center px-4 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Status</th>
              </tr>
            </thead>
            <tbody>
              {data.members.map((m) => (
                <tr key={m.id} className="border-b border-[var(--gray-4)]">
                  <td className="px-4 py-2">
                    <Link to={`/groups/${m.id}`} className="no-underline" style={{ color: "var(--accent-11)" }}>
                      <Text size="2">{m.display_name}</Text>
                    </Link>
                    {m.id === data.anchor?.id && (
                      <Badge color="jade" size="1" className="ml-2">anchor</Badge>
                    )}
                  </td>
                  <td className="px-4 py-2 text-right"><Text size="2">{m.transaction_count}</Text></td>
                  <td className="px-4 py-2 text-right"><Text size="2">{m.property_count}</Text></td>
                  <td className="px-4 py-2 text-center">
                    <Badge color={m.status === "merged" ? "gray" : "green"} size="1">{m.status}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Evidence Table */}
      <div className="mt-6 rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
        <div className="px-5 py-3 border-b border-[var(--gray-6)] bg-[var(--gray-2)]">
          <Heading size="3">Evidence Chain</Heading>
        </div>
        <table className="w-full">
          <thead>
            <tr className="border-b border-[var(--gray-6)]">
              <th className="text-left px-4 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Signal Type</th>
              <th className="text-left px-4 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Value</th>
              <th className="text-left px-4 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Source Group</th>
              <th className="text-left px-4 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Rule</th>
              <th className="text-right px-4 py-2 text-[12px] font-medium" style={{ color: "var(--gray-9)" }}>Confidence</th>
            </tr>
          </thead>
          <tbody>
            {data.evidence.map((e, i) => (
              <tr key={i} className="border-b border-[var(--gray-4)]">
                <td className="px-4 py-2">
                  <Badge color={SIGNAL_COLORS[e.signal_type] || "gray"} size="1">{e.signal_type}</Badge>
                </td>
                <td className="px-4 py-2"><Text size="2">{e.signal_value}</Text></td>
                <td className="px-4 py-2">
                  <Link to={`/groups/${e.source_group_id}`} className="no-underline text-sm" style={{ color: "var(--accent-11)" }}>
                    {e.source_group_id}
                  </Link>
                </td>
                <td className="px-4 py-2"><Text size="2">{e.rule_id}</Text></td>
                <td className="px-4 py-2 text-right"><Text size="2">{(e.confidence * 100).toFixed(0)}%</Text></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Add routes to App.tsx**

In `frontend/src/App.tsx`, add the imports after the existing page imports (around line 40):

```typescript
import DiscoveryPage from "./pages/DiscoveryPage";
import DiscoveryClusterPage from "./pages/DiscoveryClusterPage";
```

Add routes inside the `<Route element={<AppLayout />}>` block, after the groups routes:

```tsx
<Route path="/discovery" element={<DiscoveryPage />} />
<Route path="/discovery/:clusterId" element={<DiscoveryClusterPage />} />
```

- [ ] **Step 5: Add Discovery to the sidebar**

In `frontend/src/components/layout/Sidebar.tsx`, add the import for the icon:

```typescript
import { Buildings, ChartBar, Users, UsersThree, Table, MapTrifold, Kanban, ListBullets, FlowArrow, ShieldCheck, GearSix, ClockCounterClockwise, Sliders, Handshake, TreeStructure } from "@phosphor-icons/react";
```

Add the Discovery nav item to the Pipeline section (after the Data Quality item):

```typescript
{ path: "/discovery", label: "Discovery", icon: TreeStructure },
```

- [ ] **Step 6: Verify TypeScript compiles**

Run: `cd /Users/brandonolsen23/cleo-turbo/frontend && npx tsc --noEmit`
Expected: No type errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/DiscoveryPage.tsx frontend/src/pages/DiscoveryClusterPage.tsx frontend/src/types/index.ts frontend/src/App.tsx frontend/src/components/layout/Sidebar.tsx
git commit -m "feat(discovery): frontend discovery page with cluster list and detail views"
```

---

## Phase 2: Rule Hierarchy (Tasks 10-13)

After Phase 1 is validated against DH ground truth, these tasks add the full matching engine.

---

### Task 10: Contact Tenure Establishment (Step 3)

**Files:**
- Create: `cleo/discovery/contacts.py`
- Test: `tests/test_discovery_rules.py`

Build contact tenure windows from transaction data. For each contact, determine first/last transaction date per group. Detect career changes (clean date partitioning across groups). Flag contacts as "distinctive" (all appearances in one cluster) or "non-distinctive" (appears across unrelated clusters).

**Key queries:**
- `transaction_parties` JOIN `transactions` grouped by `contact_id, group_id` with `MIN(sale_date), MAX(sale_date), COUNT(*)`
- Gap detection: if a contact's appearances at Group A end in 2015 and at Group B start in 2016 with no overlap, assign separate tenures

---

### Task 11: Rule Hierarchy Engine (Step 4)

**Files:**
- Create: `cleo/discovery/rules.py`
- Test: `tests/test_discovery_rules.py`

Implement Rules 4a through 4j from the design spec. Each rule is a function that takes a candidate group + existing cluster and returns a confidence score + evidence. Rules are evaluated in order of confidence:

| Rule | Signals | Confidence | Action |
|---|---|---|---|
| 4a | Management company + Contact | 1.00 | Auto-confirm |
| 4b | Contact + Address | 0.99 | Auto-confirm |
| 4c | Management company + Address | 0.95 | Auto-confirm |
| 4d | Management company + Phone | 0.90 | Auto-confirm |
| 4e | Distinctive contact alone (in tenure) | 0.90 | Auto-confirm |
| 4f | Contact + distinctive name fragment (in tenure) | 0.85 | Auto-confirm |
| 4g | Phone + name fragment or address | 0.80 | Auto-confirm |
| 4h | Contact + address change bridged by mgmt co | 0.90 | Confirm + register address |
| 4i | Address alone (clean context) | 0.60 | Suggest only |
| 4j | Single signal only | 0.00 | No action |

Each rule function signature: `def rule_4a(candidate_gid, cluster, signals_index, db) -> (confidence, [Evidence])`

---

### Task 12: Iterative Expansion + Cluster Splitting (Steps 5-6)

**Files:**
- Modify: `cleo/discovery/engine.py`

Enhance `run_discovery()` to:
1. After Step 1 clustering, run Steps 3-4 (tenure + rules) on unclustered groups
2. Repeat Step 4 until convergence (no new confirmations) or max iterations
3. After convergence, run Step 6: connected component analysis within each cluster to detect splits
4. Score final clusters (Step 7)

Critical: only auto-confirmed outputs (Rules 4a-4h) feed into next iteration. Suggestions (4i) and no-actions (4j) never become anchors without human confirmation.

---

### Task 13: Execute and Incremental Modes

**Files:**
- Modify: `cleo/discovery/engine.py`
- Modify: `cleo/discovery/cli.py`

Implement `--execute` mode:
1. Run full algorithm
2. For clusters above `min_confidence_auto`, call `execute_merge()` from `cleo/database/group_merge_ops.py`
3. Record merges in `group_merges` with `merged_by = 'discovery_algorithm'`
4. Refresh analytics for all affected groups

Implement `--incremental` mode:
1. Find transactions added since last run (`discovery_runs.completed_at`)
2. Extract signals for only those transactions
3. Match against existing clusters
4. Execute merges for high-confidence matches

---

## Phase 3: Signal Analytics + Polish (Tasks 14-15)

---

### Task 14: Signal Analytics Queries

**Files:**
- Create: `cleo/discovery/analytics.py`
- Add endpoint to: `cleo/web/routes/discovery.py`

Queries that surface patterns the algorithm isn't yet using:
- Top N phones shared across M+ groups (not yet in any cluster)
- Top N addresses shared across M+ groups (not yet in any cluster)
- Top N contacts appearing on M+ groups (not yet in any cluster)
- Name fragments with high co-occurrence but no rule match

These power the "help me find logic I'm not seeing" requirement. Results are surfaced via a `/discovery/analytics` API endpoint and displayed in the Discovery page.

---

### Task 15: Integration with Group Detail Page

**Files:**
- Modify: `frontend/src/pages/GroupDetailPage.tsx`
- Add endpoint to: `cleo/web/routes/discovery.py`

Add a `/discovery/suggestions/{group_id}` endpoint that returns pending discovery suggestions for a specific group. Surface these in the existing SuggestedLinksCard on the group detail page alongside the current address/contact/phone suggestions.

---

## Testing Strategy

All tests use pytest with in-memory SQLite databases. Each test module creates its own minimal schema and test data (no dependency on live database).

**Test pyramid:**
- `test_discovery_signals.py` — Unit tests for signal extraction (6+ tests)
- `test_discovery_clustering.py` — Unit tests for exact match clustering (3+ tests)
- `test_discovery_rules.py` — Unit tests for each rule in the hierarchy (10+ tests, one per rule)
- `test_discovery_engine.py` — Integration tests validating end-to-end against ground truth (4+ tests)

**Run all tests:**
```bash
cd /Users/brandonolsen23/cleo-turbo && python -m pytest tests/test_discovery_*.py -v
```

**Validate against live data:**
```bash
cd /Users/brandonolsen23/cleo-turbo && python -m cleo.discovery run --validate
```
