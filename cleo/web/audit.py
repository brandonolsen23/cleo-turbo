"""
Audit logging — records all CRM mutations for accountability.

Usage:
    from ...web.audit import log_action

    log_action(db, user, "deal.create", "deal", deal_id, {"name": body.name, "stage": body.stage})
"""

import json


def log_action(db, user: dict, action: str, entity_type: str, entity_id: str, details: dict = None):
    """Write an audit log entry.

    Args:
        db: database connection
        user: user dict with at least 'id' or 'username'
        action: dot-notation action like "deal.create", "contact.promote", "group.merge"
        entity_type: "deal", "contact", "group", "list", "group_merge"
        entity_id: the entity's primary key
        details: optional dict of extra context (serialized to JSON)
    """
    user_id = user.get("id") or user.get("user_id")
    username = user.get("username", user.get("display_name", "unknown"))
    details_json = json.dumps(details) if details else None

    db.execute(
        "INSERT INTO audit_log (user_id, action, entity_type, entity_id, details_json) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, action, entity_type, entity_id, details_json)
    )
