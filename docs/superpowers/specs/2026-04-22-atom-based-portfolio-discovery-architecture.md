# Atom-Based Portfolio Discovery — Architecture Spec

**Date:** 2026-04-22
**Status:** Draft for review (v2 — full rewrite)
**Supersedes:** `cleo/discovery/` (rules-based exact-match grouping)
**Depends on:** `cleo/atoms/normalize.py`, `cleo/atoms/fingerprint.py`, exploration report `docs/atom-exploration/2026-04-22-report.md`

---

## 1. Purpose

Build a system that reconstructs **biographical narratives** for Ontario commercial real estate operators and the people who work with them. The output isn't a list of duplicate-party clusters — it's **timelines** for each Group (operator) and each Contact (person), showing when they appeared, at which addresses, with which phones, with which collaborators, and how those associations evolved over time.

The current exact-match grouping system (`cleo/discovery/`, 2,393 lines, 136,266 groups keyed by `normalize_group_name(party_name)`) is retired in full. It clusters only on exact name match of the registered entity, misses every SPV-style portfolio (where the brand lives in `trade_name` / `care_of` / `companies_json`), ignores address/phone/contact signals entirely, and has no concept of time.

The new system must:

- Treat every transaction party-side as an immutable **packet of truth** — a dated observation that contributes evidence without being averaged or weakened.
- Link packets into Group and Contact entities via layered atom matching, with variant handling (nicknames, fuzzy, subset).
- Materialize Group and Contact **timelines** as first-class outputs.
- Default to linking (same entity) when a distinctive atom matches; require **disproving evidence** to split.
- Expose calibration knobs that can be turned in sequence with measured impact.
- Feed back from the labeling tool: human-confirmed links strengthen the algorithm over time.
- Live entirely behind UI surfaces, not CLI, per CLAUDE.md.

## 2. Core Model

### 2.1 The unit of truth: party-side as immutable fact

A **party-side** is one row in `party_fingerprints` / `party_atoms`: the buyer or seller on one transaction. 249,084 exist in the corpus today. Each says: *on `sale_date`, this brand identity, with this contact, at this address, via this phone, participated in this transaction.* It is a fact.

Party-sides are never modified by the discovery pipeline. They are indexed (via atoms) and linked (via edges in the Group and Contact graphs), but their content is preserved verbatim. Errors in the source data are accepted as part of the evidence — treated as noise to be outweighed by corroborating observations, not as values to be corrected.

### 2.2 Three entities

- **Group** — an operator with a brand identity and a lifetime. A Group entity is the composite narrative across all its party-sides: its active years (first observation → last observation), its address history (with time ranges), its phone history, its contact roster, its JV partners.
- **Contact** — a person with a career. Appears across one or more Groups at different times. Has a history of employer affiliations, addresses, phones.
- **Party-side** — the dated observation that ties one Group + one Contact + one address + one phone together at a moment in time.

Groups and Contacts are *derived* from the evidence. Party-sides are the evidence.

### 2.3 The two graphs

Two graphs share the same party-side nodes but carry different edges:

- **Group graph.** Edge between party-sides A and B when their brand atoms match (via any tier: exact, subset, fuzzy, etc.). Connected components become Group entities.
- **Contact graph.** Edge between party-sides A and B when their contact fingerprints match (via any tier: exact, nickname, phonetic, fuzzy). Connected components become Contact entities.

The two graphs **cross-validate** each other:

- Same Group across different addresses over time + same contact present at both = HQ move (one Group, one continuous timeline).
- Same Contact across different Groups over time + no shared address = career change (one Contact, distinct Group affiliations in sequence).
- Matching brand + matching contact + shared address = triple-corroborated link (overwhelming evidence).
- Weak brand match (e.g., fuzzy) + shared contact at shared address = upgraded to strong (see §6).

Edges in each graph are annotated with the **match tier** that generated them, so the algorithm can apply tier-specific rules during clustering.

### 2.4 Disprove-based linking

The algorithm's default stance is: **if a distinctive atom agrees, the pair belongs to the same entity until conflicting evidence is found.** Rarity raises the disprove bar — "KingSett" alone is enough to link because collision is implausibly unlikely. Weak matches (fuzzy, phonetic, short common names) require corroborating evidence to cross into auto-link.

Long gaps, by themselves, are not disprove. Missing evidence is not evidence of absence. Disprove tests (§8) exist but are flags for review, not auto-splits.

## 3. Atom Taxonomy

Atoms are already produced by `cleo/atoms/fingerprint.py`. Recap:

### 3.1 Singleton atoms (one per party-side, `party_fingerprints`)

`street_number`, `street_name`, `street_suffix`, `street_direction`, `suite_type`, `suite_number`, `city`, `province`, `postal`, `country`, `phone`, `contact_fingerprint`, `sale_date`.

