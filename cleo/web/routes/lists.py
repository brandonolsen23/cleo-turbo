"""
Lists API — prospecting lists with scope (personal/shared) and ownership.

Personal lists are visible only to their owner — they 404 to other users.
Shared lists are visible to everyone; member adds/removes are team-editable;
metadata edits (rename, description, delete) are owner-only.
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from ..deps import get_db, get_current_user

router = APIRouter()


class ListCreate(BaseModel):
    name: str
    description: Optional[str] = None
    scope: Optional[str] = "personal"


class ListUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class MemberAdd(BaseModel):
    member_type: str
    member_id: str


def _user_id(user) -> int:
    return int(user["sub"])


def _list_for_user_or_404(db, list_id: str, me: int):
    """Fetch a list row the user is allowed to see; 404 otherwise."""
    row = db.execute(
        "SELECT * FROM lists WHERE id = ? AND (scope='shared' OR owner_user_id = ?)",
        (list_id, me),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="List not found")
    return row


@router.get("")
def browse_lists(db=Depends(get_db), user=Depends(get_current_user)):
    me = _user_id(user)
    rows = db.execute(
        "SELECT * FROM lists WHERE scope='shared' OR owner_user_id = ? ORDER BY updated_at DESC",
        (me,),
    ).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        counts = db.execute(
            "SELECT member_type, COUNT(*) as count FROM list_members "
            "WHERE list_id = ? GROUP BY member_type",
            (d["id"],),
        ).fetchall()
        d["member_counts"] = {c["member_type"]: c["count"] for c in counts}
        d["total_members"] = sum(c["count"] for c in counts)
        # Owner display name
        if d.get("owner_user_id"):
            owner_row = db.execute(
                "SELECT display_name FROM users WHERE id = ?",
                (d["owner_user_id"],),
            ).fetchone()
            d["owner_name"] = owner_row["display_name"] if owner_row else None
        else:
            d["owner_name"] = None
        results.append(d)
    return results


@router.get("/membership")
def lists_containing_member(
    member_type: str = Query(...),
    member_id: str = Query(...),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """For the AddToListDrawer pre-checked state: which of the user's accessible
    lists already contain this member?"""
    me = _user_id(user)
    rows = db.execute(
        """
        SELECT l.id AS list_id, l.name AS list_name, l.scope
        FROM lists l
        JOIN list_members lm ON lm.list_id = l.id
        WHERE lm.member_type = ? AND lm.member_id = ?
          AND (l.scope = 'shared' OR l.owner_user_id = ?)
        """,
        (member_type, member_id, me),
    ).fetchall()
    return [dict(r) for r in rows]


@router.get("/{list_id}")
def list_detail(list_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    me = _user_id(user)
    lst = _list_for_user_or_404(db, list_id, me)
    result = dict(lst)
    members_raw = db.execute(
        "SELECT member_type, member_id, added_at FROM list_members "
        "WHERE list_id = ? ORDER BY added_at DESC",
        (list_id,),
    ).fetchall()
    members = []
    for m in members_raw:
        entry = dict(m)
        if m["member_type"] == "property":
            row = db.execute("SELECT display_address, city FROM properties WHERE id = ?", (m["member_id"],)).fetchone()
            if row:
                entry["name"] = row["display_address"]
                entry["detail"] = row["city"]
        elif m["member_type"] == "contact":
            row = db.execute("SELECT display_name, company_name FROM contacts WHERE id = ?", (m["member_id"],)).fetchone()
            if row:
                entry["name"] = row["display_name"]
                entry["detail"] = row["company_name"]
        elif m["member_type"] == "group":
            row = db.execute("SELECT display_name, property_count FROM groups WHERE id = ?", (m["member_id"],)).fetchone()
            if row:
                entry["name"] = row["display_name"]
                entry["detail"] = f"{row['property_count']} properties" if row["property_count"] is not None else None
        elif m["member_type"] == "transaction":
            row = db.execute("SELECT display_address, city FROM transactions WHERE source_id = ?", (m["member_id"],)).fetchone()
            if row:
                entry["name"] = row["display_address"]
                entry["detail"] = row["city"]
        members.append(entry)
    result["members"] = members
    return result


@router.post("")
def create_list(body: ListCreate, db=Depends(get_db), user=Depends(get_current_user)):
    me = _user_id(user)
    scope = body.scope if body.scope in ("personal", "shared") else "personal"
    list_id = f"LIST_{uuid.uuid4().hex[:8].upper()}"
    db.execute(
        "INSERT INTO lists (id, name, description, owner_user_id, scope) VALUES (?, ?, ?, ?, ?)",
        (list_id, body.name, body.description, me, scope),
    )
    db.commit()
    return {"id": list_id, "status": "created", "scope": scope}


@router.patch("/{list_id}")
def update_list(list_id: str, body: ListUpdate, db=Depends(get_db), user=Depends(get_current_user)):
    me = _user_id(user)
    row = _list_for_user_or_404(db, list_id, me)
    if row["owner_user_id"] != me:
        raise HTTPException(status_code=403, detail="Only the list owner can rename or describe a list")
    updates = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.description is not None:
        updates["description"] = body.description
    if updates:
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values())
        db.execute(
            f"UPDATE lists SET {set_clause}, updated_at = datetime('now') WHERE id = ?",
            values + [list_id],
        )
        db.commit()
    return {"id": list_id, "updated": list(updates.keys())}


@router.delete("/{list_id}")
def delete_list(list_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    me = _user_id(user)
    row = _list_for_user_or_404(db, list_id, me)
    if row["owner_user_id"] != me:
        raise HTTPException(status_code=403, detail="Only the list owner can delete a list")
    db.execute("DELETE FROM list_members WHERE list_id = ?", (list_id,))
    db.execute("DELETE FROM lists WHERE id = ?", (list_id,))
    db.commit()
    return {"id": list_id, "status": "deleted"}


@router.post("/{list_id}/members")
def add_member(list_id: str, body: MemberAdd, db=Depends(get_db), user=Depends(get_current_user)):
    me = _user_id(user)
    _list_for_user_or_404(db, list_id, me)  # 404 if hidden personal list
    if body.member_type not in ("property", "contact", "group", "transaction"):
        raise HTTPException(status_code=400, detail="Invalid member_type")
    db.execute(
        "INSERT OR IGNORE INTO list_members (list_id, member_type, member_id) VALUES (?, ?, ?)",
        (list_id, body.member_type, body.member_id),
    )
    db.execute("UPDATE lists SET updated_at = datetime('now') WHERE id = ?", (list_id,))
    db.commit()
    return {"status": "added"}


@router.delete("/{list_id}/members/{member_type}/{member_id}")
def remove_member(list_id: str, member_type: str, member_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    me = _user_id(user)
    _list_for_user_or_404(db, list_id, me)
    db.execute(
        "DELETE FROM list_members WHERE list_id=? AND member_type=? AND member_id=?",
        (list_id, member_type, member_id),
    )
    db.execute("UPDATE lists SET updated_at = datetime('now') WHERE id = ?", (list_id,))
    db.commit()
    return {"status": "removed"}
