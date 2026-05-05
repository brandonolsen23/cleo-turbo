# Contact Tenure Page Design

**Date:** 2026-05-04
**Status:** Design approved, ready for implementation planning
**Supersedes (in part):** the Contact page's reliance on `auto_contact_tenures` as the source of truth for employer attribution

---

## Problem

The existing Contact detail page picks the wrong "current group" for most prospects. For Paul Braun (CON_07049), the page surfaces *CF Vaughan Portfolio Inc* — one of 63 SPVs he is on — when his actual employer is CanFirst Capital Management. The "Groups (63)" panel is a noisy SPV roster, not a career picture. Phones and addresses on the page carry no tenure context, so an analyst cannot tell whether a number is current or belonged to a former employer.

The auto-group system was supposed to solve this. For Paul it does not: there is no auto-group with `canonical_stem='dundee'`, and the auto-group with `canonical_stem='canfirst'` (AGRP_01392) credits him with only 58 of his 80 party-sides and starts his tenure in 2005, three years after he joined the firm.

The data needed to fix this is already in `party_atoms`. Filtering to `atom_type='brand_phrase' AND source_field IN ('trade_name','care_of','companies_json')` yields, for Paul:

| brand_phrase | source_field | n party-sides |
|---|---|---|
| canfirst capital management | trade_name | 41 |
| canfirst capital management | companies_json | 15 |
| canfirst capital management | care_of | 4 |
| dundee realty | care_of | 5 |
| dundee realty | companies_json | 3 |

Two clean tenures fall out of those rows by simple aggregation: Dundee Realty 1999–2001 and CanFirst Capital Management 2002–2022. The current page renders neither because it reads from `auto_contact_tenures`, which depends on auto-groups being formed for every brand — they are not, and forcing them to be will keep failing the same way.

This spec separates brand-tenure derivation from auto-group clustering, makes brand_phrase source fields the primary signal for identifying employers, and redesigns the Contact page around the resulting career history.

## Goals

- **Identify a contact's employer correctly** without depending on auto-groups being right.
- **Show every employer the contact has worked for**, with start/end dates derived from the data.
- **Distinguish active vs stale phones and addresses** so analysts do not call former-employer numbers.
- **Show the current employer's full portfolio** as the primary map on the contact page, since that is what predicts what they buy and sell.
- **Preserve the existing page bones** (Property Footprint, Transaction History) so the change is additive in feel.
- **Keep the data model forward-compatible** with a future Group/Company page that mirrors the Contact page.

## Non-goals

- Fixing the auto-group clustering algorithm. Auto-groups continue to compute as today; their job is recast (see Architecture). Algorithm tuning is out of scope.
- Job titles for realtrack-derived tenures. Realtrack data does not carry titles. LinkedIn provides them when imported.
- Replacing the existing `/groups/GRP_NNNNN` SPV-level pages. They remain as a drill-in.
- Sub-brand splits (e.g., "H&R REIT" vs "H&R Group" living on the same `h&r` stem). Stem-level is sufficient for V1; sub-brand handling is a future stem-map enhancement.

---

## Architecture

Two computed tables, one repurposed system, one new soft link.

### `contact_brand_tenures` — source of truth for "where a contact worked, when"

One row per `(contact_fingerprint, brand_stem)` where the contact has at least 2 qualifying party-sides.

| column | meaning |
|---|---|
| `contact_fingerprint` | e.g., `paul braun` |
| `brand_stem` | canonical stem from `brand_stem_phrase_map`, e.g., `canfirst` |
| `strict_start_date` | earliest sale_date among party-sides whose qualifying brand_phrase carries this stem |
| `strict_end_date` | latest sale_date among the same set |
| `inferred_start_date` | strict_start, extended backward via address bracketing (see Derivation §2) |
| `inferred_end_date` | strict_end, extended forward via address bracketing |
| `n_party_sides_strict` | count of party-sides with explicit stem mention |
| `n_party_sides_inferred` | count after address-bracketed expansion (≥ strict) |
| `top_phrases_json` | `[{"phrase":"canfirst capital management","n":60}, ...]` — variant phrases under this stem |
| `source_field_breakdown_json` | `{"trade_name":41,"companies_json":15,"care_of":4}` |
| `dominant_address_unit` | the address_unit that most frequently co-occurs with this (contact, stem) pair during the strict window — the basis for bracketed expansion |
| `auto_group_id` | nullable; populated when an `auto_groups` row exists with matching `canonical_stem` (the corroboration link) |
| `is_active` | derived: `1` if `inferred_end_date >= today - 730 days`, else `0` |
| `discovered_at` | timestamp |

