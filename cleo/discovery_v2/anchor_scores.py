"""Stage A2: Anchor uniqueness scoring.

For each anchor (phone, address_root, address_base, contact), computes the
dominant brand_stem and a score = dominance_share * log(volume + 1).
"""
from __future__ import annotations
import math
import sqlite3


_ANCHOR_QUERIES = {
    # anchor_type → SQL that yields (anchor_value, source_id, side) for each
    # party-side, with anchor_value being the canonical key for that type.
    'phone': """
        SELECT phone AS anchor_value, source_id, side
        FROM party_fingerprints
        WHERE phone IS NOT NULL AND phone != ''
    """,
    'address_root': """
        SELECT (street_number || '|' || street_name) AS anchor_value, source_id, side
        FROM party_fingerprints
        WHERE street_number IS NOT NULL AND street_number != ''
          AND street_name IS NOT NULL AND street_name != ''
    """,
    'address_base': """
        SELECT (street_number || '|' || street_name || '|' || COALESCE(street_suffix,'')) AS anchor_value, source_id, side
        FROM party_fingerprints
        WHERE street_number IS NOT NULL AND street_number != ''
          AND street_name IS NOT NULL AND street_name != ''
    """,
    'contact': """
        SELECT contact_fingerprint AS anchor_value, source_id, side
        FROM party_fingerprints
        WHERE contact_fingerprint IS NOT NULL AND contact_fingerprint != ''
    """,
}


def build_anchor_scores(conn: sqlite3.Connection, *, verbose: bool = True) -> dict:
    """Populate anchor_uniqueness for all four anchor types. Idempotent."""
    conn.execute('DELETE FROM anchor_uniqueness')

    # Per-side dominant stem lookup: each side has potentially multiple
    # phrases; pick the most-common stem across the side's phrases.
    side_stems = {}  # (source_id, side) -> stem
    for r in conn.execute("""
        SELECT pa.source_id, pa.side, m.stem, COUNT(*) AS n
        FROM party_atoms pa
        JOIN brand_stem_phrase_map m ON m.phrase = pa.atom_value
        WHERE pa.atom_type = 'brand_phrase'
        GROUP BY pa.source_id, pa.side, m.stem
    """):
        key = (r['source_id'], r['side'])
        prev = side_stems.get(key)
        if prev is None or r['n'] > prev[1]:
            side_stems[key] = (r['stem'], r['n'])

    rows_to_insert = []
    for anchor_type, anchor_sql in _ANCHOR_QUERIES.items():
        # Group party-sides by anchor_value
        by_anchor = {}  # anchor_value -> list of (source_id, side)
        for r in conn.execute(anchor_sql):
            by_anchor.setdefault(r['anchor_value'], []).append(
                (r['source_id'], r['side'])
            )
        for anchor_value, sides in by_anchor.items():
            volume = len(sides)
            stem_counts = {}
            for sid, side in sides:
                stem_tup = side_stems.get((sid, side))
                if stem_tup is not None:
                    stem = stem_tup[0]
                    stem_counts[stem] = stem_counts.get(stem, 0) + 1
            if stem_counts:
                dominant_stem, dom_n = max(stem_counts.items(), key=lambda x: x[1])
                dominance_share = dom_n / volume
            else:
                dominant_stem, dominance_share = None, 0.0
            score = dominance_share * math.log(volume + 1)
            rows_to_insert.append(
                (anchor_type, anchor_value, dominant_stem, dominance_share, volume, score)
            )

    if rows_to_insert:
        conn.executemany(
            """INSERT INTO anchor_uniqueness
                 (anchor_type, anchor_value, dominant_stem, dominance_share, volume, score)
               VALUES (?, ?, ?, ?, ?, ?)""",
            rows_to_insert,
        )
    conn.commit()
    if verbose:
        print(f'  Stage A2 (anchor scores): {len(rows_to_insert):,} anchor rows.', flush=True)
    return {'n_anchors': len(rows_to_insert)}
