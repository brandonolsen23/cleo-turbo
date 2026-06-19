# Parcel Resolution & Verification — Consolidated Build Spec

> Single authoritative spec for how RT/GW/OSM data is linked to the correct parcel, verified,
> and safely re-processed. Supersedes the brand-agreement idea in `brand-parcel-accuracy.md`
> (RT rarely carries a brand, so that check was circular). Builds on
> `ingestion-audit-and-parcel-anchor.md`. Grounded in code + live data (June 2026).
> No pipeline code is written until each stage below is approved.

## 1. The principle

The **Parcel (ARN) is the stable anchor.** RT transactions, GW assessments, OSM POIs, and the CRM
all attach to it. Resolution (address/PIN/ARN → parcel) is a **cached, re-runnable candidate
layer** whose results are **promoted into the anchor only when they're better** — never blindly
overwritten. Every link is a **recorded, checkable assertion** with a confidence tier, so wrong
placements are flagged, not silently shipped. Linking uses **address/PIN identity**, never brand
(brand is *discovered* from POIs after the parcel is correct).

## 2. Measured evidence (why this works)

A 200-record sample of the "fragile" `spatial_geocode` bucket, re-geocoded through the free Ontario
locator capturing the `Loc_name` field we currently discard:

| `Loc_name` bucket | share | meaning |
|---|---|---|
| PARCEL (PCCF/MUN) | **73.5%** | matched the parcel's own address point — authoritative; **134/147 also pass strict field-match** (the other 13 are normalization misses like "Mccordick" vs "McCordick") |
| ROADS (interpolated) | 22.0% | street-range interpolation (no house number) — the real neighbour-landing risk |
| STREET (centroid) | 3.0% | street centroid only |
| NO_RESULT | 1.5% | no match |

Dataset context: 124,544 transactions — 38% `verified`, **28.6% `spatial_geocode` (35,666)**, 18%
unresolved, 8% `arn_only`. Of unresolved, **13,819 carry a PIN**. OSM: 50,778 POIs / 1,608 brands /
16,063 properties (rooftop, already parcel-resolved). Parcel cache: 124,430 geometries.

**Implication:** ~73% of the "fragile" bucket (~26,000 transactions) are recoverable to high
confidence just by capturing the signal the geocoder already returns; only ~25% (~9,000) are
genuinely interpolated and need extra signals or review.

## 3. Data model — Parcel as a first-class entity

Today `properties` fuses parcel identity (ARN+geometry) with enrichment (owner, sale, type). Split:

- **`parcels`** — authoritative, keyed by ARN: geometry, centroid, source, geometry version,
  resolution provenance. Stable `PARC_`/ARN id. This is THE anchor.
- **`properties`** — derived *enrichment* view over a parcel (current owner, latest sale, type,
  building size). Rebuilds freely without touching parcel identity or CRM.
- **`transactions`, `gw_assessments`, `pois`, and CRM** (deals, sell_opportunities,
  property_enrichment, activities, stars, list_members) reference **`parcel_id`**.

Stable ids persist via `id_mappings` (ARN → id), never dropped. CRM survives every rebuild because
it anchors to the parcel, not to a transaction or a derived row.

## 4. Resolution as a cached candidate layer

Three caches make re-processing cheap and deterministic:
- **Parcel cache** (exists): ARN → geometry (`clean-data/parcels/`, 124,430 entries).
- **Reverse-geocode cache** (exists): coords → address (`clean-data/reverse_geocode/`).
- **Forward-geocode cache (NEW):** normalized address → full geocoder result, including the fields
  we currently discard: `loc_name`, `addr_type`, `score`, `comp_score`, and parsed
  `house/street_name/suf_type/city`. With this, a re-run reuses geocodes and only geocodes new or
  changed addresses (or on deliberate invalidation, e.g. switching geocoders). **You do not need to
  re-geocode on every run.**

The Ontario locator returns parsed address components and a `Loc_name` that already distinguishes a
parcel-level match (`PARCEL_PCCF`/`PARCEL_MUN`) from an interpolated one (`Roads_Locator`,
`STREET_CITY`). The current resolver collapses everything to `addr_type`+`score` and drops the rest.
**Capture and use it.**