### 3.2 Multi-valued atoms (many per party-side, `party_atoms`)

- `brand_phrase` and `brand_token` sourced from `party_name`, `trade_name`, `care_of`, `companies_json` — all four treated equivalently (the branded identifier lives in any of them).
- `law_firm_phrase` and `law_firm_token` sourced from `law_firms_json`.

### 3.3 What does and doesn't count as a clustering atom

**Counts:** brand, contact, address-triple, phone, postal, suite (in specific combinations — see §6).
**Blocking-only, non-scoring:** city, province, country.
**Informational, never primary signal:** law_firm atoms.
**Excluded categorically (never emitted as linking atoms):** see §9.

## 4. Variant Matching (v1-critical, not deferred)

Missing variants means missing transactions means broken timelines. All four layers are in v1.

### 4.1 Exact

Post-normalization equality. The canonical case.

### 4.2 Nickname table (first-name variants)

- Starter table of ~150 common English pairs: Dan/Daniel, Bob/Robert/Rob, Mike/Michael, Jim/James, Chuck/Charles, Rick/Richard, Tony/Anthony, Bill/William, Steve/Stephen, Joe/Joseph, Liz/Elizabeth, Pat/Patrick/Patricia, etc.
- Domain-specific additions (Italian-Canadian CRE circles are common: Vito/Vittorio, Carmelo/Carlo, Nino/Antonino, Gino/Luigi, etc.) added manually as we discover them.
- Sourced initially from `nickmatcher` / FamilySearch / US Census nickname data, curated to remove ambiguous ones.
- **Self-improving.** See §11.
- Stored in `nickname_table(canonical_first, variant_first, source, approved)` — derived, but rebuildable from a source-of-truth YAML checked into git.

Nickname match on first name + exact match on last name → same base confidence as an exact full-name match. `Dan Hagler` ↔ `Daniel Hagler` is treated as the same person at link time.

### 4.3 Phonetic (last name)

