"""
Opportunity analysis for 732-746 10th St, Hanover (PRO_74887)
~17K sf retail plaza, Grey County, estimated value $5-8M
"""
import sqlite3
import json

conn = sqlite3.connect("data/cleo.db")
conn.row_factory = sqlite3.Row

# Build exclusion list as parameterized patterns
EXCLUDE_PATTERNS = [
    'City of%', '%Municipality%', '%School Board%', '%Her Majesty%', '%Crown%', 'Province of%',
    'Regional Municipality%', 'County of%',
    'Metro Ontario%', '%Loblaw%', 'Canadian Tire%', 'Walmart%', 'Wal-Mart%', 'Costco%',
    'Sobeys%', 'Parkland%', 'Husky Oil%', 'Home Hardware%',
    'Tim Horton%', 'McDonald%', 'Shoppers Drug%',
    'Bruce Trail%', 'Nature Conservancy%', '%Heritage Trust%',
    'Skyline%', 'RioCan%', 'Crombie%', 'CAPREIT%', 'HOOPP%', 'Dream Summit%',
    'Dream Industrial%', 'Manulife%', 'Manufacturers Life%', 'Desjardins%', 'InterRent%',
    'Homestead Land%', 'Crestpoint%', 'Farhi%', 'Bonnefield%', 'Canada Net%', 'NET REIT%',
]

def excl_sql():
    """Generate SQL NOT LIKE clauses for exclusions."""
    return " AND ".join([f"g.display_name NOT LIKE ?" for _ in EXCLUDE_PATTERNS])

def excl_params():
    return EXCLUDE_PATTERNS[:]

def fmt(assessed):
    if not assessed: return "$0"
    if assessed >= 1_000_000: return f"${assessed/1_000_000:,.1f}M"
    return f"${assessed:,.0f}"

# ====================================================================
print("=" * 80)
print("STRATEGY 1: RIGHT-SIZED RETAIL BUYERS ($2M-$15M, portfolio < $100M)")
print("=" * 80)
# ====================================================================

params = excl_params()
rows = conn.execute(f'''
    SELECT g.id, g.display_name, COUNT(DISTINCT t.source_id) as retail_buys,
           AVG(t.sale_price) as avg_price, MAX(t.sale_date) as last_buy,
           ga.property_count, ga.total_assessed_value, ga.property_type_mix, ga.regions,
           ga.buys_last_36m, ga.net_acquisitions
    FROM transactions t
    JOIN transaction_parties tp ON tp.source_id = t.source_id
    JOIN groups g ON g.id = tp.group_id
    JOIN group_analytics ga ON ga.group_id = g.id
    JOIN properties p ON p.id = t.property_id
    WHERE tp.side = 'buyer'
      AND p.asset_class = 'retail'
      AND t.sale_price BETWEEN 2000000 AND 15000000
      AND t.sale_price > 100
      AND (ga.total_assessed_value IS NULL OR ga.total_assessed_value < 100000000)
      AND ga.property_count < 50
      AND {excl_sql()}
    GROUP BY g.id
    HAVING retail_buys >= 1
    ORDER BY last_buy DESC
    LIMIT 25
''', params).fetchall()

for r in rows:
    d = dict(r)
    assessed = d['total_assessed_value'] or 0
    mix = json.loads(d['property_type_mix']) if d['property_type_mix'] else {}
    regions = json.loads(d['regions']) if d['regions'] else []
    materiality = (7_000_000 / assessed * 100) if assessed > 0 else 999
    print(f"\n{d['display_name']} ({d['id']})")
    print(f"  Retail buys: {d['retail_buys']} | Avg: {fmt(d['avg_price'])} | Last: {d['last_buy']}")
    print(f"  Portfolio: {d['property_count']} props | {fmt(assessed)} assessed | Net acq: {d['net_acquisitions']} | Last 36m: {d['buys_last_36m']}")
    print(f"  Deal materiality: {materiality:.0f}% of portfolio")
    print(f"  Mix: {mix}")
    print(f"  Regions: {regions}")

# ====================================================================
print("\n" + "=" * 80)
print("STRATEGY 2: WEALTHY LOCALS & ADJACENT-MARKET PLAYERS")
print("=" * 80)
# ====================================================================

nearby_regions = ['Grey County', 'Bruce', 'Huron County', 'Wellington', 'Dufferin County', 'Simcoe County', 'Perth County']
region_likes = " OR ".join([f"ga.regions LIKE ?" for _ in nearby_regions])
region_params = [f'%{r}%' for r in nearby_regions]

params = region_params + excl_params()
rows = conn.execute(f'''
    SELECT g.id, g.display_name, ga.property_count, ga.total_assessed_value,
           ga.total_buys, ga.buys_last_36m, ga.property_type_mix, ga.regions,
           ga.net_acquisitions, ga.avg_buy_price, ga.last_transaction_date
    FROM group_analytics ga
    JOIN groups g ON g.id = ga.group_id
    WHERE ga.total_buys >= 2
      AND ga.total_assessed_value > 2000000
      AND ga.net_acquisitions > 0
      AND ({region_likes})
      AND ga.property_count < 50
      AND ga.property_count >= 2
      AND {excl_sql()}
    ORDER BY ga.buys_last_36m DESC, ga.total_assessed_value DESC
    LIMIT 30
''', params).fetchall()

