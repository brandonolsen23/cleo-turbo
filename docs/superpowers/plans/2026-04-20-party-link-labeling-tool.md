# Party Link Labeling Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the in-app labeling tool specified in `docs/superpowers/specs/2026-04-20-party-link-labeling-tool-design.md` — a workspace where the user picks an anchor RT party, walks a search-seed queue, and records field-level links between parties to produce a training-quality dataset of labeled party pairs.

**Architecture:** SQLite-backed session state with five new CRM-style tables; FastAPI routes under `/api/labeling`; React workspace at `/labeling/sessions/:id` with a four-column layout (session state / reference party / candidate party / candidate list) and an SVG overlay for drawing field-level links between two card-style party panes.

**Tech Stack:** Python 3.12 + FastAPI, SQLite (raw SQL, no ORM), React 19 + TypeScript + Radix UI Themes (jade/slate) + Tailwind + Phosphor Icons + react-router-dom v7.

**ID convention note:** The spec described `labeling_sessions.id` as `TEXT` (`LBL_NNNNN`). For implementation simplicity we use `INTEGER PRIMARY KEY AUTOINCREMENT` internally and format as `LBL_{id:05d}` in API responses (helper: `format_session_id(n: int) -> str`). URLs accept either the integer or the `LBL_NNNNN` form.

---

## Phase 1 — Database foundation

### Task 1: Create migration for labeling tables

**Files:**
- Create: `cleo/database/migrations/006_labeling_tables.py`

- [ ] **Step 1: Write the migration file**

```python
"""
Migration 006: Create labeling tables for party link labeling tool.

These are CRM-layer tables — never touched by the compiler.
Used by the /api/labeling endpoints to capture user-labeled
party pairs with field-level links.

Run:
    cd cleo-turbo
    python -m cleo.database.migrations.006_labeling_tables
"""

import sqlite3
import os


def migrate(conn):
    print("Migration 006: Creating labeling tables...")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS labeling_sessions (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            name                TEXT NOT NULL,
            audit_slug          TEXT,
            anchor_source_id    TEXT NOT NULL,
            anchor_side         TEXT NOT NULL CHECK (anchor_side IN ('buyer','seller')),
            status              TEXT NOT NULL DEFAULT 'active'
                                  CHECK (status IN ('active','paused','done')),
            created_by          TEXT NOT NULL,
            created_at          TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at          TEXT NOT NULL DEFAULT (datetime('now')),
            completed_at        TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_labeling_sessions_status ON labeling_sessions(status);
        CREATE INDEX IF NOT EXISTS idx_labeling_sessions_audit ON labeling_sessions(audit_slug);

        CREATE TABLE IF NOT EXISTS labeling_verdicts (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id          INTEGER NOT NULL REFERENCES labeling_sessions(id) ON DELETE CASCADE,
            source_id           TEXT NOT NULL,
            side                TEXT NOT NULL CHECK (side IN ('buyer','seller')),
            verdict             TEXT NOT NULL CHECK (verdict IN ('confirmed','rejected')),
            left_source_id      TEXT NOT NULL,
            left_side           TEXT NOT NULL CHECK (left_side IN ('buyer','seller')),
            seed_id             INTEGER REFERENCES labeling_seeds(id) ON DELETE SET NULL,
            rationale           TEXT,
            created_by          TEXT NOT NULL,
            created_at          TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE (session_id, source_id, side)
        );

        CREATE INDEX IF NOT EXISTS idx_labeling_verdicts_session ON labeling_verdicts(session_id);
        CREATE INDEX IF NOT EXISTS idx_labeling_verdicts_verdict ON labeling_verdicts(verdict);

        CREATE TABLE IF NOT EXISTS labeling_links (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            verdict_id          INTEGER NOT NULL REFERENCES labeling_verdicts(id) ON DELETE CASCADE,
            from_field_type     TEXT NOT NULL,
            from_field_value    TEXT NOT NULL,
            to_field_type       TEXT NOT NULL,
            to_field_value      TEXT NOT NULL,
            kind                TEXT NOT NULL CHECK (kind IN ('exact','implied')),
            created_at          TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_labeling_links_verdict ON labeling_links(verdict_id);

        CREATE TABLE IF NOT EXISTS labeling_seeds (
            id                              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id                      INTEGER NOT NULL REFERENCES labeling_sessions(id) ON DELETE CASCADE,
            term                            TEXT NOT NULL,
            field_type                      TEXT NOT NULL,
            state                           TEXT NOT NULL DEFAULT 'pending'
                                              CHECK (state IN ('pending','in_progress','done','skipped')),
            first_contributed_by_source_id  TEXT NOT NULL,
            first_contributed_by_side       TEXT NOT NULL CHECK (first_contributed_by_side IN ('buyer','seller')),
            completed_at                    TEXT,
            created_at                      TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE (session_id, term, field_type)
        );

        CREATE INDEX IF NOT EXISTS idx_labeling_seeds_session_state ON labeling_seeds(session_id, state);

        CREATE TABLE IF NOT EXISTS labeling_reviewed_index (
            session_id          INTEGER NOT NULL REFERENCES labeling_sessions(id) ON DELETE CASCADE,
            source_id           TEXT NOT NULL,
            side                TEXT NOT NULL CHECK (side IN ('buyer','seller')),
            reviewed_at         TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (session_id, source_id, side)
        );
    """)
    conn.commit()
    print("  Created 5 labeling tables.")

    for table in ['labeling_sessions', 'labeling_verdicts', 'labeling_links',
                  'labeling_seeds', 'labeling_reviewed_index']:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table} rows: {count}")
    print("Migration 006 complete.")


if __name__ == "__main__":
    db_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "cleo.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    migrate(conn)
    conn.close()
```

- [ ] **Step 2: Run the migration**

Run: `python -m cleo.database.migrations.006_labeling_tables`
Expected: prints "Migration 006 complete." and 5 tables at 0 rows each.

- [ ] **Step 3: Verify tables exist**

Run: `sqlite3 data/cleo.db ".tables" | grep labeling`
Expected: `labeling_links  labeling_reviewed_index  labeling_seeds  labeling_sessions  labeling_verdicts`

- [ ] **Step 4: Commit**

```bash
git add cleo/database/migrations/006_labeling_tables.py
git commit -m "feat(labeling): add migration for 5 labeling tables"
```

---

### Task 2: Document new CRM tables in CLAUDE.md

**Files:**
- Modify: `CLAUDE.md` (the CRM tables section)

- [ ] **Step 1: Append to the CRM tables list**

Find the block in CLAUDE.md that reads:

```
**CRM tables** (persistent, NEVER rebuilt or truncated):
deals, lists, list_members, group_contacts, contact_notes, group_notes,
sell_opportunities, buy_mandates, activities, property_enrichment,
brand_overrides, user_brand_favorites, group_overrides, group_field_overrides,
contact_field_overrides, contact_work_history, group_merges
```

Replace the final line with:

```
contact_field_overrides, contact_work_history, group_merges,
labeling_sessions, labeling_verdicts, labeling_links, labeling_seeds,
labeling_reviewed_index
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: register labeling tables as CRM tables"
```

---

## Phase 2 — Backend core services (TDD)

### Task 3: Audit markdown parser

**Files:**
- Create: `cleo/labeling/__init__.py` (empty)
- Create: `cleo/labeling/audit_parser.py`
- Create: `tests/test_labeling_audit_parser.py`

- [ ] **Step 1: Create the empty package init**

Create `cleo/labeling/__init__.py` with a single line:
```python
"""Party link labeling module."""
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_labeling_audit_parser.py`:

```python
"""Tests for audit markdown parser."""

import pytest
from pathlib import Path
from cleo.labeling.audit_parser import parse_audit_file, list_audits, AuditFile


def _write_fixture(tmp_path, content):
    d = tmp_path / "2026-04-19"
    d.mkdir()
    f = d / "08-plazacorp.md"
    f.write_text(content)
    return tmp_path


def test_parse_audit_extracts_parties_from_table(tmp_path):
    content = """# Plazacorp Investments Ltd

Some prose.

| group_id | side | party_name | trade_name | care_of | mailing | phone | source_id |
|---|---|---|---|---|---|---|---|
| GRP_01099 | buyer | Widmer Residences Corp | Plazacorp Investments Ltd |  | 10 Wanless | 416-481-2222 | RT101184 |
|  | buyer |  | Plazacorp Investments Ltd |  | 10 Wanless | 416-481-2222 | RT101911 |
| GRP_01867 | seller | 503-507 Bloor Street West Ltd | Plazacorp |  | 10 Wanless | 416-481-2222 | RT64069 |
"""
    docs_root = _write_fixture(tmp_path, content)

    result = parse_audit_file(docs_root / "2026-04-19" / "08-plazacorp.md")

    assert result.slug == "08-plazacorp"
    assert result.title == "Plazacorp Investments Ltd"
    assert len(result.parties) == 3
    assert result.parties[0] == {
        "source_id": "RT101184", "side": "buyer",
        "group_id": "GRP_01099", "party_name": "Widmer Residences Corp",
        "trade_name": "Plazacorp Investments Ltd", "care_of": "",
        "mailing": "10 Wanless", "phone": "416-481-2222",
    }
    # Blank group_id preserved as empty string, not dropped
    assert result.parties[1]["group_id"] == ""
    assert result.parties[1]["source_id"] == "RT101911"


def test_list_audits_returns_most_recent_date_folder(tmp_path):
    old = tmp_path / "2026-03-01"
    new = tmp_path / "2026-04-19"
    old.mkdir()
    new.mkdir()
    (new / "01-kingsett-capital.md").write_text("# KingSett Capital\n\n| source_id |\n|---|\n| RT1 |\n")
    (new / "README.md").write_text("# README")
    (old / "01-something.md").write_text("# Something\n\n| source_id |\n|---|\n| RT2 |\n")

    audits = list_audits(tmp_path)

    assert len(audits) == 1
    assert audits[0].slug == "01-kingsett-capital"
    assert audits[0].date_folder == "2026-04-19"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_labeling_audit_parser.py -v`
Expected: `ModuleNotFoundError: No module named 'cleo.labeling.audit_parser'`

- [ ] **Step 4: Implement the parser**

Create `cleo/labeling/audit_parser.py`:

```python
"""Parser for docs/discovery-audit/{YYYY-MM-DD}/*.md audit files.

Reads the markdown table (one row per transaction_parties row) and
returns a structured list of distinct (source_id, side) parties that
can anchor a labeling session.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
import re


@dataclass
class AuditFile:
    slug: str                    # e.g. "08-plazacorp"
    title: str                   # first H1 in the file
    date_folder: str             # e.g. "2026-04-19"
    path: Path
    parties: List[dict] = field(default_factory=list)


# Required column headers (lowercase)
_EXPECTED_COLS = {"group_id", "side", "party_name", "trade_name",
                  "care_of", "mailing", "phone", "source_id"}


def parse_audit_file(path: Path) -> AuditFile:
    """Parse a single audit markdown file.

    Returns an AuditFile with parties[] — one dict per table row.
    """
    text = path.read_text()
    slug = path.stem
    date_folder = path.parent.name

    # Title = first H1
    m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    title = m.group(1).strip() if m else slug

    # Find the table header row — line starting/ending with |, containing the expected columns
    lines = text.splitlines()
    header_idx = None
    for i, line in enumerate(lines):
        if not line.lstrip().startswith("|"):
            continue
        cells = [c.strip().lower() for c in line.strip().strip("|").split("|")]
        if _EXPECTED_COLS.issubset(set(cells)):
            header_idx = i
            break

    parties: List[dict] = []
    if header_idx is None:
        return AuditFile(slug=slug, title=title, date_folder=date_folder,
                         path=path, parties=parties)

    header_cells = [c.strip().lower() for c in lines[header_idx].strip().strip("|").split("|")]

    # Data rows start after header + separator line
    for line in lines[header_idx + 2:]:
        if not line.lstrip().startswith("|"):
            break  # table ended
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != len(header_cells):
            continue
        row = dict(zip(header_cells, cells))
        if not row.get("source_id") or not row.get("side"):
            continue
        parties.append({
            "source_id": row["source_id"],
            "side": row["side"],
            "group_id": row.get("group_id", ""),
            "party_name": row.get("party_name", ""),
            "trade_name": row.get("trade_name", ""),
            "care_of": row.get("care_of", ""),
            "mailing": row.get("mailing", ""),
            "phone": row.get("phone", ""),
        })

    return AuditFile(slug=slug, title=title, date_folder=date_folder,
                     path=path, parties=parties)


def list_audits(docs_root: Path) -> List[AuditFile]:
    """List audits from the most recent date folder under docs_root.

    docs_root is typically `docs/discovery-audit/`.
    """
    if not docs_root.is_dir():
        return []

    # Find most recent date folder (YYYY-MM-DD format, lexical sort works)
    date_dirs = sorted(
        [p for p in docs_root.iterdir()
         if p.is_dir() and re.match(r"\d{4}-\d{2}-\d{2}$", p.name)],
        reverse=True,
    )
    if not date_dirs:
        return []

    latest = date_dirs[0]
    results: List[AuditFile] = []
    for md in sorted(latest.glob("*.md")):
        if md.name.lower() == "readme.md":
            continue
        results.append(parse_audit_file(md))
    return results


def load_audit_by_slug(docs_root: Path, slug: str) -> Optional[AuditFile]:
    """Load a single audit by slug from the most recent date folder."""
    for audit in list_audits(docs_root):
        if audit.slug == slug:
            return audit
    return None
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_labeling_audit_parser.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add cleo/labeling/__init__.py cleo/labeling/audit_parser.py tests/test_labeling_audit_parser.py
git commit -m "feat(labeling): audit markdown parser"
```

