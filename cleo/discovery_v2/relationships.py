"""Derived Group-to-Group relationships.

Phase A handles JV only: a single party-side carrying two or more
distinct, non-generic brand_phrases that map to different atom_groups
→ JV edge between those Groups.

Relies on the brand_phrase → atom_groups mapping already established
by entities.assign_group_entities (where each Group's canonical_brand
is its dominant non-generic phrase).
"""

from __future__ import annotations
from collections import defaultdict
from typing import Dict, Set, Tuple

from .config import CALIBRATION


def _build_phrase_to_group_map(conn) -> Dict[str, str]:
    """Map each distinct brand_phrase to the Group whose canonical_brand
    most closely represents it. For Phase A we use exact phrase → Group
    via canonical_brand. Phrases that aren't anyone's canonical drop out."""
    return {
        row["canonical_brand"]: row["id"]
        for row in conn.execute(
            "SELECT id, canonical_brand FROM atom_groups WHERE canonical_brand IS NOT NULL"
        )
    }


def detect_jv_relationships(conn):
    """Find party-sides with 2+ distinct non-generic brand_phrases and
    emit pairwise JV edges between the Groups those phrases represent."""
    conn.execute("DELETE FROM atom_group_relationships")

    excluded = CALIBRATION["excluded_brand_phrases"]
    phrase_to_group = _build_phrase_to_group_map(conn)

    # Gather party-sides with their brand_phrase sets
    sides_phrases: Dict[Tuple[str, str], Set[str]] = defaultdict(set)
    for row in conn.execute(
        "SELECT source_id, side, atom_value FROM party_atoms WHERE atom_type = 'brand_phrase'"
    ):
        if row["atom_value"] in excluded:
            continue
        sides_phrases[(row["source_id"], row["side"])].add(row["atom_value"])

    # Aggregate pairwise (group_a, group_b) JV observations
    pair_stats: Dict[Tuple[str, str], Dict[str, object]] = defaultdict(
        lambda: {"n": 0, "first": None, "last": None}
    )
    dates = {
        (r["source_id"], r["side"]): r["sale_date"]
        for r in conn.execute("SELECT source_id, side, sale_date FROM party_fingerprints")
    }

    for (sid, side), phrases in sides_phrases.items():
        if len(phrases) < 2:
            continue
        groups = {phrase_to_group[p] for p in phrases if p in phrase_to_group}
        if len(groups) < 2:
            continue
        groups_sorted = sorted(groups)
        date = dates.get((sid, side))
        for i in range(len(groups_sorted)):
            for j in range(i + 1, len(groups_sorted)):
                key = (groups_sorted[i], groups_sorted[j])
                stats = pair_stats[key]
                stats["n"] += 1
                if date:
                    if stats["first"] is None or date < stats["first"]:
                        stats["first"] = date
                    if stats["last"] is None or date > stats["last"]:
                        stats["last"] = date

    for (a, b), stats in pair_stats.items():
        conn.execute(
            "INSERT INTO atom_group_relationships "
            "(group_a_id, group_b_id, kind, first_seen, last_seen, n_party_sides) "
            "VALUES (?, ?, 'jv', ?, ?, ?)",
            (a, b, stats["first"], stats["last"], stats["n"]),
        )
    conn.commit()
