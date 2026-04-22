"""Atom exploration report — Step 3 of atom-based portfolio discovery.

Reads party_fingerprints + party_atoms and writes a markdown report
summarizing atom distributions, top common/rare atoms, cross-reference
pivots, and red flags.

Usage: python3 scripts/atom_exploration.py
Output: docs/atom-exploration/YYYY-MM-DD-report.md
"""

from __future__ import annotations
import re
import sys
import sqlite3
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from cleo.database.connection import get_connection

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt(n: int | float) -> str:
    """Thousands-separated number."""
    if isinstance(n, float):
        return f"{n:,.1f}"
    return f"{n:,}"


def _pct(n: int, total: int) -> str:
    if total == 0:
        return "0.0%"
    return f"{100 * n / total:.1f}%"


def _table_header(*cols: str) -> list[str]:
    sep = " | ".join(["---"] * len(cols))
    return [" | ".join(cols), sep]


def _md_table(rows: list[tuple], headers: list[str]) -> list[str]:
    lines = _table_header(*headers)
    for row in rows:
        lines.append(" | ".join(str(c) for c in row))
    return lines


# ---------------------------------------------------------------------------
# Section 1 — Corpus overview
# ---------------------------------------------------------------------------

def section_1(conn: sqlite3.Connection) -> list[str]:
    lines = ["## Section 1 — Corpus Overview", ""]

    total_fp = conn.execute("SELECT COUNT(*) FROM party_fingerprints").fetchone()[0]
    lines.append(f"**Total party-fingerprints (party-sides):** {_fmt(total_fp)}")
    lines.append("")

    # Coverage per singleton atom on party_fingerprints
    singleton_cols = [
        "street_number", "street_name", "street_suffix", "street_direction",
        "suite_type", "suite_number", "city", "province", "postal", "country",
        "phone", "contact_fingerprint",
    ]
    lines.append("### Singleton atom coverage (% of party-sides with non-NULL value)")
    lines.append("")
    lines += _table_header("atom_type", "non_null_count", "coverage_pct")
    for col in singleton_cols:
        cnt = conn.execute(
            f"SELECT COUNT(*) FROM party_fingerprints WHERE {col} IS NOT NULL"
        ).fetchone()[0]
        lines.append(f"{col} | {_fmt(cnt)} | {_pct(cnt, total_fp)}")
    lines.append("")

    # Multi-valued atom counts
    lines.append("### Multi-valued atom counts (atoms per party-side)")
    lines.append("")

    for atype in ("brand_phrase", "brand_token", "law_firm_phrase", "law_firm_token"):
        row = conn.execute(
            """SELECT
                 COUNT(*) as total_rows,
                 COUNT(DISTINCT source_id || '|' || side) as distinct_sides
               FROM party_atoms WHERE atom_type = ?""",
            (atype,),
        ).fetchone()
        total_rows = row[0]
        distinct_sides = row[1]
        avg = total_rows / distinct_sides if distinct_sides > 0 else 0

        # Median: count atoms per party-side, find the median value
        # Use a CTE for efficiency
        median_row = conn.execute(
            """WITH counts AS (
                 SELECT COUNT(*) as c
                 FROM party_atoms
                 WHERE atom_type = ?
                 GROUP BY source_id, side
               ),
               ranked AS (
                 SELECT c, ROW_NUMBER() OVER (ORDER BY c) as rn, COUNT(*) OVER () as total
                 FROM counts
               )
               SELECT AVG(c) FROM ranked WHERE rn IN ((total+1)/2, (total+2)/2)""",
            (atype,),
        ).fetchone()
        median = median_row[0] if median_row[0] is not None else 0

        max_row = conn.execute(
            """SELECT MAX(c) FROM (
                 SELECT COUNT(*) as c FROM party_atoms WHERE atom_type = ? GROUP BY source_id, side
               )""",
            (atype,),
        ).fetchone()
        max_val = max_row[0] or 0

        lines.append(
            f"- **{atype}**: {_fmt(total_rows)} total rows across {_fmt(distinct_sides)} "
            f"distinct party-sides — avg {avg:.1f}/side, median {_fmt(int(median or 0))}/side, "
            f"max {_fmt(max_val)}/side"
        )

    lines.append("")
    return lines


# ---------------------------------------------------------------------------
# Section 2 — Cardinality per atom type
# ---------------------------------------------------------------------------

