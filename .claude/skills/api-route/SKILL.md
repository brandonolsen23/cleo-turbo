---
name: api-route
description: |
  How to add a new API route to the Cleo Turbo FastAPI backend. Use this skill whenever the task involves creating a new endpoint, adding a new resource, building browse/search/detail/create/update/delete endpoints, modifying the database schema, or adding FTS5 search. Also use when modifying existing routes — the patterns here are the source of truth for how routes should be structured. Trigger on: "add an endpoint", "new API", "backend route", "add search", "add CRUD", "new resource", or any request involving Python backend changes to the web layer.
---

# API Route Skill — Cleo Turbo

This skill covers the complete process of adding a new API route to the Cleo Turbo FastAPI backend. It reflects the actual patterns used across 15 existing route files.

## The Checklist

Every new API resource touches these files:

1. `cleo/web/routes/your_resource.py` — create the route file
2. `cleo/web/app.py` — register the router
3. `cleo/database/schema.py` — add table definitions (if new table)
4. `cleo/compiler/writer.py` — add FTS rebuild (if adding search)
5. `frontend/src/types/index.ts` — add matching TypeScript interfaces

## Step 1: Route File

Create `cleo/web/routes/your_resource.py`:

```python
"""
Your Resource routes — browse, search, and detail.
"""

import json
from fastapi import APIRouter, Depends, Query, HTTPException
from ..deps import get_db, get_current_user

router = APIRouter()
```

Key rules:
- `HTTPException` is always imported at the top of the file, never inside functions
- Every endpoint takes `db=Depends(get_db), user=Depends(get_current_user)` — no public endpoints
- For admin-only endpoints, use `user=Depends(require_admin)` from `..deps`
- All SQL uses `?` parameter placeholders — never f-strings with user input
- Return dicts: `dict(row)` or `[dict(r) for r in rows]`

### Browse Endpoint

All browse endpoints return the standard paginated response shape:

```python
@router.get("")
def browse(
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    some_filter: str = Query(None),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    conditions = []
    params = []

    if some_filter:
        conditions.append("some_column = ?")
        params.append(some_filter)

    where = " AND ".join(conditions) if conditions else "1=1"
    offset = (page - 1) * per_page

    total = db.execute(
        f"SELECT COUNT(*) FROM your_table WHERE {where}", params
    ).fetchone()[0]

    rows = db.execute(
        f"SELECT id, name, ... FROM your_table "
        f"WHERE {where} "
        f"ORDER BY created_at DESC "
        f"LIMIT ? OFFSET ?",
        params + [per_page, offset],
    ).fetchall()

    pages = max(1, (total + per_page - 1) // per_page)
    return {
        "results": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }
```

**Adding sort support** — validate the sort column against a whitelist:
```python
sort: str = Query("created_at"),
order: str = Query("desc"),

allowed_sorts = {"name", "created_at", "amount"}
if sort not in allowed_sorts:
    sort = "created_at"
if order not in ("asc", "desc"):
    order = "desc"

# Use in query:
f"ORDER BY {sort} {order} LIMIT ? OFFSET ?"
```

### Search Endpoint

Search always uses FTS5 — never LIKE queries. The FTS table must exist in schema.py.

```python
@router.get("/search")
def search(
    q: str = Query(..., min_length=1),
    limit: int = Query(25, ge=1, le=100),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    rows = db.execute(
        "SELECT id, name, ... "
        "FROM your_table "
        "WHERE rowid IN ("
        "  SELECT rowid FROM your_table_fts WHERE your_table_fts MATCH ?"
        ") "
        "LIMIT ?",
        (q, limit),
    ).fetchall()

    return {"results": [dict(r) for r in rows], "total": len(rows)}
```

The `SearchResponse` shape is `{results: [], total: int}` — no pagination fields needed since search results are capped by `limit`.

### Detail Endpoint

```python
@router.get("/{item_id}")
def detail(
    item_id: str,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    row = db.execute(
        "SELECT * FROM your_table WHERE id = ?", (item_id,)
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Item not found")

    result = dict(row)

    # Parse any JSON columns
    result["json_field"] = json.loads(result.get("json_field") or "[]")

    # Enrich with related data via additional queries
    related = db.execute(
        "SELECT ... FROM related_table WHERE parent_id = ?", (item_id,)
    ).fetchall()
    result["related_items"] = [dict(r) for r in related]

    return result
```

### Create Endpoint

Use Pydantic BaseModel for request validation:

```python
from pydantic import BaseModel
from typing import Optional
import uuid

class ItemCreate(BaseModel):
    name: str
    description: Optional[str] = None
    amount: Optional[float] = None

@router.post("")
def create(
    body: ItemCreate,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    item_id = f"PREFIX_{uuid.uuid4().hex[:8].upper()}"

    db.execute(
        "INSERT INTO your_table (id, name, description, amount, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))",
        (item_id, body.name, body.description, body.amount),
    )
    db.commit()

    return {"id": item_id, "status": "created"}
```

ID generation for CRM tables uses `PREFIX_{uuid.hex[:8].upper()}`. Examples: `DEAL_A3F2B1C9`, `LIST_7E4D2F1A`. Derived tables use the reconciler's stable IDs (PRO_, CON_, GRP_) — never generate those manually.

### Update Endpoint

