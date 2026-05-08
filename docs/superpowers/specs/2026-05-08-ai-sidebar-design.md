# AI Sidebar — Design Spec

In-app Claude chat panel that lets the user query Cleo Turbo's data
through a slide-out drawer. First implementation of "Claude in the
app." Read-only: Claude can search, aggregate, and explain — it
cannot mutate any record.

## Goal

Land a working chat panel that demonstrates "what Claude can do with
this data" against the live Cleo database, with enough plumbing to be
useful day-to-day for prospecting questions like:

- *"Tell me about this owner — what else do they own, who's the
  contact, when did they last buy?"*
- *"Find retail buyers in Halton with $20M+ portfolios who haven't
  been contacted in 90 days."*
- *"Who's been most active in Brantford this year?"*
- *"Show me dormant contacts I should re-engage."*

The bar for v1 is **answers a real prospecting question with one
visible run_sql call**, not a fully agentic prospecting partner.

## Non-goals

- No write actions (no logging activities, no list edits, no deal
  creation). That's a separate phase.
- No MCP server. The same tool surface is a natural extraction
  later, but not part of v1.
- No conversation persistence to the database. Conversations live in
  React state for the session and are lost on refresh.
- No per-user rate limits. Backend logs token usage but doesn't gate.
- No extended thinking. Standard tool-call loop.
- No fine-tuned routing between Haiku/Sonnet/Opus. v1 is single-model.

## Architecture

```
Browser (drawer)
   │  POST /api/ai/chat (SSE response)
   │  Authorization: Bearer <user JWT>
   │  Body: { messages, page_context }
   ▼
FastAPI: cleo/web/routes/ai.py
   │  1. Loads system prompt (project description + table-category
   │     map + page-context block).
   │  2. Calls Anthropic with run_sql / describe_schema /
   │     get_entity_url tools defined.
   │  3. Streams text deltas to browser via SSE.
   │  4. On Anthropic tool_use: executes the tool, sends the
   │     tool_result back to Anthropic, resumes streaming.
   │  5. Forwards tool-call metadata to the browser as a separate
   │     SSE event so the UI can render collapsed "Ran SQL · N rows"
   │     blocks at the right moment.
   ▼
Read-only SQLite connection
   │  sqlite3.connect("file:data/cleo.db?mode=ro", uri=True)
   │  Backed by a small statement-level guard that rejects
   │  anything except SELECT/WITH/EXPLAIN.
```

### Why a backend proxy

- API key never reaches the browser.
- Tool execution (especially `run_sql`) must be server-side.
- Auth is enforced by the existing JWT middleware.
- We can add per-conversation logging without frontend changes.

### SSE event types

| Event | Payload | Purpose |
|---|---|---|
| `text_delta` | `{ delta: "..." }` | Append tokens to the current assistant message. |
| `tool_use_start` | `{ id, name, input }` | Render the collapsed tool block. |
| `tool_use_end` | `{ id, ok, row_count?, error? }` | Update the tool block with result summary. |
| `done` | `{ stop_reason, usage }` | Turn complete. |
| `error` | `{ message }` | Surface a friendly error and close the stream. |

### Read-only safety

Connection is opened in URI mode with `mode=ro`. Even an LLM-crafted
malicious string can't write — the SQLite engine refuses any non-read
opcode. On top of that, a tiny guard rejects:

- Anything not starting with `SELECT`, `WITH`, or `EXPLAIN`
  (case-insensitive, after stripping leading whitespace and
  comments).
- Multiple statements (any `;` followed by non-whitespace).
- `PRAGMA` (read-only flag still allows some pragmas with side
  effects on session state).
- `ATTACH` (could expose other DBs).
- Anything containing `writable_schema`.

The guard is belt-and-suspenders; the read-only connection is the
hard barrier.

## Tool surface

Three tools, deliberately small. Promote frequently-used SQL into
named tools later as patterns emerge.

### `run_sql`

```jsonc
{
  "name": "run_sql",
  "description": "Execute a read-only SQL query against the Cleo database. SQLite dialect. Always include LIMIT.",
  "input_schema": {
    "type": "object",
    "properties": {
      "query": { "type": "string", "description": "A single SELECT/WITH/EXPLAIN statement." }
    },
    "required": ["query"]
  }
}
```

