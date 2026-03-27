# Cleo Turbo — Frontend & App Plan

> Plan for the web application layer: FastAPI backend, SQLite database, React frontend,
> and multi-user authentication. This sits on top of the data engine and reads from
> the database that the Compiler populates.
>
> Source of truth for terminology and data model: `docs/definitions.md`
> Source of truth for design system: `docs/styling-reference.md`
> Source of truth for the problem being solved: `docs/workflows.md`

---

## Architecture

```
clean-data/                         The Compiler              SQLite (cleo.db)
├── rt/*.json         ──────────→   reads JSON,    ──────────→  Derived tables
├── parcels/*.json                  assigns IDs,                (rebuilt on compile)
├── osm/*.json                      writes to DB                   +
└── geowarehouse/*.json                                         CRM tables
                                                                (persistent, never rebuilt)
                                                                   │
                                                                   ▼
                                                              FastAPI backend
                                                              (reads/writes SQLite)
                                                                   │
                                                                   ▼
                                                              React SPA
                                                              (served as static files)
                                                                   │
                                                                   ▼
                                                              Browser
                                                              (Brandon, wife, partner)
```

The web app never reads JSON files directly. Everything goes through SQLite.

---

## Tech Stack

### Backend
```
FastAPI                — API framework
Uvicorn                — ASGI server
SQLite + WAL mode      — Database (concurrent reads while pipeline writes)
Pydantic v2            — Request/response validation
python-jose            — JWT tokens
passlib[bcrypt]        — Password hashing
```

### Frontend
```
React 18 + TypeScript  — UI framework
Vite                   — Build tool
@radix-ui/themes       — Component library (jade accent, slate gray)
@tanstack/react-table  — Data tables
@tanstack/react-virtual — Virtual scrolling (70K+ rows)
@phosphor-icons/react  — Icons
Tailwind CSS           — Utility styles
react-router-dom       — Routing
react-map-gl + maplibre-gl — Map view
recharts               — Charts
clsx + tailwind-merge  — Class merging (cn() utility)
```

### Design System
WorkOS Dashboard style — defined in `docs/styling-reference.md`. Covers:
- Untitled Sans font (Regular 400, Medium 500)
- CSS grid layout (220px sidebar + 56px header + main area)
- Radix color tokens (slate gray scale, jade accent)
- Elevation shadows (4 levels)
- Card, table, nav, badge, drawer, chart patterns
- No dark mode — light only

---

## Database

### Overview

Single SQLite file (`data/cleo.db`). Two categories of tables:

1. **Derived tables** — rebuilt by the Compiler from clean-data/. IDs persist via
   reconciliation (ARN → PRO_ ID, name fingerprint → CON_ ID, etc.)
2. **CRM tables** — persistent, user-curated. Never touched by the Compiler.

WAL mode enables concurrent reads (web app serving 3 users) while the Compiler
writes.

### Derived Tables (rebuilt by Compiler)

**`properties`** — One per parcel (ARN). The Compiler groups transactions by ARN.
```
id              TEXT PRIMARY KEY    -- PRO_NNNNN
arn             TEXT UNIQUE         -- 20-digit (stable anchor)
display_address TEXT                -- Best address from most recent transaction
city            TEXT
region          TEXT
postal          TEXT
acreage         REAL
legal_description TEXT
current_owner_name TEXT             -- Buyer party name from most recent transaction
most_recent_sale_date TEXT
most_recent_sale_price INTEGER
transaction_count INTEGER
lat             REAL
lng             REAL
parcel_geojson  TEXT                -- GeoJSON polygon from clean-data/parcels/
```

**`transactions`** — One per RT source ID. Linked to property via ARN.
```
source_id       TEXT PRIMARY KEY    -- RT196880
property_id     TEXT                -- PRO_ FK (null if no ARN)
arn             TEXT
sale_date       TEXT
sale_price      INTEGER
transaction_note TEXT
display_address TEXT
city            TEXT
region          TEXT
postal          TEXT
seller_parties  TEXT                -- JSON array of party name strings
buyer_parties   TEXT                -- JSON array of party name strings
seller_phone    TEXT
buyer_phone     TEXT
description     TEXT
acreage         REAL
pin             TEXT
legal_description TEXT
consideration_json TEXT             -- Full consideration as JSON
broker_json     TEXT                -- Full broker data as JSON
photos_json     TEXT                -- Photo URLs as JSON
source_folder   TEXT
```

