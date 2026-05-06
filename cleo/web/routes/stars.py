"""
Stars API — per-user favourites/queue.

A star is a personal pointer to a contact, property, or group that the
current user wants to come back to. The /api/stars list payload powers
the Queue page; each row is enriched with display name, secondary
detail, and (when a teammate has engaged the entity *after* you starred
it) a team_activity object so you don't accidentally double-touch.
"""
import json
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from ..deps import get_db, get_current_user
from ..audit import log_action

router = APIRouter()

ALLOWED_ENTITY_TYPES = ("contact", "property", "group")


class StarCreate(BaseModel):
    entity_type: str
    entity_id: str


def _user_id(user) -> int:
    """JWT puts users.id in the 'sub' field (see cleo/web/auth.py:create_token)."""
    return int(user["sub"])


@router.post("")
def create_star(body: StarCreate, db=Depends(get_db), user=Depends(get_current_user)):
    if body.entity_type not in ALLOWED_ENTITY_TYPES:
        raise HTTPException(status_code=400, detail=f"entity_type must be one of {ALLOWED_ENTITY_TYPES}")
    me = _user_id(user)
    db.execute(
        "INSERT OR IGNORE INTO user_stars (user_id, entity_type, entity_id) VALUES (?, ?, ?)",
        (me, body.entity_type, body.entity_id),
    )
    log_action(db, user, "star.add", body.entity_type, body.entity_id, None)
    db.commit()
    return {"status": "starred"}


@router.delete("/{entity_type}/{entity_id}")
def delete_star(entity_type: str, entity_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    if entity_type not in ALLOWED_ENTITY_TYPES:
        raise HTTPException(status_code=400, detail=f"entity_type must be one of {ALLOWED_ENTITY_TYPES}")
    me = _user_id(user)
    db.execute(
        "DELETE FROM user_stars WHERE user_id=? AND entity_type=? AND entity_id=?",
        (me, entity_type, entity_id),
    )
    log_action(db, user, "star.remove", entity_type, entity_id, None)
    db.commit()
    return {"status": "unstarred"}


@router.get("/check")
def check_star(
    entity_type: str = Query(...),
    entity_id: str = Query(...),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    if entity_type not in ALLOWED_ENTITY_TYPES:
        raise HTTPException(status_code=400, detail=f"entity_type must be one of {ALLOWED_ENTITY_TYPES}")
    me = _user_id(user)
    row = db.execute(
        "SELECT 1 FROM user_stars WHERE user_id=? AND entity_type=? AND entity_id=?",
        (me, entity_type, entity_id),
    ).fetchone()
    return {"starred": row is not None}


@router.get("")
def list_stars(
    entity_type: Optional[str] = None,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    me = _user_id(user)
    if entity_type and entity_type not in ALLOWED_ENTITY_TYPES:
        raise HTTPException(status_code=400, detail=f"entity_type must be one of {ALLOWED_ENTITY_TYPES}")

    sql = "SELECT entity_type, entity_id, starred_at FROM user_stars WHERE user_id = ?"
    params = [me]
    if entity_type:
        sql += " AND entity_type = ?"
        params.append(entity_type)
    sql += " ORDER BY starred_at DESC"

    stars = db.execute(sql, params).fetchall()
    results = []
    for s in stars:
        item = {
            "user_id": me,
            "entity_type": s["entity_type"],
            "entity_id": s["entity_id"],
            "starred_at": s["starred_at"],
            "name": None,
            "detail": None,
            "team_activity": None,
        }
        # 1. Enrich with name + detail per entity type
        if s["entity_type"] == "contact":
            row = db.execute(
                "SELECT display_name, company_name FROM contacts WHERE id = ?",
                (s["entity_id"],),
            ).fetchone()
            if row:
                item["name"] = row["display_name"]
                item["detail"] = row["company_name"]
        elif s["entity_type"] == "property":
            row = db.execute(
                "SELECT display_address, city FROM properties WHERE id = ?",
                (s["entity_id"],),
            ).fetchone()
            if row:
                item["name"] = row["display_address"]
                item["detail"] = row["city"]
        elif s["entity_type"] == "group":
            row = db.execute(
                "SELECT display_name, property_count FROM groups WHERE id = ?",
                (s["entity_id"],),
            ).fetchone()
            if row:
                item["name"] = row["display_name"]
                item["detail"] = f"{row['property_count']} properties" if row["property_count"] is not None else None

        # 2. team_activity — only counts activities by another user that happened
        #    AFTER the star was placed. The FK column we look at depends on entity_type.
        fk_col = {"contact": "contact_id", "property": "property_id", "group": "group_id"}[s["entity_type"]]
        team_row = db.execute(
            f"""
            SELECT a.created_by_user_id AS by_user_id,
                   u.display_name AS by_user_name,
                   a.happened_at, a.activity_type, a.outcome
            FROM activities a
            JOIN users u ON u.id = a.created_by_user_id
            WHERE a.{fk_col} = ?
              AND a.created_by_user_id != ?
              AND a.happened_at > ?
            ORDER BY a.happened_at DESC
            LIMIT 1
            """,
            (s["entity_id"], me, s["starred_at"]),
        ).fetchone()
        if team_row:
            item["team_activity"] = {
                "by_user_id": team_row["by_user_id"],
                "by_user_name": team_row["by_user_name"],
                "happened_at": team_row["happened_at"],
                "activity_type": team_row["activity_type"],
                "outcome": team_row["outcome"],
            }

        results.append(item)

    return results
