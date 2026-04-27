"""
Migration 013: position-anchor columns on brand_token_summary.

Adds three columns capturing whether a 1-gram acts as a position-
consistent prefix anchor for an operator family even when it gets
filtered by wordfreq/place/industry signals (the `dh` case).

Idempotent (skips columns that already exist).
"""

import sqlite3
import os


def migrate(conn):
    print("Migration 013: adding position-anchor columns to brand_token_summary...")

    cols = {r[1] for r in conn.execute("PRAGMA table_info(brand_token_summary)")}
    for col, ddl in [
        ("position_consistency", "ALTER TABLE brand_token_summary ADD COLUMN position_consistency REAL"),
        ("total_child_coverage", "ALTER TABLE brand_token_summary ADD COLUMN total_child_coverage REAL"),
        ("is_position_anchor",   "ALTER TABLE brand_token_summary ADD COLUMN is_position_anchor INTEGER NOT NULL DEFAULT 0"),
    ]:
        if col not in cols:
            conn.execute(ddl)
    conn.commit()
    print("Migration 013 complete.")


if __name__ == "__main__":
    db_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "cleo.db")
    conn = sqlite3.connect(db_path)
    migrate(conn)
    conn.close()
