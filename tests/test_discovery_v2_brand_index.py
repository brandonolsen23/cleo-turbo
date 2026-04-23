"""Tests for the brand-token inverted index builder."""
import sqlite3


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE party_fingerprints (
            source_id TEXT, side TEXT, phone TEXT, contact_fingerprint TEXT, postal TEXT,
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
            discovered_at TEXT DEFAULT (datetime('now'))
        );
    """)
    return conn


def test_index_surfaces_party_sides_by_token():
    from cleo.discovery_v2.brand_index import build_brand_index

    conn = _make_db()
    # 3 party-sides, two of which carry 'kingsett' token (rare)
    for sid in ("RT1", "RT2", "RT3"):
        conn.execute(
            "INSERT INTO party_fingerprints (source_id, side) VALUES (?, 'buyer')", (sid,)
        )
    for sid in ("RT1", "RT2"):
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
    # RT3 carries 'ontario' only
    conn.execute(
        "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
        "VALUES ('RT3', 'buyer', 'brand_token', 'ontario', 'party_name')"
    )
    conn.commit()

    build_brand_index(conn)

    rows = conn.execute(
        "SELECT token, source_id, side FROM brand_token_index ORDER BY token, source_id"
    ).fetchall()
    index = {(r["token"], r["source_id"], r["side"]) for r in rows}
    assert ("kingsett", "RT1", "buyer") in index
    assert ("kingsett", "RT2", "buyer") in index
    assert ("ontario", "RT3", "buyer") in index


def test_summary_basic_counts():
    from cleo.discovery_v2.brand_index import build_brand_index

    conn = _make_db()
    # 10 party-sides; 'ontario' on 8 (low IDF), 'rasenberg' on 2 (high IDF)
    for i in range(10):
        conn.execute(
            "INSERT INTO party_fingerprints (source_id, side) VALUES (?, 'buyer')",
            (f"RT{i}",),
        )
    for i in range(8):
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

    build_brand_index(conn)

    summary = {
        r["token"]: r for r in conn.execute(
            "SELECT token, idf, n_party_sides, is_distinctive, is_excluded "
            "FROM brand_token_summary"
        )
    }
    assert summary["ontario"]["n_party_sides"] == 8
    assert summary["rasenberg"]["n_party_sides"] == 2


def test_min_idf_override_respected():
    from cleo.discovery_v2.brand_index import build_brand_index

    conn = _make_db()
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

    # At min_idf=3.0: rasenberg IDF ≈ log(100/3) ≈ 3.5 → distinctive; ontario IDF ≈ 0.2 → not.
    build_brand_index(conn, min_idf=3.0)
    rows = {r["token"]: r for r in conn.execute("SELECT token, is_distinctive FROM brand_token_summary")}
    assert rows["rasenberg"]["is_distinctive"] == 1
    assert rows["ontario"]["is_distinctive"] == 0


def test_excluded_tokens_flagged():
    from cleo.discovery_v2.brand_index import build_brand_index

    conn = _make_db()
    conn.execute("INSERT INTO party_fingerprints (source_id, side) VALUES ('RT1', 'buyer')")
    conn.execute(
        "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
        "VALUES ('RT1', 'buyer', 'brand_token', 'named', 'party_name')"
    )
    conn.commit()

    build_brand_index(conn)
    row = conn.execute(
        "SELECT is_excluded, is_distinctive FROM brand_token_summary WHERE token = 'named'"
    ).fetchone()
    assert row["is_excluded"] == 1
    # Even at high IDF, excluded tokens are NOT distinctive.
    assert row["is_distinctive"] == 0


def test_distinct_phrases_per_token_counted():
    from cleo.discovery_v2.brand_index import build_brand_index

    conn = _make_db()
    for sid in ("RT1", "RT2", "RT3"):
        conn.execute(
            "INSERT INTO party_fingerprints (source_id, side) VALUES (?, 'buyer')", (sid,)
        )
        conn.execute(
            "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
            "VALUES (?, 'buyer', 'brand_token', 'kingsett', 'party_name')", (sid,)
        )
    # 3 phrases: "kingsett", "kingsett capital", "kingsett capital inc"
    for sid, phrase in [
        ("RT1", "kingsett"),
        ("RT2", "kingsett capital"),
        ("RT3", "kingsett capital inc"),
    ]:
        conn.execute(
            "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
            "VALUES (?, 'buyer', 'brand_phrase', ?, 'party_name')", (sid, phrase)
        )
    conn.commit()

    build_brand_index(conn, min_idf=0.0)
    row = conn.execute(
        "SELECT n_distinct_phrases FROM brand_token_summary WHERE token = 'kingsett'"
    ).fetchone()
    assert row["n_distinct_phrases"] == 3


def test_idempotent_rebuild():
    """Running build_brand_index twice should produce identical output."""
    from cleo.discovery_v2.brand_index import build_brand_index

    conn = _make_db()
    for sid in ("RT1", "RT2"):
        conn.execute(
            "INSERT INTO party_fingerprints (source_id, side) VALUES (?, 'buyer')", (sid,)
        )
        conn.execute(
            "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
            "VALUES (?, 'buyer', 'brand_token', 'kingsett', 'party_name')", (sid,)
        )
    conn.commit()

    build_brand_index(conn, min_idf=0.0)
    n1 = conn.execute("SELECT COUNT(*) FROM brand_token_index").fetchone()[0]
    n2 = conn.execute("SELECT COUNT(*) FROM brand_token_summary").fetchone()[0]

    build_brand_index(conn, min_idf=0.0)
    n1_again = conn.execute("SELECT COUNT(*) FROM brand_token_index").fetchone()[0]
    n2_again = conn.execute("SELECT COUNT(*) FROM brand_token_summary").fetchone()[0]

    assert n1 == n1_again
    assert n2 == n2_again
