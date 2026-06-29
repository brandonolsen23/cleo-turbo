"""Test Lab — explore the n-gram lattice for a seed phrase.

Two endpoints:
  GET /api/test-lab/lattice?seed=...
      Returns the full lattice: every distinct n-gram that appears on the
      seed's RT scope, grouped by length, with scope-RT count, total-RT
      count, and purity (scope / total).
  GET /api/test-lab/node?seed=...&phrase=...
      Returns details for one selected n-gram inside the seed's scope:
      the RT/side set, the leaf brand phrases that produced it, and the
      top shared anchors (addresses, contacts, phones).

The lattice is computed on the fly. Both endpoints assume the seed is a
short phrase whose token-count is between 1 and 6 (the longest we have
an exact-match index for).
"""

from __future__ import annotations
import json
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import get_db, get_current_user
from ...atoms.normalize import tokenize_brand, normalize_brand


router = APIRouter()


# Map n-gram length → (index table, value column)
NGRAM_INDEX = {
    1: ("brand_token_index", "token"),
    2: ("brand_bigram_index", "bigram"),
    3: ("brand_trigram_index", "trigram"),
    4: ("brand_fourgram_index", "fourgram"),
    5: ("brand_fivegram_index", "fivegram"),
}
LONG_PHRASE_INDEX = ("brand_long_phrase_index", "phrase")  # length ≥ 6
MAX_NGRAM_LENGTH = 6  # cap how deep we enumerate sub-n-grams from each leaf


def _seed_tokens(seed: str) -> list[str]:
    """Tokenize a user-typed seed using the same rules as the indices."""
    if not seed or not seed.strip():
        return []
    normalized = normalize_brand(seed)
    return tokenize_brand(normalized)


def _index_for_length(length: int) -> tuple[str, str]:
    if length <= 5:
        return NGRAM_INDEX[length]
    return LONG_PHRASE_INDEX


def _fetch_scope_sides(db, ngram: str, length: int) -> set[tuple[str, str]]:
    """Return the set of (source_id, side) where this n-gram appears."""
    table, col = _index_for_length(length)
    rows = db.execute(
        f"SELECT DISTINCT source_id, side FROM {table} WHERE {col} = ?",
        (ngram,),
    ).fetchall()
    return {(r["source_id"], r["side"]) for r in rows}


def _bulk_total_rt_counts(db, ngrams_by_length: dict[int, list[str]]) -> dict[str, int]:
    """For each n-gram, count distinct source_id across the whole DB."""
    totals: dict[str, int] = {}
    for length, phrases in ngrams_by_length.items():
        if not phrases:
            continue
        table, col = _index_for_length(length)
        # Chunk to avoid huge IN clauses
        CHUNK = 500
        for i in range(0, len(phrases), CHUNK):
            chunk = phrases[i : i + CHUNK]
            placeholders = ",".join("?" * len(chunk))
            rows = db.execute(
                f"""SELECT {col} AS phrase, COUNT(DISTINCT source_id) AS n
                    FROM {table}
                    WHERE {col} IN ({placeholders})
                    GROUP BY {col}""",
                chunk,
            ).fetchall()
            for r in rows:
                totals[r["phrase"]] = r["n"]
    return totals


def _pull_brand_phrases(db, scope_sides: set[tuple[str, str]]) -> list[dict]:
    """Pull all brand_phrase atoms for the given (source_id, side) set."""
    if not scope_sides:
        return []
    rt_ids = sorted({s for s, _ in scope_sides})
    CHUNK = 500
    out: list[dict] = []
    for i in range(0, len(rt_ids), CHUNK):
        chunk = rt_ids[i : i + CHUNK]
        placeholders = ",".join("?" * len(chunk))
        rows = db.execute(
            f"""SELECT source_id, side, atom_value, source_field
                FROM party_atoms
                WHERE atom_type = 'brand_phrase'
                  AND source_id IN ({placeholders})""",
            chunk,
        ).fetchall()
        for r in rows:
            key = (r["source_id"], r["side"])
            if key in scope_sides:
                out.append({
                    "source_id": r["source_id"],
                    "side": r["side"],
                    "phrase": r["atom_value"],
                    "source_field": r["source_field"],
                })
    return out


