"""Tests for union-find graph construction."""


def test_three_nodes_one_component_via_transitive_closure():
    from cleo.discovery_v2.graph import build_components

    # A-B strong, B-C strong → {A, B, C} is one component
    edges = [
        (("RT1", "buyer"), ("RT2", "buyer"), "strong"),
        (("RT2", "buyer"), ("RT3", "buyer"), "strong"),
    ]
    components = build_components(edges)
    comp_of = {node: comp_id for comp_id, nodes in components.items() for node in nodes}
    assert comp_of[("RT1", "buyer")] == comp_of[("RT2", "buyer")]
    assert comp_of[("RT2", "buyer")] == comp_of[("RT3", "buyer")]
    assert len(components) == 1


def test_separate_strong_components_stay_separate():
    from cleo.discovery_v2.graph import build_components

    edges = [
        (("RT1", "buyer"), ("RT2", "buyer"), "strong"),
        (("RT3", "buyer"), ("RT4", "buyer"), "strong"),
    ]
    components = build_components(edges)
    assert len(components) == 2


def test_singleton_nodes_get_their_own_components():
    """Phase A: isolated party-sides (no edges) become singleton Groups
    (and singleton Contacts) so every party-side has an entity."""
    from cleo.discovery_v2.graph import build_components, seed_singletons

    edges = [(("RT1", "buyer"), ("RT2", "buyer"), "strong")]
    components = build_components(edges)
    # RT3 has no edges — add it as a singleton.
    components = seed_singletons(components, [("RT3", "buyer")])
    assert len(components) == 2
