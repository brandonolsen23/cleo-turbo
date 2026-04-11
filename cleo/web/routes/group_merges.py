"""
Group Merges API — merge, unmerge, history, suggestions.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from ...web.deps import get_db, get_current_user
from ...analytics.groups import refresh_group_analytics
from ...database.group_merge_ops import resolve_target, execute_merge

router = APIRouter()


# ── Models ───────────────────────────────────────────────────

class MergeRequest(BaseModel):
    source_ids: List[str]
    target_id: str
    primary_display_name: Optional[str] = None


class UnmergeRequest(BaseModel):
    source_group_id: str


# ── Endpoints ────────────────────────────────────────────────

@router.post("/merge")
def merge_groups(req: MergeRequest, db=Depends(get_db), user=Depends(get_current_user)):
    """Merge one or more source groups into a target group."""
    # Validate target exists and is not merged
    target = db.execute("SELECT id, status FROM groups WHERE id = ?", (req.target_id,)).fetchone()
    if not target:
        raise HTTPException(status_code=404, detail=f"Target group {req.target_id} not found")
    if target["status"] == "merged":
        raise HTTPException(status_code=400, detail="Target group is itself merged. Use the ultimate target instead.")

    # Validate all sources exist
    for sid in req.source_ids:
        src = db.execute("SELECT id, status FROM groups WHERE id = ?", (sid,)).fetchone()
        if not src:
            raise HTTPException(status_code=404, detail=f"Source group {sid} not found")
        if src["id"] == req.target_id:
            raise HTTPException(status_code=400, detail="Cannot merge a group into itself")
        # If source is already merged into this target, skip silently
        existing = db.execute(
            "SELECT id FROM group_merges WHERE source_group_id = ? AND target_group_id = ? AND unmerged_at IS NULL",
            (sid, req.target_id)
        ).fetchone()
        if existing:
            continue

        # Follow chain: if source was previously merged elsewhere, resolve
        ultimate_target = resolve_target(db, sid)
        if ultimate_target != sid and ultimate_target != req.target_id:
            raise HTTPException(
                status_code=400,
                detail=f"Source group {sid} is already merged into {ultimate_target}"
            )

    # Execute merges
    merged_count = 0
    for sid in req.source_ids:
        # Skip if already merged into this target
        existing = db.execute(
            "SELECT id FROM group_merges WHERE source_group_id = ? AND target_group_id = ? AND unmerged_at IS NULL",
            (sid, req.target_id)
        ).fetchone()
        if existing:
            continue

        # Record the merge
        db.execute(
            "INSERT INTO group_merges (source_group_id, target_group_id, merged_by) VALUES (?, ?, ?)",
            (sid, req.target_id, user["username"])
        )
        execute_merge(db, sid, req.target_id)
        merged_count += 1

    # Update display name if requested
    if req.primary_display_name:
        db.execute(
            "UPDATE groups SET display_name = ? WHERE id = ?",
            (req.primary_display_name, req.target_id)
        )

    db.commit()

    # Refresh analytics for the target group
    refresh_group_analytics(db, group_ids=[req.target_id])

    # Return updated target info
    result = dict(db.execute("SELECT * FROM groups WHERE id = ?", (req.target_id,)).fetchone())
    result["merged_count"] = merged_count
    return result


@router.post("/unmerge")
def unmerge_group(req: UnmergeRequest, db=Depends(get_db), user=Depends(get_current_user)):
    """Reverse a merge — mark it as unmerged. Requires a compiler rebuild to fully restore."""
    merge = db.execute(
        "SELECT id, source_group_id, target_group_id FROM group_merges "
        "WHERE source_group_id = ? AND unmerged_at IS NULL",
        (req.source_group_id,)
    ).fetchone()
    if not merge:
        raise HTTPException(status_code=404, detail="No active merge found for this group")

    # Mark as unmerged
    db.execute(
        "UPDATE group_merges SET unmerged_at = datetime('now'), unmerged_by = ? WHERE id = ?",
        (user["username"], merge["id"])
    )

    # Restore source group status
    db.execute(
        "UPDATE groups SET status = 'pool' WHERE id = ?",
        (req.source_group_id,)
    )

    db.commit()

    return {
        "unmerged": True,
        "source_group_id": merge["source_group_id"],
        "target_group_id": merge["target_group_id"],
        "note": "Run the compiler to fully restore property/contact assignments from clean-data."
    }


@router.get("/history/{group_id}")
def merge_history(group_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    """Get merge history for a group — both as source and target."""
    # Groups merged INTO this one
    absorbed = db.execute(
        "SELECT gm.id, gm.source_group_id, g.display_name as source_name, "
        "gm.merged_by, gm.merged_at, gm.unmerged_at, gm.unmerged_by "
        "FROM group_merges gm "
        "JOIN groups g ON gm.source_group_id = g.id "
        "WHERE gm.target_group_id = ? "
        "ORDER BY gm.merged_at DESC",
        (group_id,)
    ).fetchall()

    # This group was merged INTO another
    merged_into = db.execute(
        "SELECT gm.id, gm.target_group_id, g.display_name as target_name, "
        "gm.merged_by, gm.merged_at, gm.unmerged_at, gm.unmerged_by "
        "FROM group_merges gm "
        "JOIN groups g ON gm.target_group_id = g.id "
        "WHERE gm.source_group_id = ? "
        "ORDER BY gm.merged_at DESC",
        (group_id,)
    ).fetchall()

    return {
        "absorbed": [dict(r) for r in absorbed],
        "merged_into": [dict(r) for r in merged_into],
    }


@router.get("/candidates/{group_id}")
def merge_candidates(
    group_id: str,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Find likely duplicate groups for a specific group (prefix match + known names)."""
    group = db.execute(
        "SELECT id, normalized_name, display_name FROM groups WHERE id = ?",
        (group_id,)
    ).fetchone()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    norm = group["normalized_name"]

    # Find groups whose normalized name starts with the same first word(s)
    # Use the shorter of: first 2 words, or the full name
    words = norm.split()
    if len(words) >= 2:
        prefix = words[0] + " " + words[1]
    else:
        prefix = words[0] if words else norm

    rows = db.execute(
        "SELECT g.id, g.display_name, g.normalized_name, g.status, "
        "g.property_count, g.transaction_count, g.contact_count, "
        "ga.total_assessed_value, ga.geographic_radius_km "
        "FROM groups g "
        "LEFT JOIN group_analytics ga ON g.id = ga.group_id "
        "WHERE g.normalized_name LIKE ? AND g.id != ? AND g.status != 'merged' "
        "ORDER BY g.transaction_count DESC "
        "LIMIT 50",
        (prefix + "%", group_id)
    ).fetchall()

    return {
        "group": dict(group),
        "candidates": [dict(r) for r in rows],
    }


