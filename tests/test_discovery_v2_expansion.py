import re
import sqlite3
import pytest

from cleo.discovery_v2.stems import build_stems
from cleo.discovery_v2.anchor_scores import build_anchor_scores
from cleo.discovery_v2.seeding import build_seeds
from cleo.discovery_v2.expansion import build_expansion


def _make_db():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE party_fingerprints (
            source_id TEXT, side TEXT, phone TEXT, contact_fingerprint TEXT,
            city TEXT,
            street_number TEXT, street_name TEXT, street_suffix TEXT, street_direction TEXT,
            suite_type TEXT, suite_number TEXT,
            PRIMARY KEY (source_id, side)
        );
        CREATE TABLE party_atoms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT, side TEXT, atom_type TEXT, atom_value TEXT, source_field TEXT
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
        CREATE TABLE auto_groups (
            auto_group_id TEXT PRIMARY KEY, canonical_stem TEXT NOT NULL,
            display_name TEXT NOT NULL, tier TEXT NOT NULL,
            confidence REAL NOT NULL, n_anchors INTEGER NOT NULL,
            n_members INTEGER NOT NULL, discovered_at TEXT
        );
        CREATE TABLE auto_group_anchors (
            auto_group_id TEXT NOT NULL, anchor_type TEXT NOT NULL,
            anchor_value TEXT NOT NULL, score REAL NOT NULL,
            PRIMARY KEY (auto_group_id, anchor_type, anchor_value)
        );
        CREATE TABLE auto_group_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            auto_group_id TEXT NOT NULL,
            member_type TEXT NOT NULL,
            source_id TEXT, side TEXT, corp_name TEXT,
            match_score REAL NOT NULL
        );
        CREATE TABLE auto_group_overrides (
            id INTEGER PRIMARY KEY AUTOINCREMENT, auto_group_id TEXT NOT NULL,
            action TEXT NOT NULL, user_id TEXT NOT NULL, action_at TEXT, notes TEXT
        );
        CREATE TABLE auto_group_merges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_auto_group_id TEXT NOT NULL, child_auto_group_id TEXT NOT NULL,
            user_id TEXT NOT NULL, action_at TEXT, notes TEXT
        );
        CREATE TABLE auto_anchor_overrides (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            anchor_type TEXT NOT NULL, anchor_value TEXT NOT NULL,
            override_stem TEXT, override_service_provider INTEGER NOT NULL DEFAULT 0,
            user_id TEXT NOT NULL, action_at TEXT
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


def _seed(conn, sid, side, phrase, *, phone=None, contact=None,
          city=None, street_number=None, street_name=None, street_suffix=None,
          street_direction=None, suite_type=None, suite_number=None):
    conn.execute(
        """INSERT OR IGNORE INTO party_fingerprints
             (source_id, side, phone, contact_fingerprint, city,
              street_number, street_name, street_suffix, street_direction,
              suite_type, suite_number)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (sid, side, phone, contact, city, street_number, street_name,
         street_suffix, street_direction, suite_type, suite_number),
    )
    if phrase:
        conn.execute(
            "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
            "VALUES (?, ?, 'brand_phrase', ?, 'party_name')",
            (sid, side, phrase),
        )


def _build_pipeline(conn):
    build_stems(conn, verbose=False)
    build_anchor_scores(conn, verbose=False)
    build_seeds(conn, verbose=False)


def test_direct_stem_hit_attaches_to_group():
    conn = _make_db()
    # Seed a Skyline group (8 strong sides).
    for i in range(8):
        _seed(conn, f'STRONG{i}', 'buyer', 'skyline real estate holdings',
              phone='P1', contact='jc',
              street_number='5', street_name='douglas', street_suffix='st')
    # Add a 'no-other-anchor' party-side whose phrase IS skyline.
    _seed(conn, 'EXTRA1', 'buyer', 'skyline retail real estate holdings')
    _build_pipeline(conn)

    build_expansion(conn, verbose=False)

    members = conn.execute("""
        SELECT * FROM auto_group_members
        WHERE source_id='EXTRA1' AND side='buyer' AND member_type='party_side'
    """).fetchall()
    assert len(members) == 1
    assert members[0]['match_score'] >= 1.0  # direct stem hit


def test_phone_match_attaches_without_contradiction():
    conn = _make_db()
    # Seed a Skyline group with phone P1.
    for i in range(8):
        _seed(conn, f'STRONG{i}', 'buyer', 'skyline real estate holdings',
              phone='P1', contact='jc',
              street_number='5', street_name='douglas', street_suffix='st')
    # Add a side at phone P1 with no brand phrase at all.
    _seed(conn, 'BLANK1', 'buyer', None, phone='P1')
    _build_pipeline(conn)
    build_expansion(conn, verbose=False)

    rows = conn.execute(
        """SELECT * FROM auto_group_members
            WHERE source_id='BLANK1' AND side='buyer' AND member_type='party_side'"""
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]['match_score'] == pytest.approx(0.7)


def test_phone_match_with_contradicting_stem_does_not_attach():
    conn = _make_db()
    # Seed Skyline group at phone P1.
    for i in range(8):
        _seed(conn, f'STRONG{i}', 'buyer', 'skyline real estate holdings',
              phone='P1', contact='jc',
              street_number='5', street_name='douglas', street_suffix='st')
    # Seed a Kingsett group at phone P2 (separate group).
    conn.execute(
        """INSERT INTO brand_token_summary
             (token, idf, n_party_sides, n_distinct_phrases, is_distinctive,
              is_excluded, wordfreq_zipf, is_english_common, is_place_name,
              is_industry_stopword, filter_reason, position_consistency,
              total_child_coverage, is_position_anchor, discovered_at)
           VALUES ('kingsett', 6.50, 100, 10, 1, 0, 0.0, 0, 0, 0, NULL, NULL, NULL, 0, '2026')"""
    )
    for i in range(8):
        _seed(conn, f'KS{i}', 'buyer', 'kingsett capital',
              phone='P2', contact='ks_jc',
              street_number='40', street_name='king', street_suffix='st')
    # Add a side at phone P1 (Skyline) but whose phrase is 'kingsett capital' (Kingsett).
    _seed(conn, 'CONTRA', 'buyer', 'kingsett capital', phone='P1')
    _build_pipeline(conn)
    build_expansion(conn, verbose=False)

    # Should NOT be attached to the Skyline group (contradiction).
    skyline_groups = [r for r in conn.execute(
        "SELECT auto_group_id FROM auto_groups WHERE canonical_stem='skyline'"
    )]
    skyline_id = skyline_groups[0]['auto_group_id'] if skyline_groups else None
    if skyline_id is not None:
        contra_rows = conn.execute(
            "SELECT * FROM auto_group_members WHERE auto_group_id=? AND source_id='CONTRA'",
            (skyline_id,),
        ).fetchall()
        assert len(contra_rows) == 0


def test_numbered_corp_attached_as_separate_member_row():
    conn = _make_db()
    for i in range(8):
        _seed(conn, f'STRONG{i}', 'buyer', 'skyline real estate holdings',
              phone='P1', contact='jc',
              street_number='5', street_name='douglas', street_suffix='st')
    # Add a side at the same address with a numbered Ontario corp phrase.
    _seed(conn, 'CORP1', 'buyer', '1234567 ontario',
          phone='P1',
          street_number='5', street_name='douglas', street_suffix='st')
    _build_pipeline(conn)
    build_expansion(conn, verbose=False)

    corps = conn.execute(
        "SELECT * FROM auto_group_members WHERE member_type='numbered_corp'"
    ).fetchall()
    assert len(corps) >= 1
    assert any(r['corp_name'] == '1234567 ontario' for r in corps)


def test_no_anchor_no_stem_party_does_not_attach_via_address_alone():
    """The TD Bank case: a party at a multi-tenant building's root has no phone,
    no contact, no stem-mapped brand. Should NOT attach to any group via
    address-root-alone matching (which is now disallowed)."""
    conn = _make_db()
    # Seed a Skyline group with anchors at a SPECIFIC unit (suite 4400)
    for i in range(8):
        _seed(conn, f'STRONG{i}', 'buyer', 'skyline real estate holdings',
              phone='P1', contact='jc',
              city='toronto', street_number='66', street_name='wellington',
              street_suffix='street', street_direction='west',
              suite_type='suite', suite_number='4400')
    # Add a party at the SAME ROOT but DIFFERENT UNIT (floor 30 instead of suite 4400),
    # no phone, no contact, no stem-mapped brand.
    _seed(conn, 'TD_LIKE', 'seller', 'the toronto dominion bank',
          city='toronto', street_number='66', street_name='wellington',
          street_suffix='street', street_direction='west',
          suite_type='floor', suite_number='30th flr')
    _build_pipeline(conn)
    build_expansion(conn, verbose=False)

    # Should NOT be attached to the Skyline group.
    skyline = [r for r in conn.execute(
        "SELECT auto_group_id FROM auto_groups WHERE canonical_stem='skyline'"
    )]
    if skyline:
        rows = conn.execute(
            "SELECT * FROM auto_group_members WHERE auto_group_id=? AND source_id='TD_LIKE'",
            (skyline[0]['auto_group_id'],),
        ).fetchall()
        assert len(rows) == 0


def test_address_unit_match_attaches_to_group():
    """A party at the SAME unit as a group's address_unit anchor attaches via
    that anchor (no other identifying data needed because the unit is
    uniquely tenanted)."""
    conn = _make_db()
    for i in range(8):
        _seed(conn, f'STRONG{i}', 'buyer', 'skyline real estate holdings',
              phone='P1', contact='jc',
              city='toronto', street_number='66', street_name='wellington',
              street_suffix='street', street_direction='west',
              suite_type='suite', suite_number='4400')
    # Add a party at the same UNIT (suite 4400) but no phone, no contact, no brand.
    _seed(conn, 'EXTRA', 'seller', None,
          city='toronto', street_number='66', street_name='wellington',
          street_suffix='street', street_direction='west',
          suite_type='suite', suite_number='4400')
    _build_pipeline(conn)
    build_expansion(conn, verbose=False)

    skyline = [r for r in conn.execute(
        "SELECT auto_group_id FROM auto_groups WHERE canonical_stem='skyline'"
    )]
    assert len(skyline) >= 1
    gid = skyline[0]['auto_group_id']
    rows = conn.execute(
        "SELECT * FROM auto_group_members WHERE auto_group_id=? AND source_id='EXTRA'",
        (gid,),
    ).fetchall()
    assert len(rows) == 1
    # MATCH_SCORE_ADDRESS_UNIT_ALONE = 0.7
    assert rows[0]['match_score'] >= 0.5
