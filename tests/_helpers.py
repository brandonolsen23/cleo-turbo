"""Shared helpers for Layer 2 (discovery_v2) test suites."""
from __future__ import annotations
import sqlite3


def seed_party_side(conn: sqlite3.Connection, sid: str, side: str, phrase: str | None,
                    *, phone: str | None = None, contact: str | None = None,
                    street_number: str | None = None, street_name: str | None = None,
                    street_suffix: str | None = None,
                    sale_date: str | None = '2025-01-01') -> None:
    """Seed a single party-side with optional phrase + anchors."""
    conn.execute(
        """INSERT OR IGNORE INTO party_fingerprints
             (source_id, side, phone, contact_fingerprint,
              street_number, street_name, street_suffix, sale_date)
           VALUES (?,?,?,?,?,?,?,?)""",
        (sid, side, phone, contact, street_number, street_name, street_suffix, sale_date),
    )
    if phrase:
        conn.execute(
            "INSERT INTO party_atoms (source_id, side, atom_type, atom_value, source_field) "
            "VALUES (?, ?, 'brand_phrase', ?, 'party_name')",
            (sid, side, phrase),
        )
