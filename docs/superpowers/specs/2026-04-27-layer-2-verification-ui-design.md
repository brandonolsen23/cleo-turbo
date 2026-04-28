# Layer 2 Verification UI

**Date:** 2026-04-27
**Builds on:** Plan A — Foundation (shipped). The algorithm produces `auto_groups`, `auto_group_anchors`, `auto_group_members`, `brand_stem`, `anchor_uniqueness`, `brand_stem_phrase_map`. The list page (`/explorer/auto-groups`) and detail page (`/explorer/auto-groups/:id`) exist but only display the algorithm's outputs as static tables — no path to verify or tune anything.

## Glossary (single source of truth — used strictly throughout this spec and any subsequent plans)

| Term | Definition |
|---|---|
| **Transaction** (or **RT**) | One Realtrack record. Has two sides: buyer and seller. Identified by `source_id`. |
| **Party** | One side of one transaction — the buyer side, or the seller side. The thing the algorithm groups. Identified by `(source_id, side)`. A transaction has exactly two parties. |
| **Group** (or **auto_group**) | A collection of parties the algorithm has attached to the same operator (e.g., KingSett). Identified by `auto_group_id` (`AGRP_NNNNN`). |
| **Anchor** | A phone, address (root or base), or contact name that the algorithm has assigned to a group. The shared hooks that link parties to a group. |
| **Stem** | The canonical operator label that names a group (`kingsett`, `starlight`). Derived from a 1-gram in the brand silo. |
| **Match score** | The algorithm's per-party confidence that this party belongs to this group, computed from how many of the group's anchors that party touches and how strongly. Range -0.5 to 1.0. |
| **Brand phrase** | The entity name on a party — pulled from `party_name`, `trade_name`, `care_of`, or `companies_json`. All four sources contribute equally; the field a brand phrase came from is preserved in `party_atoms.source_field`. |
| **Tier** | Group's confidence bucket: `confirmed` (≥0.75 + 3 anchor categories), `probable` (≥0.4 + 2 categories), `candidate` (1+ categories with corroboration). |
| **Anchor category** | One of: `phone`, `address` (collapses `address_root` + `address_base`), `contact`. Three total. Used for tier counting. |
| **Anchor coverage** | Within a group, how many of the group's parties touch a specific anchor. `phone 4166876700` covers 332 of KingSett's 820 parties. |
| **Co-stem** | Another stem whose dominant phrase appears at the same anchor. If `phone 4162348444` is the Starlight phone, but `dd` and `tg` also appear there, those are co-stems — useful for spotting tenure / JV signals. |
| **Anchor signature** | The set of (anchor_type, anchor_value) pairs a party touches. Two parties with identical signatures are interchangeable for grouping purposes; useful for bundling in visualizations. |

This glossary is locked. No alternate names for any concept appear in the rest of the spec or in future plans for this work.

## Goal

Make the auto-group surface a verification workbench:

1. **Inspect** any party, anchor, or group with full evidence visible in one click.
2. **Verify** that algorithmic decisions match reality — easy to spot-check 5 Confirmed groups in 15 minutes.
3. **Visualize** the structure of a group as a graph of anchors and parties, so the *shape* of the membership is self-explanatory.
4. **Tune** the algorithm by surfacing why specific stems didn't promote, why specific groups landed in their tier, and what threshold tweaks would move which groups.

All work lives under `/explorer/auto-groups`. Existing pages (Map, Properties, Groups, Contacts, Transactions, Pipeline, etc.) are off-limits. The compiler, Layer 1 silos, and Plan A backend tables/endpoints are not modified.

## Scope decision

The work decomposes into four sub-projects, executed in order. Each ships independently and is reviewed before moving on:

| Sub-project | Surface | Description |
|---|---|---|
| **Plan D** | Detail-page redesign | Replace the current single-page detail view with five tabs (Overview, Anchors, Parties, Graph, Trail). Skeleton + Overview + Anchors + Parties tabs ship in this plan. |
| **Plan E** | Graph view | The hub-and-spoke visualization — center = group, inner ring = anchors, outer cloud = anchor-signature bundles of parties. Click bundle → expand to individual parties. |
| **Plan F** | Trail view | The single-party evidence view — pick a party, see the threads of shared anchors connecting it to its group(s). Surfaces conflicting evidence (parties whose threads point at multiple groups). |
| **Plan G** | Tuning page + list-page filters | New `/explorer/auto-groups/tuning` page (confidence histogram, "close to promotion" queue, missed-stem diagnostics). List-page additions: "close to promotion" filter, distinct-contacts column, anchor-diversity sort. |

