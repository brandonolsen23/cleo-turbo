"""
CLI entry point for the Group Discovery Algorithm.

Subcommands:
  run           Extract signals, cluster, optionally validate against ground truth
  status        Show recent discovery runs
  ground-truth  Add or update a ground truth portfolio entry
"""

import argparse
import json
import os
import sqlite3
import sys


# Resolve the database path relative to this file (../../data/cleo.db)
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_DB_PATH = os.path.join(_PROJECT_ROOT, "data", "cleo.db")


def _open_db() -> sqlite3.Connection:
    """Open the Cleo SQLite database with row_factory set."""
    if not os.path.exists(_DB_PATH):
        print(f"[discovery] ERROR: Database not found at {_DB_PATH}", file=sys.stderr)
        sys.exit(1)
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ── Subcommand: run ───────────────────────────────────────────────────────────

def cmd_run(args) -> None:
    """Run the discovery pipeline."""
    from .types import RunConfig
    from .engine import run_discovery

    # Determine mode from flags
    if args.dry_run:
        mode = "dry_run"
    elif args.execute:
        mode = "execute"
    elif args.incremental:
        mode = "incremental"
    else:
        mode = "validate"   # default (covers --validate and bare `run`)

    config = RunConfig(mode=mode)
    db = _open_db()
    try:
        result = run_discovery(db, config)
    finally:
        db.close()

    print()
    print("── Summary ──────────────────────────────────────────────")
    print(f"  run_id            : {result.run_id}")
    print(f"  mode              : {result.mode}")
    print(f"  clusters_found    : {result.clusters_found}")
    print(f"  groups_processed  : {result.groups_processed}")
    print(f"  merges_executed   : {result.merges_executed}")
    print(f"  suggestions_created: {result.suggestions_created}")


# ── Subcommand: status ────────────────────────────────────────────────────────

def cmd_status(args) -> None:
    """Show recent discovery runs."""
    db = _open_db()
    try:
        rows = db.execute(
            """
            SELECT run_id, mode, started_at, completed_at, stats_json
            FROM discovery_runs
            ORDER BY started_at DESC
            LIMIT 20
            """
        ).fetchall()
    finally:
        db.close()

    if not rows:
        print("No discovery runs found.")
        return

    print(f"{'RUN ID':<30}  {'MODE':<12}  {'STARTED':<20}  {'CLUSTERS':>8}  {'GROUPS':>7}")
    print("-" * 90)
    for row in rows:
        stats = {}
        if row["stats_json"]:
            try:
                stats = json.loads(row["stats_json"])
            except Exception:
                pass
        clusters = stats.get("clusters_found", "-")
        groups = stats.get("groups_processed", "-")
        started = (row["started_at"] or "")[:19]
        print(
            f"{row['run_id']:<30}  {row['mode']:<12}  {started:<20}  {str(clusters):>8}  {str(groups):>7}"
        )


# ── Subcommand: ground-truth ──────────────────────────────────────────────────

def cmd_ground_truth(args) -> None:
    """Add or update a ground truth portfolio."""
    from .validation import save_ground_truth

    if not args.name:
        print("[discovery] ERROR: --name is required", file=sys.stderr)
        sys.exit(1)
    if not args.anchor:
        print("[discovery] ERROR: --anchor is required", file=sys.stderr)
        sys.exit(1)
    if not args.members:
        print("[discovery] ERROR: --members is required", file=sys.stderr)
        sys.exit(1)

    member_ids = [m.strip() for m in args.members.split(",") if m.strip()]
    if not member_ids:
        print("[discovery] ERROR: --members must contain at least one group ID", file=sys.stderr)
        sys.exit(1)

    db = _open_db()
    try:
        save_ground_truth(
            db=db,
            portfolio_name=args.name,
            anchor_group_id=args.anchor,
            member_group_ids=member_ids,
            notes=args.notes or "",
        )
    finally:
        db.close()

    print(f"[discovery] Ground truth saved: '{args.name}'")
    print(f"[discovery]   anchor : {args.anchor}")
    print(f"[discovery]   members: {len(member_ids)}")
    if args.notes:
        print(f"[discovery]   notes  : {args.notes}")


# ── Argument parser ───────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m cleo.discovery",
        description="Group Discovery Algorithm — portfolio clustering for Ontario CRE entities.",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    # run
    run_parser = subparsers.add_parser(
        "run",
        help="Run the discovery pipeline",
    )
    mode_group = run_parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--validate",
        action="store_true",
        default=False,
        help="Validate clusters against ground truth (default)",
    )
    mode_group.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Execute merges for high-confidence clusters",
    )
    mode_group.add_argument(
        "--incremental",
        action="store_true",
        default=False,
        help="Process only new transactions since last run",
    )
    mode_group.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        default=False,
        help="Preview results without writing to the database",
    )

    # status
    subparsers.add_parser(
        "status",
        help="Show recent discovery runs",
    )

    # ground-truth
    gt_parser = subparsers.add_parser(
        "ground-truth",
        help="Add or update a ground truth portfolio",
    )
    gt_parser.add_argument("--name", required=True, help="Portfolio name (e.g. 'Skyline REIT')")
    gt_parser.add_argument("--anchor", required=True, help="Anchor group ID (GRP_NNNNN)")
    gt_parser.add_argument(
        "--members",
        required=True,
        help="Comma-separated list of member group IDs",
    )
    gt_parser.add_argument("--notes", default="", help="Optional notes")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "run":
        cmd_run(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "ground-truth":
        cmd_ground_truth(args)
    else:
        parser.print_help()
        sys.exit(1)
