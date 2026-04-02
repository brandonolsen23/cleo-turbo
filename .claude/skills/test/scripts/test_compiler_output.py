#!/usr/bin/env python3
"""
Cleo Turbo Compiler Output Tests

Verifies that the compiler populated all derived tables correctly:
- Table existence and row counts
- Referential integrity (no orphan satellite records)
- Stable ID format compliance
- FTS table sync with content tables

Requires: data/cleo.db to exist and be populated.
Run from project root: python3 .claude/skills/test/scripts/test_compiler_output.py
"""

import sqlite3
import sys
import re
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "cleo.db"

passed = 0
failed = 0
warnings = 0


def ok(msg):
    global passed
    passed += 1
    print(f"  ✓ {msg}")


def fail(msg, expected=None, got=None):
    global failed
    failed += 1
    print(f"  ✗ {msg}")
    if expected is not None:
        print(f"    → Expected: {expected}, Got: {got}")


def warn(msg):
    global warnings
    warnings += 1
    print(f"  ⚠ {msg}")


def main():
    global passed, failed, warnings

    print("=" * 60)
    print("Cleo Turbo Compiler Output Tests")
    print("=" * 60)
    print()

    if not DB_PATH.exists():
        fail("Database not found at data/cleo.db")
        print("\nRun the compiler first: python -m cleo.compiler")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # ================================================================
    # TEST GROUP 1: Table Existence & Row Counts
    # ================================================================
    print("TEST GROUP: Table Existence & Row Counts")

    derived_tables = [
        "properties", "transactions", "contacts", "groups", "group_names",
        "transaction_parties", "transaction_mailing_addresses",
        "transaction_party_metadata", "transaction_consideration",
        "transaction_brokers", "transaction_broker_agents",
        "pois", "gw_assessments", "gw_sales_history",
    ]

    table_counts = {}
    for table in derived_tables:
        try:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            table_counts[table] = count
            if count > 0:
                ok(f"{table}: {count:,} rows")
            else:
                warn(f"{table}: 0 rows (may be OK if no source data)")
        except sqlite3.OperationalError:
            fail(f"{table}: TABLE DOES NOT EXIST")
            table_counts[table] = -1

    print()

    # ================================================================
    # TEST GROUP 2: Referential Integrity
    # ================================================================
    print("TEST GROUP: Referential Integrity")

    # Satellite tables that reference transactions via source_id
    satellite_checks = [
        ("transaction_mailing_addresses", "source_id", "transactions", "source_id"),
        ("transaction_party_metadata", "source_id", "transactions", "source_id"),
        ("transaction_consideration", "source_id", "transactions", "source_id"),
        ("transaction_brokers", "source_id", "transactions", "source_id"),
    ]

    for child_table, child_col, parent_table, parent_col in satellite_checks:
        if table_counts.get(child_table, -1) < 0 or table_counts.get(parent_table, -1) < 0:
            warn(f"Skipping {child_table} → {parent_table} (table missing)")
            continue
        if table_counts.get(child_table, 0) == 0:
            warn(f"Skipping {child_table} → {parent_table} (no rows)")
            continue

        orphans = conn.execute(
            f"SELECT COUNT(*) FROM {child_table} "
            f"WHERE {child_col} NOT IN (SELECT {parent_col} FROM {parent_table})"
        ).fetchone()[0]

        if orphans == 0:
            ok(f"{child_table}.{child_col} → {parent_table}.{parent_col}: no orphans")
        else:
            fail(f"{child_table}: {orphans} orphan rows (reference non-existent {parent_table})")

    # Broker agents reference brokers
    if table_counts.get("transaction_broker_agents", 0) > 0 and table_counts.get("transaction_brokers", 0) > 0:
        orphans = conn.execute(
            "SELECT COUNT(*) FROM transaction_broker_agents "
            "WHERE source_id NOT IN (SELECT source_id FROM transaction_brokers)"
        ).fetchone()[0]
        if orphans == 0:
            ok("transaction_broker_agents → transaction_brokers: no orphans")
        else:
            # Agents might legitimately reference source_ids not broker source_ids
            warn(f"transaction_broker_agents: {orphans} rows with source_id not in transaction_brokers")

    # GW sales history references gw_assessments
    if table_counts.get("gw_sales_history", 0) > 0 and table_counts.get("gw_assessments", 0) > 0:
        orphans = conn.execute(
            "SELECT COUNT(*) FROM gw_sales_history "
            "WHERE arn NOT IN (SELECT arn FROM gw_assessments)"
        ).fetchone()[0]
        if orphans == 0:
            ok("gw_sales_history.arn → gw_assessments.arn: no orphans")
        else:
            fail(f"gw_sales_history: {orphans} orphan rows (ARN not in gw_assessments)")

    # Properties should link to valid groups
    if table_counts.get("properties", 0) > 0 and table_counts.get("groups", 0) > 0:
        orphans = conn.execute(
            "SELECT COUNT(*) FROM properties "
            "WHERE current_owner_group_id IS NOT NULL "
            "AND current_owner_group_id NOT IN (SELECT id FROM groups)"
        ).fetchone()[0]
        if orphans == 0:
            ok("properties.current_owner_group_id → groups.id: no orphans")
        else:
            fail(f"properties: {orphans} rows with invalid current_owner_group_id")

    print()

    # ================================================================
    # TEST GROUP 3: Stable ID Formats
    # ================================================================
    print("TEST GROUP: Stable ID Formats")

    id_checks = [
        ("properties", "PRO_"),
        ("contacts", "CON_"),
        ("groups", "GRP_"),
    ]

    for table, prefix in id_checks:
        if table_counts.get(table, 0) <= 0:
            warn(f"Skipping {table} ID check (no rows)")
            continue

        bad = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE id NOT LIKE '{prefix}%'"
        ).fetchone()[0]
        total = table_counts[table]

        if bad == 0:
            ok(f"{table}: all {total:,} IDs start with '{prefix}'")
        else:
            fail(f"{table}: {bad} IDs don't start with '{prefix}'", f"0 bad IDs", f"{bad} bad IDs")

    print()

    # ================================================================
    # TEST GROUP 4: FTS Table Sync
    # ================================================================
    print("TEST GROUP: FTS Table Sync")

    fts_pairs = [
        ("properties", "properties_fts"),
        ("contacts", "contacts_fts"),
        ("groups", "groups_fts"),
        ("transactions", "transactions_fts"),
    ]

    for content_table, fts_table in fts_pairs:
        try:
            content_count = conn.execute(f"SELECT COUNT(*) FROM {content_table}").fetchone()[0]
            fts_count = conn.execute(f"SELECT COUNT(*) FROM {fts_table}").fetchone()[0]

            if content_count == fts_count:
                ok(f"{fts_table}: {fts_count:,} rows = {content_table} ({content_count:,})")
            elif fts_count == 0 and content_count > 0:
                fail(f"{fts_table}: 0 rows but {content_table} has {content_count:,} — FTS not rebuilt?")
            else:
                warn(f"{fts_table}: {fts_count:,} rows vs {content_table}: {content_count:,} (mismatch)")
        except sqlite3.OperationalError as e:
            if "no such table" in str(e):
                fail(f"{fts_table}: TABLE DOES NOT EXIST")
            else:
                warn(f"{fts_table}: error — {e}")

    print()

    # ================================================================
    # TEST GROUP 5: Data Sanity
    # ================================================================
    print("TEST GROUP: Data Sanity")

    # Properties should have ARNs
    if table_counts.get("properties", 0) > 0:
        no_arn = conn.execute("SELECT COUNT(*) FROM properties WHERE arn IS NULL OR arn = ''").fetchone()[0]
        total = table_counts["properties"]
        if no_arn == 0:
            ok(f"All {total:,} properties have ARNs")
        else:
            fail(f"{no_arn} properties missing ARN out of {total:,}")

    # Transactions should have sale dates
    if table_counts.get("transactions", 0) > 0:
        no_date = conn.execute("SELECT COUNT(*) FROM transactions WHERE sale_date IS NULL OR sale_date = ''").fetchone()[0]
        total = table_counts["transactions"]
        pct = (no_date / total * 100) if total > 0 else 0
        if pct < 5:
            ok(f"Transactions: {total - no_date:,}/{total:,} have sale dates ({100-pct:.1f}%)")
        else:
            warn(f"Transactions: {no_date:,}/{total:,} missing sale dates ({pct:.1f}%)")

    # GW assessments should have ARNs
    if table_counts.get("gw_assessments", 0) > 0:
        no_arn = conn.execute("SELECT COUNT(*) FROM gw_assessments WHERE arn IS NULL OR arn = ''").fetchone()[0]
        total = table_counts["gw_assessments"]
        if no_arn == 0:
            ok(f"All {total:,} GW assessments have ARNs")
        else:
            fail(f"{no_arn} GW assessments missing ARN out of {total:,}")

    print()

    # ================================================================
    # SUMMARY
    # ================================================================
    conn.close()

    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed, {warnings} warnings")
    if failed == 0:
        print("✓ All checks passed!")
    else:
        print(f"✗ {failed} issue(s) need fixing")
    print("=" * 60)

    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
