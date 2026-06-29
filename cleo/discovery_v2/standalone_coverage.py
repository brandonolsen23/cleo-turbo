"""Stage A7: Standalone auto_group coverage — ensure every party-side has a home.

Runs after clustering + expansion + force-attach + conflict detection. For every
legacy group whose party-sides are not already in any auto_group, creates a
'standalone'-tier auto_group keyed on the legacy group's normalized_name.
Attaches every party-side belonging to that legacy group.

For legacy groups that are *partially* covered (some party-sides in a cluster,
some not), attaches the leftover party-sides to the dominant auto_group the
legacy group is already in. This ensures each legacy group's party-sides end
up in a single auto_group, not split.

Result: 100% party-side coverage. Each (source_id, side) pair appears in
exactly one auto_group_members row.
"""
from __future__ import annotations
import sqlite3
from collections import defaultdict


def _next_group_id_start(conn: sqlite3.Connection) -> int:
    """Find the highest existing AGRP_NNNNN integer suffix so new IDs continue from there."""
    max_n = 0
    for r in conn.execute("SELECT auto_group_id FROM auto_groups WHERE auto_group_id LIKE 'AGRP_%'"):
        try:
            n = int(r['auto_group_id'].split('_', 1)[1])
            if n > max_n:
                max_n = n
        except (ValueError, IndexError):
            pass
    return max_n


