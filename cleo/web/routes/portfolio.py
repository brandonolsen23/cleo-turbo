"""
Portfolio Capture API — POST /api/portfolio/capture (spec Section 6).

One validated door for Cowork, the Cleo UI, and scripts to commit owner
intelligence. The handler implements the Section 6.1 write order inside a
single transaction; dry_run=true (the default) rolls everything back and
returns the diff. Ownership reconcile is delegated to
compiler.owner_overrides.apply_owner_overrides; merges are applied only on
an explicit commit with apply_merges=true (spec D4).
"""

from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ...web.deps import get_db, get_current_user
from ...compiler.owner_overrides import apply_owner_overrides
from ...compiler.portfolio_capture import (
    CaptureError,
    ensure_capture_columns,
    upsert_group,
    write_profile,
    write_aliases,
    write_match_keys,
    write_contacts,
    write_links,
    run_sweep,
)
from ...database.group_merge_ops import resolve_target, execute_merge

router = APIRouter()


# ── Payload models (spec Section 5) ───────────────────────────────────

class GroupIn(BaseModel):
    id: Optional[str] = None
    display_name: str
    business_lines: List[str] = []
    hq_address: Optional[str] = None
    domain: Optional[str] = None
    website: Optional[str] = None
    partners: List[str] = []
    summary: Optional[str] = None
    source_url: Optional[str] = None


class AliasIn(BaseModel):
    alias: str
    source_url: Optional[str] = None
    confidence: Optional[float] = None


class MatchKeyIn(BaseModel):
    type: Literal["address", "phone", "domain", "spv_name", "person"]
    value_raw: str
    source_url: Optional[str] = None
    confidence: Optional[float] = None


class ContactIn(BaseModel):
    name: str
    role: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    is_current: bool = True
    source_url: Optional[str] = None


class PropertyIn(BaseModel):
    arn: str
    display_address: Optional[str] = None
    city: Optional[str] = None
    relationship: Literal["owns", "manages", "lists"] = "owns"
    source: str = "web_capture"
    source_url: Optional[str] = None
    confidence: Optional[float] = None
    registry_confirmed: bool = False


class CapturePayload(BaseModel):
    group: GroupIn
    aliases: List[AliasIn] = []
    match_keys: List[MatchKeyIn] = []
    contacts: List[ContactIn] = []
    properties: List[PropertyIn] = []
    merge_candidates: List[str] = []
    captured_by: str = "cowork"


class CaptureDiff(BaseModel):
    group_id: str
    created: bool
    overrides: dict
    sweep: dict
    merges_proposed: List[str]
    merges_applied: int = 0
    match_keys_added: int
    aliases_added: int
    contacts_linked: int
    warnings: List[str]


class _TxnConn:
    """Connection proxy that swallows commit() so helpers that commit
    internally (apply_owner_overrides) stay inside the route's single
    transaction. The route alone decides commit vs rollback."""

    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def commit(self):
        pass


# ── Endpoint (spec 6.1 write order, 6.3 status codes) ─────────────────

@router.post("/capture", response_model=CaptureDiff)
def capture(
    payload: CapturePayload,
    dry_run: bool = Query(True),
    apply_merges: bool = Query(False),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    # Runtime column migration commits on the REAL connection first, so a
    # later dry_run rollback never has to undo DDL.
    ensure_capture_columns(db)
    db.commit()

    conn = _TxnConn(db)
    warnings: List[str] = []
    actor = payload.captured_by or user.get("username", "unknown")

    try:
        # 1. Resolve or create the parent group
        group_id, created = upsert_group(
            conn, payload.group.model_dump(), payload.merge_candidates, actor)

        # 2. Profile
        write_profile(conn, group_id, payload.group.model_dump(), actor)

        # 3. Aliases
        aliases_added = write_aliases(
            conn, group_id, [a.model_dump() for a in payload.aliases], actor)

        # 4. Match keys (may raise 422 on the specificity guard)
        match_keys_added, mk_warnings = write_match_keys(
            conn, group_id, [m.model_dump() for m in payload.match_keys], actor)
        warnings.extend(mk_warnings)

        # 5. Contacts
        contacts_linked = write_contacts(
            conn, group_id, [c.model_dump() for c in payload.contacts], actor)

        # 6. Property links (+ manual_properties stubs), D4/D5
        link_res = write_links(
            conn, group_id, [p.model_dump() for p in payload.properties], actor)
        warnings.extend(link_res["warnings"])

        # 7. Reconcile via the existing owner-overrides pass
        stats = apply_owner_overrides(
            conn, scope_arns=link_res["scope_arns"], actor=actor, verbose=False)

        # 8. Match-key sweep (M4), then re-run overrides on expanded scope
        sweep = run_sweep(conn, group_id, payload.merge_candidates, actor)
        if sweep["matched_arns"]:
            expanded = sorted(set(link_res["scope_arns"]) | set(sweep["matched_arns"]))
            stats = apply_owner_overrides(
                conn, scope_arns=expanded, actor=actor, verbose=False)

        # Merges: proposed always; applied ONLY on explicit commit (D4)
        merges_proposed: List[str] = []
        for cand in payload.merge_candidates:
            row = conn.execute(
                "SELECT id, status FROM groups WHERE id = ?", (cand,)
            ).fetchone()
            if not row:
                warnings.append(f"merge candidate {cand} not found — skipped")
                continue
            if cand == group_id:
                warnings.append(f"merge candidate {cand} is the parent — skipped")
                continue
            merges_proposed.append(cand)

        merges_applied = 0
        if not dry_run and apply_merges:
            for cand in merges_proposed:
                if resolve_target(conn, cand) == group_id:
                    continue  # already merged into the parent — idempotent
                conn.execute(
                    "INSERT INTO group_merges (source_group_id, "
                    "target_group_id, merged_by) VALUES (?, ?, ?)",
                    (cand, group_id, actor),
                )
                execute_merge(conn, cand, group_id)
                merges_applied += 1
            if merges_applied:
                # Merged-in groups may have redirected links; re-run the
                # scoped overrides so ownership lands on the survivor.
                expanded = sorted(
                    set(link_res["scope_arns"]) | set(sweep["matched_arns"]))
                if expanded:
                    stats = apply_owner_overrides(
                        conn, scope_arns=expanded, actor=actor, verbose=False)

        diff = CaptureDiff(
            group_id=group_id,
            created=created,
            overrides={k: stats[k] for k in
                       ("filled", "confirmed", "conflicts",
                        "pending_no_property")},
            sweep=sweep,
            merges_proposed=merges_proposed,
            merges_applied=merges_applied,
            match_keys_added=match_keys_added,
            aliases_added=aliases_added,
            contacts_linked=contacts_linked,
            warnings=warnings,
        )

        if dry_run:
            db.rollback()
        else:
            db.execute(
                "UPDATE manual_owner_links SET approved_by = ?, "
                "approved_at = datetime('now') "
                "WHERE group_id = ? AND approved_at IS NULL",
                (user.get("username", actor), group_id),
            )
            db.commit()
        return diff

    except CaptureError as e:
        db.rollback()
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