**`contacts`** — One per unique person (name fingerprint).
```
id              TEXT PRIMARY KEY    -- CON_NNNNN
name_fingerprint TEXT UNIQUE        -- UPPERCASE first+last (stable anchor)
first_name      TEXT
last_name       TEXT
display_name    TEXT
phone           TEXT                -- Best known phone from transactions
email           TEXT                -- CRM enrichment
mobile          TEXT                -- CRM enrichment
job_title       TEXT                -- Most recent title
company_name    TEXT                -- Display name of current group
current_group_id TEXT               -- GRP_ FK
status          TEXT DEFAULT 'pool' -- 'pool' or 'engaged'
source          TEXT DEFAULT 'transaction'
transaction_count INTEGER
first_seen_date TEXT
last_seen_date  TEXT
hubspot_id      TEXT
```

**`groups`** — One per unique company/entity (normalized name).
```
id              TEXT PRIMARY KEY    -- GRP_NNNNN
display_name    TEXT
normalized_name TEXT UNIQUE         -- Stable anchor
status          TEXT DEFAULT 'pool' -- 'pool' or 'engaged'
property_count  INTEGER
transaction_count INTEGER
contact_count   INTEGER
hq_address      TEXT                -- CRM enrichment
website         TEXT                -- CRM enrichment
hubspot_id      TEXT
```

**`group_names`** — All known name variants for a group.
```
group_id        TEXT                -- GRP_ FK
name            TEXT
normalized      TEXT
source_id       TEXT                -- Which transaction this name came from
```

**`transaction_parties`** — Links contacts and groups to transactions.
```
source_id       TEXT                -- RT source_id FK
contact_id      TEXT                -- CON_ FK
group_id        TEXT                -- GRP_ FK
side            TEXT                -- 'seller' or 'buyer'
party_name      TEXT                -- Legal entity name on this transaction
contact_title   TEXT                -- attn, pres, vp, etc.
phone           TEXT
```

### CRM Tables (persistent, never rebuilt)

**`deals`**
```
id              TEXT PRIMARY KEY    -- DEAL_NNNNN
name            TEXT
stage           TEXT                -- prospecting, nurturing, negotiating,
                                   -- under_contract, firm, closed, lost
amount          INTEGER
close_date      TEXT
property_id     TEXT                -- PRO_ FK
group_id        TEXT                -- GRP_ FK
deal_owner      TEXT                -- 'brandon' or 'jamie'
description     TEXT
next_step       TEXT
priority        TEXT
lost_reason     TEXT
hubspot_id      TEXT
```

**`lists`** + **`list_members`**
```
lists: id, name, description
list_members: list_id, member_type (property|contact|group), member_id
```

**`group_contacts`** — Manual association history.
```
group_id, contact_id, is_current (1|0), role, notes
```

**`contact_notes`** + **`group_notes`**
```
contact_id|group_id, note, created_at
```

### System Tables

**`users`** — 3 users: Brandon (admin), wife (editor), partner (editor).
```
id, username, password_hash, display_name, role (admin|editor)
```

**`audit_log`** — Every CRM mutation logged.
```
id, user_id, action, entity_type, entity_id, details_json, created_at
```

**`app_meta`** — ID counters, compile timestamps, etc.
```
key, value, updated_at
```

### FTS5 Search

```sql
CREATE VIRTUAL TABLE properties_fts USING fts5(display_address, city, region);
CREATE VIRTUAL TABLE contacts_fts USING fts5(display_name, first_name, last_name, phone, company_name);
CREATE VIRTUAL TABLE groups_fts USING fts5(display_name);
CREATE VIRTUAL TABLE group_names_fts USING fts5(name);
```

---

## Authentication

JWT + bcrypt. 3 users. Simple.

- `POST /api/auth/login` — email + password → JWT token (72-hour expiry)
- `GET /api/auth/me` — current user info
- Token stored in localStorage, injected in all API calls via `Authorization: Bearer {token}`
- `ProtectedRoute` component wraps all routes except `/login`