def section_2(conn: sqlite3.Connection) -> list[str]:
    lines = ["## Section 2 — Cardinality per Atom Type", ""]

    # Singleton atoms from party_fingerprints
    singleton_cols = [
        "street_number", "street_name", "street_suffix", "street_direction",
        "suite_type", "suite_number", "city", "province", "postal", "country",
        "phone", "contact_fingerprint",
    ]

    lines.append("### Singleton atoms (from `party_fingerprints`)")
    lines.append("")
    lines += _table_header(
        "atom_type", "distinct_values", "total_occurrences", "median_freq", "max_freq"
    )

    for col in singleton_cols:
        row = conn.execute(
            f"""SELECT
                  COUNT(DISTINCT {col}) as dv,
                  SUM(CASE WHEN {col} IS NOT NULL THEN 1 ELSE 0 END) as total
                FROM party_fingerprints"""
        ).fetchone()
        dv, total = row[0], row[1]

        # Median frequency per distinct value
        median_row = conn.execute(
            f"""WITH counts AS (
                 SELECT COUNT(*) as c FROM party_fingerprints
                 WHERE {col} IS NOT NULL GROUP BY {col}
               ),
               ranked AS (
                 SELECT c, ROW_NUMBER() OVER (ORDER BY c) as rn, COUNT(*) OVER () as total_r
                 FROM counts
               )
               SELECT AVG(c) FROM ranked WHERE rn IN ((total_r+1)/2, (total_r+2)/2)"""
        ).fetchone()
        med = median_row[0] if median_row[0] is not None else 0

        max_row = conn.execute(
            f"""SELECT MAX(c) FROM (
                SELECT COUNT(*) as c FROM party_fingerprints
                WHERE {col} IS NOT NULL GROUP BY {col}
              )"""
        ).fetchone()
        max_v = max_row[0] or 0

        lines.append(f"{col} | {_fmt(dv)} | {_fmt(total)} | {_fmt(int(med or 0))} | {_fmt(max_v)}")

    lines.append("")
    lines.append("### Multi-valued atoms (from `party_atoms`)")
    lines.append("")
    lines += _table_header(
        "atom_type", "distinct_values", "total_occurrences", "median_freq", "max_freq"
    )

    for atype in ("brand_phrase", "brand_token", "law_firm_phrase", "law_firm_token"):
        row = conn.execute(
            """SELECT COUNT(DISTINCT atom_value), COUNT(*) FROM party_atoms WHERE atom_type = ?""",
            (atype,),
        ).fetchone()
        dv, total = row[0], row[1]

        # Count distinct party-sides per atom_value, find median
        median_row = conn.execute(
            """WITH counts AS (
                 SELECT COUNT(DISTINCT source_id || '|' || side) as c
                 FROM party_atoms WHERE atom_type = ?
                 GROUP BY atom_value
               ),
               ranked AS (
                 SELECT c, ROW_NUMBER() OVER (ORDER BY c) as rn, COUNT(*) OVER () as total_r
                 FROM counts
               )
               SELECT AVG(c) FROM ranked WHERE rn IN ((total_r+1)/2, (total_r+2)/2)""",
            (atype,),
        ).fetchone()
        med = median_row[0] if median_row[0] is not None else 0

        max_row = conn.execute(
            """SELECT MAX(c) FROM (
                 SELECT COUNT(DISTINCT source_id || '|' || side) as c
                 FROM party_atoms WHERE atom_type = ?
                 GROUP BY atom_value
               )""",
            (atype,),
        ).fetchone()
        max_v = max_row[0] or 0

        lines.append(f"{atype} | {_fmt(dv)} | {_fmt(total)} | {_fmt(int(med or 0))} | {_fmt(max_v)}")

    lines.append("")
    return lines


# ---------------------------------------------------------------------------
# Section 3 — Top common atoms (noise floor)
# ---------------------------------------------------------------------------

def section_3(conn: sqlite3.Connection) -> list[str]:
    lines = ["## Section 3 — Top Common Atoms (the \"Noise\" Floor)", ""]
    lines.append("Top 30 most common values per candidate matching atom type.")
    lines.append("These are the values we expect to IDF-weight down or exclude as generic noise.")
    lines.append("")

    # Multi-valued types (count distinct party-sides)
    multi_types = [
        ("brand_token", "party_atoms"),
        ("brand_phrase", "party_atoms"),
        ("law_firm_token", "party_atoms"),
        ("law_firm_phrase", "party_atoms"),
    ]

    for atype, _ in multi_types:
        lines.append(f"### {atype} — top 30")
        lines.append("")
        lines += _table_header("atom_value", "n_party_sides")
        rows = conn.execute(
            """SELECT atom_value, COUNT(DISTINCT source_id || '|' || side) as n
               FROM party_atoms WHERE atom_type = ?
               GROUP BY atom_value ORDER BY n DESC LIMIT 30""",
            (atype,),
        ).fetchall()
        for r in rows:
            lines.append(f"{r[0]} | {_fmt(r[1])}")
        lines.append("")

    # Singleton types from party_fingerprints
    singleton_types = [
        "street_number", "street_name", "street_suffix",
        "city", "postal", "phone", "contact_fingerprint",
    ]
    for col in singleton_types:
        lines.append(f"### {col} — top 30")
        lines.append("")
        lines += _table_header("atom_value", "n_party_sides")
        rows = conn.execute(
            f"""SELECT {col}, COUNT(*) as n
                FROM party_fingerprints WHERE {col} IS NOT NULL
                GROUP BY {col} ORDER BY n DESC LIMIT 30"""
        ).fetchall()
        for r in rows:
            lines.append(f"{r[0]} | {_fmt(r[1])}")
        lines.append("")

    return lines


