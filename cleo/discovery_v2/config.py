"""Calibration knobs for atom-based portfolio discovery.

Every matching rule is a knob. Phase A ships with the exact-match tier
only — subsequent phases add nickname/phonetic/fuzzy/subset.

Changes here are real. Check the eval harness output (docs/discovery-audit/)
after every knob turn.
"""

from __future__ import annotations

CALIBRATION_VERSION = "2026-04-22-phase-a-v1"

CALIBRATION = {
    "version": CALIBRATION_VERSION,

    # Tier 1 — exact brand_token match (Group graph's primary signal)
    "exact_brand_token": {
        "enabled": True,
        "min_idf": 3.0,
        "reason": (
            "Tokens on ~5,000+ party-sides have IDF under 3.0 (N=249,084). "
            "Above that floor: rasenberg (IDF ~8.5) allowed, kingsett "
            "(IDF ~6.5) allowed, holdings (IDF ~2.7) blocked, ontario (IDF "
            "~1.4) blocked. Generic corporate vocabulary gets dampened to "
            "blocking-only; distinctive tokens drive links."
        ),
    },

    # Tier 1 — exact address-triple (street_number + street_name + street_suffix)
    "exact_address_triple": {
        "enabled": True,
        "require_all_three_parts": True,
        "reason": (
            "Full triple match is strong alone (median count <= 5 per "
            "triple). Individual parts (street_name='king') are too common."
        ),
    },

    # Tier 1 — exact phone (only Strong when a brand OR address co-signal agrees)
    "exact_phone": {
        "enabled": True,
        "require_co_signal": True,
        "co_signal_atoms": ["brand_token", "address_triple"],
        "reason": (
            "Phones alias: management-company main lines appear across "
            "unrelated operator portfolios. Rarity != precision. Upgrade "
            "phone to Strong only when a brand or address corroborates."
        ),
    },

    # Tier 1 — exact contact fingerprint (drives Contact graph)
    "exact_contact_fingerprint": {
        "enabled": True,
        "reason": (
            "First+last exact match is Strong for Contact-entity linking. "
            "Does NOT merge Groups — a person can work at many Groups."
        ),
    },

    # Categorical exclusions (never used as link atoms; see spec S9).
    "excluded_brand_tokens": frozenset({
        "named", "individual",  # Named Individual(s) suppressed-name artifact
    }),
    "excluded_brand_phrases": frozenset({
        "named individual s",
        "creo mail code 01 86",  # RT scraping artifact
    }),

    # Blocking cap — skip atoms whose count of carrying party-sides exceeds
    # this threshold. A shared value on >500 sides produces C(500,2)=125K
    # pairs, most of which are unrelated (e.g., a downtown office tower
    # address shared across hundreds of businesses). Higher-count atoms
    # aren't discriminative and explode the candidate-pair set.
    "blocking_max_sides_per_atom": {
        "enabled": True,
        "max_sides": 500,
        "reason": (
            "Street number 1 appears on 2,941 party-sides alone. The "
            "top address_triple, phone, and contact_fingerprint counts "
            "run into the high hundreds. At 500 sides we keep distinctive "
            "portfolios (KingSett at 66 Wellington = 291 sides, KingSett "
            "at 161 Bay = 495 sides) while dropping pathological ones."
        ),
    },

    # Audit inputs for eval harness
    "audit_docs_root": "docs/discovery-audit",
}
