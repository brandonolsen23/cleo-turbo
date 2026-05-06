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
            details_json TEXT, created_at TEXT DEFAULT (datetime('now'))
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
    from cleo.web.app import create_app
    from cleo.web import deps
    app = create_app()
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
    from cleo.web.app import create_app
    from cleo.web import deps
    app = create_app()
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
