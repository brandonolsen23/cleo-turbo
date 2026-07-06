# Cleo Data Doctrine

> Master data-governance spec for Cleo Turbo. Locked by Brandon Olsen with Claude
> on 2026-07-06 and grounded the same day against the code and a read-only look at
> `data/cleo.db` (plain `SELECT`/`.schema` queries only; audit numbers carried from
> `docs/product-map.md`, written the same day). This document states law: what a
> datum *is*, who wins an ownership conflict, what the user-facing owner entity is,
> how the grouping algorithm is allowed to change, and how changes get accepted.
> Read `CLAUDE.md` for working rules and `docs/product-map.md` for the full audit
> this builds on. Where an older document disagrees with this one, this one wins —
> Section 8 lists every overlapping document and its disposition.

## 1. Decisions (locked)

| # | Decision | Rationale |
|---|---|---|
| D1 | Every datum is exactly one of three buckets: **Evidence** (append-only source records, never edited or deleted), **Interpretation** (everything computed from evidence — disposable, rebuilt whenever code improves), **Judgment** (human decisions — durable overlays keyed to stable IDs, replayed after every rebuild). | Makes "can I rebuild/delete this?" answerable without archaeology. The derived-vs-CRM split in CLAUDE.md was this doctrine's ancestor; the buckets subsume it. |
| D2 | Ownership display precedence: **human judgment > GW registry-confirmed > RT-derived > web-asserted (capture)**. Conflicts surface for review; nothing auto-resolves. | This is the shipped behavior of `cleo/compiler/owner_overrides.py` (Section 3), now stated as law rather than implementation accident. |
| D3 | Legacy `groups` (GRP_) are **retired as an owner entity**. `auto_groups` (AGRP_) is the ONLY user-facing owner. GRP_ demotes to a derived SPV ledger in the interpretation bucket: frozen (no new identity work), never surfaced in the UI as an owner, never merged or maintained. NOT physically deleted (Section 4 enumerates why). | One Group concept. 136,266 GRP_ rows are one-per-SPV-spelling — plumbing, not product. Phase D already cut the Groups routes over; this finishes the decision. |
| D4 | **The Groups improvement flywheel**: every auto-group surfaces its evidence in the UI; one-tap confirm/reject writes verdicts; accumulated verdicts form the ground-truth set; **no grouping-algorithm change ships without a scoreboard run against ground truth** showing agreement vs the current version and zero regression on confirmed verdicts. | Dialing in the n-gram/atom algorithm yields the most fruit. Untested algorithm changes silently reshuffle 118k groups; the scoreboard makes improvement provable. |
| D5 | Layer-1 observability: RT gets a high-water-mark scheduled pull plus an in-app freshness tile that alarms; GW gets a watched-folder ingested-vs-pending indicator; POIs get a monthly refresh **later, not now**; portfolio URLs stay manual via the capture pipeline. | Evidence rot is silent today — RT has been stalled since 2026-06-19 and was found by audit, not by an alarm. |
| D6 | Any user-facing change is **accepted in the UI, not at the DB level**. All destructive or testing work runs on `/tmp` copies of the DB. | Brandon does not use a CLI (CLAUDE.md working rule). The DB is not the product surface; a change that can't be seen in the app isn't done. |
| D7 | **Proper first — no interim shortcuts** for ownership data. No stopgap labeling (e.g., list-tags standing in for ownership) that creates a second, lesser version of the truth to migrate later. Work waits for the correct layer rather than shipping a shadow copy. | Owner ruling 2026-07-06: "proper later will never happen and then become an issue." Shortcuts are how the legacy/auto-groups split happened in the first place. |
| D8 | **Provenance is always displayed.** Every owner name, contact, or fact shown in the UI carries a visible tag for its source (RT, GW, website capture, human edit). The website-derived common name is the group's display label; the GW and RT names for each individual property are preserved and shown per-property with their source tags — never replaced, never hidden. | Owner ruling 2026-07-06. Traceability to raw data is the product's core promise; a name without a source is a claim, not data. |

