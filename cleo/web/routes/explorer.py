"""Layer 1 / Silo A Explorer endpoints.

GET /api/explorer/brands                            — list brand_tokens with signals
GET /api/explorer/brands/:token                     — detail: phrases + party-sides
GET /api/explorer/industry-stopwords                — the curated stopword list
POST /api/explorer/brands/:token/industry-stopword  — user marks a token
DELETE /api/explorer/brands/:token/industry-stopword — user unmarks
"""

from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from typing import Optional

from ..deps import get_db, get_current_user

router = APIRouter()


@router.get("/brands")
def list_brand_tokens(
    q: Optional[str] = Query(None, description="Substring match on token name"),
    distinctive_only: bool = Query(True),
    filter_reason: Optional[str] = Query(
        None, description="'excluded', 'industry', 'place', 'english', or empty for NULL"
    ),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=500),
    db=Depends(get_db), user=Depends(get_current_user),
):
    where = []
    params: list = []
    if distinctive_only:
        where.append("is_distinctive = 1")
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
                   is_industry_stopword, filter_reason
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


@router.get("/brands/{token}")
def brand_token_detail(
    token: str,
    db=Depends(get_db), user=Depends(get_current_user),
):
    summary_row = db.execute(
        """SELECT token, idf, n_party_sides, n_distinct_phrases,
                  is_distinctive, is_excluded,
                  wordfreq_zipf, is_english_common, is_place_name,
                  is_industry_stopword, filter_reason
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

    return {
        **dict(summary_row),
        "phrases": phrases,
        "party_sides": party_sides,
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
