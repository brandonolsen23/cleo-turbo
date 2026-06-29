"""Stage A8: Build the legacy → auto_group mapping + denormalised contact FK.

For every legacy group, picks the dominant auto_group its party-sides land in.
Runs after standalone_coverage (which guarantees 100% party-side coverage),
so every legacy group with at least one party-side ends up with a mapping.

Outputs:
- `legacy_to_auto_group_map` populated (replaces prior contents)
- `contacts.current_auto_group_id` populated via the map
"""
from __future__ import annotations
import sqlite3
from collections import defaultdict


def build_legacy_map(conn: sqlite3.Connection, *, verbose: bool = True) -> dict:
    """Rebuild legacy_to_auto_group_map from auto_group_members + transaction_parties + groups."""
    if verbose:
        print('  Stage A8 (legacy → auto_group map): starting...', flush=True)

    conn.execute('DELETE FROM legacy_to_auto_group_map')

    # Count: per (legacy_group_id, auto_group_id) how many party-sides agree
    counts: dict[tuple[str, str], int] = defaultdict(int)
    totals_per_legacy: dict[str, int] = defaultdict(int)

    for r in conn.execute("""
        SELECT tp.group_id AS lgid, agm.auto_group_id AS agid, COUNT(*) AS n
        FROM transaction_parties tp
        JOIN auto_group_members agm
          ON agm.source_id = tp.source_id AND agm.side = tp.side
        WHERE tp.group_id IS NOT NULL
          AND agm.member_type = 'party_side'
        GROUP BY tp.group_id, agm.auto_group_id
    """):
        counts[(r['lgid'], r['agid'])] = r['n']
        totals_per_legacy[r['lgid']] += r['n']

    # Pick dominant auto_group per legacy group; tag source by tier
    tier_by_agid: dict[str, str] = {}
    for r in conn.execute("SELECT auto_group_id, tier FROM auto_groups"):
        tier_by_agid[r['auto_group_id']] = r['tier']

    legacy_to_best: dict[str, tuple[str, int]] = {}
    for (lgid, agid), n in counts.items():
        if lgid not in legacy_to_best or n > legacy_to_best[lgid][1]:
            legacy_to_best[lgid] = (agid, n)

    rows = []
    for lgid, (agid, dominant_count) in legacy_to_best.items():
        total = totals_per_legacy[lgid]
        coverage_pct = (dominant_count / total) if total else 0.0
        tier = tier_by_agid.get(agid, '')
        source = 'standalone' if tier == 'standalone' else 'clustered'
        rows.append((lgid, agid, coverage_pct, source))

    conn.executemany(
        "INSERT INTO legacy_to_auto_group_map (legacy_group_id, auto_group_id, coverage_pct, source) "
        "VALUES (?, ?, ?, ?)",
        rows,
    )

    # Populate contacts.current_auto_group_id from the map
    conn.execute("""
        UPDATE contacts
        SET current_auto_group_id = (
            SELECT auto_group_id FROM legacy_to_auto_group_map
            WHERE legacy_group_id = contacts.current_group_id
        )
        WHERE current_group_id IS NOT NULL
    """)

    n_contacts_mapped = conn.execute(
        "SELECT COUNT(*) FROM contacts WHERE current_auto_group_id IS NOT NULL"
    ).fetchone()[0]
    n_contacts_total = conn.execute(
        "SELECT COUNT(*) FROM contacts WHERE current_group_id IS NOT NULL"
    ).fetchone()[0]

    conn.commit()

    if verbose:
        print(
            f'  Stage A8 (legacy → auto_group map): {len(rows):,} legacy groups mapped; '
            f'{n_contacts_mapped:,}/{n_contacts_total:,} contacts assigned current_auto_group_id.',
            flush=True,
        )

    return {
        'n_legacy_groups_mapped': len(rows),
        'n_contacts_auto_group_assigned': n_contacts_mapped,
        'n_contacts_with_legacy_group': n_contacts_total,
    }
