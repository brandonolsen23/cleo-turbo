"""
Backfill id_mappings — one-time migration.

Run ONCE before the first full recompile to capture current ID assignments
so they persist across table drops. After running this, the IDRegistry will
read from id_mappings (a system table that is never dropped) instead of the
derived tables.

Usage:
    python -m cleo.migrations.backfill_id_mappings

Safe to run multiple times (uses INSERT OR IGNORE).
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from cleo.database.connection import get_connection
from cleo.database.schema import create_all_tables


def backfill(conn):
    """Populate id_mappings from current derived tables."""

    # Ensure the id_mappings table exists
    create_all_tables(conn)

    print('Backfilling id_mappings from current derived tables...')

    # Properties: arn → PRO_ID
    prop_count = conn.execute(
        "INSERT OR IGNORE INTO id_mappings (entity_type, anchor_key, entity_id) "
        "SELECT 'property', arn, id FROM properties WHERE arn IS NOT NULL AND arn != ''"
    ).rowcount
    print(f'  Properties: {prop_count:,} new mappings')

    # Contacts: fingerprint → CON_ID
    con_count = conn.execute(
        "INSERT OR IGNORE INTO id_mappings (entity_type, anchor_key, entity_id) "
        "SELECT 'contact', name_fingerprint, id FROM contacts "
        "WHERE name_fingerprint IS NOT NULL AND name_fingerprint != ''"
    ).rowcount
    print(f'  Contacts: {con_count:,} new mappings')

    # Groups: normalized_name → GRP_ID
    grp_count = conn.execute(
        "INSERT OR IGNORE INTO id_mappings (entity_type, anchor_key, entity_id) "
        "SELECT 'group', normalized_name, id FROM groups "
        "WHERE normalized_name IS NOT NULL AND normalized_name != ''"
    ).rowcount
    print(f'  Groups: {grp_count:,} new mappings')

    conn.commit()

    # Summary
    totals = conn.execute(
        "SELECT entity_type, COUNT(*) FROM id_mappings GROUP BY entity_type ORDER BY entity_type"
    ).fetchall()
    print()
    print('Total id_mappings:')
    for et, c in totals:
        print(f'  {et}: {c:,}')

    # Verify no conflicts
    print()
    print('Verifying integrity...')

    # Check that group IDs match
    mismatches = conn.execute(
        "SELECT im.anchor_key, im.entity_id, g.id FROM id_mappings im "
        "JOIN groups g ON im.anchor_key = g.normalized_name "
        "WHERE im.entity_type = 'group' AND im.entity_id != g.id"
    ).fetchall()
    if mismatches:
        print(f'  WARNING: {len(mismatches)} group ID mismatches!')
        for m in mismatches[:5]:
            print(f'    {m[0]}: id_mappings={m[1]} vs groups={m[2]}')
    else:
        print('  Groups: OK')

    # Check contacts
    mismatches = conn.execute(
        "SELECT im.anchor_key, im.entity_id, c.id FROM id_mappings im "
        "JOIN contacts c ON im.anchor_key = c.name_fingerprint "
        "WHERE im.entity_type = 'contact' AND im.entity_id != c.id"
    ).fetchall()
    if mismatches:
        print(f'  WARNING: {len(mismatches)} contact ID mismatches!')
    else:
        print('  Contacts: OK')

    # Check properties
    mismatches = conn.execute(
        "SELECT im.anchor_key, im.entity_id, p.id FROM id_mappings im "
        "JOIN properties p ON im.anchor_key = p.arn "
        "WHERE im.entity_type = 'property' AND im.entity_id != p.id"
    ).fetchall()
    if mismatches:
        print(f'  WARNING: {len(mismatches)} property ID mismatches!')
    else:
        print('  Properties: OK')

    print()
    print('Done. The next compiler run will use id_mappings for stable IDs.')


if __name__ == '__main__':
    conn = get_connection()
    backfill(conn)
    conn.close()
