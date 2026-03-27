# Cleo Turbo — Build Plan

## Context

Cleo Turbo is a ground-up rebuild of a real estate data platform for Ontario commercial real estate. The predecessor project (Cleo Mini V3) had a v4 rebuild plan with a solid tech stack but an architecture that has since been superseded by a new definitions document (`docs/definitions.md`). This plan carries forward the v4 tech stack while aligning the architecture to the definitions doc — the single source of truth.

**What exists today:**
- `engines/rt/` — 6,000 lines of Python, fully operational (Extract + Classify + Normalize stages)
- 126,106 processed records (94,941 unique RT IDs) with classified + addresses output
- 109 approved test fixtures
- `raw-data/rt/` — 813MB scraped Realtrack data
- `docs/definitions.md` — 596-line canonical architecture reference
- `docs/workflows.md` — Manual prospecting loop Cleo is solving
- Empty scaffolds for everything downstream

**What needs to be built:**
- RT Compile stage (merge stage outputs → Clean Records in `clean-data/rt/`)
- Compiler (reads `clean-data/`, assigns stable IDs, writes SQLite)
- SQLite database
- FastAPI backend
- React frontend (using v3 design system — `docs/styling-reference.md`)
- CRM layer + HubSpot sync
- Deployment (Hetzner VPS)

**Reference docs carried from v3:**
- `docs/styling-reference.md` — Complete design system (WorkOS Dashboard style, Radix + Tailwind + Untitled Sans font, color tokens, component patterns, layout grid). Build the frontend using this design system — not from scratch, not porting v3 components directly.

---

## Tech Stack (carried from v4, validated)

### Backend
```
Python 3.12+
├── FastAPI              — API framework
├── Uvicorn              — ASGI server
├── Click                — CLI framework
├── Pydantic v2          — Data validation, models
├── python-jose          — JWT tokens
├── passlib[bcrypt]      — Password hashing
├── httpx                — HTTP client (APIs, scraping)
├── beautifulsoup4+lxml  — HTML parsing
├── playwright           — AgMaps token fetch (headless browser)
└── pytest               — Testing
```

### Frontend
```
React 18 + TypeScript
├── Vite                 — Build tool
├── @radix-ui/themes     — Component library
├── @tanstack/react-table — Data tables
├── @tanstack/react-virtual — Virtual scrolling (70K+ rows)
├── @phosphor-icons/react — Icons
├── Tailwind CSS 4       — Utility styles
├── react-router-dom     — Routing
├── react-map-gl + maplibre-gl — Map
└── recharts             — Charts
```

### Deployment
```
Hetzner VPS (~$5/mo)    — 2 vCPU, 4GB RAM, 40GB disk
├── Caddy                — Reverse proxy, auto HTTPS
├── systemd              — Process management
└── Litestream           — SQLite → Cloudflare R2 continuous backup
```

### Database
SQLite with WAL mode. Perfect for 3 users, no server process, FTS5 for search, easy backup via Litestream.

---

## Project Structure

```
cleo-turbo/
├── pyproject.toml                    # Dependencies, CLI entry point
├── cleo/                             # Installable Python package
│   ├── cli/                          # Click CLI commands
│   │   ├── __init__.py               # Main group: `cleo`
│   │   ├── engine.py                 # `cleo engine rt {extract,classify,normalize,...}`
│   │   ├── compiler.py               # `cleo compiler {run,status}`
│   │   ├── db.py                     # `cleo db {init,stats}`
│   │   └── web.py                    # `cleo web serve`
│   ├── compiler/                     # Reads clean-data/, writes SQLite
│   │   ├── reader.py                 # Read clean-data/ JSON files
│   │   ├── reconciler.py             # Match to existing IDs (ARN, name fingerprint)
│   │   └── writer.py                 # Write derived tables
│   ├── database/                     # SQLite schema + connection
│   │   ├── schema.py                 # DDL, table creation
│   │   └── connection.py             # WAL mode, foreign keys
│   └── web/                          # FastAPI app
│       ├── app.py                    # App factory (<50 lines)
│       ├── auth.py                   # JWT auth (3 users)
│       ├── deps.py                   # Dependency injection
│       └── routes/                   # One file per domain
├── engines/                          # Existing engine code (UNCHANGED)
│   └── rt/                           # Working RT engine (~6K lines)
│       ├── run_pipeline.py           # Extract stage
│       ├── run_classifier.py         # Classify stage
│       ├── address_normalizer/       # Normalize stage
│       ├── compile.py                # NEW: Compile stage (Phase 1)
│       └── pipeline/                 # Intermediate outputs
├── raw-data/rt/                      # 813MB scraped data (read-only)
├── clean-data/rt/                    # Final engine output (one JSON per RT ID)
├── data/cleo.db                      # SQLite database
├── frontend/                         # React SPA
├── tests/                            # pytest suite
└── docs/
    ├── definitions.md                # Source of truth
    └── workflows.md                  # Problem being solved
```

