"""Market data: Government of Canada benchmark bond yields.

Ingested from the Bank of Canada Valet API on app startup (backfill-on-start,
no cron) and served to the dashboard via cleo/web/routes/rates.py.
"""

from .ingest import ingest_bond_yields, backfill_bond_yields

__all__ = ["ingest_bond_yields", "backfill_bond_yields"]
