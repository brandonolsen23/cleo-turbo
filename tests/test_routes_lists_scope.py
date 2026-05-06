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
            details_json TEXT, created_at TEXT
        );
        INSERT INTO users (id, username, display_name, password_hash, role)
            VALUES (1, 'brandon', 'Brandon', 'x', 'editor'),
                   (2, 'jamie',   'Jamie',   'x', 'editor');
        INSERT INTO contacts (id, display_name) VALUES ('CON_1', 'Peter Vicano');
    """)
    conn.commit()
    return conn


def _client(conn, sub):
    from cleo.web.app import create_app
    from cleo.web import deps
    app = create_app()

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
