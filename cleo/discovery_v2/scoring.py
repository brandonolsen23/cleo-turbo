"""Pair scoring — compute Group-graph and Contact-graph tier per pair.

Phase A: exact-tier only. A pair carries one or more match atoms
(from the blocking pass). Scoring decides whether the pair is a
Strong edge in the Group graph, the Contact graph, both, or neither.

Phase A rules (see spec S6, revised 2026-04-23 after mega-cluster bug):
  - Exact non-generic brand_token alone → Strong Group edge
  - Exact address_triple alone → NOT Strong (downtown towers, courthouses,
    receiver offices are shared across unrelated operators; needs co-signal)
  - address_triple + brand_token → Strong (brand does the work)
  - address_triple + contact_fingerprint → Strong (same place, same person)
  - address_triple + phone → Strong (same place, same phone line)
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


def score_pair(match_atoms: List[MatchAtom], *, min_idf: Optional[float] = None) -> PairScore:
    """Given the match atoms for a pair, return the Group and Contact tiers.

    Phase A outputs: 'strong' or None. No medium tier in Phase A.

    Parameters
    ----------
    min_idf : optional override for the brand_token IDF gate. Default (None)
        uses CALIBRATION["exact_brand_token"]["min_idf"] (production = 3.0).
        Test harnesses pass 0.0 to treat all brand_tokens as sufficiently rare.
    """
    result: PairScore = {"group_tier": None, "contact_tier": None, "match_atoms": match_atoms}
    if not match_atoms:
        return result

    if min_idf is None:
        min_idf = CALIBRATION["exact_brand_token"]["min_idf"]

    brand_token_hit = any(
        a[0] == "brand_token" and (min_idf <= 0.0 or a[2] >= min_idf) for a in match_atoms
    )
    address_triple_hit = any(a[0] == "address_triple" for a in match_atoms)
    phone_hit = any(a[0] == "phone" for a in match_atoms)
    contact_hit = any(a[0] == "contact_fingerprint" for a in match_atoms)

    # Group-graph tier (revised after mega-cluster bug on 2026-04-23):
    #   - brand_token alone → Strong (brands are distinctive)
    #   - address_triple alone → NOT Strong (downtown towers, courthouses,
    #     receiver offices are shared across unrelated operators)
    #   - address_triple + brand_token → Strong (brand does the work)
    #   - address_triple + contact_fingerprint → Strong (same place, same person)
    #   - address_triple + phone → Strong (same place, same phone line)
    #   - phone alone → NOT Strong (management-line aliasing)
    #   - phone + brand_token OR phone + address_triple → Strong
    if brand_token_hit:
        result["group_tier"] = "strong"
    elif address_triple_hit and (contact_hit or phone_hit):
        result["group_tier"] = "strong"
    elif phone_hit and address_triple_hit:
        # same as above (symmetric) — kept explicit for readability
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
