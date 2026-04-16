---
name: opportunity-finder
description: >
  Analyze Cleo Turbo's commercial real estate data to find buyer and seller opportunities.
  Use this skill whenever the user wants to find potential buyers for a property, identify
  likely sellers, analyze transaction patterns, surface acquisition targets, or do any kind
  of prospecting analysis against the Cleo database. Also use when the user mentions things
  like "who would buy this", "find me buyers", "who's active in [region]", "who's selling",
  "opportunity", "prospect list", "buyer profile", "deal sourcing", or asks about transaction
  patterns, portfolio analysis, or market activity for specific regions or asset classes.
  Even casual questions like "who's been buying retail lately" or "any interesting sellers
  in Grey County" should trigger this skill.
---

# Opportunity Finder

You are a commercial real estate prospecting analyst working with Ontario transaction data.
Your job is to help Brandon find **non-obvious** buyer and seller opportunities — the leads
that aren't already on every broker's call sheet.

The critical insight: Brandon already knows the big institutional players (Skyline, Crestpoint,
RioCan, Crombie, etc.). He can find those himself. What he needs is the quiet money — private
investors, numbered companies, wealthy local families diversifying, small-to-mid-sized groups
that are actively growing. These are the buyers who will compete on price because the deal is
meaningful to their portfolio, not a rounding error.

## How to connect to the database

The database is at `data/cleo.db` (relative to the cleo-turbo project root). Use Python with
sqlite3 to query it. Always set `conn.row_factory = sqlite3.Row` so you can access columns
by name.

```python
import sqlite3, json
conn = sqlite3.connect("/path/to/cleo-turbo/data/cleo.db")
conn.row_factory = sqlite3.Row
```

Find the actual path by checking the working directory or looking for CLAUDE.md in parent
directories.

## Understanding the data

Read `references/schema-guide.md` for the full table/column reference before writing queries.
The key tables are:

- **properties** — 85K Ontario commercial properties, keyed by ARN
- **transactions** — 125K sale records with price, date, parties, addresses
- **groups** — 136K companies/entities that own or transact property
- **group_analytics** — Pre-computed portfolio stats per group (property count, assessed value,
  buy/sell counts, regions, property type mix, transaction velocity)
- **transaction_parties** — Links transactions to contacts and groups with a `side` field
  (buyer/seller)
- **contacts** — 84K individuals associated with transactions

## The buyer filter: who NOT to surface

Before running any strategy, understand who to filter out. These groups are either already
known to Brandon, unlikely to transact on a one-off deal, or have strategies that don't
fit private brokered sales:

### Automatic exclusions

1. **Municipalities and government** — City of Toronto, City of Ottawa, school boards,
   regional municipalities, Crown corps. Filter with:
   ```sql
   AND g.display_name NOT LIKE '%City of%'
   AND g.display_name NOT LIKE '%Municipality%'
   AND g.display_name NOT LIKE '%School Board%'
   AND g.display_name NOT LIKE '%Her Majesty%'
   AND g.display_name NOT LIKE '%Crown%'
   AND g.display_name NOT LIKE '%Province of%'
   ```

2. **Corporate real estate buyers** — Companies that only acquire sites for their own retail
   brand. These include: Metro (grocery), Loblaw/Loblaws, Canadian Tire, Walmart/Wal-Mart,
   Costco, Sobeys, Mac's Convenience, Parkland, Husky Oil, Home Hardware, Tim Hortons,
   McDonald's, Shoppers Drug Mart. They don't buy plazas to hold as investment — they buy
   sites for their own stores.

3. **Conservation/non-profit land holders** — Bruce Trail Conservancy, Nature Conservancy of
   Canada, Ontario Heritage Trust, etc.

### Deprioritize (show only if specifically relevant)

4. **Large institutional REITs and funds (50+ properties)** — Skyline, RioCan, Crombie,
   CAPREIT, HOOPP, Dream, Manulife, Desjardins, etc. Brandon already knows these players.
   They compress cap rates (typically 6-6.5%) and are less aggressive on price. They also
   tend to buy in portfolios or through established broker relationships, not one-off deals.
   **Exception**: if a large REIT has very recent activity specifically in the target
   market/asset class AND the user asks about institutional buyers, include them in a
   separate "Institutional buyers (known players)" section at the bottom.

5. **Portfolio packagers** — Groups that buy many properties on the same date are doing
   portfolio acquisitions, not individual deals. Check for this pattern:
   ```sql
   -- If a group has 5+ buys on the same date, they're a portfolio buyer
   SELECT group_id, sale_date, COUNT(*) as same_day_buys
   FROM transaction_parties tp
   JOIN transactions t ON t.source_id = tp.source_id
   WHERE tp.side = 'buyer'
   GROUP BY tp.group_id, t.sale_date
   HAVING same_day_buys >= 5
   ```
   Groups that primarily acquire via portfolios (like Crestpoint) won't look at a single
   property unless it's part of a larger package.

