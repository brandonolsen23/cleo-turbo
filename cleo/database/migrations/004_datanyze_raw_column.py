"""
Migration 004: Add Datanyze + LinkedIn image columns.

- contact_field_overrides.datanyze_raw — full Datanyze response as JSON
- contact_field_overrides.linkedin_photo_url — profile picture URL
- contact_work_history.company_logo_url — company logo per position
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "cleo.db")


def run(db_path: str = DB_PATH):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # contact_field_overrides columns
    existing = {row[1] for row in cur.execute("PRAGMA table_info(contact_field_overrides)").fetchall()}

    for col_name in ("datanyze_raw", "linkedin_photo_url"):
        if col_name not in existing:
            cur.execute(f"ALTER TABLE contact_field_overrides ADD COLUMN {col_name} TEXT")
            print(f"  Added column: contact_field_overrides.{col_name}")
        else:
            print(f"  Column already exists: contact_field_overrides.{col_name}")

    # contact_work_history columns
    wh_existing = {row[1] for row in cur.execute("PRAGMA table_info(contact_work_history)").fetchall()}

    if "company_logo_url" not in wh_existing:
        cur.execute("ALTER TABLE contact_work_history ADD COLUMN company_logo_url TEXT")
        print("  Added column: contact_work_history.company_logo_url")
    else:
        print("  Column already exists: contact_work_history.company_logo_url")

    conn.commit()
    conn.close()
    print("Migration 004 complete.")


if __name__ == "__main__":
    run()
