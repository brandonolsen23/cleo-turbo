"""Tests for /api/explorer/brands endpoints."""
import sqlite3
import pytest
from fastapi.testclient import TestClient


def _seeded_db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE party_fingerprints (
            source_id TEXT, side TEXT, phone TEXT, contact_fingerprint TEXT,
            postal TEXT, sale_date TEXT, street_number TEXT, street_name TEXT,
            street_suffix TEXT,
            PRIMARY KEY (source_id, side)
        );
        CREATE TABLE party_atoms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT, side TEXT,
            atom_type TEXT, atom_value TEXT, source_field TEXT
        );
        CREATE TABLE brand_token_index (
            token TEXT, source_id TEXT, side TEXT,
            PRIMARY KEY (token, source_id, side)
        );
        CREATE TABLE brand_token_summary (
            token TEXT PRIMARY KEY, idf REAL, n_party_sides INTEGER,
            n_distinct_phrases INTEGER, is_distinctive INTEGER, is_excluded INTEGER,
            discovered_at TEXT
        );
    """)
    # seed: kingsett (2 sides), ontario (3 sides), rasenberg (2 sides)
    conn.execute(
        "INSERT INTO brand_token_summary VALUES ('kingsett', 6.5, 2, 2, 1, 0, '2026-04-23')"
    )
    conn.execute(
        "INSERT INTO brand_token_summary VALUES ('rasenberg', 5.2, 2, 1, 1, 0, '2026-04-23')"
    )
    conn.execute(
        "INSERT INTO brand_token_summary VALUES ('ontario', 0.8, 3, 3, 0, 0, '2026-04-23')"
    )
    for sid, tok, phrase in [
        ("RT1", "kingsett", "kingsett capital"),
        ("RT2", "kingsett", "kingsett wealth"),
        ("RT3", "rasenberg", "rasenberg investments"),
        ("RT4", "rasenberg", "rasenberg investments"),
        ("RT5", "ontario", "1234567 ontario"),
        ("RT6", "ontario", "2345678 ontario"),
        ("RT7", "ontario", "3456789 ontario"),
    ]:
        conn.execute(
            "INSERT INTO party_fingerprints (source_id, side, sale_date) "
            "VALUES (?, 'buyer', '2020-01-01')", (sid,)
        )
        conn.execute(
            "INSERT INTO brand_token_index (token, source_id, side) VALUES (?, ?, 'buyer')",
            (tok, sid),
        )
        conn.execute(
            "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
            "VALUES (?, 'buyer', 'brand_phrase', ?, 'party_name')", (sid, phrase)
        )
    conn.commit()
    return conn


@pytest.fixture
def client():
    """TestClient with a seeded in-memory DB injected via dependency override."""
    from cleo.web.app import app
    from cleo.web import deps

    conn = _seeded_db()

    def _get_conn_override():
        yield conn

    app.dependency_overrides[deps.get_db] = _get_conn_override
    # Bypass auth for these tests — explorer routes don't need a real user.
    app.dependency_overrides[deps.get_current_user] = lambda: {"email": "test"}
    yield TestClient(app)
    app.dependency_overrides.clear()
    conn.close()


def test_list_distinctive_tokens_descending_by_count(client):
    resp = client.get("/api/explorer/brands", params={"distinctive_only": "true"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    tokens = [t["token"] for t in body["results"]]
    # Both kingsett and rasenberg have n_party_sides=2; tiebreak alphabetical ASC.
    assert tokens == ["kingsett", "rasenberg"]


def test_list_all_tokens_includes_nondistinctive(client):
    resp = client.get("/api/explorer/brands", params={"distinctive_only": "false"})
    body = resp.json()
    assert body["total"] == 3
    tokens = {t["token"] for t in body["results"]}
    assert tokens == {"kingsett", "rasenberg", "ontario"}


def test_list_search_filter(client):
    resp = client.get("/api/explorer/brands", params={"q": "king", "distinctive_only": "false"})
    body = resp.json()
    tokens = [t["token"] for t in body["results"]]
    assert tokens == ["kingsett"]


def test_detail_returns_party_sides_and_phrases(client):
    resp = client.get("/api/explorer/brands/kingsett")
    assert resp.status_code == 200
    body = resp.json()
    assert body["token"] == "kingsett"
    assert body["n_party_sides"] == 2
    assert set(body["phrases"]) == {"kingsett capital", "kingsett wealth"}
    ps_keys = {(p["source_id"], p["side"]) for p in body["party_sides"]}
    assert ps_keys == {("RT1", "buyer"), ("RT2", "buyer")}


def test_detail_unknown_token_returns_404(client):
    resp = client.get("/api/explorer/brands/nonesuch")
    assert resp.status_code == 404