---

### Task 4: Party view aggregator

**Files:**
- Create: `cleo/labeling/party_view.py`
- Create: `tests/test_labeling_party_view.py`

This service takes `(source_id, side)` and returns the aggregated party block used by both panes in the UI. It joins `transaction_parties` + `transactions` (for trade_name/care_of/companies_json/law_firms_json) + `transaction_mailing_addresses` + `contacts` (via `tp.contact_id`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_labeling_party_view.py`:

```python
"""Tests for the party view aggregator."""

import json
import sqlite3
import pytest
from cleo.labeling.party_view import get_party_view


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE transactions (
            source_id TEXT PRIMARY KEY,
            seller_trade_name TEXT, seller_care_of TEXT,
            seller_law_firms_json TEXT, seller_companies_json TEXT,
            buyer_trade_name TEXT, buyer_care_of TEXT,
            buyer_law_firms_json TEXT, buyer_companies_json TEXT
        );
        CREATE TABLE transaction_parties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT, side TEXT,
            party_name TEXT, phone TEXT, contact_id TEXT
        );
        CREATE TABLE transaction_mailing_addresses (
            source_id TEXT, side TEXT,
            display TEXT, street TEXT, city TEXT, province TEXT, postal TEXT
        );
        CREATE TABLE contacts (
            id TEXT PRIMARY KEY,
            display_name TEXT, phone TEXT, job_title TEXT
        );
    """)
    return conn


def test_party_view_aggregates_all_fields():
    conn = _make_db()
    conn.execute(
        "INSERT INTO transactions (source_id, buyer_trade_name, buyer_care_of, "
        "buyer_law_firms_json, buyer_companies_json) VALUES (?, ?, ?, ?, ?)",
        ("RT148276", "DH Management Inc", "", json.dumps(["Smith LLP"]),
         json.dumps(["DH Properties"]))
    )
    conn.execute(
        "INSERT INTO contacts (id, display_name, phone, job_title) VALUES (?, ?, ?, ?)",
        ("CON_00001", "Dan Hagler", "416-265-5055", "Pres")
    )
    conn.execute(
        "INSERT INTO transaction_parties (source_id, side, party_name, phone, contact_id) "
        "VALUES (?, ?, ?, ?, ?)",
        ("RT148276", "buyer", "Niagara Falls Shopping Centre Inc", "416-265-5055", None)
    )
    conn.execute(
        "INSERT INTO transaction_parties (source_id, side, party_name, phone, contact_id) "
        "VALUES (?, ?, ?, ?, ?)",
        ("RT148276", "buyer", None, None, "CON_00001")
    )
    conn.execute(
        "INSERT INTO transaction_mailing_addresses "
        "(source_id, side, display, street, city, province, postal) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("RT148276", "buyer", "180 Shorting Rd, Toronto M1S 3S7",
         "180 Shorting Rd", "Toronto", "Ontario", "M1S 3S7")
    )

    view = get_party_view(conn, "RT148276", "buyer")

    assert view["source_id"] == "RT148276"
    assert view["side"] == "buyer"
    assert view["trade_name"] == "DH Management Inc"
    assert view["law_firms"] == ["Smith LLP"]
    assert view["companies_other"] == ["DH Properties"]
    assert view["mailing"]["display"] == "180 Shorting Rd, Toronto M1S 3S7"
    assert "Niagara Falls Shopping Centre Inc" in [r["party_name"] for r in view["party_rows"]]
    assert view["contacts"][0]["name"] == "Dan Hagler"
    assert "416-265-5055" in view["phones"]


def test_party_view_returns_none_for_missing():
    conn = _make_db()
    assert get_party_view(conn, "RT999999", "buyer") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_labeling_party_view.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement the aggregator**

Create `cleo/labeling/party_view.py`:

```python
"""Party view aggregator — builds the full side-of-transaction block
used by the labeling UI's left/right panes.
"""

from __future__ import annotations
import json
from typing import Optional


def _parse_json_array(raw: Optional[str]) -> list:
    if not raw:
        return []
    try:
        val = json.loads(raw)
        return [str(x) for x in val] if isinstance(val, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def get_party_view(db, source_id: str, side: str) -> Optional[dict]:
    """Return aggregated party view for (source_id, side).

    Returns None if the transaction doesn't exist.
    """
    assert side in ("buyer", "seller")

    tx = db.execute(
        "SELECT * FROM transactions WHERE source_id = ?",
        (source_id,)
    ).fetchone()
    if not tx:
        return None

    prefix = f"{side}_"
    trade_name = tx[f"{prefix}trade_name"]
    care_of = tx[f"{prefix}care_of"]
    law_firms = _parse_json_array(tx[f"{prefix}law_firms_json"])
    companies_other = _parse_json_array(tx[f"{prefix}companies_json"])

    party_rows = [dict(r) for r in db.execute(
        "SELECT id, source_id, side, party_name, phone, contact_id "
        "FROM transaction_parties WHERE source_id = ? AND side = ? "
        "ORDER BY id",
        (source_id, side)
    )]

    # Contacts: look up each contact_id referenced by party rows
    contact_ids = [r["contact_id"] for r in party_rows if r["contact_id"]]
    contacts = []
    if contact_ids:
        placeholders = ",".join("?" for _ in contact_ids)
        contacts = [dict(r) for r in db.execute(
            f"SELECT id, display_name, phone, job_title FROM contacts WHERE id IN ({placeholders})",
            contact_ids
        )]
    contacts_out = [
        {"id": c["id"], "name": c["display_name"], "role": c.get("job_title"),
         "phone": c.get("phone"), "job_title": c.get("job_title")}
        for c in contacts
    ]

    mailing_row = db.execute(
        "SELECT display, street, city, province, postal "
        "FROM transaction_mailing_addresses "
        "WHERE source_id = ? AND side = ? LIMIT 1",
        (source_id, side)
    ).fetchone()
    mailing = dict(mailing_row) if mailing_row else None

    # Union of phones across party rows + contacts (deduped, preserving order)
    phones: list = []
    seen = set()
    for p in party_rows:
        ph = (p.get("phone") or "").strip()
        if ph and ph not in seen:
            phones.append(ph)
            seen.add(ph)
    for c in contacts_out:
        ph = (c.get("phone") or "").strip()
        if ph and ph not in seen:
            phones.append(ph)
            seen.add(ph)

    return {
        "source_id": source_id,
        "side": side,
        "party_rows": party_rows,
        "trade_name": trade_name,
        "care_of": care_of,
        "companies_other": companies_other,
        "law_firms": law_firms,
        "contacts": contacts_out,
        "mailing": mailing,
        "phones": phones,
    }
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_labeling_party_view.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add cleo/labeling/party_view.py tests/test_labeling_party_view.py
git commit -m "feat(labeling): party view aggregator"
```

---

### Task 5: Seed harvester

**Files:**
- Create: `cleo/labeling/seed_harvester.py`
- Create: `tests/test_labeling_seed_harvester.py`

Extracts all distinct `(term, field_type)` pairs from a party view — used to auto-populate the seed queue on session creation and on each confirmed verdict.

- [ ] **Step 1: Write the failing test**

Create `tests/test_labeling_seed_harvester.py`:

```python
"""Tests for the seed harvester — extracts search seeds from a party view."""

import pytest
from cleo.labeling.seed_harvester import harvest_seeds


def test_harvest_covers_all_field_types():
    view = {
        "source_id": "RT148276", "side": "buyer",
        "party_rows": [
            {"party_name": "Niagara Falls Shopping Centre Inc", "phone": "416-265-5055", "contact_id": None},
            {"party_name": None, "phone": None, "contact_id": "CON_1"},
        ],
        "trade_name": "DH Management Inc",
        "care_of": "c/o DH Properties",
        "companies_other": ["DH Properties"],
        "law_firms": ["Smith LLP"],
        "contacts": [{"name": "Dan Hagler", "phone": "416-265-5055", "role": "Pres"}],
        "mailing": {"display": "180 Shorting Rd, Toronto M1S 3S7"},
        "phones": ["416-265-5055"],
    }
    seeds = harvest_seeds(view)
    by_type = {(s["field_type"], s["term"]) for s in seeds}

    assert ("party_name", "Niagara Falls Shopping Centre Inc") in by_type
    assert ("trade_name", "DH Management Inc") in by_type
    assert ("care_of", "c/o DH Properties") in by_type
    assert ("company_other", "DH Properties") in by_type
    assert ("law_firm", "Smith LLP") in by_type
    assert ("contact_name", "Dan Hagler") in by_type
    assert ("address", "180 Shorting Rd, Toronto M1S 3S7") in by_type
    assert ("phone", "416-265-5055") in by_type


def test_harvest_dedups_and_strips():
    view = {
        "source_id": "RT1", "side": "buyer",
        "party_rows": [{"party_name": "  Acme Corp  ", "phone": None, "contact_id": None}],
        "trade_name": "Acme Corp",  # same as party_name — should still appear once per field_type
        "care_of": None, "companies_other": [], "law_firms": [],
        "contacts": [], "mailing": None, "phones": [],
    }
    seeds = harvest_seeds(view)

    # Same term "Acme Corp" under different field_types — both kept (they trigger different searches)
    terms_by_type = {(s["field_type"], s["term"]) for s in seeds}
    assert ("party_name", "Acme Corp") in terms_by_type
    assert ("trade_name", "Acme Corp") in terms_by_type


def test_harvest_ignores_blanks_and_none():
    view = {
        "source_id": "RT1", "side": "buyer",
        "party_rows": [{"party_name": "", "phone": "   ", "contact_id": None}],
        "trade_name": None, "care_of": "",
        "companies_other": ["", None, "Real Co"], "law_firms": [],
        "contacts": [{"name": None, "phone": ""}],
        "mailing": {"display": ""},
        "phones": [],
    }
    seeds = harvest_seeds(view)
    assert len(seeds) == 1
    assert seeds[0]["term"] == "Real Co"
    assert seeds[0]["field_type"] == "company_other"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_labeling_seed_harvester.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement the harvester**

Create `cleo/labeling/seed_harvester.py`:

```python
"""Seed harvester — extracts (term, field_type) pairs from a party view.

Used by the labeling tool to auto-populate the search-seed queue whenever
a party is confirmed into a session (and for the anchor at session creation).
"""

from __future__ import annotations
from typing import List


def _clean(s) -> str:
    if s is None:
        return ""
    return str(s).strip()


def harvest_seeds(view: dict) -> List[dict]:
    """Return a list of {term, field_type} dicts harvested from a party view.

    Deduplicated within each field_type; a single term can appear under
    multiple field_types (e.g. "Acme Corp" as both party_name and trade_name),
    since each triggers a different search semantics.
    """
    seeds: List[dict] = []
    seen: set = set()

    def add(field_type: str, term: str):
        term = _clean(term)
        if not term:
            return
        key = (field_type, term)
        if key in seen:
            return
        seen.add(key)
        seeds.append({"field_type": field_type, "term": term})

    for row in view.get("party_rows") or []:
        add("party_name", row.get("party_name"))
        add("phone", row.get("phone"))

    add("trade_name", view.get("trade_name"))
    add("care_of", view.get("care_of"))

    for v in view.get("companies_other") or []:
        add("company_other", v)
    for v in view.get("law_firms") or []:
        add("law_firm", v)

    for c in view.get("contacts") or []:
        add("contact_name", c.get("name"))
        add("phone", c.get("phone"))

    mailing = view.get("mailing") or {}
    add("address", mailing.get("display"))

    for ph in view.get("phones") or []:
        add("phone", ph)

    return seeds
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_labeling_seed_harvester.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add cleo/labeling/seed_harvester.py tests/test_labeling_seed_harvester.py
git commit -m "feat(labeling): seed harvester"
```

---

### Task 6: Labeling operations module

**Files:**
- Create: `cleo/labeling/operations.py`
- Create: `tests/test_labeling_operations.py`

Centralizes write operations that the API layer calls: create session (with anchor seeds), record verdict (with link rows and seed auto-harvest), search for candidates.

- [ ] **Step 1: Write the failing test**

Create `tests/test_labeling_operations.py`:

```python
"""Tests for labeling operations: create session, record verdict, search."""

import sqlite3
import pytest


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    # Core schema (minimal subset)
    conn.executescript("""
        CREATE TABLE transactions (
            source_id TEXT PRIMARY KEY,
            seller_trade_name TEXT, seller_care_of TEXT,
            seller_law_firms_json TEXT, seller_companies_json TEXT,
            buyer_trade_name TEXT, buyer_care_of TEXT,
            buyer_law_firms_json TEXT, buyer_companies_json TEXT
        );
        CREATE TABLE transaction_parties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT, side TEXT, party_name TEXT, phone TEXT, contact_id TEXT
        );
        CREATE TABLE transaction_mailing_addresses (
            source_id TEXT, side TEXT,
            display TEXT, street TEXT, city TEXT, province TEXT, postal TEXT
        );
        CREATE TABLE contacts (
            id TEXT PRIMARY KEY, display_name TEXT, phone TEXT, job_title TEXT
        );
    """)
    # Labeling schema
    import pathlib
    mig = pathlib.Path(__file__).parent.parent / "cleo" / "database" / "migrations" / "006_labeling_tables.py"
    src = mig.read_text()
    # Extract the executescript block (between the triple-quoted sql string)
    start = src.index('conn.executescript("""') + len('conn.executescript("""')
    end = src.index('""")', start)
    conn.executescript(src[start:end])
    return conn


