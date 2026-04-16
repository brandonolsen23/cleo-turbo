"""
Tenant categories API — canonical taxonomy for tenant classification.
"""

from fastapi import APIRouter, Depends
from ...web.deps import get_db, get_current_user

router = APIRouter()


@router.get("/")
def list_tenant_categories(db=Depends(get_db), user=Depends(get_current_user)):
    """Return the full tenant category taxonomy as a nested structure.

    Response: {
      categories: [
        { id, label, subcategories: [{ id, label }] }
      ]
    }
    """
    rows = db.execute(
        "SELECT id, label, parent_id, sort_order FROM tenant_categories ORDER BY sort_order"
    ).fetchall()

    # Build nested structure
    broad = []
    subs_by_parent = {}

    for r in rows:
        row = dict(r)
        if row["parent_id"] is None:
            broad.append({"id": row["id"], "label": row["label"], "subcategories": []})
        else:
            subs_by_parent.setdefault(row["parent_id"], []).append(
                {"id": row["id"], "label": row["label"]}
            )

    for b in broad:
        b["subcategories"] = subs_by_parent.get(b["id"], [])

    return {"categories": broad}
