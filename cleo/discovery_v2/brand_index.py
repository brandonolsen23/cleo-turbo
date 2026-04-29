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

from .config import CALIBRATION
from .signals import (
    is_english_common_token, load_place_names, common_language_zipf,
    load_industry_stopwords, DEFAULT_ZIPF_THRESHOLD,
)
from cleo.atoms.normalize import tokenize_brand


def build_brand_index(conn, *, min_idf: Optional[float] = None, verbose: bool = True):
    """Populate brand_token_index + brand_token_summary from party_atoms.

    The build is idempotent: both tables are DELETE'd and refilled on every run.
    """
    if min_idf is None:
        min_idf = CALIBRATION["exact_brand_token"]["min_idf"]

    excluded = CALIBRATION["excluded_brand_tokens"]

    # Load external signal sources once before the per-token loop.
    place_names = load_place_names(conn)
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
            zipf = common_language_zipf(token)
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


def _brand_token_lookup(conn) -> dict:
    """Build a single-pass lookup from brand_token_summary for n-gram flag rollups.

    Returns {token: {'is_distinctive': 0|1, 'is_excluded': 0|1,
                     'is_english_common': 0|1, 'is_place_name': 0|1,
                     'is_industry_stopword': 0|1}}.
    """
    lookup = {}
    for r in conn.execute(
        """SELECT token, is_distinctive, is_excluded, is_english_common,
                  is_place_name, is_industry_stopword
           FROM brand_token_summary"""
    ):
        lookup[r["token"]] = {
            "is_distinctive": r["is_distinctive"] or 0,
            "is_excluded": r["is_excluded"] or 0,
            "is_english_common": r["is_english_common"] or 0,
            "is_place_name": r["is_place_name"] or 0,
            "is_industry_stopword": r["is_industry_stopword"] or 0,
        }
    return lookup