def _seed_tx(conn, source_id, side, party_name, trade_name, phone=None, mailing=None):
    conn.execute(
        f"INSERT INTO transactions (source_id, {side}_trade_name) VALUES (?, ?) "
        "ON CONFLICT(source_id) DO UPDATE SET " + f"{side}_trade_name = excluded.{side}_trade_name",
        (source_id, trade_name)
    )
    conn.execute(
        "INSERT INTO transaction_parties (source_id, side, party_name, phone) VALUES (?, ?, ?, ?)",
        (source_id, side, party_name, phone)
    )
    if mailing:
        conn.execute(
            "INSERT INTO transaction_mailing_addresses (source_id, side, display) VALUES (?, ?, ?)",
            (source_id, side, mailing)
        )


def test_create_session_auto_harvests_anchor_seeds():
    from cleo.labeling.operations import create_session

    conn = _make_db()
    _seed_tx(conn, "RT1", "buyer", "Dan Hagler Investments Ltd", "DH Management Inc",
             phone="416-265-5055", mailing="180 Shorting Rd")

    session_id = create_session(
        conn, anchor_source_id="RT1", anchor_side="buyer",
        name="DH Management", audit_slug="05-huntington", created_by="brandon"
    )

    terms = {(r["term"], r["field_type"]) for r in conn.execute(
        "SELECT term, field_type FROM labeling_seeds WHERE session_id = ?", (session_id,)
    )}
    assert ("Dan Hagler Investments Ltd", "party_name") in terms
    assert ("DH Management Inc", "trade_name") in terms
    assert ("416-265-5055", "phone") in terms
    assert ("180 Shorting Rd", "address") in terms


def test_record_confirmed_verdict_auto_harvests_and_dedups():
    from cleo.labeling.operations import create_session, record_verdict

    conn = _make_db()
    _seed_tx(conn, "RT1", "buyer", "Party A", "DH Management Inc", phone="416-1")
    _seed_tx(conn, "RT2", "buyer", "Party B", "DH Management Inc", phone="416-2")

    session_id = create_session(
        conn, anchor_source_id="RT1", anchor_side="buyer",
        name="DH", audit_slug=None, created_by="brandon"
    )
    # RT1 anchor already contributed "DH Management Inc" as trade_name.
    # Confirming RT2 contributes it again — must not duplicate.
    verdict_id = record_verdict(
        conn, session_id=session_id,
        source_id="RT2", side="buyer",
        verdict="confirmed",
        left_source_id="RT1", left_side="buyer",
        seed_id=None, rationale="same trade_name",
        links=[{"from_field_type": "trade_name", "from_field_value": "DH Management Inc",
                "to_field_type": "trade_name", "to_field_value": "DH Management Inc",
                "kind": "exact"}],
        created_by="brandon",
    )
    assert verdict_id > 0

    dupes = conn.execute(
        "SELECT COUNT(*) FROM labeling_seeds WHERE session_id = ? "
        "AND term = ? AND field_type = ?",
        (session_id, "DH Management Inc", "trade_name")
    ).fetchone()[0]
    assert dupes == 1, "Seed should have been deduped, not re-inserted"

    # RT2's unique phone and party_name should be new seeds
    rt2_phone = conn.execute(
        "SELECT COUNT(*) FROM labeling_seeds WHERE session_id = ? "
        "AND term = ? AND field_type = 'phone'",
        (session_id, "416-2")
    ).fetchone()[0]
    assert rt2_phone == 1


def test_rejected_verdict_rejects_empty_links():
    from cleo.labeling.operations import create_session, record_verdict, VerdictValidationError

    conn = _make_db()
    _seed_tx(conn, "RT1", "buyer", "A", "X")
    _seed_tx(conn, "RT2", "buyer", "B", "Y")
    session_id = create_session(conn, "RT1", "buyer", "Session", None, "brandon")

    with pytest.raises(VerdictValidationError):
        record_verdict(
            conn, session_id=session_id, source_id="RT2", side="buyer",
            verdict="confirmed",  # confirmed with no links is invalid
            left_source_id="RT1", left_side="buyer",
            seed_id=None, rationale=None, links=[], created_by="brandon",
        )

    with pytest.raises(VerdictValidationError):
        record_verdict(
            conn, session_id=session_id, source_id="RT2", side="buyer",
            verdict="rejected",  # rejected with no rationale is invalid
            left_source_id="RT1", left_side="buyer",
            seed_id=None, rationale=None, links=[], created_by="brandon",
        )


def test_search_candidates_excludes_reviewed_and_matches_across_fields():
    from cleo.labeling.operations import create_session, search_candidates, mark_reviewed

    conn = _make_db()
    _seed_tx(conn, "RT1", "buyer", "Anchor Co", "Anchor Trade", phone="111")
    _seed_tx(conn, "RT2", "buyer", "Hit One", "Anchor Trade", phone="222")
    _seed_tx(conn, "RT3", "seller", "Hit Two via address", "Other",
             phone="333", mailing="Anchor Trade Ave")
    _seed_tx(conn, "RT4", "buyer", "Reviewed Already", "Anchor Trade", phone="444")

    session_id = create_session(conn, "RT1", "buyer", "S", None, "brandon")
    mark_reviewed(conn, session_id, "RT4", "buyer")

    hits = search_candidates(conn, session_id, term="Anchor Trade")
    keys = {(h["source_id"], h["side"]) for h in hits}

    # RT1 is anchor — not excluded automatically (users sometimes anchor a confirmed party)
    # RT2: matches via trade_name
    # RT3: matches via address "Anchor Trade Ave"
    # RT4: excluded (reviewed)
    assert ("RT2", "buyer") in keys
    assert ("RT3", "seller") in keys
    assert ("RT4", "buyer") not in keys
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_labeling_operations.py -v`
Expected: `ModuleNotFoundError: No module named 'cleo.labeling.operations'`

- [ ] **Step 3: Implement operations**

Create `cleo/labeling/operations.py`:

```python
"""Write operations + search for the labeling tool.

Called by the FastAPI routes — keep these functions free of FastAPI
imports so they can be tested standalone with an in-memory DB.
"""

from __future__ import annotations
from typing import List, Optional

from .party_view import get_party_view
from .seed_harvester import harvest_seeds


class VerdictValidationError(ValueError):
    pass


# ── Formatters ──────────────────────────────────────────────────

def format_session_id(n: int) -> str:
    return f"LBL_{n:05d}"


def parse_session_id(raw: str | int) -> int:
    """Accept either the integer form or 'LBL_NNNNN'."""
    if isinstance(raw, int):
        return raw
    s = str(raw).strip()
    if s.upper().startswith("LBL_"):
        s = s[4:]
    return int(s)


# ── Session lifecycle ──────────────────────────────────────────

def create_session(
    db, *, anchor_source_id: str, anchor_side: str,
    name: str, audit_slug: Optional[str], created_by: str,
) -> int:
    """Create a new session and auto-harvest anchor fields into seeds.

    Returns the new session id (integer). Formatted id via format_session_id.
    """
    assert anchor_side in ("buyer", "seller")
    view = get_party_view(db, anchor_source_id, anchor_side)
    if not view:
        raise ValueError(
            f"Anchor party not found: source_id={anchor_source_id}, side={anchor_side}"
        )

    cur = db.execute(
        "INSERT INTO labeling_sessions "
        "(name, audit_slug, anchor_source_id, anchor_side, status, created_by) "
        "VALUES (?, ?, ?, ?, 'active', ?)",
        (name, audit_slug, anchor_source_id, anchor_side, created_by),
    )
    session_id = cur.lastrowid

    _insert_seeds(db, session_id, harvest_seeds(view),
                  anchor_source_id, anchor_side)
    db.commit()
    return session_id


def mark_session_status(db, session_id: int, status: str):
    assert status in ("active", "paused", "done")
    completed_at_clause = ", completed_at = datetime('now')" if status == "done" else ""
    db.execute(
        f"UPDATE labeling_sessions SET status = ?, updated_at = datetime('now'){completed_at_clause} "
        "WHERE id = ?",
        (status, session_id),
    )
    db.commit()


# ── Verdicts ────────────────────────────────────────────────────

def record_verdict(
    db, *, session_id: int, source_id: str, side: str, verdict: str,
    left_source_id: str, left_side: str,
    seed_id: Optional[int], rationale: Optional[str],
    links: List[dict], created_by: str,
) -> int:
    """Record a verdict. Validates shape, inserts links, auto-harvests seeds on confirm.

    Returns the new verdict id.
    """
    if verdict not in ("confirmed", "rejected"):
        raise VerdictValidationError(f"Invalid verdict: {verdict}")
    if verdict == "confirmed" and not links:
        raise VerdictValidationError("Confirmed verdict requires at least one link")
    if verdict == "rejected" and links:
        raise VerdictValidationError("Rejected verdict must have no links")
    if verdict == "rejected" and not (rationale and rationale.strip()):
        raise VerdictValidationError("Rejected verdict requires a rationale")

    cur = db.execute(
        "INSERT INTO labeling_verdicts "
        "(session_id, source_id, side, verdict, left_source_id, left_side, "
        "seed_id, rationale, created_by) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (session_id, source_id, side, verdict, left_source_id, left_side,
         seed_id, rationale, created_by),
    )
    verdict_id = cur.lastrowid

    for link in links:
        db.execute(
            "INSERT INTO labeling_links "
            "(verdict_id, from_field_type, from_field_value, "
            "to_field_type, to_field_value, kind) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (verdict_id, link["from_field_type"], link["from_field_value"],
             link["to_field_type"], link["to_field_value"], link["kind"]),
        )

    # Auto-harvest seeds on confirm; reviewed_index always updated
    mark_reviewed(db, session_id, source_id, side, commit=False)
    if verdict == "confirmed":
        view = get_party_view(db, source_id, side)
        if view:
            _insert_seeds(db, session_id, harvest_seeds(view), source_id, side)

    db.commit()
    return verdict_id


def delete_verdict(db, verdict_id: int):
    db.execute("DELETE FROM labeling_verdicts WHERE id = ?", (verdict_id,))
    # labeling_links cascade via FK
    # Seeds are intentionally NOT rolled back (see spec)
    db.commit()


# ── Seeds ──────────────────────────────────────────────────────

def _insert_seeds(db, session_id: int, seeds: List[dict],
                  contributor_source_id: str, contributor_side: str):
    """Insert seeds (deduped via UNIQUE constraint — OR IGNORE)."""
    for s in seeds:
        db.execute(
            "INSERT OR IGNORE INTO labeling_seeds "
            "(session_id, term, field_type, state, "
            "first_contributed_by_source_id, first_contributed_by_side) "
            "VALUES (?, ?, ?, 'pending', ?, ?)",
            (session_id, s["term"], s["field_type"],
             contributor_source_id, contributor_side),
        )


def set_seed_state(db, seed_id: int, state: str):
    assert state in ("pending", "in_progress", "done", "skipped")
    completed_clause = ", completed_at = datetime('now')" if state in ("done", "skipped") else ""
    db.execute(
        f"UPDATE labeling_seeds SET state = ?{completed_clause} WHERE id = ?",
        (state, seed_id),
    )
    db.commit()


# ── Reviewed index ─────────────────────────────────────────────

def mark_reviewed(db, session_id: int, source_id: str, side: str, commit: bool = True):
    db.execute(
        "INSERT OR IGNORE INTO labeling_reviewed_index "
        "(session_id, source_id, side) VALUES (?, ?, ?)",
        (session_id, source_id, side),
    )
    if commit:
        db.commit()