def _fetch_party_packages(db, sides: set[tuple[str, str]], limit: int = 80) -> tuple[list[dict], int]:
    """Build a Party Package for each (source_id, side) in `sides`.

    Returns (packages, total). If the side set exceeds `limit`, packages is
    truncated to the first `limit` (sorted by source_id desc — newest RTs first).
    """
    total = len(sides)
    if total == 0:
        return [], 0

    # Sort sides by source_id descending so newer RTs surface first
    sides_list = sorted(sides, key=lambda s: (s[0], s[1]), reverse=True)
    if total > limit:
        sides_list = sides_list[:limit]
    sides_capped = set(sides_list)
    rt_list = sorted({s for s, _ in sides_capped})

    placeholders = ",".join("?" * len(rt_list))

    # Transactions (RT-level fields)
    txns: dict[str, dict] = {}
    for r in db.execute(
        f"""SELECT source_id, sale_date, sale_price, display_address, city, region,
                   seller_trade_name, seller_care_of, seller_companies_json, seller_law_firms_json,
                   buyer_trade_name, buyer_care_of, buyer_companies_json, buyer_law_firms_json
            FROM transactions WHERE source_id IN ({placeholders})""",
        rt_list,
    ):
        txns[r["source_id"]] = dict(r)

    # transaction_parties — multiple rows per (source_id, side)
    party_rows = db.execute(
        f"""SELECT source_id, side, party_name, contact_title, phone, contact_id
            FROM transaction_parties WHERE source_id IN ({placeholders})""",
        rt_list,
    ).fetchall()

    by_side: dict[tuple, list] = defaultdict(list)
    for r in party_rows:
        key = (r["source_id"], r["side"])
        if key in sides_capped:
            by_side[key].append(dict(r))

    # Contacts referenced
    contact_ids = sorted({r["contact_id"] for r in party_rows if r["contact_id"]})
    contacts: dict[str, dict] = {}
    if contact_ids:
        cph = ",".join("?" * len(contact_ids))
        for r in db.execute(
            f"SELECT id, display_name, first_name, last_name, job_title FROM contacts WHERE id IN ({cph})",
            contact_ids,
        ):
            contacts[r["id"]] = dict(r)

    # party_fingerprints — one row per (source_id, side)
    pf_by_side: dict[tuple, dict] = {}
    for r in db.execute(
        f"""SELECT source_id, side, street_number, street_name, street_suffix,
                   street_direction, suite_type, suite_number, city, province, postal_raw
            FROM party_fingerprints WHERE source_id IN ({placeholders})""",
        rt_list,
    ):
        key = (r["source_id"], r["side"])
        if key in sides_capped:
            pf_by_side[key] = dict(r)

    packages: list[dict] = []
    for sid, side in sides_list:
        txn = txns.get(sid)
        if not txn:
            continue
        rows = by_side.get((sid, side), [])

        # Distinct party names (preserve order)
        seen = set()
        party_names: list[str] = []
        contact_info: Optional[dict] = None
        phones_seen: set = set()
        phones: list[str] = []
        for r in rows:
            pn = r["party_name"]
            if pn and pn not in seen:
                seen.add(pn)
                party_names.append(pn)
            if r["contact_id"] and r["contact_id"] in contacts:
                c = contacts[r["contact_id"]]
                # Take the first contact we see for this side
                if contact_info is None:
                    contact_info = {
                        "display_name": c.get("display_name") or " ".join(
                            x for x in [c.get("first_name"), c.get("last_name")] if x
                        ),
                        "title": r.get("contact_title"),
                        "job_title": c.get("job_title"),
                    }
            ph = r.get("phone")
            if ph and ph not in phones_seen:
                phones_seen.add(ph)
                phones.append(ph)

        # Side-specific fields off transactions
        if side == "buyer":
            trade_name = txn.get("buyer_trade_name")
            care_of = txn.get("buyer_care_of")
            companies_json = txn.get("buyer_companies_json")
            law_firms_json = txn.get("buyer_law_firms_json")
        else:
            trade_name = txn.get("seller_trade_name")
            care_of = txn.get("seller_care_of")
            companies_json = txn.get("seller_companies_json")
            law_firms_json = txn.get("seller_law_firms_json")
        companies = json.loads(companies_json) if companies_json else []
        law_firms = json.loads(law_firms_json) if law_firms_json else []

        # Address reconstruction
        pf = pf_by_side.get((sid, side))
        address = None
        if pf:
            street_parts = [
                pf.get("street_number"),
                pf.get("street_name"),
                pf.get("street_suffix"),
                pf.get("street_direction"),
            ]
            street = " ".join(p for p in street_parts if p) or None
            suite_parts = [pf.get("suite_type"), pf.get("suite_number")]
            suite = " ".join(p for p in suite_parts if p) or None
            address = {
                "street": street,
                "suite": suite,
                "city": pf.get("city"),
                "province": pf.get("province"),
                "postal": pf.get("postal_raw"),
            }

        packages.append({
            "source_id": sid,
            "side": side,
            "side_label": "Transferee (Buyer)" if side == "buyer" else "Transferor (Seller)",
            "sale_date": txn.get("sale_date"),
            "sale_price": txn.get("sale_price"),
            "subject_address": txn.get("display_address"),
            "subject_city": txn.get("city"),
            "subject_region": txn.get("region"),
            "party_names": party_names,
            "trade_name": trade_name,
            "care_of": care_of,
            "companies": companies,
            "law_firms": law_firms,
            "contact": contact_info,
            "phones": phones,
            "address": address,
        })

    return packages, total


