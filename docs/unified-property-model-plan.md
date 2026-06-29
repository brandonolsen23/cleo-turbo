# Unified Property Model

**Status**: planning
**Goal**: collapse four overlapping concepts (Property / Transacted / Owned / Party-side / Member) into one user-facing model. Surface unresolved RT transactions as Properties the same way resolved parcels are. Make aggregate values (buy/sell totals) reflect what actually happened, not just what the parcel resolver caught.

## Why this matters

Today the Group detail page shows numbers that don't reconcile and use confusing technical terms:

- "Properties: 99" (transacted, parcel-resolved only) vs "Properties (4)" tab (currently owned only)
- "Transactions: 776" but only 99 properties — gap unexplained to the user
- "Members: 1,048" — a Layer-2 implementation detail (party-side count), not a useful business number
- "Buy Value: $1.42B" derived from `avg_price × count` (statistical noise) rather than real sum of prices

The underlying data is fine — we just hide ~85% of it. For Metrus (a developer), only 105 of 697 party-sides resolve to a parcel because subdivision lot sales typically have empty ARN in Realtrack. The other 592 are real transactions at 404 distinct addresses for $4B in dispositions and we're not surfacing them.

## User decisions captured (2026-05-14)

- **One concept: Property.** A property is a unique address the group has ever transacted on. Resolved or not.
- **Owned**: the group is the last party-side as buyer at that property.
- **Drop the words "Transacted", "Members", "Party sides", "Currently owned"** from the UI. They're internal implementation, not vocabulary.
- **Unresolved transactions count toward metrics.** Their address + price + asset class are real even when the parcel resolver couldn't match them to a canonical record.

## Scope

**In:**
- Group detail page (`GroupDetailPage.tsx`): stat cards + Properties tab unification
- `/api/groups/{id}/properties` rewrite: include unresolved
- `auto_group_analytics` table: add real-sum buy/sell value columns; add total-property count covering unresolved
- Contact detail (`ContactDetailPage.tsx`): the same lens — Portfolio Size card and any property-list views use unified properties
- The Groups list page (`GroupsPage.tsx`) Properties column: now reflects unified count

**Out (deferred):**
- Properties main page redesign (still resolved-only). Phase F.
- Map page redesign. Map needs lat/lng, which only resolved properties have. Phase F.
- Cross-group "current owner" determination for unresolved addresses (would require cross-group address normalization). For now, per-group "last side I was on" is enough.
- Backfill historical analytics for closed deals — none exist yet.

## Architecture decisions

**A1. Property identity = `COALESCE(property_id, canonical_address_key)`.**
For resolved transactions the property_id is the identity. For unresolved we build a canonical key from `LOWER(TRIM(display_address)) + '|' + LOWER(TRIM(city))`. Two rows that produce the same canonical_address_key are the same Property.

Edge cases:
- Empty `display_address`: row is dropped from the property list (counts toward total Transactions but not toward Properties).
- Slightly different formatting ("4 Oxford Rd" vs "Oxford Road 4"): may produce two Property rows. Acceptable for now; an address normalizer pass can be added later if it becomes a problem.

**A2. Owned-at-property is per-(group, property).**
For each (auto_group, property) pair, "owned" = the group's most recent party-side at that property has `side='buyer'`. Computed by walking transaction history scoped to this auto_group's `auto_group_members` joined to transactions.

For resolved properties this is consistent with the existing `properties.current_owner_group_id` lens (which uses cross-group ground truth via parcel ownership). For unresolved properties we have only this group's view, but that's enough to mark "we last bought here" vs "we last sold here."

**A3. Aggregate values use real sums, not averages × counts.**
Replace `avg_buy_price * total_buys` derivations with `SUM(t.sale_price)` over the relevant party-side join. Skip NULL/zero prices in the sum but report `n_priced` alongside so the user knows how much of the activity is priced.

**A4. Asset class for unresolved properties.**
`transactions` doesn't carry `asset_class`. For unresolved properties we leave asset_class NULL and show "—" in the table. The asset-class filter and transacted_type_mix continue to count only properties where asset_class is known. The user can spot-check unresolved entries by address pattern (e.g. "Plan 65m -" is subdivision).

A future addition: a lightweight classifier that infers asset_class from `transaction_note` or address keywords for unresolved rows. Phase F.

**A5. One Properties tab, no "Sold" tab.**
Single unified list with columns: Address, City, Type, Last Date, Last Price, Side (Owned | Sold). A filter chip toggles "Owned only / Sold only / All." Drops the artificial Owned/Sold tab split.

**A6. Stats card layout.**
Six cards instead of five, fitting the unified concept:

| Card | Value | Subtitle |
|---|---|---|
| Properties | 503 | 99 parcel-matched · 404 by address |
| Owned | M of 503 | based on last-side-as-buyer |
| Transactions | 776 | 124 buys · 652 sells |
| Buy Value | $1.4B | total acquisitions |
| Sell Value | $4.0B | total dispositions |
| Last Txn | Feb 26, 2026 | Active since 1996 |

## Schema changes

**Migration 035 — auto_group_analytics columns:**
- `total_buy_value INTEGER` — SUM of buyer-side sale_prices across all auto_group_members
- `total_sell_value INTEGER` — SUM of seller-side sale_prices
- `n_buys_priced INTEGER` — how many buyer-side transactions had a non-NULL non-zero price
- `n_sells_priced INTEGER`
- `properties_total INTEGER` — distinct (property_id OR canonical_address_key) seen on any party-side
- `properties_owned INTEGER` — subset where the group's last party-side at this property has side='buyer'

