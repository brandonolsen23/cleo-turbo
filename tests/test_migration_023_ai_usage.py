"""Tests for migration 023: ai_usage table."""
import importlib
import sqlite3


def _bootstrap_pre_migration_db() -> sqlite3.Connection:
    """In-memory DB with just the users table the migration depends on."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'editor'
        );
        INSERT INTO users (id, username, password_hash, display_name)
            VALUES (1, 'brandon', 'x', 'Brandon');
        """
    )
    conn.commit()
    return conn


def _run_migration(conn: sqlite3.Connection) -> None:
    mod = importlib.import_module("cleo.database.migrations.023_ai_usage")
    mod.migrate(conn)


def test_ai_usage_table_created():
    conn = _bootstrap_pre_migration_db()
    _run_migration(conn)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(ai_usage)").fetchall()}
    expected = {
        "id", "user_id", "created_at", "input_tokens", "output_tokens",
        "cached_tokens", "tool_calls", "model", "route_at_open",
        "first_user_message",
    }
    assert expected <= cols, f"Missing columns: {expected - cols}"


def test_migration_is_idempotent():
    conn = _bootstrap_pre_migration_db()
    _run_migration(conn)
    _run_migration(conn)  # second run must be a no-op
    n = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='ai_usage'").fetchone()[0]
    assert n == 1


def test_insert_and_read():
    conn = _bootstrap_pre_migration_db()
    _run_migration(conn)
    conn.execute(
        "INSERT INTO ai_usage (user_id, input_tokens, output_tokens, cached_tokens, "
        "tool_calls, model, route_at_open, first_user_message) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (1, 1234, 567, 1000, 3, "claude-opus-4-7", "/properties/PRO_42", "tell me about this owner"),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM ai_usage WHERE user_id = 1").fetchone()
    assert row["input_tokens"] == 1234
    assert row["model"] == "claude-opus-4-7"
    assert row["created_at"] is not None  # default fired
