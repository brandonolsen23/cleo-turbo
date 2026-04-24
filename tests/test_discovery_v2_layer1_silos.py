"""Integration tests for Layer 1 silo builders."""
import sqlite3


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE party_fingerprints (
            source_id TEXT, side TEXT,
            street_number TEXT, street_name TEXT, street_suffix TEXT,
            suite_type TEXT, suite_number TEXT,
            city TEXT, province TEXT, postal TEXT,
            phone TEXT, contact_fingerprint TEXT,
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
