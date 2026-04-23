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
from .graph import _UnionFind
from .entities import assign_group_entities, assign_contact_entities
from .timelines import materialize_timelines
from .relationships import detect_jv_relationships


def _components_from_uf(uf) -> dict:
    """Extract connected components from a populated _UnionFind.

    Returns {component_id: [party_side, ...]} matching the shape produced
    by graph.build_components + graph.seed_singletons so downstream callers
    (entity assignment) don't need to change.
    """
    groups = defaultdict(list)
    for node in uf.parent:
        groups[uf.find(node)].append(node)
    return {i: sorted(nodes) for i, nodes in enumerate(groups.values())}


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

    # Discovery wipes + rebuilds atom_* tables. The GW watcher and FastAPI
    # app may hold brief write transactions; wait up to 2 minutes for locks.
    conn.execute("PRAGMA busy_timeout = 120000")

    if verbose:
        print(f"Phase A discovery run: config {CALIBRATION['version']} (min_idf={effective_min_idf})", flush=True)

    _wipe_derived(conn)

    idf_map = compute_idf_map(conn)
    if verbose:
        print(f"  IDF map: {len(idf_map):,} (atom_type, value) entries", flush=True)

    # Streaming: blocking yields one candidate pair at a time → score it →
    # union it into the graph if Strong → discard. Memory stays O(N) in the
    # union-find structure regardless of candidate-pair count. This replaces
    # a prior batch approach that accumulated ~17M pairs in a dict and
    # pushed the process into 30GB+ of compressed-page memory.

    group_uf = _UnionFind()
    contact_uf = _UnionFind()

    all_sides = _all_party_sides(conn)
    for side in all_sides:
        group_uf.add(side)  # ensures singletons end up as their own components

    n_candidate_pairs = 0
    n_group_edges = 0
    n_contact_edges = 0
    for (sid_a, side_a, sid_b, side_b, atom_type, atom_value) in generate_candidate_pairs(
        conn, idf_map, min_idf=effective_min_idf,
    ):
        n_candidate_pairs += 1
        a = (sid_a, side_a)
        b = (sid_b, side_b)
        idf = idf_map.get((atom_type, atom_value), 0.0)
        match_atoms = [(atom_type, atom_value, idf)]
        result = score_pair(match_atoms, min_idf=effective_min_idf)
        if result["group_tier"] == "strong":
            group_uf.add(a)
            group_uf.add(b)
            group_uf.union(a, b)
            n_group_edges += 1
        if result["contact_tier"] == "strong":
            contact_uf.add(a)
            contact_uf.add(b)
            contact_uf.union(a, b)
            n_contact_edges += 1
    if verbose:
        print(f"  Candidate pairs: {n_candidate_pairs:,}", flush=True)
        print(f"  Strong Group edges: {n_group_edges:,}", flush=True)
        print(f"  Strong Contact edges: {n_contact_edges:,}", flush=True)

    group_components = _components_from_uf(group_uf)
    contact_components = _components_from_uf(contact_uf)
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
