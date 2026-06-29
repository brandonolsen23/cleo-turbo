"""Stage A1: Stem extraction with verified-promotion.

Picks the shortest-distinctive n-gram in each brand_phrase as the candidate
stem. Walk order: 1-gram (token-level distinctive flag) → 2-gram → 3-gram →
position-anchor 1-gram fallback. At each level the rarest (highest IDF) n-gram
wins.

This is the n-gram distinctiveness work. Generic words like "investments" no
longer become stems on their own; phrases like "Marlin Spring Investments Inc"
fall through 1-grams (all english-filtered) to find "marlin spring" as the
2-gram stem.
"""
from __future__ import annotations
import math
import sqlite3
from typing import Optional, Tuple

from cleo.discovery_v2.constants import (
    STEM_PROMOTION_DOMINANCE, STEM_PROMOTION_VOLUME,
    N_GRAM_GENERIC_THRESHOLD,
)


def _tokenize(phrase: str) -> list[str]:
    return [t for t in (phrase or '').split() if t]


def _candidate_from_tokens(
    tokens: list[str],
    token_info: dict[str, tuple[float, bool, bool]],
    bigram_lookup: dict[str, tuple[int, float]] | None = None,
    trigram_lookup: dict[str, tuple[int, float]] | None = None,
    defining_2g: set[str] | None = None,
    defining_3g: set[str] | None = None,
) -> Optional[Tuple[str, str]]:
    """Pick the best (stem, stem_type) for a brand_phrase given pre-loaded lookups.

    Priority order:
      0. User-declared defining_brand 3-gram or 2-gram present in the phrase
         (overrides 1-gram defaults — lets the user disambiguate "cadillac
         fairview" from a bare "fairview" 1-gram)
      1. Distinctive 1-gram (per brand_token_summary.is_distinctive) — pick
         highest IDF
      2. Distinctive 2-gram (n_distinct_phrases ≤ threshold) — LEFTMOST in the
         phrase, since brands sit before industry descriptors
      3. Distinctive 3-gram — same leftmost rule
      4. Position-anchor 1-gram fallback (e.g. "investments")
    Returns None if no candidate at any level.
    """
    if not tokens:
        return None

    # Level 0: user-declared defining-brand n-gram (3-gram > 2-gram > 1-gram order).
    # These override the level priority so "cadillac fairview" beats "fairview"
    # 1-gram on its own.
    if defining_3g and len(tokens) >= 3:
        for i in range(len(tokens) - 2):
            tg = ' '.join(tokens[i:i+3])
            if tg in defining_3g:
                return (tg, 'distinctive_3g')
    if defining_2g and len(tokens) >= 2:
        for i in range(len(tokens) - 1):
            bg = ' '.join(tokens[i:i+2])
            if bg in defining_2g:
                return (bg, 'distinctive_2g')

    # Level 1: distinctive 1-gram
    distinctive = [(t, token_info[t][0]) for t in tokens
                   if t in token_info and token_info[t][1]]
    if distinctive:
        token, _ = max(distinctive, key=lambda x: x[1])
        return (token, 'distinctive')

    # Level 2: distinctive 2-gram — LEFTMOST
    if bigram_lookup and len(tokens) >= 2:
        for i in range(len(tokens) - 1):
            bg = ' '.join(tokens[i:i+2])
            if bg in bigram_lookup:
                return (bg, 'distinctive_2g')

    # Level 3: distinctive 3-gram — LEFTMOST
    if trigram_lookup and len(tokens) >= 3:
        for i in range(len(tokens) - 2):
            tg = ' '.join(tokens[i:i+3])
            if tg in trigram_lookup:
                return (tg, 'distinctive_3g')

    # Fallback: position-anchor 1-gram (e.g. "investments")
    pa = [(t, token_info[t][0]) for t in tokens if t in token_info and token_info[t][2]]
    if pa:
        token, _ = max(pa, key=lambda x: x[1])
        return (token, 'position_anchor')

    return None