**Qualifying party-sides:** `party_atoms` rows where `atom_type='brand_phrase' AND source_field IN ('trade_name','care_of','companies_json')`, joined to `party_fingerprints` on `(source_id, side)`. The `party_name` source field is intentionally excluded — that is where SPV names live, not management-company names.

This is a derived table, rebuilt on the same cadence as the existing Layer 2 derived tables. CRM-style override tables (planned, not in this spec) can attach later.

### `group_brand_tenures` — same data, flipped perspective (Phase 2)

Read the same `contact_brand_tenures` table grouped by `brand_stem` instead of by `contact_fingerprint`. No new table is needed. The Group page extension uses this read pattern to render its Workforce tile.

### `auto_groups` — keeps existing job, drops the load-bearing role

Auto-groups continue to cluster brand-less SPV nests (e.g., the "18 Erica" pure-numbered-SPV pattern) and link related SPVs through anchor uniqueness. They no longer carry the burden of being the source of truth for employer naming.

The Contact page **stops reading `auto_contact_tenures`** for primary employer attribution. It reads `contact_brand_tenures.auto_group_id` as a hyperlink target — a "drill into the auto_group if one exists" decoration, not the source of truth.

### `current_employer` — the header pill

Not a table; a per-contact derivation rule (see §2d). Combines LinkedIn-imported career history (when present) with `contact_brand_tenures` to pick the employer to show in the page header. LinkedIn is authoritative; realtrack data is shown alongside.

---

## Derivation Rules

### 2a. Stem unification

Every qualifying brand_phrase is mapped to a `stem` via `brand_stem_phrase_map`. Phrases not in the map fall back to the first non-stopword `brand_token` of the phrase, computed via existing `cleo/atoms/normalize.py`. One stem = one tenure row per contact.

### 2b. The window — anchor-bracketed

Compute the **strict window** first: MIN/MAX `sale_date` of party-sides where the qualifying brand_phrase carries the stem. Store as `strict_start_date` / `strict_end_date`.

Then compute the **inferred window**:

1. Identify the `dominant_address_unit` for this (contact, stem) pair — the address_unit that appears on the most party-sides within the strict window.
2. Extend the window backward to the earliest `sale_date` of any party-side where the same contact appears at the dominant address (even if that party-side carries only an SPV brand_phrase).
3. Extend forward by the same rule.

Store as `inferred_start_date` / `inferred_end_date`.

For Paul × CanFirst this extends the window from 2004-07-02–2022-12-13 (strict) to 2002-04-29–2022-12-13 (inferred via 30 St Clair). For Paul × Dundee both windows are 1999-01-27–2001-06-12 (no extension; no further 390 Bay party-sides exist outside that range).

The UI uses `inferred_*_date` as the primary display. The Tenure Detail drawer (§3) shows both, so the audit trail is preserved.

### 2c. Threshold

A `(contact_fingerprint, brand_stem)` pair becomes a tenure row iff `n_party_sides_strict >= 2`. One-shot mentions get filtered as noise. The source-field filter is doing the heavy lifting on quality already.

### 2d. "Active" and "current employer"

**Per-tenure `is_active`:** `1` iff `inferred_end_date >= today - 730 days`. Two-year recency cliff.

**Per-contact current_employer (header pill):** decided by precedence:

1. If LinkedIn data is imported and specifies a current company, **LinkedIn wins**. The pill shows the LinkedIn company name.
2. Else, the realtrack tenure with `is_active = 1` and the highest `n_party_sides_inferred` is shown.
3. Else, no pill.

When LinkedIn says X and a corresponding realtrack tenure exists with stem = X, the two reconcile: pill shows "LinkedIn-confirmed". When LinkedIn says X and the realtrack data points elsewhere, the pill shows X (LinkedIn) with a "diverges from Realtrack" indicator — the Career History tile lists both, so the analyst can investigate without losing either signal.

### 2e. Deal attribution to tenures

A transaction is credited to a (contact, stem) tenure iff:

- The contact appears on either side of the transaction
- `sale_date BETWEEN inferred_start_date AND inferred_end_date`
- AND **either** the party-side carries the qualifying stem **or** is at the `dominant_address_unit` of the tenure

This is what makes the Career History tile display "60 transactions credited" rather than just the 41 with explicit "canfirst capital management" trade_name. It is also the rule the new Tenure column on the Transaction History table uses, with `(i)` marking address-inferred (vs explicit stem) attributions.

### 2f. Overlapping tenures

Allowed and expected. Board seats, consulting engagements, transitions. UI sorts career history by `inferred_end_date DESC` so the current/most-recent tenure is at the top, and shows visual overlap (color-banded date bars) when present.

### 2g. Tenure-aware contact info

For each phone and address on `party_fingerprints` for this contact, derive:

