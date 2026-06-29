"""
Migration 032: add transacted_type_mix to auto_group_analytics.

property_type_mix counts currently-owned properties (rolled up from
group_analytics). That semantic is fine for "what does this operator currently
hold" but wrong for contact-facing questions like "what does Jonathan transact
in" — properties he bought in 2020 that have since been resold show 0 current
ownership.

transacted_type_mix counts distinct properties any of the auto_group's
party-sides have ever transacted on, from transactions.property_id →
properties.asset_class. This is what the contacts page Primary/Secondary Type
columns and asset-class filter use.
"""

import sqlite3
import os


def migrate(conn):
    print("Migration 032: adding transacted_type_mix to auto_group_analytics...")

    conn.executescript("""
        ALTER TABLE auto_group_analytics ADD COLUMN transacted_type_mix TEXT;
        ALTER TABLE auto_group_analytics ADD COLUMN transacted_property_count INTEGER;
    """)
    conn.commit()
    print("Migration 032 complete.")


if __name__ == "__main__":
    db_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "cleo.db")
    conn = sqlite3.connect(db_path)
    migrate(conn)
    conn.close()
