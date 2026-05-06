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
            details_json TEXT, created_at TEXT
        );
        INSERT INTO users (id, username, display_name, password_hash, role)
            VALUES (1, 'brandon', 'Brandon', 'x', 'editor');
        INSERT INTO contacts (id, display_name) VALUES ('CON_1', 'Peter Vicano');
        INSERT INTO groups (id, display_name) VALUES ('GRP_1', 'DH Management');
    """)
    conn.commit()
    return conn


def _client(conn):
    from cleo.web.app import create_app
    from cleo.web import deps
    app = create_app()

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