## 2. D1 — The three buckets

Every table, file, and field in the system belongs to exactly one bucket. When
adding anything new, classify it first; the bucket dictates its lifecycle.

### 2.1 Bucket definitions and laws

**Evidence** — what a source said, verbatim or faithfully projected.
- Append-only. Never edited, never deleted, never "fixed."
- A wrong evidence record is corrected by appending a newer record (RT re-scrape,
  fresh GW report), never by mutating the old one.
- The canonical store is on disk: `raw-data/{rt,gw}/`, `clean-data/{rt,gw,osm}/`
  (engine-normalized projections of raw), the GW ingest folder watched by
  `engines/gw/watcher.py`, and the portfolio raw scrapes in OneDrive
  `00_Prospecting/Portfolio Capture/raw-scrapes/`.
- The DB rows for evidence are *projections*: the compiler rebuilds them from
  clean-data, so they are physically rebuildable — but their content is evidence
  and is never hand-edited. Corrections go upstream (re-scrape / re-parse),
  never into the row.

**Interpretation** — everything computed from evidence: parses, normalizations,
matches, resolutions, clusters, analytics.
- Disposable and rebuildable, never precious. When the code improves, rebuild.
- No human ever edits an interpretation row directly; a human who disagrees with
  an interpretation records a **judgment**, and the rebuild replays it.
- It is always safe to drop and regenerate this bucket, *provided* every judgment
  overlay is keyed to stable IDs and replayed afterward.

**Judgment** — human decisions: confirm, reject, rename, detach, attach, merge,
capture commits, notes, deals.
- Durable. Survives every rebuild. Never truncated by the compiler.
- Keyed only to **stable IDs**: ARN (parcel), RT `source_id` + side (party-side),
  `AGRP_` auto_group_id, `PRO_/CON_` ids (stable via `id_mappings`/`app_meta`).
  A judgment keyed to an unstable artifact (a cluster row id, a rebuildable
  surrogate key) is a bug — it will orphan on the next rebuild.
- Replayed after every rebuild: `apply_owner_overrides` re-materializes capture
  links (`cleo/compiler/writer.py:1307` final pass), discovery_v2 Stage Z
  (`cleo/discovery_v2/apply_user_edits.py`) replays `auto_group_user_edits`.
  Any new judgment table MUST ship with its replay hook.

### 2.2 Classification of the actual tables

Verified against `sqlite_master` (2026-07-06, read-only) and
`cleo/database/schema.py::drop_derived_tables`. The physical drop list is the
compiler's; the bucket is the doctrine's — they mostly coincide but the bucket
is what governs behavior.

| Bucket | Tables |
|---|---|
| Evidence (DB projections; canonical store is raw-/clean-data) | `transactions`, `transaction_parties`, `transaction_mailing_addresses`, `transaction_brokers`, `transaction_broker_agents`, `gw_assessments`, `gw_sales_history`, `pois` |
| Interpretation (compiler-rebuilt; in `drop_derived_tables`) | `properties`, `contacts`, `groups` (the SPV ledger — see D3), `group_names`, `party_atoms`, `party_fingerprints`, `brand_registry`, all `*_fts` tables |
| Interpretation (discovery_v2-rebuilt, not compiler-dropped) | `auto_groups`, `auto_group_members`, `auto_group_anchors`, `auto_group_anchor_tenures`, `auto_group_analytics`, `auto_contact_tenures`, `contact_brand_tenures`, `auto_conflict_flags`, `anchor_uniqueness`, `legacy_to_auto_group_map`, `group_analytics`, all `brand_*_index` / `brand_*_summary` / `brand_stem*` tables, `phone_summary`, `address_root_summary`, `address_base_summary`, `address_unit_summary`, `contact_fingerprint_summary`, `candidate_clusters`, `operator_candidates`, `operator_candidate_sides`, `operator_candidate_anchors`, `defining_brands`, `places`, `industry_stopwords`, `discovery_runs`, `discovery_evidence`, `discovery_cluster_names`, `atom_discovery_runs`, `_pending_tenures` |
| Judgment (persistent; compiler never touches) | `manual_owner_links`, `manual_properties`, `group_match_keys`, `group_profile`, `group_aliases`, `auto_group_user_edits`, `auto_group_overrides`, `auto_anchor_overrides`, `group_merges`, `group_overrides`, `group_field_overrides`, `contact_field_overrides`, `contact_work_history`, `labeling_sessions`, `labeling_verdicts`, `labeling_links`, `labeling_seeds`, `labeling_reviewed_index`, `discovery_ground_truth`, `discovery_exclusions`, `brand_overrides`, `user_brand_favorites`, `deals`, `lists`, `list_members`, `group_contacts`, `contact_notes`, `group_notes`, `sell_opportunities`, `buy_mandates`, `activities`, `property_enrichment`, `user_stars`, `issues` |
| System (neither evidence nor judgment; infrastructure) | `users`, `audit_log`, `app_meta`, `id_mappings`, `data_issues`, `asset_classes`, `tenant_categories`, `ai_usage` |

