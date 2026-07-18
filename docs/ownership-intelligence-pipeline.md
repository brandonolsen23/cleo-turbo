# Ownership Intelligence Pipeline — locked build spec

> Productizes AI adjudication of ownership groups: the anchor-collision dossier
> builder and the Claude rulings piloted 2026-07-07 become a nightly engine —
> dossiers in, structured rulings + facts + merge proposals out, everything
> landing in a human review queue, with an earned-autonomy ladder for eventual
> auto-apply. Locked by Brandon Olsen with Claude 2026-07-07; grounded the same
> day against the repo (read-only; every file/line reference verified; no code
> or DB modified). Executable without the conversation that produced it.
> `docs/data-doctrine.md` is law; this document amends it only where Section 12
> says so.

## 1. Decisions (locked)

| # | Decision | Rationale |
|---|---|---|
| D1 | New table `group_facts` (migration 038): searchable structured intelligence keyed to `auto_group_id` (AGRP_), one row per (field, value) with source, confidence, and `effective_from/to` timelines, plus an FTS5 index over (field, value). Machine-sourced facts are **interpretation** bucket (regenerable by re-adjudication); `source='human'` facts are **judgment**. Neither is ever compiler-dropped. | Everything the adjudicator learns must be findable in the app ("who runs Skyline?", "which groups sit at 1885 Marine Dr?"). Narrative alone is unqueryable; facts are the index. AGRP keying follows doctrine §4.3 — new layers attach to auto_groups. |
| D2 | New table `adjudications` (migration 038): one append-only row per adjudication run of a cluster — model, prompt_version, ruling, confidence, narrative, merge proposals, worklist, tokens/cost, status `pending_review → approved/rejected` (or `auto_applied` once D5 is earned). Nothing touches product tables until review. | Every AI ruling is a recorded, gradeable event. Append-only makes precision measurable per model/prompt/band — what the autonomy ladder runs on. |
| D3 | Runner at `engines/adjudicator/` (`run.py`); `scripts/build_adjudication_dossiers.py` promoted into it as `dossiers.py`. Anthropic **Batch API**, model tiering (haiku-class triage for single-signature obvious cases, sonnet-class for tangles), web-search tool where available, reusing the existing `.env` key and `ai_usage` logging. Output is a strict JSON contract (§5.4) validated before any DB write; fact/link portions re-validated through `POST /api/portfolio/capture?dry_run=true`. | The plumbing exists (`cleo/web/routes/ai.py`); the pilot proved the reasoning. Batch halves token cost; nightly cadence needs no latency. Validation-before-write keeps a hallucinated payload from ever touching the DB. |
| D4 | Review queue: `/api/adjudications` routes + a Review page listing pending adjudications with narrative, facts, merge proposals, confidence. Approve → capture commit + `execute_merge` for approved merge proposals + facts flip to `committed`. Reject → `rejected` with a reason (feeds prompt improvement). **Every approve/reject also writes an `auto_group_verdicts` row** — verdicts remain the single grading set. | One queue, one grading currency. Reusing the Phase 1b verdict store means adjudicator precision and grouping-algorithm precision are measured in the same table. |
| D5 | Autonomy ladder (doctrine amendment, §7.4): auto-apply per confidence band only after measured precision on ≥100 graded adjudications in that band exceeds a Brandon-set threshold (default 98%); always reversible (unmerge + facts soft-delete); a random 5% of auto-applied runs surface in the review queue for audit; drift alarm on Data Quality if audit disagreement >2%. | "Merges never automatic" was written before there was a way to *earn* automation. The ladder keeps the safety property (reversible, audited) while letting proven bands stop consuming Brandon's time. |
| D6 | GW worklist: `gw_worklist_item` facts render as a ranked queue in the app, ranked by expected yield (dark properties on a claimed portfolio). Pulling a GW file that resolves a worklist item auto-links the ingest back to the adjudication that requested it. | The Strongman deep-dive cracked a 20/22-dark portfolio with one reverse-address pull. The adjudicator knows which GW pulls pay; the worklist turns that into Brandon's highest-yield 10 minutes in GeoWarehouse. |
| D7 | Nightly launchd batch of N clusters (default 25) with a per-night cost ceiling (default US$2.00, env-set); an adjudicator freshness card on Data Quality. | ~$0.66/night at the default mix (§9.2) clears the 681-cluster backlog in ~28 nights for under $20. The ceiling makes cost a non-event; the card makes staleness visible per doctrine D5. |
| D8 | Narrative markdown lives in a **new `group_profile.narrative_md` column** (migration 038), riding the capture payload as `group.narrative_md`. `group_profile.summary` stays the short one-liner. | Decided after reading the schema (`cleo/database/schema.py:646-668`): `summary` is already the capture payload's short blurb; overloading it would break existing semantics. A dedicated column keeps the long-form dossier renderable on the group page. |

