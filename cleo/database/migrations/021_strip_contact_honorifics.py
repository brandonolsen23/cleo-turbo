"""Migration 021: strip leading honorifics from contact name fingerprints.

Background
----------
The original ``make_name_fingerprint`` upper-cased the entire ``name`` string
with no normalization beyond whitespace, so "Harry Aronowicz" and
"Dr Harry Aronowicz" produced different fingerprints and got separate
``CON_`` IDs. The same person's portfolio ended up scattered across multiple
contact rows.

What this migration does
------------------------
1. Recomputes each contact's fingerprint with the new
   ``strip_leading_honorifics`` rule.
2. For every collision (multiple existing CON_IDs that now share a
   fingerprint), picks a winner via the canonical-fingerprint-first rule
   (the row whose pre-existing fingerprint already matches the new one).
3. Redirects every CRM-table reference from each loser CON_ID to the
   winner. UNIQUE-constraint conflicts are resolved by deleting the loser
   side first.
4. Updates ``id_mappings`` (system table) so that the new fingerprint is
   the only anchor for the winner, and the loser's anchor row is removed.
5. Deletes the loser ``contacts`` row. The next compiler run rebuilds the
   contacts table from clean-data and naturally collapses to one row.
6. For singletons whose fingerprint just changes (no collision), updates
   ``id_mappings.anchor_key`` and ``contacts`` in-place. CON_ID preserved.
7. ``audit_log`` rows that reference contact entity IDs are intentionally
   *not* redirected — the log is a historical record.

Idempotent: rerunning is a no-op once contact fingerprints are clean.

Run via:
    python -m cleo.database.migrations.021_strip_contact_honorifics
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict

from cleo.compiler.reconciler import make_name_fingerprint


def _con_id_num(con_id: str) -> int:
    return int(con_id.split("_")[1])


def _table_has_column(conn: sqlite3.Connection, table: str, col: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == col for r in rows)


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


# Tables with a direct contact_id column. Each entry is (table, column,
# extra_unique_columns). UNIQUE-conflict resolution: delete the loser row
# whose (extra_unique_columns + column->winner) tuple already exists in the
# winner side, then update the rest.
DIRECT_FK_TABLES = [
    # (table, fk_column, unique_partner_columns)
    ("transaction_parties", "contact_id", None),  # rebuilt by compiler anyway
    ("contact_notes", "contact_id", None),
    ("contact_field_overrides", "contact_id", None),
    ("contact_work_history", "contact_id", None),
    ("group_contacts", "contact_id", ("group_id",)),
    ("buy_mandates", "contact_id", None),
    ("activities", "contact_id", None),
]

# Tables with polymorphic (entity_type, entity_id) refs that include
# 'contact'. Each entry is (table, type_column, id_column,
# entity_type_value, unique_partner_columns).
POLY_TABLES = [
    ("activities", "entity_type", "entity_id", "contact", None),
    ("user_stars", "entity_type", "entity_id", "contact", ("user_id",)),
    ("list_members", "member_type", "member_id", "contact", ("list_id",)),
]


def _redirect_direct(
    conn: sqlite3.Connection,
    table: str,
    col: str,
    winner: str,
    loser: str,
    unique_partner_cols: tuple[str, ...] | None,
) -> tuple[int, int]:
    """Returns (deleted, updated)."""
    if not _table_exists(conn, table):
        return (0, 0)
    if not _table_has_column(conn, table, col):
        return (0, 0)

    deleted = 0
    if unique_partner_cols:
        partner_csv = ", ".join(unique_partner_cols)
        # Delete loser-side rows whose (partners, winner) tuple is already
        # present on the winner side, then update the rest.
        del_sql = f"""
            DELETE FROM {table}
            WHERE {col} = ?
              AND ({partner_csv}) IN (
                  SELECT {partner_csv} FROM {table} WHERE {col} = ?
              )
        """
        cur = conn.execute(del_sql, (loser, winner))
        deleted = cur.rowcount
    cur = conn.execute(f"UPDATE {table} SET {col} = ? WHERE {col} = ?", (winner, loser))
    return (deleted, cur.rowcount)


def _redirect_poly(
    conn: sqlite3.Connection,
    table: str,
    type_col: str,
    id_col: str,
    type_value: str,
    winner: str,
    loser: str,
    unique_partner_cols: tuple[str, ...] | None,
) -> tuple[int, int]:
    if not _table_exists(conn, table):
        return (0, 0)
    if not (_table_has_column(conn, table, type_col) and _table_has_column(conn, table, id_col)):
        return (0, 0)

    deleted = 0
    if unique_partner_cols:
        partner_csv = ", ".join(unique_partner_cols)
        del_sql = f"""
            DELETE FROM {table}
            WHERE {type_col} = ? AND {id_col} = ?
              AND ({partner_csv}) IN (
                  SELECT {partner_csv} FROM {table}
                  WHERE {type_col} = ? AND {id_col} = ?
              )
        """
        cur = conn.execute(del_sql, (type_value, loser, type_value, winner))
        deleted = cur.rowcount
    cur = conn.execute(
        f"UPDATE {table} SET {id_col} = ? WHERE {type_col} = ? AND {id_col} = ?",
        (winner, type_value, loser),
    )
    return (deleted, cur.rowcount)


def _redirect_all(conn: sqlite3.Connection, winner: str, loser: str) -> dict:
    """Redirect every reference from loser → winner. Returns a per-table
    dict of (deleted, updated)."""
    stats: dict[str, tuple[int, int]] = {}
    for table, col, partners in DIRECT_FK_TABLES:
        stats[f"{table}.{col}"] = _redirect_direct(conn, table, col, winner, loser, partners)
    for table, type_col, id_col, type_value, partners in POLY_TABLES:
        key = f"{table}.{id_col}[{type_col}={type_value}]"
        stats[key] = _redirect_poly(conn, table, type_col, id_col, type_value, winner, loser, partners)
    return stats


def migrate(conn: sqlite3.Connection) -> None:
    print("Migration 021: strip contact honorifics")

    contacts = conn.execute(
        "SELECT id, display_name, name_fingerprint FROM contacts"
    ).fetchall()

    by_new_fp: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for cid, dname, ofp in contacts:
        new_fp = make_name_fingerprint(dname or "")
        if not new_fp:
            continue
        by_new_fp[new_fp].append((cid, dname, ofp or ""))

    collisions = {fp: rows for fp, rows in by_new_fp.items() if len(rows) >= 2}
    singletons = [
        (rows[0], fp) for fp, rows in by_new_fp.items()
        if len(rows) == 1 and rows[0][2] != fp
    ]

    print(f"  contacts: {len(contacts):,}")
    print(f"  merge groups: {len(collisions)}")
    print(f"  singleton renames: {len(singletons)}")

    if not collisions and not singletons:
        print("  nothing to do — already clean")
        return

    total_redirects = 0
    total_deletes = 0
    merges_done = 0

    for new_fp, rows in collisions.items():
        canonical = [r for r in rows if r[2] == new_fp]
        if canonical:
            winner = min(canonical, key=lambda r: _con_id_num(r[0]))
        else:
            winner = min(rows, key=lambda r: _con_id_num(r[0]))
        winner_id = winner[0]
        losers = [r for r in rows if r[0] != winner_id]

        # Make sure the winner's id_mappings row uses the new fingerprint.
        # If the winner's anchor was already new_fp, this is a no-op.
        # Otherwise, two id_mappings rows might exist for the winner
        # (one with old anchor, one we'll insert). Use INSERT OR REPLACE
        # keyed on (entity_type, anchor_key) — but first delete any row
        # for the winner that has the OLD anchor.
        winner_row = conn.execute(
            "SELECT anchor_key FROM id_mappings WHERE entity_type='contact' AND entity_id=?",
            (winner_id,),
        ).fetchone()
        if winner_row and winner_row[0] != new_fp:
            conn.execute(
                "DELETE FROM id_mappings WHERE entity_type='contact' AND entity_id=?",
                (winner_id,),
            )
        conn.execute(
            "INSERT OR IGNORE INTO id_mappings (entity_type, anchor_key, entity_id) "
            "VALUES ('contact', ?, ?)",
            (new_fp, winner_id),
        )

        # Redirect loser → winner across all reference tables.
        for loser in losers:
            loser_id = loser[0]
            stats = _redirect_all(conn, winner_id, loser_id)
            for tbl_key, (d, u) in stats.items():
                total_deletes += d
                total_redirects += u

            # Drop the loser's id_mappings row + contacts row.
            conn.execute(
                "DELETE FROM id_mappings WHERE entity_type='contact' AND entity_id=?",
                (loser_id,),
            )
            conn.execute("DELETE FROM contacts WHERE id=?", (loser_id,))
            merges_done += 1

        # Refresh the winner's contacts.name_fingerprint (since its old
        # value may have been the un-stripped form).
        conn.execute(
            "UPDATE contacts SET name_fingerprint=? WHERE id=?",
            (new_fp, winner_id),
        )

    # Singletons: just rename the anchor + rewrite contacts.name_fingerprint
    # and re-derive first_name/last_name with the stripped form.
    from cleo.compiler.reconciler import strip_leading_honorifics
    singleton_count = 0
    for (cid, dname, _ofp), new_fp in singletons:
        # id_mappings.anchor_key — there may already be a row for the same
        # (entity_type, new_fp) pointing to a different entity_id; only
        # collisions land in the merge path above, so for a true singleton
        # this shouldn't happen — but guard anyway.
        existing = conn.execute(
            "SELECT entity_id FROM id_mappings WHERE entity_type='contact' AND anchor_key=?",
            (new_fp,),
        ).fetchone()
        if existing and existing[0] != cid:
            # Collision we missed — skip and let a later run handle it.
            continue
        conn.execute(
            "DELETE FROM id_mappings WHERE entity_type='contact' AND entity_id=?",
            (cid,),
        )
        conn.execute(
            "INSERT OR REPLACE INTO id_mappings (entity_type, anchor_key, entity_id) "
            "VALUES ('contact', ?, ?)",
            (new_fp, cid),
        )

        # Recompute first/last from the stripped tokens, preserving the
        # original casing where possible.
        upper_tokens = strip_leading_honorifics((dname or "").upper().split())
        src_tokens = (dname or "").split()
        if len(src_tokens) > len(upper_tokens):
            src_tokens = src_tokens[len(src_tokens) - len(upper_tokens):]
        first = src_tokens[0] if src_tokens else ""
        last = " ".join(src_tokens[1:]) if len(src_tokens) > 1 else ""
        conn.execute(
            "UPDATE contacts SET name_fingerprint=?, first_name=?, last_name=? WHERE id=?",
            (new_fp, first, last, cid),
        )
        singleton_count += 1

    conn.commit()

    print(f"  merges applied: {merges_done}")
    print(f"  singleton renames: {singleton_count}")
    print(f"  total CRM redirects: {total_redirects} updates, {total_deletes} duplicate deletes")
    print("Migration 021: done.")


if __name__ == "__main__":
    from cleo.database.connection import get_connection
    conn = get_connection()
    migrate(conn)
    conn.close()
