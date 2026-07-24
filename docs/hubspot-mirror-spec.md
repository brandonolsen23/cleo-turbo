# HubSpot → Cleo One-Way Mirror — Spec (v2, 2026-07-21)

Decision: HubSpot remains the system of record for contacts and communication capture
(email logging/tracking, auto contact creation, enrichment). Cleo mirrors it read-only,
nightly. Cleo NEVER writes back to HubSpot. Cutover to Cleo-as-CRM stays an open option;
the mirror is what makes that a small step later instead of a migration.

Cost context (decided 2026-07-21, see memory crm-stack-direction): do NOT upgrade HubSpot
for Breeze enrichment (Apollo is the data engine and its direct-dial credits max out
monthly). Plan is downgrade toward free tier at renewal, AFTER M1 backfill completes.

## 0. Portal inventory (live counts, Jul 21 2026)

| Object    | Count  | Notes |
|-----------|--------|-------|
| contacts  | 3,603  | includes junk auto-created from logged marketing email — mirror everything, hide at display |
| companies | 1,583  | same caveat (Substack, Ideals, etc. from newsletter logging) |
| emails    | 34,871 | bulk is marketing/newsletter noise; sales email is the minority worth surfacing |
| calls     | 241    | high-value, all human-logged |
| notes     | 173    | high-value (incl. Claude weekly-review reconciliation notes) |
| tasks     | 292    | follow-ups |
| meetings  | 203    | calendar-logged |
| deals     | 53     | all on single 'default' pipeline (matters for free-tier downgrade) |

Portal id: 23343708. Owner id (Brandon): 580302941.

Cleo-side grounding (queried Jul 21): 84,680 contacts; 9 have email, 38,477 have phone
(100% RT/transaction-sourced), 29,370 distinct normalized numbers, most-shared number
appears on 41 contacts (office switchboards). 11 contacts already status='engaged'.
Consequence: email is nearly useless as a Cleo-side match key; name fingerprint + phone
carry the matching.

## 1. Field map — what we mirror

### contacts (hubspot_contacts)
Identity/core: hs_object_id, email, work_email, firstname, lastname, salutation,
phone, mobilephone, jobtitle, company, address, city, state, zip, country,
hs_linkedin_url, website, lifecyclestage, hs_lead_status, hubspot_owner_id,
createdate, lastmodifieddate, hs_object_source_label, hs_is_unworked, hs_merged_object_ids.

Brandon's CUSTOM properties (the actual judgment — do not lose these):
- type_of_contact        (buyer / seller / lessee / lessor / realtor / professional / personal)
- all_real_estate_classes (+ legacy real_estate_category archive)
- cap_rate_expectations
- engagement_tier
- touch_cadence
- last_meaningful_touch
- next_touch_due
- personal_intel
- subject_property       (property first reached out about — join key candidate to Cleo properties)

Engagement rollups (computed by HubSpot, power "engaged" + "ready to dial"):
notes_last_contacted, notes_last_updated, notes_next_activity_date,
num_contacted_notes, num_notes, hs_last_sales_activity_timestamp,
hs_sales_email_last_opened, hs_sales_email_last_clicked, hs_sales_email_last_replied,
hs_latest_sequence_enrolled_date, hs_email_optout.

### companies (hubspot_companies)
hs_object_id, name, domain, website, phone, address, city, state, zip,
industry, description, numberofemployees, hubspot_owner_id, createdate,
hs_lastmodifieddate, num_associated_contacts, lifecyclestage.
(Logo: render from `domain` at display time — same trick HubSpot uses.)

### engagements
`hubspot_engagements` (type discriminator) or per-type — decide in build.
- emails:   hs_object_id, hs_createdate, hs_email_direction, hs_email_status, hs_email_subject,
            hs_body_preview (NOT full hs_email_text on first pass; pull full text lazily
            for contact-associated sales emails only)
- calls:    hs_object_id, hs_createdate, hs_call_title, hs_call_body, hs_call_duration,
            hs_call_direction, hs_call_disposition, hubspot_owner_id
- notes:    hs_object_id, hs_createdate, hs_note_body, hubspot_owner_id
- meetings: hs_object_id, hs_createdate, hs_meeting_title, hs_meeting_start_time,
            hs_meeting_outcome (skip hs_meeting_body — Teams boilerplate)
