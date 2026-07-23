# Cleo Turbo

## Working Rules

- Before diagnosing something as a bug, check Domain Facts first. Missing ARNs, PINs, empty party names, and unresolved parcels are usually normal — not broken.
- When something looks "missing" in the data, ask whether it's expected before trying to fix it.
- For any change that touches the pipeline, database schema, or compiler, explain what you plan to do and wait for approval before writing code.
- Don't assume intent — if a request is ambiguous, ask.
- Don't speculate about external systems (Realtrack behavior, GeoWarehouse quirks) as though it's established fact. If you don't know, say so.
- When investigating an issue, state what you see factually before jumping to a diagnosis. Don't get tunnel vision on the first theory.
- **Capture every field the source HTML exposes, even when the value is empty or NULL.** NULL in the schema means "the source said nothing here." A missing column means "we never looked." The difference is load-bearing: if a field isn't surfaced in clean-data and the DB, there is no way to tell whether the data is absent or silently dropped. When building or extending a parser, normalizer, or compiler: the default is surface every discoverable field, mark it NULL when empty, and never skip it. This applies to every source (RT, GW, OSM) and every stage. If you are about to drop a field because it's usually empty, stop — preserve it and document it instead.
- **The user does not use a CLI.** Design solutions that live in the UI (the React app) or the API, not as command-line tools the user has to invoke from a terminal. Scripts for Claude-internal use (e.g., one-off data analysis, generating artifacts to review) are fine — they're for the developer workflow, not the user workflow. Anything the user needs to run, touch, monitor, or trigger must have a UI surface. This applies to silo discovery, data-quality checks, bulk operations, admin tasks, and any new workflow we build.

## Environment & Tooling (Cowork / remote sessions)

**Git and running the pipeline or tests MUST go through Desktop Commander (the real Mac shell), never the mounted Linux sandbox (`device_bash`).** The sandbox mounts this repo over a filesystem that cannot delete files, so git lock files (`.git/index.lock`, `.git/HEAD.lock`) get stranded and then block or half-corrupt later git commands; it also only has system `python3`, not the project `.venv`. Use Desktop Commander for every `git` command, for `.venv/bin/python`, for `pytest`, and for any pipeline run. Reading and editing files in the sandbox is fine; the moment it is git or execution, switch to Desktop Commander. If a stale lock appears, clear it from the Mac shell: `rm -f .git/*.lock`.

Cleo Turbo is a commercial real estate data platform for Ontario. It ingests property transaction data from Realtrack, parcel/ownership data from GeoWarehouse, and branded POI locations from OpenStreetMap, then compiles everything into a single SQLite database that powers a React frontend and FastAPI backend. The app is a prospecting tool for commercial realtors — the goal is to centralize property research, owner lookup, and deal tracking that currently requires bouncing between 8+ disconnected tools.

## Project Structure

```
cleo-turbo/
├── cleo/                    # Python backend
│   ├── resolver/            # Unified Parcel Resolution Service (all sources use this)
│   │   ├── __init__.py      # Public API: resolve(), ResolverContext, types
│   │   ├── types.py         # ResolutionInput, ResolutionResult, GeocodeResult, Signal, Method
│   │   ├── chain.py         # 6-step resolution chain with cross-validation
│   │   ├── cache.py         # Canonical parcel cache (clean-data/parcels/)
│   │   ├── pip.py           # Point-in-polygon verification + spatial grid index
│   │   └── pin_bridge.py    # PIN→ARN bridge via GW lookup data
│   ├── compiler/            # Reads clean-data/, assigns stable IDs, writes SQLite
│   │   ├── reader.py        # Iterates clean-data/{rt,gw,osm}/ directories
│   │   ├── reconciler.py    # Stable ID assignment (PRO_, CON_, GRP_)
│   │   └── writer.py        # 3-pass write: groups → contacts → properties+transactions
│   ├── database/
│   │   ├── connection.py    # SQLite connection (data/cleo.db)
│   │   └── schema.py        # All CREATE TABLE statements
│   └── web/
│       ├── app.py           # FastAPI app factory
│       ├── auth.py          # JWT auth
│       ├── deps.py          # Dependency injection (get_db, get_current_user)
│       └── routes/          # One file per resource (properties.py, contacts.py, etc.)
├── engines/                 # Data processing pipelines
│   ├── rt/                  # Realtrack engine (extract → dedup → classify → normalize → resolve → compile)
│   ├── gw/                  # GeoWarehouse engine (ingest → parse → normalize → resolve → compile)
│   └── osm/                 # OpenStreetMap POI import
├── frontend/                # Vite + React 19 + TypeScript
│   └── src/
│       ├── api/client.ts    # fetchApi/postApi/mutateApi helpers
│       ├── components/      # Shared components (auth/, crm/, layout/, pipeline/, ui/)
│       ├── hooks/           # Custom hooks (useAuth)
│       ├── lib/             # utils.ts (formatCurrency, formatDate, etc.) + theme.ts (Radix colors)
│       ├── pages/           # One file per page, default export
│       ├── types/index.ts   # All TypeScript interfaces
│       ├── App.tsx           # Router + providers
│       └── main.tsx
├── data/                    # SQLite database (cleo.db) — gitignored
├── clean-data/              # Compiled JSON records per source — gitignored
├── raw-data/                # Source HTML/JSON files — gitignored
└── docs/                    # Architecture and planning docs
```

