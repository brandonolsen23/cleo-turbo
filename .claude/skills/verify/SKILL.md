---
name: verify
description: |
  Post-change validation that checks the entire Cleo Turbo stack is in sync. Run this after ANY code change that touches schema, compiler, API routes, TypeScript types, or documentation. Also use proactively before committing — it catches the silent breakage that has historically caused data loss (76+ dropped fields were once missed because nobody verified the chain). Trigger on: "verify", "check everything", "is everything in sync", "did I break anything", "pre-commit check", or after completing any feature work. When in doubt, run this skill — it's cheap and fast and catches expensive mistakes.
disable-model-invocation: true
---

# Verify — Cleo Turbo Stack Integrity Check

This skill validates that every layer of the Cleo Turbo stack is consistent with every other layer. The system has five layers that must stay in sync, and a change in one that isn't reflected in the others causes silent data loss or runtime errors.

The layers, in order:
1. **Schema** (`cleo/database/schema.py`) — table definitions, columns, indexes
2. **Compiler** (`cleo/compiler/writer.py`) — reads clean-data, writes to SQLite
3. **API** (`cleo/web/routes/*.py`) — serves data to the frontend
4. **Types** (`frontend/src/types/index.ts`) — TypeScript interfaces for API responses
5. **Docs** (`CLAUDE.md`, `docs/definitions.md`, `.claude/skills/api-route/SKILL.md`) — reference material

## How to run this check

Run the verification script, then review its output:

```bash
python3 .claude/skills/verify/scripts/verify.py
```

The script checks everything it can programmatically. After it runs, review its output and fix anything it flags. Some checks require manual judgment — the script will tell you which.

If the script doesn't exist yet or fails, perform the checks manually using the sections below.

## Check 1: Derived Table Lists Match

The list of derived tables appears in four places. They must be identical.

1. `cleo/database/schema.py` — the `DERIVED_TABLES` string (CREATE TABLE statements)
2. `cleo/database/schema.py` — the `drop_derived_tables()` function (DROP statements)
3. `CLAUDE.md` — the "Derived tables" bullet under "Database: Derived vs CRM Tables"
4. `.claude/skills/api-route/SKILL.md` — the derived tables list

Extract the table names from each location and diff them. Every table that exists in CREATE must exist in DROP, and both doc files must list all of them. The DROP order matters — tables with foreign keys to other derived tables must be dropped first.

## Check 2: SQL INSERT Parameter Counts

Every INSERT statement in `writer.py` must have the same number of columns as `?` placeholders. This is the most common source of "operand mismatch" runtime errors.

For each INSERT statement:
- Count the column names between the parentheses after the table name
- Count the `?` placeholders in the VALUES clause
- They must be equal

Also verify that the column names in the INSERT actually exist in the corresponding CREATE TABLE in `schema.py`.

## Check 3: API Response ↔ TypeScript Type Alignment

For each API route file in `cleo/web/routes/`:
- Identify what columns/fields the SELECT queries return
- Check that the corresponding TypeScript interface in `types/index.ts` has matching fields
- Pay special attention to detail endpoints that use `SELECT *` — when columns are added to the schema, these endpoints automatically return new fields, but the TypeScript types won't have them unless updated

Key pairs to check:
- `properties.py` browse → `PropertyBrowseItem`
- `properties.py` detail → `PropertyDetail`
- `transactions.py` browse → `TransactionBrowseItem`
- `transactions.py` detail → `TransactionDetail`
- `contacts.py` browse → `ContactBrowseItem`
- `contacts.py` detail → `ContactDetail`
- `groups.py` browse → `GroupBrowseItem`
- `groups.py` detail → `GroupDetail`
- `gw.py` browse/detail → `GwAssessment`

## Check 4: FTS Table Column Validity

Each FTS5 virtual table in `schema.py` references columns from a content table. The column names in the FTS definition must exactly match column names in the source table. A mismatch causes "no such column" errors at rebuild time.

Check each FTS table:
- `properties_fts` → columns must exist in `properties`
- `contacts_fts` → columns must exist in `contacts`
- `groups_fts` → columns must exist in `groups`
- `transactions_fts` → columns must exist in `transactions`

## Check 5: Clean-Data Field Coverage

This is the check that catches data being silently dropped. For each data source:

**RT (Realtrack):** Read a sample file from `clean-data/rt/` and verify that every non-empty field in the JSON has a corresponding column in the database (either directly on `transactions` or in one of the satellite tables like `transaction_mailing_addresses`, `transaction_party_metadata`, `transaction_consideration`, `transaction_brokers`).

**GW (GeoWarehouse):** Read a sample file from `clean-data/gw/` and verify that every field is captured — especially `sales_history` (→ `gw_sales_history`), `registry` fields (→ `gw_assessments`), and `quality` flags (→ `gw_assessments`).

## Check 6: Schema ↔ Writer Column Coverage

For each derived table in `schema.py`, check that `writer.py` actually populates it. Specifically:
- Every table in the schema should have at least one INSERT in the writer
- For the main tables (`properties`, `transactions`, `contacts`, `groups`, `gw_assessments`), verify the INSERT covers all non-default, non-auto columns

## Check 7: TypeScript Compilation

Run the TypeScript compiler to catch type errors:
```bash
cd frontend && npx tsc --noEmit
```

Any errors here mean types are out of sync with the code that uses them.

## What to Do When Something Fails

1. Fix the inconsistency in the lowest layer first (schema → writer → API → types → docs)
2. Re-run the verify check
3. If adding a new derived table, make sure it's in ALL four locations from Check 1
4. If adding columns to an existing table, trace through all five layers
