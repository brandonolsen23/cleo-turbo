"""
Migration 039: Market data — GoC bond_yields table.

Adds the bond_yields reference table (Bank of Canada Valet benchmark yields),
backfilled on app startup by cleo/rates/. Reference data, NOT derived from
clean-data/ and NOT in drop_derived_tables(). Canonical DDL lives in
cleo/database/schema.py (MARKET_DATA_TABLES); this migration reuses it verbatim.

Purely additive: CREATE TABLE/INDEX IF NOT EXISTS. Never drops or mutates data.
The app also creates this table idempotently on startup, so running this
migration is optional — it exists for parity and fresh-DB record-keeping.

Usage (refuses to run without an explicit DB path — always a COPY first):
    .venv/bin/python cleo/database/migrations/039_bond_yields.py /tmp/cleo_test.db
"""

import os
import sqlite3
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, REPO_ROOT)


def migrate(conn):
    from cleo.database.schema import MARKET_DATA_TABLES

    print("Migration 039: bond_yields ...")
    conn.executescript(MARKET_DATA_TABLES)
    conn.commit()

    have = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table','index')")}
    wanted = ["bond_yields", "idx_bond_yields_term_date"]
    missing = [w for w in wanted if w not in have]
    print(f"  objects present: {[w for w in wanted if w in have]}")
    if missing:
        print(f"  ERROR — still missing: {missing}")
        return 1
    print("Migration 039 complete.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python cleo/database/migrations/039_bond_yields.py path/to/cleo.db")
        print("Refusing to guess the DB path. Test against a COPY before the live file.")
        sys.exit(2)
    conn = sqlite3.connect(sys.argv[1])
    rc = migrate(conn)
    conn.close()
    sys.exit(rc)