### Roles

| Role | Views | CRM (edit) | Pipeline/Admin |
|------|-------|------------|----------------|
| editor | All | All | No |
| admin | All | All | Yes |

### User Management (CLI)

```
cleo admin user create brandon@email.com "Brandon" --role admin
cleo admin user create wife@email.com "Name" --role editor
cleo admin user create partner@email.com "Jamie" --role editor
```

---

## API Routes

### Properties
```
GET  /api/properties              — Paginated browse + filters (city, region, price range)
GET  /api/properties/search?q=    — FTS5 search
GET  /api/properties/stats        — Aggregate counts for dashboard
GET  /api/properties/filters      — Available filter values (cities, regions)
GET  /api/properties/{id}         — Full detail + transaction history
```

### Transactions
```
GET  /api/transactions            — Paginated browse + filters
GET  /api/transactions/search?q=  — FTS5 search
GET  /api/transactions/{source_id} — Full detail (seller, buyer, consideration, broker)
```

### Contacts
```
GET    /api/contacts              — Paginated browse + filters (status, group)
GET    /api/contacts/search?q=    — FTS5 search
GET    /api/contacts/{id}         — Full detail (transactions, groups, phones)
PATCH  /api/contacts/{id}         — Update CRM fields (email, phone, notes)
POST   /api/contacts/{id}/promote — Flip status to engaged
```

### Groups
```
GET    /api/groups                — Paginated browse + filters (status, property count)
GET    /api/groups/search?q=      — FTS5 search
GET    /api/groups/{id}           — Full detail (known names, contacts, transactions, properties)
PATCH  /api/groups/{id}           — Update CRM fields
POST   /api/groups/{id}/promote   — Flip status to engaged
POST   /api/groups/{id}/contacts  — Link a contact
```

### CRM
```
GET    /api/deals                 — List deals (filter by stage)
POST   /api/deals                 — Create deal
PATCH  /api/deals/{id}            — Update deal
GET    /api/lists                 — All lists
POST   /api/lists                 — Create list
POST   /api/lists/{id}/members    — Add member
DELETE /api/lists/{id}/members/{type}/{id} — Remove member
POST   /api/contacts/{id}/notes   — Add note
POST   /api/groups/{id}/notes     — Add note
```

### Map
```
GET  /api/map/properties          — Properties in bounding box (clustered at zoom)
GET  /api/map/parcels/{arn}       — Parcel polygon GeoJSON
```

### Admin
```
GET  /api/admin/status            — DB size, record counts, last compile time
GET  /api/admin/users             — List users (admin only)
POST /api/admin/users             — Create user (admin only)
```

### Design Principles
- One router per domain
- All queries are SQL — no loading JSON files
- Pagination on every list endpoint (default 25, max 100)
- Dependency injection: DB connection + current user via FastAPI `Depends()`
- App factory under 50 lines — all logic lives in routers

---

## Frontend Pages

### What Connects to the Prospecting Workflow

From `docs/workflows.md`, the 8-step manual loop maps to these pages:

| Step | Manual Process | Cleo Page |
|------|---------------|-----------|
| 1. Pick a target | Zoom map, find unworked plazas | **Map**, **Properties** |
| 2. Research parcel | GeoWarehouse lookup | **Property Detail** (parcel + assessment data) |
| 3. Find transaction | Search Realtrack by address | **Transactions**, **Property Detail** (history) |
| 4. Size up portfolio | Search by contact/corp name | **Group Detail** (all properties + transactions) |
| 5. Find contact info | Google, LinkedIn, Canada411 | **Contact Detail** (phone, email, CRM fields) |
| 6. Make contact | Call, email, letter | **Contact Detail** (log activity, track outreach) |
| 7. Log and track | Google Earth pins, HubSpot | **Deals**, **Lists**, notes on contacts/groups |
| 8. Repeat | Find next unworked property | **Map** (filter: unworked) |

### Page List

**Dashboard** — Overview stats, recent transactions, pipeline summary.
- Total properties, transactions, contacts, groups
- Engaged vs pool counts
- Recent transactions table (last 30 days)
- Deal pipeline summary (count per stage)

