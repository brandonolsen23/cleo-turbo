# Prospecting Build Docket

> **Execution spec for items 1, 2, 4, 5: see `spec-phase1-prospecting.md`** — schema, endpoints,
> UI, build order, acceptance test. Start there.

Agreed with Brandon 2026-07-22 (BusinessOS session — daily click-run design). This is the build
order for making Cleo the system of record for prospecting. Work items only; the daily routine
itself lives in `03_Admin/06_Operations/MASTER - Daily Click-Run SOP.docx`.

**Standing policies for all items below:**
- CRM tables only. Nothing here touches derived tables or the compiler.
- Schema changes: spec → Brandon approves → build (per repo rules).
- Additive by default. No destructive edits, no auto-merges. Ambiguous matches go to human review.
- Every record carries source + timestamp. Provenance is load-bearing (same rule as the pipeline).

---

## 1. Multi-channel contact info — `contact_phones` / `contact_emails` (NEW CRM tables)

The core problem: one phone field per contact forces overwrite-or-lose. Phones/emails are a
collection with verdicts, not a field.

Schema (both tables, same shape):

| column | notes |
|---|---|
| id | pk |
| contact_id | CON_ stable ID |
| value | number / email address |
| label | cell, office, main, etc. |
| source | realtrack, geowarehouse, datanyze, 411, hubspot, manual |
| status | unverified, verified_good, wrong_number (bounced for email), dead |
| note | optional, e.g. "gatekeeper answers this line" |
| created_at, updated_at | timestamps |

- Seed row one from existing RT phone (source=realtrack, status=unverified). Never delete/overwrite.
- Contact page: phones/emails section — add in seconds, one-click status changes.
- Property owner card + contact header show best-ranked channel: verified_good > newest
  unverified; wrong_number/dead hidden but kept.
- Marking a number dead after a dial is capture, not cleanup — it's what prevents re-dialing
  burned numbers after a prospecting gap.

## 2. HubSpot seed + ID bridge + STANDING import (amended 2026-07-22, same session)

HubSpot is the long-term master for contact channels and comms — it auto-logs email, holds
follow-up tasks, and is where Claude already writes research cleanly. The import is therefore
PERMANENT, not transitional.

**Field-level ownership (the anti-two-way-sync rule — every field has ONE master, data only
flows away from its master):**

| Data | Master | Flow |
|---|---|---|
| Phone/email values, comms history, follow-up tasks | HubSpot | standing HubSpot → Cleo import (additive, source=hubspot) |
| Channel verdicts (dead / wrong_number / verified — set while dialing) | Cleo | Cleo-local annotation layered on imported values |
| Contact → property/group assignment, ownership map, portfolio | Cleo | never leaves Cleo |
| Campaign lists, Queue, block call log | Cleo | call activities mirrored to HubSpot via bridge (so HubSpot contact history stays complete) |
| Names / identity | neither | bridge links IDs only — NEVER rename a Cleo contact from HubSpot data (names are fingerprint keys for stable CON_ IDs; renames break the reconciler) |

- Match: name fingerprint (people), normalized name (groups). Clean → auto-link; ambiguous →
  Brandon review list; no counterpart → stays HubSpot-only.
- Store `hubspot_contact_id` on the Cleo contact. All subsequent flows are ID-to-ID.
- Seed + recurring import: HubSpot phones/emails into item-1 tables (source=hubspot,
  status=verified_good on seed; new ones arrive unverified-good per HubSpot state).
- Contact page displays: HubSpot channels with Cleo verdicts layered on, last-touched date,
  jump-link to the HubSpot record.
- **Import must be triggerable on demand** (UI button / endpoint), not schedule-only. The daily
  flow is: 6:30-7:30 research lands in HubSpot → sync fires at end of Build → details are on the
  Cleo property/contact page by the 9:45 call block. A nightly job misses same-morning research.
- Until items 1-2 ship, the call block runs Cleo Queue + HubSpot contact record side by side;
  the morning dossier lives on the HubSpot contact.
