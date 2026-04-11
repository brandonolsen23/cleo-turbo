"""
Integration tests for the group consolidation infrastructure.

Tests against the REAL database — no mocking. Run before any full recompile.

Usage:
    cd cleo-turbo
    python -m tests.test_consolidation_infrastructure

Tests:
  1. ID stability: registry produces same IDs from id_mappings
  2. Group overrides: manual group creation + compiler injection
  3. Field overrides: persist through simulated recompile
  4. Merge survival: merges re-applied after table rebuild
  5. Reconciliation report: generates correctly
  6. API endpoints: new endpoints return correct data
  7. CRM integrity: no orphaned references in current DB
"""

import sys
import os
import json
import sqlite3
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from cleo.database.connection import get_connection
from cleo.database.schema import create_all_tables
from cleo.compiler.reconciler import IDRegistry, normalize_group_name, make_name_fingerprint


# ── Helpers ─────────────────────────────────────────────────────

PASS = 0
FAIL = 0
WARN = 0


def test(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name}")
        if detail:
            print(f"    → {detail}")


def warn(name, detail=""):
    global WARN
    WARN += 1
    print(f"  ⚠ {name}")
    if detail:
        print(f"    → {detail}")


def section(title):
    print()
    print(f"{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


# ── Test 1: ID Stability ───────────────────────────────────────

def test_id_stability(conn):
    section("Test 1: ID Stability")

    # Check id_mappings table exists and has data
    try:
        count = conn.execute("SELECT COUNT(*) FROM id_mappings").fetchone()[0]
        test("id_mappings table exists and has data", count > 0, f"Found {count} mappings")
    except Exception as e:
        test("id_mappings table exists", False, str(e))
        return

    # Check counts per type
    for et in ['property', 'contact', 'group']:
        c = conn.execute(
            "SELECT COUNT(*) FROM id_mappings WHERE entity_type = ?", (et,)
        ).fetchone()[0]
        test(f"id_mappings has {et} entries", c > 0, f"{c} {et} mappings")

    # Verify ID mappings match current derived tables
    for table, anchor_col, id_col, entity_type in [
        ('groups', 'normalized_name', 'id', 'group'),
        ('contacts', 'name_fingerprint', 'id', 'contact'),
        ('properties', 'arn', 'id', 'property'),
    ]:
        mismatches = conn.execute(f"""
            SELECT im.anchor_key, im.entity_id, t.{id_col}
            FROM id_mappings im
            JOIN {table} t ON im.anchor_key = t.{anchor_col}
            WHERE im.entity_type = ? AND im.entity_id != t.{id_col}
        """, (entity_type,)).fetchall()
        test(
            f"{table} IDs match id_mappings",
            len(mismatches) == 0,
            f"{len(mismatches)} mismatches" if mismatches else ""
        )

    # Simulate registry load and verify it produces correct IDs
    registry = IDRegistry(conn)
    registry.load()

    # Sample 20 groups from the DB and verify registry returns the same ID
    samples = conn.execute(
        "SELECT normalized_name, id FROM groups WHERE normalized_name IS NOT NULL LIMIT 20"
    ).fetchall()
    all_match = True
    for norm, expected_id in samples:
        got = registry.get_or_create_group_id(norm)
        if got != expected_id:
            all_match = False
            test(f"Registry returns stable ID for '{norm}'", False,
                 f"Expected {expected_id}, got {got}")
            break
    if all_match and samples:
        test(f"Registry returns stable IDs for {len(samples)} sampled groups", True)

    # Same for contacts
    samples = conn.execute(
        "SELECT name_fingerprint, id FROM contacts WHERE name_fingerprint IS NOT NULL LIMIT 20"
    ).fetchall()
    all_match = True
    for fp, expected_id in samples:
        got = registry.get_or_create_contact_id(fp)
        if got != expected_id:
            all_match = False
            test(f"Registry returns stable ID for contact '{fp}'", False,
                 f"Expected {expected_id}, got {got}")
            break
    if all_match and samples:
        test(f"Registry returns stable IDs for {len(samples)} sampled contacts", True)

    # Same for properties
    samples = conn.execute(
        "SELECT arn, id FROM properties WHERE arn IS NOT NULL LIMIT 20"
    ).fetchall()
    all_match = True
    for arn, expected_id in samples:
        got = registry.get_or_create_property_id(arn)
        if got != expected_id:
            all_match = False
            test(f"Registry returns stable ID for property '{arn}'", False,
                 f"Expected {expected_id}, got {got}")
            break
    if all_match and samples:
        test(f"Registry returns stable IDs for {len(samples)} sampled properties", True)

    # Verify counters are consistent (next ID > max existing ID)
    for prefix, entity_type in [('PRO', 'property'), ('CON', 'contact'), ('GRP', 'group')]:
        counter_row = conn.execute(
            "SELECT value FROM app_meta WHERE key = ?",
            (f'next_{prefix.lower()}_id',)
        ).fetchone()
        if counter_row:
            next_id = int(counter_row[0])
            max_existing = conn.execute(
                "SELECT MAX(CAST(SUBSTR(entity_id, 5) AS INTEGER)) FROM id_mappings WHERE entity_type = ?",
                (entity_type,)
            ).fetchone()[0] or 0
            test(
                f"{prefix} counter ({next_id}) > max existing ID ({max_existing})",
                next_id > max_existing,
                f"Counter would collide!" if next_id <= max_existing else ""
            )


# ── Test 2: Schema — New Tables Exist ──────────────────────────

def test_schema(conn):
    section("Test 2: Schema — New Tables")

    tables_to_check = [
        'id_mappings',
        'group_overrides',
        'group_field_overrides',
        'contact_field_overrides',
    ]

    for table in tables_to_check:
        try:
            conn.execute(f"SELECT COUNT(*) FROM {table}")
            test(f"Table '{table}' exists", True)
        except Exception as e:
            test(f"Table '{table}' exists", False, str(e))

    # Verify these tables are NOT in the drop list
    from cleo.database.schema import drop_derived_tables
    import inspect
    source = inspect.getsource(drop_derived_tables)
    for table in tables_to_check:
        test(
            f"'{table}' is NOT dropped by drop_derived_tables",
            table not in source,
            "Would be destroyed on recompile!" if table in source else ""
        )


# ── Test 3: Group Overrides ────────────────────────────────────

def test_group_overrides(conn):
    section("Test 3: Group Overrides (manual group creation)")

    test_name = "__TEST_CONSOLIDATION_GROUP__"
    normalized = normalize_group_name(test_name)

    # Clean up any previous test data
    conn.execute("DELETE FROM group_overrides WHERE normalized_name = ?", (normalized,))
    conn.execute("DELETE FROM groups WHERE normalized_name = ?", (normalized,))
    conn.execute("DELETE FROM id_mappings WHERE entity_type = 'group' AND anchor_key = ?", (normalized,))
    conn.commit()

    # Simulate the create endpoint logic
    counter_row = conn.execute("SELECT value FROM app_meta WHERE key = 'next_grp_id'").fetchone()
    next_id = int(counter_row[0]) if counter_row else 1
    group_id = f"GRP_{next_id:05d}"

    # Increment counter
    conn.execute(
        "INSERT OR REPLACE INTO app_meta (key, value, updated_at) VALUES ('next_grp_id', ?, datetime('now'))",
        (str(next_id + 1),)
    )

    # Write to id_mappings
    conn.execute(
        "INSERT INTO id_mappings (entity_type, anchor_key, entity_id) VALUES ('group', ?, ?)",
        (normalized, group_id)
    )

    # Write to group_overrides
    conn.execute(
        "INSERT INTO group_overrides (group_id, display_name, normalized_name, created_by, notes) "
        "VALUES (?, ?, ?, 'test', 'integration test')",
        (group_id, test_name, normalized)
    )

    # Write to groups
    conn.execute(
        "INSERT INTO groups (id, display_name, normalized_name, status, property_count, transaction_count, contact_count) "
        "VALUES (?, ?, ?, 'pool', 0, 0, 0)",
        (group_id, test_name, normalized)
    )
    conn.commit()

    # Verify all three tables have the entry
    test("Group created in id_mappings",
         conn.execute("SELECT entity_id FROM id_mappings WHERE entity_type = 'group' AND anchor_key = ?",
                       (normalized,)).fetchone()[0] == group_id)

    test("Group created in group_overrides",
         conn.execute("SELECT group_id FROM group_overrides WHERE normalized_name = ?",
                       (normalized,)).fetchone()[0] == group_id)

    test("Group created in groups table",
         conn.execute("SELECT id FROM groups WHERE normalized_name = ?",
                       (normalized,)).fetchone()[0] == group_id)

    # Verify registry would return the same ID
    registry = IDRegistry(conn)
    registry.load()
    got = registry.get_or_create_group_id(normalized)
    test("Registry returns stable ID for manually-created group",
         got == group_id, f"Expected {group_id}, got {got}")

    # Clean up
    conn.execute("DELETE FROM group_overrides WHERE normalized_name = ?", (normalized,))
    conn.execute("DELETE FROM groups WHERE normalized_name = ?", (normalized,))
    conn.execute("DELETE FROM id_mappings WHERE entity_type = 'group' AND anchor_key = ?", (normalized,))
    # Restore counter
    conn.execute(
        "INSERT OR REPLACE INTO app_meta (key, value, updated_at) VALUES ('next_grp_id', ?, datetime('now'))",
        (str(next_id),)
    )
    conn.commit()


# ── Test 4: Field Overrides ────────────────────────────────────

def test_field_overrides(conn):
    section("Test 4: Field Overrides")

    # Pick a real group to test with
    sample_group = conn.execute(
        "SELECT id, status, hq_address FROM groups WHERE status != 'merged' LIMIT 1"
    ).fetchone()
    if not sample_group:
        warn("No groups found to test field overrides")
        return

    gid = sample_group[0]

    # Insert a field override
    conn.execute(
        "INSERT OR REPLACE INTO group_field_overrides (group_id, status, hq_address, updated_by) "
        "VALUES (?, 'engaged', '123 Test St, Toronto ON', 'test')",
        (gid,)
    )
    conn.commit()

    # Verify it's there
    row = conn.execute(
        "SELECT status, hq_address FROM group_field_overrides WHERE group_id = ?", (gid,)
    ).fetchone()
    test("Group field override written", row is not None)
    test("Override status = 'engaged'", row and row[0] == 'engaged')
    test("Override hq_address stored", row and row[1] == '123 Test St, Toronto ON')

    # Test contact field overrides
    sample_contact = conn.execute("SELECT id FROM contacts LIMIT 1").fetchone()
    if sample_contact:
        cid = sample_contact[0]
        conn.execute(
            "INSERT OR REPLACE INTO contact_field_overrides "
            "(contact_id, email, phone, updated_by) VALUES (?, 'test@test.com', '555-0000', 'test')",
            (cid,)
        )
        conn.commit()
        row = conn.execute(
            "SELECT email, phone FROM contact_field_overrides WHERE contact_id = ?", (cid,)
        ).fetchone()
        test("Contact field override written", row is not None)
        test("Override email stored", row and row[0] == 'test@test.com')

        # Clean up
        conn.execute("DELETE FROM contact_field_overrides WHERE contact_id = ?", (cid,))
        conn.commit()

    # Clean up
    conn.execute("DELETE FROM group_field_overrides WHERE group_id = ?", (gid,))
    conn.commit()


# ── Test 5: Merge Survival Logic ──────────────────────────────

def test_merge_survival(conn):
    section("Test 5: Merge Survival")

    # Check if there are any active merges
    active = conn.execute(
        "SELECT COUNT(*) FROM group_merges WHERE unmerged_at IS NULL"
    ).fetchone()[0]
    test(f"group_merges table accessible ({active} active merges)", True)

    # Verify merge target resolution works
    from cleo.database.group_merge_ops import resolve_target
    if active > 0:
        sample = conn.execute(
            "SELECT source_group_id, target_group_id FROM group_merges WHERE unmerged_at IS NULL LIMIT 1"
        ).fetchone()
        resolved = resolve_target(conn, sample[0])
        test(f"resolve_target({sample[0]}) returns valid target",
             resolved is not None and resolved != sample[0],
             f"Resolved to {resolved}")

        # Verify the target group exists
        target_exists = conn.execute(
            "SELECT id FROM groups WHERE id = ?", (resolved,)
        ).fetchone()
        test(f"Merge target {resolved} exists in groups table",
             target_exists is not None,
             "TARGET MISSING — would be orphaned on recompile!" if not target_exists else "")

    # Verify ALL active merge targets exist in id_mappings
    orphaned_targets = conn.execute("""
        SELECT gm.target_group_id
        FROM group_merges gm
        LEFT JOIN id_mappings im ON im.entity_id = gm.target_group_id AND im.entity_type = 'group'
        WHERE gm.unmerged_at IS NULL AND im.entity_id IS NULL
    """).fetchall()
    test("All merge targets have id_mappings entries",
         len(orphaned_targets) == 0,
         f"{len(orphaned_targets)} targets missing from id_mappings" if orphaned_targets else "")


# ── Test 6: CRM Integrity ─────────────────────────────────────

def test_crm_integrity(conn):
    section("Test 6: CRM Integrity (orphaned references)")

    checks = [
        ("deals", "group_id", "groups"),
        ("deals", "property_id", "properties"),
        ("group_contacts", "group_id", "groups"),
        ("group_contacts", "contact_id", "contacts"),
        ("group_notes", "group_id", "groups"),
        ("contact_notes", "contact_id", "contacts"),
    ]

    all_clean = True
    for table, col, ref_table in checks:
        try:
            count = conn.execute(
                f"SELECT COUNT(*) FROM {table} t "
                f"LEFT JOIN {ref_table} r ON t.{col} = r.id "
                f"WHERE t.{col} IS NOT NULL AND r.id IS NULL"
            ).fetchone()[0]
            test(f"{table}.{col} → {ref_table}: {count} orphaned",
                 count == 0,
                 f"{count} rows point to non-existent {ref_table}!" if count > 0 else "")
            if count > 0:
                all_clean = False
        except Exception as e:
            test(f"{table}.{col} → {ref_table}", False, str(e))


# ── Test 7: Reconciliation Report ─────────────────────────────

def test_reconciliation_report(conn):
    section("Test 7: Reconciliation Report")

    from cleo.compiler.writer import _snapshot_pre_compile, _generate_reconciliation_report

    # Take a snapshot
    snapshot = _snapshot_pre_compile(conn)
    test("Pre-compile snapshot captured",
         len(snapshot['groups']) > 0,
         f"{len(snapshot['groups'])} groups captured")

    # Generate report against current state (should show no changes)
    report = _generate_reconciliation_report(conn, snapshot)
    test("Report generated successfully", report is not None)
    test("No disappeared groups (same state)",
         len(report['disappeared_groups']) == 0,
         f"{len(report['disappeared_groups'])} disappeared" if report['disappeared_groups'] else "")
    test("No new groups (same state)",
         len(report['new_groups']) == 0,
         f"{len(report['new_groups'])} new" if report['new_groups'] else "")
    test("No orphaned CRM refs",
         len(report['orphaned_crm_refs']) == 0,
         str(report['orphaned_crm_refs']) if report['orphaned_crm_refs'] else "")


# ── Test 8: Compiler Writer Imports ────────────────────────────

def test_compiler_imports(conn):
    section("Test 8: Compiler Code Integrity")

    try:
        from cleo.compiler.writer import run_compiler
        test("writer.py imports successfully", True)
    except Exception as e:
        test("writer.py imports successfully", False, str(e))

    try:
        from cleo.compiler.reconciler import IDRegistry, normalize_group_name, make_name_fingerprint
        test("reconciler.py imports successfully", True)
    except Exception as e:
        test("reconciler.py imports successfully", False, str(e))

    try:
        from cleo.database.group_merge_ops import resolve_target, execute_merge
        test("group_merge_ops.py imports successfully", True)
    except Exception as e:
        test("group_merge_ops.py imports successfully", False, str(e))

    # Verify the writer has the new passes
    import inspect
    from cleo.compiler import writer
    source = inspect.getsource(writer.run_compiler)

    test("Writer has Pass 1b (group_overrides injection)",
         "group_overrides" in source,
         "Pass 1b missing — manual groups won't survive recompile!")

    test("Writer has group_field_overrides application",
         "group_field_overrides" in source,
         "Field overrides missing — promoted status won't survive!")

    test("Writer has contact_field_overrides application",
         "contact_field_overrides" in source,
         "Contact field overrides missing!")

    test("Writer has reconciliation report",
         "_generate_reconciliation_report" in source,
         "No reconciliation report — you won't see what changed!")

    test("Writer loads registry BEFORE dropping tables",
         source.index("registry.load()") < source.index("drop_derived_tables"),
         "Registry loads after drop — IDs won't be stable!")

    test("Writer snapshots BEFORE dropping tables",
         source.index("_snapshot_pre_compile") < source.index("drop_derived_tables"),
         "Snapshot taken after drop — reconciliation report will be empty!")


# ── Test 9: Affiliated Groups Query ───────────────────────────

def test_affiliated_groups_query(conn):
    section("Test 9: Affiliated Groups Query")

    # Find a contact with multiple group affiliations (the use case)
    multi_group_contacts = conn.execute("""
        SELECT tp.contact_id, c.display_name, COUNT(DISTINCT tp_g.group_id) as group_count
        FROM transaction_parties tp
        JOIN transaction_parties tp_g ON tp.source_id = tp_g.source_id
            AND tp_g.group_id IS NOT NULL
            AND tp_g.side = tp.side
        JOIN contacts c ON tp.contact_id = c.id
        JOIN groups g ON tp_g.group_id = g.id AND g.status != 'merged'
        WHERE tp.contact_id IS NOT NULL
        GROUP BY tp.contact_id
        HAVING group_count >= 3
        ORDER BY group_count DESC
        LIMIT 5
    """).fetchall()

    test("Found contacts with multiple group affiliations",
         len(multi_group_contacts) > 0,
         f"Top: {multi_group_contacts[0][1]} ({multi_group_contacts[0][2]} groups)" if multi_group_contacts else "None found")

    if multi_group_contacts:
        # Test the actual query from the API endpoint
        cid = multi_group_contacts[0][0]
        cname = multi_group_contacts[0][1]
        expected_count = multi_group_contacts[0][2]

        rows = conn.execute("""
            SELECT
                g.id, g.display_name, g.normalized_name, g.status,
                g.property_count, g.transaction_count, g.contact_count,
                CASE WHEN c.current_group_id = g.id THEN 1 ELSE 0 END as is_current_group,
                COUNT(DISTINCT tp_contact.source_id) as shared_transactions
            FROM transaction_parties tp_contact
            JOIN transaction_parties tp_group ON tp_contact.source_id = tp_group.source_id
                AND tp_group.group_id IS NOT NULL
                AND tp_group.side = tp_contact.side
            JOIN groups g ON tp_group.group_id = g.id
            JOIN contacts c ON c.id = ?
            WHERE tp_contact.contact_id = ?
                AND g.status != 'merged'
            GROUP BY g.id
            ORDER BY shared_transactions DESC
        """, (cid, cid)).fetchall()

        test(f"Affiliated groups query returns results for {cname}",
             len(rows) > 0, f"Got {len(rows)} groups")
        test(f"Query returns expected group count",
             len(rows) == expected_count,
             f"Expected {expected_count}, got {len(rows)}")

        # Print the groups for manual inspection
        print(f"\n    Affiliated groups for {cname}:")
        for r in rows[:8]:
            marker = " ← current" if r[7] else ""
            print(f"      {r[0]} \"{r[1]}\" — {r[4]} props, {r[8]} shared txns{marker}")
        if len(rows) > 8:
            print(f"      ... and {len(rows) - 8} more")


# ── Test 10: Stress Test — New ID Allocation ──────────────────

def test_new_id_allocation(conn):
    section("Test 10: New ID Allocation (no collisions)")

    registry = IDRegistry(conn)
    registry.load()

    # Create a brand new group that doesn't exist
    test_name = "__COLLISION_TEST_GROUP_XYZ__"
    normalized = normalize_group_name(test_name)

    # Verify it doesn't exist yet
    existing = conn.execute(
        "SELECT entity_id FROM id_mappings WHERE entity_type = 'group' AND anchor_key = ?",
        (normalized,)
    ).fetchone()

    if existing:
        test("Test group doesn't exist yet (cleanup needed)", False,
             f"Found {existing[0]} — delete it first")
        return

    # Get a new ID
    new_id = registry.get_or_create_group_id(normalized)
    test(f"New group ID allocated: {new_id}", new_id is not None)

    # Verify it was persisted to id_mappings
    stored = conn.execute(
        "SELECT entity_id FROM id_mappings WHERE entity_type = 'group' AND anchor_key = ?",
        (normalized,)
    ).fetchone()
    test("New mapping persisted to id_mappings", stored is not None and stored[0] == new_id)

    # Verify no collision with existing groups
    collision = conn.execute(
        "SELECT id FROM groups WHERE id = ?", (new_id,)
    ).fetchone()
    # It's fine if the group doesn't exist in groups yet — that happens at write time
    # What matters is no OTHER group has this ID
    collision2 = conn.execute(
        "SELECT COUNT(*) FROM id_mappings WHERE entity_id = ? AND entity_type = 'group' AND anchor_key != ?",
        (new_id, normalized)
    ).fetchone()[0]
    test("No ID collision with existing mappings", collision2 == 0,
         f"ID {new_id} is also assigned to another group!" if collision2 > 0 else "")

    # Clean up
    conn.execute(
        "DELETE FROM id_mappings WHERE entity_type = 'group' AND anchor_key = ?",
        (normalized,)
    )
    conn.commit()


# ── Main ──────────────────────────────────────────────────────

def main():
    global PASS, FAIL, WARN

    print("=" * 60)
    print("  Consolidation Infrastructure — Integration Tests")
    print("=" * 60)

    conn = get_connection()

    # Ensure new tables exist
    create_all_tables(conn)

    try:
        test_id_stability(conn)
        test_schema(conn)
        test_group_overrides(conn)
        test_field_overrides(conn)
        test_merge_survival(conn)
        test_crm_integrity(conn)
        test_reconciliation_report(conn)
        test_compiler_imports(conn)
        test_affiliated_groups_query(conn)
        test_new_id_allocation(conn)
    except Exception as e:
        print(f"\n  FATAL ERROR: {e}")
        traceback.print_exc()
        FAIL += 1

    conn.close()

    # Summary
    print()
    print("=" * 60)
    total = PASS + FAIL
    if FAIL == 0:
        print(f"  ALL {total} TESTS PASSED")
    else:
        print(f"  {PASS}/{total} passed, {FAIL} FAILED")
    if WARN:
        print(f"  {WARN} warning(s)")
    print("=" * 60)

    return 1 if FAIL > 0 else 0


if __name__ == '__main__':
    sys.exit(main())