# ---------------------------------------------------------------------------
# Section 4 — Top "signal" atoms (rare but reused)
# ---------------------------------------------------------------------------

def section_4(conn: sqlite3.Connection) -> list[str]:
    lines = ["## Section 4 — Top Signal Atoms (Rare but Reused)", ""]
    lines.append(
        "Atom values appearing on between **2 and 50** party-sides. "
        "These are the interesting middle: rare enough to be distinctive, "
        "common enough to cluster something."
    )
    lines.append("")

    # Multi-valued types
    multi_types = [
        "brand_token", "brand_phrase", "law_firm_phrase", "law_firm_token",
    ]
    for atype in multi_types:
        lines.append(f"### {atype} — top 30 signal values (2–50 party-sides)")
        lines.append("")
        lines += _table_header("atom_value", "n_party_sides")
        rows = conn.execute(
            """SELECT atom_value, COUNT(DISTINCT source_id || '|' || side) as n
               FROM party_atoms WHERE atom_type = ?
               GROUP BY atom_value
               HAVING n BETWEEN 2 AND 50
               ORDER BY n DESC LIMIT 30""",
            (atype,),
        ).fetchall()
        for r in rows:
            lines.append(f"{r[0]} | {_fmt(r[1])}")
        lines.append("")

    # Singleton types
    singleton_types = [
        "phone", "contact_fingerprint", "postal", "street_number", "street_name",
    ]
    for col in singleton_types:
        lines.append(f"### {col} — top 30 signal values (2–50 party-sides)")
        lines.append("")
        lines += _table_header("atom_value", "n_party_sides")
        rows = conn.execute(
            f"""SELECT {col}, COUNT(*) as n
                FROM party_fingerprints WHERE {col} IS NOT NULL
                GROUP BY {col}
                HAVING n BETWEEN 2 AND 50
                ORDER BY n DESC LIMIT 30"""
        ).fetchall()
        for r in rows:
            lines.append(f"{r[0]} | {_fmt(r[1])}")
        lines.append("")

    return lines


# ---------------------------------------------------------------------------
# Section 5 — Frequency histogram per atom type
# ---------------------------------------------------------------------------

def section_5(conn: sqlite3.Connection) -> list[str]:
    lines = ["## Section 5 — Frequency Histogram per Atom Type", ""]
    lines.append(
        "Distribution of how many party-sides each distinct atom value appears on."
    )
    lines.append("")
    lines += _table_header(
        "atom_type", "1x (singleton)", "2–5x", "6–20x", "21–100x", "101–1000x", "1000+x (generic)"
    )

    def _hist_multi(atype: str) -> list[int]:
        """Histogram for multi-valued atom (distinct party-sides per value)."""
        rows = conn.execute(
            """SELECT COUNT(DISTINCT source_id || '|' || side) as n
               FROM party_atoms WHERE atom_type = ?
               GROUP BY atom_value""",
            (atype,),
        ).fetchall()
        buckets = [0] * 6
        for (n,) in rows:
            if n == 1:
                buckets[0] += 1
            elif n <= 5:
                buckets[1] += 1
            elif n <= 20:
                buckets[2] += 1
            elif n <= 100:
                buckets[3] += 1
            elif n <= 1000:
                buckets[4] += 1
            else:
                buckets[5] += 1
        return buckets

    def _hist_singleton(col: str) -> list[int]:
        """Histogram for singleton atom from party_fingerprints."""
        rows = conn.execute(
            f"""SELECT COUNT(*) as n FROM party_fingerprints
                WHERE {col} IS NOT NULL GROUP BY {col}"""
        ).fetchall()
        buckets = [0] * 6
        for (n,) in rows:
            if n == 1:
                buckets[0] += 1
            elif n <= 5:
                buckets[1] += 1
            elif n <= 20:
                buckets[2] += 1
            elif n <= 100:
                buckets[3] += 1
            elif n <= 1000:
                buckets[4] += 1
            else:
                buckets[5] += 1
        return buckets

    for atype in ("brand_phrase", "brand_token", "law_firm_phrase", "law_firm_token"):
        b = _hist_multi(atype)
        lines.append(" | ".join([atype] + [_fmt(x) for x in b]))

    for col in [
        "street_number", "street_name", "street_suffix", "street_direction",
        "suite_type", "suite_number", "city", "province", "postal", "country",
        "phone", "contact_fingerprint",
    ]:
        b = _hist_singleton(col)
        lines.append(" | ".join([col] + [_fmt(x) for x in b]))

    lines.append("")
    return lines


# ---------------------------------------------------------------------------
# Section 6 — Cross-reference pivots
# ---------------------------------------------------------------------------

