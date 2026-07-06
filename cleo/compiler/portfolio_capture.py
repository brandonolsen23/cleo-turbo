"""
Portfolio Capture — pure functions behind POST /api/portfolio/capture (M2/M4).

Called by cleo/web/routes/portfolio.py inside a single transaction; every
function takes a connection and plain dicts, so it is unit-testable without
HTTP. Ownership logic is NOT implemented here — links are written to
manual_owner_links and the caller runs compiler.owner_overrides
.apply_owner_overrides (spec Section 8). Merges are never executed here
(spec D4); the route applies them only on explicit commit.
"""

import json

from ..atoms.normalize import (
    normalize_brand,
    normalize_phone,
    normalize_contact_name,
    normalize_arn,
    compose_address_key,
    parse_address_parts,
)
from ..database.group_ids import _next_group_id

SWEEP_SOURCE = "match_key_sweep"

# Single common words that must never drive a sweep on their own
# (the "Forum problem", spec 9.2).
COMMON_SINGLE_WORDS = frozenset({
    "forum", "plaza", "holdings", "holding", "group", "properties",
    "property", "realty", "investments", "investment", "developments",
    "development", "management", "capital", "centre", "center", "corp",
    "inc", "ltd", "limited", "mall", "square", "park", "place", "homes",
    "estates", "enterprises", "company", "partners", "trust", "canada",
    "ontario", "toronto",
})


class CaptureError(Exception):
    """Validation/conflict error carrying an HTTP status code."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def ensure_capture_columns(conn):
    """Idempotent runtime migration: add group_match_keys.sweepable where the
    DB predates the M4 column (schema.py now includes it for fresh DBs)."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(group_match_keys)")}
    if "sweepable" not in cols:
        conn.execute(
            "ALTER TABLE group_match_keys ADD COLUMN sweepable INTEGER DEFAULT 1"
        )


# ── Group resolution (spec Section 10) ────────────────────────────────

def upsert_group(conn, group: dict, merge_candidates, captured_by):
    """Resolve or create the parent group. Returns (group_id, created).

    Resolution order: explicit group.id -> exact normalized-name match ->
    mint a new GRP_ id. Raises CaptureError(409) when the normalized name
    collides with a group we cannot safely treat as the same entity
    (different display name, or a listed merge candidate) and no explicit
    id was supplied.
    """
    display = (group.get("display_name") or "").strip()
    norm = normalize_brand(display)
    if not norm:
        raise CaptureError(422, "group.display_name normalizes to nothing")

    explicit_id = group.get("id")
    if explicit_id:
        row = conn.execute(
            "SELECT id FROM groups WHERE id = ?", (explicit_id,)
        ).fetchone()
        if not row:
            raise CaptureError(422, f"group.id {explicit_id} not found")
        return explicit_id, False

    # Existing rows carry reconciler-format normalized names (UPPERCASE,
    # legal suffixes stripped); capture-created rows carry normalize_brand.
    # Look up both forms so re-POSTs and legacy groups both resolve.
    from .reconciler import normalize_group_name
    legacy_norm = normalize_group_name(display)
    rows = conn.execute(
        "SELECT id, display_name FROM groups "
        "WHERE normalized_name IN (?, ?) AND status != 'merged'",
        (norm, legacy_norm),
    ).fetchall()

    if len(rows) == 1:
        row = rows[0]
        if row["id"] in (merge_candidates or []):
            raise CaptureError(
                409,
                f"normalized name '{norm}' matches merge candidate "
                f"{row['id']}; a group cannot be merged into itself — "
                "supply group.id explicitly",
            )
        if (row["display_name"] or "").strip().lower() == display.lower():
            return row["id"], False
        raise CaptureError(
            409,
            f"normalized name '{norm}' collides with existing group "
            f"{row['id']} ('{row['display_name']}'); supply group.id to "
            "reuse it or rename the parent",
        )
    if len(rows) > 1:
        ids = ", ".join(r["id"] for r in rows)
        raise CaptureError(
            409,
            f"normalized name '{norm}' matches multiple groups ({ids}); "
            "supply group.id explicitly",
        )

    gid = _next_group_id(conn)
    conn.execute(
        "INSERT INTO groups (id, display_name, normalized_name, status, "
        "hq_address, website) VALUES (?, ?, ?, 'pool', ?, ?)",
        (gid, display, norm, group.get("hq_address"), group.get("website")),
    )
    # Index the new group in groups_fts (external-content FTS5 over groups;
    # the compiler rebuilds it in bulk but captures happen between rebuilds,
    # so without this the group is invisible to search).
    row = conn.execute(
        "SELECT rowid FROM groups WHERE id = ?", (gid,)
    ).fetchone()
    conn.execute(
        "INSERT INTO groups_fts(rowid, id, display_name) VALUES (?, ?, ?)",
        (row["rowid"] if hasattr(row, "keys") else row[0], gid, display),
    )
    return gid, True


