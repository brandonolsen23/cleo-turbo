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
