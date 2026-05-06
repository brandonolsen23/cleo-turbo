# CRM Daily-Outreach Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Cleo's CRM usable daily for outreach prospecting — per-user stars, a personal Queue page, wired Add-to-List + Create-Deal buttons, a shared Quick Action Bar across Property/Contact/Group detail pages, multi-entity-aware activities (schema only — frontend defers to Phase 2), auto-engage on activity log, and first/last-contacted attribution surfaces.

**Architecture:** Single SQLite migration `020_crm_daily_outreach.py` adds the `user_stars` table, scope/ownership columns on `lists`, and FK + audit columns on `activities`. Backend extends one existing route family (`activities`, `lists`, `contacts`, `groups`, `properties`) and adds one new router (`stars.py`). Frontend introduces five shared components (`QuickActionBar`, `StarButton`, `AddToListDrawer`, `CreateDealDrawer`, `AttributionStrip`) and one new page (`/queue`). All architectural decisions are locked in `docs/superpowers/specs/2026-05-05-crm-daily-outreach-design.md` — read that spec end-to-end before starting Task 1.

**Tech Stack:** Python 3.12, FastAPI, SQLite, raw SQL (no ORM), pytest with in-memory SQLite + `TestClient`. Frontend: React 19, TypeScript, Vite, Radix UI Themes, Phosphor Icons, `react-router-dom` v7, `fetchApi/postApi/mutateApi` helpers from `frontend/src/api/client.ts`.

**Branching:** Create a new branch off `main` named `feat/crm-daily-outreach-phase-1`. The current working branch (`feat/group-discovery-algorithm`) is unrelated and should not be the base.

**Working rules:**
- Run `cd frontend && npx tsc --noEmit` before every frontend commit (per CLAUDE.md).
- Backend ports: 8099. Frontend dev: 5174. Never use random ports.
- All backend routes use raw SQL with `?` placeholders. No ORM.
- Existing engaged-status `'pool'` and `'engaged'` semantics on `contacts.status` / `groups.status` are preserved — don't introduce new values.
- TDD: write the failing test first, run it, watch it fail, then implement.

---

## File Structure

**New files:**
- `cleo/database/migrations/020_crm_daily_outreach.py` — schema migration (Tasks 1–2)
- `cleo/web/routes/stars.py` — stars CRUD + queue payload (Task 4)
- `tests/test_migration_020_crm_daily_outreach.py` — migration tests (Task 1)
- `tests/test_routes_stars.py` — stars route tests (Task 4)
- `tests/test_routes_lists_scope.py` — lists scope/ownership tests (Task 5)
- `tests/test_routes_activities_phase1.py` — activities upgrades tests (Task 7)
- `tests/test_routes_engage_synthetic_activity.py` — manual engage activity tests (Task 8)
- `tests/test_routes_attribution.py` — attribution endpoint tests (Task 9)
- `frontend/src/components/crm/StarButton.tsx` — Task 11
- `frontend/src/components/crm/AttributionStrip.tsx` — Task 12
- `frontend/src/components/crm/AddToListDrawer.tsx` — Task 13
- `frontend/src/components/crm/CreateDealDrawer.tsx` — Task 14
- `frontend/src/components/crm/QuickActionBar.tsx` — Task 15
- `frontend/src/pages/QueuePage.tsx` — Task 19

**Modified files:**
- `CLAUDE.md` — add `user_stars` to CRM-tables list (Task 3)
- `cleo/database/schema.py` — add new tables/columns to canonical schema (Task 2)
- `cleo/web/app.py` — register stars router (Task 4)
- `cleo/web/routes/lists.py` — scope/ownership + membership lookup (Task 5–6)
- `cleo/web/routes/activities.py` — entity-FK population, auto-engage, star auto-remove, `'property'` whitelist (Task 7)
- `cleo/web/routes/contacts.py` — synthetic engage activity + attribution endpoint (Tasks 8–9)
- `cleo/web/routes/groups.py` — synthetic engage activity + attribution endpoint (Tasks 8–9)
- `cleo/web/routes/properties.py` — attribution endpoint (Task 9)
- `frontend/src/types/index.ts` — add CRM types (Task 10)
- `frontend/src/pages/PropertyDetailPage.tsx` — wire QuickActionBar + AttributionStrip + ActivityFeed (Task 16)
- `frontend/src/pages/ContactDetailPage.tsx` — wire QuickActionBar + AttributionStrip + ActivityFeed (Task 17)
- `frontend/src/pages/GroupDetailPage.tsx` — wire QuickActionBar + AttributionStrip + ActivityFeed (Task 18)
- `frontend/src/App.tsx` — register `/queue` route (Task 19)
- Sidebar component (location resolved by reader's grep — see Task 24 Step 1) — add Queue entry

---

## Task 0: Branch and bootstrap

- [ ] **Step 1: Create the implementation branch from `main`**

```bash
git fetch origin
git checkout main
git pull origin main
git checkout -b feat/crm-daily-outreach-phase-1
```

- [ ] **Step 2: Verify Python and Node toolchains**

```bash
python --version  # expect 3.12+
cd frontend && node --version && npx tsc --version && cd ..
```

Expected: Python 3.12 or higher, Node 18+, TypeScript 5+. If any fails, stop and reconcile with the user.

- [ ] **Step 3: Run existing test suite to confirm baseline is green**

```bash
pytest tests/ -x --ignore=tests/test_discovery_v2_expansion.py 2>&1 | tail -20
```

Expected: all tests pass (or only known-unrelated failures). If anything in the CRM-touching files (`test_routes_contacts_tenures.py`, etc.) fails, fix the baseline first.

---

## Task 1: Migration 020 — write failing test

**Files:**
- Test: `tests/test_migration_020_crm_daily_outreach.py`

- [ ] **Step 1: Create the failing test file**

Create `tests/test_migration_020_crm_daily_outreach.py`:

```python
"""Tests for migration 020: CRM daily-outreach schema changes."""
import importlib
import sqlite3


def _bootstrap_pre_migration_db() -> sqlite3.Connection:
    """In-memory DB with the pre-migration schema for the tables we touch."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'editor',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE contacts (
            id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pool',
            last_engaged_date TEXT
        );
        CREATE TABLE groups (
            id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pool'
        );
        CREATE TABLE properties (
            id TEXT PRIMARY KEY,
            display_address TEXT NOT NULL
        );
        CREATE TABLE lists (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE list_members (
            list_id TEXT, member_type TEXT, member_id TEXT,
            added_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (list_id, member_type, member_id)
        );
        CREATE TABLE sell_opportunities (
            id TEXT PRIMARY KEY, property_id TEXT,
            seller_contact_id TEXT, seller_group_id TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            last_activity_at TEXT, decay_days INTEGER DEFAULT 14,
            created_at TEXT, updated_at TEXT
        );
        CREATE TABLE buy_mandates (
            id TEXT PRIMARY KEY,
            contact_id TEXT, group_id TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            last_activity_at TEXT, decay_days INTEGER DEFAULT 14,
            created_at TEXT, updated_at TEXT
        );
        CREATE TABLE deals (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            stage TEXT NOT NULL DEFAULT 'long_shot',
            property_id TEXT, group_id TEXT,
            created_at TEXT, updated_at TEXT
        );
        CREATE TABLE activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            activity_type TEXT NOT NULL,
            outcome TEXT, summary TEXT, next_step TEXT,
            created_by TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        -- Seed: 2 users
        INSERT INTO users (id, username, password_hash, display_name) VALUES
            (1, 'brandon', 'x', 'Brandon'),
            (2, 'jamie',   'x', 'Jamie');

        -- Seed: 1 list (will be backfilled scope='shared')
        INSERT INTO lists (id, name) VALUES ('LIST_A', 'Existing List');

        -- Seed: contact, group, property, opp, mandate, deal for backfill
        INSERT INTO contacts (id, display_name) VALUES ('CON_1', 'Peter Vicano');
        INSERT INTO groups   (id, display_name) VALUES ('GRP_1', 'DH Management');
        INSERT INTO properties (id, display_address) VALUES ('PRO_1', '240 King George Rd');
        INSERT INTO sell_opportunities (id, property_id, seller_contact_id, seller_group_id)
            VALUES ('SOPP_1', 'PRO_1', 'CON_1', 'GRP_1');
        INSERT INTO buy_mandates (id, contact_id, group_id)
            VALUES ('BM_1', 'CON_1', 'GRP_1');
        INSERT INTO deals (id, name, property_id, group_id)
            VALUES ('DEAL_1', 'Test Deal', 'PRO_1', 'GRP_1');

        -- Seed activities of every entity_type so we can verify backfill
        INSERT INTO activities (entity_type, entity_id, activity_type, created_by, created_at) VALUES
            ('contact',           'CON_1', 'note', 'brandon', '2024-01-01 10:00:00'),
            ('group',             'GRP_1', 'note', 'brandon', '2024-02-01 10:00:00'),
            ('sell_opportunity',  'SOPP_1','note', 'brandon', '2024-03-01 10:00:00'),
            ('buy_mandate',       'BM_1',  'note', 'brandon', '2024-04-01 10:00:00'),
            ('deal',              'DEAL_1','note', 'brandon', '2024-05-01 10:00:00');
    """)
    conn.commit()
    return conn


def _run_migration(conn: sqlite3.Connection) -> None:
    mod = importlib.import_module("cleo.database.migrations.020_crm_daily_outreach")
    mod.migrate(conn)


def test_user_stars_table_created():
    conn = _bootstrap_pre_migration_db()
    _run_migration(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(user_stars)").fetchall()}
    assert {"user_id", "entity_type", "entity_id", "starred_at"} <= cols
    idx = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='user_stars'"
    )}
    assert "idx_user_stars_user" in idx
    assert "idx_user_stars_entity" in idx
    conn.close()


def test_lists_scope_and_owner_added_with_backfill():
    conn = _bootstrap_pre_migration_db()
    _run_migration(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(lists)").fetchall()}
    assert "owner_user_id" in cols
    assert "scope" in cols
    # Existing row backfilled to 'shared' (since owner_user_id is NULL)
    row = conn.execute("SELECT scope, owner_user_id FROM lists WHERE id='LIST_A'").fetchone()
    assert row[0] == "shared"
    assert row[1] is None
    conn.close()


def test_activities_columns_added_and_backfilled():
    conn = _bootstrap_pre_migration_db()
    _run_migration(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(activities)").fetchall()}
    for col in ("created_by_user_id", "source", "external_id", "happened_at",
                "contact_id", "property_id", "group_id"):
        assert col in cols, f"missing column {col}"

    # Direct primary-entity backfill
    row = conn.execute("SELECT contact_id FROM activities WHERE entity_type='contact'").fetchone()
    assert row["contact_id"] == "CON_1"
    row = conn.execute("SELECT group_id FROM activities WHERE entity_type='group'").fetchone()
    assert row["group_id"] == "GRP_1"

    # Parent-record backfill: sell_opp → contact + group + property
    row = conn.execute(
        "SELECT contact_id, group_id, property_id FROM activities WHERE entity_type='sell_opportunity'"
    ).fetchone()
    assert row["contact_id"] == "CON_1"
    assert row["group_id"]   == "GRP_1"
    assert row["property_id"] == "PRO_1"

    # buy_mandate → contact + group (no property)
    row = conn.execute(
        "SELECT contact_id, group_id, property_id FROM activities WHERE entity_type='buy_mandate'"
    ).fetchone()
    assert row["contact_id"] == "CON_1"
    assert row["group_id"]   == "GRP_1"
    assert row["property_id"] is None

    # deal → property + group (no contact)
    row = conn.execute(
        "SELECT contact_id, group_id, property_id FROM activities WHERE entity_type='deal'"
    ).fetchone()
    assert row["contact_id"] is None
    assert row["group_id"]   == "GRP_1"
    assert row["property_id"] == "PRO_1"

    # happened_at backfilled from created_at
    rows = conn.execute("SELECT happened_at, created_at FROM activities").fetchall()
    for r in rows:
        assert r["happened_at"] == r["created_at"]

    # source default 'manual'
    rows = conn.execute("SELECT source FROM activities").fetchall()
    for r in rows:
        assert r["source"] == "manual"
    conn.close()


def test_activities_indexes_created():
    conn = _bootstrap_pre_migration_db()
    _run_migration(conn)
    idx = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='activities'"
    )}
    for expected in ("idx_activities_contact", "idx_activities_property",
                     "idx_activities_group", "idx_activities_user", "idx_activities_dedupe"):
        assert expected in idx, f"missing index {expected}"
    conn.close()


def test_migration_idempotent():
    conn = _bootstrap_pre_migration_db()
    _run_migration(conn)
    _run_migration(conn)  # second run must not error
    conn.close()
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
pytest tests/test_migration_020_crm_daily_outreach.py -v
```

Expected: ALL fail with `ModuleNotFoundError: No module named 'cleo.database.migrations.020_crm_daily_outreach'`.

---

## Task 2: Migration 020 — implement schema changes

**Files:**
- Create: `cleo/database/migrations/020_crm_daily_outreach.py`
- Modify: `cleo/database/schema.py` (canonical schema kept in sync)

- [ ] **Step 1: Implement the migration**

Create `cleo/database/migrations/020_crm_daily_outreach.py`:

```python
"""
Migration 020: CRM daily-outreach foundations.

Adds:
- user_stars table (per-user favourites/queue)
- lists.owner_user_id + lists.scope (personal/shared)
- activities.created_by_user_id (FK), source, external_id, happened_at
- activities.contact_id / property_id / group_id (multi-entity FKs)
- Indexes on the new activity FK columns and (source, external_id) for dedupe
- Backfill: existing lists -> scope='shared'; existing activities ->
  populate FKs from primary entity_type/entity_id, deriving from parent
  records for sell_opportunity / buy_mandate / deal types.

Idempotent: rerunning is a no-op (uses IF NOT EXISTS / column-exists guards).
"""
from __future__ import annotations
import sqlite3


def _column_exists(conn: sqlite3.Connection, table: str, col: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == col for r in rows)


def _add_column_if_missing(conn: sqlite3.Connection, table: str, col_def: str) -> None:
    """col_def is like 'scope TEXT NOT NULL DEFAULT \\'personal\\''"""
    col_name = col_def.split()[0]
    if not _column_exists(conn, table, col_name):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")


def migrate(conn: sqlite3.Connection) -> None:
    print("Migration 020: CRM daily-outreach schema...")

    # 1. user_stars table
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS user_stars (
            user_id      INTEGER NOT NULL REFERENCES users(id),
            entity_type  TEXT    NOT NULL CHECK(entity_type IN ('contact','property','group')),
            entity_id    TEXT    NOT NULL,
            starred_at   TEXT    DEFAULT (datetime('now')),
            PRIMARY KEY (user_id, entity_type, entity_id)
        );
        CREATE INDEX IF NOT EXISTS idx_user_stars_user   ON user_stars(user_id);
        CREATE INDEX IF NOT EXISTS idx_user_stars_entity ON user_stars(entity_type, entity_id);
    """)

    # 2. lists scope + owner
    _add_column_if_missing(conn, "lists", "owner_user_id INTEGER REFERENCES users(id)")
    _add_column_if_missing(conn, "lists", "scope TEXT NOT NULL DEFAULT 'personal'")
    # Backfill: pre-existing lists were team-shared in the pre-scope model
    conn.execute("UPDATE lists SET scope = 'shared' WHERE owner_user_id IS NULL AND scope = 'personal'")

    # 3. activities new columns
    _add_column_if_missing(conn, "activities", "created_by_user_id INTEGER REFERENCES users(id)")
    _add_column_if_missing(conn, "activities", "source TEXT NOT NULL DEFAULT 'manual'")
    _add_column_if_missing(conn, "activities", "external_id TEXT")
    _add_column_if_missing(conn, "activities", "happened_at TEXT")
    _add_column_if_missing(conn, "activities", "contact_id  TEXT REFERENCES contacts(id)")
    _add_column_if_missing(conn, "activities", "property_id TEXT REFERENCES properties(id)")
    _add_column_if_missing(conn, "activities", "group_id    TEXT REFERENCES groups(id)")

    # 4. activities backfill — happened_at, primary FKs
    conn.execute("UPDATE activities SET happened_at = created_at WHERE happened_at IS NULL")
    conn.execute("UPDATE activities SET contact_id  = entity_id WHERE entity_type='contact'  AND contact_id  IS NULL")
    conn.execute("UPDATE activities SET group_id    = entity_id WHERE entity_type='group'    AND group_id    IS NULL")
    # No 'property' rows pre-migration (route blocked it)

    # 5. activities backfill — parent-record FKs for sell_opp / buy_mandate / deal
    conn.execute("""
        UPDATE activities SET
            contact_id  = COALESCE(contact_id,  (SELECT seller_contact_id FROM sell_opportunities WHERE id = activities.entity_id)),
            group_id    = COALESCE(group_id,    (SELECT seller_group_id   FROM sell_opportunities WHERE id = activities.entity_id)),
            property_id = COALESCE(property_id, (SELECT property_id       FROM sell_opportunities WHERE id = activities.entity_id))
        WHERE entity_type = 'sell_opportunity'
    """)
    conn.execute("""
        UPDATE activities SET
            contact_id = COALESCE(contact_id, (SELECT contact_id FROM buy_mandates WHERE id = activities.entity_id)),
            group_id   = COALESCE(group_id,   (SELECT group_id   FROM buy_mandates WHERE id = activities.entity_id))
        WHERE entity_type = 'buy_mandate'
    """)
    conn.execute("""
        UPDATE activities SET
            property_id = COALESCE(property_id, (SELECT property_id FROM deals WHERE id = activities.entity_id)),
            group_id    = COALESCE(group_id,    (SELECT group_id   FROM deals WHERE id = activities.entity_id))
        WHERE entity_type = 'deal'
    """)

    # 6. activities indexes
    conn.executescript("""
        CREATE INDEX IF NOT EXISTS idx_activities_contact  ON activities(contact_id);
        CREATE INDEX IF NOT EXISTS idx_activities_property ON activities(property_id);
        CREATE INDEX IF NOT EXISTS idx_activities_group    ON activities(group_id);
        CREATE INDEX IF NOT EXISTS idx_activities_user     ON activities(created_by_user_id);
        CREATE INDEX IF NOT EXISTS idx_activities_dedupe   ON activities(source, external_id);
    """)

    conn.commit()
    print("Migration 020: done.")


if __name__ == "__main__":
    from cleo.database.connection import get_connection
    conn = get_connection()
    migrate(conn)
    conn.close()
```

- [ ] **Step 2: Run the test to verify it passes**

```bash
pytest tests/test_migration_020_crm_daily_outreach.py -v
```

Expected: all 5 tests pass.

- [ ] **Step 3: Update `cleo/database/schema.py` so the canonical schema mirrors the migration**

Find the CRM_TABLES section in `cleo/database/schema.py`. After the existing `lists` definition (around line 412), add `user_stars` and update `lists` and `activities` to include the new columns. The schema is loaded fresh on a brand-new DB; the migration handles existing DBs.

Modify the `lists` `CREATE TABLE` block (around line 406) to:

```sql
CREATE TABLE IF NOT EXISTS lists (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT,
    owner_user_id   INTEGER REFERENCES users(id),
    scope           TEXT NOT NULL DEFAULT 'personal',
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);
```

Add immediately after the `list_members` block (around line 420):

```sql
CREATE TABLE IF NOT EXISTS user_stars (
    user_id      INTEGER NOT NULL REFERENCES users(id),
    entity_type  TEXT    NOT NULL CHECK(entity_type IN ('contact','property','group')),
    entity_id    TEXT    NOT NULL,
    starred_at   TEXT    DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, entity_type, entity_id)
);
CREATE INDEX IF NOT EXISTS idx_user_stars_user   ON user_stars(user_id);
CREATE INDEX IF NOT EXISTS idx_user_stars_entity ON user_stars(entity_type, entity_id);
```

Modify the `activities` `CREATE TABLE` block (around line 582) to:

```sql
CREATE TABLE IF NOT EXISTS activities (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type         TEXT NOT NULL,
    entity_id           TEXT NOT NULL,
    activity_type       TEXT NOT NULL,
    outcome             TEXT,
    summary             TEXT,
    next_step           TEXT,
    created_by          TEXT,
    created_by_user_id  INTEGER REFERENCES users(id),
    source              TEXT NOT NULL DEFAULT 'manual',
    external_id         TEXT,
    happened_at         TEXT,
    contact_id          TEXT REFERENCES contacts(id),
    property_id         TEXT REFERENCES properties(id),
    group_id            TEXT REFERENCES groups(id),
    created_at          TEXT DEFAULT (datetime('now'))
);
```

Add the new indexes after the existing activities indexes:

```sql
CREATE INDEX IF NOT EXISTS idx_activities_contact  ON activities(contact_id);
CREATE INDEX IF NOT EXISTS idx_activities_property ON activities(property_id);
CREATE INDEX IF NOT EXISTS idx_activities_group    ON activities(group_id);
CREATE INDEX IF NOT EXISTS idx_activities_user     ON activities(created_by_user_id);
CREATE INDEX IF NOT EXISTS idx_activities_dedupe   ON activities(source, external_id);
```

- [ ] **Step 4: Run the migration against the dev DB**

```bash
python -m cleo.database.migrations.020_crm_daily_outreach
```

Expected output: `Migration 020: CRM daily-outreach schema...` then `Migration 020: done.`

Then verify in sqlite:

```bash
sqlite3 data/cleo.db ".schema user_stars"
sqlite3 data/cleo.db "PRAGMA table_info(activities)" | grep -E "contact_id|property_id|group_id|created_by_user_id|source|happened_at"
```

Expected: see the new columns.

- [ ] **Step 5: Commit**

```bash
git add cleo/database/migrations/020_crm_daily_outreach.py cleo/database/schema.py tests/test_migration_020_crm_daily_outreach.py
git commit -m "$(cat <<'EOF'
feat(db): migration 020 — CRM daily-outreach schema

Adds user_stars table, lists.scope/owner_user_id, and the multi-entity
FK + audit columns (created_by_user_id, source, external_id,
happened_at, contact_id, property_id, group_id) on activities.
Backfills existing lists as 'shared' and populates activity FKs from
primary entity_type or parent records for sell_opp/buy_mandate/deal.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Update CLAUDE.md CRM-tables list

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add `user_stars` to the CRM tables list**

Find the line in `CLAUDE.md` that begins:
```
**CRM tables** (persistent, NEVER rebuilt or truncated):
deals, lists, list_members, group_contacts, contact_notes, group_notes,
```

Append `user_stars` to the list. The full block should read:

```
**CRM tables** (persistent, NEVER rebuilt or truncated):
deals, lists, list_members, group_contacts, contact_notes, group_notes,
sell_opportunities, buy_mandates, activities, property_enrichment,
brand_overrides, user_brand_favorites, group_overrides, group_field_overrides,
contact_field_overrides, contact_work_history, group_merges,
labeling_sessions, labeling_verdicts, labeling_links, labeling_seeds,
labeling_reviewed_index, user_stars
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): add user_stars to CRM tables list

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Stars router — write failing test

