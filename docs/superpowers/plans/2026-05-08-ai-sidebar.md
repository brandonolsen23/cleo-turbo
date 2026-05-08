# AI Sidebar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a slide-out drawer in Cleo Turbo that lets the user chat with Claude (Opus 4.7) about their data via three tools (`run_sql`, `describe_schema`, `get_entity_url`) over an SSE-streamed FastAPI endpoint, with page-aware context, prompt caching, and per-conversation cost guardrails.

**Architecture:** Browser drawer → FastAPI proxy → Anthropic streaming API. Tool execution runs server-side against a read-only SQLite connection (`mode=ro` URI). Tool-call results stream back to the drawer alongside text deltas via three SSE event types. No write actions, no MCP, no conversation persistence in v1.

**Tech Stack:**
- Backend: FastAPI, `anthropic` Python SDK ≥ 0.40, sqlite3 (stdlib).
- Frontend: React 19 + Radix UI Themes + Tailwind, `react-markdown` + `remark-gfm` (new dependencies).
- Streaming: SSE (`text/event-stream`) end-to-end. Anthropic's stream → backend → browser.

**Spec:** `docs/superpowers/specs/2026-05-08-ai-sidebar-design.md`

**Branch:** Continue on the current branch (`feat/crm-daily-outreach-phase-1`). At PR time, split into two PRs (CRM Phase 1 + AI Sidebar) using `git rebase --onto`. If you'd rather isolate now, create a fresh worktree off `feat/crm-daily-outreach-phase-1` *after* commit `c52a891` (the spec commit).

---

## Task 0: Sanity check the workspace

**Files:** none

- [ ] **Step 1: Confirm you're on the right commit and the backend is healthy**

```bash
git log --oneline -3
# Expected to see c52a891 docs(spec): AI sidebar design at HEAD or near top.
curl -s -m 5 -o /dev/null -w "HTTP %{http_code}\n" http://localhost:8099/api/properties
# Expected: HTTP 401 (auth required is fine — confirms backend is responding).
```

- [ ] **Step 2: Confirm the test suite is green**

Run from project root:

```bash
PYTHONPATH=. pytest tests/ --ignore=tests/test_discovery_v2_expansion.py --ignore=tests/test_consolidation_infrastructure.py 2>&1 | tail -3
```

Expected: `XXX passed in NN.NNs` (564+ as of branch state).

If any test is failing, stop and report. Do not start implementing on a broken main.

---

## Task 1: Migration 023 — failing test

**Files:**
- Create: `tests/test_migration_023_ai_usage.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for migration 023: ai_usage table."""
import importlib
import sqlite3


def _bootstrap_pre_migration_db() -> sqlite3.Connection:
    """In-memory DB with just the users table the migration depends on."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'editor'
        );
        INSERT INTO users (id, username, password_hash, display_name)
            VALUES (1, 'brandon', 'x', 'Brandon');
        """
    )
    conn.commit()
    return conn


def _run_migration(conn: sqlite3.Connection) -> None:
    mod = importlib.import_module("cleo.database.migrations.023_ai_usage")
    mod.migrate(conn)


def test_ai_usage_table_created():
    conn = _bootstrap_pre_migration_db()
    _run_migration(conn)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(ai_usage)").fetchall()}
    expected = {
        "id", "user_id", "created_at", "input_tokens", "output_tokens",
        "cached_tokens", "tool_calls", "model", "route_at_open",
        "first_user_message",
    }
    assert expected <= cols, f"Missing columns: {expected - cols}"


def test_migration_is_idempotent():
    conn = _bootstrap_pre_migration_db()
    _run_migration(conn)
    _run_migration(conn)  # second run must be a no-op
    n = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='ai_usage'").fetchone()[0]
    assert n == 1


def test_insert_and_read():
    conn = _bootstrap_pre_migration_db()
    _run_migration(conn)
    conn.execute(
        "INSERT INTO ai_usage (user_id, input_tokens, output_tokens, cached_tokens, "
        "tool_calls, model, route_at_open, first_user_message) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (1, 1234, 567, 1000, 3, "claude-opus-4-7", "/properties/PRO_42", "tell me about this owner"),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM ai_usage WHERE user_id = 1").fetchone()
    assert row["input_tokens"] == 1234
    assert row["model"] == "claude-opus-4-7"
    assert row["created_at"] is not None  # default fired
```

- [ ] **Step 2: Run test to verify it fails**

```bash
PYTHONPATH=. pytest tests/test_migration_023_ai_usage.py -v 2>&1 | tail -15
```

Expected: `ModuleNotFoundError: No module named 'cleo.database.migrations.023_ai_usage'`.

- [ ] **Step 3: Commit**

```bash
git add tests/test_migration_023_ai_usage.py
git commit -m "test(db): failing tests for migration 023 — ai_usage table"
```

---

## Task 2: Migration 023 — implement

**Files:**
- Create: `cleo/database/migrations/023_ai_usage.py`
- Modify: `cleo/database/schema.py` (add ai_usage to the canonical schema)

- [ ] **Step 1: Write the migration**

```python
"""Migration 023: ai_usage table — per-conversation token logging.

System table; never dropped, never rebuilt by the compiler.

Idempotent: rerunning is a no-op.

Run via:
    python -m cleo.database.migrations.023_ai_usage
"""

from __future__ import annotations

import sqlite3


def migrate(conn: sqlite3.Connection) -> None:
    print("Migration 023: ai_usage")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS ai_usage (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id            INTEGER REFERENCES users(id),
            created_at         TEXT DEFAULT (datetime('now')),
            input_tokens       INTEGER NOT NULL DEFAULT 0,
            output_tokens      INTEGER NOT NULL DEFAULT 0,
            cached_tokens      INTEGER NOT NULL DEFAULT 0,
            tool_calls         INTEGER NOT NULL DEFAULT 0,
            model              TEXT,
            route_at_open      TEXT,
            first_user_message TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_ai_usage_user ON ai_usage(user_id);
        CREATE INDEX IF NOT EXISTS idx_ai_usage_created_at ON ai_usage(created_at);
        """
    )
    conn.commit()
    print("Migration 023: done.")


if __name__ == "__main__":
    from cleo.database.connection import get_connection
    conn = get_connection()
    migrate(conn)
    conn.close()
```

- [ ] **Step 2: Add `ai_usage` to the canonical schema in `cleo/database/schema.py`**

Find the `# SYSTEM TABLES` block (around line 625) and insert *after* the existing `id_mappings` table definition:

```sql
CREATE TABLE IF NOT EXISTS ai_usage (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id            INTEGER REFERENCES users(id),
    created_at         TEXT DEFAULT (datetime('now')),
    input_tokens       INTEGER NOT NULL DEFAULT 0,
    output_tokens      INTEGER NOT NULL DEFAULT 0,
    cached_tokens      INTEGER NOT NULL DEFAULT 0,
    tool_calls         INTEGER NOT NULL DEFAULT 0,
    model              TEXT,
    route_at_open      TEXT,
    first_user_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_ai_usage_user ON ai_usage(user_id);
CREATE INDEX IF NOT EXISTS idx_ai_usage_created_at ON ai_usage(created_at);
```

Also update CLAUDE.md's "System tables" line to add `ai_usage`. Find the line that lists `users, audit_log, app_meta, data_issues, asset_classes, tenant_categories` and append `, ai_usage`.

- [ ] **Step 3: Run the failing tests**

```bash
PYTHONPATH=. pytest tests/test_migration_023_ai_usage.py -v 2>&1 | tail -10
```

Expected: 3 passed.

- [ ] **Step 4: Run the migration against the live DB**

```bash
PYTHONPATH=. python3 -m cleo.database.migrations.023_ai_usage
```

Expected output:
```
Migration 023: ai_usage
Migration 023: done.
```

- [ ] **Step 5: Verify the live DB**

```bash
sqlite3 data/cleo.db ".schema ai_usage"
```

Expected: the CREATE TABLE statement you just ran, plus both indexes.

- [ ] **Step 6: Commit**

```bash
git add cleo/database/migrations/023_ai_usage.py cleo/database/schema.py CLAUDE.md
git commit -m "feat(db): migration 023 — ai_usage table for per-turn token logging"
```

---

## Task 3: ai_tools.run_sql — failing test

