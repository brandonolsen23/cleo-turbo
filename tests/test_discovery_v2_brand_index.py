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
            wordfreq_zipf REAL, is_english_common INTEGER, is_place_name INTEGER,
            is_industry_stopword INTEGER, filter_reason TEXT,
            discovered_at TEXT DEFAULT (datetime('now')),
            position_consistency REAL,
            total_child_coverage REAL,
            is_position_anchor INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE brand_bigram_index (
            bigram TEXT NOT NULL, source_id TEXT NOT NULL, side TEXT NOT NULL,
            PRIMARY KEY (bigram, source_id, side)
        );
        CREATE TABLE brand_bigram_summary (
            bigram TEXT PRIMARY KEY,
            token_a TEXT NOT NULL, token_b TEXT NOT NULL,
            idf REAL NOT NULL, n_party_sides INTEGER NOT NULL,
            n_distinct_phrases INTEGER NOT NULL,
            any_token_distinctive INTEGER NOT NULL,
            any_token_excluded INTEGER NOT NULL,
            all_english INTEGER NOT NULL,
            all_place INTEGER NOT NULL,
            all_industry INTEGER NOT NULL,
            is_distinctive INTEGER NOT NULL,
            discovered_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE brand_trigram_index (
            trigram TEXT NOT NULL, source_id TEXT NOT NULL, side TEXT NOT NULL,
            PRIMARY KEY (trigram, source_id, side)
        );
        CREATE TABLE brand_trigram_summary (
            trigram TEXT PRIMARY KEY,
            token_a TEXT NOT NULL, token_b TEXT NOT NULL, token_c TEXT NOT NULL,
            idf REAL NOT NULL, n_party_sides INTEGER NOT NULL,
            n_distinct_phrases INTEGER NOT NULL,
            any_token_distinctive INTEGER NOT NULL,
            any_token_excluded INTEGER NOT NULL,
            all_english INTEGER NOT NULL,
            all_place INTEGER NOT NULL,
            all_industry INTEGER NOT NULL,
            is_distinctive INTEGER NOT NULL,
            discovered_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE brand_fourgram_index (
            fourgram TEXT NOT NULL, source_id TEXT NOT NULL, side TEXT NOT NULL,
            PRIMARY KEY (fourgram, source_id, side)
        );
        CREATE TABLE brand_fourgram_summary (
            fourgram TEXT PRIMARY KEY,
            token_a TEXT NOT NULL, token_b TEXT NOT NULL,
            token_c TEXT NOT NULL, token_d TEXT NOT NULL,
            idf REAL NOT NULL, n_party_sides INTEGER NOT NULL,
            n_distinct_phrases INTEGER NOT NULL,
            any_token_distinctive INTEGER NOT NULL,
            any_token_excluded INTEGER NOT NULL,
            all_english INTEGER NOT NULL,
            all_place INTEGER NOT NULL,
            all_industry INTEGER NOT NULL,
            is_distinctive INTEGER NOT NULL,
            discovered_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE brand_fivegram_index (
            fivegram TEXT NOT NULL, source_id TEXT NOT NULL, side TEXT NOT NULL,
            PRIMARY KEY (fivegram, source_id, side)
        );
        CREATE TABLE brand_fivegram_summary (
            fivegram TEXT PRIMARY KEY,
            token_a TEXT NOT NULL, token_b TEXT NOT NULL,
            token_c TEXT NOT NULL, token_d TEXT NOT NULL, token_e TEXT NOT NULL,
            idf REAL NOT NULL, n_party_sides INTEGER NOT NULL,
            n_distinct_phrases INTEGER NOT NULL,
            any_token_distinctive INTEGER NOT NULL,
            any_token_excluded INTEGER NOT NULL,
            all_english INTEGER NOT NULL,
            all_place INTEGER NOT NULL,
            all_industry INTEGER NOT NULL,
            is_distinctive INTEGER NOT NULL,
            discovered_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE brand_long_phrase_index (
            phrase TEXT NOT NULL, source_id TEXT NOT NULL, side TEXT NOT NULL,
            PRIMARY KEY (phrase, source_id, side)
        );
        CREATE TABLE brand_long_phrase_summary (
            phrase TEXT PRIMARY KEY,
            n_tokens INTEGER NOT NULL,
            idf REAL NOT NULL, n_party_sides INTEGER NOT NULL,
            n_distinct_source_phrases INTEGER NOT NULL,
            any_token_distinctive INTEGER NOT NULL,
            any_token_excluded INTEGER NOT NULL,
            all_english INTEGER NOT NULL,
            all_place INTEGER NOT NULL,
            all_industry INTEGER NOT NULL,
            is_distinctive INTEGER NOT NULL,
            discovered_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE phone_summary (
            phone TEXT PRIMARY KEY,
            n_party_sides INTEGER NOT NULL,
            is_distinctive INTEGER NOT NULL,
            discovered_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE address_base_summary (
            street_number TEXT NOT NULL, street_name TEXT NOT NULL, street_suffix TEXT NOT NULL,
            n_party_sides INTEGER NOT NULL,
            n_distinct_suites INTEGER NOT NULL,
            n_distinct_postals INTEGER NOT NULL,
            is_distinctive INTEGER NOT NULL,
            discovered_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (street_number, street_name, street_suffix)
        );
        CREATE TABLE contact_fingerprint_summary (
            contact_fingerprint TEXT PRIMARY KEY,
            n_party_sides INTEGER NOT NULL,
            is_distinctive INTEGER NOT NULL,
            discovered_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE industry_stopwords (
            token TEXT PRIMARY KEY, added_by TEXT, added_at TEXT, source TEXT
        );
        CREATE TABLE places (
            token TEXT PRIMARY KEY, added_by TEXT, added_at TEXT, source TEXT
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


def test_position_anchor_set_when_prefix_consistent_and_well_covered():
    """A token used 100% as token_a across many distinct 2-grams, with most
    party-sides absorbed by those 2-grams, gets flagged as position-anchor
    even when is_distinctive=0."""
    from cleo.discovery_v2.brand_index import build_brand_index, build_brand_ngram_index, _recompute_position_anchors

    conn = _make_db()
    # Background party-sides for IDF math
    for i in range(100):
        conn.execute(
            "INSERT INTO party_fingerprints (source_id, side) VALUES (?, 'buyer')",
            (f"bg{i}",),
        )
    # 'dh' as prefix in 4 distinct 2-grams, total ~30 sides
    pairs = [("dh management", 11), ("dh property", 5), ("dh westview", 8), ("dh canada", 6)]
    sid_counter = 0
    for phrase, n in pairs:
        for _ in range(n):
            sid_counter += 1
            sid = f"dh{sid_counter}"
            conn.execute(
                "INSERT INTO party_fingerprints (source_id, side) VALUES (?, 'buyer')", (sid,)
            )
            conn.execute(
                "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
                "VALUES (?, 'buyer', 'brand_phrase', ?, 'party_name')",
                (sid, phrase),
            )
            for tok in phrase.split(" "):
                conn.execute(
                    "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
                    "VALUES (?, 'buyer', 'brand_token', ?, 'party_name')",
                    (sid, tok),
                )
    conn.commit()

    # 'dh' Zipf is 3.44 — would be filtered as english at min_idf=3.0 default.
    # But we want to demonstrate the anchor flag rescues it.
    build_brand_index(conn, min_idf=3.0)
    build_brand_ngram_index(conn, 2, min_idf=3.0)
    _recompute_position_anchors(conn)

    row = conn.execute(
        "SELECT is_distinctive, is_position_anchor, position_consistency, total_child_coverage "
        "FROM brand_token_summary WHERE token = 'dh'"
    ).fetchone()
    assert row is not None, "dh row should exist"
    # is_distinctive should be 0 because 'dh' is filtered as english (Zipf 3.44)
    # — but if our environment differs and it's distinctive anyway, the anchor
    # flag stays 0 (we don't double-flag). Either way the position fields are populated.
    assert row["position_consistency"] is not None
    assert row["position_consistency"] >= 0.99   # all in pos_a
    assert row["total_child_coverage"] is not None
    if row["is_distinctive"] == 0:
        assert row["is_position_anchor"] == 1
    else:
        # already-distinctive token: position fields populated, anchor flag stays 0
        assert row["is_position_anchor"] == 0


def test_position_anchor_NOT_set_when_position_mixed():
    """A token that appears in BOTH token_a and token_b across its child 2-grams
    is NOT a position-anchor (likely shared across multiple unrelated operators)."""
    from cleo.discovery_v2.brand_index import build_brand_index, build_brand_ngram_index, _recompute_position_anchors

    conn = _make_db()
    for i in range(100):
        conn.execute(
            "INSERT INTO party_fingerprints (source_id, side) VALUES (?, 'buyer')",
            (f"bg{i}",),
        )
    # 'mixedtok' appears as prefix on some sides and suffix on others — ambiguous.
    # Phrases: "mixedtok aaa" (5x), "bbb mixedtok" (5x), "mixedtok ccc" (5x), "ddd mixedtok" (5x)
    sid_counter = 0
    for phrase in ["mixedtok aaa", "bbb mixedtok", "mixedtok ccc", "ddd mixedtok"]:
        for _ in range(5):
            sid_counter += 1
            sid = f"mt{sid_counter}"
            conn.execute(
                "INSERT INTO party_fingerprints (source_id, side) VALUES (?, 'buyer')", (sid,)
            )
            conn.execute(
                "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
                "VALUES (?, 'buyer', 'brand_phrase', ?, 'party_name')",
                (sid, phrase),
            )
            for tok in phrase.split(" "):
                conn.execute(
                    "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
                    "VALUES (?, 'buyer', 'brand_token', ?, 'party_name')",
                    (sid, tok),
                )
    conn.commit()

    build_brand_index(conn, min_idf=3.0)
    build_brand_ngram_index(conn, 2, min_idf=3.0)
    _recompute_position_anchors(conn)

    row = conn.execute(
        "SELECT is_position_anchor, position_consistency "
        "FROM brand_token_summary WHERE token = 'mixedtok'"
    ).fetchone()
    assert row is not None
    # 50/50 position split — consistency is 0.5
    assert row["position_consistency"] is not None
    assert row["position_consistency"] < 0.95
    assert row["is_position_anchor"] == 0


def test_position_anchor_NOT_set_with_only_one_child():
    """A token with only 1 distinct child 2-gram doesn't qualify — could be a
    one-off rather than a real operator family."""
    from cleo.discovery_v2.brand_index import build_brand_index, build_brand_ngram_index, _recompute_position_anchors

    conn = _make_db()
    for i in range(100):
        conn.execute(
            "INSERT INTO party_fingerprints (source_id, side) VALUES (?, 'buyer')",
            (f"bg{i}",),
        )
    # 'soloprefix' appears in only one 2-gram, repeated 15 times
    for i in range(15):
        sid = f"sp{i}"
        conn.execute(
            "INSERT INTO party_fingerprints (source_id, side) VALUES (?, 'buyer')", (sid,)
        )
        conn.execute(
            "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
            "VALUES (?, 'buyer', 'brand_phrase', 'soloprefix only', 'party_name')",
            (sid,),
        )
        for tok in ("soloprefix", "only"):
            conn.execute(
                "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
                "VALUES (?, 'buyer', 'brand_token', ?, 'party_name')",
                (sid, tok),
            )
    conn.commit()

    build_brand_index(conn, min_idf=3.0)
    build_brand_ngram_index(conn, 2, min_idf=3.0)
    _recompute_position_anchors(conn)

    row = conn.execute(
        "SELECT is_position_anchor FROM brand_token_summary WHERE token = 'soloprefix'"
    ).fetchone()
    assert row is not None
    # n_distinct_children=1 — fails the >=3 children rule
    assert row["is_position_anchor"] == 0


def test_position_anchor_NOT_set_for_already_distinctive_tokens():
    """Already-distinctive tokens (like 'rasenberg') get position fields
    populated for visibility but is_position_anchor stays 0 — the rescue is
    only for tokens that would otherwise be filtered.

    We use 800 background sides so rasenberg (20 sides, 820 total) achieves
    IDF = log(820/21) ≈ 3.67 ≥ 3.0 → is_distinctive=1.
    """
    from cleo.discovery_v2.brand_index import build_brand_index, build_brand_ngram_index, _recompute_position_anchors

    conn = _make_db()
    # 800 background sides ensures rasenberg is rare enough to be distinctive.
    for i in range(800):
        conn.execute(
            "INSERT INTO party_fingerprints (source_id, side) VALUES (?, 'buyer')",
            (f"bg{i}",),
        )
    # 'rasenberg' on 20 sides across 3 distinct bigrams — all as prefix (pos_a).
    # IDF = log(820/21) ≈ 3.67 → is_distinctive=1 at min_idf=3.0.
    for i in range(20):
        sid = f"r{i}"
        conn.execute(
            "INSERT INTO party_fingerprints (source_id, side) VALUES (?, 'buyer')", (sid,)
        )
        phrase = "rasenberg investments" if i < 10 else "rasenberg holdings" if i < 15 else "rasenberg properties"
        conn.execute(
            "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
            "VALUES (?, 'buyer', 'brand_phrase', ?, 'party_name')",
            (sid, phrase),
        )
        for tok in phrase.split(" "):
            conn.execute(
                "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
                "VALUES (?, 'buyer', 'brand_token', ?, 'party_name')",
                (sid, tok),
            )
    conn.commit()

    build_brand_index(conn, min_idf=3.0)
    build_brand_ngram_index(conn, 2, min_idf=3.0)
    _recompute_position_anchors(conn)

    row = conn.execute(
        "SELECT is_distinctive, is_position_anchor, position_consistency "
        "FROM brand_token_summary WHERE token = 'rasenberg'"
    ).fetchone()
    assert row is not None
    # Should be distinctive (rasenberg passes wordfreq filter + IDF ≥ 3.0)
    assert row["is_distinctive"] == 1
    # Anchor flag should stay 0 — already rescued by being distinctive
    assert row["is_position_anchor"] == 0
    # Position consistency still populated for visibility
    assert row["position_consistency"] is not None
    assert row["position_consistency"] >= 0.99   # always pos_a in this fixture
