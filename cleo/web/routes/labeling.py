"""Party link labeling API.

Endpoints under /api/labeling. See
docs/superpowers/specs/2026-04-20-party-link-labeling-tool-design.md
for the full design.
"""

from __future__ import annotations
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..deps import get_db, get_current_user
from ...labeling import operations as ops
from ...labeling.audit_parser import list_audits, load_audit_by_slug
from ...labeling.party_view import get_party_view
from ...labeling.seed_harvester import harvest_seeds

router = APIRouter()

DOCS_ROOT = Path(__file__).resolve().parents[3] / "docs" / "discovery-audit"


# ── Models ────────────────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    anchor_source_id: str
    anchor_side: str
    name: str
    audit_slug: Optional[str] = None


class PatchSessionRequest(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None


class LinkPayload(BaseModel):
    from_field_type: str
    from_field_value: str
    to_field_type: str
    to_field_value: str
    kind: str  # 'exact' | 'implied'


class VerdictRequest(BaseModel):
    source_id: str
    side: str
    verdict: str  # 'confirmed' | 'rejected'
    left_source_id: str
    left_side: str
    seed_id: Optional[int] = None
    rationale: Optional[str] = None
    links: List[LinkPayload] = []


class AddSeedRequest(BaseModel):
    term: str
    field_type: str


class SearchRequest(BaseModel):
    term: str
    field_type: Optional[str] = None
    session_id: int


class PatchSeedRequest(BaseModel):
    state: str  # 'pending' | 'in_progress' | 'done' | 'skipped'


class ReviewedRequest(BaseModel):
    source_id: str
    side: str


# ── Helpers ───────────────────────────────────────────────────

def _session_row(db, session_id: int) -> dict:
    row = db.execute("SELECT * FROM labeling_sessions WHERE id = ?", (session_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Session {session_id} not found")
    d = dict(row)
    d["display_id"] = ops.format_session_id(d["id"])
    return d


def _session_summary(db, session_id: int) -> dict:
    s = _session_row(db, session_id)
    counts = db.execute(
        "SELECT "
        "  SUM(verdict = 'confirmed') AS confirmed_count, "
        "  SUM(verdict = 'rejected') AS rejected_count "
        "FROM labeling_verdicts WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    seed_counts = db.execute(
        "SELECT state, COUNT(*) AS c FROM labeling_seeds "
        "WHERE session_id = ? GROUP BY state",
        (session_id,),
    ).fetchall()
    s["confirmed_count"] = counts["confirmed_count"] or 0
    s["rejected_count"] = counts["rejected_count"] or 0
    s["seeds_by_state"] = {r["state"]: r["c"] for r in seed_counts}
    return s


# ── Session endpoints ─────────────────────────────────────────

@router.get("/sessions")
def list_sessions(db=Depends(get_db), user=Depends(get_current_user)):
    rows = db.execute(
        "SELECT id FROM labeling_sessions ORDER BY updated_at DESC"
    ).fetchall()
    return {"sessions": [_session_summary(db, r["id"]) for r in rows]}


@router.post("/sessions")
def create_session(req: CreateSessionRequest, db=Depends(get_db), user=Depends(get_current_user)):
    try:
        sid = ops.create_session(
            db,
            anchor_source_id=req.anchor_source_id,
            anchor_side=req.anchor_side,
            name=req.name,
            audit_slug=req.audit_slug,
            created_by=user["username"],
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _session_summary(db, sid)


@router.get("/sessions/{session_id}")
def get_session(session_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    return _session_summary(db, ops.parse_session_id(session_id))


@router.patch("/sessions/{session_id}")
def patch_session(session_id: str, req: PatchSessionRequest,
                  db=Depends(get_db), user=Depends(get_current_user)):
    sid = ops.parse_session_id(session_id)
    if req.status:
        ops.mark_session_status(db, sid, req.status)
    if req.name:
        db.execute("UPDATE labeling_sessions SET name = ?, updated_at = datetime('now') WHERE id = ?",
                   (req.name, sid))
        db.commit()
    return _session_summary(db, sid)


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    sid = ops.parse_session_id(session_id)
    db.execute("DELETE FROM labeling_sessions WHERE id = ?", (sid,))
    db.commit()
    return {"deleted": True}


# ── Party fetch ───────────────────────────────────────────────

@router.get("/party/{source_id}/{side}")
def fetch_party(source_id: str, side: str,
                db=Depends(get_db), user=Depends(get_current_user)):
    view = get_party_view(db, source_id, side)
    if not view:
        raise HTTPException(404, f"Party not found: {source_id}/{side}")
    return view
