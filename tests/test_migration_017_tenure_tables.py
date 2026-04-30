import importlib
import sqlite3


_m = importlib.import_module('cleo.database.migrations.017_tenure_tables')


def _empty_db():
    return sqlite3.connect(':memory:')


def test_migration_creates_auto_group_anchor_tenures():
    conn = _empty_db()
    _m.migrate(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(auto_group_anchor_tenures)")}
    assert cols >= {
        'id', 'auto_group_id', 'anchor_type', 'anchor_value',
        'start_date', 'end_date',
        'n_party_sides_in_window', 'dominance_share_in_window',
        'score', 'discovered_at',
    }


def test_migration_creates_auto_contact_tenures():
    conn = _empty_db()
    _m.migrate(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(auto_contact_tenures)")}
    assert cols >= {
        'id', 'contact_fingerprint', 'auto_group_id',
        'start_date', 'end_date',
        'n_party_sides_in_window', 'discovered_at',
    }


def test_migration_creates_auto_conflict_flags():
    conn = _empty_db()
    _m.migrate(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(auto_conflict_flags)")}
    assert cols >= {
        'id', 'conflict_type', 'entity_type', 'entity_value', 'entity_subtype',
        'group_a', 'group_b', 'date_observed', 'description', 'discovered_at',
    }


def test_migration_anchor_tenures_check_constraint():
    """anchor_type must be one of phone / address_unit / contact."""
    import pytest
    conn = _empty_db()
    _m.migrate(conn)
    # Valid value succeeds
    conn.execute(
        "INSERT INTO auto_group_anchor_tenures "
        "(auto_group_id, anchor_type, anchor_value, start_date, end_date, "
        " n_party_sides_in_window, dominance_share_in_window, score) "
        "VALUES ('AGRP_00001', 'address_unit', 'toronto|180|shorting|road|||', "
        "        '2018-01-01', NULL, 12, 0.85, 4.2)"
    )
    # Invalid anchor_type (the now-extinct address_root) raises
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO auto_group_anchor_tenures "
            "(auto_group_id, anchor_type, anchor_value, start_date, "
            " n_party_sides_in_window, dominance_share_in_window, score) "
            "VALUES ('AGRP_00002', 'address_root', '180|shorting', "
            "        '2018-01-01', 12, 0.85, 4.2)"
        )


def test_migration_conflict_flags_check_constraint():
    import pytest
    conn = _empty_db()
    _m.migrate(conn)
    # Valid conflict_type
    conn.execute(
        "INSERT INTO auto_conflict_flags "
        "(conflict_type, entity_type, entity_value, description) "
        "VALUES ('anchor_reassignment', 'anchor', '4162655055', 'test')"
    )
    # Invalid conflict_type raises
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO auto_conflict_flags "
            "(conflict_type, entity_type, entity_value, description) "
            "VALUES ('made_up_thing', 'anchor', 'X', 'test')"
        )


def test_migration_indexes_exist():
    conn = _empty_db()
    _m.migrate(conn)
    idx = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
    )}
    assert 'idx_agat_group' in idx
    assert 'idx_agat_anchor' in idx
    assert 'idx_act_contact' in idx
    assert 'idx_act_group' in idx
    assert 'idx_acf_type' in idx
    assert 'idx_acf_entity' in idx


def test_migration_is_idempotent():
    conn = _empty_db()
    _m.migrate(conn)
    _m.migrate(conn)  # should not raise
    n = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master "
        "WHERE type='table' AND name='auto_group_anchor_tenures'"
    ).fetchone()[0]
    assert n == 1
