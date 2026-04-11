"""
Standalone group merge operations — no FastAPI dependencies.

Used by both the API routes and standalone scripts/tests.
"""


def resolve_target(db, group_id: str) -> str:
    """Follow merge chains to find the ultimate target group."""
    visited = set()
    current = group_id
    while True:
        if current in visited:
            break  # prevent cycles
        visited.add(current)
        row = db.execute(
            "SELECT target_group_id FROM group_merges "
            "WHERE source_group_id = ? AND unmerged_at IS NULL",
            (current,)
        ).fetchone()
        if row:
            current = row[0]
        else:
            break
    return current


def execute_merge(db, source_id: str, target_id: str):
    """Move all references from source group to target group."""
    # Derived tables
    db.execute(
        "UPDATE properties SET current_owner_group_id = ? WHERE current_owner_group_id = ?",
        (target_id, source_id)
    )
    db.execute(
        "UPDATE contacts SET current_group_id = ? WHERE current_group_id = ?",
        (target_id, source_id)
    )
    db.execute(
        "UPDATE transaction_parties SET group_id = ? WHERE group_id = ?",
        (target_id, source_id)
    )

    # Copy known names to target
    db.execute(
        "INSERT OR IGNORE INTO group_names (group_id, name, normalized, source_id) "
        "SELECT ?, name, normalized, source_id FROM group_names WHERE group_id = ?",
        (target_id, source_id)
    )

    # CRM tables — move notes
    db.execute(
        "UPDATE group_notes SET group_id = ? WHERE group_id = ?",
        (target_id, source_id)
    )

    # CRM — move manual contact links (skip duplicates)
    existing = db.execute(
        "SELECT contact_id FROM group_contacts WHERE group_id = ?",
        (target_id,)
    ).fetchall()
    existing_ids = {r[0] for r in existing}
    source_links = db.execute(
        "SELECT contact_id, is_current, role, notes, linked_at FROM group_contacts WHERE group_id = ?",
        (source_id,)
    ).fetchall()
    for link in source_links:
        if link[0] not in existing_ids:
            db.execute(
                "INSERT INTO group_contacts (group_id, contact_id, is_current, role, notes, linked_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (target_id, link[0], link[1], link[2], link[3], link[4])
            )
    db.execute("DELETE FROM group_contacts WHERE group_id = ?", (source_id,))

    # CRM — move deals
    db.execute(
        "UPDATE deals SET group_id = ? WHERE group_id = ?",
        (target_id, source_id)
    )

    # CRM — move list memberships
    db.execute(
        "UPDATE OR IGNORE list_members SET member_id = ? "
        "WHERE member_type = 'group' AND member_id = ?",
        (target_id, source_id)
    )
    db.execute(
        "DELETE FROM list_members WHERE member_type = 'group' AND member_id = ?",
        (source_id,)
    )

    # Mark source as merged
    db.execute(
        "UPDATE groups SET status = 'merged' WHERE id = ?",
        (source_id,)
    )

    # Recompute counts on target
    prop_count = db.execute(
        "SELECT COUNT(*) FROM properties WHERE current_owner_group_id = ?",
        (target_id,)
    ).fetchone()[0]
    contact_count = db.execute(
        "SELECT COUNT(*) FROM contacts WHERE current_group_id = ?",
        (target_id,)
    ).fetchone()[0]
    tx_count = db.execute(
        "SELECT COUNT(*) FROM transaction_parties WHERE group_id = ?",
        (target_id,)
    ).fetchone()[0]
    db.execute(
        "UPDATE groups SET property_count = ?, contact_count = ?, transaction_count = ? WHERE id = ?",
        (prop_count, contact_count, tx_count, target_id)
    )