Ruling vocabulary (fixed enum, everywhere): **UMBRELLA** (one beneficial owner
behind many entities) · **LINEAGE** (predecessor/successor entities, date-ranged)
· **MANAGED** (property/asset-manager signature, not ownership) · **SPLIT** (≥2
unrelated owners; one group each) · **REVIEW** (cannot rule at required
confidence; route to human with reasons).

## 2. What exists today (verified 2026-07-07, read-only)

### 2.1 The pilot

- `scripts/build_adjudication_dossiers.py` finds anchor-collision clusters:
  corporate signatures (mailing address_unit, phone, contact fingerprint)
  spanning many differently-named entities with no dominant stem — the cases the
  discovery engine's dominance rule declines to promote. Locked in-file
  thresholds: `VOLUME_MIN=10`, `DOMINANCE_MAX=0.5`, `ENTITIES_MIN=5`,
  `UNION_MIN_SHARED_SIDES=2`, `DOSSIER_CHAR_BUDGET=2600` (~2.5KB/dossier). Run of
  2026-07-07: **681 clusters, 14,572 distinct properties**; top 30 exported to
  `data/adjudication_dossiers_pilot.json`. Read-only on the DB (`mode=ro` URI).
- Claude adjudicated three clusters in-session with world-knowledge and
  date-range reasoning: **Skyline** (UMBRELLA, 33 entities), **Drimmer/Starlight**
  (UMBRELLA + lineage, 268 entities), **Dundee/Dream** (LINEAGE + one MANAGED +
  one REVIEW). A manual deep-dive on **The Strongman Group** cracked a
  20-of-22-dark portfolio via reverse-address (1885 Marine Dr, North Vancouver)
  + web verification — the D6 template.

### 2.2 Verified interfaces this spec builds on

| Interface | Where (verified) | What matters here |
|---|---|---|
| Anthropic client | `cleo/web/routes/ai.py:166` `_make_anthropic_client()` → `anthropic.Anthropic()` picks up `ANTHROPIC_API_KEY` | Reuse this factory — no new client config. |
| API key | `.env` line 1 at repo root has `ANTHROPIC_API_KEY` set (verified present; value not read) | Working key exists. `load_dotenv` runs only in `cleo/web/app.py:14-17` — **the runner must call `load_dotenv` itself**. |
| Model config | `ai.py:36` `DEFAULT_MODEL = os.environ.get("AI_MODEL", "claude-opus-4-7")` | Sidebar default is opus-class; the runner uses its own env vars (§5.3) so tiering never fights the sidebar. |
| Usage logging | `ai.py` inserts into `ai_usage(user_id, input_tokens, output_tokens, cached_tokens, tool_calls, model, route_at_open, first_user_message)` | Runner logs one row per cluster: `route_at_open='adjudicator:batch'`, `first_user_message=cluster_id`. |
| Capture endpoint | `cleo/web/routes/portfolio.py:123` `def capture(payload, dry_run: bool = Query(True), apply_merges …)`; port 8099; JWT via `get_current_user` | The one validated door. Runner POSTs `dry_run=true`; review-approve commits `dry_run=false`. Runner authenticates like the frontend (service login, creds in `.env`). |
| Merge ops | `cleo/database/group_merge_ops.py:28` `execute_merge(db, source_id, target_id)`; `resolve_target` follows `group_merges` rows `WHERE unmerged_at IS NULL` | GRP-level merge; reversal = set `unmerged_at` (schema-supported). AGRP merges go through `auto_group_user_edits` + Stage Z replay. |
| Verdict store | migration 037 — `auto_group_verdicts(auto_group_id, scope 'group'/'member', member_ref, verdict 'confirm'/'reject', reason, actor, created_at)`, append-only, latest-wins | The grading set (D4). Reviews write here with `reason='adjudication:<id>'`. |
| group_profile | `cleo/database/schema.py:646-668` — has `summary TEXT`, no narrative column, keyed `group_id → groups(id)` | D8: 038 adds `narrative_md TEXT`. AGRP pages already surface profile via the GRP→AGRP dispatch in `cleo/web/routes/groups.py`. |
| Migrations | `cleo/database/migrations/` runs 001–037, each self-runs against `data/cleo.db` | This spec's schema work is **038** (next free number). |
| Scheduler precedent | `scripts/rt-daily-run.sh` (launchd-driven, lockfile-aware) | Mirror it: `scripts/adjudicator-nightly.sh` + `com.cleo.adjudicator` plist. |

