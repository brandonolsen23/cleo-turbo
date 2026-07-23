"""
Migration 042: contact_phones + contact_emails (Phase 1 prospecting, step 1).

Two CRM tables holding a contact's phones/emails as a COLLECTION with per-value
verdicts, instead of the single overwrite-or-lose field on the derived `contacts`
table. Keyed by CON_ stable IDs; never dropped/rebuilt by the compiler.

Two parts, both idempotent:
  1. DDL — CREATE TABLE IF NOT EXISTS for both tables + indexes (mirror of the
     canonical DDL in cleo/database/schema.py).
  2. RT seed — copy each contact's existing derived phone/mobile/email into the
     new tables (source=realtrack, status=unverified) via INSERT OR IGNORE on the
     (contact_id, value) unique index. The RT columns on `contacts` are read-only
     here — this is a copy with provenance, not a move. Re-running is a no-op and,
     critically, will NOT resurrect a value the user later marked dead/wrong_number
     (the existing row already occupies the dedupe key, so the insert is ignored).

Usage (refuses to run without an explicit DB path — always test a COPY first):
    .venv/bin/python cleo/database/migrations/042_contact_channels.py /tmp/cleo_test.db
"""

import os
import sqlite3
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, REPO_ROOT)

from cleo.channels import normalize_phone, normalize_email  # noqa: E402


DDL = """
CREATE TABLE IF NOT EXISTS contact_phones (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id         TEXT NOT NULL REFERENCES contacts(id),
    value              TEXT NOT NULL,
    value_raw          TEXT,
    label              TEXT,
    source             TEXT NOT NULL,
    status             TEXT NOT NULL DEFAULT 'unverified',
    status_changed_at  TEXT,
    note               TEXT,
    hubspot_property   TEXT,
    created_at         TEXT DEFAULT (datetime('now')),
    updated_at         TEXT DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_contact_phones_dedupe  ON contact_phones(contact_id, value);
CREATE INDEX        IF NOT EXISTS idx_contact_phones_contact ON contact_phones(contact_id);

CREATE TABLE IF NOT EXISTS contact_emails (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id         TEXT NOT NULL REFERENCES contacts(id),
    value              TEXT NOT NULL,
    value_raw          TEXT,
    label              TEXT,
    source             TEXT NOT NULL,
    status             TEXT NOT NULL DEFAULT 'unverified',
    status_changed_at  TEXT,
    note               TEXT,
    hubspot_property   TEXT,
    created_at         TEXT DEFAULT (datetime('now')),
    updated_at         TEXT DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_contact_emails_dedupe  ON contact_emails(contact_id, value);
CREATE INDEX        IF NOT EXISTS idx_contact_emails_contact ON contact_emails(contact_id);
"""


def _table_exists(conn, table):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _seed(conn):
    """Copy derived RT phone/mobile/email into the channel tables. Additive,
    idempotent (INSERT OR IGNORE on the dedupe index)."""
    rows = conn.execute(
        "SELECT id, phone, mobile, email FROM contacts"
    ).fetchall()

    # (raw source value, label) pairs per table
    phones_inserted = 0
    emails_inserted = 0
    for contact_id, phone, mobile, email in rows:
        for raw, label in ((phone, "main"), (mobile, "cell")):
            value = normalize_phone(raw)
            if not value:
                continue
            cur = conn.execute(
                "INSERT OR IGNORE INTO contact_phones "
                "(contact_id, value, value_raw, label, source, status) "
                "VALUES (?, ?, ?, ?, 'realtrack', 'unverified')",
                (contact_id, value, raw, label),
            )
            phones_inserted += cur.rowcount

        value = normalize_email(email)
        if value:
            cur = conn.execute(
                "INSERT OR IGNORE INTO contact_emails "
                "(contact_id, value, value_raw, label, source, status) "
                "VALUES (?, ?, ?, NULL, 'realtrack', 'unverified')",
                (contact_id, value, email),
            )
            emails_inserted += cur.rowcount

    return phones_inserted, emails_inserted


def migrate(conn):
    print("Migration 042: contact_phones + contact_emails ...")
    conn.executescript(DDL)
    conn.commit()

    for table in ("contact_phones", "contact_emails"):
        if not _table_exists(conn, table):
            print(f"  ERROR — table {table} was not created")
            return 1
        print(f"  {table} present")

    phones_inserted, emails_inserted = _seed(conn)
    conn.commit()

    phone_total = conn.execute("SELECT COUNT(*) FROM contact_phones").fetchone()[0]
    email_total = conn.execute("SELECT COUNT(*) FROM contact_emails").fetchone()[0]
    print(f"  seeded {phones_inserted} phone(s), {emails_inserted} email(s) this run")
    print(f"  totals now: {phone_total} phone rows, {email_total} email rows")
    print("Migration 042 complete.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python cleo/database/migrations/042_contact_channels.py path/to/cleo.db")
        print("Refusing to guess the DB path. Test against a COPY before the live file.")
        sys.exit(2)
    conn = sqlite3.connect(sys.argv[1])
    rc = migrate(conn)
    conn.close()
    sys.exit(rc)
