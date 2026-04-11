"""
Omnisearch API — cross-entity full-text search.
"""

from fastapi import APIRouter, Depends, Query
from ...web.deps import get_db, get_current_user

router = APIRouter()


@router.get("")
def omnisearch(
    q: str = Query(..., min_length=1),
    limit: int = Query(6, ge=1, le=20),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Search across properties, contacts, and groups."""
    results = []
    like_val = f"%{q.strip()}%"

    # Properties
    props = db.execute(
        "SELECT p.id, p.display_address, p.city "
        "FROM properties p "
        "WHERE p.display_address LIKE ? OR p.city LIKE ? OR p.current_owner_name LIKE ? "
        "LIMIT ?",
        (like_val, like_val, like_val, limit)
    ).fetchall()
    for r in props:
        results.append({
            "type": "property",
            "id": r["id"],
            "title": r["display_address"],
            "subtitle": r["city"],
        })

    # Contacts
    contacts = db.execute(
        "SELECT c.id, c.display_name, c.company_name "
        "FROM contacts c "
        "WHERE c.display_name LIKE ? OR c.company_name LIKE ? "
        "LIMIT ?",
        (like_val, like_val, limit)
    ).fetchall()
    for r in contacts:
        results.append({
            "type": "contact",
            "id": r["id"],
            "title": r["display_name"],
            "subtitle": r["company_name"],
        })

    # Groups
    groups = db.execute(
        "SELECT g.id, g.display_name, g.property_count "
        "FROM groups g "
        "WHERE g.display_name LIKE ? "
        "LIMIT ?",
        (like_val, limit)
    ).fetchall()
    for r in groups:
        results.append({
            "type": "group",
            "id": r["id"],
            "title": r["display_name"],
            "subtitle": f"{r['property_count']} properties" if r["property_count"] else None,
        })

    return {"results": results[:limit * 3], "total": len(results)}
