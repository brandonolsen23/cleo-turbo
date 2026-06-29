"""N-gram extraction for the Group Identity System.

Reads party-bearing fields from transactions + transaction_parties, normalises
via cleo.atoms.normalize, generates 1..N grams from each tokenised string,
aggregates counts and source-field distribution, applies a backward-walk
subset classification, and writes data/ngram_analysis.json for inspection
before any schema / curation work begins.

This is a read-only pass. No database writes. Run from project root:

    python -m cleo.identity.ngram_extract
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter, defaultdict

from cleo.atoms.normalize import normalize_brand, tokenize_brand
from cleo.database.connection import get_connection

MAX_NGRAM_LEN = 8

# 1-gram-only stopwords. Generic words that should NEVER be defining tokens
# on their own, but remain inside longer n-grams (e.g. "ontario" alone is
# meaningless, but "ontario superior court" is the entity name for the court).
ONEGRAM_STOPWORDS = frozenset({
    # Place names commonly appearing in entity names
    "ontario", "canada", "toronto", "ottawa", "mississauga", "hamilton",
    "vaughan", "markham", "brampton", "oakville", "burlington", "milton",
    "north", "south", "east", "west", "central", "greater",
    # Generic corporate descriptors
    "holdings", "holding", "properties", "property", "investments",
    "investment", "group", "corporation", "company", "enterprises",
    "enterprise", "ventures", "venture", "capital", "international",
    "national", "regional", "global", "consolidated", "associates",
    "associate", "partnership", "partners", "partner", "limited",
    "incorporated",
    # Realtrack-specific
    "individual", "named", "individuals",
    # Industry generic
    "real", "estate", "development", "developments", "developer",
    "developers", "construction", "builder", "builders", "homes",
    "home", "realty", "trust", "fund", "funds", "reit",
    # Government/civic
    "city", "town", "county", "regional", "municipality", "municipal",
    "school", "district", "board", "boards", "ministry",
})


def _emit_source_strings(row):
    """Yield (source_field, raw_string) for one party-side row."""
    if row["party_name"]:
        yield "party_name", row["party_name"]
    if row["trade_name"]:
        yield "trade_name", row["trade_name"]
    if row["care_of"]:
        yield "care_of", row["care_of"]
    if row["companies_json"]:
        try:
            companies = json.loads(row["companies_json"])
        except (json.JSONDecodeError, TypeError):
            companies = []
        for c in companies:
            if isinstance(c, str) and c.strip():
                yield "companies_json", c


def _generate_ngrams(tokens, max_len):
    """Yield (length, ngram) for n in 1..min(len(tokens), max_len)."""
    n = len(tokens)
    for L in range(1, min(n, max_len) + 1):
        for i in range(n - L + 1):
            yield L, " ".join(tokens[i:i + L])


def extract(conn):
    """Run the extraction. Returns the analysis dict."""
    print("Loading party-side rows...")
    rows = conn.execute(
        """
        SELECT tp.source_id, tp.side, tp.party_name, tp.group_id,
               CASE WHEN tp.side = 'buyer' THEN t.buyer_trade_name
                    ELSE t.seller_trade_name END AS trade_name,
               CASE WHEN tp.side = 'buyer' THEN t.buyer_care_of
                    ELSE t.seller_care_of END AS care_of,
               CASE WHEN tp.side = 'buyer' THEN t.buyer_companies_json
                    ELSE t.seller_companies_json END AS companies_json
        FROM transaction_parties tp
        JOIN transactions t ON t.source_id = tp.source_id
        """
    ).fetchall()
    print(f"  Loaded {len(rows):,} party-side rows")

    # Aggregators (defaultdict avoids "is key in dict" branches)
    occurrence_count = Counter()                     # ngram -> total occurrences
    distinct_source_ids = defaultdict(set)           # ngram -> set of source_ids
    distinct_groups = defaultdict(set)               # ngram -> set of group_ids
    source_field_counts = defaultdict(Counter)       # ngram -> Counter[source_field]
    sample_strings = defaultdict(list)               # ngram -> up to 10 raw strings
    ngram_length = {}                                # ngram -> length

    start = time.time()
    for i, row in enumerate(rows):
        if (i + 1) % 50_000 == 0:
            elapsed = time.time() - start
            rate = (i + 1) / elapsed
            print(f"  [{i+1:,}/{len(rows):,}] {rate:.0f} rows/s")

        source_id = row["source_id"]
        group_id = row["group_id"]

        for source_field, raw in _emit_source_strings(row):
            normalised = normalize_brand(raw)
            if not normalised:
                continue
            tokens = tokenize_brand(normalised)
            if not tokens:
                continue

            seen_in_this_string = set()
            for length, ngram in _generate_ngrams(tokens, MAX_NGRAM_LEN):
                occurrence_count[ngram] += 1
                distinct_source_ids[ngram].add(source_id)
                if group_id:
                    distinct_groups[ngram].add(group_id)
                source_field_counts[ngram][source_field] += 1
                ngram_length[ngram] = length
                # Sample strings: only collect up to 10 distinct raw strings
                # to avoid memory bloat on common n-grams.
                if ngram not in seen_in_this_string and len(sample_strings[ngram]) < 10:
                    sample_strings[ngram].append(raw)
                seen_in_this_string.add(ngram)

    elapsed = time.time() - start
    print(f"  Extraction done in {elapsed:.1f}s")
    print(f"  Distinct n-grams: {len(occurrence_count):,}")

    # ── Simple classification ──
    #
    # Phase 1 keeps it simple — drop single-occurrence noise, mark 1-gram
    # stopwords, leave everything else as "candidate". Subset relationships
    # will be identified by Claude in Phase 2 (AI curation) when it has full
    # context per n-gram and can name the canonical entity.

    print("Classifying candidates...")
    status = {}
    for ngram, count in occurrence_count.items():
        if count < 2:
            continue
        if ngram_length[ngram] == 1 and ngram in ONEGRAM_STOPWORDS:
            status[ngram] = "stopword_1gram"
        else:
            status[ngram] = "candidate"
    subset_of = {}

    # Build output records
    print("Building output records...")
    records = []
    for ngram, count in occurrence_count.items():
        if count < 2:
            # Drop single-occurrence n-grams entirely — pure noise
            continue
        records.append({
            "ngram": ngram,
            "length": ngram_length[ngram],
            "occurrence_count": count,
            "distinct_transactions": len(distinct_source_ids[ngram]),
            "distinct_existing_groups": len(distinct_groups[ngram]),
            "source_field_distribution": dict(source_field_counts[ngram]),
            "sample_strings": sample_strings[ngram][:5],
            "status": status.get(ngram, "candidate_defining"),
            "subset_of": subset_of.get(ngram),
        })

    # Sort by length DESC, then occurrence_count DESC — gives 6+ grams first
    records.sort(key=lambda r: (-r["length"], -r["occurrence_count"]))

    # Stats
    by_status = Counter(r["status"] for r in records)
    by_length_stat = Counter(r["length"] for r in records)
    candidates_by_length = Counter(
        r["length"] for r in records if r["status"] == "candidate_defining"
    )

    print()
    print("── Summary ──")
    print(f"  Distinct n-grams emitted (occ ≥ 2): {len(records):,}")
    print(f"  Single-occurrence n-grams dropped:  {len(occurrence_count) - len(records):,}")
    print()
    print("  Status breakdown:")
    for status_name, n in sorted(by_status.items(), key=lambda x: -x[1]):
        print(f"    {status_name:25s} {n:>8,}")
    print()
    print("  Distribution by length (all kept):")
    for length in sorted(by_length_stat.keys()):
        cd = candidates_by_length.get(length, 0)
        total = by_length_stat[length]
        print(f"    {length}-gram  {total:>8,} total   {cd:>8,} candidate_defining")

    output = {
        "metadata": {
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_party_sides_processed": len(rows),
            "distinct_ngrams_emitted": len(records),
            "single_occurrence_dropped": len(occurrence_count) - len(records),
            "status_breakdown": dict(by_status),
            "candidate_defining_by_length": dict(candidates_by_length),
        },
        "ngrams": records,
    }
    return output


def main():
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    out_path = os.path.join(project_root, "data", "ngram_analysis.json")

    conn = get_connection()
    output = extract(conn)
    conn.close()

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    print(f"\nWriting {out_path}...")
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    size_mb = os.path.getsize(out_path) / 1024 / 1024
    print(f"  Wrote {size_mb:.1f} MB")


if __name__ == "__main__":
    main()