## Critical Rules

### Database: Derived vs CRM Tables

The database has two categories of tables. Getting this wrong will destroy user data.

**Derived tables** (rebuilt by the compiler from clean-data/):
properties, transactions, contacts, groups, group_names, transaction_parties,
transaction_mailing_addresses, transaction_brokers, transaction_broker_agents,
pois, gw_assessments, gw_sales_history

**CRM tables** (persistent, NEVER rebuilt or truncated):
deals, lists, list_members, group_contacts, contact_notes, group_notes,
contact_phones, contact_emails,
sell_opportunities, buy_mandates, activities, property_enrichment,
brand_overrides, user_brand_favorites, group_overrides, group_field_overrides,
contact_field_overrides, contact_work_history, group_merges,
labeling_sessions, labeling_verdicts, labeling_links, labeling_seeds,
labeling_reviewed_index, user_stars, issues

**System tables:**
users, audit_log, app_meta, data_issues, asset_classes, tenant_categories, ai_usage

The compiler calls `drop_derived_tables()` then recreates them. CRM tables are never touched. If you are writing code that modifies the database, always check which category the table belongs to.

### Stable IDs

The reconciler assigns stable IDs that persist across compiler re-runs via the `app_meta` table:
- `PRO_NNNNN` — properties, keyed by ARN (20-digit assessment roll number)
- `CON_NNNNN` — contacts, keyed by name fingerprint (UPPERCASE first+last)
- `GRP_NNNNN` — groups, keyed by normalized company name (UPPERCASE, legal suffixes stripped)

Never reset these counters. Never change how fingerprints/normalized names are computed without understanding that it will create duplicate IDs.

### The ARN is the backbone

The ARN (Assessment Roll Number) is what links everything together. An RT transaction, a GW detail page, and parcel geometry all connect to the same property via ARN. If you're adding a new data source or feature, figure out how it connects to ARNs.

## Tech Stack

### Backend
- Python 3.12+, FastAPI, Uvicorn
- SQLite (data/cleo.db) with FTS5 full-text search
- Raw SQL queries (no ORM) — all routes use `db.execute()` with parameterized queries
- JWT auth via python-jose, passwords via passlib/bcrypt

### Frontend
- React 19, TypeScript, Vite
- Radix UI Themes (accent: jade, gray: slate, radius: medium)
- Tailwind CSS for layout/spacing
- Phosphor Icons (`@phosphor-icons/react`)
- Mapbox GL (`react-map-gl`) for map views
- TanStack Table for data tables (some pages), TanStack Virtual for virtualization
- Recharts for charts
- react-router-dom v7 for routing

