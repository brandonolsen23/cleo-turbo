"""IDF (inverse document frequency) computation over atoms.

IDF answers: "how many party-sides share this atom value out of the total?"
Low IDF = common = weak signal. High IDF = rare = strong signal.
Formula: IDF(v) = log(N / (1 + df(v))) where N is total party-sides
and df(v) is count carrying that (atom_type, atom_value).
"""

from __future__ import annotations
import math
from typing import Dict, Tuple


def compute_idf_map(conn) -> Dict[Tuple[str, str], float]:
    """Return a dict keyed by (atom_type, atom_value) with IDF values.

    Covers both multi-valued atoms (from party_atoms) and singleton atoms
    (from party_fingerprints columns — phone, contact_fingerprint, postal).
    """
    n = conn.execute(
        "SELECT COUNT(*) FROM party_fingerprints"
    ).fetchone()[0]
    if n == 0:
        return {}

    idf: Dict[Tuple[str, str], float] = {}

    # Multi-valued atoms — count distinct party-sides per (atom_type, atom_value)
    for row in conn.execute(
        """SELECT atom_type, atom_value, COUNT(DISTINCT source_id || '|' || side) AS df
           FROM party_atoms
           GROUP BY atom_type, atom_value"""
    ):
        idf[(row[0], row[1])] = math.log(n / (1 + row[2]))

    # Singleton atoms — count non-NULL occurrences per column.
    # Introspect to gracefully handle connections whose party_fingerprints
    # schema is a subset (e.g. in-memory test fixtures).
    existing_cols = {
        row[1]
        for row in conn.execute("PRAGMA table_info(party_fingerprints)")
    }
    for col in ("phone", "contact_fingerprint", "postal"):
        if col not in existing_cols:
            continue
        for row in conn.execute(
            f"""SELECT {col} AS v, COUNT(*) AS df
                FROM party_fingerprints
                WHERE {col} IS NOT NULL AND {col} != ''
                GROUP BY {col}"""
        ):
            idf[(col, row[0])] = math.log(n / (1 + row[1]))

    return idf
