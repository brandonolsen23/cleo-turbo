"""
Tests for contact tenure establishment and distinctiveness checking.

Uses in-memory SQLite for DB-dependent tests, and constructed data for
pure-logic tests.
"""

import sqlite3
import pytest
from cleo.discovery.types import ContactTenure, Cluster
from cleo.discovery.contacts import (
    build_contact_tenures,
    check_distinctiveness,
    is_contact_in_tenure,
    is_distinctive_contact,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db():
    """Create a minimal in-memory SQLite DB with the tables/data needed."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE contacts (
            id TEXT PRIMARY KEY,
            name_fingerprint TEXT NOT NULL,
            display_name TEXT
        );

        CREATE TABLE transactions (
            source_id TEXT PRIMARY KEY,
            sale_date TEXT
        );

        CREATE TABLE transaction_parties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT NOT NULL,
            contact_id TEXT,
            group_id TEXT
        );
    """)
    return conn


def _make_cluster(cluster_id, member_group_ids):
    return Cluster(
        cluster_id=cluster_id,
        anchor_group_id=list(member_group_ids)[0],
        anchor_name='Test Anchor',
        member_group_ids=set(member_group_ids),
    )


# ---------------------------------------------------------------------------
# Test 1: build_contact_tenures — basic DB query
# ---------------------------------------------------------------------------

class TestBuildContactTenures:
    def test_builds_tenure_from_db(self):
        """Single contact appearing in two transactions for the same group -> one tenure window."""
        db = _make_db()
        db.execute("INSERT INTO contacts VALUES ('CON_001', 'DAN HAGLER', 'Dan Hagler')")
        db.execute("INSERT INTO transactions VALUES ('RT100', '2022-01-15')")
        db.execute("INSERT INTO transactions VALUES ('RT101', '2023-06-20')")
        db.execute("INSERT INTO transaction_parties VALUES (NULL, 'RT100', 'CON_001', 'GRP_A')")
        db.execute("INSERT INTO transaction_parties VALUES (NULL, 'RT101', 'CON_001', 'GRP_A')")

        tenures = build_contact_tenures(db)

        assert 'DAN HAGLER' in tenures
        window_list = tenures['DAN HAGLER']
        assert len(window_list) == 1
        window = window_list[0]
        assert window.contact_id == 'CON_001'
        assert window.group_id == 'GRP_A'
        assert window.first_seen == '2022-01-15'
        assert window.last_seen == '2023-06-20'
        assert window.transaction_count == 2

    def test_contact_in_multiple_groups(self):
        """Contact appearing in two different groups -> two tenure windows."""
        db = _make_db()
        db.execute("INSERT INTO contacts VALUES ('CON_001', 'DAN HAGLER', 'Dan Hagler')")
        db.execute("INSERT INTO transactions VALUES ('RT100', '2022-01-15')")
        db.execute("INSERT INTO transactions VALUES ('RT200', '2023-06-20')")
        db.execute("INSERT INTO transaction_parties VALUES (NULL, 'RT100', 'CON_001', 'GRP_A')")
        db.execute("INSERT INTO transaction_parties VALUES (NULL, 'RT200', 'CON_001', 'GRP_B')")

        tenures = build_contact_tenures(db)

        assert 'DAN HAGLER' in tenures
        window_list = tenures['DAN HAGLER']
        assert len(window_list) == 2
        group_ids = {w.group_id for w in window_list}
        assert group_ids == {'GRP_A', 'GRP_B'}

    def test_skips_null_contact_id(self):
        """Rows where contact_id IS NULL should be ignored."""
        db = _make_db()
        db.execute("INSERT INTO transactions VALUES ('RT100', '2022-01-15')")
        db.execute("INSERT INTO transaction_parties VALUES (NULL, 'RT100', NULL, 'GRP_A')")

        tenures = build_contact_tenures(db)
        assert tenures == {}

    def test_skips_null_group_id(self):
        """Rows where group_id IS NULL should be ignored."""
        db = _make_db()
        db.execute("INSERT INTO contacts VALUES ('CON_001', 'DAN HAGLER', 'Dan Hagler')")
        db.execute("INSERT INTO transactions VALUES ('RT100', '2022-01-15')")
        db.execute("INSERT INTO transaction_parties VALUES (NULL, 'RT100', 'CON_001', NULL)")

        tenures = build_contact_tenures(db)
        assert tenures == {}

    def test_skips_null_sale_date(self):
        """Rows where sale_date IS NULL should be ignored."""
        db = _make_db()
        db.execute("INSERT INTO contacts VALUES ('CON_001', 'DAN HAGLER', 'Dan Hagler')")
        db.execute("INSERT INTO transactions VALUES ('RT100', NULL)")
        db.execute("INSERT INTO transaction_parties VALUES (NULL, 'RT100', 'CON_001', 'GRP_A')")

        tenures = build_contact_tenures(db)
        assert tenures == {}


