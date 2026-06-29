"""Stage A9: Pick a probable HQ address per auto_group.

For each non-anonymized auto_group, score the canonical addresses appearing on
its party-sides by recency × frequency, and write the top scorer to
`auto_groups.primary_address` (with source='algorithmic').

User-set addresses (source='manual' or 'ai_enriched') are preserved — this
stage only overwrites rows whose source is null/algorithmic. Manual + AI
overrides survive every rebuild via this guard.
"""
from __future__ import annotations
import math
import sqlite3
from collections import defaultdict
from datetime import datetime


# Half-life in days for the recency weight. Addresses seen 365 days ago count
# at ~0.5 weight; ~5 years ago at ~0.0625. Tuneable.
RECENCY_HALF_LIFE_DAYS = 365.0


def _recency_weight(sale_date: str, today_iso: str) -> float:
    """Exponential decay weight: 1.0 today, 0.5 one year ago, etc."""
    if not sale_date or len(sale_date) < 10:
        return 0.3  # undated party gets a small constant weight
    try:
        d = datetime.fromisoformat(sale_date[:10])
        t = datetime.fromisoformat(today_iso[:10])
        delta_days = (t - d).days
    except (ValueError, TypeError):
        return 0.3
    if delta_days <= 0:
        return 1.0
    return math.pow(0.5, delta_days / RECENCY_HALF_LIFE_DAYS)


def build_primary_addresses(conn: sqlite3.Connection, *, verbose: bool = True) -> dict:
    """Score and assign primary_address for every auto_group.

    Skips groups whose primary_address_source is 'manual' or 'ai_enriched'
    (user-asserted overrides take precedence).
    """
    if verbose:
        print('  Stage A9 (primary HQ address): starting...', flush=True)

    today = conn.execute("SELECT date('now') AS d").fetchone()['d']

    # Pull every (auto_group_id, source_id, side, sale_date, party_address_canonical)
    # for non-anonymized groups. Anonymized bucket has no real address.
    rows = conn.execute("""
        SELECT agm.auto_group_id,
               pf.sale_date,
               pf.party_address_canonical
        FROM auto_group_members agm
        JOIN auto_groups ag ON ag.auto_group_id = agm.auto_group_id
        JOIN party_fingerprints pf
          ON pf.source_id = agm.source_id AND pf.side = agm.side
        WHERE agm.member_type = 'party_side'
          AND ag.canonical_stem != '_anonymized_individuals'
          AND pf.party_address_canonical IS NOT NULL
          AND pf.party_address_canonical != ''
    """).fetchall()

    # auto_group_id -> address -> score, count
    scores: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in rows:
        agid = r['auto_group_id']
        addr = r['party_address_canonical']
        w = _recency_weight(r['sale_date'], today)
        scores[agid][addr] += w
        counts[agid][addr] += 1

    # Which groups are protected from overwrite?
    protected = {
        r['auto_group_id']
        for r in conn.execute(
            "SELECT auto_group_id FROM auto_groups "
            "WHERE primary_address_source IN ('manual','ai_enriched')"
        )
    }

    updates: list[tuple] = []
    for agid, addr_scores in scores.items():
        if agid in protected:
            continue
        # Top scorer
        winner = max(addr_scores.items(), key=lambda kv: (kv[1], counts[agid][kv[0]]))
        winner_addr = winner[0]
        updates.append((winner_addr, 'algorithmic', agid))

    if updates:
        conn.executemany(
            "UPDATE auto_groups SET primary_address = ?, primary_address_source = ? "
            "WHERE auto_group_id = ?",
            updates,
        )
    conn.commit()

    if verbose:
        print(
            f'  Stage A9 (primary HQ address): {len(updates):,} groups updated, '
            f'{len(protected):,} protected (manual/ai).',
            flush=True,
        )

    return {
        'n_primary_addresses_assigned': len(updates),
        'n_primary_addresses_protected': len(protected),
    }