Notes that bite:
- `groups` is interpretation even though judgment tables point at it by FK
  (Section 4). The FK targets survive because GRP_ ids are stable across
  rebuilds via `app_meta` — the *ids* are the ledger, the rows are rebuilt.
- `discovery_ground_truth` is judgment but is keyed to **legacy GRP_ ids**
  (`anchor_group_id`, `member_group_ids_json`) and consumed only by the retired
  v1 engine (`cleo/discovery/validation.py`). Section 5.2 supersedes it.
- CLAUDE.md's "Derived tables" list is stale — it omits `party_atoms`,
  `party_fingerprints`, `brand_registry`, which `drop_derived_tables()` does
  drop, and its CRM list omits the capture tables and `auto_group_user_edits`.
  Section 8.3 lists the exact lines to update.

## 3. D2 — Ownership display precedence

When two sources disagree about who owns a parcel, display order is:

1. **Human judgment** — a confirmed capture link, a user edit, an explicit
   override. Wins over everything.
2. **GW registry-confirmed** — `manual_owner_links.registry_confirmed=1` or a
   GW-sourced owner name on the parcel. The registry is authoritative for the
   *registered* owner.
3. **RT-derived** — owner inferred from the most recent Realtrack transaction.
4. **Web-asserted (capture)** — an owner's website claiming the property.

**Conflicts surface for review; they never auto-resolve.** This is exactly what
`cleo/compiler/owner_overrides.py::apply_owner_overrides` already does —
verified in code 2026-07-06:

- `relationship='owns'` links fill only **dark** properties
  (`transaction_count == 0`). A GW-only parcel counts as dark even when GW
  carries a registry SPV name; the registry *name* is preserved and only
  `current_owner_group_id` is set ("web never clobbers the registry name" —
  module docstring).
- If the property has an RT-derived owner that differs, the link is flagged
  `status='conflict'` plus a `data_issues` row (rule `manual_owner_conflict`)
  — **never overwritten**.
- If the existing owner already matches, the link is confirmed
  (`registry_confirmed=1`).
- `manages`/`lists` relationships are recorded but never change ownership.
- Runs as the compiler's final pass and incrementally (`scope_arns`) on capture
  commit; merge redirects are chain-followed via `group_merges`.

Law: any new code path that sets `current_owner_group_id` or
`current_owner_name` must implement this precedence or route through
`apply_owner_overrides`. No exceptions, no "just this once" UPDATE.

## 4. D3 — Legacy groups retired; auto_groups is the owner entity

### 4.1 The ruling

- `auto_groups` (`AGRP_`, built by `cleo/discovery_v2/` from n-gram/atom
  discovery) is the **only** user-facing owner entity, everywhere in the UI.