# ── Profile / aliases / match keys / contacts ─────────────────────────

def write_profile(conn, group_id: str, group: dict, captured_by: str):
    """Upsert the group_profile row for this group (one row per group)."""
    business_lines = json.dumps(group.get("business_lines") or [])
    partners = json.dumps(group.get("partners") or [])
    existing = conn.execute(
        "SELECT id FROM group_profile WHERE group_id = ?", (group_id,)
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE group_profile SET canonical_name=?, summary=?, "
            "business_lines=?, corp_address=?, domain=?, website=?, "
            "partners=?, source='web_capture', source_url=?, web_asserted=1, "
            "captured_by=?, updated_at=datetime('now') WHERE id=?",
            (group.get("display_name"), group.get("summary"), business_lines,
             group.get("hq_address"), group.get("domain"),
             group.get("website"), partners, group.get("source_url"),
             captured_by, existing["id"]),
        )
    else:
        conn.execute(
            "INSERT INTO group_profile (group_id, canonical_name, summary, "
            "business_lines, corp_address, domain, website, partners, "
            "source, source_url, web_asserted, captured_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'web_capture', ?, 1, ?)",
            (group_id, group.get("display_name"), group.get("summary"),
             business_lines, group.get("hq_address"), group.get("domain"),
             group.get("website"), partners, group.get("source_url"),
             captured_by),
        )


def write_aliases(conn, group_id: str, aliases, captured_by: str) -> int:
    """Insert aliases (dedup on UNIQUE(group_id, alias)). Returns rows added."""
    added = 0
    for a in aliases or []:
        alias = (a.get("alias") or "").strip()
        if not alias:
            continue
        cur = conn.execute(
            "INSERT OR IGNORE INTO group_aliases (group_id, alias, "
            "normalized, source, source_url, confidence, captured_by) "
            "VALUES (?, ?, ?, 'web_capture', ?, ?, ?)",
            (group_id, alias, normalize_brand(alias), a.get("source_url"),
             a.get("confidence"), captured_by),
        )
        added += cur.rowcount
    return added


def _normalize_domain(raw):
    s = (raw or "").strip().lower()
    s = s.replace("https://", "").replace("http://", "")
    if s.startswith("www."):
        s = s[4:]
    return s.rstrip("/") or None


