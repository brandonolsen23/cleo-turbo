"""
Migration 034: extend brand_stem.stem_type CHECK constraint to allow 2-gram
and 3-gram stems.

The multi-level n-gram picker emits stem_type values 'distinctive_2g' and
'distinctive_3g' when the canonical stem is a multi-word brand identifier
("marlin spring", "sun life assurance"). The original CHECK allowed only
('distinctive', 'position_anchor'). Adds the two new values.

SQLite doesn't support ALTER on CHECK constraints — rebuild the table with
the relaxed CHECK, preserving rows.
"""

import sqlite3
import os


def migrate(conn):
    print("Migration 034: relaxing brand_stem.stem_type CHECK for n-gram stems...")

    conn.executescript("""
        CREATE TABLE brand_stem_new (
            stem                  TEXT PRIMARY KEY,
            stem_type             TEXT NOT NULL CHECK (
                stem_type IN ('distinctive', 'position_anchor',
                              'distinctive_2g', 'distinctive_3g')
            ),
            dominant_anchor_type  TEXT NOT NULL,
            dominant_anchor_value TEXT NOT NULL,
            dominance_share       REAL NOT NULL,
            volume                INTEGER NOT NULL,
            verified_at           TEXT DEFAULT (datetime('now'))
        );

        INSERT INTO brand_stem_new SELECT * FROM brand_stem;

        DROP TABLE brand_stem;
        ALTER TABLE brand_stem_new RENAME TO brand_stem;
    """)
    conn.commit()
    print("Migration 034 complete.")


if __name__ == "__main__":
    db_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "cleo.db")
    conn = sqlite3.connect(db_path)
    migrate(conn)
    conn.close()
