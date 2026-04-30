"""Stage A2: Windowed-dominance tenure detection.

For each anchor (phone, address_unit, contact), walks the chronological
timeline of party events and emits one tenure per stable run of events
sharing a dominant stem. Persists tenures to `_pending_tenures` for Stage A3
to associate with auto_group_ids. Also populates `anchor_uniqueness` from
the most-recent tenure per anchor (for backward compat with downstream
API code that still reads the static snapshot).
"""
from __future__ import annotations
import sqlite3
from datetime import datetime, timezone

from cleo.discovery_v2.timelines import iter_all_anchor_timelines
from cleo.discovery_v2.tenures import detect_tenures


def build_anchor_scores(conn: sqlite3.Connection, *, verbose: bool = True) -> dict:
    """Detect tenures for every anchor; populate _pending_tenures and
    anchor_uniqueness."""
    # Staging table — purely an A2→A3 handoff.
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS _pending_tenures (
            anchor_type TEXT NOT NULL,
            anchor_value TEXT NOT NULL,
            dominant_stem TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT,
            n_party_sides INTEGER NOT NULL,
            dominance_share REAL NOT NULL,
            score REAL NOT NULL
        );
        DELETE FROM _pending_tenures;
    """)
    conn.execute('DELETE FROM anchor_uniqueness')

    today = datetime.now(timezone.utc).date().isoformat()

    pending_rows: list[tuple] = []
    snapshot_rows: list[tuple] = []  # for anchor_uniqueness

    n_tenures = 0
    for anchor_type, anchor_value, timeline in iter_all_anchor_timelines(conn):
        tenures = detect_tenures(timeline, now=today)
        if not tenures:
            continue
        for t in tenures:
            pending_rows.append((
                anchor_type, anchor_value, t['dominant_stem'],
                t['start_date'], t['end_date'],
                t['n_party_sides'], t['dominance_share'], t['score'],
            ))
            n_tenures += 1
        # Snapshot: pick the latest tenure (the one with end_date=None first,
        # else the largest end_date).
        latest = max(
            tenures,
            key=lambda t: (t['end_date'] is None, t['end_date'] or t['start_date']),
        )
        snapshot_rows.append((
            anchor_type, anchor_value,
            latest['dominant_stem'],
            latest['dominance_share'],
            latest['n_party_sides'],
            latest['score'],
        ))

    if pending_rows:
        conn.executemany(
            """INSERT INTO _pending_tenures
                (anchor_type, anchor_value, dominant_stem,
                 start_date, end_date,
                 n_party_sides, dominance_share, score)
              VALUES (?,?,?,?,?,?,?,?)""",
            pending_rows,
        )
    if snapshot_rows:
        conn.executemany(
            """INSERT INTO anchor_uniqueness
                (anchor_type, anchor_value, dominant_stem,
                 dominance_share, volume, score)
              VALUES (?,?,?,?,?,?)""",
            snapshot_rows,
        )
    conn.commit()
    if verbose:
        print(
            f'  Stage A2 (tenures): {n_tenures:,} tenures across '
            f'{len(snapshot_rows):,} anchors.', flush=True
        )
    return {'n_tenures': n_tenures, 'n_anchors': len(snapshot_rows)}
