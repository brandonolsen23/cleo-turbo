"""Tests for address_unit URL canonicalization shim (Task 9).

Verifies that legacy 7-tuple keys with noisy city names (scarborough vs toronto)
or suite_type synonyms (unit vs suite) still resolve to the canonical row.
"""
import sqlite3
import pytest
from fastapi.testclient import TestClient


def _seeded_db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE party_fingerprints (
            source_id TEXT, side TEXT, phone TEXT, contact_fingerprint TEXT,
            postal TEXT, sale_date TEXT, city TEXT,
            street_number TEXT, street_name TEXT, street_suffix TEXT, street_direction TEXT,
            suite_type TEXT, suite_number TEXT,
            party_address_canonical TEXT,
            PRIMARY KEY (source_id, side)
        );
        CREATE TABLE party_atoms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT, side TEXT,
            atom_type TEXT, atom_value TEXT, source_field TEXT
        );
        CREATE TABLE address_unit_summary (
            city TEXT NOT NULL,
            street_number TEXT NOT NULL,
            street_name TEXT NOT NULL,
            street_suffix TEXT NOT NULL DEFAULT '',
            street_direction TEXT NOT NULL DEFAULT '',
            suite_type TEXT NOT NULL DEFAULT '',
            suite_number TEXT NOT NULL DEFAULT '',
            n_party_sides INTEGER NOT NULL,
            n_distinct_brand_stems INTEGER NOT NULL,
            dominant_stem TEXT,
            dominance_share REAL,
            discovered_at TEXT,
            PRIMARY KEY (city, street_number, street_name, street_suffix,
                         street_direction, suite_type, suite_number)
        );
        CREATE TABLE auto_groups (
            auto_group_id TEXT PRIMARY KEY, canonical_stem TEXT NOT NULL,
            display_name TEXT NOT NULL, tier TEXT NOT NULL,
            confidence REAL NOT NULL, n_anchors INTEGER NOT NULL,
            n_members INTEGER NOT NULL, discovered_at TEXT
        );
        CREATE TABLE auto_group_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            auto_group_id TEXT NOT NULL,
            member_type TEXT NOT NULL,
            source_id TEXT, side TEXT, corp_name TEXT,
            match_score REAL NOT NULL
        );
        CREATE TABLE auto_group_anchor_tenures (
            id                          INTEGER PRIMARY KEY AUTOINCREMENT,
            auto_group_id               TEXT NOT NULL,
            anchor_type                 TEXT NOT NULL,
            anchor_value                TEXT NOT NULL,
            start_date                  TEXT NOT NULL,
            end_date                    TEXT,
            n_party_sides_in_window     INTEGER NOT NULL,
            dominance_share_in_window   REAL NOT NULL,
            score                       REAL NOT NULL,
            discovered_at               TEXT DEFAULT (datetime('now'))
        );
    """)

    # Canonical row in address_unit_summary (what migration 019 stores).
    conn.execute(
        """INSERT INTO address_unit_summary
            (city, street_number, street_name, street_suffix, street_direction,
             suite_type, suite_number, n_party_sides, n_distinct_brand_stems,
             dominant_stem, dominance_share)
           VALUES ('toronto','2555','eglinton','avenue','east','suite','212',
                   3, 1, 'dh management', 1.0)""",
    )

    # party_fingerprints row with canonical key so timeline can find it.
    conn.execute(
        """INSERT INTO party_fingerprints
            (source_id, side, sale_date, party_address_canonical)
           VALUES ('RT999', 'buyer', '2023-06-01',
                   'toronto|2555|eglinton|avenue|east|suite|212')""",
    )

    conn.commit()
    return conn


@pytest.fixture
def client():
    """TestClient with canonical-address seeded in-memory DB."""
    from cleo.web.app import app
    from cleo.web import deps

    conn = _seeded_db()

    def _get_conn_override():
        yield conn

    app.dependency_overrides[deps.get_db] = _get_conn_override
    app.dependency_overrides[deps.get_current_user] = lambda: {"email": "test"}
    yield TestClient(app)
    app.dependency_overrides.clear()
    conn.close()


# ── address_unit_detail canonicalization ─────────────────────────────────────

def test_address_unit_detail_canonicalizes_legacy_key(client):
    """A legacy URL with noisy city+suite_type still resolves to the
    canonical row in address_unit_summary."""
    response = client.get(
        "/api/explorer/addresses/units/scarborough|2555|eglinton|avenue|east|unit|212"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["city"] == "toronto"
    assert data["suite_type"] == "suite"


def test_address_unit_detail_already_canonical_key(client):
    """A key that is already canonical resolves identically (idempotent)."""
    response = client.get(
        "/api/explorer/addresses/units/toronto|2555|eglinton|avenue|east|suite|212"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["city"] == "toronto"
    assert data["suite_type"] == "suite"


def test_address_unit_detail_leading_zero_stripped(client):
    """Suite number '0212' in the URL is stripped to '212' before lookup."""
    response = client.get(
        "/api/explorer/addresses/units/toronto|2555|eglinton|avenue|east|suite|0212"
    )
    assert response.status_code == 200
    assert response.json()["suite_number"] == "212"


def test_address_unit_detail_unknown_unit_returns_404(client):
    """A key that doesn't exist after canonicalization returns 404."""
    response = client.get(
        "/api/explorer/addresses/units/toronto|9999|fake|street|east|suite|1"
    )
    assert response.status_code == 404


# ── address_unit_timeline canonicalization ───────────────────────────────────

def test_address_unit_timeline_canonicalizes_legacy_key(client):
    """A legacy URL key resolves to timeline events via party_address_canonical."""
    response = client.get(
        "/api/explorer/addresses/units/scarborough|2555|eglinton|avenue|east|unit|212/timeline"
    )
    assert response.status_code == 200
    data = response.json()
    # The returned 'value' is the canonicalized key, not the raw legacy key.
    assert data["value"] == "toronto|2555|eglinton|avenue|east|suite|212"
    assert data["anchor_type"] == "address_unit"
    assert "events" in data
    assert "tenures" in data


def test_address_unit_timeline_already_canonical_key(client):
    """A canonical key resolves without transformation."""
    response = client.get(
        "/api/explorer/addresses/units/toronto|2555|eglinton|avenue|east|suite|212/timeline"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["value"] == "toronto|2555|eglinton|avenue|east|suite|212"


def test_address_unit_timeline_unknown_unit_returns_404(client):
    """Timeline for an unknown unit returns 404."""
    response = client.get(
        "/api/explorer/addresses/units/toronto|9999|fake|street|east|suite|1/timeline"
    )
    assert response.status_code == 404
