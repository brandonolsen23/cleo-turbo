"""Stage A4: Group expansion — attach party-sides + numbered-corps to seeded groups.

H2 update: time-aware expansion. A party with a sale_date is only attached to
group G if at least one of its anchors (phone / address_unit / contact) has a
tenure in G whose window contains the party's sale_date.

Backward compat: parties with NO sale_date fall back to the H1 anchor-only
scoring path (no tenure gating) so that undated parties don't orphan en masse.
"""
from __future__ import annotations
import re
import sqlite3

from cleo.discovery_v2.constants import (
    MATCH_SCORE_DIRECT_STEM_HIT,
    MATCH_SCORE_PHONE_MATCH,
    MATCH_SCORE_ADDRESS_PLUS_CONTACT,
    MATCH_SCORE_ADDRESS_UNIT_ALONE,
    MATCH_SCORE_PHONE_BRAND_CONTRADICTION,
    MATCH_SCORE_SINGLE_WEAK_SIGNAL,
    EXPANSION_ATTACH_THRESHOLD,
)


_NUMBERED_CORP_RE = re.compile(r'^\d+\s+(ontario|canada|alberta|bc|quebec)\b', re.I)


def _ensure_defining_brand_auto_groups(conn: sqlite3.Connection, *, verbose: bool) -> int:
    """Ensure every defining_brands canonical_stem has an auto_group row.

    Defining-brand rules are user-asserted ground truth — they always have
    confidence=1.0 and tier='confirmed'. If seeding didn't already create an
    auto_group for the stem (e.g. because the stem had thin anchor evidence),
    we create one here so expansion has somewhere to attach members.
    """
    try:
        rules = list(conn.execute(
            "SELECT canonical_stem, COALESCE(canonical_name, canonical_stem) AS display_name "
            "FROM defining_brands "
            "WHERE canonical_stem IS NOT NULL "
            "GROUP BY canonical_stem"
        ))
    except sqlite3.OperationalError:
        return 0

    if not rules:
        return 0

    existing_stems = {
        r['canonical_stem']
        for r in conn.execute("SELECT DISTINCT canonical_stem FROM auto_groups")
    }

    # Compute next AGRP_NNNNN id by scanning existing
    max_n = 0
    for r in conn.execute("SELECT auto_group_id FROM auto_groups WHERE auto_group_id LIKE 'AGRP_%'"):
        try:
            n = int(r['auto_group_id'].split('_', 1)[1])
            if n > max_n:
                max_n = n
        except (ValueError, IndexError):
            pass

    created = 0
    for rule in rules:
        stem = rule['canonical_stem']
        if stem in existing_stems:
            continue
        max_n += 1
        new_id = f"AGRP_{max_n:05d}"
        conn.execute(
            "INSERT INTO auto_groups "
            "(auto_group_id, canonical_stem, display_name, tier, confidence, n_anchors, n_members) "
            "VALUES (?, ?, ?, 'confirmed', 1.0, 0, 0)",
            (new_id, stem, rule['display_name']),
        )
        existing_stems.add(stem)
        created += 1

    conn.commit()
    if verbose and created:
        print(f"  Stage A4-pre (defining-brand stems): created {created} auto_groups", flush=True)
    return created


