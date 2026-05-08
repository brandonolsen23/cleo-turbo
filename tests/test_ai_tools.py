"""Tests for ai_tools — the read-only SQL + schema introspection layer
that backs the AI sidebar."""

import sqlite3
import pytest

from cleo.web.routes.ai_tools import (
    run_sql, describe_schema, get_entity_url,
    InvalidQueryError,
)


@pytest.fixture
def ro_conn(tmp_path):
    """Build a tiny on-disk DB and return a read-only connection to it,
    mirroring how the AI route opens the cleo.db at runtime."""
    db_file = tmp_path / "ai_tools_test.db"
    rw = sqlite3.connect(str(db_file))
    rw.executescript(
        """
        CREATE TABLE properties (
            id TEXT PRIMARY KEY, display_address TEXT, city TEXT
        );
        CREATE TABLE contacts (
            id TEXT PRIMARY KEY, display_name TEXT
        );
        INSERT INTO properties (id, display_address, city) VALUES
            ('PRO_1', '1 King St', 'Toronto'),
            ('PRO_2', '2 Queen St', 'Toronto'),
            ('PRO_3', '3 Bay St', 'Hamilton');
        INSERT INTO contacts (id, display_name) VALUES
            ('CON_1', 'Peter Vicano'),
            ('CON_2', 'Jane Doe');
        """
    )
    rw.commit()
    rw.close()
    ro = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
    ro.row_factory = sqlite3.Row
    yield ro
    ro.close()


# ── run_sql happy path ─────────────────────────────────────────────


def test_run_sql_returns_rows(ro_conn):
    out = run_sql(ro_conn, "SELECT id, city FROM properties ORDER BY id")
    assert out["row_count"] == 3
    assert out["truncated"] is False
    assert out["columns"] == ["id", "city"]
    assert out["rows"][0] == {"id": "PRO_1", "city": "Toronto"}


def test_run_sql_caps_at_200_rows():
    """If the underlying query returns >200 rows, mark truncated."""
    rw = sqlite3.connect(":memory:")
    rw.execute("CREATE TABLE big (n INTEGER)")
    rw.executemany("INSERT INTO big VALUES (?)", [(i,) for i in range(500)])
    rw.commit()
    out = run_sql(rw, "SELECT n FROM big ORDER BY n")
    assert out["row_count"] == 200
    assert out["truncated"] is True


def test_run_sql_with_cte(ro_conn):
    out = run_sql(
        ro_conn,
        "WITH t AS (SELECT city, COUNT(*) AS n FROM properties GROUP BY city) SELECT * FROM t ORDER BY city",
    )
    assert out["row_count"] == 2
    assert {r["city"] for r in out["rows"]} == {"Toronto", "Hamilton"}


def test_run_sql_explain_allowed(ro_conn):
    out = run_sql(ro_conn, "EXPLAIN SELECT * FROM properties")
    assert out["row_count"] > 0


# ── run_sql guard rejections ───────────────────────────────────────


@pytest.mark.parametrize(
    "bad",
    [
        "INSERT INTO properties (id) VALUES ('X')",
        "UPDATE properties SET city = 'X'",
        "DELETE FROM properties",
        "DROP TABLE properties",
        "CREATE TABLE foo (id TEXT)",
        "ALTER TABLE properties ADD COLUMN foo TEXT",
        "PRAGMA writable_schema = 1",
        "ATTACH DATABASE 'other.db' AS other",
        "SELECT 1; DROP TABLE properties",
        "  SELECT * FROM properties; DELETE FROM contacts",
        "-- harmless\nDROP TABLE properties",
    ],
)
def test_run_sql_rejects_non_select(ro_conn, bad):
    with pytest.raises(InvalidQueryError):
        run_sql(ro_conn, bad)


def test_run_sql_readonly_connection_blocks_writes(ro_conn):
    """Even if the guard were buggy, the URI mode=ro connection refuses writes."""
    # Bypass the guard intentionally by calling the underlying execute.
    with pytest.raises(sqlite3.OperationalError):
        ro_conn.execute("INSERT INTO properties (id) VALUES ('X')")


# ── describe_schema ────────────────────────────────────────────────


def test_describe_schema_lists_all_tables(ro_conn):
    out = describe_schema(ro_conn)
    names = {t["table"] for t in out["tables"]}
    assert {"properties", "contacts"} <= names
    p = next(t for t in out["tables"] if t["table"] == "properties")
    assert p["row_count"] == 3
    assert p["description"]  # non-empty fallback description


def test_describe_schema_for_specific_table(ro_conn):
    out = describe_schema(ro_conn, table="properties")
    cols = {c["name"] for c in out["columns"]}
    assert cols == {"id", "display_address", "city"}
    assert len(out["sample_rows"]) == 3  # we only have 3
    assert out["sample_rows"][0]["id"].startswith("PRO_")


def test_describe_schema_unknown_table_raises(ro_conn):
    with pytest.raises(InvalidQueryError):
        describe_schema(ro_conn, table="not_a_real_table")


# ── get_entity_url ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "etype,eid,expected",
    [
        ("property", "PRO_84463", "/properties/PRO_84463"),
        ("contact",  "CON_14995", "/contacts/CON_14995"),
        ("group",    "GRP_22771", "/groups/GRP_22771"),
        ("deal",     "DEAL_42",   "/deals/DEAL_42"),
        ("list",     "LIST_3",    "/lists/LIST_3"),
        ("transaction", "RT126011", "/transactions/RT126011"),
    ],
)
def test_get_entity_url_known_types(etype, eid, expected):
    assert get_entity_url(etype, eid) == expected


def test_get_entity_url_unknown_type_raises():
    with pytest.raises(InvalidQueryError):
        get_entity_url("nonsense", "XYZ_1")
