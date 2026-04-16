"""
Tests for the rule-based pair evaluation and clustering.

All tests are in-memory (no SQLite needed) — they construct Signal objects
directly and verify that build_rule_based_clusters() produces correct clusters,
suggestions, and evidence based on the rule hierarchy.
"""

import pytest
from cleo.discovery.types import Signal, Cluster
from cleo.discovery.rules import (
    build_rule_based_clusters,
    evaluate_pair,
    _build_signal_index,
    _build_entity_neighbors,
    _build_group_signals,
    _get_pair_categories,
    MAX_SIGNAL_FANOUT,
)


class TestEvaluatePair:
    """Test the pure rule evaluation function."""

    def test_rule_4a_mgmt_company_plus_contact(self):
        cats = {'management_company': {'entity_bridge:GRP_C'}, 'contact': {'DAN HAGLER'}}
        rule_id, confidence = evaluate_pair(cats)
        assert rule_id == '4a'
        assert confidence == 1.00

    def test_rule_4b_contact_plus_address(self):
        cats = {'contact': {'DAN HAGLER'}, 'address': {'180 SHORTING RD|TORONTO|M1S 3S7'}}
        rule_id, confidence = evaluate_pair(cats)
        assert rule_id == '4b'
        assert confidence == 0.99

    def test_rule_4c_mgmt_plus_address(self):
        cats = {'management_company': {'trade_name:ACME'}, 'address': {'100 KING ST|TORONTO|M5H 1A1'}}
        rule_id, confidence = evaluate_pair(cats)
        assert rule_id == '4c'
        assert confidence == 0.95

    def test_rule_4d_mgmt_plus_phone(self):
        cats = {'management_company': {'care_of:MGMT CO'}, 'phone': {'4162655055'}}
        rule_id, confidence = evaluate_pair(cats)
        assert rule_id == '4d'
        assert confidence == 0.90

    def test_rule_4g_phone_plus_address(self):
        cats = {'phone': {'4162655055'}, 'address': {'180 SHORTING RD|TORONTO|M1S 3S7'}}
        rule_id, confidence = evaluate_pair(cats)
        assert rule_id == '4g'
        assert confidence == 0.80

    def test_rule_4g_phone_plus_name_fragment(self):
        cats = {'phone': {'4162655055'}, 'name_fragment': {'ACME HOLDINGS'}}
        rule_id, confidence = evaluate_pair(cats)
        assert rule_id == '4g'
        assert confidence == 0.80

    def test_rule_4i_address_only_is_suggestion(self):
        cats = {'address': {'180 SHORTING RD|TORONTO|M1S 3S7'}}
        rule_id, confidence = evaluate_pair(cats)
        assert rule_id == '4i'
        assert confidence == 0.60

    def test_rule_4j_single_signal_no_action(self):
        cats = {'contact': {'DAN HAGLER'}}
        rule_id, confidence = evaluate_pair(cats)
        assert rule_id == '4j'
        assert confidence == 0.00

    def test_rule_4j_single_phone_no_action(self):
        cats = {'phone': {'4162655055'}}
        rule_id, confidence = evaluate_pair(cats)
        assert rule_id == '4j'
        assert confidence == 0.00

    def test_empty_categories_returns_none(self):
        rule_id, confidence = evaluate_pair({})
        assert rule_id == 'none'
        assert confidence == 0.0

    def test_rule_4f_contact_plus_name_fragment(self):
        """contact + name_fragment -> rule 4f, confidence 0.85."""
        cats = {'contact': {'DAN HAGLER'}, 'name_fragment': {'ACME'}}
        rule_id, confidence = evaluate_pair(cats)
        assert rule_id == '4f'
        assert confidence == 0.85

    def test_multi_category_fallback(self):
        """Two categories that don't match any specific rule -> 'multi' with 0.85."""
        cats = {'phone': {'4162655055'}, 'contact': {'DAN HAGLER'}}
        rule_id, confidence = evaluate_pair(cats)
        assert rule_id == 'multi'
        assert confidence == 0.85

    def test_rule_4e_distinctive_contact_alone(self):
        """Contact-only pair where the contact is distinctive -> rule 4e, confidence 0.90."""
        from cleo.discovery.types import ContactTenure
        tenures = {
            'DAN HAGLER': [
                ContactTenure('CON_001', 'Dan Hagler', 'GRP_A', '2020-01-01', '2022-12-31', 5,
                              is_distinctive=True),
            ]
        }
        cats = {'contact': {'DAN HAGLER'}}
        rule_id, confidence = evaluate_pair(cats, contact_tenures=tenures)
        assert rule_id == '4e'
        assert confidence == 0.90

    def test_rule_4e_not_fired_without_tenures(self):
        """Contact-only pair with no tenures dict provided -> falls through to 4j."""
        cats = {'contact': {'DAN HAGLER'}}
        rule_id, confidence = evaluate_pair(cats, contact_tenures=None)
        assert rule_id == '4j'
        assert confidence == 0.00

    def test_rule_4e_not_fired_when_contact_not_distinctive(self):
        """Contact-only pair where contact is NOT distinctive -> falls through to 4j."""
        from cleo.discovery.types import ContactTenure
        tenures = {
            'DAN HAGLER': [
                ContactTenure('CON_001', 'Dan Hagler', 'GRP_A', '2020-01-01', '2022-12-31', 5,
                              is_distinctive=False),
            ]
        }
        cats = {'contact': {'DAN HAGLER'}}
        rule_id, confidence = evaluate_pair(cats, contact_tenures=tenures)
        assert rule_id == '4j'
        assert confidence == 0.00

    def test_three_categories_matches_best_rule(self):
        """With 3 categories, the best-matching rule should fire first."""
        cats = {
            'management_company': {'entity_bridge:GRP_C'},
            'contact': {'DAN HAGLER'},
            'address': {'180 SHORTING RD|TORONTO|M1S 3S7'},
        }
        rule_id, confidence = evaluate_pair(cats)
        assert rule_id == '4a'
        assert confidence == 1.00


