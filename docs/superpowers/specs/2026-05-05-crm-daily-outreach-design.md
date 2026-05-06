# CRM Daily-Outreach Design (Phase 1)

**Date:** 2026-05-05
**Branch context:** built on top of the current `feat/group-discovery-algorithm` baseline; CRM work is independent of discovery and can branch from `main`.
**Status:** approved for implementation planning

## Goal

Brandon and Jamie need to use Cleo daily for outreach prospecting. Today the CRM scaffolding exists (Deals, Lists, Opps, Mandates, Activities, Pipeline) but key buttons are dead, there's no per-user "favourites" surface, and there's no shared engagement/attribution model.

The Phase 1 outcome: on a property or contact or group, one click each to **star for later**, **log a touch**, **add to a list**, or **create a deal**. A personal `/queue` page lists everything you've starred. Activities auto-engage contacts/groups (pool → engaged) and auto-clear your stars on entities you just touched. Teammate engagement is visible everywhere via attribution and a queue badge.

Phase 2 (multi-entity activity linking, row-level stars, list-page treatments) and Phase 3 (HubSpot import) are explicitly deferred — see Section 7.

## Background

**Existing CRM scaffolding:**
- Routes: `deals.py`, `lists.py`, `notes.py`, `activities.py`, `sell_opportunities.py`, `buy_mandates.py`
- Pages: `DealsPage`, `DealDetailPage`, `ListsPage`, `ListDetailPage`, `OpportunitiesPage`, `SellOpportunityDetailPage`, `BuyMandateDetailPage`, `Pipeline*`
- Components: `LogActivityDialog`, `ActivityFeed`, `CreateBuyMandateDrawer`, `CreateSellOppDialog`, `CrmContext`, `CrmDrawer`
- Engagement: `contacts.status` and `groups.status` already use values `'pool'` / `'engaged'`. The Contacts list already filters by Engaged/Pool. A manual "Engage" button exists.

**Key gaps:**
- `PropertyDetailPage` "Add to List" and "Create Deal" buttons are dead (no `onClick`)
- `ContactDetailPage` has no Add to List / Create Deal / Log Activity surface
- Activities API does not allow `entity_type='property'`
- No per-user concept anywhere — `lists` are effectively team-shared, no stars, no per-user queue
- No first/last contacted attribution surfaces
- Activities `created_by` is a loose TEXT string, not a user FK

**Domain context:** `docs/workflows.md` step 7 ("Log and track") is the unsolved part of Brandon's manual prospecting loop. Today outreach is fragmented across HubSpot (emails), Productive.ai (calls), Google Earth (pins). Cleo's CRM is meant to unify this — Phase 1 makes manual logging usable; Phase 3 imports HubSpot/Productive history into the same activity log.

## Architecture decisions (locked)

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | Activities link to **multi-entity** (optional `contact_id` + `property_id` + `group_id` FKs) | A touch about Peter re: 240 King George re: DH Management is one event; we want to surface it on all three entities' activity feeds. Phase 1 only populates the primary entity's FK; Phase 2 wires the typeahead. Schema is built once. |
| 2 | **Per-user stars** + **per-user/shared lists** | Standard team-CRM pattern. Stars are private "to-do"; lists have explicit scope (personal default, shared opt-in). |
| 3 | Personal lists are **truly hidden** from other users (404 on direct access, missing from list responses) | No leakage of a teammate's working notes. |
| 4 | Shared lists are **team-editable** for members; only the owner can rename/delete | Otherwise sharing is just an awkward broadcast. |
| 5 | **No collision blocking** on Deals / Sell Opps / Buy Mandates | Two-person team; trust + visibility > enforcement. The team self-coordinates by reading the activity log. |
| 6 | "**Engaged**" is binary (pool → engaged), no decay | Brandon's mental model: engaged means "we've brought them out of the pool, they're a Contact of ours." Existing schema already does this for contacts and groups. |
| 7 | Properties have **no engagement state** | Properties aren't people. They get attribution + activity feed only. |
| 8 | **Auto-engage on activity log** | Logging a touch on a `pool` contact/group flips it to `engaged` automatically — saves a click. |
| 9 | Manual "Engage" button writes a **synthetic `note` activity** | Keeps the activity log as the single source of truth for attribution. Idempotent. |
| 10 | **Star auto-remove on own engagement; flag-and-keep on teammate engagement** | When I log an activity referencing a starred entity, my star removes (intent satisfied). Teammate's engagement leaves my star alone but shows an "Engaged by Jamie" badge in my queue. |
| 11 | `happened_at` separate from `created_at` on activities | So future HubSpot imports preserve the actual contact date, not the import date. |
| 12 | Personal Queue is a **single page with type filters**, not three queues | One mental object: "things I plan to touch." |
| 13 | Quick Action Bar component is **shared across Property + Contact + Group detail pages** | One UX pattern, three surfaces. |
| 14 | **No row-level stars in Phase 1** | Detail-page stars cover the daily loop; row-level is a refinement after we feel the friction. |
| 15 | HubSpot import is **out of scope for this spec** | Schema accommodates (source/external_id/happened_at/created_by_user_id) but the import itself is its own design. |

