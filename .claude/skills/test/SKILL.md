---
name: test
description: |
  Generate and run tests for the Cleo Turbo stack. This skill creates and executes three categories of tests: API endpoint response shape verification (do endpoints return the fields TypeScript expects?), compiler output validation (did the compiler populate all tables with the right row counts?), and data-flow tracing (does a field from clean-data make it all the way through to the API response?). Use this skill whenever you need to verify that changes work end-to-end, after implementing a new feature, before committing, or when something seems broken. Trigger on: "run tests", "test this", "does it work", "verify the API", "check the endpoints", "smoke test", "integration test", "are the tables populated", or any request to validate that the system works correctly. Also use proactively after completing any implementation work — untested code is unfinished code.
disable-model-invocation: true
---

# Test — Cleo Turbo Stack Testing

This skill generates and runs tests that verify the Cleo Turbo stack works end-to-end. It covers three categories that together catch the vast majority of integration bugs: API shape tests, compiler output tests, and data-flow trace tests.

These tests require a running backend (port 8099) and a populated database. If the backend isn't running or the database is empty, start there first.

## Quick Start

Run all tests:
```bash
python3 .claude/skills/test/scripts/test_api_shapes.py
python3 .claude/skills/test/scripts/test_compiler_output.py
python3 .claude/skills/test/scripts/test_data_flow.py
```

Or run the combined runner:
```bash
python3 .claude/skills/test/scripts/run_all.py
```

If a script doesn't exist yet, create it using the patterns below.

## Category 1: API Response Shape Tests

These tests hit every API endpoint and verify that the response contains the fields that TypeScript expects. This catches the common bug where the API is updated but TypeScript types aren't (or vice versa).

### How it works

1. Parse `frontend/src/types/index.ts` to extract interface fields
2. Hit each API endpoint with a GET request
3. Compare the response keys against the TypeScript interface fields
4. Report any mismatches: fields in TypeScript but not in response, fields in response but not in TypeScript

### Endpoint-to-type mapping

| Endpoint | TypeScript Interface | Notes |
|---|---|---|
| `GET /api/properties` | `PropertyBrowseItem` | Check `results[0]` keys |
| `GET /api/properties/:id` | `PropertyDetail` | Full detail response |
| `GET /api/transactions` | `TransactionBrowseItem` | Check `results[0]` keys |
| `GET /api/transactions/:id` | `TransactionDetail` | Includes nested objects |
| `GET /api/contacts` | `ContactBrowseItem` | Check `results[0]` keys |
| `GET /api/contacts/:id` | `ContactDetail` | Full detail response |
| `GET /api/groups` | `GroupBrowseItem` | Check `results[0]` keys |
| `GET /api/groups/:id` | `GroupDetail` | Full detail response |
| `GET /api/gw` | `GwAssessment` | Check `results[0]` keys |
| `GET /api/gw/:id` | `GwAssessment` | With `sales_history` |

### What to check

For browse endpoints, the response shape is:
```json
{
  "results": [...],
  "total": 123,
  "page": 1,
  "per_page": 25,
  "pages": 5
}
```
Check that `results[0]` (if results exist) has keys matching the browse interface.

For detail endpoints, the response itself is the object — check its keys directly.

Some fields are optional or conditional (only present when data exists). The test should distinguish between "field is missing from the response entirely" (possible bug) and "field is present but null" (normal for sparse data).

### Edge cases

- Nested objects (like `consideration`, `brokers`, `seller_mailing_address` on TransactionDetail) are enriched by the detail endpoint — they won't appear in the browse response
- JSON-parsed fields (like `seller_parties`, `buyer_parties`) should be arrays, not strings
- Some detail endpoints return extra fields beyond what the TypeScript interface defines (from `SELECT *`) — flag these as warnings, not failures

## Category 2: Compiler Output Tests

These tests verify that the compiler populated all derived tables with reasonable row counts and that key relationships hold.

### What to check

