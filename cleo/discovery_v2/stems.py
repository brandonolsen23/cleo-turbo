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


def extract_candidate_stem(phrase: str, conn: sqlite3.Connection) -> Optional[Tuple[str, str]]:
    """Pick a candidate stem from a brand_phrase. Returns (stem, stem_type) or None.

    Rule: highest-IDF distinctive 1-gram in the phrase. If none, fall back to
    the highest-position-rank PA 1-gram.
    """
    tokens = _tokenize(phrase)
    if not tokens:
        return None
    placeholders = ','.join(['?'] * len(tokens))
    rows = conn.execute(
        f"""SELECT token, idf, is_distinctive,
                   COALESCE(is_position_anchor, 0) AS is_pa
           FROM brand_token_summary
           WHERE token IN ({placeholders})""",
        tokens,
    ).fetchall()
    distinctive = [(r['token'], r['idf']) for r in rows if r['is_distinctive']]
    if distinctive:
        token, _ = max(distinctive, key=lambda x: x[1])
        return (token, 'distinctive')
    pa = [(r['token'], r['idf']) for r in rows if r['is_pa']]
    if pa:
        token, _ = max(pa, key=lambda x: x[1])
        return (token, 'position_anchor')
    return None


def build_stems(conn: sqlite3.Connection, *, verbose: bool = True) -> dict:
    """Run Stage A1 end-to-end. Idempotent — clears prior derived rows first.

    Returns a dict with summary counts: { 'n_stems', 'n_phrase_mappings' }.

    Note: brand_stem_phrase_map.confidence is pinned at 1.0 in Plan A.
    Plan B refines it once anti_evidence_ratio is available per stem.
    """
    conn.execute('DELETE FROM brand_stem')
    conn.execute('DELETE FROM brand_stem_phrase_map')

    # Step 1: collect every distinct brand_phrase + its candidate stem
    phrases = [r['atom_value'] for r in conn.execute(
        "SELECT DISTINCT atom_value FROM party_atoms WHERE atom_type='brand_phrase'"
    )]
    phrase_to_candidate: dict[str, tuple[str, str]] = {}
    for ph in phrases:
        c = extract_candidate_stem(ph, conn)
        if c is not None:
            phrase_to_candidate[ph] = c

    # Step 2: for each candidate stem, find dominant anchor + dominance_share
    # Score stems against both phone and address_root anchors. The picker uses
    # dominance × log(volume + 1) — same formula as Stage A2's anchor score —
    # which correctly prefers a 5-volume @ 0.9 dominance over a 100-volume @ 0.5.
    candidate_stems = {c[0]: c[1] for c in phrase_to_candidate.values()}

    promoted: list[tuple] = []  # rows for brand_stem
    for stem, stem_type in candidate_stems.items():
        # Pull all party-sides whose phrases contain this stem candidate
        stem_phrases = [ph for ph, c in phrase_to_candidate.items() if c[0] == stem]
        if not stem_phrases:
            continue

        # Dominance against phone anchor
        phone_row = conn.execute(
            f"""WITH stem_sides AS (
                    SELECT DISTINCT pa.source_id, pa.side
                    FROM party_atoms pa
                    WHERE pa.atom_type='brand_phrase'
                      AND pa.atom_value IN ({','.join(['?']*len(stem_phrases))})
                )
                SELECT pf.phone AS anchor,
                       COUNT(*) AS sides_with_stem,
                       (SELECT COUNT(*) FROM party_fingerprints pf2
                          WHERE pf2.phone = pf.phone) AS total_at_anchor
                FROM stem_sides s
                JOIN party_fingerprints pf
                  ON pf.source_id=s.source_id AND pf.side=s.side
                WHERE pf.phone IS NOT NULL AND pf.phone != ''
                GROUP BY pf.phone
                ORDER BY sides_with_stem DESC
                LIMIT 1""",
            stem_phrases,
        ).fetchone()
        # Dominance against address_root anchor
        addr_row = conn.execute(
            f"""WITH stem_sides AS (
                    SELECT DISTINCT pa.source_id, pa.side
                    FROM party_atoms pa
                    WHERE pa.atom_type='brand_phrase'
                      AND pa.atom_value IN ({','.join(['?']*len(stem_phrases))})
                )
                SELECT (pf.street_number || '|' || pf.street_name) AS anchor,
                       COUNT(*) AS sides_with_stem,
                       (SELECT COUNT(*) FROM party_fingerprints pf2
                          WHERE pf2.street_number=pf.street_number
                            AND pf2.street_name=pf.street_name) AS total_at_anchor
                FROM stem_sides s
                JOIN party_fingerprints pf
                  ON pf.source_id=s.source_id AND pf.side=s.side
                WHERE pf.street_number != '' AND pf.street_name != ''
                  AND pf.street_number IS NOT NULL AND pf.street_name IS NOT NULL
                GROUP BY pf.street_number, pf.street_name
                ORDER BY sides_with_stem DESC
                LIMIT 1""",
            stem_phrases,
        ).fetchone()

        # Pick the better of phone vs address_root
        candidates = []
        if phone_row and phone_row['total_at_anchor'] > 0:
            d = phone_row['sides_with_stem'] / phone_row['total_at_anchor']
            candidates.append(('phone', phone_row['anchor'], d, phone_row['total_at_anchor']))
        if addr_row and addr_row['total_at_anchor'] > 0:
            d = addr_row['sides_with_stem'] / addr_row['total_at_anchor']
            candidates.append(('address_root', addr_row['anchor'], d, addr_row['total_at_anchor']))
        if not candidates:
            continue
        atype, aval, dom, vol = max(candidates, key=lambda c: c[2] * math.log(c[3] + 1))

        if dom >= STEM_PROMOTION_DOMINANCE and vol >= STEM_PROMOTION_VOLUME:
            promoted.append((stem, stem_type, atype, aval, dom, vol))

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
