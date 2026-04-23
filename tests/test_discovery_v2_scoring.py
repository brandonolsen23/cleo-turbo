"""Tests for pair scoring — exact-tier only in Phase A."""


def test_exact_rare_brand_token_is_strong_group_edge():
    from cleo.discovery_v2.scoring import score_pair
    # IDF 7.0 > min_idf 3.0
    match_atoms = [("brand_token", "kingsett", 7.0)]
    result = score_pair(match_atoms)
    assert result["group_tier"] == "strong"
    assert result["contact_tier"] is None


def test_generic_brand_token_is_not_a_link():
    """A token below min_idf shouldn't even appear in match_atoms, but
    belt-and-suspenders: scoring rejects it if it slips through."""
    from cleo.discovery_v2.scoring import score_pair
    match_atoms = [("brand_token", "holdings", 2.0)]  # below min_idf=3.0
    result = score_pair(match_atoms)
    assert result["group_tier"] is None


def test_address_triple_alone_is_strong_group_edge():
    from cleo.discovery_v2.scoring import score_pair
    match_atoms = [("address_triple", "66|wellington|street", 5.0)]
    result = score_pair(match_atoms)
    assert result["group_tier"] == "strong"


def test_phone_alone_is_not_a_strong_edge():
    """Phones alias across unrelated portfolios (management company lines).
    Phone-only stays medium (not auto-linked in Phase A)."""
    from cleo.discovery_v2.scoring import score_pair
    match_atoms = [("phone", "4162348444", 5.0)]
    result = score_pair(match_atoms)
    assert result["group_tier"] != "strong"


def test_phone_plus_brand_cosignal_is_strong():
    from cleo.discovery_v2.scoring import score_pair
    match_atoms = [
        ("phone", "4166876700", 5.0),
        ("brand_token", "kingsett", 7.0),
    ]
    result = score_pair(match_atoms)
    assert result["group_tier"] == "strong"


def test_phone_plus_address_cosignal_is_strong():
    from cleo.discovery_v2.scoring import score_pair
    match_atoms = [
        ("phone", "4166876700", 5.0),
        ("address_triple", "66|wellington|street", 5.0),
    ]
    result = score_pair(match_atoms)
    assert result["group_tier"] == "strong"


def test_exact_contact_fingerprint_is_strong_contact_edge_not_group_edge():
    """Same person can work at many different Groups. Contact-only match
    drives the Contact graph, NOT the Group graph."""
    from cleo.discovery_v2.scoring import score_pair
    match_atoms = [("contact_fingerprint", "rob kumer", 6.0)]
    result = score_pair(match_atoms)
    assert result["contact_tier"] == "strong"
    assert result["group_tier"] is None
