#!/usr/bin/env python3
"""
Cleo Turbo Stack Integrity Verifier

Checks that schema, compiler, API routes, TypeScript types, and docs are all in sync.
Run from project root: python3 .claude/skills/verify/scripts/verify.py
"""

import re
import sys
import json
import os
from pathlib import Path

# Resolve project root (script is at .claude/skills/verify/scripts/verify.py)
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent.parent

SCHEMA_PATH = PROJECT_ROOT / "cleo" / "database" / "schema.py"
WRITER_PATH = PROJECT_ROOT / "cleo" / "compiler" / "writer.py"
CLAUDE_MD_PATH = PROJECT_ROOT / "CLAUDE.md"
API_ROUTE_SKILL = PROJECT_ROOT / ".claude" / "skills" / "api-route" / "SKILL.md"
TYPES_PATH = PROJECT_ROOT / "frontend" / "src" / "types" / "index.ts"
ROUTES_DIR = PROJECT_ROOT / "cleo" / "web" / "routes"

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


def read_file(path):
    try:
        return path.read_text()
    except FileNotFoundError:
        return None


def extract_create_tables(schema_text):
    """Extract table names from CREATE TABLE statements in DERIVED_TABLES."""
    tables = re.findall(r'CREATE\s+(?:VIRTUAL\s+)?TABLE\s+IF\s+NOT\s+EXISTS\s+(\w+)', schema_text)
    return tables


def extract_drop_tables(schema_text):
    """Extract table names from drop_derived_tables()."""
    drop_section = re.search(r'def drop_derived_tables.*?conn\.commit\(\)', schema_text, re.DOTALL)
    if not drop_section:
        return []
    return re.findall(r'DROP\s+TABLE\s+IF\s+EXISTS\s+(\w+)', drop_section.group())


def extract_derived_section(schema_text):
    """Extract table names from DERIVED_TABLES and DERIVED_INDEXES strings (not FTS, not CRM)."""
    tables = []
    for var_name in ['DERIVED_TABLES', 'DERIVED_INDEXES']:
        match = re.search(rf'{var_name}\s*=\s*"""(.*?)"""', schema_text, re.DOTALL)
        if match:
            found = re.findall(r'CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+(\w+)', match.group(1))
            tables.extend(found)
    return tables


def extract_fts_tables(schema_text):
    """Extract FTS virtual table definitions."""
    fts_match = re.search(r'FTS_TABLES\s*=\s*"""(.*?)"""', schema_text, re.DOTALL)
    if not fts_match:
        return {}
    fts = {}
    for m in re.finditer(
        r"CREATE\s+VIRTUAL\s+TABLE\s+IF\s+NOT\s+EXISTS\s+(\w+)\s+USING\s+fts5\(\s*(.*?)\s*\)",
        fts_match.group(1), re.DOTALL
    ):
        name = m.group(1)
        body = m.group(2)
        cols = []
        for part in body.split(","):
            part = part.strip()
            if part.startswith("content=") or part.startswith("content_rowid=") or part.startswith("tokenize="):
                continue
            if "=" in part:
                continue
            cols.append(part.strip())
        content_match = re.search(r"content='(\w+)'", body)
        content_table = content_match.group(1) if content_match else None
        fts[name] = {"columns": cols, "content_table": content_table}
    return fts


def extract_table_columns(schema_text, table_name):
    """Extract column names from a CREATE TABLE statement (searches all SQL strings)."""
    pattern = rf'CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+{table_name}\s*\((.*?)\);'
    match = re.search(pattern, schema_text, re.DOTALL)
    # Also check DERIVED_INDEXES which may contain additional table definitions
    if not match:
        for var_name in ['DERIVED_TABLES', 'DERIVED_INDEXES', 'CRM_TABLES', 'SYSTEM_TABLES', 'FTS_TABLES']:
            section_match = re.search(rf'{var_name}\s*=\s*"""(.*?)"""', schema_text, re.DOTALL)
            if section_match:
                match = re.search(pattern, section_match.group(1), re.DOTALL)
                if match:
                    break
    if not match:
        return []
    body = match.group(1)
    cols = []
    for line in body.split("\n"):
        line = line.strip().rstrip(",")
        if not line or line.startswith("--") or line.startswith("PRIMARY") or line.startswith("UNIQUE") or line.startswith("FOREIGN"):
            continue
        # First word is column name
        parts = line.split()
        if parts and not parts[0].upper() in ("PRIMARY", "UNIQUE", "FOREIGN", "CHECK", "CONSTRAINT"):
            cols.append(parts[0])
    return cols


