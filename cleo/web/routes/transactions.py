"""
Transactions API — browse, search, detail.
"""

import json
import os
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from ...web.deps import get_db, get_current_user, fts_query

RAW_DATA_RT = Path(__file__).resolve().parents[3] / "raw-data" / "rt" / "pages"

router = APIRouter()


@router.get("")
def browse_transactions(
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    city: str = None,
    region: str = None,
    min_price: int = None,
    max_price: int = None,
    sort: str = "sale_date",
    order: str = "desc",
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Paginated transaction browse with filters."""
    allowed_sorts = {"sale_date", "sale_price", "display_address", "city"}
    if sort not in allowed_sorts:
        sort = "sale_date"
    if order not in ("asc", "desc"):
        order = "desc"

    conditions = []
    params = []

    if city:
        conditions.append("city = ?")
        params.append(city)
    if region:
        conditions.append("region = ?")
        params.append(region)
    if min_price is not None:
        conditions.append("sale_price >= ?")
        params.append(min_price)
    if max_price is not None:
        conditions.append("sale_price <= ?")
        params.append(max_price)

    where = " AND ".join(conditions) if conditions else "1=1"
    offset = (page - 1) * per_page

    count_row = db.execute(f"SELECT COUNT(*) FROM transactions WHERE {where}", params).fetchone()
    total = count_row[0]

    rows = db.execute(
        f"SELECT source_id, property_id, sale_date, sale_price, display_address, city, region, "
        f"seller_parties, buyer_parties, transaction_note, source_folder, source_position, "
        f"building_size_raw, building_size_value, building_size_unit "
        f"FROM transactions WHERE {where} ORDER BY {sort} {order} LIMIT ? OFFSET ?",
        params + [per_page, offset]
    ).fetchall()

    results = []
    for r in rows:
        d = dict(r)
        d["seller_parties"] = json.loads(d.get("seller_parties") or "[]")
        d["buyer_parties"] = json.loads(d.get("buyer_parties") or "[]")
        d["has_source_html"] = bool(d.get("source_folder") and d.get("source_position") is not None)
        d.pop("source_folder", None)
        d.pop("source_position", None)
        results.append(d)

    return {
        "results": results,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    }


@router.get("/search")
def search_transactions(
    q: str = Query(..., min_length=1),
    limit: int = Query(25, ge=1, le=100),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Full-text search on transactions."""
    like_val = f"%{q.strip()}%"
    rows = db.execute(
        "SELECT t.source_id, t.property_id, t.sale_date, t.sale_price, t.display_address, t.city, "
        "t.seller_parties, t.buyer_parties "
        "FROM transactions t "
        "WHERE t.display_address LIKE ? OR t.city LIKE ? OR t.seller_parties LIKE ? OR t.buyer_parties LIKE ? "
        "LIMIT ?",
        (like_val, like_val, like_val, like_val, limit)
    ).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        d["seller_parties"] = json.loads(d.get("seller_parties") or "[]")
        d["buyer_parties"] = json.loads(d.get("buyer_parties") or "[]")
        results.append(d)
    return {"results": results, "total": len(results)}


def _source_html_path(source_folder: str, source_position: int) -> Path | None:
    """Resolve path to the raw Realtrack detail HTML file."""
    if not source_folder or source_position is None:
        return None
    # Sanitize: no .. or absolute path components
    clean = Path(source_folder)
    if ".." in clean.parts or clean.is_absolute():
        return None
    html_file = RAW_DATA_RT / clean / f"detail_{int(source_position):03d}.html"
    if html_file.is_file():
        return html_file
    return None


@router.get("/{source_id}/html")
def transaction_source_html(source_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    """Serve the original Realtrack detail HTML for rendering in an iframe."""
    row = db.execute(
        "SELECT source_folder, source_position FROM transactions WHERE source_id = ?",
        (source_id,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Transaction not found")

    html_path = _source_html_path(row["source_folder"], row["source_position"])
    if not html_path:
        raise HTTPException(status_code=404, detail="Source HTML not available")

    content = html_path.read_text(encoding="utf-8", errors="replace")
    return HTMLResponse(content=content)


@router.get("/{source_id}")
def transaction_detail(source_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    """Full transaction detail."""
    row = db.execute("SELECT * FROM transactions WHERE source_id = ?", (source_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Transaction not found")

    result = dict(row)

    # Parse JSON fields
    for field in ["seller_parties", "buyer_parties", "photos_json",
                   "charges_json", "seller_law_firms_json", "seller_companies_json",
                   "buyer_law_firms_json", "buyer_companies_json"]:
        if result.get(field):
            result[field] = json.loads(result[field])

    # Build consideration object from inline columns
    result["consideration"] = {
        "cash": result.get("cash"),
        "debt": result.get("debt"),
        "chattels": result.get("chattels"),
        "other": result.get("other_consideration"),
        "charges": result.get("charges_json") or [],
    }

    # Build party metadata from inline columns
    for side in ["seller", "buyer"]:
        result[f"{side}_party_metadata"] = {
            "trade_name": result.get(f"{side}_trade_name") or "",
            "care_of": result.get(f"{side}_care_of") or "",
            "law_firms": result.get(f"{side}_law_firms_json") or [],
            "companies": result.get(f"{side}_companies_json") or [],
        }

    # Get associated contacts/groups
    parties = db.execute(
        "SELECT tp.side, tp.party_name, tp.contact_title, tp.phone, "
        "c.id as contact_id, c.display_name as contact_name, "
        "g.id as group_id, g.display_name as group_name "
        "FROM transaction_parties tp "
        "LEFT JOIN contacts c ON tp.contact_id = c.id "
        "LEFT JOIN groups g ON tp.group_id = g.id "
        "WHERE tp.source_id = ?",
        (source_id,)
    ).fetchall()
    result["parties"] = [dict(p) for p in parties]

    # Source HTML availability
    result["has_source_html"] = bool(
        _source_html_path(result.get("source_folder"), result.get("source_position"))
    )

    # Brokers (one-to-many: transaction → brokerages → agents)
    broker_rows = db.execute(
        "SELECT * FROM transaction_brokers WHERE source_id = ? ORDER BY id", (source_id,)
    ).fetchall()
    brokers_list = []
    for br in broker_rows:
        bd = dict(br)
        agents = db.execute(
            "SELECT agent_name FROM transaction_broker_agents WHERE broker_id = ? ORDER BY id",
            (bd["id"],)
        ).fetchall()
        brokers_list.append({
            "broker_name": bd["broker_name"],
            "phone": bd["phone"],
            "agents": [a["agent_name"] for a in agents],
        })
    result["brokers"] = brokers_list

    # Mailing addresses (one-per-side, separate table for 14 parsed address fields)
    for side in ["seller", "buyer"]:
        addr = db.execute(
            "SELECT * FROM transaction_mailing_addresses WHERE source_id = ? AND side = ?",
            (source_id, side)
        ).fetchone()
        result[f"{side}_mailing_address"] = dict(addr) if addr else None

    return result
