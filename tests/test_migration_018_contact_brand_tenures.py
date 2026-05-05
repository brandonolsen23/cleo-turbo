"""Tests for migration 018: contact_brand_tenures table."""
import sqlite3


def test_migration_creates_table_and_indexes():
    from cleo.database.migrations import (
        __init__ as _init,  # noqa: F401  (ensure package importable)
    )
    import importlib
    mod = importlib.import_module("cleo.database.migrations.018_contact_brand_tenures")

    conn = sqlite3.connect(":memory:")
    mod.migrate(conn)

    # Table exists with expected columns
    cols = {r[1] for r in conn.execute("PRAGMA table_info(contact_brand_tenures)").fetchall()}
    expected = {
        "id", "contact_fingerprint", "brand_stem",
        "strict_start_date", "strict_end_date",
        "inferred_start_date", "inferred_end_date",
        "n_party_sides_strict", "n_party_sides_inferred",
        "top_phrases_json", "source_field_breakdown_json",
        "dominant_address_unit", "auto_group_id", "is_active",
        "discovered_at",
    }
    assert expected <= cols, f"Missing columns: {expected - cols}"

    # Indexes exist
    idx = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='contact_brand_tenures'"
    )}
    assert "idx_cbt_contact" in idx
    assert "idx_cbt_stem" in idx
    conn.close()


def test_migration_idempotent():
    """Running the migration twice doesn't error."""
    import importlib
    mod = importlib.import_module("cleo.database.migrations.018_contact_brand_tenures")

    conn = sqlite3.connect(":memory:")
    mod.migrate(conn)
    mod.migrate(conn)  # second run uses CREATE TABLE IF NOT EXISTS
    conn.close()
