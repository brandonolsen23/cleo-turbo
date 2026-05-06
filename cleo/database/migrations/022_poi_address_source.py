"""Migration 022: add ``pois.address_source`` provenance column.

Distinguishes addresses that came directly from OSM ``addr:*`` tags
(``'osm'``) from those derived later (``'reverse_geocoded'``,
``'reverse_geocode_failed'``). NULL means we have not yet attempted any
derivation for this row.

Idempotent: rerunning is a no-op.

Run via:
    python -m cleo.database.migrations.022_poi_address_source
"""

from __future__ import annotations

import sqlite3


def _column_exists(conn: sqlite3.Connection, table: str, col: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == col for r in rows)


def migrate(conn: sqlite3.Connection) -> None:
    print("Migration 022: pois.address_source")

    if not _column_exists(conn, "pois", "address_source"):
        conn.execute("ALTER TABLE pois ADD COLUMN address_source TEXT")
        # Backfill: every existing non-empty address came from OSM at compile
        # time, so it's safe to mark them 'osm'. Empty addresses stay NULL
        # so the backfill script can target them.
        cur = conn.execute(
            "UPDATE pois SET address_source = 'osm' "
            "WHERE address IS NOT NULL AND TRIM(address) != ''"
        )
        print(f"  added column; backfilled address_source='osm' on {cur.rowcount:,} rows")
    else:
        print("  column already exists — no-op")

    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_pois_address_source ON pois(address_source)"
    )

    conn.commit()
    print("Migration 022: done.")


if __name__ == "__main__":
    from cleo.database.connection import get_connection
    conn = get_connection()
    migrate(conn)
    conn.close()