Plan D is the foundation for D/E/F to coexist; E and F can ship in either order after D. Plan G is independent.

This spec covers the full design end-to-end. Each sub-project gets its own implementation plan when it's ready to be built.

---

## Plan D — Detail-page redesign

### URL structure (no changes)

- `/explorer/auto-groups/:id` continues to be the entry point.
- Tabs render within the page; deep links to specific tabs use `?tab=anchors|parties|graph|trail` (defaulting to overview).

### Tab structure

| Tab | What it shows |
|---|---|
| **Overview** | Headline stats + "Why this tier" panel + top-N brand phrases + numbered corps. The current detail page minus the anchors and parties tables. |
| **Anchors** | Anchor-evidence table. Each anchor row shows type, value, score, **coverage** (X of N parties), **co-stems** (other operators sharing this anchor), and a click-through link to the corresponding Layer 1 silo page. |
| **Parties** | Readable per-party table replacing the opaque `source_id \| side \| match_score` list. Each row shows the party's brand phrase, address, contact, sale date, sale price, side, anchor signature, and match score. Sortable, filterable. Click → opens the existing `SourceViewerDrawer`. |
| **Graph** | Hub-and-spoke graph (Plan E). |
| **Trail** | Single-party evidence trail (Plan F). |

Plan D ships Overview, Anchors, and Parties. Graph and Trail tabs render placeholders ("Coming in Plan E/F") until those plans ship.

### Overview tab

Top section: stat cards (existing — confidence, anchors, parties, distinct contacts, date range). Removed: the anchors and parties tables, which move to their own tabs.

Below the stat cards: **Why this tier** panel.

For Confirmed groups:
> Confirmed because: phone (4166876700, score 2.0) + address (40 king, score 2.4) + contact (rob kumer, score 2.1). All three categories cleared the seeding bar. Confidence 0.78.

For Probable groups:
> Probable. Missing: contact category (no contact-anchor cleared the 1.5 seeding score). Strongest contact at this group's anchors is `joe smith` (score 0.31, below corroboration bar 0.5). Confidence 0.62.

For Candidate groups:
> Candidate. Single strong category (phone, score 1.8) plus 2 corroborating anchors (address_root score 0.6, contact score 0.5). Confidence 0.31.

Then **Top phrases** (top 20 brand phrases mapped to canonical_stem, current data) and **Numbered corps owned** (clickable badges → tooltip with which transactions surfaced each corp).

### Anchors tab

Replaces the current static anchors table. Each row: anchor_type, anchor_value, score, coverage (`X of N parties`), co-stems list, link icon to Layer 1 silo.

Coverage is a new computed column — for each anchor in the group, how many of the group's `auto_group_members` (party_side type) have that anchor on their party. Computed via:

```sql
SELECT aga.anchor_type, aga.anchor_value, COUNT(*) AS coverage
FROM auto_group_anchors aga
JOIN auto_group_members agm ON agm.auto_group_id = aga.auto_group_id AND agm.member_type = 'party_side'
JOIN party_fingerprints pf ON pf.source_id = agm.source_id AND pf.side = agm.side
WHERE aga.auto_group_id = ?
  AND (
    (aga.anchor_type = 'phone'        AND pf.phone = aga.anchor_value) OR
    (aga.anchor_type = 'address_root' AND (pf.street_number || '|' || pf.street_name) = aga.anchor_value) OR
    (aga.anchor_type = 'address_base' AND (pf.street_number || '|' || pf.street_name || '|' || COALESCE(pf.street_suffix,'')) = aga.anchor_value) OR
    (aga.anchor_type = 'contact'      AND pf.contact_fingerprint = aga.anchor_value)
  )
GROUP BY aga.anchor_type, aga.anchor_value
```

Co-stems for an anchor: which other stems' phrases appear on parties at this anchor. Computed from `anchor_uniqueness` plus a join through `party_fingerprints` and `brand_stem_phrase_map`. Cap at 5 co-stems per anchor; if more, show count.

Click-through links per anchor type:

