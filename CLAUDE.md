# Cleo Turbo

Cleo Turbo is a commercial real estate data platform for Ontario. It ingests property transaction data from Realtrack, parcel/ownership data from GeoWarehouse, and branded POI locations from OpenStreetMap, then compiles everything into a single SQLite database that powers a React frontend and FastAPI backend. The app is a prospecting tool for commercial realtors — the goal is to centralize property research, owner lookup, and deal tracking that currently requires bouncing between 8+ disconnected tools.

## Project Structure

```
cleo-turbo/
├── cleo/                    # Python backend
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
│   ├── rt/                  # Realtrack engine (extract → classify → normalize → resolve → compile)
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
deals, lists, list_members, group_contacts, contact_notes, group_notes

**System tables:**
users, audit_log, app_meta, data_issues

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
```

## Data Pipeline Overview

```
raw-data/rt/     → engines/rt/  (extract → classify → normalize → resolve → compile) → clean-data/rt/
raw-data/gw/     → engines/gw/  (ingest → parse → normalize → resolve → compile)     → clean-data/gw/
(imported from V3) → engines/osm/ (import)                                             → clean-data/osm/

clean-data/{rt,gw,osm}/ → cleo/compiler/ (reader → reconciler → writer) → data/cleo.db
```

Each engine stage reads from the previous stage's output folder and writes to its own folder. Stages are independent — you can re-run any stage without affecting others.

The GW watcher is special: it processes new files AND does incremental DB updates (bypasses full compiler). This is intentional — don't refactor it to go through the compiler.

## Reference Docs

- `docs/definitions.md` — Canonical terminology reference. Still accurate. Read this first if you're confused about any term.
- `docs/workflows.md` — The real-world prospecting workflows Cleo is solving. This is the "why" behind the system. Still accurate.
- `docs/build-plan.md` — Historical. Everything listed as "needs to be built" is now built. Useful for understanding original intent, but don't treat TODOs in it as current.
- `docs/styling-reference.md` — Design system reference (WorkOS Dashboard style). Still the target aesthetic.
- `docs/frontend-plan.md` — Original frontend implementation plan. The app has evolved since — use the actual code as the reference for current patterns.

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