Double Metaphone or Beider-Morse Phonetic Matching (BMPM — better for non-English names, important for Ontario's naming diversity).

Phonetic match fires when last names are phonetically equivalent but spellings differ: Kumer/Kumar, Aghar/Agar, Chen/Chan (careful — these may be distinct families; see below).

**Guard rails:**
- Phonetic alone = medium confidence. Never auto-link without co-signal (shared address, phone, or Group).
- Common-name suppression: phonetic match doesn't fire on top-frequency surnames (Smith, Chen, Patel, etc.) unless corroborated. A frequency cutoff is calibrated; it's not a hardcoded exclusion, it's a rule that scales with name commonness.

### 4.4 Edit-distance fuzzy (full fingerprint)

Jaro-Winkler similarity on the full normalized contact fingerprint or brand phrase. Threshold calibrated during Phase B (nominal starting point: ≥ 0.92 for contact, ≥ 0.95 for brand — brand is stricter because "Kingsett" ↔ "Kingsley" would be 0.91 and must not link).

Catches typos: `daniell hagler` ↔ `daniel hagler`, `rioccan` ↔ `riocan`, `kingsett capitol` ↔ `kingsett capital`.

**Fuzzy alone = medium-low confidence.** Requires co-signal to upgrade.

### 4.5 Brand-phrase subset

Cleanco already strips legal suffixes (`Inc`, `Ltd`, `Corp`, etc.). On top of that, a subset rule: if all distinctive tokens of phrase A appear in phrase B (in any order, after dropping stopwords and generic tokens), treat as a candidate variant link.

- `"DH Management"` ⊂ `"DH Property Management"` — candidate match (shared token: `dh`)
- `"KingSett Capital"` ⊂ `"KingSett Capital GP No 1"` — candidate match
- `"Management"` ⊂ `"Property Management"` — **not** a match (shared tokens are generic; no distinctive overlap)

**Subset alone = medium confidence.** Requires at least one non-generic token in common AND a co-signal (shared address, phone, or contact).

### 4.6 Initial-form matching

"DH" appearing as a brand phrase, when another party-side has "Dan Hagler" as contact at the same address and same approximate time → "DH" is inferred to be the initials of Dan Hagler (or Daniel Hagler, the group founder).

This is a derived rule rather than a pre-seeded match: the link is discovered when address + phone + time window agree between the initialed-brand party-side and a named-contact party-side. Emits a variant-link with provenance logged for auditability.

## 5. Tiered Confidence with Context Upgrade

Every candidate link has two values:

- **Base confidence**, derived from the match type (exact, nickname, phonetic, fuzzy, subset).
- **Effective confidence**, which is the base upgraded by any corroborating co-signals found on the party-sides.

### 5.1 Base confidence by match tier

| Tier | Example | Base |
|---|---|---|
| Exact match, rare atom | `brand_token = "kingsett"`, `phone = "4166876700"` | Strong |
| Exact match, common atom | `city = "toronto"` | Blocking-only (not a link by itself) |
| Nickname | `"dan hagler"` ↔ `"daniel hagler"` | Strong |
| Phonetic | `"rob kumer"` ↔ `"rob kumar"` | Medium |
| Edit-distance fuzzy | `"danell hagler"` ↔ `"daniel hagler"` | Medium-Low |
| Brand subset | `"dh management"` ⊂ `"dh property management"` | Medium |
| Initial-form | `"dh"` brand ↔ `"dan hagler"` contact at same address | Medium (upgrades easily) |

Rarity (IDF) further multiplies base: a rare token match is stronger than a common token match at the same tier. `rasenberg` exact match = exceptionally strong; `group` exact match = barely signal.

### 5.2 The context upgrade rule

A weak match upgrades to Strong the moment a corroborating atom of a different category is found on both party-sides.

Concrete:

- `"rob kumer"` ↔ `"robbie kumer"` (phonetic, Medium) + both at `66 Wellington`, both carrying `kingsett` brand_token → upgraded to Strong. Auto-linked.
- `"dh management"` ↔ `"dh property management"` (subset, Medium) + both share contact `dan hagler` → upgraded to Strong. Auto-linked.
- `"danell hagler"` ↔ `"daniel hagler"` (fuzzy, Medium-Low) + both at `180 Shorting` → upgraded to Strong.
- `"rob kumer"` at random address A, `"robbie kumer"` at random address B, no shared Group, no shared phone → stays Medium. Surfaces in review tier.

The rule encodes your principle: "as soon as Danell Hagler is found at 180 Shorting and Dan Hagler is also found at 180 Shorting, this becomes the same confidence as if Danell was correctly spelled Daniel."

### 5.3 Clustering by effective confidence

Two tiers at clustering time:

- **Strong (effective)** → union-find, auto-linked into the same Group or Contact entity.
- **Medium / Medium-Low (effective, no co-signal upgrade)** → surfaced in the labeling tool for human verdict. Human confirms or rejects. Rejected = forbidden-edge, enforced in the next discovery run.

## 6. Pair Scoring (computing Strong vs. Medium)

Not a weighted sum over atoms. Instead, **rule-based with explicit tiers:**

Two party-sides share a candidate link if at least one of the following holds:

1. **Exact match on a non-generic atom**: brand_token (IDF above threshold), phone, or address-triple.
2. **Exact match on contact fingerprint** (first+last exact).
3. **Variant match** at any tier (nickname, phonetic, fuzzy, subset).

Given a candidate link, compute **effective confidence** as follows:

```
if match_tier is Exact and atom is rare:
    confidence = Strong
elif match_tier is Nickname on contact + exact on last:
    confidence = Strong
elif match_tier is Phonetic/Fuzzy/Subset:
    confidence = Medium (base)
    if corroborating atom on both party-sides (any category):
        confidence = Strong (upgraded)
elif match_tier is Exact but atom is generic (IDF below threshold):
    confidence = None — not a link, just blocking support for higher tiers
```

Same logic applies whether we're resolving Group identity (brand atoms drive) or Contact identity (contact fingerprint drives).

### 6.1 Phone and contact as primary link atoms

- **Phone alone** with no brand or address co-signal = Medium, never auto-link. A shared phone number can be a management-company line shared across unrelated operators (a common false-positive pattern). Surfaces for review, upgrades to Strong with any co-signal.
- **Contact alone** across Groups = edge in the Contact graph, NOT in the Group graph. One person can work at many Groups. Shared contact does *not* merge two Groups unless the contact bridges them at a consistent address/phone AND the brand atoms themselves subset-match.

### 6.2 Address-triple matching

`street_number + street_name + street_suffix` (with `suite_number` optional) is the address-triple. Requires all three of the required parts to match exactly. `suite_number` match bumps the contribution when the triple matches.

`street_name` alone is near-useless (the top name "king" appears on 4,587 party-sides). Never a link atom on its own.

### 6.3 No numeric frequency thresholds for exclusion

Exclusions are **categorical**, not frequency-based. IDF handles frequency-based signal dampening continuously and without cliff effects. See §9.

## 7. The Knob Calibration Framework

Every matching rule is a knob. Knobs are calibrated in sequence; each is validated against metrics before the next is opened. Some knobs have **prerequisite filters** that activate when they open, to compensate for the extra noise admitted.

### 7.1 Knob order (sharpest → softest)

1. **Exact `brand_token` match (non-generic).** The dominant, near-tautological signal. Starting point for all calibration.
2. **Exact first+last contact fingerprint.**
3. **Exact address-triple.**
4. **Exact phone.**
5. **Brand-phrase subset match** (DH Management ⊂ DH Property Management).
6. **Nickname-table first-name match.**
7. **Phonetic last-name match** (BMPM).
8. **Edit-distance fuzzy match** (Jaro-Winkler on full fingerprint).
9. **Initial-form brand match** (DH brand = Dan Hagler initials).
10. **Context-upgrade rules** (weak match + co-signal).
11. **Gap-tolerance and subsidiary/successor flags** (the 20-year-gap case).

### 7.2 How each knob is tuned

For each knob:

1. Open the knob at its baseline setting. Re-run discovery.
2. Measure diff against previous calibration:
   - Audit recall / purity on the 8 ground-truth portfolios (`docs/discovery-audit/`).
   - Number of Group-graph edges added / removed.
   - Number of Contact-graph edges added / removed.
   - Sample 50 newly-linked pairs; manually spot-check. Record "gold vs. garbage" ratio.
   - Regression against growing corpus of labeling-tool verdicts.
3. If gold ratio ≥ 95%, keep the setting. If < 95%, identify the failure pattern.
4. If failure pattern is avoidable, add a **compensating filter rule**. Example: relaxing fuzzy to catch `danell → daniel` introduces `jim smith ↔ jim smithe`. Compensating rule: fuzzy-match on full fingerprint requires either (a) rare surname, or (b) corroborating co-signal.
5. If failure is unavoidable at this threshold, tighten the knob.
6. Commit the calibration with rationale note. Move to next knob.

### 7.3 Calibration knobs live in config, not code

`cleo/discovery/config.py`:

```python
CALIBRATION = {
    "version": "2026-04-22-v1",
    "exact_brand_token": {
        "min_idf": 3.0,  # tokens with IDF below this count as generic
        "reason": "Tokens on >5K party-sides add noise without discriminating. Set at 3.0 so 'ontario' (IDF ~1.4) is blocked, 'rasenberg' (IDF ~8.5) is allowed.",
    },
    "nickname_table": {
        "enabled": True,
        "source": "data/nickname_table.yaml",
    },
    "phonetic_last_name": {
        "algorithm": "bmpm",
        "common_surname_cutoff": 500,  # >500 party-sides = require co-signal
        "reason": "Phonetic match on Smith/Chen/Patel too noisy alone.",
    },
    "fuzzy_contact": {
        "algorithm": "jaro_winkler",
        "threshold": 0.92,
        "require_co_signal": True,  # always
    },
    "fuzzy_brand": {
        "algorithm": "jaro_winkler",
        "threshold": 0.95,
        "require_co_signal": True,
    },
    # ...
}
```

Checked into git. Every change is a commit. Reverts are `git revert`. History of calibration decisions is the history of the file.

### 7.4 Eval harness

Single admin UI surface: "Run discovery with config X". Produces:

- Portfolio diff vs. previous run (added / removed / merged / split).
- Audit metrics (recall, purity) per ground-truth portfolio.
- Sample of 50 newly-linked pairs for human spot-check (stored in `discovery_review_sample` table, user marks gold/garbage in UI).
- Regression report against labeling-tool verdicts.

Report is saved to `docs/discovery-audit/YYYY-MM-DD-run-N.md` with the config snapshot, so we have an auditable history.

## 8. Disprove Tests (Flags, Not Auto-Splits)

Disprove tests surface candidate pairs for review when the atoms agree but something about the timeline or evidence feels suspect. They never auto-split in v1. Review lands in the labeling tool.

### 8.1 Gap with total evidence change

Same distinctive brand token (e.g., `kingsett`) in two party-sides, but:

- Gap ≥ 15 years (calibrated knob), AND
- Brand phrase differs (KingSett Capital vs. KingSett Wealth Management), AND
- No shared address, phone, or contact.

Surfaces as: "Candidate subsidiary / rebrand / successor — review."

The 15-year threshold is a knob, not a rule. Calibrated based on how many real-world evolutions we find at each setting.

### 8.2 Temporal anomaly

Same Contact appearing at two geographically distant addresses within a short window (e.g., Toronto and Calgary on the same day).

Surfaces as: "Verify contact continuity — possible SPV cluster on a single day, or possible name collision."

Not disprove — same-day multi-city happens for SPV buy-walks. Flag only.

### 8.3 Competitor overlap (not JV)

Same Contact appearing at two direct competitors within the same year, without a JV signal (no shared party-side carrying both brand phrases).

Surfaces as: "Verify career transition timing or possible name collision."

### 8.4 Volume anomaly

Contact's derived total transaction volume exceeds a sanity cap (e.g., $500M in a single year).

Surfaces as: "Possible merged Contact — verify."

This is the David-George-case safety net: when auto-merge accidentally combines two distinct people, the volume aggregation flags it for manual split.

## 9. Categorical Exclusions

Exclusions are **categorical**, not frequency-based. IDF handles "mildly common" automatically. Categorical exclusions exist because the value isn't a brand/contact at all.

### 9.1 Excluded brand phrases / tokens

- **Artifacts**: `named individual s` (suppressed-name records, 43K party-sides, informationally inert), `creo mail code 01 86` (scraping artifact, 50 party-sides — investigate at source).
- **Stopwords**: `the`, `of`, `and`, `a`, `an`, `&`, `co`, `inc`, `ltd`, `llc`, `corp` (already in `tokenize_brand`).
- **Structural words that leaked into brand fields**: `street`, `road`, `avenue`, `suite`, `floor`, `unit`, etc. — address vocabulary that appears in brand fields via parser bleed. Confirmed as leak; filtered at source.

### 9.2 IDF handles the rest

`ontario` (58K party-sides, IDF ~1.4), `holdings` (17K, IDF ~2.7), `canada` (11K, IDF ~3.2) are common corporate vocabulary. No categorical exclusion. IDF makes them near-zero contributors unless multiple co-occur on the same pair — in which case the *pattern* of co-occurrence itself becomes signal.

This is important: we don't hide data. We let the math dampen the signal of common values and let the rare values speak.

### 9.3 Party-sides with only excluded atoms

A party-side whose only brand atom is `named individual s` has no brand-based link candidates. It can still link via address, phone, or contact — and it must, because these records are legitimate transaction participants with suppressed names.

## 10. Timelines — the Second Layer of Truth

### 10.1 Per-Group timelines

Once the Group graph is clustered, derive per-Group timeline tables:

- `group_addresses_timeline(group_id, postal, street_number, street_name, street_suffix, first_seen, last_seen, n_observations)` — address history with date ranges.
- `group_phones_timeline(group_id, phone, first_seen, last_seen, n_observations)` — phone history.
- `group_contacts_timeline(group_id, contact_id, first_seen, last_seen, n_observations, role)` — contact roster with tenure at this Group. (Role is derivable from linked `contacts.job_title` when available.)
- `group_party_sides(group_id, source_id, side, sale_date, confidence)` — the raw party-sides that belong to this Group, with per-link confidence.

### 10.2 Per-Contact timelines

- `contact_groups_timeline(contact_id, group_id, first_seen, last_seen, n_observations)` — employer history.
- `contact_addresses_timeline(contact_id, postal, ..., first_seen, last_seen, n_observations)` — address history across all Groups.
- `contact_party_sides(contact_id, source_id, side, sale_date)` — raw party-sides.

### 10.3 Group-to-Group relationships (JV, etc.)

When a single party-side carries two or more distinct brand phrases (the Canderel + KingSett JV case), the observation contributes to **both** Group timelines **and** emits a relationship edge:

`group_relationships(group_a_id, group_b_id, kind, first_seen, last_seen, n_party_sides)`

Where `kind ∈ { jv, parent_subsidiary, successor, ... }`. JV is the v1 relationship type (derived directly from multi-brand party-sides). Parent/subsidiary and successor are v2 (require more inference — flagged via disprove tests §8.1, confirmed by human, then written).

### 10.4 Second-order truths

Patterns the UI surfaces from the timeline data without needing to be explicitly derived:

- KingSett moved HQ in ~2015 (inferred from the 161 Bay → 66 Wellington address transition date).
- Peter Aghar left KingSett in ~2018 (inferred from his last-seen date at the KingSett contact roster).
- Phone 4166876700 has been KingSett's main line continuously since ~2000 (inferred from its 91.8% share across KingSett's party-sides and continuous presence over the time range).
- Canderel + KingSett did N JV transactions between 2010 and 2018 (relationship edges over time).