Existing columns kept (`property_count` = legacy currently-owned via parcel resolver only; `transacted_property_count` = resolved-only count). New columns add the unresolved-inclusive view.

**No new tables.** All work fits in `auto_group_analytics` + new endpoint logic.

## Wave breakdown

### Wave 1 — Backend analytics + endpoint

1. **Migration 035** — six new columns on `auto_group_analytics`
2. **Update `cleo/discovery_v2/group_analytics.py` (Stage A10):**
   - Compute the new totals using one pass over `auto_group_members → transactions`:
     - `total_buy_value`, `total_sell_value`: SUM(sale_price) split by side
     - `n_buys_priced`, `n_sells_priced`: count of priced rows
     - `properties_total`: distinct COALESCE(property_id, canonical_address_key)
     - `properties_owned`: subset where the latest party-side per property has side='buyer'
   - For each property key, track `(latest_sale_date, side_on_latest)` and count owned where side='buyer'
3. **Rewrite `GET /api/groups/{id}/properties`** to return unified rows:
   - Each row is one canonical Property (resolved or unresolved)
   - Fields: `property_id` (nullable), `canonical_address_key` (nullable when property_id set), `display_address`, `city`, `asset_class` (nullable), `last_date`, `last_price`, `last_side` (buyer/seller), `is_owned` (bool), `n_transactions` (this group's count at this property), `resolved` (bool)
   - Sort by `last_date DESC` by default
   - Query param `filter=owned|sold|all` for the filter chip
4. **Retire `GET /api/groups/{id}/properties-sold`** — Sold is now a filter on the unified endpoint
5. **Update detail endpoint** — return the new analytics fields verbatim

### Wave 2 — Frontend Group detail

1. Update `GroupDetail` and `GroupPropertyRow` types in `frontend/src/types/index.ts`
2. Rewrite stat-cards row in `GroupDetailPage.tsx` to match the 6-card layout above
3. Replace the Properties + Sold tabs with one **Properties** tab containing:
   - Filter chip (Owned / Sold / All — defaults to All)
   - Sortable columns: Address, City, Type, Last Date, Last Price, Side
   - "Owned" side badge in jade, "Sold" in gray
   - Resolved properties link to `/properties/{id}`; unresolved render as plain text
4. Drop the "Sold" tab and the `kind` prop from `PropertiesTab`

### Wave 3 — Contact detail parity

1. Update `Portfolio Size` card on ContactDetailPage to use the same unified property concept (count includes unresolved buyer-side transactions for this contact)
2. The Map tab on Contact detail keeps using resolved properties only (no lat/lng for unresolved) — add a subtitle noting "showing X of Y properties with mapped parcels"
3. Career tab unchanged

### Wave 4 — Wiring + verification

1. Re-run Stage A10 once with the new columns
2. Hit `/api/groups/AGRP_00186` (Metrus) and verify:
   - properties_total ≈ 99 + 404 = 503
   - total_buy_value ≈ $1.4B
   - total_sell_value ≈ $4.0B
   - properties_owned roughly matches what makes sense
3. Visual smoke test on 3-5 representative groups: a developer (Metrus), a holder (RioCan or Chartwell), a small standalone (DVS Farms), and an over-clustered legacy case (Ontario Superior Court)

## Test plan

- **Metrus (developer)**: Properties = 503, Owned ≈ 5-15 (active inventory), Buy Value = $1.4B, Sell Value = $4.0B
- **Chartwell (multifamily holder)**: Properties = ~80, Owned ≈ ~47, mostly multifamily, low sell value
- **DVS Farms (small operator)**: Properties = 4, all from a few transactions
- **Ontario Superior Court (over-clustered)**: Properties ~ 800, Owned = small, Sell Value massive (judicial sales)
- Filter chip: `filter=owned` returns only buyer-side-last rows; `filter=sold` returns only seller-side-last rows
- Resolved property rows link to `/properties/{id}` and load correctly; unresolved render plain text

## Risk register

| Risk | Mitigation |
|---|---|
| Address formatting drift splits the same property into multiple rows | Acceptable for v1. Future: a normalizer that strips legal subdivision references ("Plan 65m") and unifies "4 Oxford Rd" / "Oxford Road 4". |
| `transactions.display_address` is sometimes a phrase fragment ("in Bankruptcy and Insolvency") | These rows aggregate harmlessly. They appear as exotic Property entries on court-style auto_groups. Acceptable. |
| Stage A10 runtime balloons with the new owned-per-property pass | The per-property latest-side scan adds one pass over auto_group_members joined to transactions. ~700k rows; should run in <30s. Will time and confirm before shipping. |
| `total_sell_value = $4B` is too dominant in the UI for developers | The card label "Sell Value" + subtitle "total dispositions" makes context clear. User explicitly asked for both buy and sell values. |
| `properties_owned` for unresolved is per-group (not cross-group ground truth) | Acceptable; documented in tooltip. Cross-group inference would require address normalization at the system level. |

## Effort estimate

| Wave | Hours |
|---|---|
| 1 — Backend (migration + A10 + endpoint) | ~1.5 |
| 2 — Frontend Group detail rebuild | ~1.0 |
| 3 — Contact detail parity | ~0.5 |
| 4 — Wiring + verification | ~0.5 |
| **Total** | **~3.5 hours** |

## Decisions to confirm before kickoff

(None — the user has already approved the shape. The plan is ready to execute.)