**Key decision:** `engines/rt/` stays as-is. The CLI wraps it via `sys.path` manipulation — no refactoring of working code.

---

## RT Engine Stages (from definitions.md)

```
Extract → Classify → Normalize → Resolve Parcels → Compile
```

All stage definitions come from `docs/definitions.md` — the single source of truth. The v4 rebuild plan is reference material for tech stack and domain logic patterns only, not for architecture.

---

## Build Phases

### Phase 0: Project Foundation
**Goal:** pyproject.toml, CLI skeleton, engine integration — `cleo engine rt extract` works.

**Deliverables:**
- `pyproject.toml` with all dependencies, `[project.scripts]` entry `cleo = "cleo.cli:main"`
- `cleo/cli/__init__.py` — top-level Click group
- `cleo/cli/engine.py` — wraps existing `run_pipeline.py`, `run_classifier.py`, `address_normalizer/run.py`
- `.gitignore`

**Verify:** `cleo engine rt extract --limit 5` runs successfully.

---

### Phase 1: RT Compile Stage + Clean Records
**Goal:** Merge classified + addresses into one Clean Record per unique RT ID in `clean-data/rt/`.

**Deliverables:**
- `engines/rt/compile.py` — reads `pipeline/classified/` and `pipeline/addresses/`, deduplicates (126K → 95K by RT ID), merges, writes to `clean-data/rt/`
- Dedup: for duplicate RT IDs across property-type folders, score each (prefer join_verified, ARN presence, richer contacts) and pick the best
- `parcel` field starts as `null` (populated in Phase 5)
- `cleo engine rt compile` CLI command

**Clean Record format** (one file per RT ID, e.g. `clean-data/rt/RT100000.json`):
```json
{
  "source_id": "RT100000",
  "source": "rt",
  "compiled_at": "...",
  "transaction": { "sale_date", "sale_price", "transaction_note", "city", "region" },
  "property": { "addresses": [...], "city", "region", "postal" },
  "seller": { "parties", "phone", "contacts", "law_firms", "companies", "address" },
  "buyer":  { "parties", "phone", "contacts", "law_firms", "companies", "address" },
  "site":   { "pin", "arn", "acreage", "legal_description", "location" },
  "parcel": null,
  "consideration": { "cash", "debt", "chattels", "charges" },
  "broker": { "brokers": [{ "brokerage", "agents", "phone" }] },
  "description": { "description", "more_info_url" },
  "photos": { ... }
}
```

**Verify:** 94,941 files in `clean-data/rt/`. Spot-check 10 against source data.

**Critical files:**
- `engines/rt/pipeline/classified/*.json` — input (126K files)
- `engines/rt/pipeline/addresses/*.json` — input (126K files)

---

### Phase 2: Database + Compiler
**Goal:** Build the Compiler that reads `clean-data/rt/` and populates SQLite with properties, transactions, contacts, groups, and transaction_parties.

