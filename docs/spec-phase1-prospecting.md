# Phase 1 Spec — One-Surface Prospecting

Companion to `prospecting-docket.md` (items 1, 2, 4, 5). Goal: kill the three interim pains —
(a) dossier/number lives in HubSpot while calling happens in Cleo, (b) manual Queue un-starring,
(c) no home for channel verdicts. When Phase 1 ships, the morning loop is: research → HubSpot →
**Sync Now** → everything on the Cleo page by 9:45.

Approved by Brandon 2026-07-22 in principle; schema below still gets a final look before
migration code is written (repo rule).

**Non-goals (do not build in Phase 1):** MCP connector, Cleo→HubSpot writes of any kind, deals,
progress dashboard card, call recording. Nothing here touches derived tables or the compiler.

---

## 1. Schema — three new CRM tables

All keyed by stable IDs (CON_/GRP_/PRO_), which persist across compiler rebuilds. None of these
are ever dropped/rebuilt. Add to the CRM-tables list in `schema.py` and `CLAUDE.md`.

### contact_phones / contact_emails (same shape)

| column | type | notes |
|---|---|---|
| id | pk | |
| contact_id | text | CON_ stable ID |
| value | text | E.164-normalized for phones where possible; raw preserved in `value_raw` |
| value_raw | text | as found |
| label | text | cell / office / main / null |
| source | text | realtrack, geowarehouse, datanyze, 411, hubspot, manual |
| status | text | unverified, verified_good, wrong_number (email: bounced), dead |
| status_changed_at | timestamp | when a verdict was set |
| note | text | optional ("gatekeeper line") |
| hubspot_property | text | which HS field it came from (phone, mobilephone, email), null otherwise |
| created_at / updated_at | timestamps | |

- **Seeding:** one-time migration inserts each contact's existing RT phone as
  (source=realtrack, status=unverified). RT value in derived tables is untouched — this is a
  copy with provenance, not a move.
- **Best-channel ranking** (used everywhere a single number/email is displayed):
  verified_good (newest first) > unverified (newest first); wrong_number/dead/bounced never
  displayed as best, always visible in the channels list.
- Dedupe on (contact_id, normalized value): re-import of a known value updates nothing (additive
  idempotent).

### hubspot_links (the ID bridge)

| column | type | notes |
|---|---|---|
| id | pk | |
| entity_type | text | contact / group |
| entity_id | text | CON_ / GRP_ |
| hubspot_id | text | HS contact/company id |
| matched_by | text | auto_fingerprint / manual |
| confirmed_at | timestamp | null until Brandon confirms manual matches |
| created_at | timestamp | |

Unique on (entity_type, entity_id) and on (entity_type, hubspot_id) — 1:1 links only.
`contacts` is a DERIVED table, so the HS id cannot live there; this table is the join.

### hubspot_sync_state (small)

last_sync_at, cursor/watermark per object type, last run status + counts. Enough to make sync
incremental and debuggable. (A row per run appended to existing `audit_log` is fine for history.)

## 2. HubSpot import service (backend, one-way HS → Cleo)

- Auth: HubSpot private-app token in env/config. Scopes: crm.objects.contacts.read,
  crm.objects.companies.read, engagements read (notes/calls).
- **Endpoints:**
  - `POST /api/hubspot/sync` — runs an incremental sync now. Returns counts.
  - `GET /api/hubspot/sync/status` — last run, pending match-review count.
  - `GET /api/hubspot/matches/pending` / `POST /api/hubspot/matches/{id}/confirm|reject`
- **Sync pass does, in order:**
  1. Pull contacts/companies changed since watermark.
  2. Match unlinked ones: name fingerprint (UPPERCASE first+last, same normalization as the
     reconciler) for contacts; normalized company name for groups. Exactly-one candidate →
     auto-link (matched_by=auto_fingerprint). Multiple candidates → pending match review.
     Zero candidates → skip (stays HubSpot-only, re-checked next sync).
  3. For linked contacts: upsert phones/emails into item-1 tables (source=hubspot).
  4. Pull notes + call engagements for linked contacts → insert into existing `contact_notes`
     (source=hubspot, hubspot engagement id stored for idempotency). This is what puts the
     morning dossier on the Cleo page.
  5. Compute engagement rollup per linked contact: last_contacted_at, last_outcome → stored on
     a small `contact_engagement` CRM table (or columns on hubspot_links; implementer's call,
     NOT on derived contacts).
  6. **Queue auto-clear:** any starred item (contact, or property whose current owner
     group/contact is linked) with a HubSpot call engagement newer than the star → un-star.
- Hard rules: never write names/titles to any Cleo table from HS; never create Cleo contacts
  from HS (no Cleo counterpart = skip); additive only; idempotent re-runs.

## 3. UI

1. **Contact page — Channels card** replaces the single phone display: all phones/emails,
   source badge, status pill (click to cycle verdict: unverified → verified_good / wrong_number
   / dead), + Add (manual entry). Best channel bolded at top.
2. **Contact page — Notes/dossier section:** existing `contact_notes` rendered (source badge:
   hubspot / manual), plus a plain add-note box. Same on Group page with `group_notes`.
3. **Contact + property owner card:** "HubSpot: last touched {date} — {outcome}" + deep link
   `https://app.hubspot.com/contacts/{portal}/contact/{hubspot_id}` when linked; "not in
   HubSpot" chip when not.
4. **Sync Now** button (header, next to search): fires POST /sync, shows result toast +
   pending-match badge that links to a Match Review page (approve/reject candidate pairs).
5. **"Contacted" filter** on Map + Properties + Contacts browse: never / any / >6mo / >12mo
   (driven by the engagement rollup; property inherits from current-owner linkage).
6. **List detail page:** render the list description (the campaign angle) as a callout above
   members. One-line change, big payoff at call time.

## 4. Build order (each step ships something usable on its own)

1. Tables + seeding + Channels/Notes UI (kills verdict + dossier-entry pain; manual until sync)
2. Bridge + import + Sync Now + Queue auto-clear (kills two-surface + un-star pain)
3. Match Review page
4. Contacted filter + list-description callout

Realistic effort: 3–4 focused sessions. Each is a legal "after the block" time-box. Step 2 is
the biggest; don't start it the same day as step 1.

## 5. Acceptance test (the morning-after test)

At 7:00 Brandon researches a new owner with Claude → Claude writes contact + dossier + number to
HubSpot → Brandon hits Sync Now at 7:25 → by 9:45 the Cleo property page shows: best number with
source, dossier note, "last touched" state — and after the call is logged in HubSpot, the next
sync clears the star and updates last-touched. If any of that requires opening HubSpot in a
second tab during the block, Phase 1 isn't done.
