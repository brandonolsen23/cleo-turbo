# In-App Issue Tracker

**Status**: planning
**Goal**: a structured way to report data-quality / UI bugs from any page, with enough structure that Claude in a fresh chat can read the open issue log, work through them one by one, and mark each resolved with a note + commit.

## Why this matters

Today when you spot something wrong (the 3098 Carling Avenue case: wrong parcel outline, wrong photos, two unrelated transactions glued onto the same property record), there's no place to capture it. The context lives in your head until you either fix it on the spot or forget it. With hundreds of these latent issues likely sitting in the data, a structured backlog is the only way they get worked off.

The 3098 Carling case has multiple symptoms — and structured categories make it specific:
- `parcel_mismatch`: the resolver matched a restaurant strip parcel to a property whose real geometry is a church complex
- `wrong_photos`: GW property photos belong to the wrong parcel
- `transactions_merged`: the $33M RioCan→Quebec Inc deal and the $4M numbered-co deal got joined onto the same property record despite being different sites

Each is a distinct fixable issue with a different root cause. The system needs to capture each as its own ticket so we can actually resolve them.

## Architecture decisions

**A1. One table: `issues`.** CRM-class (persistent, never rebuilt by the compiler). Each row is one user-filed observation.

**A2. Entity-typed.** Every issue points at a specific record via `(entity_type, entity_id)` — so an issue is always anchored to a Property, Contact, Group, Transaction, or Auto-Group. Issues without a target are allowed (entity_type='general') for things like "the filter sidebar collapses awkwardly on narrow screens."

**A3. Closed-set categories.** Closed enum means Claude can filter, group, and prioritize predictably. The list is Cleo-specific:

| Category | What it means |
|---|---|
| `parcel_mismatch` | Property's resolved parcel is wrong (wrong ARN, wrong geometry) |
| `wrong_photos` | Property has photos from a different property |
| `transactions_merged` | Two unrelated transactions joined onto one property |
| `address_typo` | display_address has a typo / formatting bug |
| `wrong_owner` | `current_owner_group_id` points at the wrong entity |
| `mis_clustered_group` | Auto-group includes SPVs that don't belong |
| `missing_data` | Field expected to have a value but is null |
| `duplicate_entity` | Same property/contact/group appears twice |
| `ui_bug` | Display / interaction issue |
| `data_quality` | Other data-quality issue not covered above |
| `feature_request` | Not a bug — a thing that would be nice to have |
| `other` | Catch-all |

**A4. Severity is 4-level.** `low` / `medium` / `high` / `critical`. Critical means "actively misleading the user in a way that could lead to bad decisions" (e.g. a $33M deal showing on the wrong parcel). Low means "minor cosmetic."

**A5. Status workflow.** `open` (default on file) → `in_progress` (someone — Claude or human — is working on it) → `resolved` (fixed, with a note explaining what was done) → `wontfix` or `duplicate` as terminal states. No re-open mechanism in v1; if it recurs, file a new issue with a back-reference.

**A6. Evidence as JSON.** A free-form `evidence_json` blob holds whatever the reporter wants to attach: related entity IDs, URLs, screenshots-paths, comparison data. Schemaless because the shape varies wildly per category.

**A7. Claude integration is via SQL + an optional CLI.** No new auth surface needed. Claude in a fresh chat can:
- `SELECT * FROM issues WHERE status='open' ORDER BY severity DESC, reported_at ASC` — read the backlog
- `UPDATE issues SET status='in_progress', updated_at=datetime('now') WHERE id=?` — claim it
- `UPDATE issues SET status='resolved', resolved_by='claude', resolved_at=datetime('now'), resolution_notes=?, fixed_in_commit=? WHERE id=?` — close it

A thin CLI wrapper (`python -m cleo.cli.issues`) makes the common moves one-liners but isn't required.

## Schema

```sql
CREATE TABLE issues (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    -- What it's about
    entity_type       TEXT NOT NULL CHECK (entity_type IN
                        ('property','contact','group','transaction','auto_group','general')),
    entity_id         TEXT,                -- nullable for general issues
    -- Classification
    category          TEXT NOT NULL CHECK (category IN
                        ('parcel_mismatch','wrong_photos','transactions_merged',
                         'address_typo','wrong_owner','mis_clustered_group',
                         'missing_data','duplicate_entity','ui_bug',
                         'data_quality','feature_request','other')),
    severity          TEXT NOT NULL CHECK (severity IN ('low','medium','high','critical')),
    -- Content
    title             TEXT NOT NULL,
    description       TEXT NOT NULL,
    expected          TEXT,                -- "what should be" (optional)
    evidence_json     TEXT,                -- arbitrary attached data
    -- Lifecycle
    status            TEXT NOT NULL DEFAULT 'open'
                        CHECK (status IN ('open','in_progress','resolved','wontfix','duplicate')),
    reported_by       TEXT NOT NULL,
    reported_at       TEXT DEFAULT (datetime('now')),
    resolved_by       TEXT,
    resolved_at       TEXT,
    resolution_notes  TEXT,
    fixed_in_commit   TEXT,                -- git sha when applicable
    updated_at        TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_issues_status   ON issues(status);
CREATE INDEX idx_issues_entity   ON issues(entity_type, entity_id);
CREATE INDEX idx_issues_category ON issues(category);
CREATE INDEX idx_issues_severity ON issues(severity);
```

