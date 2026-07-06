# Cleo Turbo — Product Map & Data Audit

Written 2026-07-06. Every claim below was verified against the code and a
read-only snapshot of `data/cleo.db` taken the same day (copied to /tmp and
queried there; the live DB was never written). Audit SQL is included so any
future session can recompute. Read `CLAUDE.md` first — this document maps the
product to its goal; CLAUDE.md holds the working rules.

## 1. The goal and the operating loop

**End goal: every commercial parcel in Ontario tied to its true beneficial
owner, kept current, so Brandon can prospect owners two-sided — as sellers
(inventory) and buyers (mandates).**

Inventory is the constraint in Brandon's brokerage (retail/industrial
investment, $4M+). The prospecting loop the product serves
(`docs/workflows.md`):

1. **Prospect** — find who owns a target parcel or portfolio. Ownership is
   deliberately obscured in Ontario: registered owners are often numbered
   companies and SPVs, one per property.
2. **Enrich** — roll SPVs up to the real group, attach people, phones,
   mailing addresses, portfolio stats.
3. **Outreach** — contact the decision-maker, two-sided: "would you sell
   this?" and "you buy assets like this — I have one."

Everything in the repo is one of three things: a **channel** feeding raw
ownership evidence in (Section 2), an **identity pipeline** turning party
strings into beneficial owners (Section 3), or a **UI surface** for running
the loop (Section 4). A parcel with no owner name and no owner group is
"dark" — the enemy. Today 75% of properties are dark (Section 5), which is
why the Portfolio Capture channel exists.

## 2. Data channels in

### 2.1 Realtrack transactions — `engines/rt/`

The backbone. Ontario commercial sale transactions scraped from Realtrack:
parties (buyer/seller names, trade names, care-of, companies), mailing
addresses, brokers, prices, mortgages. Pipeline stages: extract → dedup →
classify → normalize → resolve_v2 (parcel resolution) → compile, orchestrated
by `engines/rt/process.py`. A daily scraper
(`engines/rt/scraper/daily_scraper.py`, cron-friendly) plus a watcher
(`engines/rt/watcher.py`) keep it current. Serves the goal by providing
*owner-change events*: who bought means who owns now, and buyer mailing
addresses/phones are the raw material for SPV clustering.

Snapshot: 124,544 transactions, sale dates 1996-01-10 → 2026-04-02. Latest
compiled row `created_at` 2026-06-24; newest raw scrape batch in
`raw-data/rt/pages/_daily/` is 2026-06-19. **The feed has not run in ~2.5
weeks — verify the cron is alive.**

### 2.2 GeoWarehouse parcels — `engines/gw/` + watcher + extension

Parcel-level registry truth: who owns a PIN/ARN *now* (often the SPV name),
assessment values, sales history. Ingested per-report: the Chrome extension
`extensions/cleo-geowarehouse/` auto-saves rendered GW report HTML, the
watcher (`python -m engines.gw.watcher`) parses and applies **incremental DB
updates that bypass the full compiler — intentional, don't refactor**
(CLAUDE.md). Writes `gw_assessments` / `gw_sales_history` and property rows.
Serves the goal as the registry-confirmed anchor: capture links marked
`registry_confirmed` outrank web assertions.

Snapshot: only 862 gw_assessments rows across 773 distinct ARNs (749 match a
properties row). This channel is manual/on-demand today — coverage is a
rounding error against 85,001 properties.

### 2.3 POIs / brands — `engines/osm/`, `pois` + `brand_registry` tables

50,778 branded points of interest (all `source='osm'`) resolved to parcels
via `engines/osm/resolve_pois_v2.py`. Serves the goal as the *targeting
layer*: "every Metro-anchored plaza in Hamilton" is a POI query joined to
properties, and the dark ones are the prospecting list. `brand_registry`,
`brand_overrides`, `user_brand_favorites` back the Brands UI
(`cleo/web/routes/brands.py`). Note: the `brand_token_index` /
`brand_*gram_*` tables are NOT from POIs — they are party-name atoms from
Realtrack (Section 3).

Known defect: 631 Shoppers Drug Mart POIs sit in `category='Grocery'`
(Section 8). 29,753 POIs (59%) have an empty category.

