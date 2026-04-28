"""Layer 1 / Silo A Explorer endpoints.

GET /api/explorer/brands                            — list brand_tokens with signals
GET /api/explorer/brands/bigrams                    — list brand bigrams
GET /api/explorer/brands/bigrams/:bigram            — bigram detail
GET /api/explorer/brands/trigrams                   — list brand trigrams
GET /api/explorer/brands/trigrams/:trigram          — trigram detail
GET /api/explorer/brands/:token                     — detail: phrases + party-sides
GET /api/explorer/industry-stopwords                — the curated stopword list
POST /api/explorer/brands/:token/industry-stopword  — user marks a token
DELETE /api/explorer/brands/:token/industry-stopword — user unmarks
GET /api/explorer/phones                            — list phones
GET /api/explorer/phones/:phone                     — phone detail
GET /api/explorer/addresses                         — list address bases
GET /api/explorer/addresses/:key                    — address detail (key = num|name|suffix)
GET /api/explorer/addresses/roots                   — list address roots (num|name)
GET /api/explorer/addresses/roots/:key              — address root detail (key = num|name)
GET /api/explorer/contacts                          — list contact fingerprints
GET /api/explorer/contacts/:fingerprint             — contact detail
GET /api/explorer/auto-groups                       — list auto-groups (Layer 2 Plan A)
GET /api/explorer/auto-groups/:auto_group_id        — auto-group detail
GET /api/explorer/auto-groups/:id/anchors-with-coverage  — anchors + coverage + co-stems
GET /api/explorer/auto-groups/:id/why-tier  — explains which categories passed/missed for tier assignment
GET /api/explorer/auto-groups/:id/parties  — paginated, filterable, sortable parties with anchor_signature
GET /api/explorer/auto-groups/tuning/histogram  — confidence-bucket counts for tuning UI
GET /api/explorer/auto-groups/tuning/close-to-promotion  — groups within a confidence window
GET /api/explorer/auto-groups/tuning/missed-stems  — distinctive/PA 1-grams that didn't promote, with dominance-contest data
"""

from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from typing import Optional

from ..deps import get_db, get_current_user
from cleo.discovery_v2.constants import (
    ANCHOR_SEEDING_SCORE_THRESHOLD,
    ANCHOR_CORROBORATION_SCORE_THRESHOLD,
    TIER_CONFIRMED_MIN_CONFIDENCE,
    TIER_PROBABLE_MIN_CONFIDENCE,
)

router = APIRouter()


@router.get("/brands")
def list_brand_tokens(
    q: Optional[str] = Query(None, description="Substring match on token name"),
    distinctive_only: bool = Query(True),
    include_position_anchors: bool = Query(True),
    filter_reason: Optional[str] = Query(
        None, description="'excluded', 'industry', 'place', 'english', or empty for NULL"
    ),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=500),
    db=Depends(get_db), user=Depends(get_current_user),
):
    where = []
    params: list = []
    if distinctive_only and include_position_anchors:
        where.append("(is_distinctive = 1 OR is_position_anchor = 1)")
    elif distinctive_only:
        where.append("is_distinctive = 1")
    # else: no distinctiveness filter applied (show everything)
    if q:
        where.append("token LIKE ?")
        params.append(f"%{q.lower()}%")
    if filter_reason is not None:
        if filter_reason == "":
            where.append("filter_reason IS NULL")
        else:
            where.append("filter_reason = ?")
            params.append(filter_reason)
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    total = db.execute(
        f"SELECT COUNT(*) FROM brand_token_summary{where_sql}",
        params,
    ).fetchone()[0]

    offset = (page - 1) * per_page
    rows = db.execute(
        f"""SELECT token, idf, n_party_sides, n_distinct_phrases,
                   is_distinctive, is_excluded,
                   wordfreq_zipf, is_english_common, is_place_name,
                   is_industry_stopword, filter_reason,
                   COALESCE(is_position_anchor, 0) AS is_position_anchor,
                   position_consistency,
                   total_child_coverage
            FROM brand_token_summary{where_sql}
            ORDER BY n_party_sides DESC, token ASC
            LIMIT ? OFFSET ?""",
        params + [per_page, offset],
    ).fetchall()

    return {
        "results": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    }


# ─────────────────────────────────────────────────────────────
# Shared helper — hydrate a set of party-side keys with their
# phone/address/contact fields AND brand_phrases per side.
# ─────────────────────────────────────────────────────────────

def _hydrate_party_sides(db, ps_keys: set, *, highlight_token: Optional[str] = None):
    """Given {(source_id, side), ...}, return a list of dicts with per-side
    metadata + brand_phrases.

    If highlight_token is given, each brand_phrase entry includes a
    `contains_token` flag (word-boundary substring match).

    Result order: sale_date DESC, then source_id.
    """
    if not ps_keys:
        return []

    # Fetch per-side metadata
    meta = {}
    for r in db.execute(
        "SELECT source_id, side, sale_date, postal, street_number, street_name, "
        "street_suffix, phone, contact_fingerprint FROM party_fingerprints"
    ):
        key = (r["source_id"], r["side"])
        if key in ps_keys:
            meta[key] = dict(r)

    # Fetch brand_phrases for these party-sides
    phrases_by_side: dict = {}
    for r in db.execute(
        "SELECT source_id, side, atom_value, source_field "
        "FROM party_atoms WHERE atom_type = 'brand_phrase'"
    ):
        key = (r["source_id"], r["side"])
        if key not in ps_keys:
            continue
        val = r["atom_value"]
        entry = {
            "phrase": val,
            "source_field": r["source_field"],
            "contains_token": False,
        }
        if highlight_token:
            entry["contains_token"] = (
                (" " + val + " ").find(" " + highlight_token + " ") != -1
            )
        phrases_by_side.setdefault(key, []).append(entry)

    def _field_order(entry):
        order = {"party_name": 0, "trade_name": 1, "care_of": 2,
                 "companies_json": 3, "law_firms_json": 4}
        return order.get(entry["source_field"], 99)

    out = []
    for key in ps_keys:
        m = meta.get(key)
        if not m:
            # party-side key not in party_fingerprints — skip
            continue
        entries = phrases_by_side.get(key, [])
        # Dedup same (phrase, source_field) then sort
        seen = set()
        deduped = []
        for e in entries:
            k = (e["phrase"], e["source_field"])
            if k in seen:
                continue
            seen.add(k)
            deduped.append(e)
        deduped.sort(key=lambda e: (_field_order(e), e["phrase"]))
        out.append({**m, "brand_phrases": deduped})

    out.sort(
        key=lambda r: (r.get("sale_date") or ""),
        reverse=True,
    )
    return out


# ─────────────────────────────────────────────────────────────
# Brands — 2gram / 3gram
# These MUST be registered before /brands/{token} to avoid the
# generic path param swallowing "bigrams" and "trigrams".
# ─────────────────────────────────────────────────────────────

def _list_brand_ngrams(
    table: str, col: str, q, distinctive_only, page, per_page, db,
):
    where = []
    params: list = []
    if distinctive_only:
        where.append("is_distinctive = 1")
    if q:
        where.append(f"{col} LIKE ?")
        params.append(f"%{q.lower()}%")
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    total = db.execute(
        f"SELECT COUNT(*) FROM {table}{where_sql}", params
    ).fetchone()[0]

    # Map column name → token columns to SELECT
    TOKEN_COLS = {
        "bigram":   "token_a, token_b",
        "trigram":  "token_a, token_b, token_c",
        "fourgram": "token_a, token_b, token_c, token_d",
        "fivegram": "token_a, token_b, token_c, token_d, token_e",
    }
    token_cols = TOKEN_COLS[col]

    offset = (page - 1) * per_page
    rows = db.execute(
        f"""SELECT {col}, {token_cols}, idf, n_party_sides, n_distinct_phrases,
                   any_token_distinctive, any_token_excluded,
                   all_english, all_place, all_industry, is_distinctive
            FROM {table}{where_sql}
            ORDER BY n_party_sides DESC, {col} ASC
            LIMIT ? OFFSET ?""",
        params + [per_page, offset],
    ).fetchall()

    return {
        "results": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    }


# ─────────────────────────────────────────────────────────────
# Containment helpers — "contains" (n-1 level) and
# "extended_by" (n+1 level) for any n-gram detail response.
# ─────────────────────────────────────────────────────────────

NGRAM_LEVELS = {
    "1gram":     {"summary": "brand_token_summary",       "key": "token",    "tokens": []},
    "2gram":     {"summary": "brand_bigram_summary",      "key": "bigram",   "tokens": ["token_a", "token_b"]},
    "3gram":     {"summary": "brand_trigram_summary",     "key": "trigram",  "tokens": ["token_a", "token_b", "token_c"]},
    "4gram":     {"summary": "brand_fourgram_summary",    "key": "fourgram", "tokens": ["token_a", "token_b", "token_c", "token_d"]},
    "5gram":     {"summary": "brand_fivegram_summary",    "key": "fivegram", "tokens": ["token_a", "token_b", "token_c", "token_d", "token_e"]},
    "long-form": {"summary": "brand_long_phrase_summary", "key": "phrase",   "tokens": []},
}


def _ngram_n_party_sides(db, level: str, value: str) -> int:
    """One-shot lookup of n_party_sides for a given (level, value)."""
    info = NGRAM_LEVELS[level]
    row = db.execute(
        f"SELECT n_party_sides FROM {info['summary']} WHERE {info['key']} = ?",
        (value,),
    ).fetchone()
    return row["n_party_sides"] if row else 0