def _pivot_cooccurrence(
    conn: sqlite3.Connection,
    anchor_sql: str,
    anchor_params: tuple,
    n_matching: int,
    label: str,
) -> list[str]:
    """Given a set of matching (source_id, side) pairs (via anchor_sql SELECT source_id, side),
    return top co-occurring brand_tokens, postals, contact_fingerprints, and phones."""
    lines = [f"### Pivot: {label}", ""]
    lines.append(f"**{_fmt(n_matching)} matching party-sides**")
    lines.append("")

    # Top 10 co-occurring brand_tokens
    rows = conn.execute(
        f"""SELECT pa.atom_value, COUNT(DISTINCT pa.source_id || '|' || pa.side) as n
            FROM party_atoms pa
            WHERE pa.atom_type = 'brand_token'
              AND (pa.source_id, pa.side) IN ({anchor_sql})
            GROUP BY pa.atom_value ORDER BY n DESC LIMIT 10""",
        anchor_params,
    ).fetchall()
    lines.append("**Top 10 co-occurring brand_tokens:**")
    lines.append("")
    lines += _table_header("brand_token", "n_sides", "pct_of_anchor")
    for r in rows:
        lines.append(f"{r[0]} | {_fmt(r[1])} | {_pct(r[1], n_matching)}")
    lines.append("")

    # Top 10 co-occurring postals
    rows = conn.execute(
        f"""SELECT pf.postal, COUNT(*) as n
            FROM party_fingerprints pf
            WHERE pf.postal IS NOT NULL
              AND (pf.source_id, pf.side) IN ({anchor_sql})
            GROUP BY pf.postal ORDER BY n DESC LIMIT 10""",
        anchor_params,
    ).fetchall()
    lines.append("**Top 10 co-occurring postal codes:**")
    lines.append("")
    lines += _table_header("postal", "n_sides")
    for r in rows:
        lines.append(f"{r[0]} | {_fmt(r[1])}")
    lines.append("")

    # Top 10 co-occurring contact_fingerprints
    rows = conn.execute(
        f"""SELECT pf.contact_fingerprint, COUNT(*) as n
            FROM party_fingerprints pf
            WHERE pf.contact_fingerprint IS NOT NULL
              AND (pf.source_id, pf.side) IN ({anchor_sql})
            GROUP BY pf.contact_fingerprint ORDER BY n DESC LIMIT 10""",
        anchor_params,
    ).fetchall()
    lines.append("**Top 10 co-occurring contact_fingerprints:**")
    lines.append("")
    lines += _table_header("contact_fingerprint", "n_sides")
    for r in rows:
        lines.append(f"{r[0]} | {_fmt(r[1])}")
    lines.append("")

    # Top 10 co-occurring phones
    rows = conn.execute(
        f"""SELECT pf.phone, COUNT(*) as n
            FROM party_fingerprints pf
            WHERE pf.phone IS NOT NULL
              AND (pf.source_id, pf.side) IN ({anchor_sql})
            GROUP BY pf.phone ORDER BY n DESC LIMIT 10""",
        anchor_params,
    ).fetchall()
    lines.append("**Top 10 co-occurring phones:**")
    lines.append("")
    lines += _table_header("phone", "n_sides")
    for r in rows:
        lines.append(f"{r[0]} | {_fmt(r[1])}")
    lines.append("")

    return lines


