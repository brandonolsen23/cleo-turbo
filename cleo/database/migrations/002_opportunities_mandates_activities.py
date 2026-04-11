"""
Migration 002: Sell Opportunities, Buy Mandates, Activities

Creates the three new CRM tables for the opportunity/mandate/matchmaking system.
These are CRM-layer tables — never touched by the compiler.

Usage:
    python -m cleo.database.migrations.002_opportunities_mandates_activities
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from cleo.database.connection import get_connection


def run_migration():
    conn = get_connection()

    # ── Sell Opportunities ──
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sell_opportunities (
            id                  TEXT PRIMARY KEY,
            property_id         TEXT NOT NULL REFERENCES properties(id),
            seller_contact_id   TEXT REFERENCES contacts(id),
            seller_group_id     TEXT REFERENCES groups(id),
            deal_value          INTEGER,
            status              TEXT NOT NULL DEFAULT 'active',
            owner               TEXT,
            notes               TEXT,
            last_activity_at    TEXT DEFAULT (datetime('now')),
            decay_days          INTEGER DEFAULT 14,
            created_at          TEXT DEFAULT (datetime('now')),
            updated_at          TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sell_opps_property ON sell_opportunities(property_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sell_opps_status ON sell_opportunities(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sell_opps_seller_contact ON sell_opportunities(seller_contact_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sell_opps_seller_group ON sell_opportunities(seller_group_id)")

    # ── Buy Mandates ──
    conn.execute("""
        CREATE TABLE IF NOT EXISTS buy_mandates (
            id                  TEXT PRIMARY KEY,
            contact_id          TEXT REFERENCES contacts(id),
            group_id            TEXT REFERENCES groups(id),
            criteria_json       TEXT,
            status              TEXT NOT NULL DEFAULT 'active',
            owner               TEXT,
            notes               TEXT,
            last_activity_at    TEXT DEFAULT (datetime('now')),
            decay_days          INTEGER DEFAULT 14,
            created_at          TEXT DEFAULT (datetime('now')),
            updated_at          TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_buy_mandates_contact ON buy_mandates(contact_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_buy_mandates_group ON buy_mandates(group_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_buy_mandates_status ON buy_mandates(status)")

    # ── Activities ──
    conn.execute("""
        CREATE TABLE IF NOT EXISTS activities (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type         TEXT NOT NULL,
            entity_id           TEXT NOT NULL,
            activity_type       TEXT NOT NULL,
            outcome             TEXT,
            summary             TEXT,
            next_step           TEXT,
            created_by          TEXT,
            created_at          TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_activities_entity ON activities(entity_type, entity_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_activities_created ON activities(created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_activities_type ON activities(activity_type)")

    conn.commit()

    # Verify
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('sell_opportunities', 'buy_mandates', 'activities')"
    ).fetchall()]
    print(f"Created tables: {', '.join(sorted(tables))}")
    print(f"Migration 002 complete.")

    conn.close()


if __name__ == "__main__":
    run_migration()