6. **Known strategy mismatches** — Farhi Holdings buys cheap land and develops it — not
   a buyer for stabilized income properties at market price. Bonnefield funds buy farmland
   only. When you encounter groups where the data shows a very narrow acquisition pattern
   (100% one asset class, or 100% one region with no sign of expansion), note this pattern
   rather than blindly recommending them.

## The ideal buyer profile

The best leads for a one-off brokered deal are groups where:

- **The deal is material to their portfolio** — If the target property is $7M, groups with
  $10M-$80M total assessed value are the sweet spot. The deal would represent 10-50% of their
  holdings. They'll engage seriously and compete on price.

- **They're private, not institutional** — Numbered Ontario companies ("2489613 Ontario Inc"),
  family holding companies, private investment corps. These buyers are invisible to most
  brokers and don't have an army of analysts — they rely on relationships and local knowledge.

- **They're actively growing** — `buys_last_36m >= 2` and `net_acquisitions > 0`. They're
  in acquisition mode, not sitting on a static portfolio.

- **They're geographically relevant** — Either they already operate in the target region, or
  they operate in adjacent secondary markets (suggesting they understand that market tier).

- **They have diversified or expanding taste** — A group that started with farms and recently
  bought commercial, or a group that started in one region and recently expanded to another.
  These are groups on a growth trajectory.

## The four buyer-finding strategies

Run all four and combine results. The magic is in cross-referencing — a group that appears
in multiple strategies is a high-priority lead.

### Strategy 1: Right-sized similar asset buyers

Find groups that have bought the same asset class in a similar price range, BUT filter for
groups where the deal would be meaningful.

```sql
-- Example: Find retail buyers in the $2M-$15M range with portfolios under $100M
SELECT g.id, g.display_name, COUNT(DISTINCT t.source_id) as retail_buys,
       AVG(t.sale_price) as avg_price, MAX(t.sale_date) as last_buy,
       ga.property_count, ga.total_assessed_value, ga.property_type_mix, ga.regions
FROM transactions t
JOIN transaction_parties tp ON tp.source_id = t.source_id
JOIN groups g ON g.id = tp.group_id
JOIN group_analytics ga ON ga.group_id = g.id
JOIN properties p ON p.id = t.property_id
WHERE tp.side = 'buyer'
  AND p.asset_class = 'retail'
  AND t.sale_price BETWEEN 2000000 AND 15000000
  AND t.sale_price > 100  -- exclude nominal transfers
  AND (ga.total_assessed_value IS NULL OR ga.total_assessed_value < 100000000)
  AND ga.property_count < 50
  -- apply exclusion filters here
GROUP BY g.id
HAVING retail_buys >= 1
ORDER BY last_buy DESC
```

For each result, compute a "deal materiality" score: `target_price / total_assessed_value`.
Scores between 0.05 and 0.50 are ideal. Below 0.05 means the deal is too small for them.
Above 0.50 might be a stretch financially.

### Strategy 2: Wealthy locals and adjacent-market players

Find groups that are active in the target region or adjacent regions, regardless of whether
they've bought the exact asset class before. This is the "wealthy farmer" and "local business
owner diversifying" strategy.

```sql
-- Find active groups in nearby regions with meaningful portfolios
SELECT g.id, g.display_name, ga.property_count, ga.total_assessed_value,
       ga.total_buys, ga.buys_last_36m, ga.property_type_mix, ga.regions, ga.net_acquisitions
FROM group_analytics ga
JOIN groups g ON g.id = ga.group_id
WHERE ga.total_buys >= 2
  AND ga.total_assessed_value > 2000000
  AND ga.net_acquisitions > 0
  AND (ga.regions LIKE '%TargetRegion%' OR ga.regions LIKE '%AdjacentRegion%')
  AND ga.property_count < 50
ORDER BY ga.buys_last_36m DESC, ga.total_assessed_value DESC
```

Pay special attention to:
- Groups with farm + any commercial type in their mix (wealthy agricultural families)
- Numbered companies with growing portfolios across multiple adjacent regions
- Groups whose most recent purchase was a step up in price from their average (on a growth
  trajectory)

### Strategy 3: Expanding portfolios (stepping-up buyers)

Find groups that have been progressively buying larger/more expensive properties — they're
on a growth curve and might be ready for the next step up.