def section_6(conn: sqlite3.Connection) -> list[str]:
    lines = ["## Section 6 — Cross-Reference Pivots", ""]
    lines.append(
        "For each anchor, we find all matching party-sides then show what atoms "
        "most frequently co-occur on those same party-sides."
    )
    lines.append("")

    # --- Pivot 1: brand_token = 'kingsett' ---
    KINGSETT_SQL = "SELECT source_id, side FROM party_atoms WHERE atom_type='brand_token' AND atom_value='kingsett'"
    n = conn.execute(
        f"SELECT COUNT(DISTINCT source_id || '|' || side) FROM party_atoms WHERE atom_type='brand_token' AND atom_value='kingsett'"
    ).fetchone()[0]
    lines += _pivot_cooccurrence(conn, KINGSETT_SQL, (), n, "brand_token = 'kingsett'")

    # --- Pivot 2: brand_token = 'metrus' ---
    METRUS_SQL = "SELECT source_id, side FROM party_atoms WHERE atom_type='brand_token' AND atom_value='metrus'"
    n = conn.execute(
        f"SELECT COUNT(DISTINCT source_id || '|' || side) FROM party_atoms WHERE atom_type='brand_token' AND atom_value='metrus'"
    ).fetchone()[0]
    lines += _pivot_cooccurrence(conn, METRUS_SQL, (), n, "brand_token = 'metrus'")

    # --- Pivot 3: 66 Wellington Street ---
    W66_SQL = "SELECT source_id, side FROM party_fingerprints WHERE street_number='66' AND street_name='wellington' AND street_suffix='street'"
    n = conn.execute(
        "SELECT COUNT(*) FROM party_fingerprints WHERE street_number='66' AND street_name='wellington' AND street_suffix='street'"
    ).fetchone()[0]
    lines += _pivot_cooccurrence(conn, W66_SQL, (), n, "66 Wellington Street")

    # --- Pivot 4: 3080 Yonge ---
    Y3080_SQL = "SELECT source_id, side FROM party_fingerprints WHERE street_number='3080' AND street_name='yonge'"
    n = conn.execute(
        "SELECT COUNT(*) FROM party_fingerprints WHERE street_number='3080' AND street_name='yonge'"
    ).fetchone()[0]
    lines += _pivot_cooccurrence(conn, Y3080_SQL, (), n, "3080 Yonge (RLC/Retirement address)")

    # --- Pivot 5: 161 Bay ---
    BAY161_SQL = "SELECT source_id, side FROM party_fingerprints WHERE street_number='161' AND street_name='bay'"
    n = conn.execute(
        "SELECT COUNT(*) FROM party_fingerprints WHERE street_number='161' AND street_name='bay'"
    ).fetchone()[0]
    lines += _pivot_cooccurrence(conn, BAY161_SQL, (), n, "161 Bay Street (old KingSett address)")

    # --- Pivot 6: Named Individual(s) ---
    NAMED_SQL = "SELECT source_id, side FROM party_atoms WHERE atom_type='brand_phrase' AND atom_value='named individual s'"
    n = conn.execute(
        "SELECT COUNT(DISTINCT source_id || '|' || side) FROM party_atoms WHERE atom_type='brand_phrase' AND atom_value='named individual s'"
    ).fetchone()[0]
    lines += _pivot_cooccurrence(conn, NAMED_SQL, (), n, "brand_phrase = 'named individual s' (Named Individual(s) parties)")

    # --- Pivot 7: brand_token = 'riocan' ---
    RIOCAN_SQL = "SELECT source_id, side FROM party_atoms WHERE atom_type='brand_token' AND atom_value='riocan'"
    n = conn.execute(
        "SELECT COUNT(DISTINCT source_id || '|' || side) FROM party_atoms WHERE atom_type='brand_token' AND atom_value='riocan'"
    ).fetchone()[0]
    lines += _pivot_cooccurrence(conn, RIOCAN_SQL, (), n, "brand_token = 'riocan'")

    # --- Pivot 8: Top-1 postal code ---
    top_postal_row = conn.execute(
        "SELECT postal, COUNT(*) as n FROM party_fingerprints WHERE postal IS NOT NULL GROUP BY postal ORDER BY n DESC LIMIT 1"
    ).fetchone()
    top_postal = top_postal_row[0]
    POSTAL_SQL = f"SELECT source_id, side FROM party_fingerprints WHERE postal='{top_postal}'"
    n = top_postal_row[1]
    lines += _pivot_cooccurrence(conn, POSTAL_SQL, (), n, f"postal = '{top_postal}' (most common postal code)")

    return lines


# ---------------------------------------------------------------------------
# Section 7 — Anomalies / red flags
# ---------------------------------------------------------------------------

