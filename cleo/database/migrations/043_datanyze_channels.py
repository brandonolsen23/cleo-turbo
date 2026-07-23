"""
Migration 043: seed Datanyze phones/emails into the channel tables.

Follows migration 042 (which seeded RT phone/mobile/email). Datanyze-enriched
numbers were previously only rendered on the contact page from
contact_field_overrides.datanyze_raw; this copies them into contact_phones /
contact_emails (source=datanyze, status=unverified) so they are stored, dedupable,
and can carry dial verdicts like any other channel.

Additive + idempotent: INSERT OR IGNORE on the (contact_id, value) dedupe index.
A Datanyze number equal to an already-stored value is skipped — this deduplicates,
never deletes. Going forward, the enrichment write path
(cleo/web/routes/contacts.py save_linkedin_profile) upserts channels directly, so
this one-time backfill only covers contacts enriched before that wiring landed.

Usage (refuses to run without an explicit DB path — always test a COPY first):
    .venv/bin/python cleo/database/migrations/043_datanyze_channels.py /tmp/cleo_test.db
"""

import json
import os
import sqlite3
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, REPO_ROOT)

from cleo.channels import upsert_datanyze_channels  # noqa: E402


def migrate(conn):
    print("Migration 043: seed Datanyze channels ...")
    for table in ("contact_phones", "contact_emails"):
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        if not exists:
            print(f"  ERROR — {table} missing. Run migration 042 first.")
            return 1

    rows = conn.execute(
        "SELECT contact_id, datanyze_raw FROM contact_field_overrides "
        "WHERE datanyze_raw IS NOT NULL AND datanyze_raw != ''"
    ).fetchall()

    contacts = 0
    phones_total = emails_total = 0
    for contact_id, raw in rows:
        try:
            datanyze = json.loads(raw)
        except (ValueError, TypeError):
            print(f"  skipping {contact_id}: unparseable datanyze_raw")
            continue
        p, e = upsert_datanyze_channels(conn, contact_id, datanyze)
        contacts += 1
        phones_total += p
        emails_total += e
    conn.commit()

    print(f"  scanned {contacts} contact(s) with Datanyze data")
    print(f"  seeded {phones_total} phone(s), {emails_total} email(s) this run")
    print("Migration 043 complete.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python cleo/database/migrations/043_datanyze_channels.py path/to/cleo.db")
        print("Refusing to guess the DB path. Test against a COPY before the live file.")
        sys.exit(2)
    conn = sqlite3.connect(sys.argv[1])
    rc = migrate(conn)
    conn.close()
    sys.exit(rc)