def _compute_containment(db, level: str, value: str, *, limit: int = 50) -> dict:
    """Return {contains: [...], extended_by: [...]} for the given (level, value).

    Each entry: {"value": str, "level": str, "n_party_sides": int}.

    Containment rules:
      - 1gram  contains: []      ; extended_by: 2grams that contain this token
      - 2gram  contains: 1grams  ; extended_by: 3grams
      - 3gram  contains: 2grams  ; extended_by: 4grams
      - 4gram  contains: 3grams  ; extended_by: 5grams
      - 5gram  contains: 4grams  ; extended_by: long-form phrases containing this 5gram
      - long-form contains: 5-gram windows ; extended_by: []
    """
    contains: list = []
    extended_by: list = []

    if level == "1gram":
        # extended_by: 2grams where token_a = value OR token_b = value
        rows = db.execute(
            "SELECT bigram, n_party_sides FROM brand_bigram_summary "
            "WHERE token_a = ? OR token_b = ? "
            "ORDER BY n_party_sides DESC LIMIT ?",
            (value, value, limit),
        ).fetchall()
        extended_by = [
            {"value": r["bigram"], "level": "2gram", "n_party_sides": r["n_party_sides"]}
            for r in rows
        ]

    elif level == "2gram":
        row = db.execute(
            "SELECT token_a, token_b FROM brand_bigram_summary WHERE bigram = ?",
            (value,),
        ).fetchone()
        if row:
            for tok in (row["token_a"], row["token_b"]):
                contains.append({
                    "value": tok, "level": "1gram",
                    "n_party_sides": _ngram_n_party_sides(db, "1gram", tok),
                })
            a, b = row["token_a"], row["token_b"]
            rows = db.execute(
                "SELECT trigram, n_party_sides FROM brand_trigram_summary "
                "WHERE (token_a = ? AND token_b = ?) "
                "   OR (token_b = ? AND token_c = ?) "
                "ORDER BY n_party_sides DESC LIMIT ?",
                (a, b, a, b, limit),
            ).fetchall()
            extended_by = [
                {"value": r["trigram"], "level": "3gram", "n_party_sides": r["n_party_sides"]}
                for r in rows
            ]

    elif level == "3gram":
        row = db.execute(
            "SELECT token_a, token_b, token_c FROM brand_trigram_summary WHERE trigram = ?",
            (value,),
        ).fetchone()
        if row:
            a, b, c = row["token_a"], row["token_b"], row["token_c"]
            for bigram_str in (f"{a} {b}", f"{b} {c}"):
                contains.append({
                    "value": bigram_str, "level": "2gram",
                    "n_party_sides": _ngram_n_party_sides(db, "2gram", bigram_str),
                })
            rows = db.execute(
                "SELECT fourgram, n_party_sides FROM brand_fourgram_summary "
                "WHERE (token_a = ? AND token_b = ? AND token_c = ?) "
                "   OR (token_b = ? AND token_c = ? AND token_d = ?) "
                "ORDER BY n_party_sides DESC LIMIT ?",
                (a, b, c, a, b, c, limit),
            ).fetchall()
            extended_by = [
                {"value": r["fourgram"], "level": "4gram", "n_party_sides": r["n_party_sides"]}
                for r in rows
            ]

    elif level == "4gram":
        row = db.execute(
            "SELECT token_a, token_b, token_c, token_d "
            "FROM brand_fourgram_summary WHERE fourgram = ?",
            (value,),
        ).fetchone()
        if row:
            a, b, c, d = row["token_a"], row["token_b"], row["token_c"], row["token_d"]
            for tg in (f"{a} {b} {c}", f"{b} {c} {d}"):
                contains.append({
                    "value": tg, "level": "3gram",
                    "n_party_sides": _ngram_n_party_sides(db, "3gram", tg),
                })
            rows = db.execute(
                "SELECT fivegram, n_party_sides FROM brand_fivegram_summary "
                "WHERE (token_a = ? AND token_b = ? AND token_c = ? AND token_d = ?) "
                "   OR (token_b = ? AND token_c = ? AND token_d = ? AND token_e = ?) "
                "ORDER BY n_party_sides DESC LIMIT ?",
                (a, b, c, d, a, b, c, d, limit),
            ).fetchall()
            extended_by = [
                {"value": r["fivegram"], "level": "5gram", "n_party_sides": r["n_party_sides"]}
                for r in rows
            ]

    elif level == "5gram":
        row = db.execute(
            "SELECT token_a, token_b, token_c, token_d, token_e "
            "FROM brand_fivegram_summary WHERE fivegram = ?",
            (value,),
        ).fetchone()
        if row:
            a, b, c, d, e = row["token_a"], row["token_b"], row["token_c"], row["token_d"], row["token_e"]
            for fg in (f"{a} {b} {c} {d}", f"{b} {c} {d} {e}"):
                contains.append({
                    "value": fg, "level": "4gram",
                    "n_party_sides": _ngram_n_party_sides(db, "4gram", fg),
                })
        # extended_by: long-form phrases containing this 5gram (word-boundary)
        rows = db.execute(
            "SELECT phrase, n_party_sides FROM brand_long_phrase_summary "
            "WHERE (' ' || phrase || ' ') LIKE '% ' || ? || ' %' "
            "ORDER BY n_party_sides DESC LIMIT ?",
            (value, limit),
        ).fetchall()
        extended_by = [
            {"value": r["phrase"], "level": "long-form", "n_party_sides": r["n_party_sides"]}
            for r in rows
        ]

    elif level == "long-form":
        # contains: every consecutive 5-token window of the phrase
        tokens = value.split(" ")
        seen: set = set()
        for i in range(len(tokens) - 4):
            window = " ".join(tokens[i:i + 5])
            if window in seen:
                continue
            seen.add(window)
            contains.append({
                "value": window, "level": "5gram",
                "n_party_sides": _ngram_n_party_sides(db, "5gram", window),
            })
        # extended_by: nothing (long-form is the last level)

    return {"contains": contains, "extended_by": extended_by}


# ─────────────────────────────────────────────────────────────
# Brand Family + Cross-silo Search helpers
# All of these MUST be registered before /brands/{token}.
# ─────────────────────────────────────────────────────────────

NGRAM_LEVELS_LIST = ["1gram", "2gram", "3gram", "4gram", "5gram", "long-form"]

LEVEL_TO_TABLE = {
    "1gram":     ("brand_token_summary",        "token"),
    "2gram":     ("brand_bigram_summary",       "bigram"),
    "3gram":     ("brand_trigram_summary",      "trigram"),
    "4gram":     ("brand_fourgram_summary",     "fourgram"),
    "5gram":     ("brand_fivegram_summary",     "fivegram"),
    "long-form": ("brand_long_phrase_summary",  "phrase"),
}


def _seed_constituent_tokens(db, level: str, value: str) -> list:
    """Return the constituent tokens for a seed.
    For 1-gram: [value].
    For 2/3/4/5-gram: token_a, token_b, ... from the summary row.
    For long-form: split phrase on spaces.
    """
    if level == "1gram":
        return [value]
    if level == "long-form":
        return value.split(" ")
    table, _ = LEVEL_TO_TABLE[level]
    cols = {"2gram": "token_a, token_b",
            "3gram": "token_a, token_b, token_c",
            "4gram": "token_a, token_b, token_c, token_d",
            "5gram": "token_a, token_b, token_c, token_d, token_e"}[level]
    pk = LEVEL_TO_TABLE[level][1]
    row = db.execute(f"SELECT {cols} FROM {table} WHERE {pk} = ?", (value,)).fetchone()
    if row is None:
        return []
    return list(dict(row).values())


def _ngrams_containing_substring(db, seed_value: str, max_per_level: int = 200) -> list:
    """Find n-grams (across all 6 silos, levels longer than the seed) whose
    value contains seed_value as a contiguous word run.

    Used for Tight family.
    """
    out = []
    for level in NGRAM_LEVELS_LIST:
        table, pk = LEVEL_TO_TABLE[level]
        # Exclude the seed itself (level + value match) — we want descendants.
        rows = db.execute(
            f"SELECT {pk} AS value, n_party_sides "
            f"FROM {table} "
            f"WHERE (' ' || {pk} || ' ') LIKE ('% ' || ? || ' %') "
            f"  AND {pk} != ? "
            f"ORDER BY n_party_sides DESC LIMIT ?",
            (seed_value, seed_value, max_per_level),
        ).fetchall()
        for r in rows:
            out.append({
                "value": r["value"],
                "level": level,
                "n_party_sides": r["n_party_sides"],
            })
    # Already sorted within level; final sort by sides desc across levels
    out.sort(key=lambda x: -x["n_party_sides"])
    return out


def _per_token_loose_count(db, token: str) -> int:
    """Count of n-grams (across 2/3/4/5-gram + long-form) that contain `token`
    as a constituent. The 1-gram silo just contains the token itself."""
    total = 0
    # 2-5gram silos: check each token column
    for level, (table, _) in LEVEL_TO_TABLE.items():
        if level in ("1gram", "long-form"):
            continue
        n_pos = {"2gram": 2, "3gram": 3, "4gram": 4, "5gram": 5}[level]
        token_cols = " OR ".join(f"token_{c} = ?" for c in "abcde"[:n_pos])
        params = [token] * n_pos
        n = db.execute(
            f"SELECT COUNT(*) FROM {table} WHERE {token_cols}", params
        ).fetchone()[0]
        total += n
    # Long-form: word-boundary substring
    n = db.execute(
        "SELECT COUNT(*) FROM brand_long_phrase_summary "
        "WHERE (' ' || phrase || ' ') LIKE ('% ' || ? || ' %')",
        (token,),
    ).fetchone()[0]
    total += n
    return total


def _per_token_loose_preview(db, token: str, limit: int = 25) -> list:
    """Return up to `limit` top n-grams (by n_party_sides) containing `token`
    as a constituent. Includes 1-gram itself (the token row) for completeness."""
    out = []
    # 1-gram: the token itself
    row = db.execute(
        "SELECT token AS value, n_party_sides FROM brand_token_summary WHERE token = ?",
        (token,),
    ).fetchone()
    if row is not None:
        out.append({"value": row["value"], "level": "1gram", "n_party_sides": row["n_party_sides"]})
    # 2..5-gram
    for level, (table, pk) in LEVEL_TO_TABLE.items():
        if level in ("1gram", "long-form"):
            continue
        n_pos = {"2gram": 2, "3gram": 3, "4gram": 4, "5gram": 5}[level]
        token_cols = " OR ".join(f"token_{c} = ?" for c in "abcde"[:n_pos])
        params = [token] * n_pos
        rows = db.execute(
            f"SELECT {pk} AS value, n_party_sides FROM {table} "
            f"WHERE {token_cols} ORDER BY n_party_sides DESC LIMIT ?",
            params + [limit],
        ).fetchall()
        for r in rows:
            out.append({"value": r["value"], "level": level, "n_party_sides": r["n_party_sides"]})
    # Long-form
    rows = db.execute(
        "SELECT phrase AS value, n_party_sides FROM brand_long_phrase_summary "
        "WHERE (' ' || phrase || ' ') LIKE ('% ' || ? || ' %') "
        "ORDER BY n_party_sides DESC LIMIT ?",
        (token, limit),
    ).fetchall()
    for r in rows:
        out.append({"value": r["value"], "level": "long-form", "n_party_sides": r["n_party_sides"]})
    out.sort(key=lambda x: -x["n_party_sides"])
    return out[:limit]


@router.get("/brands/family")
def brand_family(
    seed_value: str = Query(...),
    seed_level: str = Query(...),
    db=Depends(get_db), user=Depends(get_current_user),
):
    if seed_level not in NGRAM_LEVELS_LIST:
        raise HTTPException(status_code=400, detail=f"Invalid seed_level: {seed_level!r}")

    tight = _ngrams_containing_substring(db, seed_value)

    constituents = _seed_constituent_tokens(db, seed_level, seed_value)
    loose_sections = []
    for token in constituents:
        loose_sections.append({
            "token": token,
            "n_total": _per_token_loose_count(db, token),
            "preview": _per_token_loose_preview(db, token, limit=25),
        })

    return {
        "seed_value": seed_value,
        "seed_level": seed_level,
        "tight": tight,
        "loose_sections": loose_sections,
    }