def build_brand_ngram_index(conn, n: int, *, min_idf: Optional[float] = None, verbose: bool = True):
    """Populate brand_{n}gram_index + brand_{n}gram_summary.

    For each distinct brand_phrase in party_atoms, re-tokenize via tokenize_brand
    and emit every consecutive window of `n` tokens. n-gram distinctiveness is
    gated on the n-gram's own corpus IDF (catches "regional group" cases where
    neither constituent token is distinctive).

    Supports n=2..5. The table/column naming follows:
      2 → bigram   (token_a, token_b)
      3 → trigram  (token_a, token_b, token_c)
      4 → fourgram (token_a, token_b, token_c, token_d)
      5 → fivegram (token_a, token_b, token_c, token_d, token_e)
    """
    assert n in (2, 3, 4, 5), f"only n=2..5 supported, got {n}"
    TABLE_WORD = {2: "bigram", 3: "trigram", 4: "fourgram", 5: "fivegram"}
    TOKEN_NAMES = ["token_a", "token_b", "token_c", "token_d", "token_e"]
    table_word = TABLE_WORD[n]
    index_table = f"brand_{table_word}_index"
    summary_table = f"brand_{table_word}_summary"

    if min_idf is None:
        min_idf = CALIBRATION["exact_brand_token"]["min_idf"]

    conn.execute(f"DELETE FROM {index_table}")
    conn.execute(f"DELETE FROM {summary_table}")

    n_party_sides_total = conn.execute(
        "SELECT COUNT(*) FROM party_fingerprints"
    ).fetchone()[0]
    if n_party_sides_total == 0:
        conn.commit()
        return {"n_ngrams": 0, "n_distinctive": 0, "n_index_rows": 0}

    if verbose:
        print(f"Layer 1 Silo A (brand-{table_word} index): "
              f"building over {n_party_sides_total:,} party-sides", flush=True)

    # Build index by iterating brand_phrase rows and emitting n-grams.
    index_rows = set()  # (ngram, source_id, side)
    phrases_by_ngram = {}  # ngram → set of distinct brand_phrases that produced it
    for r in conn.execute(
        "SELECT source_id, side, atom_value "
        "FROM party_atoms WHERE atom_type = 'brand_phrase'"
    ):
        phrase = r["atom_value"]
        tokens = tokenize_brand(phrase)
        if len(tokens) < n:
            continue
        for i in range(len(tokens) - n + 1):
            window = tokens[i:i + n]
            ngram = " ".join(window)
            index_rows.add((ngram, r["source_id"], r["side"]))
            phrases_by_ngram.setdefault(ngram, set()).add(phrase)

    # Insert index rows in bulk
    conn.executemany(
        f"INSERT OR IGNORE INTO {index_table} ({table_word}, source_id, side) VALUES (?, ?, ?)",
        index_rows,
    )
    n_index_rows = conn.execute(f"SELECT COUNT(*) FROM {index_table}").fetchone()[0]

    # Compute summary stats per n-gram
    token_lookup = _brand_token_lookup(conn)

    # Count distinct party-sides per ngram via the index
    df_by_ngram = {
        row[0]: row[1]
        for row in conn.execute(
            f"SELECT {table_word}, COUNT(*) FROM {index_table} GROUP BY {table_word}"
        )
    }

    summary_rows = []
    for ngram, df in df_by_ngram.items():
        tokens = ngram.split(" ")
        idf = math.log(n_party_sides_total / (1 + df))
        n_phrases = len(phrases_by_ngram.get(ngram, set()))

        flags = [token_lookup.get(t, {}) for t in tokens]
        any_dist = 1 if any(f.get("is_distinctive") for f in flags) else 0
        any_excluded = 1 if any(f.get("is_excluded") for f in flags) else 0
        all_english = 1 if flags and all(f.get("is_english_common") for f in flags) else 0
        all_place = 1 if flags and all(f.get("is_place_name") for f in flags) else 0
        all_industry = 1 if flags and all(f.get("is_industry_stopword") for f in flags) else 0

        is_distinctive = 1 if (idf >= min_idf and not any_excluded) else 0

        # Build the summary row dynamically — n token columns followed by stats.
        row = [ngram] + tokens[:n] + [
            idf, df, n_phrases,
            any_dist, any_excluded, all_english, all_place, all_industry,
            is_distinctive,
        ]
        summary_rows.append(tuple(row))

    token_columns = ", ".join(TOKEN_NAMES[:n])
    placeholders = ", ".join(["?"] * (1 + n + 9))   # ngram + n tokens + 9 stats columns
    conn.executemany(
        f"""INSERT INTO {summary_table}
            ({table_word}, {token_columns}, idf, n_party_sides, n_distinct_phrases,
             any_token_distinctive, any_token_excluded,
             all_english, all_place, all_industry, is_distinctive)
            VALUES ({placeholders})""",
        summary_rows,
    )

    conn.commit()

    n_distinctive = sum(1 for r in summary_rows if r[-1] == 1)
    if verbose:
        print(f"  {len(summary_rows):,} distinct {table_word}s "
              f"({n_distinctive:,} distinctive at IDF≥{min_idf})", flush=True)
        print(f"  {n_index_rows:,} ({table_word}, party-side) index rows", flush=True)

    return {
        "n_ngrams": len(summary_rows),
        "n_distinctive": n_distinctive,
        "n_index_rows": n_index_rows,
    }