- `first_seen` / `last_seen` — MIN/MAX `sale_date` across this contact's party-sides carrying the phone/address.
- `tenures_overlapped` — list of tenures whose `[inferred_start_date, inferred_end_date]` window overlaps with `[first_seen, last_seen]`.
- `is_active` for the phone/address: `last_seen >= today - 730 days` AND overlaps with the contact's `current_employer` tenure. Both must be true to mark "Active".

UI surface (Contact Info card):

- Active phone/address → green tag: `Active · CanFirst since 2008`.
- Stale phone/address → muted gray tag: `Last seen Jun 12, 2001 · Dundee era`.

---

## Page Design

Two-column layout preserved (left = info cards, right = map + table). Property Footprint and Transaction History keep their bones; both gain tenure context.

### Header

Structure unchanged. The subtitle pill is the new piece. Three states:

- **LinkedIn-confirmed** (jade): LinkedIn imported AND realtrack tenure stems agree.
- **Realtrack-derived** (slate): LinkedIn not imported; pill comes from the active realtrack tenure with the most party-sides.
- **LinkedIn (with divergence)** (amber): LinkedIn says X; realtrack tenure points elsewhere. Pill shows LinkedIn as authoritative; small indicator flags the divergence so the analyst can investigate.

Existing buttons (Promote to Engaged, Notes, Buy Mandate) unchanged.

### Left Column

**1. Contact Info card** (modified)

Same fields. Each phone/address row picks up a tenure label underneath:

```
Phone
(416) 924-9009                           [Active · CanFirst since 2008]

Phone (former)
(416) 555-1234                           [Last seen Jun 12, 2001 · Dundee era]
```

Stale entries remain visible with muted styling — the warning is more useful when the number is right there. No "show stale contact info" toggle.

**2. Career History tile** (replaces both old "Group" card and "Groups (63)" panel)

Primary identity card. LinkedIn rows render first when imported; realtrack-derived rows render below. When a LinkedIn company stem matches a realtrack tenure stem, the two reconcile into a single row carrying both source pills.

```
Career History (3)                                              [+ Add manually]

● managing director · CanFirst Capital Management              [Current]
  Jan 2002 – Present · 24 yr 5 mo
  [via LinkedIn] [via Realtrack · 60 transactions credited]
  └── 30 St Clair Avenue West, Toronto · primary address during this tenure

○ unknown role · Dundee Realty
  1999 – 2001 · 3 years
  [via Realtrack · 15 transactions credited]
  └── 390 Bay Street, Toronto · primary address during this tenure
```

Each row is clickable → opens the Tenure Detail drawer.

A footer link `View 63 SPVs credited to these tenures` opens the SPV-level drill-in for analysts who need that detail. The "Groups (63)" panel itself is gone.

### Right Column

The right column's hero changes based on whether a current employer is identified.

