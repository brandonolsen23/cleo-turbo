"""
Migration 033: add auto_group_id to CRM tables that point at legacy groups.

Phase D unifies "Group" in the UI to mean an auto_group. Activities and
manual group-contact links need to be addressable by auto_group_id. Both
tables are essentially empty today (activities has 3 rows with no group_id
set; group_contacts has 0 rows), so this is a forward-looking schema change
with no backfill required.

The legacy `group_id` columns stay for now — they can be dropped in a later
phase once nothing reads them. New code writes only `auto_group_id`.
"""

import sqlite3
import os


def migrate(conn):
    print("Migration 033: adding auto_group_id to CRM tables...")

    conn.executescript("""
        ALTER TABLE group_contacts ADD COLUMN auto_group_id TEXT;
        ALTER TABLE activities      ADD COLUMN auto_group_id TEXT;

        CREATE INDEX IF NOT EXISTS idx_group_contacts_auto_group ON group_contacts(auto_group_id);
        CREATE INDEX IF NOT EXISTS idx_activities_auto_group     ON activities(auto_group_id);
    """)
    conn.commit()
    print("Migration 033 complete.")


if __name__ == "__main__":
    db_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "cleo.db")
    conn = sqlite3.connect(db_path)
    migrate(conn)
    conn.close()