def _load_defining_ngrams(conn: sqlite3.Connection, level: str) -> set[str]:
    return {r[0] for r in conn.execute(
        "SELECT ngram FROM defining_brands WHERE level = ?", (level,)
    )}


def _load_bigram_lookup(conn: sqlite3.Connection) -> dict[str, tuple[int, float]]:
    """Load 2-grams that pass the generic threshold OR are user-declared
    defining_brands at the 2gram level. Defining brands override the threshold
    so users can pin specific multi-word brands (e.g. "standard life",
    "cadillac fairview") that fall outside the automatic gate."""
    threshold = N_GRAM_GENERIC_THRESHOLD.get(2, 10)
    lookup = {
        r['bigram']: (r['n_distinct_phrases'], r['idf'])
        for r in conn.execute(
            "SELECT bigram, n_distinct_phrases, idf FROM brand_bigram_summary "
            "WHERE n_distinct_phrases <= ?",
            (threshold,),
        )
    }
    for r in conn.execute(
        "SELECT b.ngram, COALESCE(s.n_distinct_phrases, 0) AS df, COALESCE(s.idf, 0.0) AS idf "
        "FROM defining_brands b "
        "LEFT JOIN brand_bigram_summary s ON s.bigram = b.ngram "
        "WHERE b.level = '2gram'"
    ):
        lookup[r['ngram']] = (r['df'], r['idf'])
    return lookup


def _load_trigram_lookup(conn: sqlite3.Connection) -> dict[str, tuple[int, float]]:
    threshold = N_GRAM_GENERIC_THRESHOLD.get(3, 5)
    lookup = {
        r['trigram']: (r['n_distinct_phrases'], r['idf'])
        for r in conn.execute(
            "SELECT trigram, n_distinct_phrases, idf FROM brand_trigram_summary "
            "WHERE n_distinct_phrases <= ?",
            (threshold,),
        )
    }
    for r in conn.execute(
        "SELECT b.ngram, COALESCE(s.n_distinct_phrases, 0) AS df, COALESCE(s.idf, 0.0) AS idf "
        "FROM defining_brands b "
        "LEFT JOIN brand_trigram_summary s ON s.trigram = b.ngram "
        "WHERE b.level = '3gram'"
    ):
        lookup[r['ngram']] = (r['df'], r['idf'])
    return lookup


def extract_candidate_stem(phrase: str, conn: sqlite3.Connection) -> Optional[Tuple[str, str]]:
    """Pick a candidate stem from a brand_phrase. Returns (stem, stem_type) or None.

    Convenience for callers that have a single phrase. For bulk use prefer
    `_candidate_from_tokens` with pre-loaded lookups.
    """
    token_info: dict[str, tuple[float, bool, bool]] = {
        r['token']: (r['idf'], bool(r['is_distinctive']), bool(r['is_pa']))
        for r in conn.execute(
            "SELECT token, idf, is_distinctive, "
            "       COALESCE(is_position_anchor, 0) AS is_pa "
            "FROM brand_token_summary"
        )
    }
    return _candidate_from_tokens(
        _tokenize(phrase),
        token_info,
        _load_bigram_lookup(conn),
        _load_trigram_lookup(conn),
        _load_defining_ngrams(conn, "2gram"),
        _load_defining_ngrams(conn, "3gram"),
    )


