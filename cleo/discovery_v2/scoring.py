"""Pair scoring — compute Group-graph and Contact-graph tier per pair.

Phase A: exact-tier only. A pair carries one or more match atoms
(from the blocking pass). Scoring decides whether the pair is a
Strong edge in the Group graph, the Contact graph, both, or neither.

Phase A rules (see spec S6):
  - Exact non-generic brand_token alone → Strong Group edge
  - Exact address_triple alone → Strong Group edge
  - Exact phone alone → not Strong (alias risk); Strong only when
    brand or address co-signal agrees
  - Exact contact_fingerprint → Strong Contact edge (never a Group edge
    by itself — people move between Groups)
"""

from __future__ import annotations
from typing import List, Optional, Tuple, TypedDict

from .config import CALIBRATION

MatchAtom = Tuple[str, str, float]  # (atom_type, atom_value, idf)


class PairScore(TypedDict):
    group_tier: Optional[str]   # 'strong' | None
    contact_tier: Optional[str]
    match_atoms: List[MatchAtom]


def score_pair(match_atoms: List[MatchAtom]) -> PairScore:
    """Given the match atoms for a pair, return the Group and Contact tiers.

    Phase A outputs: 'strong' or None. No medium tier in Phase A.
    """
    result: PairScore = {"group_tier": None, "contact_tier": None, "match_atoms": match_atoms}
    if not match_atoms:
        return result

    min_idf = CALIBRATION["exact_brand_token"]["min_idf"]

    brand_token_hit = any(
        a[0] == "brand_token" and a[2] >= min_idf for a in match_atoms
    )
    address_triple_hit = any(a[0] == "address_triple" for a in match_atoms)
    phone_hit = any(a[0] == "phone" for a in match_atoms)
    contact_hit = any(a[0] == "contact_fingerprint" for a in match_atoms)

    # Group-graph tier
    if brand_token_hit or address_triple_hit:
        result["group_tier"] = "strong"
    elif phone_hit and (brand_token_hit or address_triple_hit):
        # unreachable given the above, but explicit about the co-signal rule
        result["group_tier"] = "strong"

    # Contact-graph tier — exact contact fingerprint → Strong
    if contact_hit:
        result["contact_tier"] = "strong"

    return result


def aggregate_match_atoms(pair_rows) -> List[MatchAtom]:
    """Given multiple candidate-pair rows for the same (source_a, source_b),
    aggregate their (atom_type, atom_value) into a single match_atoms list.

    Called by the runner to compress blocking output before scoring.
    """
    seen = set()
    result = []
    for row in pair_rows:
        key = (row["atom_type"], row["atom_value"])
        if key in seen:
            continue
        seen.add(key)
        result.append((row["atom_type"], row["atom_value"], row.get("idf", 0.0)))
    return result
