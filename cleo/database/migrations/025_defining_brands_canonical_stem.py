"""
Migration 025: Add canonical_stem to defining_brands.

The override needs to specify *which* auto_group/stem the rule applies to,
so we can disambiguate cases like "cadillac" — the token applies to Cadillac
Fairview, NOT Myers Cadillac (car dealership). Without canonical_stem the
expansion has no way to know which entity a defining-brand rule means.

Existing rows get a default canonical_stem == ngram (one-word coined brands
where this is correct).
"""

import sqlite3
import os


def migrate(conn):
    print("Migration 025: adding canonical_stem to defining_brands...")
    conn.executescript("""
        ALTER TABLE defining_brands ADD COLUMN canonical_stem TEXT;
        CREATE INDEX IF NOT EXISTS idx_defining_brands_stem ON defining_brands(canonical_stem);
    """)
    # Backfill: for 1-gram rules, the stem defaults to the ngram itself
    conn.execute(
        "UPDATE defining_brands SET canonical_stem = ngram WHERE canonical_stem IS NULL AND level = '1gram'"
    )
    conn.commit()
    print("Migration 025 complete.")


if __name__ == "__main__":
    db_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "cleo.db")
    conn = sqlite3.connect(db_path)
    migrate(conn)
    conn.close()
