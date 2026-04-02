"""
Contacts API — browse, search, detail, promote.
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from ...web.deps import get_db, get_current_user

router = APIRouter()


@router.get("")
def browse_contacts(
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    status: str = None,
    sort: str = "last_seen_date",
    order: str = "desc",
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    conditions = []
    params = []
    if status:
        conditions.append("status = ?")
        params.append(status)

    where = " AND ".join(conditions) if conditions else "1=1"
    offset = (page - 1) * per_page

    total = db.execute(f"SELECT COUNT(*) FROM contacts WHERE {where}", params).fetchone()[0]

    allowed_sorts = {"last_seen_date", "display_name", "transaction_count", "first_seen_date"}
    if sort not in allowed_sorts:
        sort = "last_seen_date"
    if order not in ("asc", "desc"):
        order = "desc"

    rows = db.execute(
        f"SELECT id, display_name, phone, email, mobile, company_name, status, transaction_count, "
        f"first_seen_date, last_seen_date, job_title "
        f"FROM contacts WHERE {where} ORDER BY {sort} {order} LIMIT ? OFFSET ?",
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
def search_contacts(
    q: str = Query(..., min_length=1),
    limit: int = Query(25, ge=1, le=100),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    rows = db.execute(
        "SELECT c.id, c.display_name, c.phone, c.company_name, c.status, c.transaction_count "
        "FROM contacts c "
        "WHERE c.rowid IN (SELECT rowid FROM contacts_fts WHERE contacts_fts MATCH ?) "
        "LIMIT ?",
        (q, limit)
    ).fetchall()
    return {"results": [dict(r) for r in rows], "total": len(rows)}


@router.get("/{contact_id}")
def contact_detail(contact_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    row = db.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Contact not found")

    result = dict(row)

    # Transactions this contact appears on
    txns = db.execute(
        "SELECT tp.source_id, tp.side, tp.party_name, tp.contact_title, tp.phone, "
        "t.sale_date, t.sale_price, t.display_address, t.city "
        "FROM transaction_parties tp "
        "JOIN transactions t ON tp.source_id = t.source_id "
        "WHERE tp.contact_id = ? ORDER BY t.sale_date DESC",
        (contact_id,)
    ).fetchall()
    result["transactions"] = [dict(t) for t in txns]

    # Group associations
    if result.get("current_group_id"):
        group = db.execute(
            "SELECT id, display_name, status FROM groups WHERE id = ?",
            (result["current_group_id"],)
        ).fetchone()
        result["current_group"] = dict(group) if group else None

    return result


@router.post("/{contact_id}/promote")
def promote_contact(contact_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    row = db.execute("SELECT status FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Contact not found")
    db.execute("UPDATE contacts SET status = 'engaged', updated_at = datetime('now') WHERE id = ?", (contact_id,))
    db.commit()
    return {"id": contact_id, "status": "engaged"}


class ContactUpdate(BaseModel):
    email: str = None
    mobile: str = None
    phone: str = None
    job_title: str = None


@router.patch("/{contact_id}")
def update_contact(contact_id: str, update: ContactUpdate, db=Depends(get_db), user=Depends(get_current_user)):
    row = db.execute("SELECT id FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Contact not found")

    fields = {k: v for k, v in update.dict().items() if v is not None}
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    sets = ", ".join(f"{k} = ?" for k in fields)
    vals = list(fields.values()) + [contact_id]
    db.execute(f"UPDATE contacts SET {sets}, updated_at = datetime('now') WHERE id = ?", vals)
    db.commit()
    return {"id": contact_id, "updated": list(fields.keys())}
