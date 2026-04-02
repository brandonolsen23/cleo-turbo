#!/usr/bin/env python3
"""
Cleo Turbo Data-Flow Trace Tests

Picks sample records from clean-data/, traces them through the database,
and verifies field values are preserved through the full pipeline.

Requires: data/cleo.db populated, clean-data/ directory present.
Run from project root: python3 .claude/skills/test/scripts/test_data_flow.py
"""

import json
import sqlite3
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "cleo.db"
RT_DIR = PROJECT_ROOT / "clean-data" / "rt"
GW_DIR = PROJECT_ROOT / "clean-data" / "gw"

passed = 0
failed = 0
warnings = 0


def ok(msg):
    global passed
    passed += 1
    print(f"  ✓ {msg}")


def fail(msg):
    global failed
    failed += 1
    print(f"  ✗ {msg}")


def warn(msg):
    global warnings
    warnings += 1
    print(f"  ⚠ {msg}")


def trace_rt_record(conn, source_file):
    """Trace one RT record from clean-data through the database."""
    with open(source_file) as f:
        record = json.load(f)

    source_id = record.get("id") or source_file.stem
    arn = record.get("site", {}).get("arn", "")

    print(f"\n  Tracing RT record: {source_file.name}")
    print(f"    source_id={source_id}, arn={arn}")

    # Find in transactions table
    row = conn.execute(
        "SELECT * FROM transactions WHERE source_id = ?", (source_id,)
    ).fetchone()

    if not row:
        # Try by source_folder
        folder = source_file.parent.name
        row = conn.execute(
            "SELECT * FROM transactions WHERE source_folder = ?", (folder,)
        ).fetchone()

    if not row:
        warn(f"RT record {source_id} not found in transactions table")
        return

    tx = dict(row)

    # Trace key fields
    # Sale price
    source_price = record.get("sale_price")
    if source_price is not None:
        db_price = tx.get("sale_price")
        if str(source_price) == str(db_price) or source_price == db_price:
            ok(f"sale_price: {source_price} → DB {db_price}")
        else:
            fail(f"sale_price mismatch: source={source_price}, DB={db_price}")

    # PIN
    source_pin = record.get("site", {}).get("pin")
    if source_pin:
        db_pin = tx.get("pin")
        if source_pin == db_pin:
            ok(f"pin: {source_pin} → DB matches")
        else:
            fail(f"pin mismatch: source={source_pin}, DB={db_pin}")

    # Description
    source_desc = record.get("description", {}).get("description")
    if source_desc:
        db_desc = tx.get("description")
        if db_desc and source_desc[:50] in db_desc:
            ok(f"description: preserved ({len(db_desc)} chars)")
        elif db_desc:
            warn(f"description: exists in DB but content differs")
        else:
            fail(f"description: present in source but NULL in DB")

    # Site fields (new in pipeline fix)
    site = record.get("site", {})
    for field in ["pin_display", "arn_display", "parcel_method", "location", "surface_rights_only"]:
        source_val = site.get(field)
        if source_val is not None:
            db_val = tx.get(field)
            if db_val is not None:
                ok(f"site.{field}: present in DB")
            else:
                fail(f"site.{field}: present in source ({source_val}) but NULL in DB")

    # More info URL
    source_url = record.get("description", {}).get("more_info_url")
    if source_url:
        db_url = tx.get("more_info_url")
        if db_url:
            ok(f"more_info_url: present in DB")
        else:
            fail(f"more_info_url: present in source but NULL in DB")

    # Consideration (satellite table)
    source_consideration = record.get("consideration", {})
    if source_consideration:
        cons_rows = conn.execute(
            "SELECT COUNT(*) FROM transaction_consideration WHERE source_id = ?",
            (source_id,)
        ).fetchone()[0]
        if cons_rows > 0:
            ok(f"consideration: {cons_rows} rows in satellite table")
        else:
            warn(f"consideration: data in source but 0 rows in transaction_consideration")

    # Brokers (satellite table)
    source_brokers = record.get("broker", {}).get("brokers", [])
    if source_brokers:
        broker_rows = conn.execute(
            "SELECT COUNT(*) FROM transaction_brokers WHERE source_id = ?",
            (source_id,)
        ).fetchone()[0]
        if broker_rows > 0:
            ok(f"brokers: {broker_rows} rows in satellite table (source has {len(source_brokers)})")
        else:
            warn(f"brokers: {len(source_brokers)} in source but 0 rows in transaction_brokers")

    # Mailing addresses (satellite table)
    seller_addr = record.get("seller", {}).get("address")
    buyer_addr = record.get("buyer", {}).get("address")
    if seller_addr or buyer_addr:
        addr_rows = conn.execute(
            "SELECT COUNT(*) FROM transaction_mailing_addresses WHERE source_id = ?",
            (source_id,)
        ).fetchone()[0]
        expected = (1 if seller_addr else 0) + (1 if buyer_addr else 0)
        if addr_rows > 0:
            ok(f"mailing_addresses: {addr_rows} rows (expected ~{expected})")
        else:
            warn(f"mailing_addresses: address data in source but 0 rows in satellite table")