## 3. D1 — `group_facts` (migration 038)

### 3.1 DDL

```sql
CREATE TABLE IF NOT EXISTS group_facts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    auto_group_id   TEXT NOT NULL,            -- AGRP_ stable id
    field           TEXT NOT NULL CHECK (field IN (
                        'hq_address','phone','principal','entity_alias',
                        'founded','aum_estimate','behavior','origin_story',
                        'website','sector_focus','gw_worklist_item','other')),
    value           TEXT NOT NULL,            -- display/search form
    value_json      TEXT,                     -- structured payload when shaped
    source          TEXT NOT NULL CHECK (source IN
                        ('rt','gw','web','site_scrape','inference','human')),
    source_url      TEXT,
    confidence      REAL,
    effective_from  TEXT,                     -- ISO date; timelines for
    effective_to    TEXT,                     --   principals/entities/aliases
    adjudication_id INTEGER REFERENCES adjudications(id),
    status          TEXT NOT NULL DEFAULT 'proposed'
                        CHECK (status IN ('proposed','committed','retracted')),
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_group_facts_group
    ON group_facts(auto_group_id, field, status);
CREATE INDEX IF NOT EXISTS idx_group_facts_adjudication
    ON group_facts(adjudication_id);
CREATE VIRTUAL TABLE IF NOT EXISTS group_facts_fts USING fts5(
    field, value, content='group_facts', content_rowid='id');
-- plus the three standard external-content sync triggers
-- (AFTER INSERT / AFTER DELETE / AFTER UPDATE on group_facts).
```

### 3.2 Field semantics

| field | value | value_json |
|---|---|---|
| hq_address | display address | `{street, city, province, postal}` |
| phone | digits, engine-normalized | `{raw, label}` |
| principal | person name | `{role, note}` — effective_from/to = tenure ("CEO 2014–2021") |
| entity_alias | SPV/brand spelling | `{kind: 'stem'\|'name'}` — effective range = active dates observed |
| founded | year or ISO date | — |
| aum_estimate | human-readable ("$4.5B AUM") | `{amount, currency, as_of, basis}` |
| behavior | one-line pattern ("buys retail plazas SW Ontario, holds long") | — |
| origin_story | one-line provenance ("spun out of Dundee Realty 2013") | — |
| website | URL | — |
| sector_focus | asset classes / geography | `{asset_classes: [], regions: []}` |
| gw_worklist_item | address or ARN to pull | §8.2 shape (required) |
| other | anything defensible | free |

### 3.3 Laws

1. **Bucket**: machine sources (`rt|gw|web|site_scrape|inference`) =
   interpretation — regenerable by re-adjudication, retractable by code.
   `human` = judgment — durable; only Brandon retracts. Not in
   `drop_derived_tables()`, never compiler-touched; the bucket governs *who may
   retract*, not lifecycle.
2. **Lifecycle**: `proposed` (pending adjudication) → `committed` on approval or
   earned auto-apply → soft-delete only (`retracted`). No physical DELETE.
3. **Provenance displayed** (doctrine D8): every fact renders with its source
   tag and clickable `source_url` when present.
4. **Timelines**: `effective_from/to` encode lineage — a Dundee→Dream principal
   or alias carries date ranges; the group page renders a timeline.
5. **App search** joins `group_facts_fts` so "1885 Marine" or a principal's name
   finds the group. Only `committed` facts surface by default.

## 4. D2 — `adjudications` (migration 038)

### 4.1 DDL