These aren't separate computations — they fall out of presenting the timeline tables in the right UI.

## 11. Self-Improving Nickname Table

When the labeling tool records a `verdict = confirmed` link between two party-sides whose first names differ (and neither is a known nickname variant), the differing first-name pair is appended to a `nickname_candidates` queue with pointers to the evidence (same last name, same address, same Group, same phone — whichever co-signals corroborated the link).

A weekly admin UI surface presents the queue:

- `Patty ↔ Patricia` (12 confirmed pairs, all with same last name + shared address)
- `Vito ↔ Vittorio` (8 pairs)
- `Robbie ↔ Rob` (already in table, skip)

Admin approves → appended to `nickname_table.yaml`, committed, next discovery run picks it up globally.

Admin rejects → marked so the candidate isn't re-queued.

Safety: auto-add applies only when the evidence is overwhelming (≥ 3 confirmed pairs with strong co-signal). Borderline cases wait for manual review.

## 12. Schema

Two categories of new tables:

### 12.1 Derived (rebuilt by discovery pass)

```sql
CREATE TABLE groups_discovered (
    id              TEXT PRIMARY KEY,  -- GRP_NNNNNN (persists via app_meta)
    canonical_brand TEXT NOT NULL,     -- most common non-generic brand_phrase
    display_name    TEXT NOT NULL,
    first_seen      TEXT,
    last_seen       TEXT,
    party_side_count INTEGER NOT NULL,
    discovered_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE contacts_discovered (
    id              TEXT PRIMARY KEY,  -- CON_NNNNNN (persists via app_meta)
    canonical_name  TEXT NOT NULL,     -- most common normalized fingerprint
    display_name    TEXT NOT NULL,
    first_seen      TEXT,
    last_seen       TEXT,
    party_side_count INTEGER NOT NULL
);

CREATE TABLE party_side_entities (
    source_id TEXT NOT NULL,
    side      TEXT NOT NULL CHECK (side IN ('buyer','seller')),
    group_id  TEXT REFERENCES groups_discovered(id),
    contact_id TEXT REFERENCES contacts_discovered(id),
    group_link_tier   TEXT,  -- 'exact'|'nickname'|'phonetic'|'fuzzy'|'subset'|'confirmed'
    contact_link_tier TEXT,
    PRIMARY KEY (source_id, side)
);

CREATE TABLE group_addresses_timeline (
    group_id TEXT NOT NULL REFERENCES groups_discovered(id),
    postal TEXT, street_number TEXT, street_name TEXT, street_suffix TEXT,
    first_seen TEXT, last_seen TEXT,
    n_observations INTEGER
);
CREATE INDEX idx_gat_group ON group_addresses_timeline(group_id);

CREATE TABLE group_phones_timeline (
    group_id TEXT NOT NULL REFERENCES groups_discovered(id),
    phone    TEXT NOT NULL,
    first_seen TEXT, last_seen TEXT,
    n_observations INTEGER
);

CREATE TABLE group_contacts_timeline (
    group_id   TEXT NOT NULL REFERENCES groups_discovered(id),
    contact_id TEXT NOT NULL REFERENCES contacts_discovered(id),
    first_seen TEXT, last_seen TEXT,
    n_observations INTEGER
);

CREATE TABLE contact_groups_timeline (
    contact_id TEXT NOT NULL REFERENCES contacts_discovered(id),
    group_id   TEXT NOT NULL REFERENCES groups_discovered(id),
    first_seen TEXT, last_seen TEXT,
    n_observations INTEGER
);

CREATE TABLE contact_addresses_timeline (
    contact_id TEXT NOT NULL REFERENCES contacts_discovered(id),
    postal TEXT, street_number TEXT, street_name TEXT, street_suffix TEXT,
    first_seen TEXT, last_seen TEXT,
    n_observations INTEGER
);

CREATE TABLE group_relationships (
    group_a_id TEXT NOT NULL REFERENCES groups_discovered(id),
    group_b_id TEXT NOT NULL REFERENCES groups_discovered(id),
    kind TEXT NOT NULL CHECK (kind IN ('jv','parent_subsidiary','successor')),
    first_seen TEXT, last_seen TEXT,
    n_party_sides INTEGER,
    PRIMARY KEY (group_a_id, group_b_id, kind)
);
```

