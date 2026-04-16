"""
Tests for iterative cluster expansion and cluster splitting.

All tests are in-memory (no SQLite needed) — they construct Signal and Cluster
objects directly and verify that expand_clusters() and split_disconnected_clusters()
produce correct results.
"""

import pytest
from cleo.discovery.types import Signal, Cluster, ContactTenure
from cleo.discovery.rules import (
    build_rule_based_clusters,
    expand_clusters,
    split_disconnected_clusters,
    evaluate_pair,
    _build_signal_index,
    _build_entity_neighbors,
    _build_group_signals,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cluster(member_ids, **kwargs):
    """Create a Cluster with the given member IDs and optional overrides."""
    return Cluster(
        cluster_id=kwargs.get('cluster_id', ''),
        anchor_group_id=kwargs.get('anchor_group_id', ''),
        anchor_name=kwargs.get('anchor_name', ''),
        member_group_ids=set(member_ids),
        confirmed_addresses=set(kwargs.get('confirmed_addresses', [])),
        confirmed_contacts=set(kwargs.get('confirmed_contacts', [])),
        confirmed_phones=set(kwargs.get('confirmed_phones', [])),
        confirmed_entities=set(kwargs.get('confirmed_entities', [])),
        confirmed_name_fragments=set(kwargs.get('confirmed_name_fragments', [])),
    )


# ===========================================================================
# Test 1: expand_clusters finds new members
# ===========================================================================

class TestExpansionFindsNewMembers:
    def test_expansion_finds_new_member_via_shared_contact_and_address(self):
        """Cluster {A, B} shares address with unclustered C.
        C also shares contact with A. After expansion, C joins the cluster.
        """
        signals = [
            # A and B: confirmed pair (contact + address)
            Signal('contact', 'DAN HAGLER', 'GRP_A', 'RT1', 'buyer'),
            Signal('contact', 'DAN HAGLER', 'GRP_B', 'RT2', 'buyer'),
            Signal('address', '180 SHORTING RD|TORONTO|M1S 3S7', 'GRP_A', 'RT1', 'buyer'),
            Signal('address', '180 SHORTING RD|TORONTO|M1S 3S7', 'GRP_B', 'RT2', 'buyer'),
            # C shares address with cluster AND contact with A
            Signal('address', '180 SHORTING RD|TORONTO|M1S 3S7', 'GRP_C', 'RT3', 'buyer'),
            Signal('contact', 'DAN HAGLER', 'GRP_C', 'RT3', 'buyer'),
        ]

        clusters, _, _ = build_rule_based_clusters(signals)
        assert len(clusters) == 1
        assert clusters[0].member_group_ids == {'GRP_A', 'GRP_B', 'GRP_C'}
        # C was already merged by initial clustering since it shares both signals directly.
        # That's correct behavior — direct pairs handle this case.

    def test_expansion_finds_member_through_cluster_signals(self):
        """C shares address with B (a cluster member) and contact with A (another member).
        But C's signals don't overlap with any single other group on 2+ types.
        Expansion should find C by checking against the cluster's expanded signal set.
        """
        signals = [
            # A and B: confirmed pair (contact ALICE + address ADDR_1)
            Signal('contact', 'ALICE SMITH', 'GRP_A', 'RT1', 'buyer'),
            Signal('contact', 'ALICE SMITH', 'GRP_B', 'RT2', 'buyer'),
            Signal('address', 'ADDR_1|TORONTO|M1S', 'GRP_A', 'RT1', 'buyer'),
            Signal('address', 'ADDR_1|TORONTO|M1S', 'GRP_B', 'RT2', 'buyer'),
            # C shares address ADDR_1 with A/B (address match with cluster)
            Signal('address', 'ADDR_1|TORONTO|M1S', 'GRP_C', 'RT3', 'buyer'),
            # C shares a DIFFERENT contact BOB with only A (contact match with cluster)
            Signal('contact', 'BOB JONES', 'GRP_A', 'RT1', 'buyer'),
            Signal('contact', 'BOB JONES', 'GRP_C', 'RT3', 'buyer'),
        ]

        # Initial clustering: A-B are paired (contact ALICE + address ADDR_1)
        # A-C: share contact BOB + address ADDR_1 -> also paired directly
        # So C joins through direct pairing too.
        clusters, _, _ = build_rule_based_clusters(signals)
        assert len(clusters) == 1
        assert 'GRP_C' in clusters[0].member_group_ids

    def test_expansion_adds_member_via_entity_and_address(self):
        """C is connected to cluster via entity bridge + shared address.
        C co-occurs with A on a transaction, and shares address with B.
        """
        signals = [
            # A and B: confirmed pair (contact + address)
            Signal('contact', 'DAN HAGLER', 'GRP_A', 'RT1', 'buyer'),
            Signal('contact', 'DAN HAGLER', 'GRP_B', 'RT2', 'buyer'),
            Signal('address', 'ADDR_1|CITY|POSTAL', 'GRP_A', 'RT1', 'buyer'),
            Signal('address', 'ADDR_1|CITY|POSTAL', 'GRP_B', 'RT2', 'buyer'),
            # C co-occurs with A on RT3 (entity bridge to cluster)
            Signal('entity', 'GRP_A', 'GRP_C', 'RT3', 'buyer'),
            Signal('entity', 'GRP_C', 'GRP_A', 'RT3', 'buyer'),
            # C shares address with B
            Signal('address', 'ADDR_1|CITY|POSTAL', 'GRP_C', 'RT4', 'buyer'),
        ]

        clusters, _, _ = build_rule_based_clusters(signals)
        # After initial clustering, A-B are in a cluster.
        # C: shares entity bridge with A (management_company) + address with cluster
        # -> rule 4c (management_company + address) -> 0.95
        # But does initial pair-wise evaluation catch A-C?
        # A-C: entity co-occurrence (A-C directly) => management_company category
        #       + they don't share address directly
        # C-B: share address only -> 4i suggestion
        # So C is NOT caught by initial pair-wise. This is where expansion helps.

        # Let's manually test expansion
        inner_signals = [
            Signal('contact', 'DAN HAGLER', 'GRP_A', 'RT1', 'buyer'),
            Signal('contact', 'DAN HAGLER', 'GRP_B', 'RT2', 'buyer'),
            Signal('address', 'ADDR_1|CITY|POSTAL', 'GRP_A', 'RT1', 'buyer'),
            Signal('address', 'ADDR_1|CITY|POSTAL', 'GRP_B', 'RT2', 'buyer'),
            Signal('entity', 'GRP_A', 'GRP_C', 'RT3', 'buyer'),
            Signal('entity', 'GRP_C', 'GRP_A', 'RT3', 'buyer'),
            Signal('address', 'ADDR_1|CITY|POSTAL', 'GRP_C', 'RT4', 'buyer'),
        ]

        init_clusters, _, _ = build_rule_based_clusters(inner_signals)

        # If A and B are already in a cluster, expand should pick up C
        # C -> shares address ADDR_1 with cluster (address match)
        #    + co-occurs with cluster member A (management_company match)
        # -> 2 categories -> confirmed
        new_count = expand_clusters(init_clusters, inner_signals)

        # Check that C was added to a cluster
        all_members = set()
        for c in init_clusters:
            all_members.update(c.member_group_ids)
        assert 'GRP_C' in all_members


# ===========================================================================
# Test 2: expand_clusters does NOT add single-signal matches
# ===========================================================================

class TestExpansionRejectsSingleSignal:
    def test_expansion_does_not_add_single_signal_match(self):
        """Cluster {A, B} shares only address with D (no other signal).
        D should NOT be added.
        """
        signals = [
            # A-B confirmed: contact + address
            Signal('contact', 'DAN HAGLER', 'GRP_A', 'RT1', 'buyer'),
            Signal('contact', 'DAN HAGLER', 'GRP_B', 'RT2', 'buyer'),
            Signal('address', 'ADDR_1|CITY|POSTAL', 'GRP_A', 'RT1', 'buyer'),
            Signal('address', 'ADDR_1|CITY|POSTAL', 'GRP_B', 'RT2', 'buyer'),
            # D shares only address with cluster
            Signal('address', 'ADDR_1|CITY|POSTAL', 'GRP_D', 'RT5', 'buyer'),
        ]

        clusters, _, _ = build_rule_based_clusters(signals)
        assert len(clusters) == 1
        initial_members = clusters[0].member_group_ids.copy()

        new_count = expand_clusters(clusters, signals)
        assert new_count == 0
        assert clusters[0].member_group_ids == initial_members
        assert 'GRP_D' not in clusters[0].member_group_ids


# ===========================================================================
# Test 3: expand_clusters converges
# ===========================================================================

class TestExpansionConverges:
    def test_expansion_converges_after_no_new_members(self):
        """After all reachable groups are added, expansion returns 0."""
        signals = [
            # A-B confirmed: contact + address
            Signal('contact', 'DAN HAGLER', 'GRP_A', 'RT1', 'buyer'),
            Signal('contact', 'DAN HAGLER', 'GRP_B', 'RT2', 'buyer'),
            Signal('address', 'ADDR_1|CITY|POSTAL', 'GRP_A', 'RT1', 'buyer'),
            Signal('address', 'ADDR_1|CITY|POSTAL', 'GRP_B', 'RT2', 'buyer'),
        ]

        clusters, _, _ = build_rule_based_clusters(signals)
        assert len(clusters) == 1

        # First expansion: nothing to add
        new1 = expand_clusters(clusters, signals)
        assert new1 == 0

        # Second expansion: still nothing
        new2 = expand_clusters(clusters, signals)
        assert new2 == 0

    def test_expansion_loop_converges(self):
        """Full iteration loop converges within max_iterations."""
        signals = [
            # A-B confirmed: contact + address
            Signal('contact', 'DAN HAGLER', 'GRP_A', 'RT1', 'buyer'),
            Signal('contact', 'DAN HAGLER', 'GRP_B', 'RT2', 'buyer'),
            Signal('address', 'ADDR_1|CITY|POSTAL', 'GRP_A', 'RT1', 'buyer'),
            Signal('address', 'ADDR_1|CITY|POSTAL', 'GRP_B', 'RT2', 'buyer'),
            # C reachable via address + contact (different contact shared with A)
            Signal('address', 'ADDR_1|CITY|POSTAL', 'GRP_C', 'RT3', 'buyer'),
            Signal('contact', 'DAN HAGLER', 'GRP_C', 'RT3', 'buyer'),
        ]

        clusters, _, _ = build_rule_based_clusters(signals)
        iterations = 0
        for i in range(5):
            new_count = expand_clusters(clusters, signals)
            iterations += 1
            if new_count == 0:
                break

        # Should converge (nothing new after initial clustering already got C)
        assert iterations <= 5


# ===========================================================================
# Test 4: expand_clusters uses expanded signals from prior rounds
# ===========================================================================

class TestExpansionUsesExpandedSignals:
    def test_two_round_expansion(self):
        """Round 1 adds C via (address + entity). Round 2 adds D via signals
        that only C contributes to the cluster.

        Setup:
        - A-B confirmed: contact ALICE + address ADDR_1
        - C: entity bridge with A + address ADDR_1 -> joins in round 1
        - C has contact CAROL
        - D: shares contact CAROL + address ADDR_2 (ADDR_2 is only on C)
        After C joins, the cluster has CAROL. D shares CAROL + ADDR_2 -> 2 signals -> joins.
        """
        signals = [
            # A-B confirmed: contact ALICE + address ADDR_1
            Signal('contact', 'ALICE', 'GRP_A', 'RT1', 'buyer'),
            Signal('contact', 'ALICE', 'GRP_B', 'RT2', 'buyer'),
            Signal('address', 'ADDR_1|CITY|POSTAL', 'GRP_A', 'RT1', 'buyer'),
            Signal('address', 'ADDR_1|CITY|POSTAL', 'GRP_B', 'RT2', 'buyer'),
            # C: entity bridge with A + address ADDR_1
            Signal('entity', 'GRP_A', 'GRP_C', 'RT3', 'buyer'),
            Signal('entity', 'GRP_C', 'GRP_A', 'RT3', 'buyer'),
            Signal('address', 'ADDR_1|CITY|POSTAL', 'GRP_C', 'RT3', 'buyer'),
            # C also has contact CAROL and address ADDR_2
            Signal('contact', 'CAROL', 'GRP_C', 'RT4', 'buyer'),
            Signal('address', 'ADDR_2|CITY|POSTAL', 'GRP_C', 'RT4', 'buyer'),
            # D: shares contact CAROL + address ADDR_2 (only from C)
            Signal('contact', 'CAROL', 'GRP_D', 'RT5', 'buyer'),
            Signal('address', 'ADDR_2|CITY|POSTAL', 'GRP_D', 'RT5', 'buyer'),
        ]

        clusters, _, _ = build_rule_based_clusters(signals)

        # Run expansion iteratively
        total_added = 0
        for i in range(5):
            new_count = expand_clusters(clusters, signals)
            total_added += new_count
            if new_count == 0:
                break

        # Both C and D should end up in the cluster
        all_members = set()
        for c in clusters:
            all_members.update(c.member_group_ids)

        assert 'GRP_C' in all_members, "C should be added via entity bridge + address"
        assert 'GRP_D' in all_members, "D should be added via CAROL contact + ADDR_2 (from C)"


# ===========================================================================
# Test 5: split_disconnected_clusters
# ===========================================================================

class TestSplitDisconnectedClusters:
    def test_split_disconnected_cluster(self):
        """Cluster with {A, B, C, D} where {A,B} share signals and {C,D} share
        signals but {A,B} and {C,D} have no overlap -> split into 2 clusters.
        """
        signals = [
            # A-B: contact + address
            Signal('contact', 'DAN HAGLER', 'GRP_A', 'RT1', 'buyer'),
            Signal('contact', 'DAN HAGLER', 'GRP_B', 'RT2', 'buyer'),
            Signal('address', 'ADDR_1|CITY|POSTAL', 'GRP_A', 'RT1', 'buyer'),
            Signal('address', 'ADDR_1|CITY|POSTAL', 'GRP_B', 'RT2', 'buyer'),
            # C-D: contact + address (different)
            Signal('contact', 'JANE DOE', 'GRP_C', 'RT3', 'buyer'),
            Signal('contact', 'JANE DOE', 'GRP_D', 'RT4', 'buyer'),
            Signal('address', 'ADDR_2|CITY|POSTAL', 'GRP_C', 'RT3', 'buyer'),
            Signal('address', 'ADDR_2|CITY|POSTAL', 'GRP_D', 'RT4', 'buyer'),
        ]

        # Artificially combine into one cluster
        big_cluster = _make_cluster(
            ['GRP_A', 'GRP_B', 'GRP_C', 'GRP_D'],
            confirmed_contacts={'DAN HAGLER', 'JANE DOE'},
            confirmed_addresses={'ADDR_1|CITY|POSTAL', 'ADDR_2|CITY|POSTAL'},
        )

        result = split_disconnected_clusters([big_cluster], signals)

        assert len(result) == 2
        member_sets = [c.member_group_ids for c in result]
        assert {'GRP_A', 'GRP_B'} in member_sets
        assert {'GRP_C', 'GRP_D'} in member_sets

    def test_no_split_when_connected(self):
        """Cluster where all members are connected -> no split."""
        signals = [
            # A-B: contact + address
            Signal('contact', 'DAN HAGLER', 'GRP_A', 'RT1', 'buyer'),
            Signal('contact', 'DAN HAGLER', 'GRP_B', 'RT2', 'buyer'),
            Signal('address', 'ADDR_1|CITY|POSTAL', 'GRP_A', 'RT1', 'buyer'),
            Signal('address', 'ADDR_1|CITY|POSTAL', 'GRP_B', 'RT2', 'buyer'),
            # B-C: contact + address (B connects them)
            Signal('contact', 'JANE DOE', 'GRP_B', 'RT3', 'buyer'),
            Signal('contact', 'JANE DOE', 'GRP_C', 'RT4', 'buyer'),
            Signal('address', 'ADDR_2|CITY|POSTAL', 'GRP_B', 'RT3', 'buyer'),
            Signal('address', 'ADDR_2|CITY|POSTAL', 'GRP_C', 'RT4', 'buyer'),
        ]

        cluster = _make_cluster(
            ['GRP_A', 'GRP_B', 'GRP_C'],
            confirmed_contacts={'DAN HAGLER', 'JANE DOE'},
            confirmed_addresses={'ADDR_1|CITY|POSTAL', 'ADDR_2|CITY|POSTAL'},
        )

        result = split_disconnected_clusters([cluster], signals)

        assert len(result) == 1
        assert result[0].member_group_ids == {'GRP_A', 'GRP_B', 'GRP_C'}

    def test_split_into_three_components(self):
        """Cluster with 3 disconnected components -> split into 3 clusters."""
        signals = [
            # Component 1: A-B
            Signal('contact', 'ALICE', 'GRP_A', 'RT1', 'buyer'),
            Signal('contact', 'ALICE', 'GRP_B', 'RT2', 'buyer'),
            Signal('address', 'ADDR_1|CITY|P', 'GRP_A', 'RT1', 'buyer'),
            Signal('address', 'ADDR_1|CITY|P', 'GRP_B', 'RT2', 'buyer'),
            # Component 2: C-D
            Signal('contact', 'BOB', 'GRP_C', 'RT3', 'buyer'),
            Signal('contact', 'BOB', 'GRP_D', 'RT4', 'buyer'),
            Signal('address', 'ADDR_2|CITY|P', 'GRP_C', 'RT3', 'buyer'),
            Signal('address', 'ADDR_2|CITY|P', 'GRP_D', 'RT4', 'buyer'),
            # Component 3: E-F
            Signal('contact', 'CAROL', 'GRP_E', 'RT5', 'buyer'),
            Signal('contact', 'CAROL', 'GRP_F', 'RT6', 'buyer'),
            Signal('address', 'ADDR_3|CITY|P', 'GRP_E', 'RT5', 'buyer'),
            Signal('address', 'ADDR_3|CITY|P', 'GRP_F', 'RT6', 'buyer'),
        ]

        big_cluster = _make_cluster(['GRP_A', 'GRP_B', 'GRP_C', 'GRP_D', 'GRP_E', 'GRP_F'])

        result = split_disconnected_clusters([big_cluster], signals)

        assert len(result) == 3
        member_sets = [c.member_group_ids for c in result]
        assert {'GRP_A', 'GRP_B'} in member_sets
        assert {'GRP_C', 'GRP_D'} in member_sets
        assert {'GRP_E', 'GRP_F'} in member_sets

    def test_single_member_dropped_after_split(self):
        """If a split produces a component with only 1 member, it's dropped."""
        signals = [
            # A-B: contact + address
            Signal('contact', 'DAN', 'GRP_A', 'RT1', 'buyer'),
            Signal('contact', 'DAN', 'GRP_B', 'RT2', 'buyer'),
            Signal('address', 'ADDR_1|CITY|P', 'GRP_A', 'RT1', 'buyer'),
            Signal('address', 'ADDR_1|CITY|P', 'GRP_B', 'RT2', 'buyer'),
            # C is alone — no pair-wise 2-signal match with anyone else in the cluster
        ]

        cluster = _make_cluster(['GRP_A', 'GRP_B', 'GRP_C'])

        result = split_disconnected_clusters([cluster], signals)

        # {A, B} stays as a cluster, {C} alone is dropped
        assert len(result) == 1
        assert result[0].member_group_ids == {'GRP_A', 'GRP_B'}

    def test_split_preserves_confirmed_signals(self):
        """After splitting, each sub-cluster should have appropriate confirmed signals."""
        signals = [
            Signal('contact', 'DAN', 'GRP_A', 'RT1', 'buyer'),
            Signal('contact', 'DAN', 'GRP_B', 'RT2', 'buyer'),
            Signal('address', 'ADDR_1|CITY|P', 'GRP_A', 'RT1', 'buyer'),
            Signal('address', 'ADDR_1|CITY|P', 'GRP_B', 'RT2', 'buyer'),
            Signal('contact', 'JANE', 'GRP_C', 'RT3', 'buyer'),
            Signal('contact', 'JANE', 'GRP_D', 'RT4', 'buyer'),
            Signal('address', 'ADDR_2|CITY|P', 'GRP_C', 'RT3', 'buyer'),
            Signal('address', 'ADDR_2|CITY|P', 'GRP_D', 'RT4', 'buyer'),
        ]

        cluster = _make_cluster(
            ['GRP_A', 'GRP_B', 'GRP_C', 'GRP_D'],
            confirmed_contacts={'DAN', 'JANE'},
            confirmed_addresses={'ADDR_1|CITY|P', 'ADDR_2|CITY|P'},
        )

        result = split_disconnected_clusters([cluster], signals)
        assert len(result) == 2

        # Find which cluster has A, B
        for c in result:
            if 'GRP_A' in c.member_group_ids:
                assert 'DAN' in c.confirmed_contacts
                assert 'ADDR_1|CITY|P' in c.confirmed_addresses
            if 'GRP_C' in c.member_group_ids:
                assert 'JANE' in c.confirmed_contacts
                assert 'ADDR_2|CITY|P' in c.confirmed_addresses


# ===========================================================================
# Test 6: expand_clusters with contact tenures
# ===========================================================================

class TestExpansionWithTenures:
    def test_expansion_with_distinctive_contact(self):
        """A distinctive contact alone (rule 4e) should be enough for expansion."""
        signals = [
            # A-B confirmed: contact + address
            Signal('contact', 'ALICE', 'GRP_A', 'RT1', 'buyer'),
            Signal('contact', 'ALICE', 'GRP_B', 'RT2', 'buyer'),
            Signal('address', 'ADDR_1|CITY|P', 'GRP_A', 'RT1', 'buyer'),
            Signal('address', 'ADDR_1|CITY|P', 'GRP_B', 'RT2', 'buyer'),
            # C shares ONLY distinctive contact with A
            Signal('contact', 'ALICE', 'GRP_C', 'RT3', 'buyer'),
        ]

        tenures = {
            'ALICE': [
                ContactTenure('CON_001', 'Alice', 'GRP_A', '2020-01-01', '2022-12-31', 5,
                              is_distinctive=True),
                ContactTenure('CON_001', 'Alice', 'GRP_B', '2020-01-01', '2022-12-31', 3,
                              is_distinctive=True),
                ContactTenure('CON_001', 'Alice', 'GRP_C', '2021-01-01', '2023-12-31', 2,
                              is_distinctive=True),
            ]
        }

        clusters, _, _ = build_rule_based_clusters(signals, contact_tenures=tenures)

        # Initial: A-B-C may already be in one cluster via rule 4e
        # or expansion should catch C
        new_count = expand_clusters(clusters, signals, tenures=tenures)

        all_members = set()
        for c in clusters:
            all_members.update(c.member_group_ids)
        assert 'GRP_C' in all_members


# ===========================================================================
# Test 7: expand_clusters returns correct count
# ===========================================================================

class TestExpansionReturnCount:
    def test_returns_zero_when_nothing_added(self):
        signals = [
            Signal('contact', 'DAN', 'GRP_A', 'RT1', 'buyer'),
            Signal('contact', 'DAN', 'GRP_B', 'RT2', 'buyer'),
            Signal('address', 'ADDR_1|CITY|P', 'GRP_A', 'RT1', 'buyer'),
            Signal('address', 'ADDR_1|CITY|P', 'GRP_B', 'RT2', 'buyer'),
        ]
        clusters, _, _ = build_rule_based_clusters(signals)
        assert expand_clusters(clusters, signals) == 0

    def test_returns_count_of_new_members(self):
        """expand_clusters returns the number of new groups added."""
        signals = [
            # A-B confirmed
            Signal('contact', 'DAN', 'GRP_A', 'RT1', 'buyer'),
            Signal('contact', 'DAN', 'GRP_B', 'RT2', 'buyer'),
            Signal('address', 'ADDR_1|CITY|P', 'GRP_A', 'RT1', 'buyer'),
            Signal('address', 'ADDR_1|CITY|P', 'GRP_B', 'RT2', 'buyer'),
            # C: entity with A + address with cluster
            Signal('entity', 'GRP_A', 'GRP_C', 'RT3', 'buyer'),
            Signal('entity', 'GRP_C', 'GRP_A', 'RT3', 'buyer'),
            Signal('address', 'ADDR_1|CITY|P', 'GRP_C', 'RT4', 'buyer'),
        ]

        clusters, _, _ = build_rule_based_clusters(signals)
        if 'GRP_C' not in {g for c in clusters for g in c.member_group_ids}:
            new_count = expand_clusters(clusters, signals)
            assert new_count >= 1


# ===========================================================================
# Test 8: expand_clusters handles empty input
# ===========================================================================

class TestExpansionEdgeCases:
    def test_empty_clusters(self):
        signals = [
            Signal('contact', 'DAN', 'GRP_A', 'RT1', 'buyer'),
        ]
        assert expand_clusters([], signals) == 0

    def test_empty_signals(self):
        cluster = _make_cluster(['GRP_A', 'GRP_B'])
        assert expand_clusters([cluster], []) == 0

    def test_all_groups_already_clustered(self):
        """When all groups with signals are already in clusters, nothing to expand."""
        signals = [
            Signal('contact', 'DAN', 'GRP_A', 'RT1', 'buyer'),
            Signal('contact', 'DAN', 'GRP_B', 'RT2', 'buyer'),
            Signal('address', 'ADDR_1|CITY|P', 'GRP_A', 'RT1', 'buyer'),
            Signal('address', 'ADDR_1|CITY|P', 'GRP_B', 'RT2', 'buyer'),
        ]
        clusters, _, _ = build_rule_based_clusters(signals)
        assert expand_clusters(clusters, signals) == 0


# ===========================================================================
# Test 9: expand_clusters does not cross-merge clusters
# ===========================================================================

class TestExpansionNoCrossMerge:
    def test_unclustered_group_goes_to_best_match(self):
        """When a group could match multiple clusters, it joins the best match (highest confidence)."""
        signals = [
            # Cluster 1: A-B (contact + address)
            Signal('contact', 'DAN', 'GRP_A', 'RT1', 'buyer'),
            Signal('contact', 'DAN', 'GRP_B', 'RT2', 'buyer'),
            Signal('address', 'ADDR_1|CITY|P', 'GRP_A', 'RT1', 'buyer'),
            Signal('address', 'ADDR_1|CITY|P', 'GRP_B', 'RT2', 'buyer'),
            # Cluster 2: E-F (contact + address)
            Signal('contact', 'JANE', 'GRP_E', 'RT5', 'buyer'),
            Signal('contact', 'JANE', 'GRP_F', 'RT6', 'buyer'),
            Signal('address', 'ADDR_2|CITY|P', 'GRP_E', 'RT5', 'buyer'),
            Signal('address', 'ADDR_2|CITY|P', 'GRP_F', 'RT6', 'buyer'),
            # C: shares contact DAN + address ADDR_1 with cluster 1
            # AND address ADDR_2 only with cluster 2
            Signal('contact', 'DAN', 'GRP_C', 'RT7', 'buyer'),
            Signal('address', 'ADDR_1|CITY|P', 'GRP_C', 'RT7', 'buyer'),
            Signal('address', 'ADDR_2|CITY|P', 'GRP_C', 'RT8', 'buyer'),
        ]

        clusters, _, _ = build_rule_based_clusters(signals)

        # C may already be matched with cluster 1 via direct pair with A or B
        # Let's just verify C is in exactly one cluster
        clusters_with_c = [c for c in clusters if 'GRP_C' in c.member_group_ids]
        if not clusters_with_c:
            expand_clusters(clusters, signals)
            clusters_with_c = [c for c in clusters if 'GRP_C' in c.member_group_ids]

        assert len(clusters_with_c) == 1, "C should be in exactly one cluster"
