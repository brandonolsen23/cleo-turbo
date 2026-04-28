# Layer 2 — Auto-Seeded Group Discovery

**Date:** 2026-04-27
**Builds on:** Layer 1 silos (`brand_token_summary`, `brand_*gram_summary`, `phone_summary`, `address_root_summary`, `address_base_summary`, `contact_fingerprint_summary`, `party_atoms`, `party_fingerprints`).

## Goal

Build operator-portfolio groups automatically from Layer 1 silo evidence, with per-contact tenure timelines, confidence tiering, and compound user confirmations. The system runs sandboxed from the existing app — its outputs go to new tables, surface in a new UI tab, and never touch the existing `groups`, `contacts`, `properties`, `transactions` tables until the user confirms it's better than what the app currently does.

The point of grouping is to surface "concrete" operators — like Skyline — by triangulating across silos. If a Skyline phone, a Skyline HQ address, and Daniel Drimmer's contact all converge on transactions that share the `skyline` stem, the system creates a Skyline group and attaches every other transaction with that phone (even ones where "skyline" doesn't appear in the brand_phrase) to the same group.

## Architecture

Layer 2 is built in three sub-projects, each independently shippable and end-to-end working:

- **Plan A — Foundation.** Stem extraction (verified-promotion). Anchor uniqueness scoring. Auto-seed from anchor convergence. Group expansion. Confidence tiering. Read-only UI for group list + drill-in.
- **Plan B — Tenure & Anti-evidence.** Per-contact closed-span tenures. Internal-transfer detection. Service-provider tagging. Cross-side conflict detection.
- **Plan C — Cascade & user actions.** Exclusive-vocabulary auto-discovery. Confirm/reject/merge/split actions. Cascade re-evaluation triggered by each user action. Override persistence.

Plan A is the foundation everything else depends on. Plans B and C iterate on it. Each plan ships its own implementation plan and is reviewed independently after shipping.

## Sandboxing

All algorithmic outputs go to new tables prefixed `auto_*`. A new builder (`cleo/discovery_v2/auto_groups.py` or equivalent) populates them — independent of the compiler's existing `drop_derived_tables()` flow. The existing `groups`, `group_names`, `contacts`, `properties`, `transactions`, and `transaction_parties` tables are not touched. The Properties/Contacts/Transactions pages in the app continue using the existing data.

Layer 2 surfaces in its own UI tab inside the Explorer (or a dedicated top-level "Groups (Auto)" tab — TBD during implementation). When the user is ready to integrate Layer 2 into the main app, that's a separate decision and a separate piece of work — not part of this design.

## Concepts

### Stems