- Legacy `groups` (`GRP_`, one row per normalized SPV spelling, 136,266 rows,
  all `status='pool'`) is demoted to a **derived SPV ledger** in the
  interpretation bucket:
  - **Frozen** — no new identity work on GRP_: no merges, no dedup passes, no
    name curation, no status lifecycle (already retired per
    `cleo/web/routes/groups.py` docstring).
  - **Never surfaced in the UI as an owner.** An SPV name may appear as a fact
    on a transaction or parcel ("registered to 1234567 Ontario Inc"), but the
    clickable owner is always the auto_group.
  - **Not physically deleted.** The rows and their stable ids stay.

### 4.2 Why not delete — the blast radius (verified by grep, 2026-07-06)

GRP_ ids are load-bearing in these places; deleting the table breaks all of them:

| Dependency | Where | What it does |
|---|---|---|
| `properties.current_owner_group_id` | `cleo/database/schema.py`; read by `cleo/web/routes/{properties,groups,contacts,issues,sell_opportunities,buy_mandates,group_merges}.py`, `cleo/analytics/groups.py`, `cleo/compiler/{writer,owner_overrides,portfolio_capture}.py`, `frontend/src/pages/PropertyDetailPage.tsx`, `frontend/src/types/index.ts` | The materialized owner pointer on every property is a GRP_ id. |
| `manual_owner_links.group_id REFERENCES groups(id)` | schema (verified `.schema manual_owner_links`) | Capture judgment layer attaches at GRP level today. |
| `group_match_keys.group_id REFERENCES groups(id)` | schema | Match-key sweep identity is GRP-keyed. |
| `group_merges` | `cleo/database/group_merge_ops.py`, `cleo/web/routes/{group_merges,portfolio}.py`, `cleo/compiler/{writer,owner_overrides}.py`, `cleo/discovery_v2/seeding.py` | Judgment overlay of GRP→GRP merges; owner_overrides chain-follows it. |
| `legacy_to_auto_group_map` | built by `cleo/discovery_v2/legacy_map.py` (Stage A8); read by `cleo/web/routes/groups.py` (id dispatch line 47; captured-properties join lines 374–530), `cleo/discovery_v2/group_analytics.py` | The bridge: every GRP_ maps to its dominant AGRP_. This is what lets GRP-keyed data surface on auto_group pages. |
| Capture endpoint | `cleo/web/routes/portfolio.py` + `cleo/compiler/portfolio_capture.py` (`upsert_group`) | Creates/updates a legacy GRP_ and attaches links, keys, aliases, profile to it. |
| `discovery_ground_truth` | `cleo/discovery/validation.py` (v1) | Ground truth keyed to GRP_ ids. |
| GRP-keyed judgment overlays | `group_overrides`, `group_field_overrides`, `group_contacts`, `group_notes`, `group_profile`, `group_aliases`, `lists`/`list_members`, `deals` | Years of CRM data pointing at GRP_ ids. |

### 4.3 Migration direction (a build phase, not done today)

Target state: **capture and all future judgment layers attach to auto_groups**
— directly (AGRP-keyed columns) or via `legacy_to_auto_group_map` with
`source='user_attached'` rows for judgments that must land on a specific
auto_group regardless of the algorithm's dominant mapping. What must change:

1. `POST /api/portfolio/capture` accepts/returns an `AGRP_` target; internally
   it may still mint a GRP_ ledger row for the SPV, but the *ownership
   attachment* records the auto_group.
2. `apply_owner_overrides` writes an auto_group pointer (new column or the map
   with `source='user_attached'`), so the UI never needs the GRP hop.
3. Group Detail's captured-properties join (`groups.py` lines 374–530) reads
   the direct attachment instead of `mol.group_id → map`.
4. `group_merges` freezes (no new GRP merges); auto_group merges continue via
   `auto_group_user_edits` + Stage Z.
5. New ground truth is keyed to party-sides and AGRP ids (Section 5.2);
   `discovery_ground_truth` is marked historical.

Until then, the map is the bridge and it is verified complete: 136,266 rows —
every legacy group mapped (product-map §5).

## 5. D4 — The Groups improvement flywheel (the heart)

The single highest-yield investment in Cleo is dialing in the auto-grouping
algorithm. The flywheel makes that dialing safe and measurable.

