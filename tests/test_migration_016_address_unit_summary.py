# tests/test_migration_016_address_unit_summary.py
import importlib
import sqlite3


_m = importlib.import_module('cleo.database.migrations.016_address_unit_summary')


def _setup_pre_migration_db():
    """Simulate the pre-016 state: anchor_uniqueness exists with the old CHECK."""
    conn = sqlite3.connect(':memory:')
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS anchor_uniqueness (
            anchor_type TEXT NOT NULL CHECK (anchor_type IN ('phone','address_root','address_base','contact')),
            anchor_value TEXT NOT NULL,
            dominant_stem TEXT,
            dominance_share REAL,
            volume INTEGER NOT NULL,
            score REAL NOT NULL,
            is_service_provider INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (anchor_type, anchor_value)
        );
    """)
    return conn


def test_migration_creates_address_unit_summary():
    conn = _setup_pre_migration_db()
    _m.migrate(conn)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='address_unit_summary'"
    ).fetchall()
    assert len(rows) == 1


def test_migration_address_unit_summary_columns():
    conn = _setup_pre_migration_db()
    _m.migrate(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(address_unit_summary)")}
    assert cols >= {
        'city', 'street_number', 'street_name', 'street_suffix', 'street_direction',
        'suite_type', 'suite_number',
        'n_party_sides', 'n_distinct_brand_stems', 'dominant_stem', 'dominance_share',
        'discovered_at',
    }


def test_migration_drops_anchor_uniqueness_check():
    """After migration, inserting anchor_type='address_unit' must succeed (the old CHECK forbade it)."""
    conn = _setup_pre_migration_db()
    _m.migrate(conn)
    conn.execute(
        "INSERT INTO anchor_uniqueness (anchor_type, anchor_value, volume, score) "
        "VALUES ('address_unit', 'toronto|180|shorting|road|||', 5, 1.5)"
    )
    cnt = conn.execute(
        "SELECT COUNT(*) FROM anchor_uniqueness WHERE anchor_type='address_unit'"
    ).fetchone()[0]
    assert cnt == 1


def test_migration_is_idempotent():
    conn = _setup_pre_migration_db()
    _m.migrate(conn)
    _m.migrate(conn)  # no error
    rows = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='address_unit_summary'"
    ).fetchone()[0]
    assert rows == 1


def test_migration_preserves_anchor_uniqueness_rows():
    """Existing rows in anchor_uniqueness must survive the table recreate."""
    conn = _setup_pre_migration_db()
    conn.execute(
        "INSERT INTO anchor_uniqueness (anchor_type, anchor_value, volume, score) "
        "VALUES ('phone', '4166876700', 137, 4.5)"
    )
    _m.migrate(conn)
    row = conn.execute(
        "SELECT anchor_type, anchor_value, volume, score FROM anchor_uniqueness "
        "WHERE anchor_type='phone' AND anchor_value='4166876700'"
    ).fetchone()
    assert row == ('phone', '4166876700', 137, 4.5)
