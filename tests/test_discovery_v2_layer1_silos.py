"""Integration tests for Layer 1 silo builders."""
import sqlite3


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE party_fingerprints (
            source_id TEXT, side TEXT,
            street_number TEXT, street_name TEXT, street_suffix TEXT,
            street_direction TEXT,
            suite_type TEXT, suite_number TEXT,
            city TEXT, province TEXT, postal TEXT,
            phone TEXT, contact_fingerprint TEXT,
            sale_date TEXT,
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
            bigram TEXT, source_id TEXT, side TEXT,
            PRIMARY KEY (bigram, source_id, side)
        );
        CREATE TABLE brand_bigram_summary (
            bigram TEXT PRIMARY KEY, token_a TEXT, token_b TEXT,
            idf REAL, n_party_sides INTEGER, n_distinct_phrases INTEGER,
            any_token_distinctive INTEGER, any_token_excluded INTEGER,
            all_english INTEGER, all_place INTEGER, all_industry INTEGER,
            is_distinctive INTEGER,
            discovered_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE brand_trigram_index (
            trigram TEXT, source_id TEXT, side TEXT,
            PRIMARY KEY (trigram, source_id, side)
        );
        CREATE TABLE brand_trigram_summary (
            trigram TEXT PRIMARY KEY, token_a TEXT, token_b TEXT, token_c TEXT,
            idf REAL, n_party_sides INTEGER, n_distinct_phrases INTEGER,
            any_token_distinctive INTEGER, any_token_excluded INTEGER,
            all_english INTEGER, all_place INTEGER, all_industry INTEGER,
            is_distinctive INTEGER,
            discovered_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE brand_fourgram_index (
            fourgram TEXT, source_id TEXT, side TEXT,
            PRIMARY KEY (fourgram, source_id, side)
        );
        CREATE TABLE brand_fourgram_summary (
            fourgram TEXT PRIMARY KEY, token_a TEXT, token_b TEXT,
            token_c TEXT, token_d TEXT,
            idf REAL, n_party_sides INTEGER, n_distinct_phrases INTEGER,
            any_token_distinctive INTEGER, any_token_excluded INTEGER,
            all_english INTEGER, all_place INTEGER, all_industry INTEGER,
            is_distinctive INTEGER,
            discovered_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE brand_fivegram_index (
            fivegram TEXT, source_id TEXT, side TEXT,
            PRIMARY KEY (fivegram, source_id, side)
        );
        CREATE TABLE brand_fivegram_summary (
            fivegram TEXT PRIMARY KEY, token_a TEXT, token_b TEXT,
            token_c TEXT, token_d TEXT, token_e TEXT,
            idf REAL, n_party_sides INTEGER, n_distinct_phrases INTEGER,
            any_token_distinctive INTEGER, any_token_excluded INTEGER,
            all_english INTEGER, all_place INTEGER, all_industry INTEGER,
            is_distinctive INTEGER,
            discovered_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE brand_long_phrase_index (
            phrase TEXT, source_id TEXT, side TEXT,
            PRIMARY KEY (phrase, source_id, side)
        );
        CREATE TABLE brand_long_phrase_summary (
            phrase TEXT PRIMARY KEY, n_tokens INTEGER, idf REAL,
            n_party_sides INTEGER, n_distinct_source_phrases INTEGER,
            any_token_distinctive INTEGER, any_token_excluded INTEGER,
            all_english INTEGER, all_place INTEGER, all_industry INTEGER,
            is_distinctive INTEGER,
            discovered_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE phone_summary (
            phone TEXT PRIMARY KEY, n_party_sides INTEGER, is_distinctive INTEGER,
            discovered_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE address_base_summary (
            street_number TEXT, street_name TEXT, street_suffix TEXT,
            n_party_sides INTEGER, n_distinct_suites INTEGER,
            n_distinct_postals INTEGER, is_distinctive INTEGER,
            discovered_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (street_number, street_name, street_suffix)
        );
        CREATE TABLE address_root_summary (
            street_number TEXT NOT NULL, street_name TEXT NOT NULL,
            n_party_sides INTEGER, n_distinct_suffixes INTEGER,
            n_distinct_directions INTEGER, n_distinct_suites INTEGER,
            n_distinct_postals INTEGER,
            discovered_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (street_number, street_name)
        );
        CREATE TABLE contact_fingerprint_summary (
            contact_fingerprint TEXT PRIMARY KEY,
            n_party_sides INTEGER, is_distinctive INTEGER,
            discovered_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE industry_stopwords (
            token TEXT PRIMARY KEY, added_by TEXT, added_at TEXT, source TEXT
        );
        CREATE TABLE places (
            token TEXT PRIMARY KEY, added_by TEXT, added_at TEXT, source TEXT
        );
        CREATE TABLE brand_stem (
            stem TEXT PRIMARY KEY, stem_type TEXT NOT NULL,
            dominant_anchor_type TEXT NOT NULL, dominant_anchor_value TEXT NOT NULL,
            dominance_share REAL NOT NULL, volume INTEGER NOT NULL, verified_at TEXT
        );
        CREATE TABLE brand_stem_phrase_map (
            phrase TEXT PRIMARY KEY, stem TEXT NOT NULL, confidence REAL NOT NULL
        );
        CREATE TABLE address_unit_summary (
            city                   TEXT NOT NULL,
            street_number          TEXT NOT NULL,
            street_name            TEXT NOT NULL,
            street_suffix          TEXT NOT NULL DEFAULT '',
            street_direction       TEXT NOT NULL DEFAULT '',
            suite_type             TEXT NOT NULL DEFAULT '',
            suite_number           TEXT NOT NULL DEFAULT '',
            n_party_sides          INTEGER NOT NULL,
            n_distinct_brand_stems INTEGER NOT NULL,
            dominant_stem          TEXT,
            dominance_share        REAL,
            discovered_at          TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (city, street_number, street_name, street_suffix,
                         street_direction, suite_type, suite_number)
        );
    """)
    return conn


def test_build_brand_bigram_index_emits_consecutive_pairs():
    from cleo.discovery_v2.brand_index import build_brand_index, build_brand_ngram_index

    conn = _make_db()
    # 100 background party-sides for IDF math
    for i in range(100):
        conn.execute(
            "INSERT INTO party_fingerprints (source_id, side) VALUES (?, 'buyer')",
            (f"bg{i}",),
        )
    # 5 party-sides carrying phrase 'kingsett capital'
    for i in range(5):
        conn.execute(
            "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
            "VALUES (?, 'buyer', 'brand_phrase', 'kingsett capital', 'party_name')",
            (f"k{i}",),
        )
        conn.execute(
            "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
            "VALUES (?, 'buyer', 'brand_token', 'kingsett', 'party_name')",
            (f"k{i}",),
        )
        conn.execute(
            "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
            "VALUES (?, 'buyer', 'brand_token', 'capital', 'party_name')",
            (f"k{i}",),
        )
        conn.execute(
            "INSERT OR IGNORE INTO party_fingerprints (source_id, side) VALUES (?, 'buyer')",
            (f"k{i}",),
        )
    conn.commit()

    build_brand_index(conn, min_idf=0.0)
    build_brand_ngram_index(conn, 2, min_idf=0.0)

    row = conn.execute(
        "SELECT bigram, n_party_sides FROM brand_bigram_summary WHERE bigram='kingsett capital'"
    ).fetchone()
    assert row is not None
    assert row["n_party_sides"] == 5


def test_build_brand_trigram_index_emits_consecutive_triples():
    from cleo.discovery_v2.brand_index import build_brand_index, build_brand_ngram_index

    conn = _make_db()
    for i in range(100):
        conn.execute(
            "INSERT INTO party_fingerprints (source_id, side) VALUES (?, 'buyer')",
            (f"bg{i}",),
        )
    # phrase 'kingsett capital gp' tokenizes to 3 tokens, so one trigram
    for i in range(3):
        conn.execute(
            "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
            "VALUES (?, 'buyer', 'brand_phrase', 'kingsett capital gp', 'party_name')",
            (f"k{i}",),
        )
        for tok in ("kingsett", "capital", "gp"):
            conn.execute(
                "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
                "VALUES (?, 'buyer', 'brand_token', ?, 'party_name')",
                (f"k{i}", tok),
            )
        conn.execute(
            "INSERT OR IGNORE INTO party_fingerprints (source_id, side) VALUES (?, 'buyer')",
            (f"k{i}",),
        )
    conn.commit()

    build_brand_index(conn, min_idf=0.0)
    build_brand_ngram_index(conn, 3, min_idf=0.0)

    row = conn.execute(
        "SELECT trigram, token_a, token_b, token_c, n_party_sides "
        "FROM brand_trigram_summary WHERE trigram='kingsett capital gp'"
    ).fetchone()
    assert row is not None
    assert row["token_a"] == "kingsett"
    assert row["token_b"] == "capital"
    assert row["token_c"] == "gp"
    assert row["n_party_sides"] == 3


def test_ngram_distinctiveness_gated_on_own_idf_not_constituents():
    """'regional group' — both tokens common English — the bigram itself is distinctive
    if its corpus IDF is high enough."""
    from cleo.discovery_v2.brand_index import build_brand_index, build_brand_ngram_index

    conn = _make_db()
    # 100 background
    for i in range(100):
        conn.execute(
            "INSERT INTO party_fingerprints (source_id, side) VALUES (?, 'buyer')",
            (f"bg{i}",),
        )
    # 3 party-sides with 'regional group' → bigram IDF = log(100/4) ≈ 3.2 → distinctive at min_idf=3.0
    for i in range(3):
        conn.execute(
            "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
            "VALUES (?, 'buyer', 'brand_phrase', 'regional group', 'party_name')",
            (f"rg{i}",),
        )
        for tok in ("regional", "group"):
            conn.execute(
                "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
                "VALUES (?, 'buyer', 'brand_token', ?, 'party_name')",
                (f"rg{i}", tok),
            )
        conn.execute(
            "INSERT OR IGNORE INTO party_fingerprints (source_id, side) VALUES (?, 'buyer')",
            (f"rg{i}",),
        )
    conn.commit()

    build_brand_index(conn, min_idf=3.0)
    build_brand_ngram_index(conn, 2, min_idf=3.0)

    row = conn.execute(
        "SELECT is_distinctive, any_token_distinctive FROM brand_bigram_summary "
        "WHERE bigram='regional group'"
    ).fetchone()
    assert row is not None
    # 'regional' and 'group' are english (wordfreq > 3.0) → not distinctive individually
    assert row["any_token_distinctive"] == 0
    # But the bigram IDF (log(100/4) ≈ 3.2) >= 3.0 → distinctive
    assert row["is_distinctive"] == 1


def test_phone_summary_counts_distinct_phones():
    from cleo.discovery_v2.brand_index import build_phone_summary

    conn = _make_db()
    for sid, phone in [("RT1", "4166876700"), ("RT2", "4166876700"), ("RT3", "9055555555")]:
        conn.execute(
            "INSERT INTO party_fingerprints (source_id, side, phone) VALUES (?, 'buyer', ?)",
            (sid, phone),
        )
    conn.commit()

    build_phone_summary(conn)

    rows = {
        r["phone"]: r["n_party_sides"]
        for r in conn.execute("SELECT phone, n_party_sides FROM phone_summary")
    }
    assert rows["4166876700"] == 2
    assert rows["9055555555"] == 1


def test_address_base_summary_counts_and_variants():
    from cleo.discovery_v2.brand_index import build_address_base_summary

    conn = _make_db()
    # 3 party-sides at 66 wellington street with different suites
    for sid, suite_num, postal in [
        ("RT1", "4400", "M5K1H6"),
        ("RT2", "4400", "M5K1H6"),
        ("RT3", "4500", "M5K1H6"),
    ]:
        conn.execute(
            """INSERT INTO party_fingerprints (source_id, side,
                 street_number, street_name, street_suffix,
                 suite_type, suite_number, postal)
               VALUES (?, 'buyer', '66', 'wellington', 'street', 'suite', ?, ?)""",
            (sid, suite_num, postal),
        )
    conn.commit()

    build_address_base_summary(conn)

    row = conn.execute(
        "SELECT n_party_sides, n_distinct_suites, n_distinct_postals "
        "FROM address_base_summary "
        "WHERE street_number='66' AND street_name='wellington' AND street_suffix='street'"
    ).fetchone()
    assert row is not None
    assert row["n_party_sides"] == 3
    assert row["n_distinct_suites"] == 2   # '4400' and '4500'
    assert row["n_distinct_postals"] == 1  # all M5K1H6


def test_contact_fingerprint_summary_counts():
    from cleo.discovery_v2.brand_index import build_contact_fingerprint_summary

    conn = _make_db()
    for sid, cfp in [("RT1", "rob kumer"), ("RT2", "rob kumer"), ("RT3", "peter aghar")]:
        conn.execute(
            "INSERT INTO party_fingerprints (source_id, side, contact_fingerprint) "
            "VALUES (?, 'buyer', ?)",
            (sid, cfp),
        )
    conn.commit()

    build_contact_fingerprint_summary(conn)

    rows = {
        r["contact_fingerprint"]: r["n_party_sides"]
        for r in conn.execute("SELECT contact_fingerprint, n_party_sides FROM contact_fingerprint_summary")
    }
    assert rows["rob kumer"] == 2
    assert rows["peter aghar"] == 1


def test_build_all_indexes_runs_full_pipeline():
    from cleo.discovery_v2.brand_index import build_all_indexes

    conn = _make_db()
    for i in range(50):
        conn.execute(
            "INSERT INTO party_fingerprints (source_id, side, phone) VALUES (?, 'buyer', ?)",
            (f"RT{i}", "4166876700" if i < 30 else None),
        )
    for i in range(30):
        conn.execute(
            "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
            "VALUES (?, 'buyer', 'brand_phrase', 'kingsett capital', 'party_name')",
            (f"RT{i}",),
        )
        for tok in ("kingsett", "capital"):
            conn.execute(
                "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
                "VALUES (?, 'buyer', 'brand_token', ?, 'party_name')",
                (f"RT{i}", tok),
            )
    conn.commit()

    build_all_indexes(conn, min_idf=0.0, verbose=False)

    assert conn.execute("SELECT COUNT(*) FROM brand_token_summary").fetchone()[0] > 0
    assert conn.execute("SELECT COUNT(*) FROM brand_bigram_summary").fetchone()[0] > 0
    assert conn.execute("SELECT COUNT(*) FROM phone_summary").fetchone()[0] > 0
    # New silos — fourgram/fivegram/long_phrase run without error (may be 0 rows
    # since 'kingsett capital' is only 2 tokens and no long phrases are inserted).
    assert conn.execute("SELECT COUNT(*) FROM brand_fourgram_summary").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM brand_fivegram_summary").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM brand_long_phrase_summary").fetchone()[0] == 0


def test_build_brand_ngram_index_n4_emits_consecutive_quadruples():
    from cleo.discovery_v2.brand_index import build_brand_index, build_brand_ngram_index

    conn = _make_db()
    for i in range(100):
        conn.execute(
            "INSERT INTO party_fingerprints (source_id, side) VALUES (?, 'buyer')",
            (f"bg{i}",),
        )
    # phrase has 4 tokens — should produce exactly 1 fourgram per party-side
    for i in range(3):
        conn.execute(
            "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
            "VALUES (?, 'buyer', 'brand_phrase', 'kingsett capital gp residential', 'party_name')",
            (f"k{i}",),
        )
        for tok in ("kingsett", "capital", "gp", "residential"):
            conn.execute(
                "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
                "VALUES (?, 'buyer', 'brand_token', ?, 'party_name')",
                (f"k{i}", tok),
            )
        conn.execute(
            "INSERT OR IGNORE INTO party_fingerprints (source_id, side) VALUES (?, 'buyer')",
            (f"k{i}",),
        )
    conn.commit()

    build_brand_index(conn, min_idf=0.0)
    build_brand_ngram_index(conn, 4, min_idf=0.0)

    row = conn.execute(
        "SELECT fourgram, token_a, token_b, token_c, token_d, n_party_sides "
        "FROM brand_fourgram_summary WHERE fourgram = 'kingsett capital gp residential'"
    ).fetchone()
    assert row is not None
    assert row["token_a"] == "kingsett"
    assert row["token_b"] == "capital"
    assert row["token_c"] == "gp"
    assert row["token_d"] == "residential"
    assert row["n_party_sides"] == 3


def test_build_brand_ngram_index_n5_emits_consecutive_quintuples():
    from cleo.discovery_v2.brand_index import build_brand_index, build_brand_ngram_index

    conn = _make_db()
    for i in range(100):
        conn.execute(
            "INSERT INTO party_fingerprints (source_id, side) VALUES (?, 'buyer')",
            (f"bg{i}",),
        )
    # 5-token phrase, exactly 1 fivegram per party-side
    for i in range(2):
        conn.execute(
            "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
            "VALUES (?, 'buyer', 'brand_phrase', 'majesty queen right province ontario', 'party_name')",
            (f"q{i}",),
        )
        for tok in ("majesty", "queen", "right", "province", "ontario"):
            conn.execute(
                "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
                "VALUES (?, 'buyer', 'brand_token', ?, 'party_name')",
                (f"q{i}", tok),
            )
        conn.execute(
            "INSERT OR IGNORE INTO party_fingerprints (source_id, side) VALUES (?, 'buyer')",
            (f"q{i}",),
        )
    conn.commit()

    build_brand_index(conn, min_idf=0.0)
    build_brand_ngram_index(conn, 5, min_idf=0.0)

    row = conn.execute(
        "SELECT fivegram, token_a, token_b, token_c, token_d, token_e, n_party_sides "
        "FROM brand_fivegram_summary WHERE fivegram = 'majesty queen right province ontario'"
    ).fetchone()
    assert row is not None
    assert row["token_e"] == "ontario"
    assert row["n_party_sides"] == 2


def test_build_long_phrase_index_captures_phrases_with_6_or_more_tokens():
    from cleo.discovery_v2.brand_index import build_brand_index, build_long_phrase_index

    conn = _make_db()
    for i in range(100):
        conn.execute(
            "INSERT INTO party_fingerprints (source_id, side) VALUES (?, 'buyer')",
            (f"bg{i}",),
        )
    # 7-token phrase
    for i in range(2):
        conn.execute(
            "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
            "VALUES (?, 'buyer', 'brand_phrase', "
            "'her majesty queen right province ontario represented', 'party_name')",
            (f"hm{i}",),
        )
        for tok in ("her", "majesty", "queen", "right", "province", "ontario", "represented"):
            conn.execute(
                "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
                "VALUES (?, 'buyer', 'brand_token', ?, 'party_name')",
                (f"hm{i}", tok),
            )
        conn.execute(
            "INSERT OR IGNORE INTO party_fingerprints (source_id, side) VALUES (?, 'buyer')",
            (f"hm{i}",),
        )
    conn.commit()

    build_brand_index(conn, min_idf=0.0)
    build_long_phrase_index(conn, min_idf=0.0)

    rows = list(conn.execute(
        "SELECT phrase, n_tokens, n_party_sides FROM brand_long_phrase_summary"
    ))
    # 'her' is in the cleanco/STOP_BRAND_TOKENS strip — tokenize_brand drops 'the','of','and','a','an','&','co','inc','ltd','llc','corp'
    # 'her' is NOT in STOP_BRAND_TOKENS, so all 7 tokens survive.
    assert len(rows) == 1
    row = rows[0]
    assert row["phrase"] == "her majesty queen right province ontario represented"
    assert row["n_tokens"] == 7
    assert row["n_party_sides"] == 2


def test_build_long_phrase_index_skips_phrases_with_fewer_than_6_tokens():
    from cleo.discovery_v2.brand_index import build_brand_index, build_long_phrase_index

    conn = _make_db()
    for i in range(100):
        conn.execute(
            "INSERT INTO party_fingerprints (source_id, side) VALUES (?, 'buyer')",
            (f"bg{i}",),
        )
    # 5-token phrase — should be SKIPPED by long-phrase silo
    conn.execute(
        "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
        "VALUES ('q1', 'buyer', 'brand_phrase', 'majesty queen right province ontario', 'party_name')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO party_fingerprints (source_id, side) VALUES ('q1', 'buyer')"
    )
    conn.commit()

    build_brand_index(conn, min_idf=0.0)
    build_long_phrase_index(conn, min_idf=0.0)

    n = conn.execute("SELECT COUNT(*) FROM brand_long_phrase_summary").fetchone()[0]
    assert n == 0


def test_build_address_root_summary_aggregates_across_suffix_variants():
    from cleo.discovery_v2.brand_index import build_address_root_summary

    conn = _make_db()
    # 5 sides at "66 wellington street" + 2 sides at "66 wellington" (no suffix)
    # = 7 sides at root "66 wellington" with 2 distinct suffix variants
    rows = [
        ("RT1", "buyer", "66", "wellington", "street", "M5K1H6"),
        ("RT2", "buyer", "66", "wellington", "street", "M5K1H6"),
        ("RT3", "buyer", "66", "wellington", "street", "M5K1A2"),
        ("RT4", "buyer", "66", "wellington", "street", "M5K1A2"),
        ("RT5", "buyer", "66", "wellington", "street", "M5K1H6"),
        ("RT6", "buyer", "66", "wellington", None, None),
        ("RT7", "buyer", "66", "wellington", "", ""),
    ]
    for sid, side, num, name, suf, postal in rows:
        conn.execute(
            """INSERT INTO party_fingerprints (source_id, side,
                 street_number, street_name, street_suffix, postal)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (sid, side, num, name, suf, postal),
        )
    conn.commit()

    build_address_root_summary(conn, verbose=False)

    row = conn.execute(
        """SELECT n_party_sides, n_distinct_suffixes, n_distinct_postals
           FROM address_root_summary
           WHERE street_number = '66' AND street_name = 'wellington'"""
    ).fetchone()
    assert row is not None
    # All 7 rows roll up
    assert row["n_party_sides"] == 7
    # Distinct suffixes: 'street', '' (NULL coalesces to ''). Empty string and NULL both match COALESCE(.., '').
    # So distinct values are: 'street' and '' → 2.
    assert row["n_distinct_suffixes"] == 2
    # Distinct postals: M5K1H6, M5K1A2, '' → 3
    assert row["n_distinct_postals"] == 3


def test_build_address_root_summary_skips_partial_addresses():
    """Rows missing street_number OR street_name are excluded."""
    from cleo.discovery_v2.brand_index import build_address_root_summary

    conn = _make_db()
    # Only RT1 has both fields — the rest should be excluded.
    conn.execute(
        "INSERT INTO party_fingerprints (source_id, side, street_number, street_name, street_suffix) "
        "VALUES ('RT1', 'buyer', '100', 'king', 'street')"
    )
    conn.execute(
        "INSERT INTO party_fingerprints (source_id, side, street_number, street_name) "
        "VALUES ('RT2', 'buyer', '100', NULL)"
    )
    conn.execute(
        "INSERT INTO party_fingerprints (source_id, side, street_number, street_name) "
        "VALUES ('RT3', 'buyer', NULL, 'king')"
    )
    conn.commit()

    build_address_root_summary(conn, verbose=False)

    rows = list(conn.execute("SELECT street_number, street_name, n_party_sides FROM address_root_summary"))
    assert len(rows) == 1
    assert rows[0]["street_number"] == "100"
    assert rows[0]["street_name"] == "king"
    assert rows[0]["n_party_sides"] == 1