**Files:**
- Test: `tests/test_routes_stars.py`

- [ ] **Step 1: Create the failing test file**

Create `tests/test_routes_stars.py`:

```python
"""Tests for /api/stars router."""
import sqlite3
import pytest
from fastapi.testclient import TestClient


def _seeded_db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT, password_hash TEXT, display_name TEXT, role TEXT,
            created_at TEXT
        );
        CREATE TABLE contacts (
            id TEXT PRIMARY KEY, display_name TEXT, company_name TEXT,
            status TEXT NOT NULL DEFAULT 'pool'
        );
        CREATE TABLE properties (
            id TEXT PRIMARY KEY, display_address TEXT, city TEXT
        );
        CREATE TABLE groups (
            id TEXT PRIMARY KEY, display_name TEXT,
            property_count INTEGER DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pool'
        );
        CREATE TABLE user_stars (
            user_id INTEGER NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id   TEXT NOT NULL,
            starred_at  TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (user_id, entity_type, entity_id)
        );
        CREATE TABLE activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT, entity_id TEXT,
            activity_type TEXT, outcome TEXT, summary TEXT, next_step TEXT,
            created_by TEXT, created_by_user_id INTEGER,
            source TEXT, external_id TEXT,
            happened_at TEXT, contact_id TEXT, property_id TEXT, group_id TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, action TEXT, entity_type TEXT, entity_id TEXT,
            details TEXT, created_at TEXT DEFAULT (datetime('now'))
        );
        INSERT INTO users (id, username, display_name, password_hash, role)
            VALUES (1, 'brandon', 'Brandon', 'x', 'editor'),
                   (2, 'jamie',   'Jamie',   'x', 'editor');
        INSERT INTO contacts (id, display_name, company_name)
            VALUES ('CON_1', 'Peter Vicano', 'DH Management');
        INSERT INTO properties (id, display_address, city)
            VALUES ('PRO_1', '240 King George Rd', 'Brantford');
        INSERT INTO groups (id, display_name, property_count)
            VALUES ('GRP_1', 'DH Management', 12);
    """)
    conn.commit()
    return conn


@pytest.fixture
def client_brandon():
    from cleo.web.app import app
    from cleo.web import deps
    conn = _seeded_db()

    def _get_db_override():
        yield conn
    app.dependency_overrides[deps.get_db] = _get_db_override
    app.dependency_overrides[deps.get_current_user] = lambda: {
        "sub": 1, "username": "brandon", "display_name": "Brandon", "role": "editor"
    }
    yield TestClient(app), conn
    app.dependency_overrides.clear()
    conn.close()


@pytest.fixture
def client_jamie():
    from cleo.web.app import app
    from cleo.web import deps
    conn = _seeded_db()

    def _get_db_override():
        yield conn
    app.dependency_overrides[deps.get_db] = _get_db_override
    app.dependency_overrides[deps.get_current_user] = lambda: {
        "sub": 2, "username": "jamie", "display_name": "Jamie", "role": "editor"
    }
    yield TestClient(app), conn
    app.dependency_overrides.clear()
    conn.close()


def test_create_star(client_brandon):
    client, conn = client_brandon
    resp = client.post("/api/stars", json={"entity_type": "contact", "entity_id": "CON_1"})
    assert resp.status_code == 200, resp.text
    rows = conn.execute("SELECT * FROM user_stars WHERE user_id=1").fetchall()
    assert len(rows) == 1
    assert rows[0]["entity_id"] == "CON_1"


def test_create_star_idempotent(client_brandon):
    client, conn = client_brandon
    client.post("/api/stars", json={"entity_type": "contact", "entity_id": "CON_1"})
    resp = client.post("/api/stars", json={"entity_type": "contact", "entity_id": "CON_1"})
    assert resp.status_code == 200
    rows = conn.execute("SELECT * FROM user_stars WHERE user_id=1").fetchall()
    assert len(rows) == 1


def test_create_star_invalid_entity_type(client_brandon):
    client, _ = client_brandon
    resp = client.post("/api/stars", json={"entity_type": "transaction", "entity_id": "X"})
    assert resp.status_code == 400


def test_delete_star(client_brandon):
    client, conn = client_brandon
    client.post("/api/stars", json={"entity_type": "property", "entity_id": "PRO_1"})
    resp = client.delete("/api/stars/property/PRO_1")
    assert resp.status_code == 200
    rows = conn.execute("SELECT * FROM user_stars").fetchall()
    assert len(rows) == 0


def test_check_star_returns_state(client_brandon):
    client, _ = client_brandon
    resp = client.get("/api/stars/check", params={"entity_type": "contact", "entity_id": "CON_1"})
    assert resp.json() == {"starred": False}
    client.post("/api/stars", json={"entity_type": "contact", "entity_id": "CON_1"})
    resp = client.get("/api/stars/check", params={"entity_type": "contact", "entity_id": "CON_1"})
    assert resp.json() == {"starred": True}


def test_list_stars_returns_only_my_stars(client_brandon, client_jamie):
    bclient, bconn = client_brandon
    bclient.post("/api/stars", json={"entity_type": "contact", "entity_id": "CON_1"})
    # Manually insert Jamie's star (different DB connection, so just verify API isolation)
    jclient, jconn = client_jamie
    jclient.post("/api/stars", json={"entity_type": "property", "entity_id": "PRO_1"})

    bresp = bclient.get("/api/stars")
    bbody = bresp.json()
    assert len(bbody) == 1
    assert bbody[0]["entity_id"] == "CON_1"
    assert bbody[0]["entity_type"] == "contact"

    jresp = jclient.get("/api/stars")
    jbody = jresp.json()
    assert len(jbody) == 1
    assert jbody[0]["entity_id"] == "PRO_1"


def test_list_stars_enriched_with_name_and_detail(client_brandon):
    client, _ = client_brandon
    client.post("/api/stars", json={"entity_type": "contact", "entity_id": "CON_1"})
    client.post("/api/stars", json={"entity_type": "property", "entity_id": "PRO_1"})
    client.post("/api/stars", json={"entity_type": "group", "entity_id": "GRP_1"})
    body = client.get("/api/stars").json()
    by_type = {r["entity_type"]: r for r in body}
    assert by_type["contact"]["name"]   == "Peter Vicano"
    assert by_type["contact"]["detail"] == "DH Management"
    assert by_type["property"]["name"]  == "240 King George Rd"
    assert by_type["property"]["detail"] == "Brantford"
    assert by_type["group"]["name"]     == "DH Management"
    assert by_type["group"]["detail"]   == "12 properties"


def test_list_stars_team_activity_when_teammate_engaged_after_star(client_brandon):
    client, conn = client_brandon
    client.post("/api/stars", json={"entity_type": "contact", "entity_id": "CON_1"})
    # Jamie logs an activity AFTER Brandon's star — should surface as team_activity
    conn.execute(
        "INSERT INTO activities (entity_type, entity_id, activity_type, outcome, "
        "created_by, created_by_user_id, contact_id, happened_at) "
        "VALUES ('contact', 'CON_1', 'call', 'connected', 'Jamie', 2, 'CON_1', "
        "        datetime('now', '+1 hour'))"
    )
    conn.commit()
    body = client.get("/api/stars").json()
    assert body[0]["team_activity"] is not None
    assert body[0]["team_activity"]["by_user_name"] == "Jamie"
    assert body[0]["team_activity"]["activity_type"] == "call"


def test_list_stars_no_team_activity_for_my_own_activity(client_brandon):
    client, conn = client_brandon
    client.post("/api/stars", json={"entity_type": "contact", "entity_id": "CON_1"})
    conn.execute(
        "INSERT INTO activities (entity_type, entity_id, activity_type, "
        "created_by, created_by_user_id, contact_id, happened_at) "
        "VALUES ('contact', 'CON_1', 'note', 'Brandon', 1, 'CON_1', "
        "        datetime('now', '+1 hour'))"
    )
    conn.commit()
    body = client.get("/api/stars").json()
    assert body[0]["team_activity"] is None


def test_list_stars_no_team_activity_for_pre_star_history(client_brandon):
    client, conn = client_brandon
    # Jamie's activity BEFORE Brandon's star — must not count
    conn.execute(
        "INSERT INTO activities (entity_type, entity_id, activity_type, "
        "created_by, created_by_user_id, contact_id, happened_at) "
        "VALUES ('contact', 'CON_1', 'call', 'Jamie', 2, 'CON_1', "
        "        datetime('now', '-1 day'))"
    )
    conn.commit()
    client.post("/api/stars", json={"entity_type": "contact", "entity_id": "CON_1"})
    body = client.get("/api/stars").json()
    assert body[0]["team_activity"] is None


def test_list_stars_filter_by_entity_type(client_brandon):
    client, _ = client_brandon
    client.post("/api/stars", json={"entity_type": "contact", "entity_id": "CON_1"})
    client.post("/api/stars", json={"entity_type": "property", "entity_id": "PRO_1"})
    body = client.get("/api/stars", params={"entity_type": "property"}).json()
    assert len(body) == 1
    assert body[0]["entity_type"] == "property"
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
pytest tests/test_routes_stars.py -v 2>&1 | tail -30
```

Expected: all fail with 404 (route not found) — the `stars.py` router doesn't exist yet.

---

## Task 5: Stars router — implement and register

**Files:**
- Create: `cleo/web/routes/stars.py`
- Modify: `cleo/web/app.py`

- [ ] **Step 1: Implement the stars router**

Create `cleo/web/routes/stars.py`:

```python
"""
Stars API — per-user favourites/queue.

A star is a personal pointer to a contact, property, or group that the
current user wants to come back to. The /api/stars list payload powers
the Queue page; each row is enriched with display name, secondary
detail, and (when a teammate has engaged the entity *after* you starred
it) a team_activity object so you don't accidentally double-touch.
"""
import json
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from ..deps import get_db, get_current_user
from ..audit import log_action

router = APIRouter()

ALLOWED_ENTITY_TYPES = ("contact", "property", "group")


class StarCreate(BaseModel):
    entity_type: str
    entity_id: str


def _user_id(user) -> int:
    """JWT puts users.id in the 'sub' field (see cleo/web/auth.py:create_token)."""
    return int(user["sub"])


@router.post("")
def create_star(body: StarCreate, db=Depends(get_db), user=Depends(get_current_user)):
    if body.entity_type not in ALLOWED_ENTITY_TYPES:
        raise HTTPException(status_code=400, detail=f"entity_type must be one of {ALLOWED_ENTITY_TYPES}")
    me = _user_id(user)
    db.execute(
        "INSERT OR IGNORE INTO user_stars (user_id, entity_type, entity_id) VALUES (?, ?, ?)",
        (me, body.entity_type, body.entity_id),
    )
    log_action(db, user, "star.add", body.entity_type, body.entity_id, None)
    db.commit()
    return {"status": "starred"}


@router.delete("/{entity_type}/{entity_id}")
def delete_star(entity_type: str, entity_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    if entity_type not in ALLOWED_ENTITY_TYPES:
        raise HTTPException(status_code=400, detail=f"entity_type must be one of {ALLOWED_ENTITY_TYPES}")
    me = _user_id(user)
    db.execute(
        "DELETE FROM user_stars WHERE user_id=? AND entity_type=? AND entity_id=?",
        (me, entity_type, entity_id),
    )
    log_action(db, user, "star.remove", entity_type, entity_id, None)
    db.commit()
    return {"status": "unstarred"}


@router.get("/check")
def check_star(
    entity_type: str = Query(...),
    entity_id: str = Query(...),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    if entity_type not in ALLOWED_ENTITY_TYPES:
        raise HTTPException(status_code=400, detail=f"entity_type must be one of {ALLOWED_ENTITY_TYPES}")
    me = _user_id(user)
    row = db.execute(
        "SELECT 1 FROM user_stars WHERE user_id=? AND entity_type=? AND entity_id=?",
        (me, entity_type, entity_id),
    ).fetchone()
    return {"starred": row is not None}


@router.get("")
def list_stars(
    entity_type: Optional[str] = None,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    me = _user_id(user)
    if entity_type and entity_type not in ALLOWED_ENTITY_TYPES:
        raise HTTPException(status_code=400, detail=f"entity_type must be one of {ALLOWED_ENTITY_TYPES}")

    sql = "SELECT entity_type, entity_id, starred_at FROM user_stars WHERE user_id = ?"
    params = [me]
    if entity_type:
        sql += " AND entity_type = ?"
        params.append(entity_type)
    sql += " ORDER BY starred_at DESC"

    stars = db.execute(sql, params).fetchall()
    results = []
    for s in stars:
        item = {
            "user_id": me,
            "entity_type": s["entity_type"],
            "entity_id": s["entity_id"],
            "starred_at": s["starred_at"],
            "name": None,
            "detail": None,
            "team_activity": None,
        }
        # 1. Enrich with name + detail per entity type
        if s["entity_type"] == "contact":
            row = db.execute(
                "SELECT display_name, company_name FROM contacts WHERE id = ?",
                (s["entity_id"],),
            ).fetchone()
            if row:
                item["name"] = row["display_name"]
                item["detail"] = row["company_name"]
        elif s["entity_type"] == "property":
            row = db.execute(
                "SELECT display_address, city FROM properties WHERE id = ?",
                (s["entity_id"],),
            ).fetchone()
            if row:
                item["name"] = row["display_address"]
                item["detail"] = row["city"]
        elif s["entity_type"] == "group":
            row = db.execute(
                "SELECT display_name, property_count FROM groups WHERE id = ?",
                (s["entity_id"],),
            ).fetchone()
            if row:
                item["name"] = row["display_name"]
                item["detail"] = f"{row['property_count']} properties" if row["property_count"] is not None else None

        # 2. team_activity — only counts activities by another user that happened
        #    AFTER the star was placed. The FK column we look at depends on entity_type.
        fk_col = {"contact": "contact_id", "property": "property_id", "group": "group_id"}[s["entity_type"]]
        team_row = db.execute(
            f"""
            SELECT a.created_by_user_id AS by_user_id,
                   u.display_name AS by_user_name,
                   a.happened_at, a.activity_type, a.outcome
            FROM activities a
            JOIN users u ON u.id = a.created_by_user_id
            WHERE a.{fk_col} = ?
              AND a.created_by_user_id != ?
              AND a.happened_at > ?
            ORDER BY a.happened_at DESC
            LIMIT 1
            """,
            (s["entity_id"], me, s["starred_at"]),
        ).fetchone()
        if team_row:
            item["team_activity"] = {
                "by_user_id": team_row["by_user_id"],
                "by_user_name": team_row["by_user_name"],
                "happened_at": team_row["happened_at"],
                "activity_type": team_row["activity_type"],
                "outcome": team_row["outcome"],
            }

        results.append(item)

    return results
```

- [ ] **Step 2: Register the router in `cleo/web/app.py`**

Find the existing CRM router includes (search for `app.include_router(notes_router`). Add the import alongside the other CRM imports:

```python
from .routes.stars import router as stars_router
```

And add the include line right after `app.include_router(activities_router, ...)`:

```python
app.include_router(stars_router, prefix="/api/stars", tags=["stars"])
```

- [ ] **Step 3: Run the stars tests to verify they pass**

```bash
pytest tests/test_routes_stars.py -v 2>&1 | tail -30
```

Expected: all 11 tests pass.

- [ ] **Step 4: Commit**

```bash
git add cleo/web/routes/stars.py cleo/web/app.py tests/test_routes_stars.py
git commit -m "$(cat <<'EOF'
feat(api): /api/stars router for per-user favourites/queue

CRUD plus a queue-payload endpoint that enriches each star with
display name, secondary detail (city/employer/property count), and a
team_activity object surfacing teammate engagement that happened
after the star was placed.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Lists scope/ownership — write failing test

**Files:**
- Test: `tests/test_routes_lists_scope.py`

- [ ] **Step 1: Create the failing test file**

Create `tests/test_routes_lists_scope.py`:

```python
"""Tests for lists scope (personal/shared) and ownership rules."""
import sqlite3
import pytest
from fastapi.testclient import TestClient


def _seeded_db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT, password_hash TEXT, display_name TEXT, role TEXT,
            created_at TEXT
        );
        CREATE TABLE lists (
            id TEXT PRIMARY KEY, name TEXT, description TEXT,
            owner_user_id INTEGER, scope TEXT NOT NULL DEFAULT 'personal',
            created_at TEXT, updated_at TEXT
        );
        CREATE TABLE list_members (
            list_id TEXT, member_type TEXT, member_id TEXT,
            added_at TEXT,
            PRIMARY KEY (list_id, member_type, member_id)
        );
        CREATE TABLE contacts (id TEXT PRIMARY KEY, display_name TEXT, company_name TEXT);
        CREATE TABLE properties (id TEXT PRIMARY KEY, display_address TEXT, city TEXT);
        CREATE TABLE groups (id TEXT PRIMARY KEY, display_name TEXT, property_count INTEGER DEFAULT 0);
        CREATE TABLE transactions (source_id TEXT PRIMARY KEY, display_address TEXT, city TEXT);
        CREATE TABLE audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, action TEXT, entity_type TEXT, entity_id TEXT,
            details TEXT, created_at TEXT
        );
        INSERT INTO users (id, username, display_name, password_hash, role)
            VALUES (1, 'brandon', 'Brandon', 'x', 'editor'),
                   (2, 'jamie',   'Jamie',   'x', 'editor');
        INSERT INTO contacts (id, display_name) VALUES ('CON_1', 'Peter Vicano');
    """)
    conn.commit()
    return conn


def _client(conn, sub):
    from cleo.web.app import app
    from cleo.web import deps

    def _get_db():
        yield conn
    app.dependency_overrides[deps.get_db] = _get_db
    app.dependency_overrides[deps.get_current_user] = lambda: {
        "sub": sub, "username": "u", "display_name": "U", "role": "editor"
    }
    return TestClient(app)


@pytest.fixture
def shared_conn():
    conn = _seeded_db()
    yield conn
    from cleo.web.app import app
    app.dependency_overrides.clear()
    conn.close()


def test_create_list_defaults_to_personal_with_owner(shared_conn):
    bclient = _client(shared_conn, sub=1)
    resp = bclient.post("/api/lists", json={"name": "Brandon's leads"})
    assert resp.status_code == 200
    list_id = resp.json()["id"]
    row = shared_conn.execute(
        "SELECT scope, owner_user_id FROM lists WHERE id=?", (list_id,)
    ).fetchone()
    assert row["scope"] == "personal"
    assert row["owner_user_id"] == 1


def test_create_list_can_be_shared(shared_conn):
    bclient = _client(shared_conn, sub=1)
    resp = bclient.post("/api/lists", json={"name": "Team Q3", "scope": "shared"})
    list_id = resp.json()["id"]
    row = shared_conn.execute(
        "SELECT scope, owner_user_id FROM lists WHERE id=?", (list_id,)
    ).fetchone()
    assert row["scope"] == "shared"
    assert row["owner_user_id"] == 1


def test_personal_list_hidden_from_other_user_in_browse(shared_conn):
    bclient = _client(shared_conn, sub=1)
    bclient.post("/api/lists", json={"name": "Brandon's secret list"})

    jclient = _client(shared_conn, sub=2)
    jbody = jclient.get("/api/lists").json()
    assert len(jbody) == 0  # Jamie sees nothing
    bbody = bclient.get("/api/lists").json()
    assert len(bbody) == 1  # Brandon sees his own


def test_shared_list_visible_to_all(shared_conn):
    bclient = _client(shared_conn, sub=1)
    bclient.post("/api/lists", json={"name": "Team Q3", "scope": "shared"})
    jclient = _client(shared_conn, sub=2)
    body = jclient.get("/api/lists").json()
    assert len(body) == 1
    assert body[0]["name"] == "Team Q3"


def test_get_personal_list_404s_for_other_user(shared_conn):
    bclient = _client(shared_conn, sub=1)
    list_id = bclient.post("/api/lists", json={"name": "Brandon private"}).json()["id"]
    jclient = _client(shared_conn, sub=2)
    resp = jclient.get(f"/api/lists/{list_id}")
    assert resp.status_code == 404


def test_owner_can_rename_list(shared_conn):
    bclient = _client(shared_conn, sub=1)
    list_id = bclient.post("/api/lists", json={"name": "Old", "scope": "shared"}).json()["id"]
    resp = bclient.patch(f"/api/lists/{list_id}", json={"name": "New"})
    assert resp.status_code == 200
    name = shared_conn.execute("SELECT name FROM lists WHERE id=?", (list_id,)).fetchone()["name"]
    assert name == "New"


def test_non_owner_cannot_rename_shared_list(shared_conn):
    bclient = _client(shared_conn, sub=1)
    list_id = bclient.post("/api/lists", json={"name": "Old", "scope": "shared"}).json()["id"]
    jclient = _client(shared_conn, sub=2)
    resp = jclient.patch(f"/api/lists/{list_id}", json={"name": "Hacked"})
    assert resp.status_code == 403


def test_owner_can_delete_list(shared_conn):
    bclient = _client(shared_conn, sub=1)
    list_id = bclient.post("/api/lists", json={"name": "X", "scope": "shared"}).json()["id"]
    resp = bclient.delete(f"/api/lists/{list_id}")
    assert resp.status_code == 200


def test_non_owner_cannot_delete_shared_list(shared_conn):
    bclient = _client(shared_conn, sub=1)
    list_id = bclient.post("/api/lists", json={"name": "X", "scope": "shared"}).json()["id"]
    jclient = _client(shared_conn, sub=2)
    resp = jclient.delete(f"/api/lists/{list_id}")
    assert resp.status_code == 403


def test_anyone_can_add_members_to_shared_list(shared_conn):
    bclient = _client(shared_conn, sub=1)
    list_id = bclient.post("/api/lists", json={"name": "Team", "scope": "shared"}).json()["id"]
    jclient = _client(shared_conn, sub=2)
    resp = jclient.post(
        f"/api/lists/{list_id}/members",
        json={"member_type": "contact", "member_id": "CON_1"},
    )
    assert resp.status_code == 200


def test_non_owner_cannot_add_member_to_personal_list(shared_conn):
    bclient = _client(shared_conn, sub=1)
    list_id = bclient.post("/api/lists", json={"name": "Brandon private"}).json()["id"]
    jclient = _client(shared_conn, sub=2)
    resp = jclient.post(
        f"/api/lists/{list_id}/members",
        json={"member_type": "contact", "member_id": "CON_1"},
    )
    assert resp.status_code == 404  # truly hidden — same response as if the list didn't exist


def test_membership_lookup_returns_lists_containing_member(shared_conn):
    bclient = _client(shared_conn, sub=1)
    a = bclient.post("/api/lists", json={"name": "List A"}).json()["id"]
    b = bclient.post("/api/lists", json={"name": "List B"}).json()["id"]
    bclient.post(f"/api/lists/{a}/members", json={"member_type": "contact", "member_id": "CON_1"})
    resp = bclient.get("/api/lists/membership", params={"member_type": "contact", "member_id": "CON_1"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["list_id"] == a
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
pytest tests/test_routes_lists_scope.py -v 2>&1 | tail -40
```

Expected: most tests fail (existing route doesn't enforce scope/ownership; `/membership` endpoint doesn't exist).

---

## Task 7: Lists scope/ownership — implement

**Files:**
- Modify: `cleo/web/routes/lists.py`

- [ ] **Step 1: Rewrite `cleo/web/routes/lists.py`**

Replace the entire file with:

```python
"""
Lists API — prospecting lists with scope (personal/shared) and ownership.

Personal lists are visible only to their owner — they 404 to other users.
Shared lists are visible to everyone; member adds/removes are team-editable;
metadata edits (rename, description, delete) are owner-only.
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from ..deps import get_db, get_current_user

router = APIRouter()


class ListCreate(BaseModel):
    name: str
    description: Optional[str] = None
    scope: Optional[str] = "personal"


class ListUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class MemberAdd(BaseModel):
    member_type: str
    member_id: str


def _user_id(user) -> int:
    return int(user["sub"])


def _list_for_user_or_404(db, list_id: str, me: int):
    """Fetch a list row the user is allowed to see; 404 otherwise."""
    row = db.execute(
        "SELECT * FROM lists WHERE id = ? AND (scope='shared' OR owner_user_id = ?)",
        (list_id, me),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="List not found")
    return row


@router.get("")
def browse_lists(db=Depends(get_db), user=Depends(get_current_user)):
    me = _user_id(user)
    rows = db.execute(
        "SELECT * FROM lists WHERE scope='shared' OR owner_user_id = ? ORDER BY updated_at DESC",
        (me,),
    ).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        counts = db.execute(
            "SELECT member_type, COUNT(*) as count FROM list_members "
            "WHERE list_id = ? GROUP BY member_type",
            (d["id"],),
        ).fetchall()
        d["member_counts"] = {c["member_type"]: c["count"] for c in counts}
        d["total_members"] = sum(c["count"] for c in counts)
        # Owner display name
        if d.get("owner_user_id"):
            owner_row = db.execute(
                "SELECT display_name FROM users WHERE id = ?",
                (d["owner_user_id"],),
            ).fetchone()
            d["owner_name"] = owner_row["display_name"] if owner_row else None
        else:
            d["owner_name"] = None
        results.append(d)
    return results


