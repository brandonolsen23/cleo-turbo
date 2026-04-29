"""
Migration 016: Layer 1 address_unit_summary + drop anchor_uniqueness CHECK.

Adds a new Layer 1 silo `address_unit_summary` keyed on the full physical address
including city, suffix, direction, suite_type, suite_number. Used to surface
unit-by-unit brand-stem breakdowns and to back the `address_unit` anchor type
in Layer 2.

Drops the CHECK constraint on `anchor_uniqueness.anchor_type` to allow the new
`address_unit` value (and future additions). The builder enforces valid types.
"""
from __future__ import annotations
import os
import sqlite3


def migrate(conn: sqlite3.Connection) -> None:
    print('Migration 016: address_unit_summary + relax anchor_uniqueness CHECK...')

    # Step 1: create address_unit_summary if missing.
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS address_unit_summary (
            city                   TEXT NOT NULL,
            street_number          TEXT NOT NULL,
            street_name            TEXT NOT NULL,
            street_suffix          TEXT NOT NULL DEFAULT '',
            street_direction       TEXT NOT NULL DEFAULT '',
            suite_type             TEXT NOT NULL DEFAULT '',
            suite_number           TEXT NOT NULL DEFAULT '',
            n_party_sides          INTEGER NOT NULL,
            n_distinct_brand_stems INTEGER NOT NULL,
            dominant_stem          TEXT,
            dominance_share        REAL,
            discovered_at          TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (city, street_number, street_name, street_suffix,
                         street_direction, suite_type, suite_number)
        );
        CREATE INDEX IF NOT EXISTS idx_aus_root
            ON address_unit_summary(city, street_number, street_name);
        CREATE INDEX IF NOT EXISTS idx_aus_dominant
            ON address_unit_summary(dominant_stem);
    """)

    # Step 2: drop the CHECK constraint on anchor_uniqueness by recreating the table.
    # SQLite can't ALTER a CHECK; we recreate the table preserving data.
    # Detect whether the CHECK is present before recreating (idempotent).
    sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='anchor_uniqueness'"
    ).fetchone()
    if sql and 'CHECK (anchor_type IN' in (sql[0] or ''):
        conn.executescript("""
            CREATE TABLE anchor_uniqueness__new (
                anchor_type TEXT NOT NULL,
                anchor_value TEXT NOT NULL,
                dominant_stem TEXT,
                dominance_share REAL,
                volume INTEGER NOT NULL,
                score REAL NOT NULL,
                is_service_provider INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (anchor_type, anchor_value)
            );
            INSERT INTO anchor_uniqueness__new
            SELECT * FROM anchor_uniqueness;
            DROP TABLE anchor_uniqueness;
            ALTER TABLE anchor_uniqueness__new RENAME TO anchor_uniqueness;
            CREATE INDEX IF NOT EXISTS idx_au_score ON anchor_uniqueness(score);
            CREATE INDEX IF NOT EXISTS idx_au_stem ON anchor_uniqueness(dominant_stem);
        """)
    conn.commit()
    print('Migration 016 complete.')


if __name__ == '__main__':
    db_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'data', 'cleo.db')
    conn = sqlite3.connect(db_path)
    migrate(conn)
    conn.close()
