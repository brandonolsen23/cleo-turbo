---
name: new-feature
description: |
  Full-stack implementation checklist for adding any new feature to Cleo Turbo. This skill enforces the correct order of operations across all five layers (schema → compiler → API → types → frontend → docs) and prevents the silent breakage that happens when one layer is updated but others aren't. Use this skill whenever the task involves adding a new data field, a new table, a new API endpoint, a new page, a new data source, or any change that touches more than one layer of the stack. Trigger on: "add a feature", "new field", "new table", "new endpoint", "new page", "new column", "add support for X", "expose X in the API", "show X in the frontend", or any request that implies changes across backend and frontend. When in doubt, use this skill — skipping a layer is how 76 fields got silently dropped.
---

# New Feature — Full-Stack Implementation Guide

This skill walks you through every layer that needs to change when adding a feature to Cleo Turbo. The system has five layers that must stay in sync, and the correct order to modify them is bottom-up: database first, frontend last. Skipping a layer or working out of order causes silent data loss or runtime errors that are hard to trace.

## Why Order Matters

Each layer depends on the one below it:
1. **Schema** defines what columns exist
2. **Compiler** writes data into those columns
3. **API** reads those columns and serves them
4. **Types** tell the frontend what shape the data has
5. **Frontend** renders the data for users
6. **Docs** tell future developers (and AI) what exists

If you add a column to the schema but forget the compiler, the column is always NULL. If you update the compiler but forget the API, the data exists but nobody can see it. If you update the API but forget TypeScript types, the frontend silently ignores the new field. Each gap is a silent failure.

## Before You Start

Identify which layers your feature touches. Not every feature needs all layers:

| Feature type | Schema | Compiler | API | Types | Frontend | Docs |
|---|---|---|---|---|---|---|
| New data field from clean-data | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| New derived table | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| New CRM table | ✓ | — | ✓ | ✓ | ✓ | ✓ |
| New API-only feature (no new data) | — | — | ✓ | ✓ | ✓ | — |
| Frontend-only change | — | — | — | maybe | ✓ | — |
| New data source | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

## Layer 1: Schema (`cleo/database/schema.py`)

### Adding columns to an existing table

1. Add the column to the CREATE TABLE statement with the correct type and default
2. If the table is derived, no migration is needed — the compiler will recreate it
3. If the table is CRM or system, you need an ALTER TABLE migration (add it to the `migrations` list in schema.py or run it manually)

### Adding a new derived table

1. Add the CREATE TABLE statement to the `DERIVED_TABLES` string
2. Add `DROP TABLE IF EXISTS your_table` to `drop_derived_tables()` — order matters, drop child tables before parent tables (foreign key dependencies)
3. Add indexes after the CREATE TABLE if you'll query by non-primary-key columns
4. If the table needs full-text search, add an FTS5 virtual table to `FTS_TABLES`

### Adding a new CRM table

1. Add the CREATE TABLE to `CRM_TABLES`
2. Never add CRM tables to `drop_derived_tables()` — this would destroy user data on every compiler run

### Checkpoint

Before moving to Layer 2, verify:
- Column names use snake_case
- Column types are correct (TEXT, INTEGER, REAL, BLOB)
- Foreign keys reference the correct parent table and column
- New derived tables appear in both CREATE and DROP sections
- Indexes exist for columns you'll filter/join on

## Layer 2: Compiler (`cleo/compiler/writer.py`)

This layer only applies to derived tables — CRM tables are populated via API endpoints.

### Adding columns to an existing INSERT

1. Find the INSERT statement for the target table
2. Add the new column name to the column list
3. Add a `?` placeholder to the VALUES clause
4. Add the value extraction from the clean-data JSON to the parameter tuple
5. **Critical**: count the columns and count the `?` marks. They must be equal. This is the single most common bug in the codebase.

### Adding a new table write

1. Add the INSERT statement after the parent record is written (so the parent ID is available)
2. Loop over the relevant data from the clean-data JSON
3. Use the same parent ID that was just inserted
4. Remember to handle missing/None data gracefully — clean-data records vary in completeness

### Writing FTS rebuild

If you added an FTS5 table in Layer 1:
```python
conn.execute("INSERT INTO your_table_fts(your_table_fts) VALUES('rebuild')")
```
Add this at the end of the write process, after all data is inserted.

### Checkpoint

Before moving to Layer 3, verify:
- Every INSERT has matching column count and placeholder count
- Column names in INSERT match column names in CREATE TABLE exactly
- Data extraction handles None/missing keys with `.get()` and fallbacks
- New satellite tables are written inside the correct parent loop
- FTS rebuild is called if an FTS table was added

