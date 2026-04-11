"""
Migration 002: Create group_merges table for manual group consolidation.

This is a CRM-layer table — never touched by the compiler.
Records which groups have been merged into which, enabling:
  - The compiler to redirect references on rebuild
  - The UI to hide absorbed groups
  - Unmerge to reverse the operation

Run:
    cd cleo-turbo
    python -m cleo.database.migrations.002_group_merges
"""

import sqlite3
import os


def migrate(conn):
    print("Migration 002: Creating group_merges table...")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS group_merges (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            source_group_id TEXT NOT NULL,
            target_group_id TEXT NOT NULL,
            merged_by       TEXT,
            merged_at       TEXT DEFAULT (datetime('now')),
            unmerged_at     TEXT,
            unmerged_by     TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_group_merges_source ON group_merges(source_group_id);
        CREATE INDEX IF NOT EXISTS idx_group_merges_target ON group_merges(target_group_id);
        CREATE INDEX IF NOT EXISTS idx_group_merges_active ON group_merges(source_group_id) WHERE unmerged_at IS NULL;
    """)
    conn.commit()
    print("  Created group_merges table with indexes.")

    # Verify
    count = conn.execute("SELECT COUNT(*) FROM group_merges").fetchone()[0]
    print(f"  group_merges rows: {count}")
    print("Migration 002 complete.")


if __name__ == "__main__":
    db_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "cleo.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    migrate(conn)
    conn.close()