def _force_attach_defining_brands(conn: sqlite3.Connection, *, verbose: bool) -> int:
    """Force-attach party-sides matching a defining_brands rule to the rule's
    canonical_stem auto_group. Bypasses anchor scoring entirely — this is
    user-asserted ground truth.

    Returns the number of party-sides force-attached.
    """
    try:
        rules = list(conn.execute(
            "SELECT ngram, level, canonical_stem "
            "FROM defining_brands "
            "WHERE canonical_stem IS NOT NULL"
        ))
    except sqlite3.OperationalError:
        return 0

    if not rules:
        return 0

    # Map canonical_stem → auto_group_id (pick first one if multiple share a stem;
    # _ensure_defining_brand_auto_groups guarantees at least one exists).
    stem_to_group: dict[str, str] = {}
    for r in conn.execute("SELECT auto_group_id, canonical_stem FROM auto_groups"):
        stem_to_group.setdefault(r['canonical_stem'], r['auto_group_id'])

    # Level → (table, column) for ngram match
    LEVEL_TABLE = {
        '1gram': ('brand_token_index', 'token'),
        '2gram': ('brand_bigram_index', 'bigram'),
        '3gram': ('brand_trigram_index', 'trigram'),
        '4gram': ('brand_fourgram_index', 'fourgram'),
        '5gram': ('brand_fivegram_index', 'fivegram'),
    }

    total_attached = 0
    rules_applied = 0

    for rule in rules:
        stem = rule['canonical_stem']
        level = rule['level']
        ngram = rule['ngram']

        gid = stem_to_group.get(stem)
        if not gid:
            continue

        if level not in LEVEL_TABLE:
            # long-form (6+) not supported here; would need different lookup
            continue

        table, col = LEVEL_TABLE[level]
        rows = conn.execute(
            f"SELECT source_id, side FROM {table} WHERE {col} = ?",
            (ngram,),
        ).fetchall()

        if not rows:
            continue

        # Use INSERT OR IGNORE so we don't conflict with the regular
        # expansion's later inserts (idx_agm_party is UNIQUE on
        # (auto_group_id, source_id, side) for party_side rows).
        conn.executemany(
            "INSERT OR IGNORE INTO auto_group_members "
            "(auto_group_id, member_type, source_id, side, corp_name, match_score) "
            "VALUES (?, 'party_side', ?, ?, NULL, 1.0)",
            [(gid, r['source_id'], r['side']) for r in rows],
        )
        total_attached += len(rows)
        rules_applied += 1

    conn.commit()
    if verbose:
        print(
            f"  Stage A4-pre (defining-brand force-attach): "
            f"{rules_applied} rules applied, {total_attached:,} party-sides attached",
            flush=True,
        )
    return total_attached


