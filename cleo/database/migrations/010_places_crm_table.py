"""
Migration 010: User-curated `places` table for Explorer silo-A filtering.

Parallel to industry_stopwords. Seed entries come from the bundled
canadian_places.json; user additions (via Explorer UI) land here with
source='user'. The is_place_name filter in the brand_index builder
combines both sources.
"""

import sqlite3
import os


def migrate(conn):
    print("Migration 010: creating places curation table...")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS places (
            token        TEXT PRIMARY KEY,
            added_by     TEXT,
            added_at     TEXT DEFAULT (datetime('now')),
            source       TEXT NOT NULL CHECK (source IN ('seed','user'))
        );
    """)
    conn.commit()
    print("Migration 010 complete.")


if __name__ == "__main__":
    db_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "cleo.db")
    conn = sqlite3.connect(db_path)
    migrate(conn)
    conn.close()
