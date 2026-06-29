"""
Migration 024: User-curated `defining_brands` table.

Parallel to industry_stopwords and places. When a token is marked as a defining
brand, the brand-index builder forces is_distinctive=1 regardless of Zipf
(English-common) score. This corrects the systemic under-clustering of real CRE
brands that happen to be English words (starlight, summit, crown, cadillac,
phoenix, sterling, etc.).

Schema mirrors the level-flexible n-gram model so the same override can apply
to bigrams, trigrams, etc. in future work. For now `level = '1gram'` is the
only supported value.
"""

import sqlite3
import os


def migrate(conn):
    print("Migration 024: creating defining_brands curation table...")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS defining_brands (
            ngram          TEXT NOT NULL,
            level          TEXT NOT NULL CHECK (level IN ('1gram','2gram','3gram','4gram','5gram','long-form')),
            group_id       TEXT REFERENCES groups(id),
            canonical_name TEXT,
            added_by       TEXT,
            added_at       TEXT DEFAULT (datetime('now')),
            source         TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('seed','user','ai_suggested')),
            notes          TEXT,
            PRIMARY KEY (ngram, level)
        );

        CREATE INDEX IF NOT EXISTS idx_defining_brands_group ON defining_brands(group_id);
        CREATE INDEX IF NOT EXISTS idx_defining_brands_level ON defining_brands(level);
    """)
    conn.commit()
    print("Migration 024 complete.")


if __name__ == "__main__":
    db_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "cleo.db")
    conn = sqlite3.connect(db_path)
    migrate(conn)
    conn.close()