**Files:**
- Create: `tests/test_ai_tools.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for ai_tools — the read-only SQL + schema introspection layer
that backs the AI sidebar."""

import sqlite3
import pytest

from cleo.web.routes.ai_tools import (
    run_sql, describe_schema, get_entity_url,
    InvalidQueryError,
)


@pytest.fixture
def ro_conn(tmp_path):
    """Build a tiny on-disk DB and return a read-only connection to it,
    mirroring how the AI route opens the cleo.db at runtime."""
    db_file = tmp_path / "ai_tools_test.db"
    rw = sqlite3.connect(str(db_file))
    rw.executescript(
        """
        CREATE TABLE properties (
            id TEXT PRIMARY KEY, display_address TEXT, city TEXT
        );
        CREATE TABLE contacts (
            id TEXT PRIMARY KEY, display_name TEXT
        );
        INSERT INTO properties (id, display_address, city) VALUES
            ('PRO_1', '1 King St', 'Toronto'),
            ('PRO_2', '2 Queen St', 'Toronto'),
            ('PRO_3', '3 Bay St', 'Hamilton');
        INSERT INTO contacts (id, display_name) VALUES
            ('CON_1', 'Peter Vicano'),
            ('CON_2', 'Jane Doe');
        """
    )
    rw.commit()
    rw.close()
    ro = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
    ro.row_factory = sqlite3.Row
    yield ro
    ro.close()


# ── run_sql happy path ─────────────────────────────────────────────


def test_run_sql_returns_rows(ro_conn):
    out = run_sql(ro_conn, "SELECT id, city FROM properties ORDER BY id")
    assert out["row_count"] == 3
    assert out["truncated"] is False
    assert out["columns"] == ["id", "city"]
    assert out["rows"][0] == {"id": "PRO_1", "city": "Toronto"}


def test_run_sql_caps_at_200_rows():
    """If the underlying query returns >200 rows, mark truncated."""
    rw = sqlite3.connect(":memory:")
    rw.execute("CREATE TABLE big (n INTEGER)")
    rw.executemany("INSERT INTO big VALUES (?)", [(i,) for i in range(500)])
    rw.commit()
    out = run_sql(rw, "SELECT n FROM big ORDER BY n")
    assert out["row_count"] == 200
    assert out["truncated"] is True


def test_run_sql_with_cte(ro_conn):
    out = run_sql(
        ro_conn,
        "WITH t AS (SELECT city, COUNT(*) AS n FROM properties GROUP BY city) SELECT * FROM t ORDER BY city",
    )
    assert out["row_count"] == 2
    assert {r["city"] for r in out["rows"]} == {"Toronto", "Hamilton"}


def test_run_sql_explain_allowed(ro_conn):
    out = run_sql(ro_conn, "EXPLAIN SELECT * FROM properties")
    assert out["row_count"] > 0


# ── run_sql guard rejections ───────────────────────────────────────


@pytest.mark.parametrize(
    "bad",
    [
        "INSERT INTO properties (id) VALUES ('X')",
        "UPDATE properties SET city = 'X'",
        "DELETE FROM properties",
        "DROP TABLE properties",
        "CREATE TABLE foo (id TEXT)",
        "ALTER TABLE properties ADD COLUMN foo TEXT",
        "PRAGMA writable_schema = 1",
        "ATTACH DATABASE 'other.db' AS other",
        "SELECT 1; DROP TABLE properties",
        "  SELECT * FROM properties; DELETE FROM contacts",
        "-- harmless\nDROP TABLE properties",
    ],
)
def test_run_sql_rejects_non_select(ro_conn, bad):
    with pytest.raises(InvalidQueryError):
        run_sql(ro_conn, bad)


def test_run_sql_readonly_connection_blocks_writes(ro_conn):
    """Even if the guard were buggy, the URI mode=ro connection refuses writes."""
    # Bypass the guard intentionally by calling the underlying execute.
    with pytest.raises(sqlite3.OperationalError):
        ro_conn.execute("INSERT INTO properties (id) VALUES ('X')")


# ── describe_schema ────────────────────────────────────────────────


def test_describe_schema_lists_all_tables(ro_conn):
    out = describe_schema(ro_conn)
    names = {t["table"] for t in out["tables"]}
    assert {"properties", "contacts"} <= names
    p = next(t for t in out["tables"] if t["table"] == "properties")
    assert p["row_count"] == 3
    assert p["description"]  # non-empty fallback description


def test_describe_schema_for_specific_table(ro_conn):
    out = describe_schema(ro_conn, table="properties")
    cols = {c["name"] for c in out["columns"]}
    assert cols == {"id", "display_address", "city"}
    assert len(out["sample_rows"]) == 3  # we only have 3
    assert out["sample_rows"][0]["id"].startswith("PRO_")


def test_describe_schema_unknown_table_raises(ro_conn):
    with pytest.raises(InvalidQueryError):
        describe_schema(ro_conn, table="not_a_real_table")


# ── get_entity_url ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "etype,eid,expected",
    [
        ("property", "PRO_84463", "/properties/PRO_84463"),
        ("contact",  "CON_14995", "/contacts/CON_14995"),
        ("group",    "GRP_22771", "/groups/GRP_22771"),
        ("deal",     "DEAL_42",   "/deals/DEAL_42"),
        ("list",     "LIST_3",    "/lists/LIST_3"),
        ("transaction", "RT126011", "/transactions/RT126011"),
    ],
)
def test_get_entity_url_known_types(etype, eid, expected):
    assert get_entity_url(etype, eid) == expected


def test_get_entity_url_unknown_type_raises():
    with pytest.raises(InvalidQueryError):
        get_entity_url("nonsense", "XYZ_1")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
PYTHONPATH=. pytest tests/test_ai_tools.py -v 2>&1 | tail -15
```

