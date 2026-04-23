"""
Migration 007: Create atom-based portfolio discovery tables.

All tables are prefixed atom_* to coexist with legacy discovery_*/groups
tables until Phase G retirement. These are DERIVED tables — rebuilt by
`cleo.discovery_v2.runner` on every run. Never contain user CRM data.

Run:
    python -m cleo.database.migrations.007_atom_discovery_tables
"""

import sqlite3
import os


def migrate(conn):
    print("Migration 007: Creating atom-based discovery tables...")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS atom_groups (
            id               TEXT PRIMARY KEY,
            canonical_brand  TEXT NOT NULL,
            display_name     TEXT NOT NULL,
            first_seen       TEXT,
            last_seen        TEXT,
            party_side_count INTEGER NOT NULL,
            discovered_at    TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS atom_contacts (
            id                TEXT PRIMARY KEY,
            canonical_name    TEXT NOT NULL,
            display_name      TEXT NOT NULL,
            first_seen        TEXT,
            last_seen         TEXT,
            party_side_count  INTEGER NOT NULL,
            discovered_at     TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS atom_party_entities (
            source_id          TEXT NOT NULL,
            side               TEXT NOT NULL CHECK (side IN ('buyer','seller')),
            group_id           TEXT REFERENCES atom_groups(id),
            contact_id         TEXT REFERENCES atom_contacts(id),
            group_link_tier    TEXT,
            contact_link_tier  TEXT,
            PRIMARY KEY (source_id, side)
        );
        CREATE INDEX IF NOT EXISTS idx_ape_group ON atom_party_entities(group_id);
        CREATE INDEX IF NOT EXISTS idx_ape_contact ON atom_party_entities(contact_id);

        CREATE TABLE IF NOT EXISTS atom_group_addresses (
            group_id       TEXT NOT NULL REFERENCES atom_groups(id),
            postal         TEXT, street_number TEXT, street_name TEXT, street_suffix TEXT,
            first_seen     TEXT, last_seen TEXT,
            n_observations INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_aga_group ON atom_group_addresses(group_id);

        CREATE TABLE IF NOT EXISTS atom_group_phones (
            group_id       TEXT NOT NULL REFERENCES atom_groups(id),
            phone          TEXT NOT NULL,
            first_seen     TEXT, last_seen TEXT,
            n_observations INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_agp_group ON atom_group_phones(group_id);

        CREATE TABLE IF NOT EXISTS atom_group_contacts (
            group_id       TEXT NOT NULL REFERENCES atom_groups(id),
            contact_id     TEXT NOT NULL REFERENCES atom_contacts(id),
            first_seen     TEXT, last_seen TEXT,
            n_observations INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_agc_group ON atom_group_contacts(group_id);

        CREATE TABLE IF NOT EXISTS atom_contact_groups (
            contact_id     TEXT NOT NULL REFERENCES atom_contacts(id),
            group_id       TEXT NOT NULL REFERENCES atom_groups(id),
            first_seen     TEXT, last_seen TEXT,
            n_observations INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_acg_contact ON atom_contact_groups(contact_id);

        CREATE TABLE IF NOT EXISTS atom_contact_addresses (
            contact_id     TEXT NOT NULL REFERENCES atom_contacts(id),
            postal         TEXT, street_number TEXT, street_name TEXT, street_suffix TEXT,
            first_seen     TEXT, last_seen TEXT,
            n_observations INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_aca_contact ON atom_contact_addresses(contact_id);

        CREATE TABLE IF NOT EXISTS atom_group_relationships (
            group_a_id     TEXT NOT NULL REFERENCES atom_groups(id),
            group_b_id     TEXT NOT NULL REFERENCES atom_groups(id),
            kind           TEXT NOT NULL CHECK (kind IN ('jv','parent_subsidiary','successor')),
            first_seen     TEXT, last_seen TEXT,
            n_party_sides  INTEGER,
            PRIMARY KEY (group_a_id, group_b_id, kind)
        );

        CREATE TABLE IF NOT EXISTS atom_discovery_runs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            config_version  TEXT NOT NULL,
            config_snapshot TEXT NOT NULL,
            ran_at          TEXT DEFAULT (datetime('now')),
            n_party_sides   INTEGER,
            n_groups        INTEGER,
            n_contacts      INTEGER,
            audit_metrics   TEXT,
            notes           TEXT
        );
    """)

    # Seed feature flag (legacy stays authoritative in Phase A).
    conn.execute(
        "INSERT OR IGNORE INTO app_meta (key, value, updated_at) "
        "VALUES ('discovery_engine', 'legacy', datetime('now'))"
    )
    conn.commit()
    print("Migration 007 complete.")


if __name__ == "__main__":
    db_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "cleo.db")
    conn = sqlite3.connect(db_path)
    migrate(conn)
    conn.close()
