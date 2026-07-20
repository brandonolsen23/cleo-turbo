"""
Migration 040: source_date on transactions and gw_assessments.

Adds a nullable source_date column (YYYY-MM-DD) recording when the source data
was obtained — RT scrape date parsed from source_folder ('_daily/DATE_.../pNNN'),
GW download date parsed from source_file ('geowarehouse-<ISO>.html'). The
compiler (cleo/compiler/writer.py) derives it deterministically on every
rebuild, so it survives the derived-table drop with no persistence. The
dashboard "Recent Records" panel sorts by it (falling back to created_at) so it
stops re-dating everything to the last rebuild time.

Canonical DDL lives in cleo/database/schema.py; a full rebuild recreates the
tables with this column. This migration is for adding the column to an existing
live DB without a rebuild — purely additive (ALTER TABLE ADD COLUMN), idempotent.

Usage (refuses to run without an explicit DB path — always a COPY first):
    .venv/bin/python cleo/database/migrations/040_source_date.py /tmp/cleo_test.db
"""

import os
import sqlite3
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, REPO_ROOT)


def _has_column(conn, table, column):
    cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    return column in cols


def migrate(conn):
    print("Migration 040: source_date ...")
    for table in ("transactions", "gw_assessments"):
        if _has_column(conn, table, "source_date"):
            print(f"  {table}.source_date already present — skipping")
            continue
        conn.execute(f"ALTER TABLE {table} ADD COLUMN source_date TEXT")
        print(f"  added {table}.source_date")
    conn.commit()

    missing = [t for t in ("transactions", "gw_assessments")
               if not _has_column(conn, t, "source_date")]
    if missing:
        print(f"  ERROR — still missing source_date on: {missing}")
        return 1
    print("Migration 040 complete.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python cleo/database/migrations/040_source_date.py path/to/cleo.db")
        print("Refusing to guess the DB path. Test against a COPY before the live file.")
        sys.exit(2)
    conn = sqlite3.connect(sys.argv[1])
    rc = migrate(conn)
    conn.close()
    sys.exit(rc)
