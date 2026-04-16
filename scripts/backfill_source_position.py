"""
One-time backfill: add source_position to the SQLite transactions table
by reading positions from classified filenames.

Also patches clean-data/rt/ files so future recompiles include source_position.
The clean-data patch runs in a second pass (can be interrupted safely).

Usage:
    python scripts/backfill_source_position.py
"""

import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLEAN_DIR = ROOT / "clean-data" / "rt"
CLASSIFIED_DIR = ROOT / "engines" / "rt" / "pipeline" / "classified"
DB_PATH = ROOT / "data" / "cleo.db"


def build_position_lookup():
    """Build RT ID → position map from classified filenames."""
    lookup = {}
    for fname in os.listdir(CLASSIFIED_DIR):
        if not fname.endswith(".json"):
            continue
        # Format: RT69383__Metro_Toronto__retail__p056__pos030.json
        parts = fname.replace(".json", "").split("__")
        if len(parts) >= 5 and parts[-1].startswith("pos"):
            rt_id = parts[0]
            position = int(parts[-1][3:])
            lookup[rt_id] = position
    return lookup


def update_database(lookup):
    """Add source_position column to transactions table and populate it."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # Add column if missing
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(transactions)").fetchall()]
    if "source_position" not in cols:
        conn.execute("ALTER TABLE transactions ADD COLUMN source_position INTEGER")
        print("Added source_position column to transactions table")

    # Batch update all RT transactions
    updated = 0
    batch = [(pos, rt_id) for rt_id, pos in lookup.items()]
    # Use executemany for speed
    conn.executemany(
        "UPDATE transactions SET source_position = ? WHERE source_id = ? AND source_position IS NULL",
        batch,
    )
    updated = conn.total_changes
    conn.commit()
    conn.close()
    print(f"Updated {updated} transaction rows in database")


def patch_clean_data(lookup):
    """Add source_position to clean-data JSON files (for future recompiles)."""
    patched = 0
    skipped = 0
    total = len(os.listdir(CLEAN_DIR))
    for i, fname in enumerate(os.listdir(CLEAN_DIR)):
        if not fname.endswith(".json"):
            continue
        rt_id = fname.replace(".json", "")
        if rt_id not in lookup:
            skipped += 1
            continue

        fpath = CLEAN_DIR / fname
        try:
            with open(fpath) as f:
                data = json.load(f)
        except (json.JSONDecodeError, ValueError):
            skipped += 1
            continue

        if data.get("source_position") == lookup[rt_id]:
            continue  # already set

        data["source_position"] = lookup[rt_id]
        with open(fpath, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        patched += 1

        if (i + 1) % 10000 == 0:
            print(f"  ... {i + 1}/{total} files processed")

    print(f"Patched {patched} clean-data files, {skipped} skipped")


def main():
    print("Building position lookup from classified files...")
    lookup = build_position_lookup()
    print(f"Found {len(lookup)} RT IDs with positions")

    print("\n--- Step 1: Updating database (fast) ---")
    update_database(lookup)

    print("\n--- Step 2: Patching clean-data files (slow, safe to interrupt) ---")
    patch_clean_data(lookup)

    print("\nDone!")


if __name__ == "__main__":
    main()
