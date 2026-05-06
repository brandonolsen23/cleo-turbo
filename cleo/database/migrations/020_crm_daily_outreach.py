"""
Migration 020: CRM daily-outreach foundations.

Adds:
- user_stars table (per-user favourites/queue)
- lists.owner_user_id + lists.scope (personal/shared)
- activities.created_by_user_id (FK), source, external_id, happened_at
- activities.contact_id / property_id / group_id (multi-entity FKs)
- Indexes on the new activity FK columns and (source, external_id) for dedupe
- Backfill: existing lists -> scope='shared'; existing activities ->
  populate FKs from primary entity_type/entity_id, deriving from parent
  records for sell_opportunity / buy_mandate / deal types.

Idempotent: rerunning is a no-op (uses IF NOT EXISTS / column-exists guards).
"""
from __future__ import annotations
import sqlite3


def _column_exists(conn: sqlite3.Connection, table: str, col: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == col for r in rows)


def _add_column_if_missing(conn: sqlite3.Connection, table: str, col_def: str) -> None:
    """col_def is like 'scope TEXT NOT NULL DEFAULT \\'personal\\''"""
    col_name = col_def.split()[0]
    if not _column_exists(conn, table, col_name):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")


def migrate(conn: sqlite3.Connection) -> None:
    print("Migration 020: CRM daily-outreach schema...")

    # 1. user_stars table
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS user_stars (
            user_id      INTEGER NOT NULL REFERENCES users(id),
            entity_type  TEXT    NOT NULL CHECK(entity_type IN ('contact','property','group')),
            entity_id    TEXT    NOT NULL,
            starred_at   TEXT    DEFAULT (datetime('now')),
            PRIMARY KEY (user_id, entity_type, entity_id)
        );
        CREATE INDEX IF NOT EXISTS idx_user_stars_user   ON user_stars(user_id);
        CREATE INDEX IF NOT EXISTS idx_user_stars_entity ON user_stars(entity_type, entity_id);
    """)

    # 2. lists scope + owner
    _add_column_if_missing(conn, "lists", "owner_user_id INTEGER REFERENCES users(id)")
    _add_column_if_missing(conn, "lists", "scope TEXT NOT NULL DEFAULT 'personal'")
    # Backfill: pre-existing lists were team-shared in the pre-scope model
    conn.execute("UPDATE lists SET scope = 'shared' WHERE owner_user_id IS NULL AND scope = 'personal'")

    # 3. activities new columns
    _add_column_if_missing(conn, "activities", "created_by_user_id INTEGER REFERENCES users(id)")
    _add_column_if_missing(conn, "activities", "source TEXT NOT NULL DEFAULT 'manual'")
    _add_column_if_missing(conn, "activities", "external_id TEXT")
    _add_column_if_missing(conn, "activities", "happened_at TEXT")
    _add_column_if_missing(conn, "activities", "contact_id  TEXT REFERENCES contacts(id)")
    _add_column_if_missing(conn, "activities", "property_id TEXT REFERENCES properties(id)")
    _add_column_if_missing(conn, "activities", "group_id    TEXT REFERENCES groups(id)")

    # 4. activities backfill — happened_at, primary FKs
    conn.execute("UPDATE activities SET happened_at = created_at WHERE happened_at IS NULL")
    conn.execute("UPDATE activities SET contact_id  = entity_id WHERE entity_type='contact'  AND contact_id  IS NULL")
    conn.execute("UPDATE activities SET group_id    = entity_id WHERE entity_type='group'    AND group_id    IS NULL")
    # No 'property' rows pre-migration (route blocked it)

    # 5. activities backfill — parent-record FKs for sell_opp / buy_mandate / deal
    conn.execute("""
        UPDATE activities SET
            contact_id  = COALESCE(contact_id,  (SELECT seller_contact_id FROM sell_opportunities WHERE id = activities.entity_id)),
            group_id    = COALESCE(group_id,    (SELECT seller_group_id   FROM sell_opportunities WHERE id = activities.entity_id)),
            property_id = COALESCE(property_id, (SELECT property_id       FROM sell_opportunities WHERE id = activities.entity_id))
        WHERE entity_type = 'sell_opportunity'
    """)
    conn.execute("""
        UPDATE activities SET
            contact_id = COALESCE(contact_id, (SELECT contact_id FROM buy_mandates WHERE id = activities.entity_id)),
            group_id   = COALESCE(group_id,   (SELECT group_id   FROM buy_mandates WHERE id = activities.entity_id))
        WHERE entity_type = 'buy_mandate'
    """)
    conn.execute("""
        UPDATE activities SET
            property_id = COALESCE(property_id, (SELECT property_id FROM deals WHERE id = activities.entity_id)),
            group_id    = COALESCE(group_id,    (SELECT group_id   FROM deals WHERE id = activities.entity_id))
        WHERE entity_type = 'deal'
    """)

    # 6. activities indexes
    conn.executescript("""
        CREATE INDEX IF NOT EXISTS idx_activities_contact  ON activities(contact_id);
        CREATE INDEX IF NOT EXISTS idx_activities_property ON activities(property_id);
        CREATE INDEX IF NOT EXISTS idx_activities_group    ON activities(group_id);
        CREATE INDEX IF NOT EXISTS idx_activities_user     ON activities(created_by_user_id);
        CREATE INDEX IF NOT EXISTS idx_activities_dedupe   ON activities(source, external_id);
    """)

    conn.commit()
    print("Migration 020: done.")


if __name__ == "__main__":
    from cleo.database.connection import get_connection
    conn = get_connection()
    migrate(conn)
    conn.close()
