"""AI sidebar — /api/ai/chat SSE endpoint.

Streams Anthropic Messages → SSE events to the browser, executing
read-only SQL / schema / URL tools server-side between turns.

Three SSE event types per turn (matches the spec):
- text_delta      : append tokens to the active assistant bubble
- tool_use_start  : render the collapsed "Ran SQL · …" block
- tool_use_end    : populate it with row count / elapsed_ms / error
- done            : turn complete (sent at the very end)
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Any, Iterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..deps import get_db, get_current_user
from .ai_tools import (
    InvalidQueryError, ROW_CAP, QUERY_TIMEOUT_SECONDS,
    describe_schema, get_entity_url, load_page_context, run_sql,
)


# ── Configuration ────────────────────────────────────────────────────


DEFAULT_MODEL = os.environ.get("AI_MODEL", "claude-opus-4-7")
MAX_OUTPUT_TOKENS = 8192
MAX_TOOL_CALLS = 15
MAX_OUTPUT_TOKENS_PER_CONVERSATION = 80_000
# Path to the live DB to open in read-only URI mode for run_sql.
# Tests monkeypatch this to a tempfile.
_RO_DB_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "cleo.db")
)


# ── Tool definitions sent to Anthropic ────────────────────────────────


TOOL_DEFINITIONS = [
    {
        "name": "run_sql",
        "description": (
            "Execute a read-only SQL query against the Cleo database "
            "(SQLite dialect). Always include LIMIT in your query. "
            f"Result rows are capped at {ROW_CAP}; if truncated=true, "
            "add LIMIT or aggregate. Per-query timeout: "
            f"{QUERY_TIMEOUT_SECONDS}s. Only SELECT/WITH/EXPLAIN allowed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "A single SELECT/WITH/EXPLAIN statement.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "describe_schema",
        "description": (
            "Inspect the database schema. Call with no arg to list every "
            "table with row count and a one-line description; call with "
            "table=<name> to see columns + 5 sample rows. "
            "USE THIS BEFORE WRITING run_sql AGAINST AN UNFAMILIAR TABLE."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "table": {"type": "string", "description": "Optional table name."},
            },
        },
    },
    {
        "name": "get_entity_url",
        "description": (
            "Build the in-app URL for an entity. Use to render clickable "
            "markdown links in your answer."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "entity_type": {
                    "type": "string",
                    "enum": ["property", "contact", "group", "deal", "list", "transaction"],
                },
                "id": {"type": "string"},
            },
            "required": ["entity_type", "id"],
        },
    },
]


# ── System prompt ────────────────────────────────────────────────────


_SYSTEM_PROMPT_BASE = """\
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
- System: users, audit_log, app_meta, ai_usage.

Currency is CAD. Addresses are Ontario.

Style:
- Be terse. Direct numbers and named entities beat narration.
- When you find something, name it (CON_NNNNN, GRP_NNNNN) and link it.
- When the user's question is ambiguous, run a small probe query
  rather than asking back — bias for showing data.
