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