@router.get("/suggestions")
def merge_suggestions(
    limit: int = 50,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Find groups that are likely duplicates across the whole dataset.

    Strategy: find groups with high transaction counts that share a normalized name prefix
    with other groups. Focus on groups with 10+ transactions to surface the most impactful merges.
    """
    # Get groups with significant activity that share 2-word prefixes
    rows = db.execute(
        """
        SELECT
            g1.id as id1, g1.display_name as name1, g1.property_count as props1,
            g1.transaction_count as txns1,
            g2.id as id2, g2.display_name as name2, g2.property_count as props2,
            g2.transaction_count as txns2
        FROM groups g1
        JOIN groups g2 ON g1.id < g2.id
            AND g2.status != 'merged'
            AND SUBSTR(g1.normalized_name, 1, INSTR(g1.normalized_name || ' ', ' ')) =
                SUBSTR(g2.normalized_name, 1, INSTR(g2.normalized_name || ' ', ' '))
            AND LENGTH(SUBSTR(g1.normalized_name, 1, INSTR(g1.normalized_name || ' ', ' '))) >= 4
        WHERE g1.status != 'merged'
            AND g1.transaction_count >= 10
            AND g2.transaction_count >= 5
        ORDER BY g1.transaction_count + g2.transaction_count DESC
        LIMIT ?
        """,
        (limit,)
    ).fetchall()

    return {"suggestions": [dict(r) for r in rows]}


@router.post("/preview")
def merge_preview(req: MergeRequest, db=Depends(get_db), user=Depends(get_current_user)):
    """Preview what a merge would affect without executing it."""
    affected_contacts = {}
    affected_properties = 0
    affected_transactions = set()

    for sid in req.source_ids:
        # Contacts with current_group_id = source
        for r in db.execute(
            "SELECT id, display_name FROM contacts WHERE current_group_id = ?", (sid,)
        ):
            affected_contacts[r[0]] = r[1]
        # Manually linked contacts
        for r in db.execute(
            "SELECT c.id, c.display_name FROM group_contacts gc "
            "JOIN contacts c ON gc.contact_id = c.id WHERE gc.group_id = ?",
            (sid,)
        ):
            affected_contacts[r[0]] = r[1]
        # Properties
        affected_properties += db.execute(
            "SELECT COUNT(*) FROM properties WHERE current_owner_group_id = ?", (sid,)
        ).fetchone()[0]
        # Transactions
        for r in db.execute(
            "SELECT DISTINCT source_id FROM transaction_parties WHERE group_id = ?", (sid,)
        ):
            affected_transactions.add(r[0])

    return {
        "source_count": len(req.source_ids),
        "target_id": req.target_id,
        "affected_contacts": [
            {"id": cid, "name": name} for cid, name in affected_contacts.items()
        ],
        "affected_properties": affected_properties,
        "affected_transactions": len(affected_transactions),
    }