```python
class ItemUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    amount: Optional[float] = None

@router.patch("/{item_id}")
def update(
    item_id: str,
    body: ItemUpdate,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    if not db.execute("SELECT 1 FROM your_table WHERE id = ?", (item_id,)).fetchone():
        raise HTTPException(status_code=404, detail="Item not found")

    updates = {k: v for k, v in body.dict().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values())

    db.execute(
        f"UPDATE your_table SET {set_clause}, updated_at = datetime('now') WHERE id = ?",
        values + [item_id],
    )
    db.commit()

    return {"id": item_id, "updated": list(updates.keys())}
```

### Delete Endpoint

```python
@router.delete("/{item_id}")
def delete(
    item_id: str,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    if not db.execute("SELECT 1 FROM your_table WHERE id = ?", (item_id,)).fetchone():
        raise HTTPException(status_code=404, detail="Item not found")

    db.execute("DELETE FROM your_table WHERE id = ?", (item_id,))
    db.commit()

    return {"id": item_id, "status": "deleted"}
```

If the table has child records, delete those first:
```python
db.execute("DELETE FROM child_table WHERE parent_id = ?", (item_id,))
db.execute("DELETE FROM your_table WHERE id = ?", (item_id,))
db.commit()
```

## Step 2: Register in app.py

In `cleo/web/app.py`, add the import and registration:

```python
from .routes.your_resource import router as your_resource_router

# Inside create_app():
app.include_router(your_resource_router, prefix="/api/your-resource", tags=["your-resource"])
```

The prefix is always `/api/` followed by the resource name with hyphens. The frontend Vite dev server proxies `/api` requests to the backend on port 8099.

## Step 3: Database Schema (if new table)

If adding a new table, add the CREATE TABLE statement to `cleo/database/schema.py`.

**Critical: know which category your table belongs to.**

- **Derived tables** (rebuilt by the compiler from clean-data/): properties, transactions, contacts, groups, group_names, transaction_parties, transaction_mailing_addresses, transaction_brokers, transaction_broker_agents, pois, gw_assessments, gw_sales_history. These get dropped and recreated on every compiler run. Add your DROP to `drop_derived_tables()`.

- **CRM tables** (persistent, never rebuilt): deals, lists, list_members, group_contacts, contact_notes, group_notes. These survive compiler runs. Never add a CRM table to `drop_derived_tables()`.

- **System tables**: users, audit_log, app_meta, data_issues.

**Adding FTS5 search** — add the virtual table definition and the rebuild step:

```sql
-- In schema.py, after the main table:
CREATE VIRTUAL TABLE IF NOT EXISTS your_table_fts USING fts5(
    id, name, description,
    content='your_table', content_rowid='rowid',
    tokenize='porter unicode61'
);
```

In `drop_derived_tables()` (if derived):
```python
conn.execute("DROP TABLE IF EXISTS your_table_fts")
```

In `cleo/compiler/writer.py`, in the FTS rebuild section:
```python
conn.execute("INSERT INTO your_table_fts(your_table_fts) VALUES('rebuild')")
```

## JSON Column Patterns

Several tables store JSON in text columns. Always parse with a fallback:

```python
result["json_field"] = json.loads(result.get("json_field") or "[]")
# or for dict columns:
result["json_field"] = json.loads(result.get("json_field") or "{}")
```

For GeoJSON specifically, handle parse errors since some records may be malformed:
```python
try:
    result["geojson"] = json.loads(row["geojson_column"])
except (json.JSONDecodeError, TypeError):
    result["geojson"] = None
```

Known JSON columns: `seller_parties` (list), `buyer_parties` (list), `photos_json` (dict), `charges_json` (list), `seller_law_firms_json` (list), `seller_companies_json` (list), `buyer_law_firms_json` (list), `buyer_companies_json` (list), `parcel_geojson` (GeoJSON geometry).

Note: Consideration data (cash, debt, chattels, other_consideration) and party metadata (trade_name, care_of, law_firms, companies) are stored as inline columns on `transactions`. Broker data uses separate tables: `transaction_brokers` and `transaction_broker_agents`.

## Error Handling

Use HTTPException with these standard codes:

| Code | When |
|------|------|
| 400 | Invalid input, bad enum value, no fields to update |
| 404 | Entity not found |
| 401 | Missing/invalid auth token (handled by deps.py) |
| 403 | Non-admin on admin endpoint (handled by deps.py) |
| 409 | Duplicate/conflict on insert |

```python
raise HTTPException(status_code=404, detail="Human-readable message")
```

FastAPI returns `{"detail": "..."}` automatically — don't wrap errors in a custom format.

## The ARN Connection

The ARN (Assessment Roll Number) is the backbone that links everything together. An RT transaction, a GW detail page, and parcel geometry all connect to the same property via ARN. If you're adding a new data source or feature, figure out how it connects to ARNs.

## Ports

- Backend: **8099** — `uvicorn cleo.web.app:app --reload --port 8099`
- Frontend: **5174** — configured in `vite.config.ts` with `strictPort: true`

Never use random ports.

## What NOT to Do

- Don't import HTTPException inside functions — always at the top of the file
- Don't use LIKE for search — use FTS5 MATCH queries
- Don't use an ORM — all queries are raw SQL with `db.execute()` and `?` params
- Don't forget `db.commit()` after INSERT/UPDATE/DELETE
- Don't generate stable IDs (PRO_, CON_, GRP_) manually — those come from the reconciler
- Don't modify derived tables from API endpoints — they're rebuilt by the compiler
- Don't forget to parse JSON columns before returning them to the frontend
- Don't create endpoints without auth — every endpoint needs `get_current_user` or `require_admin`
