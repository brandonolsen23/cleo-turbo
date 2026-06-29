# Phase D — Groups Page Cutover to Unified auto_groups

**Status**: planning
**Goal**: make the Groups main page and Group Detail page display the same unified Group concept the Contacts page already uses. Eliminate the 136k-SPV legacy list as the primary surface. Make "View Group →" links from contact pages actually resolve.

## Why this matters

Today the system has two parallel Group concepts:
- **Contacts page** uses `auto_groups` (114k rolled-up operators). One row for "Chartwell Retirement Residences" covers 106 SPVs.
- **Groups page** uses legacy `groups` (136k SPVs). Chartwell appears as 106 separate rows.

This produces concrete bugs:
1. Clicking "View Group →" on a contact navigates to `/groups/AGRP_00234` → backend returns 404 (handler only knows `GRP_xxxxx`).
2. The Groups main page list is unusably long and fragmented for any real operator.
3. Filters give incoherent results: filter "owns ≥40 multifamily" on Groups misses Chartwell because no single SPV owns that many — only the rollup does.
4. The user mental model is "one operator = one Group". The Groups page contradicts that.

## Scope decisions

**In scope**:
- `/api/groups` browse, detail, filters
- Subresources: `/api/groups/{id}/contacts`, `/{id}/attribution`, `/{id}/hq-address`, `/{id}/refresh-analytics`
- Frontend `GroupsPage.tsx` (list) and `GroupDetailPage.tsx` (detail)
- HQ address writes go through `auto_group_user_edits` set_address (already plumbed)
- TransactionDetailPage party badges resolve to auto_groups (via legacy-ID dispatch)
- Engagement: contact-level status + auto_group rollup of "N of M contacts engaged"

**Out of scope (deferred to Phase E)**:
- `GroupComparePage.tsx` — separate effort
- `group_merges` legacy flow — auto_group merges already have `apply_user_edits` path
- CommandPalette / global search — Phase E
- `/api/groups/search` endpoint — Phase E
- CRM tables migration (`deals.group_id`, `buy_mandates.group_id`, etc.) — confirmed empty (0 rows each), so no data to migrate; we add `auto_group_id` columns when the CRM features ship
- Migrating legacy `groups.hq_address` values into auto_group user edits — those die with the legacy surface

## User decisions captured (2026-05-13)