### 2.4 Portfolio Capture — web-asserted ownership

The newest channel and the main dark-parcel weapon: owners' own websites
assert "we own these properties." One validated door:
`POST /api/portfolio/capture` (`cleo/web/routes/portfolio.py`, logic in
`cleo/compiler/portfolio_capture.py`, spec in
`Portfolio-Capture-Cowork-Integration-Plan.docx`, runbook in
`docs/portfolio-capture.md`). Payload = group profile + aliases + match keys
+ contacts + property links (ARN-keyed). Writes only to persistent CRM-layer
tables: `group_profile`, `group_aliases`, `group_match_keys`,
`manual_owner_links`, `manual_properties`. `dry_run=true` is the default
(full write + diff + rollback). A match-key sweep (M4) then hunts
`transaction_mailing_addresses` / `party_fingerprints` / `gw_assessments`
for the group's office address or SPV names and attaches more parcels.

State: endpoint built and pilot-tested (Biddington, on /tmp DB copies only —
`scripts/pilot_biddington.py`, `scripts/test_portfolio_capture_m*.py`). All
three capture tables are **0 rows on the real DB**. 21 scraped portfolios
(RioCan, SmartCentres, Crombie, Strongman, Biddington, etc.) are staged as
JSON in OneDrive `00_Prospecting/Portfolio Capture/raw-scrapes/` awaiting
conversion to capture payloads.

### 2.5 HubSpot — NOT integrated

Verified: the only HubSpot artifacts are `hubspot_id TEXT` columns on
contacts/groups (`cleo/database/schema.py` lines 125, 141, 417, 520), carried
through `group_field_overrides` in `cleo/compiler/writer.py`, and surfaced on
`ContactDetailPage.tsx`. There is no HubSpot API client anywhere in the repo.
It's an ID cross-reference field, nothing more.

### 2.6 Other channels found

- **Canada411** — `engines/c411/` contains only 3 sample HTML files
  (profile page, reverse-address form/results). No code. A future
  contact-enrichment engine, unstarted.
- **Datanyze** — one-off contact CSV at repo root
  (`Datanyze Contacts - All Contacts - 04_08.csv`); migration
  `004_datanyze_raw_column.py` added a raw column for it.
- **LinkedIn extension** — `extensions/cleo-linkedin/` exists. OPEN
  QUESTION: what it captures and where it lands was not verified this pass.

## 3. The identity pipeline: raw party names → owners

This is the heart of the product. Three generations of identity coexist:

**Legacy groups (`GRP_`)** — the compiler's reconciler
(`cleo/compiler/reconciler.py`) assigns one `GRP_NNNNN` per normalized
company name (UPPERCASE, legal suffixes stripped), stable across rebuilds via
`app_meta`. Result: one group per SPV spelling — 136,266 groups, i.e. massive
fragmentation. All have `status='pool'`; the legacy status lifecycle is
retired (engagement is per-contact now, per `cleo/web/routes/groups.py`
docstring).

**Atoms** — `cleo/atoms/normalize.py` (pure canonicalizers: brand, contact
name, phone, address parts, ARN) and `cleo/atoms/fingerprint.py`, run as the
compiler's final pass. Every transaction party-side becomes one
`party_fingerprints` row (normalized mailing address, phone, contact
fingerprint) plus `party_atoms` rows (brand phrases/tokens extracted from
ALL FOUR identifier fields: `party_name`, `trade_name`, `care_of`,
`companies_json` — never just party_name; law firms are kept separate).

**Auto-groups (`AGRP_`)** — `cleo/discovery_v2/` clusters party-sides into
beneficial-owner groups using brand n-gram indexes, shared phones, shared
mailing addresses, contacts, and anchor scoring
(`seeding.py`, `expansion.py`, `conflicts.py`, `auto_groups.py`). Tiers on
`auto_groups.tier`: `confirmed` / `probable` / `candidate` /
`standalone` / `merged` (migration 026). `standalone_coverage.py` guarantees
every party-side lands in *some* auto_group (single-member standalones fill
the gaps — hence 115,747 of 118,192 are standalone). Stage A8
(`legacy_map.py`) builds `legacy_to_auto_group_map`: every legacy GRP_ maps
to its dominant AGRP_. Stage A10 (`group_analytics.py`) rolls legacy
`group_analytics` up into `auto_group_analytics`. Stage Z
(`apply_user_edits.py`) replays human edits (`auto_group_user_edits`:
detach/attach/rename/merge/create, written by
`cleo/web/routes/auto_groups.py`) on every rebuild so they survive forever.

