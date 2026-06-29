"""Auto-group user edit endpoints — Phase C of the Group Identity System.

Five operations: detach, attach, rename, merge, create. Each writes an
auto_group_user_edits audit row AND applies the change to auto_group_members /
auto_groups immediately, so the UI sees instant updates. The discovery_v2
Stage Z (`apply_user_edits`) re-applies these on every rebuild so they
survive forever.
"""
from __future__ import annotations
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...web.deps import get_db, get_current_user

router = APIRouter()


# ── Helpers ────────────────────────────────────────────────────────────────

def _next_auto_group_id(db) -> str:
    """Compute the next AGRP_NNNNN id by scanning existing rows."""
    max_n = 0
    for r in db.execute("SELECT auto_group_id FROM auto_groups WHERE auto_group_id LIKE 'AGRP_%'"):
        try:
            n = int(r['auto_group_id'].split('_', 1)[1])
            if n > max_n:
                max_n = n
        except (ValueError, IndexError):
            pass
    return f'AGRP_{max_n + 1:05d}'


def _ensure_auto_group_exists(db, auto_group_id: str) -> None:
    row = db.execute(
        "SELECT 1 FROM auto_groups WHERE auto_group_id = ?", (auto_group_id,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"auto_group {auto_group_id} not found")


def _username(user) -> str:
    """Best-effort extraction of the current user's identifier for audit trail."""
    if isinstance(user, dict):
        return user.get('username') or user.get('email') or 'unknown'
    for attr in ('username', 'email', 'name'):
        if hasattr(user, attr):
            v = getattr(user, attr)
            if v:
                return str(v)
    return 'unknown'


# ── Request bodies ─────────────────────────────────────────────────────────

class DetachRequest(BaseModel):
    source_id: str
    side: str
    notes: Optional[str] = None


class AttachRequest(BaseModel):
    source_id: str
    side: str
    notes: Optional[str] = None


class RenameRequest(BaseModel):
    new_display_name: str
    notes: Optional[str] = None


class MergeRequest(BaseModel):
    target_auto_group_id: str
    notes: Optional[str] = None


class CreateRequest(BaseModel):
    canonical_stem: str
    display_name: str
    notes: Optional[str] = None


class SetAddressRequest(BaseModel):
    primary_address: str
    notes: Optional[str] = None


class EnrichRequest(BaseModel):
    website_url: Optional[str] = None
    notes: Optional[str] = None


class AcceptEnrichmentRequest(BaseModel):
    primary_address: Optional[str] = None
    website: Optional[str] = None
    primary_phone: Optional[str] = None
    notes: Optional[str] = None


# ── Endpoints ──────────────────────────────────────────────────────────────


@router.post("/{auto_group_id}/parties/detach")
def detach_party(
    auto_group_id: str,
    body: DetachRequest,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Remove (source_id, side) from this auto_group."""
    if body.side not in ('buyer', 'seller'):
        raise HTTPException(status_code=400, detail="side must be 'buyer' or 'seller'")
    _ensure_auto_group_exists(db, auto_group_id)

    db.execute(
        "INSERT INTO auto_group_user_edits "
        "(edit_type, auto_group_id, source_id, side, edited_by, notes) "
        "VALUES ('detach', ?, ?, ?, ?, ?)",
        (auto_group_id, body.source_id, body.side, _username(user), body.notes),
    )
    deleted = db.execute(
        "DELETE FROM auto_group_members "
        "WHERE auto_group_id = ? AND source_id = ? AND side = ? AND member_type = 'party_side'",
        (auto_group_id, body.source_id, body.side),
    ).rowcount
    # Recompute n_members
    db.execute(
        "UPDATE auto_groups SET n_members = ("
        "SELECT COUNT(*) FROM auto_group_members WHERE auto_group_id = auto_groups.auto_group_id"
        ") WHERE auto_group_id = ?",
        (auto_group_id,),
    )
    db.commit()
    return {"ok": True, "deleted": deleted, "auto_group_id": auto_group_id}


@router.post("/{auto_group_id}/parties/attach")
def attach_party(
    auto_group_id: str,
    body: AttachRequest,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Force-attach (source_id, side) to this auto_group, detaching from any prior."""
    if body.side not in ('buyer', 'seller'):
        raise HTTPException(status_code=400, detail="side must be 'buyer' or 'seller'")
    _ensure_auto_group_exists(db, auto_group_id)

    # Audit row records both source and target where applicable
    db.execute(
        "INSERT INTO auto_group_user_edits "
        "(edit_type, auto_group_id, source_id, side, target_auto_group_id, edited_by, notes) "
        "VALUES ('attach', ?, ?, ?, ?, ?, ?)",
        (auto_group_id, body.source_id, body.side, auto_group_id, _username(user), body.notes),
    )
    # Detach from any prior auto_group, then attach
    db.execute(
        "DELETE FROM auto_group_members "
        "WHERE source_id = ? AND side = ? AND member_type = 'party_side'",
        (body.source_id, body.side),
    )
    db.execute(
        "INSERT OR IGNORE INTO auto_group_members "
        "(auto_group_id, member_type, source_id, side, corp_name, match_score, attached_by) "
        "VALUES (?, 'party_side', ?, ?, NULL, 1.0, 'user_edit')",
        (auto_group_id, body.source_id, body.side),
    )
    # Recompute n_members for the target
    db.execute(
        "UPDATE auto_groups SET n_members = ("
        "SELECT COUNT(*) FROM auto_group_members WHERE auto_group_id = auto_groups.auto_group_id"
        ")"
    )
    db.commit()
    return {"ok": True, "auto_group_id": auto_group_id}


@router.patch("/{auto_group_id}")
def rename_auto_group(
    auto_group_id: str,
    body: RenameRequest,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Override display_name for this auto_group."""
    _ensure_auto_group_exists(db, auto_group_id)
    name = body.new_display_name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="new_display_name must be non-empty")

    db.execute(
        "INSERT INTO auto_group_user_edits "
        "(edit_type, auto_group_id, new_display_name, edited_by, notes) "
        "VALUES ('rename', ?, ?, ?, ?)",
        (auto_group_id, name, _username(user), body.notes),
    )
    db.execute(
        "UPDATE auto_groups SET display_name = ? WHERE auto_group_id = ?",
        (name, auto_group_id),
    )
    db.commit()
    return {"ok": True, "auto_group_id": auto_group_id, "display_name": name}


@router.post("/{auto_group_id}/merge")
def merge_auto_group(
    auto_group_id: str,
    body: MergeRequest,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Move all members of {auto_group_id} into target, mark source as merged."""
    if auto_group_id == body.target_auto_group_id:
        raise HTTPException(status_code=400, detail="cannot merge a group into itself")
    _ensure_auto_group_exists(db, auto_group_id)
    _ensure_auto_group_exists(db, body.target_auto_group_id)

    db.execute(
        "INSERT INTO auto_group_user_edits "
        "(edit_type, auto_group_id, target_auto_group_id, edited_by, notes) "
        "VALUES ('merge', ?, ?, ?, ?)",
        (auto_group_id, body.target_auto_group_id, _username(user), body.notes),
    )
    # Move members
    db.execute(
        "INSERT OR IGNORE INTO auto_group_members "
        "(auto_group_id, member_type, source_id, side, corp_name, match_score, attached_by) "
        "SELECT ?, member_type, source_id, side, corp_name, match_score, 'user_edit' "
        "FROM auto_group_members WHERE auto_group_id = ?",
        (body.target_auto_group_id, auto_group_id),
    )
    db.execute("DELETE FROM auto_group_members WHERE auto_group_id = ?", (auto_group_id,))
    # Mark source as merged
    db.execute(
        "UPDATE auto_groups SET tier = 'merged', n_members = 0 WHERE auto_group_id = ?",
        (auto_group_id,),
    )
    # Recompute n_members for target
    db.execute(
        "UPDATE auto_groups SET n_members = ("
        "SELECT COUNT(*) FROM auto_group_members WHERE auto_group_id = ?"
        ") WHERE auto_group_id = ?",
        (body.target_auto_group_id, body.target_auto_group_id),
    )
    db.commit()
    return {"ok": True, "merged": auto_group_id, "into": body.target_auto_group_id}


@router.post("")
def create_auto_group(
    body: CreateRequest,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Create a new user-defined auto_group (e.g. to host a newly recognized family office)."""
    stem = body.canonical_stem.strip().lower()
    name = body.display_name.strip()
    if not stem or not name:
        raise HTTPException(status_code=400, detail="canonical_stem and display_name required")

    new_id = _next_auto_group_id(db)
    db.execute(
        "INSERT INTO auto_groups "
        "(auto_group_id, canonical_stem, display_name, tier, confidence, n_anchors, n_members) "
        "VALUES (?, ?, ?, 'confirmed', 1.0, 0, 0)",
        (new_id, stem, name),
    )
    db.execute(
        "INSERT INTO auto_group_user_edits "
        "(edit_type, auto_group_id, new_display_name, new_canonical_stem, edited_by, notes) "
        "VALUES ('create', ?, ?, ?, ?, ?)",
        (new_id, name, stem, _username(user), body.notes),
    )
    db.commit()
    return {"ok": True, "auto_group_id": new_id, "canonical_stem": stem, "display_name": name}


# ── Wave 5b: HQ address candidates + manual pick ───────────────────────────


@router.get("/{auto_group_id}/address-candidates")
def address_candidates(
    auto_group_id: str,
    limit: int = 8,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Top-N candidate HQ addresses for this auto_group, scored by
    recency × frequency. Returns enough info for the UI picker to show:
    the canonical key, count of distinct party-sides, last seen date,
    and whether each one is currently selected as primary.
    """
    _ensure_auto_group_exists(db, auto_group_id)

    rows = db.execute(
        """
        SELECT pf.party_address_canonical AS address,
               COUNT(*) AS party_side_count,
               MIN(pf.sale_date) AS first_seen,
               MAX(pf.sale_date) AS last_seen
        FROM auto_group_members agm
        JOIN party_fingerprints pf
          ON pf.source_id = agm.source_id AND pf.side = agm.side
        WHERE agm.auto_group_id = ?
          AND agm.member_type = 'party_side'
          AND pf.party_address_canonical IS NOT NULL
          AND pf.party_address_canonical != ''
        GROUP BY pf.party_address_canonical
        ORDER BY party_side_count DESC, last_seen DESC
        LIMIT ?
        """,
        (auto_group_id, limit),
    ).fetchall()

    ag = db.execute(
        "SELECT primary_address, primary_address_source FROM auto_groups WHERE auto_group_id = ?",
        (auto_group_id,),
    ).fetchone()
    current = ag["primary_address"] if ag else None
    source = ag["primary_address_source"] if ag else None

    return {
        "auto_group_id": auto_group_id,
        "current": {"primary_address": current, "primary_address_source": source},
        "candidates": [
            {
                "address": r["address"],
                "party_side_count": r["party_side_count"],
                "first_seen": r["first_seen"],
                "last_seen": r["last_seen"],
                "is_current": r["address"] == current,
            }
            for r in rows
        ],
    }


@router.post("/{auto_group_id}/set-address")
def set_address(
    auto_group_id: str,
    body: SetAddressRequest,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """User-asserted HQ address override. Wins over algorithmic + AI sources."""
    _ensure_auto_group_exists(db, auto_group_id)
    addr = body.primary_address.strip()
    if not addr:
        raise HTTPException(status_code=400, detail="primary_address must be non-empty")

    db.execute(
        "INSERT INTO auto_group_user_edits "
        "(edit_type, auto_group_id, new_primary_address, edited_by, notes) "
        "VALUES ('set_address', ?, ?, ?, ?)",
        (auto_group_id, addr, _username(user), body.notes),
    )
    db.execute(
        "UPDATE auto_groups SET primary_address = ?, primary_address_source = 'manual' "
        "WHERE auto_group_id = ?",
        (addr, auto_group_id),
    )
    # Confirmed address becomes an identity anchor for verification.
    db.execute(
        "INSERT OR REPLACE INTO auto_group_anchors "
        "(auto_group_id, anchor_type, anchor_value, score) VALUES (?, 'address_unit', ?, 5.0)",
        (auto_group_id, addr),
    )
    db.commit()
    return {"ok": True, "auto_group_id": auto_group_id, "primary_address": addr, "source": "manual"}


# ── Wave 5c: AI enrichment ─────────────────────────────────────────────────


@router.post("/{auto_group_id}/enrich")
def enrich(
    auto_group_id: str,
    body: EnrichRequest,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Trigger Claude API enrichment. Returns a proposal — does NOT modify
    auto_groups. The user reviews and accepts via the accept-enrichment endpoint.
    """
    _ensure_auto_group_exists(db, auto_group_id)

    ag = db.execute(
        "SELECT auto_group_id, display_name, canonical_stem FROM auto_groups WHERE auto_group_id = ?",
        (auto_group_id,),
    ).fetchone()

    from cleo.identity.enrich import propose_hq_enrichment

    try:
        result = propose_hq_enrichment(
            display_name=ag["display_name"],
            canonical_stem=ag["canonical_stem"],
            website_url=body.website_url,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"enrichment failed: {exc}")

    return {
        "auto_group_id": auto_group_id,
        "display_name": ag["display_name"],
        "proposal": result,
    }


@router.post("/{auto_group_id}/accept-enrichment")
def accept_enrichment(
    auto_group_id: str,
    body: AcceptEnrichmentRequest,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Apply some/all of the AI proposal to this auto_group's HQ fields.
    Each accepted field writes a separate auto_group_user_edits row with source='ai_enriched'.
    """
    _ensure_auto_group_exists(db, auto_group_id)

    applied = []

    if body.primary_address:
        db.execute(
            "INSERT INTO auto_group_user_edits "
            "(edit_type, auto_group_id, new_primary_address, edited_by, notes) "
            "VALUES ('set_address', ?, ?, ?, ?)",
            (auto_group_id, body.primary_address, _username(user), f"AI-enriched: {body.notes or ''}".strip()),
        )
        db.execute(
            "UPDATE auto_groups SET primary_address = ?, primary_address_source = 'ai_enriched' "
            "WHERE auto_group_id = ?",
            (body.primary_address, auto_group_id),
        )
        # Anchor: same as manual pick — survives discovery rebuilds and pulls
        # in any future party-side that mails to this address.
        db.execute(
            "INSERT OR REPLACE INTO auto_group_anchors "
            "(auto_group_id, anchor_type, anchor_value, score) VALUES (?, 'address_unit', ?, 5.0)",
            (auto_group_id, body.primary_address),
        )
        applied.append("primary_address")

    if body.website:
        db.execute(
            "INSERT INTO auto_group_user_edits "
            "(edit_type, auto_group_id, new_website, edited_by, notes) "
            "VALUES ('set_website', ?, ?, ?, ?)",
            (auto_group_id, body.website, _username(user), f"AI-enriched: {body.notes or ''}".strip()),
        )
        db.execute(
            "UPDATE auto_groups SET website = ? WHERE auto_group_id = ?",
            (body.website, auto_group_id),
        )
        applied.append("website")

    if body.primary_phone:
        db.execute(
            "INSERT INTO auto_group_user_edits "
            "(edit_type, auto_group_id, new_primary_phone, edited_by, notes) "
            "VALUES ('set_phone', ?, ?, ?, ?)",
            (auto_group_id, body.primary_phone, _username(user), f"AI-enriched: {body.notes or ''}".strip()),
        )
        db.execute(
            "UPDATE auto_groups SET primary_phone = ? WHERE auto_group_id = ?",
            (body.primary_phone, auto_group_id),
        )
        # Phone anchor: normalised to digits-only matches party_fingerprints.phone.
        # Identity signal only — never injected as a contact's direct line on the UI.
        digits = ''.join(c for c in body.primary_phone if c.isdigit())
        if digits:
            db.execute(
                "INSERT OR REPLACE INTO auto_group_anchors "
                "(auto_group_id, anchor_type, anchor_value, score) VALUES (?, 'phone', ?, 5.0)",
                (auto_group_id, digits),
            )
        applied.append("primary_phone")

    db.commit()
    return {"ok": True, "auto_group_id": auto_group_id, "applied": applied}


# ── Audit / inspection ─────────────────────────────────────────────────────


@router.get("/{auto_group_id}/edits")
def list_edits(
    auto_group_id: str,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """List the audit trail of user edits affecting this auto_group."""
    rows = db.execute(
        "SELECT id, edit_type, source_id, side, target_auto_group_id, new_display_name, "
        "       new_canonical_stem, edited_by, edited_at, notes, is_active "
        "FROM auto_group_user_edits "
        "WHERE auto_group_id = ? OR target_auto_group_id = ? "
        "ORDER BY id DESC",
        (auto_group_id, auto_group_id),
    ).fetchall()
    return {"results": [dict(r) for r in rows]}
