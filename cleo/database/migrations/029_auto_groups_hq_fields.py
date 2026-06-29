"""
Migration 029: HQ address + website + primary phone on auto_groups.

Wave 5 of the Contact Page Redesign plan. Each auto_group gets a canonical HQ
identity surface:
  - primary_address (canonical key — formatted in the UI via formatCanonicalAddress)
  - primary_address_source ('algorithmic' | 'manual' | 'ai_enriched')
  - website
  - primary_phone

These are populated by:
  - Algorithmic: a discovery_v2 stage that picks the most-common-recent address
    per group's party-sides.
  - Manual: user picks from candidates via the Wave 5 endpoint.
  - AI enrichment: Claude fetches the company's homepage and proposes.

Source priority on rebuild: manual > ai_enriched > algorithmic. User-set values
survive every discovery rebuild via the existing auto_group_user_edits stage.
"""

import sqlite3
import os


def migrate(conn):
    print("Migration 029: adding HQ address / website / primary_phone to auto_groups...")

    cols = {r[1] for r in conn.execute("PRAGMA table_info(auto_groups)")}
    additions = []
    if 'primary_address' not in cols:
        additions.append("ALTER TABLE auto_groups ADD COLUMN primary_address TEXT")
    if 'primary_address_source' not in cols:
        additions.append("ALTER TABLE auto_groups ADD COLUMN primary_address_source TEXT")
    if 'website' not in cols:
        additions.append("ALTER TABLE auto_groups ADD COLUMN website TEXT")
    if 'primary_phone' not in cols:
        additions.append("ALTER TABLE auto_groups ADD COLUMN primary_phone TEXT")

    for stmt in additions:
        conn.execute(stmt)

    conn.commit()
    print(f"Migration 029 complete ({len(additions)} columns added).")


if __name__ == "__main__":
    db_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "cleo.db")
    conn = sqlite3.connect(db_path)
    migrate(conn)
    conn.close()
