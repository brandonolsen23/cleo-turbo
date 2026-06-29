"""
Migration 028: User edits audit trail + provenance column on auto_group_members.

Phase C of the Group Identity System plan. Captures every manual edit to the
unified Group concept (detach a party-side, attach a party-side, rename a
group, merge two groups, create a new group) in a single auto_group_user_edits
table. The apply_user_edits stage in discovery_v2 reads this table and
re-applies the edits after every rebuild so user assertions survive.

`auto_group_members.attached_by` records the provenance of every membership
row so the UI can distinguish algorithm- vs user- vs standalone-driven
attachments and offer one-click revert.
"""

import sqlite3
import os


def migrate(conn):
    print("Migration 028: auto_group_user_edits + attached_by provenance...")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS auto_group_user_edits (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            edit_type            TEXT NOT NULL CHECK (edit_type IN
                                   ('detach','attach','rename','merge','split','create')),
            auto_group_id        TEXT NOT NULL,
            source_id            TEXT,
            side                 TEXT CHECK (side IS NULL OR side IN ('buyer','seller')),
            target_auto_group_id TEXT,
            new_display_name     TEXT,
            new_canonical_stem   TEXT,
            edited_by            TEXT NOT NULL,
            edited_at            TEXT DEFAULT (datetime('now')),
            notes                TEXT,
            is_active            INTEGER NOT NULL DEFAULT 1
        );

        CREATE INDEX IF NOT EXISTS idx_ague_auto_group ON auto_group_user_edits(auto_group_id);
        CREATE INDEX IF NOT EXISTS idx_ague_active     ON auto_group_user_edits(is_active);
        CREATE INDEX IF NOT EXISTS idx_ague_type       ON auto_group_user_edits(edit_type);
    """)

    # Add attached_by to auto_group_members if not present
    cols = {r[1] for r in conn.execute("PRAGMA table_info(auto_group_members)")}
    if 'attached_by' not in cols:
        conn.execute("ALTER TABLE auto_group_members ADD COLUMN attached_by TEXT")
        # Backfill: existing rows are from the algorithm
        conn.execute("UPDATE auto_group_members SET attached_by = 'algorithm' WHERE attached_by IS NULL")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_agm_attached_by ON auto_group_members(attached_by)")

    conn.commit()
    print("Migration 028 complete.")


if __name__ == "__main__":
    db_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "cleo.db")
    conn = sqlite3.connect(db_path)
    migrate(conn)
    conn.close()
