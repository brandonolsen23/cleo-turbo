"""
Groups API — Phase D cutover to unified auto_groups.

The user-facing "Group" concept is the auto_group (rolled up across all
constituent legacy SPVs via legacy_to_auto_group_map). Endpoints accept
AGRP_xxxxx ids natively and dispatch legacy GRP_xxxxx ids to the same
auto_group so old deep links don't 404.

Engagement is per-contact (contacts.status). The group detail page surfaces
"N of M contacts engaged" as a derived rollup, never as a stored field on
the group. Legacy promote/engage/search/create endpoints are retired.
"""

import json
import sqlite3
from collections import Counter
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel

from ...web.deps import get_db, get_current_user
from ...web.audit import log_action
from ._attribution import attribution_for

OptInt = Optional[int]
OptFloat = Optional[float]
OptStr = Optional[str]

router = APIRouter()


# ── ID resolution ────────────────────────────────────────────────────

def resolve_auto_group_id(db, group_id: str) -> str:
    """Accept AGRP_xxxxx or GRP_xxxxx; return the canonical AGRP_xxxxx.

    Legacy IDs are looked up via legacy_to_auto_group_map. If neither form
    resolves, raises HTTPException(404).
    """
    if group_id.startswith("AGRP_"):
        row = db.execute(
            "SELECT 1 FROM auto_groups WHERE auto_group_id = ?", (group_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Group not found")
        return group_id
    if group_id.startswith("GRP_"):
        row = db.execute(
            "SELECT auto_group_id FROM legacy_to_auto_group_map WHERE legacy_group_id = ?",
            (group_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Group not found")
        return row["auto_group_id"]
    raise HTTPException(status_code=404, detail="Group not found")


# ── Filters ──────────────────────────────────────────────────────────

@router.get("/filters")
def group_filters(db=Depends(get_db), user=Depends(get_current_user)):
    """Available filter values for the Groups page."""
    asset_classes = db.execute(
        "SELECT DISTINCT asset_class FROM properties "
        "WHERE asset_class IS NOT NULL ORDER BY asset_class"
    ).fetchall()
    # Regions: union of every auto_group_analytics.regions list
    regions_set: set[str] = set()
    for r in db.execute(
        "SELECT regions FROM auto_group_analytics WHERE regions IS NOT NULL"
    ):
        try:
            for region in json.loads(r["regions"]):
                if region:
                    regions_set.add(region)
        except (json.JSONDecodeError, TypeError):
            pass
    tiers = ["confirmed", "probable", "candidate", "standalone"]
    return {
        "asset_classes": [r[0] for r in asset_classes],
        # Type = the group's dominant (most-transacted) property type shown in
        # the "Type" column. Same vocabulary as asset_class, minus "unknown".
        "types": [r[0] for r in asset_classes],
        "regions": sorted(regions_set),
        "tiers": tiers,
    }


# ── Browse ───────────────────────────────────────────────────────────

@router.get("")
def browse_groups(
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    # Tier filter (replaces legacy 'status')
    tier: OptStr = Query(None),
    # Range filters against analytics
    min_properties: OptInt = Query(None),
    max_properties: OptInt = Query(None),
    min_transactions: OptInt = Query(None),
    max_transactions: OptInt = Query(None),
    min_portfolio_value: OptInt = Query(None),
    max_portfolio_value: OptInt = Query(None),
    min_velocity: OptFloat = Query(None),
    max_velocity: OptFloat = Query(None),
    min_net_acquisitions: OptInt = Query(None),
    max_net_acquisitions: OptInt = Query(None),
    # Dominant type — the group's top property type shown in the "Type" column
    dominant_type: OptStr = Query(None),
    # Asset class (uses transacted_type_mix — same lens as contacts page)
    asset_class: OptStr = Query(None),
    min_asset_class_count: OptInt = Query(None, ge=1),
    max_asset_class_count: OptInt = Query(None, ge=1),
    # Region (membership in analytics.regions list)
    region: OptStr = Query(None),
    # Min members (auto_group party-side count — handy for filtering out 1-SPV singletons)
    min_members: OptInt = Query(None),
    # Search
    q: OptStr = Query(None),
    # Sort
    sort: str = "n_members",
    order: str = "desc",
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Paginated browse of unified auto_groups."""
    # Always exclude anonymized bucket and merged groups
    conditions = [
        "ag.canonical_stem != '_anonymized_individuals'",
        "ag.tier != 'merged'",
    ]
    params: list = []

    if tier:
        conditions.append("ag.tier = ?")
        params.append(tier)
    if min_members is not None:
        conditions.append("ag.n_members >= ?")
        params.append(min_members)
    if q and q.strip():
        like_val = f"%{q.strip().lower()}%"
        conditions.append("(LOWER(ag.display_name) LIKE ? OR LOWER(ag.canonical_stem) LIKE ?)")
        params.extend([like_val, like_val])

    # Analytics range filters — use unified properties_total (resolved +
    # by-address) so developer and judicial-entity counts reflect reality.
    if min_properties is not None:
        conditions.append("COALESCE(aga.properties_total, aga.transacted_property_count, aga.property_count, 0) >= ?")
        params.append(min_properties)
    if max_properties is not None:
        conditions.append("COALESCE(aga.properties_total, aga.transacted_property_count, aga.property_count, 0) <= ?")
        params.append(max_properties)
    if min_transactions is not None:
        conditions.append("COALESCE(aga.total_buys, 0) + COALESCE(aga.total_sells, 0) >= ?")
        params.append(min_transactions)
    if max_transactions is not None:
        conditions.append("COALESCE(aga.total_buys, 0) + COALESCE(aga.total_sells, 0) <= ?")
        params.append(max_transactions)
    if min_portfolio_value is not None:
        conditions.append("aga.total_assessed_value >= ?")
        params.append(min_portfolio_value)
    if max_portfolio_value is not None:
        conditions.append("aga.total_assessed_value <= ?")
        params.append(max_portfolio_value)
    if min_velocity is not None:
        conditions.append("aga.txns_per_year >= ?")
        params.append(min_velocity)
    if max_velocity is not None:
        conditions.append("aga.txns_per_year <= ?")
        params.append(max_velocity)
    if min_net_acquisitions is not None:
        conditions.append("aga.net_acquisitions >= ?")
        params.append(min_net_acquisitions)
    if max_net_acquisitions is not None:
        conditions.append("aga.net_acquisitions <= ?")
        params.append(max_net_acquisitions)

    # Dominant type — match the group's top property type (the "Type" column
    # badge). This is the argmax of transacted_type_mix excluding "unknown".
    # ORDER BY value DESC, id ASC reproduces the Python stable-sort tiebreak so
    # the filter always agrees with the badge the row displays.
    if dominant_type:
        conditions.append(
            "(SELECT je.key FROM json_each(COALESCE(aga.transacted_type_mix, aga.property_type_mix)) je "
            "WHERE je.key != 'unknown' ORDER BY je.value DESC, je.id ASC LIMIT 1) = ?"
        )
        params.append(dominant_type)

    # Asset class — uses transacted_type_mix (full history) just like contacts.
    if asset_class:
        min_ac = min_asset_class_count or 1
        max_ac = max_asset_class_count if max_asset_class_count is not None else 1_000_000_000
        conditions.append(
            "CAST(COALESCE(json_extract(aga.transacted_type_mix, '$.' || ?), '0') AS INTEGER) "
            "BETWEEN ? AND ?"
        )
        params.extend([asset_class, min_ac, max_ac])

    # Region — substring search on the regions JSON list. Avoids json_each in a
    # large correlated subquery; the list is short (typically <30 regions).
    if region:
        conditions.append("aga.regions LIKE ?")
        params.append(f'%"{region}"%')

    where = " AND ".join(conditions)
    offset = (page - 1) * per_page

    # Sort whitelist
    sort_map = {
        "n_members":           "ag.n_members",
        "display_name":        "ag.display_name",
        "tier":                "ag.tier",
        "property_count":      "COALESCE(aga.properties_total, aga.transacted_property_count, aga.property_count)",
        "properties_owned":    "aga.properties_owned",
        "transaction_count":   "(COALESCE(aga.total_buys, 0) + COALESCE(aga.total_sells, 0))",
        "total_buys":          "aga.total_buys",
        "total_sells":         "aga.total_sells",
        "total_buy_value":     "aga.total_buy_value",
        "total_sell_value":    "aga.total_sell_value",
        "total_assessed_value": "aga.total_assessed_value",
        "avg_buy_price":       "aga.avg_buy_price",
        "net_acquisitions":    "aga.net_acquisitions",
        "txns_per_year":       "aga.txns_per_year",
        "buys_last_12m":       "aga.buys_last_12m",
        "sells_last_12m":      "aga.sells_last_12m",
        "buys_last_36m":       "aga.buys_last_36m",
        "sells_last_36m":      "aga.sells_last_36m",
        "last_transaction_date": "aga.last_transaction_date",
    }
    sort_col = sort_map.get(sort, "ag.n_members")
    if order not in ("asc", "desc"):
        order = "desc"

    total = db.execute(
        f"SELECT COUNT(*) FROM auto_groups ag "
        f"LEFT JOIN auto_group_analytics aga ON aga.auto_group_id = ag.auto_group_id "
        f"WHERE {where}",
        params,
    ).fetchone()[0]

    rows = db.execute(
        f"""
        SELECT ag.auto_group_id AS id,
               ag.display_name,
               ag.canonical_stem,
               ag.tier,
               ag.confidence,
               ag.n_members,
               ag.n_anchors,
               ag.primary_address,
               ag.primary_phone,
               ag.website,
               COALESCE(aga.properties_total, aga.transacted_property_count, aga.property_count) AS property_count,
               aga.properties_owned,
               aga.properties_total,
               aga.transacted_property_count,
               COALESCE(aga.total_buys, 0) + COALESCE(aga.total_sells, 0) AS transaction_count,
               aga.total_buys,
               aga.total_sells,
               aga.total_buy_value,
               aga.total_sell_value,
               aga.n_buys_priced,
               aga.n_sells_priced,
               aga.total_assessed_value,
               aga.avg_buy_price,
               aga.net_acquisitions,
               aga.txns_per_year,
               aga.buys_last_12m,
               aga.sells_last_12m,
               aga.buys_last_36m,
               aga.sells_last_36m,
               aga.first_transaction_date,
               aga.last_transaction_date,
               aga.region_count,
               COALESCE(aga.transacted_type_mix, aga.property_type_mix) AS property_type_mix,
               (SELECT COUNT(*) FROM contacts c WHERE c.current_auto_group_id = ag.auto_group_id) AS contact_count,
               (SELECT COUNT(*) FROM contacts c WHERE c.current_auto_group_id = ag.auto_group_id AND c.status = 'engaged') AS engaged_contact_count
        FROM auto_groups ag
        LEFT JOIN auto_group_analytics aga ON aga.auto_group_id = ag.auto_group_id
        WHERE {where}
        ORDER BY {sort_col} {order} NULLS LAST, ag.auto_group_id ASC
        LIMIT ? OFFSET ?
        """,
        params + [per_page, offset],
    ).fetchall()

    results = []
    for r in rows:
        d = dict(r)
        # Derive dominant/secondary type from the JSON mix (skip "unknown")
        dominant = None
        secondary = None
        mix_raw = d.pop("property_type_mix", None)
        if mix_raw:
            try:
                mix = json.loads(mix_raw) if isinstance(mix_raw, str) else mix_raw
                sorted_types = [
                    (k, v) for k, v in sorted(mix.items(), key=lambda x: x[1], reverse=True)
                    if k != "unknown"
                ]
                if sorted_types:
                    dominant = sorted_types[0][0]
                if len(sorted_types) >= 2:
                    secondary = sorted_types[1][0]
            except (json.JSONDecodeError, TypeError):
                pass
        d["dominant_type"] = dominant
        d["secondary_type"] = secondary
        results.append(d)

    return {
        "results": results,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    }


# ── Detail ───────────────────────────────────────────────────────────

@router.get("/{group_id}")
def group_detail(group_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    """Auto_group detail. Accepts AGRP_xxxxx or legacy GRP_xxxxx."""
    aid = resolve_auto_group_id(db, group_id)

    ag = db.execute(
        "SELECT auto_group_id, display_name, canonical_stem, tier, confidence, "
        "       n_members, n_anchors, primary_address, primary_address_source, "
        "       website, primary_phone "
        "FROM auto_groups WHERE auto_group_id = ?",
        (aid,),
    ).fetchone()
    if not ag:
        raise HTTPException(status_code=404, detail="Group not found")

    result = dict(ag)
    # Frontend-facing id alias for consistency with browse responses
    result["id"] = aid

    # Analytics
    aga = db.execute(
        "SELECT * FROM auto_group_analytics WHERE auto_group_id = ?", (aid,)
    ).fetchone()
    analytics: dict | None = None
    if aga:
        analytics = dict(aga)
        for field in ("property_type_mix", "transacted_type_mix", "regions"):
            if analytics.get(field):
                try:
                    analytics[field] = json.loads(analytics[field])
                except (json.JSONDecodeError, TypeError):
                    pass
    result["analytics"] = analytics

    # Constituent SPVs (legacy groups rolled up into this auto_group)
    spvs = db.execute(
        """
        SELECT g.id, g.display_name, g.normalized_name, g.property_count,
               g.transaction_count, m.coverage_pct, m.source
        FROM legacy_to_auto_group_map m
        JOIN groups g ON g.id = m.legacy_group_id
        WHERE m.auto_group_id = ?
        ORDER BY g.transaction_count DESC, g.display_name ASC
        """,
        (aid,),
    ).fetchall()
    result["constituent_legacy_groups"] = [dict(r) for r in spvs]

    # Story + facts (Ownership Intelligence M1, migration 038).
    # group_profile is keyed to legacy GRP ids; prefer the constituent
    # profile that carries a narrative, then the most recently updated.
    result["summary"] = None
    result["narrative_md"] = None
    result["profile_source_url"] = None
    try:
        prof = db.execute(
            """
            SELECT gp.summary, gp.narrative_md, gp.source_url
            FROM group_profile gp
            JOIN legacy_to_auto_group_map m ON m.legacy_group_id = gp.group_id
            WHERE m.auto_group_id = ?
            ORDER BY (gp.narrative_md IS NOT NULL) DESC, gp.updated_at DESC
            LIMIT 1
            """,
            (aid,),
        ).fetchone()
        if prof:
            result["summary"] = prof["summary"]
            result["narrative_md"] = prof["narrative_md"]
            result["profile_source_url"] = prof["source_url"]
    except sqlite3.OperationalError:
        pass  # DB predates migration 038

    # Committed group_facts (doctrine D8: provenance always displayed)
    facts = []
    try:
        for r in db.execute(
            "SELECT id, field, value, value_json, source, source_url, "
            "confidence, effective_from, effective_to, adjudication_id, "
            "created_at FROM group_facts WHERE auto_group_id = ? "
            "AND status = 'committed' ORDER BY field, id",
            (aid,),
        ):
            f = dict(r)
            if f.get("value_json"):
                try:
                    f["value_json"] = json.loads(f["value_json"])
                except (json.JSONDecodeError, TypeError):
                    pass
            facts.append(f)
    except sqlite3.OperationalError:
        pass  # DB predates migration 038
    result["facts"] = facts

    # Contact rollup (counts only here; full list via /api/groups/{id}/contacts)
    counts = db.execute(
        """
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN status = 'engaged' THEN 1 ELSE 0 END) AS engaged
        FROM contacts WHERE current_auto_group_id = ?
        """,
        (aid,),
    ).fetchone()
    result["total_contact_count"] = counts["total"] or 0
    result["engaged_contact_count"] = counts["engaged"] or 0

    # Portfolio building size — across currently-owned properties via the
    # constituent legacy groups
    totals_by_unit = [
        {"unit": r["unit"], "count": r["n_props"], "total": r["total"]}
        for r in db.execute(
            """
            SELECT p.building_size_unit AS unit,
                   COUNT(*) AS n_props,
                   SUM(p.building_size_value) AS total
            FROM properties p
            JOIN legacy_to_auto_group_map m ON m.legacy_group_id = p.current_owner_group_id
            WHERE m.auto_group_id = ? AND p.building_size_unit IS NOT NULL
            GROUP BY p.building_size_unit
            ORDER BY n_props DESC
            """,
            (aid,),
        )
    ]
    no_size_count = db.execute(
        """
        SELECT COUNT(*) AS n FROM properties p
        JOIN legacy_to_auto_group_map m ON m.legacy_group_id = p.current_owner_group_id
        WHERE m.auto_group_id = ? AND p.building_size_unit IS NULL
        """,
        (aid,),
    ).fetchone()["n"]
    total_properties = sum(t["count"] for t in totals_by_unit) + no_size_count
    result["portfolio_size"] = {
        "totals_by_unit": totals_by_unit,
        "no_size_count": no_size_count,
        "total_properties": total_properties,
    }
    sf_entry = next((t for t in totals_by_unit if t["unit"] == "sf"), None)
    result["portfolio_sf"] = {
        "total_sf": sf_entry["total"] if sf_entry else None,
        "properties_with_sf": sf_entry["count"] if sf_entry else 0,
        "total_properties": total_properties,
    }

    return result


# ── Properties (unified — resolved + unresolved) ─────────────────────

@router.get("/{group_id}/properties")
def group_properties(
    group_id: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    filter: str = Query("all", regex="^(all|owned|sold)$"),
    sort: str = "last_date",
    order: str = "desc",
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Unified Properties view for an auto_group.

    A Property = one unique address the group has ever transacted on:
      - resolved: keyed by transactions.property_id (links to /properties/{id})
      - unresolved: keyed by canonical_address = lower(display_address) + '|' +
        lower(city). No parcel page; displayed as-is.

    Per row:
      - display_address, city, asset_class (resolved only), last_date,
        last_price, last_side (this group's most recent side at this address)
      - is_owned: True iff last_side == 'buyer'
      - n_transactions: this group's count at this property
      - resolved: True if a parcel matched

    filter:
      - all (default): every property the group has touched
      - owned: only is_owned=True (last side was buyer)
      - sold:  only is_owned=False (last side was seller)
    """
    aid = resolve_auto_group_id(db, group_id)

    # Pull every party-side → transaction join in one query, aggregate per
    # property identity in Python. ~1k-10k rows per group is small enough
    # that a sort + page in Python is cheap.
    rows = db.execute(
        """
        SELECT t.source_id           AS source_id,
               agm.side               AS side,
               t.property_id          AS property_id,
               t.display_address      AS display_address,
               t.city                 AS city,
               t.sale_date            AS sale_date,
               t.sale_price           AS sale_price,
               p.asset_class          AS asset_class,
               p.lat                  AS lat,
               p.lng                  AS lng,
               p.building_size_raw    AS building_size_raw,
               p.building_size_value  AS building_size_value,
               p.building_size_unit   AS building_size_unit
        FROM auto_group_members agm
        JOIN transactions t ON t.source_id = agm.source_id
        LEFT JOIN properties p ON p.id = t.property_id
        WHERE agm.auto_group_id = ? AND agm.member_type = 'party_side'
        """,
        (aid,),
    ).fetchall()

    # Aggregate per Property identity
    props: dict[str, dict] = {}
    for r in rows:
        property_id = r["property_id"]
        if property_id:
            key = property_id
            resolved = True
        else:
            addr = (r["display_address"] or "").strip().lower()
            city = (r["city"] or "").strip().lower()
            if not addr:
                continue   # orphan txn — no Property identity
            key = f"addr:{addr}|{city}"
            resolved = False

        entry = props.get(key)
        if entry is None:
            entry = {
                "property_id":         property_id,
                "canonical_address":   None if resolved else key,
                "resolved":            resolved,
                "display_address":     r["display_address"],
                "city":                r["city"],
                "asset_class":         r["asset_class"],
                "lat":                 r["lat"],
                "lng":                 r["lng"],
                "building_size_raw":   r["building_size_raw"],
                "building_size_value": r["building_size_value"],
                "building_size_unit":  r["building_size_unit"],
                "last_date":           r["sale_date"],
                "last_price":          r["sale_price"],
                "last_side":           r["side"],
                "n_transactions":      1,
            }
            props[key] = entry
        else:
            entry["n_transactions"] += 1
            sale_date = r["sale_date"] or ""
            if sale_date > (entry["last_date"] or ""):
                entry["last_date"]  = r["sale_date"]
                entry["last_price"] = r["sale_price"]
                entry["last_side"]  = r["side"]

    # Union in captured/current ownership (Portfolio Capture layer):
    # properties whose current_owner_group_id is a legacy group mapped to
    # this auto_group, plus off-book manual_properties linked via
    # manual_owner_links. These are owned holdings regardless of whether a
    # transaction for them exists in Realtrack.
    own_rows = db.execute(
        """
        SELECT p.id AS property_id, p.display_address, p.city,
               p.asset_class, p.lat, p.lng, p.building_size_raw,
               p.building_size_value, p.building_size_unit,
               p.most_recent_sale_date AS sale_date,
               p.most_recent_sale_price AS sale_price
        FROM properties p
        JOIN legacy_to_auto_group_map m
          ON m.legacy_group_id = p.current_owner_group_id
        WHERE m.auto_group_id = ?
        UNION ALL
        SELECT 'manual:' || mp.arn AS property_id, mp.display_address,
               mp.city, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
        FROM manual_properties mp
        JOIN manual_owner_links mol ON mol.arn = mp.arn
        JOIN legacy_to_auto_group_map m ON m.legacy_group_id = mol.group_id
        WHERE m.auto_group_id = ? AND mol.relationship = 'owns'
          AND COALESCE(mol.status, '') NOT IN ('conflict', 'rejected')
          AND mp.arn NOT IN (SELECT arn FROM properties)
        """,
        (aid, aid),
    ).fetchall()
    for r in own_rows:
        key = r["property_id"]
        entry = props.get(key)
        if entry is None:
            props[key] = {
                "property_id":         None if str(key).startswith("manual:") else key,
                "canonical_address":   None,
                "resolved":            not str(key).startswith("manual:"),
                "display_address":     r["display_address"],
                "city":                r["city"],
                "asset_class":         r["asset_class"],
                "lat":                 r["lat"],
                "lng":                 r["lng"],
                "building_size_raw":   r["building_size_raw"],
                "building_size_value": r["building_size_value"],
                "building_size_unit":  r["building_size_unit"],
                "last_date":           r["sale_date"],
                "last_price":          r["sale_price"],
                "last_side":           "owner",
                "n_transactions":      0,
            }
        else:
            entry["last_side"] = "owner"

    # Apply Owned/Sold filter on last_side
    items = list(props.values())
    for it in items:
        it["is_owned"] = it["last_side"] in ("buyer", "owner")

    if filter == "owned":
        items = [it for it in items if it["is_owned"]]
    elif filter == "sold":
        items = [it for it in items if not it["is_owned"]]

    # Sort
    sort_keys = {
        "last_date":      lambda x: x["last_date"] or "",
        "last_price":     lambda x: x["last_price"] or 0,
        "city":           lambda x: x["city"] or "",
        "asset_class":    lambda x: x["asset_class"] or "",
        "display_address": lambda x: x["display_address"] or "",
        "n_transactions": lambda x: x["n_transactions"],
    }
    key_fn = sort_keys.get(sort, sort_keys["last_date"])
    items.sort(key=key_fn, reverse=(order == "desc"))

    total = len(items)
    offset = (page - 1) * per_page
    page_items = items[offset:offset + per_page]

    return {
        "results": page_items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if total else 0,
        "filter": filter,
    }


# /properties-sold retired — Sold is now a filter on the unified endpoint.
# Kept here as a 410 stub so anyone with the old URL gets a clear message.
@router.get("/{group_id}/properties-sold")
def group_properties_sold_retired(group_id: str):
    raise HTTPException(
        status_code=410,
        detail=(
            "Endpoint retired. Use GET /api/groups/{group_id}/properties?filter=sold"
            " — the unified Properties endpoint now covers Owned + Sold via a"
            " filter parameter."
        ),
    )


# ── Contacts (with engagement) ───────────────────────────────────────

@router.get("/{group_id}/contacts")
def group_contacts(
    group_id: str,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Contacts whose current_auto_group_id matches, plus manually-linked
    contacts via group_contacts (CRM table). Each row includes the contact's
    engagement status so the UI can render pool/engaged badges and toggles."""
    aid = resolve_auto_group_id(db, group_id)

    derived = db.execute(
        """
        SELECT c.id, c.display_name, c.phone, c.email, c.job_title, c.status,
               c.transaction_count, c.contact_type, c.first_seen_date, c.last_seen_date
        FROM contacts c
        WHERE c.current_auto_group_id = ?
        ORDER BY c.transaction_count DESC, c.display_name ASC
        """,
        (aid,),
    ).fetchall()

    manual = db.execute(
        """
        SELECT gc.contact_id, gc.is_current, gc.role, gc.notes, gc.linked_at,
               c.display_name, c.phone, c.email, c.job_title, c.status,
               c.transaction_count, c.contact_type, c.first_seen_date, c.last_seen_date
        FROM group_contacts gc
        JOIN contacts c ON gc.contact_id = c.id
        WHERE gc.auto_group_id = ?
        ORDER BY gc.is_current DESC, gc.linked_at DESC
        """,
        (aid,),
    ).fetchall()

    derived_ids = {r["id"] for r in derived}
    manual_lookup = {m["contact_id"]: m for m in manual}

    results = []
    for c in derived:
        entry = dict(c)
        entry["link_type"] = "derived"
        entry["is_current"] = True
        entry["role"] = None
        entry["link_notes"] = None
        if c["id"] in manual_lookup:
            m = manual_lookup[c["id"]]
            entry["role"] = m["role"]
            entry["link_notes"] = m["notes"]
            entry["is_current"] = bool(m["is_current"])
            entry["link_type"] = "both"
        results.append(entry)

    for m in manual:
        if m["contact_id"] not in derived_ids:
            results.append({
                "id": m["contact_id"],
                "display_name": m["display_name"],
                "phone": m["phone"],
                "email": m["email"],
                "job_title": m["job_title"],
                "status": m["status"],
                "transaction_count": m["transaction_count"],
                "contact_type": m["contact_type"],
                "first_seen_date": m["first_seen_date"],
                "last_seen_date": m["last_seen_date"],
                "link_type": "manual",
                "is_current": bool(m["is_current"]),
                "role": m["role"],
                "link_notes": m["notes"],
            })

    return {"contacts": results, "total": len(results)}


# ── Manual contact-link CRUD ─────────────────────────────────────────

class LinkContactRequest(BaseModel):
    contact_id: str
    role: Optional[str] = None
    notes: Optional[str] = None
    is_current: bool = True


class UpdateLinkRequest(BaseModel):
    is_current: Optional[bool] = None
    role: Optional[str] = None
    notes: Optional[str] = None


@router.post("/{group_id}/contacts")
def link_contact(group_id: str, body: LinkContactRequest,
                 db=Depends(get_db), user=Depends(get_current_user)):
    aid = resolve_auto_group_id(db, group_id)
    if not db.execute("SELECT 1 FROM contacts WHERE id = ?", (body.contact_id,)).fetchone():
        raise HTTPException(status_code=404, detail="Contact not found")
    if db.execute(
        "SELECT 1 FROM group_contacts WHERE auto_group_id = ? AND contact_id = ?",
        (aid, body.contact_id),
    ).fetchone():
        raise HTTPException(status_code=409, detail="Contact already linked")
    db.execute(
        "INSERT INTO group_contacts (auto_group_id, contact_id, is_current, role, notes) "
        "VALUES (?, ?, ?, ?, ?)",
        (aid, body.contact_id, 1 if body.is_current else 0, body.role, body.notes),
    )
    log_action(db, user, "group.link_contact", "auto_group", aid,
               {"contact_id": body.contact_id, "role": body.role})
    db.commit()
    return {"status": "linked", "auto_group_id": aid, "contact_id": body.contact_id}


@router.patch("/{group_id}/contacts/{contact_id}")
def update_contact_link(group_id: str, contact_id: str, body: UpdateLinkRequest,
                        db=Depends(get_db), user=Depends(get_current_user)):
    aid = resolve_auto_group_id(db, group_id)
    if not db.execute(
        "SELECT 1 FROM group_contacts WHERE auto_group_id = ? AND contact_id = ?",
        (aid, contact_id),
    ).fetchone():
        raise HTTPException(status_code=404, detail="Link not found")

    updates: dict = {}
    if body.is_current is not None:
        updates["is_current"] = 1 if body.is_current else 0
    if body.role is not None:
        updates["role"] = body.role
    if body.notes is not None:
        updates["notes"] = body.notes
    if updates:
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        db.execute(
            f"UPDATE group_contacts SET {set_clause} "
            f"WHERE auto_group_id = ? AND contact_id = ?",
            list(updates.values()) + [aid, contact_id],
        )
        db.commit()
    return {"status": "updated", "updated": list(updates.keys())}


@router.delete("/{group_id}/contacts/{contact_id}")
def unlink_contact(group_id: str, contact_id: str,
                   db=Depends(get_db), user=Depends(get_current_user)):
    aid = resolve_auto_group_id(db, group_id)
    if not db.execute(
        "SELECT 1 FROM group_contacts WHERE auto_group_id = ? AND contact_id = ?",
        (aid, contact_id),
    ).fetchone():
        raise HTTPException(status_code=404, detail="Link not found")
    db.execute(
        "DELETE FROM group_contacts WHERE auto_group_id = ? AND contact_id = ?",
        (aid, contact_id),
    )
    log_action(db, user, "group.unlink_contact", "auto_group", aid,
               {"contact_id": contact_id})
    db.commit()
    return {"status": "unlinked"}


# ── HQ address (delegated to auto_group_user_edits) ──────────────────

class HQAddressRequest(BaseModel):
    address: str


@router.post("/{group_id}/hq-address")
def set_hq_address(group_id: str, body: HQAddressRequest,
                   db=Depends(get_db), user=Depends(get_current_user)):
    """Set the auto_group's primary_address. Persists across discovery_v2
    rebuilds via the apply_user_edits stage."""
    aid = resolve_auto_group_id(db, group_id)
    db.execute(
        "INSERT INTO auto_group_user_edits "
        "(edit_type, auto_group_id, new_primary_address, edited_by) "
        "VALUES ('set_address', ?, ?, ?)",
        (aid, body.address, user.get("username") or "unknown"),
    )
    db.execute(
        "UPDATE auto_groups SET primary_address = ?, primary_address_source = 'user' "
        "WHERE auto_group_id = ?",
        (body.address, aid),
    )
    log_action(db, user, "group.set_hq_address", "auto_group", aid, {"address": body.address})
    db.commit()
    return {"id": aid, "primary_address": body.address}


# ── Refresh analytics for one auto_group ─────────────────────────────

@router.post("/{group_id}/refresh-analytics")
def refresh_single_group(group_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    """Recompute auto_group_analytics for this one group. Used after manual
    edits (detach/attach) to reflect changes immediately."""
    from ...discovery_v2.group_analytics import build_auto_group_analytics
    aid = resolve_auto_group_id(db, group_id)
    # Run the full Stage A10 (cheap — ~5s on 100k auto_groups; single-group
    # incremental refresh is a future optimization).
    result = build_auto_group_analytics(db, verbose=False)
    return {"auto_group_id": aid, "refresh_summary": result}


# ── Attribution ──────────────────────────────────────────────────────

@router.get("/{group_id}/attribution")
def group_attribution(group_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    aid = resolve_auto_group_id(db, group_id)
    return attribution_for(db, "auto_group_id", aid)



# ── Evidence + verdicts (doctrine D4 front half) ─────────────────────
#
# Every auto-group must SHOW WHY its members were grouped (D4/D8), and the
# user records one-tap confirm/reject verdicts that accumulate as ground
# truth for the future algorithm scoreboard.
#
# Evidence is derived LIVE per group from the same interpretation tables the
# discovery_v2 algorithm reads (party_fingerprints, auto_group_anchors,
# party_atoms + brand_stem_phrase_map). The discovery_evidence table is NOT
# used: it is keyed to legacy GRP_ ids and was last written by the retired v1
# engine (last run 2026-04-18) — stale and wrong-keyed for auto_groups.
#
# Verdicts land in auto_group_verdicts (migration 037): append-only history,
# keyed to stable AGRP_ ids + member refs ("<source_id>:<side>" for
# party-sides, "corp:<name>" for numbered corps). Latest row per
# (scope, member_ref) wins on read.


def _format_canonical_address(canon: Optional[str]) -> Optional[str]:
    """Render 'city|number|name|suffix|direction|suite_type|suite_number'
    (party_address_canonical / address_unit anchor format) as a readable
    address. Falls back to the raw value if the shape is unexpected."""
    if not canon:
        return canon
    parts = canon.split("|")
    if len(parts) < 4:
        return canon
    city = parts[0]
    street_bits = [p for p in parts[1:5] if p]
    suite_no = parts[6] if len(parts) > 6 else ""
    out = " ".join(street_bits)
    if suite_no:
        out += f" suite {suite_no}"
    if city:
        out = f"{out}, {city}" if out else city
    return out or canon


def _member_ref(row) -> str:
    """Stable member identifier for verdicts.

    party_side    → "<source_id>:<side>"   e.g. "RT180025:buyer"
    numbered_corp → "corp:<corp_name>"     e.g. "corp:1865087 ontario"
    """
    if row["member_type"] == "numbered_corp":
        return f"corp:{row['corp_name']}"
    return f"{row['source_id']}:{row['side']}"


def _latest_verdicts(db, aid: str) -> tuple[Optional[dict], dict]:
    """(group_verdict, {member_ref: verdict_row}) — latest row per scope+ref
    wins; full history stays in the table. Tolerates a DB copy that predates
    migration 037 by returning empty."""
    try:
        rows = db.execute(
            "SELECT id, auto_group_id, scope, member_ref, verdict, reason, "
            "       actor, created_at "
            "FROM auto_group_verdicts WHERE auto_group_id = ? ORDER BY id",
            (aid,),
        ).fetchall()
    except sqlite3.OperationalError:
        return None, {}
    latest: dict = {}
    for r in rows:
        latest[(r["scope"], r["member_ref"])] = dict(r)
    group_verdict = latest.get(("group", None))
    member_verdicts = {ref: v for (scope, ref), v in latest.items()
                       if scope == "member" and ref}
    return group_verdict, member_verdicts


@router.get("/{group_id}/evidence")
def group_evidence(
    group_id: str,
    limit: int = Query(200, ge=1, le=1000),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Per-member evidence for WHY this auto_group's members were grouped.

    For each member, the concrete linking facts — shared normalized mailing
    address, shared phone, shared contact name, and SPV-name phrases matching
    the group's canonical stem — each tagged with its source (D8). Facts are
    only asserted when actually shared with another member or when they are a
    seeding anchor; a member with nothing shared gets an empty facts list and
    the UI says so honestly.
    """
    aid = resolve_auto_group_id(db, group_id)
    ag = db.execute(
        "SELECT auto_group_id, display_name, canonical_stem, tier, confidence "
        "FROM auto_groups WHERE auto_group_id = ?",
        (aid,),
    ).fetchone()
    if not ag:
        raise HTTPException(status_code=404, detail="Group not found")
    stem = ag["canonical_stem"]

    # Seeding anchors (precomputed by discovery_v2 Stage A3)
    anchors = {
        (r["anchor_type"], r["anchor_value"]): r["score"]
        for r in db.execute(
            "SELECT anchor_type, anchor_value, score "
            "FROM auto_group_anchors WHERE auto_group_id = ?",
            (aid,),
        )
    }

    total_members = db.execute(
        "SELECT COUNT(*) FROM auto_group_members WHERE auto_group_id = ?",
        (aid,),
    ).fetchone()[0]

    members = db.execute(
        "SELECT member_type, source_id, side, corp_name, match_score "
        "FROM auto_group_members WHERE auto_group_id = ? "
        "ORDER BY member_type ASC, match_score DESC, source_id ASC, corp_name ASC "
        "LIMIT ?",
        (aid, limit),
    ).fetchall()

    # Fingerprints for ALL party-side members (share counts must span the
    # whole group, not just the displayed page). Bounded by group size.
    full_fp = db.execute(
        """
        SELECT agm.source_id, agm.side,
               pf.party_address_canonical, pf.phone, pf.contact_fingerprint
        FROM auto_group_members agm
        LEFT JOIN party_fingerprints pf
          ON pf.source_id = agm.source_id AND pf.side = agm.side
        WHERE agm.auto_group_id = ? AND agm.member_type = 'party_side'
        """,
        (aid,),
    ).fetchall()
    fp_by_member = {(r["source_id"], r["side"]): r for r in full_fp}
    addr_counts = Counter(r["party_address_canonical"] for r in full_fp
                          if r["party_address_canonical"])
    phone_counts = Counter(r["phone"] for r in full_fp if r["phone"])
    contact_counts = Counter(r["contact_fingerprint"] for r in full_fp
                             if r["contact_fingerprint"])

    # Name-stem phrases: brand phrases on member party-sides that map to the
    # group's canonical stem (the n-gram evidence). One bounded query.
    stem_phrases: dict[tuple, list] = {}
    for r in db.execute(
        """
        SELECT pa.source_id, pa.side, pa.atom_value, pa.source_field
        FROM party_atoms pa
        JOIN brand_stem_phrase_map m
          ON m.phrase = pa.atom_value AND m.stem = ?
        JOIN auto_group_members agm
          ON agm.auto_group_id = ? AND agm.member_type = 'party_side'
         AND agm.source_id = pa.source_id AND agm.side = pa.side
        WHERE pa.atom_type = 'brand_phrase'
        """,
        (stem, aid),
    ):
        stem_phrases.setdefault((r["source_id"], r["side"]), []).append(
            {"phrase": r["atom_value"], "source_field": r["source_field"]}
        )
    n_stem_members = len(stem_phrases)

    # Display context for the page's party-side members: party name, txn
    # date/address, mailing display. Batched IN-list queries.
    page_party = [(r["source_id"], r["side"]) for r in members
                  if r["member_type"] == "party_side"]
    page_sids = sorted({s for s, _ in page_party})
    names: dict[tuple, str] = {}
    txinfo: dict[str, dict] = {}
    mailing: dict[tuple, str] = {}
    if page_sids:
        ph = ",".join("?" for _ in page_sids)
        for r in db.execute(
            f"SELECT source_id, side, party_name FROM transaction_parties "
            f"WHERE source_id IN ({ph}) ORDER BY id",
            page_sids,
        ):
            key = (r["source_id"], r["side"])
            if key not in names and (r["party_name"] or "").strip():
                names[key] = r["party_name"].strip()
        for r in db.execute(
            f"SELECT source_id, sale_date, display_address, city "
            f"FROM transactions WHERE source_id IN ({ph})",
            page_sids,
        ):
            txinfo[r["source_id"]] = dict(r)
        for r in db.execute(
            f"SELECT source_id, side, display, city "
            f"FROM transaction_mailing_addresses WHERE source_id IN ({ph})",
            page_sids,
        ):
            key = (r["source_id"], r["side"])
            if key not in mailing and r["display"]:
                disp = r["display"]
                if r["city"] and r["city"].lower() not in disp.lower():
                    disp = f"{disp}, {r['city']}"
                mailing[key] = disp

    # Numbered corps: on how many member party-sides did this corp name
    # appear as a brand phrase? (That appearance is WHY it's a member.)
    corp_names = [r["corp_name"] for r in members
                  if r["member_type"] == "numbered_corp" and r["corp_name"]]
    corp_counts: dict[str, int] = {}
    if corp_names:
        ph = ",".join("?" for _ in corp_names)
        for r in db.execute(
            f"""
            SELECT pa.atom_value, COUNT(DISTINCT pa.source_id || '|' || pa.side) AS n
            FROM party_atoms pa
            JOIN auto_group_members agm
              ON agm.auto_group_id = ? AND agm.member_type = 'party_side'
             AND agm.source_id = pa.source_id AND agm.side = pa.side
            WHERE pa.atom_type = 'brand_phrase' AND pa.atom_value IN ({ph})
            GROUP BY pa.atom_value
            """,
            [aid] + corp_names,
        ):
            corp_counts[r["atom_value"]] = r["n"]

    group_verdict, member_verdicts = _latest_verdicts(db, aid)

    out_members = []
    for m in members:
        ref = _member_ref(m)
        facts: list[dict] = []

        if m["member_type"] == "party_side":
            key = (m["source_id"], m["side"])
            fp = fp_by_member.get(key)

            if fp is not None:
                canon = fp["party_address_canonical"]
                if canon:
                    n_other = addr_counts[canon] - 1
                    is_anchor = ("address_unit", canon) in anchors
                    if n_other >= 1 or is_anchor:
                        facts.append({
                            "kind": "shared_address",
                            "value": _format_canonical_address(canon),
                            "raw_value": canon,
                            "detail": (
                                f"shares mailing address with {n_other} other "
                                f"member{'s' if n_other != 1 else ''}"
                                if n_other >= 1 else
                                "seeding anchor address (unique among shown members)"
                            ),
                            "shared_with": n_other,
                            "source": "RT party mailing address",
                            "is_anchor": is_anchor,
                            "anchor_score": anchors.get(("address_unit", canon)),
                        })
                phone = fp["phone"]
                if phone:
                    n_other = phone_counts[phone] - 1
                    is_anchor = ("phone", phone) in anchors
                    if n_other >= 1 or is_anchor:
                        facts.append({
                            "kind": "shared_phone",
                            "value": phone,
                            "raw_value": phone,
                            "detail": (
                                f"shares phone with {n_other} other "
                                f"member{'s' if n_other != 1 else ''}"
                                if n_other >= 1 else
                                "seeding anchor phone (unique among shown members)"
                            ),
                            "shared_with": n_other,
                            "source": "RT party block",
                            "is_anchor": is_anchor,
                            "anchor_score": anchors.get(("phone", phone)),
                        })
                contact = fp["contact_fingerprint"]
                if contact:
                    n_other = contact_counts[contact] - 1
                    is_anchor = ("contact", contact) in anchors
                    if n_other >= 1 or is_anchor:
                        facts.append({
                            "kind": "shared_contact",
                            "value": contact,
                            "raw_value": contact,
                            "detail": (
                                f"shares contact name with {n_other} other "
                                f"member{'s' if n_other != 1 else ''}"
                                if n_other >= 1 else
                                "seeding anchor contact (unique among shown members)"
                            ),
                            "shared_with": n_other,
                            "source": "RT contact block",
                            "is_anchor": is_anchor,
                            "anchor_score": anchors.get(("contact", contact)),
                        })

            for sp in stem_phrases.get(key, []):
                facts.append({
                    "kind": "name_stem",
                    "value": sp["phrase"],
                    "raw_value": sp["phrase"],
                    "detail": (
                        f"name phrase matches group stem '{stem}' "
                        f"(seen on {n_stem_members} member"
                        f"{'s' if n_stem_members != 1 else ''})"
                    ),
                    "shared_with": max(0, n_stem_members - 1),
                    "source": f"RT {sp['source_field']}",
                    "is_anchor": False,
                    "anchor_score": None,
                })

            tx = txinfo.get(m["source_id"], {})
            out_members.append({
                "member_type": "party_side",
                "member_ref": ref,
                "source_id": m["source_id"],
                "side": m["side"],
                "corp_name": None,
                "match_score": m["match_score"],
                "display_name": names.get(key),
                "mailing_display": mailing.get(key),
                "sale_date": tx.get("sale_date"),
                "transaction_address": tx.get("display_address"),
                "transaction_city": tx.get("city"),
                "facts": facts,
                "verdict": member_verdicts.get(ref),
            })
        else:
            n_sides = corp_counts.get(m["corp_name"], 0)
            if n_sides >= 1:
                facts.append({
                    "kind": "numbered_corp_name",
                    "value": m["corp_name"],
                    "raw_value": m["corp_name"],
                    "detail": (
                        f"numbered company name appeared on {n_sides} member "
                        f"party-side{'s' if n_sides != 1 else ''}"
                    ),
                    "shared_with": n_sides,
                    "source": "RT party name",
                    "is_anchor": False,
                    "anchor_score": None,
                })
            out_members.append({
                "member_type": "numbered_corp",
                "member_ref": ref,
                "source_id": None,
                "side": None,
                "corp_name": m["corp_name"],
                "match_score": m["match_score"],
                "display_name": m["corp_name"],
                "mailing_display": None,
                "sale_date": None,
                "transaction_address": None,
                "transaction_city": None,
                "facts": facts,
                "verdict": member_verdicts.get(ref),
            })

    return {
        "auto_group_id": aid,
        "display_name": ag["display_name"],
        "canonical_stem": stem,
        "tier": ag["tier"],
        "confidence": ag["confidence"],
        "total_members": total_members,
        "shown_members": len(out_members),
        "anchors": [
            {
                "anchor_type": t,
                "anchor_value": v,
                "display_value": _format_canonical_address(v) if t == "address_unit" else v,
                "score": s,
            }
            for (t, v), s in sorted(anchors.items())
        ],
        "members": out_members,
        "group_verdict": group_verdict,
    }


class GroupVerdictRequest(BaseModel):
    scope: str                       # 'group' | 'member'
    member_ref: Optional[str] = None # required when scope == 'member'
    verdict: str                     # 'confirm' | 'reject'
    reason: Optional[str] = None


@router.post("/{group_id}/verdict")
def record_group_verdict(group_id: str, body: GroupVerdictRequest,
                         db=Depends(get_db), user=Depends(get_current_user)):
    """Record a confirm/reject verdict on a grouping (D4 flywheel judgment).

    Append-only: every call writes a new history row; reads take the latest
    row per (scope, member_ref). Verdicts are keyed to stable IDs
    (AGRP_ id + RT source_id/side or corp name) so they survive rebuilds and
    feed the future algorithm scoreboard.
    """
    aid = resolve_auto_group_id(db, group_id)

    if body.scope not in ("group", "member"):
        raise HTTPException(status_code=400, detail="scope must be 'group' or 'member'")
    if body.verdict not in ("confirm", "reject"):
        raise HTTPException(status_code=400, detail="verdict must be 'confirm' or 'reject'")

    member_ref: Optional[str] = None
    if body.scope == "member":
        member_ref = (body.member_ref or "").strip()
        if not member_ref:
            raise HTTPException(status_code=400,
                                detail="member_ref is required for member-scope verdicts")
        # Validate the ref points at an actual member of this group
        if member_ref.startswith("corp:"):
            row = db.execute(
                "SELECT 1 FROM auto_group_members WHERE auto_group_id = ? "
                "AND member_type = 'numbered_corp' AND corp_name = ?",
                (aid, member_ref[5:]),
            ).fetchone()
        else:
            sid, _, side = member_ref.rpartition(":")
            row = db.execute(
                "SELECT 1 FROM auto_group_members WHERE auto_group_id = ? "
                "AND member_type = 'party_side' AND source_id = ? AND side = ?",
                (aid, sid, side),
            ).fetchone() if sid else None
        if not row:
            raise HTTPException(status_code=404,
                                detail=f"Member {member_ref} not found in {aid}")

    actor = user.get("username") or "unknown"
    cur = db.execute(
        "INSERT INTO auto_group_verdicts "
        "(auto_group_id, scope, member_ref, verdict, reason, actor) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (aid, body.scope, member_ref, body.verdict,
         (body.reason or "").strip() or None, actor),
    )
    verdict_id = cur.lastrowid
    log_action(db, user, "group.verdict", "auto_group", aid,
               {"scope": body.scope, "member_ref": member_ref,
                "verdict": body.verdict, "reason": body.reason})
    db.commit()

    row = db.execute(
        "SELECT id, auto_group_id, scope, member_ref, verdict, reason, actor, created_at "
        "FROM auto_group_verdicts WHERE id = ?",
        (verdict_id,),
    ).fetchone()
    return dict(row)


@router.get("/{group_id}/verdicts")
def list_group_verdicts(group_id: str,
                        db=Depends(get_db), user=Depends(get_current_user)):
    """Full verdict history for this auto_group (latest first)."""
    aid = resolve_auto_group_id(db, group_id)
    try:
        rows = db.execute(
            "SELECT id, auto_group_id, scope, member_ref, verdict, reason, "
            "       actor, created_at "
            "FROM auto_group_verdicts WHERE auto_group_id = ? ORDER BY id DESC",
            (aid,),
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []
    return {"verdicts": [dict(r) for r in rows], "total": len(rows)}