- Never speculate about ownership beyond what's in the database.
"""


def _build_system_prompt_blocks(page_context_block: str) -> list[dict]:
    """Returns the system prompt as Anthropic content blocks.

    The first block is the static base prompt + tool guidance, marked
    cache_control=ephemeral so prompt caching kicks in across every
    chat. The page context (which changes per route) goes in a second,
    uncached block so it doesn't fragment the cache key.
    """
    blocks: list[dict] = [
        {
            "type": "text",
            "text": _SYSTEM_PROMPT_BASE,
            "cache_control": {"type": "ephemeral"},
        },
    ]
    if page_context_block:
        blocks.append({"type": "text", "text": page_context_block})
    return blocks


# ── Anthropic client factory (patchable in tests) ─────────────────────


def _make_anthropic_client():
    """Build a real Anthropic client. Tests monkeypatch this to a fake."""
    import anthropic
    return anthropic.Anthropic()  # picks up ANTHROPIC_API_KEY


# ── DB helpers ───────────────────────────────────────────────────────


def _open_readonly() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{_RO_DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _set_query_deadline(conn: sqlite3.Connection, deadline_ts: float) -> None:
    def _progress():
        return 1 if time.time() > deadline_ts else 0
    conn.set_progress_handler(_progress, 1000)


# ── Tool dispatch ────────────────────────────────────────────────────


def _execute_tool(name: str, args: dict, ro_conn: sqlite3.Connection) -> dict:
    """Run a tool the LLM requested. Returns a dict that gets serialized
    into a tool_result content block back to Anthropic.

    On error, returns { error: <message> } — Anthropic shows that to the
    LLM and it can self-correct on the next turn."""
    started = time.time()
    try:
        if name == "run_sql":
            _set_query_deadline(ro_conn, started + QUERY_TIMEOUT_SECONDS)
            try:
                out = run_sql(ro_conn, args.get("query", ""))
            finally:
                ro_conn.set_progress_handler(None, 0)
            out["elapsed_ms"] = int((time.time() - started) * 1000)
            return out
        if name == "describe_schema":
            return describe_schema(ro_conn, table=args.get("table"))
        if name == "get_entity_url":
            return {"url": get_entity_url(args["entity_type"], args["id"])}
        return {"error": f"Unknown tool: {name}"}
    except InvalidQueryError as exc:
        return {"error": str(exc)}
    except sqlite3.OperationalError as exc:
        return {"error": f"sqlite error: {exc}"}


# ── Pydantic schema ───────────────────────────────────────────────────


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class PageContext(BaseModel):
    entity_type: str
    id: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    page_context: PageContext | None = None
    route_at_open: str | None = None


# ── Streaming generator ───────────────────────────────────────────────


def _sse(event: str, payload: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n".encode()


def _block_to_dict(block) -> dict:
    """Anthropic SDK content blocks come back as Pydantic models. Convert
    one to the plain-dict shape we need to round-trip in api_messages."""
    btype = getattr(block, "type", None)
    if btype == "text":
        return {"type": "text", "text": block.text}
    if btype == "tool_use":
        return {
            "type": "tool_use",
            "id": block.id,
            "name": block.name,
            "input": block.input,  # already a dict per the SDK
        }
    # Defensive: pass through unknown block types as-is.
    return getattr(block, "model_dump", lambda: {})() or {"type": btype}


def _stream_chat(
    req: ChatRequest,
    user: dict,
    rw_conn: sqlite3.Connection,
) -> Iterator[bytes]:
    """Sequential turn loop:

      1. Open Anthropic stream.
      2. As `TextEvent`s arrive, forward `text_delta` SSE.
      3. When the stream ends, ask for the final message; iterate its
         content blocks and execute every tool_use block, forwarding
         `tool_use_start` / `tool_use_end` SSE around each.
      4. If stop_reason == "tool_use" and we're under the cap, append
         tool_result blocks and loop. Otherwise break and emit `done`.
    """
    ro = _open_readonly()
    try:
        page_block = load_page_context(
            ro,
            req.page_context.model_dump() if req.page_context else None,
        )
        system_blocks = _build_system_prompt_blocks(page_block)

        # Anthropic accepts plain string content for user messages; we
        # promote later turns to block lists when we add tool_result.
        api_messages: list[dict] = [
            {"role": m.role, "content": m.content} for m in req.messages
        ]

        client = _make_anthropic_client()

        tool_calls = 0
        cumulative_output_tokens = 0
        agg_input = agg_output = agg_cached = 0

        for _ in range(MAX_TOOL_CALLS + 1):
            stream_cm = client.messages.stream(
                model=DEFAULT_MODEL,
                max_tokens=MAX_OUTPUT_TOKENS,
                system=system_blocks,
                tools=TOOL_DEFINITIONS,
                messages=api_messages,
            )

            with stream_cm as stream:
                # Anthropic SDK iterates RAW events:
                #   content_block_delta → delta is TextDelta or InputJSONDelta
                #   content_block_start / content_block_stop / message_*
                # We only forward text deltas to the browser; tool_use
                # blocks are pulled from the resolved final message after
                # the stream ends, since their input only fully exists
                # there.
                for event in stream:
                    etype = getattr(event, "type", None)
                    if etype != "content_block_delta":
                        continue
                    delta = getattr(event, "delta", None)
                    if delta is None or getattr(delta, "type", None) != "text_delta":
                        continue
                    text = getattr(delta, "text", "")
                    if text:
                        yield _sse("text_delta", {"delta": text})

                # Stream is done. Pull the resolved message + usage.
                final = stream.get_final_message()

            stop_reason = final.stop_reason
            usage = final.usage  # SDK Usage model
            agg_input += getattr(usage, "input_tokens", 0) or 0
            agg_output += getattr(usage, "output_tokens", 0) or 0
            agg_cached += getattr(usage, "cache_read_input_tokens", 0) or 0
            cumulative_output_tokens += getattr(usage, "output_tokens", 0) or 0

            # Persist the assistant turn so the next call sees it.
            assistant_blocks = [_block_to_dict(b) for b in final.content]
            api_messages.append({"role": "assistant", "content": assistant_blocks})

            # If Claude requested tools, execute them in document order
            # and stream tool_use_start / tool_use_end SSE events.
            tool_results: list[dict] = []
            for block in final.content:
                if getattr(block, "type", None) != "tool_use":
                    continue
                tool_calls += 1
                tool_id = block.id
                yield _sse("tool_use_start", {
                    "id": tool_id, "name": block.name, "input": block.input,
                })
                result = _execute_tool(block.name, block.input, ro)
                ok = "error" not in result
                summary: dict = {"id": tool_id, "ok": ok}
                if not ok:
                    summary["error"] = result["error"]
                elif block.name == "run_sql":
                    summary["row_count"] = result.get("row_count", 0)
                    summary["truncated"] = result.get("truncated", False)
                    summary["elapsed_ms"] = result.get("elapsed_ms")
                yield _sse("tool_use_end", summary)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": json.dumps(result),
                })

            if stop_reason != "tool_use" or not tool_results:
                break  # Conversation turn complete.

            if tool_calls >= MAX_TOOL_CALLS:
                yield _sse("text_delta", {
                    "delta": "\n\n_(stopped after 15 tool calls — ask a more specific question to continue.)_",
                })
                break
            if cumulative_output_tokens >= MAX_OUTPUT_TOKENS_PER_CONVERSATION:
                yield _sse("text_delta", {
                    "delta": "\n\n_(stopped at output-token cap.)_",
                })
                break

            # Append the tool results and loop for the next turn.
            api_messages.append({"role": "user", "content": tool_results})

        # Persist usage row.
        first_user = next(
            (m.content for m in req.messages if m.role == "user"),
            "",
        )[:200]
        rw_conn.execute(
            "INSERT INTO ai_usage (user_id, input_tokens, output_tokens, "
            "cached_tokens, tool_calls, model, route_at_open, first_user_message) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                user.get("sub"),
                agg_input, agg_output, agg_cached,
                tool_calls, DEFAULT_MODEL,
                req.route_at_open, first_user,
            ),
        )
        rw_conn.commit()

        yield _sse("done", {
            "stop_reason": "end_turn",
            "tool_calls": tool_calls,
            "input_tokens": agg_input,
            "output_tokens": agg_output,
            "cached_tokens": agg_cached,
        })
    finally:
        ro.close()


# ── Router ───────────────────────────────────────────────────────────


router = APIRouter()


@router.post("/chat")
def chat(
    body: ChatRequest,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    if not body.messages:
        raise HTTPException(status_code=400, detail="messages must not be empty")

    return StreamingResponse(
        _stream_chat(body, user, db),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
