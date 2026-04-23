"""Tests for timeline materialization."""
import sqlite3


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE party_fingerprints (
            source_id TEXT, side TEXT, sale_date TEXT,
            street_number TEXT, street_name TEXT, street_suffix TEXT,
            postal TEXT, phone TEXT, contact_fingerprint TEXT,
            PRIMARY KEY (source_id, side)
        );
        CREATE TABLE atom_party_entities (
            source_id TEXT, side TEXT, group_id TEXT, contact_id TEXT,
            group_link_tier TEXT, contact_link_tier TEXT,
            PRIMARY KEY (source_id, side)
        );
        CREATE TABLE atom_group_addresses (
            group_id TEXT, postal TEXT,
            street_number TEXT, street_name TEXT, street_suffix TEXT,
            first_seen TEXT, last_seen TEXT, n_observations INTEGER
        );
        CREATE TABLE atom_group_phones (
            group_id TEXT, phone TEXT,
            first_seen TEXT, last_seen TEXT, n_observations INTEGER
        );
        CREATE TABLE atom_group_contacts (
            group_id TEXT, contact_id TEXT,
            first_seen TEXT, last_seen TEXT, n_observations INTEGER
        );
        CREATE TABLE atom_contact_groups (
            contact_id TEXT, group_id TEXT,
            first_seen TEXT, last_seen TEXT, n_observations INTEGER
        );
        CREATE TABLE atom_contact_addresses (
            contact_id TEXT, postal TEXT,
            street_number TEXT, street_name TEXT, street_suffix TEXT,
            first_seen TEXT, last_seen TEXT, n_observations INTEGER
        );
    """)
    return conn


def test_group_addresses_timeline_captures_date_ranges():
    from cleo.discovery_v2.timelines import materialize_timelines

    conn = _make_db()
    # Same Group: 3 party-sides at 161 Bay (2000-2010), 4 at 66 Wellington (2012-2020)
    rows = [
        ("RT1", "buyer", "2000-01-01", "161", "bay", "street", "M5J2S1"),
        ("RT2", "buyer", "2005-06-15", "161", "bay", "street", "M5J2S1"),
        ("RT3", "buyer", "2010-03-30", "161", "bay", "street", "M5J2S1"),
        ("RT4", "buyer", "2012-04-01", "66", "wellington", "street", "M5K1H6"),
        ("RT5", "buyer", "2015-08-01", "66", "wellington", "street", "M5K1H6"),
        ("RT6", "buyer", "2018-11-30", "66", "wellington", "street", "M5K1H6"),
        ("RT7", "buyer", "2020-06-01", "66", "wellington", "street", "M5K1H6"),
    ]
    for sid, side, date, num, name, suf, postal in rows:
        conn.execute(
            "INSERT INTO party_fingerprints "
            "(source_id, side, sale_date, street_number, street_name, street_suffix, postal) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (sid, side, date, num, name, suf, postal),
        )
        conn.execute(
            "INSERT INTO atom_party_entities (source_id, side, group_id) VALUES (?, ?, 'AGR_00001')",
            (sid, side),
        )
    conn.commit()

    materialize_timelines(conn)

    rows = conn.execute(
        "SELECT street_number, first_seen, last_seen, n_observations "
        "FROM atom_group_addresses WHERE group_id = 'AGR_00001' "
        "ORDER BY first_seen"
    ).fetchall()
    assert len(rows) == 2
    assert rows[0]["street_number"] == "161"
    assert rows[0]["first_seen"] == "2000-01-01"
    assert rows[0]["last_seen"] == "2010-03-30"
    assert rows[0]["n_observations"] == 3
    assert rows[1]["street_number"] == "66"
    assert rows[1]["n_observations"] == 4


def test_contact_groups_timeline_bridges_multiple_groups():
    """Same Contact appearing at two different Groups over time (career)."""
    from cleo.discovery_v2.timelines import materialize_timelines

    conn = _make_db()
    # RT1,RT2 at Group AGR_01 (2000-2003); RT3,RT4 at Group AGR_02 (2004-2020)
    # Same Contact ACN_0001 throughout.
    for sid, date, group, cfp in [
        ("RT1", "2000-01-01", "AGR_01", "andrew duncan"),
        ("RT2", "2003-06-15", "AGR_01", "andrew duncan"),
        ("RT3", "2004-03-01", "AGR_02", "andrew duncan"),
        ("RT4", "2020-06-01", "AGR_02", "andrew duncan"),
    ]:
        conn.execute(
            "INSERT INTO party_fingerprints "
            "(source_id, side, sale_date, contact_fingerprint) VALUES (?, 'buyer', ?, ?)",
            (sid, date, cfp),
        )
        conn.execute(
            "INSERT INTO atom_party_entities (source_id, side, group_id, contact_id) "
            "VALUES (?, 'buyer', ?, 'ACN_0001')",
            (sid, group),
        )
    conn.commit()

    materialize_timelines(conn)

    rows = conn.execute(
        "SELECT group_id, first_seen, last_seen, n_observations "
        "FROM atom_contact_groups WHERE contact_id = 'ACN_0001' "
        "ORDER BY first_seen"
    ).fetchall()
    assert len(rows) == 2
    assert rows[0]["group_id"] == "AGR_01"
    assert rows[0]["first_seen"] == "2000-01-01"
    assert rows[0]["last_seen"] == "2003-06-15"
    assert rows[1]["group_id"] == "AGR_02"
    assert rows[1]["first_seen"] == "2004-03-01"
