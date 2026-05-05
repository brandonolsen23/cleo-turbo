"""Stage A1: Stem extraction with verified-promotion."""
from __future__ import annotations
import math
import sqlite3
from typing import Optional, Tuple

from cleo.discovery_v2.constants import (
    STEM_PROMOTION_DOMINANCE, STEM_PROMOTION_VOLUME,
)


def _tokenize(phrase: str) -> list[str]:
    return [t for t in (phrase or '').split() if t]


def _candidate_from_tokens(
    tokens: list[str],
    token_info: dict[str, tuple[float, bool, bool]],
) -> Optional[Tuple[str, str]]:
    """Like extract_candidate_stem, but operates on a pre-loaded token_info dict.

    token_info: {token: (idf, is_distinctive, is_pa)}

    Returns (stem, stem_type) or None.
    """
    if not tokens:
        return None
    distinctive = [(t, token_info[t][0]) for t in tokens if t in token_info and token_info[t][1]]
    if distinctive:
        token, _ = max(distinctive, key=lambda x: x[1])
        return (token, 'distinctive')
    pa = [(t, token_info[t][0]) for t in tokens if t in token_info and token_info[t][2]]
    if pa:
        token, _ = max(pa, key=lambda x: x[1])
        return (token, 'position_anchor')
    return None


def extract_candidate_stem(phrase: str, conn: sqlite3.Connection) -> Optional[Tuple[str, str]]:
    """Pick a candidate stem from a brand_phrase. Returns (stem, stem_type) or None.

    Rule: highest-IDF distinctive 1-gram in the phrase. If none, fall back to
    the highest-position-rank PA 1-gram.

    NOTE: This function loads token_info from the DB on every call. For bulk use
    over many phrases, prefer building token_info once with a SELECT over
    brand_token_summary and calling _candidate_from_tokens() directly.
    """
    token_info: dict[str, tuple[float, bool, bool]] = {
        r['token']: (r['idf'], bool(r['is_distinctive']), bool(r['is_pa']))
        for r in conn.execute(
            "SELECT token, idf, is_distinctive, "
            "       COALESCE(is_position_anchor, 0) AS is_pa "
            "FROM brand_token_summary"
        )
    }
    return _candidate_from_tokens(_tokenize(phrase), token_info)