**Deliverables:**
- `cleo/database/schema.py` — full DDL (see below)
- `cleo/database/connection.py` — WAL mode, foreign keys, busy timeout
- `cleo/compiler/reader.py` — reads `clean-data/rt/*.json`, yields records
- `cleo/compiler/reconciler.py` — ID generation and persistence:
  - ARN → PRO_NNNNN (properties)
  - Name fingerprint (UPPERCASE first+last) → CON_NNNNN (contacts)
  - Normalized party name → GRP_NNNNN (groups)
- `cleo/compiler/writer.py` — 3-pass write:
  1. **Groups:** extract party names → normalize → assign GRP_ IDs
  2. **Contacts:** extract contact names → fingerprint → assign CON_ IDs
  3. **Properties + Transactions + Transaction Parties:** group by ARN, link everything
- `cleo compiler run` and `cleo db init` CLI commands

**Database tables (derived — rebuilt by Compiler):**
- `properties` (PRO_ ID, ARN, address, city, owner, latest sale, transaction count)
- `transactions` (source_id, property_id, full transaction data)
- `contacts` (CON_ ID, name_fingerprint, name, phone, status=pool|engaged)
- `groups` (GRP_ ID, normalized_name, display_name, status=pool|engaged)
- `group_names` (group_id, name variants)
- `transaction_parties` (source_id, contact_id, group_id, side)

**Database tables (CRM — persistent, never rebuilt):**
- `deals`, `lists`, `list_members`, `group_contacts`, `contact_notes`, `group_notes`

**Database tables (system):**
- `users`, `audit_log`, `app_meta`

**FTS5 indexes:** properties_fts, contacts_fts, groups_fts

**Compiler safety:** derived tables are truncated and rebuilt in a single transaction. CRM tables are never touched. Re-running the compiler after engine improvements preserves all CRM data.

**Verify:** Run compiler on 95K clean records. Expect ~50-70K properties, ~80-120K contacts, ~60-90K groups. Query a known record end-to-end.

---

### Phase 3: API Foundation + Properties/Transactions
**Goal:** FastAPI backend with auth, Properties browse/detail/search, Transactions browse/detail/search.

**Deliverables:**
- `cleo/web/app.py` — app factory, CORS, router mounts
- `cleo/web/auth.py` — JWT auth (3 users: Brandon=admin, wife=editor, partner=editor)
- `cleo/web/routes/properties.py`:
  - `GET /api/properties` — paginated, filterable (city, region, price range, owner)
  - `GET /api/properties/{id}` — detail with transaction history
  - `GET /api/properties/search` — FTS5
  - `GET /api/properties/stats` — dashboard aggregates
- `cleo/web/routes/transactions.py`:
  - `GET /api/transactions` — paginated, filterable
  - `GET /api/transactions/{source_id}` — full detail
- `cleo web serve` CLI command

**Verify:** All endpoints return correct data. Auth enforced. Pagination works. FTS5 returns sensible results.

---

### Phase 4: Frontend — Properties/Transactions + Dashboard
**Goal:** React SPA with login, Properties, Transactions, and Dashboard pages. First time the full stack is usable.

**Design system:** `docs/styling-reference.md` — WorkOS Dashboard style. Radix Themes (jade accent, slate gray, medium radius), Tailwind CSS, Untitled Sans font, CSS grid layout (220px sidebar + header + main). All patterns (cards, tables, nav, elevation, typography, spacing) are defined in the styling reference. Build to match that system.

**Deliverables:**
- Vite + React 18 + TypeScript scaffold with design system wired up (Radix Theme, Tailwind config, font files, index.css tokens)
- Auth flow (login page, JWT in localStorage, protected routes)
- Layout shell (sidebar nav, header — per styling reference grid layout)
- Properties page (data table, filters, search, virtual scrolling)
- Property Detail page (transaction history, site details, owner info)
- Transactions page (data table, search)
- Transaction Detail page (seller/buyer sides, consideration, broker)
- Dashboard page (stats cards, recent transactions, price chart via recharts)

**Verify:** Navigate from dashboard → property → transaction and back. Search works. All 3 users can log in.