| Anchor type | Target |
|---|---|
| phone | `/explorer/phones/<value>` |
| address_root | `/explorer/addresses/roots/<value>` (URL-encoded) |
| address_base | `/explorer/addresses/bases/<value>` |
| contact | `/explorer/contacts/<value>` |

These pages already exist as Layer 1 silo views. The link makes the existing infra usable for verification without duplicating it.

### Parties tab

Replaces the opaque parties table. Columns:

| Column | Source |
|---|---|
| Date | `party_fingerprints.sale_date` |
| Side | `auto_group_members.side` (buyer/seller) |
| Brand phrase | top brand phrase on this party (from `party_atoms`, atom_type='brand_phrase') |
| Address | formatted from `party_fingerprints.street_*` |
| Contact | `party_fingerprints.contact_fingerprint` |
| Phone | `party_fingerprints.phone` |
| Anchor signature | colored chips, one per anchor category the party touches that's also a group anchor |
| Match score | `auto_group_members.match_score` |

Sort: default by date desc. Sortable on every column.

Filter inputs:
- Match score range slider (default 0–1)
- Side toggle (all / buyer / seller)
- Anchor filter — pick an anchor (e.g., `contact: david vernon`) to show only parties that touch it. This is the verification path: "show me only the parties that prove david vernon is a KingSett contact."
- Brand phrase substring

Row click → opens `SourceViewerDrawer` with `source_id`. The drawer is an existing component used elsewhere in the app.

Performance: paginate at 100 per page. The 200-cap on the API already limits results to the top 200 by match_score; remove that cap and rely on pagination instead, since the user wants to inspect parties beyond the top 200 for verification.

### Backend changes for Plan D

New endpoints:

- `GET /api/explorer/auto-groups/:id/anchors-with-coverage` — returns the existing anchors list plus per-anchor `coverage` and `co_stems`. Replaces the inline anchors block in the existing detail endpoint.

- `GET /api/explorer/auto-groups/:id/parties` — paginated parties list with all the columns above. Query params: `page`, `per_page` (default 100, max 500), `min_match_score`, `side`, `anchor_type`, `anchor_value`, `q` (brand phrase substring). Sortable via `sort=date|match_score|...&order=asc|desc`.

- `GET /api/explorer/auto-groups/:id/why-tier` — returns the structured "Why this tier" data (which categories converged, which strongest near-miss, threshold gaps). Trivially derived from the existing `auto_group_anchors` data; computed inline.

The existing `GET /api/explorer/auto-groups/:id` continues to return the summary + numbered corps + top phrases. Anchors and members move to the new endpoints.

### Frontend changes for Plan D

- New tab component (`AutoGroupTabs.tsx`) wraps `Overview | Anchors | Parties | Graph | Trail`.
- Existing detail page becomes the Overview tab.
- New `AutoGroupAnchorsTab.tsx` — table with coverage, co-stems, click-through.
- New `AutoGroupPartiesTab.tsx` — paginated, filterable, sortable; row click opens SourceViewerDrawer.

Graph and Trail tabs render a "Coming soon" placeholder with the linked plan reference.

---

## Plan E — Graph view

### What it is

A radial node-edge diagram of one group. Center hub = the group. Inner ring = the group's anchors. Outer cloud = bundles of parties grouped by anchor signature.

### Visual structure

```
                    [phone X]
                    /         \
[contact A]----[ KINGSETT ]---[address Y]
                    \         /
                  [bundle: 142 parties]
                  [bundle:  87 parties]
                  [bundle:  34 parties]
                  ...
```

- **Center node** (one): displays group's display_name, tier badge, party count, anchor count.
- **Anchor nodes** (≤30): one per row in `auto_group_anchors`. Sized by anchor coverage. Colored by anchor type (phone / address / contact).
- **Bundle nodes** (~5–15 per group, default state): one per distinct anchor signature among the parties. Labeled with party count + the anchors in the signature. Sized by party count.
- **Edges**: anchor → bundle when bundle's parties touch that anchor; group → anchor (always); bundle → group (always).

### Interaction model

Default state: anchor ring expanded, parties shown as bundles only. Clean — ~30 anchor nodes + ~10 bundle nodes = ~40 nodes total. Easy to read.

Click on a bundle → expands into its individual party nodes. The bundle's edges to anchors fan out per party. Click again to collapse.

Click on a party node → opens the SourceViewerDrawer.

