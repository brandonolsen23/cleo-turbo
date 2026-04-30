import math
import sqlite3
import pytest

from cleo.discovery_v2.stems import build_stems
from cleo.discovery_v2.anchor_scores import build_anchor_scores


def _make_db():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE party_fingerprints (
            source_id TEXT, side TEXT, phone TEXT, contact_fingerprint TEXT,
            city TEXT,
            street_number TEXT, street_name TEXT, street_suffix TEXT, street_direction TEXT,
            suite_type TEXT, suite_number TEXT,
            sale_date TEXT,
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
            dominance_share REAL NOT NULL, volume INTEGER NOT NULL, verified_at TEXT
        );
        CREATE TABLE brand_stem_phrase_map (
            phrase TEXT PRIMARY KEY, stem TEXT NOT NULL, confidence REAL NOT NULL
        );
        CREATE TABLE anchor_uniqueness (
            anchor_type TEXT NOT NULL, anchor_value TEXT NOT NULL,
            dominant_stem TEXT, dominance_share REAL,
            volume INTEGER NOT NULL, score REAL NOT NULL,
            is_service_provider INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (anchor_type, anchor_value)
        );
    """)
    conn.execute(
        """INSERT INTO brand_token_summary
             (token, idf, n_party_sides, n_distinct_phrases, is_distinctive,
              is_excluded, wordfreq_zipf, is_english_common, is_place_name,
              is_industry_stopword, filter_reason, position_consistency,
              total_child_coverage, is_position_anchor, discovered_at)
           VALUES ('skyline', 6.13, 100, 10, 1, 0, 0.0, 0, 0, 0, NULL, NULL, NULL, 0, '2026')"""
    )
    return conn


def _seed(conn, source_id, side, phrase, *, phone=None, contact=None,
          city=None, street_number=None, street_name=None, street_suffix=None,
          street_direction=None, suite_type=None, suite_number=None,
          sale_date='2025-01-01'):
    conn.execute(
        """INSERT OR IGNORE INTO party_fingerprints
             (source_id, side, phone, contact_fingerprint, city,
              street_number, street_name, street_suffix, street_direction,
              suite_type, suite_number, sale_date)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (source_id, side, phone, contact, city, street_number, street_name,
         street_suffix, street_direction, suite_type, suite_number, sale_date),
    )
    if phrase:
        conn.execute(
            "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
            "VALUES (?, ?, 'brand_phrase', ?, 'party_name')",
            (source_id, side, phrase),
        )


def test_phone_anchor_scores_correctly_when_stem_dominates():
    conn = _make_db()
    # 6 sides at phone P1, all skyline. After build_stems, skyline is verified.
    for i in range(6):
        _seed(conn, f'TX{i}', 'buyer', 'skyline real estate holdings', phone='P1')
    build_stems(conn, verbose=False)

    build_anchor_scores(conn, verbose=False)

    row = conn.execute(
        "SELECT * FROM anchor_uniqueness WHERE anchor_type='phone' AND anchor_value='P1'"
    ).fetchone()
    assert row is not None
    assert row['dominant_stem'] == 'skyline'
    assert row['volume'] == 6
    assert row['dominance_share'] == pytest.approx(1.0)
    assert row['score'] == pytest.approx(1.0 * math.log(6 + 1))


def test_multi_tenant_phone_has_low_dominance():
    conn = _make_db()
    # First, give skyline a clean anchor so it gets promoted by build_stems
    # (otherwise it stays a candidate and produces no phrase mapping).
    # Phone P0 with 6 skyline sides → dominance 1.0, vol 6 → promoted.
    for i in range(6):
        _seed(conn, f'TX_P0_{i}', 'buyer', 'skyline real estate holdings', phone='P0')
    # Now the multi-tenant test: 5 skyline + 5 unrelated at phone P1.
    for i in range(5):
        _seed(conn, f'TX{i}', 'buyer', 'skyline real estate holdings', phone='P1')
    for i in range(5):
        _seed(conn, f'TX{10+i}', 'buyer', 'random unrelated holdings', phone='P1')
    build_stems(conn, verbose=False)
    build_anchor_scores(conn, verbose=False)
    row = conn.execute(
        "SELECT * FROM anchor_uniqueness WHERE anchor_type='phone' AND anchor_value='P1'"
    ).fetchone()
    # Stems-with-mapping at P1: 5 (skyline). Total: 10. Dominance = 0.5.
    # But verify the formula directly.
    assert row['dominance_share'] <= 0.5 + 0.001
    assert row['dominant_stem'] == 'skyline'  # still the majority of mapped sides


def test_anchor_with_no_mapped_phrases_has_zero_dominance():
    conn = _make_db()
    for i in range(5):
        _seed(conn, f'TX{i}', 'buyer', 'no-stem phrase', phone='P2')
    build_stems(conn, verbose=False)
    build_anchor_scores(conn, verbose=False)
    row = conn.execute(
        "SELECT * FROM anchor_uniqueness WHERE anchor_type='phone' AND anchor_value='P2'"
    ).fetchone()
    # No tenure was emitted (no mapped stems), so no snapshot row.
    assert row is None


def test_address_unit_anchor_scores_with_dominant_stem():
    """6 parties at toronto|66|wellington|street|west|suite|4400, all skyline.
    address_unit anchor score should reflect dominance and volume."""
    conn = _make_db()
    for i in range(6):
        _seed(conn, f'TX{i}', 'buyer', 'skyline real estate holdings',
              city='toronto', street_number='66', street_name='wellington',
              street_suffix='street', street_direction='west',
              suite_type='suite', suite_number='4400')
    build_stems(conn, verbose=False)
    build_anchor_scores(conn, verbose=False)
    row = conn.execute(
        """SELECT * FROM anchor_uniqueness
           WHERE anchor_type='address_unit' AND anchor_value=?""",
        ('toronto|66|wellington|street|west|suite|4400',),
    ).fetchone()
    assert row is not None
    assert row['dominant_stem'] == 'skyline'
    assert row['volume'] == 6
    assert row['dominance_share'] == pytest.approx(1.0)