def build_long_phrase_index(conn, *, min_idf: Optional[float] = None, verbose: bool = True):
    """Populate brand_long_phrase_index + brand_long_phrase_summary.

    For each distinct brand_phrase in party_atoms, re-tokenize via tokenize_brand.
    If the resulting token count is >= 6, emit ONE row keyed on the joined
    tokens. The 6+ silo captures the long tail of phrase lengths (institutional
    entities, sovereign names, school boards, etc.) without sliding-window
    storage explosion.
    """
    if min_idf is None:
        min_idf = CALIBRATION["exact_brand_token"]["min_idf"]

    conn.execute("DELETE FROM brand_long_phrase_index")
    conn.execute("DELETE FROM brand_long_phrase_summary")

    n_party_sides_total = conn.execute(
        "SELECT COUNT(*) FROM party_fingerprints"
    ).fetchone()[0]
    if n_party_sides_total == 0:
        conn.commit()
        return {"n_phrases": 0, "n_distinctive": 0, "n_index_rows": 0}

    if verbose:
        print(f"Layer 1 Silo A (brand long-form 6+): "
              f"building over {n_party_sides_total:,} party-sides", flush=True)

    # (joined-phrase, source_id, side) → presence
    index_rows: set = set()
    # joined-phrase → {raw atom_values that produced it}
    sources_by_phrase: dict = {}
    # joined-phrase → list of constituent tokens (for flag rollup)
    tokens_by_phrase: dict = {}

    for r in conn.execute(
        "SELECT source_id, side, atom_value "
        "FROM party_atoms WHERE atom_type = 'brand_phrase'"
    ):
        raw = r["atom_value"]
        tokens = tokenize_brand(raw)
        if len(tokens) < 6:
            continue
        joined = " ".join(tokens)
        index_rows.add((joined, r["source_id"], r["side"]))
        sources_by_phrase.setdefault(joined, set()).add(raw)
        tokens_by_phrase.setdefault(joined, tokens)

    conn.executemany(
        "INSERT OR IGNORE INTO brand_long_phrase_index (phrase, source_id, side) "
        "VALUES (?, ?, ?)",
        index_rows,
    )
    n_index_rows = conn.execute(
        "SELECT COUNT(*) FROM brand_long_phrase_index"
    ).fetchone()[0]

    token_lookup = _brand_token_lookup(conn)

    # Count distinct party-sides per joined-phrase via the index
    df_by_phrase = {
        row[0]: row[1]
        for row in conn.execute(
            "SELECT phrase, COUNT(*) FROM brand_long_phrase_index GROUP BY phrase"
        )
    }

    summary_rows = []
    for joined_phrase, df in df_by_phrase.items():
        tokens = tokens_by_phrase.get(joined_phrase, joined_phrase.split(" "))
        n_tokens = len(tokens)
        idf = math.log(n_party_sides_total / (1 + df))
        n_distinct_source = len(sources_by_phrase.get(joined_phrase, set()))

        flags = [token_lookup.get(t, {}) for t in tokens]
        any_dist = 1 if any(f.get("is_distinctive") for f in flags) else 0
        any_excluded = 1 if any(f.get("is_excluded") for f in flags) else 0
        all_english = 1 if flags and all(f.get("is_english_common") for f in flags) else 0
        all_place = 1 if flags and all(f.get("is_place_name") for f in flags) else 0
        all_industry = 1 if flags and all(f.get("is_industry_stopword") for f in flags) else 0

        is_distinctive = 1 if (idf >= min_idf and not any_excluded) else 0

        summary_rows.append((
            joined_phrase, n_tokens, idf, df, n_distinct_source,
            any_dist, any_excluded, all_english, all_place, all_industry,
            is_distinctive,
        ))

    conn.executemany(
        """INSERT INTO brand_long_phrase_summary
            (phrase, n_tokens, idf, n_party_sides, n_distinct_source_phrases,
             any_token_distinctive, any_token_excluded,
             all_english, all_place, all_industry, is_distinctive)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        summary_rows,
    )
    conn.commit()

    n_distinctive = sum(1 for r in summary_rows if r[-1] == 1)
    if verbose:
        print(f"  {len(summary_rows):,} distinct long-form phrases "
              f"({n_distinctive:,} distinctive at IDF≥{min_idf})", flush=True)
        print(f"  {n_index_rows:,} (phrase, party-side) index rows", flush=True)

    return {
        "n_phrases": len(summary_rows),
        "n_distinctive": n_distinctive,
        "n_index_rows": n_index_rows,
    }


def build_phone_summary(conn, *, verbose: bool = True):
    """Populate phone_summary. Phones already live in party_fingerprints.phone."""
    conn.execute("DELETE FROM phone_summary")
    conn.execute("""
        INSERT INTO phone_summary (phone, n_party_sides, is_distinctive)
        SELECT phone, COUNT(*), 1
        FROM party_fingerprints
        WHERE phone IS NOT NULL AND phone != ''
        GROUP BY phone
    """)
    n = conn.execute("SELECT COUNT(*) FROM phone_summary").fetchone()[0]
    conn.commit()
    if verbose:
        print(f"Layer 1 Silo B (phones): {n:,} distinct phones", flush=True)
    return {"n_phones": n}


def build_address_base_summary(conn, *, verbose: bool = True):
    """Populate address_base_summary. Address bases = (street_number + street_name + street_suffix)."""
    conn.execute("DELETE FROM address_base_summary")
    conn.execute("""
        INSERT INTO address_base_summary
            (street_number, street_name, street_suffix,
             n_party_sides, n_distinct_suites, n_distinct_postals, is_distinctive)
        SELECT street_number, street_name, street_suffix,
               COUNT(*) AS n_party_sides,
               COUNT(DISTINCT COALESCE(suite_type, '') || '|' || COALESCE(suite_number, '')) AS n_distinct_suites,
               COUNT(DISTINCT COALESCE(postal, '')) AS n_distinct_postals,
               1
        FROM party_fingerprints
        WHERE street_number IS NOT NULL AND street_number != ''
          AND street_name IS NOT NULL AND street_name != ''
          AND street_suffix IS NOT NULL AND street_suffix != ''
        GROUP BY street_number, street_name, street_suffix
    """)
    n = conn.execute("SELECT COUNT(*) FROM address_base_summary").fetchone()[0]
    conn.commit()
    if verbose:
        print(f"Layer 1 Silo C (address bases): {n:,} distinct bases", flush=True)
    return {"n_bases": n}


def build_address_root_summary(conn, *, verbose: bool = True):
    """Populate address_root_summary. Roots = (street_number + street_name)
    aggregation, one level shallower than address_base_summary which also
    requires street_suffix."""
    conn.execute("DELETE FROM address_root_summary")
    conn.execute("""
        INSERT INTO address_root_summary
            (street_number, street_name, n_party_sides, n_distinct_suffixes,
             n_distinct_directions, n_distinct_suites, n_distinct_postals)
        SELECT street_number, street_name,
               COUNT(*) AS n_party_sides,
               COUNT(DISTINCT COALESCE(street_suffix, '')) AS n_distinct_suffixes,
               COUNT(DISTINCT COALESCE(street_direction, '')) AS n_distinct_directions,
               COUNT(DISTINCT COALESCE(suite_type, '') || '|' || COALESCE(suite_number, '')) AS n_distinct_suites,
               COUNT(DISTINCT COALESCE(postal, '')) AS n_distinct_postals
        FROM party_fingerprints
        WHERE street_number IS NOT NULL AND street_number != ''
          AND street_name IS NOT NULL AND street_name != ''
        GROUP BY street_number, street_name
    """)
    n = conn.execute("SELECT COUNT(*) FROM address_root_summary").fetchone()[0]
    conn.commit()
    if verbose:
        print(f"Layer 1 Silo C (address roots): {n:,} distinct roots", flush=True)
    return {"n_roots": n}


def build_address_unit_summary(conn, *, verbose: bool = True):
    """Layer 1 silo: per-unit brand-stem dominance.

    A 'unit' is the full physical address: city + street_number + street_name +
    street_suffix + street_direction + suite_type + suite_number. Empty fields
    (NULL or '') are normalized to empty string in the key.
    """
    conn.execute('DELETE FROM address_unit_summary')

    # Step 1: build per-side dominant stem (most-common stem across the side's phrases).
    side_stems: dict = {}
    for r in conn.execute("""
        SELECT pa.source_id, pa.side, m.stem, COUNT(*) AS n
        FROM party_atoms pa
        JOIN brand_stem_phrase_map m ON m.phrase = pa.atom_value
        WHERE pa.atom_type = 'brand_phrase'
        GROUP BY pa.source_id, pa.side, m.stem
    """):
        key = (r['source_id'], r['side'])
        prev = side_stems.get(key)
        new_value = (r['stem'], r['n'])
        if prev is None or (r['n'] > prev[1]) or (r['n'] == prev[1] and r['stem'] < prev[0]):
            side_stems[key] = new_value

    # Step 2: aggregate parties by unit-key, computing stem counts.
    by_unit: dict = {}
    for r in conn.execute("""
        SELECT source_id, side, city, street_number, street_name,
               street_suffix, street_direction, suite_type, suite_number
        FROM party_fingerprints
        WHERE city IS NOT NULL AND city != ''
          AND street_number IS NOT NULL AND street_number != ''
          AND street_name IS NOT NULL AND street_name != ''
    """):
        key = (
            r['city'], r['street_number'], r['street_name'],
            r['street_suffix'] or '',
            r['street_direction'] or '',
            r['suite_type'] or '',
            r['suite_number'] or '',
        )
        bucket = by_unit.setdefault(key, {'sides': 0, 'stem_counts': {}})
        bucket['sides'] += 1
        st = side_stems.get((r['source_id'], r['side']))
        if st is not None:
            bucket['stem_counts'][st[0]] = bucket['stem_counts'].get(st[0], 0) + 1

    # Step 3: insert rows, computing dominant stem + share.
    rows_to_insert = []
    for (city, num, name, suf, dir_, stype, snum), bucket in by_unit.items():
        n_parties = bucket['sides']
        stem_counts = bucket['stem_counts']
        n_distinct = len(stem_counts)
        if stem_counts:
            # Sort by (-count, stem) so highest count first, ties broken alphabetically.
            dom_stem, dom_n = sorted(stem_counts.items(), key=lambda kv: (-kv[1], kv[0]))[0]
            dom_share = dom_n / n_parties
        else:
            dom_stem, dom_share = None, 0.0
        rows_to_insert.append((
            city, num, name, suf, dir_, stype, snum,
            n_parties, n_distinct, dom_stem, dom_share,
        ))

    conn.executemany(
        """INSERT INTO address_unit_summary
            (city, street_number, street_name, street_suffix, street_direction,
             suite_type, suite_number, n_party_sides, n_distinct_brand_stems,
             dominant_stem, dominance_share)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows_to_insert,
    )
    conn.commit()
    if verbose:
        print(f'Layer 1 Silo E (address units): {len(rows_to_insert):,} distinct units', flush=True)
    return {'n_units': len(rows_to_insert)}


