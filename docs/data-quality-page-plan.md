# Stage 1.7 — Data Quality Page (Build Plan)

> The in-app home for reviewing data that needs a human eye: parcel-placement
> confidence (the new tiers) + the existing text/parsing scanner issues.
> Built to fix the two past failures, which are treated as **acceptance criteria**:
>   R1. Every flagged item is ONE CLICK from the original source data.
>   R2. Plain-English context everywhere — usable cold after weeks away.
> Read-only and non-breaking. Frontend uses the Cleo Turbo design system
> (Radix jade/slate, existing component patterns).

## 0. Acceptance criteria (must hold before "done")
- **R1 — source linkage:** every Review row links to (a) the raw Realtrack HTML,
  (b) the pipeline trace (parse→classify→normalize→resolve), (c) the parcel on the
  map with RT address vs resolved-parcel address side by side. No dead ends.
- **R2 — plain English:** an "i" tooltip on every tier, metric, and category;
  a per-row reason written as a sentence (not a code); a persistent "How this page
  works" panel; a glossary. A cold reader understands it without prior context.
- tsc clean; matches design system; degrades gracefully before the rebuild
  populates tier columns (shows "no data yet", never errors).

## 1. Data sources
- **Tiers + review queue:** the new `transactions` columns from Stage 1 —
  `parcel_tier`, `parcel_loc_name`, `parcel_addr_type`, `parcel_geocode_score`,
  `parcel_field_match`, `parcel_containment`, `parcel_confidence`, `pip_verified`,
  plus existing `parcel_method`, `display_address`, `arn`, `property_id`.
  (Populated after the full re-geocode + DB rebuild; page handles empty state.)
- **Text/parsing issues:** existing `data_issues` table via the current scanner.
- **Source links reuse existing surfaces** (no new viewers built):
  - raw HTML: `GET /api/transactions/{source_id}/html`
  - pipeline trace: `/pipeline/trace/{rt_id}` (page) / `GET /api/pipeline/trace/{rt_id}`
  - map/parcel: `/properties/{property_id}` (PropertyDetailPage, has the parcel map)

## 2. Backend (cleo/web/routes/data_quality.py — extend, additive)
- **GET `/api/data-quality/tier-summary`** → counts per tier
  (`verified`/`probable`/`review`) + totals, for the scoreboard.
- **GET `/api/data-quality/review-queue`** → paginated transactions where
  `parcel_tier='review'`. Each row returns: source_id, display_address, city, arn,
  property_id, parcel_method, loc_name, containment, confidence, field_match,
  the resolved parcel's display_address (join on properties), and a generated
  **plain-English `reason`** (see §4). Filters: by reason category, by method.
- **Plain-English reason generator** (small pure helper, unit-tested): maps
  (method, loc_name, containment, field_match, pip_verified) → one sentence.
- All endpoints `get_current_user`-gated, raw SQL, browse shape
  `{results,total,page,per_page,pages}`. No writes.

## 3. Frontend (frontend/src/pages/DataQualityPage.tsx — extend)
Sections, top to bottom:
1. **Explainer panel** (collapsible, persisted open/closed in localStorage):
   what this page is, that flags ≠ broken, and the 3-step workflow
   (look at the queue → open the source/trace → confirm or fix).
2. **Tier scoreboard** — Verified / Probable / Review counts as cards, each with
   an "i" defining it in plain English; Review card is the call-to-action.
3. **Review queue** — table (one row per uncertain join):
   `RT id · address · what we think (resolved parcel addr/ARN) · plain-English
   reason · [View source HTML] [Trace] [View on map]`. Sortable; filter by reason.
   Confidence / loc_name / containment shown as small labelled chips, each "i"-explained.
4. **Text/parsing issues** — the existing scanner issues, kept, each row with an
   "i" explaining the rule and a "View source HTML" link.
5. **Glossary** (bottom): tier, containment, field-match, loc_name, PARCEL_PCCF/MUN,
   PointAddress vs StreetAddress — plain-English, 1–2 lines each.
