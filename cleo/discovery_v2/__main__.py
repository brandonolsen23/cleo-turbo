"""Developer entry point — `python -m cleo.discovery_v2`.

Runs all Layer 1 silo builders, then Layer 2 Plan A. Not a user surface.
"""

from __future__ import annotations
from cleo.database.connection import get_connection
from cleo.discovery_v2.brand_index import build_all_indexes
from cleo.discovery_v2.signals import (
    seed_industry_stopwords_table, seed_places_table,
)
from cleo.discovery_v2.auto_groups import build_auto_groups


def main():
    conn = get_connection()
    n1 = seed_industry_stopwords_table(conn)
    n2 = seed_places_table(conn)
    if n1 > 0:
        print(f'Seeded {n1} industry_stopwords rows')
    if n2 > 0:
        print(f'Seeded {n2} places rows')
    build_all_indexes(conn)
    build_auto_groups(conn)
    conn.close()


if __name__ == '__main__':
    main()
