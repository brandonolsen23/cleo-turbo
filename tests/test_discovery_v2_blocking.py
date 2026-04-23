"""Tests for candidate pair blocking."""
import sqlite3


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE party_fingerprints (
            source_id TEXT, side TEXT,
            street_number TEXT, street_name TEXT, street_suffix TEXT,
            phone TEXT, contact_fingerprint TEXT,
            PRIMARY KEY (source_id, side)
        );
        CREATE TABLE party_atoms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT, side TEXT,
            atom_type TEXT, atom_value TEXT, source_field TEXT
        );
    """)
    return conn


def test_blocks_on_rare_brand_token():
    from cleo.discovery_v2.blocking import generate_candidate_pairs
    from cleo.discovery_v2.idf import compute_idf_map

    conn = _make_db()
    # Two party-sides sharing 'kingsett' — only one occurrence of the token
    # per side, so it's rare.
    conn.execute("INSERT INTO party_fingerprints (source_id, side) VALUES ('RT1', 'buyer')")
    conn.execute("INSERT INTO party_fingerprints (source_id, side) VALUES ('RT2', 'buyer')")
    for sid in ("RT1", "RT2"):
        conn.execute(
            "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
            "VALUES (?, 'buyer', 'brand_token', 'kingsett', 'party_name')",
            (sid,),
        )
    conn.commit()

    idf = compute_idf_map(conn)
    pairs = list(generate_candidate_pairs(conn, idf, min_idf=0.0))
    keys = {(p[0], p[1], p[2], p[3], p[4]) for p in pairs}

    assert ("RT1", "buyer", "RT2", "buyer", "brand_token") in keys \
        or ("RT2", "buyer", "RT1", "buyer", "brand_token") in keys


def test_does_not_block_on_generic_brand_token_below_min_idf():
    """A token that's common (below min_idf) does not generate candidate pairs."""
    from cleo.discovery_v2.blocking import generate_candidate_pairs
    from cleo.discovery_v2.idf import compute_idf_map

    conn = _make_db()
    # 10 party-sides all carrying 'ontario' — IDF ~ log(10/11) < 0
    for i in range(10):
        conn.execute(
            "INSERT INTO party_fingerprints (source_id, side) VALUES (?, 'buyer')",
            (f"RT{i}",),
        )
        conn.execute(
            "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
            "VALUES (?, 'buyer', 'brand_token', 'ontario', 'party_name')",
            (f"RT{i}",),
        )
    conn.commit()

    idf = compute_idf_map(conn)
    # min_idf = 3.0 blocks 'ontario' entirely.
    pairs = list(generate_candidate_pairs(conn, idf, min_idf=3.0))
    brand_pairs = [p for p in pairs if p[4] == "brand_token"]
    assert brand_pairs == []


def test_blocks_on_exact_phone_and_address_triple_and_contact():
    from cleo.discovery_v2.blocking import generate_candidate_pairs
    from cleo.discovery_v2.idf import compute_idf_map

    conn = _make_db()
    conn.execute(
        "INSERT INTO party_fingerprints "
        "(source_id, side, street_number, street_name, street_suffix, phone, contact_fingerprint) "
        "VALUES ('RT1', 'buyer', '66', 'wellington', 'street', '4166876700', 'rob kumer')"
    )
    conn.execute(
        "INSERT INTO party_fingerprints "
        "(source_id, side, street_number, street_name, street_suffix, phone, contact_fingerprint) "
        "VALUES ('RT2', 'buyer', '66', 'wellington', 'street', '4166876700', 'rob kumer')"
    )
    conn.commit()

    idf = compute_idf_map(conn)
    pairs = list(generate_candidate_pairs(conn, idf, min_idf=0.0))
    atom_types = {p[4] for p in pairs}

    assert "phone" in atom_types
    assert "address_triple" in atom_types
    assert "contact_fingerprint" in atom_types


def test_blocking_skips_atoms_above_max_sides_cap():
    """High-count atoms (like downtown addresses shared across 500+
    unrelated businesses) don't generate useful candidate pairs."""
    from cleo.discovery_v2.blocking import generate_candidate_pairs
    from cleo.discovery_v2.idf import compute_idf_map

    conn = _make_db()
    # 10 party-sides all sharing the same phone
    for i in range(10):
        conn.execute(
            "INSERT INTO party_fingerprints (source_id, side, phone) "
            "VALUES (?, 'buyer', '4162348444')",
            (f"RT{i}",),
        )
    conn.commit()

    idf = compute_idf_map(conn)
    # cap = 5: should skip the phone entirely (10 > 5)
    pairs = list(generate_candidate_pairs(conn, idf, min_idf=0.0, max_sides=5))
    phone_pairs = [p for p in pairs if p[4] == "phone"]
    assert phone_pairs == []

    # cap = 100: should include all C(10, 2) = 45 phone pairs
    pairs_all = list(generate_candidate_pairs(conn, idf, min_idf=0.0, max_sides=100))
    phone_pairs_all = [p for p in pairs_all if p[4] == "phone"]
    assert len(phone_pairs_all) == 45
