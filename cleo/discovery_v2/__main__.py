"""Developer entry point — `python -m cleo.discovery_v2`.

NOT a user surface. CLAUDE.md reserves user-facing operations for the UI
(admin panel lands in Phase E). This exists for developer workflow:
calibration, debugging, and one-off experiments.
"""

from __future__ import annotations
from cleo.database.connection import get_connection
from cleo.discovery_v2.runner import run_discovery


def main():
    conn = get_connection()
    run_discovery(conn)
    conn.close()


if __name__ == "__main__":
    main()