- **New reusable `InfoTip` component** (`components/ui/InfoTip.tsx`): a Phosphor
  `Info` icon with a Radix tooltip/popover; used everywhere above. Single source
  of the definition strings (a `dataQualityGlossary.ts` content file) so the
  scoreboard "i", the chips, and the glossary all read from one place.
- Types added to `src/types/index.ts`; data via `fetchApi`.

## 4. The "i" / plain-English content (drafted, in one content file)
Examples (final copy lives in `dataQualityGlossary.ts`):
- **Verified:** "Address matched a parcel's own address point and the location sits
  inside that parcel — high confidence this is the right parcel."
- **Probable:** "Rooftop-quality match inside a parcel, but without a full
  parcel-level address match — very likely right, worth a glance."
- **Review:** "The point wasn't confirmed inside the parcel, the match was
  interpolated along a street, or signals disagreed — most likely to be on the
  wrong (often neighbouring) parcel. Check these."
- **containment=nearest_centroid:** "We couldn't confirm the point was inside any
  parcel, so we picked the closest one — a guess, not a containment match."
- per-row reason examples: "Geocoder interpolated this along the street instead of
  pinning a rooftop, so it may sit on a neighbouring lot." / "Resolved only by ARN,
  with no independent location check."

## 5. Verification
- `cd frontend && npx tsc` clean.
- Screenshot the page (via the running frontend) and read every "i".
- Click-through: from a Review row, open source HTML, trace, and map — confirm all
  three resolve for a real record.
- Cold-read check: confirm the explainer + glossary make the workflow clear with no
  outside context.
- Backend: unit-test the reason generator; curl the two endpoints.

## 6. Build order
Backend reason-helper + endpoints → InfoTip + glossary content file → scoreboard →
review queue table + source links → fold in existing scanner issues + explainer +
glossary → tsc + screenshot + click-through. Each step committed on
`feat/stage1-verification`.

## 7. Out of scope (later)
- Editing/correcting a placement from the page (Stage 3/4 — promote/remap).
- The map overlay of RT-pin vs parcel as a bespoke view (link to existing map first;
  bespoke overlay only if the side-by-side addresses aren't enough).

## 8. R3 — Field-source provenance (added requirement)

**Every value the page displays must declare WHERE it came from**, because a real
class of bug is the app comparing/showing the wrong data layer. This amends §0
(new acceptance criterion R3) and §4 (the "i"/glossary content).

- **R3 acceptance:** each displayed field carries an "i" (or a small source chip)
  naming its source layer, and the glossary explains the layers + how to trace a
  value back to the original Realtrack HTML.
- **Source layers to label (the vocabulary):**
  - `RT HTML` — the original scraped Realtrack detail/export page (ground truth).
  - `RT clean record` — `clean-data/rt/{id}.json` (parsed/normalized from the HTML).
  - `transactions (DB)` — the compiled row the app reads (derived from the clean record).
  - `resolver` — Ontario geocoder + AgMaps PIP (produces arn, tier, containment,
    loc_name, field_match, confidence).
  - `property (DB)` — the parcel-level enrichment row; **address here may be RT- or
    GW-sourced** (compiler COALESCE) — call that out explicitly.
  - `GeoWarehouse` / `AgMaps parcel` where relevant.
- **Per-field mapping shown via "i" (examples):**
  - displayed RT address → "`transactions.display_address` ← RT clean record ← RT HTML
    (export/detail address)."
  - resolved ARN → "`transactions.arn` = resolver's resolved_arn (geocode → AgMaps
    point-in-polygon, or ARN/PIN bridge) — NOT from the RT HTML."
  - tier / containment / loc_name / confidence → "produced by the resolver
    (Ontario geocoder + AgMaps), not present in the source HTML."
  - resolved-parcel address (the 'what we think' column) → "`properties.display_address`
    — may be RT- or GW-sourced; compare against the RT address and the HTML."
- **Implementation:** the single glossary content file (`dataQualityGlossary.ts`)
  gains a `source` field per term/column; the review-queue table renders a small
  source chip per column, and the "View source HTML" link is always adjacent so the
  displayed value can be checked against ground truth in one click.
