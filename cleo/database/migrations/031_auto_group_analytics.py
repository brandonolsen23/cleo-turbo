"""
Migration 031: auto_group_analytics — rolled-up analytics per auto_group.

Mirrors group_analytics but keyed on auto_group_id. Populated by
cleo/discovery_v2/group_analytics.py during the discovery_v2 build, aggregating
constituent legacy groups via legacy_to_auto_group_map. Lets contact / property
/ map routes read property_type_mix, regions, totals, etc. through the unified
auto_group concept instead of joining one specific SPV per contact.
"""

import sqlite3
import os


def migrate(conn):
    print("Migration 031: creating auto_group_analytics...")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS auto_group_analytics (
            auto_group_id            TEXT PRIMARY KEY,
            property_count           INTEGER,
            total_assessed_value     INTEGER,
            property_type_mix        TEXT,   -- JSON: {"multifamily": 106, ...}
            regions                  TEXT,   -- JSON: ["Metro Toronto", ...]
            region_count             INTEGER,
            total_buys               INTEGER,
            total_sells              INTEGER,
            avg_buy_price            INTEGER,
            avg_sell_price           INTEGER,
            first_transaction_date   TEXT,
            last_transaction_date    TEXT,
            net_acquisitions         INTEGER,
            txns_per_year            REAL,
            buys_last_12m            INTEGER,
            sells_last_12m           INTEGER,
            buys_last_36m            INTEGER,
            sells_last_36m           INTEGER,
            centroid_lat             REAL,
            centroid_lng             REAL,
            refreshed_at             TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_aga_property_count ON auto_group_analytics(property_count);
        CREATE INDEX IF NOT EXISTS idx_aga_total_buys     ON auto_group_analytics(total_buys);
        CREATE INDEX IF NOT EXISTS idx_aga_last_txn       ON auto_group_analytics(last_transaction_date);
    """)
    conn.commit()
    print("Migration 031 complete.")


if __name__ == "__main__":
    db_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "cleo.db")
    conn = sqlite3.connect(db_path)
    migrate(conn)
    conn.close()
