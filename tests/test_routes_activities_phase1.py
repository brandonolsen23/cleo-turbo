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
            details_json TEXT, created_at TEXT
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
    from cleo.web.app import create_app
    from cleo.web import deps
    app = create_app()

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
