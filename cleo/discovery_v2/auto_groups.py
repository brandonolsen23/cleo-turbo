"""Layer 2 Plan A orchestrator: stems → anchor scores → seeding → expansion → display."""
from __future__ import annotations
import sqlite3

from cleo.discovery_v2.stems import build_stems
from cleo.discovery_v2.anchor_scores import build_anchor_scores
from cleo.discovery_v2.seeding import build_seeds
from cleo.discovery_v2.expansion import build_expansion


def build_auto_groups(conn: sqlite3.Connection, *, verbose: bool = True) -> dict:
    """Run all five stages of Plan A. Idempotent — each stage clears its own derived tables."""
    if verbose:
        print('Layer 2 Plan A: starting build...', flush=True)

    a1 = build_stems(conn, verbose=verbose)
    a2 = build_anchor_scores(conn, verbose=verbose)
    a3 = build_seeds(conn, verbose=verbose)
    a4 = build_expansion(conn, verbose=verbose)
    a5 = _finalize_display_and_counts(conn, verbose=verbose)

    summary = {**a1, **a2, **a3, **a4, **a5}
    if verbose:
        print(f'Layer 2 Plan A: done. {summary}', flush=True)
    return summary


def _finalize_display_and_counts(conn: sqlite3.Connection, *, verbose: bool = True) -> dict:
    """Stage A5: pick display_name as max-count phrase mapping to canonical_stem; refresh n_members."""
    n_updated = 0
    for r in conn.execute('SELECT auto_group_id, canonical_stem FROM auto_groups').fetchall():
        gid, stem = r['auto_group_id'], r['canonical_stem']

        # display_name: most-frequent phrase among members where phrase → stem
        row = conn.execute(
            """SELECT pa.atom_value AS phrase, COUNT(*) AS n
               FROM auto_group_members agm
               JOIN party_atoms pa
                 ON pa.source_id = agm.source_id
                AND pa.side      = agm.side
                AND pa.atom_type = 'brand_phrase'
               JOIN brand_stem_phrase_map m
                 ON m.phrase = pa.atom_value
                AND m.stem   = ?
               WHERE agm.auto_group_id = ?
                 AND agm.member_type = 'party_side'
               GROUP BY pa.atom_value
               ORDER BY n DESC
               LIMIT 1""",
            (stem, gid),
        ).fetchone()
        display_name = row['phrase'] if row else stem

        n_members = conn.execute(
            'SELECT COUNT(*) AS n FROM auto_group_members WHERE auto_group_id=?',
            (gid,),
        ).fetchone()['n']

        conn.execute(
            'UPDATE auto_groups SET display_name=?, n_members=? WHERE auto_group_id=?',
            (display_name, n_members, gid),
        )
        n_updated += 1
    conn.commit()
    if verbose:
        print(f'  Stage A5 (display + counts): {n_updated:,} groups updated.', flush=True)
    return {'n_groups_finalized': n_updated}
