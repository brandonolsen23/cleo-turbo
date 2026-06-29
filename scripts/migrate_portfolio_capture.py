"""
Migration — Portfolio Capture (Milestone 1).

Adds the seven persistent CRM tables (group_profile, group_aliases,
group_match_keys, manual_owner_links, property_capture, property_tenants,
manual_properties). Idempotent: every statement uses IF NOT EXISTS, so it is
safe to re-run and leaves all existing data untouched.

Usage (dev / one-off):
    python scripts/migrate_portfolio_capture.py path/to/cleo.db

Safety: this script refuses to run unless given an explicit DB path, so it
can never silently touch the live database. Always test against a COPY first.
"""
import sqlite3
import sys

NEW_TABLES = [
    "group_profile", "group_aliases", "group_match_keys", "manual_owner_links",
    "property_capture", "property_tenants", "manual_properties",
]


def migrate(db_path):
    # Import here so the script works whether run from repo root or scripts/.
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from cleo.database.schema import create_all_tables

    conn = sqlite3.connect(db_path)
    before = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    create_all_tables(conn)  # IF NOT EXISTS throughout — only the missing tables are created
    after = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()

    created = [t for t in NEW_TABLES if t in after]
    newly = [t for t in NEW_TABLES if t in after and t not in before]
    missing = [t for t in NEW_TABLES if t not in after]
    print(f"DB: {db_path}")
    print(f"  Portfolio Capture tables present: {len(created)}/7")
    print(f"  Newly created this run: {newly or '(none — already present)'}")
    if missing:
        print(f"  ERROR — still missing: {missing}")
        return 1
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/migrate_portfolio_capture.py path/to/cleo.db")
        print("Refusing to guess the DB path. Test against a COPY before the live file.")
        sys.exit(2)
    sys.exit(migrate(sys.argv[1]))
