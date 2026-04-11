"""
Migration 001: Asset Classes & Contact Type

Adds:
  - asset_classes reference table (seeded with canonical taxonomy)
  - asset_class + asset_subclass columns on properties
  - contact_type column on contacts
  - Populates asset_class on all existing properties from primary_property_type mapping

Safe to run multiple times (all operations are idempotent).
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from cleo.database.connection import get_connection
from cleo.database.asset_classes import seed_asset_classes, populate_asset_classes


def run():
    conn = get_connection()

    print("Migration 001: Asset Classes & Contact Type")
    print()

    # ── 1. Create asset_classes table ──
    print("Creating asset_classes table...")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS asset_classes (
            id              TEXT PRIMARY KEY,
            label           TEXT NOT NULL,
            parent_id       TEXT,
            sort_order      INTEGER DEFAULT 0,
            FOREIGN KEY (parent_id) REFERENCES asset_classes(id)
        )
    """)
    conn.commit()

    # ── 2. Seed asset class data ──
    print("Seeding asset class taxonomy...")
    seed_asset_classes(conn)
    count = conn.execute("SELECT COUNT(*) FROM asset_classes").fetchone()[0]
    print(f"  Asset classes: {count}")

    # ── 3. Add asset_class and asset_subclass to properties ──
    print("Adding asset_class columns to properties...")
    existing = [row[1] for row in conn.execute("PRAGMA table_info(properties)").fetchall()]

    if "asset_class" not in existing:
        conn.execute("ALTER TABLE properties ADD COLUMN asset_class TEXT")
        print("  Added asset_class column")
    else:
        print("  asset_class column already exists")

    if "asset_subclass" not in existing:
        conn.execute("ALTER TABLE properties ADD COLUMN asset_subclass TEXT")
        print("  Added asset_subclass column")
    else:
        print("  asset_subclass column already exists")

    # Create indexes
    conn.execute("CREATE INDEX IF NOT EXISTS idx_properties_asset_class ON properties(asset_class)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_properties_asset_subclass ON properties(asset_subclass)")
    conn.commit()

    # ── 4. Populate asset_class from primary_property_type mapping ──
    print("Populating asset_class from primary_property_type...")
    updated = populate_asset_classes(conn)
    print(f"  Updated {updated:,} properties")

    # Show distribution
    rows = conn.execute(
        "SELECT asset_class, COUNT(*) as cnt FROM properties "
        "WHERE asset_class IS NOT NULL GROUP BY asset_class ORDER BY cnt DESC"
    ).fetchall()
    for row in rows:
        print(f"    {row[0]}: {row[1]:,}")

    null_count = conn.execute(
        "SELECT COUNT(*) FROM properties WHERE asset_class IS NULL"
    ).fetchone()[0]
    print(f"    (unmapped): {null_count:,}")

    # ── 5. Add contact_type to contacts ──
    print("Adding contact_type column to contacts...")
    existing = [row[1] for row in conn.execute("PRAGMA table_info(contacts)").fetchall()]

    if "contact_type" not in existing:
        conn.execute("ALTER TABLE contacts ADD COLUMN contact_type TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_contacts_contact_type ON contacts(contact_type)")
        conn.commit()
        print("  Added contact_type column")
    else:
        print("  contact_type column already exists")

    print()
    print("Migration 001 complete.")


if __name__ == "__main__":
    run()