@router.get("/membership")
def lists_containing_member(
    member_type: str = Query(...),
    member_id: str = Query(...),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """For the AddToListDrawer pre-checked state: which of the user's accessible
    lists already contain this member?"""
    me = _user_id(user)
    rows = db.execute(
        """
        SELECT l.id AS list_id, l.name AS list_name, l.scope
        FROM lists l
        JOIN list_members lm ON lm.list_id = l.id
        WHERE lm.member_type = ? AND lm.member_id = ?
          AND (l.scope = 'shared' OR l.owner_user_id = ?)
        """,
        (member_type, member_id, me),
    ).fetchall()
    return [dict(r) for r in rows]


@router.get("/{list_id}")
def list_detail(list_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    me = _user_id(user)
    lst = _list_for_user_or_404(db, list_id, me)
    result = dict(lst)
    members_raw = db.execute(
        "SELECT member_type, member_id, added_at FROM list_members "
        "WHERE list_id = ? ORDER BY added_at DESC",
        (list_id,),
    ).fetchall()
    members = []
    for m in members_raw:
        entry = dict(m)
        if m["member_type"] == "property":
            row = db.execute("SELECT display_address, city FROM properties WHERE id = ?", (m["member_id"],)).fetchone()
            if row:
                entry["name"] = row["display_address"]
                entry["detail"] = row["city"]
        elif m["member_type"] == "contact":
            row = db.execute("SELECT display_name, company_name FROM contacts WHERE id = ?", (m["member_id"],)).fetchone()
            if row:
                entry["name"] = row["display_name"]
                entry["detail"] = row["company_name"]
        elif m["member_type"] == "group":
            row = db.execute("SELECT display_name, property_count FROM groups WHERE id = ?", (m["member_id"],)).fetchone()
            if row:
                entry["name"] = row["display_name"]
                entry["detail"] = f"{row['property_count']} properties" if row["property_count"] is not None else None
        elif m["member_type"] == "transaction":
            row = db.execute("SELECT display_address, city FROM transactions WHERE source_id = ?", (m["member_id"],)).fetchone()
            if row:
                entry["name"] = row["display_address"]
                entry["detail"] = row["city"]
        members.append(entry)
    result["members"] = members
    return result


@router.post("")
def create_list(body: ListCreate, db=Depends(get_db), user=Depends(get_current_user)):
    me = _user_id(user)
    scope = body.scope if body.scope in ("personal", "shared") else "personal"
    list_id = f"LIST_{uuid.uuid4().hex[:8].upper()}"
    db.execute(
        "INSERT INTO lists (id, name, description, owner_user_id, scope) VALUES (?, ?, ?, ?, ?)",
        (list_id, body.name, body.description, me, scope),
    )
    db.commit()
    return {"id": list_id, "status": "created", "scope": scope}


@router.patch("/{list_id}")
def update_list(list_id: str, body: ListUpdate, db=Depends(get_db), user=Depends(get_current_user)):
    me = _user_id(user)
    row = _list_for_user_or_404(db, list_id, me)
    if row["owner_user_id"] != me:
        raise HTTPException(status_code=403, detail="Only the list owner can rename or describe a list")
    updates = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.description is not None:
        updates["description"] = body.description
    if updates:
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values())
        db.execute(
            f"UPDATE lists SET {set_clause}, updated_at = datetime('now') WHERE id = ?",
            values + [list_id],
        )
        db.commit()
    return {"id": list_id, "updated": list(updates.keys())}


@router.delete("/{list_id}")
def delete_list(list_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    me = _user_id(user)
    row = _list_for_user_or_404(db, list_id, me)
    if row["owner_user_id"] != me:
        raise HTTPException(status_code=403, detail="Only the list owner can delete a list")
    db.execute("DELETE FROM list_members WHERE list_id = ?", (list_id,))
    db.execute("DELETE FROM lists WHERE id = ?", (list_id,))
    db.commit()
    return {"id": list_id, "status": "deleted"}


@router.post("/{list_id}/members")
def add_member(list_id: str, body: MemberAdd, db=Depends(get_db), user=Depends(get_current_user)):
    me = _user_id(user)
    _list_for_user_or_404(db, list_id, me)  # 404 if hidden personal list
    if body.member_type not in ("property", "contact", "group", "transaction"):
        raise HTTPException(status_code=400, detail="Invalid member_type")
    db.execute(
        "INSERT OR IGNORE INTO list_members (list_id, member_type, member_id) VALUES (?, ?, ?)",
        (list_id, body.member_type, body.member_id),
    )
    db.execute("UPDATE lists SET updated_at = datetime('now') WHERE id = ?", (list_id,))
    db.commit()
    return {"status": "added"}


@router.delete("/{list_id}/members/{member_type}/{member_id}")
def remove_member(list_id: str, member_type: str, member_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    me = _user_id(user)
    _list_for_user_or_404(db, list_id, me)
    db.execute(
        "DELETE FROM list_members WHERE list_id=? AND member_type=? AND member_id=?",
        (list_id, member_type, member_id),
    )
    db.execute("UPDATE lists SET updated_at = datetime('now') WHERE id = ?", (list_id,))
    db.commit()
    return {"status": "removed"}
```

- [ ] **Step 2: Run the tests to verify they pass**

```bash
pytest tests/test_routes_lists_scope.py -v 2>&1 | tail -30
```

Expected: all 12 tests pass.

- [ ] **Step 3: Commit**

```bash
git add cleo/web/routes/lists.py tests/test_routes_lists_scope.py
git commit -m "$(cat <<'EOF'
feat(api): lists scope (personal/shared) and ownership rules

Personal lists are visible only to their owner; shared lists are
team-editable for members but metadata edits are owner-only. Adds
GET /api/lists/membership for the AddToListDrawer pre-check.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Activities upgrades — write failing test

**Files:**
- Test: `tests/test_routes_activities_phase1.py`

- [ ] **Step 1: Create the failing test file**

Create `tests/test_routes_activities_phase1.py`:

```python
"""Tests for Phase 1 activities upgrades:
- 'property' entity_type accepted
- created_by_user_id FK populated
- Primary entity FK auto-populated based on entity_type
- sell_opp / buy_mandate / deal entity types derive FKs from parent record
- Auto-engage flips contacts/groups status from pool→engaged
- Star auto-remove deletes the current user's star on referenced entities
- Manual engage idempotence preserved (no duplicate synthetic activity)
"""
import sqlite3
import pytest
from fastapi.testclient import TestClient


def _seeded_db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT, password_hash TEXT, display_name TEXT, role TEXT,
            created_at TEXT
        );
        CREATE TABLE contacts (
            id TEXT PRIMARY KEY, display_name TEXT,
            status TEXT NOT NULL DEFAULT 'pool',
            last_engaged_date TEXT
        );
        CREATE TABLE groups (
            id TEXT PRIMARY KEY, display_name TEXT,
            status TEXT NOT NULL DEFAULT 'pool'
        );
        CREATE TABLE properties (id TEXT PRIMARY KEY, display_address TEXT);
        CREATE TABLE sell_opportunities (
            id TEXT PRIMARY KEY, property_id TEXT,
            seller_contact_id TEXT, seller_group_id TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            last_activity_at TEXT, decay_days INTEGER DEFAULT 14,
            updated_at TEXT
        );
        CREATE TABLE buy_mandates (
            id TEXT PRIMARY KEY, contact_id TEXT, group_id TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            last_activity_at TEXT, decay_days INTEGER DEFAULT 14,
            updated_at TEXT
        );
        CREATE TABLE deals (
            id TEXT PRIMARY KEY, name TEXT, stage TEXT,
            property_id TEXT, group_id TEXT,
            updated_at TEXT
        );
        CREATE TABLE activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT, entity_id TEXT,
            activity_type TEXT, outcome TEXT, summary TEXT, next_step TEXT,
            created_by TEXT, created_by_user_id INTEGER,
            source TEXT NOT NULL DEFAULT 'manual',
            external_id TEXT, happened_at TEXT,
            contact_id TEXT, property_id TEXT, group_id TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE user_stars (
            user_id INTEGER NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id   TEXT NOT NULL,
            starred_at  TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (user_id, entity_type, entity_id)
        );
        CREATE TABLE audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, action TEXT, entity_type TEXT, entity_id TEXT,
            details TEXT, created_at TEXT
        );

        INSERT INTO users (id, username, display_name, password_hash, role)
            VALUES (1, 'brandon', 'Brandon', 'x', 'editor'),
                   (2, 'jamie',   'Jamie',   'x', 'editor');
        INSERT INTO contacts (id, display_name) VALUES ('CON_1', 'Peter Vicano');
        INSERT INTO groups   (id, display_name) VALUES ('GRP_1', 'DH Management');
        INSERT INTO properties (id, display_address) VALUES ('PRO_1', '240 King George Rd');
        INSERT INTO sell_opportunities (id, property_id, seller_contact_id, seller_group_id)
            VALUES ('SOPP_1', 'PRO_1', 'CON_1', 'GRP_1');
        INSERT INTO buy_mandates (id, contact_id, group_id) VALUES ('BM_1', 'CON_1', 'GRP_1');
        INSERT INTO deals (id, name, stage, property_id, group_id)
            VALUES ('DEAL_1', 'Test Deal', 'long_shot', 'PRO_1', 'GRP_1');
    """)
    conn.commit()
    return conn


def _client(conn, sub=1):
    from cleo.web.app import app
    from cleo.web import deps

    def _get_db():
        yield conn
    app.dependency_overrides[deps.get_db] = _get_db
    app.dependency_overrides[deps.get_current_user] = lambda: {
        "sub": sub, "username": "brandon" if sub == 1 else "jamie",
        "display_name": "Brandon" if sub == 1 else "Jamie", "role": "editor"
    }
    return TestClient(app)


@pytest.fixture
def conn():
    c = _seeded_db()
    yield c
    from cleo.web.app import app
    app.dependency_overrides.clear()
    c.close()


def test_property_entity_type_now_accepted(conn):
    client = _client(conn)
    resp = client.post("/api/activities", json={
        "entity_type": "property", "entity_id": "PRO_1",
        "activity_type": "note", "summary": "site visit"
    })
    assert resp.status_code == 200, resp.text


def test_contact_activity_populates_contact_id_fk(conn):
    client = _client(conn)
    client.post("/api/activities", json={
        "entity_type": "contact", "entity_id": "CON_1",
        "activity_type": "email", "outcome": "email_sent"
    })
    row = conn.execute(
        "SELECT contact_id, property_id, group_id FROM activities ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row["contact_id"] == "CON_1"
    assert row["property_id"] is None
    assert row["group_id"] is None


def test_property_activity_populates_property_id_fk(conn):
    client = _client(conn)
    client.post("/api/activities", json={
        "entity_type": "property", "entity_id": "PRO_1",
        "activity_type": "note"
    })
    row = conn.execute("SELECT contact_id, property_id, group_id FROM activities ORDER BY id DESC LIMIT 1").fetchone()
    assert row["property_id"] == "PRO_1"
    assert row["contact_id"] is None
    assert row["group_id"] is None


def test_group_activity_populates_group_id_fk(conn):
    client = _client(conn)
    client.post("/api/activities", json={
        "entity_type": "group", "entity_id": "GRP_1", "activity_type": "note"
    })
    row = conn.execute("SELECT contact_id, property_id, group_id FROM activities ORDER BY id DESC LIMIT 1").fetchone()
    assert row["group_id"] == "GRP_1"


def test_sell_opp_activity_derives_fks_from_parent(conn):
    client = _client(conn)
    client.post("/api/activities", json={
        "entity_type": "sell_opportunity", "entity_id": "SOPP_1",
        "activity_type": "call"
    })
    row = conn.execute("SELECT contact_id, property_id, group_id FROM activities ORDER BY id DESC LIMIT 1").fetchone()
    assert row["contact_id"] == "CON_1"
    assert row["property_id"] == "PRO_1"
    assert row["group_id"] == "GRP_1"


def test_buy_mandate_activity_derives_fks_from_parent(conn):
    client = _client(conn)
    client.post("/api/activities", json={
        "entity_type": "buy_mandate", "entity_id": "BM_1", "activity_type": "call"
    })
    row = conn.execute("SELECT contact_id, property_id, group_id FROM activities ORDER BY id DESC LIMIT 1").fetchone()
    assert row["contact_id"] == "CON_1"
    assert row["group_id"] == "GRP_1"
    assert row["property_id"] is None


def test_deal_activity_derives_fks_from_parent(conn):
    client = _client(conn)
    client.post("/api/activities", json={
        "entity_type": "deal", "entity_id": "DEAL_1", "activity_type": "note"
    })
    row = conn.execute("SELECT contact_id, property_id, group_id FROM activities ORDER BY id DESC LIMIT 1").fetchone()
    assert row["property_id"] == "PRO_1"
    assert row["group_id"] == "GRP_1"
    assert row["contact_id"] is None


def test_created_by_user_id_populated(conn):
    client = _client(conn, sub=2)
    client.post("/api/activities", json={
        "entity_type": "contact", "entity_id": "CON_1", "activity_type": "note"
    })
    row = conn.execute("SELECT created_by_user_id, created_by FROM activities ORDER BY id DESC LIMIT 1").fetchone()
    assert row["created_by_user_id"] == 2
    assert row["created_by"] in ("Jamie", "jamie")  # display_name preferred, fallback to username


def test_auto_engage_flips_contact_pool_to_engaged(conn):
    client = _client(conn)
    assert conn.execute("SELECT status FROM contacts WHERE id='CON_1'").fetchone()["status"] == "pool"
    client.post("/api/activities", json={
        "entity_type": "contact", "entity_id": "CON_1", "activity_type": "call"
    })
    status = conn.execute("SELECT status, last_engaged_date FROM contacts WHERE id='CON_1'").fetchone()
    assert status["status"] == "engaged"
    assert status["last_engaged_date"] is not None


def test_auto_engage_flips_group_pool_to_engaged(conn):
    client = _client(conn)
    assert conn.execute("SELECT status FROM groups WHERE id='GRP_1'").fetchone()["status"] == "pool"
    client.post("/api/activities", json={
        "entity_type": "group", "entity_id": "GRP_1", "activity_type": "note"
    })
    assert conn.execute("SELECT status FROM groups WHERE id='GRP_1'").fetchone()["status"] == "engaged"


def test_auto_engage_does_not_unflip_already_engaged(conn):
    conn.execute("UPDATE contacts SET status='engaged' WHERE id='CON_1'")
    conn.commit()
    client = _client(conn)
    client.post("/api/activities", json={
        "entity_type": "contact", "entity_id": "CON_1", "activity_type": "note"
    })
    assert conn.execute("SELECT status FROM contacts WHERE id='CON_1'").fetchone()["status"] == "engaged"


def test_star_auto_remove_on_own_activity(conn):
    client = _client(conn, sub=1)
    conn.execute("INSERT INTO user_stars (user_id, entity_type, entity_id) VALUES (1, 'contact', 'CON_1')")
    conn.commit()
    client.post("/api/activities", json={
        "entity_type": "contact", "entity_id": "CON_1", "activity_type": "email", "outcome": "email_sent"
    })
    rows = conn.execute("SELECT * FROM user_stars WHERE user_id=1").fetchall()
    assert len(rows) == 0


def test_star_auto_remove_does_not_touch_other_users_stars(conn):
    client = _client(conn, sub=1)
    # Brandon stars CON_1, Jamie also stars CON_1
    conn.execute("INSERT INTO user_stars (user_id, entity_type, entity_id) VALUES (1, 'contact', 'CON_1')")
    conn.execute("INSERT INTO user_stars (user_id, entity_type, entity_id) VALUES (2, 'contact', 'CON_1')")
    conn.commit()
    # Brandon logs an activity
    client.post("/api/activities", json={
        "entity_type": "contact", "entity_id": "CON_1", "activity_type": "call"
    })
    # Brandon's star removed, Jamie's preserved
    assert conn.execute("SELECT COUNT(*) FROM user_stars WHERE user_id=1").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM user_stars WHERE user_id=2").fetchone()[0] == 1


def test_star_auto_remove_handles_multiple_fks(conn):
    """Activity referencing both contact and property auto-removes both stars."""
    client = _client(conn, sub=1)
    conn.execute("INSERT INTO user_stars (user_id, entity_type, entity_id) VALUES (1, 'contact', 'CON_1')")
    conn.execute("INSERT INTO user_stars (user_id, entity_type, entity_id) VALUES (1, 'property', 'PRO_1')")
    conn.commit()
    # Logging from a sell_opp populates BOTH contact_id and property_id
    client.post("/api/activities", json={
        "entity_type": "sell_opportunity", "entity_id": "SOPP_1", "activity_type": "call"
    })
    rows = conn.execute("SELECT * FROM user_stars WHERE user_id=1").fetchall()
    assert len(rows) == 0


def test_happened_at_defaults_to_now(conn):
    client = _client(conn)
    client.post("/api/activities", json={
        "entity_type": "contact", "entity_id": "CON_1", "activity_type": "note"
    })
    row = conn.execute("SELECT happened_at FROM activities ORDER BY id DESC LIMIT 1").fetchone()
    assert row["happened_at"] is not None


def test_source_defaults_to_manual(conn):
    client = _client(conn)
    client.post("/api/activities", json={
        "entity_type": "contact", "entity_id": "CON_1", "activity_type": "note"
    })
    row = conn.execute("SELECT source FROM activities ORDER BY id DESC LIMIT 1").fetchone()
    assert row["source"] == "manual"
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
pytest tests/test_routes_activities_phase1.py -v 2>&1 | tail -40
```

Expected: most fail — `'property'` whitelist is the most-obvious one (currently rejected with 400). FK columns won't be populated; auto-engage won't fire; star auto-remove won't fire.

---

## Task 9: Activities upgrades — implement

**Files:**
- Modify: `cleo/web/routes/activities.py`

- [ ] **Step 1: Replace the activities route file**

Replace the entire `cleo/web/routes/activities.py` with:

```python
"""
Activities API — structured activity logging across CRM entities.

Phase 1 changes:
- 'property' added to the entity_type whitelist
- created_by_user_id FK populated from JWT 'sub'
- Primary entity FK (contact_id / property_id / group_id) auto-populated
  from entity_type/entity_id, with parent-record derivation for
  sell_opportunity / buy_mandate / deal types
- Auto-engage rule: any activity with a non-null contact_id or group_id
  flips that entity's status from 'pool' to 'engaged'
- Star auto-remove rule: when the current user logs an activity, any of
  their stars on the entities referenced by that activity are removed
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from typing import Optional
from ..deps import get_db, get_current_user

router = APIRouter()

ACTIVITY_TYPES = ["call", "email", "meeting", "note"]
OUTCOMES = ["connected", "voicemail", "no_answer", "email_sent", "meeting_held", None]
ENTITY_TYPES = ["sell_opportunity", "buy_mandate", "deal", "contact", "group", "property"]


class ActivityCreate(BaseModel):
    entity_type: str
    entity_id: str
    activity_type: str
    outcome: Optional[str] = None
    summary: Optional[str] = None
    next_step: Optional[str] = None
    happened_at: Optional[str] = None  # default now
    source: Optional[str] = None  # default 'manual'
    external_id: Optional[str] = None


def _user_id(user) -> int:
    return int(user["sub"])


def _resolve_fks(db, entity_type: str, entity_id: str):
    """Return (contact_id, property_id, group_id) for an activity's primary entity."""
    if entity_type == "contact":
        return entity_id, None, None
    if entity_type == "property":
        return None, entity_id, None
    if entity_type == "group":
        return None, None, entity_id
    if entity_type == "sell_opportunity":
        row = db.execute(
            "SELECT seller_contact_id, property_id, seller_group_id "
            "FROM sell_opportunities WHERE id = ?",
            (entity_id,),
        ).fetchone()
        if row:
            return row["seller_contact_id"], row["property_id"], row["seller_group_id"]
    elif entity_type == "buy_mandate":
        row = db.execute(
            "SELECT contact_id, group_id FROM buy_mandates WHERE id = ?",
            (entity_id,),
        ).fetchone()
        if row:
            return row["contact_id"], None, row["group_id"]
    elif entity_type == "deal":
        row = db.execute(
            "SELECT property_id, group_id FROM deals WHERE id = ?",
            (entity_id,),
        ).fetchone()
        if row:
            return None, row["property_id"], row["group_id"]
    return None, None, None


@router.get("")
def list_activities(
    entity_type: str = None,
    entity_id: str = None,
    activity_type: str = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    conditions = []
    params = []
    if entity_type and entity_id:
        conditions.append("entity_type = ? AND entity_id = ?")
        params.extend([entity_type, entity_id])
    elif entity_type:
        conditions.append("entity_type = ?")
        params.append(entity_type)
    if activity_type:
        conditions.append("activity_type = ?")
        params.append(activity_type)
    where = " AND ".join(conditions) if conditions else "1=1"
    offset = (page - 1) * per_page
    total = db.execute(f"SELECT COUNT(*) FROM activities WHERE {where}", params).fetchone()[0]
    rows = db.execute(
        f"SELECT * FROM activities WHERE {where} ORDER BY happened_at DESC, id DESC LIMIT ? OFFSET ?",
        params + [per_page, offset],
    ).fetchall()
    return {
        "results": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": max(1, (total + per_page - 1) // per_page),
    }


@router.get("/entity/{entity_type}/{entity_id}")
def entity_activities(
    entity_type: str,
    entity_id: str,
    limit: int = Query(50, ge=1, le=200),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    rows = db.execute(
        "SELECT * FROM activities WHERE entity_type = ? AND entity_id = ? "
        "ORDER BY happened_at DESC, id DESC LIMIT ?",
        (entity_type, entity_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


@router.post("")
def create_activity(body: ActivityCreate, db=Depends(get_db), user=Depends(get_current_user)):
    if body.entity_type not in ENTITY_TYPES:
        raise HTTPException(status_code=400,
                            detail=f"Invalid entity_type. Must be one of: {', '.join(ENTITY_TYPES)}")
    if body.activity_type not in ACTIVITY_TYPES:
        raise HTTPException(status_code=400,
                            detail=f"Invalid activity_type. Must be one of: {', '.join(ACTIVITY_TYPES)}")

    me = _user_id(user)
    created_by = user.get("display_name") or user.get("username") or "unknown"
    contact_id, property_id, group_id = _resolve_fks(db, body.entity_type, body.entity_id)
    happened_at = body.happened_at  # None -> SQL DEFAULT (datetime('now'))
    source = body.source or "manual"

    # Insert activity
    cursor = db.execute(
        """
        INSERT INTO activities
          (entity_type, entity_id, activity_type, outcome, summary, next_step,
           created_by, created_by_user_id, source, external_id, happened_at,
           contact_id, property_id, group_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, datetime('now')), ?, ?, ?)
        """,
        (body.entity_type, body.entity_id, body.activity_type, body.outcome,
         body.summary, body.next_step, created_by, me, source, body.external_id,
         happened_at, contact_id, property_id, group_id),
    )

    # Auto-engage rule
    if contact_id:
        db.execute(
            "UPDATE contacts SET status='engaged', last_engaged_date=COALESCE(?, datetime('now')) "
            "WHERE id=? AND status='pool'",
            (happened_at, contact_id),
        )
    if group_id:
        db.execute(
            "UPDATE groups SET status='engaged' WHERE id=? AND status='pool'",
            (group_id,),
        )

    # Star auto-remove rule (current user only)
    fks = []
    if contact_id:
        fks.append(("contact", contact_id))
    if property_id:
        fks.append(("property", property_id))
    if group_id:
        fks.append(("group", group_id))
    if fks:
        where = " OR ".join("(entity_type=? AND entity_id=?)" for _ in fks)
        params = [me] + [v for pair in fks for v in pair]
        db.execute(f"DELETE FROM user_stars WHERE user_id=? AND ({where})", params)

    # last_activity_at propagation (existing behavior)
    if body.entity_type == "sell_opportunity":
        db.execute(
            "UPDATE sell_opportunities SET last_activity_at=datetime('now'), updated_at=datetime('now') WHERE id=?",
            (body.entity_id,),
        )
    elif body.entity_type == "buy_mandate":
        db.execute(
            "UPDATE buy_mandates SET last_activity_at=datetime('now'), updated_at=datetime('now') WHERE id=?",
            (body.entity_id,),
        )

    db.commit()
    return {"id": cursor.lastrowid, "status": "created"}


@router.get("/stale")
def stale_entities(db=Depends(get_db), user=Depends(get_current_user)):
    """Get all stale sell opportunities and buy mandates."""
    stale_sell = db.execute(
        "SELECT so.id, so.property_id, so.status, so.owner, so.deal_value, "
        "so.last_activity_at, so.decay_days, "
        "p.display_address, p.city, "
        "CAST(julianday('now') - julianday(so.last_activity_at) AS INTEGER) AS days_since_activity "
        "FROM sell_opportunities so "
        "JOIN properties p ON so.property_id = p.id "
        "WHERE so.status = 'active' "
        "AND julianday('now') - julianday(so.last_activity_at) > so.decay_days "
        "ORDER BY days_since_activity DESC"
    ).fetchall()
    stale_buy = db.execute(
        "SELECT bm.id, bm.contact_id, bm.group_id, bm.status, bm.owner, "
        "bm.criteria_json, bm.last_activity_at, bm.decay_days, "
        "c.display_name AS contact_name, g.display_name AS group_name, "
        "CAST(julianday('now') - julianday(bm.last_activity_at) AS INTEGER) AS days_since_activity "
        "FROM buy_mandates bm "
        "LEFT JOIN contacts c ON bm.contact_id = c.id "
        "LEFT JOIN groups g ON bm.group_id = g.id "
        "WHERE bm.status = 'active' "
        "AND julianday('now') - julianday(bm.last_activity_at) > bm.decay_days "
        "ORDER BY days_since_activity DESC"
    ).fetchall()
    return {
        "sell_opportunities": [dict(r) for r in stale_sell],
        "buy_mandates": [dict(r) for r in stale_buy],
        "total_stale": len(stale_sell) + len(stale_buy),
    }
```

- [ ] **Step 2: Run the tests to verify they pass**

```bash
pytest tests/test_routes_activities_phase1.py -v 2>&1 | tail -40
```

Expected: all 17 tests pass.

- [ ] **Step 3: Run the broader test suite to confirm no regression**

```bash
pytest tests/ -x --ignore=tests/test_discovery_v2_expansion.py 2>&1 | tail -10
```

Expected: same baseline as Task 0 step 3.

- [ ] **Step 4: Commit**

```bash
git add cleo/web/routes/activities.py tests/test_routes_activities_phase1.py
git commit -m "$(cat <<'EOF'
feat(api): activities Phase 1 — multi-entity FKs + auto-engage + star auto-remove

Adds 'property' to entity_type whitelist, populates the contact_id /
property_id / group_id FKs at write time (deriving from parent records
for sell_opp / buy_mandate / deal), auto-engages pool contacts and
groups, and removes the current user's stars on entities the activity
references. created_by_user_id now reads JWT 'sub' for proper FK
attribution.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Synthetic engage activity — write failing test

**Files:**
- Test: `tests/test_routes_engage_synthetic_activity.py`

- [ ] **Step 1: Create the failing test file**

Create `tests/test_routes_engage_synthetic_activity.py`:

```python
"""When the manual Engage button is hit on a contact or group, a synthetic
'note' activity is written so the activity log remains the single source
of truth for attribution. Idempotent: re-engaging an already-engaged
entity does nothing."""
import sqlite3
import pytest
from fastapi.testclient import TestClient


def _seeded_db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT, password_hash TEXT, display_name TEXT, role TEXT,
            created_at TEXT
        );
        CREATE TABLE contacts (
            id TEXT PRIMARY KEY, display_name TEXT,
            status TEXT NOT NULL DEFAULT 'pool',
            last_engaged_date TEXT,
            updated_at TEXT
        );
        CREATE TABLE contact_field_overrides (
            contact_id TEXT PRIMARY KEY, status TEXT, updated_by TEXT, updated_at TEXT
        );
        CREATE TABLE groups (
            id TEXT PRIMARY KEY, display_name TEXT,
            status TEXT NOT NULL DEFAULT 'pool',
            updated_at TEXT
        );
        CREATE TABLE group_field_overrides (
            group_id TEXT PRIMARY KEY, status TEXT, updated_by TEXT, updated_at TEXT
        );
        CREATE TABLE activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT, entity_id TEXT,
            activity_type TEXT, outcome TEXT, summary TEXT, next_step TEXT,
            created_by TEXT, created_by_user_id INTEGER,
            source TEXT NOT NULL DEFAULT 'manual',
            external_id TEXT, happened_at TEXT,
            contact_id TEXT, property_id TEXT, group_id TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, action TEXT, entity_type TEXT, entity_id TEXT,
            details TEXT, created_at TEXT
        );
        INSERT INTO users (id, username, display_name, password_hash, role)
            VALUES (1, 'brandon', 'Brandon', 'x', 'editor');
        INSERT INTO contacts (id, display_name) VALUES ('CON_1', 'Peter Vicano');
        INSERT INTO groups (id, display_name) VALUES ('GRP_1', 'DH Management');
    """)
    conn.commit()
    return conn


def _client(conn):
    from cleo.web.app import app
    from cleo.web import deps

    def _get_db():
        yield conn
    app.dependency_overrides[deps.get_db] = _get_db
    app.dependency_overrides[deps.get_current_user] = lambda: {
        "sub": 1, "username": "brandon", "display_name": "Brandon", "role": "editor"
    }
    return TestClient(app)


@pytest.fixture
def conn():
    c = _seeded_db()
    yield c
    from cleo.web.app import app
    app.dependency_overrides.clear()
    c.close()


def test_engage_contact_writes_synthetic_activity(conn):
    client = _client(conn)
    resp = client.post("/api/contacts/CON_1/engage")
    assert resp.status_code == 200
    rows = conn.execute(
        "SELECT * FROM activities WHERE contact_id='CON_1' AND activity_type='note'"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["summary"] == "Marked engaged"
    assert rows[0]["created_by_user_id"] == 1


def test_engage_contact_idempotent_no_duplicate_activity(conn):
    client = _client(conn)
    client.post("/api/contacts/CON_1/engage")
    client.post("/api/contacts/CON_1/engage")
    rows = conn.execute(
        "SELECT * FROM activities WHERE contact_id='CON_1'"
    ).fetchall()
    assert len(rows) == 1


def test_engage_group_writes_synthetic_activity(conn):
    client = _client(conn)
    resp = client.post("/api/groups/GRP_1/engage")
    assert resp.status_code == 200
    rows = conn.execute(
        "SELECT * FROM activities WHERE group_id='GRP_1' AND activity_type='note'"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["summary"] == "Marked engaged"


def test_engage_group_idempotent(conn):
    client = _client(conn)
    client.post("/api/groups/GRP_1/engage")
    client.post("/api/groups/GRP_1/engage")
    rows = conn.execute("SELECT * FROM activities WHERE group_id='GRP_1'").fetchall()
    assert len(rows) == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
pytest tests/test_routes_engage_synthetic_activity.py -v 2>&1 | tail -20
```

Expected: tests fail because the existing engage endpoints don't write activities.

---

## Task 11: Synthetic engage activity — implement

**Files:**
- Modify: `cleo/web/routes/contacts.py` (around line 571)
- Modify: `cleo/web/routes/groups.py` (around line 453)

- [ ] **Step 1: Update the contacts engage endpoint**

Open `cleo/web/routes/contacts.py` and find the `engage_contact` function (around line 565+). Replace the function body so it short-circuits if already engaged and writes the synthetic activity. The function ends at line ~580 currently.

Find this block:

```python
    db.execute("UPDATE contacts SET status = 'engaged', updated_at = datetime('now') WHERE id = ?", (contact_id,))
    # ...override insert...
    return {"id": contact_id, "status": "engaged"}
```

Replace the entire `engage_contact` endpoint with:

```python
@router.post("/{contact_id}/engage")
def engage_contact(contact_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    """Manually flip pool→engaged on a contact and write a synthetic note activity.
    Idempotent: re-engaging does nothing."""
    row = db.execute("SELECT status FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Contact not found")
    if row["status"] == "engaged":
        return {"id": contact_id, "status": "engaged", "already": True}

    me = int(user["sub"])
    created_by = user.get("display_name") or user.get("username") or "unknown"

    db.execute(
        "UPDATE contacts SET status='engaged', last_engaged_date=datetime('now'), "
        "updated_at=datetime('now') WHERE id=?",
        (contact_id,),
    )
    db.execute(
        "INSERT INTO contact_field_overrides (contact_id, status, updated_by) "
        "VALUES (?, 'engaged', ?) "
        "ON CONFLICT(contact_id) DO UPDATE SET status='engaged', updated_by=?, "
        "updated_at=datetime('now')",
        (contact_id, created_by, created_by),
    )
    # Synthetic activity — keep activity log as the source of truth for attribution
    db.execute(
        "INSERT INTO activities "
        "(entity_type, entity_id, activity_type, summary, source, "
        " created_by, created_by_user_id, contact_id, happened_at) "
        "VALUES ('contact', ?, 'note', 'Marked engaged', 'manual', ?, ?, ?, datetime('now'))",
        (contact_id, created_by, me, contact_id),
    )
    db.commit()
    return {"id": contact_id, "status": "engaged"}
```

- [ ] **Step 2: Update the groups engage endpoint**

Open `cleo/web/routes/groups.py` and find the engage endpoint (around line 450+). Replace it with:

```python
@router.post("/{group_id}/engage")
def engage_group(group_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    """Manually flip pool→engaged on a group and write a synthetic note activity.
    Idempotent: re-engaging does nothing."""
    row = db.execute("SELECT status FROM groups WHERE id = ?", (group_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Group not found")
    if row["status"] == "engaged":
        return {"id": group_id, "status": "engaged", "already": True}

    me = int(user["sub"])
    created_by = user.get("display_name") or user.get("username") or "unknown"

    db.execute(
        "UPDATE groups SET status='engaged', updated_at=datetime('now') WHERE id=?",
        (group_id,),
    )
    db.execute(
        "INSERT INTO group_field_overrides (group_id, status, updated_by) "
        "VALUES (?, 'engaged', ?) "
        "ON CONFLICT(group_id) DO UPDATE SET status='engaged', updated_by=?, "
        "updated_at=datetime('now')",
        (group_id, created_by, created_by),
    )
    db.execute(
        "INSERT INTO activities "
        "(entity_type, entity_id, activity_type, summary, source, "
        " created_by, created_by_user_id, group_id, happened_at) "
        "VALUES ('group', ?, 'note', 'Marked engaged', 'manual', ?, ?, ?, datetime('now'))",
        (group_id, created_by, me, group_id),
    )
    db.commit()
    return {"id": group_id, "status": "engaged"}
```

- [ ] **Step 3: Run the tests to verify they pass**

```bash
pytest tests/test_routes_engage_synthetic_activity.py -v 2>&1 | tail -20
```

Expected: all 4 tests pass.

- [ ] **Step 4: Commit**

```bash
git add cleo/web/routes/contacts.py cleo/web/routes/groups.py tests/test_routes_engage_synthetic_activity.py
git commit -m "$(cat <<'EOF'
feat(api): manual engage writes synthetic note activity

Engage endpoints on contacts and groups now insert a 'note' activity
('Marked engaged') alongside the status flip, so the activity log
remains the single source of truth for attribution. Idempotent.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: Attribution endpoints — write failing test

**Files:**
- Test: `tests/test_routes_attribution.py`

- [ ] **Step 1: Create the failing test file**

Create `tests/test_routes_attribution.py`:

```python
"""Tests for /api/{contacts|properties|groups}/{id}/attribution."""
import sqlite3
import pytest
from fastapi.testclient import TestClient


def _seeded_db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT, password_hash TEXT, display_name TEXT, role TEXT,
            created_at TEXT
        );
        CREATE TABLE contacts (id TEXT PRIMARY KEY, display_name TEXT, status TEXT, last_engaged_date TEXT);
        CREATE TABLE properties (id TEXT PRIMARY KEY, display_address TEXT, city TEXT);
        CREATE TABLE groups (id TEXT PRIMARY KEY, display_name TEXT, status TEXT);
        CREATE TABLE activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT, entity_id TEXT,
            activity_type TEXT, outcome TEXT, summary TEXT, next_step TEXT,
            created_by TEXT, created_by_user_id INTEGER,
            source TEXT, external_id TEXT, happened_at TEXT,
            contact_id TEXT, property_id TEXT, group_id TEXT,
            created_at TEXT
        );
        INSERT INTO users (id, username, display_name, password_hash, role) VALUES
            (1, 'brandon', 'Brandon', 'x', 'editor'),
            (2, 'jamie',   'Jamie',   'x', 'editor');
        INSERT INTO contacts (id, display_name) VALUES ('CON_1', 'Peter Vicano');
        INSERT INTO properties (id, display_address) VALUES ('PRO_1', '240 King George Rd');
        INSERT INTO groups (id, display_name) VALUES ('GRP_1', 'DH Management');
    """)
    conn.commit()
    return conn