- tasks:    hs_object_id, hs_createdate, hs_task_subject, hs_task_body, hs_task_status,
            hs_task_priority, hs_timestamp (due date)

### associations (hubspot_associations)
(from_type, from_id, to_type, to_id). Needed: engagement→contact, engagement→company,
engagement→deal, contact→company.

### deals (hubspot_deals) — small, mirror whole
hs_object_id, dealname, pipeline, dealstage, amount, deal_currency_code, dealtype,
closedate, createdate, hubspot_owner_id, notes_last_contacted, hs_is_closed_won/lost.

### owners
Tiny lookup (id → name/email) so records show "Brandon"/"Jamie" not raw ids.

## 2. Cleo-side design (doctrine compliant)

CRITICAL (learned 2026-07-07): `contacts` and other derived tables are recreated from
schema.py on every compile. Mirror data lives in its OWN raw tables (evidence bucket),
in schema.py from day one:

- hubspot_contacts / hubspot_companies / hubspot_engagements / hubspot_associations /
  hubspot_deals / hubspot_owners — raw mirror, 1:1 with HubSpot, hs_object_id PK, upsert-only.
- hubspot_sync_state — per object type: high-water lastmodifieddate, last run, row counts.
- Normalized match keys (digits-only phone w/ extension split, lowercased email, Cleo-style
  name_fingerprint) are COMPUTED columns/tables in the interpretation bucket — rebuildable
  from raw, never hand-edited. Not a separate DB file.

### 2a. Matching (M2) — link, never merge; mirror NEVER creates Cleo contacts
Pool guarantee: 84,680 contacts before mirror = 84,680 after. Matching only annotates.

Keys, by trust: email exact (near-certain, low yield) > phone normalized (strong but
one-to-many — switchboards) > name fingerprint (good, collides on common names).

Tiers (decided 2026-07-21):
1. AUTO-LINK: name fingerprint exact AND phone agrees. Phone's weight is inverse to its
   shared count — fingerprint + unique-ish phone (N≤2) links even on fingerprint collision
   candidates; fingerprint + switchboard phone (N large) only auto-links when the
   fingerprint is unique in the pool, else review.
2. AUTO-LINK: fingerprint exact, unique both sides, no phone conflict.
3. REVIEW QUEUE: fingerprint collisions; fuzzy-near names; phone-only matches where the
   number appears on ≤3 contacts (likely same person under a name variant — e.g.
   "Jon"/"Jonathan"). Phone-only with N above cutoff: NO suggestion (pure metadata) —
   otherwise the RioCan-main-line case spams 41 junk suggestions per compile.
4. NO MATCH: HubSpot-only records stay in the mirror, invisible to the pool.

- contact_hubspot_links (cleo_contact_id, hs_object_id, method, confidence, confirmed_by,
  created_at) — judgment overlay, append-only. contacts.hubspot_id (column exists) is
  POPULATED FROM this table at compile, never written directly.
- Disagreeing keys (phone→A, name→B) always → review queue; that signal usually means a
  mis-attributed RT phone or shared desk.
- BEFORE building: read-only DRY RUN — fingerprint + normalized-phone match in memory,
  report auto-link count / review-queue size / HubSpot-only count / phone-only-suggestion
  count under the ≤3 rule / corroborated-RT-number count. Sizes the review UI and tunes
  thresholds before any schema work.

### 2b. Channel provenance (contact_channels) — "which phone is accurate"
Current schema can't express multi-source fields (contacts.phone = one slot;
contact_field_overrides = one override slot). New table:

contact_channels (contact_id, channel [phone|mobile|email|linkedin], value_normalized,
value_display, source [rt|gw|hubspot|apollo|manual|web], first_seen, verified_at,
verdict [good|bad|unknown], shared_count).

- Display precedence: manual > hubspot > apollo > gw > rt (extends doctrine precedence
  to contact fields; a HubSpot number is one Brandon saved himself, so it outranks RT scrape).
  Source badges on every value. Existing contacts.phone becomes a source=rt row at compile.
- Verdicts are judgment: dialing a dud marks the ROW bad (the value + the fact RT was wrong
  both survive); never overwrite values.
- Corroboration runs both ways: HubSpot number matching an RT number VALIDATES that RT
  number (verdict upgrade) — attacks "RT phones usually aren't good" structurally.