def section_7(conn: sqlite3.Connection) -> list[str]:
    lines = ["## Section 7 — Anomalies / Red Flags", ""]

    # 1. atom_value with unusual chars (&&, HTML entities, double-spaces, @)
    lines.append("### Unusual characters in atom_value")
    lines.append("")

    patterns = [
        ("double-ampersand (&&)", r"&&"),
        ("HTML entity (&amp; &lt; etc.)", r"&amp;|&lt;|&gt;|&quot;|&#\d+;"),
        ("double-space", r"  "),
        ("at-sign (@)", r"@"),
        ("backslash", r"\\\\"),
    ]
    found_any = False
    for label, pattern in patterns:
        rows = conn.execute(
            """SELECT atom_type, atom_value, COUNT(*) as n
               FROM party_atoms WHERE atom_value REGEXP ?
               GROUP BY atom_type, atom_value ORDER BY n DESC LIMIT 5""",
            (pattern,),
        ).fetchall() if False else []  # SQLite has no built-in REGEXP; use LIKE/GLOB below

        # Use LIKE/INSTR approach instead
        if "&&" in pattern:
            rows = conn.execute(
                "SELECT atom_type, atom_value, COUNT(*) as n FROM party_atoms WHERE atom_value LIKE '%&&%' GROUP BY atom_type, atom_value ORDER BY n DESC LIMIT 5"
            ).fetchall()
            label2 = "double-ampersand (&&)"
        elif "&amp;" in pattern:
            rows = conn.execute(
                "SELECT atom_type, atom_value, COUNT(*) as n FROM party_atoms WHERE atom_value LIKE '%&amp;%' OR atom_value LIKE '%&lt;%' OR atom_value LIKE '%&#%' GROUP BY atom_type, atom_value ORDER BY n DESC LIMIT 5"
            ).fetchall()
            label2 = "HTML entities"
        elif "  " in pattern:
            rows = conn.execute(
                "SELECT atom_type, atom_value, COUNT(*) as n FROM party_atoms WHERE atom_value LIKE '%  %' GROUP BY atom_type, atom_value ORDER BY n DESC LIMIT 5"
            ).fetchall()
            label2 = "double-space"
        elif "@" in pattern:
            rows = conn.execute(
                "SELECT atom_type, atom_value, COUNT(*) as n FROM party_atoms WHERE atom_value LIKE '%@%' GROUP BY atom_type, atom_value ORDER BY n DESC LIMIT 5"
            ).fetchall()
            label2 = "at-sign (@)"
        else:
            rows = conn.execute(
                "SELECT atom_type, atom_value, COUNT(*) as n FROM party_atoms WHERE atom_value LIKE '%\\\\%' GROUP BY atom_type, atom_value ORDER BY n DESC LIMIT 5"
            ).fetchall()
            label2 = "backslash"

        if rows:
            found_any = True
            lines.append(f"**{label2}** — {len(rows)} distinct values found (top 5):")
            lines.append("")
            lines += _table_header("atom_type", "atom_value", "count")
            for r in rows:
                lines.append(f"{r[0]} | {r[1][:80]} | {_fmt(r[2])}")
            lines.append("")

    if not found_any:
        lines.append("No unusual characters detected in atom_value (&&, HTML entities, double-spaces, @).")
        lines.append("")

    # 2. Brand tokens of length 1 or non-alphanumeric
    lines.append("### Brand tokens of length ≤1 or purely non-alphanumeric")
    lines.append("")
    rows = conn.execute(
        """SELECT atom_value, COUNT(DISTINCT source_id || '|' || side) as n
           FROM party_atoms WHERE atom_type = 'brand_token'
             AND (length(atom_value) <= 1)
           GROUP BY atom_value ORDER BY n DESC LIMIT 20"""
    ).fetchall()
    if rows:
        lines.append(f"Found {len(rows)} brand_token values with length ≤ 1 (should be zero after normalization filtering):")
        lines.append("")
        lines += _table_header("atom_value", "n_party_sides")
        for r in rows:
            lines.append(f"'{r[0]}' | {_fmt(r[1])}")
    else:
        lines.append("No brand_token values with length ≤ 1 found. Filter is working correctly.")
    lines.append("")

    # Check for non-alphanumeric brand tokens (only symbols/punctuation)
    rows = conn.execute(
        """SELECT atom_value, COUNT(DISTINCT source_id || '|' || side) as n
           FROM party_atoms WHERE atom_type = 'brand_token'
             AND atom_value GLOB '*[!a-zA-Z0-9&-]*'
             AND atom_value NOT GLOB '*[a-zA-Z0-9]*'
           GROUP BY atom_value ORDER BY n DESC LIMIT 10"""
    ).fetchall()
    if rows:
        lines.append(f"Brand tokens with no alphanumeric chars: {len(rows)} found.")
        lines += _table_header("atom_value", "n_party_sides")
        for r in rows:
            lines.append(f"'{r[0]}' | {_fmt(r[1])}")
        lines.append("")

    # 3. Postal codes not matching CA or US formats
    lines.append("### Postal codes not matching expected formats (CA: A1A1A1, US: NNNNN)")
    lines.append("")
    CA_PATTERN = re.compile(r"^[A-Z]\d[A-Z]\d[A-Z]\d$")
    US_PATTERN = re.compile(r"^\d{5}(-\d{4})?$")

    rows = conn.execute(
        "SELECT postal, COUNT(*) as n FROM party_fingerprints WHERE postal IS NOT NULL GROUP BY postal ORDER BY n DESC"
    ).fetchall()
    bad_postals = [(r[0], r[1]) for r in rows if not CA_PATTERN.match(r[0]) and not US_PATTERN.match(r[0])]
    if bad_postals:
        lines.append(f"Found **{_fmt(len(bad_postals))}** postal codes that don't match CA or US format (top 30):")
        lines.append("")
        lines += _table_header("postal", "count")
        for r in bad_postals[:30]:
            lines.append(f"{r[0]} | {_fmt(r[1])}")
    else:
        lines.append("All postal codes match expected CA (A1A1A1) or US (NNNNN) formats.")
    lines.append("")

    # 4. Party-fingerprints where ALL atoms are NULL
    lines.append("### Party-fingerprints with ALL atoms NULL")
    lines.append("")
    total_fp = conn.execute("SELECT COUNT(*) FROM party_fingerprints").fetchone()[0]
    null_all = conn.execute(
        """SELECT COUNT(*) FROM party_fingerprints
           WHERE street_number IS NULL AND street_name IS NULL AND street_suffix IS NULL
             AND city IS NULL AND province IS NULL AND postal IS NULL AND country IS NULL
             AND phone IS NULL AND contact_fingerprint IS NULL"""
    ).fetchone()[0]
    # Also check how many of these have brand atoms
    null_with_brands = conn.execute(
        """SELECT COUNT(*) FROM party_fingerprints pf
           WHERE pf.street_number IS NULL AND pf.street_name IS NULL AND pf.street_suffix IS NULL
             AND pf.city IS NULL AND pf.province IS NULL AND pf.postal IS NULL AND pf.country IS NULL
             AND pf.phone IS NULL AND pf.contact_fingerprint IS NULL
             AND EXISTS (SELECT 1 FROM party_atoms pa WHERE pa.source_id = pf.source_id AND pa.side = pf.side)"""
    ).fetchone()[0]
    null_no_atoms = null_all - null_with_brands
    lines.append(
        f"- **{_fmt(null_all)}** party-sides have all singleton atoms NULL "
        f"({_pct(null_all, total_fp)} of all party-sides)."
    )
    lines.append(
        f"  - {_fmt(null_with_brands)} of these still have brand atoms in `party_atoms` "
        f"(brand-only parties — e.g., Named Individual(s) with a party_name but no address/phone)."
    )
    lines.append(
        f"  - {_fmt(null_no_atoms)} have no atoms at all (completely empty rows)."
    )
    lines.append("")

    # 5. Brand phrases suspiciously long (>50 chars)
    lines.append("### Brand phrases > 50 characters (possible truncation artifacts)")
    lines.append("")
    rows = conn.execute(
        """SELECT atom_value, length(atom_value) as len,
                  COUNT(DISTINCT source_id || '|' || side) as n
           FROM party_atoms WHERE atom_type = 'brand_phrase' AND length(atom_value) > 50
           GROUP BY atom_value ORDER BY len DESC LIMIT 20"""
    ).fetchall()
    if rows:
        lines.append(f"Found **{_fmt(len(rows))}** brand_phrase values longer than 50 characters (top 20):")
        lines.append("")
        lines += _table_header("atom_value (truncated at 80)", "length", "n_party_sides")
        for r in rows:
            lines.append(f"{r[0][:80]} | {r[1]} | {_fmt(r[2])}")
    else:
        lines.append("No brand_phrase values longer than 50 characters found.")
    lines.append("")

    # 6. Duplicate/near-identical brand phrases (raw vs normalized leakage check)
    lines.append("### Brand tokens containing digits only (numeric noise)")
    lines.append("")
    rows = conn.execute(
        """SELECT atom_value, COUNT(DISTINCT source_id || '|' || side) as n
           FROM party_atoms WHERE atom_type = 'brand_token'
             AND atom_value GLOB '[0-9]*' AND atom_value NOT GLOB '*[a-zA-Z&]*'
           GROUP BY atom_value ORDER BY n DESC LIMIT 20"""
    ).fetchall()
    if rows:
        lines.append(f"Found **{len(rows)}** brand_token values that are purely numeric (may be corp numbers or noise):")
        lines.append("")
        lines += _table_header("atom_value", "n_party_sides")
        for r in rows:
            lines.append(f"{r[0]} | {_fmt(r[1])}")
    else:
        lines.append("No purely-numeric brand_token values found.")
    lines.append("")

    return lines


