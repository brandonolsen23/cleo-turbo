"""End-to-end runner integration test."""
import sqlite3


def _make_db_with_two_kingsett_sides():
    """Minimal corpus: two party-sides sharing 'kingsett' brand_token."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE app_meta (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT);
        CREATE TABLE party_fingerprints (
            source_id TEXT, side TEXT,
            street_number TEXT, street_name TEXT, street_suffix TEXT,
            street_direction TEXT, suite_type TEXT, suite_number TEXT,
            city TEXT, province TEXT, postal TEXT, postal_raw TEXT,
            country TEXT, phone TEXT, contact_fingerprint TEXT,
            sale_date TEXT, computed_at TEXT,
            PRIMARY KEY (source_id, side)
        );
        CREATE TABLE party_atoms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT, side TEXT,
            atom_type TEXT, atom_value TEXT, source_field TEXT
        );
        CREATE TABLE atom_groups (
            id TEXT PRIMARY KEY, canonical_brand TEXT, display_name TEXT,
            first_seen TEXT, last_seen TEXT, party_side_count INTEGER,
            discovered_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE atom_contacts (
            id TEXT PRIMARY KEY, canonical_name TEXT, display_name TEXT,
            first_seen TEXT, last_seen TEXT, party_side_count INTEGER,
            discovered_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE atom_party_entities (
            source_id TEXT, side TEXT, group_id TEXT, contact_id TEXT,
            group_link_tier TEXT, contact_link_tier TEXT,
            PRIMARY KEY (source_id, side)
        );
        CREATE TABLE atom_group_addresses (group_id TEXT, postal TEXT,
            street_number TEXT, street_name TEXT, street_suffix TEXT,
            first_seen TEXT, last_seen TEXT, n_observations INTEGER);
        CREATE TABLE atom_group_phones (group_id TEXT, phone TEXT,
            first_seen TEXT, last_seen TEXT, n_observations INTEGER);
        CREATE TABLE atom_group_contacts (group_id TEXT, contact_id TEXT,
            first_seen TEXT, last_seen TEXT, n_observations INTEGER);
        CREATE TABLE atom_contact_groups (contact_id TEXT, group_id TEXT,
            first_seen TEXT, last_seen TEXT, n_observations INTEGER);
        CREATE TABLE atom_contact_addresses (contact_id TEXT, postal TEXT,
            street_number TEXT, street_name TEXT, street_suffix TEXT,
            first_seen TEXT, last_seen TEXT, n_observations INTEGER);
        CREATE TABLE atom_group_relationships (
            group_a_id TEXT, group_b_id TEXT, kind TEXT,
            first_seen TEXT, last_seen TEXT, n_party_sides INTEGER,
            PRIMARY KEY (group_a_id, group_b_id, kind)
        );
        CREATE TABLE atom_discovery_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            config_version TEXT, config_snapshot TEXT,
            ran_at TEXT DEFAULT (datetime('now')),
            n_party_sides INTEGER, n_groups INTEGER, n_contacts INTEGER,
            audit_metrics TEXT, notes TEXT
        );
    """)
    for sid, date in [("RT1", "2020-01-01"), ("RT2", "2022-06-15")]:
        conn.execute(
            "INSERT INTO party_fingerprints (source_id, side, sale_date) "
            "VALUES (?, 'buyer', ?)",
            (sid, date),
        )
        conn.execute(
            "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
            "VALUES (?, 'buyer', 'brand_token', 'kingsett', 'party_name')",
            (sid,),
        )
        conn.execute(
            "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
            "VALUES (?, 'buyer', 'brand_phrase', 'kingsett capital', 'party_name')",
            (sid,),
        )
    conn.commit()
    return conn


def test_runner_produces_one_group_from_two_kingsett_sides():
    from cleo.discovery_v2.runner import run_discovery

    conn = _make_db_with_two_kingsett_sides()
    run_discovery(conn, min_idf=0.0, verbose=False)

    groups = conn.execute("SELECT id, canonical_brand, party_side_count FROM atom_groups").fetchall()
    assert len(groups) == 1
    assert groups[0]["canonical_brand"] == "kingsett capital"
    assert groups[0]["party_side_count"] == 2

    party_sides = conn.execute("SELECT group_id FROM atom_party_entities").fetchall()
    assert len(party_sides) == 2
    assert all(p["group_id"] == groups[0]["id"] for p in party_sides)

    runs = conn.execute("SELECT n_party_sides, n_groups FROM atom_discovery_runs").fetchall()
    assert len(runs) == 1
    assert runs[0]["n_party_sides"] == 2
    assert runs[0]["n_groups"] == 1