def build_stems(conn: sqlite3.Connection, *, verbose: bool = True) -> dict:
    """Run Stage A1 end-to-end. Idempotent — clears prior derived rows first.

    Returns a dict with summary counts: { 'n_stems', 'n_phrase_mappings' }.

    Note: brand_stem_phrase_map.confidence is pinned at 1.0 in Plan A.
    Plan B refines it once anti_evidence_ratio is available per stem.
    """
    conn.execute('DELETE FROM brand_stem')
    conn.execute('DELETE FROM brand_stem_phrase_map')

    # Step 1: collect every distinct brand_phrase + its candidate stem.
    # Pre-load token_info + bigram/trigram lookups once (three queries) instead
    # of one query per phrase.
    token_info: dict[str, tuple[float, bool, bool]] = {
        r['token']: (r['idf'], bool(r['is_distinctive']), bool(r['is_pa']))
        for r in conn.execute(
            "SELECT token, idf, is_distinctive, "
            "       COALESCE(is_position_anchor, 0) AS is_pa "
            "FROM brand_token_summary"
        )
    }
    bigram_lookup = _load_bigram_lookup(conn)
    trigram_lookup = _load_trigram_lookup(conn)
    defining_2g = _load_defining_ngrams(conn, "2gram")
    defining_3g = _load_defining_ngrams(conn, "3gram")
    if verbose:
        print(
            f'  Stage A1: token_info={len(token_info):,}, '
            f'bigram_lookup={len(bigram_lookup):,}, '
            f'trigram_lookup={len(trigram_lookup):,}, '
            f'defining 2g/3g={len(defining_2g)}/{len(defining_3g)}',
            flush=True,
        )

    phrases = [r['atom_value'] for r in conn.execute(
        "SELECT DISTINCT atom_value FROM party_atoms WHERE atom_type='brand_phrase'"
    )]
    phrase_to_candidate: dict[str, tuple[str, str]] = {}
    for ph in phrases:
        c = _candidate_from_tokens(_tokenize(ph), token_info,
                                    bigram_lookup, trigram_lookup,
                                    defining_2g, defining_3g)
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

    # Step 3: write phrase → stem map. PER-PHRASE ANCHOR CHECK — a phrase is
    # only mapped to a verified stem if at least one of the party-sides that
    # carries this phrase also carries the stem's dominant anchor (phone or
    # address_root). This is the structural fix for Issue #3: a stem like
    # "lorne" was getting promoted by the real Lorne Investments brand's
    # phone, then every "X Lorne Y" phrase (West Lorne towns, Lorne Avenue
    # streets, Lorne Brenneman given-name farms) rode along through blind
    # text-based mapping. The anchor check enforces "this phrase shares the
    # cluster's real-world signal," not just "this phrase contains the
    # candidate token."
    #
    # qualifying_source stems (management-company brands in trade_name /
    # care_of / companies_json) are exempt because they're already gated on
    # source-field selectivity + volume and don't have a strong single anchor.
    verified_anchor: dict[str, tuple[str, str] | None] = {}
    for stem, stem_type, atype, aval, dom, vol in promoted:
        verified_anchor[stem] = None if atype == 'qualifying_source' else (atype, aval)

    # Reverse phrase → sides map (built once from the side_phrases dict above)
    phrase_to_sides: dict[str, set] = {}
    for sk, phrases_list in side_phrases.items():
        for ph in phrases_list:
            phrase_to_sides.setdefault(ph, set()).add(sk)

    mappings = []
    filtered_phrases = 0
    for ph, (cand, _) in phrase_to_candidate.items():
        if cand not in verified_anchor:
            continue
        anchor = verified_anchor[cand]
        if anchor is None:
            # qualifying_source — keep broad mapping
            mappings.append((ph, cand, 1.0))
            continue
        # Strict: at least one of this phrase's party-sides must carry the
        # stem's dominant anchor value.
        atype, aval = anchor
        has_anchor = False
        for sk in phrase_to_sides.get(ph, ()):
            phone, addr_root = side_anchors.get(sk, (None, None))
            if atype == 'phone' and phone == aval:
                has_anchor = True
                break
            if atype == 'address_root' and addr_root == aval:
                has_anchor = True
                break
        if has_anchor:
            mappings.append((ph, cand, 1.0))
        else:
            filtered_phrases += 1

    if mappings:
        conn.executemany(
            "INSERT INTO brand_stem_phrase_map (phrase, stem, confidence) VALUES (?, ?, ?)",
            mappings,
        )

    conn.commit()
    if verbose:
        verified = set(verified_anchor.keys())
        print(f'  Stage A1 (stems): {len(verified):,} verified stems, '
              f'{len(mappings):,} phrase mappings ({filtered_phrases:,} filtered by '
              f'per-phrase anchor check).', flush=True)
    return {'n_stems': len(verified_anchor), 'n_phrase_mappings': len(mappings)}
