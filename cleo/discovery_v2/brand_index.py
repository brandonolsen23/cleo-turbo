"""Layer 1 / Silo A — inverted index from brand_tokens to party-sides.

For every distinct brand_token in `party_atoms`, record:
  - the party-sides that carry it (brand_token_index)
  - summary stats: IDF, count of party-sides, count of distinct
    brand_phrases that contain it, plus is_distinctive / is_excluded
    flags (brand_token_summary)

No clustering, no anchor assignment, no entity creation. Just the index.
"""

from __future__ import annotations
import math
from typing import Optional

import wordfreq

from .config import CALIBRATION
from .signals import (
    is_english_common_token, load_place_names,
    load_industry_stopwords, DEFAULT_ZIPF_THRESHOLD,
)


def build_brand_index(conn, *, min_idf: Optional[float] = None, verbose: bool = True):
    """Populate brand_token_index + brand_token_summary from party_atoms.

    The build is idempotent: both tables are DELETE'd and refilled on every run.
    """
    if min_idf is None:
        min_idf = CALIBRATION["exact_brand_token"]["min_idf"]

    excluded = CALIBRATION["excluded_brand_tokens"]

    # Load external signal sources once before the per-token loop.
    place_names = load_place_names()
    industry_stopwords_set = load_industry_stopwords(conn)
    zipf_threshold = DEFAULT_ZIPF_THRESHOLD

    # Wipe (DELETE, not DROP — schema is managed by migration 008).
    conn.execute("DELETE FROM brand_token_index")
    conn.execute("DELETE FROM brand_token_summary")

    n_party_sides_total = conn.execute(
        "SELECT COUNT(*) FROM party_fingerprints"
    ).fetchone()[0]
    if n_party_sides_total == 0:
        conn.commit()
        return {"n_tokens": 0, "n_distinctive": 0, "n_index_rows": 0}

    if verbose:
        print(f"Layer 1 Silo A (brand-token index): "
              f"{n_party_sides_total:,} party-sides total", flush=True)

    # Populate brand_token_index: distinct (token, source_id, side) triples.
    conn.execute("""
        INSERT OR IGNORE INTO brand_token_index (token, source_id, side)
        SELECT DISTINCT atom_value, source_id, side
        FROM party_atoms
        WHERE atom_type = 'brand_token'
    """)
    n_index_rows = conn.execute(
        "SELECT COUNT(*) FROM brand_token_index"
    ).fetchone()[0]

    # Compute summary: IDF, n_party_sides, n_distinct_phrases per token.
    # IDF = log(N / (1 + df)) where df = count of distinct party-sides carrying the token.
    #
    # n_distinct_phrases: for a given token, how many distinct brand_phrase values appear
    # on the party-sides that carry that token?  Computed with a single join pass
    # (CTE approach) rather than a correlated subquery — the correlated form is O(tokens ×
    # party_atoms) and is impossibly slow on the full 249k-row dataset.
    summary_rows = []
    for r in conn.execute("""
        WITH phrase_counts AS (
            -- For every (token, party-side) pair in the index, find all brand_phrases
            -- that co-occur on that same party-side, then count distinct phrase values.
            SELECT bti.token,
                   COUNT(DISTINCT pa.atom_value) AS n_distinct_phrases
            FROM brand_token_index bti
            JOIN party_atoms pa
              ON pa.source_id = bti.source_id
             AND pa.side      = bti.side
             AND pa.atom_type = 'brand_phrase'
            GROUP BY bti.token
        )
        SELECT bti.token,
               COUNT(*) AS n_party_sides,
               COALESCE(pc.n_distinct_phrases, 0) AS n_distinct_phrases
        FROM brand_token_index bti
        LEFT JOIN phrase_counts pc ON pc.token = bti.token
        GROUP BY bti.token
    """):
        token = r["token"]
        df = r["n_party_sides"]
        idf = math.log(n_party_sides_total / (1 + df))

        try:
            zipf = float(wordfreq.zipf_frequency(token, "en"))
        except Exception:
            zipf = 0.0

        english = 1 if zipf >= zipf_threshold else 0
        place = 1 if token in place_names else 0
        industry = 1 if token in industry_stopwords_set else 0
        is_excluded_flag = 1 if token in excluded else 0

        # Filter-reason precedence: excluded > industry > place > english > (None → distinctive)
        if is_excluded_flag:
            reason = "excluded"
        elif industry:
            reason = "industry"
        elif place:
            reason = "place"
        elif english:
            reason = "english"
        else:
            reason = None

        is_distinctive = 1 if (
            idf >= min_idf
            and not is_excluded_flag
            and not industry
            and not place
            and not english
        ) else 0

        summary_rows.append((
            token, idf, df, r["n_distinct_phrases"], is_distinctive, is_excluded_flag,
            zipf, english, place, industry, reason,
        ))

    conn.executemany(
        """INSERT INTO brand_token_summary
           (token, idf, n_party_sides, n_distinct_phrases, is_distinctive, is_excluded,
            wordfreq_zipf, is_english_common, is_place_name, is_industry_stopword, filter_reason)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        summary_rows,
    )
    conn.commit()

    n_distinctive = sum(1 for r in summary_rows if r[4] == 1)
    if verbose:
        print(f"  {len(summary_rows):,} distinct tokens ({n_distinctive:,} distinctive at IDF≥{min_idf})", flush=True)
        print(f"  {n_index_rows:,} (token, party-side) index rows", flush=True)

    return {
        "n_tokens": len(summary_rows),
        "n_distinctive": n_distinctive,
        "n_index_rows": n_index_rows,
    }