class TestBuildRuleBasedClusters:
    """Integration tests for the full clustering pipeline."""

    def test_rule_4a_mgmt_company_plus_contact_cluster(self):
        """Two groups sharing a management company (via entity co-occurrence) and a contact."""
        signals = [
            # Group A and Group B both have contact DAN HAGLER
            Signal('contact', 'DAN HAGLER', 'GRP_A', 'RT1', 'buyer'),
            Signal('contact', 'DAN HAGLER', 'GRP_B', 'RT2', 'buyer'),
            # Entity co-occurrence: A appears with C, B appears with C
            Signal('entity', 'GRP_C', 'GRP_A', 'RT3', 'buyer'),
            Signal('entity', 'GRP_A', 'GRP_C', 'RT3', 'buyer'),
            Signal('entity', 'GRP_C', 'GRP_B', 'RT4', 'buyer'),
            Signal('entity', 'GRP_B', 'GRP_C', 'RT4', 'buyer'),
        ]
        clusters, suggestions, evidence = build_rule_based_clusters(signals)
        assert len(clusters) == 1
        assert clusters[0].member_group_ids == {'GRP_A', 'GRP_B'}

    def test_rule_4b_contact_plus_address_cluster(self):
        """Two groups sharing a contact and an address -> confirmed cluster."""
        signals = [
            Signal('contact', 'DAN HAGLER', 'GRP_A', 'RT1', 'buyer'),
            Signal('contact', 'DAN HAGLER', 'GRP_B', 'RT2', 'buyer'),
            Signal('address', '180 SHORTING RD|TORONTO|M1S 3S7', 'GRP_A', 'RT1', 'buyer'),
            Signal('address', '180 SHORTING RD|TORONTO|M1S 3S7', 'GRP_B', 'RT2', 'buyer'),
        ]
        clusters, suggestions, evidence = build_rule_based_clusters(signals)
        assert len(clusters) == 1
        assert clusters[0].member_group_ids == {'GRP_A', 'GRP_B'}

    def test_rule_4c_mgmt_plus_address_cluster(self):
        """Shared trade_name + address -> confirmed cluster."""
        signals = [
            Signal('trade_name', 'ACME HOLDINGS', 'GRP_A', 'RT1', 'buyer'),
            Signal('trade_name', 'ACME HOLDINGS', 'GRP_B', 'RT2', 'buyer'),
            Signal('address', '100 KING ST|TORONTO|M5H 1A1', 'GRP_A', 'RT1', 'buyer'),
            Signal('address', '100 KING ST|TORONTO|M5H 1A1', 'GRP_B', 'RT2', 'buyer'),
        ]
        clusters, suggestions, evidence = build_rule_based_clusters(signals)
        assert len(clusters) == 1
        assert clusters[0].member_group_ids == {'GRP_A', 'GRP_B'}

    def test_rule_4d_mgmt_plus_phone_cluster(self):
        """Shared care_of + phone -> confirmed cluster."""
        signals = [
            Signal('care_of', 'C/O MANAGEMENT CO', 'GRP_A', 'RT1', 'buyer'),
            Signal('care_of', 'C/O MANAGEMENT CO', 'GRP_B', 'RT2', 'buyer'),
            Signal('phone', '4162655055', 'GRP_A', '', ''),
            Signal('phone', '4162655055', 'GRP_B', '', ''),
        ]
        clusters, suggestions, evidence = build_rule_based_clusters(signals)
        assert len(clusters) == 1
        assert clusters[0].member_group_ids == {'GRP_A', 'GRP_B'}

    def test_rule_4g_phone_plus_address_cluster(self):
        """Shared phone + address -> confirmed cluster (confidence 0.80)."""
        signals = [
            Signal('phone', '4162655055', 'GRP_A', '', ''),
            Signal('phone', '4162655055', 'GRP_B', '', ''),
            Signal('address', '180 SHORTING RD|TORONTO|M1S 3S7', 'GRP_A', 'RT1', 'buyer'),
            Signal('address', '180 SHORTING RD|TORONTO|M1S 3S7', 'GRP_B', 'RT2', 'buyer'),
        ]
        clusters, suggestions, evidence = build_rule_based_clusters(signals)
        assert len(clusters) == 1

    def test_rule_4i_address_only_is_suggestion(self):
        """Two groups sharing ONLY an address -> suggestion, not confirmed cluster."""
        signals = [
            Signal('address', '180 SHORTING RD|TORONTO|M1S 3S7', 'GRP_A', 'RT1', 'buyer'),
            Signal('address', '180 SHORTING RD|TORONTO|M1S 3S7', 'GRP_B', 'RT2', 'buyer'),
        ]
        clusters, suggestions, evidence = build_rule_based_clusters(signals)
        assert len(clusters) == 0
        assert len(suggestions) == 1
        gid_a, gid_b, rule_id, confidence = suggestions[0]
        assert {gid_a, gid_b} == {'GRP_A', 'GRP_B'}
        assert rule_id == '4i'
        assert confidence == 0.60

    def test_rule_4j_single_signal_no_action(self):
        """Two groups sharing ONLY a contact -> no cluster, no suggestion."""
        signals = [
            Signal('contact', 'DAN HAGLER', 'GRP_A', 'RT1', 'buyer'),
            Signal('contact', 'DAN HAGLER', 'GRP_B', 'RT2', 'buyer'),
        ]
        clusters, suggestions, evidence = build_rule_based_clusters(signals)
        assert len(clusters) == 0
        # 4j has confidence 0.0, which is not > 0, so no suggestion either
        assert len(suggestions) == 0

    def test_mega_signal_filtered(self):
        """A signal shared by >50 groups should be skipped entirely."""
        signals = []
        # Create 55 groups sharing the same address
        for i in range(55):
            signals.append(Signal('address', 'MEGA_ADDR', f'GRP_{i:05d}', f'RT{i}', 'buyer'))
        # Add a contact shared by only 2 of them
        signals.append(Signal('contact', 'SOLO CONTACT', 'GRP_00000', 'RT0', 'buyer'))
        signals.append(Signal('contact', 'SOLO CONTACT', 'GRP_00001', 'RT1', 'buyer'))

        clusters, suggestions, evidence = build_rule_based_clusters(signals)
        # The address signal has fanout > 50 so it's skipped.
        # Only shared contact remains -> single signal -> no cluster.
        assert len(clusters) == 0

    def test_entity_bridge_detected(self):
        """A and B both co-occur with C on separate transactions -> management_company for (A,B)."""
        signals = [
            # A co-occurs with C on RT1
            Signal('entity', 'GRP_C', 'GRP_A', 'RT1', 'buyer'),
            Signal('entity', 'GRP_A', 'GRP_C', 'RT1', 'buyer'),
            # B co-occurs with C on RT2
            Signal('entity', 'GRP_C', 'GRP_B', 'RT2', 'buyer'),
            Signal('entity', 'GRP_B', 'GRP_C', 'RT2', 'buyer'),
            # Also A and B share a phone
            Signal('phone', '4162655055', 'GRP_A', '', ''),
            Signal('phone', '4162655055', 'GRP_B', '', ''),
        ]
        clusters, suggestions, evidence = build_rule_based_clusters(signals)
        # management_company (entity bridge via C) + phone -> rule 4d, confidence 0.90
        assert len(clusters) == 1
        assert clusters[0].member_group_ids == {'GRP_A', 'GRP_B'}

    def test_clusters_only_from_confirmed_pairs(self):
        """build_rule_based_clusters only creates clusters from pairs with 2+ signal types."""
        signals = [
            # Pair A-B: contact + address -> confirmed
            Signal('contact', 'DAN HAGLER', 'GRP_A', 'RT1', 'buyer'),
            Signal('contact', 'DAN HAGLER', 'GRP_B', 'RT2', 'buyer'),
            Signal('address', '180 SHORTING RD|TORONTO|M1S 3S7', 'GRP_A', 'RT1', 'buyer'),
            Signal('address', '180 SHORTING RD|TORONTO|M1S 3S7', 'GRP_B', 'RT2', 'buyer'),
            # Pair C-D: address only -> suggestion
            Signal('address', '100 KING ST|TORONTO|M5H 1A1', 'GRP_C', 'RT3', 'buyer'),
            Signal('address', '100 KING ST|TORONTO|M5H 1A1', 'GRP_D', 'RT4', 'buyer'),
        ]
        clusters, suggestions, evidence = build_rule_based_clusters(signals)
        assert len(clusters) == 1
        assert clusters[0].member_group_ids == {'GRP_A', 'GRP_B'}
        assert len(suggestions) == 1  # C-D is a suggestion

    def test_no_mega_cluster(self):
        """A-B share address, B-C share contact (no other overlap).
        A and C should NOT be in the same cluster — they don't share 2 signals directly.
        """
        signals = [
            # A-B share address only
            Signal('address', 'ADDR_1', 'GRP_A', 'RT1', 'buyer'),
            Signal('address', 'ADDR_1', 'GRP_B', 'RT2', 'buyer'),
            # B-C share contact only
            Signal('contact', 'JOHN DOE', 'GRP_B', 'RT3', 'buyer'),
            Signal('contact', 'JOHN DOE', 'GRP_C', 'RT4', 'buyer'),
        ]
        clusters, suggestions, evidence = build_rule_based_clusters(signals)
        # Neither pair has 2+ signal types, so no confirmed clusters
        assert len(clusters) == 0
        # A-B: address only -> suggestion (4i, 0.60)
        # B-C: contact only -> no action (4j, 0.00)
        assert len(suggestions) == 1  # only A-B

    def test_no_mega_cluster_transitive_chain(self):
        """Even if each pair has address+contact, transitive chains should still be allowed.
        The point is that EACH edge in the chain must have 2+ signal types.
        """
        signals = [
            # A-B: address + contact
            Signal('address', 'ADDR_1', 'GRP_A', 'RT1', 'buyer'),
            Signal('address', 'ADDR_1', 'GRP_B', 'RT2', 'buyer'),
            Signal('contact', 'JOHN DOE', 'GRP_A', 'RT1', 'buyer'),
            Signal('contact', 'JOHN DOE', 'GRP_B', 'RT2', 'buyer'),
            # B-C: address + contact (different values)
            Signal('address', 'ADDR_2', 'GRP_B', 'RT3', 'buyer'),
            Signal('address', 'ADDR_2', 'GRP_C', 'RT4', 'buyer'),
            Signal('contact', 'JANE DOE', 'GRP_B', 'RT3', 'buyer'),
            Signal('contact', 'JANE DOE', 'GRP_C', 'RT4', 'buyer'),
        ]
        clusters, suggestions, evidence = build_rule_based_clusters(signals)
        # Both edges have 2+ categories, so A-B-C form one cluster
        assert len(clusters) == 1
        assert clusters[0].member_group_ids == {'GRP_A', 'GRP_B', 'GRP_C'}

    def test_empty_signals_returns_empty(self):
        clusters, suggestions, evidence = build_rule_based_clusters([])
        assert clusters == []
        assert suggestions == []
        assert evidence == []

    def test_evidence_created_for_confirmed_pairs(self):
        """Evidence records should be generated for confirmed cluster pairs."""
        signals = [
            Signal('contact', 'DAN HAGLER', 'GRP_A', 'RT1', 'buyer'),
            Signal('contact', 'DAN HAGLER', 'GRP_B', 'RT2', 'buyer'),
            Signal('address', '180 SHORTING RD|TORONTO|M1S 3S7', 'GRP_A', 'RT1', 'buyer'),
            Signal('address', '180 SHORTING RD|TORONTO|M1S 3S7', 'GRP_B', 'RT2', 'buyer'),
        ]
        clusters, suggestions, evidence = build_rule_based_clusters(signals)
        assert len(evidence) > 0
        # Evidence should reference both signal types
        evidence_types = {e.signal_type for e in evidence}
        assert 'contact' in evidence_types
        assert 'address' in evidence_types
        # All evidence should reference rule 4b
        for e in evidence:
            assert e.rule_id == '4b'
            assert e.confidence == 0.99

    def test_cluster_confirmed_fields_populated(self):
        """Cluster confirmed_* fields should be populated from pair categories."""
        signals = [
            Signal('contact', 'DAN HAGLER', 'GRP_A', 'RT1', 'buyer'),
            Signal('contact', 'DAN HAGLER', 'GRP_B', 'RT2', 'buyer'),
            Signal('address', '180 SHORTING RD|TORONTO|M1S 3S7', 'GRP_A', 'RT1', 'buyer'),
            Signal('address', '180 SHORTING RD|TORONTO|M1S 3S7', 'GRP_B', 'RT2', 'buyer'),
            Signal('phone', '4162655055', 'GRP_A', '', ''),
            Signal('phone', '4162655055', 'GRP_B', '', ''),
        ]
        clusters, suggestions, evidence = build_rule_based_clusters(signals)
        assert len(clusters) == 1
        c = clusters[0]
        assert '180 SHORTING RD|TORONTO|M1S 3S7' in c.confirmed_addresses
        assert 'DAN HAGLER' in c.confirmed_contacts
        assert '4162655055' in c.confirmed_phones

    def test_management_company_via_trade_name(self):
        """Shared trade_name + contact -> management_company + contact -> rule 4a."""
        signals = [
            Signal('trade_name', 'ACME MGMT', 'GRP_A', 'RT1', 'buyer'),
            Signal('trade_name', 'ACME MGMT', 'GRP_B', 'RT2', 'buyer'),
            Signal('contact', 'DAN HAGLER', 'GRP_A', 'RT1', 'buyer'),
            Signal('contact', 'DAN HAGLER', 'GRP_B', 'RT2', 'buyer'),
        ]
        clusters, suggestions, evidence = build_rule_based_clusters(signals)
        assert len(clusters) == 1
        # Should match rule 4a (management_company + contact)
        rule_ids = {e.rule_id for e in evidence}
        assert '4a' in rule_ids

    def test_management_company_via_care_of(self):
        """Shared care_of + phone -> management_company + phone -> rule 4d."""
        signals = [
            Signal('care_of', 'C/O MGMT CORP', 'GRP_A', 'RT1', 'buyer'),
            Signal('care_of', 'C/O MGMT CORP', 'GRP_B', 'RT2', 'buyer'),
            Signal('phone', '4162655055', 'GRP_A', '', ''),
            Signal('phone', '4162655055', 'GRP_B', '', ''),
        ]
        clusters, suggestions, evidence = build_rule_based_clusters(signals)
        assert len(clusters) == 1
        rule_ids = {e.rule_id for e in evidence}
        assert '4d' in rule_ids