### 5.1 Current baseline (product-map.md, 2026-07-06)

- 118,192 auto_groups: **182 confirmed / 1,597 probable / 666 candidate /
  115,747 standalone** (0 merged). Standalones are single-member coverage
  fillers (`standalone_coverage.py` guarantees every party-side lands in some
  auto_group).
- 85,001 properties; 19,978 (23.5%) carry an owner group; 63,772 (75.0%) dark.
- Signals used today (`cleo/discovery_v2/`): SPV-name n-grams
  (`brand_*_index`), shared mailing addresses, shared phones, shared contact
  fingerprints, anchor scoring — extracted from ALL FOUR identifier fields
  (`party_name`, `trade_name`, `care_of`, `companies_json`).

### 5.2 The loop, stated as law

1. **Evidence surfacing.** Every auto-group page must show WHY its members are
   grouped: which shared corporate addresses, shared phones, shared contacts,
   and which SPV-name n-grams caused each membership. The data already exists
   (`auto_group_anchors`, `party_fingerprints`, `party_atoms`,
   `brand_*_index`); the UI surface does not. A grouping the user can't
   inspect is a grouping the user can't correct.
2. **One-tap verdicts.** Confirm/reject on a membership (a party-side pair) is
   one tap and writes to the labeling tables — verified schema:
   `labeling_verdicts(session_id, source_id, side, verdict
   'confirmed'|'rejected', left_source_id, left_side, seed_id, rationale,
   created_by)` with `labeling_sessions` (anchored to a party-side) and
   `labeling_seeds` (term + field_type queue driving the session). Verdicts are
   keyed to RT source_id + side — stable IDs, rebuild-proof. Written today via
   `cleo/labeling/operations.py` / `cleo/web/routes/labeling.py` (LabelingPage).
3. **Ground truth.** The accumulated verdict set IS the ground-truth corpus.
   **Verified gap, stated honestly: `cleo/discovery_v2/` contains zero
   references to any `labeling_*` table or ground truth today** — verdicts are
   collected but nothing feeds them back. The old `discovery_ground_truth`
   table is v1-only and GRP-keyed (Section 4.2). Closing this loop is Phase 3.
4. **The scoreboard rule.** NO change to the grouping algorithm (seeding,
   expansion, conflict rules, stopwords, n-gram weighting, tier thresholds)
   ships without a scoreboard run on a /tmp DB copy reporting, versus the
   current shipped version:
   - agreement % on the full labeled pair set, and
   - **zero regressions on confirmed verdicts** (a pair a human confirmed must
     not come apart; a pair a human rejected must not rejoin — a rejoin is a
     hard block, not a warning).

### 5.3 Metrics, precisely

| Metric | Definition |
|---|---|
| Precision on labeled pairs | Of labeled pairs the algorithm groups together, % the human confirmed. Computed per run over all `labeling_verdicts`. |
| Recall on labeled pairs | Of human-confirmed pairs, % the algorithm groups together (reported alongside precision; the tune lever trades these). |
| Coverage | % of owned properties (`current_owner_group_id IS NOT NULL`) attached to a confirmed or probable auto-group (via the map or direct attachment). Baseline: the 182+1,597 tiers cover a sliver of 19,978. |
| Review throughput | Verdicts per session-hour in the UI. If the evidence panel is good, this goes up; it is a product metric, not vanity. |
| Regression count | Confirmed verdicts violated by the candidate run. Must be 0 to ship. |

### 5.4 The dial-in process

`seed → label → tune → re-score → widen`, repeated:

1. **Seed** — pick a target cohort (e.g. multi-property candidates in the
   `candidate` tier, or one brand family) and open a labeling session.
2. **Label** — confirm/reject memberships in the UI using the evidence panel.
3. **Tune** — adjust the algorithm (weights, stopwords, thresholds) in code.
4. **Re-score** — scoreboard run on a /tmp copy; compare precision/recall/
   coverage vs shipped; check regression count == 0.
5. **Widen** — ship, promote tiers, move to the next cohort. Verdicts
   accumulate; the ground-truth set only grows.

