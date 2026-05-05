import sqlite3
import pytest
from cleo.discovery_v2.timelines import (
    build_anchor_timeline,
    iter_all_anchor_timelines,
)


def _make_db():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE party_fingerprints (
            source_id TEXT, side TEXT, phone TEXT, contact_fingerprint TEXT,
            city TEXT,
            street_number TEXT, street_name TEXT, street_suffix TEXT,
            street_direction TEXT, suite_type TEXT, suite_number TEXT,
            sale_date TEXT,
            party_address_canonical TEXT,
            PRIMARY KEY (source_id, side)
        );
        CREATE TABLE party_atoms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT, side TEXT, atom_type TEXT, atom_value TEXT, source_field TEXT
        );
        CREATE TABLE brand_stem_phrase_map (
            phrase TEXT PRIMARY KEY, stem TEXT NOT NULL, confidence REAL NOT NULL
        );
    """)
    return conn


def _seed(conn, sid, side, phrase=None, *, phone=None, contact=None,
          city=None, street_number=None, street_name=None,
          sale_date=None):
    addr_canonical = "|".join([
        (city or "").lower(),
        street_number or "",
        (street_name or "").lower(),
        "",  # street_suffix
        "",  # street_direction
        "",  # suite_type
        "",  # suite_number
    ])
    conn.execute(
        """INSERT INTO party_fingerprints
            (source_id, side, phone, contact_fingerprint,
             city, street_number, street_name, sale_date,
             party_address_canonical)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (sid, side, phone, contact, city, street_number, street_name, sale_date,
         addr_canonical),
    )
    if phrase:
        conn.execute(
            "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
            "VALUES (?, ?, 'brand_phrase', ?, 'party_name')",
            (sid, side, phrase),
        )


def _map(conn, phrase, stem):
    conn.execute(
        "INSERT OR IGNORE INTO brand_stem_phrase_map (phrase, stem, confidence) VALUES (?,?,1.0)",
        (phrase, stem),
    )


def test_anchor_timeline_returns_events_in_chronological_order():
    conn = _make_db()
    _seed(conn, 'RT3', 'seller', 'kingsett capital', phone='P1', sale_date='2020-05-01')
    _seed(conn, 'RT1', 'seller', 'kingsett capital', phone='P1', sale_date='2018-03-01')
    _seed(conn, 'RT2', 'seller', 'kingsett capital', phone='P1', sale_date='2019-07-15')
    _map(conn, 'kingsett capital', 'kingsett')

    events = build_anchor_timeline(conn, 'phone', 'P1')

    dates = [e['sale_date'] for e in events]
    assert dates == sorted(dates)
    assert all(e['stem'] == 'kingsett' for e in events)


def test_anchor_timeline_includes_unmapped_events_with_null_stem():
    conn = _make_db()
    _seed(conn, 'RT1', 'seller', 'kingsett capital', phone='P1', sale_date='2018-03-01')
    _seed(conn, 'RT2', 'seller', 'random co', phone='P1', sale_date='2019-07-15')
    _map(conn, 'kingsett capital', 'kingsett')
    # 'random co' is unmapped — phrase exists in atoms but no stem mapping

    events = build_anchor_timeline(conn, 'phone', 'P1')
    by_id = {e['source_id']: e for e in events}

    assert by_id['RT1']['stem'] == 'kingsett'
    assert by_id['RT2']['stem'] is None  # unmapped


def test_anchor_timeline_excludes_events_without_sale_date():
    conn = _make_db()
    _seed(conn, 'RT1', 'seller', 'kingsett capital', phone='P1', sale_date='2018-03-01')
    _seed(conn, 'RT2', 'seller', 'kingsett capital', phone='P1', sale_date=None)
    _map(conn, 'kingsett capital', 'kingsett')

    events = build_anchor_timeline(conn, 'phone', 'P1')
    assert len(events) == 1
    assert events[0]['source_id'] == 'RT1'


def test_anchor_timeline_address_unit_anchor():
    """Timeline for an address_unit anchor uses the 7-field key."""
    conn = _make_db()
    for sid, dt in (('RT1', '2018-01-01'), ('RT2', '2019-01-01')):
        _seed(conn, sid, 'seller', 'dh management',
              city='toronto', street_number='180', street_name='shorting',
              sale_date=dt)
    _map(conn, 'dh management', 'dh')

    key = 'toronto|180|shorting||||'
    events = build_anchor_timeline(conn, 'address_unit', key)
    assert len(events) == 2
    assert all(e['stem'] == 'dh' for e in events)


def test_iter_all_anchor_timelines_yields_each_anchor_once():
    conn = _make_db()
    # Two phones, three contacts, one address_unit
    _seed(conn, 'RT1', 'seller', 'a', phone='P1', sale_date='2018-01-01')
    _seed(conn, 'RT2', 'seller', 'a', phone='P2', sale_date='2019-01-01')
    _seed(conn, 'RT3', 'seller', 'a', contact='C1', sale_date='2020-01-01')
    _seed(conn, 'RT4', 'seller', 'a',
          city='toronto', street_number='180', street_name='shorting',
          sale_date='2018-06-01')
    _map(conn, 'a', 'alpha')

    timelines = list(iter_all_anchor_timelines(conn))

    types = sorted({(t, v) for t, v, events in timelines})
    assert ('phone', 'P1') in types
    assert ('phone', 'P2') in types
    assert ('contact', 'C1') in types
    assert ('address_unit', 'toronto|180|shorting||||') in types
    assert len(timelines) == 4


def test_iter_all_anchor_timelines_skips_anchors_with_no_dated_events():
    """An anchor whose every party has no sale_date is skipped (Stage A2 cannot
    place it in time anyway)."""
    conn = _make_db()
    _seed(conn, 'RT1', 'seller', 'a', phone='P1', sale_date=None)
    _map(conn, 'a', 'alpha')

    timelines = list(iter_all_anchor_timelines(conn))
    assert len(timelines) == 0


def test_anchor_timeline_returns_empty_for_unknown_anchor():
    conn = _make_db()
    events = build_anchor_timeline(conn, 'phone', 'UNKNOWN_PHONE')
    assert events == []
