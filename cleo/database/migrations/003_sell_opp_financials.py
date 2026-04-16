"""
Migration 003: Add financial fields to sell_opportunities.

NOI + Cap Rate → Expected Price → Expected Price × Commission % → Deal Value
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "cleo.db")


def run(db_path: str = DB_PATH):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Check which columns already exist
    existing = {row[1] for row in cur.execute("PRAGMA table_info(sell_opportunities)").fetchall()}

    new_columns = [
        ("noi", "INTEGER"),
        ("expected_cap_rate", "REAL"),
        ("expected_price", "INTEGER"),
        ("commission_pct", "REAL"),
    ]

    for col_name, col_type in new_columns:
        if col_name not in existing:
            cur.execute(f"ALTER TABLE sell_opportunities ADD COLUMN {col_name} {col_type}")
            print(f"  Added column: {col_name} ({col_type})")
        else:
            print(f"  Column already exists: {col_name}")

    conn.commit()
    conn.close()
    print("Migration 003 complete.")


if __name__ == "__main__":
    run()
