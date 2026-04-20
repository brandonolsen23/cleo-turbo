"""
Migration 006: Create labeling tables for party link labeling tool.

These are CRM-layer tables — never touched by the compiler.
Used by the /api/labeling endpoints to capture user-labeled
party pairs with field-level links.

Run:
    cd cleo-turbo
    python -m cleo.database.migrations.006_labeling_tables
"""

import sqlite3
import os


def migrate(conn):
    print("Migration 006: Creating labeling tables...")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS labeling_sessions (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            name                TEXT NOT NULL,
            audit_slug          TEXT,
            anchor_source_id    TEXT NOT NULL,
            anchor_side         TEXT NOT NULL CHECK (anchor_side IN ('buyer','seller')),
            status              TEXT NOT NULL DEFAULT 'active'
                                  CHECK (status IN ('active','paused','done')),
            created_by          TEXT NOT NULL,
            created_at          TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at          TEXT NOT NULL DEFAULT (datetime('now')),
            completed_at        TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_labeling_sessions_status ON labeling_sessions(status);
        CREATE INDEX IF NOT EXISTS idx_labeling_sessions_audit ON labeling_sessions(audit_slug);

        CREATE TABLE IF NOT EXISTS labeling_verdicts (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id          INTEGER NOT NULL REFERENCES labeling_sessions(id) ON DELETE CASCADE,
            source_id           TEXT NOT NULL,
            side                TEXT NOT NULL CHECK (side IN ('buyer','seller')),
            verdict             TEXT NOT NULL CHECK (verdict IN ('confirmed','rejected')),
            left_source_id      TEXT NOT NULL,
            left_side           TEXT NOT NULL CHECK (left_side IN ('buyer','seller')),
            seed_id             INTEGER REFERENCES labeling_seeds(id) ON DELETE SET NULL,
            rationale           TEXT,
            created_by          TEXT NOT NULL,
            created_at          TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE (session_id, source_id, side)
        );

        CREATE INDEX IF NOT EXISTS idx_labeling_verdicts_session ON labeling_verdicts(session_id);
        CREATE INDEX IF NOT EXISTS idx_labeling_verdicts_verdict ON labeling_verdicts(verdict);

        CREATE TABLE IF NOT EXISTS labeling_links (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            verdict_id          INTEGER NOT NULL REFERENCES labeling_verdicts(id) ON DELETE CASCADE,
            from_field_type     TEXT NOT NULL,
            from_field_value    TEXT NOT NULL,
            to_field_type       TEXT NOT NULL,
            to_field_value      TEXT NOT NULL,
            kind                TEXT NOT NULL CHECK (kind IN ('exact','implied')),
            created_at          TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_labeling_links_verdict ON labeling_links(verdict_id);

        CREATE TABLE IF NOT EXISTS labeling_seeds (
            id                              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id                      INTEGER NOT NULL REFERENCES labeling_sessions(id) ON DELETE CASCADE,
            term                            TEXT NOT NULL,
            field_type                      TEXT NOT NULL,
            state                           TEXT NOT NULL DEFAULT 'pending'
                                              CHECK (state IN ('pending','in_progress','done','skipped')),
            first_contributed_by_source_id  TEXT NOT NULL,
            first_contributed_by_side       TEXT NOT NULL CHECK (first_contributed_by_side IN ('buyer','seller')),
            completed_at                    TEXT,
            created_at                      TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE (session_id, term, field_type)
        );

        CREATE INDEX IF NOT EXISTS idx_labeling_seeds_session_state ON labeling_seeds(session_id, state);

        CREATE TABLE IF NOT EXISTS labeling_reviewed_index (
            session_id          INTEGER NOT NULL REFERENCES labeling_sessions(id) ON DELETE CASCADE,
            source_id           TEXT NOT NULL,
            side                TEXT NOT NULL CHECK (side IN ('buyer','seller')),
            reviewed_at         TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (session_id, source_id, side)
        );
    """)
    conn.commit()
    print("  Created 5 labeling tables.")

    for table in ['labeling_sessions', 'labeling_verdicts', 'labeling_links',
                  'labeling_seeds', 'labeling_reviewed_index']:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table} rows: {count}")
    print("Migration 006 complete.")


if __name__ == "__main__":
    db_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "cleo.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    migrate(conn)
    conn.close()