```sql
CREATE TABLE IF NOT EXISTS adjudications (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_id      TEXT NOT NULL,            -- e.g. COLL_007 (dossier id)
    dossier_json    TEXT NOT NULL,            -- exact dossier sent (replay)
    model           TEXT NOT NULL,
    prompt_version  TEXT NOT NULL,            -- e.g. 'adj-v1'
    ruling          TEXT NOT NULL CHECK (ruling IN
                        ('umbrella','lineage','managed','split','review')),
    confidence      REAL,
    narrative_md    TEXT,
    merge_proposals TEXT,                     -- JSON array (§5.4)
    facts_emitted   INTEGER NOT NULL DEFAULT 0,
    gw_worklist     TEXT,                     -- JSON array (§8.2)
    capture_payloads TEXT,                    -- JSON: capture payload(s) built
    input_tokens    INTEGER, output_tokens INTEGER,
    web_searches    INTEGER DEFAULT 0,
    cost_usd        REAL,
    status          TEXT NOT NULL DEFAULT 'pending_review' CHECK (status IN
                        ('pending_review','approved','rejected','auto_applied')),
    reviewed_by     TEXT, reviewed_at TEXT, reject_reason TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_adjudications_status
    ON adjudications(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_adjudications_cluster
    ON adjudications(cluster_id, created_at DESC);
```

Laws: **append-only** — re-running a cluster inserts a new row; the queue shows
the latest per cluster_id; only status/review columns mutate, and only via the
review endpoints (§6) or D5 auto-apply; never truncated (system bucket, like
`ai_usage`). `dossier_json` + `prompt_version` + `model` make every ruling
reproducible and every precision number attributable. `cost_usd` is computed
from tokens at the `costs.py` price table so the nightly ceiling (§9) is
enforceable without a billing API.

## 5. D3 — the runner: `engines/adjudicator/`

### 5.1 Layout

```
engines/adjudicator/
  __init__.py
  dossiers.py     # promoted from scripts/build_adjudication_dossiers.py:
                  #   same thresholds + read-only discipline, callable
                  #   (build_dossiers(db_path, limit, exclude_cluster_ids)),
                  #   can emit ALL clusters, not just top 30
  prompts.py      # versioned system + task prompts (PROMPT_VERSION='adj-v1')
  contract.py     # pydantic models for §5.4 + validator
  tiering.py      # triage/deep routing rule (§5.3)
  costs.py        # price table, per-run cost math, ceiling enforcement
  run.py          # orchestrator (batch submit, poll, validate, persist)
scripts/adjudicator-nightly.sh   # launchd entry point (§9)
```

`scripts/build_adjudication_dossiers.py` stays as a thin shim calling the
engine (same CLI output); the hardcoded Cowork `OUT_COPY` path is dropped.

### 5.2 Steps per cluster (run.py)

1. **Select** — clusters with no adjudication at the current `prompt_version`,
   ranked by dossier score (properties × recency), take N.
2. **Dossier** — build fresh from the live DB (read-only URI); store the exact
   JSON in `adjudications.dossier_json`.
3. **Tier** — route to triage or deep (§5.3).
4. **Submit** — one Anthropic **Batch API** job for the night
   (`client.messages.batches.create`), via the `ai.py` client factory.
   Deep-tier requests include the server-side web-search tool when the
   model/API combination supports it; triage never does.
5. **Poll + parse** — parse each result against the contract. A malformed
   response gets ONE repair round-trip; still malformed → synthesize
   `ruling='review'`, `confidence=0`, narrative = raw text, move on.
6. **Validate** — contract checks (§5.5), then POST each emitted capture
   payload to `http://localhost:8099/api/portfolio/capture?dry_run=true`. A 422
   stores the errors in the narrative footer and downgrades the ruling to
   `review`. Nothing commits here — dry_run only.
7. **Persist** — `adjudications` row (`pending_review`), `group_facts` rows
   (`proposed`), `ai_usage` row.
8. **Stop** — at N clusters or when estimated cost hits the ceiling. Partial
   nights are fine; selection resumes next night.

### 5.3 Model tiering

| Tier | Trigger | Model (env) | Web search |
|---|---|---|---|
| triage | single-signature cluster AND ≤8 entities AND one auto_group holds >70% of sides — "obvious" | `ADJUDICATOR_MODEL_TRIAGE`, default `claude-haiku-4-5` | no |
| deep | everything else (multi-anchor tangles, lineage candidates, SPLIT suspects) | `ADJUDICATOR_MODEL_DEEP`, default `claude-sonnet-4-6` | yes, ≤5 searches/cluster |

