# Schema Guide for Opportunity Analysis

## Key Tables

### properties
The property universe — ~85K Ontario commercial properties.

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | `PRO_NNNNN` format |
| arn | TEXT UNIQUE | 20-digit Assessment Roll Number — the backbone ID |
| display_address | TEXT | Street address |
| city | TEXT | Municipality name |
| region | TEXT | Ontario region (e.g., "Grey County", "Metro Toronto") |
| acreage | REAL | Lot size |
| asset_class | TEXT | retail, multifamily, industrial, office, agricultural, land, mixed_use, hospitality |
| primary_property_type | TEXT | More granular: retail, multifamily, industrial, comm-ind-land, farm, res-land, office, hotel-motel, restaurant-bar, other-bldg |
| current_owner_name | TEXT | GW owner name (may differ from most recent buyer) |
| current_owner_group_id | TEXT | FK to groups |
| most_recent_sale_date | TEXT | ISO date |
| most_recent_sale_price | INTEGER | CAD, may be NULL |
| transaction_count | INTEGER | Total known transactions |
| lat, lng | REAL | Coordinates (when resolved) |

### transactions
~125K sale records from Realtrack.

| Column | Type | Notes |
|--------|------|-------|
| source_id | TEXT PK | RT transaction ID |
| property_id | TEXT FK | Links to properties.id (may be NULL if unresolved) |
| arn | TEXT | May be NULL |
| sale_date | TEXT | ISO date |
| sale_price | INTEGER | CAD. $1-$2 = nominal transfer |
| display_address | TEXT | |
| city | TEXT | |
| region | TEXT | |
| description | TEXT | Property description from RT |
| seller_parties | TEXT | JSON array of seller names |
| buyer_parties | TEXT | JSON array of buyer names |
| cash, debt, chattels, other_consideration | INTEGER | Deal structure breakdown |

### groups
~136K companies/entities.

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | `GRP_NNNNN` format |
| display_name | TEXT | Company name |
| normalized_name | TEXT UNIQUE | Uppercase, legal suffixes stripped |
| property_count | INTEGER | Current owned properties |
| transaction_count | INTEGER | Total transactions |
| contact_count | INTEGER | Associated contacts |

### group_analytics
Pre-computed analytics per group — the power table for opportunity finding.

| Column | Type | Notes |
|--------|------|-------|
| group_id | TEXT PK FK | Links to groups.id |
| property_count | INTEGER | Current owned properties |
| total_assessed_value | INTEGER | Sum of assessed values |
| property_type_mix | TEXT | JSON object: `{"retail": 5, "farm": 3, "industrial": 2}` |
| regions | TEXT | JSON array: `["Grey County", "Bruce", "Wellington"]` |
| region_count | INTEGER | Number of distinct regions |
| total_buys | INTEGER | Lifetime buy transactions |
| total_sells | INTEGER | Lifetime sell transactions |
| avg_buy_price | INTEGER | Average acquisition price |
| median_buy_price | INTEGER | Median acquisition price |
| avg_sell_price | INTEGER | Average disposition price |
| buys_last_12m | INTEGER | Buys in trailing 12 months |
| sells_last_12m | INTEGER | Sells in trailing 12 months |
| buys_last_36m | INTEGER | Buys in trailing 36 months |
| sells_last_36m | INTEGER | Sells in trailing 36 months |
| net_acquisitions | INTEGER | total_buys - total_sells |
| txns_per_year | REAL | Annual transaction velocity |
| first_transaction_date | TEXT | Earliest known transaction |
| last_transaction_date | TEXT | Most recent transaction |
| avg_hold_period_days | INTEGER | Average hold in days |
| centroid_lat, centroid_lng | REAL | Portfolio geographic center |

### transaction_parties
Links transactions to contacts and groups.

| Column | Type | Notes |
|--------|------|-------|
| source_id | TEXT FK | Links to transactions.source_id |
| contact_id | TEXT FK | Links to contacts.id |
| group_id | TEXT FK | Links to groups.id |
| side | TEXT | `'buyer'` or `'seller'` |
| party_name | TEXT | Raw party name from transaction |
| phone | TEXT | |