@router.get("/brands/family/loose")
def brand_family_loose_full(
    token: str = Query(...),
    page: int = Query(1, ge=1),
    per_page: int = Query(100, ge=1, le=500),
    db=Depends(get_db), user=Depends(get_current_user),
):
    """Full paginated list of n-grams (any level) containing the given token
    as a constituent, sorted by n_party_sides desc."""
    rows = []
    # 1-gram: just the token
    r = db.execute(
        "SELECT token AS value, '1gram' AS level, n_party_sides FROM brand_token_summary WHERE token = ?",
        (token,),
    ).fetchone()
    if r is not None:
        rows.append({"value": r["value"], "level": r["level"], "n_party_sides": r["n_party_sides"]})

    for level, (table, pk) in LEVEL_TO_TABLE.items():
        if level in ("1gram", "long-form"):
            continue
        n_pos = {"2gram": 2, "3gram": 3, "4gram": 4, "5gram": 5}[level]
        token_cols = " OR ".join(f"token_{c} = ?" for c in "abcde"[:n_pos])
        for r in db.execute(
            f"SELECT {pk} AS value, n_party_sides FROM {table} WHERE {token_cols}",
            [token] * n_pos,
        ):
            rows.append({"value": r["value"], "level": level, "n_party_sides": r["n_party_sides"]})

    for r in db.execute(
        "SELECT phrase AS value, n_party_sides FROM brand_long_phrase_summary "
        "WHERE (' ' || phrase || ' ') LIKE ('% ' || ? || ' %')",
        (token,),
    ):
        rows.append({"value": r["value"], "level": "long-form", "n_party_sides": r["n_party_sides"]})

    rows.sort(key=lambda x: -x["n_party_sides"])
    total = len(rows)
    offset = (page - 1) * per_page
    page_rows = rows[offset:offset + per_page]

    return {
        "token": token,
        "results": page_rows,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    }


@router.get("/brands/search")
def brand_search(
    q: str = Query(...),
    per_level: int = Query(25, ge=1, le=100),
    db=Depends(get_db), user=Depends(get_current_user),
):
    """Substring search across all 6 brand silos. Returns results grouped by level."""
    like = "%" + q.lower() + "%"
    out = {}
    for level, (table, pk) in LEVEL_TO_TABLE.items():
        if level == "1gram":
            rows = db.execute(
                f"SELECT {pk} AS value, n_party_sides, is_distinctive, "
                "       COALESCE(is_position_anchor, 0) AS is_position_anchor "
                f"FROM {table} WHERE {pk} LIKE ? "
                f"ORDER BY n_party_sides DESC LIMIT ?",
                (like, per_level),
            ).fetchall()
        else:
            rows = db.execute(
                f"SELECT {pk} AS value, n_party_sides, is_distinctive "
                f"FROM {table} WHERE {pk} LIKE ? "
                f"ORDER BY n_party_sides DESC LIMIT ?",
                (like, per_level),
            ).fetchall()
        out[level] = [dict(r) for r in rows]
    return {"q": q, "results_by_level": out}


@router.get("/brands/bigrams")
def list_bigrams(
    q: Optional[str] = Query(None),
    distinctive_only: bool = Query(True),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=500),
    db=Depends(get_db), user=Depends(get_current_user),
):
    return _list_brand_ngrams("brand_bigram_summary", "bigram",
                              q, distinctive_only, page, per_page, db)


@router.get("/brands/trigrams")
def list_trigrams(
    q: Optional[str] = Query(None),
    distinctive_only: bool = Query(True),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=500),
    db=Depends(get_db), user=Depends(get_current_user),
):
    return _list_brand_ngrams("brand_trigram_summary", "trigram",
                              q, distinctive_only, page, per_page, db)


@router.get("/brands/bigrams/{bigram}")
def bigram_detail(
    bigram: str, db=Depends(get_db), user=Depends(get_current_user),
):
    summary = db.execute(
        """SELECT bigram, token_a, token_b, idf, n_party_sides, n_distinct_phrases,
                  any_token_distinctive, any_token_excluded,
                  all_english, all_place, all_industry, is_distinctive
           FROM brand_bigram_summary WHERE bigram = ?""",
        (bigram,),
    ).fetchone()
    if summary is None:
        raise HTTPException(status_code=404, detail=f"Unknown bigram: {bigram!r}")

    # Distinct phrases in party_atoms that CONTAIN this bigram as consecutive words.
    phrases = [
        r["atom_value"] for r in db.execute(
            """SELECT DISTINCT atom_value FROM party_atoms
               WHERE atom_type = 'brand_phrase'
                 AND (' ' || atom_value || ' ') LIKE ('% ' || ? || ' %')
               ORDER BY atom_value""",
            (bigram,),
        )
    ]

    ps_keys = {
        (r["source_id"], r["side"]) for r in db.execute(
            "SELECT source_id, side FROM brand_bigram_index WHERE bigram = ?",
            (bigram,),
        )
    }
    party_sides = _hydrate_party_sides(db, ps_keys, highlight_token=bigram)

    cont = _compute_containment(db, "2gram", bigram)
    return {**dict(summary), "phrases": phrases, "party_sides": party_sides,
            "contains": cont["contains"], "extended_by": cont["extended_by"]}


@router.get("/brands/trigrams/{trigram}")
def trigram_detail(
    trigram: str, db=Depends(get_db), user=Depends(get_current_user),
):
    summary = db.execute(
        """SELECT trigram, token_a, token_b, token_c, idf, n_party_sides, n_distinct_phrases,
                  any_token_distinctive, any_token_excluded,
                  all_english, all_place, all_industry, is_distinctive
           FROM brand_trigram_summary WHERE trigram = ?""",
        (trigram,),
    ).fetchone()
    if summary is None:
        raise HTTPException(status_code=404, detail=f"Unknown trigram: {trigram!r}")

    phrases = [
        r["atom_value"] for r in db.execute(
            """SELECT DISTINCT atom_value FROM party_atoms
               WHERE atom_type = 'brand_phrase'
                 AND (' ' || atom_value || ' ') LIKE ('% ' || ? || ' %')
               ORDER BY atom_value""",
            (trigram,),
        )
    ]

    ps_keys = {
        (r["source_id"], r["side"]) for r in db.execute(
            "SELECT source_id, side FROM brand_trigram_index WHERE trigram = ?",
            (trigram,),
        )
    }
    party_sides = _hydrate_party_sides(db, ps_keys, highlight_token=trigram)

    cont = _compute_containment(db, "3gram", trigram)
    return {**dict(summary), "phrases": phrases, "party_sides": party_sides,
            "contains": cont["contains"], "extended_by": cont["extended_by"]}


# ─────────────────────────────────────────────────────────────
# Brands — 4gram / 5gram / long-form
# These MUST also be registered before /brands/{token}.
# ─────────────────────────────────────────────────────────────

@router.get("/brands/4grams")
def list_fourgrams(
    q: Optional[str] = Query(None),
    distinctive_only: bool = Query(True),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=500),
    db=Depends(get_db), user=Depends(get_current_user),
):
    return _list_brand_ngrams("brand_fourgram_summary", "fourgram",
                              q, distinctive_only, page, per_page, db)


@router.get("/brands/5grams")
def list_fivegrams(
    q: Optional[str] = Query(None),
    distinctive_only: bool = Query(True),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=500),
    db=Depends(get_db), user=Depends(get_current_user),
):
    return _list_brand_ngrams("brand_fivegram_summary", "fivegram",
                              q, distinctive_only, page, per_page, db)


@router.get("/brands/4grams/{fourgram}")
def fourgram_detail(
    fourgram: str, db=Depends(get_db), user=Depends(get_current_user),
):
    summary = db.execute(
        """SELECT fourgram, token_a, token_b, token_c, token_d,
                  idf, n_party_sides, n_distinct_phrases,
                  any_token_distinctive, any_token_excluded,
                  all_english, all_place, all_industry, is_distinctive
           FROM brand_fourgram_summary WHERE fourgram = ?""",
        (fourgram,),
    ).fetchone()
    if summary is None:
        raise HTTPException(status_code=404, detail=f"Unknown fourgram: {fourgram!r}")

    phrases = [
        r["atom_value"] for r in db.execute(
            """SELECT DISTINCT atom_value FROM party_atoms
               WHERE atom_type = 'brand_phrase'
                 AND (' ' || atom_value || ' ') LIKE ('% ' || ? || ' %')
               ORDER BY atom_value""",
            (fourgram,),
        )
    ]

    ps_keys = {
        (r["source_id"], r["side"]) for r in db.execute(
            "SELECT source_id, side FROM brand_fourgram_index WHERE fourgram = ?",
            (fourgram,),
        )
    }
    party_sides = _hydrate_party_sides(db, ps_keys, highlight_token=fourgram)

    cont = _compute_containment(db, "4gram", fourgram)
    return {**dict(summary), "phrases": phrases, "party_sides": party_sides,
            "contains": cont["contains"], "extended_by": cont["extended_by"]}


@router.get("/brands/5grams/{fivegram}")
def fivegram_detail(
    fivegram: str, db=Depends(get_db), user=Depends(get_current_user),
):
    summary = db.execute(
        """SELECT fivegram, token_a, token_b, token_c, token_d, token_e,
                  idf, n_party_sides, n_distinct_phrases,
                  any_token_distinctive, any_token_excluded,
                  all_english, all_place, all_industry, is_distinctive
           FROM brand_fivegram_summary WHERE fivegram = ?""",
        (fivegram,),
    ).fetchone()
    if summary is None:
        raise HTTPException(status_code=404, detail=f"Unknown fivegram: {fivegram!r}")

    phrases = [
        r["atom_value"] for r in db.execute(
            """SELECT DISTINCT atom_value FROM party_atoms
               WHERE atom_type = 'brand_phrase'
                 AND (' ' || atom_value || ' ') LIKE ('% ' || ? || ' %')
               ORDER BY atom_value""",
            (fivegram,),
        )
    ]

    ps_keys = {
        (r["source_id"], r["side"]) for r in db.execute(
            "SELECT source_id, side FROM brand_fivegram_index WHERE fivegram = ?",
            (fivegram,),
        )
    }
    party_sides = _hydrate_party_sides(db, ps_keys, highlight_token=fivegram)

    cont = _compute_containment(db, "5gram", fivegram)
    return {**dict(summary), "phrases": phrases, "party_sides": party_sides,
            "contains": cont["contains"], "extended_by": cont["extended_by"]}


