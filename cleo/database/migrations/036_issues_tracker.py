"""
Migration 036: in-app issue tracker.

Lets users file specific data-quality and UI bugs from any component in the UI
via a hover-revealed 'i' button. The component identity + component-specific
data (e.g. the source_id of a transactions-table row) pin down exactly which
element of which page is being reported, so Claude in a future chat can read
the issue and dive in with full context.

Schema design notes:
- categories is a JSON array (e.g. ["rt_property_mismatch", "parcel_geometry_wrong"])
  because real issues often span multiple categories. The 11 allowed values are
  enforced at the API layer, not the DB, since SQLite can't CHECK array members.
- component / component_data_json identify the exact UI element clicked.
  Free-form strings — no controlled vocabulary — so new components can be
  reported without DB schema changes.
- severity is captured but hidden in the report form; auto-derived from the
  highest-severity category (parcel_mismatch=high, ui issues=low, etc.). Visible
  in the list/detail UI.

This is a CRM table — registered in CRM_TABLES and never rebuilt by the compiler.
"""

import sqlite3
import os


CATEGORIES = (
    'rt_property_mismatch',
    'parcel_geometry_wrong',
    'wrong_owner',
    'group_clustering_issue',
    'parsing_error',
    'missing_data',
    'duplicate_entity',
    'formatting_issue',
    'layout_issue',
    'wrong_calculation',
    'other',
)


def migrate(conn):
    print("Migration 036: creating issues table...")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS issues (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            -- What the issue is about (page-level anchor)
            entity_type       TEXT NOT NULL CHECK (entity_type IN
                                ('property','contact','group','transaction',
                                 'auto_group','general')),
            entity_id         TEXT,
            -- Component-level anchor (which UI element on the page)
            component         TEXT,
            component_data_json TEXT,
            -- Classification (categories is a JSON array of category strings)
            categories        TEXT NOT NULL,
            severity          TEXT NOT NULL DEFAULT 'medium'
                                CHECK (severity IN ('low','medium','high','critical')),
            -- Content
            title             TEXT NOT NULL,
            description       TEXT NOT NULL,
            -- Lifecycle
            status            TEXT NOT NULL DEFAULT 'open'
                                CHECK (status IN ('open','in_progress','resolved',
                                                  'wontfix','duplicate')),
            reported_by       TEXT NOT NULL,
            reported_at       TEXT DEFAULT (datetime('now')),
            resolved_by       TEXT,
            resolved_at       TEXT,
            resolution_notes  TEXT,
            fixed_in_commit   TEXT,
            updated_at        TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_issues_status   ON issues(status);
        CREATE INDEX IF NOT EXISTS idx_issues_entity   ON issues(entity_type, entity_id);
        CREATE INDEX IF NOT EXISTS idx_issues_severity ON issues(severity);
        CREATE INDEX IF NOT EXISTS idx_issues_reported ON issues(reported_at DESC);
    """)
    conn.commit()
    print(f"Migration 036 complete. {len(CATEGORIES)} categories supported: {', '.join(CATEGORIES)}")


if __name__ == "__main__":
    db_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "cleo.db")
    conn = sqlite3.connect(db_path)
    migrate(conn)
    conn.close()
