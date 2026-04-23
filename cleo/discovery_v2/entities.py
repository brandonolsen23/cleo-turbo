"""Entity assignment — convert components into atom_groups / atom_contacts rows.

Assigns stable IDs via app_meta counters (next_agr_id, next_acn_id)
so subsequent runs can reuse IDs. In Phase A the mapping is by the
party-side membership fingerprint; collisions produce a new ID.
v2 will add a stability layer with split/merge events.
"""

from __future__ import annotations
from collections import Counter
from typing import Dict, List, Tuple

from .config import CALIBRATION

PartySide = Tuple[str, str]


def _next_counter(conn, key: str, *, seed: int = 1) -> int:
    row = conn.execute(
        "SELECT value FROM app_meta WHERE key = ?", (key,),
    ).fetchone()
    return int(row[0]) if row else seed


def _save_counter(conn, key: str, value: int):
    conn.execute(
        "INSERT OR REPLACE INTO app_meta (key, value, updated_at) "
        "VALUES (?, ?, datetime('now'))",
        (key, str(value)),
    )


def _load_party_metadata(conn, sides: List[PartySide]):
    """Load sale_date per party-side, grouped."""
    if not sides:
        return {}
    placeholders = ",".join("(?,?)" for _ in sides)
    flat = [x for s in sides for x in s]
    rows = conn.execute(
        f"SELECT source_id, side, sale_date FROM party_fingerprints "
        f"WHERE (source_id, side) IN (VALUES {placeholders})",
        flat,
    ).fetchall()
    return {(r["source_id"], r["side"]): r["sale_date"] for r in rows}


def _load_brand_phrases(conn, sides: List[PartySide]):
    if not sides:
        return {}
    placeholders = ",".join("(?,?)" for _ in sides)
    flat = [x for s in sides for x in s]
    rows = conn.execute(
        f"SELECT source_id, side, atom_value FROM party_atoms "
        f"WHERE atom_type = 'brand_phrase' AND (source_id, side) IN (VALUES {placeholders})",
        flat,
    ).fetchall()
    out: Dict[PartySide, List[str]] = {}
    for r in rows:
        out.setdefault((r["source_id"], r["side"]), []).append(r["atom_value"])
    return out


def _load_contact_fingerprints(conn, sides: List[PartySide]):
    if not sides:
        return {}
    placeholders = ",".join("(?,?)" for _ in sides)
    flat = [x for s in sides for x in s]
    rows = conn.execute(
        f"SELECT source_id, side, contact_fingerprint FROM party_fingerprints "
        f"WHERE (source_id, side) IN (VALUES {placeholders})",
        flat,
    ).fetchall()
    return {(r["source_id"], r["side"]): r["contact_fingerprint"] for r in rows}


def _pick_canonical_brand(
    sides: List[PartySide],
    brand_phrases_by_side: Dict[PartySide, List[str]],
    idf_map: Dict[Tuple[str, str], float],
    min_idf: float,
    excluded_phrases: frozenset,
) -> str:
    """Return the most common non-generic brand_phrase across the sides,
    tie-broken by the longer phrase (more information)."""
    phrase_counter = Counter()
    for side in sides:
        for phrase in brand_phrases_by_side.get(side, []):
            if phrase in excluded_phrases:
                continue
            if idf_map.get(("brand_phrase", phrase), 0.0) < min_idf:
                continue
            phrase_counter[phrase] += 1
    if phrase_counter:
        return max(
            phrase_counter.items(), key=lambda kv: (kv[1], len(kv[0]))
        )[0]
    # All phrases were generic or excluded — fall back to any phrase we saw.
    for side in sides:
        for phrase in brand_phrases_by_side.get(side, []):
            if phrase not in excluded_phrases:
                return phrase
    return "(unlabeled)"


