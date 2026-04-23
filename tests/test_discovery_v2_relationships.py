"""Tests for JV relationship detection."""
import sqlite3


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE party_fingerprints (
            source_id TEXT, side TEXT, sale_date TEXT,
            PRIMARY KEY (source_id, side)
        );
        CREATE TABLE party_atoms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT, side TEXT,
            atom_type TEXT, atom_value TEXT, source_field TEXT
        );
        CREATE TABLE atom_groups (
            id TEXT PRIMARY KEY,
            canonical_brand TEXT, display_name TEXT,
            first_seen TEXT, last_seen TEXT,
            party_side_count INTEGER, discovered_at TEXT
        );
        CREATE TABLE atom_party_entities (
            source_id TEXT, side TEXT, group_id TEXT, contact_id TEXT,
            group_link_tier TEXT, contact_link_tier TEXT,
            PRIMARY KEY (source_id, side)
        );
        CREATE TABLE atom_group_relationships (
            group_a_id TEXT, group_b_id TEXT, kind TEXT,
            first_seen TEXT, last_seen TEXT, n_party_sides INTEGER,
            PRIMARY KEY (group_a_id, group_b_id, kind)
        );
    """)
    return conn


def test_multi_brand_phrase_party_side_emits_jv_edge():
    from cleo.discovery_v2.relationships import detect_jv_relationships

    conn = _make_db()
    # RT1 has both "kingsett capital" and "canderel" brand_phrases.
    conn.execute(
        "INSERT INTO party_fingerprints (source_id, side, sale_date) VALUES ('RT1', 'buyer', '2015-06-01')"
    )
    conn.execute(
        "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
        "VALUES ('RT1', 'buyer', 'brand_phrase', 'kingsett capital', 'party_name')"
    )
    conn.execute(
        "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
        "VALUES ('RT1', 'buyer', 'brand_phrase', 'canderel', 'companies_json')"
    )
    conn.execute(
        "INSERT INTO atom_party_entities (source_id, side, group_id) "
        "VALUES ('RT1', 'buyer', 'AGR_01')"
    )
    # Both Groups exist in atom_groups
    conn.execute(
        "INSERT INTO atom_groups (id, canonical_brand, display_name, party_side_count) "
        "VALUES ('AGR_01', 'kingsett capital', 'Kingsett Capital', 1)"
    )
    # A second party-side establishes canderel as its own Group AGR_02
    conn.execute(
        "INSERT INTO party_fingerprints (source_id, side, sale_date) VALUES ('RT2', 'buyer', '2017-03-01')"
    )
    conn.execute(
        "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
        "VALUES ('RT2', 'buyer', 'brand_phrase', 'canderel', 'party_name')"
    )
    conn.execute(
        "INSERT INTO atom_party_entities (source_id, side, group_id) VALUES ('RT2', 'buyer', 'AGR_02')"
    )
    conn.execute(
        "INSERT INTO atom_groups (id, canonical_brand, display_name, party_side_count) "
        "VALUES ('AGR_02', 'canderel', 'Canderel', 1)"
    )
    conn.commit()

    detect_jv_relationships(conn)

    rows = conn.execute(
        "SELECT group_a_id, group_b_id, kind, n_party_sides FROM atom_group_relationships"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["kind"] == "jv"
    assert {rows[0]["group_a_id"], rows[0]["group_b_id"]} == {"AGR_01", "AGR_02"}
    assert rows[0]["n_party_sides"] == 1


def test_single_brand_party_side_emits_no_jv():
    from cleo.discovery_v2.relationships import detect_jv_relationships

    conn = _make_db()
    conn.execute(
        "INSERT INTO party_fingerprints (source_id, side, sale_date) VALUES ('RT1', 'buyer', '2015-06-01')"
    )
    conn.execute(
        "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
        "VALUES ('RT1', 'buyer', 'brand_phrase', 'kingsett capital', 'party_name')"
    )
    conn.execute(
        "INSERT INTO atom_party_entities (source_id, side, group_id) VALUES ('RT1', 'buyer', 'AGR_01')"
    )
    conn.execute(
        "INSERT INTO atom_groups (id, canonical_brand, display_name, party_side_count) "
        "VALUES ('AGR_01', 'kingsett capital', 'Kingsett Capital', 1)"
    )
    conn.commit()

    detect_jv_relationships(conn)

    rows = conn.execute("SELECT * FROM atom_group_relationships").fetchall()
    assert rows == []