def _client(conn):
    from cleo.web.app import app
    from cleo.web import deps

    def _get_db():
        yield conn
    app.dependency_overrides[deps.get_db] = _get_db
    app.dependency_overrides[deps.get_current_user] = lambda: {
        "sub": 1, "username": "brandon", "display_name": "Brandon", "role": "editor"
    }
    return TestClient(app)


@pytest.fixture
def conn():
    c = _seeded_db()
    yield c
    from cleo.web.app import app
    app.dependency_overrides.clear()
    c.close()


def test_contact_attribution_zero_activities(conn):
    client = _client(conn)
    resp = client.get("/api/contacts/CON_1/attribution")
    assert resp.status_code == 200
    body = resp.json()
    assert body["first_contacted"] is None
    assert body["last_contacted"] is None
    assert body["total_activities"] == 0
    assert body["by_user"] == []


def test_contact_attribution_with_activities(conn):
    client = _client(conn)
    conn.execute(
        "INSERT INTO activities (entity_type, entity_id, activity_type, outcome, "
        "created_by, created_by_user_id, contact_id, happened_at, source) VALUES "
        "('contact', 'CON_1', 'call',  'connected',  'Jamie',   2, 'CON_1', '2024-03-12 09:14:00', 'manual'),"
        "('contact', 'CON_1', 'email', 'email_sent', 'Brandon', 1, 'CON_1', '2026-05-05 11:22:00', 'manual'),"
        "('contact', 'CON_1', 'note',  NULL,         'Brandon', 1, 'CON_1', '2025-01-15 10:00:00', 'manual')"
    )
    conn.commit()
    body = client.get("/api/contacts/CON_1/attribution").json()
    assert body["total_activities"] == 3
    assert body["first_contacted"]["user_name"] == "Jamie"
    assert body["first_contacted"]["activity_type"] == "call"
    assert body["first_contacted"]["outcome"] == "connected"
    assert body["last_contacted"]["user_name"] == "Brandon"
    assert body["last_contacted"]["activity_type"] == "email"
    by_user = {b["user_name"]: b["count"] for b in body["by_user"]}
    assert by_user == {"Brandon": 2, "Jamie": 1}