### contacts
~84K individuals.

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | `CON_NNNNN` format |
| display_name | TEXT | |
| current_group_id | TEXT FK | Most recent group affiliation |
| contact_type | TEXT | |
| transaction_count | INTEGER | |

### gw_assessments
GeoWarehouse assessment data (~750 records currently).

| Column | Type | Notes |
|--------|------|-------|
| property_id | TEXT FK | Links to properties |
| assessed_value | INTEGER | MPAC assessed value |
| zoning | TEXT | Zoning code |
| property_code | TEXT | MPAC property code |
| ownership_type | TEXT | |
| site_area_sqft | REAL | |
| municipality | TEXT | |

## Common Query Patterns

### Find buyers of a specific asset class in a price range
```sql
SELECT g.id, g.display_name, COUNT(*) as buy_count, AVG(t.sale_price) as avg_price,
       MAX(t.sale_date) as last_buy, ga.property_count, ga.total_assessed_value
FROM transactions t
JOIN transaction_parties tp ON tp.source_id = t.source_id
JOIN groups g ON g.id = tp.group_id
JOIN group_analytics ga ON ga.group_id = g.id
JOIN properties p ON p.id = t.property_id
WHERE tp.side = 'buyer'
  AND p.asset_class = ?            -- e.g., 'retail'
  AND t.sale_price BETWEEN ? AND ? -- price range
  AND t.sale_price > 100           -- exclude nominal transfers
GROUP BY g.id
ORDER BY last_buy DESC
```

### Find groups active in nearby regions
```sql
SELECT g.id, g.display_name, ga.total_buys, ga.property_count,
       ga.total_assessed_value, ga.property_type_mix, ga.regions
FROM group_analytics ga
JOIN groups g ON g.id = ga.group_id
WHERE (ga.regions LIKE '%Grey County%' OR ga.regions LIKE '%Bruce%')
  AND ga.total_buys >= 2
ORDER BY ga.buys_last_36m DESC
```

### Find transaction counterparties of a known buyer
```sql
SELECT seller_g.id, seller_g.display_name, t.display_address, t.sale_price, t.sale_date
FROM transactions t
JOIN transaction_parties buyer_tp ON buyer_tp.source_id = t.source_id AND buyer_tp.side = 'buyer'
JOIN transaction_parties seller_tp ON seller_tp.source_id = t.source_id AND seller_tp.side = 'seller'
JOIN groups seller_g ON seller_g.id = seller_tp.group_id
WHERE buyer_tp.group_id = ?  -- known buyer group_id
ORDER BY t.sale_date DESC
```

### Find potential sellers (long hold + small portfolio)
```sql
SELECT p.id, p.display_address, p.city, p.most_recent_sale_date, p.most_recent_sale_price,
       p.current_owner_name, g.id as group_id, ga.property_count, ga.sells_last_12m
FROM properties p
LEFT JOIN groups g ON g.id = p.current_owner_group_id
LEFT JOIN group_analytics ga ON ga.group_id = g.id
WHERE p.asset_class = ?
  AND p.most_recent_sale_date < date('now', '-10 years')
  AND (ga.property_count IS NULL OR ga.property_count <= 3)
ORDER BY p.most_recent_sale_date ASC
```

## Ontario Regions Reference

The 50 regions in the database, grouped by market tier:

**GTA Core**: Metro Toronto, Peel Region, York Region, Durham Region, Halton Region
**GTA Ring**: Kitchener-Waterloo, Hamilton-Wentworth, Niagara N, Niagara S, Simcoe County
**Southwest Secondary**: Grey County, Bruce, Huron County, Perth County, Wellington, Dufferin County, Middlesex County, Oxford County, Elgin County, Lambton, Brant, Norfolk, Kent County, Essex County
**Eastern**: Ottawa-Carleton, Frontenac County, Hastings County, Leeds, Renfrew, Lanark County, Lennox County, Northumberland, Peterborough County, Prince Edward, Stormont, Prescott, Russell Township, Grenville County, Glengarry County
**Central**: Muskoka, Victoria, Haldimand County
**Northern**: Algoma, Cochrane, Kenora, Nipissing District, Parry Sound, Sudbury, Thunder Bay, Manitoulin, Rainy River
