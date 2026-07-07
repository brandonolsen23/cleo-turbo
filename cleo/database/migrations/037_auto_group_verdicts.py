"""
Migration 037: auto_group_verdicts — D4 flywheel verdict store.

Doctrine D4 front half: every auto-group shows WHY its members were grouped
(the Evidence tab), and Brandon records one-tap confirm/reject verdicts that
accumulate as ground truth for the future algorithm scoreboard (Phase 3).

Why a NEW table instead of reusing labeling_verdicts:
- labeling_verdicts is session-bound (session_id NOT NULL, cascading delete
  from labeling_sessions) and models a PAIR of party-sides
  (left_source_id/left_side vs source_id/side) with UNIQUE(session_id,
  source_id, side). Auto-group verdicts are keyed to an AGRP_ id — a
  membership judgment ("this member belongs / doesn't belong to this group")
  or a group-level judgment ("this grouping is right / wrong"), not a pair
  comparison inside a labeling session. Forcing them in would mean fake
  sessions and misused pair columns.
- discovery_ground_truth is keyed to legacy GRP_ ids and consumed only by the
  retired v1 engine — doctrine Section 5.2 supersedes it.

Key design (doctrine D1 Judgment bucket — durable, replayed nowhere because
it overlays nothing; it IS the ground truth corpus the scoreboard reads):
- auto_group_id: AGRP_ stable id.
- scope 'group'  → member_ref NULL; verdict about the grouping as a whole.
- scope 'member' → member_ref identifies the member with stable IDs:
    party_side rows:    "<source_id>:<side>"  e.g. "RT180025:buyer"
    numbered_corp rows: "corp:<corp_name>"    e.g. "corp:1865087 ontario"
- Append-only history: no UNIQUE constraint; the LATEST row per
  (auto_group_id, scope, member_ref) wins on read. Nothing is ever lost.
- verdict values are 'confirm'/'reject' (imperative, matching the API), not
  labeling_verdicts' 'confirmed'/'rejected' — different table, different verbs,
  keeps accidental cross-table UNIONs from silently type-punning.

This is a CRM/judgment table — never rebuilt or truncated by the compiler or
by discovery_v2. Purely additive migration (CREATE TABLE + indexes only).
"""

import sqlite3
import os


def migrate(conn):
    print("Migration 037: creating auto_group_verdicts table...")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS auto_group_verdicts (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            auto_group_id TEXT NOT NULL,
            scope         TEXT NOT NULL CHECK (scope IN ('group','member')),
            member_ref    TEXT,
            verdict       TEXT NOT NULL CHECK (verdict IN ('confirm','reject')),
            reason        TEXT,
            actor         TEXT NOT NULL,
            created_at    TEXT NOT NULL DEFAULT (datetime('now')),
            CHECK (
                (scope = 'group'  AND member_ref IS NULL) OR
                (scope = 'member' AND member_ref IS NOT NULL)
            )
        );

        CREATE INDEX IF NOT EXISTS idx_agv_group
            ON auto_group_verdicts(auto_group_id, scope, member_ref);
        CREATE INDEX IF NOT EXISTS idx_agv_created
            ON auto_group_verdicts(created_at DESC);
    """)
    conn.commit()
    print("Migration 037 complete.")


if __name__ == "__main__":
    db_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "cleo.db")
    conn = sqlite3.connect(db_path)
    migrate(conn)
    conn.close()
