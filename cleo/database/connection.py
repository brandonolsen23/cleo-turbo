"""
SQLite connection management.

WAL mode enables concurrent reads (web app serving users) while the
Compiler writes. Foreign keys enforced. Busy timeout prevents lock errors.
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'cleo.db')
DB_PATH = os.path.abspath(DB_PATH)


def get_connection(db_path=None):
    """Create a new SQLite connection with WAL mode and foreign keys."""
    path = db_path or DB_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, timeout=10, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    return conn
