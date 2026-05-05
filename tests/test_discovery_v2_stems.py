import sqlite3
import pytest

from cleo.discovery_v2.stems import extract_candidate_stem, build_stems


def _make_db():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE party_fingerprints (
            source_id TEXT, side TEXT, phone TEXT,
            street_number TEXT, street_name TEXT,
            PRIMARY KEY (source_id, side)
        );
        CREATE TABLE party_atoms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT, side TEXT,
            atom_type TEXT, atom_value TEXT, source_field TEXT
        );
        CREATE TABLE brand_token_summary (
            token TEXT PRIMARY KEY, idf REAL, n_party_sides INTEGER,
            n_distinct_phrases INTEGER, is_distinctive INTEGER, is_excluded INTEGER,
            wordfreq_zipf REAL, is_english_common INTEGER, is_place_name INTEGER,
            is_industry_stopword INTEGER, filter_reason TEXT,
            position_consistency REAL, total_child_coverage REAL,
            is_position_anchor INTEGER NOT NULL DEFAULT 0,
            discovered_at TEXT
        );
        CREATE TABLE brand_stem (
            stem TEXT PRIMARY KEY, stem_type TEXT NOT NULL,
            dominant_anchor_type TEXT NOT NULL, dominant_anchor_value TEXT NOT NULL,
            dominance_share REAL NOT NULL, volume INTEGER NOT NULL,
            verified_at TEXT
        );
        CREATE TABLE brand_stem_phrase_map (
            phrase TEXT PRIMARY KEY, stem TEXT NOT NULL, confidence REAL NOT NULL
        );
    """)
    # Seed brand_token_summary
    conn.executemany(
        """INSERT INTO brand_token_summary
            (token, idf, n_party_sides, n_distinct_phrases, is_distinctive, is_excluded,
             wordfreq_zipf, is_english_common, is_place_name, is_industry_stopword,
             filter_reason, position_consistency, total_child_coverage,
             is_position_anchor, discovered_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        [
            # distinctive: skyline (idf 6.13), kingsett (6.5)
            ('skyline',  6.13, 539, 50, 1, 0, 0.0, 0, 0, 0, None, None, None, 0, '2026-04-26'),
            ('kingsett', 6.50, 367, 30, 1, 0, 0.0, 0, 0, 0, None, None, None, 0, '2026-04-26'),
            # position-anchor: dd (rare 2-letter operator code), no distinctive
            ('dd',       7.10,  60,  8, 0, 0, 0.0, 0, 0, 0, None, 0.99, 1.0, 1, '2026-04-26'),
            # generic words (filtered)
            ('holdings', 4.20, 17000, 100, 0, 0, 0.0, 0, 0, 1, 'industry', None, None, 0, '2026-04-26'),
            ('real',     3.50, 3500,  20, 0, 0, 0.0, 0, 0, 0, 'english',  None, None, 0, '2026-04-26'),
            ('estate',   3.50, 3700,  20, 0, 0, 0.0, 0, 0, 0, 'english',  None, None, 0, '2026-04-26'),
        ]
    )
    return conn


def _seed_phrase(conn, source_id, side, phrase, phone=None):
    conn.execute(
        "INSERT OR IGNORE INTO party_fingerprints (source_id, side, phone) VALUES (?,?,?)",
        (source_id, side, phone),
    )
    conn.execute(
        "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
        "VALUES (?, ?, 'brand_phrase', ?, 'party_name')",
        (source_id, side, phrase),
    )
    conn.commit()


def _seed_qualifying_phrase(conn, source_id, side, phrase, source_field='care_of', phone=None):
    """Seed a brand_phrase atom in a qualifying source field (trade_name/care_of/companies_json)."""
    conn.execute(
        "INSERT OR IGNORE INTO party_fingerprints (source_id, side, phone) VALUES (?,?,?)",
        (source_id, side, phone),
    )
    conn.execute(
        "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
        "VALUES (?, ?, 'brand_phrase', ?, ?)",
        (source_id, side, phrase, source_field),
    )
    conn.commit()


def test_candidate_stem_picks_highest_idf_distinctive_1gram():
    conn = _make_db()
    out = extract_candidate_stem('skyline real estate holdings', conn)
    assert out == ('skyline', 'distinctive')