## Section 1 — Data Model & Schema

**Migration file:** `cleo/database/migrations/020_crm_daily_outreach.py` (next sequential number after `019_address_canonicalization.py`).

### 1.1 New table: `user_stars`

CRM table — persistent, never rebuilt by compiler.

```sql
CREATE TABLE user_stars (
  user_id      INTEGER NOT NULL REFERENCES users(id),
  entity_type  TEXT    NOT NULL CHECK(entity_type IN ('contact','property','group')),
  entity_id    TEXT    NOT NULL,
  starred_at   TEXT    DEFAULT (datetime('now')),
  PRIMARY KEY (user_id, entity_type, entity_id)
);
CREATE INDEX idx_user_stars_user   ON user_stars(user_id);
CREATE INDEX idx_user_stars_entity ON user_stars(entity_type, entity_id);
```

### 1.2 Modified: `lists`

```sql
ALTER TABLE lists ADD COLUMN owner_user_id INTEGER REFERENCES users(id);
ALTER TABLE lists ADD COLUMN scope TEXT NOT NULL DEFAULT 'personal';
-- Backfill: existing lists were team-shared in the pre-scope model
UPDATE lists SET scope = 'shared' WHERE owner_user_id IS NULL;
```

- `scope='personal'` — visible only to `owner_user_id`. New rows default to personal with `owner_user_id = current_user`.
- `scope='shared'` — visible to all users; member adds/removes by anyone; metadata edits by owner only.

### 1.3 Modified: `activities`

```sql
ALTER TABLE activities ADD COLUMN created_by_user_id INTEGER REFERENCES users(id);
ALTER TABLE activities ADD COLUMN source      TEXT NOT NULL DEFAULT 'manual';
ALTER TABLE activities ADD COLUMN external_id TEXT;
ALTER TABLE activities ADD COLUMN happened_at TEXT;
ALTER TABLE activities ADD COLUMN contact_id  TEXT REFERENCES contacts(id);
ALTER TABLE activities ADD COLUMN property_id TEXT REFERENCES properties(id);
ALTER TABLE activities ADD COLUMN group_id    TEXT REFERENCES groups(id);

UPDATE activities SET happened_at = created_at WHERE happened_at IS NULL;

-- Direct primary-entity backfill
UPDATE activities SET contact_id = entity_id WHERE entity_type = 'contact';
UPDATE activities SET group_id   = entity_id WHERE entity_type = 'group';
-- (no existing 'property' rows since the route blocks it; nothing to backfill)

-- Parent-record backfill for sell_opp / buy_mandate / deal entity types
UPDATE activities SET
  contact_id  = (SELECT seller_contact_id FROM sell_opportunities WHERE id = activities.entity_id),
  group_id    = (SELECT seller_group_id   FROM sell_opportunities WHERE id = activities.entity_id),
  property_id = (SELECT property_id       FROM sell_opportunities WHERE id = activities.entity_id)
WHERE entity_type = 'sell_opportunity';

UPDATE activities SET
  contact_id = (SELECT contact_id FROM buy_mandates WHERE id = activities.entity_id),
  group_id   = (SELECT group_id   FROM buy_mandates WHERE id = activities.entity_id)
WHERE entity_type = 'buy_mandate';

UPDATE activities SET
  property_id = (SELECT property_id FROM deals WHERE id = activities.entity_id),
  group_id    = (SELECT group_id   FROM deals WHERE id = activities.entity_id)
WHERE entity_type = 'deal';

CREATE INDEX idx_activities_contact  ON activities(contact_id);
CREATE INDEX idx_activities_property ON activities(property_id);
CREATE INDEX idx_activities_group    ON activities(group_id);
CREATE INDEX idx_activities_user     ON activities(created_by_user_id);
CREATE INDEX idx_activities_dedupe   ON activities(source, external_id);
```