def write_match_keys(conn, group_id: str, match_keys, captured_by: str):
    """Normalize + guard + insert match keys. Returns (added, warnings).

    Specificity guard (spec 9.2):
      - spv_name normalizing to a single COMMON word -> CaptureError 422
        (a rejected low-specificity key, spec 6.3).
      - spv_name normalizing to a single uncommon token, or an address
        missing street number/city -> stored with sweepable=0 (identity
        only, never drives attachment) plus a warning in the diff.
    """
    added, warnings = 0, []
    for mk in match_keys or []:
        ktype = mk.get("type")
        raw = (mk.get("value_raw") or "").strip()
        if not raw:
            continue
        sweepable = 1
        if ktype == "address":
            value = compose_address_key(raw)
            if not value:
                warnings.append(f"address match key {raw!r} unparseable — skipped")
                continue
            parts = parse_address_parts(raw)
            if not parts or not parts.get("street_number") or not parts.get("city"):
                sweepable = 0
                warnings.append(
                    f"address match key {raw!r} lacks street number + city — "
                    "stored identity-only (sweepable=0)")
        elif ktype == "spv_name":
            value = normalize_brand(raw)
            if not value:
                warnings.append(f"spv_name match key {raw!r} normalizes to nothing — skipped")
                continue
            tokens = value.split()
            if len(tokens) < 2 and tokens[0] in COMMON_SINGLE_WORDS:
                raise CaptureError(
                    422,
                    f"spv_name match key {raw!r} normalizes to the single "
                    f"common word '{value}' — rejected (specificity guard, "
                    "spec 9.2)")
            if len(tokens) < 2:
                sweepable = 0
                warnings.append(
                    f"spv_name match key {raw!r} is a single token — "
                    "stored identity-only (sweepable=0)")
        elif ktype == "phone":
            value = normalize_phone(raw)
            sweepable = 0  # stored, not swept (spec D3)
            if not value:
                warnings.append(f"phone match key {raw!r} invalid — skipped")
                continue
        elif ktype == "domain":
            value = _normalize_domain(raw)
            sweepable = 0  # identity/dedup only (spec D3)
            if not value:
                continue
        elif ktype == "person":
            parts = raw.split()
            first = parts[0] if parts else None
            last = " ".join(parts[1:]) if len(parts) > 1 else None
            value = normalize_contact_name(first, last)
            sweepable = 0  # stored, not swept (spec D3)
            if not value:
                continue
        else:
            warnings.append(f"unknown match key type {ktype!r} — skipped")
            continue

        cur = conn.execute(
            "INSERT OR IGNORE INTO group_match_keys (group_id, key_type, "
            "value, value_raw, source, source_url, confidence, sweepable, "
            "captured_by) VALUES (?, ?, ?, ?, 'web_capture', ?, ?, ?, ?)",
            (group_id, ktype, value, raw, mk.get("source_url"),
             mk.get("confidence"), sweepable, captured_by),
        )
        added += cur.rowcount
    return added, warnings


def write_contacts(conn, group_id: str, contacts, captured_by: str) -> int:
    """Upsert contacts (matched by reconciler name fingerprint) and link
    them via group_contacts. Returns the number of links now present."""
    from .reconciler import make_name_fingerprint
    linked = 0
    for c in contacts or []:
        name = (c.get("name") or "").strip()
        if not name:
            continue
        fp = make_name_fingerprint(name)
        if not fp:
            continue
        row = conn.execute(
            "SELECT id FROM contacts WHERE name_fingerprint = ?", (fp,)
        ).fetchone()
        if row:
            contact_id = row["id"]
        else:
            nrow = conn.execute(
                "SELECT MAX(CAST(SUBSTR(id, 5) AS INTEGER)) FROM contacts "
                "WHERE id LIKE 'CON\\_%' ESCAPE '\\'"
            ).fetchone()
            contact_id = f"CON_{(nrow[0] or 0) + 1:05d}"
            parts = name.split()
            conn.execute(
                "INSERT INTO contacts (id, name_fingerprint, first_name, "
                "last_name, display_name, phone, email, status, source) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'pool', 'portfolio_capture')",
                (contact_id, fp, parts[0] if parts else None,
                 " ".join(parts[1:]) or None, name,
                 normalize_phone(c.get("phone")), c.get("email")),
            )
        conn.execute(
            "INSERT OR IGNORE INTO group_contacts (group_id, contact_id, "
            "is_current, role) VALUES (?, ?, ?, ?)",
            (group_id, contact_id,
             1 if c.get("is_current", True) else 0, c.get("role")),
        )
        linked += 1
    return linked


# ── Property links (spec 6.1 step 6 + D4/D5) ─────────────────────────