# ── Search ─────────────────────────────────────────────────────

def search_candidates(
    db, session_id: int, *, term: str, field_type: Optional[str] = None, limit: int = 200,
) -> List[dict]:
    """Search RT parties for `term` across labelable fields, excluding reviewed.

    Returns list of {source_id, side, match_fields, preview} dicts.
    `field_type` is an optional hint — currently unused for ranking but accepted
    for API symmetry and future use.
    """
    like = f"%{term}%"
    # Union of hits across sources. Side is determined per source.
    rows = db.execute(
        """
        WITH hits AS (
            -- trade_name / care_of / company_other / law_firm on transactions (per-side prefix)
            SELECT source_id, 'buyer' AS side, 'trade_name' AS mf FROM transactions WHERE buyer_trade_name LIKE ?
            UNION
            SELECT source_id, 'buyer', 'care_of' FROM transactions WHERE buyer_care_of LIKE ?
            UNION
            SELECT source_id, 'buyer', 'company_other' FROM transactions WHERE buyer_companies_json LIKE ?
            UNION
            SELECT source_id, 'buyer', 'law_firm' FROM transactions WHERE buyer_law_firms_json LIKE ?
            UNION
            SELECT source_id, 'seller', 'trade_name' FROM transactions WHERE seller_trade_name LIKE ?
            UNION
            SELECT source_id, 'seller', 'care_of' FROM transactions WHERE seller_care_of LIKE ?
            UNION
            SELECT source_id, 'seller', 'company_other' FROM transactions WHERE seller_companies_json LIKE ?
            UNION
            SELECT source_id, 'seller', 'law_firm' FROM transactions WHERE seller_law_firms_json LIKE ?
            -- party_name and phone on transaction_parties
            UNION
            SELECT source_id, side, 'party_name' FROM transaction_parties WHERE party_name LIKE ?
            UNION
            SELECT source_id, side, 'phone' FROM transaction_parties WHERE phone LIKE ?
            -- address on mailing addresses
            UNION
            SELECT source_id, side, 'address' FROM transaction_mailing_addresses WHERE display LIKE ?
            -- contact_name via tp.contact_id -> contacts.display_name
            UNION
            SELECT tp.source_id, tp.side, 'contact_name'
              FROM transaction_parties tp JOIN contacts c ON c.id = tp.contact_id
              WHERE c.display_name LIKE ?
        )
        SELECT h.source_id, h.side,
               GROUP_CONCAT(DISTINCT h.mf) AS match_fields
        FROM hits h
        LEFT JOIN labeling_reviewed_index r
            ON r.session_id = ? AND r.source_id = h.source_id AND r.side = h.side
        WHERE r.source_id IS NULL
        GROUP BY h.source_id, h.side
        LIMIT ?
        """,
        (like, like, like, like, like, like, like, like,
         like, like, like, like, session_id, limit),
    ).fetchall()

    return [{"source_id": r["source_id"], "side": r["side"],
             "match_fields": (r["match_fields"] or "").split(",")}
            for r in rows]
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_labeling_operations.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add cleo/labeling/operations.py tests/test_labeling_operations.py
git commit -m "feat(labeling): session + verdict + search operations"
```

---

## Phase 3 — Backend API routes

### Task 7: Session + party endpoints

**Files:**
- Create: `cleo/web/routes/labeling.py`
- Modify: `cleo/web/app.py`

- [ ] **Step 1: Create the route module with session + party endpoints**

Create `cleo/web/routes/labeling.py`:

```python
"""Party link labeling API.

Endpoints under /api/labeling. See
docs/superpowers/specs/2026-04-20-party-link-labeling-tool-design.md
for the full design.
"""

from __future__ import annotations
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..deps import get_db, get_current_user
from ...labeling import operations as ops
from ...labeling.audit_parser import list_audits, load_audit_by_slug
from ...labeling.party_view import get_party_view
from ...labeling.seed_harvester import harvest_seeds

router = APIRouter()

DOCS_ROOT = Path(__file__).resolve().parents[3] / "docs" / "discovery-audit"


# ── Models ────────────────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    anchor_source_id: str
    anchor_side: str
    name: str
    audit_slug: Optional[str] = None