def build_contact_fingerprint_summary(conn, *, verbose: bool = True):
    """Populate contact_fingerprint_summary."""
    conn.execute("DELETE FROM contact_fingerprint_summary")
    conn.execute("""
        INSERT INTO contact_fingerprint_summary
            (contact_fingerprint, n_party_sides, is_distinctive)
        SELECT contact_fingerprint, COUNT(*), 1
        FROM party_fingerprints
        WHERE contact_fingerprint IS NOT NULL AND contact_fingerprint != ''
        GROUP BY contact_fingerprint
    """)
    n = conn.execute("SELECT COUNT(*) FROM contact_fingerprint_summary").fetchone()[0]
    conn.commit()
    if verbose:
        print(f"Layer 1 Silo D (contact fingerprints): {n:,} distinct contacts", flush=True)
    return {"n_contacts": n}


def _recompute_position_anchors(conn, *, verbose: bool = True):
    """Compute position_consistency, total_child_coverage, and is_position_anchor
    on every row of brand_token_summary, using brand_bigram_summary as input.

    A 1-gram is a position-anchor when ALL hold:
      - n_party_sides >= 10
      - is_distinctive = 0 (we're rescuing tokens already filtered)
      - is_excluded = 0
      - position_consistency >= 0.95
      - total_child_coverage >= 0.85
      - n_distinct_children >= 3

    Already-distinctive tokens get position_consistency and total_child_coverage
    populated for visibility but is_position_anchor stays 0 (no rescue needed).
    """
    if verbose:
        print("Layer 1 Silo A: recomputing position-anchor flags...", flush=True)

    # Build per-token aggregates from brand_bigram_summary.
    # For each 1-gram, count n_party_sides where it appears as token_a vs token_b,
    # and how many distinct child 2-grams contain it.
    tokens_stats: dict = {}
    for row in conn.execute(
        "SELECT token_a, token_b, n_party_sides FROM brand_bigram_summary"
    ):
        for tok, side in ((row["token_a"], "a"), (row["token_b"], "b")):
            stats = tokens_stats.setdefault(tok, {"pos_a": 0, "pos_b": 0, "n_children": 0})
            if side == "a":
                stats["pos_a"] += row["n_party_sides"]
            else:
                stats["pos_b"] += row["n_party_sides"]
            stats["n_children"] += 1

    # Update each brand_token_summary row.
    n_anchors = 0
    updates = []
    for token_row in conn.execute(
        "SELECT token, n_party_sides, is_distinctive, is_excluded "
        "FROM brand_token_summary"
    ):
        token = token_row["token"]
        sides_1g = token_row["n_party_sides"]
        is_distinctive = token_row["is_distinctive"]
        is_excluded = token_row["is_excluded"]

        s = tokens_stats.get(token, {"pos_a": 0, "pos_b": 0, "n_children": 0})
        pos_a = s["pos_a"]
        pos_b = s["pos_b"]
        n_children = s["n_children"]
        total_pos = pos_a + pos_b

        position_consistency = (max(pos_a, pos_b) / total_pos) if total_pos > 0 else None
        total_child_coverage = min(1.0, total_pos / sides_1g) if sides_1g > 0 else None

        is_anchor = 0
        if (sides_1g >= 10
            and is_distinctive == 0
            and is_excluded == 0
            and position_consistency is not None
            and position_consistency >= 0.95
            and total_child_coverage is not None
            and total_child_coverage >= 0.85
            and n_children >= 3):
            is_anchor = 1
            n_anchors += 1

        updates.append((position_consistency, total_child_coverage, is_anchor, token))

    conn.executemany(
        "UPDATE brand_token_summary "
        "SET position_consistency = ?, total_child_coverage = ?, is_position_anchor = ? "
        "WHERE token = ?",
        updates,
    )
    conn.commit()
    if verbose:
        print(f"  {n_anchors:,} position-anchor 1-grams flagged", flush=True)
    return {"n_anchors": n_anchors}


