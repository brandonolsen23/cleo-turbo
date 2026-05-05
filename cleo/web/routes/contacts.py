"""
Contacts API — browse, search, detail, promote.
"""

import json
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from ...web.deps import get_db, get_current_user, fts_query
from ...web.audit import log_action

# Type alias for optional query params — more explicit than bare `int = None`
OptInt = Optional[int]
OptStr = Optional[str]

router = APIRouter()


@router.get("/filters")
def contact_filters(db=Depends(get_db), user=Depends(get_current_user)):
    """Available filter values for the Contacts page."""
    contact_types = db.execute(
        "SELECT DISTINCT contact_type FROM contacts WHERE contact_type IS NOT NULL ORDER BY contact_type"
    ).fetchall()
    regions = db.execute(
        "SELECT DISTINCT t.region FROM transaction_parties tp "
        "JOIN transactions t ON tp.source_id = t.source_id "
        "WHERE t.region != '' GROUP BY t.region ORDER BY t.region"
    ).fetchall()
    return {
        "contact_types": [r[0] for r in contact_types],
        "regions": [r[0] for r in regions],
    }


@router.get("")
def browse_contacts(
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    status: OptStr = Query(None),
    contact_type: OptStr = Query(None),
    min_transactions: OptInt = Query(None),
    max_transactions: OptInt = Query(None),
    min_buy_value: OptInt = Query(None),
    max_buy_value: OptInt = Query(None),
    region: OptStr = Query(None),
    asset_class: OptStr = Query(None),
    min_asset_class_count: OptInt = Query(None, ge=1),
    max_asset_class_count: OptInt = Query(None, ge=1),
    q: OptStr = Query(None),
    sort: str = "last_seen_date",
    order: str = "desc",
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    conditions = []
    params = []
    if status:
        conditions.append("c.status = ?")
        params.append(status)
    if contact_type:
        conditions.append("c.contact_type = ?")
        params.append(contact_type)
    if min_transactions is not None:
        conditions.append("c.transaction_count >= ?")
        params.append(min_transactions)
    if max_transactions is not None:
        conditions.append("c.transaction_count <= ?")
        params.append(max_transactions)
    if q and q.strip():
        conditions.append(
            "(c.display_name LIKE ? OR c.company_name LIKE ? OR c.phone LIKE ?)"
        )
        like_val = f"%{q.strip()}%"
        params.extend([like_val, like_val, like_val])
    if region:
        conditions.append(
            "c.id IN (SELECT tp.contact_id FROM transaction_parties tp "
            "JOIN transactions t ON tp.source_id = t.source_id "
            "WHERE t.region = ? AND tp.contact_id IS NOT NULL)"
        )
        params.append(region)
    # Buy value filters use a subquery on the same aggregation we SELECT
    buy_value_subquery = (
        "(SELECT SUM(t.sale_price) FROM transaction_parties tp "
        "JOIN transactions t ON t.source_id = tp.source_id "
        "WHERE tp.contact_id = c.id AND tp.side = 'buyer' AND t.sale_price IS NOT NULL)"
    )
    if min_buy_value is not None:
        conditions.append(f"{buy_value_subquery} >= ?")
        params.append(min_buy_value)
    if max_buy_value is not None:
        conditions.append(f"{buy_value_subquery} <= ?")
        params.append(max_buy_value)
    if asset_class:
        min_ac = min_asset_class_count or 1
        having = "HAVING COUNT(*) >= ?"
        ac_params = [asset_class, min_ac]
        if max_asset_class_count is not None:
            having += " AND COUNT(*) <= ?"
            ac_params.append(max_asset_class_count)
        # Filter contacts whose current group owns N..M properties of this class
        conditions.append(
            f"c.current_group_id IN (SELECT current_owner_group_id FROM properties "
            f"WHERE asset_class = ? AND current_owner_group_id IS NOT NULL "
            f"GROUP BY current_owner_group_id {having})"
        )
        params.extend(ac_params)

    where = " AND ".join(conditions) if conditions else "1=1"
    offset = (page - 1) * per_page

    total = db.execute(f"SELECT COUNT(*) FROM contacts c WHERE {where}", params).fetchone()[0]

    allowed_sorts = {"last_seen_date", "display_name", "transaction_count", "first_seen_date", "total_buy_value"}
    if sort not in allowed_sorts:
        sort = "last_seen_date"
    if order not in ("asc", "desc"):
        order = "desc"

    # total_buy_value is a computed column, so ORDER BY uses the alias
    order_clause = f"total_buy_value {order}" if sort == "total_buy_value" else f"c.{sort} {order}"
    # When sorting by buy value, put NULLs last
    if sort == "total_buy_value":
        order_clause = f"total_buy_value IS NULL, {order_clause}"

    rows = db.execute(
        f"SELECT c.id, c.display_name, c.phone, c.email, c.mobile, c.company_name, c.status, "
        f"c.contact_type, c.transaction_count, c.first_seen_date, c.last_seen_date, c.job_title, "
        f"{buy_value_subquery} as total_buy_value, "
        f"(SELECT tma.city FROM transaction_parties tp "
        f"JOIN transaction_mailing_addresses tma ON tma.source_id = tp.source_id AND tma.side = tp.side "
        f"WHERE tp.contact_id = c.id AND tma.city IS NOT NULL AND tma.city != '' "
        f"ORDER BY tp.source_id DESC LIMIT 1) as mailing_city, "
        f"ga.property_type_mix "
        f"FROM contacts c "
        f"LEFT JOIN group_analytics ga ON c.current_group_id = ga.group_id "
        f"WHERE {where} ORDER BY {order_clause} LIMIT ? OFFSET ?",
        params + [per_page, offset]
    ).fetchall()

    # Derive dominant/secondary property types from group's property_type_mix
    results = []
    for r in rows:
        d = dict(r)
        dominant = None
        secondary = None
        mix_raw = d.pop("property_type_mix", None)
        if mix_raw:
            try:
                mix = json.loads(mix_raw) if isinstance(mix_raw, str) else mix_raw
                # Filter out "unknown" — not a meaningful property type
                sorted_types = [
                    (k, v) for k, v in sorted(mix.items(), key=lambda x: x[1], reverse=True)
                    if k != "unknown"
                ]
                if len(sorted_types) >= 1:
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


@router.get("/search")
def search_contacts(
    q: str = Query(..., min_length=1),
    limit: int = Query(25, ge=1, le=100),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    like_val = f"%{q.strip()}%"
    rows = db.execute(
        "SELECT c.id, c.display_name, c.phone, c.company_name, c.status, c.transaction_count "
        "FROM contacts c "
        "WHERE c.display_name LIKE ? OR c.company_name LIKE ? OR c.phone LIKE ? "
        "LIMIT ?",
        (like_val, like_val, like_val, limit)
    ).fetchall()
    return {"results": [dict(r) for r in rows], "total": len(rows)}


@router.get("/{contact_id}")
def contact_detail(contact_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    row = db.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Contact not found")

    result = dict(row)

    # Apply field overrides (user-edited + LinkedIn enrichment + Datanyze)
    overrides = db.execute(
        "SELECT email, phone, mobile, job_title, contact_type, "
        "linkedin_url, linkedin_headline, linkedin_photo_url, linkedin_enriched_at, datanyze_raw "
        "FROM contact_field_overrides WHERE contact_id = ?",
        (contact_id,)
    ).fetchone()
    if overrides:
        ov = dict(overrides)
        # Override job_title and contact_type if the override has a value
        for field in ("job_title", "contact_type"):
            if ov.get(field):
                result[field] = ov[field]
        # For email/phone/mobile: DON'T override RT values — keep both
        # RT values stay in result["phone"], result["email"], result["mobile"]
        # LinkedIn-specific fields (always from overrides)
        result["linkedin_url"] = ov.get("linkedin_url")
        result["linkedin_headline"] = ov.get("linkedin_headline")
        result["linkedin_photo_url"] = ov.get("linkedin_photo_url")
        result["linkedin_enriched_at"] = ov.get("linkedin_enriched_at")
        # Datanyze raw data — parse JSON so frontend can show alongside RT data
        raw = ov.get("datanyze_raw")
        result["datanyze_contacts"] = json.loads(raw) if raw else None
    else:
        result["linkedin_url"] = None
        result["linkedin_headline"] = None
        result["linkedin_photo_url"] = None
        result["linkedin_enriched_at"] = None
        result["datanyze_contacts"] = None

    # Work history
    positions = db.execute(
        "SELECT id, company, title, start_date, end_date, is_current, location, company_logo_url "
        "FROM contact_work_history WHERE contact_id = ? "
        "ORDER BY is_current DESC, start_date DESC",
        (contact_id,)
    ).fetchall()
    result["work_history"] = [dict(p) for p in positions]

    # Transactions this contact appears on (with tenant brands via property)
    txns = db.execute(
        "SELECT tp.source_id, tp.side, tp.party_name, tp.contact_title, tp.phone, "
        "t.sale_date, t.sale_price, t.display_address, t.city, "
        "(SELECT GROUP_CONCAT(p2.brand || '|' || p2.category, ';;') "
        " FROM pois p2 WHERE p2.property_id = t.property_id AND p2.brand != '') as brands_raw "
        "FROM transaction_parties tp "
        "JOIN transactions t ON tp.source_id = t.source_id "
        "WHERE tp.contact_id = ? ORDER BY t.sale_date DESC",
        (contact_id,)
    ).fetchall()
    txn_list = []
    for t in txns:
        td = dict(t)
        raw = td.pop("brands_raw", None)
        if raw:
            td["brands"] = [{"brand": b.split("|")[0], "category": b.split("|")[1] if "|" in b else ""}
                            for b in raw.split(";;") if b]
        else:
            td["brands"] = []
        txn_list.append(td)
    result["transactions"] = txn_list

    # Group associations
    if result.get("current_group_id"):
        group = db.execute(
            "SELECT id, display_name, status, hq_address FROM groups WHERE id = ?",
            (result["current_group_id"],)
        ).fetchone()
        if group:
            gd = dict(group)
            # Fallback: buyer mailing address from contact's most recent transaction
            if not gd.get("hq_address") and result.get("transactions"):
                latest_src = result["transactions"][0].get("source_id")
                if latest_src:
                    ma = db.execute(
                        "SELECT display, geocode_string FROM transaction_mailing_addresses "
                        "WHERE source_id = ? AND side = 'buyer'",
                        (latest_src,)
                    ).fetchone()
                    if ma:
                        gd["hq_address"] = ma["geocode_string"] or ma["display"]
            result["current_group"] = gd
        else:
            result["current_group"] = None

    # ── Career history (contact_brand_tenures) ─────────────────────────────
    fp = result.get("name_fingerprint")
    cbt_rows = []
    if fp:
        cbt_rows = db.execute(
            """
            SELECT cbt.brand_stem, cbt.strict_start_date, cbt.strict_end_date,
                   cbt.inferred_start_date, cbt.inferred_end_date,
                   cbt.n_party_sides_strict, cbt.n_party_sides_inferred,
                   cbt.top_phrases_json, cbt.source_field_breakdown_json,
                   cbt.dominant_address_unit, cbt.auto_group_id, cbt.is_active
            FROM contact_brand_tenures cbt
            WHERE cbt.contact_fingerprint = ?
            ORDER BY cbt.inferred_end_date DESC, cbt.brand_stem ASC
            """,
            (fp,),
        ).fetchall()

    career_history = []
    for r in cbt_rows:
        cd = dict(r)
        top_phrases = json.loads(cd["top_phrases_json"])
        cd["display_name"] = top_phrases[0]["phrase"] if top_phrases else cd["brand_stem"]
        cd["top_phrases"] = top_phrases
        cd["source_field_breakdown"] = json.loads(cd["source_field_breakdown_json"])
        # Strip the raw JSON columns from the response — clients use the parsed forms.
        cd.pop("top_phrases_json", None)
        cd.pop("source_field_breakdown_json", None)
        career_history.append(cd)

    # n_transactions_credited per tenure: count this contact's transactions
    # whose sale_date falls in the inferred window.
    if career_history and txn_list:
        for t in career_history:
            t["n_transactions_credited"] = sum(
                1 for x in txn_list
                if x.get("sale_date")
                and t["inferred_start_date"] <= x["sale_date"] <= t["inferred_end_date"]
            )
    result["career_history"] = career_history

    # ── current_employer derivation (LinkedIn > active realtrack) ──────────
    work_positions = result.get("work_history") or []
    linkedin_current = next(
        (p for p in work_positions if p.get("is_current")),
        None,
    )
    current_employer = None
    if linkedin_current:
        current_employer = {
            "source": "linkedin",
            "company": linkedin_current.get("company"),
            "title": linkedin_current.get("title"),
            "brand_stem": None,  # populated by reconcile step below
            "display_name": linkedin_current.get("company"),
        }
    active_tenures = [t for t in career_history if t.get("is_active") == 1]
    if active_tenures:
        active_tenures.sort(
            key=lambda t: (-t.get("n_party_sides_inferred", 0), t.get("brand_stem")),
        )
        top_active = active_tenures[0]
        if current_employer is None:
            current_employer = {
                "source": "realtrack",
                "company": top_active["display_name"],
                "title": None,
                "brand_stem": top_active["brand_stem"],
                "display_name": top_active["display_name"],
            }
        else:
            # LinkedIn already set; check if its company stem matches the top
            # realtrack tenure for divergence indicator. Stem comparison is
            # lowercase substring containment (LinkedIn names are messy).
            li_lower = (linkedin_current.get("company") or "").lower()
            if top_active["brand_stem"] in li_lower:
                current_employer["source"] = "linkedin_confirmed"
                current_employer["brand_stem"] = top_active["brand_stem"]
            else:
                current_employer["source"] = "linkedin_diverges"
                current_employer["realtrack_stem"] = top_active["brand_stem"]
                current_employer["realtrack_display_name"] = top_active["display_name"]
    result["current_employer"] = current_employer

    # ── Per-transaction tenure attribution (spec §2e) ──────────────────────
    # A transaction credits a tenure iff:
    #   sale_date in [inferred_start, inferred_end]
    #   AND (the side's brand_phrase carries the stem OR the side's address_unit
    #        equals the tenure's dominant_address_unit)
    if fp and txn_list:
        # Pre-fetch the brand_stems and address_units of the contact's party-sides.
        side_info = {}
        for r in db.execute(
            """
            SELECT pf.source_id, pf.side,
                   pf.city, COALESCE(pf.street_number,'') AS sn,
                   COALESCE(pf.street_name,'') AS st,
                   COALESCE(pf.street_suffix,'') AS sx,
                   COALESCE(pf.street_direction,'') AS sd,
                   COALESCE(pf.suite_type,'') AS suite_t,
                   COALESCE(pf.suite_number,'') AS suite_n
            FROM party_fingerprints pf
            WHERE pf.contact_fingerprint = ?
            """,
            (fp,),
        ).fetchall():
            addr_unit = "|".join([
                (r["city"] or "").lower(), r["sn"], (r["st"] or "").lower(),
                (r["sx"] or "").lower(), (r["sd"] or "").lower(),
                (r["suite_t"] or "").lower(), r["suite_n"],
            ])
            side_info[(r["source_id"], r["side"])] = {"addr_unit": addr_unit, "stems": set()}

        # Lookup the qualifying brand_phrase stems present on each side.
        # party_atoms and brand_stem_phrase_map may not exist in all environments —
        # silently skip if the tables are absent.
        try:
            for r in db.execute(
                """
                SELECT pa.source_id, pa.side, m.stem
                FROM party_atoms pa
                JOIN brand_stem_phrase_map m ON m.phrase = pa.atom_value
                JOIN party_fingerprints pf ON pf.source_id = pa.source_id AND pf.side = pa.side
                WHERE pa.atom_type = 'brand_phrase'
                  AND pa.source_field IN ('trade_name','care_of','companies_json')
                  AND pf.contact_fingerprint = ?
                """,
                (fp,),
            ).fetchall():
                key = (r["source_id"], r["side"])
                if key in side_info:
                    side_info[key]["stems"].add(r["stem"])
        except Exception:
            pass  # Tables not available in this environment

        for txn in txn_list:
            attribution = None
            sid = txn.get("source_id")
            sd = txn.get("side")
            sale_date = txn.get("sale_date")
            if sid and sd and sale_date:
                info = side_info.get((sid, sd), {"addr_unit": "", "stems": set()})
                for t in career_history:
                    if not (t["inferred_start_date"] <= sale_date <= t["inferred_end_date"]):
                        continue
                    explicit = t["brand_stem"] in info["stems"]
                    address_match = (
                        t.get("dominant_address_unit") is not None
                        and info["addr_unit"] == t["dominant_address_unit"]
                    )
                    if explicit or address_match:
                        attribution = {
                            "brand_stem": t["brand_stem"],
                            "display_name": t["display_name"],
                            "inferred": not explicit,
                        }
                        break  # career_history is sorted; take the most-recent-ending match
            txn["tenure"] = attribution
        result["transactions"] = txn_list

    # ── Phone / address tenure tags ────────────────────────────────────────
    today = db.execute("SELECT date('now') AS d").fetchone()["d"]
    cliff = db.execute("SELECT date('now','-730 days') AS d").fetchone()["d"]

    def _tag_for_phone(phone_value):
        if not phone_value or not fp or not career_history:
            return None
        seen = db.execute(
            "SELECT MIN(sale_date) AS first_seen, MAX(sale_date) AS last_seen "
            "FROM party_fingerprints WHERE contact_fingerprint = ? AND phone = ?",
            (fp, phone_value),
        ).fetchone()
        if not seen or not seen["last_seen"]:
            return None
        last_seen = seen["last_seen"]
        first_seen = seen["first_seen"]
        # Find tenures whose window overlaps [first_seen, last_seen].
        overlapping = [
            t for t in career_history
            if not (t["inferred_end_date"] < first_seen or t["inferred_start_date"] > last_seen)
        ]
        if not overlapping:
            return {"state": "stale", "last_seen": last_seen, "stem": None,
                    "display_name": None}
        # Active iff the phone overlaps an explicitly active tenure (is_active=1)
        # for the current employer, OR was seen recently (within the cliff window)
        # and overlaps the current employer's tenure.
        ce_stem = (current_employer or {}).get("brand_stem")
        active_overlap = [
            t for t in overlapping
            if t["brand_stem"] == ce_stem and t.get("is_active") == 1
        ]
        is_active = bool(active_overlap) and (
            active_overlap[0].get("is_active") == 1 or last_seen >= cliff
        )
        if is_active:
            ce = next(t for t in overlapping if t["brand_stem"] == ce_stem)
            return {
                "state": "active",
                "last_seen": last_seen,
                "stem": ce_stem,
                "display_name": ce["display_name"],
                "since": ce["inferred_start_date"],
            }
        # Stale — label with the dominant overlapping tenure (most party-sides).
        overlapping.sort(key=lambda t: -t.get("n_party_sides_inferred", 0))
        return {
            "state": "stale",
            "last_seen": last_seen,
            "stem": overlapping[0]["brand_stem"],
            "display_name": overlapping[0]["display_name"],
        }

    result["phone_tenure_tag"] = _tag_for_phone(result.get("phone"))

    # Address tenure tag: the contact's "primary mailing address" doesn't live
    # on the contacts row. We surface a tag for each unique address that
    # appears on this contact's party-sides, sorted most-recent first. The UI
    # decides which one to show under the (single) Address row.
    address_tags = []
    if fp:
        addr_rows = db.execute(
            """
            SELECT city,
                   COALESCE(street_number,'') AS sn,
                   COALESCE(street_name,'') AS st,
                   COALESCE(street_suffix,'') AS sx,
                   COALESCE(street_direction,'') AS sd,
                   COALESCE(suite_type,'') AS suite_t,
                   COALESCE(suite_number,'') AS suite_n,
                   MIN(sale_date) AS first_seen, MAX(sale_date) AS last_seen
            FROM party_fingerprints
            WHERE contact_fingerprint = ?
              AND street_number IS NOT NULL AND street_number != ''
            GROUP BY 1,2,3,4,5,6,7
            ORDER BY MAX(sale_date) DESC
            """,
            (fp,),
        ).fetchall()
        for ar in addr_rows:
            addr_unit = "|".join([
                (ar["city"] or "").lower(), ar["sn"], (ar["st"] or "").lower(),
                (ar["sx"] or "").lower(), (ar["sd"] or "").lower(),
                (ar["suite_t"] or "").lower(), ar["suite_n"],
            ])
            # Match against tenure dominant_address_unit.
            matching = [t for t in career_history if t.get("dominant_address_unit") == addr_unit]
            tag = None
            if matching:
                t = matching[0]
                if t.get("is_active") == 1 and ar["last_seen"] >= cliff:
                    tag = {"state": "active", "stem": t["brand_stem"],
                           "display_name": t["display_name"],
                           "since": t["inferred_start_date"]}
                else:
                    tag = {"state": "stale", "stem": t["brand_stem"],
                           "display_name": t["display_name"],
                           "last_seen": ar["last_seen"]}
            address_tags.append({
                "address_unit": addr_unit,
                "first_seen": ar["first_seen"],
                "last_seen": ar["last_seen"],
                "tag": tag,
            })
    result["address_tenure_tags"] = address_tags

    return result


@router.get("/{contact_id}/properties")
def contact_property_history(contact_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    """Properties currently owned by the contact's groups, with lat/lng for mapping."""
    row = db.execute("SELECT id, current_group_id FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Contact not found")

    # Collect all group IDs this contact belongs to
    group_ids = set()
    if row["current_group_id"]:
        group_ids.add(row["current_group_id"])
    extra = db.execute(
        "SELECT group_id FROM group_contacts WHERE contact_id = ? AND is_current = 1",
        (contact_id,)
    ).fetchall()
    for r in extra:
        group_ids.add(r["group_id"])

    if not group_ids:
        return {"properties": []}

    placeholders = ",".join("?" * len(group_ids))
    rows = db.execute(
        "SELECT DISTINCT p.id, p.display_address, p.city, p.lat, p.lng, p.asset_class, "
        "p.most_recent_sale_price, p.current_owner_name, p.current_owner_group_id "
        "FROM properties p "
        f"WHERE p.current_owner_group_id IN ({placeholders}) "
        "AND p.lat IS NOT NULL AND p.lng IS NOT NULL",
        tuple(group_ids)
    ).fetchall()
    return {"properties": [dict(r) for r in rows]}


@router.post("/{contact_id}/promote")
def promote_contact(contact_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    row = db.execute("SELECT status FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Contact not found")
    db.execute("UPDATE contacts SET status = 'engaged', updated_at = datetime('now') WHERE id = ?", (contact_id,))
    # Persist status override so it survives recompiles
    db.execute(
        "INSERT INTO contact_field_overrides (contact_id, status, updated_by) VALUES (?, 'engaged', ?) "
        "ON CONFLICT(contact_id) DO UPDATE SET status = 'engaged', updated_by = ?, updated_at = datetime('now')",
        (contact_id, user["username"], user["username"])
    )
    log_action(db, user, "contact.promote", "contact", contact_id, {"from_status": row["status"]})
    db.commit()
    return {"id": contact_id, "status": "engaged"}


class ContactUpdate(BaseModel):
    email: str = None
    mobile: str = None
    phone: str = None
    job_title: str = None
    contact_type: str = None
    linkedin_url: str = None

# Fields that get persisted to contact_field_overrides so they survive recompiles
_CONTACT_OVERRIDE_FIELDS = {'email', 'mobile', 'phone', 'job_title', 'contact_type', 'linkedin_url'}


@router.patch("/{contact_id}")
def update_contact(contact_id: str, update: ContactUpdate, db=Depends(get_db), user=Depends(get_current_user)):
    row = db.execute("SELECT id FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Contact not found")

    fields = {k: v for k, v in update.dict().items() if v is not None}
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    sets = ", ".join(f"{k} = ?" for k in fields)
    vals = list(fields.values()) + [contact_id]
    db.execute(f"UPDATE contacts SET {sets}, updated_at = datetime('now') WHERE id = ?", vals)

    # Persist user-edited fields to contact_field_overrides so they survive recompiles
    override_fields = {k: v for k, v in fields.items() if k in _CONTACT_OVERRIDE_FIELDS}
    if override_fields:
        # Ensure row exists
        db.execute(
            "INSERT OR IGNORE INTO contact_field_overrides (contact_id, updated_by) VALUES (?, ?)",
            (contact_id, user["username"])
        )
        for col, val in override_fields.items():
            db.execute(
                f"UPDATE contact_field_overrides SET {col} = ?, updated_by = ?, updated_at = datetime('now') "
                "WHERE contact_id = ?",
                (val, user["username"], contact_id)
            )

    db.commit()
    return {"id": contact_id, "updated": list(fields.keys())}


@router.get("/{contact_id}/affiliated-groups")
def contact_affiliated_groups(contact_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    """Returns all groups this contact has been associated with across all transactions."""
    contact = db.execute("SELECT id, display_name FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    if not contact:
        raise HTTPException(404, "Contact not found")

    rows = db.execute("""
        SELECT
            g.id, g.display_name, g.normalized_name, g.status,
            g.property_count, g.transaction_count, g.contact_count,
            CASE WHEN c.current_group_id = g.id THEN 1 ELSE 0 END as is_current_group,
            COUNT(DISTINCT tp_contact.source_id) as shared_transactions
        FROM transaction_parties tp_contact
        JOIN transaction_parties tp_group ON tp_contact.source_id = tp_group.source_id
            AND tp_group.group_id IS NOT NULL
            AND tp_group.side = tp_contact.side
        JOIN groups g ON tp_group.group_id = g.id
        JOIN contacts c ON c.id = ?
        WHERE tp_contact.contact_id = ?
            AND g.status != 'merged'
        GROUP BY g.id
        ORDER BY shared_transactions DESC
    """, (contact_id, contact_id)).fetchall()

    return {
        "contact": dict(contact),
        "affiliated_groups": [dict(r) for r in rows],
    }


# ── LinkedIn Profile Enrichment ──────────────────────────────

class LinkedInPosition(BaseModel):
    company: str
    title: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    is_current: bool = False
    location: Optional[str] = None
    company_logo_url: Optional[str] = None

class ContactDetailEntry(BaseModel):
    value: str
    type: str = "unknown"
    source_field: Optional[str] = None

class ContactDetails(BaseModel):
    emails: list[ContactDetailEntry] = []
    phones: list[ContactDetailEntry] = []

class LinkedInProfileData(BaseModel):
    linkedin_url: str
    headline: Optional[str] = None
    profile_photo_url: Optional[str] = None
    positions: list[LinkedInPosition] = []
    contact_details: Optional[ContactDetails] = None


@router.post("/{contact_id}/linkedin-profile")
def save_linkedin_profile(contact_id: str, data: LinkedInProfileData, db=Depends(get_db), user=Depends(get_current_user)):
    """Receive structured LinkedIn profile data (from Chrome extension or manual entry).
    Saves the URL + headline to overrides and replaces work history."""
    row = db.execute("SELECT id FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Contact not found")

    # Upsert contact_field_overrides with linkedin data + profile photo
    db.execute(
        "INSERT INTO contact_field_overrides (contact_id, linkedin_url, linkedin_headline, linkedin_photo_url, linkedin_enriched_at, updated_by) "
        "VALUES (?, ?, ?, ?, datetime('now'), ?) "
        "ON CONFLICT(contact_id) DO UPDATE SET "
        "linkedin_url = ?, linkedin_headline = ?, linkedin_photo_url = ?, linkedin_enriched_at = datetime('now'), "
        "updated_by = ?, updated_at = datetime('now')",
        (contact_id, data.linkedin_url, data.headline, data.profile_photo_url, user["username"],
         data.linkedin_url, data.headline, data.profile_photo_url, user["username"])
    )

    # Replace work history (delete existing, insert new)
    db.execute("DELETE FROM contact_work_history WHERE contact_id = ?", (contact_id,))
    for pos in data.positions:
        db.execute(
            "INSERT INTO contact_work_history (contact_id, company, title, start_date, end_date, is_current, location, company_logo_url) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (contact_id, pos.company, pos.title, pos.start_date, pos.end_date,
             1 if pos.is_current else 0, pos.location, pos.company_logo_url)
        )

    # Save Datanyze contact details if provided
    contact_details_saved = False
    if data.contact_details:
        cd = data.contact_details
        # Pick the best email: prefer "work" type, then first available
        email = None
        if cd.emails:
            work_emails = [e for e in cd.emails if e.type == "work"]
            email = work_emails[0].value if work_emails else cd.emails[0].value

        # Pick mobile vs office phone
        mobile = None
        phone = None
        for p in cd.phones:
            if p.type in ("mobile", "cell", "direct") and not mobile:
                mobile = p.value
            elif p.type in ("hq", "office", "unknown") and not phone:
                phone = p.value
        # If only one phone and no type hint, put it in phone
        if not phone and not mobile and cd.phones:
            phone = cd.phones[0].value

        # Build dynamic SET clause — only update fields that have values
        updates = []
        params = []
        if email:
            updates.append("email = ?")
            params.append(email)
        if mobile:
            updates.append("mobile = ?")
            params.append(mobile)
        if phone:
            updates.append("phone = ?")
            params.append(phone)

        if updates:
            params.extend([user["username"], contact_id])
            db.execute(
                f"UPDATE contact_field_overrides SET {', '.join(updates)}, "
                f"updated_by = ?, updated_at = datetime('now') "
                f"WHERE contact_id = ?",
                params
            )
            # Only fill blank fields in the contacts table — never overwrite RT data
            existing = db.execute(
                "SELECT email, phone, mobile FROM contacts WHERE id = ?",
                (contact_id,)
            ).fetchone()
            if existing:
                fill_updates = []
                fill_params = []
                if email and not existing["email"]:
                    fill_updates.append("email = ?")
                    fill_params.append(email)
                if mobile and not existing["mobile"]:
                    fill_updates.append("mobile = ?")
                    fill_params.append(mobile)
                if phone and not existing["phone"]:
                    fill_updates.append("phone = ?")
                    fill_params.append(phone)
                if fill_updates:
                    fill_params.append(contact_id)
                    db.execute(
                        f"UPDATE contacts SET {', '.join(fill_updates)}, updated_at = datetime('now') "
                        f"WHERE id = ?",
                        fill_params
                    )
            contact_details_saved = True

        # Store the full Datanyze response for reference
        db.execute(
            "UPDATE contact_field_overrides SET datanyze_raw = ?, updated_at = datetime('now') "
            "WHERE contact_id = ?",
            (json.dumps({"emails": [e.model_dump() for e in cd.emails],
                         "phones": [p.model_dump() for p in cd.phones]}), contact_id)
        )

    log_action(db, user, "contact.linkedin_enriched", "contact", contact_id, {
        "linkedin_url": data.linkedin_url,
        "positions_count": len(data.positions),
        "contact_details_saved": contact_details_saved,
    })
    db.commit()

    return {
        "id": contact_id,
        "linkedin_url": data.linkedin_url,
        "linkedin_headline": data.headline,
        "positions_saved": len(data.positions),
        "contact_details_saved": contact_details_saved,
    }


@router.get("/{contact_id}/work-history")
def contact_work_history(contact_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    """Returns stored work history for a contact, ordered by most recent first."""
    row = db.execute("SELECT id FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Contact not found")

    positions = db.execute(
        "SELECT id, company, title, start_date, end_date, is_current, location, company_logo_url, created_at "
        "FROM contact_work_history WHERE contact_id = ? "
        "ORDER BY is_current DESC, start_date DESC",
        (contact_id,)
    ).fetchall()

    # Also get the overrides for linkedin metadata
    overrides = db.execute(
        "SELECT linkedin_url, linkedin_headline, linkedin_photo_url, linkedin_enriched_at "
        "FROM contact_field_overrides WHERE contact_id = ?",
        (contact_id,)
    ).fetchone()

    return {
        "contact_id": contact_id,
        "linkedin_url": overrides["linkedin_url"] if overrides else None,
        "linkedin_headline": overrides["linkedin_headline"] if overrides else None,
        "linkedin_enriched_at": overrides["linkedin_enriched_at"] if overrides else None,
        "positions": [dict(p) for p in positions],
    }