The legacy `created_by` TEXT column stays for back-compat — display logic prefers the FK-resolved name and falls back to TEXT. No backfill of historical TEXT → user FKs (too fragile).

### 1.4 No denormalized `engaged_at` / `last_engaged_by_user_id` columns

All attribution is derived from `activities` joined to `users`. Indexes from 1.3 make this cheap.

### 1.5 No engagement state on properties

`properties` table is unchanged. Property pages show first/last contacted attribution + activity feed; no badge, no chip filter.

### 1.6 CLAUDE.md update

Add `user_stars` to the CRM-tables list in `CLAUDE.md` § "Database: Derived vs CRM Tables" so future compiler work doesn't drop it.

## Section 2 — Backend API

### 2.1 New router: `stars.py`

```
GET    /api/stars                                     → my stars (current user only); enriched with name/detail
                                                        + team_activity field per row (see 2.1.2)
                                                        optional ?entity_type=contact|property|group filter
POST   /api/stars                                     → body: { entity_type, entity_id }; idempotent (PK conflict no-op)
DELETE /api/stars/{entity_type}/{entity_id}           → unstar
GET    /api/stars/check?entity_type=&entity_id=       → { starred: bool }
```

**2.1.1 Enrichment** — each star row in the GET response includes:
- `name` — from `contacts.display_name` / `properties.display_address` / `groups.display_name`
- `detail` — secondary line (city, brand stem, member count)
- `starred_at`

**2.1.2 `team_activity`** — null unless a teammate engaged the entity *after* you starred it. When non-null:
```json
{
  "by_user_id": 2,
  "by_user_name": "Jamie",
  "happened_at": "2026-05-04T14:22:11",
  "activity_type": "call",
  "outcome": "connected"
}
```
Computed as `MAX(happened_at) FROM activities WHERE {fk}=entity_id AND created_by_user_id != :me AND happened_at > user_stars.starred_at`. Pre-star history doesn't count.

**2.1.3 Audit log** — star/unstar via `log_action(db, user, "star.add" / "star.remove", entity_type, entity_id, …)` (existing pattern from `deals.py`).

### 2.2 Modified router: `lists.py`

- `GET /api/lists` — `WHERE scope='shared' OR owner_user_id=:me`
- `POST /api/lists` — accepts `scope` (default `'personal'`); sets `owner_user_id = current_user`
- `PATCH /api/lists/{id}` — only `owner_user_id` may change name/description; otherwise 403
- `DELETE /api/lists/{id}` — owner only; 403 otherwise
- `POST /api/lists/{id}/members` and `DELETE /api/lists/{id}/members/{member_type}/{member_id}` — anyone with read access; 404 on personal lists owned by another user (truly hidden, no info leak)
- `GET /api/lists/{id}` — 404 if `scope='personal' AND owner_user_id ≠ :me`
- **New:** `GET /api/lists/membership?member_type=&member_id=` — returns `[{ list_id, list_name, scope }]` for the current user's accessible lists that contain this member. Powers the AddToListDrawer's pre-checked state.

### 2.3 Modified router: `activities.py`

Five behavior changes:

**1. Add `'property'` to `ENTITY_TYPES`.** One-line whitelist update.