All of the above are in `DERIVED_TABLES` and dropped/recreated by each discovery run.

Note: the existing `groups` / `contacts` tables (produced by the compiler) are preserved during the transition. Once the new system is validated against the 8 audits, a separate migration retires the legacy tables.

### 12.2 Semi-derived / growing (not dropped between runs)

```sql
CREATE TABLE nickname_table (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_first   TEXT NOT NULL,
    variant_first     TEXT NOT NULL,
    source            TEXT NOT NULL CHECK (source IN ('seed','labeling_derived')),
    confirmed_at      TEXT,
    UNIQUE (canonical_first, variant_first)
);

CREATE TABLE nickname_candidates (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    first_a          TEXT NOT NULL,
    first_b          TEXT NOT NULL,
    evidence_source  TEXT NOT NULL,  -- labeling_verdict_id
    confirmed_count  INTEGER,
    state            TEXT CHECK (state IN ('pending','approved','rejected')),
    created_at       TEXT DEFAULT (datetime('now'))
);

CREATE TABLE discovery_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    config_version  TEXT NOT NULL,
    config_snapshot TEXT NOT NULL,  -- full CALIBRATION dict as JSON
    ran_at          TEXT DEFAULT (datetime('now')),
    n_party_sides   INTEGER,
    n_groups        INTEGER,
    n_contacts      INTEGER,
    audit_metrics   TEXT,  -- JSON
    notes           TEXT
);

CREATE TABLE discovery_review_sample (
    run_id          INTEGER NOT NULL REFERENCES discovery_runs(id),
    pair_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id_a     TEXT, side_a TEXT,
    source_id_b     TEXT, side_b TEXT,
    match_tier      TEXT,
    human_verdict   TEXT CHECK (human_verdict IN ('gold','garbage', NULL))
);
```