## Layer 3: API (`cleo/web/routes/*.py`)

### Adding fields to an existing endpoint

1. If the endpoint uses `SELECT *`, the new columns are automatically included — but you should still verify by checking what the endpoint returns
2. If the endpoint uses explicit column lists, add the new columns
3. If the new data comes from a satellite table, add a JOIN or a separate query in the detail endpoint
4. Parse any JSON columns with `json.loads(result.get("field") or "[]")`

### Adding a new endpoint

Follow the patterns in the `api-route` skill (`Read .claude/skills/api-route/SKILL.md`). The key points:
1. Create `cleo/web/routes/your_resource.py` with `router = APIRouter()`
2. Every endpoint takes `db=Depends(get_db), user=Depends(get_current_user)`
3. Browse endpoints return `{results, total, page, per_page, pages}`
4. Search endpoints use FTS5 MATCH queries
5. Register the router in `cleo/web/app.py`

### Checkpoint

Before moving to Layer 4, verify:
- New columns are included in SELECT statements (or `SELECT *` is used)
- JSON columns are parsed before returning
- Browse endpoints include new fields if they should be visible in list views
- Detail endpoints include related data from satellite tables
- The endpoint is registered in `app.py`

## Layer 4: TypeScript Types (`frontend/src/types/index.ts`)

1. Add new fields to the existing interface that matches the endpoint's response shape
2. Use `?` (optional) for fields that may be null or missing
3. If adding a new endpoint, create a new interface
4. If the data includes nested objects (like satellite table data enriched into a detail response), create sub-interfaces

### Key type mappings

| SQLite type | TypeScript type |
|---|---|
| TEXT | string |
| INTEGER | number |
| REAL | number |
| NULL-able anything | type \| null |
| JSON string (parsed by API) | the parsed shape (e.g., `string[]`, `Record<string, any>`) |

### Checkpoint

Before moving to Layer 5, verify:
- Every field the API returns has a corresponding TypeScript field
- Optional fields are marked with `?`
- Run `cd frontend && npx tsc --noEmit` — it must pass with no errors

## Layer 5: Frontend (`frontend/src/pages/*.tsx`)

Follow the patterns in the `frontend-page` skill (`Read .claude/skills/frontend-page/SKILL.md`). The key points:

1. For new fields on existing pages: add them to the relevant card/table/section
2. For new pages: create the component, add the route in App.tsx, add to Sidebar if top-level
3. Use Radix components (`Heading`, `Text`, `Badge`, `Button`) — not raw HTML for text elements
4. Use formatting helpers (`formatCurrency`, `formatDate`, `formatPhone`) from `lib/utils.ts`
5. Use Phosphor icons from `@phosphor-icons/react`

### Checkpoint

Before moving to Layer 6, verify:
- The new data is visible in the UI
- Formatting is correct (dates, currencies, phone numbers)
- Null/missing data is handled gracefully (no "undefined" or "null" showing)
- TypeScript compiles: `cd frontend && npx tsc --noEmit`

## Layer 6: Documentation

Update these files to reflect your changes:

1. **`CLAUDE.md`** — If you added a new derived table, add it to the derived tables list. If you added a new CRM table, add it to the CRM tables list.
2. **`docs/definitions.md`** — Add or update the table description in the database reference section.
3. **`.claude/skills/api-route/SKILL.md`** — If you added a new derived table, add it to the derived tables list there too.

These docs are read by AI assistants in future sessions. If they're out of date, the AI will make incorrect assumptions and introduce bugs.

## Final Verification

After all layers are complete, run the verify skill:

```bash
python3 .claude/skills/verify/scripts/verify.py
```

This checks:
- Derived table lists match across schema, drop function, CLAUDE.md, and api-route skill
- INSERT column/placeholder counts match
- FTS columns are valid
- TypeScript compiles
- Clean-data fields have corresponding database columns

Fix anything it flags before committing.

## Common Mistakes

1. **Adding a column to schema but not to the INSERT in writer.py** — The column is always NULL. The verify script catches this for INSERT mismatches but not for missing columns.
2. **Adding a derived table to CREATE but not to DROP** — On next compiler run, the old table persists with stale data alongside new tables. The verify script catches this.
3. **Updating the API but not TypeScript types** — The frontend silently ignores new fields. TypeScript compilation won't catch this because the API returns plain JSON.
4. **Forgetting to parse JSON columns in the API** — The frontend receives a JSON string instead of a parsed object, causing rendering bugs.
5. **Updating CLAUDE.md but not api-route skill (or vice versa)** — Future AI sessions get inconsistent information about what tables exist. The verify script catches this.