def test_property_attribution(conn):
    client = _client(conn)
    conn.execute(
        "INSERT INTO activities (entity_type, entity_id, activity_type, "
        "created_by, created_by_user_id, property_id, happened_at, source) VALUES "
        "('property', 'PRO_1', 'note', 'Brandon', 1, 'PRO_1', '2026-05-01 10:00:00', 'manual')"
    )
    conn.commit()
    body = client.get("/api/properties/PRO_1/attribution").json()
    assert body["total_activities"] == 1
    assert body["first_contacted"]["user_name"] == "Brandon"


def test_group_attribution(conn):
    client = _client(conn)
    conn.execute(
        "INSERT INTO activities (entity_type, entity_id, activity_type, "
        "created_by, created_by_user_id, group_id, happened_at, source) VALUES "
        "('group', 'GRP_1', 'meeting', 'Jamie', 2, 'GRP_1', '2026-01-01 10:00:00', 'manual')"
    )
    conn.commit()
    body = client.get("/api/groups/GRP_1/attribution").json()
    assert body["total_activities"] == 1
    assert body["first_contacted"]["user_name"] == "Jamie"
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
pytest tests/test_routes_attribution.py -v 2>&1 | tail -20
```

Expected: 404 on every test — the endpoints don't exist.

---

## Task 13: Attribution endpoints — implement

**Files:**
- Modify: `cleo/web/routes/contacts.py`
- Modify: `cleo/web/routes/properties.py`
- Modify: `cleo/web/routes/groups.py`

- [ ] **Step 1: Add a shared helper module for attribution**

Create `cleo/web/routes/_attribution.py`:

```python
"""Shared helper for first/last/by-user attribution lookups on activities."""


def attribution_for(db, fk_column: str, entity_id: str) -> dict:
    """Return first/last contacted + per-user counts for a given entity.

    fk_column must be one of 'contact_id', 'property_id', 'group_id'.
    """
    if fk_column not in ("contact_id", "property_id", "group_id"):
        raise ValueError(f"Invalid fk_column: {fk_column}")

    total = db.execute(
        f"SELECT COUNT(*) FROM activities WHERE {fk_column} = ?", (entity_id,)
    ).fetchone()[0]

    if total == 0:
        return {
            "first_contacted": None,
            "last_contacted": None,
            "total_activities": 0,
            "by_user": [],
        }

    first = db.execute(
        f"""
        SELECT a.created_by_user_id AS user_id,
               u.display_name AS user_name,
               a.happened_at, a.activity_type, a.outcome
        FROM activities a
        LEFT JOIN users u ON u.id = a.created_by_user_id
        WHERE a.{fk_column} = ?
        ORDER BY a.happened_at ASC, a.id ASC
        LIMIT 1
        """,
        (entity_id,),
    ).fetchone()

    last = db.execute(
        f"""
        SELECT a.created_by_user_id AS user_id,
               u.display_name AS user_name,
               a.happened_at, a.activity_type, a.outcome
        FROM activities a
        LEFT JOIN users u ON u.id = a.created_by_user_id
        WHERE a.{fk_column} = ?
        ORDER BY a.happened_at DESC, a.id DESC
        LIMIT 1
        """,
        (entity_id,),
    ).fetchone()

    by_user_rows = db.execute(
        f"""
        SELECT a.created_by_user_id AS user_id,
               u.display_name AS user_name,
               COUNT(*) AS count
        FROM activities a
        LEFT JOIN users u ON u.id = a.created_by_user_id
        WHERE a.{fk_column} = ?
        GROUP BY a.created_by_user_id
        ORDER BY count DESC
        """,
        (entity_id,),
    ).fetchall()

    return {
        "first_contacted": dict(first) if first else None,
        "last_contacted": dict(last) if last else None,
        "total_activities": total,
        "by_user": [dict(r) for r in by_user_rows],
    }