### Design System
- Radix UI `<Theme>` wraps the entire app with `accentColor="jade"` `grayColor="slate"`
- Colors use CSS variables: `var(--jade-9)`, `var(--gray-11)`, etc.
- For Mapbox (which can't use CSS vars), use `getRadixHex()` from `lib/theme.ts`
- Card pattern: `rounded-[var(--card-radius)] border border-[var(--gray-6)] p-5`
- Table header: `bg-[var(--gray-2)]` with `text-[12px] font-medium` and `color: var(--gray-9)`
- Muted text: `style={{ color: "var(--gray-9)" }}`
- Link style: `color: var(--accent-11)`, `no-underline`
- Currency is CAD: `formatCurrency()` in `lib/utils.ts`

## How to Add a Frontend Page

1. Create `frontend/src/pages/YourPage.tsx` with a default export function component
2. Add route in `App.tsx` inside the `<Route element={<AppLayout />}>` block
3. Import the page at the top of `App.tsx` — use `lazy()` for heavy pages (map, pipeline), direct import for everything else
4. For list pages: use `fetchApi<BrowseResponse<YourType>>` with pagination state, render an HTML `<table>` (not TanStack Table for simple lists), navigate on row click
5. For detail pages: use `useParams()` to get the ID, `fetchApi<YourDetail>` to load, back-link at top (`← ResourceName` linking back to list), two or three column grid layout with cards
6. Add TypeScript interfaces to `frontend/src/types/index.ts`
7. Use Radix `<Heading>`, `<Text>`, `<Badge>`, `<Button>` — not raw HTML for these
8. Use `formatCurrency()`, `formatDate()`, `formatPhone()` from `lib/utils.ts`
9. For full-bleed pages (like the map), add the route path to `FULL_BLEED_ROUTES` in `components/layout/AppLayout.tsx`
10. The layout uses a Sidebar + Header wrapper — pages render inside `<Outlet />`, so don't add their own nav chrome

## How to Add an API Route

1. Create `cleo/web/routes/your_resource.py`
2. Define `router = APIRouter()`
3. All endpoints take `db=Depends(get_db), user=Depends(get_current_user)` — imports from `...web.deps`
4. Write raw SQL with `?` parameter placeholders (SQLite style)
5. Return dicts: `[dict(r) for r in rows]`
6. For browse endpoints: accept `page` + `per_page` params, return `{ results, total, page, per_page, pages }`
7. For search endpoints: use FTS5 MATCH queries against the `_fts` tables
8. Register in `cleo/web/app.py`: import router, `app.include_router(router, prefix="/api/your-resource", tags=["your-resource"])`
9. Parse JSON columns (like `seller_parties`) with `json.loads()` before returning
10. For admin-only endpoints, use `user=Depends(require_admin)` from `deps.py`
11. All API routes are prefixed with `/api/` — the frontend proxies `/api` requests to the backend via vite config

## How to Run

**Ports are fixed. Never use random ports.**
- Backend: **8099**
- Frontend: **5174** (configured in `vite.config.ts` with `strictPort: true`)

```bash
# Backend (from project root)
uvicorn cleo.web.app:app --reload --port 8099

# Frontend dev server (from frontend/)
npm run dev          # starts on port 5174, proxies /api to backend on 8099

# Build frontend for production
cd frontend && npm run build   # outputs to frontend/dist/

# Run the compiler (rebuild database from clean-data/)
python -m cleo.compiler

# GW watcher (auto-process new GeoWarehouse files)
python -m engines.gw.watcher

# RT pipeline orchestrator (preferred way to run the RT pipeline)
cd engines/rt && python process.py --new                          # process new records only
cd engines/rt && python process.py --from classify --skip resolve # reprocess after parser fix
cd engines/rt && python process.py --from classify                # reprocess everything from classify
cd engines/rt && python process.py --resolve-unresolved           # retry failed parcel resolutions
cd engines/rt && python process.py --status                       # show pipeline state + history

# RT watcher (auto-detects new files, delegates to process.py --new)
python engines/rt/watcher.py

# RT resolve only (reprocess all parcel links)
cd engines/rt && python -m parcel_resolver.resolve_v2 --reprocess

# OSM POI parcel resolution
python engines/osm/resolve_pois_v2.py --retry
```

## Data Pipeline Overview

```
raw-data/rt/     → engines/rt/  (extract → dedup → classify → normalize → resolve_v2 → compile) → clean-data/rt/
raw-data/gw/     → engines/gw/  (ingest → parse → normalize → resolve → compile)         → clean-data/gw/
(imported from V3) → engines/osm/ (import → resolve_pois_v2)                               → clean-data/osm/

clean-data/{rt,gw,osm}/ → cleo/compiler/ (reader → reconciler → writer) → data/cleo.db
```

Each engine stage reads from the previous stage's output folder and writes to its own folder. Stages are independent — you can re-run any stage without affecting others.

### Unified Parcel Resolution Service

**ALL parcel resolution goes through `cleo/resolver/`.** No targeted fixes in individual pipelines. Each engine has a thin adapter that converts its file format → `ResolutionInput`, calls `resolve()`, and converts `ResolutionResult` back to the pipeline's output format.

**Architecture:**
- `cleo/resolver/` — core resolution logic (types, chain, cache, PIP, PIN bridge)
- `engines/rt/parcel_resolver/adapter.py` — RT adapter (addresses → parcel_links)
- `engines/gw/adapter.py` — GW adapter (normalized → parcel_links)
- `engines/osm/adapter.py` — OSM adapter (POI → in-place update)

**Resolution chain (6 steps):**
1. PIN→ARN bridge (local GW lookup, zero API calls)
2. ARN lookup (cache → AgMaps API)
3. Address geocoding (Ontario geocoder, all variants, captures 44 attributes incl. Comp_score)
4. Coordinate PIP (OSM rooftop coords → spatial query)
5. Cross-validation (decision hierarchy: OSM coords > PointAddress > consensus > StreetAddress > ARN > PIN)
6. PIP verification (local grid-based check, zero API calls)

**Method names** (standardized across all sources): `verified`, `spatial_consensus`, `spatial_geocode`, `spatial_override`, `spatial_coords`, `arn_only`, `pin_bridge`, `unresolved`, `error`

**Confidence scoring:** 0.0–1.0. verified=0.95, spatial_consensus=0.90, spatial_coords=0.90, spatial_geocode=0.85, spatial_override=0.80, arn_only=0.50, pin_bridge=0.40.

**Usage:**
```python
from cleo.resolver import resolve, ResolverContext, ResolutionInput, GeocodableAddress

ctx = ResolverContext(agmaps_client=client, geocoder_client=geocoder, pin_to_arn=pin_table)
result = resolve(ResolutionInput(source="rt", source_id="RT156261", arn="34090010005020000000", addresses=[...]), ctx)
print(result.resolved_arn, result.method, result.confidence)
```

**Policy: NO TARGETED FIXES.** If a record resolves to the wrong parcel, the fix goes in `cleo/resolver/chain.py`, not in the individual engine. The old `engines/rt/parcel_resolver/cache.py` and `pin_bridge.py` now redirect to `cleo/resolver/`.

### RT Parcel Resolution (v2)

The RT pipeline uses `engines/rt/parcel_resolver/resolve_v2.py` — a unified single-pass resolver that replaces the old multi-stage pipeline (pin_bridge → geocode_preflight → geocode → resolve). It does everything in one pass:

1. **PIN→ARN bridge** — local GW data lookup, zero API calls
2. **ARN resolution** — parcel cache → AgMaps API
3. **Ontario geocoding** — geocodes all address variants via the provincial GeocodeServer
4. **Multi-address consensus** — if multiple addresses resolve to the same parcel, high confidence
5. **Cross-validation** — if ARN and geocode disagree, trust geocode (PointAddress) or consensus

Key files:
- `parcel_resolver/ontario_geocoder.py` — Ontario Address Locator client (Playwright + AgMaps proxy)
- `parcel_resolver/resolve_v2.py` — Unified orchestrator with checkpoint/resume
- `parcel_resolver/agmaps.py` — AgMaps parcel query client (ARN and spatial point queries)
- `parcel_resolver/cache.py` — Shared parcel cache (clean-data/parcels/)
- `parcel_resolver/token.py` — AgMaps token management

Run modes:
```bash
python -m parcel_resolver.resolve_v2                          # resume (skip done)
python -m parcel_resolver.resolve_v2 --reprocess              # redo all records
python -m parcel_resolver.resolve_v2 --reprocess-unresolved   # redo only failed
python -m parcel_resolver.resolve_v2 --limit 100              # test with N records
```

**CRITICAL: Throttle = hard stop.** If the Ontario geocoder detects rate limiting (3 consecutive errors or 10% error rate), the pipeline stops immediately and prints a warning. Do NOT auto-retry. Wait 5+ minutes before restarting.

### Watchers

The GW watcher processes new files AND does incremental DB updates (bypasses full compiler). This is intentional — don't refactor it to go through the compiler.

The RT watcher (`engines/rt/watcher.py`) monitors for new Realtrack HTML files and runs the full pipeline automatically. It also catches unresolved addresses files and pushes them through resolve_v2. **Lockfile-aware:** if resolve_v2 is already running, the watcher only runs the safe early stages (assemble → classify → normalize) and queues resolve for the next cycle.

### Daily Auto-Scraper

The daily scraper (`engines/rt/scraper/daily_scraper.py`) is a lightweight, cron-friendly scraper that catches new Realtrack transactions automatically.

**Key finding (verified Apr 2026):** Searching with sf3="" ("All Property Types") and sf1="" (blank region) returns ALL transactions — both categorized and uncategorized — from all 50 Ontario regions in a single search. Every RT ID from individual category searches also appears in the "All" results. This means one search is sufficient.

Run modes:
```bash
# Daily sweep — last 14 days, all regions, all types (~2-5 min)
python -m engines.rt.scraper.daily_scraper --daily

# Weekly audit — last 90 days, catches backdated entries (~30-60 min)
python -m engines.rt.scraper.daily_scraper --audit

# Monthly gap analysis — find sequential RT ID gaps
python -m engines.rt.scraper.daily_scraper --gaps

# Dry run — count only, no downloads
python -m engines.rt.scraper.daily_scraper --daily --dry-run

# Custom lookback period
python -m engines.rt.scraper.daily_scraper --daily --days 7
```

**How it works:**
1. Logs in to Realtrack via httpx
2. Discovers current property types from the search form (alerts on new/removed types)
3. Runs ONE search: all regions, all types, last N days, sorted by date descending
4. Pages through results, downloads only new detail pages (deduped against known RT IDs)
5. Runs a verification pass: sums individual category counts and compares against "All" total
6. Deposits files into `raw-data/rt/pages/_daily/` where the RT watcher picks them up

**Concurrency safe:** The scraper only writes to raw-data/. If resolve_v2 is running, the watcher processes new files through normalize only and queues resolve for later.

**Scheduling (cron):**
```bash
0 6 * * *   cd ~/cleo-turbo && python -m engines.rt.scraper.daily_scraper --daily >> /tmp/rt_daily.log 2>&1
0 0 * * 0   cd ~/cleo-turbo && python -m engines.rt.scraper.daily_scraper --audit >> /tmp/rt_audit.log 2>&1
0 3 1 * *   cd ~/cleo-turbo && python -m engines.rt.scraper.daily_scraper --gaps >> /tmp/rt_gaps.log 2>&1
```

Key files:
- `engines/rt/scraper/daily_scraper.py` — Main daily scraper (daily/audit/gaps modes)
- `engines/rt/scraper/shared.py` — Shared utilities (session, HTML parsing, credentials, property type discovery)
- `engines/rt/scraper/search_scraper.py` — Bulk historical scraper (used for initial data load, not daily use)
- `engines/rt/scraper/inventory.py` — RT ID inventory manager

### RT Pipeline Orchestrator

`engines/rt/process.py` is the single entry point for running the RT pipeline. It replaces manually calling individual stage scripts. Two modes:

**Mode 1 — New records** (`--new`): Processes only records that are missing from downstream stages. This is what the daily scraper + watcher use. The orchestrator finds assembled files without a classified counterpart, classifies them, finds classified files without a normalized counterpart, normalizes them, etc. Nothing gets deleted or overwritten — it only creates missing output.

**Mode 2 — Reprocess** (`--from <stage>`): Reprocesses ALL records from a given stage onward, overwriting existing output in place. Uses a marker file (`pipeline/_reprocess.json`) to track progress so crashed runs can resume. Use `--skip resolve` to keep existing parcel links when fixing a parser bug.

All runs are logged to `pipeline/_processing_log.jsonl` (append-only) with timestamps, file counts, and elapsed times. Use `--status` to see pipeline state and processing history.

Key files:
- `engines/rt/process.py` — Pipeline orchestrator (--new, --from, --status, --dry-run)
- `engines/rt/pipeline/_processing_log.jsonl` — Append-only processing history

## Reference Docs

- `docs/definitions.md` — Canonical terminology reference. Still accurate. Read this first if you're confused about any term.
- `docs/workflows.md` — The real-world prospecting workflows Cleo is solving. This is the "why" behind the system. Still accurate.
- `docs/build-plan.md` — Historical. Everything listed as "needs to be built" is now built. Useful for understanding original intent, but don't treat TODOs in it as current.
- `docs/styling-reference.md` — Design system reference (WorkOS Dashboard style). Still the target aesthetic.
- `docs/frontend-plan.md` — Original frontend implementation plan. The app has evolved since — use the actual code as the reference for current patterns.

## Domain Facts

Things that are true about the data sources and domain. Read these before diagnosing any "missing data" issue. Do NOT treat any of these as bugs or things that need fixing.

### Realtrack (RT)

- **Not every RT transaction has an ARN.** Many records legitimately have no Assessment Roll Number. This is normal — do not flag it as a data issue or try to "fix" it.
- **Not every RT transaction has a PIN.** Same as ARN — PINs are often absent. Normal.
- **RT building size (`bldg`) is a free-text string with mixed units.** About 24% of records have a non-empty value. Units include `sf` (square feet), `units` (multifamily), `rooms` (hotels), `beds` (care), `bdrms`, `suites`, and a long tail. Fill rate varies by property type: office 59%, multifamily 55%, industrial 52%, hotel 47%, retail 42% — land categories near 0% (expected). Stored as three columns on `transactions` and denormalised onto `properties` (latest non-null wins): `building_size_raw` (verbatim source), `building_size_value` (parsed number), `building_size_unit` (normalised). You cannot sum across units — `"22 units"` and `"22,000 sf"` are incomparable; aggregate per-unit. Parser: `engines/rt/building_size.py`.
- **Building size filters are sf-only.** Properties, Map, Contacts browse endpoints accept `building_size_min` / `building_size_max` (sf, applies `building_size_unit='sf'` implicitly). Groups browse accepts `min_portfolio_sf` / `max_portfolio_sf` which filters by SUM of building_size_value across owned properties. Non-sf properties are excluded when these filters are active — by design.
- **Portfolio Size aggregation.** Group and contact detail endpoints return a `portfolio_sf` object: `{total_sf, properties_with_sf, total_properties}`. Group definition: `WHERE current_owner_group_id = ?`. Contact definition: properties where the contact is on the buyer side of the property's `most_recent_source_id` transaction (direct buyer). Both are sf-only lower bounds — only ~24% of properties have RT-reported building size, so the count `properties_with_sf < total_properties` is normal. The UI shows the totals as "X.XM sf · Reported on N of M". Computed on the fly; if it ever becomes a bottleneck, denormalise onto `groups.total_building_size_sf` in the compiler.
- **RT records can be incomplete at scrape time.** Newly posted transactions sometimes have partial data ($0 price, empty parties) that gets filled in hours or days later. The audit scraper (90-day lookback) is designed to catch these.
- **RT export data and detail page data overlap but aren't identical.** The export has fields the detail page doesn't (like postal code), and the detail page has fields the export doesn't (like mortgage/charge details). The assembler merges both.
- **"Named Individual(s)" is a real seller/buyer name.** RT uses this when the actual person's name is suppressed. It's not a parsing error.
- **The branded portfolio identifier can live in any of four fields per transaction side.** `party_name` (the registered entity — often the brand itself for branded portfolios like RioCan), `trade_name` (management company / brand, common on SPV portfolios like DH Management), `care_of` (the "c/o" routing, also often a management company), or `companies_json` (additional management-company names parsed from contact blocks). Never assume the brand is in just one of them. Any signal extraction, ownership lookup, or clustering logic that reads "who owns this property" must normalize across all four. Reading only `transaction_parties.party_name` silently misses every SPV-style portfolio. Law firms live in a separate field (`law_firms_json`) and are NOT branded-identifier data. See `docs/definitions.md` → "Where the Branded Identifier Lives" for the full field map.

### GeoWarehouse (GW)

- **GW data is parcel-level, not transaction-level.** It tells you who owns a parcel now, not the transaction history.
- **GW assessment values are often outdated.** Ontario reassesses on a multi-year cycle. Don't compare GW assessed values to RT sale prices and call it a discrepancy.

### General

- **Not every property resolves to a parcel.** The parcel resolver has an ~89% success rate. The remaining ~11% are genuinely unresolvable (rural land, new subdivisions, ambiguous addresses). This is expected.
- **The ARN is 20 digits but displayed with spaces.** e.g., "53 07 060 001 02600". These spaces are part of the display format. The raw ARN is the same string with spaces.
- **Currency is always CAD.** All prices, assessed values, and mortgage amounts are Canadian dollars.

## Frontend API Layer

The frontend uses three helpers in `src/api/client.ts`:
- `fetchApi<T>(path, params?)` — GET requests with optional query params
- `postApi<T>(path, body)` — POST requests with JSON body
- `mutateApi<T>(path, method, body?)` — PUT/PATCH/DELETE requests

All three automatically attach the JWT token from localStorage and redirect to `/login` on 401. Path is relative to `/api` (e.g., `fetchApi("/properties")` hits `/api/properties`).

On the frontend, TypeScript interfaces for all API responses live in `src/types/index.ts`. When adding a new endpoint, add the response type there — not inline in the page component.

## Git Workflow

- Commit after every working change, not just at the end of a session
- Use branches for new features or risky changes
- Before committing frontend changes, run `cd frontend && npx tsc` to check for type errors
- The database (data/cleo.db), clean-data/, and raw-data/ are gitignored — only code is tracked
