"""Tests for IDF computation."""
import math
import sqlite3


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE party_fingerprints (
            source_id TEXT, side TEXT, phone TEXT,
            PRIMARY KEY (source_id, side)
        );
        CREATE TABLE party_atoms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT, side TEXT,
            atom_type TEXT, atom_value TEXT, source_field TEXT
        );
    """)
    return conn


def test_idf_common_token_low_rare_token_high():
    from cleo.discovery_v2.idf import compute_idf_map

    conn = _make_db()
    # 100 party-sides; 'ontario' on 80; 'rasenberg' on 2
    for i in range(100):
        conn.execute(
            "INSERT INTO party_fingerprints (source_id, side) VALUES (?, 'buyer')",
            (f"RT{i}",),
        )
    for i in range(80):
        conn.execute(
            "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
            "VALUES (?, 'buyer', 'brand_token', 'ontario', 'party_name')",
            (f"RT{i}",),
        )
    for i in range(2):
        conn.execute(
            "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
            "VALUES (?, 'buyer', 'brand_token', 'rasenberg', 'party_name')",
            (f"RT{i}",),
        )
    conn.commit()

    idf_map = compute_idf_map(conn)
    ontario_idf = idf_map[("brand_token", "ontario")]
    rasenberg_idf = idf_map[("brand_token", "rasenberg")]

    assert ontario_idf < 1.0, f"common token IDF too high: {ontario_idf}"
    assert rasenberg_idf > 3.0, f"rare token IDF too low: {rasenberg_idf}"
    # Sanity: match the log(N / (1 + df)) formula
    assert math.isclose(ontario_idf, math.log(100 / 81), rel_tol=1e-6)


def test_idf_covers_singleton_atoms_too():
    """IDF is computed for phone (singleton, from party_fingerprints) too."""
    from cleo.discovery_v2.idf import compute_idf_map

    conn = _make_db()
    for i in range(50):
        conn.execute(
            "INSERT INTO party_fingerprints (source_id, side, phone) "
            "VALUES (?, 'buyer', ?)",
            (f"RT{i}", "4166876700" if i < 30 else "9055555555"),
        )
    conn.commit()

    idf_map = compute_idf_map(conn)
    assert ("phone", "4166876700") in idf_map
    assert ("phone", "9055555555") in idf_map