def test_candidate_stem_falls_back_to_position_anchor_when_no_distinctive():
    conn = _make_db()
    out = extract_candidate_stem('dd 64 roehampton', conn)
    assert out == ('dd', 'position_anchor')


def test_candidate_stem_returns_none_when_phrase_has_no_signal():
    conn = _make_db()
    out = extract_candidate_stem('the real estate holdings', conn)
    assert out is None


def test_candidate_stem_handles_empty_phrase():
    conn = _make_db()
    assert extract_candidate_stem('', conn) is None
    assert extract_candidate_stem(None, conn) is None


def test_build_stems_promotes_skyline_above_thresholds():
    conn = _make_db()
    # Seed 6 sides at phone P1, 5 of them with skyline phrases (dominance 5/6 = 0.83)
    for i in range(5):
        _seed_phrase(conn, f'TX{i}', 'buyer', 'skyline real estate holdings', phone='P1')
    _seed_phrase(conn, 'TX5', 'buyer', 'something else', phone='P1')

    build_stems(conn, verbose=False)

    rows = conn.execute('SELECT * FROM brand_stem').fetchall()
    stems = {r['stem']: dict(r) for r in rows}
    assert 'skyline' in stems
    assert stems['skyline']['stem_type'] == 'distinctive'
    assert stems['skyline']['dominant_anchor_type'] == 'phone'
    assert stems['skyline']['dominant_anchor_value'] == 'P1'
    assert stems['skyline']['volume'] >= 5
    assert stems['skyline']['dominance_share'] >= 0.6


def test_build_stems_rejects_low_dominance():
    conn = _make_db()
    # 2 sides with skyline at phone P1, 8 sides with random other content at P1.
    # Dominance = 2/10 = 0.2 — below threshold.
    for i in range(2):
        _seed_phrase(conn, f'TX{i}', 'buyer', 'skyline real estate holdings', phone='P1')
    for i in range(8):
        _seed_phrase(conn, f'TX{100+i}', 'buyer', 'something unrelated', phone='P1')

    build_stems(conn, verbose=False)

    rows = conn.execute('SELECT * FROM brand_stem WHERE stem=?', ('skyline',)).fetchall()
    assert len(rows) == 0


def test_build_stems_rejects_low_volume():
    conn = _make_db()
    # Only 3 sides total at P1, all skyline — dominance OK but volume below 5.
    for i in range(3):
        _seed_phrase(conn, f'TX{i}', 'buyer', 'skyline real estate holdings', phone='P1')

    build_stems(conn, verbose=False)

    rows = conn.execute('SELECT * FROM brand_stem WHERE stem=?', ('skyline',)).fetchall()
    assert len(rows) == 0


def test_build_stems_is_idempotent():
    conn = _make_db()
    for i in range(6):
        _seed_phrase(conn, f'TX{i}', 'buyer', 'skyline real estate holdings', phone='P1')
    build_stems(conn, verbose=False)
    build_stems(conn, verbose=False)
    rows = conn.execute('SELECT * FROM brand_stem WHERE stem=?', ('skyline',)).fetchall()
    assert len(rows) == 1


def test_build_stems_picker_prefers_higher_score_when_both_qualify():
    """Both phone and address_root qualify for skyline; verify the picker chose the higher-score one."""
    conn = _make_db()
    # Phone P1: 5 sides, all skyline (dominance 1.0, volume 5)
    for i in range(5):
        _seed_phrase(conn, f'TX{i}', 'buyer', 'skyline real estate holdings', phone='P1')
    # Address (5, douglas): 6 sides, 5 skyline + 1 unrelated (dominance 0.83, volume 6)
    # — same source_ids deliberately so the address co-anchor exists
    for i in range(5):
        conn.execute(
            "UPDATE party_fingerprints SET street_number='5', street_name='douglas' "
            "WHERE source_id=? AND side='buyer'",
            (f'TX{i}',),
        )
    # Add a 6th side at the address only (not at phone P1) with a non-skyline phrase
    conn.execute(
        "INSERT INTO party_fingerprints (source_id, side, phone, street_number, street_name) "
        "VALUES ('TXADDR_ONLY', 'buyer', NULL, '5', 'douglas')"
    )
    conn.execute(
        "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
        "VALUES ('TXADDR_ONLY', 'buyer', 'brand_phrase', 'unrelated other thing', 'party_name')"
    )
    conn.commit()

    build_stems(conn, verbose=False)

    rows = conn.execute('SELECT * FROM brand_stem WHERE stem=?', ('skyline',)).fetchall()
    assert len(rows) == 1
    row = dict(rows[0])
    # Phone score: 1.0 * log(5+1) ≈ 1.79
    # Address score: 0.833 * log(6+1) ≈ 1.62
    # Phone wins.
    assert row['dominant_anchor_type'] == 'phone'
    assert row['dominant_anchor_value'] == 'P1'
    assert row['volume'] == 5
    assert row['dominance_share'] == pytest.approx(1.0)


