"""AI sidebar tool implementations.

Three tools that the LLM can call via the /api/ai/chat endpoint:
- run_sql            — execute a read-only SELECT/WITH/EXPLAIN
- describe_schema    — list tables or inspect one table's columns + samples
- get_entity_url     — pure URL builder for in-app entity links

Run-time safety for run_sql:
1. The AI route opens the SQLite connection in ?mode=ro URI mode, so
   even an LLM-crafted malicious query string can't write.
2. This module additionally screens incoming queries for non-SELECT
   verbs and multi-statement payloads — belt-and-suspenders.
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any

# How many rows to return per run_sql call. Anything over this is
# truncated so the LLM knows to add LIMIT / aggregate.
ROW_CAP = 200

# Hard wall-clock cap per query. The actual interrupt is wired up via
# sqlite3.Connection.set_progress_handler in the AI route at the
# connection level; this constant is documented here for the route
# to import.
QUERY_TIMEOUT_SECONDS = 5

# Hand-curated one-line descriptions per table. Drives the
# describe_schema no-arg form so Claude can pick the right table
# before guessing column names. Mirrors the categorization in
# CLAUDE.md (derived / CRM / system).
TABLE_DESCRIPTIONS: dict[str, str] = {
    # Derived
    "properties":         "One row per parcel (ARN). Display address, city, region, current owner, asset class.",
    "transactions":       "RT (Realtrack) transactions. Sale price, date, parties (registered names in seller_parties / buyer_parties JSON).",
    "transaction_parties":"Per-side party rows for each transaction; links to contacts/groups; contact_title carries 'attn'/'pres'/etc.",
    "transaction_mailing_addresses":"Mailing address listed per transaction side (where to send legal docs).",
    "transaction_brokers":"Broker firms attached to a transaction.",
    "transaction_broker_agents":"Individual broker agents listed under a brokerage.",
    "contacts":           "Stable CON_NNNNN identities. display_name + first_name + last_name (honorifics stripped). status pool/engaged.",
    "groups":             "Stable GRP_NNNNN entities — companies / SPVs / brands. property_count, status pool/engaged.",
    "group_names":        "All raw party_name spellings that map to a single GRP_ ID.",
    "pois":               "Branded POIs from OSM (tenants on a parcel). brand, category, address, address_source.",
    "gw_assessments":     "GeoWarehouse assessment records. owner_name, owner_mailing, assessed_value.",
    "gw_sales_history":   "GeoWarehouse historical sales attached to a property.",
    "group_analytics":    "Pre-computed per-group portfolio metrics (total value, transaction velocity, regions, etc.).",
    "address_root_summary":"Pre-computed counts per (street_number + street_name) — drives the Explorer Addresses tab.",
    "address_base_summary":"Same as above, but with street_suffix included.",
    # CRM (persistent)
    "deals":              "User-created deals. stage, amount, deal_owner, property_id/group_id link.",
    "lists":              "User-created lists. scope = personal | shared.",
    "list_members":       "Membership rows: (list_id, member_type, member_id).",
    "group_contacts":     "Manual contact↔group links (alongside the auto current_group_id).",
    "contact_notes":      "Free-form notes on a contact.",
    "group_notes":        "Free-form notes on a group.",
    "sell_opportunities": "Sell-side opportunities tracked by the user.",
    "buy_mandates":       "Buy-side mandates tracked by the user.",
    "activities":         "User-logged activities (call/email/meeting/note). Auto-FKs into contact_id/property_id/group_id.",
    "user_stars":         "Per-user star/queue. (user_id, entity_type, entity_id).",
    "ai_usage":           "Per-turn token usage from the AI sidebar.",
    "contact_field_overrides":"Per-contact field overrides (e.g. corrected display_name, phone).",
    "group_field_overrides":"Per-group field overrides (status, hq_address, website, hubspot_id).",
    "contact_work_history":"LinkedIn-style work history per contact.",
    # System
    "users":              "Application users.",
    "audit_log":          "Append-only log of CRM mutations.",
    "id_mappings":        "Stable (anchor → CON_/PRO_/GRP_) lookup. Persists across compiler rebuilds.",
    "app_meta":           "Key-value store for compiler counters etc.",
}

# Entity types that the AI can produce in-app links for. Maps each
# type to its route prefix.
ENTITY_URL_PREFIXES: dict[str, str] = {
    "property":    "/properties/",
    "contact":     "/contacts/",
    "group":       "/groups/",
    "deal":        "/deals/",
    "list":        "/lists/",
    "transaction": "/transactions/",
}


class InvalidQueryError(Exception):
    """Raised when a tool call from the LLM is malformed or rejected."""


# ── run_sql ──────────────────────────────────────────────────────────


# Strip a leading EXPLAIN / EXPLAIN QUERY PLAN before checking the verb,
# so EXPLAIN <write-verb> doesn't sneak through. SQLite would refuse the
# write under ?mode=ro anyway — this just keeps the guard's stated
# policy (SELECT / WITH only inside an EXPLAIN) honest.
_EXPLAIN_PREFIX = re.compile(r"^\s*EXPLAIN(\s+QUERY\s+PLAN)?\b\s*", re.IGNORECASE)
_ALLOWED_PREFIX = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)
_BANNED_TOKENS = re.compile(r"\b(PRAGMA|ATTACH|writable_schema)\b", re.IGNORECASE)
_COMMENT = re.compile(r"--[^\n]*|/\*.*?\*/", re.DOTALL)


def _strip_comments(query: str) -> str:
    return _COMMENT.sub("", query)


def _has_multiple_statements(query: str) -> bool:
    """Returns True if there's a `;` followed by anything non-blank.

    A trailing `;` is OK; a `;` mid-string is also OK (we only inspect
    the post-comment-stripped query, but string literals containing `;`
    are rare in select-only queries — a false positive here just rejects
    a query, never permits a write).
    """
    stripped = _strip_comments(query)
    parts = [p for p in stripped.split(";") if p.strip()]
    return len(parts) > 1


def _validate_query(query: str) -> None:
    cleaned = _strip_comments(query)
    inner = _EXPLAIN_PREFIX.sub("", cleaned, count=1)
    if not _ALLOWED_PREFIX.match(inner):
        raise InvalidQueryError(
            "Only SELECT, WITH, and EXPLAIN queries are allowed."
        )
    if _BANNED_TOKENS.search(cleaned):
        raise InvalidQueryError(
            "PRAGMA, ATTACH, and writable_schema references are not allowed."
        )
    if _has_multiple_statements(query):
        raise InvalidQueryError("Multiple statements are not allowed.")


def run_sql(conn: sqlite3.Connection, query: str) -> dict[str, Any]:
    """Execute a read-only SQL query and return shaped results."""
    _validate_query(query)
    cur = conn.execute(query)
    columns = [d[0] for d in (cur.description or [])]
    rows: list[dict[str, Any]] = []
    truncated = False
    for i, r in enumerate(cur):
        if i >= ROW_CAP:
            truncated = True
            break
        rows.append({c: r[c] if isinstance(r, sqlite3.Row) else r[idx]
                     for idx, c in enumerate(columns)})
    return {
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "truncated": truncated,
    }


# ── describe_schema ──────────────────────────────────────────────────


def _list_tables(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        name = r[0] if not isinstance(r, sqlite3.Row) else r["name"]
        try:
            # Double-quote the identifier so a future migration that
            # creates a table with non-standard chars still gets a
            # valid count query. SQL injection isn't possible (mode=ro
            # connection + sqlite_master is our only source of names),
            # but consistency with describe_schema's strict-identifier
            # check is the goal here.
            count = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
        except sqlite3.Error:
            count = None
        out.append({
            "table": name,
            "row_count": count,
            "description": TABLE_DESCRIPTIONS.get(name, ""),
        })
    return out


def _describe_one_table(conn: sqlite3.Connection, table: str) -> dict[str, Any]:
    info = conn.execute(f"PRAGMA table_info({table})").fetchall()
    if not info:
        raise InvalidQueryError(f"Table '{table}' does not exist.")
    columns = [
        {
            "name": r[1] if not isinstance(r, sqlite3.Row) else r["name"],
            "type": r[2] if not isinstance(r, sqlite3.Row) else r["type"],
            "nullable": (r[3] if not isinstance(r, sqlite3.Row) else r["notnull"]) == 0,
            "default": r[4] if not isinstance(r, sqlite3.Row) else r["dflt_value"],
        }
        for r in info
    ]
    sample = conn.execute(f"SELECT * FROM {table} LIMIT 5").fetchall()
    sample_rows = [
        {c["name"]: row[c["name"]] if isinstance(row, sqlite3.Row) else row[i]
         for i, c in enumerate(columns)}
        for row in sample
    ]
    return {
        "table": table,
        "description": TABLE_DESCRIPTIONS.get(table, ""),
        "columns": columns,
        "sample_rows": sample_rows,
    }


def describe_schema(conn: sqlite3.Connection, table: str | None = None) -> dict[str, Any]:
    if table is None:
        return {"tables": _list_tables(conn)}
    # Reject non-identifier inputs to avoid SQL injection in PRAGMA / SELECT
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table):
        raise InvalidQueryError(f"Invalid table name: {table!r}")
    return _describe_one_table(conn, table)


# ── get_entity_url ───────────────────────────────────────────────────


def get_entity_url(entity_type: str, entity_id: str) -> str:
    prefix = ENTITY_URL_PREFIXES.get(entity_type)
    if prefix is None:
        raise InvalidQueryError(
            f"Unknown entity_type {entity_type!r}. Allowed: "
            f"{sorted(ENTITY_URL_PREFIXES)}"
        )
    if not entity_id:
        raise InvalidQueryError("entity_id is required.")
    return f"{prefix}{entity_id}"


# ── page_context loader ─────────────────────────────────────────────


def load_page_context(
    conn: sqlite3.Connection,
    page_context: dict[str, str] | None,
) -> str:
    """Build the natural-language `{{page_context_block}}` string that
    gets injected into the system prompt.

    Returns "" when the user didn't supply page context, when the
    entity_type is unknown, or when the requested id doesn't resolve.
    """
    if not page_context:
        return ""
    etype = page_context.get("entity_type")
    eid = page_context.get("id")
    if not etype or not eid:
        return ""

    if etype == "property":
        row = conn.execute(
            "SELECT id, display_address, city, current_owner_name "
            "FROM properties WHERE id = ?",
            (eid,),
        ).fetchone()
        if not row:
            return ""
        owner = row["current_owner_name"] or "(no owner on file)"
        addr = row["display_address"] or "(no address on file)"
        city = row["city"] or ""
        return (
            f"User is currently looking at property {row['id']} ({addr}"
            + (f", {city}" if city else "")
            + f"). Owner: {owner}."
        )

    if etype == "contact":
        row = conn.execute(
            "SELECT id, display_name, company_name FROM contacts WHERE id = ?",
            (eid,),
        ).fetchone()
        if not row:
            return ""
        company = row["company_name"]
        company_clause = f" Currently at {company}." if company else ""
        return (
            f"User is currently looking at contact {row['id']} ({row['display_name']})."
            + company_clause
        )

    if etype == "group":
        row = conn.execute(
            "SELECT id, display_name, property_count FROM groups WHERE id = ?",
            (eid,),
        ).fetchone()
        if not row:
            return ""
        n = row["property_count"] or 0
        return (
            f"User is currently looking at group {row['id']} ({row['display_name']}). "
            f"property_count={n}."
        )

    if etype == "deal":
        row = conn.execute(
            "SELECT id, name, stage FROM deals WHERE id = ?",
            (eid,),
        ).fetchone()
        if not row:
            return ""
        return f"User is currently looking at deal {row['id']} ({row['name']}, stage={row['stage']})."

    if etype == "list":
        row = conn.execute(
            "SELECT id, name, scope FROM lists WHERE id = ?",
            (eid,),
        ).fetchone()
        if not row:
            return ""
        return f"User is currently looking at list {row['id']} ({row['name']}, scope={row['scope']})."

    if etype == "transaction":
        row = conn.execute(
            "SELECT source_id, sale_date, display_address, sale_price "
            "FROM transactions WHERE source_id = ?",
            (eid,),
        ).fetchone()
        if not row:
            return ""
        return (
            f"User is currently looking at transaction {row['source_id']} "
            f"(sale_date={row['sale_date']}, address={row['display_address']}, "
            f"price={row['sale_price']})."
        )

    return ""
