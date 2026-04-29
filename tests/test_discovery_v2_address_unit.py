import sqlite3
import pytest
from cleo.discovery_v2.brand_index import build_address_unit_summary


def _make_db():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE party_fingerprints (
            source_id TEXT, side TEXT, city TEXT,
            street_number TEXT, street_name TEXT, street_suffix TEXT,
            street_direction TEXT, suite_type TEXT, suite_number TEXT,
            phone TEXT, contact_fingerprint TEXT,
            PRIMARY KEY (source_id, side)
        );
        CREATE TABLE party_atoms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT, side TEXT, atom_type TEXT, atom_value TEXT, source_field TEXT
        );
        CREATE TABLE brand_stem_phrase_map (
            phrase TEXT PRIMARY KEY, stem TEXT NOT NULL, confidence REAL NOT NULL
        );
        CREATE TABLE address_unit_summary (
            city TEXT NOT NULL,
            street_number TEXT NOT NULL,
            street_name TEXT NOT NULL,
            street_suffix TEXT NOT NULL DEFAULT '',
            street_direction TEXT NOT NULL DEFAULT '',
            suite_type TEXT NOT NULL DEFAULT '',
            suite_number TEXT NOT NULL DEFAULT '',
            n_party_sides INTEGER NOT NULL,
            n_distinct_brand_stems INTEGER NOT NULL,
            dominant_stem TEXT,
            dominance_share REAL,
            discovered_at TEXT,
            PRIMARY KEY (city, street_number, street_name, street_suffix,
                         street_direction, suite_type, suite_number)
        );
    """)
    return conn


def _seed_party(conn, sid, side, **fields):
    base = dict(city=None, street_number=None, street_name=None, street_suffix=None,
                street_direction=None, suite_type=None, suite_number=None,
                phone=None, contact_fingerprint=None)
    base.update(fields)
    conn.execute(
        """INSERT INTO party_fingerprints
            (source_id, side, city, street_number, street_name, street_suffix,
             street_direction, suite_type, suite_number, phone, contact_fingerprint)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (sid, side, base['city'], base['street_number'], base['street_name'],
         base['street_suffix'], base['street_direction'],
         base['suite_type'], base['suite_number'],
         base['phone'], base['contact_fingerprint']),
    )


def _seed_phrase(conn, sid, side, phrase, stem):
    conn.execute(
        "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
        "VALUES (?, ?, 'brand_phrase', ?, 'party_name')",
        (sid, side, phrase),
    )
    conn.execute(
        "INSERT OR IGNORE INTO brand_stem_phrase_map (phrase, stem, confidence) VALUES (?, ?, 1.0)",
        (phrase, stem),
    )


def test_build_address_unit_summary_aggregates_by_full_unit_key():
    conn = _make_db()
    # Two parties at the same unit, one mapped, one unmapped
    _seed_party(conn, 'RT1', 'buyer', city='toronto', street_number='66',
                street_name='wellington', street_suffix='street',
                street_direction='west', suite_type='suite', suite_number='4400')
    _seed_party(conn, 'RT2', 'buyer', city='toronto', street_number='66',
                street_name='wellington', street_suffix='street',
                street_direction='west', suite_type='suite', suite_number='4400')
    _seed_phrase(conn, 'RT1', 'buyer', 'kingsett capital', 'kingsett')

    build_address_unit_summary(conn, verbose=False)

    rows = conn.execute(
        """SELECT city, street_number, street_name, street_suffix, street_direction,
                  suite_type, suite_number, n_party_sides, dominant_stem
           FROM address_unit_summary"""
    ).fetchall()
    assert len(rows) == 1
    r = dict(rows[0])
    assert r['n_party_sides'] == 2
    assert r['dominant_stem'] == 'kingsett'


def test_build_address_unit_summary_distinct_units_at_same_root():
    conn = _make_db()
    _seed_party(conn, 'RT1', 'buyer', city='toronto', street_number='66',
                street_name='wellington', street_suffix='street',
                street_direction='west', suite_type='suite', suite_number='4400')
    _seed_party(conn, 'RT2', 'buyer', city='toronto', street_number='66',
                street_name='wellington', street_suffix='street',
                street_direction='west', suite_type='suite', suite_number='4100')
    _seed_party(conn, 'RT3', 'buyer', city='toronto', street_number='66',
                street_name='wellington', street_suffix='street',
                street_direction='west', suite_type='floor', suite_number='30th flr')
    _seed_phrase(conn, 'RT1', 'buyer', 'kingsett capital', 'kingsett')
    _seed_phrase(conn, 'RT2', 'buyer', 'weirfoulds llp', 'weirfoulds')

    build_address_unit_summary(conn, verbose=False)

    rows = conn.execute('SELECT * FROM address_unit_summary ORDER BY suite_number').fetchall()
    assert len(rows) == 3  # 3 distinct units at same root


def test_build_address_unit_summary_dominance_calculation():
    """Suite 4400: 4 parties total. 3 map to kingsett, 1 to other. Dominance = 3/4 = 0.75."""
    conn = _make_db()
    for sid in ('RT1', 'RT2', 'RT3'):
        _seed_party(conn, sid, 'buyer', city='toronto', street_number='66',
                    street_name='wellington', street_suffix='street',
                    street_direction='west', suite_type='suite', suite_number='4400')
        _seed_phrase(conn, sid, 'buyer', 'kingsett capital', 'kingsett')
    _seed_party(conn, 'RT4', 'buyer', city='toronto', street_number='66',
                street_name='wellington', street_suffix='street',
                street_direction='west', suite_type='suite', suite_number='4400')
    _seed_phrase(conn, 'RT4', 'buyer', 'random other corp', 'random')

    build_address_unit_summary(conn, verbose=False)

    row = conn.execute(
        "SELECT * FROM address_unit_summary WHERE suite_number='4400'"
    ).fetchone()
    assert row['n_party_sides'] == 4
    assert row['dominant_stem'] == 'kingsett'
    assert row['dominance_share'] == pytest.approx(0.75)
    assert row['n_distinct_brand_stems'] == 2


def test_build_address_unit_summary_skips_parties_without_city_or_street():
    """A party with no city or no street_number should NOT be in the summary."""
    conn = _make_db()
    _seed_party(conn, 'RT1', 'buyer', city='toronto', street_number='66', street_name='wellington')
    _seed_party(conn, 'RT2', 'buyer', street_number='66', street_name='wellington')  # no city
    _seed_party(conn, 'RT3', 'buyer', city='toronto', street_name='wellington')  # no street_number

    build_address_unit_summary(conn, verbose=False)
    rows = conn.execute('SELECT * FROM address_unit_summary').fetchall()
    assert len(rows) == 1
    assert rows[0]['street_number'] == '66'


def test_build_address_unit_summary_idempotent():
    conn = _make_db()
    _seed_party(conn, 'RT1', 'buyer', city='toronto', street_number='66',
                street_name='wellington', street_suffix='street')
    build_address_unit_summary(conn, verbose=False)
    build_address_unit_summary(conn, verbose=False)
    cnt = conn.execute('SELECT COUNT(*) FROM address_unit_summary').fetchone()[0]
    assert cnt == 1