1. **Table existence**: Every derived table in the schema actually exists in the database
2. **Row counts**: Each table has a non-zero row count (if clean-data exists for that source)
3. **Referential integrity**: Foreign keys point to existing parent records
4. **No orphans**: Satellite table rows (transaction_mailing_addresses, etc.) reference existing transactions
5. **ID format**: Stable IDs follow the expected format (PRO_NNNNN, CON_NNNNN, GRP_NNNNN)
6. **FTS sync**: FTS tables have the same row count as their content tables

### Key queries

```sql
-- Table row counts
SELECT 'properties' as tbl, COUNT(*) as cnt FROM properties
UNION ALL SELECT 'transactions', COUNT(*) FROM transactions
UNION ALL SELECT 'contacts', COUNT(*) FROM contacts
UNION ALL SELECT 'groups', COUNT(*) FROM groups
UNION ALL SELECT 'gw_assessments', COUNT(*) FROM gw_assessments;

-- Orphan check (satellite tables referencing non-existent parents)
SELECT COUNT(*) FROM transaction_mailing_addresses
WHERE source_id NOT IN (SELECT source_id FROM transactions);

-- ID format check
SELECT COUNT(*) FROM properties WHERE id NOT LIKE 'PRO_%';
SELECT COUNT(*) FROM contacts WHERE id NOT LIKE 'CON_%';
SELECT COUNT(*) FROM groups WHERE id NOT LIKE 'GRP_%';

-- FTS sync
SELECT
  (SELECT COUNT(*) FROM properties) as table_count,
  (SELECT COUNT(*) FROM properties_fts) as fts_count;
```

## Category 3: Data-Flow Trace Tests

These are the most powerful tests. They pick a specific record from clean-data, trace it through the compiler into the database, and then through the API to verify the field values match.

### How it works

1. Pick a sample record from `clean-data/rt/` or `clean-data/gw/`
2. Read the JSON file to get the source data
3. Query the database for the corresponding record (match by source_id or ARN)
4. Hit the API endpoint for the same record
5. Compare key field values across all three: source JSON → database → API response

### What to trace

For RT records:
- `sale_price` → `transactions.sale_price` → API `sale_price`
- `seller.parties[0].name` → `transactions.seller_parties` (JSON) → API `seller_parties[0].name`
- `site.pin` → `transactions.pin` → API `pin`
- `description.description` → `transactions.description` → API `description`
- `consideration` → `transaction_consideration` rows → API `consideration` array
- `broker.brokers` → `transaction_brokers` rows → API `brokers` array

For GW records:
- `assessment.assessed_value` → `gw_assessments.assessed_value` → API `assessed_value`
- `sales_history` → `gw_sales_history` rows → API `sales_history` array
- `registry.land_registry_status` → `gw_assessments.land_registry_status` → API `land_registry_status`

### When data is missing

Not every clean-data record has every field. The trace test should:
- Skip fields that are null/missing in the source JSON
- Flag fields that exist in the source but are NULL in the database (potential compiler bug)
- Flag fields that exist in the database but are missing from the API response (potential API bug)

## Writing New Tests

When you add a new feature using the `new-feature` skill, add corresponding tests:

1. **If you added a new column**: Add it to the data-flow trace for the relevant entity type
2. **If you added a new table**: Add a row-count check and an orphan check to compiler output tests
3. **If you added a new endpoint**: Add an API shape test mapping it to its TypeScript interface
4. **If you added a new TypeScript interface**: Make sure an API shape test covers it

## Test Output Format

All test scripts should output in this format for consistency:

```
============================================================
Cleo Turbo [Category] Tests
============================================================

TEST GROUP: [Name]
  ✓ passed check description
  ✗ failed check description
    → Expected: X, Got: Y
  ⚠ warning description

============================================================
Results: N passed, N failed, N warnings
✓ All checks passed! / ✗ N issue(s) need fixing
============================================================
```

Exit code 0 if all pass, 1 if any fail. Warnings don't cause failure.
