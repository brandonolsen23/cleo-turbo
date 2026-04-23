"""Orchestrator — run the full Phase A discovery pass.

Order:
  1. Wipe derived atom_* tables (except atom_discovery_runs).
  2. Compute IDF map.
  3. Generate candidate pairs (blocking).
  4. Score pairs → Strong Group and Contact edges.
  5. Union-find → components.
  6. Assign entities (atom_groups, atom_contacts).
  7. Materialize timelines.
  8. Detect JV relationships.
  9. Log the run to atom_discovery_runs.
"""

from __future__ import annotations
import json
from collections import defaultdict
from typing import Optional

from .config import CALIBRATION
from .idf import compute_idf_map
from .blocking import generate_candidate_pairs
from .scoring import score_pair
from .graph import build_components, seed_singletons
from .entities import assign_group_entities, assign_contact_entities
from .timelines import materialize_timelines
from .relationships import detect_jv_relationships


def _wipe_derived(conn):
    for tbl in (
        "atom_group_relationships",
        "atom_contact_addresses", "atom_contact_groups",
        "atom_group_contacts", "atom_group_phones", "atom_group_addresses",
        "atom_party_entities",
        "atom_contacts", "atom_groups",
    ):
        conn.execute(f"DELETE FROM {tbl}")


def _all_party_sides(conn):
    return [
        (r["source_id"], r["side"])
        for r in conn.execute("SELECT source_id, side FROM party_fingerprints")
    ]


def _pairs_from_blocking(conn, idf_map, min_idf):
    """Aggregate candidate-pair rows by (a, b) into {pair: [(atom_type, value, idf), ...]}."""
    pairs = defaultdict(list)
    for (sid_a, side_a, sid_b, side_b, atom_type, atom_value) in generate_candidate_pairs(
        conn, idf_map, min_idf=min_idf,
    ):
        a, b = (sid_a, side_a), (sid_b, side_b)
        if a > b:
            a, b = b, a
        idf = idf_map.get((atom_type, atom_value), 0.0)
        pairs[(a, b)].append((atom_type, atom_value, idf))
    return pairs


def run_discovery(conn, *, verbose: bool = True, min_idf: Optional[float] = None):
    """Run the full Phase A discovery pipeline.

    Parameters
    ----------
    min_idf : optional override for blocking's IDF threshold and the scoring
        brand_token IDF gate. Default (None) uses
        CALIBRATION["exact_brand_token"]["min_idf"] (production = 3.0).
        Test harnesses pass 0.0 to disable the gate on small fixtures.
    """
    effective_min_idf = (
        min_idf if min_idf is not None
        else CALIBRATION["exact_brand_token"]["min_idf"]
    )

    if verbose:
        print(f"Phase A discovery run: config {CALIBRATION['version']} (min_idf={effective_min_idf})", flush=True)

    _wipe_derived(conn)

    idf_map = compute_idf_map(conn)
    if verbose:
        print(f"  IDF map: {len(idf_map):,} (atom_type, value) entries", flush=True)

    pairs = _pairs_from_blocking(conn, idf_map, effective_min_idf)
    if verbose:
        print(f"  Candidate pairs: {len(pairs):,}", flush=True)

    group_edges = []
    contact_edges = []
    for (a, b), match_atoms in pairs.items():
        result = score_pair(match_atoms, min_idf=effective_min_idf)
        if result["group_tier"] == "strong":
            group_edges.append((a, b, "strong"))
        if result["contact_tier"] == "strong":
            contact_edges.append((a, b, "strong"))
    if verbose:
        print(f"  Strong Group edges: {len(group_edges):,}", flush=True)
        print(f"  Strong Contact edges: {len(contact_edges):,}", flush=True)

    all_sides = _all_party_sides(conn)
    group_components = seed_singletons(build_components(group_edges), all_sides)
    contact_components = build_components(contact_edges)  # no singletons for contacts
    if verbose:
        print(f"  Group components: {len(group_components):,}", flush=True)
        print(f"  Contact components: {len(contact_components):,}", flush=True)

    assign_group_entities(
        conn, group_components, idf_map,
        min_idf=effective_min_idf,
        tier_by_pair={},
    )
    assign_contact_entities(conn, contact_components, tier_by_pair={})

    materialize_timelines(conn)
    detect_jv_relationships(conn)

    n_party_sides = conn.execute("SELECT COUNT(*) FROM party_fingerprints").fetchone()[0]
    n_groups = conn.execute("SELECT COUNT(*) FROM atom_groups").fetchone()[0]
    n_contacts = conn.execute("SELECT COUNT(*) FROM atom_contacts").fetchone()[0]

    conn.execute(
        "INSERT INTO atom_discovery_runs "
        "(config_version, config_snapshot, n_party_sides, n_groups, n_contacts) "
        "VALUES (?, ?, ?, ?, ?)",
        (CALIBRATION["version"], _safe_dumps(CALIBRATION),
         n_party_sides, n_groups, n_contacts),
    )
    conn.commit()

    if verbose:
        print(f"  Wrote {n_groups:,} Groups, {n_contacts:,} Contacts.", flush=True)
    return {"n_party_sides": n_party_sides, "n_groups": n_groups, "n_contacts": n_contacts}


def _safe_dumps(obj):
    return json.dumps(obj, default=lambda v: list(v) if isinstance(v, (set, frozenset)) else str(v))