Expected: `ImportError: cannot import name 'run_sql' from 'cleo.web.routes.ai_tools'` (the file doesn't exist yet).

- [ ] **Step 3: Commit**

```bash
git add tests/test_ai_tools.py
git commit -m "test(ai): failing tests for run_sql / describe_schema / get_entity_url"
```

---

## Task 4: ai_tools — implement

**Files:**
- Create: `cleo/web/routes/ai_tools.py`

- [ ] **Step 1: Write the implementation**

```python
"""AI sidebar tool implementations.

Three tools that the LLM can call via the /api/ai/chat endpoint:
- run_sql            — execute a read-only SELECT/WITH/EXPLAIN
- describe_schema    — list tables or inspect one table's columns + samples
- get_entity_url     — pure URL builder for in-app entity links

Run-time safety for run_sql:
1. The AI route opens the SQLite connection in ?mode=ro URI mode, so
   even an LLM-crafted malicious query string can't write.
2. This module additionally screens incoming queries for non-SELECT
   verbs and multi-statement payloads — belt-and-suspenders.
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any

# How many rows to return per run_sql call. Anything over this is
# truncated so the LLM knows to add LIMIT / aggregate.
ROW_CAP = 200

# Hard wall-clock cap per query. The actual interrupt is wired up via
# sqlite3.Connection.set_progress_handler in the AI route at the
# connection level; this constant is documented here for the route
# to import.
QUERY_TIMEOUT_SECONDS = 5

# Hand-curated one-line descriptions per table. Drives the
# describe_schema no-arg form so Claude can pick the right table
# before guessing column names. Mirrors the categorization in
# CLAUDE.md (derived / CRM / system).
TABLE_DESCRIPTIONS: dict[str, str] = {
    # Derived
    "properties":         "One row per parcel (ARN). Display address, city, region, current owner, asset class.",
    "transactions":       "RT (Realtrack) transactions. Sale price, date, parties (registered names in seller_parties / buyer_parties JSON).",
    "transaction_parties":"Per-side party rows for each transaction; links to contacts/groups; contact_title carries 'attn'/'pres'/etc.",
    "transaction_mailing_addresses":"Mailing address listed per transaction side (where to send legal docs).",
    "transaction_brokers":"Broker firms attached to a transaction.",
    "transaction_broker_agents":"Individual broker agents listed under a brokerage.",
    "contacts":           "Stable CON_NNNNN identities. display_name + first_name + last_name (honorifics stripped). status pool/engaged.",
    "groups":             "Stable GRP_NNNNN entities — companies / SPVs / brands. property_count, status pool/engaged.",
    "group_names":        "All raw party_name spellings that map to a single GRP_ ID.",
    "pois":               "Branded POIs from OSM (tenants on a parcel). brand, category, address, address_source.",
    "gw_assessments":     "GeoWarehouse assessment records. owner_name, owner_mailing, assessed_value.",
    "gw_sales_history":   "GeoWarehouse historical sales attached to a property.",
    "group_analytics":    "Pre-computed per-group portfolio metrics (total value, transaction velocity, regions, etc.).",
    "address_root_summary":"Pre-computed counts per (street_number + street_name) — drives the Explorer Addresses tab.",
    "address_base_summary":"Same as above, but with street_suffix included.",
    # CRM (persistent)
    "deals":              "User-created deals. stage, amount, deal_owner, property_id/group_id link.",
    "lists":              "User-created lists. scope = personal | shared.",
    "list_members":       "Membership rows: (list_id, member_type, member_id).",
    "group_contacts":     "Manual contact↔group links (alongside the auto current_group_id).",
    "contact_notes":      "Free-form notes on a contact.",
    "group_notes":        "Free-form notes on a group.",
    "sell_opportunities": "Sell-side opportunities tracked by the user.",
    "buy_mandates":       "Buy-side mandates tracked by the user.",
    "activities":         "User-logged activities (call/email/meeting/note). Auto-FKs into contact_id/property_id/group_id.",
    "user_stars":         "Per-user star/queue. (user_id, entity_type, entity_id).",
    "ai_usage":           "Per-turn token usage from the AI sidebar.",
    "contact_field_overrides":"Per-contact field overrides (e.g. corrected display_name, phone).",
    "group_field_overrides":"Per-group field overrides (status, hq_address, website, hubspot_id).",
    "contact_work_history":"LinkedIn-style work history per contact.",
    # System
    "users":              "Application users.",
    "audit_log":          "Append-only log of CRM mutations.",
    "id_mappings":        "Stable (anchor → CON_/PRO_/GRP_) lookup. Persists across compiler rebuilds.",
    "app_meta":           "Key-value store for compiler counters etc.",
}

# Entity types that the AI can produce in-app links for. Maps each
# type to its route prefix.
ENTITY_URL_PREFIXES: dict[str, str] = {
    "property":    "/properties/",
    "contact":     "/contacts/",
    "group":       "/groups/",
    "deal":        "/deals/",
    "list":        "/lists/",
    "transaction": "/transactions/",
}


class InvalidQueryError(Exception):
    """Raised when a tool call from the LLM is malformed or rejected."""


# ── run_sql ──────────────────────────────────────────────────────────


_ALLOWED_PREFIX = re.compile(r"^\s*(SELECT|WITH|EXPLAIN)\b", re.IGNORECASE)
_BANNED_TOKENS = re.compile(r"\b(PRAGMA|ATTACH|writable_schema)\b", re.IGNORECASE)
_COMMENT = re.compile(r"--[^\n]*|/\*.*?\*/", re.DOTALL)


def _strip_comments(query: str) -> str:
    return _COMMENT.sub("", query)


def _has_multiple_statements(query: str) -> bool:
    """Returns True if there's a `;` followed by anything non-blank.

    A trailing `;` is OK; a `;` mid-string is also OK (we only inspect
    the post-comment-stripped query, but string literals containing `;`
    are rare in select-only queries — a false positive here just rejects
    a query, never permits a write).
    """
    stripped = _strip_comments(query)
    parts = [p for p in stripped.split(";") if p.strip()]
    return len(parts) > 1


def _validate_query(query: str) -> None:
    cleaned = _strip_comments(query)
    if not _ALLOWED_PREFIX.match(cleaned):
        raise InvalidQueryError(
            "Only SELECT, WITH, and EXPLAIN queries are allowed."
        )
    if _BANNED_TOKENS.search(cleaned):
        raise InvalidQueryError(
            "PRAGMA, ATTACH, and writable_schema references are not allowed."
        )
    if _has_multiple_statements(query):
        raise InvalidQueryError("Multiple statements are not allowed.")


def run_sql(conn: sqlite3.Connection, query: str) -> dict[str, Any]:
    """Execute a read-only SQL query and return shaped results."""
    _validate_query(query)
    cur = conn.execute(query)
    columns = [d[0] for d in (cur.description or [])]
    rows: list[dict[str, Any]] = []
    truncated = False
    for i, r in enumerate(cur):
        if i >= ROW_CAP:
            truncated = True
            break
        rows.append({c: r[c] if isinstance(r, sqlite3.Row) else r[idx]
                     for idx, c in enumerate(columns)})
    return {
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "truncated": truncated,
    }


# ── describe_schema ──────────────────────────────────────────────────


def _list_tables(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        name = r[0] if not isinstance(r, sqlite3.Row) else r["name"]
        try:
            count = conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        except sqlite3.Error:
            count = None
        out.append({
            "table": name,
            "row_count": count,
            "description": TABLE_DESCRIPTIONS.get(name, ""),
        })
    return out


def _describe_one_table(conn: sqlite3.Connection, table: str) -> dict[str, Any]:
    info = conn.execute(f"PRAGMA table_info({table})").fetchall()
    if not info:
        raise InvalidQueryError(f"Table '{table}' does not exist.")
    columns = [
        {
            "name": r[1] if not isinstance(r, sqlite3.Row) else r["name"],
            "type": r[2] if not isinstance(r, sqlite3.Row) else r["type"],
            "nullable": (r[3] if not isinstance(r, sqlite3.Row) else r["notnull"]) == 0,
            "default": r[4] if not isinstance(r, sqlite3.Row) else r["dflt_value"],
        }
        for r in info
    ]
    sample = conn.execute(f"SELECT * FROM {table} LIMIT 5").fetchall()
    sample_rows = [
        {c["name"]: row[c["name"]] if isinstance(row, sqlite3.Row) else row[i]
         for i, c in enumerate(columns)}
        for row in sample
    ]
    return {
        "table": table,
        "description": TABLE_DESCRIPTIONS.get(table, ""),
        "columns": columns,
        "sample_rows": sample_rows,
    }


def describe_schema(conn: sqlite3.Connection, table: str | None = None) -> dict[str, Any]:
    if table is None:
        return {"tables": _list_tables(conn)}
    # Reject non-identifier inputs to avoid SQL injection in PRAGMA / SELECT
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table):
        raise InvalidQueryError(f"Invalid table name: {table!r}")
    return _describe_one_table(conn, table)


# ── get_entity_url ───────────────────────────────────────────────────


def get_entity_url(entity_type: str, entity_id: str) -> str:
    prefix = ENTITY_URL_PREFIXES.get(entity_type)
    if prefix is None:
        raise InvalidQueryError(
            f"Unknown entity_type {entity_type!r}. Allowed: "
            f"{sorted(ENTITY_URL_PREFIXES)}"
        )
    if not entity_id:
        raise InvalidQueryError("entity_id is required.")
    return f"{prefix}{entity_id}"
```

- [ ] **Step 2: Run the tests**

```bash
PYTHONPATH=. pytest tests/test_ai_tools.py -v 2>&1 | tail -15
```

Expected: all tests pass (about 20 cases including parametrized rejects and entity types).

- [ ] **Step 3: Commit**

```bash
git add cleo/web/routes/ai_tools.py
git commit -m "feat(ai): run_sql / describe_schema / get_entity_url tool implementations"
```

---

## Task 5: Page-context loader — failing test

**Files:**
- Modify: `tests/test_ai_tools.py` (add tests for the loader)

- [ ] **Step 1: Append the failing tests to `tests/test_ai_tools.py`**

```python
# ── page_context loader ─────────────────────────────────────────────


from cleo.web.routes.ai_tools import load_page_context  # noqa: E402


@pytest.fixture
def page_ctx_conn(tmp_path):
    db_file = tmp_path / "page_ctx.db"
    rw = sqlite3.connect(str(db_file))
    rw.executescript(
        """
        CREATE TABLE properties (
            id TEXT PRIMARY KEY, display_address TEXT, city TEXT,
            current_owner_name TEXT
        );
        CREATE TABLE contacts (id TEXT PRIMARY KEY, display_name TEXT, company_name TEXT);
        CREATE TABLE groups (id TEXT PRIMARY KEY, display_name TEXT, property_count INTEGER);
        CREATE TABLE deals (id TEXT PRIMARY KEY, name TEXT, stage TEXT);
        CREATE TABLE lists (id TEXT PRIMARY KEY, name TEXT, scope TEXT);
        CREATE TABLE transactions (
            source_id TEXT PRIMARY KEY, sale_date TEXT,
            display_address TEXT, sale_price INTEGER
        );
        INSERT INTO properties VALUES
            ('PRO_84463', '325 Guelph Street', 'Georgetown', 'Crialmar Properties Limited');
        INSERT INTO contacts VALUES ('CON_42', 'Peter Vicano', 'DH Management');
        INSERT INTO groups VALUES ('GRP_22771', 'CRIALMAR PROPERTIES LIMITED', 1);
        INSERT INTO deals VALUES ('DEAL_1', 'Crialmar deal', 'priority_deal');
        INSERT INTO lists VALUES ('LIST_1', 'Q3 prospects', 'personal');
        INSERT INTO transactions VALUES
            ('RT126011', '2017-06-12', '900, 920 Watters Road', 9322500);
        """
    )
    rw.commit()
    rw.close()
    ro = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
    ro.row_factory = sqlite3.Row
    yield ro
    ro.close()


def test_page_context_property(page_ctx_conn):
    out = load_page_context(page_ctx_conn, {"entity_type": "property", "id": "PRO_84463"})
    assert "PRO_84463" in out
    assert "325 Guelph Street" in out
    assert "Crialmar" in out


def test_page_context_contact(page_ctx_conn):
    out = load_page_context(page_ctx_conn, {"entity_type": "contact", "id": "CON_42"})
    assert "CON_42" in out and "Peter Vicano" in out


def test_page_context_group(page_ctx_conn):
    out = load_page_context(page_ctx_conn, {"entity_type": "group", "id": "GRP_22771"})
    assert "GRP_22771" in out and "CRIALMAR" in out.upper()


def test_page_context_unknown_entity_returns_empty(page_ctx_conn):
    out = load_page_context(page_ctx_conn, {"entity_type": "property", "id": "PRO_DOESNT_EXIST"})
    assert out == ""


def test_page_context_no_input_returns_empty(page_ctx_conn):
    assert load_page_context(page_ctx_conn, None) == ""
    assert load_page_context(page_ctx_conn, {}) == ""
```

- [ ] **Step 2: Run, see failures**

```bash
PYTHONPATH=. pytest tests/test_ai_tools.py -k page_context -v 2>&1 | tail -10
```

Expected: ImportError on `load_page_context`.

- [ ] **Step 3: Commit**

```bash
git add tests/test_ai_tools.py
git commit -m "test(ai): failing tests for load_page_context"
```

---

## Task 6: Page-context loader — implement

**Files:**
- Modify: `cleo/web/routes/ai_tools.py`

- [ ] **Step 1: Append the loader to `cleo/web/routes/ai_tools.py`**

```python
# ── page_context loader ─────────────────────────────────────────────


def load_page_context(
    conn: sqlite3.Connection,
    page_context: dict[str, str] | None,
) -> str:
    """Build the natural-language `{{page_context_block}}` string that
    gets injected into the system prompt.

    Returns "" when the user didn't supply page context, when the
    entity_type is unknown, or when the requested id doesn't resolve.
    """
    if not page_context:
        return ""
    etype = page_context.get("entity_type")
    eid = page_context.get("id")
    if not etype or not eid:
        return ""

    if etype == "property":
        row = conn.execute(
            "SELECT id, display_address, city, current_owner_name "
            "FROM properties WHERE id = ?",
            (eid,),
        ).fetchone()
        if not row:
            return ""
        owner = row["current_owner_name"] or "(no owner on file)"
        addr = row["display_address"] or "(no address on file)"
        city = row["city"] or ""
        return (
            f"User is currently looking at property {row['id']} ({addr}"
            + (f", {city}" if city else "")
            + f"). Owner: {owner}."
        )

    if etype == "contact":
        row = conn.execute(
            "SELECT id, display_name, company_name FROM contacts WHERE id = ?",
            (eid,),
        ).fetchone()
        if not row:
            return ""
        company = row["company_name"]
        company_clause = f" Currently at {company}." if company else ""
        return (
            f"User is currently looking at contact {row['id']} ({row['display_name']})."
            + company_clause
        )

    if etype == "group":
        row = conn.execute(
            "SELECT id, display_name, property_count FROM groups WHERE id = ?",
            (eid,),
        ).fetchone()
        if not row:
            return ""
        n = row["property_count"] or 0
        return (
            f"User is currently looking at group {row['id']} ({row['display_name']}). "
            f"property_count={n}."
        )

    if etype == "deal":
        row = conn.execute(
            "SELECT id, name, stage FROM deals WHERE id = ?",
            (eid,),
        ).fetchone()
        if not row:
            return ""
        return f"User is currently looking at deal {row['id']} ({row['name']}, stage={row['stage']})."

    if etype == "list":
        row = conn.execute(
            "SELECT id, name, scope FROM lists WHERE id = ?",
            (eid,),
        ).fetchone()
        if not row:
            return ""
        return f"User is currently looking at list {row['id']} ({row['name']}, scope={row['scope']})."

    if etype == "transaction":
        row = conn.execute(
            "SELECT source_id, sale_date, display_address, sale_price "
            "FROM transactions WHERE source_id = ?",
            (eid,),
        ).fetchone()
        if not row:
            return ""
        return (
            f"User is currently looking at transaction {row['source_id']} "
            f"(sale_date={row['sale_date']}, address={row['display_address']}, "
            f"price={row['sale_price']})."
        )

    return ""
```

- [ ] **Step 2: Run the tests**

```bash
PYTHONPATH=. pytest tests/test_ai_tools.py -v 2>&1 | tail -10
```

Expected: all green.

- [ ] **Step 3: Commit**

```bash
git add cleo/web/routes/ai_tools.py
git commit -m "feat(ai): page-context loader for property/contact/group/deal/list/transaction"
```

---

## Task 7: Install the Anthropic Python SDK

**Files:**
- Modify: requirements file or environment.

- [ ] **Step 1: Install**

```bash
pip install 'anthropic>=0.40,<1.0'
```

- [ ] **Step 2: Verify import**

```bash
python3 -c "import anthropic; print(anthropic.__version__)"
```

Expected: prints a version ≥ 0.40.

- [ ] **Step 3: Pin in requirements (only if a `requirements.txt` exists in the repo)**

If `requirements.txt` exists at the project root, append `anthropic>=0.40,<1.0`. If the project has no requirements file (the stack relies on developer-installed packages), skip — note the dependency in the next commit message.

- [ ] **Step 4: Commit (no code change unless requirements.txt was updated)**

If you updated requirements.txt:

```bash
git add requirements.txt
git commit -m "chore(deps): add anthropic SDK for AI sidebar"
```

If not, no commit yet — the dependency will be implicit from the import in Task 8.

---

## Task 8: AI chat endpoint — failing test (mocked Anthropic)

**Files:**
- Create: `tests/test_routes_ai.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for /api/ai/chat — the AI sidebar SSE endpoint."""

import json
import sqlite3
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


def _seed(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE,
            password_hash TEXT, display_name TEXT, role TEXT DEFAULT 'editor'
        );
        CREATE TABLE properties (
            id TEXT PRIMARY KEY, display_address TEXT, city TEXT,
            current_owner_name TEXT
        );
        CREATE TABLE contacts (id TEXT PRIMARY KEY, display_name TEXT, company_name TEXT);
        CREATE TABLE groups (id TEXT PRIMARY KEY, display_name TEXT, property_count INTEGER);
        CREATE TABLE deals (id TEXT PRIMARY KEY, name TEXT, stage TEXT);
        CREATE TABLE lists (id TEXT PRIMARY KEY, name TEXT, scope TEXT);
        CREATE TABLE transactions (
            source_id TEXT PRIMARY KEY, sale_date TEXT,
            display_address TEXT, sale_price INTEGER
        );
        CREATE TABLE ai_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, created_at TEXT DEFAULT (datetime('now')),
            input_tokens INTEGER, output_tokens INTEGER, cached_tokens INTEGER,
            tool_calls INTEGER, model TEXT, route_at_open TEXT,
            first_user_message TEXT
        );
        INSERT INTO users (id, username, password_hash, display_name)
            VALUES (1, 'brandon', 'x', 'Brandon');
        INSERT INTO properties VALUES
            ('PRO_84463', '325 Guelph Street', 'Georgetown', 'Crialmar Properties Limited');
        """
    )
    conn.commit()


@pytest.fixture
def client_with_mock(tmp_path):
    """Wire FastAPI with a real on-disk SQLite (so file:?mode=ro works)
    and a stub Anthropic client whose stream we control."""
    db_file = tmp_path / "ai.db"
    rw = sqlite3.connect(str(db_file), check_same_thread=False)
    rw.row_factory = sqlite3.Row
    _seed(rw)

    from cleo.web.app import create_app
    from cleo.web import deps
    app = create_app()

    def _get_db_override():
        yield rw
    app.dependency_overrides[deps.get_db] = _get_db_override
    app.dependency_overrides[deps.get_current_user] = lambda: {
        "sub": 1, "username": "brandon", "display_name": "Brandon", "role": "editor"
    }

    # Patch the route's anthropic client factory to a fake.
    import cleo.web.routes.ai as ai_route
    fake = _FakeAnthropicClient()
    monkey = patch.object(ai_route, "_make_anthropic_client", lambda: fake)
    monkey.start()

    # Tell the route which DB file to open in ?mode=ro.
    monkey2 = patch.object(ai_route, "_RO_DB_PATH", str(db_file))
    monkey2.start()

    yield TestClient(app), rw, fake

    monkey.stop()
    monkey2.stop()
    app.dependency_overrides.clear()
    rw.close()


# ── Fake Anthropic streaming client ────────────────────────────────
#
# Mirrors the slice of the SDK that the route actually consumes:
#   client.messages.stream(...) → context manager
#     iterating yields events with .type ("text" for text deltas)
#     stream.get_final_message() returns Message with
#         .content (list of TextBlock | ToolUseBlock)
#         .stop_reason
#         .usage (Usage with input_tokens / output_tokens / cache_read_input_tokens)
# The fakes use SimpleNamespace so .attr access matches the SDK shape.


from types import SimpleNamespace


def _text_event(text: str):
    """A raw content_block_delta event with a text_delta payload."""
    return SimpleNamespace(
        type="content_block_delta",
        index=0,
        delta=SimpleNamespace(type="text_delta", text=text),
    )


def _text_block(text: str):
    return SimpleNamespace(type="text", text=text)


def _tool_use_block(name: str, input_payload: dict, id_: str = "tool_1"):
    return SimpleNamespace(type="tool_use", id=id_, name=name, input=input_payload)


def _make_final(content: list, stop_reason: str = "end_turn",
                input_tokens: int = 100, output_tokens: int = 50,
                cache_read_input_tokens: int = 80):
    usage = SimpleNamespace(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_input_tokens=cache_read_input_tokens,
    )
    return SimpleNamespace(content=content, stop_reason=stop_reason, usage=usage)


class _FakeStream:
    """Yields the pre-baked text events; get_final_message() returns the
    pre-baked Message. Acts as its own context manager (the SDK does the
    same)."""

    def __init__(self, events: list, final):
        self._events = events
        self._final = final

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __iter__(self):
        return iter(self._events)

    def get_final_message(self):
        return self._final


class _FakeAnthropicClient:
    """The route calls `_make_anthropic_client()` then
    `client.messages.stream(...)`. We queue scripted (events, final)
    pairs so each stream() call peels off one turn."""

    def __init__(self):
        # Each entry: (events_list, final_message)
        self.scripts: list[tuple[list, object]] = []
        self.calls: list[dict] = []
        self.messages = self  # `client.messages.stream(...)` shape

    def stream(self, **kwargs):
        self.calls.append(kwargs)
        if not self.scripts:
            raise AssertionError("No script queued for this stream() call.")
        events, final = self.scripts.pop(0)
        return _FakeStream(events, final)


# ── Tests ──────────────────────────────────────────────────────────


def test_chat_simple_text_response(client_with_mock):
    client, conn, fake = client_with_mock
    fake.scripts.append((
        [_text_event("Hello "), _text_event("Brandon.")],
        _make_final(content=[_text_block("Hello Brandon.")]),
    ))

    resp = client.post(
        "/api/ai/chat",
        json={
            "messages": [{"role": "user", "content": "Hi"}],
            "page_context": None,
            "route_at_open": "/",
        },
    )
    assert resp.status_code == 200
    body = resp.text
    assert "Hello " in body and "Brandon." in body
    rows = conn.execute("SELECT * FROM ai_usage").fetchall()
    assert len(rows) == 1
    assert rows[0]["model"] == "claude-opus-4-7"
    assert rows[0]["first_user_message"].startswith("Hi")


def test_chat_runs_sql_tool(client_with_mock):
    client, conn, fake = client_with_mock
    # Turn 1: Claude requests run_sql (no streamed text).
    fake.scripts.append((
        [],
        _make_final(
            content=[_tool_use_block("run_sql", {"query": "SELECT id FROM properties"}, id_="t1")],
            stop_reason="tool_use",
        ),
    ))
    # Turn 2: Claude consumes the tool result and answers.
    fake.scripts.append((
        [_text_event("Found 1 property: PRO_84463")],
        _make_final(content=[_text_block("Found 1 property: PRO_84463")]),
    ))

    resp = client.post(
        "/api/ai/chat",
        json={
            "messages": [{"role": "user", "content": "List the properties."}],
            "page_context": None,
            "route_at_open": "/properties",
        },
    )
    assert resp.status_code == 200
    body = resp.text
    assert "PRO_84463" in body
    rows = conn.execute("SELECT tool_calls FROM ai_usage").fetchall()
    assert rows[0]["tool_calls"] == 1


def test_chat_rejects_writes_via_run_sql(client_with_mock):
    client, conn, fake = client_with_mock
    fake.scripts.append((
        [],
        _make_final(
            content=[_tool_use_block("run_sql", {"query": "DROP TABLE properties"}, id_="t1")],
            stop_reason="tool_use",
        ),
    ))
    fake.scripts.append((
        [_text_event("Sorry — only SELECT statements are allowed.")],
        _make_final(content=[_text_block("Sorry — only SELECT statements are allowed.")]),
    ))

    resp = client.post(
        "/api/ai/chat",
        json={
            "messages": [{"role": "user", "content": "Drop properties."}],
            "page_context": None,
            "route_at_open": "/",
        },
    )
    assert resp.status_code == 200
    assert "tool_use_end" in resp.text
    # The route forwards the InvalidQueryError text in the tool_use_end SSE.
    assert "Only SELECT" in resp.text or "SELECT" in resp.text


def test_chat_caps_tool_call_loop(client_with_mock):
    """Stop after MAX_TOOL_CALLS even if Claude keeps requesting tool_use."""
    client, conn, fake = client_with_mock
    # Queue 20 turns of run_sql, then one final answer (unreachable).
    for i in range(20):
        fake.scripts.append((
            [],
            _make_final(
                content=[_tool_use_block("run_sql", {"query": f"SELECT {i}"}, id_=f"t{i}")],
                stop_reason="tool_use",
            ),
        ))
    fake.scripts.append((
        [_text_event("done")],
        _make_final(content=[_text_block("done")]),
    ))

    resp = client.post(
        "/api/ai/chat",
        json={
            "messages": [{"role": "user", "content": "loop"}],
            "page_context": None,
            "route_at_open": "/",
        },
    )
    assert resp.status_code == 200
    rows = conn.execute("SELECT tool_calls FROM ai_usage").fetchall()
    assert rows[0]["tool_calls"] == 15


def test_chat_includes_page_context(client_with_mock):
    client, conn, fake = client_with_mock
    fake.scripts.append((
        [_text_event("ok")],
        _make_final(content=[_text_block("ok")]),
    ))
    client.post(
        "/api/ai/chat",
        json={
            "messages": [{"role": "user", "content": "this owner"}],
            "page_context": {"entity_type": "property", "id": "PRO_84463"},
            "route_at_open": "/properties/PRO_84463",
        },
    )
    sent = fake.calls[0]
    sysprompt = sent["system"] if isinstance(sent["system"], str) else "".join(
        b.get("text", "") for b in sent["system"]
    )
    assert "PRO_84463" in sysprompt
    assert "Crialmar" in sysprompt
```

- [ ] **Step 2: Run, see failures**

```bash
PYTHONPATH=. pytest tests/test_routes_ai.py -v 2>&1 | tail -15
```

Expected: ImportError or "module ai not found".

- [ ] **Step 3: Commit**

```bash
git add tests/test_routes_ai.py
git commit -m "test(ai): failing tests for /api/ai/chat — streaming + tool loop + page context"
```

---

## Task 9: AI chat endpoint — implement

**Files:**
- Create: `cleo/web/routes/ai.py`

- [ ] **Step 1: Implement the route**

```python
"""AI sidebar — /api/ai/chat SSE endpoint.

Streams Anthropic Messages → SSE events to the browser, executing
read-only SQL / schema / URL tools server-side between turns.

Three SSE event types per turn (matches the spec):
- text_delta      : append tokens to the active assistant bubble
- tool_use_start  : render the collapsed "Ran SQL · …" block
- tool_use_end    : populate it with row count / elapsed_ms / error
- done            : turn complete (sent at the very end)
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Any, Iterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..deps import get_db, get_current_user
from .ai_tools import (
    InvalidQueryError, ROW_CAP, QUERY_TIMEOUT_SECONDS,
    describe_schema, get_entity_url, load_page_context, run_sql,
)


# ── Configuration ────────────────────────────────────────────────────


DEFAULT_MODEL = os.environ.get("AI_MODEL", "claude-opus-4-7")
MAX_OUTPUT_TOKENS = 8192
MAX_TOOL_CALLS = 15
MAX_OUTPUT_TOKENS_PER_CONVERSATION = 80_000
# Path to the live DB to open in read-only URI mode for run_sql.
# Tests monkeypatch this to a tempfile.
_RO_DB_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "cleo.db")
)


# ── Tool definitions sent to Anthropic ────────────────────────────────


TOOL_DEFINITIONS = [
    {
        "name": "run_sql",
        "description": (
            "Execute a read-only SQL query against the Cleo database "
            "(SQLite dialect). Always include LIMIT in your query. "
            f"Result rows are capped at {ROW_CAP}; if truncated=true, "
            "add LIMIT or aggregate. Per-query timeout: "
            f"{QUERY_TIMEOUT_SECONDS}s. Only SELECT/WITH/EXPLAIN allowed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "A single SELECT/WITH/EXPLAIN statement.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "describe_schema",
        "description": (
            "Inspect the database schema. Call with no arg to list every "
            "table with row count and a one-line description; call with "
            "table=<name> to see columns + 5 sample rows. "
            "USE THIS BEFORE WRITING run_sql AGAINST AN UNFAMILIAR TABLE."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "table": {"type": "string", "description": "Optional table name."},
            },
        },
    },
    {
        "name": "get_entity_url",
        "description": (
            "Build the in-app URL for an entity. Use to render clickable "
            "markdown links in your answer."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "entity_type": {
                    "type": "string",
                    "enum": ["property", "contact", "group", "deal", "list", "transaction"],
                },
                "id": {"type": "string"},
            },
            "required": ["entity_type", "id"],
        },
    },
]


# ── System prompt ────────────────────────────────────────────────────


_SYSTEM_PROMPT_BASE = """\
You are an analyst inside Cleo Turbo, a commercial real estate
prospecting tool for Ontario. The user is a CRE broker. They use
this tool to find acquisition targets, track outreach, and decide
who to call.

You have read-only access to a SQLite database via the run_sql tool.
Use describe_schema BEFORE writing queries against unfamiliar tables
— never guess column names. Always include LIMIT in your queries.
Quote ARNs (20-digit assessment roll numbers) and stable IDs
(CON_NNNNN, PRO_NNNNN, GRP_NNNNN) verbatim in answers; render them as
markdown links via get_entity_url when they refer to an entity the
user can click.

Tables fall into three categories:
- Derived (rebuilt by the compiler from clean-data/): properties,
  transactions, contacts, groups, group_names, transaction_parties,
  pois, gw_assessments, gw_sales_history.
- CRM (persistent, user-typed): deals, lists, list_members,
  group_contacts, contact_notes, group_notes, sell_opportunities,
  buy_mandates, activities, user_stars, contact_field_overrides.
- System: users, audit_log, app_meta, ai_usage.

Currency is CAD. Addresses are Ontario.

Style:
- Be terse. Direct numbers and named entities beat narration.
- When you find something, name it (CON_NNNNN, GRP_NNNNN) and link it.
- When the user's question is ambiguous, run a small probe query
  rather than asking back — bias for showing data.
- Never speculate about ownership beyond what's in the database.
"""


def _build_system_prompt_blocks(page_context_block: str) -> list[dict]:
    """Returns the system prompt as Anthropic content blocks. The first
    block is cache_control'd so prompt caching kicks in."""
    base = _SYSTEM_PROMPT_BASE
    if page_context_block:
        base = base.rstrip() + "\n\n" + page_context_block + "\n"
    return [
        {"type": "text", "text": base, "cache_control": {"type": "ephemeral"}},
    ]


# ── Anthropic client factory (patchable in tests) ─────────────────────


def _make_anthropic_client():
    """Build a real Anthropic client. Tests monkeypatch this to a fake."""
    import anthropic
    return anthropic.Anthropic()  # picks up ANTHROPIC_API_KEY


# ── DB helpers ───────────────────────────────────────────────────────


def _open_readonly() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{_RO_DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    # Per-query wall-clock interrupt so a slow / runaway query can't hang
    # the request. We tick the progress handler at ~1k vdbe ops; on each
    # tick we check elapsed time and return non-zero to abort.
    return conn


def _set_query_deadline(conn: sqlite3.Connection, deadline_ts: float) -> None:
    def _progress():
        return 1 if time.time() > deadline_ts else 0
    conn.set_progress_handler(_progress, 1000)


# ── Tool dispatch ────────────────────────────────────────────────────


def _execute_tool(name: str, args: dict, ro_conn: sqlite3.Connection) -> dict:
    """Run a tool the LLM requested. Returns a dict that gets serialized
    into a tool_result content block back to Anthropic.

    On error, returns { error: <message> } — Anthropic shows that to the
    LLM and it can self-correct on the next turn."""
    started = time.time()
    try:
        if name == "run_sql":
            _set_query_deadline(ro_conn, started + QUERY_TIMEOUT_SECONDS)
            try:
                out = run_sql(ro_conn, args.get("query", ""))
            finally:
                ro_conn.set_progress_handler(None, 0)
            out["elapsed_ms"] = int((time.time() - started) * 1000)
            return out
        if name == "describe_schema":
            return describe_schema(ro_conn, table=args.get("table"))
        if name == "get_entity_url":
            return {"url": get_entity_url(args["entity_type"], args["id"])}
        return {"error": f"Unknown tool: {name}"}
    except InvalidQueryError as exc:
        return {"error": str(exc)}
    except sqlite3.OperationalError as exc:
        return {"error": f"sqlite error: {exc}"}


# ── Pydantic schema ───────────────────────────────────────────────────


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class PageContext(BaseModel):
    entity_type: str
    id: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    page_context: PageContext | None = None
    route_at_open: str | None = None


# ── Streaming generator ───────────────────────────────────────────────


def _sse(event: str, payload: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n".encode()


def _block_to_dict(block) -> dict:
    """Anthropic SDK content blocks come back as Pydantic models. Convert
    one to the plain-dict shape we need to round-trip in api_messages."""
    btype = getattr(block, "type", None)
    if btype == "text":
        return {"type": "text", "text": block.text}
    if btype == "tool_use":
        return {
            "type": "tool_use",
            "id": block.id,
            "name": block.name,
            "input": block.input,  # already a dict per the SDK
        }
    # Defensive: pass through unknown block types as-is.
    return getattr(block, "model_dump", lambda: {})() or {"type": btype}


def _stream_chat(
    req: ChatRequest,
    user: dict,
    rw_conn: sqlite3.Connection,
) -> Iterator[bytes]:
    """Sequential turn loop:

      1. Open Anthropic stream.
      2. As `TextEvent`s arrive, forward `text_delta` SSE.
      3. When the stream ends, ask for the final message; iterate its
         content blocks and execute every tool_use block, forwarding
         `tool_use_start` / `tool_use_end` SSE around each.
      4. If stop_reason == "tool_use" and we're under the cap, append
         tool_result blocks and loop. Otherwise break and emit `done`.
    """
    ro = _open_readonly()
    try:
        page_block = load_page_context(
            ro,
            req.page_context.dict() if req.page_context else None,
        )
        system_blocks = _build_system_prompt_blocks(page_block)

        # Anthropic accepts plain string content for user messages; we
        # promote later turns to block lists when we add tool_result.
        api_messages: list[dict] = [
            {"role": m.role, "content": m.content} for m in req.messages
        ]

        client = _make_anthropic_client()

        tool_calls = 0
        cumulative_output_tokens = 0
        agg_input = agg_output = agg_cached = 0

        for _ in range(MAX_TOOL_CALLS + 1):
            stream_cm = client.messages.stream(
                model=DEFAULT_MODEL,
                max_tokens=MAX_OUTPUT_TOKENS,
                system=system_blocks,
                tools=TOOL_DEFINITIONS,
                messages=api_messages,
            )

            with stream_cm as stream:
                # Anthropic SDK iterates RAW events:
                #   content_block_delta → delta is TextDelta or InputJSONDelta
                #   content_block_start / content_block_stop / message_*
                # We only forward text deltas to the browser; tool_use
                # blocks are pulled from the resolved final message after
                # the stream ends, since their input only fully exists
                # there.
                for event in stream:
                    etype = getattr(event, "type", None)
                    if etype != "content_block_delta":
                        continue
                    delta = getattr(event, "delta", None)
                    if delta is None or getattr(delta, "type", None) != "text_delta":
                        continue
                    text = getattr(delta, "text", "")
                    if text:
                        yield _sse("text_delta", {"delta": text})

                # Stream is done. Pull the resolved message + usage.
                final = stream.get_final_message()

            stop_reason = final.stop_reason
            usage = final.usage  # SDK Usage model
            agg_input += getattr(usage, "input_tokens", 0) or 0
            agg_output += getattr(usage, "output_tokens", 0) or 0
            agg_cached += getattr(usage, "cache_read_input_tokens", 0) or 0
            cumulative_output_tokens += getattr(usage, "output_tokens", 0) or 0

            # Persist the assistant turn so the next call sees it.
            assistant_blocks = [_block_to_dict(b) for b in final.content]
            api_messages.append({"role": "assistant", "content": assistant_blocks})

            # If Claude requested tools, execute them in document order
            # and stream tool_use_start / tool_use_end SSE events.
            tool_results: list[dict] = []
            for block in final.content:
                if getattr(block, "type", None) != "tool_use":
                    continue
                tool_calls += 1
                tool_id = block.id
                yield _sse("tool_use_start", {
                    "id": tool_id, "name": block.name, "input": block.input,
                })
                result = _execute_tool(block.name, block.input, ro)
                ok = "error" not in result
                summary: dict = {"id": tool_id, "ok": ok}
                if not ok:
                    summary["error"] = result["error"]
                elif block.name == "run_sql":
                    summary["row_count"] = result.get("row_count", 0)
                    summary["truncated"] = result.get("truncated", False)
                    summary["elapsed_ms"] = result.get("elapsed_ms")
                yield _sse("tool_use_end", summary)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": json.dumps(result),
                })

            if stop_reason != "tool_use" or not tool_results:
                break  # Conversation turn complete.

            if tool_calls >= MAX_TOOL_CALLS:
                yield _sse("text_delta", {
                    "delta": "\n\n_(stopped after 15 tool calls — ask a more specific question to continue.)_",
                })
                break
            if cumulative_output_tokens >= MAX_OUTPUT_TOKENS_PER_CONVERSATION:
                yield _sse("text_delta", {
                    "delta": "\n\n_(stopped at output-token cap.)_",
                })
                break

            # Append the tool results and loop for the next turn.
            api_messages.append({"role": "user", "content": tool_results})

        # Persist usage row.
        first_user = next(
            (m.content for m in req.messages if m.role == "user"),
            "",
        )[:200]
        rw_conn.execute(
            "INSERT INTO ai_usage (user_id, input_tokens, output_tokens, "
            "cached_tokens, tool_calls, model, route_at_open, first_user_message) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                user.get("sub"),
                agg_input, agg_output, agg_cached,
                tool_calls, DEFAULT_MODEL,
                req.route_at_open, first_user,
            ),
        )
        rw_conn.commit()

        yield _sse("done", {
            "stop_reason": "end_turn",
            "tool_calls": tool_calls,
            "input_tokens": agg_input,
            "output_tokens": agg_output,
            "cached_tokens": agg_cached,
        })
    finally:
        ro.close()


# ── Router ───────────────────────────────────────────────────────────


router = APIRouter()


@router.post("/chat")
def chat(
    body: ChatRequest,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    if not body.messages:
        raise HTTPException(status_code=400, detail="messages must not be empty")

    return StreamingResponse(
        _stream_chat(body, user, db),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

- [ ] **Step 2: Run the AI route tests**

```bash
PYTHONPATH=. pytest tests/test_routes_ai.py -v 2>&1 | tail -25
```

Expected: 5/5 pass. (If anything fails on the cap-loop test, double-check `MAX_TOOL_CALLS = 15`.)

- [ ] **Step 3: Commit**

```bash
git add cleo/web/routes/ai.py
git commit -m "feat(api): /api/ai/chat — SSE streaming + tool loop + usage logging"
```

---

## Task 10: Register the AI router

**Files:**
- Modify: `cleo/web/app.py`

- [ ] **Step 1: Find the existing router registration block**

```bash
grep -n "include_router" cleo/web/app.py | head -5
```

Pick the line under the most recent feature router (e.g., `attribution` or `stars`). Add the AI router right after.

- [ ] **Step 2: Wire the import + include_router**

In `cleo/web/app.py`, find the imports for the route modules and add:

```python
from .routes import ai as ai_routes
```

Find where the existing routers are registered and add:

```python
app.include_router(ai_routes.router, prefix="/api/ai", tags=["ai"])
```

- [ ] **Step 3: Run the full backend test suite**

```bash
PYTHONPATH=. pytest tests/ --ignore=tests/test_discovery_v2_expansion.py --ignore=tests/test_consolidation_infrastructure.py 2>&1 | tail -3
```

Expected: clean (560+ passed).

- [ ] **Step 4: Smoke check the live backend — restart if needed**

```bash
# Kill any old listener and restart cleanly
lsof -ti:8099 -sTCP:LISTEN | xargs kill -9 2>/dev/null
uvicorn cleo.web.app:app --reload --port 8099 &
sleep 5
# Endpoint exists? It must require auth — 401 is the expected unauthenticated response.
curl -s -m 5 -o /dev/null -w "HTTP %{http_code}\n" -X POST http://localhost:8099/api/ai/chat -H "Content-Type: application/json" -d '{"messages":[{"role":"user","content":"x"}]}'
```

Expected: HTTP 401.

- [ ] **Step 5: Commit**

```bash
git add cleo/web/app.py
git commit -m "feat(api): register /api/ai router"
```

---

## Task 11: Install frontend deps (react-markdown + remark-gfm)

**Files:**
- Modify: `frontend/package.json`, `frontend/package-lock.json`

- [ ] **Step 1: Install**

```bash
cd /Users/brandonolsen23/cleo-turbo/frontend
npm install react-markdown remark-gfm
```

- [ ] **Step 2: Verify the entries landed in package.json**

```bash
grep -E "react-markdown|remark-gfm" package.json
```

Expected: both lines present under `dependencies`.

- [ ] **Step 3: Type-check**

```bash
npx tsc -b --noEmit 2>&1 | tail -3
```

Expected: clean (no new errors from the install).

- [ ] **Step 4: Commit**

```bash
cd /Users/brandonolsen23/cleo-turbo
git add frontend/package.json frontend/package-lock.json
git commit -m "chore(deps): add react-markdown + remark-gfm for AI sidebar"
```

---

## Task 12: TypeScript types for AI

**Files:**
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Append the AI types to the bottom of the file**

```ts
// ============================================================
// AI Sidebar
// ============================================================

export type AIRole = "user" | "assistant";

export interface AITextPart {
  kind: "text";
  text: string;
}

export interface AIToolPart {
  kind: "tool";
  id: string;
  name: "run_sql" | "describe_schema" | "get_entity_url";
  input: Record<string, unknown>;
  /** undefined = in flight, true/false once tool_use_end arrives. */
  ok?: boolean;
  error?: string;
  rowCount?: number;
  truncated?: boolean;
  elapsedMs?: number;
}

export type AIMessagePart = AITextPart | AIToolPart;

export interface AIMessage {
  role: AIRole;
  parts: AIMessagePart[];
  /** Streaming flag for the active assistant message. */
  inFlight?: boolean;
}

export interface AIPageContext {
  entity_type: "property" | "contact" | "group" | "deal" | "list" | "transaction";
  id: string;
}

export interface AIDoneEvent {
  stop_reason: string;
  tool_calls: number;
  input_tokens: number;
  output_tokens: number;
  cached_tokens: number;
}
```

- [ ] **Step 2: Type-check**

```bash
cd frontend && npx tsc -b --noEmit 2>&1 | tail -5
```

Expected: clean.

- [ ] **Step 3: Commit**

```bash
cd /Users/brandonolsen23/cleo-turbo
git add frontend/src/types/index.ts
git commit -m "types(frontend): AI sidebar message + tool + page-context types"
```

---

## Task 13: SSE-aware fetch wrapper

**Files:**
- Create: `frontend/src/api/aiClient.ts`

- [ ] **Step 1: Implement**

```ts
import type {
  AIDoneEvent, AIMessage, AIPageContext, AIRole,
} from "../types";

const TOKEN_KEY = "cleo_jwt"; // matches the existing api/client.ts convention

interface ChatBody {
  messages: { role: AIRole; content: string }[];
  page_context: AIPageContext | null;
  route_at_open: string | null;
}

export interface AIStreamHandlers {
  onTextDelta(delta: string): void;
  onToolUseStart(part: { id: string; name: string; input: Record<string, unknown> }): void;
  onToolUseEnd(part: {
    id: string; ok: boolean; error?: string;
    row_count?: number; truncated?: boolean; elapsed_ms?: number;
  }): void;
  onDone(evt: AIDoneEvent): void;
  onError(message: string): void;
}

/** Convert AIMessage history to the on-the-wire { role, content } shape. */
function flattenMessage(m: AIMessage): { role: AIRole; content: string } {
  const text = m.parts
    .filter((p): p is { kind: "text"; text: string } => p.kind === "text")
    .map((p) => p.text)
    .join("");
  return { role: m.role, content: text };
}

export async function streamChat(
  history: AIMessage[],
  pageContext: AIPageContext | null,
  routeAtOpen: string | null,
  handlers: AIStreamHandlers,
): Promise<void> {
  const token = localStorage.getItem(TOKEN_KEY);
  const body: ChatBody = {
    messages: history.map(flattenMessage),
    page_context: pageContext,
    route_at_open: routeAtOpen,
  };
  const resp = await fetch("/api/ai/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });

  if (!resp.ok || !resp.body) {
    handlers.onError(`HTTP ${resp.status}`);
    return;
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buf = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });

    // Parse complete SSE events. Each event is a block separated by \n\n.
    let idx: number;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const block = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      const lines = block.split("\n");
      let event = "message";
      const dataParts: string[] = [];
      for (const line of lines) {
        if (line.startsWith("event: ")) event = line.slice(7).trim();
        else if (line.startsWith("data: ")) dataParts.push(line.slice(6));
      }
      if (!dataParts.length) continue;
      let payload: any;
      try {
        payload = JSON.parse(dataParts.join("\n"));
      } catch {
        continue;
      }
      switch (event) {
        case "text_delta":
          handlers.onTextDelta(payload.delta);
          break;
        case "tool_use_start":
          handlers.onToolUseStart(payload);
          break;
        case "tool_use_end":
          handlers.onToolUseEnd(payload);
          break;
        case "done":
          handlers.onDone(payload);
          break;
        case "error":
          handlers.onError(payload.message ?? "unknown error");
          break;
      }
    }
  }
}
```

- [ ] **Step 2: Type-check**

```bash
cd frontend && npx tsc -b --noEmit 2>&1 | tail -3
```

Expected: clean.

- [ ] **Step 3: Verify the JWT key matches the existing client**

```bash
grep -n "cleo_jwt\|TOKEN_KEY\|localStorage" frontend/src/api/client.ts | head -5
```

If the existing client uses a different key (e.g., `"token"`), update the constant in `aiClient.ts` to match.

- [ ] **Step 4: Commit**

```bash
cd /Users/brandonolsen23/cleo-turbo
git add frontend/src/api/aiClient.ts
git commit -m "feat(frontend): SSE-aware streamChat client for /api/ai/chat"
```

---

## Task 14: usePageContext hook

**Files:**
- Create: `frontend/src/components/ai/usePageContext.ts`

- [ ] **Step 1: Implement**

```ts
import { useLocation } from "react-router-dom";
import type { AIPageContext } from "../../types";

