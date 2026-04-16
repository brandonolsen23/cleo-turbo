"""
Group Merges API — merge, unmerge, history, suggestions, comparison.
"""

import json
from fastapi import APIRouter, Depends, HTTPException, Query
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


# ── Evidence-Based Comparison ──────────────────────────────────

@router.get("/compare")
def compare_groups(
    group_ids: str = Query(..., description="Comma-separated group IDs (2-10)"),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Side-by-side evidence comparison for merge verification.

    Returns full party details for each group: contacts, mailing addresses,
    recent transactions, known names, plus shared signals between them.
    """
    ids = [gid.strip() for gid in group_ids.split(",") if gid.strip()]
    if len(ids) < 2 or len(ids) > 10:
        raise HTTPException(400, "Provide 2-10 group IDs")

    # Validate groups exist
    groups = {}
    for gid in ids:
        row = db.execute(
            "SELECT id, display_name, normalized_name, status, property_count, "
            "transaction_count, contact_count, hq_address "
            "FROM groups WHERE id = ?",
            (gid,)
        ).fetchone()
        if not row:
            raise HTTPException(404, f"Group {gid} not found")
        groups[gid] = dict(row)

    placeholders = ",".join("?" for _ in ids)

    # ── Per-group data ──

    # Contacts per group (with transaction date range + linkedin)
    for gid in ids:
        contacts = db.execute(
            "SELECT c.id, c.display_name, c.phone, c.job_title, c.contact_type, "
            "c.transaction_count, c.first_seen_date, c.last_seen_date, "
            "cfo.linkedin_url, cfo.linkedin_headline "
            "FROM contacts c "
            "LEFT JOIN contact_field_overrides cfo ON cfo.contact_id = c.id "
            "WHERE c.current_group_id = ? ORDER BY c.transaction_count DESC",
            (gid,)
        ).fetchall()
        groups[gid]["contacts"] = [dict(c) for c in contacts]

    # Known names per group
    for gid in ids:
        names = db.execute(
            "SELECT name, normalized FROM group_names WHERE group_id = ?",
            (gid,)
        ).fetchall()
        groups[gid]["known_names"] = [dict(n) for n in names]

    # Mailing addresses per group (unique addresses with frequency)
    for gid in ids:
        addrs = db.execute(
            "SELECT tma.display, tma.city, tma.province, tma.postal, "
            "COUNT(DISTINCT tma.source_id) as usage_count "
            "FROM transaction_mailing_addresses tma "
            "JOIN transaction_parties tp ON tp.source_id = tma.source_id AND tp.side = tma.side "
            "WHERE tp.group_id = ? AND tma.display IS NOT NULL AND tma.display != '' "
            "GROUP BY tma.display "
            "ORDER BY usage_count DESC",
            (gid,)
        ).fetchall()
        groups[gid]["mailing_addresses"] = [dict(a) for a in addrs]

    # Recent transactions per group (last 20)
    for gid in ids:
        txns = db.execute(
            "SELECT t.source_id, t.sale_date, t.sale_price, t.display_address, t.city, "
            "tp.side, tp.party_name, tp.phone as party_phone "
            "FROM transaction_parties tp "
            "JOIN transactions t ON tp.source_id = t.source_id "
            "WHERE tp.group_id = ? ORDER BY t.sale_date DESC LIMIT 20",
            (gid,)
        ).fetchall()
        groups[gid]["recent_transactions"] = [dict(t) for t in txns]

    # ── Shared signals ──

    # Shared mailing addresses: addresses appearing on 2+ of the requested groups
    shared_addresses = db.execute(
        f"SELECT tma.display, tma.city, tma.postal, "
        f"GROUP_CONCAT(DISTINCT tp.group_id) as group_ids, "
        f"COUNT(DISTINCT tp.group_id) as group_count, "
        f"COUNT(DISTINCT tma.source_id) as total_txns "
        f"FROM transaction_mailing_addresses tma "
        f"JOIN transaction_parties tp ON tp.source_id = tma.source_id AND tp.side = tma.side "
        f"WHERE tp.group_id IN ({placeholders}) "
        f"AND tma.display IS NOT NULL AND tma.display != '' "
        f"AND tma.display NOT LIKE 'RR %' AND tma.display NOT LIKE 'PO Box%' "
        f"AND tma.display NOT LIKE 'P.O.%' AND tma.display NOT LIKE 'General Delivery%' "
        f"GROUP BY tma.display "
        f"HAVING COUNT(DISTINCT tp.group_id) > 1 "
        f"ORDER BY group_count DESC, total_txns DESC",
        ids
    ).fetchall()

    # Shared contacts: contacts appearing in transaction_parties for 2+ of these groups
    shared_contacts = db.execute(
        f"SELECT c.id, c.display_name, c.phone, c.job_title, "
        f"GROUP_CONCAT(DISTINCT tp.group_id) as group_ids, "
        f"COUNT(DISTINCT tp.group_id) as group_count, "
        f"MIN(t.sale_date) as earliest_date, "
        f"MAX(t.sale_date) as latest_date "
        f"FROM transaction_parties tp "
        f"JOIN contacts c ON c.id = tp.contact_id "
        f"LEFT JOIN transactions t ON t.source_id = tp.source_id "
        f"WHERE tp.group_id IN ({placeholders}) AND tp.contact_id IS NOT NULL "
        f"GROUP BY c.id "
        f"HAVING COUNT(DISTINCT tp.group_id) > 1 "
        f"ORDER BY group_count DESC, c.transaction_count DESC",
        ids
    ).fetchall()

    # Shared phones: same phone on contacts in different groups
    shared_phones = db.execute(
        f"SELECT c.phone, "
        f"GROUP_CONCAT(DISTINCT c.id || ':' || c.display_name || ':' || c.current_group_id) as contact_details, "
        f"COUNT(DISTINCT c.current_group_id) as group_count "
        f"FROM contacts c "
        f"WHERE c.current_group_id IN ({placeholders}) "
        f"AND c.phone IS NOT NULL AND c.phone != '' "
        f"GROUP BY c.phone "
        f"HAVING COUNT(DISTINCT c.current_group_id) > 1 "
        f"ORDER BY group_count DESC",
        ids
    ).fetchall()

    # Parse shared phones into structured data
    shared_phones_parsed = []
    for row in shared_phones:
        contacts_in_phone = []
        for entry in row["contact_details"].split(","):
            parts = entry.split(":", 2)
            if len(parts) == 3:
                contacts_in_phone.append({
                    "contact_id": parts[0],
                    "display_name": parts[1],
                    "group_id": parts[2],
                })
        shared_phones_parsed.append({
            "phone": row["phone"],
            "group_count": row["group_count"],
            "contacts": contacts_in_phone,
        })

    # ── Compute match tier ──
    has_shared_contact_and_address = False
    shared_contact_ids = {r["id"] for r in shared_contacts}
    shared_addr_set = {r["display"] for r in shared_addresses}

    # Check if any shared contact also used a shared address
    if shared_contact_ids and shared_addr_set:
        for cid in shared_contact_ids:
            check = db.execute(
                f"SELECT 1 FROM transaction_parties tp "
                f"JOIN transaction_mailing_addresses tma "
                f"ON tma.source_id = tp.source_id AND tma.side = tp.side "
                f"WHERE tp.contact_id = ? AND tp.group_id IN ({placeholders}) "
                f"AND tma.display IN ({','.join('?' for _ in shared_addr_set)}) "
                f"LIMIT 1",
                [cid] + ids + list(shared_addr_set)
            ).fetchone()
            if check:
                has_shared_contact_and_address = True
                break

    if has_shared_contact_and_address:
        match_tier = 1
    elif len(shared_addresses) > 0:
        match_tier = 2
    elif len(shared_phones_parsed) > 0:
        match_tier = 3
    elif len(shared_contacts) > 0:
        match_tier = 4
    else:
        match_tier = 0

    # Build match reasons
    match_reasons = []
    if has_shared_contact_and_address:
        sc_names = [r["display_name"] for r in shared_contacts[:3]]
        sa_names = [r["display"] for r in shared_addresses[:2]]
        match_reasons.append(
            f"{', '.join(sc_names)} appear{'s' if len(sc_names)==1 else ''} on both groups "
            f"at {sa_names[0]}"
        )
    elif shared_addresses:
        addr_display = shared_addresses[0]["display"]
        addr_city = shared_addresses[0]["city"]
        reason = f"Both groups transact from {addr_display}"
        if addr_city:
            reason += f", {addr_city}"
        match_reasons.append(reason)
    if shared_phones_parsed and not has_shared_contact_and_address:
        match_reasons.append(
            f"Shared phone: {shared_phones_parsed[0]['phone']}"
        )
    if shared_contacts and not has_shared_contact_and_address:
        match_reasons.append(
            f"{shared_contacts[0]['display_name']} appears on both groups"
        )

    return {
        "groups": groups,
        "shared_addresses": [dict(r) for r in shared_addresses],
        "shared_contacts": [
            {**dict(r), "group_ids": r["group_ids"].split(",")}
            for r in shared_contacts
        ],
        "shared_phones": shared_phones_parsed,
        "match_tier": match_tier,
        "match_reasons": match_reasons,
    }


@router.get("/address-suggestions")
def address_suggestions(
    group_id: Optional[str] = Query(None, description="Suggestions for a specific group"),
    min_tier: int = Query(1, ge=1, le=4),
    limit: int = Query(30, ge=1, le=100),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Find groups connected by shared mailing addresses, contacts, and phones.

    If group_id is provided, returns suggestions for that specific group.
    Otherwise returns global suggestions ranked by match quality.
    """
    if group_id:
        # Per-group suggestions: find other groups that share addresses/contacts/phones
        group = db.execute(
            "SELECT id, display_name FROM groups WHERE id = ?", (group_id,)
        ).fetchone()
        if not group:
            raise HTTPException(404, "Group not found")

        suggestions = []

        # 1. Groups sharing a corporate mailing address
        # Step 1a: get this group's mailing addresses (fast, small result set)
        my_addrs = db.execute(
            """
            SELECT DISTINCT tma.display
            FROM transaction_mailing_addresses tma
            JOIN transaction_parties tp ON tp.source_id = tma.source_id AND tp.side = tma.side
            WHERE tp.group_id = ?
              AND tma.display IS NOT NULL AND tma.display != ''
              AND tma.display NOT LIKE 'RR %' AND tma.display NOT LIKE 'PO Box%'
              AND tma.display NOT LIKE 'P.O.%' AND tma.display NOT LIKE 'General Delivery%'
            """,
            (group_id,)
        ).fetchall()
        my_addr_list = [r["display"] for r in my_addrs]

        # Step 1b: find other groups using those same addresses
        addr_matches = []
        if my_addr_list:
            addr_placeholders = ",".join("?" for _ in my_addr_list)
            addr_matches = db.execute(
                f"""
                SELECT tp.group_id as other_gid, g.display_name, g.property_count,
                       g.transaction_count, g.contact_count,
                       tma.display as shared_addr, tma.city as addr_city,
                       COUNT(DISTINCT tma.source_id) as shared_count, 'address' as match_type
                FROM transaction_mailing_addresses tma
                JOIN transaction_parties tp ON tp.source_id = tma.source_id AND tp.side = tma.side
                JOIN groups g ON g.id = tp.group_id
                WHERE tma.display IN ({addr_placeholders})
                  AND tp.group_id != ?
                  AND g.status != 'merged'
                GROUP BY tp.group_id, tma.display
                ORDER BY shared_count DESC
                LIMIT ?
                """,
                my_addr_list + [group_id, limit * 2]
            ).fetchall()

        # 2. Groups sharing contacts
        contact_matches = db.execute(
            """
            SELECT tp2.group_id as other_gid, g.display_name,
                   g.property_count, g.transaction_count, g.contact_count,
                   c.id as contact_id, c.display_name as shared_contact, c.phone as contact_phone,
                   COUNT(DISTINCT tp2.source_id) as shared_count, 'contact' as match_type,
                   MIN(t.sale_date) as earliest_date,
                   MAX(t.sale_date) as latest_date,
                   cfo.linkedin_url as contact_linkedin_url
            FROM transaction_parties tp
            JOIN transaction_parties tp2 ON tp2.contact_id = tp.contact_id
                AND tp2.group_id != tp.group_id
            JOIN contacts c ON c.id = tp.contact_id
            JOIN groups g ON g.id = tp2.group_id
            LEFT JOIN transactions t ON t.source_id = tp.source_id
            LEFT JOIN contact_field_overrides cfo ON cfo.contact_id = c.id
            WHERE tp.group_id = ? AND tp.contact_id IS NOT NULL
              AND g.status != 'merged'
            GROUP BY tp2.group_id, c.id
            ORDER BY shared_count DESC
            LIMIT ?
            """,
            (group_id, limit * 2)
        ).fetchall()

        # 3. Groups sharing phone numbers
        phone_matches = db.execute(
            """
            SELECT c2.current_group_id as other_gid, g.display_name,
                   g.property_count, g.transaction_count, g.contact_count,
                   c.phone as shared_phone, c2.display_name as other_contact,
                   'phone' as match_type
            FROM contacts c
            JOIN contacts c2 ON c2.phone = c.phone AND c2.current_group_id != c.current_group_id
            JOIN groups g ON g.id = c2.current_group_id
            WHERE c.current_group_id = ?
              AND c.phone IS NOT NULL AND c.phone != ''
              AND g.status != 'merged'
            LIMIT ?
            """,
            (group_id, limit)
        ).fetchall()

        # Deduplicate and rank by group, computing best tier per group
        group_map = {}  # other_gid -> suggestion dict
        for r in addr_matches:
            gid = r["other_gid"]
            if gid not in group_map:
                group_map[gid] = {
                    "group_id": gid,
                    "display_name": r["display_name"],
                    "property_count": r["property_count"],
                    "transaction_count": r["transaction_count"],
                    "contact_count": r["contact_count"],
                    "shared_addresses": [],
                    "shared_contacts": [],
                    "shared_phones": [],
                    "match_tier": 2,
                }
            group_map[gid]["shared_addresses"].append({
                "address": r["shared_addr"],
                "city": r["addr_city"],
                "usage_count": r["shared_count"],
            })

        for r in contact_matches:
            gid = r["other_gid"]
            if gid not in group_map:
                group_map[gid] = {
                    "group_id": gid,
                    "display_name": r["display_name"],
                    "property_count": r["property_count"],
                    "transaction_count": r["transaction_count"],
                    "contact_count": r["contact_count"],
                    "shared_addresses": [],
                    "shared_contacts": [],
                    "shared_phones": [],
                    "match_tier": 4,
                }
            group_map[gid]["shared_contacts"].append({
                "contact_id": r["contact_id"],
                "name": r["shared_contact"],
                "phone": r["contact_phone"],
                "earliest_date": r["earliest_date"],
                "latest_date": r["latest_date"],
                "linkedin_url": r["contact_linkedin_url"],
            })
            # Upgrade tier: contact + address = tier 1
            if group_map[gid]["shared_addresses"]:
                group_map[gid]["match_tier"] = 1

        for r in phone_matches:
            gid = r["other_gid"]
            if gid not in group_map:
                group_map[gid] = {
                    "group_id": gid,
                    "display_name": r["display_name"],
                    "property_count": r["property_count"],
                    "transaction_count": r["transaction_count"],
                    "contact_count": r["contact_count"],
                    "shared_addresses": [],
                    "shared_contacts": [],
                    "shared_phones": [],
                    "match_tier": 3,
                }
            group_map[gid]["shared_phones"].append({
                "phone": r["shared_phone"],
                "other_contact": r["other_contact"],
            })
            # Phone + address = tier 2 still, but phone + contact = upgrade
            if group_map[gid]["shared_contacts"] and group_map[gid]["match_tier"] > 3:
                group_map[gid]["match_tier"] = 3

        # Filter by min_tier and sort
        results = [
            v for v in group_map.values()
            if v["match_tier"] <= min_tier or min_tier >= v["match_tier"]
        ]
        results = [v for v in group_map.values() if v["match_tier"] <= min_tier]

        # Sort: tier 1 first, then by total evidence count
        results.sort(key=lambda x: (
            x["match_tier"],
            -(len(x["shared_addresses"]) + len(x["shared_contacts"]) + len(x["shared_phones"])),
            -x["transaction_count"],
        ))

        return {
            "group_id": group_id,
            "suggestions": results[:limit],
            "total": len(results),
        }

    else:
        # Global suggestions: find the most impactful address clusters
        rows = db.execute(
            """
            SELECT tma.display as address, tma.city, tma.postal,
                   COUNT(DISTINCT tp.group_id) as group_count,
                   COUNT(DISTINCT tma.source_id) as txn_count,
                   GROUP_CONCAT(DISTINCT tp.group_id) as group_ids
            FROM transaction_mailing_addresses tma
            JOIN transaction_parties tp ON tp.source_id = tma.source_id AND tp.side = tma.side
            JOIN groups g ON g.id = tp.group_id
            WHERE tma.display IS NOT NULL AND tma.display != ''
              AND g.status != 'merged'
              AND tma.display NOT LIKE 'RR %' AND tma.display NOT LIKE 'PO Box%'
              AND tma.display NOT LIKE 'P.O.%' AND tma.display NOT LIKE 'General Delivery%'
            GROUP BY tma.display
            HAVING COUNT(DISTINCT tp.group_id) BETWEEN 2 AND 50
            ORDER BY group_count DESC, txn_count DESC
            LIMIT ?
            """,
            (limit,)
        ).fetchall()

        clusters = []
        for row in rows:
            gids = row["group_ids"].split(",")[:10]  # Cap preview at 10 groups
            gid_placeholders = ",".join("?" for _ in gids)
            groups_in_cluster = db.execute(
                f"SELECT id, display_name, property_count, transaction_count "
                f"FROM groups WHERE id IN ({gid_placeholders}) ORDER BY transaction_count DESC",
                gids
            ).fetchall()
            clusters.append({
                "address": row["address"],
                "city": row["city"],
                "postal": row["postal"],
                "group_count": row["group_count"],
                "txn_count": row["txn_count"],
                "groups": [dict(g) for g in groups_in_cluster],
            })

        return {"clusters": clusters, "total": len(clusters)}