Not dropped between runs. `nickname_table` and `nickname_candidates` grow over time as the labeling tool produces evidence.

## 13. UI Surfaces

Per CLAUDE.md, all user-facing operations live in the UI.

### 13.1 Atom Explorer (new, primary discovery surface)

A search box on a new `/explorer` page that indexes atoms by:

- Brand token (e.g., `kingsett`)
- Brand phrase (e.g., `kingsett capital`)
- Contact last-name token (e.g., `hagler`)
- Contact full fingerprint (e.g., `dan hagler`)
- Phone
- Postal / address-triple

Type `hagler` → see all contacts with "hagler" as a name token:

> - **Dan Hagler** — 47 party-sides, DH Management Inc (2002-2024), 180 Shorting Rd
> - **Daniel Hagler** — 12 party-sides, DH Property Management (2002-2024), 180 Shorting Rd *(likely same as Dan — auto-merged)*
> - **Nina Wine Hagler** — 8 party-sides, DH Management Inc (2015-2023), 180 Shorting Rd *(family — co-located)*
> - **Joseph Hagler** — 3 party-sides, JH Properties (2018-2020), North York

Type `kingsett` → see all brand entities with "kingsett" token:

> - **KingSett Capital** — 348 party-sides, 1998-2026, current HQ: 66 Wellington
> - **KingSett Wealth Management** — 12 party-sides, 2020-2026 *(likely subsidiary — review)*

