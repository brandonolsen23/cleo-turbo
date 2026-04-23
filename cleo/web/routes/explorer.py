"""Layer 1 / Silo A Explorer endpoints.

GET /api/explorer/brands                 — list distinctive brand_tokens with stats
GET /api/explorer/brands/:token          — detail: phrases and party-sides carrying this token
"""

from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional

from ..deps import get_db, get_current_user

router = APIRouter()


@router.get("/brands")
def list_brand_tokens(
    q: Optional[str] = Query(None, description="Substring match on token name"),
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
        where.append("token LIKE ?")
        params.append(f"%{q.lower()}%")
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    total = db.execute(
        f"SELECT COUNT(*) FROM brand_token_summary{where_sql}",
        params,
    ).fetchone()[0]

    offset = (page - 1) * per_page
    rows = db.execute(
        f"""SELECT token, idf, n_party_sides, n_distinct_phrases,
                   is_distinctive, is_excluded
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
        "SELECT token, idf, n_party_sides, n_distinct_phrases, is_distinctive, is_excluded "
        "FROM brand_token_summary WHERE token = ?",
        (token,),
    ).fetchone()
    if summary_row is None:
        raise HTTPException(status_code=404, detail=f"Unknown brand_token: {token!r}")

    # All distinct brand_phrases carried on party-sides that also carry this token
    phrases = [
        r["atom_value"] for r in db.execute(
            """SELECT DISTINCT pa.atom_value
               FROM party_atoms pa
               JOIN brand_token_index bti
                 ON bti.source_id = pa.source_id AND bti.side = pa.side
               WHERE bti.token = ? AND pa.atom_type = 'brand_phrase'
               ORDER BY pa.atom_value""",
            (token,),
        )
    ]

    # Party-sides carrying this token — with key atoms for context
    party_sides = [
        dict(r) for r in db.execute(
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
        )
    ]

    return {
        **dict(summary_row),
        "phrases": phrases,
        "party_sides": party_sides,
    }
