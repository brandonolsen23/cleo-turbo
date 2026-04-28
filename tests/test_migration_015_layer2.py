import importlib
import sqlite3

# Migration module names start with digits, so we can't use a plain
# `from ... import ...` statement.
_m = importlib.import_module('cleo.database.migrations.015_layer2_foundation_tables')


DERIVED_TABLES = {
    'brand_stem',
    'brand_stem_phrase_map',
    'anchor_uniqueness',
    'auto_groups',
    'auto_group_anchors',
    'auto_group_members',
}
CRM_TABLES = {
    'auto_group_overrides',
    'auto_group_merges',
    'auto_anchor_overrides',
}


def test_migration_creates_all_layer2_tables():
    conn = sqlite3.connect(':memory:')
    _m.migrate(conn)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    table_names = {r[0] for r in rows}
    assert DERIVED_TABLES.issubset(table_names), \
        f'Missing derived: {DERIVED_TABLES - table_names}'
    assert CRM_TABLES.issubset(table_names), \
        f'Missing CRM: {CRM_TABLES - table_names}'


def test_migration_is_idempotent():
    conn = sqlite3.connect(':memory:')
    _m.migrate(conn)
    _m.migrate(conn)  # should not raise
    cnt = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master "
        "WHERE type='table' AND name='auto_groups'"
    ).fetchone()[0]
    assert cnt == 1