## 6. D5 — Layer-1 observability

Evidence channels must announce their own staleness in the app. Current
freshness is discovered by audit — unacceptable.

| Channel | Mechanism (law) | Verified current state |
|---|---|---|
| Realtrack | High-water-mark scheduled pull: the daily scraper (`engines/rt/scraper/daily_scraper.py`) dedupes against known RT ids via `engines/rt/scraper/inventory.py::load_existing_rt_ids` (clean-data filenames ARE the RT ids; raw detail pages parsed for ids) — append-only and idempotent by RT source id, safe to re-run. Plus a **freshness tile on the Data Quality page** showing newest raw batch + newest compiled row, alarming when no new batch lands within the expected window (daily cron ⇒ alarm at ~48h). | **Stalled: newest raw batch 2026-06-19; newest compiled row 2026-06-24; max sale_date 2026-04-02.** Phase 0 restarts the cron and adds the tile. |
| GeoWarehouse | Watched-folder indicator: `engines/gw/watcher.py` exists and applies incremental updates (compiler bypass is intentional — CLAUDE.md). The tile shows files ingested vs pending in the watched folder and last-ingest timestamp. | 862 assessments / 773 ARNs — manual, on-demand channel; the tile makes its cadence visible. |
| POIs (OSM) | Monthly refresh — **later, not now.** No tile yet; note the import date statically. | 50,778 POIs, one-time import. |
| Portfolio URLs | Manual, standardized through the capture pipeline (`POST /api/portfolio/capture`). Freshness is per-group (`captured_at` on links/keys); no scheduler. | 21 portfolios scraped, 0 committed. |

## 7. D6 — Acceptance and testing rules

1. **UI acceptance.** A user-facing change is accepted by looking at the app,
   not by inspecting the DB. Every phase in Section 9 defines its acceptance
   criteria as things visible at `localhost:5174`. If acceptance requires a
   SQL query, the work isn't finished.
2. **/tmp rule.** All destructive or testing work runs on copies:
   `cp data/cleo.db /tmp/...` first. The existing test guard is the pattern —
   `scripts/test_portfolio_capture_m1.py`:
   `assert "cleo_test" in db or "/tmp/" in db, "refusing to run on a non-copy path"`.
   Every new test/scoreboard script MUST carry an equivalent guard.
3. **Env override for serving.** `CLEO_DB_PATH` (read in
   `cleo/database/connection.py:11`) points the API at a copy for demo/test
   serving. Use it; never point tests at `data/cleo.db`.
4. **dry_run defaults to true** on capture; merges only with
   `apply_merges=true` (verified in `cleo/web/routes/portfolio.py`).

## 8. Relationship to other documents

Dispositions: **superseded** (this doctrine overrules it where they touch),
**valid-within-scope** (still authoritative for its own subject),
**historical** (implemented or obsolete; context only).

### 8.1 Repo-root .docx plans

| Document | Disposition |
|---|---|
| `Cleo-Turbo-Buildout-Plan.docx` (Apr 2026) | Historical — counts stale, CRM phases largely built; its group model predates auto_groups. |
| `Phase-2.5-Group-Merging-Plan.docx` | **Superseded by D3/D4.** It assumes legacy GRP_ groups remain the primary entity and manual GRP→GRP merging is the consolidation mechanism ("Manual merges only… Brandon decides which groups are the same entity"). That role now belongs to auto_groups + verdicts. `group_merges` survives only as a frozen judgment overlay / redirect chain. |
| `Group_Analytics_Build_Plan.docx` | Superseded for user-facing use — analytics keyed to legacy groups; Stage A10 rolls them into `auto_group_analytics`, which is what the UI reads. Valid as internal-computation history. |
| `CRM-Matchmaking-Buildout-Plan.docx` | Valid-within-scope for the two-sided opportunity model (sell opps / buy mandates / deals); superseded wherever it treats legacy groups as the owner entity. |
| `data-integrity-audit.docx` (2026-04-02) | Historical — the gaps it found were fixed per `docs/data-pipeline-fix-plan.md` (status IMPLEMENTED). Its spirit survives as the CLAUDE.md "capture every field" rule. |
| `Shared_Address_Formatter_Plan.docx` | Valid-within-scope — display formatting, interpretation bucket. |
| `Portfolio-Capture-Cowork-Integration-Plan.docx` (locked, 2026-06-30) | Valid — the capture contract stands. **Amended by D3 in one respect:** it attaches ownership at GRP level; the migration direction (Section 4.3) moves attachment to auto_groups. |
| `Ontario_Municipal_GIS_Research.docx` | Valid-within-scope — research for scaling registry confirmation (GW coverage problem). |