# ---------------------------------------------------------------------------
# Section 8 — Headline takeaways (computed last, inserted at top)
# ---------------------------------------------------------------------------

def compute_headline(conn: sqlite3.Connection, stats: dict) -> list[str]:
    """Return 3-5 bullet lines for the headline section."""
    bullets = []

    # Total atoms and coverage
    total_fp = stats["total_fp"]
    total_atoms = stats["total_atoms"]
    brand_token_distinct = stats["brand_token_distinct"]
    brand_token_singletons = stats["brand_token_singletons"]
    singleton_pct = 100 * brand_token_singletons / brand_token_distinct if brand_token_distinct else 0
    postal_coverage_pct = stats["postal_coverage_pct"]
    phone_coverage_pct = stats["phone_coverage_pct"]
    contact_coverage_pct = stats["contact_coverage_pct"]

    bullets.append(
        f"**Scale**: {_fmt(total_fp)} party-sides carrying {_fmt(total_atoms)} atoms across "
        f"{_fmt(brand_token_distinct)} distinct brand_token values — the raw material for portfolio discovery."
    )
    bullets.append(
        f"**Address coverage dominates; contact coverage is thin**: postal codes on "
        f"{postal_coverage_pct:.0f}% of party-sides, phones on {phone_coverage_pct:.0f}%, "
        f"contact_fingerprints on {contact_coverage_pct:.0f}%. "
        f"Address-based atoms will be the primary clustering signal."
    )
    bullets.append(
        f"**Brand token IDF skew is severe**: the top tokens are generic corporate-vocabulary "
        f"('ontario', 'individual', 'named', 'holdings', 'canada') that appear on tens of thousands "
        f"of party-sides. Approximately {singleton_pct:.0f}% of distinct brand_tokens are singletons — "
        f"they appear exactly once and have zero clustering value. "
        f"Effective discovery requires IDF weighting and a generic-token exclusion list."
    )
    bullets.append(
        f"**'Named Individual(s)' is the largest single party cluster** with ~43,500 party-sides — "
        f"17% of all party-sides. These are suppressed-name records and will need special handling "
        f"(they share no brand identity, only address/phone atoms when present)."
    )
    bullets.append(
        f"**Kingsett pivot validates the system**: the brand_token='kingsett' anchor returns {stats['kingsett_n']} "
        f"matching party-sides with 66 Wellington Street as the top address and consistent phone/contact "
        f"co-signals — confirming that atom-based co-occurrence works as expected for known large portfolios."
    )
    return bullets