**When current employer IS identified** (Paul's case):

1. **Group Portfolio Footprint** (hero, top of right column) — large map, header `CanFirst's Portfolio (847 transactions)`. Every transaction credited to any canfirst tenure across any contact.
2. **Property Footprint** (smaller, below) — Paul's 80 transactions on a condensed map. Pins color-coded by tenure (CanFirst color, Dundee color, unattributed gray). Hover shows the tenure.
3. **Transaction History** (table, full-width below the maps) — Paul's 80 deals. Adds a `Tenure` column showing which tenure each row is credited to (`CanFirst`, `Dundee`, `CanFirst (i)` for inferred-via-address).

**When no current employer is identified** (e.g., contacts with no qualifying brand_phrases):

Property Footprint promotes back to the hero spot — preserving today's default. Group Portfolio Footprint is hidden.

### Tenure Detail drawer

Click any Career History row → side drawer slides in from the right (does not navigate away from the Contact page). Contents:

```
CanFirst Capital Management
Jan 2002 – Present (LinkedIn) · 60 deals credited (Realtrack)

Why we named this tenure
───────────────────────────────────────────────────
Top phrases extracted from his transactions:
  • canfirst capital management ······ 60×
  • canfirst capital ·················· 4×

Source field breakdown:
  • trade_name ········· 41
  • companies_json ····· 15
  • care_of ············· 4

Window
───────────────────────────────────────────────────
Earliest explicit canfirst mention:  2004-07-02 (RT36352)
Inferred start (via 30 St Clair):    2002-04-29 (RT25393)
Latest:                              2022-12-13 (RT...)

Linked auto_group:  AGRP_01392  →  [Open group page]

Credited transactions (60)
───────────────────────────────────────────────────
[scrollable list: date · address · price · brand_phrase · source_field]
```

This is the audit-trail surface. When the algorithm gets something wrong, the user sees exactly *why* and can decide what to override (override workflow is a separate spec).

---

## Group Page Extension (Phase 2 sketch)

Out of scope for V1 implementation. Sketched here only to confirm the data model is forward-compatible.

### Identity systems

Cleo currently has three "who is this company" identities:

| Identity | What it is | Granularity |
|---|---|---|
| `GRP_NNNNN` (compiler) | UPPERCASE party_name with legal suffixes stripped | One per SPV (CanFirst has 63) |
| `AGRP_NNNNN` (auto_groups) | Clustered SPVs by anchor uniqueness | One per cluster (CanFirst has 1) |
| `canonical_stem` (the new spine) | Brand stem from `brand_stem_phrase_map` | One per management-company brand (`canfirst`) |

The Phase 2 Group page uses `canonical_stem` as its primary identity — the prospecting unit. Likely URL `/companies/canfirst`. Existing `/groups/GRP_NNNNN` pages remain as the SPV-level drill-in. The auto_groups Explorer page remains as an internal QA tool.

### Mirror layout

| Contact page section | Group page equivalent |
|---|---|
| Career History tile | **Workforce / Personnel History** — every contact with a tenure at this stem, sorted by `is_active DESC, n_party_sides DESC`. Click → opens that contact's page. |
| Tenure-aware Contact Info | **Active Office / Active Phones** — addresses + phones with their tenure window at this stem |
| Group Portfolio Footprint (hero) | **Portfolio Footprint** — already the natural hero on a Group page |
| Transaction History | Existing transactions table, gains a "Contact" column |

### Forward compatibility

The `contact_brand_tenures` table is keyed on `(contact_fingerprint, brand_stem)`. Reading it grouped by `brand_stem` populates the Workforce tile. Reading the same `phone_tenures` / `address_tenures` derivations aggregated to the stem level populates Active Office / Active Phones. **No schema change is needed for Phase 2** — only new endpoints and rendering.

---

## Implementation phases

**V1 (this spec):**
- Build `contact_brand_tenures` table and the derivation pipeline.
- Compute phone / address tenure metadata per contact.
- Add `/api/contacts/:id` enrichment: career_history, current_employer, phone/address tenure tags.
- Add `/api/companies/:stem/portfolio-footprint` endpoint for the hero map.
- Redesign Contact page per §3.
- Tenure Detail drawer.
- Stale-phone "last seen" labeling.

**V2 (deferred, separate spec):**
- Group/Company page at `/companies/:stem`.
- Override workflow for incorrect tenure attributions.
- Sub-brand splits if needed (e.g., H&R REIT vs H&R Group).
- Job-title derivation from text patterns in `companies_json` (low confidence; LinkedIn remains primary).

---

## Open questions deferred to plan

- Whether `contact_brand_tenures` is rebuilt on the existing Layer 2 cadence or computed on demand.
- Whether `dominant_address_unit` is stored on the tenure row or recomputed from `address_unit_summary` lookups at render time.
- API shape for the Tenure Detail drawer — single endpoint returning everything, or split.

These are implementation-plan concerns, not design decisions.

---

## Decision log

| # | Decision | Rationale |
|---|---|---|
| 1 | Spine is brand-stem tenures derived from `party_atoms`, not auto-groups | Auto-groups have failed to produce a Dundee silo for Paul Braun and similar gaps elsewhere. The brand_phrase data is already explicit in `trade_name` / `care_of` / `companies_json`. |
| 2 | Auto-groups link soft-corroboratively (option C) | Best of both: source-of-truth from data already there; auto-groups still useful for SPV nests and as a hyperlink target when their canonical_stem matches |
| 3 | Anchor-bracketed window | Matches user mental model — Paul moved to 30 St Clair in 2002, that's when CanFirst started, regardless of which SPV the early deals named. Strict + inferred dates both stored for audit. |
| 4 | Threshold ≥ 2 party-sides | Balances catching short tenures with filtering one-shot noise. Source-field filter ensures quality. |
| 5 | LinkedIn always wins for current employer; realtrack shown alongside | LinkedIn carries titles + ground-truth dates; realtrack adds transaction count and historical employers LinkedIn does not cover. Both are visible. |
| 6 | Drill-in is a side drawer | Keeps analyst on the Contact page while comparing tenures. |
| 7 | Group Portfolio Footprint is the right-column hero (when current employer known) | What predicts buyer/seller behavior is the firm's whole portfolio, not just the contact's slice. |
| 8 | Stale phones/addresses always visible with `Last seen [date] · [tenure]` | "Don't call this number" warning is most useful right next to the number, not hidden behind a toggle. |
| 9 | `party_name` excluded from qualifying source fields | SPV names live there. The CLAUDE.md "branded identifier lives in four fields" rule means trade_name / care_of / companies_json are where management-company brands live; party_name is the registered SPV. |