@router.get("/brands/long-phrases")
def list_long_phrases(
    q: Optional[str] = Query(None),
    distinctive_only: bool = Query(True),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=500),
    db=Depends(get_db), user=Depends(get_current_user),
):
    where = []
    params: list = []
    if distinctive_only:
        where.append("is_distinctive = 1")
    if q:
        where.append("phrase LIKE ?")
        params.append(f"%{q.lower()}%")
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    total = db.execute(
        f"SELECT COUNT(*) FROM brand_long_phrase_summary{where_sql}", params
    ).fetchone()[0]

    offset = (page - 1) * per_page
    rows = db.execute(
        f"""SELECT phrase, n_tokens, idf, n_party_sides, n_distinct_source_phrases,
                   any_token_distinctive, any_token_excluded,
                   all_english, all_place, all_industry, is_distinctive
            FROM brand_long_phrase_summary{where_sql}
            ORDER BY n_party_sides DESC, phrase ASC
            LIMIT ? OFFSET ?""",
        params + [per_page, offset],
    ).fetchall()

    return {
        "results": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    }


@router.get("/brands/long-phrases/{phrase}")
def long_phrase_detail(
    phrase: str, db=Depends(get_db), user=Depends(get_current_user),
):
    summary = db.execute(
        """SELECT phrase, n_tokens, idf, n_party_sides, n_distinct_source_phrases,
                  any_token_distinctive, any_token_excluded,
                  all_english, all_place, all_industry, is_distinctive
           FROM brand_long_phrase_summary WHERE phrase = ?""",
        (phrase,),
    ).fetchone()
    if summary is None:
        raise HTTPException(status_code=404, detail=f"Unknown long-form phrase: {phrase!r}")

    raw_phrases = [
        r["atom_value"] for r in db.execute(
            """SELECT DISTINCT atom_value FROM party_atoms
               WHERE atom_type = 'brand_phrase'
                 AND atom_value LIKE ('%' || ? || '%')
               ORDER BY atom_value""",
            (phrase,),
        )
    ]

    ps_keys = {
        (r["source_id"], r["side"]) for r in db.execute(
            "SELECT source_id, side FROM brand_long_phrase_index WHERE phrase = ?",
            (phrase,),
        )
    }
    party_sides = _hydrate_party_sides(db, ps_keys, highlight_token=phrase)

    cont = _compute_containment(db, "long-form", phrase)
    return {**dict(summary), "phrases": raw_phrases, "party_sides": party_sides,
            "contains": cont["contains"], "extended_by": cont["extended_by"]}


# ─────────────────────────────────────────────────────────────
# Brands — unigram detail (generic {token} — must come AFTER
# the specific /brands/bigrams and /brands/trigrams routes)
# ─────────────────────────────────────────────────────────────

@router.get("/brands/{token}")
def brand_token_detail(
    token: str,
    db=Depends(get_db), user=Depends(get_current_user),
):
    summary_row = db.execute(
        """SELECT token, idf, n_party_sides, n_distinct_phrases,
                  is_distinctive, is_excluded,
                  wordfreq_zipf, is_english_common, is_place_name,
                  is_industry_stopword, filter_reason,
                  COALESCE(is_position_anchor, 0) AS is_position_anchor,
                  position_consistency,
                  total_child_coverage
           FROM brand_token_summary WHERE token = ?""",
        (token,),
    ).fetchone()
    if summary_row is None:
        raise HTTPException(status_code=404, detail=f"Unknown brand_token: {token!r}")

    # Phrases that ACTUALLY contain the token as a word. The previous version
    # returned every phrase on any party-side carrying the token, which picked
    # up unrelated co-phrases (e.g., party_name='11 yorkville partners' +
    # trade_name='riocan holdings' would have leaked '11 yorkville partners'
    # into the riocan detail view).
    phrases = [
        r["atom_value"] for r in db.execute(
            """SELECT DISTINCT atom_value
               FROM party_atoms
               WHERE atom_type = 'brand_phrase'
                 AND (' ' || atom_value || ' ') LIKE ('% ' || ? || ' %')
               ORDER BY atom_value""",
            (token,),
        )
    ]

    party_side_rows = db.execute(
        """SELECT bti.source_id, bti.side,
                  pf.sale_date, pf.postal,
                  pf.street_number, pf.street_name, pf.street_suffix,
                  pf.phone, pf.contact_fingerprint
           FROM brand_token_index bti
           LEFT JOIN party_fingerprints pf
             ON pf.source_id = bti.source_id AND pf.side = bti.side
           WHERE bti.token = ?
           ORDER BY pf.sale_date DESC, bti.source_id""",
        (token,),
    ).fetchall()

    # Gather every brand_phrase carried on these party-sides, grouped by
    # (source_id, side). Each phrase keeps its source_field (party_name /
    # trade_name / care_of / companies_json / law_firms_json) and a flag
    # indicating whether it contains the queried token as a whole word.
    ps_keys = {(r["source_id"], r["side"]) for r in party_side_rows}
    phrases_by_side: dict = {}
    if ps_keys:
        rows = db.execute(
            "SELECT source_id, side, atom_value, source_field "
            "FROM party_atoms WHERE atom_type = 'brand_phrase'"
        ).fetchall()
        for r in rows:
            key = (r["source_id"], r["side"])
            if key not in ps_keys:
                continue
            val = r["atom_value"]
            contains = (" " + val + " ").find(" " + token + " ") != -1
            phrases_by_side.setdefault(key, []).append({
                "phrase": val,
                "source_field": r["source_field"],
                "contains_token": contains,
            })

    def _field_order(entry):
        # Display order for the source_field tags.
        order = {
            "party_name": 0, "trade_name": 1, "care_of": 2,
            "companies_json": 3, "law_firms_json": 4,
        }
        return order.get(entry["source_field"], 99)

    party_sides = []
    for r in party_side_rows:
        key = (r["source_id"], r["side"])
        entries = phrases_by_side.get(key, [])
        # Dedup same (phrase, source_field) pairs and sort by field then phrase
        seen = set()
        deduped = []
        for e in entries:
            k = (e["phrase"], e["source_field"])
            if k in seen:
                continue
            seen.add(k)
            deduped.append(e)
        deduped.sort(key=lambda e: (_field_order(e), e["phrase"]))
        party_sides.append({**dict(r), "brand_phrases": deduped})

    cont = _compute_containment(db, "1gram", token)
    return {
        **dict(summary_row),
        "phrases": phrases,
        "party_sides": party_sides,
        "contains": cont["contains"],
        "extended_by": cont["extended_by"],
    }


@router.get("/industry-stopwords")
def list_industry_stopwords(db=Depends(get_db), user=Depends(get_current_user)):
    rows = db.execute(
        "SELECT token, added_by, added_at, source FROM industry_stopwords "
        "ORDER BY source DESC, added_at DESC"
    ).fetchall()
    return {"results": [dict(r) for r in rows]}


@router.post("/brands/{token}/industry-stopword", status_code=204)
def mark_industry_stopword(
    token: str, db=Depends(get_db), user=Depends(get_current_user)
):
    added_by = user.get("email") if isinstance(user, dict) else str(user)
    db.execute(
        "INSERT OR REPLACE INTO industry_stopwords (token, added_by, source) "
        "VALUES (?, ?, 'user')",
        (token, added_by),
    )
    # Mirror into brand_token_summary so the list reflects this immediately
    # without requiring a full rebuild.
    db.execute(
        "UPDATE brand_token_summary "
        "SET is_industry_stopword = 1, is_distinctive = 0, "
        "    filter_reason = CASE WHEN is_excluded = 1 THEN 'excluded' ELSE 'industry' END "
        "WHERE token = ?",
        (token,),
    )
    db.commit()
    return Response(status_code=204)


@router.delete("/brands/{token}/industry-stopword", status_code=204)
def unmark_industry_stopword(
    token: str, db=Depends(get_db), user=Depends(get_current_user)
):
    db.execute("DELETE FROM industry_stopwords WHERE token = ?", (token,))

    row = db.execute(
        """SELECT idf, is_excluded, is_english_common, is_place_name
           FROM brand_token_summary WHERE token = ?""",
        (token,),
    ).fetchone()
    if row:
        from cleo.discovery_v2.config import CALIBRATION
        min_idf = CALIBRATION["exact_brand_token"]["min_idf"]
        if row["is_excluded"]:
            reason, distinctive = "excluded", 0
        elif row["is_english_common"]:
            reason, distinctive = "english", 0
        elif row["is_place_name"]:
            reason, distinctive = "place", 0
        elif row["idf"] < min_idf:
            reason, distinctive = None, 0
        else:
            reason, distinctive = None, 1
        db.execute(
            """UPDATE brand_token_summary SET is_industry_stopword = 0,
               is_distinctive = ?, filter_reason = ? WHERE token = ?""",
            (distinctive, reason, token),
        )
    db.commit()
    return Response(status_code=204)


@router.get("/places")
def list_places(db=Depends(get_db), user=Depends(get_current_user)):
    rows = db.execute(
        "SELECT token, added_by, added_at, source FROM places "
        "ORDER BY source DESC, added_at DESC"
    ).fetchall()
    return {"results": [dict(r) for r in rows]}


@router.post("/brands/{token}/place", status_code=204)
def mark_place(
    token: str, db=Depends(get_db), user=Depends(get_current_user)
):
    added_by = user.get("email") if isinstance(user, dict) else str(user)
    db.execute(
        "INSERT OR REPLACE INTO places (token, added_by, source) "
        "VALUES (?, ?, 'user')",
        (token, added_by),
    )
    # Reflect in brand_token_summary immediately.
    # Place takes precedence OVER english but UNDER industry and excluded.
    db.execute(
        """UPDATE brand_token_summary
           SET is_place_name = 1,
               is_distinctive = 0,
               filter_reason = CASE
                 WHEN is_excluded = 1 THEN 'excluded'
                 WHEN is_industry_stopword = 1 THEN 'industry'
                 ELSE 'place'
               END
           WHERE token = ?""",
        (token,),
    )
    db.commit()
    return Response(status_code=204)


@router.delete("/brands/{token}/place", status_code=204)
def unmark_place(
    token: str, db=Depends(get_db), user=Depends(get_current_user)
):
    db.execute("DELETE FROM places WHERE token = ?", (token,))

    row = db.execute(
        """SELECT idf, is_excluded, is_industry_stopword, is_english_common
           FROM brand_token_summary WHERE token = ?""",
        (token,),
    ).fetchone()
    if row:
        from cleo.discovery_v2.config import CALIBRATION
        min_idf = CALIBRATION["exact_brand_token"]["min_idf"]
        if row["is_excluded"]:
            reason, distinctive = "excluded", 0
        elif row["is_industry_stopword"]:
            reason, distinctive = "industry", 0
        elif row["is_english_common"]:
            reason, distinctive = "english", 0
        elif row["idf"] < min_idf:
            reason, distinctive = None, 0
        else:
            reason, distinctive = None, 1
        db.execute(
            """UPDATE brand_token_summary SET is_place_name = 0,
               is_distinctive = ?, filter_reason = ? WHERE token = ?""",
            (distinctive, reason, token),
        )
    db.commit()
    return Response(status_code=204)