class PatchSessionRequest(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None


class LinkPayload(BaseModel):
    from_field_type: str
    from_field_value: str
    to_field_type: str
    to_field_value: str
    kind: str  # 'exact' | 'implied'


class VerdictRequest(BaseModel):
    source_id: str
    side: str
    verdict: str  # 'confirmed' | 'rejected'
    left_source_id: str
    left_side: str
    seed_id: Optional[int] = None
    rationale: Optional[str] = None
    links: List[LinkPayload] = []


class AddSeedRequest(BaseModel):
    term: str
    field_type: str


class SearchRequest(BaseModel):
    term: str
    field_type: Optional[str] = None
    session_id: int


class PatchSeedRequest(BaseModel):
    state: str  # 'pending' | 'in_progress' | 'done' | 'skipped'


class ReviewedRequest(BaseModel):
    source_id: str
    side: str


# ── Helpers ───────────────────────────────────────────────────

def _session_row(db, session_id: int) -> dict:
    row = db.execute("SELECT * FROM labeling_sessions WHERE id = ?", (session_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Session {session_id} not found")
    d = dict(row)
    d["display_id"] = ops.format_session_id(d["id"])
    return d


def _session_summary(db, session_id: int) -> dict:
    s = _session_row(db, session_id)
    counts = db.execute(
        "SELECT "
        "  SUM(verdict = 'confirmed') AS confirmed_count, "
        "  SUM(verdict = 'rejected') AS rejected_count "
        "FROM labeling_verdicts WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    seed_counts = db.execute(
        "SELECT state, COUNT(*) AS c FROM labeling_seeds "
        "WHERE session_id = ? GROUP BY state",
        (session_id,),
    ).fetchall()
    s["confirmed_count"] = counts["confirmed_count"] or 0
    s["rejected_count"] = counts["rejected_count"] or 0
    s["seeds_by_state"] = {r["state"]: r["c"] for r in seed_counts}
    return s


# ── Session endpoints ─────────────────────────────────────────

@router.get("/sessions")
def list_sessions(db=Depends(get_db), user=Depends(get_current_user)):
    rows = db.execute(
        "SELECT id FROM labeling_sessions ORDER BY updated_at DESC"
    ).fetchall()
    return {"sessions": [_session_summary(db, r["id"]) for r in rows]}


@router.post("/sessions")
def create_session(req: CreateSessionRequest, db=Depends(get_db), user=Depends(get_current_user)):
    try:
        sid = ops.create_session(
            db,
            anchor_source_id=req.anchor_source_id,
            anchor_side=req.anchor_side,
            name=req.name,
            audit_slug=req.audit_slug,
            created_by=user["username"],
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _session_summary(db, sid)


@router.get("/sessions/{session_id}")
def get_session(session_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    return _session_summary(db, ops.parse_session_id(session_id))


@router.patch("/sessions/{session_id}")
def patch_session(session_id: str, req: PatchSessionRequest,
                  db=Depends(get_db), user=Depends(get_current_user)):
    sid = ops.parse_session_id(session_id)
    if req.status:
        ops.mark_session_status(db, sid, req.status)
    if req.name:
        db.execute("UPDATE labeling_sessions SET name = ?, updated_at = datetime('now') WHERE id = ?",
                   (req.name, sid))
        db.commit()
    return _session_summary(db, sid)


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    sid = ops.parse_session_id(session_id)
    db.execute("DELETE FROM labeling_sessions WHERE id = ?", (sid,))
    db.commit()
    return {"deleted": True}


# ── Party fetch ───────────────────────────────────────────────

@router.get("/party/{source_id}/{side}")
def fetch_party(source_id: str, side: str,
                db=Depends(get_db), user=Depends(get_current_user)):
    view = get_party_view(db, source_id, side)
    if not view:
        raise HTTPException(404, f"Party not found: {source_id}/{side}")
    return view
```

- [ ] **Step 2: Register the router**

Modify `cleo/web/app.py`. After the `from .routes.discovery import router as discovery_router` line, add:

```python
from .routes.labeling import router as labeling_router
```

After the `app.include_router(discovery_router, ...)` line, add:

```python
    app.include_router(labeling_router, prefix="/api/labeling", tags=["labeling"])
```

- [ ] **Step 3: Smoke test it**

Restart the backend (`pkill -f uvicorn && uvicorn cleo.web.app:app --reload --port 8099 &`), then:

Run: `curl -s http://localhost:8099/openapi.json | python -c "import json,sys; paths=json.load(sys.stdin)['paths']; print('\n'.join(p for p in paths if '/labeling' in p))"`
Expected: 5 paths listed (`/api/labeling/sessions`, `/api/labeling/sessions/{session_id}`, `/api/labeling/party/{source_id}/{side}`).

- [ ] **Step 4: Commit**

```bash
git add cleo/web/routes/labeling.py cleo/web/app.py
git commit -m "feat(labeling): session + party API endpoints"
```

---

### Task 8: Seed queue, search, verdict, reviewed endpoints

**Files:**
- Modify: `cleo/web/routes/labeling.py`

- [ ] **Step 1: Append endpoint implementations**

Append to `cleo/web/routes/labeling.py`:

```python
# ── Seeds ─────────────────────────────────────────────────────

@router.get("/sessions/{session_id}/seeds")
def list_seeds(
    session_id: str,
    state: Optional[str] = Query(None),
    db=Depends(get_db), user=Depends(get_current_user),
):
    sid = ops.parse_session_id(session_id)
    if state:
        rows = db.execute(
            "SELECT * FROM labeling_seeds WHERE session_id = ? AND state = ? "
            "ORDER BY field_type, term",
            (sid, state),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM labeling_seeds WHERE session_id = ? "
            "ORDER BY state, field_type, term",
            (sid,),
        ).fetchall()
    return {"seeds": [dict(r) for r in rows]}


@router.post("/sessions/{session_id}/seeds")
def add_seed(
    session_id: str, req: AddSeedRequest,
    db=Depends(get_db), user=Depends(get_current_user),
):
    sid = ops.parse_session_id(session_id)
    sess = _session_row(db, sid)
    ops._insert_seeds(
        db, sid,
        [{"term": req.term.strip(), "field_type": req.field_type}],
        contributor_source_id=sess["anchor_source_id"],
        contributor_side=sess["anchor_side"],
    )
    db.commit()
    return {"added": True}


@router.patch("/sessions/{session_id}/seeds/{seed_id}")
def patch_seed(
    session_id: str, seed_id: int, req: PatchSeedRequest,
    db=Depends(get_db), user=Depends(get_current_user),
):
    ops.set_seed_state(db, seed_id, req.state)
    return {"updated": True}


@router.post("/sessions/{session_id}/seeds/{seed_id}/search")
def run_seed_search(
    session_id: str, seed_id: int,
    db=Depends(get_db), user=Depends(get_current_user),
):
    sid = ops.parse_session_id(session_id)
    seed = db.execute(
        "SELECT * FROM labeling_seeds WHERE id = ? AND session_id = ?",
        (seed_id, sid),
    ).fetchone()
    if not seed:
        raise HTTPException(404, "Seed not found")
    ops.set_seed_state(db, seed_id, "in_progress")
    hits = ops.search_candidates(
        db, sid, term=seed["term"], field_type=seed["field_type"]
    )
    return {
        "seed": dict(seed),
        "left_party": {"source_id": seed["first_contributed_by_source_id"],
                       "side": seed["first_contributed_by_side"]},
        "candidates": hits,
    }


# ── Generic search ────────────────────────────────────────────

@router.post("/search")
def generic_search(
    req: SearchRequest,
    db=Depends(get_db), user=Depends(get_current_user),
):
    hits = ops.search_candidates(db, req.session_id, term=req.term, field_type=req.field_type)
    return {"candidates": hits}


# ── Verdicts ──────────────────────────────────────────────────

@router.post("/sessions/{session_id}/verdicts")
def create_verdict(
    session_id: str, req: VerdictRequest,
    db=Depends(get_db), user=Depends(get_current_user),
):
    sid = ops.parse_session_id(session_id)
    try:
        verdict_id = ops.record_verdict(
            db, session_id=sid,
            source_id=req.source_id, side=req.side,
            verdict=req.verdict,
            left_source_id=req.left_source_id, left_side=req.left_side,
            seed_id=req.seed_id, rationale=req.rationale,
            links=[l.model_dump() for l in req.links],
            created_by=user["username"],
        )
    except ops.VerdictValidationError as e:
        raise HTTPException(400, str(e))
    return {"verdict_id": verdict_id}


@router.get("/sessions/{session_id}/verdicts")
def list_verdicts(
    session_id: str,
    db=Depends(get_db), user=Depends(get_current_user),
):
    sid = ops.parse_session_id(session_id)
    rows = db.execute(
        "SELECT * FROM labeling_verdicts WHERE session_id = ? ORDER BY created_at DESC",
        (sid,),
    ).fetchall()
    return {"verdicts": [dict(r) for r in rows]}


@router.get("/sessions/{session_id}/verdicts/{verdict_id}")
def get_verdict(
    session_id: str, verdict_id: int,
    db=Depends(get_db), user=Depends(get_current_user),
):
    v = db.execute("SELECT * FROM labeling_verdicts WHERE id = ?", (verdict_id,)).fetchone()
    if not v:
        raise HTTPException(404, "Verdict not found")
    links = db.execute(
        "SELECT * FROM labeling_links WHERE verdict_id = ?", (verdict_id,)
    ).fetchall()
    result = dict(v)
    result["links"] = [dict(l) for l in links]
    return result


@router.delete("/sessions/{session_id}/verdicts/{verdict_id}")
def remove_verdict(
    session_id: str, verdict_id: int,
    db=Depends(get_db), user=Depends(get_current_user),
):
    ops.delete_verdict(db, verdict_id)
    return {"deleted": True}


# ── Reviewed index ────────────────────────────────────────────

@router.post("/sessions/{session_id}/reviewed")
def mark_reviewed_endpoint(
    session_id: str, req: ReviewedRequest,
    db=Depends(get_db), user=Depends(get_current_user),
):
    ops.mark_reviewed(db, ops.parse_session_id(session_id), req.source_id, req.side)
    return {"marked": True}
```

- [ ] **Step 2: Smoke test create a session and record a verdict**

Pick any RT source_id in the DB and use it as the anchor. Example (replace RT184886 with a real ID):

```bash
TOKEN=$(curl -s -X POST http://localhost:8099/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"brandon","password":"<your-pw>"}' | python -c "import json,sys;print(json.load(sys.stdin)['token'])")

# Create a session
curl -s -X POST http://localhost:8099/api/labeling/sessions \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"anchor_source_id":"RT184886","anchor_side":"buyer","name":"Smoke Test"}'

# List seeds
curl -s http://localhost:8099/api/labeling/sessions/1/seeds -H "Authorization: Bearer $TOKEN" \
  | python -m json.tool | head -30
```

Expected: a created session with a non-empty seed list reflecting the anchor's fields.

- [ ] **Step 3: Commit**

```bash
git add cleo/web/routes/labeling.py
git commit -m "feat(labeling): seeds, search, verdicts, reviewed endpoints"
```

---

### Task 9: Audit integration + export endpoints

**Files:**
- Modify: `cleo/web/routes/labeling.py`

- [ ] **Step 1: Append audit + export endpoints**

Append to `cleo/web/routes/labeling.py`:

```python
# ── Audit integration ─────────────────────────────────────────

@router.get("/audits")
def audits(db=Depends(get_db), user=Depends(get_current_user)):
    audits = list_audits(DOCS_ROOT)
    result = []
    for a in audits:
        sessions = db.execute(
            "SELECT id, name, status, created_at FROM labeling_sessions "
            "WHERE audit_slug = ? ORDER BY created_at DESC",
            (a.slug,),
        ).fetchall()
        result.append({
            "slug": a.slug,
            "title": a.title,
            "date_folder": a.date_folder,
            "row_count": len(a.parties),
            "distinct_groups": len({p["group_id"] for p in a.parties if p["group_id"]}),
            "distinct_parties": len({(p["source_id"], p["side"]) for p in a.parties}),
            "sessions": [dict(s) for s in sessions],
        })
    return {"audits": result}


@router.get("/audits/{slug}/parties")
def audit_parties(slug: str, db=Depends(get_db), user=Depends(get_current_user)):
    a = load_audit_by_slug(DOCS_ROOT, slug)
    if not a:
        raise HTTPException(404, f"Audit {slug} not found")
    # Collapse to distinct (source_id, side); keep first-seen row's fields as preview
    seen = {}
    for row in a.parties:
        key = (row["source_id"], row["side"])
        if key not in seen:
            seen[key] = row
    return {
        "slug": a.slug,
        "title": a.title,
        "parties": list(seen.values()),
    }


# ── Export ────────────────────────────────────────────────────

def _build_export(db, session_id: int) -> dict:
    sess = dict(db.execute("SELECT * FROM labeling_sessions WHERE id = ?",
                            (session_id,)).fetchone())
    verdicts = db.execute(
        "SELECT * FROM labeling_verdicts WHERE session_id = ? ORDER BY created_at",
        (session_id,),
    ).fetchall()

    pairs = []
    stats = {"confirmed_count": 0, "rejected_count": 0,
             "seeds_processed": 0, "seeds_skipped": 0}
    for v in verdicts:
        v = dict(v)
        if v["verdict"] == "confirmed":
            stats["confirmed_count"] += 1
        else:
            stats["rejected_count"] += 1
        links = [dict(l) for l in db.execute(
            "SELECT from_field_type, from_field_value, "
            "to_field_type, to_field_value, kind "
            "FROM labeling_links WHERE verdict_id = ?",
            (v["id"],),
        )]
        left = get_party_view(db, v["left_source_id"], v["left_side"])
        right = get_party_view(db, v["source_id"], v["side"])
        seed_info = None
        if v["seed_id"]:
            s = db.execute("SELECT term, field_type FROM labeling_seeds WHERE id = ?",
                            (v["seed_id"],)).fetchone()
            if s:
                seed_info = {"term": s["term"], "field_type": s["field_type"]}
        pairs.append({
            "verdict": v["verdict"],
            "rationale": v["rationale"],
            "left":  {"source_id": v["left_source_id"], "side": v["left_side"],
                      "fields": _export_fields(left)},
            "right": {"source_id": v["source_id"], "side": v["side"],
                      "fields": _export_fields(right)},
            "links": links,
            "seed": seed_info,
            "created_at": v["created_at"],
        })

    for state in ("done", "skipped"):
        c = db.execute(
            "SELECT COUNT(*) FROM labeling_seeds WHERE session_id = ? AND state = ?",
            (session_id, state),
        ).fetchone()[0]
        stats[f"seeds_{'processed' if state == 'done' else 'skipped'}"] = c

    return {
        "session": {
            "id": ops.format_session_id(sess["id"]),
            "name": sess["name"],
            "audit_slug": sess["audit_slug"],
            "anchor": {"source_id": sess["anchor_source_id"],
                       "side": sess["anchor_side"]},
            "created_at": sess["created_at"],
            "completed_at": sess["completed_at"],
        },
        "pairs": pairs,
        "stats": stats,
    }


def _export_fields(view: Optional[dict]) -> dict:
    """Flat field dictionary for the export format."""
    if not view:
        return {}
    return {
        "party_name": [r.get("party_name") for r in (view["party_rows"] or []) if r.get("party_name")],
        "trade_name": view.get("trade_name"),
        "care_of": view.get("care_of"),
        "company_other": view.get("companies_other") or [],
        "law_firm": view.get("law_firms") or [],
        "contact_name": [c.get("name") for c in (view["contacts"] or []) if c.get("name")],
        "address": (view.get("mailing") or {}).get("display"),
        "phone": view.get("phones") or [],
    }


@router.get("/sessions/{session_id}/export")
def export_session(
    session_id: str,
    db=Depends(get_db), user=Depends(get_current_user),
):
    return _build_export(db, ops.parse_session_id(session_id))


@router.get("/export/all")
def export_all(db=Depends(get_db), user=Depends(get_current_user)):
    ids = [r["id"] for r in db.execute(
        "SELECT id FROM labeling_sessions WHERE status = 'done'"
    )]
    return {"sessions": [_build_export(db, sid) for sid in ids]}
```

- [ ] **Step 2: Smoke test the audit endpoint**

```bash
curl -s http://localhost:8099/api/labeling/audits -H "Authorization: Bearer $TOKEN" \
  | python -m json.tool | head -40
```

Expected: JSON with 8 audit entries, slugs like `01-kingsett-capital` through `08-plazacorp`.

- [ ] **Step 3: Commit**

```bash
git add cleo/web/routes/labeling.py
git commit -m "feat(labeling): audit + export endpoints"
```

---

## Phase 4 — Frontend data layer

### Task 10: TypeScript types + sidebar nav + routes

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/layout/AppLayout.tsx`
- Modify: `frontend/src/components/layout/Sidebar.tsx`

- [ ] **Step 1: Add types**

Append to `frontend/src/types/index.ts`:

```typescript
// ── Labeling ─────────────────────────────────────────────────

export type FieldType =
  | "party_name" | "trade_name" | "care_of" | "company_other"
  | "law_firm" | "contact_name" | "address" | "phone";

export type LinkKind = "exact" | "implied";

export interface LabelingSession {
  id: number;
  display_id: string; // e.g. "LBL_00001"
  name: string;
  audit_slug: string | null;
  anchor_source_id: string;
  anchor_side: "buyer" | "seller";
  status: "active" | "paused" | "done";
  created_by: string;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  confirmed_count: number;
  rejected_count: number;
  seeds_by_state: Record<string, number>;
}

export interface LabelingSeed {
  id: number;
  session_id: number;
  term: string;
  field_type: FieldType;
  state: "pending" | "in_progress" | "done" | "skipped";
  first_contributed_by_source_id: string;
  first_contributed_by_side: "buyer" | "seller";
  completed_at: string | null;
  created_at: string;
}

export interface LabelingCandidate {
  source_id: string;
  side: "buyer" | "seller";
  match_fields: string[];
}

export interface LabelingLinkInput {
  from_field_type: FieldType;
  from_field_value: string;
  to_field_type: FieldType;
  to_field_value: string;
  kind: LinkKind;
}

export interface LabelingLink extends LabelingLinkInput {
  id: number;
  verdict_id: number;
  created_at: string;
}

export interface LabelingVerdict {
  id: number;
  session_id: number;
  source_id: string;
  side: "buyer" | "seller";
  verdict: "confirmed" | "rejected";
  left_source_id: string;
  left_side: "buyer" | "seller";
  seed_id: number | null;
  rationale: string | null;
  created_by: string;
  created_at: string;
  links?: LabelingLink[];
}

export interface LabelingPartyView {
  source_id: string;
  side: "buyer" | "seller";
  party_rows: { id: number; party_name: string | null; phone: string | null; contact_id: string | null }[];
  trade_name: string | null;
  care_of: string | null;
  companies_other: string[];
  law_firms: string[];
  contacts: { id: string; name: string; role: string | null; phone: string | null; job_title: string | null }[];
  mailing: { display: string; street: string; city: string; province: string; postal: string } | null;
  phones: string[];
}

export interface LabelingAuditSummary {
  slug: string;
  title: string;
  date_folder: string;
  row_count: number;
  distinct_groups: number;
  distinct_parties: number;
  sessions: { id: number; name: string; status: string; created_at: string }[];
}

export interface LabelingAuditParty {
  source_id: string;
  side: "buyer" | "seller";
  group_id: string;
  party_name: string;
  trade_name: string;
  care_of: string;
  mailing: string;
  phone: string;
}
```

- [ ] **Step 2: Add sidebar entry**

Modify `frontend/src/components/layout/Sidebar.tsx`. In the Pipeline nav group, after the Discovery entry, add:

```typescript
      { path: "/labeling", label: "Labeling", icon: Tag },
```

Also add `Tag` to the Phosphor Icons import at the top of the file.

- [ ] **Step 3: Add full-bleed route and add lazy-loaded routes**

Modify `frontend/src/components/layout/AppLayout.tsx`, change:

```typescript
const FULL_BLEED_ROUTES = ["/map"];
```

to:

```typescript
const FULL_BLEED_ROUTES = ["/map", "/labeling/sessions/"];
```

Modify `frontend/src/App.tsx`:

Add lazy imports near the other lazy pages:

```typescript
const LabelingPage = lazy(() => import("./pages/LabelingPage"));
const LabelingAuditPage = lazy(() => import("./pages/LabelingAuditPage"));
const LabelingSessionPage = lazy(() => import("./pages/LabelingSessionPage"));
```

Inside the routes (after the `/discovery/:clusterId` line):

```typescript
                <Route path="/labeling" element={<LabelingPage />} />
                <Route path="/labeling/audits/:slug" element={<LabelingAuditPage />} />
                <Route path="/labeling/sessions/:id" element={<LabelingSessionPage />} />
```

- [ ] **Step 4: Commit (don't build yet — the pages don't exist yet and would break the build)**

```bash
git add frontend/src/types/index.ts frontend/src/App.tsx \
        frontend/src/components/layout/AppLayout.tsx frontend/src/components/layout/Sidebar.tsx
git commit -m "feat(labeling): types + routes + sidebar entry"
```

---

## Phase 5 — Frontend pages

### Task 11: Landing page at /labeling

**Files:**
- Create: `frontend/src/pages/LabelingPage.tsx`

Lists audits as cards with counts and existing sessions.

- [ ] **Step 1: Create the page**

Create `frontend/src/pages/LabelingPage.tsx`:

```tsx
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Heading, Text, Badge, Button } from "@radix-ui/themes";
import { Tag, CaretRight } from "@phosphor-icons/react";
import { fetchApi } from "../api/client";
import { formatDate } from "../lib/utils";
import type { LabelingAuditSummary, LabelingSession } from "../types";

export default function LabelingPage() {
  const [audits, setAudits] = useState<LabelingAuditSummary[]>([]);
  const [sessions, setSessions] = useState<LabelingSession[]>([]);

  useEffect(() => {
    fetchApi<{ audits: LabelingAuditSummary[] }>("/labeling/audits")
      .then((r) => setAudits(r.audits));
    fetchApi<{ sessions: LabelingSession[] }>("/labeling/sessions")
      .then((r) => setSessions(r.sessions));
  }, []);

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-center gap-2">
        <Tag size={20} weight="fill" style={{ color: "var(--accent-11)" }} />
        <Heading size="6">Portfolio Labeling</Heading>
      </div>
      <Text size="2" style={{ color: "var(--gray-11)" }}>
        Pick an audit to start labeling — each session captures field-level links between parties.
      </Text>

      <div>
        <Heading size="3" mb="2">Audits</Heading>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {audits.map((a) => (
            <Link
              key={a.slug}
              to={`/labeling/audits/${a.slug}`}
              className="no-underline rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5 hover:border-[var(--accent-8)]"
              style={{ color: "inherit" }}
            >
              <div className="flex items-start justify-between mb-2">
                <Heading size="3">{a.title}</Heading>
                <CaretRight size={16} style={{ color: "var(--gray-9)" }} />
              </div>
              <Text size="1" style={{ color: "var(--gray-9)" }}>
                {a.row_count} rows · {a.distinct_groups} groups · {a.distinct_parties} parties
              </Text>
              <div className="mt-2 flex flex-wrap gap-1">
                {a.sessions.map((s) => (
                  <Badge key={s.id} size="1" variant="soft" color={s.status === "done" ? "green" : "jade"}>
                    {s.name} · {s.status}
                  </Badge>
                ))}
                {a.sessions.length === 0 && (
                  <Badge size="1" variant="soft" color="gray">No sessions yet</Badge>
                )}
              </div>
            </Link>
          ))}
        </div>
      </div>

      <div>
        <Heading size="3" mb="2">Your sessions</Heading>
        {sessions.length === 0 && <Text size="2" style={{ color: "var(--gray-9)" }}>None yet.</Text>}
        <div className="flex flex-col gap-2">
          {sessions.map((s) => (
            <Link
              key={s.id}
              to={`/labeling/sessions/${s.id}`}
              className="no-underline rounded-[var(--card-radius)] border border-[var(--gray-6)] px-4 py-3 hover:border-[var(--accent-8)]"
              style={{ color: "inherit" }}
            >
              <div className="flex items-center justify-between">
                <div>
                  <Text size="3" weight="medium">{s.name}</Text>
                  <Text size="1" ml="2" style={{ color: "var(--gray-9)" }}>
                    {s.display_id} · {s.anchor_source_id}/{s.anchor_side}
                  </Text>
                </div>
                <div className="flex items-center gap-3">
                  <Badge size="1" variant="soft" color={s.status === "done" ? "green" : "jade"}>
                    {s.status}
                  </Badge>
                  <Text size="1" style={{ color: "var(--gray-9)" }}>
                    {s.confirmed_count}✓ / {s.rejected_count}✗
                  </Text>
                  <Text size="1" style={{ color: "var(--gray-9)" }}>
                    {formatDate(s.updated_at)}
                  </Text>
                </div>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Type-check and verify page loads**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

Restart frontend (`cd frontend && npm run dev`), visit http://localhost:5174/labeling.
Expected: 8 audit cards rendered.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/LabelingPage.tsx
git commit -m "feat(labeling): landing page at /labeling"
```

---

### Task 12: Audit browse page at /labeling/audits/:slug

**Files:**
- Create: `frontend/src/pages/LabelingAuditPage.tsx`

Shows the parties in the audit and lets the user start a session from one.

- [ ] **Step 1: Create the page**

Create `frontend/src/pages/LabelingAuditPage.tsx`:

```tsx
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Heading, Text, Badge, Button, TextField } from "@radix-ui/themes";
import { CaretLeft } from "@phosphor-icons/react";
import { fetchApi, postApi } from "../api/client";
import type { LabelingAuditParty, LabelingSession } from "../types";

interface AuditPartiesResponse {
  slug: string;
  title: string;
  parties: LabelingAuditParty[];
}

export default function LabelingAuditPage() {
  const { slug } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState<AuditPartiesResponse | null>(null);
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    fetchApi<AuditPartiesResponse>(`/labeling/audits/${slug}/parties`)
      .then((r) => { setData(r); setName(r.title); });
  }, [slug]);

  async function startSession(p: LabelingAuditParty) {
    setCreating(true);
    try {
      const s = await postApi<LabelingSession>("/labeling/sessions", {
        anchor_source_id: p.source_id,
        anchor_side: p.side,
        name: name || data?.title || slug,
        audit_slug: slug,
      });
      navigate(`/labeling/sessions/${s.id}`);
    } finally {
      setCreating(false);
    }
  }

  if (!data) return <div className="p-6"><Text>Loading…</Text></div>;

  return (
    <div className="flex flex-col gap-5 p-6">
      <Link to="/labeling" className="no-underline flex items-center gap-1"
            style={{ color: "var(--accent-11)" }}>
        <CaretLeft size={14} /> Labeling
      </Link>
      <Heading size="6">{data.title}</Heading>

      <div className="flex items-center gap-3">
        <Text size="2" style={{ color: "var(--gray-11)" }}>Session name:</Text>
        <TextField.Root size="2" value={name} onChange={(e) => setName(e.target.value)} />
      </div>

      <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden">
        <table className="w-full">
          <thead>
            <tr style={{ background: "var(--gray-2)" }}>
              {["RT ID", "Side", "Party", "Trade / Care-of", "Mailing", "Phone", ""].map((h) => (
                <th key={h} className="text-left px-3 py-2 text-[12px] font-medium"
                    style={{ color: "var(--gray-9)" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.parties.map((p, i) => (
              <tr key={i} className="border-t border-[var(--gray-4)]">
                <td className="px-3 py-2 text-[13px]">{p.source_id}</td>
                <td className="px-3 py-2">
                  <Badge size="1" variant="soft" color={p.side === "buyer" ? "jade" : "amber"}>
                    {p.side}
                  </Badge>
                </td>
                <td className="px-3 py-2 text-[13px]">{p.party_name || "—"}</td>
                <td className="px-3 py-2 text-[13px]">{p.trade_name || p.care_of || "—"}</td>
                <td className="px-3 py-2 text-[13px]" style={{ color: "var(--gray-11)" }}>
                  {p.mailing || "—"}
                </td>
                <td className="px-3 py-2 text-[13px]" style={{ color: "var(--gray-11)" }}>
                  {p.phone || "—"}
                </td>
                <td className="px-3 py-2">
                  <Button size="1" variant="soft" disabled={creating}
                          onClick={() => startSession(p)}>
                    Start as anchor
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Smoke test**

Visit http://localhost:5174/labeling/audits/08-plazacorp. Expected: 40 rows of parties. Click "Start as anchor" on any row → page navigates to /labeling/sessions/N.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/LabelingAuditPage.tsx
git commit -m "feat(labeling): audit browse + start-session page"
```

---

### Task 13: Session workspace skeleton

**Files:**
- Create: `frontend/src/pages/LabelingSessionPage.tsx`

Workspace with four columns; components for each column are added in later tasks. This task creates the skeleton and wires state.

- [ ] **Step 1: Create the page**

Create `frontend/src/pages/LabelingSessionPage.tsx`:

```tsx
import { useEffect, useState, useCallback } from "react";
import { Link, useParams } from "react-router-dom";
import { Heading, Text, Badge, Button } from "@radix-ui/themes";
import { CaretLeft, DownloadSimple } from "@phosphor-icons/react";
import { fetchApi, postApi, mutateApi } from "../api/client";
import type {
  LabelingSession, LabelingSeed, LabelingCandidate, LabelingPartyView,
  LabelingVerdict, LabelingLinkInput, LinkKind,
} from "../types";

import SeedQueuePanel from "../components/labeling/SeedQueuePanel";
import PartyCard from "../components/labeling/PartyCard";
import CandidateListPanel from "../components/labeling/CandidateListPanel";
import LinkCanvas from "../components/labeling/LinkCanvas";
import VerdictBar from "../components/labeling/VerdictBar";

export default function LabelingSessionPage() {
  const { id } = useParams();

  const [session, setSession] = useState<LabelingSession | null>(null);
  const [seeds, setSeeds] = useState<LabelingSeed[]>([]);
  const [verdicts, setVerdicts] = useState<LabelingVerdict[]>([]);
  const [currentSeed, setCurrentSeed] = useState<LabelingSeed | null>(null);
  const [candidates, setCandidates] = useState<LabelingCandidate[]>([]);
  const [leftParty, setLeftParty] = useState<LabelingPartyView | null>(null);
  const [rightParty, setRightParty] = useState<LabelingPartyView | null>(null);
  const [pendingLinks, setPendingLinks] = useState<LabelingLinkInput[]>([]);
  const [linkKind, setLinkKind] = useState<LinkKind>("exact");
  const [rationale, setRationale] = useState("");

  const reloadSession = useCallback(async () => {
    const s = await fetchApi<LabelingSession>(`/labeling/sessions/${id}`);
    setSession(s);
    const { seeds: ss } = await fetchApi<{ seeds: LabelingSeed[] }>(`/labeling/sessions/${id}/seeds`);
    setSeeds(ss);
    const { verdicts: vs } = await fetchApi<{ verdicts: LabelingVerdict[] }>(`/labeling/sessions/${id}/verdicts`);
    setVerdicts(vs);
  }, [id]);

  useEffect(() => { reloadSession(); }, [reloadSession]);

  async function runSeed(seed: LabelingSeed) {
    setCurrentSeed(seed);
    setRightParty(null);
    setPendingLinks([]);
    setRationale("");
    const r = await postApi<{
      seed: LabelingSeed;
      left_party: { source_id: string; side: "buyer" | "seller" };
      candidates: LabelingCandidate[];
    }>(`/labeling/sessions/${id}/seeds/${seed.id}/search`, {});
    setCandidates(r.candidates);
    const left = await fetchApi<LabelingPartyView>(
      `/labeling/party/${r.left_party.source_id}/${r.left_party.side}`
    );
    setLeftParty(left);
    reloadSession();
  }

  async function loadCandidate(c: LabelingCandidate) {
    const view = await fetchApi<LabelingPartyView>(`/labeling/party/${c.source_id}/${c.side}`);
    setRightParty(view);
    setPendingLinks([]);
    setRationale("");
    await postApi(`/labeling/sessions/${id}/reviewed`, { source_id: c.source_id, side: c.side });
  }

  async function submitVerdict(verdict: "confirmed" | "rejected" | "skip") {
    if (!rightParty || !leftParty) return;
    if (verdict === "skip") {
      await postApi(`/labeling/sessions/${id}/reviewed`, {
        source_id: rightParty.source_id, side: rightParty.side,
      });
    } else {
      await postApi(`/labeling/sessions/${id}/verdicts`, {
        source_id: rightParty.source_id,
        side: rightParty.side,
        verdict,
        left_source_id: leftParty.source_id,
        left_side: leftParty.side,
        seed_id: currentSeed?.id ?? null,
        rationale: rationale || null,
        links: verdict === "confirmed" ? pendingLinks : [],
      });
    }
    // Advance to next unreviewed candidate
    const nextIdx = candidates.findIndex(
      (c) => c.source_id === rightParty.source_id && c.side === rightParty.side
    );
    const next = candidates.slice(nextIdx + 1).find(
      (c) => !verdicts.find((v) => v.source_id === c.source_id && v.side === c.side)
    );
    if (next) await loadCandidate(next);
    else setRightParty(null);
    reloadSession();
  }

  async function exportJson() {
    const token = localStorage.getItem("cleo_token");
    const res = await fetch(`/api/labeling/sessions/${id}/export`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `labeling-session-${id}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  if (!session) return <div className="p-6"><Text>Loading…</Text></div>;

  return (
    <div className="flex flex-col h-full" style={{ height: "100vh" }}>
      {/* Top bar */}
      <div className="h-10 flex items-center gap-4 px-4 border-b border-[var(--gray-4)]"
           style={{ background: "var(--gray-2)" }}>
        <Link to="/labeling" className="no-underline flex items-center gap-1"
              style={{ color: "var(--accent-11)" }}>
          <CaretLeft size={14} />
        </Link>
        <Heading size="3">{session.name}</Heading>
        <Text size="1" style={{ color: "var(--gray-9)" }}>
          {session.display_id} · anchor {session.anchor_source_id}/{session.anchor_side}
        </Text>
        <div className="flex-1" />
        <Text size="1">{session.confirmed_count}✓ / {session.rejected_count}✗</Text>
        <Badge size="1" variant="soft">
          {session.seeds_by_state.pending ?? 0} seeds pending
        </Badge>
        <Button size="1" variant="soft" onClick={exportJson}>
          <DownloadSimple size={12} /> Export
        </Button>
      </div>

      {/* Body — four columns */}
      <div className="flex-1 flex overflow-hidden">
        <div className="w-[240px] border-r border-[var(--gray-4)] overflow-y-auto">
          <SeedQueuePanel
            sessionId={id!}
            seeds={seeds}
            verdicts={verdicts}
            currentSeedId={currentSeed?.id}
            onRunSeed={runSeed}
          />
        </div>

        <div className="flex-1 flex overflow-hidden relative">
          <div className="flex-1 p-4 overflow-auto border-r border-[var(--gray-4)]">
            {leftParty
              ? <PartyCard view={leftParty} side="left"
                           sharedHighlights={pendingLinks.map((l) => l.from_field_value)} />
              : <Text size="2" style={{ color: "var(--gray-9)" }}>
                  Pick a seed from the queue to start.
                </Text>}
          </div>
          <div className="flex-1 p-4 overflow-auto">
            {rightParty
              ? <PartyCard view={rightParty} side="right"
                           sharedHighlights={pendingLinks.map((l) => l.to_field_value)} />
              : <Text size="2" style={{ color: "var(--gray-9)" }}>
                  Pick a candidate from the list.
                </Text>}
          </div>
          <LinkCanvas links={pendingLinks} />
        </div>

        <div className="w-[300px] border-l border-[var(--gray-4)] overflow-y-auto">
          <CandidateListPanel
            candidates={candidates}
            verdicts={verdicts}
            currentRight={rightParty}
            onPick={loadCandidate}
          />
        </div>
      </div>

      {/* Action bar */}
      <VerdictBar
        linkKind={linkKind}
        setLinkKind={setLinkKind}
        rationale={rationale}
        setRationale={setRationale}
        disabled={!rightParty}
        pendingLinks={pendingLinks}
        setPendingLinks={setPendingLinks}
        onConfirm={() => submitVerdict("confirmed")}
        onReject={() => submitVerdict("rejected")}
        onSkip={() => submitVerdict("skip")}
      />
    </div>
  );
}
```

- [ ] **Step 2: The page imports 5 components that don't exist yet — that's expected.** These are implemented in Tasks 14-17.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/LabelingSessionPage.tsx
git commit -m "feat(labeling): session workspace page skeleton"
```

---

## Phase 6 — Workspace components

### Task 14: PartyCard + SeedQueuePanel + CandidateListPanel

**Files:**
- Create: `frontend/src/components/labeling/PartyCard.tsx`
- Create: `frontend/src/components/labeling/SeedQueuePanel.tsx`
- Create: `frontend/src/components/labeling/CandidateListPanel.tsx`

PartyCard renders the structured fields with per-row connector dots. The connector dot carries a `data-link-anchor` attribute that LinkCanvas (next task) reads to draw SVG lines.

- [ ] **Step 1: Create PartyCard**

Create `frontend/src/components/labeling/PartyCard.tsx`:

```tsx
import { Heading, Badge, Text } from "@radix-ui/themes";
import { Link as LinkIcon } from "@phosphor-icons/react";
import type { LabelingPartyView, FieldType } from "../../types";

interface Props {
  view: LabelingPartyView;
  side: "left" | "right";
  sharedHighlights: string[];
}

interface Row {
  field_type: FieldType;
  value: string;
  role?: string | null;
}

function buildRows(view: LabelingPartyView): Row[] {
  const rows: Row[] = [];
  for (const p of view.party_rows) {
    if (p.party_name) rows.push({ field_type: "party_name", value: p.party_name });
  }
  if (view.trade_name) rows.push({ field_type: "trade_name", value: view.trade_name });
  if (view.care_of)    rows.push({ field_type: "care_of",    value: view.care_of });
  for (const v of view.companies_other) rows.push({ field_type: "company_other", value: v });
  for (const v of view.law_firms)       rows.push({ field_type: "law_firm", value: v });
  for (const c of view.contacts) if (c.name)
    rows.push({ field_type: "contact_name", value: c.name, role: c.role });
  if (view.mailing?.display) rows.push({ field_type: "address", value: view.mailing.display });
  for (const ph of view.phones) rows.push({ field_type: "phone", value: ph });
  return rows;
}

const FIELD_LABEL: Record<FieldType, string> = {
  party_name: "Party",
  trade_name: "Trade name",
  care_of: "Care of",
  company_other: "Company",
  law_firm: "Law firm",
  contact_name: "Contact",
  address: "Address",
  phone: "Phone",
};

export default function PartyCard({ view, side, sharedHighlights }: Props) {
  const rows = buildRows(view);
  const anchorSide = side === "left" ? "right" : "left"; // dot on the inner edge

  return (
    <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)]"
         style={{ background: "white" }}>
      <div className="px-4 py-2 border-b border-[var(--gray-4)] flex items-center justify-between">
        <Heading size="2">{view.source_id}</Heading>
        <Badge size="1" variant="soft" color={view.side === "buyer" ? "jade" : "amber"}>
          {view.side}
        </Badge>
      </div>
      <div className="flex flex-col">
        {rows.map((r, i) => {
          const key = `${side}:${r.field_type}:${r.value}:${i}`;
          const highlighted = sharedHighlights.includes(r.value);
          return (
            <div key={key}
                 className="relative flex items-center gap-2 px-4 py-2 border-b border-[var(--gray-3)]"
                 style={{ background: highlighted ? "var(--accent-2)" : "transparent" }}>
              <Text size="1" style={{ color: "var(--gray-9)", width: 90, flexShrink: 0 }}>
                {FIELD_LABEL[r.field_type]}
                {r.role ? <> · <i>{r.role}</i></> : null}
              </Text>
              <Text size="2" className="flex-1">{r.value}</Text>
              <button
                data-link-anchor="1"
                data-field-type={r.field_type}
                data-field-value={r.value}
                data-pane={side}
                className="w-3 h-3 rounded-full border border-[var(--accent-9)] hover:bg-[var(--accent-9)]"
                style={{
                  position: "absolute",
                  [anchorSide]: -6,
                  top: "50%",
                  transform: "translateY(-50%)",
                }}
                aria-label={`Link anchor for ${r.field_type}: ${r.value}`}
              >
                <LinkIcon size={8} weight="bold" style={{ opacity: 0 }} />
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create SeedQueuePanel**

Create `frontend/src/components/labeling/SeedQueuePanel.tsx`:

```tsx
import { Badge, Heading, Text, TextField, Button } from "@radix-ui/themes";
import { useState } from "react";
import { MagnifyingGlass, CheckCircle, XCircle, Minus } from "@phosphor-icons/react";
import { postApi } from "../../api/client";
import type { LabelingSeed, LabelingVerdict, FieldType } from "../../types";

interface Props {
  sessionId: string;
  seeds: LabelingSeed[];
  verdicts: LabelingVerdict[];
  currentSeedId?: number;
  onRunSeed: (s: LabelingSeed) => void;
}

const FIELD_COLORS: Record<FieldType, string> = {
  party_name: "jade", trade_name: "blue", care_of: "cyan",
  company_other: "indigo", law_firm: "plum", contact_name: "orange",
  address: "amber", phone: "tomato",
};

export default function SeedQueuePanel({ sessionId, seeds, verdicts, currentSeedId, onRunSeed }: Props) {
  const [newTerm, setNewTerm] = useState("");
  const [newType, setNewType] = useState<FieldType>("party_name");

  const pending = seeds.filter((s) => s.state === "pending");
  const inProgress = seeds.filter((s) => s.state === "in_progress");
  const done = seeds.filter((s) => s.state === "done");
  const skipped = seeds.filter((s) => s.state === "skipped");

  const confirmedParties = verdicts.filter((v) => v.verdict === "confirmed");
  const rejectedParties = verdicts.filter((v) => v.verdict === "rejected");

  async function addSeed() {
    if (!newTerm.trim()) return;
    await postApi(`/labeling/sessions/${sessionId}/seeds`,
                  { term: newTerm, field_type: newType });
    setNewTerm("");
    // Parent will reload on next loop.
  }

  return (
    <div className="p-3 flex flex-col gap-4 text-[13px]">
      <div>
        <Heading size="1" mb="1">Ad-hoc search</Heading>
        <div className="flex flex-col gap-1">
          <TextField.Root size="1" placeholder="Search term"
                          value={newTerm} onChange={(e) => setNewTerm(e.target.value)}>
            <TextField.Slot><MagnifyingGlass size={12} /></TextField.Slot>
          </TextField.Root>
          <select value={newType} onChange={(e) => setNewType(e.target.value as FieldType)}
                  className="px-2 py-1 text-[12px] rounded border border-[var(--gray-6)]">
            {Object.keys(FIELD_COLORS).map((ft) => <option key={ft} value={ft}>{ft}</option>)}
          </select>
          <Button size="1" variant="soft" onClick={addSeed}>Add seed</Button>
        </div>
      </div>

      <SeedGroup label={`Pending (${pending.length})`} seeds={pending}
                 currentSeedId={currentSeedId} onRunSeed={onRunSeed} />
      {inProgress.length > 0 && (
        <SeedGroup label={`In progress (${inProgress.length})`} seeds={inProgress}
                   currentSeedId={currentSeedId} onRunSeed={onRunSeed} />
      )}
      {done.length > 0 && (
        <SeedGroup label={`Done (${done.length})`} seeds={done}
                   currentSeedId={currentSeedId} onRunSeed={onRunSeed} />
      )}
      {skipped.length > 0 && (
        <SeedGroup label={`Skipped (${skipped.length})`} seeds={skipped}
                   currentSeedId={currentSeedId} onRunSeed={onRunSeed} />
      )}

      <div>
        <Heading size="1" mb="1">Confirmed ({confirmedParties.length})</Heading>
        <div className="flex flex-col gap-1">
          {confirmedParties.map((v) => (
            <div key={v.id} className="flex items-center gap-1 text-[12px]">
              <CheckCircle size={12} weight="fill" style={{ color: "var(--jade-10)" }} />
              {v.source_id}/{v.side}
            </div>
          ))}
        </div>
      </div>

      {rejectedParties.length > 0 && (
        <div>
          <Heading size="1" mb="1">Rejected ({rejectedParties.length})</Heading>
          <div className="flex flex-col gap-1">
            {rejectedParties.map((v) => (
              <div key={v.id} className="flex items-center gap-1 text-[12px]">
                <XCircle size={12} weight="fill" style={{ color: "var(--tomato-10)" }} />
                {v.source_id}/{v.side}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function SeedGroup({ label, seeds, currentSeedId, onRunSeed }: {
  label: string; seeds: LabelingSeed[]; currentSeedId?: number;
  onRunSeed: (s: LabelingSeed) => void;
}) {
  return (
    <div>
      <Heading size="1" mb="1">{label}</Heading>
      <div className="flex flex-col gap-1">
        {seeds.map((s) => (
          <button key={s.id}
                  onClick={() => onRunSeed(s)}
                  className="text-left px-2 py-1 rounded hover:bg-[var(--accent-2)] border border-transparent"
                  style={{
                    borderColor: currentSeedId === s.id ? "var(--accent-9)" : "transparent",
                    background: currentSeedId === s.id ? "var(--accent-2)" : undefined,
                  }}>
            <Badge size="1" variant="soft" color={FIELD_COLORS[s.field_type] as any}>
              {s.field_type}
            </Badge>{" "}
            <span className="text-[12px]">{s.term}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Create CandidateListPanel**

Create `frontend/src/components/labeling/CandidateListPanel.tsx`:

```tsx
import { Badge, Heading, Text } from "@radix-ui/themes";
import { CheckCircle, XCircle } from "@phosphor-icons/react";
import type { LabelingCandidate, LabelingVerdict, LabelingPartyView } from "../../types";

interface Props {
  candidates: LabelingCandidate[];
  verdicts: LabelingVerdict[];
  currentRight: LabelingPartyView | null;
  onPick: (c: LabelingCandidate) => void;
}

function verdictFor(v: LabelingVerdict[], c: LabelingCandidate) {
  return v.find((x) => x.source_id === c.source_id && x.side === c.side);
}

export default function CandidateListPanel({ candidates, verdicts, currentRight, onPick }: Props) {
  const sorted = [...candidates].sort((a, b) => {
    const va = verdictFor(verdicts, a);
    const vb = verdictFor(verdicts, b);
    if (!!va === !!vb) return 0;
    return va ? 1 : -1;
  });

  return (
    <div className="p-3 text-[13px]">
      <Heading size="1" mb="2">Candidates ({candidates.length})</Heading>
      <div className="flex flex-col gap-1">
        {sorted.map((c) => {
          const v = verdictFor(verdicts, c);
          const isCurrent = currentRight &&
            currentRight.source_id === c.source_id && currentRight.side === c.side;
          return (
            <button key={`${c.source_id}:${c.side}`}
                    onClick={() => onPick(c)}
                    className="text-left px-2 py-1 rounded hover:bg-[var(--accent-2)]"
                    style={{
                      background: isCurrent ? "var(--accent-2)" : undefined,
                      opacity: v ? 0.6 : 1,
                    }}>
              <div className="flex items-center gap-1">
                {v?.verdict === "confirmed" && (
                  <CheckCircle size={12} weight="fill" style={{ color: "var(--jade-10)" }} />
                )}
                {v?.verdict === "rejected" && (
                  <XCircle size={12} weight="fill" style={{ color: "var(--tomato-10)" }} />
                )}
                <Text size="1">{c.source_id}</Text>
                <Badge size="1" variant="soft" color={c.side === "buyer" ? "jade" : "amber"}>
                  {c.side}
                </Badge>
              </div>
              <Text size="1" style={{ color: "var(--gray-9)" }}>
                {c.match_fields.join(", ")}
              </Text>
            </button>
          );
        })}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: errors only for missing LinkCanvas / VerdictBar (created next).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/labeling/PartyCard.tsx \
        frontend/src/components/labeling/SeedQueuePanel.tsx \
        frontend/src/components/labeling/CandidateListPanel.tsx
git commit -m "feat(labeling): party card + seed queue + candidate list"
```

---

### Task 15: LinkCanvas (SVG overlay)

**Files:**
- Create: `frontend/src/components/labeling/LinkCanvas.tsx`

Draws SVG lines between data-link-anchor dots on the two PartyCards. Redraws on window resize / scroll. Works purely off DOM queries — no parent state required for geometry.

- [ ] **Step 1: Create LinkCanvas**

Create `frontend/src/components/labeling/LinkCanvas.tsx`:

```tsx
import { useEffect, useRef, useState } from "react";
import type { LabelingLinkInput } from "../../types";

interface Props {
  links: LabelingLinkInput[];
}

interface Segment {
  x1: number; y1: number; x2: number; y2: number;
  kind: "exact" | "implied";
  key: string;
}

function findAnchor(pane: "left" | "right", field_type: string, value: string): DOMRect | null {
  const el = document.querySelector(
    `[data-link-anchor="1"][data-pane="${pane}"][data-field-type="${field_type}"][data-field-value="${cssEscape(value)}"]`
  ) as HTMLElement | null;
  return el?.getBoundingClientRect() ?? null;
}

function cssEscape(s: string): string {
  // Attribute-value selector needs quote-safe content; rely on CSS.escape
  return (typeof CSS !== "undefined" && (CSS as any).escape) ? (CSS as any).escape(s) : s.replace(/"/g, '\\"');
}

export default function LinkCanvas({ links }: Props) {
  const [segments, setSegments] = useState<Segment[]>([]);
  const rafRef = useRef<number>(0);

  useEffect(() => {
    function recompute() {
      const segs: Segment[] = [];
      for (let i = 0; i < links.length; i++) {
        const l = links[i];
        const a = findAnchor("left", l.from_field_type, l.from_field_value);
        const b = findAnchor("right", l.to_field_type, l.to_field_value);
        if (a && b) {
          segs.push({
            x1: a.left + a.width / 2, y1: a.top + a.height / 2,
            x2: b.left + b.width / 2, y2: b.top + b.height / 2,
            kind: l.kind,
            key: `${i}:${l.from_field_type}:${l.from_field_value}->${l.to_field_type}:${l.to_field_value}`,
          });
        }
      }
      setSegments(segs);
    }
    function schedule() {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = requestAnimationFrame(recompute);
    }
    recompute();
    window.addEventListener("resize", schedule);
    window.addEventListener("scroll", schedule, true);
    return () => {
      window.removeEventListener("resize", schedule);
      window.removeEventListener("scroll", schedule, true);
      cancelAnimationFrame(rafRef.current);
    };
  }, [links]);

  return (
    <svg
      style={{
        position: "fixed",
        inset: 0,
        pointerEvents: "none",
        zIndex: 50,
      }}
      width="100%"
      height="100%"
    >
      {segments.map((s) => (
        <line
          key={s.key}
          x1={s.x1} y1={s.y1} x2={s.x2} y2={s.y2}
          stroke="var(--accent-9)"
          strokeWidth={2}
          strokeDasharray={s.kind === "implied" ? "5 4" : undefined}
        />
      ))}
    </svg>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/labeling/LinkCanvas.tsx
git commit -m "feat(labeling): SVG link overlay"
```

---

### Task 16: VerdictBar + click-to-link interaction

**Files:**
- Create: `frontend/src/components/labeling/VerdictBar.tsx`

Handles click-based link creation: click an anchor on the left pane, then an anchor on the right pane → adds a link of the current kind. Also hosts rationale input, confirm/reject/skip buttons, exact/implied toggle, keyboard shortcuts (`E`/`I`/`C`/`R`/`S`), and the drawn-links list with delete.

- [ ] **Step 1: Create VerdictBar**

Create `frontend/src/components/labeling/VerdictBar.tsx`:

```tsx
import { useEffect } from "react";
import { Button, TextField, Badge } from "@radix-ui/themes";
import { CheckCircle, XCircle, SkipForward, Trash } from "@phosphor-icons/react";
import type { LabelingLinkInput, LinkKind, FieldType } from "../../types";

interface Props {
  linkKind: LinkKind;
  setLinkKind: (k: LinkKind) => void;
  rationale: string;
  setRationale: (s: string) => void;
  disabled: boolean;
  pendingLinks: LabelingLinkInput[];
  setPendingLinks: (l: LabelingLinkInput[]) => void;
  onConfirm: () => void;
  onReject: () => void;
  onSkip: () => void;
}

export default function VerdictBar({
  linkKind, setLinkKind, rationale, setRationale, disabled,
  pendingLinks, setPendingLinks, onConfirm, onReject, onSkip,
}: Props) {
  // Click-to-link: capture clicks on elements with data-link-anchor
  useEffect(() => {
    let pendingLeft: { field_type: FieldType; field_value: string } | null = null;

    function handleClick(e: MouseEvent) {
      const target = (e.target as HTMLElement).closest("[data-link-anchor]") as HTMLElement | null;
      if (!target) return;
      const pane = target.dataset.pane as "left" | "right";
      const field_type = target.dataset.fieldType as FieldType;
      const field_value = target.dataset.fieldValue || "";
      if (pane === "left") {
        pendingLeft = { field_type, field_value };
      } else if (pane === "right" && pendingLeft) {
        // Dedup identical links
        const already = pendingLinks.find(
          (l) => l.from_field_type === pendingLeft!.field_type
              && l.from_field_value === pendingLeft!.field_value
              && l.to_field_type === field_type
              && l.to_field_value === field_value,
        );
        if (!already) {
          setPendingLinks([...pendingLinks, {
            from_field_type: pendingLeft.field_type,
            from_field_value: pendingLeft.field_value,
            to_field_type: field_type,
            to_field_value: field_value,
            kind: linkKind,
          }]);
        }
        pendingLeft = null;
      }
    }

    function handleKey(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return; // don't intercept while typing
      if (e.key.toLowerCase() === "e") setLinkKind("exact");
      else if (e.key.toLowerCase() === "i") setLinkKind("implied");
      else if (!disabled && e.key.toLowerCase() === "c") onConfirm();
      else if (!disabled && e.key.toLowerCase() === "r") onReject();
      else if (!disabled && e.key.toLowerCase() === "s") onSkip();
    }

    document.addEventListener("click", handleClick, true);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("click", handleClick, true);
      document.removeEventListener("keydown", handleKey);
    };
  }, [linkKind, pendingLinks, setPendingLinks, setLinkKind, disabled, onConfirm, onReject, onSkip]);

  return (
    <div className="border-t border-[var(--gray-4)] p-3 flex flex-col gap-2"
         style={{ background: "var(--gray-2)" }}>
      <div className="flex items-center gap-3">
        <span className="text-[12px]" style={{ color: "var(--gray-9)" }}>Mode (E / I):</span>
        <Button size="1" variant={linkKind === "exact" ? "solid" : "soft"} onClick={() => setLinkKind("exact")}>
          ● Exact
        </Button>
        <Button size="1" variant={linkKind === "implied" ? "solid" : "soft"} onClick={() => setLinkKind("implied")}>
          ○ Implied
        </Button>
        <div className="flex-1" />
        <TextField.Root size="1" placeholder="Rationale (required for reject)"
                        value={rationale}
                        onChange={(e) => setRationale(e.target.value)}
                        style={{ width: 320 }} />
        <Button size="1" color="jade" disabled={disabled || pendingLinks.length === 0} onClick={onConfirm}>
          <CheckCircle size={12} /> Confirm (C)
        </Button>
        <Button size="1" color="tomato" variant="soft"
                disabled={disabled || !rationale.trim()} onClick={onReject}>
          <XCircle size={12} /> Reject (R)
        </Button>
        <Button size="1" variant="soft" disabled={disabled} onClick={onSkip}>
          <SkipForward size={12} /> Skip (S)
        </Button>
      </div>
      {pendingLinks.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {pendingLinks.map((l, i) => (
            <Badge key={i} size="1" variant="soft"
                   color={l.kind === "exact" ? "jade" : "blue"}>
              {l.from_field_type}:{l.from_field_value}
              {" → "}
              {l.to_field_type}:{l.to_field_value}
              <button className="ml-1 opacity-70 hover:opacity-100"
                      onClick={() => setPendingLinks(pendingLinks.filter((_, j) => j !== i))}>
                <Trash size={10} />
              </button>
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/labeling/VerdictBar.tsx
git commit -m "feat(labeling): verdict bar + click-to-link interaction"
```

---

## Phase 7 — Verification

### Task 17: End-to-end smoke test

**Files:** none (verification only).

- [ ] **Step 1: Restart both servers**

```bash
pkill -f "uvicorn cleo.web" || true
pkill -f "vite"            || true
uvicorn cleo.web.app:app --reload --port 8099 &
( cd frontend && npm run dev ) &
sleep 5
curl -s -o /dev/null -w "backend: %{http_code}\n" http://localhost:8099/
curl -s -o /dev/null -w "frontend: %{http_code}\n" http://localhost:5174/
```

Expected: both 200.

- [ ] **Step 2: Manual golden-path walkthrough**

In a browser, authenticated:

1. Open http://localhost:5174/labeling — 8 audit cards visible.
2. Click **05 — Huntington** (or any). Audit page loads with party rows.
3. Click **Start as anchor** on a row — session workspace opens. Top bar shows anchor info; left sidebar has seeds populated from the anchor.
4. Click any pending seed in the left sidebar — the reference pane (column 2) loads the party that contributed the seed; candidate list (column 4) populates.
5. Click any candidate row — it loads into the right pane. Field rows are visible on both cards with connector dots on inner edges.
6. Click a connector dot on the left, then a matching dot on the right — a solid green line appears between them.
7. Press `I` — mode switches to implied. Draw another link — it shows as dashed.
8. Press `C` — verdict saved, candidate disappears from unreviewed list, next candidate loads.
9. Pick an unmatched candidate, type a rationale in the bar, press `R` — rejected; list advances.
10. Top bar Export button — JSON file downloads with confirmed/rejected pairs including full field data and links.
11. Refresh the page — session state is restored (seeds, verdicts, lists).

If any step fails, diagnose and fix before the next task.

- [ ] **Step 3: Verify tsc still clean**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Verify pytest still clean**

Run: `pytest tests/test_labeling_audit_parser.py tests/test_labeling_party_view.py tests/test_labeling_seed_harvester.py tests/test_labeling_operations.py -v`
Expected: all passed.

- [ ] **Step 5: Commit (if any fixups were needed during smoke test)**

---

## Notes for the implementer

- **Do not** alter any compiler-owned tables. Everything added here is CRM-layer and lives under its own migration.
- **Raw HTML escape hatch** (spec mentioned): intentionally deferred — the current `PartyCard` shows structured fields only. If a parser gap is hit during real labeling, the follow-up is to add a collapsible "Open raw RT" link in the card header that opens the RT detail page at `/transactions/:sourceId` in a new tab. That is out of scope for this plan.
- **Audit README and `06-18-erica-numbered-spv.md`:** the audit parser just skips the README and processes all other `.md` files under the latest `YYYY-MM-DD` folder — no special-casing needed.
- **Frontend state is deliberately kept in the page component** rather than a context. The workspace is the only consumer of this state; no other page needs it.
- **Performance:** seed searches may return large candidate lists (e.g. a shared Toronto address can match hundreds of RTs). The `search_candidates` function caps at 200 hits. If that's insufficient in practice, add `LIMIT` + cursor pagination rather than removing the cap.