```

- [ ] **Step 2: Add the contact attribution endpoint**

In `cleo/web/routes/contacts.py`, add this import near the other route imports:

```python
from ._attribution import attribution_for
```

Add this endpoint at the bottom of the file (just before any closing block):

```python
@router.get("/{contact_id}/attribution")
def contact_attribution(contact_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    return attribution_for(db, "contact_id", contact_id)
```

- [ ] **Step 3: Add the property attribution endpoint**

In `cleo/web/routes/properties.py`, add this import:

```python
from ._attribution import attribution_for
```

Add this endpoint at the bottom of the file:

```python
@router.get("/{property_id}/attribution")
def property_attribution(property_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    return attribution_for(db, "property_id", property_id)
```

- [ ] **Step 4: Add the group attribution endpoint**

In `cleo/web/routes/groups.py`, add this import:

```python
from ._attribution import attribution_for
```

Add this endpoint at the bottom of the file:

```python
@router.get("/{group_id}/attribution")
def group_attribution(group_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    return attribution_for(db, "group_id", group_id)
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
pytest tests/test_routes_attribution.py -v 2>&1 | tail -20
```

Expected: all 4 tests pass.

- [ ] **Step 6: Run the full backend test suite**

```bash
pytest tests/ -x --ignore=tests/test_discovery_v2_expansion.py 2>&1 | tail -10
```

Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add cleo/web/routes/_attribution.py cleo/web/routes/contacts.py cleo/web/routes/properties.py cleo/web/routes/groups.py tests/test_routes_attribution.py
git commit -m "$(cat <<'EOF'
feat(api): /api/{contacts,properties,groups}/{id}/attribution

Returns first/last contacted (user + happened_at + activity_type +
outcome) plus per-user counts. Backed by a shared helper that joins
activities to users and uses the new entity-FK indexes.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 14: Frontend types

**Files:**
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Add the new types**

Append to `frontend/src/types/index.ts` (don't overwrite existing exports):

```ts
// ============================================================
// CRM Phase 1 — daily-outreach surfaces
// ============================================================

export type CrmEntityType = "contact" | "property" | "group";

export interface UserStar {
  user_id: number;
  entity_type: CrmEntityType;
  entity_id: string;
  starred_at: string;
  name: string | null;
  detail: string | null;
  team_activity: TeamActivity | null;
}

export interface TeamActivity {
  by_user_id: number;
  by_user_name: string;
  happened_at: string;
  activity_type: string;
  outcome: string | null;
}

export interface ListSummary {
  id: string;
  name: string;
  description: string | null;
  scope: "personal" | "shared";
  owner_user_id: number | null;
  owner_name: string | null;
  total_members: number;
  member_counts: Record<string, number>;
  created_at: string;
  updated_at: string;
}

export interface ListMembership {
  list_id: string;
  list_name: string;
  scope: "personal" | "shared";
}

export interface ContactEvent {
  user_id: number | null;
  user_name: string | null;
  happened_at: string;
  activity_type: string;
  outcome: string | null;
}

export interface AttributionResponse {
  first_contacted: ContactEvent | null;
  last_contacted: ContactEvent | null;
  total_activities: number;
  by_user: { user_id: number | null; user_name: string | null; count: number }[];
}
```

If `ActivityEntityType` doesn't already include `'property'` in this file, update it. Search for `ActivityEntityType` and ensure the union covers all six current types:

```ts
export type ActivityEntityType =
  | "sell_opportunity"
  | "buy_mandate"
  | "deal"
  | "contact"
  | "group"
  | "property";
```

- [ ] **Step 2: Type-check**

```bash
cd frontend && npx tsc --noEmit 2>&1 | tail -20
```

Expected: clean (no new errors). If there are pre-existing errors, note them but don't fix in this task.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "types(frontend): CRM Phase 1 daily-outreach types

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 15: StarButton component

**Files:**
- Create: `frontend/src/components/crm/StarButton.tsx`

- [ ] **Step 1: Implement the component**

Create `frontend/src/components/crm/StarButton.tsx`:

```tsx
import { useEffect, useState, useCallback } from "react";
import { Star } from "@phosphor-icons/react";
import { fetchApi, postApi, mutateApi } from "../../api/client";
import type { CrmEntityType } from "../../types";

interface StarButtonProps {
  entityType: CrmEntityType;
  entityId: string;
  size?: number;
  showLabel?: boolean;
  className?: string;
}

const EVENT_NAME = "crm-star-changed";

export default function StarButton({
  entityType,
  entityId,
  size = 18,
  showLabel = false,
  className,
}: StarButtonProps) {
  const [starred, setStarred] = useState<boolean | null>(null);
  const [pending, setPending] = useState(false);

  const refresh = useCallback(() => {
    fetchApi<{ starred: boolean }>(
      `/stars/check?entity_type=${entityType}&entity_id=${encodeURIComponent(entityId)}`
    )
      .then((r) => setStarred(r.starred))
      .catch(() => setStarred(false));
  }, [entityType, entityId]);

  useEffect(() => {
    refresh();
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<{ entity_type: string; entity_id: string }>).detail;
      if (detail.entity_type === entityType && detail.entity_id === entityId) refresh();
    };
    window.addEventListener(EVENT_NAME, handler as EventListener);
    return () => window.removeEventListener(EVENT_NAME, handler as EventListener);
  }, [refresh, entityType, entityId]);

  async function toggle(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (pending || starred === null) return;
    const next = !starred;
    setStarred(next); // optimistic
    setPending(true);
    try {
      if (next) {
        await postApi("/stars", { entity_type: entityType, entity_id: entityId });
      } else {
        await mutateApi(`/stars/${entityType}/${encodeURIComponent(entityId)}`, "DELETE");
      }
      window.dispatchEvent(
        new CustomEvent(EVENT_NAME, { detail: { entity_type: entityType, entity_id: entityId } })
      );
    } catch {
      setStarred(!next); // revert
    } finally {
      setPending(false);
    }
  }

  const label = showLabel ? (starred ? "Starred" : "Star") : null;
  const color = starred ? "var(--accent-11)" : "var(--gray-9)";

  return (
    <button
      onClick={toggle}
      disabled={pending || starred === null}
      title={starred ? "Remove from queue" : "Add to queue"}
      className={
        className ??
        "inline-flex items-center gap-1 px-2 py-1 rounded text-[13px] hover:bg-[var(--gray-3)] transition-colors disabled:opacity-50"
      }
      style={{ color }}
    >
      <Star size={size} weight={starred ? "fill" : "regular"} />
      {label && <span>{label}</span>}
    </button>
  );
}
```

- [ ] **Step 2: Type-check**

```bash
cd frontend && npx tsc --noEmit 2>&1 | tail -10
```

Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/crm/StarButton.tsx
git commit -m "feat(frontend): StarButton component for per-user CRM stars

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 16: AttributionStrip component

**Files:**
- Create: `frontend/src/components/crm/AttributionStrip.tsx`

- [ ] **Step 1: Implement the component**

Create `frontend/src/components/crm/AttributionStrip.tsx`:

```tsx
import { useEffect, useState } from "react";
import { Text } from "@radix-ui/themes";
import { fetchApi } from "../../api/client";
import { formatDate } from "../../lib/utils";
import type { AttributionResponse, CrmEntityType } from "../../types";

interface AttributionStripProps {
  entityType: CrmEntityType;
  entityId: string;
}

const ENDPOINT_BY_TYPE: Record<CrmEntityType, string> = {
  contact: "/contacts",
  property: "/properties",
  group: "/groups",
};

export default function AttributionStrip({ entityType, entityId }: AttributionStripProps) {
  const [data, setData] = useState<AttributionResponse | null>(null);

  useEffect(() => {
    fetchApi<AttributionResponse>(`${ENDPOINT_BY_TYPE[entityType]}/${entityId}/attribution`)
      .then(setData)
      .catch(() => setData(null));
  }, [entityType, entityId]);

  if (!data) return null;

  if (data.total_activities === 0) {
    return (
      <Text size="2" style={{ color: "var(--gray-9)" }}>
        Never contacted
      </Text>
    );
  }

  const renderEvent = (label: string, ev: AttributionResponse["first_contacted"]) => {
    if (!ev) return null;
    const outcomeBit = ev.outcome ? ` → ${ev.outcome}` : "";
    return (
      <div className="flex gap-2 text-[13px] items-baseline">
        <Text size="2" style={{ color: "var(--gray-9)", minWidth: 110 }}>
          {label}
        </Text>
        <Text size="2">
          <span style={{ fontWeight: 500 }}>{ev.user_name ?? "Unknown user"}</span>
          {" · "}
          {formatDate(ev.happened_at)}
          {" · "}
          <span style={{ color: "var(--gray-11)" }}>
            {ev.activity_type}
            {outcomeBit}
          </span>
        </Text>
      </div>
    );
  };

  const byUserStr = data.by_user
    .filter((u) => u.user_name)
    .map((u) => `${u.user_name} (${u.count})`)
    .join(" · ");

  return (
    <div className="flex flex-col gap-1">
      {renderEvent("First contacted", data.first_contacted)}
      {renderEvent("Last contacted", data.last_contacted)}
      <Text size="1" style={{ color: "var(--gray-9)" }}>
        {data.total_activities} {data.total_activities === 1 ? "activity" : "activities"}
        {byUserStr ? ` · ${byUserStr}` : ""}
      </Text>
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

```bash
cd frontend && npx tsc --noEmit 2>&1 | tail -10
```

Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/crm/AttributionStrip.tsx
git commit -m "feat(frontend): AttributionStrip — first/last contacted + per-user counts

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 17: AddToListDrawer component

**Files:**
- Create: `frontend/src/components/crm/AddToListDrawer.tsx`

- [ ] **Step 1: Implement the component**

Create `frontend/src/components/crm/AddToListDrawer.tsx`:

```tsx
import { useEffect, useState } from "react";
import { Button, Heading, Text, TextField, Switch, Badge } from "@radix-ui/themes";
import { X, Plus } from "@phosphor-icons/react";
import { fetchApi, postApi, mutateApi } from "../../api/client";
import type { ListSummary, ListMembership } from "../../types";

interface AddToListDrawerProps {
  memberType: "contact" | "property" | "group";
  memberId: string;
  onClose: () => void;
}

export default function AddToListDrawer({ memberType, memberId, onClose }: AddToListDrawerProps) {
  const [lists, setLists] = useState<ListSummary[]>([]);
  const [memberOf, setMemberOf] = useState<Set<string>>(new Set());
  const [pending, setPending] = useState<Set<string>>(new Set());
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [newShared, setNewShared] = useState(false);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    fetchApi<ListSummary[]>("/lists").then(setLists);
    fetchApi<ListMembership[]>(
      `/lists/membership?member_type=${memberType}&member_id=${encodeURIComponent(memberId)}`
    ).then((r) => setMemberOf(new Set(r.map((m) => m.list_id))));
  }, [memberType, memberId]);

  async function toggleMember(listId: string) {
    if (pending.has(listId)) return;
    const isMember = memberOf.has(listId);
    setPending((p) => new Set(p).add(listId));
    const next = new Set(memberOf);
    if (isMember) next.delete(listId);
    else next.add(listId);
    setMemberOf(next);
    try {
      if (isMember) {
        await mutateApi(
          `/lists/${listId}/members/${memberType}/${encodeURIComponent(memberId)}`,
          "DELETE"
        );
      } else {
        await postApi(`/lists/${listId}/members`, { member_type: memberType, member_id: memberId });
      }
    } catch {
      // revert
      const reverted = new Set(memberOf);
      if (isMember) reverted.add(listId);
      else reverted.delete(listId);
      setMemberOf(reverted);
    } finally {
      setPending((p) => {
        const n = new Set(p);
        n.delete(listId);
        return n;
      });
    }
  }

  async function createAndAdd() {
    if (!newName.trim()) return;
    setCreating(true);
    try {
      const res = await postApi<{ id: string }>("/lists", {
        name: newName.trim(),
        description: newDesc.trim() || null,
        scope: newShared ? "shared" : "personal",
      });
      await postApi(`/lists/${res.id}/members`, { member_type: memberType, member_id: memberId });
      const refreshed = await fetchApi<ListSummary[]>("/lists");
      setLists(refreshed);
      setMemberOf((prev) => new Set(prev).add(res.id));
      setShowCreate(false);
      setNewName("");
      setNewDesc("");
      setNewShared(false);
    } finally {
      setCreating(false);
    }
  }

  const personal = lists.filter((l) => l.scope === "personal");
  const shared = lists.filter((l) => l.scope === "shared");

  return (
    <div className="fixed inset-0 z-50 flex">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative ml-auto w-full max-w-md h-full overflow-y-auto bg-[var(--color-background)] border-l border-[var(--gray-6)] p-6">
        <div className="flex items-center justify-between mb-4">
          <Heading size="4">Add to list</Heading>
          <button onClick={onClose} className="p-1 rounded hover:bg-[var(--gray-3)]">
            <X size={18} />
          </button>
        </div>

        {personal.length > 0 && (
          <div className="mb-6">
            <Text size="2" weight="medium" style={{ color: "var(--gray-11)" }} className="block mb-2">
              My personal lists
            </Text>
            <div className="flex flex-col gap-1">
              {personal.map((l) => (
                <ListRow
                  key={l.id}
                  list={l}
                  checked={memberOf.has(l.id)}
                  onToggle={() => toggleMember(l.id)}
                />
              ))}
            </div>
          </div>
        )}

        {shared.length > 0 && (
          <div className="mb-6">
            <Text size="2" weight="medium" style={{ color: "var(--gray-11)" }} className="block mb-2">
              Shared lists
            </Text>
            <div className="flex flex-col gap-1">
              {shared.map((l) => (
                <ListRow
                  key={l.id}
                  list={l}
                  checked={memberOf.has(l.id)}
                  onToggle={() => toggleMember(l.id)}
                />
              ))}
            </div>
          </div>
        )}

        {!showCreate ? (
          <Button variant="soft" onClick={() => setShowCreate(true)}>
            <Plus size={14} /> New list
          </Button>
        ) : (
          <div className="flex flex-col gap-2 p-3 border border-[var(--gray-6)] rounded-md">
            <TextField.Root value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="List name" />
            <TextField.Root value={newDesc} onChange={(e) => setNewDesc(e.target.value)} placeholder="Description (optional)" />
            <label className="flex items-center gap-2">
              <Switch checked={newShared} onCheckedChange={setNewShared} />
              <Text size="2">Shared with team</Text>
            </label>
            <div className="flex justify-end gap-2 mt-2">
              <Button variant="soft" color="gray" onClick={() => setShowCreate(false)}>Cancel</Button>
              <Button onClick={createAndAdd} disabled={creating || !newName.trim()}>
                {creating ? "Creating..." : "Create + add"}
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function ListRow({
  list,
  checked,
  onToggle,
}: {
  list: ListSummary;
  checked: boolean;
  onToggle: () => void;
}) {
  return (
    <label className="flex items-center justify-between gap-2 p-2 rounded hover:bg-[var(--gray-2)] cursor-pointer">
      <div className="flex items-center gap-2">
        <input type="checkbox" checked={checked} onChange={onToggle} />
        <Text size="2">{list.name}</Text>
        {list.scope === "shared" && (
          <Badge size="1" variant="soft" color="jade">shared</Badge>
        )}
      </div>
      <Text size="1" style={{ color: "var(--gray-9)" }}>
        {list.total_members} members
      </Text>
    </label>
  );
}
```

- [ ] **Step 2: Type-check and commit**

```bash
cd frontend && npx tsc --noEmit 2>&1 | tail -10
```

Expected: clean.

```bash
cd .. && git add frontend/src/components/crm/AddToListDrawer.tsx
git commit -m "feat(frontend): AddToListDrawer — personal + shared lists with create-new

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 18: CreateDealDrawer component

**Files:**
- Create: `frontend/src/components/crm/CreateDealDrawer.tsx`

- [ ] **Step 1: Implement the component**

Create `frontend/src/components/crm/CreateDealDrawer.tsx`:

```tsx
import { useState } from "react";
import { Button, Heading, Select, Text, TextArea, TextField } from "@radix-ui/themes";
import { X } from "@phosphor-icons/react";
import { useNavigate } from "react-router-dom";
import { postApi } from "../../api/client";
import type { CrmEntityType } from "../../types";

interface CreateDealDrawerProps {
  entityType: CrmEntityType;
  entityId: string;
  entityName: string;
  ownerName?: string;
  onClose: () => void;
}

const STAGES = [
  "long_shot", "priority_deal", "mandate", "viable_deal",
  "in_negotiation", "under_contract", "firm",
];

export default function CreateDealDrawer({
  entityType,
  entityId,
  entityName,
  ownerName,
  onClose,
}: CreateDealDrawerProps) {
  const navigate = useNavigate();
  const [name, setName] = useState(`${entityName} — Deal`);
  const [stage, setStage] = useState("long_shot");
  const [amount, setAmount] = useState("");
  const [closeDate, setCloseDate] = useState("");
  const [priority, setPriority] = useState("");
  const [description, setDescription] = useState("");
  const [nextStep, setNextStep] = useState("");
  const [saving, setSaving] = useState(false);

  async function handleCreate() {
    if (!name.trim()) return;
    setSaving(true);
    try {
      const body: Record<string, unknown> = {
        name: name.trim(),
        stage,
        deal_owner: ownerName || null,
        amount: amount ? parseInt(amount, 10) : null,
        close_date: closeDate || null,
        priority: priority || null,
        description: description.trim() || null,
        next_step: nextStep.trim() || null,
      };
      if (entityType === "property") body.property_id = entityId;
      else if (entityType === "group") body.group_id = entityId;
      // Deals have no contact_id today; logging from a contact starts a deal without entity link
      const res = await postApi<{ id: string }>("/deals", body);
      navigate(`/deals/${res.id}`);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative ml-auto w-full max-w-md h-full overflow-y-auto bg-[var(--color-background)] border-l border-[var(--gray-6)] p-6">
        <div className="flex items-center justify-between mb-4">
          <Heading size="4">Create deal</Heading>
          <button onClick={onClose} className="p-1 rounded hover:bg-[var(--gray-3)]">
            <X size={18} />
          </button>
        </div>

        <div className="space-y-3">
          <Field label="Name">
            <TextField.Root value={name} onChange={(e) => setName(e.target.value)} />
          </Field>

          <Field label="Stage">
            <Select.Root value={stage} onValueChange={setStage}>
              <Select.Trigger className="w-full" />
              <Select.Content>
                {STAGES.map((s) => (
                  <Select.Item key={s} value={s}>{s.replace(/_/g, " ")}</Select.Item>
                ))}
              </Select.Content>
            </Select.Root>
          </Field>

          <Field label="Amount (CAD)">
            <TextField.Root
              type="number"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="optional"
            />
          </Field>

          <Field label="Close date">
            <TextField.Root type="date" value={closeDate} onChange={(e) => setCloseDate(e.target.value)} />
          </Field>

          <Field label="Priority">
            <Select.Root value={priority || "none"} onValueChange={(v) => setPriority(v === "none" ? "" : v)}>
              <Select.Trigger className="w-full" placeholder="none" />
              <Select.Content>
                <Select.Item value="none">none</Select.Item>
                <Select.Item value="low">low</Select.Item>
                <Select.Item value="medium">medium</Select.Item>
                <Select.Item value="high">high</Select.Item>
              </Select.Content>
            </Select.Root>
          </Field>

          <Field label="Description">
            <TextArea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} />
          </Field>

          <Field label="Next step">
            <TextField.Root value={nextStep} onChange={(e) => setNextStep(e.target.value)} />
          </Field>
        </div>

        <div className="flex justify-end gap-2 mt-6">
          <Button variant="soft" color="gray" onClick={onClose}>Cancel</Button>
          <Button onClick={handleCreate} disabled={saving || !name.trim()}>
            {saving ? "Creating..." : "Create deal"}
          </Button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <Text size="2" weight="medium" className="block mb-1" style={{ color: "var(--gray-11)" }}>
        {label}
      </Text>
      {children}
    </div>
  );
}
```

- [ ] **Step 2: Type-check and commit**

```bash
cd frontend && npx tsc --noEmit 2>&1 | tail -10
cd .. && git add frontend/src/components/crm/CreateDealDrawer.tsx
git commit -m "feat(frontend): CreateDealDrawer — pre-bound to current entity

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 19: QuickActionBar component

**Files:**
- Create: `frontend/src/components/crm/QuickActionBar.tsx`

- [ ] **Step 1: Implement the component**

Create `frontend/src/components/crm/QuickActionBar.tsx`:

```tsx
import { useState } from "react";
import { Button } from "@radix-ui/themes";
import { NotePencil, ListPlus, Briefcase, Tag, Handshake } from "@phosphor-icons/react";
import StarButton from "./StarButton";
import LogActivityDialog from "./LogActivityDialog";
import AddToListDrawer from "./AddToListDrawer";
import CreateDealDrawer from "./CreateDealDrawer";
import type { CrmEntityType } from "../../types";

interface QuickActionBarProps {
  entityType: CrmEntityType;
  entityId: string;
  entityName: string;
  ownerName?: string;
  onCreateSellOpp?: () => void;     // Property only
  onCreateBuyMandate?: () => void;  // Contact + Group only
  onActivityLogged?: () => void;
}

export default function QuickActionBar({
  entityType,
  entityId,
  entityName,
  ownerName,
  onCreateSellOpp,
  onCreateBuyMandate,
  onActivityLogged,
}: QuickActionBarProps) {
  const [showLog, setShowLog] = useState(false);
  const [showAddToList, setShowAddToList] = useState(false);
  const [showCreateDeal, setShowCreateDeal] = useState(false);

  return (
    <>
      <div className="flex items-center gap-2 flex-wrap">
        <StarButton entityType={entityType} entityId={entityId} showLabel />
        <Button size="2" variant="soft" onClick={() => setShowLog(true)}>
          <NotePencil size={14} /> Log activity
        </Button>
        <Button size="2" variant="soft" onClick={() => setShowAddToList(true)}>
          <ListPlus size={14} /> Add to list
        </Button>
        <Button size="2" variant="soft" onClick={() => setShowCreateDeal(true)}>
          <Briefcase size={14} /> Create deal
        </Button>
        {entityType === "property" && onCreateSellOpp && (
          <Button size="2" variant="soft" onClick={onCreateSellOpp}>
            <Tag size={14} /> Sell opportunity
          </Button>
        )}
        {(entityType === "contact" || entityType === "group") && onCreateBuyMandate && (
          <Button size="2" variant="soft" onClick={onCreateBuyMandate}>
            <Handshake size={14} /> Buy mandate
          </Button>
        )}
      </div>

      {showLog && (
        <LogActivityDialog
          entityType={entityType}
          entityId={entityId}
          onClose={() => setShowLog(false)}
          onSaved={() => {
            setShowLog(false);
            onActivityLogged?.();
          }}
        />
      )}
      {showAddToList && (
        <AddToListDrawer
          memberType={entityType}
          memberId={entityId}
          onClose={() => setShowAddToList(false)}
        />
      )}
      {showCreateDeal && (
        <CreateDealDrawer
          entityType={entityType}
          entityId={entityId}
          entityName={entityName}
          ownerName={ownerName}
          onClose={() => setShowCreateDeal(false)}
        />
      )}
    </>
  );
}
```

- [ ] **Step 2: Type-check and commit**

```bash
cd frontend && npx tsc --noEmit 2>&1 | tail -10
cd .. && git add frontend/src/components/crm/QuickActionBar.tsx
git commit -m "feat(frontend): QuickActionBar — shared CRM action surface

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 20: Wire QuickActionBar into PropertyDetailPage

**Files:**
- Modify: `frontend/src/pages/PropertyDetailPage.tsx`

- [ ] **Step 1: Find and replace the dead button row**

In `frontend/src/pages/PropertyDetailPage.tsx`, find this block (around line 545–548):

```tsx
            <Button size="2" variant="soft">Add to List</Button>
            <Button size="2" variant="soft" onClick={() => setShowSellOppDialog(true)}>Sell Opportunity</Button>
            <Button size="2" variant="soft">Create Deal</Button>
```

Replace it with:

```tsx
            <QuickActionBar
              entityType="property"
              entityId={prop.id}
              entityName={prop.display_address}
              onCreateSellOpp={() => setShowSellOppDialog(true)}
            />
```

Also remove or repurpose any neighboring `<Button>` siblings that are about Add to List / Create Deal (they're handled by the bar now).

- [ ] **Step 2: Add the imports at the top of the file**

Find the existing imports section. Add:

```tsx
import QuickActionBar from "../components/crm/QuickActionBar";
import AttributionStrip from "../components/crm/AttributionStrip";
import ActivityFeed from "../components/crm/ActivityFeed";
```

- [ ] **Step 3: Add AttributionStrip near the page header**

Find a sensible spot in the page header (just under the address title and breadcrumbs, above the action bar). Add:

```tsx
<AttributionStrip entityType="property" entityId={prop.id} />
```

- [ ] **Step 4: Add the ActivityFeed card**

Find the page's card layout (typically inside a tab or sidebar). Add a new card:

```tsx
<div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
  <Text size="3" weight="medium" className="mb-3 block">Activity</Text>
  <ActivityFeed entityType="property" entityId={prop.id} />
</div>
```

Place it where it makes sense given the existing card layout — under the AttributionStrip, alongside other cards.

- [ ] **Step 5: Type-check and verify in the browser**

```bash
cd frontend && npx tsc --noEmit 2>&1 | tail -10
```

Expected: clean.

Start the dev servers if they're not already running:

```bash
# Terminal 1
uvicorn cleo.web.app:app --reload --port 8099

# Terminal 2
cd frontend && npm run dev
```

Open `http://localhost:5174/properties` in a browser, navigate into a property, and verify:
1. The QuickActionBar appears with star + log activity + add to list + create deal + sell opportunity buttons
2. Star toggles and persists across reload
3. Log activity dialog opens, can submit a note, the activity appears in the feed
4. Add to list drawer opens, you can create a new personal list and add the property
5. Create deal drawer opens and creates a deal pre-bound to this property

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/PropertyDetailPage.tsx
git commit -m "feat(frontend): wire QuickActionBar onto PropertyDetailPage

Replaces the dead Add to List and Create Deal buttons with the shared
QuickActionBar; adds AttributionStrip and ActivityFeed.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 21: Wire QuickActionBar into ContactDetailPage

**Files:**
- Modify: `frontend/src/pages/ContactDetailPage.tsx`

- [ ] **Step 1: Replace the lone Buy Mandate button**

Find the existing Buy Mandate button (around line 126):

```tsx
          <Button size="1" variant="soft" onClick={() => setShowBuyMandateDialog(true)}>
            Buy Mandate
          </Button>
```

Replace with:

```tsx
          <QuickActionBar
            entityType="contact"
            entityId={contact.id}
            entityName={contact.display_name}
            onCreateBuyMandate={() => setShowBuyMandateDialog(true)}
          />
```

- [ ] **Step 2: Add imports**

```tsx
import QuickActionBar from "../components/crm/QuickActionBar";
import AttributionStrip from "../components/crm/AttributionStrip";
import ActivityFeed from "../components/crm/ActivityFeed";
```

- [ ] **Step 3: Rename the existing "Activity" card and add a real activity feed**

Find the existing card at line 282 that shows transaction stats:

```tsx
          <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
            <Text size="3" weight="medium" className="mb-3 block">Activity</Text>
```

Rename the heading from "Activity" to "Transaction Stats" so it doesn't conflict with the new activity feed:

```tsx
            <Text size="3" weight="medium" className="mb-3 block">Transaction Stats</Text>
```

Then add a new card immediately below this one (still in the left column):

```tsx
          <div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
            <Text size="3" weight="medium" className="mb-3 block">Activity log</Text>
            <ActivityFeed entityType="contact" entityId={contact.id} />
          </div>
```

- [ ] **Step 4: Add AttributionStrip near the existing engaged badge**

Find the engaged badge at line 117 and add `<AttributionStrip>` immediately after it (in the same flex column):

```tsx
<AttributionStrip entityType="contact" entityId={contact.id} />
```

- [ ] **Step 5: Type-check and verify in the browser**

```bash
cd frontend && npx tsc --noEmit 2>&1 | tail -10
```

Open a contact in the browser. Verify:
1. QuickActionBar with star + log + add-to-list + create-deal + buy-mandate
2. Star persists
3. Logging an email-sent activity flips the contact's status badge to "engaged" automatically
4. AttributionStrip shows first/last contacted

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/ContactDetailPage.tsx
git commit -m "feat(frontend): wire QuickActionBar onto ContactDetailPage

Adds AttributionStrip and a real ActivityFeed; renames the legacy
'Activity' stats card to 'Transaction Stats' to avoid confusion.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 22: Wire QuickActionBar into GroupDetailPage

**Files:**
- Modify: `frontend/src/pages/GroupDetailPage.tsx`

- [ ] **Step 1: Inspect current page structure**

```bash
grep -nE "Buy Mandate|Create Deal|Add to List|status === 'engaged'" frontend/src/pages/GroupDetailPage.tsx | head -10
```

The engaged badge is around line 235; the manual Engage button is around line 238.

- [ ] **Step 2: Add imports**

```tsx
import QuickActionBar from "../components/crm/QuickActionBar";
import AttributionStrip from "../components/crm/AttributionStrip";
import ActivityFeed from "../components/crm/ActivityFeed";
```

- [ ] **Step 3: Add QuickActionBar near the page header**

Locate the page-header area (where title + status badge live, around line 230-245). Add the bar right under the title row:

```tsx
<QuickActionBar
  entityType="group"
  entityId={group.id}
  entityName={group.display_name}
  onCreateBuyMandate={
    /* If GroupDetailPage already has a buy-mandate state setter, pass it here. Otherwise pass undefined and skip the button. */
    undefined
  }
/>
<AttributionStrip entityType="group" entityId={group.id} />
```

If `GroupDetailPage` doesn't yet have a buy-mandate dialog wired, leave `onCreateBuyMandate={undefined}` for Phase 1. The bar simply omits the Buy Mandate button when the callback is missing.

- [ ] **Step 4: Add ActivityFeed card**

Below the existing top section, add:

```tsx
<div className="rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5">
  <Text size="3" weight="medium" className="mb-3 block">Activity log</Text>
  <ActivityFeed entityType="group" entityId={group.id} />
</div>
```

Place it in the existing card-stack — alongside the Anchors / Tenures / Members cards.

- [ ] **Step 5: Type-check and verify**

```bash
cd frontend && npx tsc --noEmit 2>&1 | tail -10
```

Open a group in the browser. Verify:
1. QuickActionBar appears (without Buy Mandate button if `onCreateBuyMandate` is undefined)
2. Logging an activity flips the group from `pool` to `engaged`
3. ActivityFeed shows the entry
4. AttributionStrip renders

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/GroupDetailPage.tsx
git commit -m "feat(frontend): wire QuickActionBar onto GroupDetailPage

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 23: QueuePage

**Files:**
- Create: `frontend/src/pages/QueuePage.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create the page**

Create `frontend/src/pages/QueuePage.tsx`:

```tsx
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Badge, Button, Heading, Text } from "@radix-ui/themes";
import { Star, Warning } from "@phosphor-icons/react";
import { fetchApi, mutateApi } from "../api/client";
import type { UserStar, CrmEntityType } from "../types";
import { formatDate } from "../lib/utils";

const TYPE_LABEL: Record<CrmEntityType, string> = {
  contact: "Contact",
  property: "Property",
  group: "Group",
};

const TYPE_PATH: Record<CrmEntityType, string> = {
  contact: "/contacts",
  property: "/properties",
  group: "/groups",
};

type Filter = "all" | CrmEntityType;

export default function QueuePage() {
  const [stars, setStars] = useState<UserStar[] | null>(null);
  const [filter, setFilter] = useState<Filter>("all");

  const load = () => {
    fetchApi<UserStar[]>("/stars").then(setStars);
  };

  useEffect(() => {
    load();
    const handler = () => load();
    window.addEventListener("crm-star-changed", handler);
    return () => window.removeEventListener("crm-star-changed", handler);
  }, []);

  if (stars === null) {
    return (
      <div className="p-6">
        <Text size="2" style={{ color: "var(--gray-9)" }}>Loading…</Text>
      </div>
    );
  }

  const filtered = filter === "all" ? stars : stars.filter((s) => s.entity_type === filter);

  async function handleUnstar(s: UserStar) {
    await mutateApi(`/stars/${s.entity_type}/${encodeURIComponent(s.entity_id)}`, "DELETE");
    window.dispatchEvent(
      new CustomEvent("crm-star-changed", {
        detail: { entity_type: s.entity_type, entity_id: s.entity_id },
      })
    );
  }

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="mb-4">
        <Heading size="6">Queue</Heading>
        <Text size="2" style={{ color: "var(--gray-9)" }}>
          Your personal to-touch list. Star any contact, property, or group to add it.
          Items auto-clear when you log an activity that references them.
        </Text>
      </div>

      <div className="flex gap-2 mb-4">
        {(["all", "contact", "property", "group"] as Filter[]).map((f) => (
          <Button
            key={f}
            size="2"
            variant={filter === f ? "solid" : "soft"}
            onClick={() => setFilter(f)}
          >
            {f === "all" ? `All (${stars.length})` : TYPE_LABEL[f]}
          </Button>
        ))}
      </div>

      {filtered.length === 0 && (
        <div className="border border-[var(--gray-6)] rounded-[var(--card-radius)] p-8 text-center">
          <Text size="3" style={{ color: "var(--gray-9)" }}>
            Nothing in your queue. Hit the ⭐ on any contact, property, or group to add it here.
          </Text>
        </div>
      )}

      <div className="flex flex-col gap-2">
        {filtered.map((s) => (
          <Link
            key={`${s.entity_type}:${s.entity_id}`}
            to={`${TYPE_PATH[s.entity_type]}/${s.entity_id}`}
            className="block p-4 rounded-[var(--card-radius)] border border-[var(--gray-6)] hover:bg-[var(--gray-2)] transition-colors no-underline"
          >
            <div className="flex justify-between items-start gap-3">
              <div className="flex items-start gap-2 flex-1">
                <Star size={18} weight="fill" style={{ color: "var(--accent-11)", marginTop: 2 }} />
                <div className="flex flex-col gap-1 flex-1">
                  <Text size="3" weight="medium">{s.name ?? s.entity_id}</Text>
                  <Text size="1" style={{ color: "var(--gray-9)" }}>
                    {TYPE_LABEL[s.entity_type]}
                    {s.detail ? ` · ${s.detail}` : ""}
                    {` · Starred ${formatDate(s.starred_at)}`}
                  </Text>
                  {s.team_activity && (
                    <div className="flex items-center gap-1 mt-1">
                      <Warning size={14} style={{ color: "var(--amber-11)" }} />
                      <Text size="1" style={{ color: "var(--amber-11)" }}>
                        {s.team_activity.by_user_name} engaged {formatDate(s.team_activity.happened_at)} —{" "}
                        {s.team_activity.activity_type}
                        {s.team_activity.outcome ? ` → ${s.team_activity.outcome}` : ""}
                      </Text>
                    </div>
                  )}
                </div>
              </div>
              <Button
                size="1"
                variant="soft"
                color="gray"
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  handleUnstar(s);
                }}
              >
                Remove
              </Button>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Register the route**

In `frontend/src/App.tsx`, find the existing routes inside `<Route element={<AppLayout />}>`. Add an import at the top (alongside other page imports — direct, not lazy):

```tsx
import QueuePage from "./pages/QueuePage";
```

Add the route inside the AppLayout block, near the Dashboard / Lists routes:

```tsx
<Route path="/queue" element={<QueuePage />} />
```

- [ ] **Step 3: Type-check and verify**

```bash
cd frontend && npx tsc --noEmit 2>&1 | tail -10
```

Open `http://localhost:5174/queue` in the browser. Star a few entities from their detail pages, then come back to /queue:
1. Stars appear, sorted by starred_at desc
2. Click a row → navigates to the entity
3. Click Remove → unstar persists
4. Have a teammate (or the same user from a different fixture) log an activity AFTER you starred something — the team_activity warning row should appear

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/QueuePage.tsx frontend/src/App.tsx
git commit -m "feat(frontend): /queue page — personal star queue with type filter

Single cross-entity-type queue (contacts, properties, groups). Surfaces
'Engaged by teammate' warning rows when a teammate has touched a
starred entity since you starred it.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 24: Sidebar Queue entry

**Files:**
- Modify: the sidebar component (location: see Step 1)

- [ ] **Step 1: Locate the sidebar component**

```bash
grep -lE "Dashboard|Sidebar|Lists" frontend/src/components/layout/ frontend/src/components/ 2>/dev/null
ls frontend/src/components/layout/
```

The sidebar likely lives at `frontend/src/components/layout/Sidebar.tsx` (or similar — confirm by searching the imports of `AppLayout.tsx`):

```bash
grep -nE "import.*[Ss]idebar" frontend/src/components/layout/AppLayout.tsx
```

Record the file path before editing.

- [ ] **Step 2: Add the Queue entry**

Open the sidebar file. Find the existing nav items (Dashboard, Lists, Deals, etc.). Add a Queue entry between Dashboard and Lists. The exact JSX depends on the file's pattern — match the surrounding entries.

Sample (adjust to the file's actual `<NavLink>` / `<Link>` pattern):

```tsx
import { Star } from "@phosphor-icons/react";

// ... inside the nav list, between Dashboard and Lists ...
<NavLink to="/queue" className={navItemClass}>
  <Star size={16} />
  <span>Queue</span>
</NavLink>
```

If there's a per-item count badge pattern in the existing sidebar, optionally also fetch `/api/stars` count and render a small badge. If the sidebar already has a count-badge utility, reuse it; otherwise skip the badge and rely on the page itself.

- [ ] **Step 3: Type-check and verify**

```bash
cd frontend && npx tsc --noEmit 2>&1 | tail -10
```

Reload the browser. Confirm Queue appears in the sidebar between Dashboard and Lists, navigates to `/queue` on click.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/  # path will be specific to the sidebar file
git commit -m "feat(frontend): sidebar Queue entry

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 25: End-to-end manual smoke test

**Files:** none (verification only)

- [ ] **Step 1: Run the full backend suite**

```bash
pytest tests/ --ignore=tests/test_discovery_v2_expansion.py 2>&1 | tail -5
```

Expected: green.

- [ ] **Step 2: Type-check frontend**

```bash
cd frontend && npx tsc --noEmit 2>&1 | tail -10
```

Expected: clean.

- [ ] **Step 3: Restart both dev servers**

```bash
# kill any existing
pkill -f "uvicorn cleo.web.app"
pkill -f "vite"

# bring them up
uvicorn cleo.web.app:app --reload --port 8099 &
cd frontend && npm run dev &
cd ..
```

Wait ~5 seconds, then:

```bash
curl -s http://localhost:8099/api/healthz || echo "NO HEALTHZ"
curl -s http://localhost:5174/ | head -5
```

Expected: backend responds; frontend serves the index page.

- [ ] **Step 4: Manual end-to-end smoke (the Peter Vicano flow)**

Open the browser at `http://localhost:5174/`. Log in. Then:

1. Navigate to a property (e.g., `/properties` → click any row).
   - Verify QuickActionBar renders.
   - Verify AttributionStrip renders ("Never contacted" expected for a fresh prop).
   - Verify ActivityFeed renders (empty).
2. Click ⭐ Star. Confirm icon fills.
3. Visit `/queue`. Confirm the property appears.
4. Back to the property. Click Log activity → choose "email" + "email_sent" + summary "Emailed Peter re: feeler" → save.
5. Verify:
   - The activity appears in the property's ActivityFeed
   - AttributionStrip now shows "First contacted: <you> — email → email_sent"
   - Going to `/queue`, the property is GONE (auto-removed because YOU logged the activity)
6. Navigate to a contact (`/contacts` → pick one with `status='pool'`).
7. Click Star, then Log activity → "call" → "connected".
8. Verify:
   - Contact's status badge flips to `engaged`
   - Contact disappears from `/queue`
   - `AttributionStrip` shows your call
9. Click Add to List on a property. Create a new "personal" list "Brandon's Q3 prospects". Confirm the property is added. Refresh the drawer → confirm it's pre-checked.
10. Click Add to List again. Toggle the personal list off. Confirm removal.
11. Click Create deal. Set name + stage = priority_deal + amount = 1500000. Submit. Confirm redirect to `/deals/<id>`.

If any step fails, the corresponding task is incomplete — fix before proceeding.

- [ ] **Step 5: Open a PR (optional but recommended)**

```bash
git push -u origin feat/crm-daily-outreach-phase-1
gh pr create --title "CRM daily-outreach Phase 1: stars, queue, attribution, wired CTAs" --body "$(cat <<'EOF'
## Summary
Phase 1 of the CRM daily-outreach plan from
docs/superpowers/specs/2026-05-05-crm-daily-outreach-design.md.

- Migration 020 — user_stars + lists.scope/owner_user_id +
  activities.{contact,property,group}_id + audit columns
- /api/stars router (per-user queue with team-activity enrichment)
- Lists: personal/shared scope, owner-only metadata edits
- Activities: 'property' allowed; FK auto-population; auto-engage;
  star auto-remove
- Manual engage on contacts/groups writes a synthetic note activity
- Attribution endpoints on contacts/properties/groups
- Frontend: QuickActionBar, StarButton, AttributionStrip,
  AddToListDrawer, CreateDealDrawer wired onto Property/Contact/Group
  detail pages
- New /queue page + sidebar entry

## Test plan
- [ ] Backend pytest all green
- [ ] frontend tsc clean
- [ ] Manual smoke: star → log activity → auto-remove from queue
- [ ] Manual smoke: pool contact → log activity → status flips to engaged
- [ ] Manual smoke: shared list visible to other user; personal list hidden
- [ ] Manual smoke: Create deal pre-bound to property

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-Review Checklist (run after writing the plan)

- **Spec coverage:** every section 1-9 of the spec has a task. Section 1 → Tasks 1-3. Section 2.1 (stars) → Tasks 4-5. Section 2.2 (lists) → Tasks 6-7. Section 2.3 (activities) → Tasks 8-9. Section 2.4 (synthetic engage) → Tasks 10-11. Section 2.5 (attribution) → Tasks 12-13. Section 3 (frontend components) → Tasks 14-19. Section 4 (page wiring) → Tasks 20-22. Section 5 (queue + sidebar) → Tasks 23-24. Section 8 (testing) → embedded in each backend task as TDD; manual smoke = Task 25.
- **No placeholders** — every step has executable content. Sidebar in Task 24 is the only soft spot ("location varies"); Step 1 of that task gives a grep command to locate it before editing.
- **Type consistency** — `CrmEntityType`, `UserStar`, `ListSummary`, `AttributionResponse`, `ContactEvent`, `TeamActivity` defined in Task 14 and used consistently in Tasks 15-19, 23.

---

**Plan complete. Saved to `docs/superpowers/plans/2026-05-05-crm-daily-outreach-phase-1.md`.**