def build_standalone_coverage(conn: sqlite3.Connection, *, verbose: bool = True) -> dict:
    """Populate auto_groups + auto_group_members for every uncovered party-side.

    Idempotent: only acts on party-sides not already in auto_group_members.
    """
    if verbose:
        print('  Stage A7 (standalone coverage): starting...', flush=True)

    # 1. Find every party-side currently in auto_group_members (the "covered" set)
    covered = set()
    for r in conn.execute(
        "SELECT source_id, side FROM auto_group_members WHERE member_type='party_side' AND source_id IS NOT NULL"
    ):
        covered.add((r['source_id'], r['side']))

    # 2. Build (legacy_group_id) -> [(source_id, side), ...] for every party-side via
    #    transaction_parties. We only care about parties that have a group_id set.
    legacy_to_parties: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for r in conn.execute(
        "SELECT source_id, side, group_id FROM transaction_parties WHERE group_id IS NOT NULL"
    ):
        legacy_to_parties[r['group_id']].append((r['source_id'], r['side']))

    # 3. Identify the dominant auto_group per legacy group (for partial-coverage handling).
    dominant_by_legacy: dict[str, str] = {}
    counts: dict[tuple[str, str], int] = defaultdict(int)
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

    # For each legacy group, pick the auto_group with the most members
    legacy_to_best: dict[str, tuple[str, int]] = {}
    for (lgid, agid), n in counts.items():
        if lgid not in legacy_to_best or n > legacy_to_best[lgid][1]:
            legacy_to_best[lgid] = (agid, n)
    dominant_by_legacy = {lgid: agid for lgid, (agid, _) in legacy_to_best.items()}

    # 4. Load legacy group metadata for entirely-uncovered groups
    legacy_meta: dict[str, dict] = {}
    for r in conn.execute(
        "SELECT id, normalized_name, display_name, status FROM groups"
    ):
        legacy_meta[r['id']] = {
            'normalized_name': r['normalized_name'],
            'display_name': r['display_name'],
            'status': r['status'],
        }

    next_id = _next_group_id_start(conn)
    standalones_created = 0
    party_sides_attached_to_dominant = 0
    party_sides_attached_to_new_standalone = 0
    legacy_groups_skipped_merged = 0
    anonymized_attached = 0

    # Anonymized bucket = (source_id, side) where the ENTIRE side carries no
    # identifying signal at all: no group_id'd entity row, no real party_name
    # (only empty strings or the literal "Named Individual(s)" marker RT writes
    # for suppressed identities), and no trade_name / care_of / companies_json
    # on the transactions row for that side. Any whisper of an entity (e.g. a
    # named LLC sister row, a trade_name, or a c/o routing) means the side has
    # an identity to follow and must not be swept here.
    ANONYMIZED_STEM = "_anonymized_individuals"
    ANONYMIZED_DISPLAY = "Named Individuals (anonymized)"

    anon_agid_row = conn.execute(
        "SELECT auto_group_id FROM auto_groups WHERE canonical_stem = ?",
        (ANONYMIZED_STEM,)
    ).fetchone()
    if anon_agid_row:
        anon_agid = anon_agid_row['auto_group_id']
    else:
        next_id += 1
        anon_agid = f'AGRP_{next_id:05d}'
        conn.execute(
            "INSERT INTO auto_groups "
            "(auto_group_id, canonical_stem, display_name, tier, confidence, n_anchors, n_members) "
            "VALUES (?, ?, ?, 'standalone', 0.0, 0, 0)",
            (anon_agid, ANONYMIZED_STEM, ANONYMIZED_DISPLAY),
        )

    anon_attachments: list[tuple] = []
    for r in conn.execute("""
        WITH side_signals AS (
            SELECT
                tp.source_id,
                tp.side,
                MAX(CASE WHEN tp.group_id IS NOT NULL THEN 1 ELSE 0 END) AS has_entity,
                MAX(CASE
                    WHEN tp.party_name IS NOT NULL
                     AND TRIM(tp.party_name) != ''
                     AND LOWER(TRIM(tp.party_name)) NOT LIKE '%named individual%'
                    THEN 1 ELSE 0
                END) AS has_real_name
            FROM transaction_parties tp
            GROUP BY tp.source_id, tp.side
        )
        SELECT ss.source_id, ss.side
        FROM side_signals ss
        JOIN transactions t ON t.source_id = ss.source_id
        WHERE ss.has_entity = 0
          AND ss.has_real_name = 0
          AND COALESCE(
                NULLIF(TRIM(CASE ss.side WHEN 'seller' THEN t.seller_trade_name
                                          WHEN 'buyer'  THEN t.buyer_trade_name END), ''),
                '') = ''
          AND COALESCE(
                NULLIF(TRIM(CASE ss.side WHEN 'seller' THEN t.seller_care_of
                                          WHEN 'buyer'  THEN t.buyer_care_of END), ''),
                '') = ''
          AND COALESCE(
                CASE ss.side WHEN 'seller' THEN t.seller_companies_json
                              WHEN 'buyer'  THEN t.buyer_companies_json END,
                '[]') IN ('[]', '')
    """):
        if (r['source_id'], r['side']) in covered:
            continue
        anon_attachments.append((anon_agid, 'party_side', r['source_id'], r['side'], None, 1.0))
        anonymized_attached += 1

    if anon_attachments:
        conn.executemany(
            "INSERT OR IGNORE INTO auto_group_members "
            "(auto_group_id, member_type, source_id, side, corp_name, match_score) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            anon_attachments,
        )
        # Mark these as covered so the standalone pass below doesn't double-process
        for _, _, sid, side, _, _ in anon_attachments:
            covered.add((sid, side))

    # 5. Walk each legacy group, decide what to do with its uncovered party-sides
    new_auto_groups: list[tuple] = []
    new_members: list[tuple] = []

    for lgid, parties in legacy_to_parties.items():
        uncovered = [(sid, side) for sid, side in parties if (sid, side) not in covered]
        if not uncovered:
            continue

        # Skip if the legacy group was merged (these are dead in the legacy system)
        meta = legacy_meta.get(lgid)
        if not meta or meta.get('status') == 'merged':
            legacy_groups_skipped_merged += 1
            continue

        if lgid in dominant_by_legacy:
            # Partial coverage: attach the leftovers to the dominant auto_group
            agid = dominant_by_legacy[lgid]
            for sid, side in uncovered:
                new_members.append((agid, 'party_side', sid, side, None, 1.0))
            party_sides_attached_to_dominant += len(uncovered)
        else:
            # No coverage: create a new standalone auto_group
            next_id += 1
            new_agid = f'AGRP_{next_id:05d}'
            new_auto_groups.append((
                new_agid,
                meta['normalized_name'],
                meta['display_name'],
                'standalone',
                0.0,
                0,
                len(uncovered),
            ))
            for sid, side in uncovered:
                new_members.append((new_agid, 'party_side', sid, side, None, 1.0))
            standalones_created += 1
            party_sides_attached_to_new_standalone += len(uncovered)

    # 6. Bulk insert
    if new_auto_groups:
        conn.executemany(
            "INSERT INTO auto_groups "
            "(auto_group_id, canonical_stem, display_name, tier, confidence, n_anchors, n_members) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            new_auto_groups,
        )
    if new_members:
        # INSERT OR IGNORE because a dominant-auto_group leftover might collide with an
        # idx_agm_party UNIQUE row from a prior force-attach during the same run.
        conn.executemany(
            "INSERT OR IGNORE INTO auto_group_members "
            "(auto_group_id, member_type, source_id, side, corp_name, match_score) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            new_members,
        )
    conn.commit()

    if verbose:
        print(
            f'  Stage A7 (standalone coverage): '
            f'{standalones_created:,} new standalone auto_groups, '
            f'{party_sides_attached_to_new_standalone:,} party-sides into standalones, '
            f'{party_sides_attached_to_dominant:,} party-sides into existing dominant groups, '
            f'{anonymized_attached:,} anonymized party-sides into placeholder bucket, '
            f'{legacy_groups_skipped_merged:,} merged legacy groups skipped.',
            flush=True,
        )

    return {
        'n_standalones_created': standalones_created,
        'n_party_sides_attached_to_dominant': party_sides_attached_to_dominant,
        'n_party_sides_attached_to_new_standalone': party_sides_attached_to_new_standalone,
        'n_anonymized_attached': anonymized_attached,
        'n_legacy_groups_skipped_merged': legacy_groups_skipped_merged,
    }