const ROUTE_PATTERNS: { regex: RegExp; entity_type: AIPageContext["entity_type"] }[] = [
  { regex: /^\/properties\/([^/?#]+)/,    entity_type: "property"    },
  { regex: /^\/contacts\/([^/?#]+)/,      entity_type: "contact"     },
  { regex: /^\/groups\/([^/?#]+)/,        entity_type: "group"       },
  { regex: /^\/deals\/([^/?#]+)/,         entity_type: "deal"        },
  { regex: /^\/lists\/([^/?#]+)/,         entity_type: "list"        },
  { regex: /^\/transactions\/([^/?#]+)/,  entity_type: "transaction" },
];

/** Read the current pathname and, if it matches a known entity-detail
 * route, return the matching AIPageContext. Otherwise null. */
export function usePageContext(): AIPageContext | null {
  const { pathname } = useLocation();
  for (const { regex, entity_type } of ROUTE_PATTERNS) {
    const m = pathname.match(regex);
    if (m && m[1]) return { entity_type, id: m[1] };
  }
  return null;
}
```

- [ ] **Step 2: Type-check**

```bash
cd frontend && npx tsc -b --noEmit 2>&1 | tail -3
```

Expected: clean.

- [ ] **Step 3: Commit**

```bash
cd /Users/brandonolsen23/cleo-turbo
git add frontend/src/components/ai/usePageContext.ts
git commit -m "feat(frontend): usePageContext hook — derive AI context from current route"
```

---

## Task 15: ToolCallBlock component

**Files:**
- Create: `frontend/src/components/ai/ToolCallBlock.tsx`

- [ ] **Step 1: Implement**

```tsx
import { useState } from "react";
import { Text, Badge } from "@radix-ui/themes";
import { CaretRight, CaretDown, Database, MagnifyingGlass, Link as LinkIcon } from "@phosphor-icons/react";
import type { AIToolPart } from "../../types";

const ICON: Record<AIToolPart["name"], JSX.Element> = {
  run_sql:         <Database size={14} />,
  describe_schema: <MagnifyingGlass size={14} />,
  get_entity_url:  <LinkIcon size={14} />,
};

function summarize(part: AIToolPart): string {
  if (part.error) return part.error;
  if (part.ok === undefined) return "running…";
  if (part.name === "run_sql") {
    const n = part.rowCount ?? 0;
    return `${n} ${n === 1 ? "row" : "rows"}${part.truncated ? " (truncated)" : ""}`;
  }
  if (part.name === "describe_schema") {
    const t = (part.input as { table?: string }).table;
    return t ? `described ${t}` : "listed tables";
  }
  return "ok";
}

function highlightSQL(sql: string): JSX.Element {
  const KEYWORDS = /\b(SELECT|FROM|WHERE|JOIN|LEFT|RIGHT|INNER|OUTER|ON|GROUP BY|ORDER BY|HAVING|LIMIT|OFFSET|WITH|AS|AND|OR|NOT|IN|IS|NULL|LIKE|EXISTS|CASE|WHEN|THEN|ELSE|END|UNION|ALL|DISTINCT|EXPLAIN)\b/gi;
  const parts = sql.split(KEYWORDS);
  return (
    <pre className="text-[12px] whitespace-pre-wrap break-words p-2 rounded bg-[var(--gray-3)]">
      {parts.map((seg, i) =>
        i % 2 === 1 ? (
          <span key={i} style={{ color: "var(--accent-11)", fontWeight: 600 }}>{seg}</span>
        ) : (
          <span key={i}>{seg}</span>
        )
      )}
    </pre>
  );
}

export default function ToolCallBlock({ part }: { part: AIToolPart }) {
  const [open, setOpen] = useState(false);
  const summary = summarize(part);
  const isError = part.ok === false || !!part.error;

  return (
    <div className="my-2 rounded border border-[var(--gray-6)] overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-[var(--gray-2)]"
      >
        {open ? <CaretDown size={12} /> : <CaretRight size={12} />}
        {ICON[part.name]}
        <Text size="2" weight="medium">{part.name}</Text>
        <Text size="1" style={{ color: isError ? "var(--red-11)" : "var(--gray-9)" }}>
          · {summary}
        </Text>
        {part.elapsedMs !== undefined && (
          <Badge size="1" variant="soft" color="gray">{part.elapsedMs}ms</Badge>
        )}
      </button>
      {open && (
        <div className="px-3 pb-3 border-t border-[var(--gray-4)]">
          {part.name === "run_sql" && (
            <>
              <Text size="1" weight="medium" className="block mt-2 mb-1" style={{ color: "var(--gray-11)" }}>Query</Text>
              {highlightSQL((part.input as { query?: string }).query ?? "")}
            </>
          )}
          {part.name === "describe_schema" && (part.input as { table?: string }).table && (
            <Text size="2">Table: <code>{(part.input as { table: string }).table}</code></Text>
          )}
          {part.name === "get_entity_url" && (
            <Text size="2">
              {(part.input as { entity_type: string; id: string }).entity_type}{" "}
              <code>{(part.input as { entity_type: string; id: string }).id}</code>
            </Text>
          )}
          {isError && (
            <Text size="2" style={{ color: "var(--red-11)" }} className="block mt-2">
              {part.error}
            </Text>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

```bash
cd frontend && npx tsc -b --noEmit 2>&1 | tail -3
```

Expected: clean.

- [ ] **Step 3: Commit**

```bash
cd /Users/brandonolsen23/cleo-turbo
git add frontend/src/components/ai/ToolCallBlock.tsx
git commit -m "feat(frontend): ToolCallBlock — collapsed/expanded tool-call rendering"
```

---

## Task 16: MessageBubble component

**Files:**
- Create: `frontend/src/components/ai/MessageBubble.tsx`

- [ ] **Step 1: Implement**

```tsx
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Link as RouterLink } from "react-router-dom";
import { Text } from "@radix-ui/themes";
import type { AIMessage, AIToolPart } from "../../types";
import ToolCallBlock from "./ToolCallBlock";

export default function MessageBubble({ message }: { message: AIMessage }) {
  const isUser = message.role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-3`}>
      <div
        className={`max-w-[88%] rounded-lg px-3 py-2 text-[14px] leading-relaxed ${
          isUser ? "bg-[var(--accent-3)]" : "bg-[var(--gray-2)]"
        }`}
      >
        {message.parts.map((part, i) => {
          if (part.kind === "tool") {
            return <ToolCallBlock key={i} part={part as AIToolPart} />;
          }
          return (
            <ReactMarkdown
              key={i}
              remarkPlugins={[remarkGfm]}
              components={{
                a: ({ href = "", children, ...rest }) => {
                  if (href.startsWith("/")) {
                    return (
                      <RouterLink
                        to={href}
                        style={{ color: "var(--accent-11)" }}
                        className="no-underline hover:underline"
                      >
                        {children}
                      </RouterLink>
                    );
                  }
                  return (
                    <a
                      href={href}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ color: "var(--accent-11)" }}
                      className="no-underline hover:underline"
                      {...rest}
                    >
                      {children}
                    </a>
                  );
                },
                code: ({ children }) => (
                  <code className="px-1 py-0.5 rounded bg-[var(--gray-3)] text-[12px]">{children}</code>
                ),
                pre: ({ children }) => (
                  <pre className="p-2 rounded bg-[var(--gray-3)] overflow-x-auto text-[12px]">{children}</pre>
                ),
                table: ({ children }) => (
                  <table className="my-2 text-[12px] border-collapse w-full">{children}</table>
                ),
                th: ({ children }) => (
                  <th className="px-2 py-1 text-left bg-[var(--gray-3)] border border-[var(--gray-5)]">{children}</th>
                ),
                td: ({ children }) => (
                  <td className="px-2 py-1 border border-[var(--gray-5)]">{children}</td>
                ),
              }}
            >
              {part.text}
            </ReactMarkdown>
          );
        })}
        {message.inFlight && (
          <Text size="1" style={{ color: "var(--gray-9)" }}>▍</Text>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

```bash
cd frontend && npx tsc -b --noEmit 2>&1 | tail -3
```

Expected: clean.

- [ ] **Step 3: Commit**

```bash
cd /Users/brandonolsen23/cleo-turbo
git add frontend/src/components/ai/MessageBubble.tsx
git commit -m "feat(frontend): MessageBubble — markdown + tool-call rendering"
```

---

## Task 17: SuggestedPrompts component

**Files:**
- Create: `frontend/src/components/ai/SuggestedPrompts.tsx`

- [ ] **Step 1: Implement**

```tsx
import { Text } from "@radix-ui/themes";
import type { AIPageContext } from "../../types";

const PROMPTS_PROPERTY = [
  "Tell me about this owner",
  "Recent comparable sales nearby",
  "Other properties this owner has bought",
];

const PROMPTS_PEOPLE = [
  "What does their portfolio look like?",
  "What have they bought recently?",
  "Who else are they affiliated with?",
];

const PROMPTS_OPEN = [
  "Find retail buyers in Halton with $20M+ portfolios",
  "Who's been most active in Brantford this year?",
  "Show me dormant contacts I should re-engage",
];

function chooseSet(ctx: AIPageContext | null): string[] {
  if (!ctx) return PROMPTS_OPEN;
  if (ctx.entity_type === "property") return PROMPTS_PROPERTY;
  if (ctx.entity_type === "contact" || ctx.entity_type === "group") return PROMPTS_PEOPLE;
  return PROMPTS_OPEN;
}

export default function SuggestedPrompts({
  context,
  onPick,
}: {
  context: AIPageContext | null;
  onPick: (prompt: string) => void;
}) {
  const prompts = chooseSet(context);
  return (
    <div className="flex flex-col gap-2">
      <Text size="1" style={{ color: "var(--gray-9)" }} className="block mb-1">Try asking:</Text>
      {prompts.map((p) => (
        <button
          key={p}
          type="button"
          onClick={() => onPick(p)}
          className="text-left px-3 py-2 rounded border border-[var(--gray-6)] hover:bg-[var(--gray-2)] text-[13px]"
        >
          {p}
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Type-check + commit**

```bash
cd frontend && npx tsc -b --noEmit 2>&1 | tail -3
cd /Users/brandonolsen23/cleo-turbo
git add frontend/src/components/ai/SuggestedPrompts.tsx
git commit -m "feat(frontend): SuggestedPrompts — route-aware empty-state prompts"
```

---

## Task 18: AskClaudeDrawer — assemble the chat surface

**Files:**
- Create: `frontend/src/components/ai/AskClaudeDrawer.tsx`

- [ ] **Step 1: Implement**

```tsx
import { useEffect, useRef, useState } from "react";
import { Heading, Text, TextArea, Button, Badge } from "@radix-ui/themes";
import { X, PaperPlaneTilt } from "@phosphor-icons/react";
import { useLocation } from "react-router-dom";
import { streamChat } from "../../api/aiClient";
import { usePageContext } from "./usePageContext";
import MessageBubble from "./MessageBubble";
import SuggestedPrompts from "./SuggestedPrompts";
import type { AIMessage, AIToolPart } from "../../types";

interface AskClaudeDrawerProps {
  open: boolean;
  onClose: () => void;
}

function newAssistant(): AIMessage {
  return { role: "assistant", parts: [], inFlight: true };
}

export default function AskClaudeDrawer({ open, onClose }: AskClaudeDrawerProps) {
  const pageContext = usePageContext();
  const { pathname } = useLocation();
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<AIMessage[]>([]);
  const [pending, setPending] = useState(false);
  const scrollerRef = useRef<HTMLDivElement>(null);

  // Auto-scroll on new content.
  useEffect(() => {
    if (!scrollerRef.current) return;
    scrollerRef.current.scrollTop = scrollerRef.current.scrollHeight;
  }, [messages]);

  // Focus the input when the drawer opens.
  const inputRef = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  async function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || pending) return;
    setInput("");
    setPending(true);

    const userMsg: AIMessage = {
      role: "user",
      parts: [{ kind: "text", text: trimmed }],
    };
    const assistant = newAssistant();
    const history = [...messages, userMsg, assistant];
    setMessages(history);

    const toolIndex = new Map<string, AIToolPart>();

    function patchAssistant(mutator: (m: AIMessage) => AIMessage) {
      setMessages((prev) => {
        const next = prev.slice();
        next[next.length - 1] = mutator(next[next.length - 1]);
        return next;
      });
    }

    try {
      await streamChat(
        [...messages, userMsg],
        pageContext,
        pathname,
        {
          onTextDelta: (delta) => {
            patchAssistant((m) => {
              const parts = m.parts.slice();
              const last = parts[parts.length - 1];
              if (last && last.kind === "text") {
                parts[parts.length - 1] = { kind: "text", text: last.text + delta };
              } else {
                parts.push({ kind: "text", text: delta });
              }
              return { ...m, parts };
            });
          },
          onToolUseStart: ({ id, name, input }) => {
            const tp: AIToolPart = {
              kind: "tool",
              id, name: name as AIToolPart["name"],
              input,
            };
            toolIndex.set(id, tp);
            patchAssistant((m) => ({ ...m, parts: [...m.parts, tp] }));
          },
          onToolUseEnd: ({ id, ok, error, row_count, truncated, elapsed_ms }) => {
            const tp = toolIndex.get(id);
            if (!tp) return;
            tp.ok = ok;
            tp.error = error;
            tp.rowCount = row_count;
            tp.truncated = truncated;
            tp.elapsedMs = elapsed_ms;
            // Force a re-render
            patchAssistant((m) => ({ ...m, parts: m.parts.map((p) => (p as AIToolPart).id === id ? { ...tp } : p) }));
          },
          onDone: () => {
            patchAssistant((m) => ({ ...m, inFlight: false }));
          },
          onError: (msg) => {
            patchAssistant((m) => ({
              ...m,
              parts: [...m.parts, { kind: "text", text: `\n\n_Error: ${msg}_` }],
              inFlight: false,
            }));
          },
        },
      );
    } catch (err) {
      patchAssistant((m) => ({
        ...m,
        parts: [...m.parts, { kind: "text", text: `\n\n_Network error: ${String(err)}_` }],
        inFlight: false,
      }));
    } finally {
      setPending(false);
    }
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      send(input);
    }
  }

  if (!open) return null;
  const empty = messages.length === 0;

  return (
    <div className="fixed inset-0 z-50 flex">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />
      <div
        className="relative ml-auto h-full flex flex-col"
        style={{
          width: 420,
          background: "var(--color-background)",
          borderLeft: "1px solid var(--gray-6)",
        }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--gray-6)]">
          <div className="flex items-center gap-2">
            <Heading size="3">Ask Claude</Heading>
            {pageContext && (
              <Badge size="1" variant="soft" color="jade">
                Looking at {pageContext.id}
              </Badge>
            )}
          </div>
          <button onClick={onClose} className="p-1 rounded hover:bg-[var(--gray-3)]">
            <X size={18} />
          </button>
        </div>

        {/* Messages */}
        <div ref={scrollerRef} className="flex-1 overflow-y-auto px-4 py-3">
          {empty ? (
            <SuggestedPrompts context={pageContext} onPick={(p) => setInput(p)} />
          ) : (
            messages.map((m, i) => <MessageBubble key={i} message={m} />)
          )}
        </div>

        {/* Input */}
        <div className="border-t border-[var(--gray-6)] p-3">
          <TextArea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Ask anything about your data… (⌘+Enter to send)"
            rows={3}
            disabled={pending}
          />
          <div className="flex justify-end mt-2">
            <Button
              onClick={() => send(input)}
              disabled={pending || !input.trim()}
              size="2"
            >
              <PaperPlaneTilt size={14} /> Send
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

```bash
cd frontend && npx tsc -b --noEmit 2>&1 | tail -3
```

Expected: clean.

- [ ] **Step 3: Commit**

```bash
cd /Users/brandonolsen23/cleo-turbo
git add frontend/src/components/ai/AskClaudeDrawer.tsx
git commit -m "feat(frontend): AskClaudeDrawer — chat surface with streaming, page context, suggested prompts"
```

---

## Task 19: Header trigger button

**Files:**
- Modify: `frontend/src/components/layout/Header.tsx`

- [ ] **Step 1: Inspect the existing header**

```bash
grep -n "import\|return\|className" frontend/src/components/layout/Header.tsx | head -25
```

The header should have a search bar and the user menu. Find the right edge of the header.

- [ ] **Step 2: Add the trigger button**

Add a prop `onAskClaude: () => void` to `Header.tsx`. Render a button with the Sparkle icon next to the search bar. Example diff:

```tsx
import { MagnifyingGlass, Sparkle } from "@phosphor-icons/react";

// In the props interface:
interface HeaderProps {
  // ...existing props...
  onAskClaude: () => void;
}

// In the right-side region of the header (next to the search bar / before user menu):
<button
  onClick={onAskClaude}
  className="inline-flex items-center gap-1 px-2 py-1 rounded hover:bg-[var(--gray-3)] text-[13px]"
  title="Ask Claude (⌘I)"
  style={{ color: "var(--gray-11)" }}
>
  <Sparkle size={16} />
</button>
```

(Adjust import path / button placement to match the actual structure of `Header.tsx`.)

- [ ] **Step 3: Type-check**

```bash
cd frontend && npx tsc -b --noEmit 2>&1 | tail -3
```

Expected: TS errors about `onAskClaude` not being passed yet — that's wired up in Task 20. As long as the only errors are about the missing prop in `AppLayout.tsx`, you're good. Don't fix here.

- [ ] **Step 4: Commit**

```bash
cd /Users/brandonolsen23/cleo-turbo
git add frontend/src/components/layout/Header.tsx
git commit -m "feat(frontend): Header trigger button for Ask Claude (⌘I)"
```

---

## Task 20: Wire the drawer + keyboard shortcut into AppLayout

**Files:**
- Modify: `frontend/src/components/layout/AppLayout.tsx`

- [ ] **Step 1: Inspect AppLayout**

```bash
grep -n "Header\|Outlet\|useState\|useEffect" frontend/src/components/layout/AppLayout.tsx | head -10
```

- [ ] **Step 2: Add the drawer state, the shortcut, and pass `onAskClaude` to `Header`**

At the top of `AppLayout.tsx`:

```tsx
import { useEffect, useState } from "react";
import AskClaudeDrawer from "../ai/AskClaudeDrawer";
```

Inside the component:

```tsx
const [askOpen, setAskOpen] = useState(false);

useEffect(() => {
  const handler = (e: KeyboardEvent) => {
    const meta = e.metaKey || e.ctrlKey;
    if (meta && e.key.toLowerCase() === "i") {
      e.preventDefault();
      setAskOpen((v) => !v);
    }
  };
  window.addEventListener("keydown", handler);
  return () => window.removeEventListener("keydown", handler);
}, []);
```

Pass `onAskClaude={() => setAskOpen(true)}` into the existing `<Header ... />`. Render the drawer next to the existing layout (after `<Outlet />`):

```tsx
<AskClaudeDrawer open={askOpen} onClose={() => setAskOpen(false)} />
```

- [ ] **Step 3: Type-check**

```bash
cd frontend && npx tsc -b --noEmit 2>&1 | tail -3
```

Expected: clean.

- [ ] **Step 4: Commit**

```bash
cd /Users/brandonolsen23/cleo-turbo
git add frontend/src/components/layout/AppLayout.tsx
git commit -m "feat(frontend): wire AskClaudeDrawer + ⌘I shortcut into AppLayout"
```

---

## Task 21: End-to-end manual smoke test

**Files:** none (verification).

- [ ] **Step 1: Make sure both dev servers are up**

```bash
# Backend
lsof -ti:8099 -sTCP:LISTEN >/dev/null || (uvicorn cleo.web.app:app --reload --port 8099 &)
sleep 3
curl -s -m 5 -o /dev/null -w "backend: HTTP %{http_code}\n" http://localhost:8099/api/properties
# Frontend
lsof -ti:5174 -sTCP:LISTEN >/dev/null || (cd frontend && npm run dev &)
sleep 5
curl -s -m 5 -o /dev/null -w "frontend: HTTP %{http_code}\n" http://localhost:5174/
```

Expected: backend HTTP 401 (auth-required), frontend HTTP 200.

- [ ] **Step 2: Confirm `ANTHROPIC_API_KEY` is set in your shell**

```bash
echo "${ANTHROPIC_API_KEY:0:8}…"
```

Expected: prints a non-empty prefix. If empty: `export ANTHROPIC_API_KEY=sk-ant-...` and restart the backend.

- [ ] **Step 3: In the browser, log in and run the smoke flow**

Open `http://localhost:5174`, log in, then:

1. Click the **Sparkle** icon in the header (or press `⌘I`). Drawer slides in from the right.
2. Empty state shows three suggested prompts based on the current page (Dashboard → "Find retail buyers in Halton…" etc.).
3. Navigate to a property: `/properties/PRO_84463`. Drawer should now show a "Looking at PRO_84463" pill at the top.
4. Press `⌘I` to close, `⌘I` to reopen — state persists in this session.
5. Type **"Tell me about this owner"** and press `⌘+Enter` (or Send).
6. Watch:
   - A `▶ run_sql` block appears as Claude calls the tool.
   - The block updates from "running…" to "N rows · NNNms".
   - The assistant message starts streaming text below the tool block.
   - Any CON_/PRO_/GRP_ identifiers in the answer are clickable and navigate inside the app.
7. Type **"Drop the properties table"** to confirm the guard kicks in: Claude either refuses outright or attempts run_sql and gets back the InvalidQueryError, then apologizes.

- [ ] **Step 4: Verify usage logging**

```bash
sqlite3 data/cleo.db "SELECT id, user_id, input_tokens, output_tokens, cached_tokens, tool_calls, model, route_at_open, first_user_message FROM ai_usage ORDER BY id DESC LIMIT 5;"
```

Expected: at least one row per smoke conversation, with `model = 'claude-opus-4-7'`, plausible token counts, the route at open, and the truncated first user message.

- [ ] **Step 5: Final test suite**

```bash
PYTHONPATH=. pytest tests/ --ignore=tests/test_discovery_v2_expansion.py --ignore=tests/test_consolidation_infrastructure.py 2>&1 | tail -3
cd frontend && npx tsc -b --noEmit 2>&1 | tail -3
```

Expected: backend tests green, frontend type-check clean.

- [ ] **Step 6: Final commit (only if any cleanup is needed). If steps 1–5 passed without changes, no commit.**

---

## Summary

| | Backend | Frontend | Migration | Tests |
|---|---|---|---|---|
| New files | `cleo/web/routes/ai.py`, `cleo/web/routes/ai_tools.py` | `frontend/src/components/ai/{AskClaudeDrawer,MessageBubble,ToolCallBlock,SuggestedPrompts,usePageContext}.{tsx,ts}`, `frontend/src/api/aiClient.ts` | `cleo/database/migrations/023_ai_usage.py` | `tests/test_ai_tools.py`, `tests/test_routes_ai.py`, `tests/test_migration_023_ai_usage.py` |
| Modified files | `cleo/web/app.py`, `cleo/database/schema.py`, `CLAUDE.md` | `frontend/src/types/index.ts`, `frontend/src/components/layout/{Header,AppLayout}.tsx`, `frontend/package.json`, `frontend/package-lock.json` | — | — |
| New deps | `anthropic ≥ 0.40` | `react-markdown`, `remark-gfm` | — | — |
| New env var | `ANTHROPIC_API_KEY`, optional `AI_MODEL` | — | — | — |

## Test plan

- [ ] `pytest tests/test_migration_023_ai_usage.py` — 3 tests pass
- [ ] `pytest tests/test_ai_tools.py` — ~25 tests pass (run_sql happy/reject, describe_schema, get_entity_url, page-context loader)
- [ ] `pytest tests/test_routes_ai.py` — 5 tests pass with the mocked Anthropic client
- [ ] Full suite (backend) — 568+ pass
- [ ] `cd frontend && npx tsc -b --noEmit` — clean
- [ ] Manual smoke per Task 21
