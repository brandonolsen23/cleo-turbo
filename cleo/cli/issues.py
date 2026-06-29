"""
CLI for reviewing and resolving issues from the in-app tracker.

Common workflows:

    # List open issues, newest first
    python -m cleo.cli.issues list

    # List open critical/high issues only
    python -m cleo.cli.issues list --severity high

    # List by category
    python -m cleo.cli.issues list --category rt_property_mismatch

    # View a single issue with full context
    python -m cleo.cli.issues view 17

    # Mark resolved with a note + commit
    python -m cleo.cli.issues resolve 17 --note "Fixed PIN bridge entry" --commit abc1234

    # Mark in_progress (Claude claiming the issue)
    python -m cleo.cli.issues claim 17

    # Mark wontfix or duplicate
    python -m cleo.cli.issues close 17 --status wontfix --note "Working as intended"
"""

from __future__ import annotations
import argparse
import json
import sys

from cleo.database.connection import get_connection


SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _issue_row(r) -> dict:
    d = dict(r)
    try:
        d["categories"] = json.loads(d.get("categories") or "[]")
    except (json.JSONDecodeError, TypeError):
        d["categories"] = []
    if d.get("component_data_json"):
        try:
            d["component_data"] = json.loads(d["component_data_json"])
        except (json.JSONDecodeError, TypeError):
            d["component_data"] = None
    d.pop("component_data_json", None)
    return d


def cmd_list(args):
    conn = get_connection()
    conditions = []
    params = []
    if args.status:
        conditions.append("status = ?")
        params.append(args.status)
    else:
        conditions.append("status = 'open'")
    if args.severity:
        conditions.append("severity = ?")
        params.append(args.severity)
    if args.category:
        conditions.append("categories LIKE ?")
        params.append(f'%"{args.category}"%')
    if args.entity_type:
        conditions.append("entity_type = ?")
        params.append(args.entity_type)
    where = " AND ".join(conditions)

    rows = conn.execute(
        f"SELECT * FROM issues WHERE {where} "
        "ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 "
        "                       WHEN 'medium' THEN 2 ELSE 3 END, "
        "         reported_at ASC",
        params,
    ).fetchall()

    if args.json:
        print(json.dumps([_issue_row(r) for r in rows], indent=2))
        return

    if not rows:
        print("(no issues match)")
        return

    print(f"{'#':>4}  {'SEV':<8} {'STATUS':<12} {'ENTITY':<25} {'CATEGORIES':<35} TITLE")
    print('-' * 130)
    for r in rows:
        d = _issue_row(r)
        ent = f'{d["entity_type"]}:{d["entity_id"] or "—"}'[:23]
        cats = ",".join(d["categories"])[:33]
        title = (d["title"] or "")[:60]
        print(f'{d["id"]:>4}  {d["severity"]:<8} {d["status"]:<12} {ent:<25} {cats:<35} {title}')


def cmd_view(args):
    conn = get_connection()
    r = conn.execute("SELECT * FROM issues WHERE id = ?", (args.id,)).fetchone()
    if not r:
        print(f"Issue {args.id} not found.", file=sys.stderr)
        sys.exit(1)

    d = _issue_row(r)
    if args.json:
        print(json.dumps(d, indent=2))
        return

    print(f"Issue #{d['id']} — {d['title']}")
    print(f"  Status:     {d['status']}")
    print(f"  Severity:   {d['severity']}")
    print(f"  Categories: {', '.join(d['categories'])}")
    print(f"  Entity:     {d['entity_type']} = {d['entity_id'] or '—'}")
    if d.get("component"):
        print(f"  Component:  {d['component']}")
    if d.get("component_data"):
        print(f"  Component data: {json.dumps(d['component_data'])}")
    print(f"  Reported:   {d['reported_at']} by {d['reported_by']}")
    if d.get("resolved_at"):
        print(f"  Resolved:   {d['resolved_at']} by {d.get('resolved_by')}")
    if d.get("fixed_in_commit"):
        print(f"  Commit:     {d['fixed_in_commit']}")
    print()
    print("Description:")
    print(d["description"])
    if d.get("resolution_notes"):
        print()
        print("Resolution notes:")
        print(d["resolution_notes"])


def _set_status(conn, issue_id, new_status, *, note=None, commit=None, by="claude"):
    existing = conn.execute("SELECT id FROM issues WHERE id = ?", (issue_id,)).fetchone()
    if not existing:
        print(f"Issue {issue_id} not found.", file=sys.stderr)
        sys.exit(1)

    set_parts = ["status = ?", "updated_at = datetime('now')"]
    params = [new_status]
    if new_status in ("resolved", "wontfix", "duplicate"):
        set_parts.append("resolved_at = datetime('now')")
        set_parts.append("resolved_by = ?")
        params.append(by)
    if note is not None:
        set_parts.append("resolution_notes = ?")
        params.append(note)
    if commit is not None:
        set_parts.append("fixed_in_commit = ?")
        params.append(commit)
    params.append(issue_id)
    conn.execute(f"UPDATE issues SET {', '.join(set_parts)} WHERE id = ?", params)
    conn.commit()
    print(f"Issue {issue_id} → {new_status}")


def cmd_resolve(args):
    conn = get_connection()
    _set_status(conn, args.id, "resolved",
                note=args.note, commit=args.commit, by=args.by)


def cmd_claim(args):
    conn = get_connection()
    _set_status(conn, args.id, "in_progress", by=args.by)


def cmd_close(args):
    conn = get_connection()
    _set_status(conn, args.id, args.status,
                note=args.note, commit=args.commit, by=args.by)


def main():
    p = argparse.ArgumentParser(description="Review and resolve in-app issues.")
    sub = p.add_subparsers(dest="cmd", required=True)

    lp = sub.add_parser("list", help="List issues (default: open)")
    lp.add_argument("--status", choices=["open", "in_progress", "resolved",
                                          "wontfix", "duplicate"])
    lp.add_argument("--severity", choices=["low", "medium", "high", "critical"])
    lp.add_argument("--category")
    lp.add_argument("--entity-type", choices=["property", "contact", "group",
                                                "transaction", "auto_group", "general"])
    lp.add_argument("--json", action="store_true")
    lp.set_defaults(func=cmd_list)

    vp = sub.add_parser("view", help="Show a single issue's full context")
    vp.add_argument("id", type=int)
    vp.add_argument("--json", action="store_true")
    vp.set_defaults(func=cmd_view)

    rp = sub.add_parser("resolve", help="Mark an issue resolved")
    rp.add_argument("id", type=int)
    rp.add_argument("--note", help="What was done to fix it")
    rp.add_argument("--commit", help="Git SHA of the fix")
    rp.add_argument("--by", default="claude", help="Resolver identity")
    rp.set_defaults(func=cmd_resolve)

    cp = sub.add_parser("claim", help="Mark an issue in_progress")
    cp.add_argument("id", type=int)
    cp.add_argument("--by", default="claude")
    cp.set_defaults(func=cmd_claim)

    xp = sub.add_parser("close", help="Mark wontfix or duplicate")
    xp.add_argument("id", type=int)
    xp.add_argument("--status", choices=["wontfix", "duplicate"], required=True)
    xp.add_argument("--note")
    xp.add_argument("--commit")
    xp.add_argument("--by", default="claude")
    xp.set_defaults(func=cmd_close)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