Each entry click-throughs to the Group or Contact detail page with full timeline.

This is the primary tool for both exploratory research and calibration review.

### 13.2 Group detail page (replaces/augments current `/groups/:id`)

For each Group entity:

- Canonical display name + all brand variants observed
- Lifetime range (first_seen → last_seen)
- Address history with date ranges (map pins color-coded by era)
- Phone history with date ranges
- Contact roster with per-person tenure
- JV / relationship network (edges to other Groups)
- Raw party-sides list with sale_date, address, contact on each
- Per-party-side "remove from this Group" override action

### 13.3 Contact detail page

- Canonical name + all variants observed
- Career timeline (Group affiliations with date ranges)
- Per-Group addresses and phones
- Volume aggregates per Group (flags volume anomalies per §8.4)
- Per-party-side overrides as above

### 13.4 Admin: Discovery Run

- "Run discovery" button (current config).
- Config-editing UI (direct YAML edit with diff preview).
- Run progress, completion time.
- Post-run diff viewer: Groups added/removed/merged/split; Contacts added/removed/merged/split.
- Audit metrics vs. previous run.
- Sample of 50 newly-linked pairs for spot-check; mark gold/garbage inline.
- Approve / rollback buttons (writing to the active-config pointer in `app_meta`).

### 13.5 Admin: Nickname Review

Weekly queue of `nickname_candidates` with evidence counts. Approve → global nickname; reject → suppressed.

### 13.6 Labeling tool integration (existing)

Medium-confidence candidate pairs are surfaced in the existing labeling queue. Human verdicts feed back as:

- `confirmed` → forced-edge in next discovery run.
- `rejected` → forbidden-edge.
- If the verdict pair's first names differ → row in `nickname_candidates`.

## 14. Data Quality Fixes (from Exploration Report)

Implement before Phase A:

- **Malformed postal codes (61 values).** Store raw in new `postal_raw` column, set `postal` to NULL when format validation fails. Keeps "capture every field" while blocking bad values from signal.
- **French street suffixes.** Add to `_STREET_SUFFIX_MAP`: `rue → rue`, `chemin → chemin`, `ch → chemin`, `boul → boulevard` (already mapped as variant).
- **`creo mail code 01 86` artifact (50 party-sides).** Investigate the source parser (likely an RT field bleed). Fix at source, not at the discovery layer.
- **Long brand phrases (20 values >50 chars).** Investigate — some are legitimate legal entity names ("Her Majesty the Queen..."), others may be parser merges. Manual review; no code change unless a pattern emerges.
- **Purely numeric brand_tokens (20 values).** Some are legit corp numbers (`2725312 canada` → corp number). Keep, but dampen IDF contribution since they're effectively unique per corp and provide only weak signal for reuse clustering.

## 15. Rollout Phases