## 5. The signal hierarchy & verification tiers

Each signal independently proposes a candidate ARN; trust comes from **corroboration between
independent signals**, with a deterministic tie-break — not a strict precedence ladder (so a wrong
PIN can't outrank a correct geocode). Signals, by independent strength:

1. **PIN → ARN** (corroborating vote ONLY — see Appendix A). Built from GW data; ~0% coverage of the unresolved set and many-to-many — but
   PINs are sometimes wrong, so it's a vote, not gospel.
2. **ARN on the RT record** (correlated with PIN — same source; don't double-count).
3. **Address field-match → ARN** via the locator's `PARCEL_*` result (see §6).
4. **Geocoded point inside a parcel polygon** (PIP-contained) — geometric confirmation.
5. **OSM POI / building footprint** at the same address — independent rooftop corroboration.

**Tiers (what publishes vs what's quarantined):**
- **Verified** — ≥2 independent signals agree AND a trusted point is PIP-contained in that parcel
  (e.g., `Loc_name=PARCEL_*` + field-match + containment; or PIN/ARN bridge + containment).
- **Probable** — one strong signal, no disagreement (contained `PointAddress`, or an address-field
  match) — published, flagged as single-source.
- **Review** — `Roads_Locator`/`STREET_*` interpolation, or not PIP-contained, or signals conflict.
  **Never auto-placed on the map.** Goes to the review queue.

**Kill the silent nearest-centroid fallback** in `query_by_point` (it currently returns a neighbour
with no flag). Containment is binary evidence; a non-contained point is Review, not a guess.

## 6. Field matching (your 2025 plan — included)

The locator already returns parsed components, so matching is `RT(107 / Edward / St)` vs
`geocoder(house=107 / street_name=Edward / suf_type=Street)` + city. Rules:
- Canonicalize both sides through `cleo/address` (suffix St↔Street, directionals, ordinals,
  Mc/Mac, saints) before comparing — this closes the 13/147 normalization gap seen in the sample.
- A **match** requires house number equal AND street-name equal (post-canonical) AND city equal.
- Unit/suite handled separately; dense multi-parcel addresses (towers, plazas, condo PINs) resolve
  to the building/parcel level and mark unit-level as Review rather than inventing precision.
- The parcel polygon layer itself carries **no** civic address (only ARN+PIN+geometry), so the
  "parcel address" for matching comes from the locator's `PARCEL_*` result (and, where available,
  GW/MPAC). That's why field-match pairs with PIP-containment.

## 7. Re-processing safely — promote on improvement

The answer to "is everything fine if I re-run?": **a re-run can only improve or hold, never churn.**
- Resolution writes **candidate** parcel assignments with `{parcel_id, tier, confidence, signals,
  version}` — it does **not** overwrite the canonical link in place.
- A **promotion** step diffs candidate vs current canonical per record and promotes only when the
  new tier/confidence is ≥ current, logging `old → new` for audit.
- Stable keys already prevent duplication (properties UNIQUE on ARN, contacts by fingerprint,
  groups by normalized name, transactions by source_id).
- **CRM-safe ARN change:** if a re-resolve moves a transaction to a corrected parcel, that's a clean
  re-point of `transaction.parcel_id`. If a parcel a user had CRM on turns out wrong, it's **flagged
  for review / offered for migration**, never silently orphaned (the failure mode that exists today).

## 8. Verification surface (make accuracy visible)

- **Persist provenance** on transactions/parcels: `loc_name`, `addr_type`, `score`,
  `parcel_confidence`, `pip_verified`, `parcel_assignment` (contained vs fallback), `tier`.
- **Write failed assertions to the `issues` table** (categories already exist: `rt_property_mismatch`,
  `parcel_geometry_wrong`) and surface in the Data Quality page as a **review queue**.
- **Metrics:** track tier distribution over time; target ≥99% Verified+Probable on POI/PIN-backed
  records; drive down un-reviewed Review-tier joins. This converts "I think things land wrong" into a
  measured, before/after number.

## 9. Automation (keep the app current, decoupled)

- **RT collection — cloud (Apify), collect-only:** scheduled httpx job — log in, date-windowed
  search, "is this RT ID new?" (manifest in cloud storage → no duplication), save HTML. No browser,
  no parsing, no DB. Runs even when the laptop is closed.
- **GW collection — rebuilt MV3 Chrome extension:** always-on, saves the rendered GW DOM as
  `geowarehouse-<ISO>.html` into the watch folder (exact pipeline contract — not a PDF). GW also
  feeds the PIN→ARN and address→ARN authorities that strengthen RT linking.
- **Local ingestion — triggered by new saves:** pull → parse → classify → normalize → resolve
  (cached) → **verify/tier** → **promote** → rebuild. Collection never touches the DB; ingestion
  never scrapes; re-resolution is always safe.

## 10. Staged build plan (approve-before-code)

1. **Verification capture (non-breaking):** add the forward-geocode cache; capture `Loc_name` +
   parsed fields; compute field-match + PIP-containment; persist provenance + tier; write Review
   items to `issues`. Re-geocode pass (free) to reclassify the 35,666 — expected ~73% → Verified,
   ~25% → Review. Pure visibility; no placement changes yet.
2. **First-class `parcels` table:** introduce it, repoint transactions/GW/POI/CRM to `parcel_id`,
   make `properties` a derived enrichment view.
3. **Promote-on-improvement re-processing:** candidate links + diff + promote + CRM-safe ARN change.
4. **Corroboration upgrades:** PIN/ARN authority expansion (via GW), OSM/building rooftop
   corroboration for the ~25% interpolated bucket; brand-aware property typing from POIs.
5. **Automation:** Apify collector + GW extension wired to the triggered local ingest.

Suggested order: 1 → 2 → 3 → 4 → 5. Step 1 is non-breaking, immediately useful, and turns the
accuracy problem into a measured one before any structural change.

## Appendix A — Scope, the PIN→ARN bridge, and re-geocode sizing

Resolution + verification apply to **every transaction (124,544), not a retail subset.** The
35,666 `spatial_geocode` figure is all-asset-class (industrial, land, office, multifamily, retail).
Cross-asset coverage is the point — an owner's industrial portfolio (e.g. DH Management) matters as
much as their retail, and a misplaced industrial sale corrupts portfolio analysis just as badly.
Only the **OSM rooftop corroboration** leg skews retail; the `Loc_name` + field-match +
point-in-polygon verification is asset-class-agnostic.

### The PIN→ARN bridge is NOT a resolver (measured)
- Built only from captured GW data: **760 distinct PINs**.
- Of the **13,819** unresolved-with-PIN transactions, **0** have a PIN present in the bridge source
  → it can resolve **none** of them.
- Even within its 760 PINs, **20 map to >1 ARN** (and 20 ARNs cover >1 PIN); across all transactions
  **497 PINs** appear with >1 ARN. PIN (Land Registry) and ARN (assessment roll) are genuinely
  **many-to-many** (condos, severances, consolidations), so a first-wins `pin→arn` dict is unsound.
- Therefore PIN→ARN is a **corroborating vote and a bad-PIN detector only** — flag it when it
  disagrees with a contained, field-matched geocode; never resolve from it alone, never skip
  geocoding because of it.

### Re-geocode workload — geocode everything once (no batch, no shortcut)

Workload is driven by **distinct addresses** (the forward-geocode cache dedups), not rows:

| current method | rows | distinct addresses |
|---|---|---|
| verified | 47,396 | 37,822 |
| spatial_geocode | 35,666 | 28,302 |
| unresolved | 22,891 | 17,358 |
| arn_only | 10,178 | 9,106 |
| spatial_consensus | 5,403 | 4,680 |
| spatial_override | 3,010 | 2,711 |
| **total** | **124,544** | **95,444** |

- **Geocode all 95,444 distinct addresses once** — cached (~1.5 days, free, resumable), then every
  future run is instant from cache. No PIN shortcut, no partial batch.
- Every transaction across every asset class then carries uniform, provenance-tagged, corroborated
  placement (Loc_name + field-match + PIP containment), with PIN/ARN as cross-checks that flag
  disagreements rather than silently deciding.
