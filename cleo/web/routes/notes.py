"""
Notes API — notes on contacts and groups.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from ...web.deps import get_db, get_current_user

router = APIRouter()


class NoteCreate(BaseModel):
    note: str


# ============================================================
# Contact Notes
# ============================================================

@router.get("/contacts/{contact_id}/notes")
def list_contact_notes(contact_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    rows = db.execute(
        "SELECT id, contact_id, note, created_by, created_at "
        "FROM contact_notes WHERE contact_id = ? ORDER BY created_at DESC",
        (contact_id,)
    ).fetchall()
    return [dict(r) for r in rows]


@router.post("/contacts/{contact_id}/notes")
def create_contact_note(contact_id: str, body: NoteCreate, db=Depends(get_db), user=Depends(get_current_user)):
    # Verify contact exists
    if not db.execute("SELECT 1 FROM contacts WHERE id = ?", (contact_id,)).fetchone():
        raise HTTPException(status_code=404, detail="Contact not found")

    cursor = db.execute(
        "INSERT INTO contact_notes (contact_id, note, created_by) VALUES (?, ?, ?)",
        (contact_id, body.note, user.get("display_name", user.get("username")))
    )
    db.commit()
    return {"id": cursor.lastrowid, "status": "created"}


# ============================================================
# Group Notes
# ============================================================

@router.get("/groups/{group_id}/notes")
def list_group_notes(group_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    rows = db.execute(
        "SELECT id, group_id, note, created_by, created_at "
        "FROM group_notes WHERE group_id = ? ORDER BY created_at DESC",
        (group_id,)
    ).fetchall()
    return [dict(r) for r in rows]


@router.post("/groups/{group_id}/notes")
def create_group_note(group_id: str, body: NoteCreate, db=Depends(get_db), user=Depends(get_current_user)):
    if not db.execute("SELECT 1 FROM groups WHERE id = ?", (group_id,)).fetchone():
        raise HTTPException(status_code=404, detail="Group not found")

    cursor = db.execute(
        "INSERT INTO group_notes (group_id, note, created_by) VALUES (?, ?, ?)",
        (group_id, body.note, user.get("display_name", user.get("username")))
    )
    db.commit()
    return {"id": cursor.lastrowid, "status": "created"}