# ---------------------------------------------------------------------------
# Test 2: check_distinctiveness — single cluster
# ---------------------------------------------------------------------------

class TestDistinctiveSingleCluster:
    def test_distinctive_single_cluster(self):
        """Contact whose groups all belong to the same cluster -> distinctive."""
        tenures = {
            'DAN HAGLER': [
                ContactTenure('CON_001', 'Dan Hagler', 'GRP_A', '2020-01-01', '2022-12-31', 5),
                ContactTenure('CON_001', 'Dan Hagler', 'GRP_B', '2021-03-01', '2023-06-30', 3),
            ]
        }
        cluster = _make_cluster('CL_1', {'GRP_A', 'GRP_B'})
        result = check_distinctiveness(tenures, [cluster])

        for t in result['DAN HAGLER']:
            assert t.is_distinctive is True

    def test_distinctive_single_group_no_cluster(self):
        """Contact in a single group that belongs to no cluster -> still distinctive
        (only one 'domain' regardless)."""
        tenures = {
            'ALICE SMITH': [
                ContactTenure('CON_002', 'Alice Smith', 'GRP_X', '2019-01-01', '2020-12-31', 2),
            ]
        }
        result = check_distinctiveness(tenures, [])

        assert result['ALICE SMITH'][0].is_distinctive is True


# ---------------------------------------------------------------------------
# Test 3: check_distinctiveness — multiple clusters
# ---------------------------------------------------------------------------

class TestNotDistinctiveMultiCluster:
    def test_not_distinctive_multi_cluster(self):
        """Contact whose groups span two different clusters -> not distinctive."""
        tenures = {
            'JOHN DOE': [
                ContactTenure('CON_003', 'John Doe', 'GRP_A', '2018-01-01', '2019-12-31', 4),
                ContactTenure('CON_003', 'John Doe', 'GRP_C', '2018-06-01', '2020-06-30', 3),
            ]
        }
        cluster1 = _make_cluster('CL_1', {'GRP_A', 'GRP_B'})
        cluster2 = _make_cluster('CL_2', {'GRP_C', 'GRP_D'})

        result = check_distinctiveness(tenures, [cluster1, cluster2])

        for t in result['JOHN DOE']:
            assert t.is_distinctive is False


# ---------------------------------------------------------------------------
# Test 4: career change (clean date partition)
# ---------------------------------------------------------------------------

class TestCareerChangeDetected:
    def test_career_change_detected(self):
        """Contact whose groups are in different clusters but dates don't overlap -> distinctive."""
        tenures = {
            'JANE CAREER': [
                # Old job at cluster 1: ended 2018
                ContactTenure('CON_004', 'Jane Career', 'GRP_A', '2015-01-01', '2018-12-31', 7),
                # New job at cluster 2: started 2019 (clean gap)
                ContactTenure('CON_004', 'Jane Career', 'GRP_C', '2019-06-01', '2023-01-01', 5),
            ]
        }
        cluster1 = _make_cluster('CL_1', {'GRP_A', 'GRP_B'})
        cluster2 = _make_cluster('CL_2', {'GRP_C', 'GRP_D'})

        result = check_distinctiveness(tenures, [cluster1, cluster2])

        for t in result['JANE CAREER']:
            assert t.is_distinctive is True

    def test_career_change_same_day_boundary(self):
        """last_seen == first_seen of next tenure is NOT a clean partition (boundary overlap)."""
        tenures = {
            'BOUNDARY CASE': [
                ContactTenure('CON_005', 'Boundary Case', 'GRP_A', '2015-01-01', '2019-01-01', 4),
                ContactTenure('CON_005', 'Boundary Case', 'GRP_C', '2019-01-01', '2022-06-01', 3),
            ]
        }
        cluster1 = _make_cluster('CL_1', {'GRP_A'})
        cluster2 = _make_cluster('CL_2', {'GRP_C'})

        result = check_distinctiveness(tenures, [cluster1, cluster2])

        # last_seen >= first_seen of next → overlap → not distinctive
        for t in result['BOUNDARY CASE']:
            assert t.is_distinctive is False


