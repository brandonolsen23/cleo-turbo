import pytest
from cleo.discovery.types import Signal, Cluster
from cleo.discovery.clustering import build_exact_match_clusters


class TestExactMatchClustering:
    def _make_signals(self):
        """Create signals mimicking DH portfolio: 3 groups sharing address + contact."""
        return [
            # Address signals: all 3 groups at 180 Shorting Rd
            Signal('address', '180 SHORTING RD|TORONTO|M1S 3S7', 'GRP_00001', 'RT184886', 'buyer'),
            Signal('address', '180 SHORTING RD|TORONTO|M1S 3S7', 'GRP_00002', 'RT184886', 'buyer'),
            Signal('address', '180 SHORTING RD|TORONTO|M1S 3S7', 'GRP_00003', 'RT148276', 'buyer'),
            # Contact signals: Dan Hagler on all 3
            Signal('contact', 'DAN HAGLER', 'GRP_00001', 'RT184886', 'buyer'),
            Signal('contact', 'DAN HAGLER', 'GRP_00002', 'RT184886', 'buyer'),
            Signal('contact', 'DAN HAGLER', 'GRP_00003', 'RT148276', 'buyer'),
            # Phone: same phone on 2 groups
            Signal('phone', '4162655055', 'GRP_00001', '', ''),
            Signal('phone', '4162655055', 'GRP_00002', '', ''),
            # Unrelated group at different address
            Signal('address', '100 KING ST|TORONTO|M5H 1A1', 'GRP_00099', 'RT999999', 'buyer'),
        ]

    def test_clusters_groups_by_shared_signals(self):
        signals = self._make_signals()
        clusters = build_exact_match_clusters(signals)
        dh_cluster = None
        for c in clusters:
            if 'GRP_00001' in c.member_group_ids:
                dh_cluster = c
                break
        assert dh_cluster is not None
        assert 'GRP_00002' in dh_cluster.member_group_ids
        assert 'GRP_00003' in dh_cluster.member_group_ids
        assert 'GRP_00099' not in dh_cluster.member_group_ids

    def test_isolated_groups_not_clustered(self):
        signals = self._make_signals()
        clusters = build_exact_match_clusters(signals)
        member_sets = [c.member_group_ids for c in clusters]
        for ms in member_sets:
            if 'GRP_00099' in ms:
                assert len(ms) == 1

    def test_records_shared_signals_on_cluster(self):
        signals = self._make_signals()
        clusters = build_exact_match_clusters(signals)
        dh_cluster = next(c for c in clusters if 'GRP_00001' in c.member_group_ids)
        assert '180 SHORTING RD|TORONTO|M1S 3S7' in dh_cluster.confirmed_addresses
        assert 'DAN HAGLER' in dh_cluster.confirmed_contacts

    def test_returns_only_multi_member_clusters(self):
        """Single-group components should never appear in results."""
        signals = self._make_signals()
        clusters = build_exact_match_clusters(signals)
        for c in clusters:
            assert len(c.member_group_ids) >= 2

    def test_empty_signals_returns_empty(self):
        clusters = build_exact_match_clusters([])
        assert clusters == []

    def test_no_shared_signals_returns_empty(self):
        signals = [
            Signal('address', '1 UNIQUE ST|TORONTO|M1A 1A1', 'GRP_00001', 'RT1', 'buyer'),
            Signal('address', '2 UNIQUE ST|TORONTO|M2B 2B2', 'GRP_00002', 'RT2', 'buyer'),
        ]
        clusters = build_exact_match_clusters(signals)
        assert clusters == []

    def test_confirmed_phones_recorded(self):
        signals = self._make_signals()
        clusters = build_exact_match_clusters(signals)
        dh_cluster = next(c for c in clusters if 'GRP_00001' in c.member_group_ids)
        assert '4162655055' in dh_cluster.confirmed_phones

    def test_confirmed_entities_recorded(self):
        signals = [
            Signal('trade_name', 'ACME HOLDINGS', 'GRP_00010', 'RT1', 'buyer'),
            Signal('trade_name', 'ACME HOLDINGS', 'GRP_00011', 'RT2', 'buyer'),
            Signal('care_of', 'C/O ACME', 'GRP_00010', 'RT1', 'buyer'),
            Signal('care_of', 'C/O ACME', 'GRP_00011', 'RT2', 'buyer'),
        ]
        clusters = build_exact_match_clusters(signals)
        assert len(clusters) == 1
        c = clusters[0]
        assert 'ACME HOLDINGS' in c.confirmed_entities
        assert 'C/O ACME' in c.confirmed_entities

    def test_transitive_connections(self):
        """Groups A-B share address1, B-C share address2. All three should be in one cluster."""
        signals = [
            Signal('address', 'ADDR_1', 'GRP_A', 'RT1', 'buyer'),
            Signal('address', 'ADDR_1', 'GRP_B', 'RT2', 'buyer'),
            Signal('address', 'ADDR_2', 'GRP_B', 'RT3', 'buyer'),
            Signal('address', 'ADDR_2', 'GRP_C', 'RT4', 'buyer'),
        ]
        clusters = build_exact_match_clusters(signals)
        assert len(clusters) == 1
        c = clusters[0]
        assert {'GRP_A', 'GRP_B', 'GRP_C'} == c.member_group_ids

    def test_two_separate_clusters(self):
        """Two independent shared-signal groups should produce two separate clusters."""
        signals = [
            Signal('address', 'SHARED_ADDR_1', 'GRP_001', 'RT1', 'buyer'),
            Signal('address', 'SHARED_ADDR_1', 'GRP_002', 'RT2', 'buyer'),
            Signal('address', 'SHARED_ADDR_2', 'GRP_003', 'RT3', 'buyer'),
            Signal('address', 'SHARED_ADDR_2', 'GRP_004', 'RT4', 'buyer'),
        ]
        clusters = build_exact_match_clusters(signals)
        assert len(clusters) == 2
        all_ids = {gid for c in clusters for gid in c.member_group_ids}
        assert all_ids == {'GRP_001', 'GRP_002', 'GRP_003', 'GRP_004'}