def assign_group_entities(
    conn, components: Dict[int, List[PartySide]],
    idf_map: Dict[Tuple[str, str], float], min_idf: float,
    tier_by_pair: Dict[Tuple[PartySide, PartySide], str],
) -> Dict[int, str]:
    """Write atom_groups + atom_party_entities rows for each component.

    Returns {component_id: agr_id}. Idempotent: caller is expected to have
    cleared the derived tables before this runs (done by the runner).
    """
    cfg = CALIBRATION
    excluded = cfg["excluded_brand_phrases"]
    counter = _next_counter(conn, "next_agr_id", seed=1)
    comp_to_id: Dict[int, str] = {}

    all_sides = [s for nodes in components.values() for s in nodes]
    dates = _load_party_metadata(conn, all_sides)
    brand_phrases = _load_brand_phrases(conn, all_sides)

    for comp_id, sides in components.items():
        canonical = _pick_canonical_brand(
            sides, brand_phrases, idf_map, min_idf, excluded,
        )
        display = canonical.title()
        agr_id = f"AGR_{counter:05d}"
        counter += 1
        comp_to_id[comp_id] = agr_id

        sale_dates = sorted(
            d for d in (dates.get(s) for s in sides) if d
        )
        first_seen = sale_dates[0] if sale_dates else None
        last_seen = sale_dates[-1] if sale_dates else None

        conn.execute(
            "INSERT INTO atom_groups "
            "(id, canonical_brand, display_name, first_seen, last_seen, party_side_count) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (agr_id, canonical, display, first_seen, last_seen, len(sides)),
        )
        for (source_id, side) in sides:
            conn.execute(
                "INSERT OR IGNORE INTO atom_party_entities "
                "(source_id, side, group_id, group_link_tier) "
                "VALUES (?, ?, ?, 'strong')",
                (source_id, side, agr_id),
            )
            conn.execute(
                "UPDATE atom_party_entities SET group_id = ?, group_link_tier = 'strong' "
                "WHERE source_id = ? AND side = ?",
                (agr_id, source_id, side),
            )

    _save_counter(conn, "next_agr_id", counter)
    conn.commit()
    return comp_to_id


def assign_contact_entities(
    conn, components: Dict[int, List[PartySide]],
    tier_by_pair: Dict[Tuple[PartySide, PartySide], str],
) -> Dict[int, str]:
    """Write atom_contacts + update atom_party_entities.contact_id for each component.

    Canonical name = most common contact_fingerprint in the component.

    Note: atom_party_entities rows may already exist from assign_group_entities.
    This function uses INSERT OR IGNORE + UPDATE to safely add the contact_id
    column to existing rows (first pass sets group_id, second pass sets
    contact_id on the same row). The PRIMARY KEY on (source_id, side) ensures
    both passes share the same row.
    """
    counter = _next_counter(conn, "next_acn_id", seed=1)
    comp_to_id: Dict[int, str] = {}

    all_sides = [s for nodes in components.values() for s in nodes]
    fingerprints = _load_contact_fingerprints(conn, all_sides)
    dates = _load_party_metadata(conn, all_sides)

    for comp_id, sides in components.items():
        fps = [fingerprints.get(s) for s in sides]
        fps = [fp for fp in fps if fp]
        if not fps:
            continue  # singleton with no contact — skip; party still has a Group
        counter_fp = Counter(fps).most_common(1)[0][0]
        display = " ".join(w.capitalize() for w in counter_fp.split())
        acn_id = f"ACN_{counter:05d}"
        counter += 1
        comp_to_id[comp_id] = acn_id

        sale_dates = sorted(d for d in (dates.get(s) for s in sides) if d)
        first_seen = sale_dates[0] if sale_dates else None
        last_seen = sale_dates[-1] if sale_dates else None

        conn.execute(
            "INSERT INTO atom_contacts "
            "(id, canonical_name, display_name, first_seen, last_seen, party_side_count) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (acn_id, counter_fp, display, first_seen, last_seen, len(sides)),
        )
        for (source_id, side) in sides:
            conn.execute(
                "INSERT OR IGNORE INTO atom_party_entities "
                "(source_id, side) VALUES (?, ?)",
                (source_id, side),
            )
            conn.execute(
                "UPDATE atom_party_entities SET contact_id = ?, contact_link_tier = 'strong' "
                "WHERE source_id = ? AND side = ?",
                (acn_id, source_id, side),
            )

    _save_counter(conn, "next_acn_id", counter)
    conn.commit()
    return comp_to_id
