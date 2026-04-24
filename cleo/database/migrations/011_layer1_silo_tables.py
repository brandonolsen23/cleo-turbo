"""
Migration 011: Layer 1 silo tables.

Adds parallel base-level data silos for Phase 1 of portfolio discovery:
  - brand_bigram_index + brand_bigram_summary (2-token combos)
  - brand_trigram_index + brand_trigram_summary (3-token combos)
  - phone_summary (digit-only phones from party_fingerprints.phone)
  - address_base_summary (street_number + street_name + street_suffix triples)
  - contact_fingerprint_summary (first+last fingerprints)

No clustering, no inference. These are raw-data indexes.
"""

import sqlite3
import os


def migrate(conn):
    print("Migration 011: creating Layer 1 silo tables...")

    conn.executescript("""
        -- ── Brand bigrams ──────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS brand_bigram_index (
            bigram       TEXT NOT NULL,
            source_id    TEXT NOT NULL,
            side         TEXT NOT NULL CHECK (side IN ('buyer','seller')),
            PRIMARY KEY (bigram, source_id, side)
        );
        CREATE INDEX IF NOT EXISTS idx_bbi_side ON brand_bigram_index(source_id, side);

        CREATE TABLE IF NOT EXISTS brand_bigram_summary (
            bigram                 TEXT PRIMARY KEY,
            token_a                TEXT NOT NULL,
            token_b                TEXT NOT NULL,
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
        CREATE INDEX IF NOT EXISTS idx_bbs_n ON brand_bigram_summary(n_party_sides);
        CREATE INDEX IF NOT EXISTS idx_bbs_idf ON brand_bigram_summary(idf);

        -- ── Brand trigrams ─────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS brand_trigram_index (
            trigram      TEXT NOT NULL,
            source_id    TEXT NOT NULL,
            side         TEXT NOT NULL CHECK (side IN ('buyer','seller')),
            PRIMARY KEY (trigram, source_id, side)
        );
        CREATE INDEX IF NOT EXISTS idx_bti_side ON brand_trigram_index(source_id, side);

        CREATE TABLE IF NOT EXISTS brand_trigram_summary (
            trigram                TEXT PRIMARY KEY,
            token_a                TEXT NOT NULL,
            token_b                TEXT NOT NULL,
            token_c                TEXT NOT NULL,
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
        CREATE INDEX IF NOT EXISTS idx_bts_n ON brand_trigram_summary(n_party_sides);
        CREATE INDEX IF NOT EXISTS idx_bts_idf ON brand_trigram_summary(idf);

        -- ── Phones ─────────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS phone_summary (
            phone               TEXT PRIMARY KEY,
            n_party_sides       INTEGER NOT NULL,
            is_distinctive      INTEGER NOT NULL,
            discovered_at       TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_ps_n ON phone_summary(n_party_sides);

        -- ── Address bases ──────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS address_base_summary (
            street_number       TEXT NOT NULL,
            street_name         TEXT NOT NULL,
            street_suffix       TEXT NOT NULL,
            n_party_sides       INTEGER NOT NULL,
            n_distinct_suites   INTEGER NOT NULL,
            n_distinct_postals  INTEGER NOT NULL,
            is_distinctive      INTEGER NOT NULL,
            discovered_at       TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (street_number, street_name, street_suffix)
        );
        CREATE INDEX IF NOT EXISTS idx_abs_n ON address_base_summary(n_party_sides);

        -- ── Contact fingerprints ──────────────────────────────────────
        CREATE TABLE IF NOT EXISTS contact_fingerprint_summary (
            contact_fingerprint TEXT PRIMARY KEY,
            n_party_sides       INTEGER NOT NULL,
            is_distinctive      INTEGER NOT NULL,
            discovered_at       TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_cfs_n ON contact_fingerprint_summary(n_party_sides);
    """)
    conn.commit()
    print("Migration 011 complete.")


if __name__ == "__main__":
    db_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "cleo.db")
    conn = sqlite3.connect(db_path)
    migrate(conn)
    conn.close()
