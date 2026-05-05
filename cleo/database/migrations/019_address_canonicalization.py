"""
Migration 019: address canonicalization columns on party_fingerprints.

Adds:
  - property_canonical_id  TEXT  — joins to properties.id (parcel-level
    identity). NULL when the transaction's parcel was unresolved.
  - party_address_canonical TEXT — pipe-joined string of canonicalized
    7-tuple components (city/suite-type/suite-number normalized via
    cleo/resolver/resources/*.json). Always non-NULL once populated by
    the compiler (empty components yield empty fragments).

Both columns are populated by the next run of the compiler's fingerprint
pass (cleo/atoms/fingerprint.py). This migration only adds the schema —
it does NOT backfill. Backfill = compiler rerun.

Idempotent.
"""
from __future__ import annotations
import os
import sqlite3


def migrate(conn: sqlite3.Connection) -> None:
    print("Migration 019: address canonicalization columns...")
    existing_cols = {r[1] for r in conn.execute("PRAGMA table_info(party_fingerprints)")}
    if "property_canonical_id" not in existing_cols:
        conn.execute(
            "ALTER TABLE party_fingerprints ADD COLUMN property_canonical_id TEXT"
        )
    if "party_address_canonical" not in existing_cols:
        conn.execute(
            "ALTER TABLE party_fingerprints ADD COLUMN party_address_canonical TEXT"
        )
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_pf_property_canonical
            ON party_fingerprints(property_canonical_id);
        CREATE INDEX IF NOT EXISTS idx_pf_party_addr_canonical
            ON party_fingerprints(party_address_canonical);
        """
    )
    conn.commit()
    print("Migration 019 complete.")


if __name__ == "__main__":
    db_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "data", "cleo.db"
    )
    conn = sqlite3.connect(db_path)
    migrate(conn)
    conn.close()
