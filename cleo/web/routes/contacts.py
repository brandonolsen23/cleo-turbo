"""
Contacts API — browse, search, detail, promote.
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from ...web.deps import get_db, get_current_user, fts_query
from ...web.audit import log_action

router = APIRouter()


@router.get("/filters")
def contact_filters(db=Depends(get_db), user=Depends(get_current_user)):
    """Available filter values for the Contacts page."""
    contact_types = db.execute(
        "SELECT DISTINCT contact_type FROM contacts WHERE contact_type IS NOT NULL ORDER BY contact_type"
    ).fetchall()
    regions = db.execute(
        "SELECT DISTINCT t.region FROM transaction_parties tp "
        "JOIN transactions t ON tp.source_id = t.source_id "
        "WHERE t.region != '' GROUP BY t.region ORDER BY t.region"
    ).fetchall()
    return {
        "contact_types": [r[0] for r in contact_types],
        "regions": [r[0] for r in regions],
    }


@router.get("")
def browse_contacts(
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    status: str = None,
    contact_type: str = None,
    min_transactions: int = None,
    max_transactions: int = None,
    min_buy_value: int = None,
    max_buy_value: int = None,
    region: str = None,
    asset_class: str = None,
    min_asset_class_count: int = Query(None, ge=1),
    max_asset_class_count: int = Query(None, ge=1),
    q: str = None,
    sort: str = "last_seen_date",
    order: str = "desc",
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    conditions = []
    params = []
    if status:
        conditions.append("c.status = ?")
        params.append(status)
    if contact_type:
        conditions.append("c.contact_type = ?")
        params.append(contact_type)
    if min_transactions is not None:
        conditions.append("c.transaction_count >= ?")
        params.append(min_transactions)
    if max_transactions is not None:
        conditions.append("c.transaction_count <= ?")
        params.append(max_transactions)
    if q and q.strip():
        conditions.append(
            "(c.display_name LIKE ? OR c.company_name LIKE ? OR c.phone LIKE ?)"
        )
        like_val = f"%{q.strip()}%"
        params.extend([like_val, like_val, like_val])
    if region:
        conditions.append(
            "c.id IN (SELECT tp.contact_id FROM transaction_parties tp "
            "JOIN transactions t ON tp.source_id = t.source_id "
            "WHERE t.region = ? AND tp.contact_id IS NOT NULL)"
        )
        params.append(region)
    # Buy value filters use a subquery on the same aggregation we SELECT
    buy_value_subquery = (
        "(SELECT SUM(t.sale_price) FROM transaction_parties tp "
        "JOIN transactions t ON t.source_id = tp.source_id "
        "WHERE tp.contact_id = c.id AND tp.side = 'buyer' AND t.sale_price IS NOT NULL)"
    )
    if min_buy_value is not None:
        conditions.append(f"{buy_value_subquery} >= ?")
        params.append(min_buy_value)
    if max_buy_value is not None:
        conditions.append(f"{buy_value_subquery} <= ?")
        params.append(max_buy_value)
    if asset_class:
        min_ac = min_asset_class_count or 1
        having = "HAVING COUNT(*) >= ?"
        ac_params = [asset_class, min_ac]
        if max_asset_class_count is not None:
            having += " AND COUNT(*) <= ?"
            ac_params.append(max_asset_class_count)
        # Filter contacts whose current group owns N..M properties of this class
        conditions.append(
            f"c.current_group_id IN (SELECT current_owner_group_id FROM properties "
            f"WHERE asset_class = ? AND current_owner_group_id IS NOT NULL "
            f"GROUP BY current_owner_group_id {having})"
        )
        params.extend(ac_params)

    where = " AND ".join(conditions) if conditions else "1=1"
    offset = (page - 1) * per_page

    total = db.execute(f"SELECT COUNT(*) FROM contacts c WHERE {where}", params).fetchone()[0]

    allowed_sorts = {"last_seen_date", "display_name", "transaction_count", "first_seen_date", "total_buy_value"}
    if sort not in allowed_sorts:
        sort = "last_seen_date"
    if order not in ("asc", "desc"):
        order = "desc"

    # total_buy_value is a computed column, so ORDER BY uses the alias
    order_clause = f"total_buy_value {order}" if sort == "total_buy_value" else f"c.{sort} {order}"
    # When sorting by buy value, put NULLs last
    if sort == "total_buy_value":
        order_clause = f"total_buy_value IS NULL, {order_clause}"

    rows = db.execute(
        f"SELECT c.id, c.display_name, c.phone, c.email, c.mobile, c.company_name, c.status, "
        f"c.contact_type, c.transaction_count, c.first_seen_date, c.last_seen_date, c.job_title, "
        f"{buy_value_subquery} as total_buy_value "
        f"FROM contacts c WHERE {where} ORDER BY {order_clause} LIMIT ? OFFSET ?",
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
    like_val = f"%{q.strip()}%"
    rows = db.execute(
        "SELECT c.id, c.display_name, c.phone, c.company_name, c.status, c.transaction_count "
        "FROM contacts c "
        "WHERE c.display_name LIKE ? OR c.company_name LIKE ? OR c.phone LIKE ? "
        "LIMIT ?",
        (like_val, like_val, like_val, limit)
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
            "SELECT id, display_name, status, hq_address FROM groups WHERE id = ?",
            (result["current_group_id"],)
        ).fetchone()
        if group:
            gd = dict(group)
            # Fallback: buyer mailing address from contact's most recent transaction
            if not gd.get("hq_address") and result.get("transactions"):
                latest_src = result["transactions"][0].get("source_id")
                if latest_src:
                    ma = db.execute(
                        "SELECT display, geocode_string FROM transaction_mailing_addresses "
                        "WHERE source_id = ? AND side = 'buyer'",
                        (latest_src,)
                    ).fetchone()
                    if ma:
                        gd["hq_address"] = ma["geocode_string"] or ma["display"]
            result["current_group"] = gd
        else:
            result["current_group"] = None

    return result


@router.get("/{contact_id}/properties")
def contact_property_history(contact_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    """All properties a contact has been party to (via transaction_parties), with lat/lng for mapping."""
    row = db.execute("SELECT id FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Contact not found")

    rows = db.execute(
        "SELECT DISTINCT p.id, p.display_address, p.city, p.lat, p.lng, p.asset_class, "
        "p.most_recent_sale_price, p.current_owner_name, p.current_owner_group_id "
        "FROM transaction_parties tp "
        "JOIN transactions t ON tp.source_id = t.source_id "
        "JOIN properties p ON t.property_id = p.id "
        "WHERE tp.contact_id = ? AND p.lat IS NOT NULL AND p.lng IS NOT NULL",
        (contact_id,)
    ).fetchall()
    return {"properties": [dict(r) for r in rows]}


@router.post("/{contact_id}/promote")
def promote_contact(contact_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    row = db.execute("SELECT status FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Contact not found")
    db.execute("UPDATE contacts SET status = 'engaged', updated_at = datetime('now') WHERE id = ?", (contact_id,))
    # Persist status override so it survives recompiles
    db.execute(
        "INSERT INTO contact_field_overrides (contact_id, status, updated_by) VALUES (?, 'engaged', ?) "
        "ON CONFLICT(contact_id) DO UPDATE SET status = 'engaged', updated_by = ?, updated_at = datetime('now')",
        (contact_id, user["username"], user["username"])
    )
    log_action(db, user, "contact.promote", "contact", contact_id, {"from_status": row["status"]})
    db.commit()
    return {"id": contact_id, "status": "engaged"}


class ContactUpdate(BaseModel):
    email: str = None
    mobile: str = None
    phone: str = None
    job_title: str = None
    contact_type: str = None

# Fields that get persisted to contact_field_overrides so they survive recompiles
_CONTACT_OVERRIDE_FIELDS = {'email', 'mobile', 'phone', 'job_title', 'contact_type'}


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

    # Persist user-edited fields to contact_field_overrides so they survive recompiles
    override_fields = {k: v for k, v in fields.items() if k in _CONTACT_OVERRIDE_FIELDS}
    if override_fields:
        # Ensure row exists
        db.execute(
            "INSERT OR IGNORE INTO contact_field_overrides (contact_id, updated_by) VALUES (?, ?)",
            (contact_id, user["username"])
        )
        for col, val in override_fields.items():
            db.execute(
                f"UPDATE contact_field_overrides SET {col} = ?, updated_by = ?, updated_at = datetime('now') "
                "WHERE contact_id = ?",
                (val, user["username"], contact_id)
            )

    db.commit()
    return {"id": contact_id, "updated": list(fields.keys())}


@router.get("/{contact_id}/affiliated-groups")
def contact_affiliated_groups(contact_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    """Returns all groups this contact has been associated with across all transactions."""
    contact = db.execute("SELECT id, display_name FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    if not contact:
        raise HTTPException(404, "Contact not found")

    rows = db.execute("""
        SELECT
            g.id, g.display_name, g.normalized_name, g.status,
            g.property_count, g.transaction_count, g.contact_count,
            CASE WHEN c.current_group_id = g.id THEN 1 ELSE 0 END as is_current_group,
            COUNT(DISTINCT tp_contact.source_id) as shared_transactions
        FROM transaction_parties tp_contact
        JOIN transaction_parties tp_group ON tp_contact.source_id = tp_group.source_id
            AND tp_group.group_id IS NOT NULL
            AND tp_group.side = tp_contact.side
        JOIN groups g ON tp_group.group_id = g.id
        JOIN contacts c ON c.id = ?
        WHERE tp_contact.contact_id = ?
            AND g.status != 'merged'
        GROUP BY g.id
        ORDER BY shared_transactions DESC
    """, (contact_id, contact_id)).fetchall()

    return {
        "contact": dict(contact),
        "affiliated_groups": [dict(r) for r in rows],
    }