def build_all_indexes(conn, *, min_idf: Optional[float] = None, verbose: bool = True):
    """Populate every Layer 1 silo index/summary table.

    Order matters: brand_token_summary must be built BEFORE brand n-gram
    builders so that the n-gram flag rollups can look up constituent
    token flags. Position-anchor recompute runs after the bigram build
    (bigram data is the input) but before higher n-grams (so n_children
    counts are stable by the time 3/4/5-grams run).
    """
    build_brand_index(conn, min_idf=min_idf, verbose=verbose)
    build_brand_ngram_index(conn, 2, min_idf=min_idf, verbose=verbose)
    _recompute_position_anchors(conn, verbose=verbose)   # after bigram is built
    build_brand_ngram_index(conn, 3, min_idf=min_idf, verbose=verbose)
    build_brand_ngram_index(conn, 4, min_idf=min_idf, verbose=verbose)
    build_brand_ngram_index(conn, 5, min_idf=min_idf, verbose=verbose)
    build_long_phrase_index(conn, min_idf=min_idf, verbose=verbose)
    build_phone_summary(conn, verbose=verbose)
    build_address_base_summary(conn, verbose=verbose)
    build_address_root_summary(conn, verbose=verbose)
    build_address_unit_summary(conn, verbose=verbose)        # ← Plan H1
    build_contact_fingerprint_summary(conn, verbose=verbose)