# ---------------------------------------------------------------------------
# Test 5: overlapping dates — not distinctive
# ---------------------------------------------------------------------------

class TestOverlappingDatesNotDistinctive:
    def test_overlapping_dates_not_distinctive(self):
        """Contact concurrently active in two different clusters -> not distinctive."""
        tenures = {
            'OVERLAP GUY': [
                ContactTenure('CON_006', 'Overlap Guy', 'GRP_A', '2018-01-01', '2022-06-30', 8),
                ContactTenure('CON_006', 'Overlap Guy', 'GRP_C', '2020-03-01', '2023-12-31', 6),
            ]
        }
        cluster1 = _make_cluster('CL_1', {'GRP_A'})
        cluster2 = _make_cluster('CL_2', {'GRP_C'})

        result = check_distinctiveness(tenures, [cluster1, cluster2])

        for t in result['OVERLAP GUY']:
            assert t.is_distinctive is False


# ---------------------------------------------------------------------------
# Test 6: is_distinctive_contact helper
# ---------------------------------------------------------------------------

class TestIsDistinctiveContactHelper:
    def test_is_distinctive_contact_helper(self):
        """is_distinctive_contact() returns True when any tenure window is marked distinctive."""
        tenures = {
            'ALICE SMITH': [
                ContactTenure('CON_002', 'Alice Smith', 'GRP_X', '2019-01-01', '2020-12-31', 2,
                              is_distinctive=True),
            ]
        }
        assert is_distinctive_contact('ALICE SMITH', tenures) is True

    def test_is_not_distinctive_when_false(self):
        """is_distinctive_contact() returns False when all windows are not distinctive."""
        tenures = {
            'BOB JONES': [
                ContactTenure('CON_007', 'Bob Jones', 'GRP_A', '2018-01-01', '2019-12-31', 3,
                              is_distinctive=False),
                ContactTenure('CON_007', 'Bob Jones', 'GRP_C', '2018-06-01', '2020-06-30', 2,
                              is_distinctive=False),
            ]
        }
        assert is_distinctive_contact('BOB JONES', tenures) is False

    def test_is_distinctive_missing_fingerprint(self):
        """is_distinctive_contact() returns False for unknown fingerprints."""
        assert is_distinctive_contact('NOBODY HERE', {}) is False


# ---------------------------------------------------------------------------
# Test 7: is_contact_in_tenure helper
# ---------------------------------------------------------------------------

class TestIsContactInTenure:
    def test_contact_in_tenure_found(self):
        tenures = {
            'DAN HAGLER': [
                ContactTenure('CON_001', 'Dan Hagler', 'GRP_A', '2020-01-01', '2022-12-31', 5),
            ]
        }
        assert is_contact_in_tenure('DAN HAGLER', 'GRP_A', tenures) is True

    def test_contact_in_tenure_wrong_group(self):
        tenures = {
            'DAN HAGLER': [
                ContactTenure('CON_001', 'Dan Hagler', 'GRP_A', '2020-01-01', '2022-12-31', 5),
            ]
        }
        assert is_contact_in_tenure('DAN HAGLER', 'GRP_Z', tenures) is False

    def test_contact_in_tenure_unknown_fingerprint(self):
        assert is_contact_in_tenure('NOBODY', 'GRP_A', {}) is False