**Properties** — Browse and search the property registry.
- Data table: address, city, latest sale date, latest price, owner, transaction count
- Filters: city, region, price range
- FTS5 search bar
- Click row → Property Detail
- Virtual scrolling for 70K+ rows

**Property Detail** — Everything about one parcel.
- Address, city, ARN, PIN, acreage, legal description
- Parcel polygon on mini-map
- Transaction history (chronological table)
- Current owner (group link)
- Tenants (future: OSM/Brand data)
- Actions: create deal, add to list

**Transactions** — Browse all historical transactions.
- Data table: date, address, city, price, seller, buyer
- Filters: date range, city, price range
- Search
- Click row → Transaction Detail

**Transaction Detail** — Full transaction record.
- Seller side: party names, contacts (linked to CON_), phone, address, law firms
- Buyer side: same structure
- Property link (if ARN resolved)
- Sale details: date, price, consideration breakdown
- Broker info
- Description, photos
- Site: PIN, ARN, acreage, legal description

**Contacts** — Browse all contacts (pool + engaged).
- Data table: name, phone, company, status badge, transaction count
- Filter: status (pool/engaged), group
- Search
- Click row → Contact Detail

**Contact Detail** — One person across all their transactions.
- Status badge (pool/engaged) + promote button
- Contact info: phone, email, mobile (editable for engaged)
- Current group association
- Transaction history: every transaction they appear on, which side, which company
- Group history: current and former associations
- Notes section
- Actions: promote, edit fields, add note, create deal

**Groups** — Browse all groups (pool + engaged).
- Data table: name, status, property count, contact count, transaction count
- Filter: status, minimum property count
- Search
- Click row → Group Detail

**Group Detail** — One company/entity across all its activity.
- Status badge + promote button
- All known names
- Associated contacts (current and former)
- All transactions where any group name appears
- All properties (via transactions where group is buyer)
- Portfolio summary: total value, property types, geographic spread
- Notes section
- Actions: promote, link contacts, add note, create deal

**Map** — Geographic view for prospecting.
- MapLibre GL base map
- Property markers with clustering at zoom levels
- Click marker → mini card → link to Property Detail
- Parcel polygon overlay (load on zoom)
- Layer toggles: properties, parcels, (future: POIs, brands)
- Filter: city, price range, worked/unworked

**Deals** — Pipeline management.
- Kanban board: columns = stages (Prospecting → Nurturing → Negotiating → Under Contract → Firm → Closed | Lost)
- Cards show: deal name, property, group, amount
- Drag to change stage
- Click card → deal detail drawer
- Create deal from any property/group/contact page

**Lists** — Prospecting target lists.
- List of lists with member counts
- Click → list detail showing all members (properties, contacts, groups)
- Add/remove members
- Create new list

**Admin** (admin role only) — System management.
- Database stats: table counts, DB size, last compile time
- User management: list users, create user
- Trigger compiler re-run

**Login** — Simple email + password form. Redirects to dashboard on success.

---

## Project Structure