def test_address_root_and_base_no_longer_in_anchor_uniqueness():
    """After Plan H1, anchor_uniqueness should not contain address_root or address_base rows."""
    conn = _make_db()
    for i in range(6):
        _seed(conn, f'TX{i}', 'buyer', 'skyline real estate holdings',
              city='toronto', street_number='66', street_name='wellington',
              street_suffix='street', street_direction='west',
              suite_type='suite', suite_number='4400')
    build_stems(conn, verbose=False)
    build_anchor_scores(conn, verbose=False)
    types = {r['anchor_type'] for r in conn.execute('SELECT DISTINCT anchor_type FROM anchor_uniqueness')}
    assert 'address_unit' in types
    assert 'address_root' not in types
    assert 'address_base' not in types


def test_anchor_scores_emits_two_tenures_on_stem_change():
    """Phone P1: 5 dh events (early), then 5 midland events 2+ years later → two tenures."""
    conn = _make_db()
    # Need a brand_token_summary row for both stems so build_stems promotes them.
    conn.execute(
        """INSERT INTO brand_token_summary
             (token, idf, n_party_sides, n_distinct_phrases, is_distinctive,
              is_excluded, wordfreq_zipf, is_english_common, is_place_name,
              is_industry_stopword, filter_reason, position_consistency,
              total_child_coverage, is_position_anchor, discovered_at)
           VALUES ('dh', 6.0, 50, 10, 1, 0, 0.0, 0, 0, 0, NULL, NULL, NULL, 0, '2026'),
                  ('midland', 6.0, 50, 10, 1, 0, 0.0, 0, 0, 0, NULL, NULL, NULL, 0, '2026')"""
    )
    # Give each stem its own clean promotion phone so build_stems can achieve
    # dominance >= 0.6 on at least one anchor (same pattern as test_multi_tenant_phone_has_low_dominance).
    for i in range(6):
        _seed(conn, f'DH_P0_{i}', 'seller', 'dh management', phone='P_DH')
    for i in range(6):
        _seed(conn, f'MD_P0_{i}', 'seller', 'midland industries', phone='P_MD')
    # Five DH events 2018-Jan through 2018-May on shared phone P1
    for i in range(5):
        _seed(conn, f'DH{i}', 'seller', 'dh management',
              phone='P1', sale_date=f'2018-0{i+1}-01')
    # Five midland events starting 2022 (2+ year gap) on shared phone P1
    for i in range(5):
        _seed(conn, f'MD{i}', 'seller', 'midland industries',
              phone='P1', sale_date=f'2022-0{i+1}-01')
    build_stems(conn, verbose=False)
    build_anchor_scores(conn, verbose=False)

    pendings = conn.execute(
        "SELECT dominant_stem, start_date, end_date FROM _pending_tenures "
        "WHERE anchor_type='phone' AND anchor_value='P1' "
        "ORDER BY start_date"
    ).fetchall()
    assert len(pendings) == 2
    assert pendings[0]['dominant_stem'] == 'dh'
    assert pendings[1]['dominant_stem'] == 'midland'


def test_anchor_uniqueness_snapshot_picks_latest_tenure():
    """anchor_uniqueness reflects the most recent tenure (snapshot semantics)."""
    conn = _make_db()
    conn.execute(
        """INSERT INTO brand_token_summary
             (token, idf, n_party_sides, n_distinct_phrases, is_distinctive,
              is_excluded, wordfreq_zipf, is_english_common, is_place_name,
              is_industry_stopword, filter_reason, position_consistency,
              total_child_coverage, is_position_anchor, discovered_at)
           VALUES ('dh', 6.0, 50, 10, 1, 0, 0.0, 0, 0, 0, NULL, NULL, NULL, 0, '2026'),
                  ('midland', 6.0, 50, 10, 1, 0, 0.0, 0, 0, 0, NULL, NULL, NULL, 0, '2026')"""
    )
    # Clean promotion phones so each stem achieves >= 0.6 dominance on its anchor.
    for i in range(6):
        _seed(conn, f'DH_P0_{i}', 'seller', 'dh management', phone='P_DH')
    for i in range(6):
        _seed(conn, f'MD_P0_{i}', 'seller', 'midland industries', phone='P_MD')
    # DH events on shared phone in 2018; midland events in 2025 (well within RECENT_TENURE_DAYS).
    for i in range(5):
        _seed(conn, f'DH{i}', 'seller', 'dh management',
              phone='P1', sale_date=f'2018-0{i+1}-01')
    for i in range(5):
        _seed(conn, f'MD{i}', 'seller', 'midland industries',
              phone='P1', sale_date=f'2025-0{i+1}-01')
    build_stems(conn, verbose=False)
    build_anchor_scores(conn, verbose=False)

    row = conn.execute(
        "SELECT dominant_stem FROM anchor_uniqueness "
        "WHERE anchor_type='phone' AND anchor_value='P1'"
    ).fetchone()
    assert row['dominant_stem'] == 'midland'  # latest tenure wins the snapshot


def test_anchor_scores_skips_anchors_without_dated_events():
    conn = _make_db()
    _seed(conn, 'X1', 'seller', 'skyline real estate holdings',
          phone='P_NODATE', sale_date=None)
    build_stems(conn, verbose=False)
    build_anchor_scores(conn, verbose=False)
    rows = conn.execute(
        "SELECT * FROM _pending_tenures WHERE anchor_value='P_NODATE'"
    ).fetchall()
    assert rows == []