- Result rows capped at **200**. A `truncated: true` flag tells Claude to add `LIMIT` or aggregate.
- Per-query timeout: **5 seconds** (`SET QUERY_TIMEOUT` via `progress_handler` interrupt — SQLite's standard mechanism).
- Returns `{ rows: [...], columns: [...], row_count: N, truncated: bool, elapsed_ms: M }`.

### `describe_schema`

```jsonc
{
  "name": "describe_schema",
  "description": "Inspect the database schema. Call with no arg to list tables; call with a table name to see columns and 5 sample rows.",
  "input_schema": {
    "type": "object",
    "properties": {
      "table": { "type": "string", "description": "Optional table name." }
    }
  }
}
```

- No-arg form: returns `[{ table, row_count, description }]` for every table. Description is a one-line label drawn from a small handwritten map (so Claude knows `properties` is derived and `deals` is CRM, etc.).
- With `table`: returns `{ columns: [{ name, type, nullable, default }], sample_rows: [...] }`. Sample is the literal first 5 rows from a `SELECT * FROM <table> LIMIT 5`.

### `get_entity_url`

```jsonc
{
  "name": "get_entity_url",
  "description": "Get the in-app URL for an entity. Use it to render clickable links in your answer.",
  "input_schema": {
    "type": "object",
    "properties": {
      "entity_type": { "type": "string", "enum": ["property", "contact", "group", "deal", "list", "transaction"] },
      "id": { "type": "string" }
    },
    "required": ["entity_type", "id"]
  }
}
```

- Returns `{ url: "/properties/PRO_84463" }`. Pure URL builder — no DB call.
- Why expose this: lets Claude link to entities in markdown answers without baking URL patterns into the system prompt and getting them wrong.

## System prompt

```
You are an analyst inside Cleo Turbo, a commercial real estate
prospecting tool for Ontario. The user is a CRE broker. They use
this tool to find acquisition targets, track outreach, and decide
who to call.

You have read-only access to a SQLite database via the run_sql tool.
Use describe_schema BEFORE writing queries against unfamiliar tables
— never guess column names. Always include LIMIT in your queries.
Quote ARNs (20-digit assessment roll numbers) and stable IDs
(CON_NNNNN, PRO_NNNNN, GRP_NNNNN) verbatim in answers; render them as
markdown links via get_entity_url when they refer to an entity the
user can click.

Tables fall into three categories:
- Derived (rebuilt by the compiler from clean-data/): properties,
  transactions, contacts, groups, group_names, transaction_parties,
  pois, gw_assessments, gw_sales_history.
- CRM (persistent, user-typed): deals, lists, list_members,
  group_contacts, contact_notes, group_notes, sell_opportunities,
  buy_mandates, activities, user_stars, contact_field_overrides.
- System: users, audit_log, app_meta.

Currency is CAD. Addresses are Ontario.

{{page_context_block}}

Style:
- Be terse. Direct numbers and named entities beat narration.
- When you find something, name it (CON_NNNNN, GRP_NNNNN) and link it.
- When the user's question is ambiguous, run a small probe query
  rather than asking back — bias for showing data.
- Never speculate about ownership beyond what's in the database.
```

`{{page_context_block}}` is one of:

- Empty string when no page context.
- `User is currently looking at property PRO_84463 (325 Guelph Street, Georgetown). Owner: Crialmar Properties Limited.` (or analogous block for contact / group / deal / list).

The block is generated by a small `_load_page_context` helper that does one targeted SQL fetch per entity type. Refreshed on the client when the user navigates while the drawer is open (frontend re-sends the new context on the next message).

## Drawer UI

Follows the existing `AddToListDrawer` / `CreateDealDrawer` pattern in `frontend/src/components/crm/`.

### Trigger

- Sparkle/Brain icon button in `Header.tsx`, right of the search bar.
- Keyboard shortcut: `⌘I` (Mac) / `Ctrl+I` (other). Conflict-free with `⌘K` (CommandPalette).

### Layout

Right-side drawer, ~420 px wide, full-height, fades over content with backdrop:

```
┌──────────────────────────────────┐
│ Ask Claude              [X]      │  header
│ ◉ Looking at PRO_84463           │  context pill (optional)
├──────────────────────────────────┤
│  user bubbles right-aligned      │
│  assistant bubbles left-aligned  │  message area
│  ▶ Ran SQL · 12 rows             │   (collapsed tool block)
│  ▶ Described table: contacts     │
├──────────────────────────────────┤
│ [Ask anything about your data… ] │  input area
│                          [Send]  │
└──────────────────────────────────┘
```

### Message rendering

- Markdown via `react-markdown` + `remark-gfm` (new dependencies — not currently in `frontend/package.json`).
- Tokens stream into the active assistant message as `text_delta` events arrive.
- Tool-call blocks render inline at the moment Claude calls the tool. Collapsed by default with one-line summary; expand to see:
  - Full SQL text in a styled `<pre>` block. No external syntax highlighter — light/dark color tokens for keywords via a 30-line regex tokenizer in `ToolCallBlock.tsx` is enough; saves a 200 KB dependency.
  - Result table — first 10 rows as a real `<table>`, with "+ N more rows" footer.
  - Elapsed ms.

### Empty state

Three suggested prompts, route-aware:

| On route | Suggested prompts |
|---|---|
| `/properties/:id` | "Tell me about this owner" / "Recent comparable sales nearby" / "Other properties this owner has bought" |
| `/contacts/:id` or `/groups/:id` | "What does their portfolio look like?" / "What have they bought recently?" / "Who else they're affiliated with" |
| `/queue` or other | "Find retail buyers in Halton with $20M+ portfolios" / "Who's been most active in Brantford this year?" / "Show me dormant contacts" |

Clicking a suggested prompt fills the input but does **not** auto-send.

### State

- React state inside the drawer component. `useState` for messages array, `useRef` for the active EventSource (or fetch-stream reader).
- The "context" pill auto-updates when the user navigates while the drawer is open. The next user message includes the updated `page_context` payload.
- Conversation lost on browser refresh. v1 is intentionally session-scoped.

## Model + streaming

- **Model: `claude-opus-4-7`**. Configurable via `AI_MODEL` env var.
- **Streaming: yes.** Anthropic Messages streaming API → FastAPI streams via SSE.
- **`max_tokens`: 8192**.
- **Prompt caching breakpoints:**
  1. After the system prompt + tool definitions + table-category map (stable across all chats; near-100% cache hit).
  2. After the previous assistant turn (stable within a multi-turn conversation).
- **Cost guardrail:** stop the agentic loop after **15 tool calls** or **80 k cumulative output tokens** in a single turn. Surface a `Stopped at limit — ask a more specific question?` message.

## Cost / usage logging

New table `ai_usage` (system table — never dropped, never cached):

| column | type |
|---|---|
| `id` | INTEGER PRIMARY KEY |
| `user_id` | INTEGER REFERENCES users(id) |
| `created_at` | TEXT DEFAULT now |
| `input_tokens` | INTEGER |
| `output_tokens` | INTEGER |
| `cached_tokens` | INTEGER |
| `tool_calls` | INTEGER |
| `model` | TEXT |
| `route_at_open` | TEXT  *(e.g. `/properties/PRO_84463`)* |
| `first_user_message` | TEXT  *(truncated to 200 chars; for skimming what people asked)* |

Backend writes one row per turn (not per message). Surfaced via a small `/api/ai/usage` endpoint later if useful.

## Auth / identity

- Frontend includes the existing JWT in `Authorization: Bearer ...` on `POST /api/ai/chat`.
- Backend uses the existing `get_current_user` dependency. Anonymous chat is rejected.
- The `user_id` is stamped on `ai_usage` rows.
- Tool execution does not currently use the user identity (data isn't user-scoped). When write actions land in a future phase, the existing JWT will already be threaded through.

## File structure

New / modified files:

```
cleo/web/routes/
├── ai.py                              (NEW)  ─ /api/ai/chat SSE endpoint
└── ai_tools.py                         (NEW)  ─ run_sql / describe_schema / get_entity_url

cleo/web/
└── app.py                              (MOD)  ─ register the router

cleo/database/migrations/
└── 023_ai_usage.py                     (NEW)  ─ ai_usage table

frontend/src/components/ai/
├── AskClaudeDrawer.tsx                 (NEW)  ─ the drawer + chat UI
├── ToolCallBlock.tsx                   (NEW)  ─ collapsed/expanded SQL blocks
├── MessageBubble.tsx                   (NEW)  ─ user/assistant bubbles + markdown
├── SuggestedPrompts.tsx                (NEW)  ─ route-aware empty state
└── usePageContext.ts                   (NEW)  ─ derive { entity_type, id } from useLocation

frontend/src/components/layout/Header.tsx (MOD)  ─ trigger button
frontend/src/App.tsx                    (MOD)  ─ keyboard shortcut + provider

frontend/src/api/aiClient.ts            (NEW)  ─ SSE-aware fetch wrapper

frontend/src/types/index.ts             (MOD)  ─ AIMessage / AIToolCall / AIUsage types
```

Approximate LOC budget: 700–900 net new (most of it the drawer UI).

## Testing

### Backend

- `tests/test_routes_ai.py` (NEW):
  - `run_sql` accepts `SELECT * FROM properties LIMIT 5` and returns rows.
  - `run_sql` rejects `INSERT INTO ...`, `DROP TABLE ...`, `PRAGMA writable_schema = 1`, multi-statement queries.
  - `run_sql` truncates at 200 rows and sets `truncated: true`.
  - `describe_schema()` returns the table list.
  - `describe_schema(table='properties')` returns columns + 5 sample rows.
  - `get_entity_url('property', 'PRO_42')` returns `/properties/PRO_42`.
- A small mock for the Anthropic streaming response so the SSE handler can be tested without a live API call.

### Frontend

- Unit test the `usePageContext` hook against react-router's MemoryRouter.
- Manual smoke test for the drawer (driven by the user) — too much streaming UI to be worth automating in v1.

## Open questions resolved during brainstorming

- Surface: in-app drawer (not MCP server, not dedicated page).
- Scope: read-only.
- Tool: SQL pass-through (read-only connection) + schema introspection + URL builder.
- Page context: yes, automatic.
- Model: Claude Opus 4.7.
- Streaming: yes (SSE + Anthropic streaming API).
- Persistence: per-session in-memory.

## Out of scope (future phases)

- Write actions (log activity, add to list, create deal). Will graduate to read-write on a separate phase with explicit confirmations.
- MCP server. Same tool surface, different transport.
- Saved conversations / conversation history page.
- Per-user rate limits.
- Multi-model routing (Haiku for cheap Q&A, Opus for complex agentic loops).
- Extended thinking.
- File uploads (e.g., paste a property list, get analysis).
- Voice input.
