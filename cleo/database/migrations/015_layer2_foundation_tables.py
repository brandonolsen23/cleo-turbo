"""
Migration 015: Layer 2 foundation tables (Plan A scope).

Creates derived tables that the Layer 2 builder rebuilds on each run, plus CRM
tables that persist user actions across runs (Plan A reads them; Plan C writes
them through the UI).

Derived (rebuilt every Layer 2 run):
  - brand_stem
  - brand_stem_phrase_map
  - anchor_uniqueness
  - auto_groups
  - auto_group_anchors
  - auto_group_members

CRM (never dropped or rebuilt):
  - auto_group_overrides
  - auto_group_merges
  - auto_anchor_overrides
"""
from __future__ import annotations
import os
import sqlite3


def migrate(conn: sqlite3.Connection) -> None:
    print('Migration 015: creating Layer 2 foundation tables...')
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS brand_stem (
            stem                  TEXT PRIMARY KEY,
            stem_type             TEXT NOT NULL CHECK (stem_type IN ('distinctive', 'position_anchor')),
            dominant_anchor_type  TEXT NOT NULL,
            dominant_anchor_value TEXT NOT NULL,
            dominance_share       REAL NOT NULL,
            volume                INTEGER NOT NULL,
            verified_at           TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS brand_stem_phrase_map (
            phrase     TEXT PRIMARY KEY,
            stem       TEXT NOT NULL,
            confidence REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_bspm_stem ON brand_stem_phrase_map(stem);

        CREATE TABLE IF NOT EXISTS anchor_uniqueness (
            anchor_type         TEXT NOT NULL CHECK (anchor_type IN ('phone','address_root','address_base','contact')),
            anchor_value        TEXT NOT NULL,
            dominant_stem       TEXT,
            dominance_share     REAL,
            volume              INTEGER NOT NULL,
            score               REAL NOT NULL,
            is_service_provider INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (anchor_type, anchor_value)
        );
        CREATE INDEX IF NOT EXISTS idx_au_score ON anchor_uniqueness(score);
        CREATE INDEX IF NOT EXISTS idx_au_stem  ON anchor_uniqueness(dominant_stem);

        CREATE TABLE IF NOT EXISTS auto_groups (
            auto_group_id  TEXT PRIMARY KEY,
            canonical_stem TEXT NOT NULL,
            display_name   TEXT NOT NULL,
            tier           TEXT NOT NULL CHECK (tier IN ('confirmed','probable','candidate')),
            confidence     REAL NOT NULL,
            n_anchors      INTEGER NOT NULL,
            n_members      INTEGER NOT NULL,
            discovered_at  TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_ag_tier ON auto_groups(tier);
        CREATE INDEX IF NOT EXISTS idx_ag_stem ON auto_groups(canonical_stem);

        CREATE TABLE IF NOT EXISTS auto_group_anchors (
            auto_group_id TEXT NOT NULL,
            anchor_type   TEXT NOT NULL,
            anchor_value  TEXT NOT NULL,
            score         REAL NOT NULL,
            PRIMARY KEY (auto_group_id, anchor_type, anchor_value)
        );

        CREATE TABLE IF NOT EXISTS auto_group_members (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            auto_group_id TEXT NOT NULL,
            member_type   TEXT NOT NULL CHECK (member_type IN ('party_side','numbered_corp')),
            source_id     TEXT,
            side          TEXT,
            corp_name     TEXT,
            match_score   REAL NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_agm_party
            ON auto_group_members(auto_group_id, source_id, side)
            WHERE member_type = 'party_side';
        CREATE UNIQUE INDEX IF NOT EXISTS idx_agm_corp
            ON auto_group_members(auto_group_id, corp_name)
            WHERE member_type = 'numbered_corp';

        -- CRM tables
        CREATE TABLE IF NOT EXISTS auto_group_overrides (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            auto_group_id TEXT NOT NULL,
            action        TEXT NOT NULL CHECK (action IN ('confirm','reject','split')),
            user_id       TEXT NOT NULL,
            action_at     TEXT NOT NULL DEFAULT (datetime('now')),
            notes         TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_ago_group ON auto_group_overrides(auto_group_id);

        CREATE TABLE IF NOT EXISTS auto_group_merges (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_auto_group_id TEXT NOT NULL,
            child_auto_group_id  TEXT NOT NULL,
            user_id              TEXT NOT NULL,
            action_at            TEXT NOT NULL DEFAULT (datetime('now')),
            notes                TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_agm_parent ON auto_group_merges(parent_auto_group_id);

        CREATE TABLE IF NOT EXISTS auto_anchor_overrides (
            id                        INTEGER PRIMARY KEY AUTOINCREMENT,
            anchor_type               TEXT NOT NULL,
            anchor_value              TEXT NOT NULL,
            override_stem             TEXT,
            override_service_provider INTEGER NOT NULL DEFAULT 0,
            user_id                   TEXT NOT NULL,
            action_at                 TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_aao_anchor ON auto_anchor_overrides(anchor_type, anchor_value);
    """)
    conn.commit()
    print('Migration 015 complete.')


if __name__ == '__main__':
    db_path = os.path.join(
        os.path.dirname(__file__), '..', '..', '..', 'data', 'cleo.db'
    )
    conn = sqlite3.connect(db_path)
    migrate(conn)
    conn.close()
