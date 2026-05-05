"""
Migration 018: contact_brand_tenures derived table.

Adds a per-(contact, brand_stem) tenure table sourced from party_atoms
brand_phrase rows in the `trade_name`, `care_of`, and `companies_json`
source fields. Replaces auto_contact_tenures as the source of truth for
"where a contact worked, when" on the Contact detail page.

Idempotent: rebuilt on every Layer 2 run via build_contact_brand_tenures.
"""
from __future__ import annotations
import os
import sqlite3


def migrate(conn: sqlite3.Connection) -> None:
    print("Migration 018: contact_brand_tenures table...")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS contact_brand_tenures (
            id                          INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_fingerprint         TEXT NOT NULL,
            brand_stem                  TEXT NOT NULL,
            strict_start_date           TEXT NOT NULL,
            strict_end_date             TEXT NOT NULL,
            inferred_start_date         TEXT NOT NULL,
            inferred_end_date           TEXT NOT NULL,
            n_party_sides_strict        INTEGER NOT NULL,
            n_party_sides_inferred      INTEGER NOT NULL,
            top_phrases_json            TEXT NOT NULL,
            source_field_breakdown_json TEXT NOT NULL,
            dominant_address_unit       TEXT,
            auto_group_id               TEXT,
            is_active                   INTEGER NOT NULL,
            discovered_at               TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_cbt_contact
            ON contact_brand_tenures(contact_fingerprint);
        CREATE INDEX IF NOT EXISTS idx_cbt_stem
            ON contact_brand_tenures(brand_stem);
        CREATE INDEX IF NOT EXISTS idx_cbt_active
            ON contact_brand_tenures(is_active, brand_stem);
    """)
    conn.commit()
    print("Migration 018 complete.")


if __name__ == "__main__":
    db_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "cleo.db")
    conn = sqlite3.connect(db_path)
    migrate(conn)
    conn.close()
