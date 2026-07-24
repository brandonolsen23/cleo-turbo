# HubSpot Mirror — Build Brief for Claude Code

You are building the HubSpot → Cleo one-way mirror. The full design is in
`docs/hubspot-mirror-spec.md` (v2, 2026-07-21) — READ IT FIRST, it is the contract.
This brief adds the repo-specific facts, guardrails, and build order. Where this brief
and the spec disagree, the spec wins on design, this brief wins on process.

## Non-negotiable guardrails

1. ONE-WAY. Cleo never writes to HubSpot. Token is read-only scoped; there is no code
   path that calls a HubSpot write endpoint. Ever.
2. The mirror NEVER creates rows in `contacts`. Pool is 84,680 before and after.
   Matching only annotates (links + channels + status).
3. DERIVED-TABLE RULE (this has broken prod twice): derived tables are recreated from
   `cleo/database/schema.py` on every compile/rebuild. The new `hubspot_*` raw tables
   are EVIDENCE tables — model them on the `gw_assessments` lane (durable, upsert-only),
   NOT on `contacts`. Any migration that touches a derived table must also edit
   schema.py in the same commit, or the next pipeline run silently wipes it.
4. There is NO migration runner. Migrations run per-file with duplicate-column
   tolerance. Migration 033 is partially applied on the real DB (activities has
   auto_group_id; deals/user_stars don't) — check before relying on those columns.
5. Develop and test against a COPY: `cp data/cleo.db /tmp/cleo_test.db` and use the
   `CLEO_DB_PATH` env override (exists in `database/connection.py`). Real DB only
   after the copy passes. Back up the real DB before first real migration
   (pattern: `cleo.db.YYYYMMDD-HHMMSS`).
6. Acceptance is IN THE UI, not at the DB level. A phase is done when Brandon can see
   it on a page, not when a SELECT works.
7. Do not touch: auto_groups / discovery_v2, the RT lane (`engines/rt`), the GW lane
   (`engines/gw`), portfolio-capture code. Firewall per spec §2c: contact channels are
   never inputs to entity resolution.
8. Secrets: token lives in `.env` as `HUBSPOT_PRIVATE_APP_TOKEN`. Standalone runners
   must call `load_dotenv()` themselves (the ai.py lesson). Never commit the token.

## Repo facts

- DB: `data/cleo.db` (repo-root `cleo.db` is 0 bytes — ignore it).
- Mimic the GW lane layout: new code in `engines/hubspot/` (fetcher, normalizer,
  upserter), logs to `engines/hubspot/launchd.log` + `launchd.err.log`.
- launchd: agents `com.cleo.rt-daily-scraper` (7:30) and `com.cleo.gw-daily-scraper`
  (7:35) exist in `~/Library/LaunchAgents/`. New: `com.cleo.hubspot-mirror` at 07:45,
  RunAtLoad true, same plist shape. Manual fire: `launchctl kickstart gui/$UID/<label>`.
- Freshness cards: Data Quality page reads `/api/data-quality/freshness` — add the
  mirror as a third lane card (frontend: React 19 + Radix jade/slate; follow existing
  card component, don't invent styling).
- Branch: create `feature/hubspot-mirror` (do not pile onto feature/portfolio-capture-m1).
- HubSpot portal 23343708; Brandon's owner id 580302941. Counts as of Jul 21 2026:
  3,603 contacts / 1,583 companies / 34,871 emails / 241 calls / 173 notes /
  292 tasks / 203 meetings / 53 deals.
- Cleo contacts: 84,680 rows; only 9 emails; 38,477 phones (all RT-sourced),
  29,370 distinct normalized; most-shared number on 41 contacts. So: matching is
  name_fingerprint + normalized phone; email is a bonus key, not the plan.
- `contacts.hubspot_id` column and `activities` (source, external_id + dedupe index)
  already exist — they are the intended landing points, populated at compile only.

## Prerequisite (Brandon does this, not you)

Create a HubSpot private app: Settings → Integrations → Private Apps → Create.
Scopes: crm.objects.contacts.read, crm.objects.companies.read, crm.objects.deals.read,
crm.objects.owners.read, plus engagement reads (calls/emails/meetings/notes/tasks) and
crm.schemas.*.read. NO write scopes. Put the token in `.env` as
HUBSPOT_PRIVATE_APP_TOKEN. If the token is missing, stop and ask — do not mock it.

## Build order — one phase per session, stop at each gate

### Session 1 — M0 dry run (read-only, NO schema changes)
Script: `engines/hubspot/dry_run_match.py`.
- Fetch all contacts (id, name fields, email, phone, mobilephone, jobtitle, company)
  via search API, paginated.
- Normalize: digits-only phones (strip leading 1, split extensions), lowercase emails,
  compute Cleo-compatible name_fingerprint (REUSE Cleo's existing fingerprint function —
  find it in the codebase, do not reimplement; matching depends on identical logic).
- Match in memory against contacts + spec §2a tiers. Report:
  auto-link count (tier 1 and 2 separately), review-queue size (by reason),
  phone-only suggestions under the ≤3 shared-count rule, HubSpot-only count,
  corroborated-RT-number count, top shared-number offenders.
- Output: printed table + `outputs/hubspot_dry_run_YYYYMMDD.json`.
- GATE: show Brandon the numbers. Thresholds (the "3") get tuned here before M2 is built.

### Session 2 — M1 mirror (spec §1, §3)
- Migration: hubspot_contacts, hubspot_companies, hubspot_owners, hubspot_sync_state
  (+ schema.py registration per guardrail 3).
- `engines/hubspot/sync.py`: full backfill then incremental via
  lastmodifieddate > high-water mark. Upsert on hs_object_id. Mirror everything,
  including junk contacts — filtering is display-time, never fetch-time.
- launchd plist + install + `scripts/hubspot-daily-run.sh` (mirror gw-daily-run.sh).
- Freshness card on Data Quality page.
- GATE (UI): card shows last sync time + row counts matching portal counts.

### Session 3 — M2 links + channels (spec §2a, §2b, §2d)
- Tables: contact_hubspot_links (append-only), contact_channels (+ shared_count compute).
- Matcher runs the tiers using M0 thresholds; auto-links write links; review candidates
  land in a queue table surfaced in UI (follow the Evidence-tab/verdict pattern on
  group pages for the review UI).
- Compile step: populate contacts.hubspot_id from links; derive status='engaged' +
  last_engaged_date per spec §2d; contacts.phone becomes a source=rt channel row.
- Contact card: sourced phone/email badges, 'i' icon with shared count, phone-only
  suggestions (accept = judgment write).
- GATE (UI): Henry Li (known HubSpot contact) shows badge + last-touch + sourced phones;
  pool count unchanged (84,680); review queue usable.

### Session 4 — M3 engagements timeline (spec §1 engagements, §2 activities)
- Mirror engagements + associations; derive into activities
  (source='hubspot', external_id=hs_object_id); timeline on contact page.
- Body policy: previews only in bulk; full text lazily for contact-associated sales
  emails (open question 1 in spec — ask Brandon at this gate if unresolved).
- GATE (UI): Henry Li's page shows the Jan '24 notes + Jul '26 email summary.

## Working style

Task list per session; verification step at the end of each. If something in the spec
turns out to be wrong against the real repo, say so and propose the fix — don't silently
diverge. Never fabricate HubSpot data in tests; use the real read-only token against the
real portal (it's Brandon's own data). Commit per logical unit on the feature branch;
don't merge to main without Brandon.