- **(a) Engagement is per-contact, not per-group.** The contact's status flag (pool/engaged) is the source of truth. The Group detail page shows "X of N contacts engaged" rolled up across the auto_group's contacts. The old Promote/Engage endpoints on `/api/groups` are retired; group-level engagement is a derived view, not a stored state.
- **(b) "Currently Owned" is the primary lens.** A property is in the portfolio iff the auto_group is the *current* buyer. Properties the group bought and later sold are historical data — surface them in a separate "Sold" tab, not as part of the primary portfolio. The "Transacted In" framing disappears from the UI. (Behind the scenes, `transacted_type_mix` is still used for the asset-class filter and Primary/Secondary Type because that lens captures the operator's character; users never see the term.)
- **(c) No mixing of legacy and new in the UI.** The UI never displays `GRP_xxxxx`. Backend can still dispatch legacy IDs to auto_groups for old deep links (so they don't 404), but no surface element exposes the legacy concept. Legacy `groups.hq_address` is not migrated — orphans die quietly.
- **(d) CommandPalette / global search** — Phase E.

## Architecture decisions

**D1. ID space**: `/api/groups/{id}` accepts both `AGRP_xxxxx` and `GRP_xxxxx`. Legacy IDs are resolved via `legacy_to_auto_group_map` and the response is the auto_group's detail. Old deep links keep working without a 404. Frontend always emits `AGRP_xxxxx`.

**D2. Browse default**: List shows auto_groups only, filtered to exclude `canonical_stem='_anonymized_individuals'` and `tier='merged'`. No legacy toggle in UI; legacy is debugging-only.

**D3. Analytics source of truth**: `auto_group_analytics` (already built by Stage A10). Filters and sorts use that table directly. The asset_class filter uses `transacted_type_mix` (built today for contacts page).

**D4. Constituent SPVs**: Show on detail page as a card listing `legacy_to_auto_group_map` members. Each row has a detach button (calls existing `POST /api/auto-groups/{agid}/detach`).

**D5. Properties view — one primary lens, one secondary**:
- **Currently Owned** (primary) — `legacy_to_auto_group_map.legacy_group_id = properties.current_owner_group_id`. This is the operator's active portfolio.
- **Sold** (secondary tab) — properties where the auto_group's party-sides were the buyer on a previous transaction but the *current* owner is someone else. Historical data, useful for "who recently sold what."
- "Transacted In" is not a user-visible category. `transacted_type_mix` continues to power the asset-class filter and Primary/Secondary Type badges (where it captures the operator's character regardless of current ownership), but never appears as a tab label.

**D6. Engagement**: Per-contact, with a group-level rollup.
- `contacts.status` (pool/engaged) is the source of truth. Engagement is a contact-level action.
- Group detail page shows "N of M contacts engaged" — a derived count, no new column.
- The legacy `groups.status` field is ignored by the Groups UI. The legacy `POST /api/groups/{id}/promote` and `/engage` endpoints are retired (return 410 Gone, or just removed from the router).
- An "Engage Contact" action will be added to the contact card on the Group detail page so the user can toggle status without leaving.
- Per-engagement history (timestamp, by whom, note) uses the existing `activities` table — Phase E concern, not blocking this phase.

**D7. ID stability risk**: `AGRP_NNNNN` numbers are assigned by iteration order in standalone_coverage. A full discovery_v2 rebuild may reshuffle. Documented limitation; not blocking this phase. Phase F can address with `canonical_stem`-based stable IDs.

## Wave breakdown

### Wave 1 — Backend endpoints repointed

Rewrite the 15 endpoints in `cleo/web/routes/groups.py`. Per-endpoint cost is small; the volume is the work.

| # | Endpoint | Current source | New source |
|---|---|---|---|
| 1 | `GET /api/groups/filters` | distinct from `transactions` | distinct from `auto_group_analytics.regions`, `transacted_type_mix` keys, tier values |
| 2 | `GET /api/groups` (browse) | `groups + group_analytics` | `auto_groups + auto_group_analytics`, exclude `_anonymized_individuals` and `tier='merged'` |
| 3 | ~~`GET /api/groups/search`~~ | `groups_fts` | **Deferred to Phase E** — removed from this phase's scope |
| 4 | ~~`POST /api/groups` (create)~~ | inserts into `groups` | **Retired** — manual group creation goes through `auto_group_user_edits` 'create' edit (already exists via /api/auto-groups) |
| 5 | `GET /api/groups/{id}` | `groups + group_analytics` | Accept both ID forms; legacy `GRP_xxxxx` looks up via `legacy_to_auto_group_map` and serves the auto_group's response. Returned shape: `auto_groups` + `auto_group_analytics` + `constituent_legacy_groups` list + `engaged_contact_count` + `total_contact_count`. |
| 6 | ~~`POST /api/groups/{id}/promote`~~ | writes `groups.status` | **Retired** (HTTP 410 / removed) — engagement is per-contact, not per-group |
| 7 | ~~`POST /api/groups/{id}/engage`~~ | writes `groups.status` | **Retired** — same as #6 |
| 8 | `POST /api/groups/{id}/hq-address` | writes `groups.hq_address` | writes `auto_group_user_edits` set_address (existing flow on `/api/auto-groups/{id}/set-address`); the `/api/groups/...` form just dispatches to the auto-groups handler |
| 9 | `POST /api/groups/{id}/refresh-analytics` | calls `refresh_group_analytics` | calls `build_auto_group_analytics` scoped to one auto_group |
| 10 | `GET /api/groups/{id}/contacts` | `contacts WHERE current_group_id = ?` | `contacts WHERE current_auto_group_id = ?`. Adds `engagement_status` field per contact (pool/engaged) so the UI can show the badge inline. |
| 11 | `POST /api/groups/{id}/contacts` | inserts `group_contacts` | inserts `group_contacts` keyed on auto_group_id (schema change: see below) |
| 12 | `PATCH /api/groups/{id}/contacts/{cid}` | updates `group_contacts` | same w/ auto_group_id |
| 13 | `DELETE /api/groups/{id}/contacts/{cid}` | deletes `group_contacts` | same w/ auto_group_id |
| 14 | `GET /api/groups/{id}/attribution` | rollup over legacy group | rollup over auto_group's party-sides |
| 15 | `GET /api/groups/{id}/properties` (new) | — | Currently Owned: properties via `legacy_to_auto_group_map → properties.current_owner_group_id`. Paged. |
| 16 | `GET /api/groups/{id}/properties-sold` (new) | — | Sold-but-no-longer-owned: properties the auto_group transacted on as buyer where the current owner is now a different group. Paged. |
| 17 | `POST /api/contacts/{cid}/engage` (new, lives in contacts router) | — | Toggles `contacts.status` to engaged/pool. Used by Engage button on Group detail page. |

Schema migrations needed:
- `033_group_contacts_auto_group_id.py` — add `auto_group_id` column to `group_contacts`. CRM table has 0 rows; add column, no backfill.

### Wave 2 — Frontend: Groups list page

Update `GroupsPage.tsx` (~475 lines). Columns:

| Column | Source field |
|---|---|
| Name | `display_name` (title-cased) |
| Tier | `tier` badge (confirmed=jade, probable=gray, candidate=amber, standalone=neutral) |
| Members | `n_members` |
| Properties | `auto_group_analytics.transacted_property_count` |
| Transactions | `analytics.total_buys + analytics.total_sells` |
| Buy Value | `analytics.total_buys * analytics.avg_buy_price` |
| Primary Type | derived from `transacted_type_mix` |
| Secondary Type | derived from `transacted_type_mix` |
| Last Txn | `analytics.last_transaction_date` |

Filter sidebar:
- Tier (multi-select)
- Region (from analytics.regions)
- Asset class + min/max count (uses transacted_type_mix — same as contacts page)
- Min property count / min transaction count
- Search (display_name + canonical_stem LIKE)
- Drop legacy filters that don't apply: brand, status

Update `GroupBrowseItem` type in `frontend/src/types/index.ts`.

### Wave 3 — Frontend: Group Detail page

Rebuild `GroupDetailPage.tsx` (~712 lines). Layout:

```
┌── Header ──────────────────────────────────────────────┐
│ Chartwell Retirement Residences                        │
│ [probable] 159 members · 106 SPVs                      │
│ HQ: 100 Milverton Dr Suite 700, Mississauga · [Pick]   │
└────────────────────────────────────────────────────────┘

┌── Stats (5 cards) ─────────────────────────────────────┐
│ Properties: 47 · Transactions: 133 · Buy Value: $4.2B  │
│ Engaged Contacts: 2 of 12 · Last txn Apr 2, 2026       │
└────────────────────────────────────────────────────────┘

┌── Tabs: Properties / Sold / Contacts /                 │
│         Constituent SPVs / Activity                    │
└────────────────────────────────────────────────────────┘
```

Per tab:
- **Properties** (primary) — currently owned. `legacy_to_auto_group_map → properties.current_owner_group_id`. Sortable by city, asset class, last sale date, assessed value.
- **Sold** — historical sales. Properties where the auto_group's party-sides were buyer on a previous transaction but the current owner is different.
- **Contacts** — `WHERE current_auto_group_id = ?`. Each row shows the contact's engagement status badge (pool/engaged) inline with an "Engage" / "Mark Pool" toggle button.
- **Constituent SPVs** — `legacy_to_auto_group_map` rows. Each has detach button → existing `POST /api/auto-groups/{agid}/detach` endpoint
- **Activity** — `activities WHERE auto_group_id = ?` (after schema migration adds the column)

Reuse `HqPicker` component (already exists, built for the contact group card).

The header card adds an "Engaged Contacts" stat ("2 of 12") to make group-level engagement visible at a glance, since the user wants this surfaced.

### Wave 4 — Linkage fixes

1. **TransactionDetailPage** (`frontend/src/pages/TransactionDetailPage.tsx:95,138`) — party badges currently `navigate(\`/groups/\${p.group_id}\`)` with legacy IDs. After D1, that's fine (legacy IDs auto-resolve to auto_groups via the endpoint). Verify no visual break.
2. **CommandPalette** (`frontend/src/components/ui/CommandPalette.tsx:69`) — global search returns groups. Repoint the search backend to query `auto_groups`. Frontend code already navigates to `/groups/{id}`; just needs to receive `AGRP_xxxxx` results.
3. **ContactDetailPage** "View Group →" — already uses `auto_group_id`, becomes live the moment D1 ships.

### Wave 5 — Cleanup + docs

1. Update CLAUDE.md "Database: Derived vs CRM Tables" section to clarify that the auto_group_analytics / auto_groups / auto_group_members / legacy_to_auto_group_map tables are managed by discovery_v2 and not by the compiler.
2. Update `docs/definitions.md` — clarify "Group" now refers to auto_groups in the UI; legacy `groups` table is a compiler-managed canonicalization artifact that auto_groups roll up over.
3. Add note to "How to Add an API Route" — Groups subroutes should accept both ID forms via the helper.
4. Remove or comment-out the create-legacy-group endpoint if it's unused.

## Risk register

| Risk | Mitigation |
|---|---|
| auto_group AGRP_NNNNN numbering not stable across rebuilds | Document. Phase F to introduce stable IDs from canonical_stem hashing. |
| `legacy_to_auto_group_map` can lose a legacy_group_id between rebuilds (different clustering decision) | Detail handler 404s gracefully; legacy-ID lookup falls back to direct `groups` query when no mapping exists. |
| `groups.hq_address` (legacy) had user edits we'd lose | None observed in DB. If any exist, one-off migration script copies them into `auto_group_user_edits` set_address before cutover. |
| Performance: 105k auto_groups × analytics joins | Same magnitude as legacy. Indices on auto_group_analytics PK + tier + property_count cover the queries. |
| FTS for auto_groups doesn't exist (legacy had groups_fts) | Search uses LIKE on display_name + canonical_stem — adequate at this scale (114k rows). FTS table is Phase E if perf demands it. |

## Test plan

1. **Browse**: `/api/groups?per_page=20` returns 20 auto_groups, biggest first; no `_anonymized_individuals` or `merged` rows.
2. **Detail (auto)**: `/api/groups/AGRP_00234` returns Chartwell + 106 constituent SPVs + 47 current-owned + 79 transacted-in.
3. **Detail (legacy)**: `/api/groups/GRP_05646` (DVS Farms) resolves to `AGRP_05981`.
4. **Filter**: `asset_class=multifamily&min=20` includes Chartwell, Starlight, Skyline, Marlin Spring, Boardwalk.
5. **Contacts subroute**: `/api/groups/AGRP_00234/contacts` returns Boulakia and the other Chartwell signers.
6. **Frontend nav**:
   - Click "View Group →" on Jonathan Boulakia → Chartwell detail page loads with all tabs populated
   - Click party badge on RT198242 → DVS Farms auto_group page loads (not a 404)
   - CommandPalette search "Chartwell" → returns the auto_group
7. **HQ pick**: edit HQ from the Group detail page → writes auto_group_user_edits → survives discovery_v2 rebuild.

## Effort estimate

| Wave | Hours |
|---|---|
| 1 — Backend repoint (10 endpoints retained + 3 new + 1 migration; 4 retired) | ~3.0 |
| 2 — Frontend list page | ~1.5 |
| 3 — Frontend detail page + 5 tabs + engagement toggle | ~3.5 |
| 4 — Linkage fixes (TransactionDetail party badges only; search → Phase E) | ~0.5 |
| 5 — Docs + cleanup | ~1.0 |
| Testing | ~1.0 |
| **Total** | **~10–11 hours** |

## Open decisions before kickoff

All four open decisions resolved 2026-05-13 — captured in the "User decisions" section above:
1. ✅ Promote/Engage retired; engagement is per-contact with group-level rollup
2. ✅ Properties (primary) + Sold (secondary); "Transacted In" disappears from UI
3. ✅ No legacy mixing; no hq_address migration; orphans die
4. ✅ CommandPalette → Phase E