A triage ruling with `confidence < 0.85` re-queues to the deep tier the same
night (counts against the ceiling). Model ids are env-only;
`adjudications.model` records what actually ran.

### 5.4 Output contract (the exact JSON the model must return)

```json
{
  "cluster_id": "COLL_007",
  "ruling": "umbrella | lineage | managed | split | review",
  "confidence": 0.93,
  "narrative_md": "## Who this is\n...(markdown, <= 4000 chars)",
  "groups": [
    {"display_name": "Skyline Group of Companies",
     "auto_group_ids": ["AGRP_004512", "AGRP_099213"],
     "entities": ["skyline", "1865087 ontario"],
     "capture": { "…capture payload per docs/portfolio-capture.md,
                   plus group.narrative_md and facts[] (§12.2)…" }}
  ],
  "merge_proposals": [
    {"kind": "agrp", "source": "AGRP_099213", "target": "AGRP_004512",
     "reason": "same phone + principal; entities are SPVs of one owner"}
  ],
  "facts": [
    {"auto_group_id": "AGRP_004512", "field": "principal",
     "value": "Jason Castellan", "value_json": "{\"role\":\"co-founder/CEO\"}",
     "source": "web", "source_url": "https://…", "confidence": 0.95,
     "effective_from": "2005-01-01", "effective_to": null}
  ],
  "gw_worklist": [
    {"address": "1885 Marine Dr", "city": "North Vancouver", "arn": null,
     "why": "reverse-address exposes SPVs for 20 dark claimed properties",
     "expected_yield": 20}
  ],
  "web_searches_used": 3,
  "review_reasons": []
}
```

| Field | Rules |
|---|---|
| ruling / confidence | enum above; confidence ∈ [0,1]. `split` requires ≥2 `groups`; `review` requires non-empty `review_reasons` and emits NO merge_proposals. |
| narrative_md | Required except for review. ≤4000 chars. What Brandon reads first. |
| groups[] | ≥1 unless ruling=review. `auto_group_ids` must appear in the dossier — the model may not invent AGRP ids. `capture` must validate against the capture schema. |
| merge_proposals[] | `kind` ∈ {`agrp`,`grp`}. agrp → `auto_group_user_edits` merge (Stage-Z-replayed). grp → capture `merge_candidates` → `execute_merge`. Source/target must exist. |
| facts[] | §3 checks: field in enum; `web`/`site_scrape` ⇒ `source_url` required; `inference` ⇒ confidence ≤0.8. |
| gw_worklist[] | address+city required (ARN optional); `expected_yield` = integer count of dark properties the pull should light up. |

### 5.5 Validation (contract.py, before any DB write)

1. JSON parses and pydantic-validates; enum and cross-field rules above.
2. **No-web fallback**: if web search was unavailable or unused on a deep-tier
   tangle, confidence caps at **0.75** (clamp noted in `review_reasons`), and
   rulings that depend on world knowledge absent from the dossier (lineage
   claims, brand identity) without a supporting search or `source_url`
   downgrade to `review`. More REVIEW rulings in no-web mode is the designed
   fallback, not an error.
3. Every fact's `auto_group_id` must exist in the dossier, or be the
   placeholder `$group[i]` resolved after capture commit returns group ids.
4. Capture payloads must dry-run clean (§5.2 step 6) — a 422 downgrades; never
   "fix up" a payload silently.

## 6. D4 — review queue

### 6.1 API (`cleo/web/routes/adjudications.py`, at `/api/adjudications`)

| Route | Behavior |
|---|---|
| `GET /api/adjudications?status=pending_review` | List (latest per cluster_id): ruling, confidence, fact/merge counts, cost, created_at. |
| `GET /api/adjudications/{id}` | Full record: narrative_md, dossier, proposed facts, merge_proposals, gw_worklist, capture payloads. |
| `POST /api/adjudications/{id}/approve` | Body `{apply_merges: bool, approved_merge_indexes: [int], edits?}`. Runs §6.3. |
| `POST /api/adjudications/{id}/reject` | Body `{reason: string}` (required). Runs §6.4. |
| `GET /api/adjudications/stats` | Per confidence band: graded count, approve rate, audit disagreement — feeds the D5 gate and the Data Quality card. |

Standard JWT (`get_current_user`); approve/reject also writes `audit_log`.

