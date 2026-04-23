"""
Migration 008: Replace clustering tables with brand-token index tables.

Drops the Phase A clustering schema (atom_groups, atom_contacts, timelines,
JV relationships) — those were the wrong abstraction for Layer 1 discovery.
Adds brand_token_index + brand_token_summary to power the Explorer UI.
"""

import sqlite3
import os


def migrate(conn):
    print("Migration 008: swapping clustering tables for brand_token index...")

    conn.executescript("""
        -- Drop the Phase A clustering tables in FK-safe order.
        DROP TABLE IF EXISTS atom_group_relationships;
        DROP TABLE IF EXISTS atom_contact_addresses;
        DROP TABLE IF EXISTS atom_contact_groups;
        DROP TABLE IF EXISTS atom_group_contacts;
        DROP TABLE IF EXISTS atom_group_phones;
        DROP TABLE IF EXISTS atom_group_addresses;
        DROP TABLE IF EXISTS atom_party_entities;
        DROP TABLE IF EXISTS atom_contacts;
        DROP TABLE IF EXISTS atom_groups;
        -- Keep atom_discovery_runs as run history.

        -- New Layer 1 Silo A index tables.
        CREATE TABLE IF NOT EXISTS brand_token_index (
            token        TEXT NOT NULL,
            source_id    TEXT NOT NULL,
            side         TEXT NOT NULL CHECK (side IN ('buyer','seller')),
            PRIMARY KEY (token, source_id, side)
        );
        CREATE INDEX IF NOT EXISTS idx_bti_side ON brand_token_index(source_id, side);

        CREATE TABLE IF NOT EXISTS brand_token_summary (
            token              TEXT PRIMARY KEY,
            idf                REAL NOT NULL,
            n_party_sides      INTEGER NOT NULL,
            n_distinct_phrases INTEGER NOT NULL,
            is_distinctive     INTEGER NOT NULL,   -- 1 if IDF >= min_idf, else 0
            is_excluded        INTEGER NOT NULL,   -- 1 if in excluded_brand_tokens list
            discovered_at      TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_bts_idf ON brand_token_summary(idf);
        CREATE INDEX IF NOT EXISTS idx_bts_n ON brand_token_summary(n_party_sides);
    """)

    # Clear the old next_agr_id / next_acn_id counters — we're not using them anymore.
    conn.execute("DELETE FROM app_meta WHERE key IN ('next_agr_id', 'next_acn_id')")
    conn.commit()
    print("Migration 008 complete.")


if __name__ == "__main__":
    db_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "cleo.db")
    conn = sqlite3.connect(db_path)
    migrate(conn)
    conn.close()