def build_expansion(conn: sqlite3.Connection, *, verbose: bool = True) -> dict:
    """Attach party-sides and numbered corps to seeded groups. Idempotent."""
    conn.execute('DELETE FROM auto_group_members')
    conn.execute('DELETE FROM auto_conflict_flags')

    # Path 2: user-asserted defining-brand rules. Run BEFORE normal expansion so
    # these attachments survive any anchor-score gating. Direct attaches happen
    # at match_score=1.0; later expansion may add MORE attachments (e.g. JV
    # co-investors) but won't conflict because of UNIQUE constraint.
    _ensure_defining_brand_auto_groups(conn, verbose=verbose)
    _force_attach_defining_brands(conn, verbose=verbose)

    # 1. Pull every group's canonical stem
    groups = list(conn.execute('SELECT auto_group_id, canonical_stem FROM auto_groups'))
    if not groups:
        if verbose:
            print('  Stage A4 (expansion): no groups to expand.', flush=True)
        return {'n_party_side_members': 0, 'n_numbered_corp_members': 0,
                'n_expansion_conflicts': 0}

    # H2: Load tenures — one lookup row per (anchor_type, anchor_value).
    # A tenure window contains sale_date D iff start_date <= D <= COALESCE(end_date, '9999-12-31').
    tenures_by_anchor: dict[tuple[str, str], list[tuple]] = {}
    for r in conn.execute(
        "SELECT auto_group_id, anchor_type, anchor_value, "
        "       start_date, end_date, score "
        "FROM auto_group_anchor_tenures"
    ):
        key = (r['anchor_type'], r['anchor_value'])
        tenures_by_anchor.setdefault(key, []).append((
            r['auto_group_id'], r['start_date'], r['end_date'], r['score'],
        ))

    # H1-compat: static anchors per group (for the no-sale_date fallback path).
    anchors_by_group: dict[str, dict] = {}
    for r in conn.execute('SELECT * FROM auto_group_anchors'):
        anchors_by_group.setdefault(r['auto_group_id'], {})[
            (r['anchor_type'], r['anchor_value'])
        ] = r['score']

    # 2. For each party-side, look up its anchor values + its stems
    side_data: dict[tuple, dict] = {}  # (sid, side) -> info dict
    for r in conn.execute("""
        SELECT source_id, side, phone, contact_fingerprint,
               party_address_canonical, sale_date,
               city, street_number, street_name
        FROM party_fingerprints
    """):
        addr_unit = (
            r['party_address_canonical']
            if r['city'] and r['street_number'] and r['street_name']
            else None
        )
        side_data[(r['source_id'], r['side'])] = {
            'phone':     r['phone'] or None,
            'addr_unit': addr_unit,
            'contact':   r['contact_fingerprint'] or None,
            'sale_date': r['sale_date'] or None,
            'stems':     set(),
            'phrases':   [],
        }

    for r in conn.execute("""
        SELECT pa.source_id, pa.side, pa.atom_value, m.stem
        FROM party_atoms pa
        LEFT JOIN brand_stem_phrase_map m ON m.phrase = pa.atom_value
        WHERE pa.atom_type='brand_phrase'
    """):
        key = (r['source_id'], r['side'])
        if key in side_data:
            if r['stem']:
                side_data[key]['stems'].add(r['stem'])
            side_data[key]['phrases'].append(r['atom_value'])

    # 3. Score each party-side against each group it touches
    member_rows: list[tuple] = []
    numbered_corps: list[tuple] = []   # (group_id, corp_name, match_score)
    conflict_rows: list[tuple] = []    # values for auto_conflict_flags insert

    for (sid, side), info in side_data.items():
        sale_date = info['sale_date']

        # Identify groups where this side has a direct stem hit (brand phrase → stem → group).
        # Direct stem hits are always considered, regardless of tenure windows.
        direct_group_ids: set[str] = set()
        for group_id, gstem in groups:
            if gstem in info['stems']:
                direct_group_ids.add(group_id)

        # ── H1 FALLBACK: no sale_date ──────────────────────────────────────
        if sale_date is None:
            for group_id, _stem in groups:
                anchors = anchors_by_group.get(group_id, {})
                if not anchors:
                    continue
                score = _score_match(info, anchors, group_canonical_stem=_stem)
                if score >= EXPANSION_ATTACH_THRESHOLD:
                    member_rows.append((group_id, 'party_side', sid, side, None, score))
                    for ph in info['phrases']:
                        if _NUMBERED_CORP_RE.match(ph or ''):
                            numbered_corps.append((group_id, ph.lower(), score))
            continue

        # ── H2 TIME-AWARE PATH ─────────────────────────────────────────────
        # Build candidate_groups: group_id → {anchors filtered to tenure-containing rows}
        candidate_groups: dict[str, dict] = {}
        saw_contact_anchor = False

        for atype, aval in (
            ('phone',        info['phone']),
            ('address_unit', info['addr_unit']),
            ('contact',      info['contact']),
        ):
            if not aval:
                continue
            for gid, t_start, t_end, anchor_score in tenures_by_anchor.get((atype, aval), []):
                t_end_eff = t_end if t_end is not None else '9999-12-31'
                if t_start <= sale_date <= t_end_eff:
                    rec = candidate_groups.setdefault(gid, {'anchors': {}})
                    rec['anchors'][(atype, aval)] = anchor_score
                    if atype == 'contact':
                        saw_contact_anchor = True

        # Promote direct-stem-hit groups as candidates (they bypass tenure gating).
        for group_id in direct_group_ids:
            candidate_groups.setdefault(group_id, {'anchors': {}})

        if not candidate_groups:
            continue  # orphan — no tenure window match and no direct stem hit

        if len(candidate_groups) == 1:
            gid, cdata = next(iter(candidate_groups.items()))
            # Use H1 _score_match. Prefer tenured anchors; fall back to static anchors
            # if this group was promoted purely via direct-stem (empty tenured anchors).
            anchors_for_score = cdata['anchors'] or anchors_by_group.get(gid, {})
            gstem = next((s for g, s in groups if g == gid), None)
            score = _score_match(info, anchors_for_score, group_canonical_stem=gstem)
            if score >= EXPANSION_ATTACH_THRESHOLD:
                member_rows.append((gid, 'party_side', sid, side, None, score))
                for ph in info['phrases']:
                    if _NUMBERED_CORP_RE.match(ph or ''):
                        numbered_corps.append((gid, ph.lower(), score))
        else:
            # Multiple groups claim this anchor on this date — emit conflict flag.
            # Do NOT attach.
            sorted_gids = sorted(candidate_groups.keys())
            conflict_type = 'contact_overlap' if saw_contact_anchor else 'anchor_reassignment'
            conflict_rows.append((
                conflict_type,
                'anchor',
                f'{sid}|{side}',
                None,
                sorted_gids[0],
                sorted_gids[1] if len(sorted_gids) > 1 else None,
                sale_date,
                (
                    f'Party {sid}/{side} on {sale_date} matches '
                    f'{len(candidate_groups)} groups via anchor tenures.'
                ),
            ))

    # Insert party-side members.
    # OR IGNORE because the defining-brand force-attach pass (run earlier in
    # this same function) may have already attached some of these rows; the
    # UNIQUE constraint on (auto_group_id, source_id, side) for party_side rows
    # makes that a no-op rather than a crash.
    if member_rows:
        conn.executemany(
            """INSERT OR IGNORE INTO auto_group_members
                 (auto_group_id, member_type, source_id, side, corp_name, match_score)
               VALUES (?, ?, ?, ?, ?, ?)""",
            member_rows,
        )

    # Dedupe numbered_corps before insert (same corp_name in many sides → one row per group)
    seen: set[tuple] = set()
    corp_rows: list[tuple] = []
    for gid, corp_name, sc in numbered_corps:
        key = (gid, corp_name)
        if key in seen:
            continue
        seen.add(key)
        corp_rows.append((gid, 'numbered_corp', None, None, corp_name, sc))

    if corp_rows:
        conn.executemany(
            """INSERT INTO auto_group_members
                 (auto_group_id, member_type, source_id, side, corp_name, match_score)
               VALUES (?, ?, ?, ?, ?, ?)""",
            corp_rows,
        )

    # Insert conflict flags
    if conflict_rows:
        conn.executemany(
            """INSERT INTO auto_conflict_flags
                (conflict_type, entity_type, entity_value, entity_subtype,
                 group_a, group_b, date_observed, description)
              VALUES (?,?,?,?,?,?,?,?)""",
            conflict_rows,
        )

    conn.commit()
    if verbose:
        print(
            f'  Stage A4 (expansion): {len(member_rows):,} party-sides, '
            f'{len(corp_rows):,} numbered-corp memberships, '
            f'{len(conflict_rows):,} conflicts.',
            flush=True,
        )
    return {
        'n_party_side_members': len(member_rows),
        'n_numbered_corp_members': len(corp_rows),
        'n_expansion_conflicts': len(conflict_rows),
    }