**Human overlays** — `group_merges` (legacy-group merges, chain-followed),
`group_field_overrides` / `group_overrides`, `labeling_*` tables (party-link
labeling verdicts, `cleo/web/routes/labeling.py`), and the Portfolio Capture
layer: `manual_owner_links` + `manual_properties` + `group_match_keys`.

**The reconciler** — `cleo/compiler/owner_overrides.py::apply_owner_overrides`
materializes `manual_owner_links` onto `properties`. Policy (verified in
code): `owns` links fill **dark** properties (`transaction_count == 0`) —
GW-only parcels count as dark even when GW carries a registry SPV name, and
the registry *name* is preserved (only `current_owner_group_id` is set). If a
property has a Realtrack-derived owner that differs, the link is flagged
`status='conflict'` + a `data_issues` row — **never overwritten**. Runs as
the compiler's final pass (`cleo/compiler/writer.py:1307`) and incrementally
(scoped to ARNs) on capture commit. Merges pointed at since-merged groups
follow the `group_merges` redirect chain.

### Flow diagram

```
RT party strings                     GW registry owner        Owner websites
(party_name, trade_name,             (per-parcel SPV name)    (asserted portfolios)
 care_of, companies_json)                   |                        |
        |                                   |                        v
        v                                   |             POST /api/portfolio/capture
compiler reconciler ---------------> properties.current_owner_name   |
  GRP_ per normalized name                  ^                        v
  (groups, 136k, fragmented)                |             manual_owner_links (CRM,
        |                                   |              survives rebuilds)
        v                                   |              + group_match_keys sweep
cleo/atoms fingerprint pass                 |                        |
  party_fingerprints + party_atoms          |                        v
        |                                   |          apply_owner_overrides
        v                                   |          (cleo/compiler/owner_overrides.py)
cleo/discovery_v2                           |            - dark parcel -> FILL group id
  brand/phone/address/contact silos         +----------  - RT owner differs -> CONFLICT,
  -> auto_groups (AGRP_, tiered)            |             never overwrite
  -> legacy_to_auto_group_map               v
  -> auto_group_analytics          properties.current_owner_group_id
  -> apply_user_edits (Stage Z              |
     replays human edits)                   v
        ^                          UI: Groups / Properties / Map
        |                          (Groups routes resolve GRP_ -> AGRP_
auto_group_user_edits (human:       via legacy_to_auto_group_map)
detach/attach/rename/merge/create)
```

## 4. What each UI page reads

Router: `frontend/src/App.tsx`. Backend routes register in `cleo/web/app.py`.

