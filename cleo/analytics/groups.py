"""
Group Analytics — compute and materialize portfolio, transaction, velocity,
and geographic metrics for every group.

The group_analytics table is a SYSTEM table (not derived, not CRM).
It survives compiler rebuilds and is refreshed on demand.

Usage:
    from cleo.analytics.groups import refresh_group_analytics

    # Full refresh (all groups):
    refresh_group_analytics(conn)

    # Targeted refresh (after CRM edit):
    refresh_group_analytics(conn, group_ids=["GRP_00123", "GRP_00456"])
"""

import json
import math
import time
from datetime import datetime, timedelta
from statistics import median


def _haversine_km(lat1, lng1, lat2, lng2):
    """Great-circle distance between two points in km."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlng / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _compute_hold_periods(conn, group_id):
    """
    Compute average hold period for a group by finding properties where the
    group bought AND later sold.  Returns average days or None.
    """
    # Get all transactions where this group was a party, grouped by property
    rows = conn.execute(
        """
        SELECT t.property_id, t.sale_date, tp.side
        FROM transaction_parties tp
        JOIN transactions t ON tp.source_id = t.source_id
        WHERE tp.group_id = ? AND t.property_id IS NOT NULL AND t.sale_date IS NOT NULL
        ORDER BY t.property_id, t.sale_date
        """,
        (group_id,)
    ).fetchall()

    # Group by property
    props = {}
    for r in rows:
        pid = r["property_id"]
        if pid not in props:
            props[pid] = []
        props[pid].append((r["sale_date"], r["side"]))

    hold_days = []
    for pid, txns in props.items():
        # Sort by date
        txns.sort(key=lambda x: x[0])
        # Find buy→sell pairs
        last_buy_date = None
        for date_str, side in txns:
            if side == "buyer":
                last_buy_date = date_str
            elif side == "seller" and last_buy_date:
                try:
                    buy_dt = datetime.strptime(last_buy_date[:10], "%Y-%m-%d")
                    sell_dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
                    days = (sell_dt - buy_dt).days
                    if days > 0:
                        hold_days.append(days)
                except (ValueError, TypeError):
                    pass
                last_buy_date = None

    return round(sum(hold_days) / len(hold_days)) if hold_days else None


def refresh_group_analytics(conn, group_ids=None):
    """
    Compute and upsert group analytics.

    Args:
        conn: SQLite connection (with row_factory=sqlite3.Row)
        group_ids: Optional list of group IDs to refresh.
                   If None, refreshes ALL groups with any transaction or property.
    """
    start = time.time()

    # Ensure the table exists
    conn.execute("""
        CREATE TABLE IF NOT EXISTS group_analytics (
            group_id            TEXT PRIMARY KEY REFERENCES groups(id),
            property_count      INTEGER DEFAULT 0,
            total_assessed_value INTEGER,
            property_type_mix   TEXT,
            regions             TEXT,
            region_count        INTEGER DEFAULT 0,
            total_buys          INTEGER DEFAULT 0,
            total_sells         INTEGER DEFAULT 0,
            avg_buy_price       INTEGER,
            median_buy_price    INTEGER,
            avg_sell_price      INTEGER,
            median_sell_price   INTEGER,
            first_transaction_date TEXT,
            last_transaction_date  TEXT,
            net_acquisitions    INTEGER DEFAULT 0,
            avg_hold_period_days INTEGER,
            txns_per_year       REAL,
            buys_last_12m       INTEGER DEFAULT 0,
            sells_last_12m      INTEGER DEFAULT 0,
            buys_last_36m       INTEGER DEFAULT 0,
            sells_last_36m      INTEGER DEFAULT 0,
            hq_lat              REAL,
            hq_lng              REAL,
            avg_distance_from_hq_km REAL,
            max_distance_from_hq_km REAL,
            geographic_radius_km REAL,
            centroid_lat        REAL,
            centroid_lng        REAL,
            refreshed_at        TEXT DEFAULT (datetime('now'))
        )
    """)

    # Determine which groups to refresh
    if group_ids:
        placeholders = ",".join("?" for _ in group_ids)
        target_groups = conn.execute(
            f"SELECT id FROM groups WHERE id IN ({placeholders})", group_ids
        ).fetchall()
        target_ids = [r["id"] for r in target_groups]
    else:
        # All groups that have at least one transaction party or own a property
        target_groups = conn.execute("""
            SELECT DISTINCT g.id FROM groups g
            WHERE g.id IN (
                SELECT DISTINCT group_id FROM transaction_parties WHERE group_id IS NOT NULL
                UNION
                SELECT DISTINCT current_owner_group_id FROM properties WHERE current_owner_group_id IS NOT NULL
            )
        """).fetchall()
        target_ids = [r["id"] for r in target_groups]

    if not target_ids:
        print("  Group Analytics: no groups to refresh")
        return 0

    now = datetime.now()
    cutoff_12m = (now - timedelta(days=365)).strftime("%Y-%m-%d")
    cutoff_36m = (now - timedelta(days=365 * 3)).strftime("%Y-%m-%d")

    # ----- Bulk-load transaction data -----
    # Build a dict: group_id → {buys: [(date, price)], sells: [(date, price)]}
    print(f"  Group Analytics: loading transaction data for {len(target_ids):,} groups...")

    group_txns = {}
    for gid in target_ids:
        group_txns[gid] = {"buys": [], "sells": []}

    # Process in batches to avoid SQL parameter limits
    BATCH = 500
    for i in range(0, len(target_ids), BATCH):
        batch = target_ids[i:i + BATCH]
        placeholders = ",".join("?" for _ in batch)
        rows = conn.execute(
            f"""
            SELECT tp.group_id, tp.side, t.sale_date, t.sale_price
            FROM transaction_parties tp
            JOIN transactions t ON tp.source_id = t.source_id
            WHERE tp.group_id IN ({placeholders})
            """,
            batch
        ).fetchall()
        for r in rows:
            gid = r["group_id"]
            side = r["side"]
            if gid in group_txns:
                bucket = "buys" if side == "buyer" else "sells"
                group_txns[gid][bucket].append((r["sale_date"], r["sale_price"]))

    # ----- Bulk-load property data -----
    print("  Group Analytics: loading property data...")

    group_props = {}  # group_id → [{lat, lng, region, type, assessed_value}]
    for gid in target_ids:
        group_props[gid] = []

    for i in range(0, len(target_ids), BATCH):
        batch = target_ids[i:i + BATCH]
        placeholders = ",".join("?" for _ in batch)
        rows = conn.execute(
            f"""
            SELECT p.current_owner_group_id as gid, p.id as pid, p.lat, p.lng,
                   p.region, p.primary_property_type as ptype,
                   p.most_recent_sale_price as sale_price
            FROM properties p
            WHERE p.current_owner_group_id IN ({placeholders})
            """,
            batch
        ).fetchall()
        for r in rows:
            gid = r["gid"]
            if gid in group_props:
                group_props[gid].append({
                    "pid": r["pid"],
                    "lat": r["lat"],
                    "lng": r["lng"],
                    "region": r["region"],
                    "ptype": r["ptype"],
                    "sale_price": r["sale_price"],
                })

    # Bulk-load assessed values (latest per property)
    print("  Group Analytics: loading assessment data...")
    prop_assessed = {}  # property_id → latest assessed value
    for i in range(0, len(target_ids), BATCH):
        batch = target_ids[i:i + BATCH]
        placeholders = ",".join("?" for _ in batch)
        rows = conn.execute(
            f"""
            SELECT ga.property_id, ga.assessed_value, ga.valuation_date
            FROM gw_assessments ga
            JOIN properties p ON ga.property_id = p.id
            WHERE p.current_owner_group_id IN ({placeholders})
              AND ga.assessed_value IS NOT NULL
            ORDER BY ga.valuation_date DESC
            """,
            batch
        ).fetchall()
        for r in rows:
            pid = r["property_id"]
            if pid and pid not in prop_assessed:
                prop_assessed[pid] = r["assessed_value"]

    # ----- Load existing HQ coordinates (preserve across refreshes) -----
    existing_geo = {}
    for i in range(0, len(target_ids), BATCH):
        batch = target_ids[i:i + BATCH]
        placeholders = ",".join("?" for _ in batch)
        rows = conn.execute(
            f"SELECT group_id, hq_lat, hq_lng FROM group_analytics WHERE group_id IN ({placeholders})",
            batch
        ).fetchall()
        for r in rows:
            if r["hq_lat"] is not None and r["hq_lng"] is not None:
                existing_geo[r["group_id"]] = (r["hq_lat"], r["hq_lng"])

    # ----- Compute metrics per group -----
    print("  Group Analytics: computing metrics...")
    upsert_count = 0

    for gid in target_ids:
        txns = group_txns.get(gid, {"buys": [], "sells": []})
        props = group_props.get(gid, [])

        # -- Portfolio metrics --
        prop_count = len(props)
        # Portfolio value: sum of most recent sale prices (purchase value only)
        total_assessed = sum(
            p.get("sale_price") or 0
            for p in props
        ) or None

        type_counts = {}
        region_set = set()
        for p in props:
            ptype = p["ptype"] or "unknown"
            type_counts[ptype] = type_counts.get(ptype, 0) + 1
            if p["region"]:
                region_set.add(p["region"])

        property_type_mix = json.dumps(type_counts) if type_counts else None
        regions = json.dumps(sorted(region_set)) if region_set else None
        region_count = len(region_set)

        # -- Transaction metrics --
        buys = txns["buys"]
        sells = txns["sells"]
        total_buys = len(buys)
        total_sells = len(sells)

        buy_prices = [p for _, p in buys if p and p > 0]
        sell_prices = [p for _, p in sells if p and p > 0]

        avg_buy = round(sum(buy_prices) / len(buy_prices)) if buy_prices else None
        med_buy = round(median(buy_prices)) if buy_prices else None
        avg_sell = round(sum(sell_prices) / len(sell_prices)) if sell_prices else None
        med_sell = round(median(sell_prices)) if sell_prices else None

        all_dates = [d for d, _ in buys + sells if d]
        all_dates.sort()
        first_date = all_dates[0] if all_dates else None
        last_date = all_dates[-1] if all_dates else None

        net_acq = total_buys - total_sells

        # Hold period (expensive — only compute for groups with manageable txn count)
        hold_period = None
        if total_buys > 0 and total_sells > 0 and (total_buys + total_sells) < 500:
            hold_period = _compute_hold_periods(conn, gid)

        # -- Velocity metrics --
        total_txns = total_buys + total_sells
        txns_per_year = None
        if first_date and last_date and first_date != last_date:
            try:
                first_dt = datetime.strptime(first_date[:10], "%Y-%m-%d")
                last_dt = datetime.strptime(last_date[:10], "%Y-%m-%d")
                years = (last_dt - first_dt).days / 365.25
                if years > 0:
                    txns_per_year = round(total_txns / years, 2)
            except (ValueError, TypeError):
                pass

        buys_12m = sum(1 for d, _ in buys if d and d >= cutoff_12m)
        sells_12m = sum(1 for d, _ in sells if d and d >= cutoff_12m)
        buys_36m = sum(1 for d, _ in buys if d and d >= cutoff_36m)
        sells_36m = sum(1 for d, _ in sells if d and d >= cutoff_36m)

        # -- Geographic metrics --
        hq_lat, hq_lng = existing_geo.get(gid, (None, None))

        coords = [(p["lat"], p["lng"]) for p in props if p["lat"] and p["lng"]]
        centroid_lat = None
        centroid_lng = None
        avg_dist = None
        max_dist = None
        geo_radius = None

        if coords:
            centroid_lat = round(sum(c[0] for c in coords) / len(coords), 6)
            centroid_lng = round(sum(c[1] for c in coords) / len(coords), 6)

            if hq_lat is not None and hq_lng is not None:
                distances = [_haversine_km(hq_lat, hq_lng, c[0], c[1]) for c in coords]
                avg_dist = round(sum(distances) / len(distances), 1) if distances else None
                max_dist = round(max(distances), 1) if distances else None

            # Geographic radius: max pairwise distance / 2
            if len(coords) >= 2:
                max_pair = 0
                # Sample if too many points
                sample = coords if len(coords) <= 50 else coords[:25] + coords[-25:]
                for i in range(len(sample)):
                    for j in range(i + 1, len(sample)):
                        d = _haversine_km(sample[i][0], sample[i][1],
                                          sample[j][0], sample[j][1])
                        if d > max_pair:
                            max_pair = d
                geo_radius = round(max_pair / 2, 1)

        # -- Upsert --
        conn.execute(
            """
            INSERT OR REPLACE INTO group_analytics (
                group_id, property_count, total_assessed_value, property_type_mix,
                regions, region_count, total_buys, total_sells, avg_buy_price,
                median_buy_price, avg_sell_price, median_sell_price,
                first_transaction_date, last_transaction_date, net_acquisitions,
                avg_hold_period_days, txns_per_year, buys_last_12m, sells_last_12m,
                buys_last_36m, sells_last_36m, hq_lat, hq_lng,
                avg_distance_from_hq_km, max_distance_from_hq_km,
                geographic_radius_km, centroid_lat, centroid_lng, refreshed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (gid, prop_count, total_assessed, property_type_mix, regions,
             region_count, total_buys, total_sells, avg_buy, med_buy,
             avg_sell, med_sell, first_date, last_date, net_acq,
             hold_period, txns_per_year, buys_12m, sells_12m, buys_36m,
             sells_36m, hq_lat, hq_lng, avg_dist, max_dist, geo_radius,
             centroid_lat, centroid_lng)
        )
        upsert_count += 1

        if upsert_count % 5000 == 0:
            conn.commit()

    conn.commit()

    elapsed = round(time.time() - start, 1)
    print(f"  Group Analytics: refreshed {upsert_count:,} groups in {elapsed}s")
    return upsert_count
