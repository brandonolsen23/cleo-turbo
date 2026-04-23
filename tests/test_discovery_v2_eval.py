"""Tests for eval metrics against audit portfolios."""


def test_audit_recall_and_purity_perfect_match():
    """When every audit party-side lands in the same atom Group, and that
    Group contains only audit-members, recall and purity are both 100%."""
    from cleo.discovery_v2.eval import compute_audit_metrics

    party_entities = {
        ("RT1", "buyer"): "AGR_0001",
        ("RT2", "buyer"): "AGR_0001",
        ("RT3", "seller"): "AGR_0001",
    }
    audit_parties = [
        {"source_id": "RT1", "side": "buyer"},
        {"source_id": "RT2", "side": "buyer"},
        {"source_id": "RT3", "side": "seller"},
    ]
    metrics = compute_audit_metrics("test-audit", audit_parties, party_entities)
    assert metrics["recall"] == 1.0
    assert metrics["purity"] == 1.0
    assert metrics["dominant_group_id"] == "AGR_0001"
    assert metrics["dominant_group_size"] == 3


def test_audit_recall_less_than_1_when_members_split():
    from cleo.discovery_v2.eval import compute_audit_metrics

    party_entities = {
        ("RT1", "buyer"): "AGR_0001",
        ("RT2", "buyer"): "AGR_0001",
        ("RT3", "seller"): "AGR_0002",  # split off
    }
    audit_parties = [
        {"source_id": "RT1", "side": "buyer"},
        {"source_id": "RT2", "side": "buyer"},
        {"source_id": "RT3", "side": "seller"},
    ]
    metrics = compute_audit_metrics("test-audit", audit_parties, party_entities)
    assert metrics["recall"] == 2 / 3
    assert metrics["dominant_group_size"] == 2


def test_audit_purity_less_than_1_when_group_contains_nonaudit_members():
    from cleo.discovery_v2.eval import compute_audit_metrics

    party_entities = {
        ("RT1", "buyer"): "AGR_0001",
        ("RT2", "buyer"): "AGR_0001",
        ("RT_other", "buyer"): "AGR_0001",  # same group, non-audit member
    }
    audit_parties = [
        {"source_id": "RT1", "side": "buyer"},
        {"source_id": "RT2", "side": "buyer"},
    ]
    metrics = compute_audit_metrics("test-audit", audit_parties, party_entities)
    assert metrics["recall"] == 1.0
    assert metrics["purity"] == 2 / 3