# ─────────────────────────────────────────────────────────────
# Phones
# ─────────────────────────────────────────────────────────────

@router.get("/phones")
def list_phones(
    q: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=500),
    db=Depends(get_db), user=Depends(get_current_user),
):
    where = []
    params: list = []
    if q:
        where.append("phone LIKE ?")
        # Accept formatted or unformatted search; strip non-digits
        digits = "".join(c for c in q if c.isdigit())
        params.append(f"%{digits or q}%")
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    total = db.execute(
        f"SELECT COUNT(*) FROM phone_summary{where_sql}", params
    ).fetchone()[0]

    offset = (page - 1) * per_page
    rows = db.execute(
        f"""SELECT phone, n_party_sides
            FROM phone_summary{where_sql}
            ORDER BY n_party_sides DESC, phone ASC
            LIMIT ? OFFSET ?""",
        params + [per_page, offset],
    ).fetchall()
    return {
        "results": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    }


@router.get("/phones/{phone}")
def phone_detail(
    phone: str, db=Depends(get_db), user=Depends(get_current_user),
):
    summary = db.execute(
        "SELECT phone, n_party_sides FROM phone_summary WHERE phone = ?",
        (phone,),
    ).fetchone()
    if summary is None:
        raise HTTPException(status_code=404, detail=f"Unknown phone: {phone!r}")

    ps_keys = {
        (r["source_id"], r["side"]) for r in db.execute(
            "SELECT source_id, side FROM party_fingerprints WHERE phone = ?",
            (phone,),
        )
    }
    party_sides = _hydrate_party_sides(db, ps_keys, highlight_token=None)

    return {**dict(summary), "party_sides": party_sides}


# ─────────────────────────────────────────────────────────────
# Addresses
# ─────────────────────────────────────────────────────────────

def _parse_address_key(key: str):
    """Unpack '{street_number}|{street_name}|{street_suffix}' — returns a tuple."""
    parts = key.split("|", 2)
    if len(parts) != 3:
        raise HTTPException(status_code=400, detail=f"Invalid address key: {key!r}")
    return parts[0], parts[1], parts[2]


def _parse_address_root_key(key: str):
    """Unpack '{street_number}|{street_name}' — returns a tuple."""
    parts = key.split("|")
    if len(parts) != 2:
        raise HTTPException(
            status_code=400, detail=f"Invalid address root key: {key!r}"
        )
    return parts[0], parts[1]


@router.get("/addresses")
def list_addresses(
    q: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=500),
    db=Depends(get_db), user=Depends(get_current_user),
):
    where = []
    params: list = []
    if q:
        ql = q.lower()
        where.append("(street_number LIKE ? OR street_name LIKE ? OR street_suffix LIKE ?)")
        like = f"%{ql}%"
        params.extend([like, like, like])
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    total = db.execute(
        f"SELECT COUNT(*) FROM address_base_summary{where_sql}", params
    ).fetchone()[0]

    offset = (page - 1) * per_page
    rows = db.execute(
        f"""SELECT street_number, street_name, street_suffix,
                   n_party_sides, n_distinct_suites, n_distinct_postals
            FROM address_base_summary{where_sql}
            ORDER BY n_party_sides DESC, street_name ASC, street_number ASC
            LIMIT ? OFFSET ?""",
        params + [per_page, offset],
    ).fetchall()

    results = []
    for r in rows:
        d = dict(r)
        d["key"] = f"{r['street_number']}|{r['street_name']}|{r['street_suffix']}"
        results.append(d)
    return {
        "results": results,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    }


# ─────────────────────────────────────────────────────────────
# Address roots — coarser key (number+name, no suffix).
# These MUST be registered before /addresses/{key} to avoid the
# generic path param swallowing "roots".
# ─────────────────────────────────────────────────────────────

@router.get("/addresses/roots")
def list_address_roots(
    q: Optional[str] = Query(None, description="Substring match on street_number or street_name"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=500),
    db=Depends(get_db), user=Depends(get_current_user),
):
    where = []
    params: list = []
    if q:
        ql = q.lower()
        where.append("(street_number LIKE ? OR street_name LIKE ?)")
        like = f"%{ql}%"
        params.extend([like, like])
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    total = db.execute(
        f"SELECT COUNT(*) FROM address_root_summary{where_sql}", params
    ).fetchone()[0]

    offset = (page - 1) * per_page
    rows = db.execute(
        f"""SELECT street_number, street_name, n_party_sides,
                   n_distinct_suffixes, n_distinct_directions,
                   n_distinct_suites, n_distinct_postals
            FROM address_root_summary{where_sql}
            ORDER BY n_party_sides DESC, street_name ASC, street_number ASC
            LIMIT ? OFFSET ?""",
        params + [per_page, offset],
    ).fetchall()

    results = []
    for r in rows:
        d = dict(r)
        d["key"] = f"{r['street_number']}|{r['street_name']}"
        results.append(d)
    return {
        "results": results,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    }


@router.get("/addresses/roots/{key}")
def address_root_detail(
    key: str, db=Depends(get_db), user=Depends(get_current_user),
):
    snum, sname = _parse_address_root_key(key)
    summary = db.execute(
        """SELECT street_number, street_name, n_party_sides,
                  n_distinct_suffixes, n_distinct_directions,
                  n_distinct_suites, n_distinct_postals
           FROM address_root_summary
           WHERE street_number = ? AND street_name = ?""",
        (snum, sname),
    ).fetchone()
    if summary is None:
        raise HTTPException(
            status_code=404, detail=f"Unknown address root: {key!r}"
        )

    # by_suffix — collapse NULL/empty into a "(none)" bucket.
    by_suffix = []
    for r in db.execute(
        """SELECT COALESCE(NULLIF(street_suffix, ''), '') AS suffix,
                  COUNT(*) AS n_party_sides
           FROM party_fingerprints
           WHERE street_number = ? AND street_name = ?
           GROUP BY COALESCE(NULLIF(street_suffix, ''), '')
           ORDER BY n_party_sides DESC
           LIMIT 50""",
        (snum, sname),
    ):
        suffix = r["suffix"]
        if suffix:
            by_suffix.append({
                "value": suffix,
                "n_party_sides": r["n_party_sides"],
                "base_key": f"{snum}|{sname}|{suffix}",
            })
        else:
            by_suffix.append({
                "value": "(none)",
                "n_party_sides": r["n_party_sides"],
                "base_key": None,
            })

    # by_suite — preserve NULLs as null (front-end shows them as "no suite").
    by_suite = [
        dict(r) for r in db.execute(
            """SELECT suite_type, suite_number, COUNT(*) AS n_party_sides
               FROM party_fingerprints
               WHERE street_number = ? AND street_name = ?
               GROUP BY suite_type, suite_number
               ORDER BY n_party_sides DESC
               LIMIT 50""",
            (snum, sname),
        )
    ]

    # by_postal
    by_postal = [
        dict(r) for r in db.execute(
            """SELECT postal, COUNT(*) AS n_party_sides
               FROM party_fingerprints
               WHERE street_number = ? AND street_name = ?
               GROUP BY postal
               ORDER BY n_party_sides DESC
               LIMIT 50""",
            (snum, sname),
        )
    ]

    ps_keys = {
        (r["source_id"], r["side"]) for r in db.execute(
            """SELECT source_id, side FROM party_fingerprints
               WHERE street_number = ? AND street_name = ?""",
            (snum, sname),
        )
    }
    party_sides = _hydrate_party_sides(db, ps_keys, highlight_token=None)

    d = dict(summary)
    d["key"] = key
    d["by_suffix"] = by_suffix
    d["by_suite"] = by_suite
    d["by_postal"] = by_postal
    d["party_sides"] = party_sides
    return d


@router.get("/addresses/{key}")
def address_detail(
    key: str, db=Depends(get_db), user=Depends(get_current_user),
):
    snum, sname, ssuf = _parse_address_key(key)
    summary = db.execute(
        """SELECT street_number, street_name, street_suffix,
                  n_party_sides, n_distinct_suites, n_distinct_postals
           FROM address_base_summary
           WHERE street_number = ? AND street_name = ? AND street_suffix = ?""",
        (snum, sname, ssuf),
    ).fetchone()
    if summary is None:
        raise HTTPException(status_code=404, detail=f"Unknown address base: {key!r}")

    # Suite variants at this base
    suite_variants = [
        dict(r) for r in db.execute(
            """SELECT suite_type, suite_number, postal, COUNT(*) AS n_party_sides
               FROM party_fingerprints
               WHERE street_number = ? AND street_name = ? AND street_suffix = ?
               GROUP BY suite_type, suite_number, postal
               ORDER BY n_party_sides DESC""",
            (snum, sname, ssuf),
        )
    ]

    ps_keys = {
        (r["source_id"], r["side"]) for r in db.execute(
            """SELECT source_id, side FROM party_fingerprints
               WHERE street_number = ? AND street_name = ? AND street_suffix = ?""",
            (snum, sname, ssuf),
        )
    }
    party_sides = _hydrate_party_sides(db, ps_keys, highlight_token=None)

    d = dict(summary)
    d["key"] = key
    d["suite_variants"] = suite_variants
    d["party_sides"] = party_sides
    return d


# ─────────────────────────────────────────────────────────────
# Auto-Groups (Layer 2 Plan A)
# ─────────────────────────────────────────────────────────────

