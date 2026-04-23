"""Tests for entity assignment."""
import sqlite3


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE app_meta (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT);
        CREATE TABLE party_fingerprints (
            source_id TEXT, side TEXT, sale_date TEXT,
            contact_fingerprint TEXT,
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
        CREATE TABLE atom_contacts (
            id TEXT PRIMARY KEY,
            canonical_name TEXT, display_name TEXT,
            first_seen TEXT, last_seen TEXT,
            party_side_count INTEGER, discovered_at TEXT
        );
        CREATE TABLE atom_party_entities (
            source_id TEXT, side TEXT, group_id TEXT, contact_id TEXT,
            group_link_tier TEXT, contact_link_tier TEXT,
            PRIMARY KEY (source_id, side)
        );
    """)
    return conn


def test_group_canonical_brand_is_most_common_nongeneric_phrase():
    from cleo.discovery_v2.entities import assign_group_entities

    conn = _make_db()
    # 3 party-sides, all in one Group component. brand_phrases:
    #  RT1: "kingsett capital" (non-generic)
    #  RT2: "kingsett capital" (non-generic)
    #  RT3: "holdings"         (generic — below idf threshold)
    for sid, date in [("RT1", "2020-01-01"), ("RT2", "2022-06-15"), ("RT3", "2023-03-01")]:
        conn.execute(
            "INSERT INTO party_fingerprints (source_id, side, sale_date) VALUES (?, 'buyer', ?)",
            (sid, date),
        )
    for sid, phrase in [
        ("RT1", "kingsett capital"), ("RT2", "kingsett capital"), ("RT3", "holdings"),
    ]:
        conn.execute(
            "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
            "VALUES (?, 'buyer', 'brand_phrase', ?, 'party_name')",
            (sid, phrase),
        )

    components = {0: [("RT1", "buyer"), ("RT2", "buyer"), ("RT3", "buyer")]}
    idf_map = {
        ("brand_phrase", "kingsett capital"): 7.0,
        ("brand_phrase", "holdings"): 1.0,
    }
    min_idf = 3.0

    assign_group_entities(conn, components, idf_map, min_idf, tier_by_pair={})
    row = conn.execute(
        "SELECT id, canonical_brand, display_name, first_seen, last_seen, party_side_count "
        "FROM atom_groups"
    ).fetchone()
    assert row is not None
    assert row["canonical_brand"] == "kingsett capital"
    assert row["first_seen"] == "2020-01-01"
    assert row["last_seen"] == "2023-03-01"
    assert row["party_side_count"] == 3
    assert row["id"].startswith("AGR_")


def test_group_id_counter_persists_via_app_meta():
    from cleo.discovery_v2.entities import assign_group_entities

    conn = _make_db()
    conn.execute(
        "INSERT INTO app_meta (key, value, updated_at) VALUES ('next_agr_id', '1000', datetime('now'))"
    )
    conn.execute("INSERT INTO party_fingerprints (source_id, side, sale_date) VALUES ('RT1', 'buyer', '2020-01-01')")
    conn.execute(
        "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
        "VALUES ('RT1', 'buyer', 'brand_phrase', 'kingsett capital', 'party_name')"
    )

    components = {0: [("RT1", "buyer")]}
    assign_group_entities(conn, components, {("brand_phrase", "kingsett capital"): 7.0}, 3.0, tier_by_pair={})
    row = conn.execute("SELECT id FROM atom_groups").fetchone()
    assert row["id"] == "AGR_01000"
    next_counter = conn.execute(
        "SELECT value FROM app_meta WHERE key = 'next_agr_id'"
    ).fetchone()[0]
    assert int(next_counter) == 1001
