"""
Brands API — browse, favorites, category overrides.

Provides the brand registry (all known brands from POI data),
user-level favorite management, and category override support.
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from ...web.deps import get_db, get_current_user

router = APIRouter()


# ── Request models ──────────────────────────────────────────────

class FavoritesRequest(BaseModel):
    brands: List[str]


class CategoryOverrideRequest(BaseModel):
    brand: str
    category: str


class CategoryDeleteRequest(BaseModel):
    brand: str


# ── Fixed category list ─────────────────────────────────────────

RETAIL_CATEGORIES = [
    {"id": "Grocery", "color": "lime"},
    {"id": "Big-Box Retail", "color": "blue"},
    {"id": "Discount Retail", "color": "amber"},
    {"id": "Specialty Retail", "color": "plum"},
    {"id": "QSR", "color": "orange"},
    {"id": "Full-Service", "color": "violet"},
    {"id": "Take-out", "color": "pink"},
    {"id": "Fuel", "color": "indigo"},
    {"id": "Financial Services", "color": "cyan"},
    {"id": "Automotive", "color": "tomato"},
]


# ── Helpers ──────────────────────────────────────────────────────

def _ensure_favorites_seeded(db, user_id: int):
    """If the user has no favorites, seed from curated brands."""
    count = db.execute(
        "SELECT COUNT(*) FROM user_brand_favorites WHERE user_id = ?",
        (user_id,)
    ).fetchone()[0]

    if count == 0:
        # Seed from all curated brands in the registry
        curated = db.execute(
            "SELECT brand FROM brand_registry WHERE is_curated = 1"
        ).fetchall()
        for row in curated:
            db.execute(
                "INSERT OR IGNORE INTO user_brand_favorites (user_id, brand) VALUES (?, ?)",
                (user_id, row[0])
            )
        db.commit()
        return len(curated)
    return 0


# ── Endpoints ────────────────────────────────────────────────────

@router.get("/categories")
def list_categories(user=Depends(get_current_user)):
    """Return the fixed category list with colors."""
    return {"categories": RETAIL_CATEGORIES}


@router.get("/favorites")
def get_favorites(
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Return the current user's favorite brands with effective categories."""
    user_id = user["id"]
    _ensure_favorites_seeded(db, user_id)

    rows = db.execute("""
        SELECT
            br.brand,
            COALESCE(bo.category, br.category) AS category,
            br.poi_count,
            br.is_curated
        FROM user_brand_favorites ubf
        JOIN brand_registry br ON br.brand = ubf.brand
        LEFT JOIN brand_overrides bo ON bo.brand = br.brand
        WHERE ubf.user_id = ?
        ORDER BY COALESCE(bo.category, br.category), br.brand
    """, (user_id,)).fetchall()

    return {
        "favorites": [
            {
                "brand": r[0],
                "category": r[1] if r[1] else None,
                "poi_count": r[2],
                "is_curated": bool(r[3]),
            }
            for r in rows
        ]
    }


@router.post("/favorites")
def add_favorites(
    req: FavoritesRequest,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Add brands to the current user's favorites."""
    user_id = user["id"]
    added = 0
    for brand in req.brands:
        # Verify brand exists in registry
        exists = db.execute(
            "SELECT 1 FROM brand_registry WHERE brand = ?", (brand,)
        ).fetchone()
        if exists:
            db.execute(
                "INSERT OR IGNORE INTO user_brand_favorites (user_id, brand) VALUES (?, ?)",
                (user_id, brand)
            )
            added += 1
    db.commit()
    return {"added": added}


@router.delete("/favorites")
def remove_favorites(
    req: FavoritesRequest,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Remove brands from the current user's favorites."""
    user_id = user["id"]
    removed = 0
    for brand in req.brands:
        cursor = db.execute(
            "DELETE FROM user_brand_favorites WHERE user_id = ? AND brand = ?",
            (user_id, brand)
        )
        removed += cursor.rowcount
    db.commit()
    return {"removed": removed}


@router.get("")
def browse_brands(
    search: str = None,
    category: str = None,
    favorites_only: bool = False,
    curated_only: bool = False,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=500),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Browse all brands with effective category and favorite status."""
    user_id = user["id"]
    _ensure_favorites_seeded(db, user_id)

    conditions = []
    params = []

    if search and search.strip():
        conditions.append("br.brand LIKE ?")
        params.append(f"%{search.strip()}%")

    if category:
        conditions.append("COALESCE(bo.category, br.category) = ?")
        params.append(category)

    if favorites_only:
        conditions.append("ubf.brand IS NOT NULL")

    if curated_only:
        conditions.append("br.is_curated = 1")

    where = " AND ".join(conditions) if conditions else "1=1"
    offset = (page - 1) * per_page

    # Count total
    count_sql = f"""
        SELECT COUNT(*)
        FROM brand_registry br
        LEFT JOIN brand_overrides bo ON bo.brand = br.brand
        LEFT JOIN user_brand_favorites ubf ON ubf.brand = br.brand AND ubf.user_id = ?
        WHERE {where}
    """
    total = db.execute(count_sql, [user_id] + params).fetchone()[0]

    # Fetch page
    query_sql = f"""
        SELECT
            br.brand,
            COALESCE(bo.category, br.category) AS effective_category,
            br.poi_count,
            br.is_curated,
            CASE WHEN ubf.brand IS NOT NULL THEN 1 ELSE 0 END AS is_favorite
        FROM brand_registry br
        LEFT JOIN brand_overrides bo ON bo.brand = br.brand
        LEFT JOIN user_brand_favorites ubf ON ubf.brand = br.brand AND ubf.user_id = ?
        WHERE {where}
        ORDER BY br.poi_count DESC, br.brand
        LIMIT ? OFFSET ?
    """
    rows = db.execute(query_sql, [user_id] + params + [per_page, offset]).fetchall()

    pages = (total + per_page - 1) // per_page if total > 0 else 1

    return {
        "brands": [
            {
                "brand": r[0],
                "category": r[1] if r[1] else None,
                "poi_count": r[2],
                "is_curated": bool(r[3]),
                "is_favorite": bool(r[4]),
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }


@router.put("/category")
def set_category_override(
    req: CategoryOverrideRequest,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Set or change the category for a brand (writes to brand_overrides)."""
    # Verify brand exists
    exists = db.execute(
        "SELECT 1 FROM brand_registry WHERE brand = ?", (req.brand,)
    ).fetchone()
    if not exists:
        raise HTTPException(status_code=404, detail="Brand not found in registry")

    # Validate category
    valid_categories = {c["id"] for c in RETAIL_CATEGORIES}
    if req.category not in valid_categories:
        raise HTTPException(status_code=400, detail=f"Invalid category. Must be one of: {', '.join(sorted(valid_categories))}")

    db.execute(
        "INSERT OR REPLACE INTO brand_overrides (brand, category, updated_by, updated_at) "
        "VALUES (?, ?, ?, datetime('now'))",
        (req.brand, req.category, str(user["id"]))
    )
    db.commit()

    return {"brand": req.brand, "category": req.category, "source": "override"}


@router.delete("/category")
def remove_category_override(
    req: CategoryDeleteRequest,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Remove a category override (reverts to CSV default or null)."""
    db.execute("DELETE FROM brand_overrides WHERE brand = ?", (req.brand,))
    db.commit()

    # Return the effective category after removal
    row = db.execute(
        "SELECT category FROM brand_registry WHERE brand = ?", (req.brand,)
    ).fetchone()
    default_category = row[0] if row and row[0] else None

    return {"brand": req.brand, "category": default_category, "source": "default"}