@router.get("/auto-groups")
def list_auto_groups(
    tier: str = Query("confirmed"),
    q: Optional[str] = Query(None),
    close_to_promotion: bool = Query(False),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=500),
    db=Depends(get_db), user=Depends(get_current_user),
):
    if tier not in ("confirmed", "probable", "candidate"):
        raise HTTPException(status_code=400, detail=f"Invalid tier: {tier!r}")
    where = ["tier = ?"]
    params: list = [tier]
    if q:
        where.append("(LOWER(display_name) LIKE ? OR LOWER(canonical_stem) LIKE ?)")
        like = f"%{q.lower()}%"
        params.extend([like, like])
    if close_to_promotion:
        where.append("confidence >= ? AND confidence < ?")
        params.extend([
            TIER_CONFIRMED_MIN_CONFIDENCE - 0.05,
            TIER_CONFIRMED_MIN_CONFIDENCE,
        ])
    where_sql = " WHERE " + " AND ".join(where)

    total = db.execute(
        f"SELECT COUNT(*) FROM auto_groups{where_sql}", params
    ).fetchone()[0]
    offset = (page - 1) * per_page

    # Anchor diversity: count of distinct categories among the group's anchors.
    # Computed via correlated subquery using the address_root+address_base collapse.
    # Distinct contacts: count of distinct contact_fingerprint among party_side members.
    rows = db.execute(
        f"""SELECT ag.auto_group_id, ag.canonical_stem, ag.display_name, ag.tier,
                   ag.confidence, ag.n_anchors, ag.n_members,
                   (SELECT COUNT(DISTINCT
                                 CASE WHEN aga.anchor_type IN ('address_root', 'address_base')
                                      THEN 'address'
                                      ELSE aga.anchor_type
                                 END)
                    FROM auto_group_anchors aga
                    WHERE aga.auto_group_id = ag.auto_group_id) AS anchor_diversity,
                   (SELECT COUNT(DISTINCT pf.contact_fingerprint)
                    FROM auto_group_members agm
                    JOIN party_fingerprints pf
                      ON pf.source_id = agm.source_id AND pf.side = agm.side
                    WHERE agm.auto_group_id = ag.auto_group_id
                      AND agm.member_type = 'party_side'
                      AND pf.contact_fingerprint IS NOT NULL
                      AND pf.contact_fingerprint != '') AS n_distinct_contacts
            FROM auto_groups ag
            {where_sql}
            ORDER BY n_members DESC, canonical_stem ASC
            LIMIT ? OFFSET ?""",
        params + [per_page, offset],
    ).fetchall()
    return {
        "results": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    }


@router.get("/auto-groups/{auto_group_id}")
def auto_group_detail(
    auto_group_id: str, db=Depends(get_db), user=Depends(get_current_user),
):
    summary = db.execute(
        """SELECT auto_group_id, canonical_stem, display_name, tier, confidence,
                  n_anchors, n_members, discovered_at
           FROM auto_groups WHERE auto_group_id = ?""",
        (auto_group_id,),
    ).fetchone()
    if summary is None:
        raise HTTPException(status_code=404, detail=f"Unknown auto_group: {auto_group_id!r}")

    anchors = [dict(r) for r in db.execute(
        """SELECT anchor_type, anchor_value, score FROM auto_group_anchors
           WHERE auto_group_id = ? ORDER BY score DESC""",
        (auto_group_id,),
    )]
    members = [dict(r) for r in db.execute(
        """SELECT member_type, source_id, side, corp_name, match_score
           FROM auto_group_members
           WHERE auto_group_id = ? AND member_type = 'party_side'
           ORDER BY match_score DESC LIMIT 200""",
        (auto_group_id,),
    )]
    numbered_corps = [dict(r) for r in db.execute(
        """SELECT corp_name, match_score FROM auto_group_members
           WHERE auto_group_id = ? AND member_type = 'numbered_corp'
           ORDER BY corp_name""",
        (auto_group_id,),
    )]
    top_phrases = [dict(r) for r in db.execute(
        """SELECT pa.atom_value AS phrase, COUNT(*) AS n
           FROM auto_group_members agm
           JOIN party_atoms pa
             ON pa.source_id = agm.source_id
            AND pa.side      = agm.side
            AND pa.atom_type = 'brand_phrase'
           WHERE agm.auto_group_id = ? AND agm.member_type = 'party_side'
           GROUP BY pa.atom_value
           ORDER BY n DESC LIMIT 20""",
        (auto_group_id,),
    )]
    daterange = db.execute(
        """SELECT MIN(pf.sale_date) AS min_d, MAX(pf.sale_date) AS max_d
           FROM auto_group_members agm
           JOIN party_fingerprints pf
             ON pf.source_id = agm.source_id AND pf.side = agm.side
           WHERE agm.auto_group_id = ? AND agm.member_type = 'party_side'""",
        (auto_group_id,),
    ).fetchone()
    n_distinct_contacts = db.execute(
        """SELECT COUNT(DISTINCT pf.contact_fingerprint) AS n
           FROM auto_group_members agm
           JOIN party_fingerprints pf
             ON pf.source_id = agm.source_id AND pf.side = agm.side
           WHERE agm.auto_group_id = ? AND agm.member_type = 'party_side'""",
        (auto_group_id,),
    ).fetchone()["n"]

    d = dict(summary)
    d["anchors"]             = anchors
    d["members"]             = members
    d["numbered_corps"]      = numbered_corps
    d["top_phrases"]         = top_phrases
    d["min_sale_date"]       = daterange["min_d"] if daterange else None
    d["max_sale_date"]       = daterange["max_d"] if daterange else None
    d["n_distinct_contacts"] = n_distinct_contacts
    return d


# Bulk coverage queries: one per anchor type. Each query joins
# auto_group_anchors → auto_group_members → party_fingerprints to count parties
# per anchor in a single round-trip.
_COVERAGE_SQL_BY_TYPE = {
    'phone': """
        SELECT aga.anchor_value, COUNT(*) AS coverage
        FROM auto_group_anchors aga
        JOIN auto_group_members agm
          ON agm.auto_group_id = aga.auto_group_id
         AND agm.member_type = 'party_side'
        JOIN party_fingerprints pf
          ON pf.source_id = agm.source_id
         AND pf.side = agm.side
         AND pf.phone = aga.anchor_value
        WHERE aga.auto_group_id = ? AND aga.anchor_type = 'phone'
        GROUP BY aga.anchor_value
    """,
    'address_root': """
        SELECT aga.anchor_value, COUNT(*) AS coverage
        FROM auto_group_anchors aga
        JOIN auto_group_members agm
          ON agm.auto_group_id = aga.auto_group_id
         AND agm.member_type = 'party_side'
        JOIN party_fingerprints pf
          ON pf.source_id = agm.source_id
         AND pf.side = agm.side
         AND (pf.street_number || '|' || pf.street_name) = aga.anchor_value
        WHERE aga.auto_group_id = ? AND aga.anchor_type = 'address_root'
        GROUP BY aga.anchor_value
    """,
    'address_base': """
        SELECT aga.anchor_value, COUNT(*) AS coverage
        FROM auto_group_anchors aga
        JOIN auto_group_members agm
          ON agm.auto_group_id = aga.auto_group_id
         AND agm.member_type = 'party_side'
        JOIN party_fingerprints pf
          ON pf.source_id = agm.source_id
         AND pf.side = agm.side
         AND (pf.street_number || '|' || pf.street_name || '|' || COALESCE(pf.street_suffix,'')) = aga.anchor_value
        WHERE aga.auto_group_id = ? AND aga.anchor_type = 'address_base'
        GROUP BY aga.anchor_value
    """,
    'contact': """
        SELECT aga.anchor_value, COUNT(*) AS coverage
        FROM auto_group_anchors aga
        JOIN auto_group_members agm
          ON agm.auto_group_id = aga.auto_group_id
         AND agm.member_type = 'party_side'
        JOIN party_fingerprints pf
          ON pf.source_id = agm.source_id
         AND pf.side = agm.side
         AND pf.contact_fingerprint = aga.anchor_value
        WHERE aga.auto_group_id = ? AND aga.anchor_type = 'contact'
        GROUP BY aga.anchor_value
    """,
}


# Bulk co-stem queries: one per anchor type. The window function caps at 5
# co-stems per anchor in SQL so a single anchor with hundreds of cross-pollinating
# stems doesn't bloat the response.
_CO_STEMS_SQL_BY_TYPE = {
    'phone': """
        WITH co AS (
            SELECT aga.anchor_value, m.stem,
                   COUNT(DISTINCT pf.source_id || '|' || pf.side) AS n_parties
            FROM auto_group_anchors aga
            JOIN party_fingerprints pf ON pf.phone = aga.anchor_value
            JOIN party_atoms pa
              ON pa.source_id = pf.source_id AND pa.side = pf.side
             AND pa.atom_type = 'brand_phrase'
            JOIN brand_stem_phrase_map m ON m.phrase = pa.atom_value
            WHERE aga.auto_group_id = ? AND aga.anchor_type = 'phone'
              AND m.stem != ?
            GROUP BY aga.anchor_value, m.stem
        )
        SELECT anchor_value, stem, n_parties FROM (
            SELECT anchor_value, stem, n_parties,
                   ROW_NUMBER() OVER (PARTITION BY anchor_value ORDER BY n_parties DESC) AS rk
            FROM co
        ) WHERE rk <= 5
    """,
    'address_root': """
        WITH co AS (
            SELECT aga.anchor_value, m.stem,
                   COUNT(DISTINCT pf.source_id || '|' || pf.side) AS n_parties
            FROM auto_group_anchors aga
            JOIN party_fingerprints pf
              ON (pf.street_number || '|' || pf.street_name) = aga.anchor_value
            JOIN party_atoms pa
              ON pa.source_id = pf.source_id AND pa.side = pf.side
             AND pa.atom_type = 'brand_phrase'
            JOIN brand_stem_phrase_map m ON m.phrase = pa.atom_value
            WHERE aga.auto_group_id = ? AND aga.anchor_type = 'address_root'
              AND m.stem != ?
            GROUP BY aga.anchor_value, m.stem
        )
        SELECT anchor_value, stem, n_parties FROM (
            SELECT anchor_value, stem, n_parties,
                   ROW_NUMBER() OVER (PARTITION BY anchor_value ORDER BY n_parties DESC) AS rk
            FROM co
        ) WHERE rk <= 5
    """,
    'address_base': """
        WITH co AS (
            SELECT aga.anchor_value, m.stem,
                   COUNT(DISTINCT pf.source_id || '|' || pf.side) AS n_parties
            FROM auto_group_anchors aga
            JOIN party_fingerprints pf
              ON (pf.street_number || '|' || pf.street_name || '|' || COALESCE(pf.street_suffix,''))
                 = aga.anchor_value
            JOIN party_atoms pa
              ON pa.source_id = pf.source_id AND pa.side = pf.side
             AND pa.atom_type = 'brand_phrase'
            JOIN brand_stem_phrase_map m ON m.phrase = pa.atom_value
            WHERE aga.auto_group_id = ? AND aga.anchor_type = 'address_base'
              AND m.stem != ?
            GROUP BY aga.anchor_value, m.stem
        )
        SELECT anchor_value, stem, n_parties FROM (
            SELECT anchor_value, stem, n_parties,
                   ROW_NUMBER() OVER (PARTITION BY anchor_value ORDER BY n_parties DESC) AS rk
            FROM co
        ) WHERE rk <= 5
    """,
    'contact': """
        WITH co AS (
            SELECT aga.anchor_value, m.stem,
                   COUNT(DISTINCT pf.source_id || '|' || pf.side) AS n_parties
            FROM auto_group_anchors aga
            JOIN party_fingerprints pf ON pf.contact_fingerprint = aga.anchor_value
            JOIN party_atoms pa
              ON pa.source_id = pf.source_id AND pa.side = pf.side
             AND pa.atom_type = 'brand_phrase'
            JOIN brand_stem_phrase_map m ON m.phrase = pa.atom_value
            WHERE aga.auto_group_id = ? AND aga.anchor_type = 'contact'
              AND m.stem != ?
            GROUP BY aga.anchor_value, m.stem
        )
        SELECT anchor_value, stem, n_parties FROM (
            SELECT anchor_value, stem, n_parties,
                   ROW_NUMBER() OVER (PARTITION BY anchor_value ORDER BY n_parties DESC) AS rk
            FROM co
        ) WHERE rk <= 5
    """,
}