def _score_match(info: dict, anchors: dict, *, group_canonical_stem: str) -> float:
    """Score a single (party-side, group) pair using constants.py rules."""
    score = 0.0
    has_phone_match = ('phone', info['phone']) in anchors if info['phone'] else False
    has_unit_match = ('address_unit', info['addr_unit']) in anchors if info['addr_unit'] else False
    has_contact_match = ('contact', info['contact']) in anchors if info['contact'] else False
    has_direct_stem = group_canonical_stem in info['stems']

    # Strong: direct stem hit
    if has_direct_stem:
        score = max(score, MATCH_SCORE_DIRECT_STEM_HIT)

    # Phone match — but only if no contradicting stem on the side
    if has_phone_match:
        contradicting = info['stems'] - {group_canonical_stem}
        if contradicting:
            return MATCH_SCORE_PHONE_BRAND_CONTRADICTION  # explicit do-not-attach
        score = max(score, MATCH_SCORE_PHONE_MATCH)

    if has_unit_match and has_contact_match:
        score = max(score, MATCH_SCORE_ADDRESS_PLUS_CONTACT)
    elif has_unit_match:
        score = max(score, MATCH_SCORE_ADDRESS_UNIT_ALONE)

    # Single weak signal: contact only, common-name risk
    if has_contact_match and not (has_phone_match or has_unit_match or has_direct_stem):
        score = max(score, MATCH_SCORE_SINGLE_WEAK_SIGNAL)

    # No-anchor party with no stem hit and no phone/unit/contact → 0.0 (don't attach).
    # This is the TD Bank case: address_root would have matched in the old algorithm,
    # but address_root is no longer a Layer 2 anchor.
    return score
