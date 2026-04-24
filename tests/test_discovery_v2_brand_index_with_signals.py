"""Tests for the brand_index builder's external-signal integration."""
import sqlite3


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE party_fingerprints (
            source_id TEXT, side TEXT,
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
            wordfreq_zipf REAL, is_english_common INTEGER, is_place_name INTEGER,
            is_industry_stopword INTEGER, filter_reason TEXT,
            discovered_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE industry_stopwords (
            token TEXT PRIMARY KEY, added_by TEXT, added_at TEXT, source TEXT
        );
    """)
    return conn


def _seed_token(conn, token, sides, phrase=None):
    """Insert a token carried by `sides` party-sides."""
    for sid in sides:
        conn.execute(
            "INSERT OR IGNORE INTO party_fingerprints (source_id, side) VALUES (?, 'buyer')", (sid,)
        )
        conn.execute(
            "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
            "VALUES (?, 'buyer', 'brand_token', ?, 'party_name')",
            (sid, token),
        )
        if phrase:
            conn.execute(
                "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
                "VALUES (?, 'buyer', 'brand_phrase', ?, 'party_name')",
                (sid, phrase),
            )


def test_signals_computed_and_distinctive_reflects_them():
    from cleo.discovery_v2.brand_index import build_brand_index
    from cleo.discovery_v2.signals import seed_industry_stopwords_table

    conn = _make_db()
    seed_industry_stopwords_table(conn)
    # 100 sides total for meaningful IDF
    for i in range(100):
        conn.execute(
            "INSERT OR IGNORE INTO party_fingerprints (source_id, side) VALUES (?, 'buyer')",
            (f"RT_bg{i}",),
        )
    # Four test tokens, each on 5 sides (so corpus IDF is similar for all)
    _seed_token(conn, "metrus", [f"m{i}" for i in range(5)], "metrus development")
    _seed_token(conn, "river", [f"r{i}" for i in range(5)], "river holdings")
    _seed_token(conn, "windsor", [f"w{i}" for i in range(5)], "windsor properties")
    _seed_token(conn, "gp", [f"g{i}" for i in range(5)], "kingsett capital gp")
    conn.commit()

    build_brand_index(conn, min_idf=0.0)

    summary = {
        r["token"]: r for r in conn.execute(
            "SELECT token, is_distinctive, is_english_common, is_place_name, "
            "is_industry_stopword, filter_reason FROM brand_token_summary"
        )
    }
    # metrus: all filters negative, distinctive
    assert summary["metrus"]["is_distinctive"] == 1
    assert summary["metrus"]["is_english_common"] == 0
    assert summary["metrus"]["is_place_name"] == 0
    assert summary["metrus"]["is_industry_stopword"] == 0
    assert summary["metrus"]["filter_reason"] is None or summary["metrus"]["filter_reason"] == ""

    # river: English common, NOT distinctive
    assert summary["river"]["is_distinctive"] == 0
    assert summary["river"]["is_english_common"] == 1
    assert summary["river"]["filter_reason"] == "english"

    # windsor: place name, NOT distinctive
    assert summary["windsor"]["is_distinctive"] == 0
    assert summary["windsor"]["is_place_name"] == 1
    # filter_reason reports the strongest filter; windsor is ALSO somewhat common English,
    # but place_name takes precedence in the reason ordering
    assert summary["windsor"]["filter_reason"] in ("place", "english")

    # gp: industry stopword, NOT distinctive
    assert summary["gp"]["is_distinctive"] == 0
    assert summary["gp"]["is_industry_stopword"] == 1
    assert summary["gp"]["filter_reason"] == "industry"


def test_user_added_stopword_reflected_in_next_build():
    from cleo.discovery_v2.brand_index import build_brand_index
    from cleo.discovery_v2.signals import seed_industry_stopwords_table

    conn = _make_db()
    seed_industry_stopwords_table(conn)
    # 100 sides total
    for i in range(100):
        conn.execute(
            "INSERT OR IGNORE INTO party_fingerprints (source_id, side) VALUES (?, 'buyer')",
            (f"RT_bg{i}",),
        )
    _seed_token(conn, "zellerhoff", [f"z{i}" for i in range(5)], "zellerhoff holdings")
    conn.commit()

    build_brand_index(conn, min_idf=0.0)
    before = conn.execute(
        "SELECT is_industry_stopword, is_distinctive FROM brand_token_summary WHERE token = 'zellerhoff'"
    ).fetchone()
    assert before["is_industry_stopword"] == 0
    assert before["is_distinctive"] == 1

    # Simulate user action: mark as industry stopword
    conn.execute(
        "INSERT INTO industry_stopwords (token, added_by, source) VALUES ('zellerhoff', 'brandon', 'user')"
    )
    conn.commit()

    build_brand_index(conn, min_idf=0.0)
    after = conn.execute(
        "SELECT is_industry_stopword, is_distinctive, filter_reason FROM brand_token_summary WHERE token = 'zellerhoff'"
    ).fetchone()
    assert after["is_industry_stopword"] == 1
    assert after["is_distinctive"] == 0
    assert after["filter_reason"] == "industry"


def test_excluded_token_takes_precedence_in_reason():
    from cleo.discovery_v2.brand_index import build_brand_index

    conn = _make_db()
    for i in range(100):
        conn.execute(
            "INSERT OR IGNORE INTO party_fingerprints (source_id, side) VALUES (?, 'buyer')",
            (f"RT_bg{i}",),
        )
    # 'named' is in CALIBRATION['excluded_brand_tokens']
    _seed_token(conn, "named", [f"n{i}" for i in range(5)], "named individual s")
    conn.commit()

    build_brand_index(conn, min_idf=0.0)
    row = conn.execute(
        "SELECT is_excluded, is_distinctive, filter_reason FROM brand_token_summary WHERE token = 'named'"
    ).fetchone()
    assert row["is_excluded"] == 1
    assert row["is_distinctive"] == 0
    assert row["filter_reason"] == "excluded"
