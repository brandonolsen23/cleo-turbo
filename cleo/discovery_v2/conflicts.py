"""Stage A6: Conflict detection.

Scans auto_group_anchor_tenures and auto_contact_tenures for three conflict
patterns:
  - anchor_reassignment: same anchor with non-overlapping tenures on
    different groups.
  - contact_overlap: same contact with overlapping tenures on different groups.
  - transient_tenure: short-window low-volume tenures (4950 Yonge case).

These are surfaced for human review in the Conflicts UI (Plan H3); they
don't change the algorithm's outputs.

Idempotent: clears auto_conflict_flags at start, then re-emits all three
conflict types. This means A4-emitted conflict rows are wiped when A6 runs
(the orchestrator enforces A4 → contact_tenures → A6 order; A6's output is
the canonical set of structural conflicts derived from the tenure tables).
"""
from __future__ import annotations

import sqlite3
from datetime import date

from cleo.discovery_v2.constants import (
    MIN_PERMANENT_TENURE_DAYS,
    MIN_TENURE_PARTY_COUNT,
)


def _days_between(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def detect_conflicts(
    conn: sqlite3.Connection,
    *,
    verbose: bool = True,
    now: str | None = None,
) -> dict:
    """Idempotent — clears prior flags and recomputes all three conflict types.

    Args:
        conn: SQLite connection (must have auto_group_anchor_tenures,
              auto_contact_tenures, auto_conflict_flags tables).
        verbose: If True, print a summary line when done.
        now: Ignored. Kept for backward compatibility with the old signature.

    Returns:
        Dict with key 'n_conflicts' (total rows inserted).
    """
    # Idempotent: clear the entire table and re-derive everything.
    conn.execute('DELETE FROM auto_conflict_flags')

    flag_rows: list[tuple] = []

    # ── 1. anchor_reassignment ────────────────────────────────────────────
    # Same anchor (type + value) appears with non-overlapping windows on two
    # different groups. Emit one flag per consecutive pair (a → b).
    anchors_on_multiple_groups = conn.execute(
        """
        SELECT anchor_type, anchor_value
          FROM auto_group_anchor_tenures
         GROUP BY anchor_type, anchor_value
        HAVING COUNT(DISTINCT auto_group_id) > 1
        """
    ).fetchall()

    for row in anchors_on_multiple_groups:
        atype, aval = row['anchor_type'], row['anchor_value']
        tenures = conn.execute(
            """
            SELECT auto_group_id, start_date, end_date
              FROM auto_group_anchor_tenures
             WHERE anchor_type = ? AND anchor_value = ?
             ORDER BY start_date
            """,
            (atype, aval),
        ).fetchall()

        for i in range(len(tenures) - 1):
            a = tenures[i]
            b = tenures[i + 1]
            if a['auto_group_id'] == b['auto_group_id']:
                continue
            # Non-overlapping: a ends before b starts.
            # end_date is always set now; use it directly.
            a_end = a['end_date'] or '9999-12-31'
            if a_end < b['start_date']:
                flag_rows.append((
                    'anchor_reassignment',
                    'anchor',
                    aval,
                    atype,
                    a['auto_group_id'],
                    b['auto_group_id'],
                    a['end_date'],
                    (
                        f'{atype} {aval} reassigned from {a["auto_group_id"]} '
                        f'(ended {a["end_date"]}) to {b["auto_group_id"]} '
                        f'(started {b["start_date"]}).'
                    ),
                ))

    # ── 2. contact_overlap ────────────────────────────────────────────────
    # Same contact fingerprint holds overlapping tenures on two different
    # groups. Could be a service provider, job change, or name collision.
    contacts_on_multiple_groups = conn.execute(
        """
        SELECT contact_fingerprint
          FROM auto_contact_tenures
         GROUP BY contact_fingerprint
        HAVING COUNT(DISTINCT auto_group_id) > 1
        """
    ).fetchall()

    for row in contacts_on_multiple_groups:
        cf = row['contact_fingerprint']
        tenures = conn.execute(
            """
            SELECT auto_group_id, start_date, end_date
              FROM auto_contact_tenures
             WHERE contact_fingerprint = ?
             ORDER BY start_date
            """,
            (cf,),
        ).fetchall()

        # O(n²) overlap check across all pairs — contacts rarely have >3
        # group memberships so this is fine.
        for i in range(len(tenures)):
            for j in range(i + 1, len(tenures)):
                if tenures[i]['auto_group_id'] == tenures[j]['auto_group_id']:
                    continue
                a_start = tenures[i]['start_date']
                a_end   = tenures[i]['end_date'] or '9999-12-31'
                b_start = tenures[j]['start_date']
                b_end   = tenures[j]['end_date'] or '9999-12-31'
                # Two intervals [a_start, a_end] and [b_start, b_end] overlap
                # iff b_start <= a_end AND a_start <= b_end.
                if b_start <= a_end and a_start <= b_end:
                    flag_rows.append((
                        'contact_overlap',
                        'contact',
                        cf,
                        None,  # entity_subtype
                        tenures[i]['auto_group_id'],
                        tenures[j]['auto_group_id'],
                        b_start,
                        (
                            f'Contact {cf} held tenures at '
                            f'{tenures[i]["auto_group_id"]} '
                            f'({tenures[i]["start_date"]}–'
                            f'{tenures[i]["end_date"] or "ongoing"}) '
                            f'and {tenures[j]["auto_group_id"]} '
                            f'({tenures[j]["start_date"]}–'
                            f'{tenures[j]["end_date"] or "ongoing"}); '
                            f'either a service provider, a job change, '
                            f'or a name collision.'
                        ),
                    ))

    # ── 3. transient_tenure ───────────────────────────────────────────────
    # A tenure that is both low-volume (< MIN_TENURE_PARTY_COUNT) AND
    # short-duration (< MIN_PERMANENT_TENURE_DAYS). Surfaces one-off
    # appearances like "4950 Yonge" single transactions.
    # Under the simplified model end_date is always set (last observed date),
    # so no NULL filter needed.
    transient_candidates = conn.execute(
        """
        SELECT auto_group_id, anchor_type, anchor_value,
               start_date, end_date, n_party_sides_in_window
          FROM auto_group_anchor_tenures
         WHERE n_party_sides_in_window < ?
        """,
        (MIN_TENURE_PARTY_COUNT,),
    ).fetchall()

    for row in transient_candidates:
        days = _days_between(row['start_date'], row['end_date'])
        if days < MIN_PERMANENT_TENURE_DAYS:
            flag_rows.append((
                'transient_tenure',
                'anchor',
                row['anchor_value'],
                row['anchor_type'],
                row['auto_group_id'],
                None,  # group_b
                row['end_date'],
                (
                    f'{row["anchor_type"]} {row["anchor_value"]} had a transient '
                    f'tenure on {row["auto_group_id"]} '
                    f'({row["start_date"]}–{row["end_date"]}, '
                    f'{row["n_party_sides_in_window"]} parties). Likely one-off.'
                ),
            ))

    if flag_rows:
        conn.executemany(
            """
            INSERT INTO auto_conflict_flags
                (conflict_type, entity_type, entity_value, entity_subtype,
                 group_a, group_b, date_observed, description)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            flag_rows,
        )

    conn.commit()

    if verbose:
        print(f'  Stage A6 (conflicts): {len(flag_rows):,} flags emitted.', flush=True)

    return {'n_conflicts': len(flag_rows)}
