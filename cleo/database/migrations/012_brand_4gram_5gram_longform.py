"""
Migration 012: Brand 4-gram / 5-gram / 6+ long-form silo tables.

Extends the n-gram coverage so institutional entities and the long
tail of multi-token brand_phrases get their own indexes:

  - brand_fourgram_index + brand_fourgram_summary  (4-token windows)
  - brand_fivegram_index + brand_fivegram_summary  (5-token windows)
  - brand_long_phrase_index + brand_long_phrase_summary
        (one row per distinct full phrase with >= 6 tokens after
         stopword stripping; n_tokens column shows actual length)

No clustering, no inference. Pure additional indexes.
"""

import sqlite3
import os


def migrate(conn):
    print("Migration 012: creating 4-gram / 5-gram / long-form silo tables...")

    conn.executescript("""
        -- ── Brand 4-grams ──────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS brand_fourgram_index (
            fourgram     TEXT NOT NULL,
            source_id    TEXT NOT NULL,
            side         TEXT NOT NULL CHECK (side IN ('buyer','seller')),
            PRIMARY KEY (fourgram, source_id, side)
        );
        CREATE INDEX IF NOT EXISTS idx_b4i_side ON brand_fourgram_index(source_id, side);

        CREATE TABLE IF NOT EXISTS brand_fourgram_summary (
            fourgram               TEXT PRIMARY KEY,
            token_a                TEXT NOT NULL,
            token_b                TEXT NOT NULL,
            token_c                TEXT NOT NULL,
            token_d                TEXT NOT NULL,
            idf                    REAL NOT NULL,
            n_party_sides          INTEGER NOT NULL,
            n_distinct_phrases     INTEGER NOT NULL,
            any_token_distinctive  INTEGER NOT NULL,
            any_token_excluded     INTEGER NOT NULL,
            all_english            INTEGER NOT NULL,
            all_place              INTEGER NOT NULL,
            all_industry           INTEGER NOT NULL,
            is_distinctive         INTEGER NOT NULL,
            discovered_at          TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_b4s_n ON brand_fourgram_summary(n_party_sides);
        CREATE INDEX IF NOT EXISTS idx_b4s_idf ON brand_fourgram_summary(idf);
        CREATE INDEX IF NOT EXISTS idx_b4s_token_a ON brand_fourgram_summary(token_a);

        -- ── Brand 5-grams ──────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS brand_fivegram_index (
            fivegram     TEXT NOT NULL,
            source_id    TEXT NOT NULL,
            side         TEXT NOT NULL CHECK (side IN ('buyer','seller')),
            PRIMARY KEY (fivegram, source_id, side)
        );
        CREATE INDEX IF NOT EXISTS idx_b5i_side ON brand_fivegram_index(source_id, side);

        CREATE TABLE IF NOT EXISTS brand_fivegram_summary (
            fivegram               TEXT PRIMARY KEY,
            token_a                TEXT NOT NULL,
            token_b                TEXT NOT NULL,
            token_c                TEXT NOT NULL,
            token_d                TEXT NOT NULL,
            token_e                TEXT NOT NULL,
            idf                    REAL NOT NULL,
            n_party_sides          INTEGER NOT NULL,
            n_distinct_phrases     INTEGER NOT NULL,
            any_token_distinctive  INTEGER NOT NULL,
            any_token_excluded     INTEGER NOT NULL,
            all_english            INTEGER NOT NULL,
            all_place              INTEGER NOT NULL,
            all_industry           INTEGER NOT NULL,
            is_distinctive         INTEGER NOT NULL,
            discovered_at          TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_b5s_n ON brand_fivegram_summary(n_party_sides);
        CREATE INDEX IF NOT EXISTS idx_b5s_idf ON brand_fivegram_summary(idf);
        CREATE INDEX IF NOT EXISTS idx_b5s_token_a ON brand_fivegram_summary(token_a);

        -- ── Brand long-form (6+ tokens) ────────────────────────────────
        CREATE TABLE IF NOT EXISTS brand_long_phrase_index (
            phrase       TEXT NOT NULL,
            source_id    TEXT NOT NULL,
            side         TEXT NOT NULL CHECK (side IN ('buyer','seller')),
            PRIMARY KEY (phrase, source_id, side)
        );
        CREATE INDEX IF NOT EXISTS idx_blpi_side ON brand_long_phrase_index(source_id, side);

        CREATE TABLE IF NOT EXISTS brand_long_phrase_summary (
            phrase                    TEXT PRIMARY KEY,
            n_tokens                  INTEGER NOT NULL,
            idf                       REAL NOT NULL,
            n_party_sides             INTEGER NOT NULL,
            n_distinct_source_phrases INTEGER NOT NULL,
            any_token_distinctive     INTEGER NOT NULL,
            any_token_excluded        INTEGER NOT NULL,
            all_english               INTEGER NOT NULL,
            all_place                 INTEGER NOT NULL,
            all_industry              INTEGER NOT NULL,
            is_distinctive            INTEGER NOT NULL,
            discovered_at             TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_blps_n ON brand_long_phrase_summary(n_party_sides);
        CREATE INDEX IF NOT EXISTS idx_blps_n_tokens ON brand_long_phrase_summary(n_tokens);
    """)
    conn.commit()
    print("Migration 012 complete.")


if __name__ == "__main__":
    db_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "cleo.db")
    conn = sqlite3.connect(db_path)
    migrate(conn)
    conn.close()