| Page (frontend/src/pages/) | API route file | Reads |
|---|---|---|
| DashboardPage | properties.py `/properties/stats` | properties aggregates |
| PropertiesPage / PropertyDetailPage | properties.py | properties, transactions, transaction_parties, transaction_mailing_addresses, gw_assessments, gw_sales_history, pois, group_analytics, contacts |
| TransactionsPage / TransactionDetailPage | transactions.py | transactions, transaction_parties, transaction_mailing_addresses, transaction_brokers, transaction_broker_agents (+ raw RT HTML from raw-data/rt/pages) |
| ContactsPage / ContactDetailPage | contacts.py | contacts, auto_groups + auto_group_analytics (via contacts.current_auto_group_id), contact_brand_tenures, contact_work_history, contact_field_overrides, party_fingerprints/party_atoms, group_contacts |
| GroupsPage (browse) | groups.py | **auto_groups + auto_group_analytics** (Phase D cutover; legacy GRP_ ids dispatched through legacy_to_auto_group_map) |
| GroupDetailPage → Properties tab | groups.py `/{id}/properties` | transactions via auto_group_members **UNION captured ownership**: properties whose current_owner_group_id maps to this auto_group + off-book manual_properties via manual_owner_links (`relationship='owns'`, non-conflict). Added in commit a8ba7c9c2 (2026-07-06). Captured rows show `last_side='owner'`, n_transactions=0 |
| GroupComparePage | groups.py | auto_group_analytics side-by-side |
| MapPage | geo.py | properties + pois as GeoJSON (Mapbox GL) |
| ListsPage / ListDetailPage | lists.py | lists, list_members (+ joins to properties/contacts/groups/transactions), scope personal/shared |
| DealsPage / DealDetailPage | deals.py | deals (+ properties, groups) |
| OpportunitiesPage (+ sell/buy detail) | sell_opportunities.py, buy_mandates.py | sell_opportunities, buy_mandates (CRM) |
| PipelineOverviewPage / Stage / Record / Trace | pipeline.py | **no DB** — reads engine files live from raw-data/ and clean-data/ on disk |
| DataQualityPage | data_quality.py | data_issues (+ transactions/properties context) |
| DiscoveryPage / DiscoveryClusterPage | discovery.py | discovery_runs, discovery_evidence, discovery_ground_truth, discovery_exclusions (v1 engine — superseded by discovery_v2/Explorer) |
| Explorer* (brands 1–5gram/long-form, phones, addresses, contacts, auto-groups, conflicts) | explorer.py | brand_*_index/summary, phone_summary, address_root/base/unit_summary, contact_fingerprint_summary, party_atoms, party_fingerprints, auto_groups, auto_group_members, auto_group_anchors, auto_conflict_flags, places, industry_stopwords |
| IssuesPage / IssueDetailPage | issues.py | issues (in-app bug/data tracker, migration 036; entity-anchored, 11 categories) |
| LabelingPage / Session / Audit | labeling.py | labeling_sessions, labeling_verdicts, labeling_links, labeling_seeds |
| QueuePage | activities.py | daily outreach queue (migration 020_crm_daily_outreach) |
| AdminPage / AuditLogPage / SettingsPage / TestLabPage | admin.py, audit.py, test_lab.py | users, audit_log, misc |

There is **no Capture Portfolio UI page yet** — the endpoint exists but the
review UI (build-plan Milestone 3) does not (Section 8).

## 5. Data audit — real DB snapshot, 2026-07-06

Method: `cp data/cleo.db /tmp/cleo_audit/` (WAL was already checkpointed;
0-byte -wal) and query the copy. Live DB never opened for write.

| Metric | Value | SQL used |
|---|---|---|
| Properties total | **85,001** | `SELECT COUNT(*) FROM properties` |
| … with current_owner_group_id | **19,978** (23.5%) | `…WHERE current_owner_group_id IS NOT NULL` |
| … dark (no owner name AND no group) | **63,772** (75.0%) | `…WHERE (current_owner_name IS NULL OR TRIM(current_owner_name)='') AND current_owner_group_id IS NULL` |
| Transactions | **124,544**, sale_date 1996-01-10 → 2026-04-02 | `SELECT COUNT(*), MIN(sale_date), MAX(sale_date) FROM transactions` |
| … newest compiled row | 2026-06-24 | `SELECT MAX(created_at) FROM transactions` |
| Contacts | **83,806** | `SELECT COUNT(*) FROM contacts` |
| Groups (legacy) by status | **136,266**, all `pool` | `SELECT status, COUNT(*) FROM groups GROUP BY status` |
| Auto_groups by tier | **118,192**: standalone 115,747 · probable 1,597 · candidate 666 · confirmed 182 · merged 0 | `SELECT tier, COUNT(*) FROM auto_groups GROUP BY tier` |
| legacy_to_auto_group_map | **136,266** (= every legacy group mapped) | `SELECT COUNT(*) FROM legacy_to_auto_group_map` |
| POIs total | **50,778** (all source=osm) | `SELECT source, COUNT(*) FROM pois GROUP BY source` |
| POIs by category | (blank) 29,753 · QSR 4,808 · Take-out 3,181 · Fuel 2,722 · Financial Services 2,567 · Specialty Retail 2,041 · Grocery 1,793 · Big-Box 1,314 · Discount 957 · Full-Service 891 · Automotive 751 | `SELECT category, COUNT(*) FROM pois GROUP BY category ORDER BY 2 DESC` |
| Shoppers miscategorized as Grocery | **631** | `SELECT COUNT(*) FROM pois WHERE category='Grocery' AND (brand LIKE 'Shoppers%' OR name LIKE 'Shoppers%')` |
| gw_assessments | **862** rows · 773 distinct ARNs · 749 match a property | `SELECT COUNT(*)…; COUNT(DISTINCT arn)…; SELECT COUNT(*) FROM properties WHERE arn IN (SELECT arn FROM gw_assessments)` |
| manual_owner_links / manual_properties / group_match_keys | **0 / 0 / 0** (capture layer pilot-only, real DB untouched) | `SELECT COUNT(*) FROM …` each |
| group_merges (active) / auto_group_user_edits / issues | 0 / 4 / 5 | `SELECT COUNT(*) FROM …` |
| app_meta counters | next_pro_id 85041 · next_con_id 83884 · next_grp_id 136267 · discovery_engine='legacy' | `SELECT key, value FROM app_meta` |