def _bulk_coverage(db, auto_group_id: str) -> dict:
    """Return {(anchor_type, anchor_value): coverage} for every anchor of the group."""
    out: dict = {}
    for anchor_type, sql in _COVERAGE_SQL_BY_TYPE.items():
        for r in db.execute(sql, (auto_group_id,)):
            out[(anchor_type, r['anchor_value'])] = r['coverage']
    return out


def _bulk_co_stems(db, auto_group_id: str, canonical_stem: str) -> dict:
    """Return {(anchor_type, anchor_value): [{stem, n_parties}, ...]} for every anchor of the group.
    Each list is already capped at 5 entries (via SQL ROW_NUMBER) sorted by n_parties desc.
    """
    out: dict = {}
    for anchor_type, sql in _CO_STEMS_SQL_BY_TYPE.items():
        for r in db.execute(sql, (auto_group_id, canonical_stem)):
            key = (anchor_type, r['anchor_value'])
            out.setdefault(key, []).append({'stem': r['stem'], 'n_parties': r['n_parties']})
    return out


@router.get('/auto-groups/{auto_group_id}/anchors-with-coverage')
def auto_group_anchors_with_coverage(
    auto_group_id: str, db=Depends(get_db), user=Depends(get_current_user),
):
    # 404 if the group doesn't exist
    summary = db.execute(
        'SELECT canonical_stem FROM auto_groups WHERE auto_group_id = ?',
        (auto_group_id,),
    ).fetchone()
    if summary is None:
        raise HTTPException(status_code=404, detail=f'Unknown auto_group: {auto_group_id!r}')

    anchors = [dict(r) for r in db.execute(
        """SELECT anchor_type, anchor_value, score
           FROM auto_group_anchors
           WHERE auto_group_id = ?
           ORDER BY score DESC""",
        (auto_group_id,),
    )]

    # Bulk lookups: 4 queries each instead of N+1.
    coverage_map = _bulk_coverage(db, auto_group_id)
    co_stems_map = _bulk_co_stems(db, auto_group_id, summary['canonical_stem'])

    for a in anchors:
        key = (a['anchor_type'], a['anchor_value'])
        a['coverage'] = coverage_map.get(key, 0)
        a['co_stems'] = co_stems_map.get(key, [])

    return {'anchors': anchors}


def _category_of_anchor_type(anchor_type: str) -> str:
    if anchor_type in ('address_root', 'address_base'):
        return 'address'
    return anchor_type


def _anchor_pf_clause(anchor_type: str) -> Optional[str]:
    """SQL fragment that filters party_fingerprints (aliased pf) for the given anchor_type.

    The clause expects exactly one bind param: the anchor_value.
    Returns None for unknown anchor_types.
    """
    if anchor_type == 'phone':
        return 'pf.phone = ?'
    elif anchor_type == 'address_root':
        return "(pf.street_number || '|' || pf.street_name) = ?"
    elif anchor_type == 'address_base':
        return "(pf.street_number || '|' || pf.street_name || '|' || COALESCE(pf.street_suffix,'')) = ?"
    elif anchor_type == 'contact':
        return 'pf.contact_fingerprint = ?'
    return None


@router.get('/auto-groups/{auto_group_id}/why-tier')
def auto_group_why_tier(
    auto_group_id: str, db=Depends(get_db), user=Depends(get_current_user),
):
    summary = db.execute(
        'SELECT auto_group_id, canonical_stem, tier, confidence FROM auto_groups WHERE auto_group_id = ?',
        (auto_group_id,),
    ).fetchone()
    if summary is None:
        raise HTTPException(status_code=404, detail=f'Unknown auto_group: {auto_group_id!r}')

    # Group anchors that passed the seeding threshold, bucketed by category.
    strong_by_category: dict[str, list] = {'phone': [], 'address': [], 'contact': []}
    for r in db.execute(
        """SELECT anchor_type, anchor_value, score
           FROM auto_group_anchors
           WHERE auto_group_id = ? AND score >= ?
           ORDER BY score DESC""",
        (auto_group_id, ANCHOR_SEEDING_SCORE_THRESHOLD),
    ):
        cat = _category_of_anchor_type(r['anchor_type'])
        strong_by_category[cat].append(dict(r))

    categories_response = []
    for cat in ('phone', 'address', 'contact'):
        anchors_in_cat = strong_by_category[cat]
        if anchors_in_cat:
            categories_response.append({
                'category': cat,
                'passes_threshold': True,
                'strongest_anchor': anchors_in_cat[0],
                'near_miss_anchor': None,
            })
        else:
            # Find the highest-scoring anchor in this category whose dominant_stem
            # matches this group's stem but score < threshold.
            near_miss = _near_miss_anchor(
                db, auto_group_id, summary['canonical_stem'], cat
            )
            categories_response.append({
                'category': cat,
                'passes_threshold': False,
                'strongest_anchor': None,
                'near_miss_anchor': near_miss,
            })

    n_passing = sum(1 for c in categories_response if c['passes_threshold'])

    return {
        'auto_group_id': auto_group_id,
        'canonical_stem': summary['canonical_stem'],
        'tier': summary['tier'],
        'confidence': summary['confidence'],
        'n_categories_passing': n_passing,
        'categories': categories_response,
        'seeding_threshold': ANCHOR_SEEDING_SCORE_THRESHOLD,
        'corroboration_threshold': ANCHOR_CORROBORATION_SCORE_THRESHOLD,
    }


def _near_miss_anchor(db, auto_group_id: str, canonical_stem: str, category: str):
    """Find the strongest anchor in this category whose dominant_stem matches the
    group's canonical_stem but score < ANCHOR_SEEDING_SCORE_THRESHOLD.

    Mirrors the seeding filter (cleo/discovery_v2/seeding.py:90-93): only
    anchors with score >= ANCHOR_CORROBORATION_SCORE_THRESHOLD and
    is_service_provider = 0 are considered, since anchors below the
    corroboration bar aren't "near" the threshold and service-provider-flagged
    anchors would never be used for seeding regardless of score.

    NOTE: Full override-aware behavior (auto_anchor_overrides.override_service_provider,
    override_stem) is deferred to Plan C. This query honors the static
    is_service_provider flag on anchor_uniqueness but does not apply per-anchor
    user overrides yet.

    Returns dict with {anchor_type, anchor_value, score} or None.
    """
    if category == 'phone':
        type_clause = "anchor_type = 'phone'"
    elif category == 'address':
        type_clause = "anchor_type IN ('address_root', 'address_base')"
    elif category == 'contact':
        type_clause = "anchor_type = 'contact'"
    else:
        return None

    row = db.execute(
        f"""SELECT anchor_type, anchor_value, score
            FROM anchor_uniqueness
            WHERE dominant_stem = ?
              AND score < ?
              AND score >= ?
              AND is_service_provider = 0
              AND {type_clause}
            ORDER BY score DESC
            LIMIT 1""",
        (canonical_stem, ANCHOR_SEEDING_SCORE_THRESHOLD, ANCHOR_CORROBORATION_SCORE_THRESHOLD),
    ).fetchone()
    return dict(row) if row else None


# ─────────────────────────────────────────────────────────────
# Auto-group parties (Plan D Task 3)
# ─────────────────────────────────────────────────────────────

_PARTIES_VALID_SORTS = {
    'date': 'pf.sale_date',
    'match_score': 'agm.match_score',
    'sale_price': 't.sale_price',
}


@router.get('/auto-groups/{auto_group_id}/parties')
def auto_group_parties(
    auto_group_id: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(100, ge=1, le=500),
    min_match_score: Optional[float] = Query(None),
    side: Optional[str] = Query(None),
    anchor_type: Optional[str] = Query(None),
    anchor_value: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    sort: str = Query('date'),
    order: str = Query('desc'),
    db=Depends(get_db), user=Depends(get_current_user),
):
    # 404 if the group doesn't exist
    summary = db.execute(
        'SELECT auto_group_id, canonical_stem FROM auto_groups WHERE auto_group_id = ?',
        (auto_group_id,),
    ).fetchone()
    if summary is None:
        raise HTTPException(status_code=404, detail=f'Unknown auto_group: {auto_group_id!r}')

    # Validate sort
    sort_column = _PARTIES_VALID_SORTS.get(sort)
    if sort_column is None:
        raise HTTPException(status_code=400, detail=f'Invalid sort: {sort!r}')
    order_sql = 'DESC' if order.lower() == 'desc' else 'ASC'

    if side is not None and side not in ('buyer', 'seller'):
        raise HTTPException(status_code=400, detail=f'Invalid side: {side!r}')
    if (anchor_type is None) != (anchor_value is None):
        raise HTTPException(status_code=400, detail='anchor_type and anchor_value must be provided together')
    if anchor_type and anchor_type not in ('phone', 'address_root', 'address_base', 'contact'):
        raise HTTPException(status_code=400, detail=f'Invalid anchor_type: {anchor_type!r}')

    where = ["agm.auto_group_id = ?", "agm.member_type = 'party_side'"]
    params: list = [auto_group_id]

    if min_match_score is not None:
        where.append('agm.match_score >= ?')
        params.append(min_match_score)
    if side in ('buyer', 'seller'):
        where.append('agm.side = ?')
        params.append(side)
    if anchor_type and anchor_value:
        clause = _anchor_pf_clause(anchor_type)
        if clause is None:
            # This branch is unreachable thanks to the I-1 validation above,
            # but defensive in case the validation is later removed.
            raise HTTPException(status_code=400, detail=f'Invalid anchor_type: {anchor_type!r}')
        where.append(clause)
        params.append(anchor_value)
    if q:
        where.append("EXISTS (SELECT 1 FROM party_atoms pa WHERE pa.source_id = agm.source_id AND pa.side = agm.side AND pa.atom_type = 'brand_phrase' AND LOWER(pa.atom_value) LIKE ?)")
        params.append(f'%{q.lower()}%')

    where_sql = ' WHERE ' + ' AND '.join(where)

    # Total count
    total = db.execute(
        f"""SELECT COUNT(*) FROM auto_group_members agm
            JOIN party_fingerprints pf
              ON pf.source_id = agm.source_id AND pf.side = agm.side
            {where_sql}""",
        params,
    ).fetchone()[0]

    offset = (page - 1) * per_page

    # Top brand phrase per party — most-frequent phrase mapped to the group's canonical_stem.
    # Fall back to any brand phrase on the party if no stem-mapped phrase exists.
    rows = db.execute(
        f"""SELECT
              agm.source_id, agm.side, agm.match_score,
              pf.phone, pf.contact_fingerprint AS contact, pf.sale_date,
              pf.street_number, pf.street_name, pf.street_suffix,
              pf.suite_type, pf.suite_number, pf.postal,
              t.sale_price,
              (SELECT pa.atom_value
                 FROM party_atoms pa
                 LEFT JOIN brand_stem_phrase_map m ON m.phrase = pa.atom_value
                 WHERE pa.source_id = agm.source_id
                   AND pa.side = agm.side
                   AND pa.atom_type = 'brand_phrase'
                 ORDER BY (CASE WHEN m.stem = ? THEN 0 ELSE 1 END), pa.id ASC
                 LIMIT 1) AS top_brand_phrase
            FROM auto_group_members agm
            JOIN party_fingerprints pf
              ON pf.source_id = agm.source_id AND pf.side = agm.side
            LEFT JOIN transactions t ON t.source_id = agm.source_id
            {where_sql}
            ORDER BY {sort_column} {order_sql}, agm.source_id
            LIMIT ? OFFSET ?""",
        [summary['canonical_stem']] + params + [per_page, offset],
    ).fetchall()

    # Pre-load group anchors once so we can compute anchor_signature per row.
    group_anchors = list(db.execute(
        'SELECT anchor_type, anchor_value FROM auto_group_anchors WHERE auto_group_id = ?',
        (auto_group_id,),
    ))

    results = []
    for r in rows:
        d = dict(r)
        d['anchor_signature'] = _anchor_signature_for_party(d, group_anchors)
        results.append(d)

    return {
        'results': results,
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page,
    }


