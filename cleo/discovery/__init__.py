"""
Group Discovery Algorithm — portfolio clustering for Ontario CRE entities.

Identifies SPVs belonging to the same parent entity by matching shared
contacts, addresses, phones, and management company names across transactions.
Outputs real group_merges entries for high-confidence matches and surfaces
suggestions for ambiguous ones.

Usage:
    python -m cleo.discovery --validate    # compare to ground truth
    python -m cleo.discovery --execute     # bulk sort, execute merges
    python -m cleo.discovery --incremental # process new transactions only
    python -m cleo.discovery --dry-run     # preview without merging
"""
