"""
Tenure-related endpoints for the Contact page.

Three endpoints:
  GET /api/contacts/:id/tenures/:stem        — Tenure Detail drawer payload
  GET /api/companies/:stem/portfolio-footprint — Hero map (current employer's portfolio)
  GET /api/contacts/:id/property-footprint-tenured — Color-coded pin map
"""
import json
from fastapi import APIRouter, Depends, HTTPException
from ..deps import get_db, get_current_user

router = APIRouter()


def _resolve_fingerprint(db, contact_id: str) -> str | None:
    row = db.execute(
        "SELECT name_fingerprint FROM contacts WHERE id = ?", (contact_id,)
    ).fetchone()
    if not row:
        return None
    raw = row["name_fingerprint"]
    return raw.lower() if raw else None


@router.get("/contacts/{contact_id}/tenures/{stem}")
def tenure_detail(
    contact_id: str, stem: str,
    db=Depends(get_db), user=Depends(get_current_user),
):
    fp = _resolve_fingerprint(db, contact_id)
    if not fp:
        raise HTTPException(status_code=404, detail="Contact not found")

    cbt = db.execute(
        """
        SELECT brand_stem, strict_start_date, strict_end_date,
               inferred_start_date, inferred_end_date,
               n_party_sides_strict, n_party_sides_inferred,
               top_phrases_json, source_field_breakdown_json,
               dominant_address_unit, auto_group_id, is_active
        FROM contact_brand_tenures
        WHERE contact_fingerprint = ? AND brand_stem = ?
        """,
        (fp, stem),
    ).fetchone()
    if not cbt:
        raise HTTPException(status_code=404, detail="Tenure not found")

    body = dict(cbt)
    top_phrases = json.loads(body.pop("top_phrases_json"))
    body["top_phrases"] = top_phrases
    body["display_name"] = top_phrases[0]["phrase"] if top_phrases else stem
    body["source_field_breakdown"] = json.loads(body.pop("source_field_breakdown_json"))

    body["auto_group_display_name"] = None
    if body.get("auto_group_id"):
        gd = db.execute(
            "SELECT display_name FROM auto_groups WHERE auto_group_id = ?",
            (body["auto_group_id"],),
        ).fetchone()
        if gd:
            body["auto_group_display_name"] = gd["display_name"]

    side_stems: dict = {}
    for r in db.execute(
        """
        SELECT pa.source_id, pa.side, m.stem, pa.atom_value, pa.source_field
        FROM party_atoms pa
        JOIN brand_stem_phrase_map m ON m.phrase = pa.atom_value
        JOIN party_fingerprints pf ON pf.source_id = pa.source_id AND pf.side = pa.side
        WHERE pa.atom_type='brand_phrase'
          AND pa.source_field IN ('trade_name','care_of','companies_json')
          AND pf.contact_fingerprint = ?
        """,
        (fp,),
    ).fetchall():
        side_stems.setdefault((r["source_id"], r["side"]), []).append(
            {"stem": r["stem"], "phrase": r["atom_value"], "source_field": r["source_field"]}
        )

    side_addr: dict = {}
    for r in db.execute(
        """
        SELECT pf.source_id, pf.side, pf.city,
               COALESCE(pf.street_number,'') AS sn,
               COALESCE(pf.street_name,'') AS st,
               COALESCE(pf.street_suffix,'') AS sx,
               COALESCE(pf.street_direction,'') AS sd,
               COALESCE(pf.suite_type,'') AS suite_t,
               COALESCE(pf.suite_number,'') AS suite_n
        FROM party_fingerprints pf WHERE pf.contact_fingerprint = ?
        """,
        (fp,),
    ).fetchall():
        side_addr[(r["source_id"], r["side"])] = "|".join([
            (r["city"] or "").lower(), r["sn"], (r["st"] or "").lower(),
            (r["sx"] or "").lower(), (r["sd"] or "").lower(),
            (r["suite_t"] or "").lower(), r["suite_n"],
        ])

    txn_rows = db.execute(
        """
        SELECT tp.source_id, tp.side, t.sale_date, t.sale_price,
               t.display_address, t.city
        FROM transaction_parties tp
        JOIN transactions t ON tp.source_id = t.source_id
        JOIN contacts c ON c.id = tp.contact_id
        WHERE LOWER(c.name_fingerprint) = ?
          AND t.sale_date BETWEEN ? AND ?
        ORDER BY t.sale_date DESC
        """,
        (fp, body["inferred_start_date"], body["inferred_end_date"]),
    ).fetchall()

    credited = []
    for r in txn_rows:
        sid_key = (r["source_id"], r["side"])
        explicit_phrases = [s for s in side_stems.get(sid_key, []) if s["stem"] == stem]
        address_match = (
            body.get("dominant_address_unit") is not None
            and side_addr.get(sid_key) == body["dominant_address_unit"]
        )
        if explicit_phrases:
            txn_dict = dict(r)
            txn_dict["inferred"] = False
            txn_dict["brand_phrase"] = explicit_phrases[0]["phrase"]
            txn_dict["source_field"] = explicit_phrases[0]["source_field"]
            credited.append(txn_dict)
        elif address_match:
            txn_dict = dict(r)
            txn_dict["inferred"] = True
            txn_dict["brand_phrase"] = None
            txn_dict["source_field"] = None
            credited.append(txn_dict)
    body["credited_transactions"] = credited
    return body


