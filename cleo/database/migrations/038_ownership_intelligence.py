"""
Migration 038: Ownership Intelligence Pipeline M1 (D1 + D2 + D8).

Per docs/ownership-intelligence-pipeline.md (locked 2026-07-07):
- D1  group_facts — searchable structured intelligence keyed to AGRP_ ids,
      one row per (field, value) with source/confidence/effective timelines,
      plus an FTS5 external-content index over (field, value) with the three
      standard sync triggers.
- D2  adjudications — one append-only row per adjudication run of a cluster.
- D8  group_profile.narrative_md — long-form dossier markdown; `summary`
      stays the short one-liner.

Purely additive: CREATE TABLE/INDEX/TRIGGER IF NOT EXISTS + one guarded
ALTER TABLE ADD COLUMN. Never drops or mutates data. The canonical DDL
lives in cleo/database/schema.py (OWNERSHIP_INTEL_TABLES) so fresh DBs and
rebuilds carry the same shape — this migration reuses it verbatim.

Bucket notes (docs/data-doctrine.md D1):
- adjudications is a SYSTEM record (like ai_usage): append-only, never
  truncated, only status/review columns mutate via the review endpoints.
- group_facts rows with machine sources are interpretation; source='human'
  rows are judgment. Neither is compiler-dropped (not in
  drop_derived_tables); lifecycle is proposed -> committed -> retracted
  (soft-delete only).

Usage (refuses to run without an explicit DB path — always a COPY first):
    .venv/bin/python cleo/database/migrations/038_ownership_intelligence.py /tmp/cleo_test.db
"""

import os
import sqlite3
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, REPO_ROOT)


def migrate(conn):
    from cleo.database.schema import OWNERSHIP_INTEL_TABLES

    print("Migration 038: group_facts + adjudications + group_profile.narrative_md ...")
    conn.executescript(OWNERSHIP_INTEL_TABLES)

    cols = {r[1] for r in conn.execute("PRAGMA table_info(group_profile)")}
    if "narrative_md" not in cols:
        conn.execute("ALTER TABLE group_profile ADD COLUMN narrative_md TEXT")
        print("  group_profile.narrative_md added")
    else:
        print("  group_profile.narrative_md already present")

    conn.commit()

    # Report
    have = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table','trigger')")}
    wanted = ["group_facts", "adjudications", "group_facts_fts",
              "group_facts_fts_ai", "group_facts_fts_ad", "group_facts_fts_au"]
    missing = [w for w in wanted if w not in have]
    print(f"  objects present: {[w for w in wanted if w in have]}")
    if missing:
        print(f"  ERROR — still missing: {missing}")
        return 1
    print("Migration 038 complete.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python cleo/database/migrations/038_ownership_intelligence.py path/to/cleo.db")
        print("Refusing to guess the DB path. Test against a COPY before the live file.")
        sys.exit(2)
    conn = sqlite3.connect(sys.argv[1])
    rc = migrate(conn)
    conn.close()
    sys.exit(rc)
