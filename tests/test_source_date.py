"""Tests for the deterministic source_date derivation (Phase 3).

source_date records when the source was obtained (GW download date / RT scrape
date), parsed from source_file/source_folder so the compiler can re-derive it
identically on every rebuild — no persistence needed. See
docs/incremental-recompile-plan.md.
"""

import importlib.util
import os
import sqlite3

from cleo.compiler.writer import _derive_source_date


def test_rt_daily_folder_date():
    assert _derive_source_date('_daily/2026-07-17_073007/p004') == '2026-07-17'


def test_gw_source_file_date():
    assert _derive_source_date('geowarehouse-2026-02-25T02-58-03-818Z.html') == '2026-02-25'


def test_bulk_import_folder_has_no_date():
    # Historical bulk RT folders carry no date -> None (falls back to created_at).
    assert _derive_source_date('Peel_Region/industrial/p033') is None


def test_empty_and_none():
    assert _derive_source_date('') is None
    assert _derive_source_date(None) is None


# --- migration 040 idempotency ------------------------------------------------

def _load_migration():
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'cleo', 'database', 'migrations', '040_source_date.py')
    spec = importlib.util.spec_from_file_location('mig040', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_adds_column_and_is_idempotent():
    mod = _load_migration()
    conn = sqlite3.connect(':memory:')
    conn.execute("CREATE TABLE transactions (source_id TEXT)")
    conn.execute("CREATE TABLE gw_assessments (id TEXT)")

    assert mod.migrate(conn) == 0
    for t in ('transactions', 'gw_assessments'):
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({t})")}
        assert 'source_date' in cols

    # Second run must not error or duplicate the column.
    assert mod.migrate(conn) == 0
    conn.close()
