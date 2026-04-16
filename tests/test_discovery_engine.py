import pytest
from cleo.discovery.types import Cluster
from cleo.discovery.validation import validate_clusters


class TestValidation:
    def test_perfect_match(self):
        gt = [{'portfolio_name': 'DH', 'anchor_group_id': 'GRP_00001',
               'member_group_ids': {'GRP_00001', 'GRP_00002', 'GRP_00003'}}]
        clusters = [Cluster(
            cluster_id='C1', anchor_group_id='GRP_00001', anchor_name='DH',
            member_group_ids={'GRP_00001', 'GRP_00002', 'GRP_00003'}
        )]
        results = validate_clusters(clusters, gt)
        assert results['DH']['precision'] == 1.0
        assert results['DH']['recall'] == 1.0
        assert results['DH']['missing'] == []
        assert results['DH']['unexpected'] == []

    def test_partial_recall(self):
        gt = [{'portfolio_name': 'DH', 'anchor_group_id': 'GRP_00001',
               'member_group_ids': {'GRP_00001', 'GRP_00002', 'GRP_00003'}}]
        clusters = [Cluster(
            cluster_id='C1', anchor_group_id='GRP_00001', anchor_name='DH',
            member_group_ids={'GRP_00001', 'GRP_00002'}
        )]
        results = validate_clusters(clusters, gt)
        assert results['DH']['recall'] == pytest.approx(2/3, abs=0.01)
        assert 'GRP_00003' in results['DH']['missing']

    def test_false_positive(self):
        gt = [{'portfolio_name': 'DH', 'anchor_group_id': 'GRP_00001',
               'member_group_ids': {'GRP_00001', 'GRP_00002'}}]
        clusters = [Cluster(
            cluster_id='C1', anchor_group_id='GRP_00001', anchor_name='DH',
            member_group_ids={'GRP_00001', 'GRP_00002', 'GRP_00099'}
        )]
        results = validate_clusters(clusters, gt)
        assert results['DH']['precision'] == pytest.approx(2/3, abs=0.01)
        assert 'GRP_00099' in results['DH']['unexpected']

    def test_no_match(self):
        gt = [{'portfolio_name': 'DH', 'anchor_group_id': 'GRP_00001',
               'member_group_ids': {'GRP_00001', 'GRP_00002'}}]
        clusters = [Cluster(
            cluster_id='C1', anchor_group_id='GRP_00050', anchor_name='Other',
            member_group_ids={'GRP_00050', 'GRP_00051'}
        )]
        results = validate_clusters(clusters, gt)
        assert results['DH']['recall'] == 0.0