Each phase ends with metrics re-measured, discovery run committed, plan docs updated.

**Phase A — Exact-match layer.** Blocking + pair scoring for exact brand_token, exact contact fingerprint, exact address-triple, exact phone. Write Group and Contact graphs. Materialize basic timelines. No variants yet. Calibrate knobs 1-4 (§7.1). Validate against 8 audits.

**Phase B — Variant matching layer.** Add nickname table (seed from `nickmatcher`), brand-phrase subset, phonetic (BMPM), fuzzy (Jaro-Winkler). Calibrate knobs 5-8 with compensating filters as needed. Re-measure audits.

**Phase C — Context-upgrade rules.** Implement the weak-match + co-signal → strong promotion. This is the logic that makes variant matching precise without being noisy. Calibrate knob 10.

**Phase D — Timelines + JV modeling.** Materialize `group_addresses_timeline`, `group_contacts_timeline`, etc. Detect multi-brand-phrase party-sides → JV relationship edges. Surface on Group detail pages.

**Phase E — UI surfaces.** Build the Atom Explorer, Group detail timeline view, Contact timeline view, admin discovery run UI.

**Phase F — Labeling tool integration, overrides, self-improving nicknames.** Wire the labeling tool to emit forced-edges and nickname candidates. Build nickname review queue. Build per-member Group override UI.

**Phase G — Retire legacy discovery.** Delete `cleo/discovery/{rules,engine,signals,clustering,contacts,validation}.py`. Flip feature flag. Migrate CRM tables' `group_id` references via the compatibility view.

## 16. Migration from `cleo/discovery/`

The current module is retired in its entirety. Retirement path:

1. Phases A-D write to new schema (`groups_discovered`, `contacts_discovered`, etc.) in parallel with the legacy schema.
2. Phase E's UI reads from new schema.
3. Phase G deletes legacy code and legacy-schema backfill.

Feature flag in `app_meta.discovery_engine`: `legacy` or `atom_based`. Default flipped to `atom_based` only after Phase D metrics meet acceptance criteria.

Compatibility: CRM tables referencing `group_id TEXT` are not changed in v1. A view joins `party_side_entities` back to the legacy `groups` so existing CRM reads continue working during the transition.

## 17. Non-Goals (v1)

- **Sub-portfolio / parent-subsidiary hierarchy.** Flat Groups in v1. Subsidiaries are detected as a disprove-flag but confirmed by human, not auto-modeled as tree structure.
- **Asset-class-aware clustering.** One Group's residential and industrial portfolios are one Group here.
- **Cross-source clustering (RT + GW + OSM).** Party-side is RT-only. GW/OSM linking is a separate problem handled elsewhere.
- **Probabilistic m/u estimation (Fellegi-Sunter EM).** Revisit in v2 when the labeling-verdict corpus is large enough (~1K+ confirmed pairs) to train weights instead of hand-tuning them.
- **Asset-ownership inference.** What the Group *owns* today (parcels, active leases) is a separate problem from who the Group *is*.
- **Temporal split of a single Group into two successor Groups.** When KingSett Capital becomes KingSett Wealth Management, v1 flags for review. v2 models the succession as a relationship edge.

## 18. Open Questions (before implementation)

1. **Starter nickname table scope.** Proposal: import `nickmatcher` (~1500 English pairs), apply a manual filter to drop ambiguous mappings (e.g., `gene ↔ eugene` keep; `terry ↔ theresa/terrance` drop), plus a hand-curated ~50 domain-specific pairs for Ontario CRE (Italian-Canadian, etc.). Output: ~800-1000 approved pairs. Approve?

2. **Common-surname phonetic cutoff.** Proposal: surnames on ≥500 party-sides require co-signal when phonetic-matched. Tuneable. OK?

3. **Fuzzy thresholds.** Starting: contact Jaro-Winkler ≥ 0.92, brand Jaro-Winkler ≥ 0.95. Both require co-signal. Calibrate in Phase B.

4. **Gap-with-evidence-change threshold.** Starting: 15 years. Flags as "subsidiary / rebrand / successor" for human review. Calibrate based on how many real-world cases we find at different settings.

5. **Initial-form brand rules.** Proposal: "DH" (≤3 uppercase characters, no lowercase content) matches to a contact whose first-name + last-name initials match, IF both party-sides share address + phone + sale_date within 90 days. Too loose? Too tight?

6. **JV threshold.** A party-side with 2 distinct brand_phrases → JV. With 3+? All pairwise relationships, or treat as "consortium" marker? Proposal: all pairwise JV edges.

---

**Next step after approval:** writing-plans skill produces the Phase A implementation plan — exact-match layer only, calibrated against the 8 audits, saved to `docs/superpowers/plans/2026-04-22-discovery-phase-a.md`.