- shared_count computed at compile across all sources. Classification: N=1–2 likely direct
  line; N≥3 shared/office line, labeled as such wherever displayed ("reaches Gitlin" vs
  "reaches RioCan reception"). Contact-card 'i' icon: source + "appears on N other contacts."
  Thresholds start at 3; tune after dry run.
- Phone-only matches surface as SUGGESTIONS on contact cards; accepting one is a judgment
  write to contact_channels. Suggestion ≠ identity link.

### 2c. FIREWALL — channels are never clustering evidence
Entity resolution (properties→groups, contacts→groups, contacts→properties, discovery_v2
fingerprints) NEVER reads contact_channels, suggested or accepted. A phone is a great way
to reach a person and a terrible way to define one — shared numbers leaking into evidence
would glue unrelated contacts into blobs (41 contacts on one RioCan line). Channels enrich
cards; transaction evidence + fingerprints build relationships; the two never cross.
Admitting confirmed direct lines (N=1, human-verified) as weak evidence would be a
deliberate doctrine change, not a default.

### 2d. Engaged status
Compile rule: confirmed link + real HubSpot activity (num_contacted_notes > 0 OR
notes_last_contacted NOT NULL) → contacts.status='engaged',
last_engaged_date=notes_last_contacted. Derived at compile ⇒ survives rebuilds, refreshes
nightly. Engaged flows ONLY through confirmed identity links — never phone-only.
Pool views split: engaged / linked-but-cold / untouched pool (the who's-left-to-hunt map).

### activities integration
Compile derives hubspot engagement rows into `activities` (source='hubspot',
external_id=hs_object_id — idx_activities_dedupe anticipates exactly this). Rebuildable
from the mirror ⇒ safe under recompile.

## 3. Sync mechanics

- Auth: HubSpot private app token, read-only scopes (crm.objects.*.read,
  crm.schemas.*.read). Token in .env (loader must load_dotenv itself).
- Incremental: search API filtered on lastmodifieddate > high-water mark, per object type.
  First run = full backfill (3.6k contacts + 1.6k companies ≈ 50 pages; 35k emails ≈ 350
  pages — batched, fine at nightly cadence).
- Schedule: launchd com.cleo.hubspot-mirror, daily 07:45 (after RT 7:30 / GW 7:35), plus
  `launchctl kickstart` on demand. Same log pattern as engines/gw.
- Noise filtering at DERIVE time, not mirror time (mirror everything, judge later).

## 4. Communications consolidation — what Cleo does and does NOT do

Cleo = consolidation of DISPLAY: contact/group pages get a timeline (calls, notes, sales
emails, meetings, tasks) joined to parcels and groups — the join HubSpot cannot make.
"Ready to dial" = worklist status + next_touch_due + notes_last_contacted.

Explicitly NOT building in Cleo (HubSpot keeps doing these):
- Email capture (BCC/forwarding, Gmail/Outlook extension logging)
- Open/click tracking and deliverability
- Auto contact-card creation from a tracked email
- Enrichment + logo lookup (mirror carries HubSpot's enrichment; logo from domain at display)
- Sending email from Cleo

## 5. Phases (each accepted in the UI, per doctrine)

- M0: DRY RUN (read-only match pass, report tier counts). No schema changes.
- M1: hubspot_contacts + companies + owners mirror, sync_state, launchd job.
      Accept: freshness card on Data Quality page shows last sync + counts.
- M2: link layer per §2a + contact_channels per §2b + engaged per §2d.
      Accept: Henry Li shows HubSpot badge, last-touch, sourced phone badges in Cleo;
      review queue usable; pool count unchanged.
- M3: engagements + associations mirror → activities derivation; timeline on contact page.
      Accept: Henry Li's page shows Jan '24 notes + Jul '26 email summary.
- M4 (later, opt-in): worklist "ready to dial" pulls next_touch_due/touch_cadence from mirror.

Decided (2026-07-21): junk auto-created HubSpot contacts are mirrored but hidden (never
excluded at fetch). Identity links vs channel suggestions split per §2a/§2b. Firewall §2c.

Still open:
1. Full email bodies for contact-associated sales emails, or previews only?
2. Deals: mirror only, or does Cleo's deals concept (migration 033, partially applied)
   eventually own pipeline?
3. Exact shared-count thresholds (start 3; tune after M0 dry run).
