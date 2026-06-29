"""
Migration 027: Legacy-to-auto-group mapping + contacts.current_auto_group_id.

Phase B of the Group Identity System plan. Creates the bridge between the
legacy `groups` table (still maintained by the compiler) and the user-facing
`auto_groups` table.

- `legacy_to_auto_group_map`: per legacy group, the dominant auto_group its
  party-sides are in. Rebuilt after every discovery_v2 run.
- `contacts.current_auto_group_id`: denormalised contact-level FK derived from
  the mapping for fast joins (used by API/UI).
"""

import sqlite3
import os


def migrate(conn):
    print("Migration 027: legacy_to_auto_group_map + contacts.current_auto_group_id...")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS legacy_to_auto_group_map (
            legacy_group_id  TEXT PRIMARY KEY,
            auto_group_id    TEXT NOT NULL,
            coverage_pct     REAL,
            source           TEXT NOT NULL CHECK (source IN ('clustered','standalone','user_attached')),
            computed_at      TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_l2a_auto ON legacy_to_auto_group_map(auto_group_id);
    """)

    # Add current_auto_group_id to contacts if not present
    cols = {r[1] for r in conn.execute("PRAGMA table_info(contacts)")}
    if 'current_auto_group_id' not in cols:
        conn.execute("ALTER TABLE contacts ADD COLUMN current_auto_group_id TEXT")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_contacts_auto_group ON contacts(current_auto_group_id)"
        )

    conn.commit()
    print("Migration 027 complete.")


if __name__ == "__main__":
    db_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "cleo.db")
    conn = sqlite3.connect(db_path)
    migrate(conn)
    conn.close()