# ── Second promotion path: qualifying-source-field volume ─────────────────


def test_build_stems_promotes_via_qualifying_source_fields():
    """A stem with no anchor dominance but >= STEM_PROMOTION_VOLUME qualifying-field
    party-sides should be promoted with dominant_anchor_type='qualifying_source'."""
    conn = _make_db()
    # Seed 'kingsett capital' in care_of across 6 distinct party-sides,
    # spread across unrelated addresses/phones so dominance never hits 0.6.
    for i in range(6):
        _seed_qualifying_phrase(
            conn, f'TX{i}', 'seller', 'kingsett capital',
            source_field='care_of', phone=f'P{i}',  # each a different phone
        )
    # No anchor dominance — every phone appears just once (dominance = 1/1 but vol = 1 < 5)
    build_stems(conn, verbose=False)

    rows = conn.execute('SELECT * FROM brand_stem WHERE stem=?', ('kingsett',)).fetchall()
    assert len(rows) == 1, "kingsett should be promoted via qualifying-source-field path"
    row = dict(rows[0])
    assert row['dominant_anchor_type'] == 'qualifying_source'
    assert row['dominant_anchor_value'] == ''
    assert row['dominance_share'] == pytest.approx(1.0)
    assert row['volume'] >= 6

    # Its phrase must also appear in brand_stem_phrase_map
    map_rows = conn.execute(
        'SELECT * FROM brand_stem_phrase_map WHERE stem=?', ('kingsett',)
    ).fetchall()
    assert len(map_rows) >= 1
    phrases = {r['phrase'] for r in map_rows}
    assert 'kingsett capital' in phrases


def test_build_stems_qualifying_source_already_promoted_not_duplicated():
    """A stem promoted via anchor dominance is not double-promoted via qualifying-source path."""
    conn = _make_db()
    # Promote skyline via anchor dominance (6 sides, same phone → dominance 1.0)
    for i in range(6):
        _seed_phrase(conn, f'TX{i}', 'buyer', 'skyline real estate holdings', phone='P1')
    # Also seed skyline phrases in qualifying fields — should not create a second brand_stem row
    for i in range(6, 12):
        _seed_qualifying_phrase(
            conn, f'TX{i}', 'buyer', 'skyline real estate holdings',
            source_field='trade_name',
        )

    build_stems(conn, verbose=False)

    rows = conn.execute('SELECT * FROM brand_stem WHERE stem=?', ('skyline',)).fetchall()
    assert len(rows) == 1, "skyline must appear exactly once in brand_stem"
    # The anchor-dominance path ran first, so the row should reflect anchor dominance
    assert rows[0]['dominant_anchor_type'] != 'qualifying_source'


def test_build_stems_qualifying_source_below_volume_threshold_excluded():
    """A stem appearing in qualifying source fields but on fewer than STEM_PROMOTION_VOLUME
    distinct party-sides is NOT promoted."""
    conn = _make_db()
    # Only 4 qualifying-field sides (< 5 threshold)
    for i in range(4):
        _seed_qualifying_phrase(
            conn, f'TX{i}', 'seller', 'kingsett capital',
            source_field='companies_json', phone=f'P{i}',
        )

    build_stems(conn, verbose=False)

    rows = conn.execute('SELECT * FROM brand_stem WHERE stem=?', ('kingsett',)).fetchall()
    assert len(rows) == 0, "kingsett must NOT be promoted when qualifying-field count < 5"