### 8.2 docs/

| Document | Disposition |
|---|---|
| `product-map.md` (2026-07-06) | Companion — the audit this doctrine builds on. Current. |
| `portfolio-capture.md` | Valid — runbook for the capture endpoint; GRP-attachment note as above. |
| `architecture-deep-dive.md` (Jun 2026) | Valid-within-scope — verified architecture reference. |
| `definitions.md` (2026-03-26) | Valid-within-scope for terminology; predates auto_groups cutover — its Group definitions need an AGRP note. |
| `vocabulary.md` | Valid — and it supports D3: the user-facing word is "Group," never "auto_group." |
| `workflows.md` | Valid — north-star document. |
| `group-identity-system-plan.md` | Valid — D3's direct predecessor (unified Group backed by auto_groups). The doctrine extends it. |
| `phase-d-groups-cutover-plan.md` | Historical/implemented — Groups routes are cut over (`groups.py` docstring). Consistent with D3. |
| `group-consolidation-plan.md` | **Superseded by D3** — consolidation via legacy-group merging; that mechanism is frozen. |
| `unified-property-model-plan.md` | Valid-within-scope (planning) — must attach to auto_groups per D3 when built. |
| `contact-page-redesign-plan.md` | Valid-within-scope — already auto_groups-first. |
| `data-quality-page-plan.md` | Valid — D5's freshness tiles and Phase 1 join-health metrics extend this page. |
| `parcel-resolution-spec.md`, `ingestion-audit-and-parcel-anchor.md`, `stage1-implementation-checklist.md` | Valid-within-scope — parcel-anchor doctrine; evidence-bucket rationale. |
| `brand-parcel-accuracy.md` | Partially superseded by `parcel-resolution-spec.md` (it says so itself). |
| `parcel-resolution.md`, `resolve-parcels.md` (2026-03-26) | Historical — describe the pre-unified resolver; `cleo/resolver/` (CLAUDE.md) is current. |
| `brand-system-plan.md` | Valid-within-scope — interpretation-bucket work (fixes the Shoppers-as-Grocery class of defect). |
| `build-plan.md`, `frontend-plan.md` | Historical (CLAUDE.md already says so). |
| `data-pipeline-fix-plan.md` | Historical — implemented 2026-04-02. |
| `daily-scraper-plan.md`, `pipeline-orchestrator-plan.md`, `issue-tracker-plan.md` | Historical/implemented (daily_scraper.py, process.py, migration 036). |
| `early-dedup-plan.md`, `reprocess-plan.md`, `rt-automation-notes.md` | Valid-within-scope — RT evidence-layer mechanics. |
| `rt-pipeline-audit.md`, `rt-audit-*`, `rt-field-inventory.txt` | Historical audit artifacts. |
| `portfolio-capture-build-plan.md` | Valid — Milestones 2–3 (crawl endpoint, review UI) map onto Phases 2/4 below; GRP-attachment amended by D3. |
| `portfolio-capture-session-handoff.md` | Historical — session prompt. |
| `rt-pipeline-rewire-plan.docx`, `unified-parcel-resolution-plan.docx` | Historical — implemented by `engines/rt/process.py` and `cleo/resolver/` respectively. |
| `styling-reference.md` | Valid-within-scope — design system. |
| `atom-exploration/`, `superpowers/` | Historical exploration notes. |
| `previous-session-transcript.md` (repo root) | Historical. |

