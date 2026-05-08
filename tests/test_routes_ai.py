"""Tests for /api/ai/chat — the AI sidebar SSE endpoint."""

import json
import sqlite3
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


def _seed(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE,
            password_hash TEXT, display_name TEXT, role TEXT DEFAULT 'editor'
        );
        CREATE TABLE properties (
            id TEXT PRIMARY KEY, display_address TEXT, city TEXT,
            current_owner_name TEXT
        );
        CREATE TABLE contacts (id TEXT PRIMARY KEY, display_name TEXT, company_name TEXT);
        CREATE TABLE groups (id TEXT PRIMARY KEY, display_name TEXT, property_count INTEGER);
        CREATE TABLE deals (id TEXT PRIMARY KEY, name TEXT, stage TEXT);
        CREATE TABLE lists (id TEXT PRIMARY KEY, name TEXT, scope TEXT);
        CREATE TABLE transactions (
            source_id TEXT PRIMARY KEY, sale_date TEXT,
            display_address TEXT, sale_price INTEGER
        );
        CREATE TABLE ai_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, created_at TEXT DEFAULT (datetime('now')),
            input_tokens INTEGER, output_tokens INTEGER, cached_tokens INTEGER,
            tool_calls INTEGER, model TEXT, route_at_open TEXT,
            first_user_message TEXT
        );
        INSERT INTO users (id, username, password_hash, display_name)
            VALUES (1, 'brandon', 'x', 'Brandon');
        INSERT INTO properties VALUES
            ('PRO_84463', '325 Guelph Street', 'Georgetown', 'Crialmar Properties Limited');
        """
    )
    conn.commit()


@pytest.fixture
def client_with_mock(tmp_path):
    """Wire FastAPI with a real on-disk SQLite (so file:?mode=ro works)
    and a stub Anthropic client whose stream we control."""
    db_file = tmp_path / "ai.db"
    rw = sqlite3.connect(str(db_file), check_same_thread=False)
    rw.row_factory = sqlite3.Row
    _seed(rw)

    from cleo.web.app import create_app
    from cleo.web import deps
    app = create_app()

    def _get_db_override():
        yield rw
    app.dependency_overrides[deps.get_db] = _get_db_override
    app.dependency_overrides[deps.get_current_user] = lambda: {
        "sub": 1, "username": "brandon", "display_name": "Brandon", "role": "editor"
    }

    # Patch the route's anthropic client factory to a fake.
    import cleo.web.routes.ai as ai_route
    fake = _FakeAnthropicClient()
    monkey = patch.object(ai_route, "_make_anthropic_client", lambda: fake)
    monkey.start()

    # Tell the route which DB file to open in ?mode=ro.
    monkey2 = patch.object(ai_route, "_RO_DB_PATH", str(db_file))
    monkey2.start()

    yield TestClient(app), rw, fake

    monkey.stop()
    monkey2.stop()
    app.dependency_overrides.clear()
    rw.close()


# ── Fake Anthropic streaming client ────────────────────────────────
#
# Mirrors the slice of the SDK that the route actually consumes:
#   client.messages.stream(...) → context manager
#     iterating yields events with .type ("text" for text deltas)
#     stream.get_final_message() returns Message with
#         .content (list of TextBlock | ToolUseBlock)
#         .stop_reason
#         .usage (Usage with input_tokens / output_tokens / cache_read_input_tokens)
# The fakes use SimpleNamespace so .attr access matches the SDK shape.


from types import SimpleNamespace


def _text_event(text: str):
    """A raw content_block_delta event with a text_delta payload."""
    return SimpleNamespace(
        type="content_block_delta",
        index=0,
        delta=SimpleNamespace(type="text_delta", text=text),
    )


def _text_block(text: str):
    return SimpleNamespace(type="text", text=text)


def _tool_use_block(name: str, input_payload: dict, id_: str = "tool_1"):
    return SimpleNamespace(type="tool_use", id=id_, name=name, input=input_payload)


def _make_final(content: list, stop_reason: str = "end_turn",
                input_tokens: int = 100, output_tokens: int = 50,
                cache_read_input_tokens: int = 80):
    usage = SimpleNamespace(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_input_tokens=cache_read_input_tokens,
    )
    return SimpleNamespace(content=content, stop_reason=stop_reason, usage=usage)


class _FakeStream:
    """Yields the pre-baked text events; get_final_message() returns the
    pre-baked Message. Acts as its own context manager (the SDK does the
    same)."""

    def __init__(self, events: list, final):
        self._events = events
        self._final = final

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __iter__(self):
        return iter(self._events)

    def get_final_message(self):
        return self._final


class _FakeAnthropicClient:
    """The route calls `_make_anthropic_client()` then
    `client.messages.stream(...)`. We queue scripted (events, final)
    pairs so each stream() call peels off one turn."""

    def __init__(self):
        # Each entry: (events_list, final_message)
        self.scripts: list[tuple[list, object]] = []
        self.calls: list[dict] = []
        self.messages = self  # `client.messages.stream(...)` shape

    def stream(self, **kwargs):
        self.calls.append(kwargs)
        if not self.scripts:
            raise AssertionError("No script queued for this stream() call.")
        events, final = self.scripts.pop(0)
        return _FakeStream(events, final)


# ── Tests ──────────────────────────────────────────────────────────


def test_chat_simple_text_response(client_with_mock):
    client, conn, fake = client_with_mock
    fake.scripts.append((
        [_text_event("Hello "), _text_event("Brandon.")],
        _make_final(content=[_text_block("Hello Brandon.")]),
    ))

    resp = client.post(
        "/api/ai/chat",
        json={
            "messages": [{"role": "user", "content": "Hi"}],
            "page_context": None,
            "route_at_open": "/",
        },
    )
    assert resp.status_code == 200
    body = resp.text
    assert "Hello " in body and "Brandon." in body
    rows = conn.execute("SELECT * FROM ai_usage").fetchall()
    assert len(rows) == 1
    assert rows[0]["model"] == "claude-opus-4-7"
    assert rows[0]["first_user_message"].startswith("Hi")


def test_chat_runs_sql_tool(client_with_mock):
    client, conn, fake = client_with_mock
    # Turn 1: Claude requests run_sql (no streamed text).
    fake.scripts.append((
        [],
        _make_final(
            content=[_tool_use_block("run_sql", {"query": "SELECT id FROM properties"}, id_="t1")],
            stop_reason="tool_use",
        ),
    ))
    # Turn 2: Claude consumes the tool result and answers.
    fake.scripts.append((
        [_text_event("Found 1 property: PRO_84463")],
        _make_final(content=[_text_block("Found 1 property: PRO_84463")]),
    ))

    resp = client.post(
        "/api/ai/chat",
        json={
            "messages": [{"role": "user", "content": "List the properties."}],
            "page_context": None,
            "route_at_open": "/properties",
        },
    )
    assert resp.status_code == 200
    body = resp.text
    assert "PRO_84463" in body
    rows = conn.execute("SELECT tool_calls FROM ai_usage").fetchall()
    assert rows[0]["tool_calls"] == 1


def test_chat_rejects_writes_via_run_sql(client_with_mock):
    client, conn, fake = client_with_mock
    fake.scripts.append((
        [],
        _make_final(
            content=[_tool_use_block("run_sql", {"query": "DROP TABLE properties"}, id_="t1")],
            stop_reason="tool_use",
        ),
    ))
    fake.scripts.append((
        [_text_event("Sorry — only SELECT statements are allowed.")],
        _make_final(content=[_text_block("Sorry — only SELECT statements are allowed.")]),
    ))

    resp = client.post(
        "/api/ai/chat",
        json={
            "messages": [{"role": "user", "content": "Drop properties."}],
            "page_context": None,
            "route_at_open": "/",
        },
    )
    assert resp.status_code == 200
    assert "tool_use_end" in resp.text
    # The route forwards the InvalidQueryError text in the tool_use_end SSE.
    assert "Only SELECT" in resp.text or "SELECT" in resp.text


def test_chat_caps_tool_call_loop(client_with_mock):
    """Stop after MAX_TOOL_CALLS even if Claude keeps requesting tool_use."""
    client, conn, fake = client_with_mock
    # Queue 20 turns of run_sql, then one final answer (unreachable).
    for i in range(20):
        fake.scripts.append((
            [],
            _make_final(
                content=[_tool_use_block("run_sql", {"query": f"SELECT {i}"}, id_=f"t{i}")],
                stop_reason="tool_use",
            ),
        ))
    fake.scripts.append((
        [_text_event("done")],
        _make_final(content=[_text_block("done")]),
    ))

    resp = client.post(
        "/api/ai/chat",
        json={
            "messages": [{"role": "user", "content": "loop"}],
            "page_context": None,
            "route_at_open": "/",
        },
    )
    assert resp.status_code == 200
    rows = conn.execute("SELECT tool_calls FROM ai_usage").fetchall()
    assert rows[0]["tool_calls"] == 15


def test_chat_includes_page_context(client_with_mock):
    client, conn, fake = client_with_mock
    fake.scripts.append((
        [_text_event("ok")],
        _make_final(content=[_text_block("ok")]),
    ))
    client.post(
        "/api/ai/chat",
        json={
            "messages": [{"role": "user", "content": "this owner"}],
            "page_context": {"entity_type": "property", "id": "PRO_84463"},
            "route_at_open": "/properties/PRO_84463",
        },
    )
    sent = fake.calls[0]
    sysprompt = sent["system"] if isinstance(sent["system"], str) else "".join(
        b.get("text", "") for b in sent["system"]
    )
    assert "PRO_84463" in sysprompt
    assert "Crialmar" in sysprompt
