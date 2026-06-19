# Cleo Turbo — Architecture Deep Dive (Verified)

> Produced by reading the actual code (June 2026), not by trusting prior docs. Where this
> document and `CLAUDE.md`/`docs/*` disagree, **this document reflects what the code does.**
> A consolidated list of doc-vs-code drift is in [§10](#10-code-vs-docs-discrepancies).
> File references use `path:line` relative to the repo root.

## 1. What the system is

Cleo Turbo is a commercial-real-estate prospecting platform for Ontario. It ingests three
sources — Realtrack transactions (RT), GeoWarehouse parcel/ownership (GW), and OpenStreetMap
branded POIs (OSM) — normalizes and parcel-resolves them, compiles everything into a single
SQLite database (`data/cleo.db`), and serves a FastAPI backend to a React/Vite frontend. On top
of the raw data sits an **identity stack** that clusters transaction parties into branded
"groups" (the portfolio-owner view that is the product's reason to exist).

The **ARN (20-digit Assessment Roll Number)** is the backbone: RT transactions, GW detail pages,
and parcel geometry all join on it. Properties are one-per-ARN.

## 2. Repo layout (corrected)

```
cleo-turbo/
├── cleo/                      # Python backend + data logic
│   ├── web/                   # FastAPI app, auth, 31 routers (§7)
│   ├── database/              # connection.py, schema.py, migrations/001..036_*.py (§6)
│   ├── compiler/              # reader → reconciler → writer (6-pass) → cleo.db (§3.4)
│   ├── resolver/              # unified parcel resolver (§4) — USED BY RT ONLY
│   ├── address/               # shared address formatter (display strings)
│   ├── atoms/                 # party-side atomization + fingerprints (feeds identity)
│   ├── identity/              # n-gram extract + AI HQ enrichment
│   ├── analytics/             # legacy group analytics (group_analytics table)
│   ├── discovery/             # v1 rule-based clustering (DISC_, still mounted)
│   ├── discovery_v2/          # v2 anchor/stem auto-group discovery (~5,300 LOC, AGRP_)
│   ├── labeling/              # human party-link ground-truth labeling
│   ├── cli/                   # issues.py dev CLI
│   └── migrations/            # one-time DATA backfills (≠ database/migrations schema files)
├── engines/
│   ├── rt/                    # Realtrack: scrape→assemble→dedup→classify→normalize→resolve→compile
│   ├── gw/                    # GeoWarehouse: ingest→parse→normalize→resolve→compile
│   └── osm/                   # OSM POI import + in-place resolution
├── frontend/                  # Vite + React 19 + TS (§8)
├── rebuild.py                 # the REAL DB compiler entrypoint (admin UI calls this)
├── data/cleo.db               # compiled SQLite (gitignored)
├── clean-data/{rt,gw,osm,parcels}/   # per-record JSON + parcel cache (gitignored)
└── raw-data/{rt,gw,osm}/      # source HTML/JSON (gitignored)
```

> CLAUDE.md's `cleo/` tree lists only `web/compiler/database/resolver` and omits the seven
> identity-stack packages — which are collectively the largest body of logic in the repo.

## 3. The data pipeline

Three engines each write per-record JSON into `clean-data/<source>/`, then the compiler turns
all of `clean-data/` into `cleo.db`. **Naming trap:** `engines/rt/compile.py` and
`engines/gw/compile.py` write *clean-data JSON* (per-record). The *SQLite* compiler is
`cleo/compiler/writer.py`, invoked by `rebuild.py`. They are different things.

### 3.1 RT (Realtrack) — `engines/rt/`

Pipeline dirs live under `engines/rt/pipeline/`. Stages (orchestrated by `process.py`):

| Stage | Script | In → Out |
|---|---|---|
| scrape | `scraper/daily_scraper.py` | Realtrack web → `raw-data/rt/pages/_daily/...` |
| extract+assemble | `run_pipeline.py` + `assembler.py` | `raw-data/rt/pages/...` → `pipeline/extracted/`, `pipeline/assembled/` |
| dedup | `dedup.py` | `assembled/` → `deduped/` (best file per RT ID) |
| classify | `run_classifier.py` | `deduped/` → `classified/` |
| normalize | `address_normalizer/run.py` | `classified/` → `addresses/` |
| resolve | `parcel_resolver/resolve_v2.py` | `addresses/` → `parcel_links/` |
| compile | `compile.py` | `classified/` ∩ `addresses/` (+`parcel_links/`) → `clean-data/rt/{RT_ID}.json` |

- `run_pipeline.process_folder` (`engines/rt/run_pipeline.py:52`) joins detail+export+results
  **by position**, with an address/price/date cross-check and an address-based fallback
  (`assembler.find_matching_export`, `assembler.py:118`). Position joins are a fragility point.
- `building_size.py` parses the free-text `bldg` field into value/unit (the "you cannot sum
  across units" rule lives here).
- **Orchestrator** `process.py`: `--new` runs every stage incrementally (pending = input files
  with no output counterpart; nothing overwritten). `--from <stage>` reprocesses everything from
  a stage onward, tracked by a resume marker `pipeline/_reprocess.json`; `--skip resolve` keeps
  parcel links. `--reprocess <RT_IDS>` does targeted per-record reprocessing.
- **Watcher** `watcher.py` just shells `process.py --new`; `resolve` self-skips when its lockfile
  (`pipeline/parcel_links/.resolve_v2.lock`) holds a live PID, so new files queue safely.
- **Daily scraper "one search = all" — confirmed in code.** `_make_search_params`
  (`scraper/daily_scraper.py:119`) sets `sf1=""` (all regions) + `sf3=""` (all types) sorted by
  date desc; `verify_completeness` (`:328`) re-runs per-category searches and asserts the "All"
  total ≥ sum of categories.

### 3.2 GW (GeoWarehouse) — `engines/gw/`

`ingest.py` (copies `geowarehouse-*.html` from `~/Downloads/...`) → `parse.py` →
`normalize.py` → `resolve_parcels.py` → `compile.py` → `clean-data/gw/{GW_ID}.json`. Dedup is by
**PIN**. GW data is parcel-level (who owns it now), not transactional. The **GW watcher does
incremental DB updates that bypass the compiler** (intentional per CLAUDE.md) — a second write
path into `gw_assessments`/properties, which is a consistency risk to keep in mind.

### 3.3 OSM — `engines/osm/`

`fetch.py` (Overpass) → `process.py` (enrich with `brands.csv` + `brand_aliases.json`, building
geometry, approx sqft) → `clean-data/osm/{OSM_ID}.json` → `resolve_pois_v2.py` resolves **in
place** (writes ARN/parcel fields back into the same POI file).

### 3.4 Compiler — `cleo/compiler/` (run via `rebuild.py`)

`writer.run_compiler` is **6 passes** (CLAUDE.md says 3): (1) groups, (2) contacts,
(3) properties + transactions + parties + mailing addresses + brokers, (4) POIs, (5) GW
assessments + sales history, (6) PIN→ARN orphan-transaction linking. Then it rebuilds FTS5
tables, builds `brand_registry`, runs the atoms fingerprint pass
(`cleo/atoms/fingerprint.run_fingerprint_pass`, `writer.py:1355`), refreshes group analytics, and
writes `data/reconciliation_report.json`.

`drop_derived_tables()` (`schema.py:912`) drops only the derived set (§6) plus the 4 FTS tables;
CRM and system tables are never touched. FK enforcement is disabled during the load and
re-enabled at the end.

**Stable IDs** (`compiler/reconciler.py`): `PRO_` per ARN, `CON_` per name fingerprint
(UPPERCASE first+last, honorifics stripped), `GRP_` per normalized company name. **Correction:**
the anchor→ID maps live in the `id_mappings` *system* table (`reconciler.py:103-141`), **not**
`app_meta` — `app_meta` only stores the next-id counters. `id_mappings` must survive derived-table
drops or every CRM foreign key breaks; it is missing from CLAUDE.md's table lists.

## 4. The parcel resolver — `cleo/resolver/`

A 6-step chain (`chain.py:79 resolve()`): (1) PIN→ARN bridge (local GW lookup, mutates
`input.arn`), (2) ARN lookup (cache → AgMaps API), (3) address geocoding (Ontario geocoder, all
variants, skips Postal matches), (4) coordinate PIP (OSM rooftop coords), (5) cross-validation
decision (`_decide`), (6) local PIP verification (±0.05 confidence, never overturns the decision).
Methods and confidences match CLAUDE.md exactly (`types.py:190-218`): verified 0.95,
spatial_consensus/spatial_coords 0.90, spatial_geocode 0.85, spatial_override 0.80, arn_only 0.50,
pin_bridge 0.40. A >500 m haversine sanity check can discard an ARN-only result (`chain.py:398`).

External clients: **AgMaps** (ArcGIS parcel MapServer; ARN + spatial-point queries; 0.4 s
throttle) and the **Ontario geocoder**, which is **Playwright browser automation** that runs the
geocode `fetch` inside the page and captures the AgMaps token from network traffic. Throttle =
hard stop (3 consecutive errors or >=10% error rate -> `ThrottleError`, resolve_v2 aborts).

> **Major correction:** "ALL parcel resolution goes through `cleo/resolver/`" is true for **RT
> only**. GW (`engines/gw/resolve_parcels.py`) and OSM (`engines/osm/resolve_pois_v2.py`) call
> `agmaps`/`ontario_geocoder` directly and never import `cleo.resolver`. `engines/gw/adapter.py`
> and `engines/osm/adapter.py` exist but have **zero importers** (dead code). So the confidence /
> cross-validation / PIP-verify machinery only runs for RT; GW is ARN-cache->API only. The
> "no targeted fixes, fix it in chain.py" policy does not actually cover GW/OSM.
> Also note the `ParcelGrid` spatial index in `pip.py` is **not called** by the live chain —
> step 6 does a direct expected-parcel test only.

## 5. The identity stack (groups)

This is the product's core IP and is almost entirely absent from CLAUDE.md.

- **`cleo/atoms/`** — `fingerprint.run_fingerprint_pass` rebuilds `party_fingerprints` +
  `party_atoms` from transactions/parties. This is the canonical implementation of the
  "branded identifier lives in 4 fields" rule (§9). Runs as the final compiler pass.
- **`cleo/discovery_v2/`** (~5,300 LOC, the active system) — `python -m cleo.discovery_v2`:
  Layer 1 builds brand n-gram / phone / address inverted indexes; Layer 2 (`build_auto_groups`,
  stages A1–A10 + Stage Z) clusters parties into **`auto_groups` (AGRP_ ids)** by
  shortest-distinctive-stem + anchor convergence, detects contact tenures, flags conflicts,
  guarantees standalone coverage, picks HQ addresses, replays CRM user edits (Stage Z), and rolls
  up analytics. Maps back to legacy `GRP_` via `legacy_to_auto_group_map`.
- **`cleo/discovery/`** (v1, rule-based, `DISC_` ids) — **still mounted** at `/api/discovery`.
  Two competing clustering engines coexist undocumented; v2 is the active build target.
- **`cleo/analytics/groups.py`** — legacy `refresh_group_analytics` → `group_analytics` (system
  table). `discovery_v2/group_analytics.py` is the auto-group successor that rolls these up.
- **`cleo/labeling/`** — human-in-the-loop party-link ground-truth (LBL_ ids; CRM `labeling_*`
  tables) that feeds discovery validation.
- **`cleo/address/`** — single source of truth for display-address formatting, shared by all
  pipelines and the compiler.

## 6. Database — `cleo/database/`

SQLite at `data/cleo.db`, WAL mode, `foreign_keys=ON`, `Row` factory. **The authoritative schema
is `schema.py` + 36 migration files** (`database/migrations/001..036_*.py`), not `schema.py`
alone. The live `auto_groups`/`auto_group_*`/`legacy_to_auto_group_map`/`contact_brand_tenures`/
`brand_*`/`issues` tables are **migration-only** and do not appear in `schema.py`.

Three categories (the compiler rebuilds only the first):

- **Derived** (dropped + rebuilt): properties, transactions, contacts, groups, group_names,
  transaction_parties, transaction_mailing_addresses, transaction_brokers,
  transaction_broker_agents, pois, gw_assessments, gw_sales_history, **brand_registry,
  party_fingerprints, party_atoms** (these three are NOT in CLAUDE.md's derived list) + 4 FTS
  tables.
- **CRM** (never dropped): deals, lists, list_members, user_stars, group_contacts, contact_notes,
  group_notes, group_merges, brand_overrides, user_brand_favorites, group_overrides,
  group_field_overrides, contact_field_overrides, contact_work_history, sell_opportunities,
  buy_mandates, property_enrichment, activities, the labeling_* tables, and
  **auto_group_user_edits** (Stage Z depends on it; not in CLAUDE.md).
- **System**: id_mappings, ai_usage, users, audit_log, app_meta, asset_classes,
  tenant_categories, group_analytics, data_issues, discovery_* tables.

## 7. Backend API — `cleo/web/`

`create_app()` registers **31 routers**, all under `/api/*` (quirks: search is at
`/api/omnisearch`; `contact_tenures` is mounted at bare `/api`, overlapping the contacts
namespace). SPA `dist/` is served at `/` when built. Browse endpoints return
`{results,total,page,per_page,pages}` (with several inconsistent exceptions: brands -> `{brands}`,
lists/notes/stars -> bare arrays, geo -> GeoJSON).

- **Auth is hand-rolled, NOT JWT/bcrypt** despite the docstring. `auth.py` issues a
  `base64url(payload).hmac_sha256_hex` token (not RFC-7519 JWT) and hashes passwords with
  **PBKDF2-HMAC-SHA256** (100k iters). No `python-jose`/`passlib` involved.
- `require_admin` gates **only `admin.py`**; every other router gates on `get_current_user`
  alone, and there is essentially **no per-user row scoping** (notes, deals, activities,
  labeling, discovery, brand curation are global to any authenticated user). `user_stars` and
  list ownership are the exceptions.
- **FTS5 tables are defined and populated but never queried** — every "search" endpoint uses
  `LIKE '%q%'`. `deps.fts_query()` exists but is never called.
- **AI subsystem** (`ai.py`): `POST /api/ai/chat` real SSE stream to `anthropic.Anthropic()`
  (default model `claude-opus-4-7`), an agentic loop (<=15 tool calls) with tools `run_sql`,
  `describe_schema`, `get_entity_url`. SQL safety is solid (read-only connection, SELECT/WITH
  allowlist, row + timeout caps) **but has no table allowlist** — the model can `SELECT * FROM
  users` and stream password hashes. Logged to `ai_usage`.

## 8. Frontend — `frontend/src/`

Vite 8 + React 19 + TypeScript, Radix UI Themes (jade/slate, light only), Tailwind for layout,
Phosphor icons, Mapbox GL, TanStack Table/Virtual, Recharts, React Flow (`@xyflow/react`),
react-router-dom 7. Dev server depends on `NODE_ENV` not being `production` (see §11).

- **`App.tsx`** holds everything: provider stack (`Theme -> AuthProvider -> CrmProvider ->
  SourceViewerProvider -> BrowserRouter -> IssueReporterProvider -> Suspense -> Routes`) plus
  global drawers (CRM, SourceViewer, CommandPalette). `AuthProvider` is defined inline here, not
  in `hooks/`.
- **Auth guard** is a `localStorage` token check inside `AppLayout.tsx:26` (`<Navigate
  to="/login">`); there is **no client-side role gating** anywhere — `/admin`, `/test-lab`,
  pipeline reprocess/rebuild are all reachable by any logged-in user (security is backend-only).
  `FULL_BLEED_ROUTES = ["/map", "/labeling/sessions/"]`.
- **~70 pages.** Core browse/detail (properties, transactions, contacts, groups), CRM (deals
  kanban, lists, queue, opportunities/mandates), pipeline inspector, data quality, discovery,
  **labeling** (the heaviest page), and a large **Explorer** family (~30 highly-duplicated
  n-gram brand/phone/address pages). Groups are modeled as **auto-groups (AGRP_)** with a
  `tier` field, not legacy `GRP_`.
- **API layer**: `api/client.ts` (`fetchApi`/`postApi`/`mutateApi`, Bearer from localStorage,
  hard `window.location` redirect on 401) plus an undocumented `api/aiClient.ts` (`streamChat`)
  for the Ask-Claude drawer. `types/index.ts` is a single 2,696-line interface bank.
- **State**: React Context (auth, CRM drawer, source viewer, issue reporter) + URL searchParams
  for list filters + hand-rolled `useEffect`+`fetch` everywhere; no Redux/Query. Some
  cross-component coupling via synthetic DOM events (fake Cmd-K, `crm-star-changed`).
- **`lib/theme.ts`**: design tokens + `getRadixHex()` — a static sRGB hex table used for Mapbox
  because `getComputedStyle` returns Display-P3 on Apple Silicon (which Mapbox rejects). A few
  colors referenced by label maps are missing from the table and silently fall back to gray.
- Dead/duplicate: `pages/PropertyDetailPage.old.tsx` (unrouted); duplicate
  `AssetClass`/`AssetSubclass` interface blocks in `types/index.ts`.

## 9. Cross-cutting concepts

- **ARN backbone** — the join key across all sources; properties are one-per-ARN; all-zero ARNs
  are treated as empty.
- **Stable IDs** — `PRO_/CON_/GRP_` (compiler) persisted via `id_mappings`; `AGRP_` (discovery_v2
  auto-groups); `DISC_` (discovery v1); plus `DEAL_/SO_/BM_/LBL_` for CRM objects.
- **"Branded identifier lives in 4 fields"** — for each transaction side the owner identity can
  appear in `party_name`, `*_trade_name`, `*_care_of`, or `*_companies_json`; law firms
  (`*_law_firms_json`) are explicitly NOT ownership signals. Enforced canonically in
  `cleo/atoms/fingerprint.py:216-231` and surfaced in the frontend transaction types. This is the
  one major doc claim that the code matches exactly.

## 10. Code vs docs discrepancies

| # | CLAUDE.md / docs claim | Reality |
|---|---|---|
| 1 | "ALL parcel resolution goes through `cleo/resolver/`" | RT only. GW/OSM resolve directly; their adapters are dead code. |
| 2 | Compiler is "3-pass" | It's 6 passes (+ FTS/atoms/analytics post-steps). |
| 3 | Auth = "JWT via python-jose, bcrypt via passlib" | Hand-rolled HMAC token + PBKDF2 passwords. |
| 4 | "Use FTS5 MATCH queries" for search | FTS5 populated but never queried; all search is `LIKE`. |
| 5 | `cleo/` tree = web/compiler/database/resolver | Also address, atoms, identity, analytics, discovery, discovery_v2, labeling, cli, migrations. |
| 6 | Stable-ID maps persist in `app_meta` | They persist in `id_mappings`; `app_meta` only holds counters. |
| 7 | `python -m cleo.compiler` to rebuild | No `__main__`; use `rebuild.py` (what the admin UI calls). |
| 8 | Derived/CRM table lists | Missing brand_registry/party_*/party_atoms (derived), auto_group_user_edits (CRM), and the whole migration-only auto_group/issues/brand_* family. |
| 9 | Groups keyed by `GRP_` | Active surface is `auto_groups` (`AGRP_`) with tiers; `GRP_` is the legacy backend id. |
| 10 | (unstated) | Two parallel clustering engines (`discovery` v1 + `discovery_v2`) coexist; AI model pinned two different ways (`claude-opus-4-7` in ai.py vs `claude-sonnet-4-6` in identity/enrich.py). |

**Net:** the code is in better shape than the docs; the docs simply predate the auto-group
identity stack and several refactors.

## 11. Environment & operational notes

- **Ports are fixed**: backend 8099, frontend 5174 (`vite.config.ts` `strictPort`). The frontend
  proxies `/api` -> `127.0.0.1:8099`.
- **`NODE_ENV=production` breaks the dev server.** Vite's React Fast Refresh preamble is skipped
  in production mode, causing a `$RefreshSig$ is not defined` white page. Launch the frontend
  with `NODE_ENV=development` (baked into the repo's `start-cleo.command` / `Cleo Turbo.app`).
- **Backend deps** live in the project `.venv`; there is now a `requirements.txt` (generated from
  imports). Pipeline scrapers additionally need `playwright` (`playwright install chromium`).

## 12. Risks worth tracking (security + fragility)

1. **Hardcoded JWT-secret default** (`auth.py:22`, `cleo-turbo-dev-secret-change-in-production`) —
   if `CLEO_JWT_SECRET` is unset in prod, anyone can forge admin tokens. Highest severity.
2. **CORS** `allow_origins=["*"]` with `allow_credentials=True` (invalid/unsafe combo).
3. **AI `run_sql`** can read the `users` table (password hashes) and all CRM/audit data and stream
   it to the browser — no table allowlist.
4. **Unauthenticated-by-role heavy operations**: `groups /refresh-analytics` and
   `data-quality /scan` run expensive global recomputes with no admin gate; `auto_groups` id gen
   is a race-prone `MAX()+1`.
5. **Stored, unsanitized Realtrack HTML** is served verbatim by `transactions/{id}/html`
   (stored-XSS surface in the app origin).
6. **Two write paths into GW/property tables** (compiler Pass 5 vs the GW watcher's incremental
   update) — consistency risk.
7. **Position-based RT join** and **two competing dedup/scoring functions** (`dedup.py` vs
   `compile.py`) can disagree on which duplicate wins.
8. **Default seeded admin** `brandon`/`admin` in `rebuild.py --fresh` — change the password.
