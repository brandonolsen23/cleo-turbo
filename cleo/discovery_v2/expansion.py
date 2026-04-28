"""Stage A4: Group expansion — attach party-sides + numbered-corps to seeded groups."""
from __future__ import annotations
import re
import sqlite3

from cleo.discovery_v2.constants import (
    MATCH_SCORE_DIRECT_STEM_HIT,
    MATCH_SCORE_PHONE_MATCH,
    MATCH_SCORE_ADDRESS_PLUS_CONTACT,
    MATCH_SCORE_ADDRESS_ROOT_ALONE,
    MATCH_SCORE_PHONE_BRAND_CONTRADICTION,
    MATCH_SCORE_SINGLE_WEAK_SIGNAL,
    EXPANSION_ATTACH_THRESHOLD,
)


_NUMBERED_CORP_RE = re.compile(r'^\d+\s+(ontario|canada|alberta|bc|quebec)\b', re.I)


def build_expansion(conn: sqlite3.Connection, *, verbose: bool = True) -> dict:
    """Attach party-sides and numbered corps to seeded groups. Idempotent."""
    conn.execute('DELETE FROM auto_group_members')

    # 1. Pull every group's anchors into in-memory lookup tables for cheap matching
    groups = list(conn.execute('SELECT auto_group_id, canonical_stem FROM auto_groups'))
    if not groups:
        if verbose:
            print('  Stage A4 (expansion): no groups to expand.', flush=True)
        return {'n_party_side_members': 0, 'n_numbered_corp_members': 0}

    anchors_by_group = {}  # group_id -> {(type, value): score}
    for r in conn.execute('SELECT * FROM auto_group_anchors'):
        anchors_by_group.setdefault(r['auto_group_id'], {})[
            (r['anchor_type'], r['anchor_value'])
        ] = r['score']

    # 2. For each party-side, look up its anchor values + its stems
    side_data = {}  # (sid, side) -> { 'phone', 'addr_root', 'addr_base', 'contact', 'stems' }
    for r in conn.execute("""
        SELECT source_id, side, phone, contact_fingerprint,
               street_number, street_name, street_suffix
        FROM party_fingerprints
    """):
        addr_root = (
            f"{r['street_number']}|{r['street_name']}"
            if r['street_number'] and r['street_name'] else None
        )
        addr_base = (
            f"{r['street_number']}|{r['street_name']}|{r['street_suffix'] or ''}"
            if r['street_number'] and r['street_name'] else None
        )
        side_data[(r['source_id'], r['side'])] = {
            'phone':     r['phone'] or None,
            'addr_root': addr_root,
            'addr_base': addr_base,
            'contact':   r['contact_fingerprint'] or None,
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
    member_rows = []
    numbered_corps = []  # (group_id, corp_name, match_score)
    for (sid, side), info in side_data.items():
        for group_id, _stem in groups:
            anchors = anchors_by_group.get(group_id, {})
            if not anchors:
                continue
            score = _score_match(info, anchors, group_canonical_stem=_stem)
            if score >= EXPANSION_ATTACH_THRESHOLD:
                member_rows.append((group_id, 'party_side', sid, side, None, score))
                # Numbered-corp side-effect: any numbered corp phrase on this side
                # gets recorded as a group-owned vehicle.
                for ph in info['phrases']:
                    if _NUMBERED_CORP_RE.match(ph or ''):
                        numbered_corps.append((group_id, ph.lower(), score))

    if member_rows:
        conn.executemany(
            """INSERT INTO auto_group_members
                 (auto_group_id, member_type, source_id, side, corp_name, match_score)
               VALUES (?, ?, ?, ?, ?, ?)""",
            member_rows,
        )

    # Dedupe numbered_corps before insert (same corp_name in many sides → one row per group)
    seen = set()
    corp_rows = []
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

    conn.commit()
    if verbose:
        print(
            f'  Stage A4 (expansion): {len(member_rows):,} party-sides, '
            f'{len(corp_rows):,} numbered-corp memberships.',
            flush=True,
        )
    return {
        'n_party_side_members': len(member_rows),
        'n_numbered_corp_members': len(corp_rows),
    }


def _score_match(info: dict, anchors: dict, *, group_canonical_stem: str) -> float:
    """Score a single (party-side, group) pair using constants.py rules."""
    score = 0.0
    has_phone_match = ('phone', info['phone']) in anchors if info['phone'] else False
    has_addr_match = (
        ('address_root', info['addr_root']) in anchors if info['addr_root'] else False
    ) or (
        ('address_base', info['addr_base']) in anchors if info['addr_base'] else False
    )
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

    if has_addr_match and has_contact_match:
        score = max(score, MATCH_SCORE_ADDRESS_PLUS_CONTACT)
    elif has_addr_match:
        score = max(score, MATCH_SCORE_ADDRESS_ROOT_ALONE)

    # Single weak signal (only contact, common name) caps at 0.3
    if has_contact_match and not (has_phone_match or has_addr_match or has_direct_stem):
        score = max(score, MATCH_SCORE_SINGLE_WEAK_SIGNAL)

    return score
