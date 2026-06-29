"""
Migration 030: extend auto_group_user_edits to capture HQ overrides.

Adds three new edit_types — set_address, set_website, set_phone — and the
backing columns (new_primary_address, new_website, new_primary_phone). The
apply_user_edits stage in discovery_v2 reads these on every rebuild so manual
and AI-confirmed HQ identity survives forever.
"""

import sqlite3
import os


def migrate(conn):
    print("Migration 030: extending auto_group_user_edits for HQ overrides...")

    conn.executescript("""
        CREATE TABLE auto_group_user_edits_new (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            edit_type            TEXT NOT NULL CHECK (edit_type IN
                                   ('detach','attach','rename','merge','split','create',
                                    'set_address','set_website','set_phone')),
            auto_group_id        TEXT NOT NULL,
            source_id            TEXT,
            side                 TEXT CHECK (side IS NULL OR side IN ('buyer','seller')),
            target_auto_group_id TEXT,
            new_display_name     TEXT,
            new_canonical_stem   TEXT,
            new_primary_address  TEXT,
            new_website          TEXT,
            new_primary_phone    TEXT,
            edited_by            TEXT NOT NULL,
            edited_at            TEXT DEFAULT (datetime('now')),
            notes                TEXT,
            is_active            INTEGER NOT NULL DEFAULT 1
        );

        INSERT INTO auto_group_user_edits_new
            (id, edit_type, auto_group_id, source_id, side, target_auto_group_id,
             new_display_name, new_canonical_stem, edited_by, edited_at, notes, is_active)
        SELECT id, edit_type, auto_group_id, source_id, side, target_auto_group_id,
               new_display_name, new_canonical_stem, edited_by, edited_at, notes, is_active
        FROM auto_group_user_edits;

        DROP TABLE auto_group_user_edits;
        ALTER TABLE auto_group_user_edits_new RENAME TO auto_group_user_edits;

        CREATE INDEX IF NOT EXISTS idx_ague_auto_group ON auto_group_user_edits(auto_group_id);
        CREATE INDEX IF NOT EXISTS idx_ague_active     ON auto_group_user_edits(is_active);
        CREATE INDEX IF NOT EXISTS idx_ague_type       ON auto_group_user_edits(edit_type);
    """)
    conn.commit()
    print("Migration 030 complete.")


if __name__ == "__main__":
    db_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "cleo.db")
    conn = sqlite3.connect(db_path)
    migrate(conn)
    conn.close()