def trace_gw_record(conn, source_file):
    """Trace one GW record from clean-data through the database."""
    with open(source_file) as f:
        record = json.load(f)

    arn = record.get("arn", "") or source_file.stem

    print(f"\n  Tracing GW record: {source_file.name}")
    print(f"    arn={arn}")

    # Find in gw_assessments
    row = conn.execute(
        "SELECT * FROM gw_assessments WHERE arn = ?", (arn,)
    ).fetchone()

    if not row:
        warn(f"GW record {arn} not found in gw_assessments table")
        return

    gw = dict(row)

    # Assessment value
    source_val = record.get("assessment", {}).get("assessed_value")
    if source_val is not None:
        db_val = gw.get("assessed_value")
        if db_val is not None:
            ok(f"assessed_value: source={source_val}, DB={db_val}")
        else:
            fail(f"assessed_value: present in source but NULL in DB")

    # Registry fields (new in pipeline fix)
    registry = record.get("registry", {})
    for field in ["land_registry_status", "registration_type", "lro"]:
        source_val = registry.get(field)
        if source_val is not None:
            db_val = gw.get(field)
            if db_val is not None:
                ok(f"registry.{field}: present in DB")
            else:
                fail(f"registry.{field}: present in source ({source_val}) but NULL in DB")

    # Quality flags (new in pipeline fix)
    quality = record.get("quality", {})
    for field in ["has_mpac_data", "is_active", "address_parsed", "parcel_resolved"]:
        source_val = quality.get(field)
        if source_val is not None:
            db_val = gw.get(field)
            if db_val is not None:
                ok(f"quality.{field}: present in DB")
            else:
                fail(f"quality.{field}: present in source but NULL in DB")

    # Sales history (satellite table)
    source_history = record.get("sales_history", [])
    if source_history:
        hist_rows = conn.execute(
            "SELECT COUNT(*) FROM gw_sales_history WHERE arn = ?", (arn,)
        ).fetchone()[0]
        if hist_rows > 0:
            ok(f"sales_history: {hist_rows} rows (source has {len(source_history)})")
            if hist_rows != len(source_history):
                warn(f"sales_history count mismatch: source={len(source_history)}, DB={hist_rows}")
        else:
            fail(f"sales_history: {len(source_history)} in source but 0 in gw_sales_history — DATA LOSS")


def main():
    global passed, failed, warnings

    print("=" * 60)
    print("Cleo Turbo Data-Flow Trace Tests")
    print("=" * 60)

    if not DB_PATH.exists():
        fail("Database not found at data/cleo.db")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # ================================================================
    # RT Records
    # ================================================================
    print("\nTEST GROUP: RT Data Flow")

    if RT_DIR.exists():
        rt_files = sorted(RT_DIR.glob("**/*.json"))[:3]  # Sample 3 records
        if rt_files:
            for f in rt_files:
                trace_rt_record(conn, f)
        else:
            warn("No JSON files in clean-data/rt/")
    else:
        warn("clean-data/rt/ directory not found")

    # ================================================================
    # GW Records
    # ================================================================
    print("\nTEST GROUP: GW Data Flow")

    if GW_DIR.exists():
        gw_files = sorted(GW_DIR.glob("**/*.json"))[:3]  # Sample 3 records
        if gw_files:
            for f in gw_files:
                trace_gw_record(conn, f)
        else:
            warn("No JSON files in clean-data/gw/")
    else:
        warn("clean-data/gw/ directory not found")

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
