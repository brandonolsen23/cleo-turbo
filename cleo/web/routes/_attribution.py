"""Shared helper for first/last/by-user attribution lookups on activities."""


def attribution_for(db, fk_column: str, entity_id: str) -> dict:
    """Return first/last contacted + per-user counts for a given entity.

    fk_column must be one of 'contact_id', 'property_id', 'group_id'.
    """
    if fk_column not in ("contact_id", "property_id", "group_id"):
        raise ValueError(f"Invalid fk_column: {fk_column}")

    total = db.execute(
        f"SELECT COUNT(*) FROM activities WHERE {fk_column} = ?", (entity_id,)
    ).fetchone()[0]

    if total == 0:
        return {
            "first_contacted": None,
            "last_contacted": None,
            "total_activities": 0,
            "by_user": [],
        }

    first = db.execute(
        f"""
        SELECT a.created_by_user_id AS user_id,
               u.display_name AS user_name,
               a.happened_at, a.activity_type, a.outcome
        FROM activities a
        LEFT JOIN users u ON u.id = a.created_by_user_id
        WHERE a.{fk_column} = ?
        ORDER BY a.happened_at ASC, a.id ASC
        LIMIT 1
        """,
        (entity_id,),
    ).fetchone()

    last = db.execute(
        f"""
        SELECT a.created_by_user_id AS user_id,
               u.display_name AS user_name,
               a.happened_at, a.activity_type, a.outcome
        FROM activities a
        LEFT JOIN users u ON u.id = a.created_by_user_id
        WHERE a.{fk_column} = ?
        ORDER BY a.happened_at DESC, a.id DESC
        LIMIT 1
        """,
        (entity_id,),
    ).fetchone()

    by_user_rows = db.execute(
        f"""
        SELECT a.created_by_user_id AS user_id,
               u.display_name AS user_name,
               COUNT(*) AS count
        FROM activities a
        LEFT JOIN users u ON u.id = a.created_by_user_id
        WHERE a.{fk_column} = ?
        GROUP BY a.created_by_user_id
        ORDER BY count DESC
        """,
        (entity_id,),
    ).fetchall()

    return {
        "first_contacted": dict(first) if first else None,
        "last_contacted": dict(last) if last else None,
        "total_activities": total,
        "by_user": [dict(r) for r in by_user_rows],
    }