**2. Write `created_by_user_id`.** Pull from `user["sub"]` (the JWT payload field that holds `users.id` — confirmed in `cleo/web/auth.py:create_token` and the recent `brands.py` fix at commit `14c2c4b`). Keep writing the legacy `created_by` TEXT field alongside (populated as today: `user.get("display_name", user.get("username"))` — note that `display_name` isn't currently in the JWT, so today this falls back to `username`; the FK is the canonical going forward).

**3. Populate primary-entity FKs.** New helper `_populate_entity_fks(body, db) -> (contact_id, property_id, group_id)`:
- `entity_type='contact'`  → `contact_id = entity_id`
- `entity_type='property'` → `property_id = entity_id`
- `entity_type='group'`    → `group_id = entity_id`
- `entity_type='sell_opportunity'` → look up the opp; copy `seller_contact_id`, `seller_group_id`, `property_id`
- `entity_type='buy_mandate'` → look up the mandate; copy `contact_id`, `group_id`
- `entity_type='deal'` → look up the deal; copy `property_id`, `group_id`

**4. Auto-engage rule.** Inside the same transaction as the insert:
```sql
UPDATE contacts SET status='engaged', last_engaged_date=? WHERE id=? AND status='pool'
UPDATE groups   SET status='engaged' WHERE id=? AND status='pool'
```
Only fires when the corresponding FK is non-null. The `last_engaged_date` column already exists on `contacts`.

**5. Star auto-remove rule.** Inside the same transaction:
```sql
DELETE FROM user_stars
WHERE user_id = :me
  AND ((entity_type='contact'  AND entity_id = :contact_id)
    OR (entity_type='property' AND entity_id = :property_id)
    OR (entity_type='group'    AND entity_id = :group_id))
```
Best-effort; only the current user's stars are touched. Teammate stars on the same entity are untouched.

**Phase 2 hook (designed now, not built):** body accepts optional `linked_contact_id`, `linked_property_id`, `linked_group_id`. Phase 1 frontend doesn't send these; if the route receives them, it populates whichever FK is not already set by the primary entity (no double-write).

### 2.4 Modified routers: `contacts.py` + `groups.py` — synthetic Engage activity

The existing `POST /api/contacts/{id}/engage` and `POST /api/groups/{id}/engage` endpoints, after flipping `status='engaged'`, also insert:
```sql
INSERT INTO activities (entity_type, entity_id, activity_type, source, summary,
                        created_by, created_by_user_id, contact_id_or_group_id, happened_at)
VALUES (:entity_type, :id, 'note', 'manual', 'Marked engaged', :user_name, :user_id, :id, datetime('now'))
```

Idempotent: if `status` is already `'engaged'` at endpoint entry, do nothing — no status update, no synthetic activity.

### 2.5 New endpoints: `/api/{contacts|properties|groups}/{id}/attribution`

Each route joins `activities.created_by_user_id → users.id` and returns `users.display_name` as `user_name`. The `users` table has `id`, `username`, `display_name`, `role` columns (verified in `cleo/database/schema.py:613`).

Each returns:
```json
{
  "first_contacted": { "user_id": 2, "user_name": "Jamie", "happened_at": "2024-03-12T09:14:00",
                       "activity_type": "call", "outcome": "connected" },
  "last_contacted":  { "user_id": 1, "user_name": "Brandon", "happened_at": "2026-05-05T11:22:00",
                       "activity_type": "email", "outcome": "email_sent" },
  "total_activities": 14,
  "by_user": [
    { "user_id": 1, "user_name": "Brandon", "count": 9 },
    { "user_id": 2, "user_name": "Jamie",   "count": 5 }
  ]
}
```

Returns `{ first_contacted: null, last_contacted: null, total_activities: 0, by_user: [] }` when no activities exist for the entity.

### 2.6 Router registration

`cleo/web/app.py` gets one new line after the existing CRM router includes:
```python
from .routes.stars import router as stars_router
app.include_router(stars_router, prefix="/api/stars", tags=["stars"])
```

### 2.7 Backend file inventory

- New: `cleo/web/routes/stars.py` (~120 lines), `cleo/database/migrations/020_crm_daily_outreach.py`
- Modified: `cleo/web/routes/activities.py`, `cleo/web/routes/lists.py`, `cleo/web/routes/contacts.py`, `cleo/web/routes/groups.py`, `cleo/web/routes/properties.py` (attribution endpoint), `cleo/web/app.py`, `CLAUDE.md`

## Section 3 — Frontend: Quick Action Bar (shared component)

### 3.1 `frontend/src/components/crm/QuickActionBar.tsx`

```tsx
interface QuickActionBarProps {
  entityType: 'contact' | 'property' | 'group';
  entityId: string;
  entityName: string;
  onCreateSellOpp?: () => void;     // Property only
  onCreateBuyMandate?: () => void;  // Contact + Group only
}
```

Renders, left to right:
- **⭐ Star/Unstar** — `<StarButton>` (3.4); fills jade when starred
- **📝 Log Activity** — opens existing `LogActivityDialog` with `entityType` + `entityId` pre-bound
- **📋 Add to List** — opens `AddToListDrawer` (3.2)
- **💼 Create Deal** — opens `CreateDealDrawer` (3.3)
- **🏷️ Sell Opportunity** (Property only) — calls `onCreateSellOpp`
- **🤝 Buy Mandate** (Contact + Group only) — calls `onCreateBuyMandate`

Visual: matches existing `PropertyDetailPage` button row — `<Button size="2" variant="soft">`, gap-2. Phosphor icons: `Star`, `NotePencil`, `ListPlus`, `Briefcase`, `Tag`, `Handshake`.

### 3.2 `frontend/src/components/crm/AddToListDrawer.tsx`

Right-side drawer matching existing `CrmDrawer` pattern. On open:
1. `GET /api/lists` — split into "My personal lists" + "Shared lists" sections
2. `GET /api/lists/membership?member_type=&member_id=` — pre-check the boxes for lists this entity is already in

Each list row: checkbox + name + member count + scope badge.
Below: collapsible "+ New list" form with `name`, optional `description`, `scope` toggle (personal default).

Save:
- For each newly-checked list: `POST /api/lists/{id}/members`
- For each newly-unchecked list: `DELETE /api/lists/{id}/members/{type}/{id}`
- Toast: "Added to N lists" or "Updated"

### 3.3 `frontend/src/components/crm/CreateDealDrawer.tsx`

Right-side drawer. Form:
- `name` — required, defaults to `${entityName} — Deal`
- `stage` — Select, defaults `long_shot`
- `amount` — optional integer (CAD)
- `close_date` — optional date
- `priority` — optional Select (`low|medium|high`)
- `description` — TextArea
- `next_step` — TextField
- `deal_owner` — defaults to current user's display name

Pre-bind based on `entityType`:
- `'property'` → `property_id = entityId`
- `'group'`    → `group_id = entityId`
- `'contact'`  → no FK (Deals don't have a contact_id today; out of scope to add)

POST `/api/deals` → on 201, `navigate('/deals/' + response.id)` and close drawer.

### 3.4 `frontend/src/components/crm/StarButton.tsx`

Reusable star toggle. Phase 1 only used inside QuickActionBar; extracted now so Phase 2 row-level stars are a 5-line wiring change per page.

```tsx
interface StarButtonProps {
  entityType: 'contact' | 'property' | 'group';
  entityId: string;
  size?: '1' | '2';
  showLabel?: boolean;
}
```

Self-managing: fetches state via `GET /api/stars/check` on mount, posts/deletes on click, optimistic UI with revert-on-5xx, emits a global `crm-star-changed` event so multiple instances stay in sync.

### 3.5 `frontend/src/components/crm/AttributionStrip.tsx`

```tsx
interface AttributionStripProps {
  entityType: 'contact' | 'property' | 'group';
  entityId: string;
}
```

Calls `GET /api/{type}/{id}/attribution`, renders:
```
First contacted  Jamie · Mar 12 2024 · call → connected
Last contacted   Brandon · today · email → email_sent
14 activities · Brandon (9) · Jamie (5)
```
When `total_activities === 0`, renders a muted `Never contacted` line. Uses existing `formatDate` helper from `lib/utils.ts`.

### 3.6 LogActivityDialog — Phase 1 unchanged

Already accepts `entityType` + `entityId` props. Phase 2 will extend with the contact↔property↔group typeahead.

## Section 4 — Frontend: Page Wiring

### 4.1 `PropertyDetailPage.tsx`

Replace the dead button row at lines 546–548 with:
```tsx
<QuickActionBar
  entityType="property"
  entityId={prop.id}
  entityName={prop.display_address}
  onCreateSellOpp={() => setShowSellOppDialog(true)}
/>
```
Add `<AttributionStrip entityType="property" entityId={prop.id} />` in or near the header.
Add `<ActivityFeed entityType="property" entityId={prop.id} />` as a new card on the page (works once Section 2.3 enables `'property'` in the entity_type whitelist).

### 4.2 `ContactDetailPage.tsx`

Replace the lone Buy Mandate button at line 126 with:
```tsx
<QuickActionBar
  entityType="contact"
  entityId={contact.id}
  entityName={contact.display_name}
  onCreateBuyMandate={() => setShowBuyMandateDialog(true)}
/>
```
Rename the existing "Activity" stats card (line 282) to "Transaction Stats" — it currently mislabels transaction counts as activity. Add a new card below: `<ActivityFeed entityType="contact" entityId={contact.id} />`. Add `<AttributionStrip />` near the existing engaged badge (line 117).

The existing engaged badge logic (`contact.status === 'engaged'`) is unchanged. The new auto-engage rule (Section 2.3) will refresh the same flag without further frontend changes.

### 4.3 `GroupDetailPage.tsx`

Same treatment as Contact: drop in `QuickActionBar` with `entityType='group'`, add `AttributionStrip` near the engaged badge at lines 235–238, add `ActivityFeed`.

### 4.4 No other pages touched in Phase 1

- `/contacts`, `/properties`, `/groups` list pages — no row-level stars, no Properties/Groups Engaged filter chip yet
- `DealDetailPage`, `SellOpportunityDetailPage`, `BuyMandateDetailPage` — already have `ActivityFeed`; no changes

### 4.5 Existing dialogs stay where they are

`CreateSellOppDialog` lives on `PropertyDetailPage`. `CreateBuyMandateDrawer` lives on Contact + Group pages. The bar's right-side button calls back to the page-owned dialog rather than absorbing those dialogs into the shared component.

### 4.6 Types

Add to `frontend/src/types/index.ts`:
```ts
export interface UserStar {
  user_id: number;
  entity_type: 'contact' | 'property' | 'group';
  entity_id: string;
  starred_at: string;
  name?: string;
  detail?: string;
  team_activity?: TeamActivity | null;
}
export interface TeamActivity {
  by_user_id: number;
  by_user_name: string;
  happened_at: string;
  activity_type: string;
  outcome: string | null;
}
export interface ListSummary {
  id: string;
  name: string;
  description: string | null;
  scope: 'personal' | 'shared';
  owner_user_id: number | null;
  owner_name?: string;
  total_members: number;
  member_counts: Record<string, number>;
}
export interface AttributionResponse {
  first_contacted: ContactEvent | null;
  last_contacted: ContactEvent | null;
  total_activities: number;
  by_user: { user_id: number; user_name: string; count: number }[];
}
export interface ContactEvent {
  user_id: number;
  user_name: string;
  happened_at: string;
  activity_type: string;
  outcome: string | null;
}
```

## Section 5 — Frontend: Personal Queue Page

### 5.1 `frontend/src/pages/QueuePage.tsx` at route `/queue`

Per-user surface — current user's stars only. Layout:

```
┌─────────────────────────────────────────────────────────┐
│ Queue                              [N items starred]    │
│ Your personal to-touch list. Star any contact, property,│
│ or group to add it. Items auto-clear when you log an    │
│ activity that references them.                          │
├─────────────────────────────────────────────────────────┤
│ [All] [Contacts] [Properties] [Groups]                  │
├─────────────────────────────────────────────────────────┤
│ ⭐ Peter Vicano                                          │
│    Contact · DH Management · ON                          │
│    Starred 2d ago                                        │
│  ⚠️ Jamie engaged 1d ago — call → connected             │
└─────────────────────────────────────────────────────────┘
```

Behavior:
- Single `GET /api/stars` fetch on mount; client-side type filter (no extra round trips)
- Each row links to `/{contacts|properties|groups}/{id}`
- Each row has hover-revealed inline unstar
- Sort: most recently starred at top
- "⚠️ Engaged by teammate" sub-row appears when `team_activity` is non-null on that row
- Empty state: "Nothing in your queue. Hit the ⭐ on any contact, property, or group to add it here."
- No bulk operations in Phase 1

### 5.2 Sidebar

`frontend/src/components/layout/Sidebar.tsx` (or wherever the nav lives): add "Queue" with `<Star />` icon between Dashboard and Lists. Badge shows count of starred items, refreshes on the global `crm-star-changed` event.

### 5.3 Routing

`App.tsx` gets one new route inside the `<Route element={<AppLayout />}>` block:
```tsx
<Route path="/queue" element={<QueuePage />} />
```
Direct import (not lazy) — small page.

## Section 6 — Cross-cutting rules (the derived semantics)

### 6.1 Engagement state

Stored: `contacts.status`, `groups.status` (existing TEXT columns, values `'pool'` | `'engaged'`).
Properties: no engagement state.

Transition rules:
- **Manual:** `POST /api/contacts/{id}/engage` and `POST /api/groups/{id}/engage` flip pool→engaged and insert a synthetic `note` activity (Section 2.4).
- **Auto:** `POST /api/activities` whose resolved `contact_id` or `group_id` references a `pool` entity flips it to `engaged` in the same transaction (Section 2.3.4).
- **One-way door:** no engaged→pool API in Phase 1. Erroneous engagements stay until an admin reverses them (out of scope).
- **Idempotence:** manual engage on already-engaged entity does nothing — no duplicate synthetic activity.

### 6.2 Attribution

Derived on demand from `activities` joined to `users`. No denormalized columns. Backed by indexes from Section 1.3. Future HubSpot imports retroactively populate first-contacted because `happened_at` preserves the real date, not the import date.

### 6.3 Star auto-remove

Pseudocode, executed inside the activity-create transaction:
```python
fks = [(t, eid) for t, eid in [
    ('contact', contact_id),
    ('property', property_id),
    ('group', group_id),
] if eid]

if fks:
    where = " OR ".join("(entity_type=? AND entity_id=?)" for _ in fks)
    params = [me] + [v for pair in fks for v in pair]
    db.execute(f"DELETE FROM user_stars WHERE user_id=? AND ({where})", params)
```

Only the current user's stars are removed. Teammate stars on the same entity remain.

### 6.4 Engaged-by-teammate signal

Per Section 2.1.2 — `MAX(happened_at) FROM activities WHERE {fk}=entity_id AND created_by_user_id != :me AND happened_at > user_stars.starred_at`. Pre-star history doesn't count.

### 6.5 Concurrency

- Optimistic UI on Star toggles; revert on 5xx
- Activity-create transaction wraps insert + auto-engage + auto-remove-star (all-or-nothing)
- No locking on Lists; last-write-wins is fine for a 2-person team

## Section 7 — Phase 1 vs. Phase 2 deliverables

### Phase 1 — IN scope (this spec → this implementation plan)

**Schema:** all of migration `020_crm_daily_outreach.py` (Section 1).

**Backend:**
- New `stars.py` route + register
- `lists.py` scope/ownership + `/membership` lookup
- `activities.py` `'property'` whitelist + auto-engage + star auto-remove + FK population
- `contacts.py` / `groups.py` engage endpoints write synthetic activity
- `/api/{contacts|properties|groups}/{id}/attribution` endpoints

**Frontend:**
- Components: `QuickActionBar`, `StarButton`, `AddToListDrawer`, `CreateDealDrawer`, `AttributionStrip`
- Wire onto `PropertyDetailPage`, `ContactDetailPage`, `GroupDetailPage`
- Add `ActivityFeed` to those three pages
- New `QueuePage` at `/queue` + sidebar entry
- Types in `frontend/src/types/index.ts`

**Tests:** see Section 8.

### Phase 2 — OUT of scope (follow-up after a week of real use)

- Multi-entity activity linking (the contact↔property↔group typeahead in `LogActivityDialog`)
- Row-level star icons on `/contacts`, `/properties`, `/groups` list pages
- Pool/Engaged filter chips on `/properties` and `/groups` (Contacts already has it)
- Engaged badge column on Contacts + Groups list rows
- Bulk operations on Queue (bulk-clear, bulk-add-to-list)

### Phase 3 — explicitly out, separate project

- HubSpot import (manual backfill + ongoing sync). Schema is ready.
- Productive.ai call sync.
- Team activity feed page (firehose across users).
- "Reverse engaged" admin tool.

## Section 8 — Testing

### 8.1 Backend (`pytest`)

New test files:
- `tests/test_stars_api.py` — star/unstar, idempotence, scope-isolation across users, check endpoint, queue payload includes `team_activity` enrichment
- `tests/test_lists_scope.py` — personal hidden from non-owners, shared visible to all, owner-only metadata mutations, anyone-edits-members on shared
- `tests/test_activities_phase1.py`:
  - FK auto-population from `entity_type`
  - Sell_opp / buy_mandate / deal entity types derive FKs from parent record
  - Auto-engage flips `pool` → `engaged` for contacts and groups
  - No duplicate synthetic activity on idempotent manual engage
  - Star auto-remove fires only for current user, only on referenced entities
  - `'property'` entity type now accepted
- `tests/test_attribution_endpoints.py` — first/last/by_user payload correctness with multi-user fixtures, zero-activity case

Modified:
- `tests/test_contacts.py` / `tests/test_groups.py` — manual engage endpoint now writes a synthetic activity; assert it appears

### 8.2 Frontend (manual smoke + tsc)

- `cd frontend && npx tsc` clean before each commit (per CLAUDE.md)
- Manual verification (per CLAUDE.md "test in a browser"):
  - Star a property → appears in `/queue` → log a property-page activity → property auto-removes from queue
  - Pool contact's status flips to engaged on first activity logged from contact page
  - Personal list created by Brandon doesn't appear in Jamie's `GET /api/lists` response
  - Shared list created by Brandon — Jamie can add members but receives 403 on rename/delete
  - `AttributionStrip` renders correctly when 0, 1, and many activities exist on each entity type

### 8.3 Out of scope for Phase 1 testing

- No automated frontend component tests (project has no harness; not adding one now)
- No load tests (small team, low volume)
- No HubSpot import fixtures

## Section 9 — Open questions / risks

### 9.1 Deal-page touches don't auto-engage a contact in Phase 1

When `entity_type='deal'`, the activity populates `property_id` + `group_id` from the deal record but no `contact_id` (deals have no contact FK). So a touch logged from a Deal detail page can't auto-engage a contact in Phase 1.

**Mitigation:** Phase 2's typeahead lets the user pick the contact when logging from a Deal page. Phase 1 accepts this gap — users can log from the contact page itself if they want auto-engage.

### 9.2 `created_by` TEXT vs. `created_by_user_id` FK divergence

Historical activity rows have `created_by` TEXT only. New rows have both. Display logic prefers FK-resolved `users.display_name` and falls back to TEXT. No backfill of historical TEXT → FK (too fragile — names aren't unique, and the TEXT field has been freeform).

### 9.3 User deletion orphans

`user_stars`, `activities.created_by_user_id`, `lists.owner_user_id` all reference `users(id)`. No user deletion flow exists today. If/when one's added, it'll need its own design (probably soft-delete + reassign). Phase 1 punts.

### 9.4 CLAUDE.md compliance

`user_stars` must be added to the "Database: Derived vs CRM Tables" CRM-table list in `CLAUDE.md`. Doc edit, no code impact.

### 9.5 Existing engaged status today

A handful of contacts and groups may already have `status='engaged'` set via the existing manual button. Those don't have a synthetic activity row to back them. **Decision:** leave them alone — Phase 1's synthetic-activity rule applies only going forward. Pre-existing engaged entities show in the Engaged filter but their attribution endpoint returns `null` for first/last contacted (and `total_activities=0`). When a new activity is logged, attribution starts working normally.

### 9.6 Small data integrity note

The `lists` backfill in 1.2 marks all existing lists as `scope='shared'` with `owner_user_id=NULL`. Existing UI continues to see them. If any user wants their existing lists "owned" personally going forward, they can recreate them or we add a one-off SQL migration later. Out of scope for the spec.