A **stem** is the canonical operator label that links many brand_phrases to one operator. Examples: `skyline` (linking `skyline real estate holdings`, `skyline retail real estate holdings`, `skyline apartment reit`); `kingsett` (linking `kingsett capital`, `ks gta industrial no 1`, `aero park iii`); `dd` (linking `dd 64 roehampton`, `dd 150 elm ridge` — Daniel Drimmer's Starlight SPVs).

A stem is a 1-gram from the existing `brand_token_summary` table. It can be either:
- A **distinctive 1-gram** (`is_distinctive = 1`), e.g., `skyline`, `kingsett`, `metrus`
- A **position-anchor 1-gram** (`is_position_anchor = 1`), e.g., `dd`, `ks`, `tg`

Stems are **verified before they're trusted**. A candidate stem is promoted to verified only when ≥60% of phrases sharing that candidate co-occur with a single dominant anchor (phone or HQ-address) and that anchor has volume ≥ 5. Until verified, no phrases are mapped to that stem and it contributes nothing to grouping.

This is "Option C" from the design discussion — auto-discovered patterns must prove themselves before they can anchor a group.

### Anchors

An **anchor** is one of: a phone, an address root (`number+name`), an address base (`number+name+suffix`), or a contact_fingerprint. Each anchor gets a uniqueness score:

```
score = dominance_share × log(volume + 1)

where:
  volume          = number of party-sides at this anchor
  dominant_stem   = the stem that the most party-sides at this anchor share
  dominance_share = (party-sides whose phrases map to dominant_stem) / volume
```

A score near 1 × log(big_number) means the anchor is dominated by one operator with significant evidence — a strong group anchor. A score near 0 means the anchor is mixed-tenant (a multi-tenant office building, a shared switchboard, a common-name contact) and shouldn't anchor a group.

### Groups

An **auto_group** is one operator. Identity: `(auto_group_id, canonical_stem, display_name, tier, confidence)`. Members are party-sides and numbered-corp entities. Anchors that established the group are tracked in `auto_group_anchors`.

Groups are tiered. Tiering counts **anchor categories** (`phone`, `address`, `contact`) — `address_root` and `address_base` collapse into the single `address` category to avoid double-counting:
- **Confirmed**: 3 categories converge on the same stem (phone + address + contact)
- **Probable**: 2 categories converge
- **Candidate**: 1 strong category + at least one corroborating anchor (any category, score ≥ 0.5)

The display name is the most-frequent brand_phrase among the group's members that maps to the group's canonical stem.

### Tenure (Plan B)

For each contact_fingerprint, walk their party-sides chronologically. Stable runs where the strongest anchor (phone or HQ-address) maps to a single group become a closed span: `(contact_fingerprint, auto_group_id, start_date, end_date)`. End_date NULL = current. Discontinuities reveal job changes.

Marco Muzzo at Erin Mills 1996–2010, Crownvetch 2010–present (hypothetical example): a 2005 transaction with marco muzzo + Erin Mills phone → linked to Erin Mills tenure. A 2020 transaction with the same name + a Crownvetch phone → linked to Crownvetch tenure. Without tenure modeling, the algorithm would either merge them into one Frankenstein group or refuse to link them at all.

Multi-group simultaneous tenures are disallowed by default. The rare overlap case (a JV principal at two operators concurrently) is flagged in `auto_contact_tenures.overlap_flag` for human review rather than auto-resolved.

### Anti-evidence (Plan B)

When evidence pulls in different directions, the algorithm refuses to merge or demotes the anchor:

- **Same anchor on both sides of a transaction, same stem on both sides** → strong evidence of an internal transfer. Reinforces grouping (both SPV names collapse into the group).
- **Same anchor on both sides, different stems** → likely a law firm or escrow agent attribution. Demote that anchor's score.
- **Phrase says X but anchors are dominated by Y** → flag the side for review; don't auto-attach.
- **Same name appears at many unrelated phones/addresses** (e.g., "michael smith" at 10 unrelated operators) → tag the contact as a `service_provider`. Service providers never anchor groups.

### Cascade (Plan C)

When the user confirms a Probable group:
1. Lock that group's anchors as user-confirmed in `auto_group_overrides`.
2. Identify every other auto_group whose anchors overlap with the confirmed one.
3. For each affected group, recompute:
   - **Auto-merge** if its anchors are now dominated by the confirmed group's stem
   - **Promote Probable → Confirmed** if new evidence pushes its score past threshold
   - **Demote Probable → Candidate** if confirmation revealed a contradiction
4. Surface a "since you confirmed Skyline, here's what changed" summary; every cascade is reviewable and undoable.

The cascade is computationally cheap because only the affected anchor-overlapping subset is recomputed.

## Database schema

### Derived tables (rebuilt every Layer 2 run)

```sql
CREATE TABLE brand_stem (
    stem                 TEXT PRIMARY KEY,
    stem_type            TEXT NOT NULL CHECK (stem_type IN ('distinctive', 'position_anchor')),
    dominant_anchor_type TEXT NOT NULL,    -- 'phone' | 'address_root'
    dominant_anchor_value TEXT NOT NULL,
    dominance_share      REAL NOT NULL,
    volume               INTEGER NOT NULL,
    verified_at          TEXT DEFAULT (datetime('now'))
);

CREATE TABLE brand_stem_phrase_map (
    phrase     TEXT PRIMARY KEY,
    stem       TEXT NOT NULL,
    confidence REAL NOT NULL,
    FOREIGN KEY (stem) REFERENCES brand_stem(stem)
);

CREATE TABLE anchor_uniqueness (
    anchor_type      TEXT NOT NULL CHECK (anchor_type IN ('phone', 'address_root', 'address_base', 'contact')),
    anchor_value     TEXT NOT NULL,
    dominant_stem    TEXT,
    dominance_share  REAL,
    volume           INTEGER NOT NULL,
    score            REAL NOT NULL,
    is_service_provider INTEGER NOT NULL DEFAULT 0,  -- Plan B
    PRIMARY KEY (anchor_type, anchor_value)
);
CREATE INDEX idx_au_score ON anchor_uniqueness(score);
CREATE INDEX idx_au_stem  ON anchor_uniqueness(dominant_stem);

CREATE TABLE auto_groups (
    auto_group_id    TEXT PRIMARY KEY,         -- 'AGRP_NNNNN'
    canonical_stem   TEXT NOT NULL,
    display_name     TEXT NOT NULL,
    tier             TEXT NOT NULL CHECK (tier IN ('confirmed', 'probable', 'candidate')),
    confidence       REAL NOT NULL,
    n_anchors        INTEGER NOT NULL,
    n_members        INTEGER NOT NULL,
    discovered_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE auto_group_anchors (
    auto_group_id  TEXT NOT NULL,
    anchor_type    TEXT NOT NULL,
    anchor_value   TEXT NOT NULL,
    score          REAL NOT NULL,
    PRIMARY KEY (auto_group_id, anchor_type, anchor_value),
    FOREIGN KEY (auto_group_id) REFERENCES auto_groups(auto_group_id)
);

CREATE TABLE auto_group_members (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    auto_group_id  TEXT NOT NULL,
    member_type    TEXT NOT NULL CHECK (member_type IN ('party_side', 'numbered_corp')),
    source_id      TEXT,                              -- party_side: transaction source_id; numbered_corp: NULL
    side           TEXT,                              -- party_side: 'buyer' | 'seller'; numbered_corp: NULL
    corp_name      TEXT,                              -- numbered_corp: '151516 canada' etc.; party_side: NULL
    match_score    REAL NOT NULL,
    FOREIGN KEY (auto_group_id) REFERENCES auto_groups(auto_group_id)
);
CREATE UNIQUE INDEX idx_agm_party ON auto_group_members(auto_group_id, source_id, side)
    WHERE member_type = 'party_side';
CREATE UNIQUE INDEX idx_agm_corp ON auto_group_members(auto_group_id, corp_name)
    WHERE member_type = 'numbered_corp';

CREATE TABLE auto_contact_tenures (         -- Plan B
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_fingerprint TEXT NOT NULL,
    auto_group_id       TEXT NOT NULL,
    start_date          TEXT NOT NULL,
    end_date            TEXT,                       -- NULL = current
    n_party_sides       INTEGER NOT NULL,
    overlap_flag        INTEGER NOT NULL DEFAULT 0, -- 1 = co-occurs with another tenure window
    FOREIGN KEY (auto_group_id) REFERENCES auto_groups(auto_group_id)
);
CREATE INDEX idx_act_contact ON auto_contact_tenures(contact_fingerprint);
CREATE INDEX idx_act_group   ON auto_contact_tenures(auto_group_id);

CREATE TABLE auto_group_exclusive_vocab (   -- Plan C
    auto_group_id  TEXT NOT NULL,
    phrase         TEXT NOT NULL,
    n_appearances  INTEGER NOT NULL,
    PRIMARY KEY (auto_group_id, phrase),
    FOREIGN KEY (auto_group_id) REFERENCES auto_groups(auto_group_id)
);

CREATE TABLE auto_service_providers (       -- Plan B
    anchor_type   TEXT NOT NULL,
    anchor_value  TEXT NOT NULL,
    reason        TEXT NOT NULL,                    -- 'high_distinct_stems', 'cross_side_attribution', etc.
    score         REAL NOT NULL,
    PRIMARY KEY (anchor_type, anchor_value)
);
```

### CRM tables (persistent, never dropped, survive Layer 2 runs)

```sql
CREATE TABLE auto_group_overrides (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    auto_group_id   TEXT NOT NULL,
    action          TEXT NOT NULL CHECK (action IN ('confirm', 'reject', 'split')),
    user_id         TEXT NOT NULL,
    action_at       TEXT NOT NULL DEFAULT (datetime('now')),
    notes           TEXT
);
CREATE INDEX idx_ago_group ON auto_group_overrides(auto_group_id);

CREATE TABLE auto_group_merges (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_auto_group_id  TEXT NOT NULL,
    child_auto_group_id   TEXT NOT NULL,
    user_id               TEXT NOT NULL,
    action_at             TEXT NOT NULL DEFAULT (datetime('now')),
    notes                 TEXT
);
CREATE INDEX idx_agm_parent ON auto_group_merges(parent_auto_group_id);

CREATE TABLE auto_anchor_overrides (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    anchor_type              TEXT NOT NULL,
    anchor_value             TEXT NOT NULL,
    override_stem            TEXT,                          -- NULL = no stem override
    override_service_provider INTEGER NOT NULL DEFAULT 0,    -- 1 = force service provider
    user_id                  TEXT NOT NULL,
    action_at                TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_aao_anchor ON auto_anchor_overrides(anchor_type, anchor_value);
```

CRM tables are never touched by the Layer 2 builder. They drive the cascade: when the algorithm regenerates auto_groups, it reads the CRM tables and respects user actions (confirmed groups stay confirmed, rejected groups don't reappear, merged groups stay merged).

## Build pipeline (Plan A scope)

The Layer 2 builder runs after Layer 1's `discovery_v2` build. Five stages, each idempotent:

### Stage A1 — Stem extraction (verified-promotion)

1. For each brand_phrase in `party_atoms` where `atom_type = 'brand_phrase'`, find candidate stem:
   - Highest-IDF distinctive 1-gram in the phrase, OR
   - Highest-rank position-anchor 1-gram if no distinctive 1-gram exists.
2. For each candidate stem `s`:
   - Find the anchor (phone or address_root) where the most party-sides have a phrase mapping to `s`.
   - Compute `dominance_share = N_sides_at_anchor_with_s / N_sides_at_anchor`.
3. Promote `s` to verified if `dominance_share ≥ 0.6 AND volume ≥ 5`. Else discard `s` and the phrases that mapped only to it.
4. Apply verified stems: each phrase whose candidate matches a verified stem gets that stem in `brand_stem_phrase_map` with `confidence = candidate_idf_or_pa_rank`.

Output: `brand_stem`, `brand_stem_phrase_map`.

### Stage A2 — Anchor uniqueness scoring

For each anchor type (phone, address_root, address_base, contact_fingerprint) and each value:
1. Pull all `(source_id, side)` party-sides at this anchor.
2. For each party-side, look up the dominant stem (most-common stem across the side's phrases via `brand_stem_phrase_map`).
3. Find the dominant_stem across the anchor's party-sides.
4. Compute `dominance_share` and `score = dominance_share × log(volume + 1)`.
5. Insert into `anchor_uniqueness`.

Output: `anchor_uniqueness` rows for every populated anchor.

### Stage A3 — Auto-seed from anchor convergence

1. For each verified stem, pull all anchors where `dominant_stem = stem AND score ≥ 1.5`.
2. Group those anchors into one seed per stem. Generate `auto_group_id = AGRP_NNNNN` (using a counter pattern matching existing `app_meta` ID schemes).
3. Tier the seed by counting **anchor categories** that converge — collapse `address_root` and `address_base` into one "address" category, so categories are: `phone`, `address`, `contact`. Maximum 3.
   - 3 distinct anchor categories → `confirmed`
   - 2 distinct anchor categories → `probable`
   - 1 anchor category with score ≥ 1.5 + at least one corroborating anchor (any category) with score ≥ 0.5 → `candidate`
   - Pure single anchor with no corroboration → don't seed (the stem stays unattached)
4. Compute confidence:
   ```
   confidence = (n_anchor_categories / 3) × 0.4
              + min(avg_anchor_score / 5.0, 1.0) × 0.4
              + 0.2  # placeholder; replaced by (1 - anti_evidence_ratio) × 0.2 in Plan B
   ```
   The `5.0` reference is a fixed score ceiling — keeps confidence stable across runs and avoids being skewed by an outlier mega-anchor.
5. Insert `auto_groups`, `auto_group_anchors`.

Apply CRM overrides (read `auto_group_overrides`, `auto_group_merges`, `auto_anchor_overrides`) to lock in user-confirmed actions:
- A `confirm` action forces tier = `confirmed` regardless of computed score.
- A `reject` action removes the auto_group.
- A `merge` action collapses two auto_groups into one.
- An `override_stem` redirects an anchor's dominant_stem.
- An `override_service_provider = 1` removes the anchor from seeding eligibility.

### Stage A4 — Group expansion

For each seeded auto_group:
1. Find all party-sides whose anchors match the group's `auto_group_anchors`.
2. Score each candidate party-side:
   ```
   match_score:
     direct stem hit (phrase → group stem)              = 1.0
     phone match, no contradicting stem                 = 0.7
     address_root match + contact match                 = 0.7
     address_root match alone (HQ-class anchor)         = 0.5
     phone match + brand contradiction (other stem)     = -0.5  → don't attach
     single weak signal (just contact, common name)     = 0.3   → don't attach
   ```
3. Attach if `match_score ≥ 0.5`. Insert into `auto_group_members` with `member_type = 'party_side'`.
4. For each attached party-side whose `party_atoms.atom_value` includes a numbered Ontario or numbered Canada corp pattern (e.g., `\d+\s+ontario`, `\d+\s+canada`), insert a corresponding `auto_group_members` row with `member_type = 'numbered_corp'` and the corp name as the source_id surrogate.

Output: populated `auto_group_members`.

### Stage A5 — Display name and counts

For each auto_group:
1. `display_name` = most-frequent brand_phrase across the group's members where the phrase maps to `canonical_stem`.
2. Update `auto_groups.n_anchors`, `n_members`, `confidence`.

## API endpoints (Plan A scope)

```
GET /api/explorer/auto-groups
    ?tier=confirmed|probable|candidate
    &q=<substring on display_name or canonical_stem>
    &page=&per_page=
    → { results: AutoGroupSummary[], total, page, per_page, pages }

GET /api/explorer/auto-groups/{auto_group_id}
    → AutoGroupDetail with anchors, members, evidence summary, top phrases
```

`AutoGroupSummary` includes: `auto_group_id`, `canonical_stem`, `display_name`, `tier`, `confidence`, `n_anchors`, `n_members`.

`AutoGroupDetail` extends summary with: anchor list (typed), member party-sides (capped at 200 with link to full list), top brand_phrases (top 20), date range, n_distinct_contacts.

Endpoints are read-only in Plan A. Plan C adds POST/PATCH endpoints for confirm/reject/merge/split actions.

## UI surface (Plan A scope)

A new "Groups (Auto)" tab inside the Explorer, peer to existing Brands/Phones/Addresses/Contacts, at `/explorer/auto-groups`. Two views:

**List view** (`/explorer/auto-groups`):
- Tier filter (Confirmed / Probable / Candidate, default = Confirmed)
- Search input (substring on display_name or canonical_stem)
- Paginated table: display_name, canonical_stem, tier badge, confidence, n_anchors, n_members
- Row click → detail

**Detail view** (`/explorer/auto-groups/:id`):
- Header: display_name, canonical_stem, tier badge, confidence, n_party_sides, n_anchors
- Sections:
  - **Anchors** — typed list (phone / address-root / address-base / contact) with per-anchor score
  - **Top phrases** — top brand_phrases that landed in this group
  - **Members** — party-side cards (reusing existing `PartySideCard`)
  - **Numbered corps owned** — list of numbered Ontario/Canada corps tagged as group-owned vehicles
  - **Date range** — earliest and latest sale_date among members

Read-only in Plan A. No confirm/reject buttons until Plan C ships.

## Defaults and tunable knobs

| Knob | Default | Where it lives |
|---|---|---|
| Stem promotion: dominance threshold | 0.6 | constants module |
| Stem promotion: volume threshold | 5 | constants module |
| Anchor seeding score threshold | 1.5 | constants module |
| Confidence tier: confirmed | ≥ 0.75 | constants module |
| Confidence tier: probable | 0.4–0.75 | constants module |
| Confidence tier: candidate | < 0.4 | constants module |
| Service-provider trigger | score < 0.3 AND volume ≥ 5 AND distinct_stems ≥ 5 | constants module |
| Group expansion match threshold | 0.5 | constants module |

All knobs live in `cleo/discovery_v2/constants.py` (or similar). Tuning them and re-running the builder is fast (no schema changes).

## Testing

### Plan A

Unit tests:
- Stem extraction: synthetic phrases with known candidate-stem mappings; verify promotion thresholds.
- Anchor scoring: synthetic party_fingerprints with known stem distributions; verify dominance and score formula.
- Seed tiering: synthetic anchor sets with 1, 2, 3+ types; verify tier assignment.
- Match scoring: party-sides with various anchor combinations; verify expansion rule.

Integration tests:
- Seed Skyline (5198260439 + 5 Douglas + jason castellan) and verify expansion picks up sub-REIT phrases.
- Seed KingSett (4166876700 + 40 King) and verify SREIT/KS-prefixed SPVs attach.
- Verify a multi-tenant building (161 Bay) doesn't seed any group from address alone.
- Verify a common-name contact (e.g., "michael smith") doesn't seed any group.
- Verify the Berkshire mega-cluster failure mode from prior iteration doesn't recur.

Real-DB smoke:
- Run the full builder against `data/cleo.db`. Capture: total auto_groups by tier, top 10 by n_members, manual spot-check of 5 groups against known-good operators.

### Plan B

- Tenure span generation for known multi-job contacts (e.g., daniel drimmer at starlight + transglobe shows two tenures or one — depends on whether they're treated as the same group).
- Internal-transfer detection on synthetic same-phone-both-sides-same-stem transactions.
- Service-provider tagging on rudolph bratty, michael smith equivalents.

### Plan C

- Cascade: confirm group X, verify groups whose anchors overlap get re-tiered (auto-merge / promotion / demotion).
- Override persistence: reject a group, run builder again, verify it doesn't reappear.
- Merge: manually merge groups A and B, verify subsequent builds keep them merged.

## Non-goals (explicitly out of scope)

- Cross-source merging (RT + GW + OSM) — separate Layer 3 effort, not part of this design.
- Address-name SPV pattern recognition (e.g., resolving "DD 64 Roehampton" to the actual ARN at 64 Roehampton) — separate Layer 3 effort.
- Modifying the existing `groups`, `contacts`, `properties`, `transactions` tables or the pages that read from them.
- Replacing or feeding the auto_groups data into the Properties / Contacts / Transactions UI surfaces.
- Cross-side trade-flow analysis ("who sells most to whom"). Already visible in Layer 1 query patterns; not a Layer 2 product.
- Brokerage / agent attribution.

## Success criteria

- Plan A produces ≥ 50 Confirmed auto_groups against `data/cleo.db` with manual spot-check showing ≥ 90% correctly identify a real operator (no Frankenstein clusters).
- All known top-10 operators (Starlight, Skyline, Metrus, KingSett, H&R, Dream, RioCan, Berkshire Axis, Greenpark, Erin Mills) appear as Confirmed groups with the expected anchor convergence.
- A multi-tenant office building (e.g., 161 Bay) does NOT seed a group from its address alone.
- A common-name contact (e.g., "michael smith") does NOT seed a group.
- The Berkshire mega-cluster failure mode from earlier iterations doesn't reproduce.
- Plan B adds tenure for ≥ 80% of contacts with ≥ 5 party-sides; rare overlap cases (< 5%) are flagged for review.
- Plan C cascade re-tiers correctly on user confirmation: confirming a top operator triggers visible cascade effects on related Probable groups.

## Open questions for spec review

None — the design discussion resolved all major architectural decisions:
- Stem extraction: verified-promotion (Option C)
- Confidence tiering: tiered buckets (Confirmed / Probable / Candidate)
- Tenure model: closed spans (Option A)
- Sandboxing: strict, new tables only
- Cascade: first-class, surfaces "since you confirmed X, here's what changed"
- All four name-identifier fields contribute equally (already verified in Layer 1)

Tunable knobs (thresholds) will be adjusted iteratively after Plan A produces its first run.