@router.get("/companies/{stem}/portfolio-footprint")
def company_portfolio_footprint(
    stem: str, db=Depends(get_db), user=Depends(get_current_user),
):
    """Every transaction credited to any tenure carrying this stem."""
    n_tenures = db.execute(
        "SELECT COUNT(*) AS n FROM contact_brand_tenures WHERE brand_stem = ?",
        (stem,),
    ).fetchone()["n"]
    if n_tenures == 0:
        raise HTTPException(status_code=404, detail="Stem has no tenures")

    rows = db.execute(
        """
        SELECT DISTINCT t.source_id, t.sale_date, t.sale_price,
               t.display_address, t.city, t.property_id,
               p.lat, p.lng, p.asset_class
        FROM contact_brand_tenures cbt
        JOIN contacts c ON LOWER(c.name_fingerprint) = cbt.contact_fingerprint
        JOIN transaction_parties tp ON tp.contact_id = c.id
        JOIN transactions t ON t.source_id = tp.source_id
        LEFT JOIN properties p ON p.id = t.property_id
        WHERE cbt.brand_stem = ?
          AND t.sale_date BETWEEN cbt.inferred_start_date AND cbt.inferred_end_date
        """,
        (stem,),
    ).fetchall()

    properties = []
    seen_ids = set()
    for r in rows:
        if r["property_id"] in seen_ids:
            continue
        if r["lat"] is None or r["lng"] is None:
            continue
        seen_ids.add(r["property_id"])
        properties.append({
            "id": r["property_id"],
            "display_address": r["display_address"],
            "city": r["city"],
            "lat": r["lat"], "lng": r["lng"],
            "asset_class": r["asset_class"],
            "most_recent_sale_price": r["sale_price"],
        })
    return {
        "stem": stem,
        "n_transactions": len(rows),
        "properties": properties,
    }


@router.get("/contacts/{contact_id}/property-footprint-tenured")
def contact_property_footprint_tenured(
    contact_id: str, db=Depends(get_db), user=Depends(get_current_user),
):
    """Contact's properties with tenure_stem + inferred flag per pin."""
    fp = _resolve_fingerprint(db, contact_id)
    if not fp:
        raise HTTPException(status_code=404, detail="Contact not found")

    tenures = [dict(r) for r in db.execute(
        """
        SELECT brand_stem, inferred_start_date, inferred_end_date,
               dominant_address_unit, n_party_sides_inferred
        FROM contact_brand_tenures WHERE contact_fingerprint = ?
        ORDER BY inferred_end_date DESC
        """,
        (fp,),
    ).fetchall()]

    side_addr: dict = {}
    for r in db.execute(
        """
        SELECT pf.source_id, pf.side, pf.city,
               COALESCE(pf.street_number,'') AS sn,
               COALESCE(pf.street_name,'') AS st,
               COALESCE(pf.street_suffix,'') AS sx,
               COALESCE(pf.street_direction,'') AS sd,
               COALESCE(pf.suite_type,'') AS suite_t,
               COALESCE(pf.suite_number,'') AS suite_n
        FROM party_fingerprints pf WHERE pf.contact_fingerprint = ?
        """,
        (fp,),
    ).fetchall():
        side_addr[(r["source_id"], r["side"])] = "|".join([
            (r["city"] or "").lower(), r["sn"], (r["st"] or "").lower(),
            (r["sx"] or "").lower(), (r["sd"] or "").lower(),
            (r["suite_t"] or "").lower(), r["suite_n"],
        ])

    side_stems: dict = {}
    for r in db.execute(
        """
        SELECT pa.source_id, pa.side, m.stem
        FROM party_atoms pa
        JOIN brand_stem_phrase_map m ON m.phrase = pa.atom_value
        JOIN party_fingerprints pf ON pf.source_id = pa.source_id AND pf.side = pa.side
        WHERE pa.atom_type='brand_phrase'
          AND pa.source_field IN ('trade_name','care_of','companies_json')
          AND pf.contact_fingerprint = ?
        """,
        (fp,),
    ).fetchall():
        side_stems.setdefault((r["source_id"], r["side"]), set()).add(r["stem"])

    rows = db.execute(
        """
        SELECT t.source_id, tp.side, t.sale_date, t.sale_price,
               t.display_address, t.city, t.property_id,
               p.lat, p.lng, p.asset_class
        FROM transaction_parties tp
        JOIN transactions t ON t.source_id = tp.source_id
        LEFT JOIN properties p ON p.id = t.property_id
        WHERE tp.contact_id = ?
        """,
        (contact_id,),
    ).fetchall()

    properties = []
    seen = set()
    for r in rows:
        if r["property_id"] in seen or r["lat"] is None or r["lng"] is None:
            continue
        seen.add(r["property_id"])
        sid_key = (r["source_id"], r["side"])
        attribution = None
        if r["sale_date"]:
            for t in tenures:
                if not (t["inferred_start_date"] <= r["sale_date"] <= t["inferred_end_date"]):
                    continue
                explicit = t["brand_stem"] in side_stems.get(sid_key, set())
                addr_match = (
                    t.get("dominant_address_unit") is not None
                    and side_addr.get(sid_key) == t["dominant_address_unit"]
                )
                if explicit or addr_match:
                    attribution = {"brand_stem": t["brand_stem"], "inferred": not explicit}
                    break
        properties.append({
            "id": r["property_id"],
            "display_address": r["display_address"],
            "city": r["city"],
            "lat": r["lat"], "lng": r["lng"],
            "asset_class": r["asset_class"],
            "most_recent_sale_price": r["sale_price"],
            "tenure_stem": (attribution or {}).get("brand_stem"),
            "inferred": (attribution or {}).get("inferred", False),
        })
    return {"properties": properties}