def _anchor_signature_for_party(party: dict, group_anchors: list) -> list:
    """Return the subset of group_anchors that this party's data matches."""
    addr_root = (
        f"{party['street_number']}|{party['street_name']}"
        if party.get('street_number') and party.get('street_name') else None
    )
    addr_base = (
        f"{party['street_number']}|{party['street_name']}|{party.get('street_suffix') or ''}"
        if party.get('street_number') and party.get('street_name') else None
    )
    matches = []
    for a in group_anchors:
        at, av = a['anchor_type'], a['anchor_value']
        if at == 'phone' and party.get('phone') == av:
            matches.append({'anchor_type': at, 'anchor_value': av, 'category': 'phone'})
        elif at == 'address_root' and addr_root == av:
            matches.append({'anchor_type': at, 'anchor_value': av, 'category': 'address'})
        elif at == 'address_base' and addr_base == av:
            matches.append({'anchor_type': at, 'anchor_value': av, 'category': 'address'})
        elif at == 'contact' and party.get('contact') == av:
            matches.append({'anchor_type': at, 'anchor_value': av, 'category': 'contact'})
    return matches


# ─────────────────────────────────────────────────────────────
# Tuning page endpoints (Plan G)
# ─────────────────────────────────────────────────────────────

@router.get('/auto-groups/tuning/histogram')
def auto_groups_tuning_histogram(
    db=Depends(get_db), user=Depends(get_current_user),
):
    """Confidence histogram in 0.05-wide buckets. Returns 20 buckets covering [0.00, 1.00]."""
    # Compute bucket counts via integer math: bucket index = floor(confidence * 20),
    # clamped to [0, 19] so 1.0 confidence lands in the last bucket.
    rows = db.execute(
        """SELECT
              MIN(CAST(confidence * 20 AS INT), 19) AS bucket_idx,
              COUNT(*) AS n
           FROM auto_groups
           GROUP BY bucket_idx
           ORDER BY bucket_idx"""
    ).fetchall()
    counts_by_idx = {r['bucket_idx']: r['n'] for r in rows}

    buckets = []
    for i in range(20):
        lower = i * 0.05
        upper = (i + 1) * 0.05
        buckets.append({
            'lower': round(lower, 2),
            'upper': round(upper, 2),
            'count': counts_by_idx.get(i, 0),
        })

    return {
        'buckets': buckets,
        'tier_confirmed_threshold': TIER_CONFIRMED_MIN_CONFIDENCE,
        'tier_probable_threshold': TIER_PROBABLE_MIN_CONFIDENCE,
    }


@router.get('/auto-groups/tuning/close-to-promotion')
def auto_groups_close_to_promotion(
    from_: float = Query(0.70, alias='from', ge=0.0, le=1.0),
    to: float = Query(0.75, ge=0.0, le=1.0),
    page: int = Query(1, ge=1),
    per_page: int = Query(100, ge=1, le=500),
    db=Depends(get_db), user=Depends(get_current_user),
):
    """Groups whose confidence sits in [from, to). Default window is [0.70, 0.75) —
    Probable groups within 0.05 of the Confirmed threshold."""
    if from_ >= to:
        raise HTTPException(status_code=400, detail=f'Invalid window: from={from_} must be < to={to}')

    total = db.execute(
        """SELECT COUNT(*) FROM auto_groups
           WHERE confidence >= ? AND confidence < ?""",
        (from_, to),
    ).fetchone()[0]
    offset = (page - 1) * per_page
    rows = db.execute(
        """SELECT auto_group_id, canonical_stem, display_name, tier, confidence,
                  n_anchors, n_members
           FROM auto_groups
           WHERE confidence >= ? AND confidence < ?
           ORDER BY confidence DESC, canonical_stem ASC
           LIMIT ? OFFSET ?""",
        (from_, to, per_page, offset),
    ).fetchall()

    return {
        'results': [dict(r) for r in rows],
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page,
        'from_confidence': from_,
        'to_confidence': to,
    }


@router.get('/auto-groups/tuning/missed-stems')
def auto_groups_tuning_missed_stems(
    min_n_party_sides: int = Query(100, ge=1),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db=Depends(get_db), user=Depends(get_current_user),
):
    """1-grams that are distinctive or position-anchor with high party-side counts
    but didn't get a verified stem. For each, surfaces the strongest-phone anchor
    and the stem that won the dominance contest at that anchor.

    Phone-only diagnostic for now — most missed stems (DD/KS/Dundee/PIRET) cluster
    at operator switchboards. Address-anchor analysis can be added later.
    """
    # Total count for pagination (cheap — counts the missed-token candidate set).
    total = db.execute(
        """SELECT COUNT(*) FROM brand_token_summary bts
           LEFT JOIN brand_stem bs ON bs.stem = bts.token
           WHERE (bts.is_distinctive = 1 OR COALESCE(bts.is_position_anchor, 0) = 1)
             AND bts.n_party_sides >= ?
             AND bs.stem IS NULL""",
        (min_n_party_sides,),
    ).fetchone()[0]

    offset = (page - 1) * per_page

    # Bulk query: for each missed token, find its strongest-phone anchor + the
    # stem that won there.
    rows = db.execute(
        """WITH missed AS (
              SELECT bts.token, bts.n_party_sides
              FROM brand_token_summary bts
              LEFT JOIN brand_stem bs ON bs.stem = bts.token
              WHERE (bts.is_distinctive = 1 OR COALESCE(bts.is_position_anchor, 0) = 1)
                AND bts.n_party_sides >= ?
                AND bs.stem IS NULL
              ORDER BY bts.n_party_sides DESC
              LIMIT ? OFFSET ?
           ),
           by_phone AS (
              SELECT m.token, pf.phone AS anchor_value, COUNT(*) AS sides_with_token,
                     ROW_NUMBER() OVER (PARTITION BY m.token ORDER BY COUNT(*) DESC) AS rk
              FROM missed m
              JOIN brand_token_index bti ON bti.token = m.token
              JOIN party_fingerprints pf
                ON pf.source_id = bti.source_id AND pf.side = bti.side
              WHERE pf.phone IS NOT NULL AND pf.phone != ''
              GROUP BY m.token, pf.phone
           )
           SELECT m.token, m.n_party_sides,
                  bp.anchor_value AS strongest_phone,
                  bp.sides_with_token AS token_sides_at_anchor,
                  au.dominant_stem AS winner_stem,
                  au.dominance_share AS winner_dominance,
                  au.volume AS anchor_volume
           FROM missed m
           LEFT JOIN by_phone bp ON bp.token = m.token AND bp.rk = 1
           LEFT JOIN anchor_uniqueness au
             ON au.anchor_type = 'phone' AND au.anchor_value = bp.anchor_value
           ORDER BY m.n_party_sides DESC""",
        (min_n_party_sides, per_page, offset),
    ).fetchall()

    return {
        'results': [dict(r) for r in rows],
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page,
        'min_n_party_sides': min_n_party_sides,
    }


# ─────────────────────────────────────────────────────────────
# Contacts
# ─────────────────────────────────────────────────────────────

@router.get("/contacts")
def list_contacts(
    q: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=500),
    db=Depends(get_db), user=Depends(get_current_user),
):
    where = []
    params: list = []
    if q:
        where.append("contact_fingerprint LIKE ?")
        params.append(f"%{q.lower()}%")
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    total = db.execute(
        f"SELECT COUNT(*) FROM contact_fingerprint_summary{where_sql}", params
    ).fetchone()[0]

    offset = (page - 1) * per_page
    rows = db.execute(
        f"""SELECT contact_fingerprint, n_party_sides
            FROM contact_fingerprint_summary{where_sql}
            ORDER BY n_party_sides DESC, contact_fingerprint ASC
            LIMIT ? OFFSET ?""",
        params + [per_page, offset],
    ).fetchall()
    return {
        "results": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    }


@router.get("/contacts/{fingerprint}")
def contact_detail(
    fingerprint: str, db=Depends(get_db), user=Depends(get_current_user),
):
    summary = db.execute(
        "SELECT contact_fingerprint, n_party_sides FROM contact_fingerprint_summary "
        "WHERE contact_fingerprint = ?",
        (fingerprint,),
    ).fetchone()
    if summary is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown contact fingerprint: {fingerprint!r}",
        )

    ps_keys = {
        (r["source_id"], r["side"]) for r in db.execute(
            "SELECT source_id, side FROM party_fingerprints "
            "WHERE contact_fingerprint = ?",
            (fingerprint,),
        )
    }
    party_sides = _hydrate_party_sides(db, ps_keys, highlight_token=None)

    return {**dict(summary), "party_sides": party_sides}
