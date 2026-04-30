"""
Migration 017: Layer 2 tenure tables + conflict flags.

Adds three new derived tables that replace the static-anchor model with a
time-windowed one:

- auto_group_anchor_tenures: one row per (auto_group_id, anchor, time-window).
  Source of truth for which anchors back which groups, with start/end dates.
- auto_contact_tenures: one row per (contact_fingerprint, auto_group_id, window).
  When a person was associated with a group.
- auto_conflict_flags: one row per detected anomaly (anchor reassigned, contact
  overlap across groups, etc.). Surfaces for human review only.

The existing auto_group_anchors and anchor_uniqueness tables continue to exist
and are rebuilt by Layer 2 as denormalized "current state" snapshots so
downstream API code keeps working without per-route rewrites.
"""
from __future__ import annotations
import os
import sqlite3


def migrate(conn: sqlite3.Connection) -> None:
    print('Migration 017: tenure tables + conflict flags...')

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS auto_group_anchor_tenures (
            id                          INTEGER PRIMARY KEY AUTOINCREMENT,
            auto_group_id               TEXT NOT NULL,
            anchor_type                 TEXT NOT NULL
                CHECK (anchor_type IN ('phone','address_unit','contact')),
            anchor_value                TEXT NOT NULL,
            start_date                  TEXT NOT NULL,
            end_date                    TEXT,
            n_party_sides_in_window     INTEGER NOT NULL,
            dominance_share_in_window   REAL NOT NULL,
            score                       REAL NOT NULL,
            discovered_at               TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_agat_group
            ON auto_group_anchor_tenures(auto_group_id);
        CREATE INDEX IF NOT EXISTS idx_agat_anchor
            ON auto_group_anchor_tenures(anchor_type, anchor_value);

        CREATE TABLE IF NOT EXISTS auto_contact_tenures (
            id                       INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_fingerprint      TEXT NOT NULL,
            auto_group_id            TEXT NOT NULL,
            start_date               TEXT NOT NULL,
            end_date                 TEXT,
            n_party_sides_in_window  INTEGER NOT NULL,
            discovered_at            TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_act_contact
            ON auto_contact_tenures(contact_fingerprint);
        CREATE INDEX IF NOT EXISTS idx_act_group
            ON auto_contact_tenures(auto_group_id);

        CREATE TABLE IF NOT EXISTS auto_conflict_flags (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            conflict_type   TEXT NOT NULL
                CHECK (conflict_type IN
                       ('anchor_reassignment','contact_overlap',
                        'abrupt_tenure_end','transient_tenure')),
            entity_type     TEXT NOT NULL
                CHECK (entity_type IN ('anchor','contact')),
            entity_value    TEXT NOT NULL,
            entity_subtype  TEXT,
            group_a         TEXT,
            group_b         TEXT,
            date_observed   TEXT,
            description     TEXT NOT NULL,
            discovered_at   TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_acf_type
            ON auto_conflict_flags(conflict_type);
        CREATE INDEX IF NOT EXISTS idx_acf_entity
            ON auto_conflict_flags(entity_type, entity_value);
    """)
    conn.commit()
    print('Migration 017 complete.')


if __name__ == '__main__':
    db_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'data', 'cleo.db')
    conn = sqlite3.connect(db_path)
    migrate(conn)
    conn.close()
