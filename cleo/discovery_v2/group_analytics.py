"""Stage A10: auto_group_analytics — roll up group_analytics per auto_group.

Aggregates the constituent legacy groups (via legacy_to_auto_group_map) into a
single per-auto_group analytics row. Lets the contacts / properties / map
routes read property_type_mix, totals, regions, etc. against the unified Group
concept instead of joining one arbitrary SPV per contact.

Aggregation rules per column:
- Sums:        property_count, total_assessed_value, total_buys, total_sells,
               net_acquisitions, buys/sells_last_12m/36m
- Min/Max:     first_transaction_date / last_transaction_date
- Weighted:   avg_buy_price = SUM(legacy_avg × legacy_buys) / SUM(legacy_buys);
              avg_sell_price = same shape; centroid_lat/lng weighted by
              property_count
- JSON sum:    property_type_mix — sum value-per-key across legacy mixes
- Set union:   regions — distinct sorted; region_count = len
- Recomputed: txns_per_year = (total_buys + total_sells) / years_span
- Skipped:    medians (can't be reconstructed from per-group medians),
              hq_lat/lng (will be derived from auto_groups.primary_address)
"""
from __future__ import annotations
import json
import sqlite3
from collections import defaultdict
from datetime import date


def build_auto_group_analytics(conn: sqlite3.Connection, *, verbose: bool = True) -> dict:
    if verbose:
        print('  Stage A10 (auto_group_analytics): starting...', flush=True)

    # Idempotent column adds — mirrors the owned-asset-class breakdown rolled up
    # from group_analytics. Safe on databases predating these columns.
    for col in ("owned_asset_class_counts TEXT", "owned_asset_class_value TEXT"):
        try:
            conn.execute(f"ALTER TABLE auto_group_analytics ADD COLUMN {col}")
        except sqlite3.OperationalError:
            pass

    conn.execute('DELETE FROM auto_group_analytics')

    # Pull every legacy group's analytics + its auto_group mapping in one shot.
    rows = conn.execute("""
        SELECT m.auto_group_id,
               ga.group_id,
               ga.property_count,
               ga.total_assessed_value,
               ga.property_type_mix,
               ga.owned_asset_class_counts,
               ga.owned_asset_class_value,
               ga.regions,
               ga.total_buys,
               ga.total_sells,
               ga.avg_buy_price,
               ga.avg_sell_price,
               ga.first_transaction_date,
               ga.last_transaction_date,
               ga.net_acquisitions,
               ga.buys_last_12m,
               ga.sells_last_12m,
               ga.buys_last_36m,
               ga.sells_last_36m,
               ga.centroid_lat,
               ga.centroid_lng
        FROM legacy_to_auto_group_map m
        JOIN group_analytics ga ON ga.group_id = m.legacy_group_id
    """).fetchall()

    agg: dict[str, dict] = defaultdict(lambda: {
        'property_count': 0,
        'total_assessed_value': 0,
        'property_type_mix': defaultdict(int),
        'owned_asset_class_counts': defaultdict(int),
        'owned_asset_class_value': defaultdict(int),
        'regions': set(),
        'total_buys': 0,
        'total_sells': 0,
        # Weighted-mean accumulators: (sum, weight)
        'buy_price_num': 0, 'buy_price_den': 0,
        'sell_price_num': 0, 'sell_price_den': 0,
        'centroid_lat_num': 0.0, 'centroid_lat_den': 0,
        'centroid_lng_num': 0.0, 'centroid_lng_den': 0,
        'first_transaction_date': None,
        'last_transaction_date': None,
        'net_acquisitions': 0,
        'buys_last_12m': 0,
        'sells_last_12m': 0,
        'buys_last_36m': 0,
        'sells_last_36m': 0,
    })

    for r in rows:
        a = agg[r['auto_group_id']]
        # Simple sums
        for k in ('property_count', 'total_assessed_value', 'total_buys', 'total_sells',
                  'net_acquisitions', 'buys_last_12m', 'sells_last_12m',
                  'buys_last_36m', 'sells_last_36m'):
            if r[k] is not None:
                a[k] += r[k]

        # JSON sum for property_type_mix
        if r['property_type_mix']:
            try:
                mix = json.loads(r['property_type_mix'])
                for k, v in mix.items():
                    if isinstance(v, (int, float)):
                        a['property_type_mix'][k] += int(v)
            except (json.JSONDecodeError, TypeError):
                pass

        # JSON sum for the owned asset-class count/value breakdowns
        for src_key in ('owned_asset_class_counts', 'owned_asset_class_value'):
            if r[src_key]:
                try:
                    blob = json.loads(r[src_key])
                    for k, v in blob.items():
                        if isinstance(v, (int, float)):
                            a[src_key][k] += int(v)
                except (json.JSONDecodeError, TypeError):
                    pass

        # Union regions
        if r['regions']:
            try:
                regions = json.loads(r['regions'])
                if isinstance(regions, list):
                    for region in regions:
                        if region:
                            a['regions'].add(region)
            except (json.JSONDecodeError, TypeError):
                pass

        # Weighted-mean prices (legacy avg × legacy count = total dollars; divide later)
        if r['avg_buy_price'] is not None and r['total_buys']:
            a['buy_price_num'] += r['avg_buy_price'] * r['total_buys']
            a['buy_price_den'] += r['total_buys']
        if r['avg_sell_price'] is not None and r['total_sells']:
            a['sell_price_num'] += r['avg_sell_price'] * r['total_sells']
            a['sell_price_den'] += r['total_sells']

        # Weighted centroid by property_count
        if r['centroid_lat'] is not None and r['property_count']:
            a['centroid_lat_num'] += r['centroid_lat'] * r['property_count']
            a['centroid_lat_den'] += r['property_count']
        if r['centroid_lng'] is not None and r['property_count']:
            a['centroid_lng_num'] += r['centroid_lng'] * r['property_count']
            a['centroid_lng_den'] += r['property_count']

        # Min/Max dates
        if r['first_transaction_date']:
            if a['first_transaction_date'] is None or r['first_transaction_date'] < a['first_transaction_date']:
                a['first_transaction_date'] = r['first_transaction_date']
        if r['last_transaction_date']:
            if a['last_transaction_date'] is None or r['last_transaction_date'] > a['last_transaction_date']:
                a['last_transaction_date'] = r['last_transaction_date']

    today = date.today().isoformat()
    inserts: list[tuple] = []
    for agid, a in agg.items():
        # Weighted-mean prices
        avg_buy = int(a['buy_price_num'] / a['buy_price_den']) if a['buy_price_den'] else None
        avg_sell = int(a['sell_price_num'] / a['sell_price_den']) if a['sell_price_den'] else None
        centroid_lat = (a['centroid_lat_num'] / a['centroid_lat_den']) if a['centroid_lat_den'] else None
        centroid_lng = (a['centroid_lng_num'] / a['centroid_lng_den']) if a['centroid_lng_den'] else None

        # txns_per_year from totals + year span
        total_txns = a['total_buys'] + a['total_sells']
        txns_per_year = None
        if total_txns and a['first_transaction_date'] and a['last_transaction_date']:
            try:
                start = date.fromisoformat(a['first_transaction_date'])
                end = date.fromisoformat(a['last_transaction_date'])
                years = max((end - start).days / 365.25, 1.0)
                txns_per_year = round(total_txns / years, 2)
            except (ValueError, TypeError):
                pass

        # Property-type mix → dict ordered by count desc (storage order doesn't matter
        # but consistency helps debugging).
        mix = dict(sorted(a['property_type_mix'].items(), key=lambda kv: (-kv[1], kv[0])))
        ac_counts = dict(sorted(a['owned_asset_class_counts'].items(), key=lambda kv: (-kv[1], kv[0])))
        ac_value = dict(sorted(a['owned_asset_class_value'].items(), key=lambda kv: (-kv[1], kv[0])))
        regions_sorted = sorted(a['regions'])

        inserts.append((
            agid,
            a['property_count'] or None,
            a['total_assessed_value'] or None,
            json.dumps(mix) if mix else None,
            json.dumps(ac_counts) if ac_counts else None,
            json.dumps(ac_value) if ac_value else None,
            json.dumps(regions_sorted) if regions_sorted else None,
            len(regions_sorted) or None,
            a['total_buys'] or None,
            a['total_sells'] or None,
            avg_buy, avg_sell,
            a['first_transaction_date'],
            a['last_transaction_date'],
            a['net_acquisitions'] or None,
            txns_per_year,
            a['buys_last_12m'] or None,
            a['sells_last_12m'] or None,
            a['buys_last_36m'] or None,
            a['sells_last_36m'] or None,
            centroid_lat, centroid_lng,
            today,
        ))

    if inserts:
        conn.executemany(
            """INSERT INTO auto_group_analytics
               (auto_group_id, property_count, total_assessed_value,
                property_type_mix, owned_asset_class_counts, owned_asset_class_value,
                regions, region_count,
                total_buys, total_sells, avg_buy_price, avg_sell_price,
                first_transaction_date, last_transaction_date,
                net_acquisitions, txns_per_year,
                buys_last_12m, sells_last_12m, buys_last_36m, sells_last_36m,
                centroid_lat, centroid_lng, refreshed_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            inserts,
        )

    # ── Unified Property pass (Phase D follow-up) ─────────────────────────
    #
    # Walks every (auto_group, party-side) once via auto_group_members joined
    # to transactions. Per auto_group we accumulate:
    #   - resolved property_ids (for the legacy transacted_type_mix + count)
    #   - unified Property identity = COALESCE(property_id, canonical_address_key)
    #     where canonical_address_key = lower(trim(display_address)) + '|' +
    #     lower(trim(city)). Counts both resolved AND unresolved transactions.
    #   - per-Property: most-recent (sale_date, side) to derive properties_owned
    #   - real-sum buy_value / sell_value with priced-count alongside
    #
    # Rows where BOTH property_id is null AND display_address is empty are
    # included in the financial sums (they're real transactions) but excluded
    # from properties_total (no identity to dedupe on).
    transacted_typed: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))
    properties_seen: dict[str, set] = defaultdict(set)
    # property_key → (latest_sale_date, side_on_latest) for each auto_group
    latest_per_property: dict[str, dict[str, tuple[str, str]]] = defaultdict(dict)
    money: dict[str, dict[str, int]] = defaultdict(lambda: {
        'buy_sum': 0, 'sell_sum': 0, 'n_buys_priced': 0, 'n_sells_priced': 0,
    })

    for r in conn.execute("""
        SELECT agm.auto_group_id     AS agid,
               agm.side               AS side,
               t.source_id            AS source_id,
               t.property_id          AS property_id,
               t.display_address      AS display_address,
               t.city                 AS city,
               t.sale_date            AS sale_date,
               t.sale_price           AS sale_price,
               p.asset_class          AS asset_class
        FROM auto_group_members agm
        JOIN transactions t ON t.source_id = agm.source_id
        LEFT JOIN properties p ON p.id = t.property_id
        WHERE agm.member_type = 'party_side'
    """):
        agid = r['agid']

        # Real-sum dollar totals
        price = r['sale_price'] or 0
        if r['side'] == 'buyer':
            if price > 0:
                money[agid]['buy_sum'] += price
                money[agid]['n_buys_priced'] += 1
        elif r['side'] == 'seller':
            if price > 0:
                money[agid]['sell_sum'] += price
                money[agid]['n_sells_priced'] += 1

        # Unified property identity
        prop_key = r['property_id']
        if not prop_key:
            addr = (r['display_address'] or '').strip().lower()
            city = (r['city'] or '').strip().lower()
            if addr:
                prop_key = f'addr:{addr}|{city}'
        if prop_key is None:
            continue   # truly orphan transaction — counts toward $ but not Property

        properties_seen[agid].add(prop_key)

        # Track latest party-side per property to derive properties_owned
        prev = latest_per_property[agid].get(prop_key)
        sale_date = r['sale_date'] or ''
        if prev is None or sale_date > prev[0]:
            latest_per_property[agid][prop_key] = (sale_date, r['side'] or '')

        # Resolved-only typed mix (existing semantic)
        if r['property_id'] is not None and r['asset_class']:
            transacted_typed[agid][r['asset_class']].add(r['property_id'])

    # Compose per-auto_group update rows
    unified_updates = []
    typed_keys = set(transacted_typed.keys())
    money_keys = set(money.keys())
    props_keys = set(properties_seen.keys())
    all_keys = typed_keys | money_keys | props_keys

    for agid in all_keys:
        ac_map = transacted_typed.get(agid, {})
        mix = {ac: len(p) for ac, p in ac_map.items()}
        mix = dict(sorted(mix.items(), key=lambda kv: (-kv[1], kv[0])))

        # Resolved-only count: distinct property_ids in the typed map
        resolved_pids = {pid for pids in ac_map.values() for pid in pids}
        transacted_count = len(resolved_pids) if resolved_pids else None

        pids_all = properties_seen.get(agid, set())
        properties_total = len(pids_all) if pids_all else None

        latest = latest_per_property.get(agid, {})
        properties_owned = sum(1 for _, side in latest.values() if side == 'buyer')
        properties_owned = properties_owned or None

        m = money.get(agid, {'buy_sum': 0, 'sell_sum': 0, 'n_buys_priced': 0, 'n_sells_priced': 0})
        total_buy_value = m['buy_sum'] or None
        total_sell_value = m['sell_sum'] or None
        n_buys_priced = m['n_buys_priced'] or None
        n_sells_priced = m['n_sells_priced'] or None

        unified_updates.append((
            json.dumps(mix) if mix else None,
            transacted_count,
            total_buy_value, total_sell_value,
            n_buys_priced, n_sells_priced,
            properties_total, properties_owned,
            agid,
        ))

    if unified_updates:
        conn.executemany(
            "UPDATE auto_group_analytics SET "
            "  transacted_type_mix       = ?, "
            "  transacted_property_count = ?, "
            "  total_buy_value           = ?, "
            "  total_sell_value          = ?, "
            "  n_buys_priced             = ?, "
            "  n_sells_priced            = ?, "
            "  properties_total          = ?, "
            "  properties_owned          = ? "
            "WHERE auto_group_id = ?",
            unified_updates,
        )

    conn.commit()

    if verbose:
        print(
            f'  Stage A10 (auto_group_analytics): {len(inserts):,} auto_groups rolled up, '
            f'{len(unified_updates):,} with unified-property metrics.',
            flush=True,
        )

    return {
        'n_auto_group_analytics_rows': len(inserts),
        'n_auto_groups_with_unified_metrics': len(unified_updates),
    }
