"""
Migration 014: address_root_summary table.

Coarser-grained address aggregation than address_base_summary — drops
street_suffix from the key so all variants of the same (number, name)
roll up together. Useful for surfacing big buckets like "66 wellington"
that span 280 'street' + 11 no-suffix party-sides as one root.
"""

import sqlite3
import os


def migrate(conn):
    print("Migration 014: creating address_root_summary table...")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS address_root_summary (
            street_number          TEXT NOT NULL,
            street_name            TEXT NOT NULL,
            n_party_sides          INTEGER NOT NULL,
            n_distinct_suffixes    INTEGER NOT NULL,
            n_distinct_directions  INTEGER NOT NULL,
            n_distinct_suites      INTEGER NOT NULL,
            n_distinct_postals     INTEGER NOT NULL,
            discovered_at          TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (street_number, street_name)
        );
        CREATE INDEX IF NOT EXISTS idx_ars_n ON address_root_summary(n_party_sides);
    """)
    conn.commit()
    print("Migration 014 complete.")


if __name__ == "__main__":
    db_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "cleo.db")
    conn = sqlite3.connect(db_path)
    migrate(conn)
    conn.close()
