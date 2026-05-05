"""Tests for migration 019: address canonicalization columns."""
import importlib
import sqlite3


def _fresh_pf_db():
    """Mock a stripped-down party_fingerprints schema (pre-migration)."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE party_fingerprints (
            source_id TEXT NOT NULL,
            side TEXT NOT NULL,
            street_number TEXT,
            street_name TEXT,
            street_suffix TEXT,
            street_direction TEXT,
            suite_type TEXT,
            suite_number TEXT,
            city TEXT,
            province TEXT,
            postal TEXT,
            postal_raw TEXT,
            country TEXT,
            phone TEXT,
            contact_fingerprint TEXT,
            sale_date TEXT,
            computed_at TEXT,
            PRIMARY KEY (source_id, side)
        );
        """
    )
    return conn


def test_migration_adds_columns_and_indexes():
    mod = importlib.import_module(
        "cleo.database.migrations.019_address_canonicalization"
    )
    conn = _fresh_pf_db()
    mod.migrate(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(party_fingerprints)")}
    assert "property_canonical_id" in cols
    assert "party_address_canonical" in cols
    indexes = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='party_fingerprints'"
    )}
    assert "idx_pf_property_canonical" in indexes
    assert "idx_pf_party_addr_canonical" in indexes
    conn.close()


def test_migration_is_idempotent():
    mod = importlib.import_module(
        "cleo.database.migrations.019_address_canonicalization"
    )
    conn = _fresh_pf_db()
    mod.migrate(conn)
    mod.migrate(conn)  # second run must not raise
    cols = {r[1] for r in conn.execute("PRAGMA table_info(party_fingerprints)")}
    assert "property_canonical_id" in cols
    conn.close()
