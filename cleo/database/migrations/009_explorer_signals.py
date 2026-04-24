"""
Migration 009: Explorer external-signal columns + industry_stopwords CRM table.

Extends brand_token_summary with columns carrying external signals about
each token: wordfreq Zipf score, dictionary-word flag, place-name flag,
industry-stopword flag, and a human-readable filter reason.

Adds a persistent industry_stopwords table (CRM-style — not rebuilt by
the index builder) that the user curates via the Explorer UI.
"""

import sqlite3
import os


def migrate(conn):
    print("Migration 009: adding Explorer signal columns + industry_stopwords...")

    # Add signal columns to brand_token_summary (idempotent — check column existence first).
    cols = {r[1] for r in conn.execute("PRAGMA table_info(brand_token_summary)")}
    for col, ddl in [
        ("wordfreq_zipf",        "ALTER TABLE brand_token_summary ADD COLUMN wordfreq_zipf REAL"),
        ("is_english_common",    "ALTER TABLE brand_token_summary ADD COLUMN is_english_common INTEGER"),
        ("is_place_name",        "ALTER TABLE brand_token_summary ADD COLUMN is_place_name INTEGER"),
        ("is_industry_stopword", "ALTER TABLE brand_token_summary ADD COLUMN is_industry_stopword INTEGER"),
        ("filter_reason",        "ALTER TABLE brand_token_summary ADD COLUMN filter_reason TEXT"),
    ]:
        if col not in cols:
            conn.execute(ddl)

    # Persistent table for the curated industry stopword list.
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS industry_stopwords (
            token        TEXT PRIMARY KEY,
            added_by     TEXT,
            added_at     TEXT DEFAULT (datetime('now')),
            source       TEXT NOT NULL CHECK (source IN ('seed','user'))
        );
    """)

    conn.commit()
    print("Migration 009 complete.")


if __name__ == "__main__":
    db_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "cleo.db")
    conn = sqlite3.connect(db_path)
    migrate(conn)
    conn.close()