@router.get("/lattice")
def lattice(
    seed: str = Query(..., min_length=1),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Return the full n-gram lattice for the seed phrase."""
    tokens = _seed_tokens(seed)
    if not tokens:
        raise HTTPException(400, "seed is empty after normalization")
    seed_length = len(tokens)
    if seed_length > MAX_NGRAM_LENGTH:
        raise HTTPException(400, f"seed must be ≤{MAX_NGRAM_LENGTH} tokens after normalization")
    seed_normalized = " ".join(tokens)

    # Step 1: scope sides — all (source_id, side) carrying the seed n-gram
    scope_sides = _fetch_scope_sides(db, seed_normalized, seed_length)
    if not scope_sides:
        return {
            "seed": seed,
            "seed_normalized": seed_normalized,
            "seed_tokens": tokens,
            "scope_rt_count": 0,
            "scope_side_count": 0,
            "leaves": [],
            "ngrams_by_length": {},
        }
    scope_rt_set = {sid for sid, _ in scope_sides}

    # Step 2: brand phrases on those sides → the "leaves"
    phrase_rows = _pull_brand_phrases(db, scope_sides)
    leaf_sides: dict[str, set] = defaultdict(set)
    leaf_source_fields: dict[str, set] = defaultdict(set)
    for r in phrase_rows:
        leaf_sides[r["phrase"]].add((r["source_id"], r["side"]))
        leaf_source_fields[r["phrase"]].add(r["source_field"])

    # Step 3: walk every leaf and emit contiguous sub-n-grams (1..MAX_NGRAM_LENGTH)
    ngram_scope_sides: dict[str, set] = defaultdict(set)
    ngram_leaves: dict[str, set] = defaultdict(set)
    ngram_length: dict[str, int] = {}
    for phrase, sides in leaf_sides.items():
        p_tokens = tokenize_brand(phrase)
        n_tokens = len(p_tokens)
        if n_tokens == 0:
            continue
        for length in range(1, min(n_tokens, MAX_NGRAM_LENGTH) + 1):
            for i in range(n_tokens - length + 1):
                window = p_tokens[i : i + length]
                ngram = " ".join(window)
                ngram_scope_sides[ngram] |= sides
                ngram_leaves[ngram].add(phrase)
                ngram_length[ngram] = length

    # Step 4: bulk-lookup total RT count per n-gram from the appropriate index
    by_length: dict[int, list[str]] = defaultdict(list)
    for ngram, length in ngram_length.items():
        by_length[length].append(ngram)
    totals = _bulk_total_rt_counts(db, by_length)

    # Step 5: shape the response
    ngrams_by_length: dict[str, list[dict]] = {}
    for length in sorted(by_length.keys()):
        bucket = []
        for ngram in by_length[length]:
            sides = ngram_scope_sides[ngram]
            scope_rt_count = len({sid for sid, _ in sides})
            total_rt_count = totals.get(ngram, scope_rt_count)
            if total_rt_count <= 0:
                total_rt_count = scope_rt_count or 1
            purity = scope_rt_count / total_rt_count if total_rt_count else 0.0
            bucket.append({
                "phrase": ngram,
                "length": length,
                "scope_rt_count": scope_rt_count,
                "scope_side_count": len(sides),
                "total_rt_count": total_rt_count,
                "purity": round(purity, 4),
                "leaf_count": len(ngram_leaves[ngram]),
            })
        # Sort: scope_rt desc, then alpha
        bucket.sort(key=lambda x: (-x["scope_rt_count"], x["phrase"]))
        ngrams_by_length[str(length)] = bucket

    # Leaves list (one row per distinct brand phrase)
    leaves_list = []
    for phrase, sides in leaf_sides.items():
        leaves_list.append({
            "phrase": phrase,
            "scope_rt_count": len({sid for sid, _ in sides}),
            "scope_side_count": len(sides),
            "source_fields": sorted(leaf_source_fields[phrase]),
            "token_count": len(tokenize_brand(phrase)),
        })
    leaves_list.sort(key=lambda x: (-x["scope_rt_count"], x["phrase"]))

    return {
        "seed": seed,
        "seed_normalized": seed_normalized,
        "seed_tokens": tokens,
        "scope_rt_count": len(scope_rt_set),
        "scope_side_count": len(scope_sides),
        "leaves": leaves_list,
        "ngrams_by_length": ngrams_by_length,
    }


@router.get("/node")
def node(
    seed: str = Query(..., min_length=1),
    phrase: str = Query(..., min_length=1),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Return detail for one n-gram, scoped to the seed's RT set.

    Returns:
      - rts: list of RT IDs in scope that carry this n-gram
      - leaves: brand-phrase leaves containing this n-gram, with RT count
      - shared_anchors: top addresses/contacts/phones across the n-gram's
        sides, with share% (fraction of sides carrying that anchor)
    """
    seed_tokens = _seed_tokens(seed)
    if not seed_tokens:
        raise HTTPException(400, "seed is empty")
    seed_length = len(seed_tokens)
    seed_normalized = " ".join(seed_tokens)

    ngram_tokens = _seed_tokens(phrase)
    if not ngram_tokens:
        raise HTTPException(400, "phrase is empty")
    ngram_length = len(ngram_tokens)
    if ngram_length > MAX_NGRAM_LENGTH:
        raise HTTPException(400, f"phrase must be ≤{MAX_NGRAM_LENGTH} tokens")
    ngram_normalized = " ".join(ngram_tokens)

    # Sides carrying the seed
    seed_sides = _fetch_scope_sides(db, seed_normalized, seed_length)
    if not seed_sides:
        raise HTTPException(404, "seed has no sides")

    # Sides carrying the n-gram
    ngram_sides_all = _fetch_scope_sides(db, ngram_normalized, ngram_length)

    # Intersection: sides where BOTH the seed and the n-gram appear
    sides_in_scope = seed_sides & ngram_sides_all
    rts_in_scope = sorted({sid for sid, _ in sides_in_scope})

    # Pull brand phrases for the n-gram's in-scope sides
    phrase_rows = _pull_brand_phrases(db, sides_in_scope)

    # Leaves: brand phrases that contain the n-gram as a contiguous token subsequence
    def _contains(haystack_tokens: list[str], needle_tokens: list[str]) -> bool:
        if not needle_tokens or len(haystack_tokens) < len(needle_tokens):
            return False
        n = len(needle_tokens)
        for i in range(len(haystack_tokens) - n + 1):
            if haystack_tokens[i : i + n] == needle_tokens:
                return True
        return False

    leaf_to_sides: dict[str, set] = defaultdict(set)
    leaf_to_source_fields: dict[str, set] = defaultdict(set)
    for r in phrase_rows:
        if _contains(tokenize_brand(r["phrase"]), ngram_tokens):
            leaf_to_sides[r["phrase"]].add((r["source_id"], r["side"]))
            leaf_to_source_fields[r["phrase"]].add(r["source_field"])

    leaves = sorted(
        [
            {
                "phrase": p,
                "rt_count": len({sid for sid, _ in sides}),
                "side_count": len(sides),
                "source_fields": sorted(leaf_to_source_fields[p]),
            }
            for p, sides in leaf_to_sides.items()
        ],
        key=lambda x: (-x["rt_count"], x["phrase"]),
    )

    # Shared anchors: pull party_fingerprints for the n-gram's in-scope sides
    addresses: dict[str, int] = defaultdict(int)
    contacts: dict[str, int] = defaultdict(int)
    phones: dict[str, int] = defaultdict(int)
    side_count = len(sides_in_scope)
    if side_count > 0:
        rt_ids = sorted({sid for sid, _ in sides_in_scope})
        CHUNK = 500
        for i in range(0, len(rt_ids), CHUNK):
            chunk = rt_ids[i : i + CHUNK]
            placeholders = ",".join("?" * len(chunk))
            rows = db.execute(
                f"""SELECT source_id, side, party_address_canonical, contact_fingerprint, phone, suite_number
                    FROM party_fingerprints
                    WHERE source_id IN ({placeholders})""",
                chunk,
            ).fetchall()
            for r in rows:
                key = (r["source_id"], r["side"])
                if key not in sides_in_scope:
                    continue
                if r["party_address_canonical"] and not r["suite_number"]:
                    addresses[r["party_address_canonical"]] += 1
                if r["contact_fingerprint"]:
                    contacts[r["contact_fingerprint"]] += 1
                if r["phone"]:
                    phones[r["phone"]] += 1

    def _top(counter: dict[str, int], k: int = 5) -> list[dict]:
        items = sorted(counter.items(), key=lambda x: -x[1])[:k]
        return [
            {"value": v, "share_count": c, "share_pct": round(c / side_count, 4) if side_count else 0.0}
            for v, c in items
        ]

    # Index totals + purity for THIS n-gram
    total_rt = len({sid for sid, _ in ngram_sides_all})
    scope_rt = len(rts_in_scope)
    purity = scope_rt / total_rt if total_rt else 0.0

    # Leak set: sides where the n-gram appears but the seed does NOT
    leak_sides = ngram_sides_all - seed_sides

    # Full Party Packages — what the user actually wants to eyeball
    scope_packages, scope_total = _fetch_party_packages(db, sides_in_scope, limit=120)
    leak_packages, leak_total = _fetch_party_packages(db, leak_sides, limit=60)

    return {
        "seed": seed,
        "seed_normalized": seed_normalized,
        "phrase": phrase,
        "phrase_normalized": ngram_normalized,
        "length": ngram_length,
        "scope_rt_count": scope_rt,
        "scope_side_count": side_count,
        "total_rt_count": total_rt,
        "purity": round(purity, 4),
        "rts": rts_in_scope,
        "leaves": leaves,
        "shared_anchors": {
            "addresses": _top(addresses),
            "contacts": _top(contacts),
            "phones": _top(phones),
        },
        "scope_packages": scope_packages,
        "scope_packages_total": scope_total,
        "leak_packages": leak_packages,
        "leak_packages_total": leak_total,
    }
