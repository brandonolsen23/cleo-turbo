#!/usr/bin/env python3
"""
Standalone rebuild script — runs the Cleo compiler as a detached process.

Writes progress to data/rebuild-status.json so the admin UI can poll for updates.
This script is spawned by the admin API endpoint and runs independently of
the HTTP request lifecycle.

Usage:
    python3 rebuild.py              # Normal rebuild
    python3 rebuild.py --fresh      # Delete DB first and recreate schema + seed user
"""

import json
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

STATUS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "rebuild-status.json")


def write_status(phase, message, error=None, done=False):
    """Write current rebuild status to JSON file for polling."""
    status = {
        "running": not done,
        "phase": phase,
        "message": message,
        "error": error,
        "timestamp": time.time(),
        "pid": os.getpid(),
    }
    os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
    # Write atomically via temp file
    tmp = STATUS_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(status, f)
    os.replace(tmp, STATUS_FILE)


def main():
    fresh = "--fresh" in sys.argv

    write_status("starting", "Rebuild starting...")

    try:
        from cleo.database.connection import get_connection, DB_PATH
        from cleo.database.schema import create_all_tables
        from cleo.compiler.writer import run_compiler

        if fresh:
            # Delete existing DB for a completely clean start
            for ext in ("", "-wal", "-shm"):
                path = DB_PATH + ext
                if os.path.exists(path):
                    os.remove(path)
            write_status("schema", "Creating fresh database schema...")

            # Create schema + seed admin user
            conn = get_connection()
            create_all_tables(conn)
            from cleo.web.auth import hash_password
            pw_hash = hash_password("admin")
            conn.execute(
                "INSERT OR IGNORE INTO users (username, password_hash, display_name, role) "
                "VALUES (?, ?, ?, ?)",
                ("brandon", pw_hash, "Brandon", "admin"),
            )
            conn.commit()
            conn.close()

        write_status("compiling", "Running compiler...")
        start = time.time()

        conn = get_connection()
        try:
            run_compiler(conn)
        finally:
            conn.close()

        elapsed = round(time.time() - start, 1)

        # Read final counts
        conn = get_connection()
        counts = {}
        for table in ["properties", "transactions", "contacts", "groups", "pois", "gw_assessments"]:
            try:
                counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            except Exception:
                counts[table] = 0
        conn.close()

        write_status(
            "done",
            f"Rebuild completed in {elapsed}s",
            done=True,
        )
        # Append counts to status
        with open(STATUS_FILE) as f:
            status = json.load(f)
        status["elapsed"] = elapsed
        status["counts"] = counts
        with open(STATUS_FILE, "w") as f:
            json.dump(status, f)

        print(f"SUCCESS — {elapsed}s")

    except Exception as e:
        write_status("error", str(e), error=traceback.format_exc()[-1500:], done=True)
        print(f"ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