### Grocery POI dark rate — recomputed

Denominator confirmed: **1,162** Grocery POIs excluding Shoppers
(`SELECT COUNT(*) FROM pois WHERE category='Grocery' AND brand NOT LIKE
'Shoppers%' AND (name IS NULL OR name NOT LIKE 'Shoppers%')` = 1,793 − 631).
Of those, 1,152 resolve to a property (10 unresolved), and **835 sit on dark
parcels** (owner name empty AND no owner group; join `pois.property_id =
properties.id`) — **71.9% dark**. The previously quoted **681/1,162 does not
reproduce** on today's DB. Nearby variants: 804 distinct dark *properties*,
916 POIs with no owner group, 735 on zero-transaction parcels. OPEN QUESTION:
the 681 figure's exact definition (likely an older DB state or a
distinct-address count from the prospecting workbook). Use 835/1,162 going
forward, or pin the definition.

## 6. Invariants — never break these

1. **Derived vs CRM table split** (CLAUDE.md "Critical Rules"). The compiler
   `drop_derived_tables()` rebuilds derived tables only; CRM tables
   (deals, lists, manual_owner_links, group_profile, labeling_*, issues, …)
   are never truncated. Captured ownership must survive a full rebuild —
   `apply_owner_overrides` re-applies it as the writer's final pass
   (`cleo/compiler/writer.py:1307`).
2. **Base parcel fields are immutable by labeling.** Labeling verdicts write
   only to `labeling_*` tables; nothing in `cleo/web/routes/labeling.py`
   touches `properties`. Human judgment layers on top; source data stays
   source data.
3. **Realtrack-derived owners are never overwritten** by web-captured links.
   Conflicts land as `manual_owner_links.status='conflict'` + a `data_issues`
   row (rule `manual_owner_conflict`) for review
   (`cleo/compiler/owner_overrides.py`).
4. **ARNs come only from the engine normalizers** — `engines/rt/
   address_normalizer/pin_arn.py` / `engines/gw` format_arn. Spec D5:
   `cleo/atoms/normalize.py::normalize_arn` delegates, never reimplements.
   Invalid ARNs are skipped with a warning, never "fixed" by hand.
5. **Merges are human-approved only.** Capture proposes `merge_candidates`;
   they execute only on explicit commit with `apply_merges=true` (spec D4,
   `cleo/web/routes/portfolio.py`). Auto_group merges likewise go through
   the user-edit endpoints and are replayed by Stage Z.
6. **dry_run defaults to true** on `/api/portfolio/capture` — full write
   order runs, diff returns, everything rolls back.
7. **Stable ID counters (PRO_/CON_/GRP_ in app_meta) are never reset**, and
   fingerprint/normalization functions are never changed casually — doing so
   forks IDs.
8. **No targeted parcel-resolution fixes** — all resolution goes through
   `cleo/resolver/`; fixes belong in `chain.py`, not in engines.
9. **The GW watcher's compiler bypass is intentional**; don't refactor it.
10. **No CLI for user-facing features**; fixed ports (backend 8099, frontend
    5174). Preserve every source field — NULL means "source said nothing,"
    a missing column means "we never looked."