def extract_insert_statements(writer_text):
    """Extract INSERT statements with their table, columns, and placeholder counts."""
    inserts = []
    for m in re.finditer(
        r'INSERT\s+(?:OR\s+\w+\s+)?INTO\s+(\w+)\s*\(([^)]+)\)\s*.*?VALUES\s*\(([^)]+)\)',
        writer_text, re.DOTALL
    ):
        table = m.group(1)
        # Clean column names: strip whitespace, quotes, newlines
        # Python source has multi-line strings like: "col1, col2, "\n"col3, col4"
        # So we need to remove the Python string delimiters too
        raw_cols = m.group(2).replace('\n', ' ').replace('"', ' ').replace("'", ' ')
        cols = [c.strip() for c in raw_cols.split(',')]
        cols = [c for c in cols if c and not c.startswith('--')]  # Remove empties and comments

        # Count value expressions (both ? placeholders and literal values like 'pool')
        values_str = m.group(3).replace('\n', ' ')
        # Split on commas that aren't inside quotes
        value_count = 0
        depth = 0
        in_quote = False
        for char in values_str:
            if char == "'" and depth == 0:
                in_quote = not in_quote
            elif char == '(' and not in_quote:
                depth += 1
            elif char == ')' and not in_quote:
                depth -= 1
            elif char == ',' and depth == 0 and not in_quote:
                value_count += 1
        value_count += 1  # N commas = N+1 values

        inserts.append({"table": table, "columns": cols, "placeholders": value_count})
    return inserts


def extract_doc_tables(text, label="Derived tables"):
    """Extract table names from a doc file's derived tables list."""
    # Look for the line after the label
    lines = text.split("\n")
    tables = []
    capture = False
    for line in lines:
        if label.lower() in line.lower() and ("rebuilt" in line.lower() or "compiler" in line.lower()):
            capture = True
            # Check if tables are on same line
            after = line.split(":")[-1] if ":" in line else ""
            found = re.findall(r'\b([a-z_]+)\b', after)
            # Filter to likely table names
            for t in found:
                if "_" in t or t in ("properties", "transactions", "contacts", "groups", "pois"):
                    tables.append(t)
            continue
        if capture:
            if line.strip() == "" or line.startswith("**") or line.startswith("#"):
                if tables:
                    break
            found = re.findall(r'\b([a-z_]+)\b', line)
            for t in found:
                if "_" in t or t in ("properties", "transactions", "contacts", "groups", "pois"):
                    tables.append(t)
    return tables


def extract_ts_interfaces(types_text):
    """Extract interface names and their fields from TypeScript."""
    interfaces = {}
    for m in re.finditer(r'export\s+interface\s+(\w+)\s*(?:extends\s+\w+\s*)?\{([^}]+)\}', types_text, re.DOTALL):
        name = m.group(1)
        body = m.group(2)
        fields = []
        for line in body.split("\n"):
            line = line.strip()
            field_match = re.match(r'(\w+)\??:', line)
            if field_match:
                fields.append(field_match.group(1))
        interfaces[name] = fields
    return interfaces