### 8.3 CLAUDE.md — lines needing update (do not treat as done until edited)

CLAUDE.md remains the working-rules document, but three passages now conflict
with verified reality and with this doctrine:

1. **"Derived tables" list** (Critical Rules → Database) omits `party_atoms`,
   `party_fingerprints`, `brand_registry` — all three ARE dropped by
   `drop_derived_tables()` (verified in `cleo/database/schema.py`).
2. **"CRM tables" list** omits `group_profile`, `group_aliases`,
   `group_match_keys`, `manual_owner_links`, `manual_properties`,
   `auto_group_user_edits`, `discovery_ground_truth`, `discovery_exclusions`,
   `user_stars` — all persistent judgment tables. A reader following the list
   as written could wrongly treat them as expendable. The discovery_v2-rebuilt
   interpretation tables (`auto_groups` etc.) appear in neither list and
   should be named as a third category.
3. **Stable IDs section**: "`GRP_NNNNN` — groups, keyed by normalized company
   name" is still true mechanically but needs the D3 rider: GRP_ is an SPV
   ledger id, not the user-facing owner entity; that is `AGRP_`.

## 9. Phased build order

Each phase is small, independently shippable, and accepted **in the UI** (D6).

**Phase 0 — RT restart + freshness tiles.**
Reinstall/verify the daily-scraper cron; backfill 2026-06-19 → today via
`--audit`; add RT + GW freshness tiles to the Data Quality page.
*Accept when:* Data Quality shows "RT: last batch <date>, last compile <date>"
with a red state at >48h, and the tile turns green after the backfill run; GW
tile shows ingested-vs-pending counts from the watched folder.

**Phase 1 — Join-health metrics on Data Quality.**
Tiles for the joins the product lives on: % properties dark, % owned properties
attached to confirmed/probable auto-groups (coverage metric, §5.3), gw_assessments↔properties
match count, POIs resolved to parcels, capture links by status
(active/conflict/pending).
*Accept when:* each tile shows the live number with a plain-English caption and
links to the underlying list; numbers reconcile with product-map §5 on day one.

**Phase 2 — Evidence-surfacing + verdict UI for auto-groups.**
Group Detail gains an Evidence panel: per member, the shared addresses, phones,
contacts, and SPV-name n-grams that caused the grouping; one-tap confirm/reject
writing `labeling_verdicts` (stable party-side keys).
*Accept when:* Brandon can open a probable group, see why each member is there,
tap confirm/reject, and see the verdict persist across a page reload and a
discovery rebuild.

**Phase 3 — Scoreboard harness.**
A script (with the /tmp guard) that runs candidate grouping code on a DB copy
and reports precision/recall/coverage vs shipped, plus regression count on
confirmed verdicts; results surfaced on a simple admin page per D6.
*Accept when:* two runs on the same code show identical numbers (determinism),
a deliberately broken config shows regressions > 0, and the shipped-vs-candidate
comparison renders in the app.

**Phase 4 — Capture→auto_groups attachment + legacy demotion in UI.**
Implement §4.3: capture targets AGRP; owner display resolves without the GRP
hop; kill remaining UI surfaces that present GRP_ rows as owners; capture
review UI (pending/conflict queues) lands here.
*Accept when:* committing a capture on a test copy shows the properties on the
auto-group's page immediately, conflicts appear in a review queue, and no page
in the app renders a GRP_ entity as a clickable owner.

**Phase 5 — Portfolio rollout of the 21 scraped groups.**
Convert the OneDrive raw scrapes to capture payloads; dry-run each; commit
through the Phase 4 flow, one group at a time, verifying counts against the
scrape.
*Accept when:* each committed group's page shows the expected property count,
the dark-property percentage on Data Quality visibly drops, and every conflict
raised is dispositioned in the review UI.

## 10. Amending this doctrine

The decisions table (Section 1) changes only by explicit sign-off from Brandon,
recorded here with a date. Everything else in this document is description and
must track the code — when the code legitimately moves (through the phases
above), update the description, never the other way around.