- Call-flow division (amended, prevents double-entry): call outcomes (VM / contact made / no
  answer) are logged in HUBSPOT — they're contact-cadence data. Cleo's contacted/last-touch
  status becomes an IMPORTED display field via the bridge (import maps HubSpot call activities →
  Cleo engagement status; also auto-clears matching Queue items). Cleo Log Activity remains only
  for channel verdicts (wrong_number/dead, keyed to Cleo phone rows). Narrative written once at
  the post-block debrief → HubSpot. Interim (pre-import): un-star the Queue item manually after
  the call.
- **Grain rule:** person-grain facts (seller flag, asset-class criteria, motivation) → HubSpot
  contact. Parcel-grain facts (WHICH property is in play, contacted-not-selling status) → Cleo
  (sell_opportunities / buy_mandates via existing UI buttons). Same fact can legitimately touch
  both at different grains — that is not duplication.
- **Graduation rule:** Cleo Opportunities = pre-deal radar (parcel-keyed, cheap, most die).
  HubSpot Sellers Pipeline = the ONLY deal board (real transactions, pace math, morning scan).
  When a Cleo opportunity turns real → create the HubSpot deal (Claude, at debrief).
- **Do NOT use Cleo's "Create deal" button / deals table** while HubSpot is the deal board. Two
  deal boards = split brain.
- **Deals-in-Cleo is the AGREED END STATE** (Brandon, 2026-07-22): deals are property-specific,
  so Cleo-native deals (property + groups + contacts + stages) is architecturally correct.
  Explicitly deferred until ALL THREE preconditions exist: (a) revenue/commission fields + stage
  math in Cleo, (b) the morning scan reads Cleo's pipeline for firm-date GCI pace, (c) an answer
  for Jamie's visibility (Cleo is single-user today). Until then this is a parked decision, not
  a build item — do not let it become a sprint. One-sentence architecture: HubSpot holds the
  people, Cleo holds the properties and groups, Cleo makes the person-to-parcel connections.

## 3. Cleo MCP connector (scope narrowed by the standing import)

Thin MCP server wrapping existing FastAPI routes so Claude writes to Cleo with the same
discipline as the HubSpot connector. Contact channels are NOT in scope — they ride the item-2
import. Tools (all additive, all stamped source=claude into audit_log):

- `set_channel_status` (verdicts on imported/RT channels)
- `add_contact_note` / `add_group_note`
- `link_contact_to_group` (proposes; Brandon confirms in UI for ambiguous cases)
- `add_to_list` / `create_list` (campaign lists)
- read tools as needed (lookup contact/property/group by ID or name)

No group merges, no renames, no overrides, no deletes — those stay human-only in the UI.

## 4. "Never contacted" filter on Map + Properties browse

Status exists on property/contact records; map filter bar (cities/price/yrs/sf/types/
categories/brands) has no engagement filter. Add it — it's the difference between hunting fresh
targets and re-treading called ones.

## 5. Notes affordance on Contact + Group detail pages

Tables exist (contact_notes, group_notes). Verify/add UI: visible notes box on both pages, and
field edits capture source + date (e.g. "Datanyze, Jul 2026") instead of silent overwrite.

## 6. Dashboard progress card

Derivable from existing timestamps (list_members.added, stars, activities): "this week: N added,
N called, N conversations." No schema change. Feeds the Operating Tracker numbers Brandon logs
daily.

---

## Explicitly rejected (don't resurrect these)

- **Follow-up dates / "Today" view in Cleo** — HubSpot is the follow-up engine (tasks, dated,
  read by the morning scan). Two activity schedulers = both die.
- **Two-way HubSpot sync** — replaced by field-level ownership (item 2). Each field has one
  master; data flows one way per field. Never build bidirectional field sync.
- **"Cleo as master for contact channels"** — considered and reversed same day: HubSpot
  auto-captures comms and is Claude's clean write surface; Cleo can't compete there. Cleo
  masters assignment, verdicts, and the ownership map instead.
- **Week-dated lists** ("wk Jul retail…") — lists are campaigns (thesis + client + angle in the
  description field, 2–4 active). Daily calls = the Queue (auto-clears on logged activity).