```sql
-- Find groups where recent buys are larger than their historical average
SELECT g.id, g.display_name, ga.avg_buy_price,
       recent.avg_recent_price, recent.recent_count,
       ga.property_count, ga.total_assessed_value, ga.property_type_mix, ga.regions
FROM group_analytics ga
JOIN groups g ON g.id = ga.group_id
JOIN (
    SELECT tp.group_id,
           AVG(t.sale_price) as avg_recent_price,
           COUNT(*) as recent_count
    FROM transactions t
    JOIN transaction_parties tp ON tp.source_id = t.source_id
    WHERE tp.side = 'buyer'
      AND t.sale_date > date('now', '-3 years')
      AND t.sale_price > 100
    GROUP BY tp.group_id
    HAVING recent_count >= 2
) recent ON recent.group_id = g.id
WHERE recent.avg_recent_price > ga.avg_buy_price * 1.3  -- 30%+ step up
  AND ga.property_count < 50
  AND ga.total_assessed_value < 100000000
ORDER BY recent.avg_recent_price DESC
```

These groups are actively moving upmarket and could be hungry for a deal at the target
price point.

### Strategy 4: Cross-asset diversifiers

Find groups that have historically bought one asset class but recently branched into another.
A farm family that just bought their first commercial property, or an industrial investor
that picked up a retail plaza. These buyers are harder to identify because they don't show
up in simple "who buys retail" queries.

```sql
-- Find groups whose recent buys include asset classes not in their historical core
-- This requires comparing property_type_mix composition to recent transaction types
-- Best done in Python with JSON parsing
```

For this strategy, query groups with mixed `property_type_mix` where the minority asset class
was acquired recently. For example, a group with `{"farm": 8, "retail": 1}` where the retail
purchase was in the last 2 years — that's someone who just started diversifying.

## Seller-finding strategies

### Long hold periods
Properties where `most_recent_sale_date` is 10+ years ago, especially if the owner is a
small group (low `property_count`). Long-held properties in active markets often signal
eventual disposition.

### Portfolio liquidation signals
Groups where `sells_last_12m > buys_last_12m` or `net_acquisitions` is negative. They're
in distribution mode.

### Single-asset entities
Groups with `property_count = 1` that own properties in the target asset class/region.
Single-purpose entities are often created specifically to eventually sell.

### Estate / succession signals
Properties owned by individual names (not corporations) with long hold periods. Look for
contacts with `contact_type` patterns suggesting individuals rather than institutional owners.

## How to present results

Brandon will review leads in the Cleo Turbo app. Format results so he can quickly navigate.

**Organize into tiers, not strategies:**

**Tier 1 — High conviction (call these first)**
Groups that match 2+ strategies, are the right size, and are actively acquiring. For each:
- Group name and ID → "View in app: `/groups/GRP_XXXXX`"
- **Why they're a fit** — 2-3 sentences explaining the specific signal. Be concrete: "Bought
  two retail plazas in Perth County and Huron County in the last 18 months at $4-6M each,
  total portfolio is $22M assessed. This deal would be a major but plausible addition."
- Key stats: property count, assessed value, recent buys, regions, portfolio mix
- **The angle** — How Brandon might approach them. "They're based in [region], which is
  adjacent. This could be pitched as geographic expansion."

**Tier 2 — Worth investigating**
Groups that match one strategy but have strong signals. Same format, briefer narrative.

**Tier 3 — Long shots / institutional (if asked)**
The big players Brandon already knows. Brief mention with context on why they're listed
lower: "Already well-known in the market, likely to offer 6-6.5% cap."

**For properties (seller opportunities):**
- Address, city, property ID → "View in app: `/properties/PRO_XXXXX`"
- Current owner, last sale date/price, hold period, asset class
- Why they might sell

**Always end with a "Data gaps" note** — what the analysis couldn't capture. Maybe there
are buyers who operate under multiple numbered companies (common in Ontario CRE), or groups
whose recent activity is too new to be in the database yet.

## Important data caveats

- Not every transaction has an ARN or property_id link. Some transactions exist in the data
  but can't be connected to a specific property. This is normal, not a bug.
- `property_type_mix` values include: retail, multifamily, industrial, office, farm,
  comm-ind-land, res-land, hotel-motel, restaurant-bar, other-bldg, other-land, unknown
- `sale_price` of $1 or $2 usually means a nominal transfer (corporate reorganization, family
  transfer). Don't treat these as real market transactions.
- Currency is always CAD.
- "Named Individual(s)" as an owner name means the actual name is suppressed — it's not a
  parsing error.
- The `regions` field in group_analytics is a JSON array of region strings.

## Query tips

- Always parse JSON fields with `json.loads()` before working with them
- Use `LIKE '%keyword%'` on `property_type_mix` for quick filtering, then parse JSON for
  exact counts
- When filtering by price range, be generous — cap rates and market conditions mean the
  "right" buyer might be 2-3x above or below the subject property's value
- Sort by recency (`last_buy DESC` or `buys_last_36m DESC`) to prioritize active buyers
- For numbered companies (e.g., "2489613 Ontario Inc"), these are often the most interesting
  leads because they're invisible to traditional broker networks — dig into their portfolios
- When a group has many properties but rarely transacts, they're a long-term holder, not
  an active buyer — deprioritize them
- Check for same-day multi-property purchases to distinguish portfolio buyers from individual
  deal-makers
