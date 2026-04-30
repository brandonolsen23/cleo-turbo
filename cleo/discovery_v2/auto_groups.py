"""Layer 2 orchestrator: A1 → A2 (tenures) → A3 (seed) → A4 (time-aware) →
contact_tenures → A6 (conflicts) → A5 (display)."""
from __future__ import annotations
import sqlite3

from cleo.discovery_v2.stems import build_stems
from cleo.discovery_v2.anchor_scores import build_anchor_scores
from cleo.discovery_v2.seeding import build_seeds, build_contact_tenures
from cleo.discovery_v2.expansion import build_expansion
from cleo.discovery_v2.conflicts import detect_conflicts


def build_auto_groups(conn: sqlite3.Connection, *, verbose: bool = True) -> dict:
    """Run all stages of Layer 2. Idempotent — each stage clears its own derived tables."""
    if verbose:
        print('Layer 2: starting build...', flush=True)

    a1 = build_stems(conn, verbose=verbose)
    a2 = build_anchor_scores(conn, verbose=verbose)
    a3 = build_seeds(conn, verbose=verbose)
    a4 = build_expansion(conn, verbose=verbose)
    ct = build_contact_tenures(conn, verbose=verbose)
    a6 = detect_conflicts(conn, verbose=verbose)
    a5 = _finalize_display_and_counts(conn, verbose=verbose)

    summary = {**a1, **a2, **a3, **a4, **ct, **a6, **a5}
    if verbose:
        print(f'Layer 2: done. {summary}', flush=True)
    return summary


def _finalize_display_and_counts(conn: sqlite3.Connection, *, verbose: bool = True) -> dict:
    """Stage A5: pick display_name as max-count phrase mapping to canonical_stem; refresh n_members.

    Uses two bulk queries (one for display names, one for counts) instead of a per-group
    loop. The per-group loop performed 2 queries × 1682 groups = 3364 round-trips, each
    with a 3-table JOIN — that doesn't finish in any reasonable time on a real-size DB.
    """
    # Bulk display-name selection: rank phrases per group, take top 1.
    name_by_group: dict[str, str] = {}
    for r in conn.execute("""
        WITH ranked AS (
            SELECT agm.auto_group_id,
                   pa.atom_value AS phrase,
                   COUNT(*) AS n,
                   ROW_NUMBER() OVER (
                       PARTITION BY agm.auto_group_id
                       ORDER BY COUNT(*) DESC, length(pa.atom_value) ASC, pa.atom_value ASC
                   ) AS rk
            FROM auto_group_members agm
            JOIN auto_groups g
              ON g.auto_group_id = agm.auto_group_id
            JOIN party_atoms pa
              ON pa.source_id = agm.source_id
             AND pa.side      = agm.side
             AND pa.atom_type = 'brand_phrase'
            JOIN brand_stem_phrase_map m
              ON m.phrase = pa.atom_value
             AND m.stem   = g.canonical_stem
            WHERE agm.member_type = 'party_side'
            GROUP BY agm.auto_group_id, pa.atom_value
        )
        SELECT auto_group_id, phrase FROM ranked WHERE rk = 1
    """):
        name_by_group[r['auto_group_id']] = r['phrase']

    # Bulk member counts (all member types — party_side + numbered_corp).
    count_by_group: dict[str, int] = {}
    for r in conn.execute("""
        SELECT auto_group_id, COUNT(*) AS n
        FROM auto_group_members
        GROUP BY auto_group_id
    """):
        count_by_group[r['auto_group_id']] = r['n']

    # Update each auto_group; fall back to canonical_stem when no party-side members.
    updates = []
    for r in conn.execute('SELECT auto_group_id, canonical_stem FROM auto_groups').fetchall():
        gid = r['auto_group_id']
        display_name = name_by_group.get(gid, r['canonical_stem'])
        n_members = count_by_group.get(gid, 0)
        updates.append((display_name, n_members, gid))

    conn.executemany(
        'UPDATE auto_groups SET display_name=?, n_members=? WHERE auto_group_id=?',
        updates,
    )
    conn.commit()
    if verbose:
        print(f'  Stage A5 (display + counts): {len(updates):,} groups updated.', flush=True)
    return {'n_groups_finalized': len(updates)}