def write_links(conn, group_id: str, properties, captured_by: str) -> dict:
    """Write manual_owner_links (and manual_properties stubs for ARNs not
    yet in properties). Returns dict with links_added, manual_created,
    scope_arns (ARNs eligible for the override pass under D4), warnings.

    D4: registry_confirmed links are always eligible to fill dark
    properties. web_asserted links are eligible only at confidence >=
    0.90; below that the link is inserted with status='pending' and its
    ARN is excluded from the override scope, surfacing for review.
    """
    links_added, manual_created = 0, 0
    scope_arns, warnings = [], []
    seen_scope = set()

    for p in properties or []:
        raw_arn = p.get("arn") or ""
        arn = normalize_arn(raw_arn)
        if not arn:
            warnings.append(f"ARN {raw_arn!r} is not a valid ARN — skipped")
            continue

        exists = conn.execute(
            "SELECT id FROM properties WHERE arn = ?", (arn,)
        ).fetchone()
        if not exists:
            cur = conn.execute(
                "INSERT OR IGNORE INTO manual_properties (arn, "
                "display_address, city, source, source_url, confidence, "
                "captured_by) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (arn, p.get("display_address"), p.get("city"),
                 p.get("source") or "web_capture", p.get("source_url"),
                 p.get("confidence"), captured_by),
            )
            manual_created += cur.rowcount
            warnings.append(
                f"ARN {arn} not found in properties — "
                "manual_properties stub created, link stays pending until "
                "a real property row exists")

        registry = 1 if p.get("registry_confirmed") else 0
        confidence = p.get("confidence")
        relationship = p.get("relationship") or "owns"

        status = "active"
        eligible = True
        if not registry and (confidence is None or confidence < 0.90):
            status = "pending"
            eligible = False
            warnings.append(
                f"ARN {arn}: web_asserted link below confidence 0.90 — "
                "inserted status='pending' for review (D4)")

        cur = conn.execute(
            "INSERT OR IGNORE INTO manual_owner_links (arn, group_id, "
            "relationship, status, source, source_url, confidence, "
            "web_asserted, registry_confirmed, captured_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (arn, group_id, relationship, status,
             p.get("source") or "web_capture", p.get("source_url"),
             confidence, 0 if registry else 1, registry, captured_by),
        )
        links_added += cur.rowcount

        if eligible and arn not in seen_scope:
            seen_scope.add(arn)
            scope_arns.append(arn)

    return {"links_added": links_added, "manual_created": manual_created,
            "scope_arns": scope_arns, "warnings": warnings}


# ── Match-key sweep (M4, spec Section 9) ──────────────────────────────

def _known_identity_norms(conn, group_id: str, merge_candidates) -> set:
    """Normalized names that clearly mean 'this entity': the group's own
    normalized name + aliases + spv_name keys + merge candidates' names."""
    known = set()
    row = conn.execute(
        "SELECT display_name, normalized_name FROM groups WHERE id = ?",
        (group_id,),
    ).fetchone()
    if row:
        for v in (normalize_brand(row["display_name"]),
                  (row["normalized_name"] or "").lower() or None):
            if v:
                known.add(v)
    for r in conn.execute(
        "SELECT normalized FROM group_aliases WHERE group_id = ?", (group_id,)
    ):
        if r["normalized"]:
            known.add(r["normalized"])
    for r in conn.execute(
        "SELECT value FROM group_match_keys WHERE group_id = ? "
        "AND key_type = 'spv_name'", (group_id,)
    ):
        known.add(r["value"])
    for cand in merge_candidates or []:
        r = conn.execute(
            "SELECT display_name FROM groups WHERE id = ?", (cand,)
        ).fetchone()
        if r:
            v = normalize_brand(r["display_name"])
            if v:
                known.add(v)
    return known


def _dark_and_attachable(prop_row, group_id, merge_set) -> bool:
    """A candidate qualifies only if the property is dark (no Realtrack
    owner) or already owned by the parent / a group being merged in."""
    if prop_row is None:
        return False
    tx = prop_row["transaction_count"] or 0
    owner_gid = prop_row["current_owner_group_id"]
    if tx > 0:
        return False  # has a Realtrack-derived owner path — never sweep it
    return owner_gid in (None, "", group_id) or owner_gid in merge_set