This is a CRM table — added to `CRM_TABLES` in `schema.py` so the compiler never touches it.

## API

| Endpoint | Description |
|---|---|
| `GET /api/issues` | Paginated list. Filters: `status`, `category`, `severity`, `entity_type`, `entity_id`, `q` (search title+description). Sort: `severity`, `reported_at` (default desc), `status`. |
| `POST /api/issues` | Create. Body: `{entity_type, entity_id, category, severity, title, description, expected?, evidence?}`. Returns the new id. |
| `GET /api/issues/{id}` | Single issue with full context. |
| `PATCH /api/issues/{id}` | Update `status`, `resolution_notes`, `fixed_in_commit`, severity, category. |
| `GET /api/issues/stats` | Counts by status + category for the issues dashboard widget. |

All endpoints require auth.

## Frontend

**Three surfaces, in order of importance:**

### 1. "Report Issue" entry point

A small button — bug-icon, no label — pinned to the right side of the page header on every detail page (Property, Contact, Group, Transaction, Auto-Group). Clicks open a modal.

Modal pre-fills `entity_type` and `entity_id` from the current page (e.g. PRO_26073). User fills:
- **Category** (required, dropdown of the 12)
- **Severity** (required, default `medium`)
- **Title** (required, ~80 chars, e.g. "Wrong parcel matched to 3098 Carling Ave")
- **Description** (required, free-text)
- **What it should be** (optional)
- **Evidence** (optional — a textarea where the user can paste related entity IDs / URLs / notes; gets stored as `evidence_json` with structure parsed if possible, raw text otherwise)

Cmd+I (or similar) shortcut opens the same modal from anywhere.

### 2. `/issues` list page

A new top-level nav entry under "System" (or CRM, TBD). Filterable list:
- Status (default: open)
- Category multi-select
- Severity
- Entity type
- Search

Columns: ID · Title · Entity (clickable, jumps to the page) · Category badge · Severity badge · Reporter · Reported at · Status badge

### 3. `/issues/{id}` detail page

- Title, description, expected, evidence
- Link to the entity page
- Status changer (open → in_progress → resolved/wontfix/duplicate)
- Resolution notes + commit field (fills when transitioning to resolved)
- Timeline: reported_at → updated_at → resolved_at
- "Open in a new chat with Claude" button that copies a structured prompt onto the clipboard:
  > Read issue #N from `/api/issues/{N}` and resolve it. When done, PATCH the issue with status=resolved, resolution_notes=..., fixed_in_commit=... .

That last button is the integration glue — one click takes you from "I found a bug" to "Claude is fixing it" with all context preloaded.

## Claude workflow

For a fresh chat:

> "Let's work through open issues. Pull `SELECT id, entity_type, entity_id, category, severity, title FROM issues WHERE status='open' ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, reported_at` and pick the first one."

Claude:
1. Reads the issue
2. Investigates the underlying entity (parcel data, photos, transactions, etc.)
3. Makes the fix
4. Commits it
5. `UPDATE issues SET status='resolved', resolved_by='claude', resolution_notes='...', fixed_in_commit='<sha>' WHERE id=?`
6. Moves to the next

No state lives in chat history — everything is in the issues table. New chats can pick up where the last left off.

## Implementation phases

### Wave 1 — schema + API + minimum CLI (~2 h)
- Migration 036: `issues` table + CRM-table registration
- `cleo/web/routes/issues.py`: CRUD endpoints
- `cleo/cli/issues.py`: `list`, `resolve`, `view` commands (~30 lines, optional but very low cost)

### Wave 2 — frontend report flow (~1.5 h)
- Floating `ReportIssueButton` on every detail page + global Cmd+I shortcut
- `ReportIssueModal` with the form
- Auto-prefill from current page URL

### Wave 3 — issues list + detail (~1.5 h)
- `/issues` page with filter sidebar
- `/issues/{id}` detail with status changer + "copy Claude prompt" button
- Sidebar nav entry

### Wave 4 — polish (~0.5 h)
- Stats widget on Dashboard (open count, critical count)
- Update CLAUDE.md so future sessions know how to query/resolve issues

**Total: ~5–6 hours.**

## Decisions to confirm before kickoff

1. **Nav placement** — Issues under System (admin-feeling) or CRM (work-feeling)? My take: CRM. It's part of the daily workflow.
2. **Comments / threading** — single description + resolution note (current plan) or full comment threads (more work)? My take: skip comments in v1, add only if it becomes needed.
3. **Re-open** — once resolved, allowed to re-open or always file a new issue? My take: file new, link back. Simpler audit trail.
4. **Severity defaults** — should we auto-suggest severity based on category (parcel_mismatch defaults to high, ui_bug to medium, feature_request to low)? My take: yes, sensible defaults reduce friction; the user can still override.
5. **Cmd+I** — is the shortcut OK or does it conflict with another binding you use? My take: pick a less-loaded shortcut like Cmd+Shift+B (Bug) if Cmd+I is taken. *Suggest you choose.*