Click on an anchor → highlights every bundle / party connected to it.

"Expand all" button → renders every party as an individual node. Warns if total parties > 200.

Pan / zoom standard React Flow.

### Bundling rule

Group parties whose `(source_id, side)` rows have identical anchor signatures (same set of `(anchor_type, anchor_value)` pairs that match group anchors). Bundles are computed server-side; the API returns precomputed bundles + their party lists.

Parties whose match_score is borderline (0.5 ≤ score < 0.7) are NEVER bundled — they're rendered individually so the verification trail is visible per-party. Parties with match_score ≥ 0.7 bundle by default.

### Backend for Plan E

`GET /api/explorer/auto-groups/:id/graph?layout=anchor_ring` returns:

```json
{
  "center": { "id": "AGRP_00001", "display_name": "kingsett capital", "tier": "confirmed", "party_count": 820, "anchor_count": 31 },
  "anchors": [
    { "id": "anchor:phone:4166876700", "type": "phone", "value": "4166876700", "score": 2.0, "coverage": 332 },
    ...
  ],
  "bundles": [
    {
      "id": "bundle:1",
      "anchor_signature": [["phone","4166876700"],["address_root","40|king"],["contact","rob kumer"]],
      "party_count": 142,
      "min_match_score": 1.0,
      "max_match_score": 1.0
    },
    ...
  ],
  "individual_parties": [
    {
      "id": "party:RT100502:seller",
      "source_id": "RT100502", "side": "seller",
      "anchor_signature": [...],
      "match_score": 0.62,
      "brand_phrase": "..."
    },
    ...
  ],
  "edges": [
    { "source": "AGRP_00001", "target": "anchor:phone:4166876700" },
    { "source": "anchor:phone:4166876700", "target": "bundle:1" },
    { "source": "bundle:1", "target": "AGRP_00001" },
    ...
  ]
}
```

Bundles are computed by `GROUP BY anchor_signature` server-side. The "borderline → individual" rule excludes those parties from bundles before grouping.

`GET /api/explorer/auto-groups/:id/graph/bundle/:bundle_id` — returns the parties in one bundle, used when the user clicks "expand bundle." Avoids overloading the initial graph payload when bundles are large.

### Frontend for Plan E

- React Flow integration (added as a dependency: `@xyflow/react`).
- Custom node types: `GroupCenter`, `AnchorNode`, `BundleNode`, `PartyNode`.
- Custom edge types with hover popover showing the anchor that links a party to a bundle/group.
- Layout: simple radial. Center node at origin. Anchor nodes evenly distributed on a circle of radius R₁ (≈ 200px). Bundle nodes on a wider circle of radius R₂ (≈ 380px). When the user expands a bundle, its parties render as a small grid attached to the bundle node. React Flow doesn't ship a radial layout by default — implement a small layout helper (deterministic, no force-directed simulation needed for this shape).
- Initial render performance budget: < 1s for groups up to 50 anchors and 30 bundles. "Expand all" can take longer (with progress indicator) but must warn on N > 200.

---

## Plan F — Trail view

### What it is

The single-party evidence view. Pick one party, see the threads of shared anchors connecting it to its group(s). The visual answer to "why is this party in this group?"

### Entry point

Two ways to enter:

1. From the Parties tab (Plan D) → click "Trail" icon on a row → opens this tab focused on that party.
2. From the SourceViewerDrawer → "View Layer 2 trail" button → navigates to `/explorer/auto-groups/<group_id>/trail?source_id=...&side=...`. (The drawer surfaces the party's group attribution.)

### Visual structure

```
[party RT100502 / seller]
    |                                  |
    | phone 4166876700  | address 40 king | contact rob kumer
    |                                  |
[ KINGSETT ]                        [ KINGSETT ]
```

- **Left node**: the party (with its brand phrase, address, sale_date, sale_price for context).
- **Threads**: one per anchor on the party. Each thread is labeled with the anchor (`phone 4166876700`).
- **Right nodes**: groups the threads point at.

If all threads point at the same group → confirmed. Confidence is high.

If threads point at DIFFERENT groups → conflict surfaced. Either the contact has a tenure split (worked at Group A 2010–2018, Group B 2018+), or the party is a JV / cross-portfolio transaction. The visual cue is immediate: a thread to KingSett and a thread to Starlight = something to investigate.

If a party has anchors that DON'T point at any group → unattached anchors, displayed as terminating threads with a note. These are tuning signals — anchors that exist but didn't get assigned to a group at seeding time.

### Backend for Plan F

`GET /api/explorer/auto-groups/parties/:source_id/:side/trail` — returns the trail data for one party:

```json
{
  "party": {
    "source_id": "RT100502", "side": "seller",
    "brand_phrase": "kingsett capital", "sale_date": "2019-04-22", "sale_price": 5200000,
    "address": "40 king street suite 4400", "contact": "rob kumer", "phone": "4166876700"
  },
  "threads": [
    {
      "anchor_type": "phone", "anchor_value": "4166876700",
      "groups": [
        { "auto_group_id": "AGRP_00001", "stem": "kingsett", "tier": "confirmed", "score_in_group": 2.0 }
      ]
    },
    {
      "anchor_type": "contact", "anchor_value": "rob kumer",
      "groups": [
        { "auto_group_id": "AGRP_00001", "stem": "kingsett", "tier": "confirmed", "score_in_group": 2.1 }
      ]
    },
    ...
  ],
  "primary_group": { "auto_group_id": "AGRP_00001", "stem": "kingsett", "match_score": 1.0 }
}
```

Conflict detection happens client-side: any thread with `groups.length > 1`, OR any party with multiple distinct `auto_group_id`s across its threads, is flagged with a warning UI.

### Frontend for Plan F

- React Flow again, but with a simpler horizontal layout (party left, groups right, threads as labeled edges).
- Conflict highlighting: if multiple groups appear, color the conflicting threads orange/red.
- "Why this group" call-out (computed client-side): "3 of 4 anchors point at KingSett; 1 anchor (contact `david vernon`) also appears at Starlight. Primary attribution: KingSett (match_score 0.95)."

---

## Plan G — Tuning page + list-page filters

### Tuning page (`/explorer/auto-groups/tuning`)

A new top-level page within the auto-groups surface. Three sections:

**1. Confidence histogram.** Bar chart of group counts per confidence bucket (0.00–0.05, 0.05–0.10, …, 0.95–1.00). Tier thresholds (0.4, 0.75) drawn as vertical lines. Hover a bucket → list of groups in it. Clicking a bucket filters the list page by that confidence range.

The point: see whether 0.75 is the right Confirmed cutoff. If most "real" operators sit at 0.70–0.74 and the algorithm is just barely missing them, lowering the threshold to 0.70 might be the right tuning. The histogram makes that visible.

**2. Close to promotion.** Probable groups within 0.05 of the Confirmed threshold (confidence 0.70–0.75). Each row: stem, current confidence, what's missing (from the "Why this tier" computation in Plan D), how easily it'd promote. Sortable by confidence desc.

This is the verification queue. Fast pass through this list = fast tuning iteration.

**3. Stems that didn't promote.** From the Plan A run notes, distinctive 1-grams with ≥100 party-sides that didn't get verified stems (`dd`, `ks`, `dundee`, `piret`, etc.). Each row: token, party_side count, the dominant stem at the candidate's strongest anchor (the one that beat it), the dominance share that won.

Click a row → drilldown showing the dominance contest:

> `dd` failed promotion. Strongest anchor: phone 4162348444 (Starlight phone). At that phone: 511 party-sides total, 320 contain `starlight`, 178 contain `dd`. Starlight wins (dominance 0.626 > dd's 0.348).

This surfaces the algorithmic tradeoff. If you want `dd` to be its own stem, the rule needs to be relaxed (e.g., promote a stem if it's the primary stem at *any* anchor, not just *the* dominant one).

### Backend for Plan G

- `GET /api/explorer/auto-groups/tuning/histogram` — confidence bucket counts.
- `GET /api/explorer/auto-groups/tuning/close-to-promotion?from=0.70&to=0.75` — queryable cutoff.
- `GET /api/explorer/auto-groups/tuning/missed-stems?min_n_party_sides=100` — the table of distinctive 1-grams that didn't promote, with dominance-contest data per row.

### List-page additions

- New filter on the existing list page: "Close to promotion" toggle. When on, restricts to confidence 0.70–0.75 regardless of tier.
- New column: **Anchor diversity** = count of distinct anchor categories in `auto_group_anchors` for the group. 1, 2, or 3.
- New column: **Distinct contacts** = `n_distinct_contacts` (already in the detail endpoint; surface in list).
- Sortable by anchor diversity DESC (Confirmed groups with all 3 categories rise to top of any tier filter).

---

## Database considerations

No schema changes. All new endpoints are queries against the existing Plan A tables (`auto_groups`, `auto_group_anchors`, `auto_group_members`, `party_fingerprints`, `party_atoms`, `brand_stem`, `brand_stem_phrase_map`, `anchor_uniqueness`).

Indexes that may need to be added if performance becomes an issue (note for Plan D implementation):

- `CREATE INDEX idx_pa_atom_value ON party_atoms(atom_value)` — speeds up brand-phrase substring filters.
- `CREATE INDEX idx_pf_phone_root_contact ON party_fingerprints(phone, street_number, street_name, contact_fingerprint)` — composite for the anchor-coverage query.

These would land in a new migration if the SQLite query planner shows them as needed during real-DB testing.

## Testing

### Plan D

- Unit tests on the anchor-coverage computation against synthetic data with known overlaps.
- Unit tests on the "why this tier" structured output.
- API integration tests for the three new endpoints (anchors-with-coverage, parties paginated, why-tier).
- Frontend smoke test: tabs render, anchors tab clicks through to Layer 1 silo, parties tab pagination + filter combinations, SourceViewerDrawer opens on row click.

### Plan E

- Backend test: bundle-grouping logic produces correct anchor signatures and respects the borderline-individual rule.
- Frontend smoke test: graph renders for the top-10 Confirmed groups in the real DB, click-to-expand-bundle works, "expand all" warning appears for groups > 200 parties.
- Performance: initial graph render < 1s on representative group sizes.

### Plan F

- Backend test: trail computation correctly identifies all groups each anchor points at, handles parties with no group attribution, handles parties with multi-group threads (conflicts).
- Frontend smoke test: trail renders for a party with single-group threads, with multi-group threads (conflict highlighting visible), with unattached anchors.

### Plan G

- Backend test: histogram bucket counts match a separate `SELECT COUNT(*) FROM auto_groups GROUP BY ...` reference query.
- Backend test: close-to-promotion query respects the from/to bounds.
- Backend test: missed-stems data correctly identifies the dominance-contest winner per token.
- Frontend smoke test: histogram clicks filter the list page; close-to-promotion table renders sorted; missed-stems drilldown explains a known case (`dd` lost to `starlight`).

## Out of scope

- **User actions on groups** (confirm / reject / merge / split) — that's Plan C of the original Layer 2 design (not yet planned). The Verification UI surfaces the evidence; the cascade-on-action workflow is a separate effort.
- **Tenure inference** — Plan B of the original Layer 2 design. The Trail view will surface conflicts visually; tenure resolution is the Plan B answer.
- **Modifying Layer 1 silos** — phone, address, contact silo pages are linked from the Anchors tab but not modified.
- **Modifying the existing Map, Properties, Groups, Contacts, Transactions, Pipeline pages** — strict Layer 2 sandbox.

## Success criteria

After all four sub-projects ship:

1. Pick any Confirmed group from the list. Within 5 minutes you can verify its core anchors and spot-check 5 attached parties without leaving the auto-group surface (click-throughs to Layer 1 silos count as "without leaving" — they're verification jumps, not work).
2. Look at any Probable group's "Why this tier" panel and understand exactly what's stopping it from being Confirmed.
3. The Graph view for a top-10 group renders in < 1s and is readable at a glance — anchor structure visible, party clusters visible, no hairball.
4. The Trail view surfaces at least one real conflict in the dataset (a party whose threads point at multiple groups) — discovered organically through navigation, not contrived.
5. The Tuning page enables a single-day algorithm tuning loop: see the confidence histogram → pick a threshold change → know which groups would flip tiers without re-running the build.

## Decomposition recap

- **Plan D — Detail-page redesign** (Overview / Anchors / Parties tabs + tab shell). Foundation for E and F.
- **Plan E — Graph view tab.** Independent after D.
- **Plan F — Trail view tab + entry from SourceViewerDrawer.** Independent after D.
- **Plan G — Tuning page + list-page filters.** Fully independent.

Each plan lands as a separate `docs/superpowers/plans/YYYY-MM-DD-...md` and ships under subagent-driven-development before the next is scoped.