for r in rows:
    d = dict(r)
    assessed = d['total_assessed_value'] or 0
    mix = json.loads(d['property_type_mix']) if d['property_type_mix'] else {}
    regions = json.loads(d['regions']) if d['regions'] else []
    has_commercial = any(k in mix for k in ['retail', 'office', 'industrial', 'mixed_use'])
    diversified = len(mix) >= 2
    tags = []
    if has_commercial: tags.append("HAS COMMERCIAL")
    if diversified: tags.append("DIVERSIFIED")
    if 'farm' in mix and has_commercial: tags.append("FARM+COMMERCIAL")
    tag_str = f" [{', '.join(tags)}]" if tags else ""
    print(f"\n{d['display_name']} ({d['id']}){tag_str}")
    print(f"  Buys: {d['total_buys']} total | {d['buys_last_36m']} last 36m | Net acq: {d['net_acquisitions']} | Last: {d['last_transaction_date']}")
    print(f"  Portfolio: {d['property_count']} props | {fmt(assessed)} assessed | Avg buy: {fmt(d['avg_buy_price'])}")
    print(f"  Mix: {mix}")
    print(f"  Regions: {regions}")

# ====================================================================
print("\n" + "=" * 80)
print("STRATEGY 3: STEPPING-UP BUYERS (recent avg > historical avg)")
print("=" * 80)
# ====================================================================

params = excl_params()
rows = conn.execute(f'''
    SELECT g.id, g.display_name, ga.avg_buy_price,
           recent.avg_recent_price, recent.recent_count, recent.max_recent,
           ga.property_count, ga.total_assessed_value, ga.property_type_mix, ga.regions,
           ga.buys_last_36m, ga.net_acquisitions
    FROM group_analytics ga
    JOIN groups g ON g.id = ga.group_id
    JOIN (
        SELECT tp.group_id,
               AVG(t.sale_price) as avg_recent_price,
               MAX(t.sale_price) as max_recent,
               COUNT(*) as recent_count
        FROM transactions t
        JOIN transaction_parties tp ON tp.source_id = t.source_id
        WHERE tp.side = 'buyer'
          AND t.sale_date > date('now', '-3 years')
          AND t.sale_price > 500000
        GROUP BY tp.group_id
        HAVING recent_count >= 2
    ) recent ON recent.group_id = g.id
    WHERE recent.avg_recent_price > ga.avg_buy_price * 1.3
      AND ga.property_count < 50
      AND ga.total_assessed_value < 100000000
      AND ga.total_assessed_value > 2000000
      AND ga.avg_buy_price > 500000
      AND recent.max_recent >= 3000000
      AND {excl_sql()}
    ORDER BY recent.avg_recent_price DESC
    LIMIT 20
''', params).fetchall()

for r in rows:
    d = dict(r)
    assessed = d['total_assessed_value'] or 0
    mix = json.loads(d['property_type_mix']) if d['property_type_mix'] else {}
    regions = json.loads(d['regions']) if d['regions'] else []
    step_up = (d['avg_recent_price'] / d['avg_buy_price'] - 1) * 100 if d['avg_buy_price'] else 0
    print(f"\n{d['display_name']} ({d['id']})")
    print(f"  Step-up: {step_up:.0f}% | Historical avg: {fmt(d['avg_buy_price'])} -> Recent avg: {fmt(d['avg_recent_price'])} | Max recent: {fmt(d['max_recent'])}")
    print(f"  Recent buys: {d['recent_count']} | Portfolio: {d['property_count']} props | {fmt(assessed)} assessed")
    print(f"  Mix: {mix}")
    print(f"  Regions: {regions}")

# ====================================================================
print("\n" + "=" * 80)
print("STRATEGY 4: CROSS-ASSET DIVERSIFIERS (retail is minority of portfolio)")
print("=" * 80)
# ====================================================================

params = excl_params()
rows = conn.execute(f'''
    SELECT g.id, g.display_name, ga.property_count, ga.total_assessed_value,
           ga.property_type_mix, ga.regions, ga.total_buys, ga.buys_last_36m,
           ga.net_acquisitions, ga.last_transaction_date
    FROM group_analytics ga
    JOIN groups g ON g.id = ga.group_id
    WHERE ga.property_type_mix LIKE '%retail%'
      AND ga.total_assessed_value > 3000000
      AND ga.property_count >= 3
      AND ga.property_count < 50
      AND ga.net_acquisitions > 0
      AND {excl_sql()}
    ORDER BY ga.buys_last_36m DESC, ga.total_assessed_value DESC
    LIMIT 80
''', params).fetchall()

diversifiers = []
for r in rows:
    d = dict(r)
    mix = json.loads(d['property_type_mix']) if d['property_type_mix'] else {}
    total_props = sum(mix.values())
    retail_count = mix.get('retail', 0)
    if total_props > 0 and 0 < retail_count < total_props * 0.4:
        primary = max(mix, key=mix.get)
        d['_mix'] = mix
        d['_primary'] = primary
        d['_retail_pct'] = retail_count / total_props * 100
        d['_regions'] = json.loads(d['regions']) if d['regions'] else []
        diversifiers.append(d)

for d in diversifiers[:20]:
    assessed = d['total_assessed_value'] or 0
    print(f"\n{d['display_name']} ({d['id']})")
    print(f"  Primary asset: {d['_primary']} | Retail: {d['_retail_pct']:.0f}% ({d['_mix'].get('retail',0)} of {sum(d['_mix'].values())} props)")
    print(f"  Buys: {d['total_buys']} total | {d['buys_last_36m']} last 36m | Net acq: {d['net_acquisitions']} | Last: {d['last_transaction_date']}")
    print(f"  Portfolio: {d['property_count']} props | {fmt(assessed)} assessed")
    print(f"  Full mix: {d['_mix']}")
    print(f"  Regions: {d['_regions']}")

conn.close()
