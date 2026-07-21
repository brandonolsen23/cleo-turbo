"""
Migration 041: owned asset-class breakdown on the analytics tables.

Adds a per-asset-class count and value breakdown of each group's
currently-owned portfolio, keyed by the same `asset_class` vocabulary the
Groups asset-class filter uses:

  owned_asset_class_counts  {asset_class: n_owned_properties}
  owned_asset_class_value   {asset_class: sum(most_recent_sale_price)}

The value blob reconciles with total_assessed_value (sum across classes). This
lets the Groups browse filter combine "owns 3–10 retail properties" with
"$20M–$200M of retail" against the same owned-retail set, instead of pairing a
transacted-history count with an all-asset-classes portfolio total.

Both tables are refreshed in place (not derived/dropped), so existing databases
need the columns added. refresh_group_analytics and build_auto_group_analytics
also add these columns idempotently at run time; this migration keeps a fresh
`data/cleo.db` in sync without a full analytics refresh.
"""

import sqlite3
import os


def migrate(conn):
    print("Migration 041: adding owned asset-class breakdown columns...")

    for table in ("group_analytics", "auto_group_analytics"):
        for col in ("owned_asset_class_counts TEXT", "owned_asset_class_value TEXT"):
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col}")
            except sqlite3.OperationalError:
                pass  # column already present

    conn.commit()
    print("Migration 041 complete.")


if __name__ == "__main__":
    db_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "cleo.db")
    conn = sqlite3.connect(db_path)
    migrate(conn)
    conn.close()