def run_sweep(conn, group_id: str, merge_candidates, captured_by: str) -> dict:
    """Attach dark parcels that share a swept match key with the group.

    Returns {'matched_arns': [...], 'attached': int, 'ambiguous': [...]}.
    Only keys with sweepable=1 and key_type in (address, spv_name) drive
    attachment (spec D3 + 9.2). Ambiguous owners are surfaced, never
    attached.
    """
    merge_set = set(merge_candidates or [])
    known = _known_identity_norms(conn, group_id, merge_candidates)
    matched_arns, ambiguous = [], []
    attached = 0
    seen = set()

    keys = conn.execute(
        "SELECT key_type, value FROM group_match_keys WHERE group_id = ? "
        "AND sweepable = 1 AND key_type IN ('address', 'spv_name')",
        (group_id,),
    ).fetchall()

    # candidate ARN -> (owner_norm, registry_confirmed)
    candidates, ambiguous_set = {}, set()

    for key in keys:
        ktype, value = key["key_type"], key["value"]

        if ktype == "spv_name":
            # Most selective token drives the LIKE prefilter: longest token
            # that is not a common word (fallback: longest token).
            toks = value.split()
            distinctive = [t for t in toks if t not in COMMON_SINGLE_WORDS]
            token = max(distinctive or toks, key=len)
            like = f"%{token}%"
            # (a) dark properties whose registry owner name matches
            rows = conn.execute(
                "SELECT id, arn, current_owner_name, current_owner_group_id, "
                "transaction_count FROM properties "
                "WHERE current_owner_name LIKE ? COLLATE NOCASE "
                "AND (transaction_count IS NULL OR transaction_count = 0)",
                (like,),
            ).fetchall()
            for r in rows:
                if normalize_brand(r["current_owner_name"]) != value:
                    continue
                if not _dark_and_attachable(r, group_id, merge_set):
                    continue
                if r["arn"]:
                    candidates.setdefault(r["arn"], (value, 1))
            # (b) GW assessment owner names joined to their property row
            rows = conn.execute(
                "SELECT ga.arn AS garn, ga.owner_name, p.id AS pid, "
                "p.current_owner_group_id, p.transaction_count "
                "FROM gw_assessments ga "
                "JOIN properties p ON p.arn = ga.arn "
                "WHERE ga.owner_name LIKE ? COLLATE NOCASE",
                (like,),
            ).fetchall()
            for r in rows:
                if normalize_brand(r["owner_name"]) != value:
                    continue
                if not _dark_and_attachable(r, group_id, merge_set):
                    continue
                candidates.setdefault(r["garn"], (value, 1))

        else:  # address key: match GW owner mailing addresses
            parts = value.split()
            num = parts[0]
            name_tok = parts[1] if len(parts) > 1 else ""
            rows = conn.execute(
                "SELECT ga.arn AS garn, ga.owner_name, ga.owner_mailing, "
                "p.id AS pid, p.current_owner_group_id, p.transaction_count "
                "FROM gw_assessments ga "
                "JOIN properties p ON p.arn = ga.arn "
                "WHERE ga.owner_mailing LIKE ? COLLATE NOCASE "
                "AND ga.owner_mailing LIKE ? COLLATE NOCASE",
                (f"%{num}%", f"%{name_tok}%"),
            ).fetchall()
            addr_hits = []
            for r in rows:
                if compose_address_key(r["owner_mailing"]) != value:
                    continue
                if not _dark_and_attachable(r, group_id, merge_set):
                    continue
                addr_hits.append(r)
            owner_norms = {normalize_brand(r["owner_name"]) or "" for r in addr_hits}
            single_owner = len(owner_norms - {""}) <= 1
            for r in addr_hits:
                onorm = normalize_brand(r["owner_name"]) or ""
                if onorm in known or single_owner:
                    candidates.setdefault(r["garn"], (onorm, 1))
                else:
                    # address shared by owners that are not clearly the
                    # same entity — surface, never attach (spec 9.1)
                    ambiguous_set.add(r["garn"])

    for arn in sorted(ambiguous_set - set(candidates)):
        ambiguous.append(arn)

    for arn, (_norm, registry) in sorted(candidates.items()):
        if arn in seen:
            continue
        seen.add(arn)
        cur = conn.execute(
            "INSERT OR IGNORE INTO manual_owner_links (arn, group_id, "
            "relationship, status, source, confidence, web_asserted, "
            "registry_confirmed, captured_by) "
            "VALUES (?, ?, 'owns', 'active', ?, 0.95, 0, ?, ?)",
            (arn, group_id, SWEEP_SOURCE, registry, captured_by),
        )
        attached += cur.rowcount
        matched_arns.append(arn)

    return {"matched_arns": matched_arns, "attached": attached,
            "ambiguous": ambiguous}