def build_stems(conn: sqlite3.Connection, *, verbose: bool = True) -> dict:
    """Run Stage A1 end-to-end. Idempotent — clears prior derived rows first.

    Returns a dict with summary counts: { 'n_stems', 'n_phrase_mappings' }.

    Note: brand_stem_phrase_map.confidence is pinned at 1.0 in Plan A.
    Plan B refines it once anti_evidence_ratio is available per stem.
    """
    conn.execute('DELETE FROM brand_stem')
    conn.execute('DELETE FROM brand_stem_phrase_map')

    # Step 1: collect every distinct brand_phrase + its candidate stem.
    # Pre-load token_info once (one query) instead of one query per phrase.
    token_info: dict[str, tuple[float, bool, bool]] = {
        r['token']: (r['idf'], bool(r['is_distinctive']), bool(r['is_pa']))
        for r in conn.execute(
            "SELECT token, idf, is_distinctive, "
            "       COALESCE(is_position_anchor, 0) AS is_pa "
            "FROM brand_token_summary"
        )
    }

    phrases = [r['atom_value'] for r in conn.execute(
        "SELECT DISTINCT atom_value FROM party_atoms WHERE atom_type='brand_phrase'"
    )]
    phrase_to_candidate: dict[str, tuple[str, str]] = {}
    for ph in phrases:
        c = _candidate_from_tokens(_tokenize(ph), token_info)
        if c is not None:
            phrase_to_candidate[ph] = c

    # Step 2: for each candidate stem, find dominant anchor + dominance_share.
    # Replaced per-stem loop (N×2 heavy SQL joins) with 4 bulk queries + pure-Python
    # aggregation. Semantics: each party-side contributes its anchor counts to EVERY
    # candidate stem on that side (multi-stem sides are real — JV transactions,
    # multi-firm contacts — and every stem deserves credit for promotion).
    candidate_stems = {c[0]: c[1] for c in phrase_to_candidate.values()}

    # --- Pre-computation pass A: side → set of stems ---
    # Pull every (source_id, side, atom_value) row for brand_phrase atoms in one query.
    side_phrases: dict[tuple[str, str], list[str]] = {}
    for r in conn.execute(
        "SELECT source_id, side, atom_value FROM party_atoms WHERE atom_type='brand_phrase'"
    ):
        sk = (r['source_id'], r['side'])
        side_phrases.setdefault(sk, []).append(r['atom_value'])

    # For each side, collect ALL candidate stems present — both stems on a side
    # are real signals (JV transactions, multi-firm contacts) and each deserves
    # credit toward its own dominance score.  Picking one dominant stem and
    # discarding the rest silently drops evidence.
    side_to_stems: dict[tuple[str, str], set[str]] = {}
    for sk, phrases_list in side_phrases.items():
        stems: set[str] = set()
        for ph in phrases_list:
            c = phrase_to_candidate.get(ph)
            if c is not None:
                stems.add(c[0])
        if stems:
            side_to_stems[sk] = stems

    # --- Pre-computation pass B: side → anchors ---
    # One query for all phone + address_root values per (source_id, side).
    side_anchors: dict[tuple[str, str], tuple[str | None, str | None]] = {}
    for r in conn.execute(
        "SELECT source_id, side, phone, street_number, street_name FROM party_fingerprints"
    ):
        sk = (r['source_id'], r['side'])
        phone = r['phone'] if r['phone'] else None
        addr_root = (
            f"{r['street_number']}|{r['street_name']}"
            if r['street_number'] and r['street_name'] else None
        )
        side_anchors[sk] = (phone, addr_root)

    # --- Pre-computation pass C: anchor total volumes ---
    phone_total: dict[str, int] = dict(conn.execute(
        "SELECT phone, COUNT(*) FROM party_fingerprints "
        "WHERE phone IS NOT NULL AND phone != '' GROUP BY phone"
    ).fetchall())

    addr_total: dict[str, int] = dict(conn.execute(
        "SELECT (street_number || '|' || street_name) AS k, COUNT(*) "
        "FROM party_fingerprints "
        "WHERE street_number IS NOT NULL AND street_number != '' "
        "  AND street_name IS NOT NULL AND street_name != '' "
        "GROUP BY street_number, street_name"
    ).fetchall())

    # --- Aggregation: build per-stem anchor counts in one Python pass ---
    phone_count_by_stem: dict[str, dict[str, int]] = {}   # stem → phone → count
    addr_count_by_stem: dict[str, dict[str, int]] = {}    # stem → addr_root → count

    for sk, stems in side_to_stems.items():
        phone, addr_root = side_anchors.get(sk, (None, None))
        for stem in stems:
            if phone is not None:
                d = phone_count_by_stem.setdefault(stem, {})
                d[phone] = d.get(phone, 0) + 1
            if addr_root is not None:
                d = addr_count_by_stem.setdefault(stem, {})
                d[addr_root] = d.get(addr_root, 0) + 1

    # --- Per-stem dominance scoring (pure Python, no SQL) ---
    promoted: list[tuple] = []
    for stem, stem_type in candidate_stems.items():
        candidates = []

        # Best phone for this stem
        phone_map = phone_count_by_stem.get(stem)
        if phone_map:
            anchor, sides_with_stem = max(phone_map.items(), key=lambda kv: kv[1])
            total = phone_total.get(anchor, 0)
            if total > 0:
                d = sides_with_stem / total
                candidates.append(('phone', anchor, d, total))

        # Best address_root for this stem
        addr_map = addr_count_by_stem.get(stem)
        if addr_map:
            anchor, sides_with_stem = max(addr_map.items(), key=lambda kv: kv[1])
            total = addr_total.get(anchor, 0)
            if total > 0:
                d = sides_with_stem / total
                candidates.append(('address_root', anchor, d, total))

        if not candidates:
            continue

        atype, aval, dom, vol = max(candidates, key=lambda c: c[2] * math.log(c[3] + 1))

        if dom >= STEM_PROMOTION_DOMINANCE and vol >= STEM_PROMOTION_VOLUME:
            promoted.append((stem, stem_type, atype, aval, dom, vol))

    # --- Second promotion path: qualifying-source-field volume ---
    # Management-company brands (trade_name / care_of / companies_json) often
    # operate from shared office buildings, so they never dominate any single
    # anchor.  But by spec those three fields are exactly where management-
    # company names live.  If a candidate stem appears as the candidate for a
    # brand_phrase that recurs in those fields on >= STEM_PROMOTION_VOLUME
    # distinct party-sides corpus-wide, promote it regardless of anchor dominance.
    QUALIFYING_SOURCE_FIELDS = ('trade_name', 'care_of', 'companies_json')
    already_promoted_stems = {row[0] for row in promoted}

    stem_qualifying_sides: dict[str, set] = {}
    for r in conn.execute(
        f"""SELECT pa.atom_value AS phrase, pa.source_id, pa.side
            FROM party_atoms pa
            WHERE pa.atom_type = 'brand_phrase'
              AND pa.source_field IN ({','.join('?' * len(QUALIFYING_SOURCE_FIELDS))})""",
        QUALIFYING_SOURCE_FIELDS,
    ):
        cand = phrase_to_candidate.get(r['phrase'])
        if cand is None:
            continue
        stem = cand[0]
        if stem in already_promoted_stems:
            continue
        stem_qualifying_sides.setdefault(stem, set()).add((r['source_id'], r['side']))

    for stem, sides in stem_qualifying_sides.items():
        if len(sides) >= STEM_PROMOTION_VOLUME:
            stem_type = candidate_stems[stem]
            promoted.append((stem, stem_type, 'qualifying_source', '', 1.0, len(sides)))

    if promoted:
        conn.executemany(
            """INSERT INTO brand_stem
                 (stem, stem_type, dominant_anchor_type, dominant_anchor_value,
                  dominance_share, volume)
               VALUES (?, ?, ?, ?, ?, ?)""",
            promoted,
        )

    # Step 3: write phrase → stem map (only phrases whose candidate was promoted)
    verified = {row[0] for row in promoted}
    mappings = []
    for ph, (cand, _) in phrase_to_candidate.items():
        if cand in verified:
            mappings.append((ph, cand, 1.0))  # confidence = 1.0 placeholder for Plan A
    if mappings:
        conn.executemany(
            "INSERT INTO brand_stem_phrase_map (phrase, stem, confidence) VALUES (?, ?, ?)",
            mappings,
        )

    conn.commit()
    if verbose:
        print(f'  Stage A1 (stems): {len(verified):,} verified stems, '
              f'{len(mappings):,} phrase mappings.', flush=True)
    return {'n_stems': len(verified), 'n_phrase_mappings': len(mappings)}