---

### Phase 5: Resolve Parcels Stage (can parallel with Phase 4)
**Goal:** Query AgMaps API to get parcel polygons for RT records. Update Clean Records.

**Deliverables:**
- `engines/rt/parcel_resolver/` — AgMaps client, resolution chain, SQLite cache
- Resolution strategy: ARN direct (66%) → PIN bridge (21%) → spatial/address (13%)
- Aggressive caching (multiple transactions share parcels)
- Output: populate `parcel` field in `clean-data/rt/` Clean Records
- Also write `clean-data/parcels/{arn}.json` — one per unique parcel
- `cleo engine rt resolve-parcels` CLI command

**Verify:** Resolve 1,000 sample records. Valid GeoJSON polygons returned. Cache prevents duplicate API calls.

---

### Phase 6: Map + Contacts/Groups Views
**Goal:** Map view for prospecting, Contacts and Groups browse/detail pages.

**Deliverables:**
- Map page (MapLibre GL, property markers with clustering, parcel polygons, click-to-detail)
- `GET /api/map/clusters`, `GET /api/map/parcels`, `GET /api/map/properties`
- Contacts page + detail (status badge, transaction history, group associations)
- Groups page + detail (known names, contacts, transactions, properties)
- `GET /api/contacts`, `GET /api/groups` with search and filters

---

### Phase 7: CRM — Pool to Engaged + Deals + Lists
**Goal:** Write operations. Promote contacts/groups, create deals, build lists, add notes.

**Deliverables:**
- Pool → Engaged promotion (`POST /api/contacts/{id}/promote`)
- CRM field updates (email, phone, notes)
- Deal CRUD with pipeline stages (Prospecting → Nurturing → Negotiating → Under Contract → Firm → Closed | Lost)
- List management (create lists, add properties/contacts/groups)
- Group-Contact associations (current/former)
- Audit logging for all CRM mutations
- Frontend: promote buttons, deal board, list manager, notes sections

---

### Phase 8: HubSpot Sync + Admin
**Goal:** Bidirectional sync with HubSpot for engaged contacts/groups. Admin panel.

**Deliverables:**
- Push engaged contacts → HubSpot Contacts, engaged groups → HubSpot Companies
- Pull enrichment back (emails, notes)
- Field mapping per definitions.md
- Admin page: system status, user management, compile/sync triggers, audit log viewer

---

### Phase 9: Deployment
**Goal:** Production deploy to Hetzner VPS.

```
Internet → Caddy (HTTPS, static frontend) → FastAPI (uvicorn :8000) → cleo.db
                                                                          ↓
                                                                    Litestream → R2
```

- Caddy + systemd + Litestream config
- DNS + auto HTTPS via Let's Encrypt
- 3 user accounts created
- Data synced and compiler run on VPS

---

### Phase 10: Additional Data Sources (ongoing)
Each new source (OSM, Brand, GeoWarehouse) follows the same pattern:
1. Build engine in `engines/{source}/`
2. Run source-specific stages per the stage sequence table
3. Write Clean Records to `clean-data/{source}/`
4. Update Compiler reader to include new source
5. Re-run compiler

---

## Dependency Graph

```
Phase 0 ──→ Phase 1 ──→ Phase 2 ──→ Phase 3 ──→ Phase 4 ──→ Phase 6 ──→ Phase 7 ──→ Phase 8 ──→ Phase 9
                                                    ↑
                                      Phase 5 ──────┘  (parallel with Phase 4)
```

**Critical path to first usable app:** Phases 0 → 1 → 2 → 3 → 4

---

## Key Risks

1. **Resolve Parcels API volume (~70K+ calls):** Mitigated by aggressive caching, batching, resume capability.
2. **Group reconciliation quality:** By design, groups are manual. System surfaces candidates, human decides.
3. **Frontend performance with 70K+ rows:** Virtual scrolling + server-side pagination. Never load all records.
4. **Compiler re-run speed:** Target <60 seconds for 95K records. Batch inserts, single transaction.
