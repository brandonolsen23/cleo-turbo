"""
Migration 035: extend auto_group_analytics for the unified Property model.

The Group detail page now treats Property as "any unique address the group has
ever transacted on" — resolved (parcel-matched) and unresolved (only known by
display_address + city). Aggregate buy/sell values come from real SUM of
transactions.sale_price, not avg×count derivations.

New columns:
- total_buy_value, total_sell_value: real-sum dollar totals
- n_buys_priced, n_sells_priced: how many transactions in that side had a
  non-NULL non-zero price (so the UI can show "X of Y transactions priced")
- properties_total: distinct properties (COALESCE(property_id,
  canonical_address_key)) seen on any party-side
- properties_owned: subset where the group's last party-side per property
  is on the buyer side

Existing columns kept — property_count and transacted_property_count remain
as the resolved-only counts for any downstream consumer that still wants
parcel-resolver semantics.
"""

import sqlite3
import os


def migrate(conn):
    print("Migration 035: adding unified-Property columns to auto_group_analytics...")

    conn.executescript("""
        ALTER TABLE auto_group_analytics ADD COLUMN total_buy_value  INTEGER;
        ALTER TABLE auto_group_analytics ADD COLUMN total_sell_value INTEGER;
        ALTER TABLE auto_group_analytics ADD COLUMN n_buys_priced    INTEGER;
        ALTER TABLE auto_group_analytics ADD COLUMN n_sells_priced   INTEGER;
        ALTER TABLE auto_group_analytics ADD COLUMN properties_total INTEGER;
        ALTER TABLE auto_group_analytics ADD COLUMN properties_owned INTEGER;
    """)
    conn.commit()
    print("Migration 035 complete.")


if __name__ == "__main__":
    db_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "cleo.db")
    conn = sqlite3.connect(db_path)
    migrate(conn)
    conn.close()
