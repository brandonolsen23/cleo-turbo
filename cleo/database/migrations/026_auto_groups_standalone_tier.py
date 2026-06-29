"""
Migration 026: Extend auto_groups.tier to include 'standalone' and 'merged'.

Phase A of the Group Identity System plan: every party-side must belong to an
auto_group. For legacy groups not covered by any clustering result, we create
a 'standalone' auto_group. 'merged' is added now too (Phase C will use it).

SQLite doesn't support modifying CHECK constraints in place, so we recreate
the table. Existing rows are preserved.
"""

import sqlite3
import os


def migrate(conn):
    print("Migration 026: extending auto_groups.tier check constraint...")

    # Build new table, copy data, swap.
    conn.executescript("""
        CREATE TABLE auto_groups_new (
            auto_group_id  TEXT PRIMARY KEY,
            canonical_stem TEXT NOT NULL,
            display_name   TEXT NOT NULL,
            tier           TEXT NOT NULL CHECK (tier IN ('confirmed','probable','candidate','standalone','merged')),
            confidence     REAL NOT NULL,
            n_anchors      INTEGER NOT NULL,
            n_members      INTEGER NOT NULL,
            discovered_at  TEXT DEFAULT (datetime('now'))
        );

        INSERT INTO auto_groups_new
        SELECT auto_group_id, canonical_stem, display_name, tier, confidence,
               n_anchors, n_members, discovered_at
        FROM auto_groups;

        DROP TABLE auto_groups;
        ALTER TABLE auto_groups_new RENAME TO auto_groups;

        CREATE INDEX IF NOT EXISTS idx_ag_tier ON auto_groups(tier);
        CREATE INDEX IF NOT EXISTS idx_ag_stem ON auto_groups(canonical_stem);
    """)
    conn.commit()
    print("Migration 026 complete.")


if __name__ == "__main__":
    db_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "cleo.db")
    conn = sqlite3.connect(db_path)
    migrate(conn)
    conn.close()