## 7. Migration / version state

There is **no migration runner and no schema_migrations/version table** —
verified: `sqlite_master` contains no migration/version table, `app_meta`
holds only ID counters and `discovery_engine`. Migrations live in
`cleo/database/migrations/001…036` and are run **per-file**, each with its
own `if __name__ == "__main__"` block connecting to `data/cleo.db`
(e.g. `.venv/bin/python cleo/database/migrations/036_issues_tracker.py`).
`cleo/migrations/` (different directory) holds only a one-off ID-mapping
backfill.

The real DB is current **through 036** (issues tracker, applied 2026-07-06 —
the `issues` table exists with 5 rows). Portfolio Capture tables came via
`cleo/database/schema.py` + `scripts/migrate_portfolio_capture.py`, plus a
runtime guard `ensure_capture_columns()` that adds
`group_match_keys.sweepable` on older DBs.

**How to check whether migration N is applied:** each migration creates or
alters a specific table — probe `sqlite_master` / `pragma_table_info` for its
artifact (036 → `issues`; 027 → `legacy_to_auto_group_map`; 031/035 →
`auto_group_analytics` columns). There is no ledger; the schema itself is
the ledger.

## 8. Open decisions & known gaps for rollout

1. **Capture doesn't fill NULL `display_address` on dark parcels.**
   `apply_owner_overrides` sets only `current_owner_group_id` /
   `current_owner_name`; the payload's `display_address`/`city` land in
   `manual_properties` stubs but are never copied onto an existing
   `properties` row with a blank address. Captured holdings can therefore
   show as address-less rows in the UI.
2. **Group analytics tiles don't reflect captured holdings promptly.**
   `group_analytics` (`cleo/analytics/groups.py`, refreshed on demand) and
   its Stage A10 rollup `auto_group_analytics` do count
   `current_owner_group_id`-owned properties — but nothing triggers a
   refresh on capture commit, and the header tile on GroupDetailPage reads
   the stale analytics row. The Properties tab (transactions UNION captured)
   is correct; the tile lags until the next analytics/discovery rebuild.
3. **No review/detach UI for capture.** `status='conflict'` and `'pending'`
   manual_owner_links are only visible via data_issues; build-plan
   Milestones 2–3 (crawl endpoint + Capture Portfolio review page) are
   unbuilt. Everything goes through the API today.
4. **Leasing-page relationship policy undecided.** `relationship in
   ('manages','lists')` links are recorded but never affect ownership
   (`owner_overrides` skips them). Whether a leasing page implies
   owns-vs-manages, and how staged 'lists' relationships surface, is open —
   the Biddington acceptance case was exactly this judgment.
5. **21 scraped portfolios awaiting payloads.** JSONs in OneDrive
   `00_Prospecting/Portfolio Capture/raw-scrapes/` (+ consolidated CSV dated
   2026-07-06, ~987 rows) need conversion to capture payloads, dry-run
   diffs, and committed captures. This is the single highest-leverage
   dark-parcel fill available.
6. **Shoppers category fix.** 631 Shoppers Drug Mart POIs are
   `category='Grocery'`; they poison grocery-anchored prospecting queries.
   Fix belongs in the OSM brand/category mapping (`engines/osm/brands.csv` /
   `brand_aliases.json`) or `brand_overrides` — decide which, then re-run.
7. **RT feed freshness.** No new raw scrapes since 2026-06-19; max sale_date
   2026-04-02. Confirm the cron entries in CLAUDE.md are actually installed
   and running.
8. **`app_meta.discovery_engine='legacy'`** while Groups routes are already
   cut over to auto_groups (Phase D). OPEN QUESTION: what still reads this
   flag and whether it should say `v2`.
9. **GW coverage is 862 parcels.** Scaling registry confirmation (bulk GW
   pulls, municipal ARN feeds — see `Ontario_Municipal_GIS_Research.docx`)
   is an open acquisition question.
10. **59% of POIs have no category**; `groups.status` is vestigial (all
    'pool'); `engines/c411` and the LinkedIn extension are unbuilt/unverified
    enrichment channels; HubSpot is an ID column, not a sync.
