"""
Asset classes API — canonical taxonomy for property classification.
"""

from fastapi import APIRouter, Depends
from ...web.deps import get_db, get_current_user

router = APIRouter()


@router.get("/")
def list_asset_classes(db=Depends(get_db), user=Depends(get_current_user)):
    """Return the full asset class taxonomy as a nested structure.

    Response: {
      classes: [
        { id, label, subcategories: [{ id, label }] }
      ]
    }
    """
    rows = db.execute(
        "SELECT id, label, parent_id, sort_order FROM asset_classes ORDER BY sort_order"
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

    return {"classes": broad}


@router.get("/distribution")
def asset_class_distribution(db=Depends(get_db), user=Depends(get_current_user)):
    """Return counts of properties per asset class."""
    rows = db.execute(
        "SELECT asset_class, COUNT(*) as count FROM properties "
        "WHERE asset_class IS NOT NULL GROUP BY asset_class ORDER BY count DESC"
    ).fetchall()

    return {"distribution": [dict(r) for r in rows]}
