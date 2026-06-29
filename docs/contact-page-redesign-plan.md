# Contact Page Redesign — Plan

Mirror the property-page pattern (which the user likes), add tab-structured deeper content (Kerso-inspired), unify enrichment sources, and introduce a one-canonical-HQ-address mechanism for groups. Five waves, each independently shippable.

## Architectural decisions locked in

1. **Group display name resolution** — use the override hierarchy already built:
   - `auto_groups.display_name` is the canonical UI string
   - On creation it's seeded from `defining_brands.canonical_name` (correctly cased) when a defining-brand rule exists
   - Algorithm-derived names ("starlight investments" lowercase) get overridden by either the defining-brand canonical name OR a user rename via the Phase C `PATCH /api/auto-groups/{id}` endpoint
2. **Tab navigation in the main pane** (replaces today's vertical scroll-stack)
3. **Communication sync deferred** — must wait until HubSpot ↔ Cleo bi-directional sync is in place. Communication tab built later as a separate epic.

## Wave 1 — Header cleanup

**Goal:** clean, scannable header that puts the contact's identity + their employer prominently and tucks the action overflow into a menu.

**Current state (problems):**
- 6 visible actions on a single row: `Promote to Engaged · Notes · Star · Log activity · Add to list · Create deal · Buy mandate`
- Group identity is a small lowercase chip below "Never contacted"
- Title (`pres`) buried in the left sidebar, not next to the name

**Target shape:**
```
← Contacts
                                                      [☆] [Log activity] [Add to list] [···]
Daniel Drimmer  [in]
President · Starlight Investments
Pool · Never contacted
```

**Deliverables:**
- Heading 1: contact name (largest text — `<Heading size="7">` or similar Radix scale)
- Subtitle: `{title} · {group_display_name_link}` — proper-cased, group name clickable to its detail page
- Status line (smaller, muted): `{lifecycle_stage} · {last_contacted_summary}`
- Action row collapsed to: `Star` (icon), `Log activity` (primary green pill), `Add to list` (secondary), `···` overflow
- Overflow menu contains: Promote to Engaged, Create deal, Buy mandate, Notes, Mark as collision (future)
- `pool` and other lifecycle pills relocate into the status line, not the action row

**Effort:** ~2 hrs

**Acceptance:**
- Group name proper-cased and links to its auto_group detail page
- Action row never exceeds 4 visible buttons
- Promote/Create-deal/Buy-mandate accessible in ≤2 clicks via overflow

**Risks:** Low. UI-only.

---

## Wave 2 — Stats cards row

**Goal:** push the metrics that matter most for a CRE contact to the top of the page, matching the property-page card pattern.

**Target shape (cards row, full-bleed under header):**
```
[ Transactions ]  [ Portfolio Size ]  [ Tenure              ]  [ Last seen        ]
  779               2.86M sf            14 yrs at Starlight    Mar 2, 2026
```

**Deliverables:**
- 4-card row component reusing the property page's StatCard pattern
- Cards: `Transactions`, `Portfolio Size` (sf), `Tenure` (years at current employer, derived from career_history.is_active=1 row), `Last Seen` (max sale_date)
- Data already in the API response — just promoted from the bottom of the page to the top
- Hide cards gracefully when data is missing (e.g. no portfolio size for anonymized contacts)

**Effort:** ~2-3 hrs

**Acceptance:**
- All 4 cards render correctly for Daniel Drimmer (CON_00274)
- Cards render gracefully for a contact with no portfolio data (e.g. a broker on one transaction)
- Mobile/narrow layout collapses cards into a 2-up grid

**Risks:** Low. UI-only. Data is already there.

---

## Wave 3 — Group card + restructured body

**Goal:** mirror the property page's Owner-card + Map layout for contacts. Move mailing addresses out of the sidebar (they belong in a tab later) so the left rail isn't an unbounded scroll.

**Target shape:**
```
┌────────────────────────────┐  ┌──────────────────────────────────────────────┐
│ Group / Employer           │  │ Group portfolio map (Starlight, 443 txns)    │
│                            │  │ — Daniel's signed transactions overlaid      │
│ Starlight Investments      │  │                                              │
│ <HQ address — see Wave 5>  │  │ [Toggle: All Starlight | Daniel only]       │
│ <Website link if set>      │  │                                              │
│                            │  │                                              │
│ [Call Group] [Email Group] │  │                                              │
│                            │  │                                              │
│ — Linked contacts (5) —    │  │                                              │
│ Daniel Drimmer (CEO)       │  │                                              │
│ Barbara Lanys              │  │                                              │
│ ...                        │  │                                              │
└────────────────────────────┘  └──────────────────────────────────────────────┘
```

**Deliverables:**
- New left-column `Group` card showing:
  - Group name (linked to detail)
  - HQ address placeholder (replaced by real logic in Wave 5)
  - Optional website (from defining_brands.notes or future override)
  - Action buttons: Call Group / Email Group (use group HQ phone/email if known)
  - "Linked contacts" section listing other contacts assigned to this auto_group
- Main pane shows one unified map (no longer two separate Portfolio + Footprint cards)
- Map has a toggle: `All Group properties` (default) | `This contact's signed transactions`
- Mailing addresses card removed from sidebar (its content moves to a Career tab in Wave 4)
- Contact Info card stays in left rail above Group card

**Effort:** ~1 day

**Acceptance:**
- Daniel Drimmer's page: Group card shows "Starlight Investments" with linked contacts; map toggles correctly between 443 txns and 779 txns
- Anonymized contacts (current_auto_group = "Named Individuals (anonymized)") hide the Group card entirely or show a "No group affiliation" state
- Page height shrinks by ~40% vs. current layout

**Risks:** Medium. Restructuring the layout grid; will need to verify mobile responsiveness.

---

## Wave 4 — Tabs + unified Contact Info

**Goal:** replace vertical scrolling with tab navigation in the main pane. Merge Datanyze enrichment into one Contact Info card with source badges.

**Target shape:**

**Tab strip (in main pane below stats cards):**
| Tab | Content |
|---|---|
| **Map** (default) | The unified group/contact map from Wave 3 |
| **Transactions** | Full table (today's Transaction History; 779 rows for Daniel) |
| **Career** | Career history, mailing addresses over time, tenure rendering |
| **Activity** | Logged activity placeholder; full implementation deferred until HubSpot sync |

**Left sidebar Contact Info card (unified Datanyze + RT):**
```
Contact Info                                                            [Edit]

📧 Email
   daniel@starlight.com       [Datanyze]
   dan.drimmer@gmail.com      [Datanyze]

☎ Phone
   (416) 234-8444             [Realtrack]
   (416) 555-0142 (mobile)    [Datanyze]

🔗 Social
   linkedin.com/in/...        [LinkedIn]
   x.com/ddrimmer             [Datanyze]
```

**Deliverables:**
- Tab strip component using Radix `Tabs.Root`
- Map tab as default
- Transactions tab — table view; replaces the inline Transaction History block from current page
- Career tab — career_history rows + mailing addresses over time + address tenure tags
- Activity tab — empty state for now ("Activity log coming when HubSpot sync is live")
- Contact Info card refactor:
  - One unified card listing emails, phones, social
  - Source badge per row (`Datanyze`, `Realtrack`, `LinkedIn`, `User-edited`)
  - Datanyze contact card removed entirely

**Effort:** ~1-2 days

**Acceptance:**
- All 4 tabs render their content correctly
- Datanyze data merged into Contact Info; no separate Datanyze card anywhere on the page
- Tab state persists in URL hash (`/contacts/CON_00274#career`) so deep links survive
- Empty states render cleanly for tabs with no data (e.g. Career tab on a single-transaction broker)

**Risks:** Medium. Tab state management + URL sync. Worth testing mobile layout.

---

## Wave 5 — HQ address logic + AI enrichment

**Goal:** show exactly ONE canonical HQ address per group, with a clear mechanism for picking/correcting it. Reusable pattern for website, primary phone, leadership.

**Three layered mechanisms:**

### 5a. Algorithmic guess (default)
- Score each address candidate per group by `(recency_weight * frequency_weight)`
- Top scorer becomes `auto_groups.primary_address` (denormalised, recomputed on each discovery_v2 run)
- Show in UI: "Probable HQ — confirm" with edit affordance

### 5b. Manual override
- User opens group detail page, sees top-5 candidate addresses
- One-click pick the right one
- Override stored in `auto_group_user_edits` (new `edit_type='set_address'`)
- Survives rebuilds via the `apply_user_edits` stage

### 5c. AI enrichment (premium path)
- "Find HQ" button on Group card
- User optionally supplies website URL; otherwise system finds it via search by `display_name`
- Claude fetches homepage + Contact page + LinkedIn About
- Returns: `{ candidate_address, website, primary_phone, evidence_snippets }`
- User confirms with one click; all three fields populate

**Deliverables:**
- Schema: `auto_groups` columns — `primary_address`, `primary_address_source` (`'algorithmic' | 'manual' | 'ai_enriched'`), `website`, `primary_phone`
- Algorithmic builder runs in discovery_v2 final stage (recomputes scores, picks defaults)
- API endpoints:
  - `GET /api/auto-groups/{id}/address-candidates` — top 5 candidate addresses with scores
  - `POST /api/auto-groups/{id}/set-address` — user picks one (writes to user_edits)
  - `POST /api/auto-groups/{id}/enrich` — triggers AI fetch + returns proposed enrichment
  - `POST /api/auto-groups/{id}/accept-enrichment` — applies the AI proposal
- UI: address row in Group card with `[edit]` icon → opens address picker with 3 options (top candidates / manual / AI)
- AI cost: ~$0.02 per enrichment on Sonnet

**Effort:** ~2-3 days

**Acceptance:**
- Every non-anonymized auto_group has a probable HQ address shown by default
- User can pick a different address from a list in one click
- AI enrichment returns a usable answer for known brands (RioCan → 2300 Yonge St Suite 500, KingSett → 130 King St West, Starlight → 3280 Bloor St W)
- Address override survives a discovery_v2 rebuild

**Risks:** Medium-high. The AI path needs careful prompt design + error handling. Address-candidate scoring needs to feel right (currently 35 addresses for Daniel — many are SPV mailings, not his employer's HQ).

---

## What's NOT in this plan (deferred)

- **Communication tab implementation** — needs HubSpot bidirectional sync first. Build it as a separate epic when CRM sync is on the roadmap.
- **Activity log fed by app actions** — exists today in skeleton form (`activities` table); will integrate properly into Communication tab when sync lands.
- **Property page parallel redesign** — already feels good per user; revisit only if patterns established here suggest improvements.
- **Group detail page parallel redesign** — share the Wave 3/4 patterns later; same structure (header + stats cards + tabbed body + sidebar) applies cleanly.

## Status

- 2026-05-13: Plan finalised. Starting Wave 1 + Wave 2.