### 6.2 Review page (frontend `AdjudicationsPage`, route `/adjudications`)

List → detail. Detail shows, in order: ruling badge + confidence, rendered
narrative, facts table (field/value/source/confidence, source links), merge
proposals (each with evidence line + include/exclude toggle), gw_worklist
items, dossier (collapsed). Buttons: Approve (with merge toggles), Reject
(reason required). Ordering: non-review rulings by confidence desc, then review.

### 6.3 Approve flow

1. POST stored capture payload(s) to `/api/portfolio/capture?dry_run=false`
   (+`apply_merges=true` only when the reviewer approved grp-kind proposals —
   this is what invokes `execute_merge`, per the existing endpoint).
2. Execute approved `agrp`-kind merges via the existing auto_group user-edit
   path (`auto_group_user_edits` action merge) so Stage Z replays them.
3. Flip this adjudication's `group_facts` rows `proposed → committed`.
4. Write `auto_group_verdicts`: one row per ruled group — `(auto_group_id,
   scope='group', verdict='confirm', reason='adjudication:{id}',
   actor=<reviewer>)`. **This row is the grade.**
5. Stamp `status='approved'`, `reviewed_by`, `reviewed_at`.

### 6.4 Reject flow

1. Stamp `status='rejected'`, `reject_reason`, `reviewed_by/at`. Facts stay
   `proposed` (never surface); a nightly sweep retracts them.
2. Write `auto_group_verdicts` rows with `verdict='reject'`,
   `reason='adjudication:{id}: {reject_reason}'`.
