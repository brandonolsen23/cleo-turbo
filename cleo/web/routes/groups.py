"""
Groups API — browse, search, detail, promote.
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from ...web.deps import get_db, get_current_user

router = APIRouter()


@router.get("")
def browse_groups(
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    status: str = None,
    min_properties: int = None,
    sort: str = "transaction_count",
    order: str = "desc",
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    conditions = []
    params = []
    if status:
        conditions.append("status = ?")
        params.append(status)
    if min_properties is not None:
        conditions.append("property_count >= ?")
        params.append(min_properties)

    where = " AND ".join(conditions) if conditions else "1=1"
    offset = (page - 1) * per_page

    total = db.execute(f"SELECT COUNT(*) FROM groups WHERE {where}", params).fetchone()[0]

    allowed_sorts = {"transaction_count", "property_count", "contact_count", "display_name"}
    if sort not in allowed_sorts:
        sort = "transaction_count"
    if order not in ("asc", "desc"):
        order = "desc"

    rows = db.execute(
        f"SELECT id, display_name, status, property_count, transaction_count, contact_count "
        f"FROM groups WHERE {where} ORDER BY {sort} {order} LIMIT ? OFFSET ?",
        params + [per_page, offset]
    ).fetchall()

    return {
        "results": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    }


@router.get("/search")
def search_groups(
    q: str = Query(..., min_length=1),
    limit: int = Query(25, ge=1, le=100),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    rows = db.execute(
        "SELECT g.id, g.display_name, g.status, g.property_count, g.transaction_count, g.contact_count "
        "FROM groups g "
        "WHERE g.rowid IN (SELECT rowid FROM groups_fts WHERE groups_fts MATCH ?) "
        "LIMIT ?",
        (q, limit)
    ).fetchall()
    return {"results": [dict(r) for r in rows], "total": len(rows)}


@router.get("/{group_id}")
def group_detail(group_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    row = db.execute("SELECT * FROM groups WHERE id = ?", (group_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Group not found")

    result = dict(row)

    # Known names
    names = db.execute(
        "SELECT name, normalized, source_id FROM group_names WHERE group_id = ?",
        (group_id,)
    ).fetchall()
    result["known_names"] = [dict(n) for n in names]

    # Associated contacts
    contacts = db.execute(
        "SELECT id, display_name, phone, job_title, status, transaction_count "
        "FROM contacts WHERE current_group_id = ? ORDER BY transaction_count DESC",
        (group_id,)
    ).fetchall()
    result["contacts"] = [dict(c) for c in contacts]

    # Transactions where this group appears
    txns = db.execute(
        "SELECT DISTINCT t.source_id, t.sale_date, t.sale_price, t.display_address, t.city, "
        "tp.side, tp.party_name "
        "FROM transaction_parties tp "
        "JOIN transactions t ON tp.source_id = t.source_id "
        "WHERE tp.group_id = ? ORDER BY t.sale_date DESC LIMIT 100",
        (group_id,)
    ).fetchall()
    result["transactions"] = [dict(t) for t in txns]

    # Properties owned (where group is buyer on most recent transaction)
    props = db.execute(
        "SELECT id, display_address, city, most_recent_sale_date, most_recent_sale_price "
        "FROM properties WHERE current_owner_group_id = ? ORDER BY most_recent_sale_date DESC",
        (group_id,)
    ).fetchall()
    result["properties"] = [dict(p) for p in props]

    return result


@router.post("/{group_id}/promote")
def promote_group(group_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    row = db.execute("SELECT status FROM groups WHERE id = ?", (group_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Group not found")
    db.execute("UPDATE groups SET status = 'engaged', updated_at = datetime('now') WHERE id = ?", (group_id,))
    db.commit()
    return {"id": group_id, "status": "engaged"}
