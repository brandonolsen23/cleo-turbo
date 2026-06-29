"""
Owner overrides — apply manual_owner_links onto the derived properties table.

`manual_owner_links` (CRM, persistent) is the SOURCE OF TRUTH for captured
ownership. This module re-applies every active link so the materialized owner
on `properties` is always reconstructable after a compiler rebuild, and can
also be run incrementally (scoped to specific ARNs) right after a capture is
approved, so the user sees the override without waiting for a full compile.

Two callers, one function:
  - Compiler final pass: apply_owner_overrides(conn)            # all links
  - Approve endpoint (incremental): apply_owner_overrides(conn, scope_arns=[...])

Policy (decided in the build plan + session sign-off):
  - relationship='owns' fills a DARK property (no Realtrack transaction:
    transaction_count == 0). A GW-only parcel counts as dark even if GW carries
    a registry owner name (often an SPV) — that's exactly the case the capture
    is meant to attach to a parent group. The GW owner *name* is preserved;
    only current_owner_group_id is set (web never clobbers the registry name).
  - If a property has a Realtrack-derived owner (transaction_count > 0) that
    differs from the captured group, the link does NOT overwrite it: the link
    is flagged status='conflict' and a data_issues row is logged for review.
  - If the existing owner already matches the captured group, it's confirmed.
  - relationship in ('manages','lists') is recorded but never changes ownership.
"""

CONFLICT_RULE = "manual_owner_conflict"


def _merge_redirect(conn):
    """Build src->ultimate-target map from active group_merges (chain-following),
    so an override pointed at a since-merged group resolves to the survivor."""
    rows = conn.execute(
        "SELECT source_group_id, target_group_id FROM group_merges "
        "WHERE unmerged_at IS NULL"
    ).fetchall()
    redirect = {r[0]: r[1] for r in rows}
    for src in list(redirect.keys()):
        target = redirect[src]
        visited = {src}
        while target in redirect and target not in visited:
            visited.add(target)
            target = redirect[target]
        redirect[src] = target
    return redirect


def apply_owner_overrides(conn, scope_arns=None, actor="compiler", verbose=True):
    """Apply active manual_owner_links onto the properties table.

    scope_arns: optional iterable of ARNs to limit to (incremental mode, used by
        the Approve endpoint). None = all active links (compiler final pass).

    Returns a stats dict:
        filled, confirmed, conflicts, pending_no_property, skipped_non_owns
    """
    stats = {"filled": 0, "confirmed": 0, "conflicts": 0,
             "pending_no_property": 0, "skipped_non_owns": 0}

    redirect = _merge_redirect(conn)

    sql = ("SELECT id, arn, group_id, relationship FROM manual_owner_links "
           "WHERE status != 'superseded'")
    params = []
    scoped = scope_arns is not None
    if scoped:
        arns = [a for a in scope_arns]
        if not arns:
            return stats
        sql += " AND arn IN (%s)" % ",".join("?" * len(arns))
        params = arns
    links = conn.execute(sql, params).fetchall()

    # Idempotency: clear prior open conflict issues in scope before re-deriving.
    if not scoped:
        conn.execute(
            "UPDATE data_issues SET status='resolved', resolved_at=datetime('now'), "
            "resolved_by=? WHERE rule=? AND status='open'",
            (actor, CONFLICT_RULE),
        )
    else:
        pids = conn.execute(
            "SELECT id FROM properties WHERE arn IN (%s)" % ",".join("?" * len(params)),
            params,
        ).fetchall()
        for (pid,) in pids:
            conn.execute(
                "UPDATE data_issues SET status='resolved', resolved_at=datetime('now'), "
                "resolved_by=? WHERE rule=? AND status='open' AND source_id=?",
                (actor, CONFLICT_RULE, pid),
            )

    for link_id, arn, group_id, relationship in links:
        gid = redirect.get(group_id, group_id)

        # manages / lists are recorded but never change ownership in v1.
        if relationship != "owns":
            conn.execute(
                "UPDATE manual_owner_links SET status='active' WHERE id=?", (link_id,)
            )
            stats["skipped_non_owns"] += 1
            continue

        prop = conn.execute(
            "SELECT id, current_owner_group_id, current_owner_name, transaction_count "
            "FROM properties WHERE arn=?",
            (arn,),
        ).fetchone()

        if not prop:
            # Off-book: no real property row yet. Link stays pending; it applies
            # once GW/RT builds a row for this ARN (reconciled on ARN).
            conn.execute(
                "UPDATE manual_owner_links SET property_id=NULL WHERE id=?", (link_id,)
            )
            stats["pending_no_property"] += 1
            continue

        pid, cur_gid, cur_name, tx_count = prop
        tx_count = tx_count or 0

        # Keep the manual_properties stub (if any) reconciled on ARN.
        conn.execute(
            "UPDATE manual_properties SET resolved_pid=? WHERE arn=? AND "
            "(resolved_pid IS NULL OR resolved_pid != ?)",
            (pid, arn, pid),
        )

        grow = conn.execute(
            "SELECT display_name FROM groups WHERE id=?", (gid,)
        ).fetchone()
        group_name = grow[0] if grow else (cur_name or "")

        has_rt_owner = tx_count > 0

        if not has_rt_owner:
            # Dark (GW-only or none): fill the owner group. Preserve an existing
            # registry owner name; only set it when blank.
            new_name = cur_name if (cur_name or "").strip() else group_name
            conn.execute(
                "UPDATE properties SET current_owner_group_id=?, current_owner_name=?, "
                "updated_at=datetime('now') WHERE id=?",
                (gid, new_name, pid),
            )
            conn.execute(
                "UPDATE manual_owner_links SET status='active', property_id=?, "
                "conflict_note=NULL WHERE id=?",
                (pid, link_id),
            )
            stats["filled"] += 1
        elif cur_gid and cur_gid == gid:
            # Existing owner already matches the captured group — confirmed.
            conn.execute(
                "UPDATE manual_owner_links SET status='active', property_id=?, "
                "registry_confirmed=1, conflict_note=NULL WHERE id=?",
                (pid, link_id),
            )
            stats["confirmed"] += 1
        else:
            # RT-derived owner differs (or is unmapped). Do NOT overwrite — flag.
            note = (
                f"Realtrack-derived owner {cur_gid or '(unmapped)'} "
                f"[{(cur_name or '').strip()}] differs from captured "
                f"{gid} [{group_name}]"
            )
            conn.execute(
                "UPDATE manual_owner_links SET status='conflict', property_id=?, "
                "conflict_note=? WHERE id=?",
                (pid, note, link_id),
            )
            conn.execute(
                "INSERT INTO data_issues (source_id, rule, severity, field_path, "
                "actual_value, message, status, introduced_at) "
                "VALUES (?, ?, 'warning', 'current_owner_group_id', ?, ?, 'open', "
                "datetime('now'))",
                (pid, CONFLICT_RULE, cur_gid or "", note),
            )
            stats["conflicts"] += 1

    conn.commit()
    if verbose:
        print(
            f"  Owner overrides: filled={stats['filled']} "
            f"confirmed={stats['confirmed']} conflicts={stats['conflicts']} "
            f"pending(no prop)={stats['pending_no_property']} "
            f"manages/lists={stats['skipped_non_owns']}"
        )
    return stats