3. Reject reasons are the prompt-improvement corpus: before any
   `prompt_version` bump, re-run all rejected dossiers with the new prompt on a
   /tmp DB copy and hand-compare (the adjudicator's scoreboard rule).

## 7. D5 — autonomy ladder

### 7.1 Bands and the gate

Confidence bands `[0.90,0.95)`, `[0.95,0.98)`, `[0.98,1.00]`. Per band, per
prompt_version+tier, auto-apply unlocks ONLY when: ≥ **100 graded
adjudications** exist in the band (graded = approved/rejected by Brandon); AND
measured precision (approved ÷ graded) **exceeds the threshold** — default
**98%**, settable only by Brandon in Settings; AND Brandon flips the band's
auto-apply switch in the UI (offered, never assumed). Below 0.90 there is no
ladder: always human review. A `prompt_version` or model change resets every
band's counter to zero.

### 7.2 What auto-apply does

Exactly §6.3 with `status='auto_applied'`, `reviewed_by='autonomy:band'` —
except merges auto-apply only in the top band; lower bands auto-commit facts +
capture links and leave merges pending. No verdict row is written for the
auto-applied portion (machines don't grade themselves); verdicts come from the
audit sample.

### 7.3 Always reversible, always audited

- **Reversal**: unmerge via `group_merges.unmerged_at` (grp) / compensating
  `auto_group_user_edits` edit (agrp); facts flip to `retracted`; capture links
  detach through the existing capture review path. One button on the detail
  page: "Reverse this adjudication."
- **Audit**: a random **5%** of auto-applied adjudications surface in the
  review queue flagged AUDIT; Brandon grades them normally.
- **Drift alarm**: audit disagreement (audit rejects ÷ audited) > **2%** turns
  the Data Quality adjudicator card red and suspends that band's auto-apply
  until Brandon re-enables it.

### 7.4 Doctrine amendment (explicit text)

Add to `docs/data-doctrine.md` Section 1 as a dated rider, recorded per its
Section 10 (amends the merge law stated in doctrine D2's "nothing
auto-resolves" and the invariant "merges are human-approved only", product-map
§6.5 / capture spec D4):

> **Amendment 2026-07-07 (Ownership Intelligence Pipeline D5).** "Merges never
> automatic" becomes "**never automatic until earned, always reversible, always
> audited.**" A machine may apply a ruling class automatically only after ≥100
> human-graded adjudications in that confidence band show precision above a
> Brandon-set threshold (default 98%); every automatic action must be
> reversible in one step (unmerge + fact soft-delete); a random 5% of automatic
> actions are re-queued for human audit, and auto-apply suspends if audit
> disagreement exceeds 2%. Human review remains the default below the earned
> band.

## 8. D6 — GW worklist

Committed `gw_worklist_item` facts render as a ranked queue — page
`/gw-worklist`, backed by `GET /api/adjudications/gw-worklist`. Rank =
`expected_yield` descending. Each item shows address/city/ARN, the why, the
group, and a link to its adjudication. The Strongman pattern is the template:
one reverse-address pull resolved 20 of 22 dark properties.

Item shape (`value_json` of the fact):

```json
{"address": "…", "city": "…", "arn": null, "why": "…",
 "expected_yield": 20, "status": "open | resolved | abandoned",
 "resolved_by_ingest": null}
```

Auto-link on ingest: after each GW ingest, a hook in `engines/gw/watcher.py`
matches the report's ARN/address (engine-normalized, never hand-parsed) against
open worklist items; a hit sets `status='resolved'`, records the ingest
reference, and the adjudication detail page shows "resolved by GW ingest
<date>". The watcher's compiler bypass is intentional and untouched — the hook
is read-plus-fact-update only.

## 9. D7 — scheduling + cost

### 9.1 Scheduling

- `scripts/adjudicator-nightly.sh` (mirrors `scripts/rt-daily-run.sh`): env
  sourcing, lockfile, then
  `PYTHONPATH=. .venv/bin/python -m engines.adjudicator.run --limit 25`.
- launchd plist `com.cleo.adjudicator.plist`, nightly 02:30 (after the RT
  window). Env: `ADJUDICATOR_NIGHTLY_LIMIT` (25), `ADJUDICATOR_NIGHTLY_BUDGET_USD`
  (2.00), `ADJUDICATOR_MODEL_TRIAGE`, `ADJUDICATOR_MODEL_DEEP`.
- **Freshness card** on Data Quality (doctrine D5 pattern): last run, clusters
  adjudicated, pending_review count, last-night + cumulative cost, audit
  disagreement %. Red when no run in 48h or the drift alarm fires.

### 9.2 Cost math (shown, so the ceiling is checkable)

Per cluster: dossier ~2.5KB ≈ 750 tok in; system+task prompt ~2,000 tok
(prompt-cached across the batch); output ~2KB ≈ 600–1,500 tok. Deep tier adds
~9,000 tok of web-search results at ≤5 searches. Assumed list prices (pin in
`costs.py`; re-verify at build): haiku-class $1.00/$5.00 per MTok in/out,
sonnet-class $3.00/$15.00, web search $10/1,000 searches. Batch = 50% off tokens.

| Tier | In tok | Out tok | Token cost (batch) | Web | Total/cluster |
|---|---|---|---|---|---|
| triage (haiku) | ~3,000 | ~800 | 3,000×$0.50/M + 800×$2.50/M = $0.0035 | — | **~$0.004** |
| deep (sonnet) | ~12,000 | ~1,500 | 12,000×$1.50/M + 1,500×$7.50/M = $0.029 | 3×$0.01 | **~$0.06** |

Default night (25 clusters ≈ 15 triage + 10 deep): 15×$0.004 + 10×$0.06 ≈
**$0.66/night**; the $2.00 ceiling is ~3× headroom. Full 681-cluster backlog ≈
28 nights ≈ **$18–20 total**. If batch or web search proves unavailable for a
model, non-batch sonnet at full price is ~$0.13/cluster — the ceiling simply
forces N down (runner stops submitting at the ceiling, §5.2 step 8).

## 10. Milestones

Each accepted **in the UI** (doctrine D6); built/tested on /tmp DB copies first.

**M1 — Schema + facts + narrative visible on a group page.**
Migration 038 (`group_facts`, `adjudications`, `group_profile.narrative_md`);
capture payload accepts `facts[]` + `group.narrative_md`; group page renders a
Facts panel and the narrative. Seed by re-running the hand-done **Strongman**
capture (facts + narrative from the 2026-07-07 deep-dive) through the extended
endpoint.
*Accept when:* the Strongman group page at `localhost:5174` shows the narrative
and facts (hq_address, principal, gw_worklist_item rows) with source tags, and
FTS search finds the group by "1885 Marine".

**M2 — Runner on the 27 remaining pilot dossiers.**
`engines/adjudicator/` built; batch run over the 27 top-30 dossiers not
adjudicated in the pilot session (30 minus Skyline, Drimmer/Starlight,
Dundee/Dream); all land `pending_review`.
*Accept when:* 27 adjudication rows exist with rulings, narratives, proposed
facts, dry-run-validated capture payloads, ai_usage rows, and visible total
cost — and the live DB shows zero committed facts/links from the run.

**M3 — Review queue; Brandon grades the 27.**
Routes + AdjudicationsPage per §6.
*Accept when:* Brandon approves/rejects all 27 in the UI; approved ones show
facts+narrative+properties on their group pages; every decision produced an
`auto_group_verdicts` row; rejects carry reasons; `/api/adjudications/stats`
shows per-band precision.

**M4 — GW worklist page.**
§8, including the watcher auto-link hook.
*Accept when:* the worklist ranks items by expected yield; pulling one real GW
file for a top item flips it to resolved on the page and links back to its
adjudication.

**M5 — Autonomy ladder activation.**
§7: stats gate, band switches in Settings, audit sampling, drift alarm,
reversal button. Nightly runs continue until ≥100 graded exist in a band.
*Accept when:* with <100 graded, no band is unlockable (UI shows progress); on
a /tmp copy seeded past the gate, the band unlocks only after Brandon flips the
switch; an auto-applied run appears with AUDIT sampling; a forced audit
disagreement >2% turns the Data Quality card red and suspends auto-apply.

## 11. Runbook

```
# 0. Everything destructive on a copy first (doctrine D6):
cp data/cleo.db /tmp/cleo_adjudicator_test.db

# 1. Migration 038 (idempotent; refuses to run without an explicit path —
#    copy the migrate_portfolio_capture.py guard):
.venv/bin/python cleo/database/migrations/038_ownership_intelligence.py \
    /tmp/cleo_adjudicator_test.db
# Live DB only after M1 acceptance on the copy.

# 2. Build dossiers (read-only; safe against the live DB):
PYTHONPATH=. .venv/bin/python -m engines.adjudicator.dossiers

# 3. Manual run against a test API (CLEO_DB_PATH serves the copy on 8099):
PYTHONPATH=. .venv/bin/python -m engines.adjudicator.run --limit 2 --verbose

# 4. Review at http://localhost:5174/adjudications (approve/reject).

# 5. Nightly install (after M3 acceptance):
cp scripts/com.cleo.adjudicator.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.cleo.adjudicator.plist
```

Rules that bite: the runner must `load_dotenv` itself (§2.2); dossier
generation stays read-only (`mode=ro` URI); the runner writes only
`adjudications` / `group_facts(proposed)` / `ai_usage` — commits happen only
through review approve or an earned D5 band; `dry_run` stays default-true on
capture.

## 12. Relationship to other documents

**Amends** — `docs/data-doctrine.md`: the §7.4 rider amends the merge law
("nothing auto-resolves" / "merges are human-approved only"), recorded per
doctrine §10 with Brandon's sign-off, dated 2026-07-07. All other doctrine law
(buckets, precedence, D6 UI acceptance, /tmp rule, D8 provenance) binds this
spec unchanged.

**Extends** — `docs/portfolio-capture.md` / capture endpoint: the payload gains
top-level `facts: []` (§5.4 shape; written to `group_facts` under the payload's
dry_run/commit semantics) and `group.narrative_md` (written to
`group_profile.narrative_md`). Everything else in the capture contract —
dry_run default, apply_merges gate, ARN normalization, specificity rejections,
precedence — is unchanged; capture remains the single validated door for the
fact/link portions of every adjudication. Also extends the Data Quality page
(freshness card §9.1, drift alarm §7.3).

**Consumes** — `scripts/build_adjudication_dossiers.py` (promoted into
`engines/adjudicator/dossiers.py`, thresholds and read-only discipline carried
verbatim); `auto_group_verdicts` (migration 037, Phase 1b — the grading set:
reviews write it, the D5 gate and the grouping scoreboard read it; one verdict
currency everywhere); `cleo/web/routes/ai.py` (client factory, `.env` key,
prompt-caching pattern, `ai_usage` logging — reused, not duplicated);
`execute_merge` / `group_merges` / `auto_group_user_edits` (existing merge
machinery; this spec adds no new mechanism, only proposals routed through it).

## 13. Amending this spec

Section 1 changes only with Brandon's explicit sign-off, recorded here with a
date. Operational thresholds (tiering rule, bands, budget, N) live in
env/config per §5.3/§7.1/§9.1 — update the description when they legitimately
move, never the decisions table without a ruling.