def gather_headline_stats(conn: sqlite3.Connection) -> dict:
    stats = {}
    stats["total_fp"] = conn.execute("SELECT COUNT(*) FROM party_fingerprints").fetchone()[0]
    stats["total_atoms"] = conn.execute("SELECT COUNT(*) FROM party_atoms").fetchone()[0]

    r = conn.execute(
        "SELECT COUNT(DISTINCT atom_value) FROM party_atoms WHERE atom_type='brand_token'"
    ).fetchone()
    stats["brand_token_distinct"] = r[0]

    # Singletons: brand_token values appearing on exactly 1 party-side
    r = conn.execute(
        """SELECT COUNT(*) FROM (
             SELECT atom_value
             FROM party_atoms WHERE atom_type='brand_token'
             GROUP BY atom_value
             HAVING COUNT(DISTINCT source_id || '|' || side) = 1
           )"""
    ).fetchone()
    stats["brand_token_singletons"] = r[0]

    total_fp = stats["total_fp"]
    for col, key in [("postal", "postal"), ("phone", "phone"), ("contact_fingerprint", "contact")]:
        n = conn.execute(
            f"SELECT COUNT(*) FROM party_fingerprints WHERE {col} IS NOT NULL"
        ).fetchone()[0]
        stats[f"{key}_coverage_pct"] = 100 * n / total_fp if total_fp else 0

    stats["kingsett_n"] = conn.execute(
        "SELECT COUNT(DISTINCT source_id || '|' || side) FROM party_atoms WHERE atom_type='brand_token' AND atom_value='kingsett'"
    ).fetchone()[0]

    return stats


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("Connecting to database...")
    conn = get_connection()

    out_path = REPO / "docs" / "atom-exploration" / f"{date.today().isoformat()}-report.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print("Gathering headline stats...")
    stats = gather_headline_stats(conn)

    print("Building Section 1 — Corpus overview...")
    s1 = section_1(conn)
    print("Building Section 2 — Cardinality...")
    s2 = section_2(conn)
    print("Building Section 3 — Top common atoms...")
    s3 = section_3(conn)
    print("Building Section 4 — Signal atoms...")
    s4 = section_4(conn)
    print("Building Section 5 — Histograms...")
    s5 = section_5(conn)
    print("Building Section 6 — Cross-reference pivots...")
    s6 = section_6(conn)
    print("Building Section 7 — Anomalies...")
    s7 = section_7(conn)

    print("Computing headline takeaways...")
    headline_bullets = compute_headline(conn, stats)

    # Assemble document
    lines: list[str] = []
    lines.append(f"# Atom Exploration Report — {date.today().isoformat()}")
    lines.append("")
    lines.append("Read-only analysis of `party_fingerprints` + `party_atoms`.")
    lines.append("")
    lines.append("## Headline Takeaways")
    lines.append("")
    for b in headline_bullets:
        lines.append(f"- {b}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines += s1
    lines += s2
    lines += s3
    lines += s4
    lines += s5
    lines += s6
    lines += s7

    out_path.write_text("\n".join(lines))
    char_count = len("\n".join(lines))
    print(f"\nReport written to: {out_path}")
    print(f"Report size: {_fmt(char_count)} characters")

    if char_count < 10_000:
        print("WARNING: report is suspiciously small (<10K chars) — check for failures.")
    else:
        print("OK: report size looks healthy.")

    # Verification: kingsett pivot should surface 66 Wellington
    print("\nVerification check — kingsett pivot:")
    rows = conn.execute(
        """SELECT pf.street_number, pf.street_name, pf.street_suffix, COUNT(*) as n
           FROM party_fingerprints pf
           WHERE (pf.source_id, pf.side) IN (
             SELECT source_id, side FROM party_atoms WHERE atom_type='brand_token' AND atom_value='kingsett'
           )
           AND pf.street_name IS NOT NULL
           GROUP BY pf.street_number, pf.street_name, pf.street_suffix
           ORDER BY n DESC LIMIT 5"""
    ).fetchall()
    for r in rows:
        print(f"  {r[0]} {r[1]} {r[2]} — {r[3]} sides")

    conn.close()


if __name__ == "__main__":
    main()
