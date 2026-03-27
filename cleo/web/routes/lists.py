"""
Lists API — prospecting lists with members.
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from ...web.deps import get_db, get_current_user

router = APIRouter()


class ListCreate(BaseModel):
    name: str
    description: Optional[str] = None


class ListUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class MemberAdd(BaseModel):
    member_type: str  # property, contact, group, transaction
    member_id: str


@router.get("")
def browse_lists(db=Depends(get_db), user=Depends(get_current_user)):
    rows = db.execute("SELECT * FROM lists ORDER BY updated_at DESC").fetchall()
    results = []
    for r in rows:
        d = dict(r)
        # Count members by type
        counts = db.execute(
            "SELECT member_type, COUNT(*) as count FROM list_members "
            "WHERE list_id = ? GROUP BY member_type",
            (d["id"],)
        ).fetchall()
        d["member_counts"] = {c["member_type"]: c["count"] for c in counts}
        d["total_members"] = sum(c["count"] for c in counts)
        results.append(d)
    return results


@router.get("/{list_id}")
def list_detail(list_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    lst = db.execute("SELECT * FROM lists WHERE id = ?", (list_id,)).fetchone()
    if not lst:
        raise HTTPException(status_code=404, detail="List not found")

    result = dict(lst)

    # Fetch members with enrichment
    members_raw = db.execute(
        "SELECT member_type, member_id, added_at FROM list_members "
        "WHERE list_id = ? ORDER BY added_at DESC",
        (list_id,)
    ).fetchall()

    members = []
    for m in members_raw:
        entry = dict(m)
        # Enrich with entity name
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
                entry["detail"] = f"{row['property_count']} properties"
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
    list_id = f"LIST_{uuid.uuid4().hex[:8].upper()}"
    db.execute(
        "INSERT INTO lists (id, name, description) VALUES (?, ?, ?)",
        (list_id, body.name, body.description)
    )
    db.commit()
    return {"id": list_id, "status": "created"}


@router.patch("/{list_id}")
def update_list(list_id: str, body: ListUpdate, db=Depends(get_db), user=Depends(get_current_user)):
    if not db.execute("SELECT 1 FROM lists WHERE id = ?", (list_id,)).fetchone():
        raise HTTPException(status_code=404, detail="List not found")

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
            values + [list_id]
        )
        db.commit()

    return {"id": list_id, "updated": list(updates.keys())}


@router.delete("/{list_id}")
def delete_list(list_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    if not db.execute("SELECT 1 FROM lists WHERE id = ?", (list_id,)).fetchone():
        raise HTTPException(status_code=404, detail="List not found")
    db.execute("DELETE FROM list_members WHERE list_id = ?", (list_id,))
    db.execute("DELETE FROM lists WHERE id = ?", (list_id,))
    db.commit()
    return {"id": list_id, "status": "deleted"}


@router.post("/{list_id}/members")
def add_member(list_id: str, body: MemberAdd, db=Depends(get_db), user=Depends(get_current_user)):
    if not db.execute("SELECT 1 FROM lists WHERE id = ?", (list_id,)).fetchone():
        raise HTTPException(status_code=404, detail="List not found")

    if body.member_type not in ("property", "contact", "group", "transaction"):
        raise HTTPException(status_code=400, detail="Invalid member_type")

    try:
        db.execute(
            "INSERT INTO list_members (list_id, member_type, member_id) VALUES (?, ?, ?)",
            (list_id, body.member_type, body.member_id)
        )
        db.commit()
    except Exception:
        raise HTTPException(status_code=409, detail="Already a member")

    # Update list timestamp
    db.execute("UPDATE lists SET updated_at = datetime('now') WHERE id = ?", (list_id,))
    db.commit()

    return {"status": "added"}


@router.delete("/{list_id}/members/{member_type}/{member_id}")
def remove_member(list_id: str, member_type: str, member_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    db.execute(
        "DELETE FROM list_members WHERE list_id = ? AND member_type = ? AND member_id = ?",
        (list_id, member_type, member_id)
    )
    db.execute("UPDATE lists SET updated_at = datetime('now') WHERE id = ?", (list_id,))
    db.commit()
    return {"status": "removed"}