```
cleo-turbo/
├── cleo/                          # Python package
│   ├── database/
│   │   ├── schema.py              # DDL — all CREATE TABLE statements
│   │   └── connection.py          # SQLite connection (WAL, foreign keys)
│   ├── compiler/
│   │   ├── reader.py              # Read clean-data/ JSON files
│   │   ├── reconciler.py          # ID generation + persistence (PRO_, CON_, GRP_)
│   │   └── writer.py              # Write derived tables to SQLite
│   └── web/
│       ├── app.py                 # FastAPI app factory (<50 lines)
│       ├── auth.py                # JWT auth + login endpoint
│       ├── deps.py                # Dependency injection (db, current user)
│       └── routes/
│           ├── properties.py
│           ├── transactions.py
│           ├── contacts.py
│           ├── groups.py
│           ├── crm.py             # Deals, lists, notes
│           ├── map.py
│           └── admin.py
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.js         # From styling-reference.md
│   ├── postcss.config.js
│   ├── index.html
│   └── src/
│       ├── main.tsx               # Radix Theme wrapper
│       ├── index.css              # @font-face, CSS tokens, Radix overrides
│       ├── App.tsx                # Router + auth context + layout
│       ├── api/
│       │   └── client.ts          # fetchApi<T>() with JWT injection
│       ├── hooks/
│       │   ├── useAuth.ts         # Auth context (login, logout, token)
│       │   └── usePagination.ts
│       ├── components/
│       │   ├── layout/            # AppLayout, Sidebar, Header
│       │   ├── ui/                # DataTable, SearchBar, StatusBadge, etc.
│       │   └── crm/               # DealCard, NoteForm, PromoteButton
│       ├── pages/
│       │   ├── LoginPage.tsx
│       │   ├── DashboardPage.tsx
│       │   ├── PropertiesPage.tsx
│       │   ├── PropertyDetailPage.tsx
│       │   ├── TransactionsPage.tsx
│       │   ├── TransactionDetailPage.tsx
│       │   ├── ContactsPage.tsx
│       │   ├── ContactDetailPage.tsx
│       │   ├── GroupsPage.tsx
│       │   ├── GroupDetailPage.tsx
│       │   ├── MapPage.tsx
│       │   ├── DealsPage.tsx
│       │   ├── ListsPage.tsx
│       │   └── AdminPage.tsx
│       ├── lib/
│       │   ├── theme.ts           # Radix theme constants, chart colors
│       │   └── utils.ts           # cn(), formatCurrency(), formatDate()
│       └── types/
│           └── index.ts           # Shared TypeScript types
├── data/
│   └── cleo.db                    # SQLite database
└── docs/
    ├── definitions.md
    ├── styling-reference.md
    └── this file
```

---

## Build Order

### Step 1: Database + Compiler

Build the bridge from clean-data/ JSON to SQLite.

- `cleo/database/schema.py` — all CREATE TABLE statements
- `cleo/database/connection.py` — WAL mode, foreign keys, busy timeout
- `cleo/compiler/reader.py` — read clean-data/rt/*.json
- `cleo/compiler/reconciler.py` — ID assignment (ARN → PRO_, fingerprint → CON_, name → GRP_)
- `cleo/compiler/writer.py` — populate derived tables
- CLI: `cleo db init`, `cleo compiler run`

**Verify:** Run compiler on 95K clean records. Check row counts.

### Step 2: API Foundation

Stand up FastAPI with auth and the first read endpoints.

- `cleo/web/app.py` — app factory
- `cleo/web/auth.py` — JWT login
- `cleo/web/deps.py` — DB + user injection
- `cleo/web/routes/properties.py` — browse, search, detail
- `cleo/web/routes/transactions.py` — browse, search, detail
- CLI: `cleo web serve`, `cleo admin user create`

**Verify:** Hit all endpoints with curl. Auth works. Pagination works. Search returns results.

### Step 3: Frontend Shell

Scaffold the React app with the design system and first pages.

- Vite + React + TypeScript scaffold
- Wire up design system (Radix Theme, Tailwind, fonts, CSS tokens)
- Auth flow (login page, JWT storage, protected routes)
- Layout (sidebar + header + main area)
- Properties page (data table, filters, search)
- Property Detail page (transaction history, site info)
- Transactions page + Transaction Detail page
- Dashboard (basic stats)

**Verify:** Login → browse properties → click into detail → see transactions. All 3 users work.

### Step 4: Contacts, Groups, Map

- Contacts + Groups API routes
- Contacts page + detail
- Groups page + detail
- Map page (property markers, parcel polygons, clustering)

**Verify:** Navigate from property → contact → group and back. Map loads with markers.

### Step 5: CRM

- Pool → Engaged promotion
- Deals CRUD + pipeline board
- Lists CRUD
- Notes on contacts/groups
- Audit logging

**Verify:** Full workflow: find contact → promote → create deal → add to list.

### Step 6: HubSpot + Admin + Deploy

- HubSpot sync for engaged contacts/groups
- Admin page (stats, users, compile trigger)
- Deploy to Hetzner VPS (Caddy + systemd + Litestream)

---

## What's NOT in Scope (for now)

- Dark mode — light only per styling reference
- Mobile-responsive layout — desktop-first (3 users on desktop)
- Real-time updates / websockets — not needed for 3 users
- File uploads — no use case yet
- Email sending — HubSpot handles outbound email
- Drip campaigns — HubSpot handles sequences
- Call logging — Productive.ai → HubSpot handles this
