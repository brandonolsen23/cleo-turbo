import sqlite3
import pytest
from cleo.discovery_v2.conflicts import detect_conflicts


def _make_db():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript("""
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
        CREATE TABLE auto_contact_tenures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_fingerprint TEXT NOT NULL,
            auto_group_id TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT,
            n_party_sides_in_window INTEGER NOT NULL
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
    """)
    return conn


def test_anchor_reassignment_flagged():
    """Same anchor with two non-overlapping tenures on different groups."""
    conn = _make_db()
    conn.execute(
        "INSERT INTO auto_group_anchor_tenures "
        "(auto_group_id, anchor_type, anchor_value, "
        " start_date, end_date, n_party_sides_in_window, "
        " dominance_share_in_window, score) VALUES "
        "('AGRP_DH', 'phone', '4162655055', "
        " '2010-01-01', '2014-12-31', 18, 0.95, 5.5)"
    )
    conn.execute(
        "INSERT INTO auto_group_anchor_tenures "
        "(auto_group_id, anchor_type, anchor_value, "
        " start_date, end_date, n_party_sides_in_window, "
        " dominance_share_in_window, score) VALUES "
        "('AGRP_BB', 'phone', '4162655055', "
        " '2016-01-01', NULL, 22, 0.92, 6.1)"
    )

    detect_conflicts(conn, verbose=False)

    flags = conn.execute(
        "SELECT * FROM auto_conflict_flags WHERE conflict_type='anchor_reassignment'"
    ).fetchall()
    assert len(flags) == 1
    assert flags[0]['group_a'] == 'AGRP_DH'
    assert flags[0]['group_b'] == 'AGRP_BB'
    assert flags[0]['entity_value'] == '4162655055'


def test_contact_overlap_flagged():
    conn = _make_db()
    conn.execute(
        "INSERT INTO auto_contact_tenures "
        "(contact_fingerprint, auto_group_id, "
        " start_date, end_date, n_party_sides_in_window) VALUES "
        "('jane_smith', 'AGRP_A', '2015-01-01', '2020-12-31', 12), "
        "('jane_smith', 'AGRP_B', '2018-01-01', '2022-12-31', 8)"
    )
    detect_conflicts(conn, verbose=False)
    flags = conn.execute(
        "SELECT * FROM auto_conflict_flags WHERE conflict_type='contact_overlap'"
    ).fetchall()
    assert len(flags) == 1


def test_transient_tenure_flagged():
    conn = _make_db()
    conn.execute(
        "INSERT INTO auto_group_anchor_tenures "
        "(auto_group_id, anchor_type, anchor_value, "
        " start_date, end_date, n_party_sides_in_window, "
        " dominance_share_in_window, score) VALUES "
        "('AGRP_X', 'address_unit', 'toronto|4950|yonge||||', "
        " '2014-06-01', '2014-06-01', 1, 1.0, 0.69)"
    )
    detect_conflicts(conn, verbose=False)
    flags = conn.execute(
        "SELECT * FROM auto_conflict_flags WHERE conflict_type='transient_tenure'"
    ).fetchall()
    assert len(flags) == 1


def test_abrupt_tenure_end_flagged():
    """Tenure with high volume (>=50) that ended >RECENT_TENURE_DAYS ago without a successor."""
    conn = _make_db()
    conn.execute(
        "INSERT INTO auto_group_anchor_tenures "
        "(auto_group_id, anchor_type, anchor_value, "
        " start_date, end_date, n_party_sides_in_window, "
        " dominance_share_in_window, score) VALUES "
        "('AGRP_X', 'phone', 'P_DEAD', '2018-01-01', '2022-12-31', 200, 0.95, 8.5)"
    )
    detect_conflicts(conn, verbose=False, now='2026-04-30')
    flags = conn.execute(
        "SELECT * FROM auto_conflict_flags WHERE conflict_type='abrupt_tenure_end'"
    ).fetchall()
    assert len(flags) == 1


def test_no_conflicts_for_clean_data():
    """Single tenure per anchor, single group per contact, recent activity → 0 flags."""
    conn = _make_db()
    conn.execute(
        "INSERT INTO auto_group_anchor_tenures "
        "(auto_group_id, anchor_type, anchor_value, "
        " start_date, end_date, n_party_sides_in_window, "
        " dominance_share_in_window, score) VALUES "
        "('AGRP_X', 'phone', 'P', '2024-01-01', NULL, 50, 0.95, 7.2)"
    )
    detect_conflicts(conn, verbose=False, now='2026-04-30')
    flags = conn.execute("SELECT COUNT(*) AS n FROM auto_conflict_flags").fetchone()
    assert flags['n'] == 0


def test_detect_conflicts_is_idempotent():
    """Running twice shouldn't double-emit flags."""
    conn = _make_db()
    conn.execute(
        "INSERT INTO auto_group_anchor_tenures "
        "(auto_group_id, anchor_type, anchor_value, "
        " start_date, end_date, n_party_sides_in_window, "
        " dominance_share_in_window, score) VALUES "
        "('AGRP_DH', 'phone', '4162655055', "
        " '2010-01-01', '2014-12-31', 18, 0.95, 5.5),"
        "('AGRP_BB', 'phone', '4162655055', "
        " '2016-01-01', NULL, 22, 0.92, 6.1)"
    )
    detect_conflicts(conn, verbose=False)
    detect_conflicts(conn, verbose=False)
    flags = conn.execute(
        "SELECT COUNT(*) AS n FROM auto_conflict_flags WHERE conflict_type='anchor_reassignment'"
    ).fetchone()
    assert flags['n'] == 1
