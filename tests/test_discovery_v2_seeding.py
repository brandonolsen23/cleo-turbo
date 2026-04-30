import sqlite3
import pytest

from cleo.discovery_v2.stems import build_stems
from cleo.discovery_v2.anchor_scores import build_anchor_scores
from cleo.discovery_v2.seeding import build_seeds


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
        CREATE TABLE auto_group_anchor_tenures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            auto_group_id TEXT NOT NULL,
            anchor_type TEXT NOT NULL,
            anchor_value TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT,
            n_party_sides_in_window INTEGER NOT NULL,
            dominance_share_in_window REAL NOT NULL,
            score REAL NOT NULL,
            discovered_at TEXT
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
          street_direction=None, suite_type=None, suite_number=None,
          sale_date='2025-01-01'):
    conn.execute(
        """INSERT OR IGNORE INTO party_fingerprints
             (source_id, side, phone, contact_fingerprint, city,
              street_number, street_name, street_suffix, street_direction,
              suite_type, suite_number, sale_date)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (sid, side, phone, contact, city, street_number, street_name,
         street_suffix, street_direction, suite_type, suite_number, sale_date),
    )
    if phrase:
        conn.execute(
            "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
            "VALUES (?, ?, 'brand_phrase', ?, 'party_name')",
            (sid, side, phrase),
        )


def _run_to_anchors(conn):
    build_stems(conn, verbose=False)
    build_anchor_scores(conn, verbose=False)


def test_three_category_convergence_creates_confirmed_group():
    conn = _make_db()
    # 8 skyline party-sides converging on phone P1, address_unit (toronto|5|douglas|st), contact 'jc'.
    for i in range(8):
        _seed(conn, f'TX{i}', 'buyer', 'skyline real estate holdings',
              phone='P1', contact='jc',
              city='toronto', street_number='5', street_name='douglas', street_suffix='st')
    _run_to_anchors(conn)

    build_seeds(conn, verbose=False)

    groups = conn.execute('SELECT * FROM auto_groups').fetchall()
    assert len(groups) == 1
    g = dict(groups[0])
    assert g['canonical_stem'] == 'skyline'
    assert g['tier'] == 'confirmed'
    assert g['n_anchors'] >= 3  # phone + address_unit + contact

    anchors = conn.execute(
        'SELECT * FROM auto_group_anchors WHERE auto_group_id=?', (g['auto_group_id'],)
    ).fetchall()
    types = {a['anchor_type'] for a in anchors}
    assert {'phone', 'contact'}.issubset(types)
    assert 'address_unit' in types


def test_two_category_convergence_creates_probable_group():
    conn = _make_db()
    # 6 skyline at phone P1 + address_unit (toronto|5|douglas|st), no contact.
    for i in range(6):
        _seed(conn, f'TX{i}', 'buyer', 'skyline real estate holdings',
              phone='P1',
              city='toronto', street_number='5', street_name='douglas', street_suffix='st')
    _run_to_anchors(conn)
    build_seeds(conn, verbose=False)
    groups = conn.execute('SELECT * FROM auto_groups').fetchall()
    assert len(groups) == 1
    assert groups[0]['tier'] in ('probable', 'confirmed')
    # Sanity: confidence below confirmed threshold given only 2 categories
    if groups[0]['tier'] == 'probable':
        assert groups[0]['confidence'] < 0.75


def test_pure_single_anchor_does_not_seed():
    conn = _make_db()
    # 6 sides with skyline at phone P1, no other anchors.
    for i in range(6):
        _seed(conn, f'TX{i}', 'buyer', 'skyline real estate holdings', phone='P1')
    _run_to_anchors(conn)
    build_seeds(conn, verbose=False)
    groups = conn.execute('SELECT * FROM auto_groups').fetchall()
    # 1 strong anchor + 0 corroborating → no seed (need >= 2 corroborating
    # anchors total per the candidate-tier rule).
    # NOTE: if the address_unit anchor is also present (it isn't here — no city),
    # the test would need to include the corroborating bar.
    assert len(groups) == 0


def test_reject_override_removes_group():
    conn = _make_db()
    for i in range(8):
        _seed(conn, f'TX{i}', 'buyer', 'skyline real estate holdings',
              phone='P1', contact='jc',
              city='toronto', street_number='5', street_name='douglas', street_suffix='st')
    _run_to_anchors(conn)
    build_seeds(conn, verbose=False)
    groups = conn.execute('SELECT * FROM auto_groups').fetchall()
    assert len(groups) == 1
    gid = groups[0]['auto_group_id']

    # User rejects this group. Re-run seeding; group should be removed.
    conn.execute(
        "INSERT INTO auto_group_overrides (auto_group_id, action, user_id) VALUES (?, 'reject', 'tester')",
        (gid,),
    )
    conn.commit()
    build_seeds(conn, verbose=False)
    groups = conn.execute('SELECT * FROM auto_groups').fetchall()
    assert len(groups) == 0


def test_seeding_populates_auto_group_anchor_tenures():
    """When the pipeline runs end-to-end, auto_group_anchor_tenures is
    populated for every (group, anchor) pair that survived seeding."""
    conn = _make_db()
    for i in range(8):
        _seed(conn, f'TX{i}', 'buyer', 'skyline real estate holdings',
              phone='P1', contact='jc',
              city='toronto', street_number='5', street_name='douglas',
              street_suffix='st')
    _run_to_anchors(conn)
    build_seeds(conn, verbose=False)

    rows = conn.execute(
        "SELECT auto_group_id, anchor_type, anchor_value, "
        "       start_date, end_date FROM auto_group_anchor_tenures"
    ).fetchall()
    assert len(rows) >= 3  # phone + contact + address_unit, at least
    # Each row's auto_group_id must reference an existing auto_group
    gids = {r['auto_group_id'] for r in rows}
    seeded_gids = {r['auto_group_id'] for r in conn.execute(
        "SELECT auto_group_id FROM auto_groups"
    )}
    assert gids.issubset(seeded_gids)


def test_seeding_creates_one_tenure_row_per_pending_tenure():
    """If A2 emitted two tenures for the same anchor (different stems / time
    windows), A3 must create two auto_group_anchor_tenures rows — one in each
    matching stem's group."""
    conn = _make_db()
    # Need brand_token_summary entries for both stems so build_stems promotes them.
    conn.execute(
        """INSERT INTO brand_token_summary
             (token, idf, n_party_sides, n_distinct_phrases, is_distinctive,
              is_excluded, wordfreq_zipf, is_english_common, is_place_name,
              is_industry_stopword, filter_reason, position_consistency,
              total_child_coverage, is_position_anchor, discovered_at)
           VALUES ('dh', 6.0, 50, 10, 1, 0, 0.0, 0, 0, 0, NULL, NULL, NULL, 0, '2026'),
                  ('midland', 6.0, 50, 10, 1, 0, 0.0, 0, 0, 0, NULL, NULL, NULL, 0, '2026')"""
    )
    # Clean promotion phones for each stem (so build_stems verifies them).
    for i in range(6):
        _seed(conn, f'DHCLEAN{i}', 'seller', 'dh management',
              phone='P_DH', contact='dan_h',
              city='toronto', street_number='180', street_name='shorting',
              sale_date=f'2018-0{i+1}-01')
    for i in range(6):
        _seed(conn, f'MDCLEAN{i}', 'seller', 'midland industries',
              phone='P_MD', contact='midland_c',
              city='toronto', street_number='100', street_name='king',
              sale_date=f'2024-0{i+1}-01')
    # Shared phone P1 — DH events 2018, then midland events 2024 (>730d gap)
    for i in range(5):
        _seed(conn, f'DH_S{i}', 'seller', 'dh management',
              phone='P1', sale_date=f'2018-0{i+1}-01')
    for i in range(5):
        _seed(conn, f'MD_S{i}', 'seller', 'midland industries',
              phone='P1', sale_date=f'2024-0{i+1}-01')
    _run_to_anchors(conn)
    build_seeds(conn, verbose=False)

    # Pull all tenures for P1 — should be 2, in different groups
    rows = conn.execute(
        """SELECT agt.auto_group_id, ag.canonical_stem, agt.start_date
           FROM auto_group_anchor_tenures agt
           JOIN auto_groups ag ON ag.auto_group_id = agt.auto_group_id
           WHERE agt.anchor_value = 'P1' AND agt.anchor_type = 'phone'
           ORDER BY agt.start_date"""
    ).fetchall()
    assert len(rows) == 2
    stems = {r['canonical_stem'] for r in rows}
    assert stems == {'dh', 'midland'}


# ── Contact tenure tests (Task 6) ──────────────────────────────────────────

from cleo.discovery_v2.expansion import build_expansion
from cleo.discovery_v2.seeding import build_contact_tenures


def _run_full_pipeline_to_members(conn):
    """A1 → A2 → A3 → A4: produces auto_group_members so contact tenures can build."""
    build_stems(conn, verbose=False)
    build_anchor_scores(conn, verbose=False)
    build_seeds(conn, verbose=False)
    build_expansion(conn, verbose=False)


def _make_db_with_auto_group_members():
    conn = _make_db()
    conn.executescript("""
        CREATE TABLE auto_group_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            auto_group_id TEXT NOT NULL,
            member_type TEXT NOT NULL,
            source_id TEXT, side TEXT, corp_name TEXT,
            match_score REAL NOT NULL
        );
        CREATE TABLE auto_conflict_flags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conflict_type TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_value TEXT NOT NULL,
            entity_subtype TEXT,
            group_a TEXT,
            group_b TEXT,
            date_observed TEXT,
            description TEXT NOT NULL,
            discovered_at TEXT
        );
        CREATE TABLE auto_contact_tenures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_fingerprint TEXT NOT NULL,
            auto_group_id TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT,
            n_party_sides_in_window INTEGER NOT NULL,
            discovered_at TEXT
        );
    """)
    return conn


def test_contact_tenures_built_from_group_members():
    """A contact appearing on parties of a single group produces one tenure
    spanning the contact's first to last event."""
    conn = _make_db_with_auto_group_members()
    # 8 skyline party-sides converging on phone P1, contact 'jc'.
    for i in range(8):
        _seed(conn, f'TX{i}', 'buyer', 'skyline real estate holdings',
              phone='P1', contact='jc',
              city='toronto', street_number='5', street_name='douglas',
              street_suffix='st',
              sale_date=f'2024-0{(i % 9) + 1}-01')
    _run_full_pipeline_to_members(conn)

    build_contact_tenures(conn, verbose=False)

    rows = conn.execute(
        "SELECT auto_group_id, start_date, end_date, n_party_sides_in_window "
        "FROM auto_contact_tenures WHERE contact_fingerprint='jc'"
    ).fetchall()
    assert len(rows) == 1
    r = rows[0]
    assert r['n_party_sides_in_window'] == 8
    assert r['start_date'] == '2024-01-01'


def test_contact_tenures_split_into_two_windows_with_long_gap():
    """A contact at the same group, 5 events 2018, 5 events 2024 (>730d gap)
    → 2 contact tenure rows."""
    conn = _make_db_with_auto_group_members()
    # Need promotion events
    for i in range(5):
        _seed(conn, f'EARLY{i}', 'buyer', 'skyline real estate holdings',
              phone='P1', contact='jc',
              city='toronto', street_number='5', street_name='douglas',
              street_suffix='st',
              sale_date=f'2018-0{i+1}-01')
    for i in range(5):
        _seed(conn, f'LATE{i}', 'buyer', 'skyline real estate holdings',
              phone='P1', contact='jc',
              city='toronto', street_number='5', street_name='douglas',
              street_suffix='st',
              sale_date=f'2024-0{i+1}-01')
    _run_full_pipeline_to_members(conn)

    build_contact_tenures(conn, verbose=False)

    rows = conn.execute(
        "SELECT start_date, end_date, n_party_sides_in_window "
        "FROM auto_contact_tenures WHERE contact_fingerprint='jc' "
        "ORDER BY start_date"
    ).fetchall()
    assert len(rows) == 2
    assert rows[0]['start_date'] == '2018-01-01'
    assert rows[0]['end_date'] == '2018-05-01'
    assert rows[1]['start_date'] == '2024-01-01'


def test_contact_tenures_idempotent():
    conn = _make_db_with_auto_group_members()
    for i in range(8):
        _seed(conn, f'TX{i}', 'buyer', 'skyline real estate holdings',
              phone='P1', contact='jc',
              city='toronto', street_number='5', street_name='douglas',
              street_suffix='st',
              sale_date='2024-06-01')
    _run_full_pipeline_to_members(conn)
    build_contact_tenures(conn, verbose=False)
    build_contact_tenures(conn, verbose=False)
    n = conn.execute("SELECT COUNT(*) FROM auto_contact_tenures").fetchone()[0]
    assert n == 1
