"""Developer entry point — `python -m cleo.discovery_v2`.

Runs Layer 1 / Silo A (brand-token index). Not a user surface.
"""

from __future__ import annotations
from cleo.database.connection import get_connection
from cleo.discovery_v2.brand_index import build_brand_index
from cleo.discovery_v2.signals import seed_industry_stopwords_table


def main():
    conn = get_connection()
    n = seed_industry_stopwords_table(conn)
    if n > 0:
        print(f"Seeded {n} industry_stopwords rows from resources/industry_stopwords_seed.json")
    build_brand_index(conn)
    conn.close()


if __name__ == "__main__":
    main()
