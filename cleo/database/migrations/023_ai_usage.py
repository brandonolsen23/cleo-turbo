"""Migration 023: ai_usage table — per-conversation token logging.

System table; never dropped, never rebuilt by the compiler.

Idempotent: rerunning is a no-op.

Run via:
    python -m cleo.database.migrations.023_ai_usage
"""

from __future__ import annotations

import sqlite3


def migrate(conn: sqlite3.Connection) -> None:
    print("Migration 023: ai_usage")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS ai_usage (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id            INTEGER REFERENCES users(id),
            created_at         TEXT DEFAULT (datetime('now')),
            input_tokens       INTEGER NOT NULL DEFAULT 0,
            output_tokens      INTEGER NOT NULL DEFAULT 0,
            cached_tokens      INTEGER NOT NULL DEFAULT 0,
            tool_calls         INTEGER NOT NULL DEFAULT 0,
            model              TEXT,
            route_at_open      TEXT,
            first_user_message TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_ai_usage_user ON ai_usage(user_id);
        CREATE INDEX IF NOT EXISTS idx_ai_usage_created_at ON ai_usage(created_at);
        """
    )
    conn.commit()
    print("Migration 023: done.")


if __name__ == "__main__":
    from cleo.database.connection import get_connection
    conn = get_connection()
    migrate(conn)
    conn.close()
