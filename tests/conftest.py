"""Shared pytest fixtures for Layer 2 (discovery_v2) test suites."""
import sqlite3
import pytest


_DDL = """
CREATE TABLE party_fingerprints (
    source_id TEXT, side TEXT, phone TEXT, contact_fingerprint TEXT,
    street_number TEXT, street_name TEXT, street_suffix TEXT,
    PRIMARY KEY (source_id, side)
);
CREATE TABLE party_atoms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT, side TEXT, atom_type TEXT, atom_value TEXT, source_field TEXT
);
CREATE TABLE brand_token_summary (
    token TEXT PRIMARY KEY, idf REAL, n_party_sides INTEGER,
    n_distinct_phrases INTEGER, is_distinctive INTEGER, is_excluded INTEGER,
    wordfreq_zipf REAL, is_english_common INTEGER, is_place_name INTEGER,
    is_industry_stopword INTEGER, filter_reason TEXT,
    position_consistency REAL, total_child_coverage REAL,
    is_position_anchor INTEGER NOT NULL DEFAULT 0,
    discovered_at TEXT
);
CREATE TABLE brand_stem (
    stem TEXT PRIMARY KEY, stem_type TEXT NOT NULL,
    dominant_anchor_type TEXT NOT NULL, dominant_anchor_value TEXT NOT NULL,
    dominance_share REAL NOT NULL, volume INTEGER NOT NULL, verified_at TEXT
);
CREATE TABLE brand_stem_phrase_map (
    phrase TEXT PRIMARY KEY, stem TEXT NOT NULL, confidence REAL NOT NULL
);
CREATE TABLE anchor_uniqueness (
    anchor_type TEXT NOT NULL, anchor_value TEXT NOT NULL,
    dominant_stem TEXT, dominance_share REAL,
    volume INTEGER NOT NULL, score REAL NOT NULL,
    is_service_provider INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (anchor_type, anchor_value)
);
CREATE TABLE auto_groups (
    auto_group_id TEXT PRIMARY KEY, canonical_stem TEXT NOT NULL,
    display_name TEXT NOT NULL, tier TEXT NOT NULL,
    confidence REAL NOT NULL, n_anchors INTEGER NOT NULL,
    n_members INTEGER NOT NULL, discovered_at TEXT
);
CREATE TABLE auto_group_anchors (
    auto_group_id TEXT NOT NULL, anchor_type TEXT NOT NULL,
    anchor_value TEXT NOT NULL, score REAL NOT NULL,
    PRIMARY KEY (auto_group_id, anchor_type, anchor_value)
);
CREATE TABLE auto_group_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    auto_group_id TEXT NOT NULL,
    member_type TEXT NOT NULL,
    source_id TEXT, side TEXT, corp_name TEXT,
    match_score REAL NOT NULL
);
CREATE TABLE auto_group_overrides (
    id INTEGER PRIMARY KEY AUTOINCREMENT, auto_group_id TEXT NOT NULL,
    action TEXT NOT NULL, user_id TEXT NOT NULL, action_at TEXT, notes TEXT
);
CREATE TABLE auto_group_merges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_auto_group_id TEXT NOT NULL, child_auto_group_id TEXT NOT NULL,
    user_id TEXT NOT NULL, action_at TEXT, notes TEXT
);
CREATE TABLE auto_anchor_overrides (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    anchor_type TEXT NOT NULL, anchor_value TEXT NOT NULL,
    override_stem TEXT, override_service_provider INTEGER NOT NULL DEFAULT 0,
    user_id TEXT NOT NULL, action_at TEXT
);
"""


@pytest.fixture
def discovery_v2_db():
    """Fresh in-memory DB with all Layer 2 derived + CRM tables.

    Pre-seeds brand_token_summary with 'skyline' (distinctive). Add more tokens
    in the test itself if you need other operators.
    """
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript(_DDL)
    conn.execute(
        """INSERT INTO brand_token_summary
             (token, idf, n_party_sides, n_distinct_phrases, is_distinctive,
              is_excluded, wordfreq_zipf, is_english_common, is_place_name,
              is_industry_stopword, filter_reason, position_consistency,
              total_child_coverage, is_position_anchor, discovered_at)
           VALUES ('skyline', 6.13, 100, 10, 1, 0, 0.0, 0, 0, 0, NULL, NULL, NULL, 0, '2026')"""
    )
    yield conn
    conn.close()


def seed_party_side(conn, sid, side, phrase, *, phone=None, contact=None,
                    street_number=None, street_name=None, street_suffix=None):
    """Seed a single party-side with optional phrase + anchors."""
    conn.execute(
        """INSERT OR IGNORE INTO party_fingerprints
             (source_id, side, phone, contact_fingerprint,
              street_number, street_name, street_suffix)
           VALUES (?,?,?,?,?,?,?)""",
        (sid, side, phone, contact, street_number, street_name, street_suffix),
    )
    if phrase:
        conn.execute(
            "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
            "VALUES (?, ?, 'brand_phrase', ?, 'party_name')",
            (sid, side, phrase),
        )