def main():
    global passed, failed, warnings

    print("=" * 60)
    print("Cleo Turbo Stack Integrity Verifier")
    print("=" * 60)
    print()

    schema_text = read_file(SCHEMA_PATH)
    writer_text = read_file(WRITER_PATH)
    claude_md = read_file(CLAUDE_MD_PATH)
    skill_text = read_file(API_ROUTE_SKILL)
    types_text = read_file(TYPES_PATH)

    if not schema_text:
        fail("Cannot read schema.py")
        return
    if not writer_text:
        fail("Cannot read writer.py")
        return

    # ================================================================
    # CHECK 1: Derived Table Lists Match
    # ================================================================
    print("CHECK 1: Derived Table Lists Match")

    derived_tables = set(extract_derived_section(schema_text))
    fts_tables_in_schema = set(extract_fts_tables(schema_text).keys())
    all_schema_tables = derived_tables | fts_tables_in_schema

    drop_tables = set(extract_drop_tables(schema_text))

    # Check CREATE vs DROP
    missing_from_drop = derived_tables - drop_tables
    missing_from_create = drop_tables - all_schema_tables
    fts_missing_from_drop = fts_tables_in_schema - drop_tables

    if not missing_from_drop and not fts_missing_from_drop:
        ok(f"All {len(derived_tables)} derived + {len(fts_tables_in_schema)} FTS tables are in drop_derived_tables()")
    else:
        if missing_from_drop:
            fail(f"Tables in CREATE but NOT in DROP: {missing_from_drop}")
        if fts_missing_from_drop:
            fail(f"FTS tables NOT in DROP: {fts_missing_from_drop}")

    if missing_from_create:
        warn(f"Tables in DROP but NOT in CREATE: {missing_from_create}")

    # Check CLAUDE.md
    if claude_md:
        doc_tables = set(extract_doc_tables(claude_md))
        missing_from_docs = derived_tables - doc_tables
        extra_in_docs = doc_tables - derived_tables
        if not missing_from_docs:
            ok("CLAUDE.md lists all derived tables")
        else:
            fail(f"Tables missing from CLAUDE.md: {missing_from_docs}")
        if extra_in_docs:
            warn(f"Extra tables in CLAUDE.md not in schema: {extra_in_docs}")
    else:
        warn("Cannot read CLAUDE.md")

    # Check api-route skill
    if skill_text:
        skill_tables = set(extract_doc_tables(skill_text))
        missing_from_skill = derived_tables - skill_tables
        if not missing_from_skill:
            ok("api-route skill lists all derived tables")
        else:
            fail(f"Tables missing from api-route skill: {missing_from_skill}")
    else:
        warn("Cannot read api-route skill")

    print()

    # ================================================================
    # CHECK 2: SQL INSERT Parameter Counts
    # ================================================================
    print("CHECK 2: SQL INSERT Parameter Counts")

    inserts = extract_insert_statements(writer_text)
    for ins in inserts:
        if ins["columns"] and ins["placeholders"]:
            if len(ins["columns"]) == ins["placeholders"]:
                ok(f"{ins['table']}: {len(ins['columns'])} cols = {ins['placeholders']} params")
            else:
                fail(f"{ins['table']}: {len(ins['columns'])} cols ≠ {ins['placeholders']} params — MISMATCH")

    # Check columns exist in schema
    for ins in inserts:
        schema_cols = set(extract_table_columns(schema_text, ins["table"]))
        if not schema_cols:
            continue  # Table might be defined elsewhere
        for col in ins["columns"]:
            if col not in schema_cols:
                fail(f"{ins['table']}.{col} in INSERT but not in CREATE TABLE")

    print()

    # ================================================================
    # CHECK 3: FTS Column Validity
    # ================================================================
    print("CHECK 3: FTS Column Validity")

    fts_defs = extract_fts_tables(schema_text)
    for fts_name, fts_info in fts_defs.items():
        content_table = fts_info["content_table"]
        if not content_table:
            warn(f"{fts_name}: no content table specified")
            continue
        table_cols = set(extract_table_columns(schema_text, content_table))
        if not table_cols:
            warn(f"{fts_name}: cannot find content table '{content_table}'")
            continue
        bad_cols = [c for c in fts_info["columns"] if c not in table_cols]
        if not bad_cols:
            ok(f"{fts_name}: all columns valid in '{content_table}'")
        else:
            fail(f"{fts_name}: columns {bad_cols} not found in '{content_table}' (has: {sorted(table_cols)})")

    print()

    # ================================================================
    # CHECK 4: TypeScript Compilation
    # ================================================================
    print("CHECK 4: TypeScript Compilation")

    frontend_dir = PROJECT_ROOT / "frontend"
    if (frontend_dir / "tsconfig.json").exists():
        result = os.system(f"cd {frontend_dir} && npx tsc --noEmit > /dev/null 2>&1")
        if result == 0:
            ok("TypeScript compiles with no errors")
        else:
            fail("TypeScript compilation failed — run 'cd frontend && npx tsc --noEmit' for details")
    else:
        warn("No tsconfig.json found, skipping TypeScript check")

    print()

    # ================================================================
    # CHECK 5: Clean-Data Field Coverage (sample check)
    # ================================================================
    print("CHECK 5: Clean-Data Field Coverage (sample)")

    rt_dir = PROJECT_ROOT / "clean-data" / "rt"
    gw_dir = PROJECT_ROOT / "clean-data" / "gw"

    if rt_dir.exists():
        sample_files = sorted(rt_dir.iterdir())[:1]
        if sample_files:
            with open(sample_files[0]) as f:
                sample = json.load(f)

            # Check key nested structures have corresponding tables
            has_mailing = "address" in sample.get("seller", {})
            has_metadata = any(sample.get("seller", {}).get(k) is not None for k in ["trade_name", "care_of", "law_firms", "companies"])
            has_consideration = bool(sample.get("consideration", {}))
            has_broker = bool(sample.get("broker", {}).get("brokers"))
            has_description_url = "more_info_url" in sample.get("description", {})

            if "transaction_mailing_addresses" in derived_tables:
                ok("RT mailing addresses → transaction_mailing_addresses table exists")
            elif has_mailing:
                fail("RT has seller/buyer addresses but no transaction_mailing_addresses table")

            if "transaction_party_metadata" in derived_tables:
                ok("RT party metadata → transaction_party_metadata table exists")
            elif has_metadata:
                fail("RT has trade_name/care_of/law_firms but no transaction_party_metadata table")

            if "transaction_consideration" in derived_tables:
                ok("RT consideration → transaction_consideration table exists")
            elif has_consideration:
                fail("RT has consideration data but no transaction_consideration table")

            if "transaction_brokers" in derived_tables:
                ok("RT broker data → transaction_brokers table exists")
            elif has_broker:
                fail("RT has broker data but no transaction_brokers table")

            # Check site fields on transactions table
            tx_cols = set(extract_table_columns(schema_text, "transactions"))
            for field in ["pin_display", "arn_display", "parcel_method", "location", "surface_rights_only", "more_info_url"]:
                if field in tx_cols:
                    ok(f"RT site field '{field}' → transactions.{field}")
                else:
                    fail(f"RT site field '{field}' has no column in transactions table")
    else:
        warn("No clean-data/rt/ directory found")

    if gw_dir.exists():
        sample_files = sorted(gw_dir.iterdir())[:1]
        if sample_files:
            with open(sample_files[0]) as f:
                gw_sample = json.load(f)

            if gw_sample.get("sales_history"):
                if "gw_sales_history" in derived_tables:
                    ok("GW sales_history → gw_sales_history table exists")
                else:
                    fail("GW has sales_history but no gw_sales_history table — DATA LOSS")

            registry = gw_sample.get("registry", {})
            gw_cols = set(extract_table_columns(schema_text, "gw_assessments"))
            for field in ["land_registry_status", "registration_type", "lro"]:
                if field in gw_cols:
                    ok(f"GW registry.{field} → gw_assessments.{field}")
                else:
                    fail(f"GW registry field '{field}' has no column in gw_assessments")

            quality = gw_sample.get("quality", {})
            for field in ["has_mpac_data", "is_active", "address_parsed", "parcel_resolved"]:
                if field in gw_cols:
                    ok(f"GW quality.{field} → gw_assessments.{field}")
                else:
                    fail(f"GW quality flag '{field}' has no column in gw_assessments")
    else:
        warn("No clean-data/gw/ directory found")

    print()

    # ================================================================
    # SUMMARY
    # ================================================================
    print("=" * 60)
    total = passed + failed + warnings
    print(f"Results: {passed} passed, {failed} failed, {warnings} warnings")
    if failed == 0:
        print("✓ All checks passed!")
    else:
        print(f"✗ {failed} issue(s) need fixing before commit")
    print("=" * 60)

    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
