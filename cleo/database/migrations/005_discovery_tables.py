"""
Migration 005: Create discovery tables for portfolio clustering algorithm.

These are CRM-layer tables — never touched by the compiler.
The discovery engine writes evidence and run metadata here.
Confirmed clusters become real group_merges entries.

Run:
    cd cleo-turbo
    python -m cleo.database.migrations.005_discovery_tables
"""

import sqlite3
import os


def migrate(conn):
    print("Migration 005: Creating discovery tables...")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS discovery_evidence (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id          TEXT NOT NULL,
            signal_type     TEXT NOT NULL,
            signal_value    TEXT NOT NULL,
            source_group_id TEXT NOT NULL,
            target_group_id TEXT NOT NULL,
            source_id       TEXT,
            rule_id         TEXT,
            confidence      REAL,
            iteration       INTEGER DEFAULT 0,
            created_at      TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_disc_evidence_run ON discovery_evidence(run_id);
        CREATE INDEX IF NOT EXISTS idx_disc_evidence_source ON discovery_evidence(source_group_id);
        CREATE INDEX IF NOT EXISTS idx_disc_evidence_target ON discovery_evidence(target_group_id);
        CREATE INDEX IF NOT EXISTS idx_disc_evidence_type ON discovery_evidence(signal_type);

        CREATE TABLE IF NOT EXISTS discovery_runs (
            run_id          TEXT PRIMARY KEY,
            mode            TEXT NOT NULL,
            started_at      TEXT NOT NULL,
            completed_at    TEXT,
            stats_json      TEXT,
            diff_json       TEXT,
            config_json     TEXT
        );

        CREATE TABLE IF NOT EXISTS discovery_exclusions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            exclusion_type  TEXT NOT NULL,
            exclusion_value TEXT NOT NULL,
            reason          TEXT,
            created_by      TEXT,
            created_at      TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_disc_exclusions_type ON discovery_exclusions(exclusion_type);

        CREATE TABLE IF NOT EXISTS discovery_ground_truth (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            portfolio_name  TEXT NOT NULL,
            anchor_group_id TEXT NOT NULL,
            member_group_ids_json TEXT NOT NULL,
            notes           TEXT,
            created_at      TEXT DEFAULT (datetime('now')),
            updated_at      TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    print("  Created discovery_evidence, discovery_runs, discovery_exclusions, discovery_ground_truth.")

    # Verify
    for table in ['discovery_evidence', 'discovery_runs', 'discovery_exclusions', 'discovery_ground_truth']:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table} rows: {count}")
    print("Migration 005 complete.")


if __name__ == "__main__":
    db_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "cleo.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    migrate(conn)
    conn.close()
