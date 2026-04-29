# Layer 2 Plan H — Timeline-Aware Attribution

**Date:** 2026-04-29
**Builds on:** Plan A (foundation), Plan D (verification UI), Plan G (tuning), Plan F (trail). Replaces the timeless anchor model with one where every anchor-to-group attachment carries a date window. Adds unit-level address anchors with city in the key. Surfaces conflicts as discrete events.

**Trigger:** A real false positive surfaced during verification: `RT196095` (Toronto-Dominion Bank, c/o Enterprise Real Estate, 66 Wellington St W, 30th Flr) attached to KingSett because the address-root match alone (`66|wellington`) hit the expansion threshold. The static-anchor model can't distinguish floor 30 (TD's space) from suite 4400 (KingSett's space) within the same building. The deeper diagnosis: even with unit-level keys, the model still can't capture the time dimension — DH Management has occupied three different addresses over the past 15 years, and a static "DH = 180 Shorting" rule loses the 160 Shorting and 2555 Eglinton tenures along with everything that happened there.

---

## Goal

Make the Layer 2 attribution model timeline-aware. Every anchor-to-group attachment is a tenure with a start and end date. Cross-references between silos are verified against tenure consistency. Conflicts (a contact crossing two unrelated groups in overlapping windows, an anchor whose dominant stem changes mid-stream) are detected and flagged as discrete events for review, not absorbed silently into a confidence score.

Ship as three sub-plans (H1, H2, H3), each independently ships working software:

- **H1** — Unit-level anchors + city in address keys. Fixes the TD Bank false positive. Layer 1 UI shows the unit-by-unit breakdown at any address root.
- **H2** — Timelines and tenures. New schema for anchor tenures and contact tenures. Stage A0 (timeline builder), updated Stage A2 (windowed dominance), updated Stage A4 (time-aware attachment), new Stage A6 (conflict detection).
- **H3** — Time-aware UI. Each silo detail page gets a timeline view. Auto-group detail page shows anchor tenures (not static anchors). Trail view (Plan F update) becomes time-aware. Conflict panel surfaces flagged events.

H1 ships first as the immediate cleanup. H2 is the architectural change. H3 surfaces it.

---

## Glossary (locked — used strictly)

| Term | Meaning |
|---|---|
| **Party** | One side of one transaction. `(source_id, side)`. |
| **Anchor** | Phone, address_unit, or contact_fingerprint. The atomic linkage point between parties and groups. |
| **Address unit** | Full physical address: city + street_number + street_name + street_suffix + street_direction + suite_type + suite_number. The finest-grained physical location. |
| **Address root** | `(city, street_number, street_name)`. The discovery net. Used for browsing in Layer 1. **Never** sufficient for Layer 2 attachment. |
| **Address base** | `(city, street_number, street_name, street_suffix)`. A middle granularity. Layer 1 only. |
| **Group / auto_group** | An operator with a history. Identified by `auto_group_id`. |
| **Stem** | Canonical operator label (e.g., `dh`, `kingsett`). |
| **Timeline** | Chronological list of party events for a silo entry — an anchor or a contact or a stem. The story of that entry. |
| **Stable window** | A contiguous span on a timeline where the dominant stem doesn't change AND activity gaps don't exceed `MAX_TENURE_GAP_DAYS` (default 730 = 2 years). |
| **Tenure** | A stable window for a (anchor, group) pair or (contact, group) pair. Has start_date and end_date (end_date NULL = ongoing). |
| **Cross-reference** | When entity X's timeline contains entity Y, X confirms Y's tenure if their windows overlap and stems align. |
| **Default trust** | New evidence consistent with an established tenure adds to it. New evidence inconsistent with an established tenure becomes a conflict flag. |
| **Conflict flag** | A row in `auto_conflict_flags`. Surfaced for review, not auto-resolved. Types: `anchor_reassignment`, `contact_overlap`, `abrupt_tenure_end`. |
| **Orphan party** | A party with no anchors that match any group's tenure AND no brand-phrase stem hit. Stays unattached. Recorded as a singleton tied to its address until further evidence. |

---

## Core principles

1. **Every silo entry has a timeline.** Addresses, phones, contacts, stems all have stories. The algorithm computes those stories and reasons over them.
2. **Default trust.** Cross-references confirm by default. Negative evidence is rare and specific. When evidence aligns with an established tenure, it strengthens the tenure. When it contradicts, it's a flag.
3. **Conflicts are events, not scores.** Specific patterns trigger explicit flags surfaced for review. The algorithm doesn't try to auto-resolve ambiguity by lowering a confidence number.
4. **Tenure windows are first-class.** "DH was at 160 Shorting from 2014 to 2021" is the kind of fact the data model holds explicitly.
5. **Operator history is part of group identity.** A group's anchors are date-windowed. The algorithm's "DH Management" group encompasses the 2555 Eglinton era + the 160 Shorting era + the 180 Shorting era as a continuous operator history, not three separate static anchors.
6. **Address roots are for discovery, not attribution.** They remain useful for "show me everyone at 66 Wellington" browsing in Layer 1 but never anchor a Layer 2 attachment.

---

## Architecture overview

### What changes vs the current Plan A model

**Anchor schema:**
- Add new anchor type: `address_unit` (full address with city + suite + direction).
- City joins the existing `address_root` and `address_base` keys (Layer 1 silo improvement).
- Drop `address_root` and `address_base` from `auto_group_anchors` — they remain Layer 1 silos only.

**Algorithm stages:**
- New Stage A0: per-silo timeline builder.
- Existing Stage A2 (anchor uniqueness): becomes time-windowed dominance — produces tenure rows, not single dominance scores.
- Existing Stage A3 (seeding): consumes tenure data; a group's anchors are the union of stems' tenured anchors.
- Existing Stage A4 (expansion): time-aware. A party at date D attaches to anchor X's group only if X has a tenure spanning D.
- Existing Stage A5 (display): unchanged.
- New Stage A6: conflict detection.

**Database additions:**
- `auto_group_anchor_tenures` (replaces the timeless `auto_group_anchors`).
- `auto_contact_tenures` (the structure Plan B was going to add, brought forward).
- `auto_conflict_flags`.

**UI additions:**
- Each Layer 1 silo detail page (phone, address_unit, contact) gets a timeline section.
- Auto-group detail tabs change from "Anchors" to "Anchor Tenures" — date-bracketed.
- Trail view (Plan F) becomes time-aware.
- New "Conflicts" tab on the Auto-Groups list page.

### What stays the same

- The Layer 1 silos (`brand_token_summary`, `phone_summary`, `address_root_summary`, etc.) keep their existing structure plus city additions.
- The CRM tables (`auto_group_overrides`, `auto_group_merges`, `auto_anchor_overrides`) survive unchanged.
- Plan A's stem extraction logic (verified-promotion via dominance) is unchanged.
- Plan G's tuning page works on the new model with cosmetic updates only.

---

## Plan H1 — Unit-level anchors + city + Layer 1 UI breakdown

**Goal:** Fix the multi-tenant building false positives (TD Bank case) and surface unit-by-unit breakdowns in the Address silo UI. Cross-city collisions go away. Layer 2 still uses static anchors (no tenures yet) but with the right granularity.

### Schema changes (Migration 016)

```sql
-- Update CHECK constraint on anchor_uniqueness.anchor_type to include address_unit
-- (SQLite requires recreating the table; alternative is to drop the CHECK and rely on app validation)

CREATE TABLE address_unit_summary (
    city                   TEXT NOT NULL,
    street_number          TEXT NOT NULL,
    street_name            TEXT NOT NULL,
    street_suffix          TEXT,
    street_direction       TEXT,
    suite_type             TEXT,
    suite_number           TEXT,
    n_party_sides          INTEGER NOT NULL,
    n_distinct_brand_stems INTEGER NOT NULL,
    dominant_stem          TEXT,
    dominance_share        REAL,
    discovered_at          TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (city, street_number, street_name, street_suffix, street_direction, suite_type, suite_number)
);
CREATE INDEX idx_aus_root ON address_unit_summary(city, street_number, street_name);
CREATE INDEX idx_aus_dominant ON address_unit_summary(dominant_stem);
```

`address_root_summary` and `address_base_summary` get a `city` column added (data backfilled from party_fingerprints).

### Algorithm changes

- New `build_address_unit_summary(conn)` in `cleo/discovery_v2/brand_index.py`.
- `cleo/discovery_v2/anchor_scores.py` adds `address_unit` to `_ANCHOR_QUERIES`. The dominance-share + log-volume formula is unchanged.
- Stage A3 seeding: the `anchor_category` collapse logic stays the same — `address_unit` collapses into the `address` category. Address_root and address_base are no longer seeding inputs.
- Stage A4 expansion: replace the existing `address_root` / `address_base` matching with `address_unit` matching. New match-score rules:
  - Direct stem hit → 1.0 (unchanged)
  - `address_unit` match where unit is uniquely tenanted → 0.7
  - `address_unit` match + contact match → 0.85
  - Phone match (no contradiction) → 0.7 (unchanged)
  - Phone + brand contradiction → -0.5 (unchanged)
  - **No-anchor party + direct stem hit on group's stem** → 1.0 (still attaches; "they forgot the suite")
  - **No-anchor party + no stem + phone match** → 0.7 (still attaches via phone)
  - **No-anchor party at a known address root with no stem hit and no other anchors** → 0.0 (don't attach — fixes the TD Bank case)

### Layer 1 UI

The `/explorer/addresses/roots/<num>|<name>` detail page already exists. Add a new section: "Units at this root."

```
Units at 66 Wellington (toronto)
  ┌──────────────────┬────────────┬─────────────┬──────────────┐
  │ Unit             │ # Parties  │ Dom. Stem   │ Dom. Share   │
  ├──────────────────┼────────────┼─────────────┼──────────────┤
  │ suite 4400 west  │ 156        │ kingsett    │ 88%          │
  │ suite 4100 west  │ 11         │ weirfoulds  │ 82%          │
  │ floor 30 west    │ 3          │ —           │ 0%           │
  │ (no unit)        │ 99         │ kingsett    │ 47%          │
  └──────────────────┴────────────┴─────────────┴──────────────┘
```

Click a unit row → navigates to the unit detail (new page at `/explorer/addresses/units/<encoded-unit-key>`).

### Backend endpoints

- `GET /api/explorer/addresses/roots/{key}/units` — units within a root with brand-stem dominance.
- `GET /api/explorer/addresses/units/{key}` — detail view of a single unit (parties, dominant stem, brand phrases).

### Migration strategy for H1

- Plan A's auto_groups gets rebuilt. The `dh` group goes from "address_root: 180 Shorting" + "address_root: 160 Shorting" + "address_base: 2555 Eglinton" anchors to specific unit anchors (address_unit: ...|180|shorting|road|||, ...|160|shorting|road|||, ...|2555|eglinton|avenue||suite|212).
- Existing CRM overrides survive but their anchor references may need migration if they targeted address_root or address_base. (Spot-check: there are likely few or zero such overrides; this is fresh territory.)

---

## Plan H2 — Timelines and tenures

**Goal:** Replace the static anchor model with a time-windowed one. Every anchor-to-group attachment carries dates. Contact tenures inferred from the data. Conflicts surfaced as discrete events.

### Schema changes (Migration 017)

```sql
-- Replace auto_group_anchors with auto_group_anchor_tenures.
-- Old auto_group_anchors gets dropped (it's a derived table; rebuilt by Layer 2 anyway).

CREATE TABLE auto_group_anchor_tenures (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    auto_group_id               TEXT NOT NULL,
    anchor_type                 TEXT NOT NULL CHECK (anchor_type IN ('phone','address_unit','contact')),
    anchor_value                TEXT NOT NULL,
    start_date                  TEXT NOT NULL,
    end_date                    TEXT,                            -- NULL = ongoing
    n_party_sides_in_window     INTEGER NOT NULL,
    dominance_share_in_window   REAL NOT NULL,
    score                       REAL NOT NULL,                   -- old anchor uniqueness score, computed within the window
    discovered_at               TEXT DEFAULT (datetime('now'))
);
CREATE INDEX idx_agat_group ON auto_group_anchor_tenures(auto_group_id);
CREATE INDEX idx_agat_anchor ON auto_group_anchor_tenures(anchor_type, anchor_value);

CREATE TABLE auto_contact_tenures (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_fingerprint      TEXT NOT NULL,
    auto_group_id            TEXT NOT NULL,
    start_date               TEXT NOT NULL,
    end_date                 TEXT,                                 -- NULL = ongoing
    n_party_sides_in_window  INTEGER NOT NULL,
    discovered_at            TEXT DEFAULT (datetime('now'))
);
CREATE INDEX idx_act_contact ON auto_contact_tenures(contact_fingerprint);
CREATE INDEX idx_act_group ON auto_contact_tenures(auto_group_id);

CREATE TABLE auto_conflict_flags (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conflict_type   TEXT NOT NULL CHECK (conflict_type IN ('anchor_reassignment','contact_overlap','abrupt_tenure_end','transient_tenure')),
    entity_type     TEXT NOT NULL CHECK (entity_type IN ('anchor','contact')),
    entity_value    TEXT NOT NULL,                                 -- anchor_value or contact_fingerprint
    entity_subtype  TEXT,                                          -- anchor_type, when entity_type='anchor'
    group_a         TEXT,                                          -- nullable
    group_b         TEXT,                                          -- nullable
    date_observed   TEXT,                                          -- key date defining the conflict
    description     TEXT NOT NULL,
    discovered_at   TEXT DEFAULT (datetime('now'))
);
CREATE INDEX idx_acf_type ON auto_conflict_flags(conflict_type);
CREATE INDEX idx_acf_entity ON auto_conflict_flags(entity_type, entity_value);
```

### Algorithm changes

#### Stage A0 — Per-silo timeline builder (new)

For each anchor (phone, address_unit, contact_fingerprint), build a chronological list of party events:

```python
def build_anchor_timeline(conn, anchor_type, anchor_value):
    """Return [(sale_date, source_id, side, dominant_stem, brand_phrase), ...] sorted by sale_date."""
```

Same for contacts. Returns the timeline as an in-memory list. Used by Stages A2 and A6. Not stored — computed on-demand and cached per-run.

#### Stage A2 — Windowed dominance (replaces existing)

For each anchor with timeline T:
1. Walk events in date order.
2. Maintain a "current run" identified by its dominant stem (computed over the events in the run).
3. Start a new run when:
   - The dominant stem of the cumulative run drops below `STEM_PROMOTION_DOMINANCE` (0.6) for more than `RUN_GRACE_EVENTS` consecutive events (rule of thumb: 2-3 events of a different stem don't end a run; 5+ does).
   - The gap between consecutive events exceeds `MAX_TENURE_GAP_DAYS` (730 = 2 years).
4. For each completed run, emit a tenure: `(anchor, dominant_stem, start_date, end_date, n_party_sides, dominance_share, score)`.

The output replaces `anchor_uniqueness` for tenure-bearing anchors. (We may keep `anchor_uniqueness` as a "current state" snapshot — the most recent tenure per anchor — for simpler queries; but the source of truth is the tenure table.)

#### Stage A3 — Seeding (updated)

For each verified stem `s`:
- Pull all anchor tenures where `dominant_stem_in_window = s`.
- Group them under one auto_group keyed by `s`.
- Convert tenures to `auto_group_anchor_tenures` rows.

The seeding rules (3 categories converged → confirmed, etc.) apply to anchors that have at least one open or recent tenure (within last `RECENT_TENURE_DAYS` = 1095 = 3 years). A group with all tenures ended >3 years ago is "dormant" — promoted differently or marked as historical.

#### Stage A4 — Time-aware expansion (replaces existing)

For each party (source_id, side, sale_date):
1. Look up its anchors (phone, address_unit, contact).
2. For each anchor, find any tenure that contains `sale_date` (i.e., `start_date <= sale_date <= COALESCE(end_date, '9999-12-31')`).
3. If exactly one tenured group surfaces across all anchors → attach the party to that group at the match-score from H1's rules.
4. If multiple groups surface → CONFLICT signal — this is a real conflict, not just shared anchor IDs. Either:
   - The party is at a JV between two groups, OR
   - One of the tenures is wrong, OR
   - The contact is a service provider.
   Don't attach; emit a `auto_conflict_flags` row of type `contact_overlap` (if the conflict is between contact tenures) or `anchor_reassignment` (between anchor tenures).
5. If no tenured group surfaces → orphan. Don't attach. Future signals can pull it in.

#### Stage A6 — Conflict detection (new)

After A2 produces tenures, scan for:

**Anchor reassignment**: Same anchor with two non-overlapping tenures on different stems.
> "Phone 416-555-1234 was DH's switchboard from 2010-2015, then BigBank's switchboard from 2016+."
Emits `auto_conflict_flags` with `conflict_type='anchor_reassignment'`, `entity_type='anchor'`, `entity_value=phone-value`, `group_a=DH`, `group_b=BigBank`, `date_observed=2015-12-31` (the end of the first tenure).

**Contact overlap**: Same contact_fingerprint with overlapping tenures on two unrelated groups.
> "Jane Smith was DH's contact 2015-2020 AND was unrelated_corp's contact 2018-2022."
Emits `auto_conflict_flags` with `conflict_type='contact_overlap'`, `entity_type='contact'`. Either Jane is a service provider (LLC formation agent), or she moved jobs, or it's a name collision.

**Abrupt tenure end**: An anchor that was active continuously, then abruptly disappears. Often signals an operator wind-down or data gap.
> "Phone X had 200 parties from 2015-2022, then 0 parties from 2022-present."

**Transient tenure**: A tenure shorter than `MIN_PERMANENT_TENURE_DAYS` (default 365 = 1 year) at low volume. Signals one-offs (the 4950 Yonge case).

These flags don't change the data — they just surface for human review.

### Tunable knobs (added to constants module)

```python
MAX_TENURE_GAP_DAYS = 730             # 2 years; gap larger than this splits a tenure
RECENT_TENURE_DAYS = 1095              # 3 years; tenure ended later than this is "active"
MIN_PERMANENT_TENURE_DAYS = 365        # 1 year; shorter is transient
MIN_TENURE_PARTY_COUNT = 3             # at least 3 parties to count as a real tenure
RUN_GRACE_EVENTS = 3                   # how many off-stem events to tolerate before splitting a run
```

---

## Plan H3 — Time-aware UI

### Layer 1 silo timelines

Each silo's detail page (`/explorer/phones/<value>`, `/explorer/addresses/units/<key>`, `/explorer/contacts/<value>`) gets a "Timeline" section.

Visual: chronological table of party events with co-occurring anchors highlighted. Plus a horizontal tenure bar showing dominant-stem windows over time.

```
Timeline of phone 4162655055
   Tenure: dh from 2010 to present
   ────────────────────────────────────
   2025-03-15 | RT123 | seller | dh management         | dan hagler | 180 shorting
   2024-11-22 | RT456 | seller | midland industrial    | dan hagler | 180 shorting
   ...
   2010-04-01 | RT001 | seller | dh property mgmt     | dan hagler | 2555 eglinton
```

Click any party row → opens the SourceViewerDrawer (existing behavior).

### Auto-group detail page — Anchor Tenures tab

Replaces the existing Anchors tab. Each row = one tenure, not one static anchor.

| Anchor | Tenure | Score | n parties | Coverage of group |
|---|---|---|---|---|
| address_unit toronto\|180\|shorting\|road\|\|\| | 2018 → present | 4.5 | 12 | 35% |
| address_unit toronto\|160\|shorting\|road\|\|\| | 2014 → 2021 | 3.8 | 8 | 24% |
| address_unit scarborough\|2555\|eglinton\|avenue\|\|suite\|212 | 2009 → 2015 | 2.9 | 6 | 18% |
| phone 4162655055 | 2010 → present | 6.2 | 22 | 65% |
| contact dan hagler | 2009 → present | 4.1 | 28 | 82% |

Sortable by tenure dates, score, party count. Click a row → drills into that anchor's Layer 1 detail page.

### Trail view (Plan F update)

For a party at sale_date D, each thread now shows:
- Anchor → which group's tenure spans D (if any) → group node.
- If the anchor has a tenure spanning D, edge is solid jade.
- If the anchor has tenures but none spans D, edge is dashed amber with a "tenure-mismatch" label showing the actual tenure dates.
- If the anchor has no tenures at all (orphan anchor), edge is dashed gray to "(unattached)".

So a party from 2012 at "2555 Eglinton suite 212" with phone "4162655055" reads: phone thread → DH (jade, tenure 2010-present spans 2012); address thread → DH (jade, tenure 2009-2015 spans 2012); contact thread → DH (jade). All confirmations align.

A party from 2025 at "2555 Eglinton suite 212" reads: phone thread → DH (still jade, tenure ongoing); address thread → DH but DASHED AMBER ("2555 Eglinton suite 212 was DH's tenure 2009-2015; data after that suggests DH moved out"). The trail view tells the story.

### New "Conflicts" tab on the Auto-Groups list page

Surfaces unresolved entries from `auto_conflict_flags`. Filterable by conflict_type. Clicking a row shows the affected anchor/contact and the timelines side-by-side for review. User can dismiss (mark as accepted: "yes, this is a JV") or escalate to merge/split (which would live in Plan C).

---

## Decomposition into implementation plans

Each sub-plan is its own implementation plan when it's ready to be built. Each ships independently working software.

| Sub-plan | Scope | Estimated tasks |
|---|---|---|
| **Plan H1** | Migration 016 (address_unit_summary, city columns), Stage A2 update for unit-level, Stage A4 update with new match scores, Layer 1 UI breakdowns | ~10 |
| **Plan H2** | Migration 017 (tenure tables, conflict flags), Stage A0 timeline builder, Stage A2 windowed dominance, Stage A4 time-aware expansion, Stage A6 conflict detection, constants additions | ~15 |
| **Plan H3** | Layer 1 timeline UI, auto-group Anchor Tenures tab, Plan F trail-view time-awareness, Conflicts tab | ~10 |

H1 ships first (immediate cleanup of the TD Bank case). H2 introduces tenures (the architectural change). H3 surfaces them visually.

---

## Database considerations

### Indexes
- `auto_group_anchor_tenures`: on (auto_group_id), on (anchor_type, anchor_value).
- `auto_contact_tenures`: on (contact_fingerprint), on (auto_group_id).
- For tenure-overlap queries (Stage A4 time-aware lookup), the composite index on (anchor_type, anchor_value) + filtering on (start_date, end_date) is sufficient at our scale (≤30 tenures per anchor typically).

### Performance
- Plan A's full Layer 2 build currently runs in ~30 seconds.
- Stage A0 (timeline builder) is one ORDER BY query per anchor — bounded by the number of distinct anchors (~250k including orphans). Can run in chunks.
- Stage A2 (windowed dominance) iterates the timeline events for each anchor, O(N events). Total work: O(total parties + total events) ≈ O(500k) — fast.
- Stage A6 (conflict detection) is O(tenures) — small.
- Expected new total time: 1-3 minutes. Acceptable for a builder run.

### Migration safety
- All Layer 2 derived tables get rebuilt by the builder anyway (Plan A established this pattern). No data loss.
- CRM tables (`auto_group_overrides`, `auto_group_merges`, `auto_anchor_overrides`) survive untouched. CRM rows that referenced specific anchors may need migration — but `auto_anchor_overrides` is keyed on `(anchor_type, anchor_value)` and the new `address_unit` anchor type is additive. The address_root and address_base override rows become inert (the algorithm no longer reads them) but don't break.

---

## Testing approach

### Unit tests
- Stage A0: synthetic timelines with known stem patterns; verify timeline ordering and stable-window detection.
- Stage A2: contrived timelines with stem changes; verify tenure boundaries computed correctly.
- Stage A4: parties at specific dates against synthetic tenure data; verify only the right group attaches.
- Stage A6: each conflict type with synthetic triggering data; verify flag emission.

### Integration tests
- Build the full pipeline against synthetic DH-shaped data (three address tenures, multiple phones, multiple contacts) → verify the resulting tenure structure matches the expected timeline.
- Build against the synthetic AGRP_00004 conflict case from Plan F's fixture → verify conflict flag emitted.

### Real-DB verification (per sub-plan)
- H1: TD Bank case (RT196095) does NOT attach to KingSett. The 90 false-positive parties at 66 Wellington with no other anchors stay unattached.
- H2: DH Management (AGRP_00738) shows three distinct address_unit tenures spanning 2009-present. Real conflicts surface (count > 0).
- H3: Trail view for a party from 2012 correctly shows the tenure-overlapping anchors highlighted vs the non-overlapping ones dashed.

---

## Out of scope (explicitly deferred)

- **Contact name aliasing.** `nina wine` and `nina hagler wine` remain separate fingerprints. The Plan B follow-up handles aliasing.
- **Brand-phrase aliasing.** `dh management` and `dh property management` already work via the `dh` stem. No further action.
- **Cross-source merging.** RT + GW + OSM merging is a Layer 3 concern.
- **Address-to-ARN resolution.** Layer 3.
- **User actions on conflicts** (confirm "this is a JV", merge two groups, etc.). Plan C territory.
- **Modifying the existing app pages** (Properties, Contacts, Transactions). Strict isolation continues.
- **Auto-resolving conflicts.** Conflicts surface for human review only. The algorithm emits flags; it doesn't merge or split groups based on conflict detection.

---

## Success criteria

After all three sub-plans ship:

1. **TD Bank false positive eliminated.** RT196095 (seller, TD Bank at 66 Wellington floor 30) does NOT attach to KingSett. The Trail view for this party shows: address thread → no kingsett tenure at floor 30 → unattached.

2. **DH Management's office moves are visible.** AGRP_00738's Anchor Tenures tab shows the three sequential address_unit tenures: Scarborough/2555 Eglinton suite 212 (2009-2015), Toronto/160 Shorting Rd (2014-2021), Toronto/180 Shorting Rd (2018-present). Click any of them → drills into the unit's timeline.

3. **The 4950 Yonge one-off is correctly classified.** A `transient_tenure` flag is emitted because it has only 1 party event, well below `MIN_TENURE_PARTY_COUNT`. The party still attaches to DH via the `dan hagler` contact tenure (which spans 2014).

4. **Cross-city collisions eliminated.** Any "52 main st" anchors split into per-city instances (e.g., `st thomas|52|main|street|||` is distinct from `hamilton|52|main|street|||`).

5. **Conflict detection produces non-zero flags on real data.** Likely candidates: shared service-provider phones across multiple unrelated groups, contacts at law firms (Bratty, Cassels, etc.) crossing client boundaries.

6. **Performance.** Full Layer 2 rebuild completes in < 5 minutes.

7. **Algorithmic behavior the user described:** A new contact appearing at an established DH-tenured anchor automatically attaches as a DH person. The algorithm doesn't second-guess the established tenure — it grows the contact roster. Conflicts only emerge when the new evidence's own timeline contradicts an existing tenure (different group with overlapping window).

---

## Migration sequence

1. **Plan H1 ships.** Migration 016 adds `address_unit_summary` and city columns. Layer 2 builder runs once with the new anchor type. Existing auto_groups rebuild with cleaner address-unit anchors. CRM overrides keyed on old types continue working but become inert for routing.

2. **Plan H2 ships.** Migration 017 adds tenure tables and conflict flags. Layer 2 builder runs with timeline reasoning. Existing static `auto_group_anchors` table is dropped (or kept as a denormalized "current state" view of `auto_group_anchor_tenures`).

3. **Plan H3 ships.** UI updates only. No schema changes.

4. **Plan B (deferred)** later picks up contact name aliasing and tenure-aware merging across name variants. The tenure infrastructure built in H2 is what B operates on.

---

## What this gives you

The mental model the algorithm encodes is the one you described:
- Silos are facts. Their timelines are the stories.
- Cross-references confirm by default. New evidence consistent with a tenure adds to it.
- Operators have histories. DH moved offices three times; that's a feature, not noise.
- Conflicts are explicit events surfaced for review, not silent confidence drops.
- The algorithm does the boring work of building tenures from raw event data. You do the interesting work of resolving the conflicts that surface.

This becomes the foundation for Plan B's tenure-aware contact aliasing and Plan C's user-action workflows. Both will operate on the tenure model H2 establishes — they'll feel like extensions, not rewrites.
