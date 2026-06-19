# Brand → Parcel Accuracy: Rooftop Anchoring + Verification

> Goal: place major retail brands on the **correct parcel with ~99% accuracy**, and make every
> RT/GW→parcel join a recorded, checkable assertion so wrong placements are caught, not shipped.
> Grounded in the live DB (June 2026) and code (`path:line` from repo root). Companion to
> `ingestion-audit-and-parcel-anchor.md`.

## 1. The problem, precisely

When an RT transaction has only a street address (no reliable ARN), the pipeline geocodes the
address and assigns the parcel containing that point. For commercial addresses this often lands on
the **neighbouring** parcel, so the transaction is attributed to the wrong property/brand (e.g. a
Shoppers Drug Mart sale reads as a Rona sale). A mis-placed dot doesn't just move on the map — it
mislabels the *deal*, which corrupts ownership, brand portfolios, and every insight built on them.

## 2. Ground truth — the St. Thomas case (live data)

| Record | Address | ARN | Property | method | Coord source |
|---|---|---|---|---|---|
| RT156261 (SDM sale) | 107 Edward | …453 | PRO_23013 | `spatial_geocode` | interpolated |
| OSM_11711 Shoppers Drug Mart | 107 Edward | …453 | PRO_23013 | `spatial_osm` | **rooftop** |
| RT63278 (sale) | 101 Edward | …450 | PRO_62143 | `spatial_geocode` | interpolated |
| OSM_35553 Rona | 101 Edward | …450 | PRO_62143 | `spatial_osm` | **rooftop** |

Findings:
- The pair is **currently correct** — the SDM transaction and the SDM POI are co-located on
  PRO_23013; Rona on PRO_62143. (Likely nudged right by a prior re-resolve.)
- But both transactions rode the **fragile `spatial_geocode` path** (interpolated, conf 0.70–0.85,
  not PIP-verified). They're right by luck, not by anchor.
- PRO_23013 is typed **"office"** despite hosting Shoppers + Canada Post POIs — the classifier
  ignores POI brand/category.
- The OSM POIs are rooftop-accurate and already correctly parcel-resolved from their own
  coordinate. **They are the asset we should be anchoring to.**

## 3. Dataset sizing (live)

Transactions by `parcel_method` (of 124,544):

| method | count | % | quality |
|---|---|---|---|
| verified | 47,396 | 38.1% | strong (ARN+geocode agree) |
| **spatial_geocode** | **35,666** | **28.6%** | **fragile — interpolated, neighbour-prone** |
| (unresolved) | 22,891 | 18.4% | no parcel |
| arn_only | 10,178 | 8.2% | ARN trusted, no spatial check |
| spatial_consensus | 5,403 | 4.3% | strong (≥2 variants agree) |
| spatial_override | 3,010 | 2.4% | geocode overrode ARN |

OSM assets: **50,778 POIs, 1,608 distinct brands, on 16,063 properties** — rooftop, already
parcel-resolved. **3,803** transactions sit on a POI-bearing property yet used `spatial_geocode`
— the immediate, checkable target set for both the fix and the verification layer.

## 4. Root cause (code-confirmed)

1. **Interpolated geocodes.** A `StreetAddress` (non-rooftop) point can fall on a lot line and
   PIP into the neighbour. chain.py accepts it at conf 0.70 (`chain.py:199`) and resolves
   `spatial_geocode` with no further check (`chain.py:364-382`).
2. **Nearest-centroid fallback, unflagged.** `agmaps.query_by_point` (`agmaps.py:149-198`) expands
   the search box up to ~135 m and, failing true point-in-polygon containment, returns the parcel
   with the **nearest centroid** — or finally `features[0]`. It returns a normal parcel dict, so
   chain.py **cannot tell a true containment hit from a guess**.
3. **No parcel self-check.** Nothing compares the requested address (or brand) against the parcel
   it landed on. The AgMaps parcel layer exposes only ARN + PIN + geometry (no civic address), and
   the geocoder's `comp_score`/parsed components are captured then discarded (`types.py:88-98`).
   The only distance gate (`chain.py:398`) lives in the ARN-only branch and uses a 500 m threshold
   — useless against a neighbour 30 m away.
4. **RT carries no coordinate.** The RT adapter hardcodes `coords=None` (`adapter.py:100`), so the
   resolver's high-confidence **coordinate-PIP step never fires for RT** — even though the rooftop
   coordinate exists in OSM.
5. **RT↔OSM only meet by shared ARN.** The compiler attaches a POI to a property purely by ARN
   (`writer.py:891-894`). If RT resolves to the wrong ARN and the POI to the right one, the brand's
   transaction and the brand's POI live on different properties and never reconcile.

## 5. The architecture — rooftop anchor + verifiable joins

Two complementary moves. The first fixes placement; the second makes correctness *provable*.

### 5A. OSM rooftop coordinate as the authoritative spatial anchor for branded retail
The resolver already ranks a coordinate-PIP hit as **Priority 1**, above address-geocode and ARN
(`chain.py:317-326`, conf 0.90 for OSM-sourced coords). The only missing piece is *feeding RT a
coordinate*. Plan:
- Build a **brand → POI spatial index** from the OSM corpus (brand, rooftop lat/lng, city, resolved
  ARN) and thread it into `ResolverContext`, exactly parallel to the existing `pin_to_arn` bridge
  (`chain.py:105-115`).
- When an RT record's brand (normalized from its four branded fields via
  `cleo/atoms/normalize.normalize_brand`) matches a POI brand **and** that POI is within a tight
  radius of the RT address's geocoded vicinity (reuse `_haversine_m`, `chain.py:38`), set
  `ResolutionInput.coords` to the POI's rooftop point.
- The existing Step-4 coords-PIP + Step-6 PIP-verify then place the transaction on the **POI's
  parcel** deterministically. Because RT and the POI now share the ARN, the compiler reunites the
  brand's sale and the brand's POI on one property (`writer.py:891-894`).
- Disambiguate "which Shoppers" by requiring brand match **and** proximity (nearest brand-matching
  POI to the geocoded point, within e.g. ≤150 m) **and** street-name agreement.

This makes branded placement track OSM's rooftop accuracy — the 99% target — for every brand that
has a POI (1,608 brands / 16k properties today, and growing as OSM is refreshed).

### 5B. Verification layer — every join is a checkable assertion
Independent of the anchor, surface and persist provenance so wrong joins are caught:
- **Return a containment flag** from `query_by_point` (`true PIP` vs `nearest_centroid` vs
  `features[0]`), so the resolver can demote/flag fallback guesses instead of trusting them.
- **Persist provenance** on `transactions` (and GW): `parcel_confidence`, `pip_verified`,
  `geocode_addr_type` (PointAddress vs StreetAddress), `parcel_assignment` (contained vs fallback).
  Today only `parcel_method` survives.
- **Brand↔parcel-POI agreement check (the St. Thomas detector).** If an RT transaction's brand is
  "Shoppers" but the parcel it landed on hosts only a "Rona" POI, that is a high-signal mismatch →
  write it to the `issues` table (category `rt_property_mismatch`, already defined in migration 036)
  and show it in the Data Quality page. This single check would have flagged the exact error you
  describe.
- **Confidence gate.** Treat `arn_only` (0.50) and low geocode joins differently from `verified`
  (0.95) in the UI — let the map filter/flag by join quality.

### 5C. Bonus — brand-aware property typing
A property hosting an SDM/Canada Post POI is retail/pharmacy, not "office." Use POI brand/category
to set/correct `primary_property_type` during compile. (PRO_23013 is mislabeled today.)

## 6. Why this fits the parcel-anchor model
The Parcel stays the anchor (§ `ingestion-audit-and-parcel-anchor.md`). 5A changes *which* parcel a
branded transaction binds to (the correct, rooftop-confirmed one); 5B records *why* and flags when
it's uncertain. Re-resolving is safe because it only re-points `transaction → parcel`; CRM stays on
the parcel. The brand↔POI agreement check becomes a standing data-quality monitor, so accuracy is
measured continuously, not discovered by accident.

## 7. Staged plan (approve-before-code; pipeline changes need sign-off)
1. **Verification first (non-breaking):** add the containment flag + persisted provenance + the
   brand↔parcel-POI agreement check writing to `issues`. Immediately quantifies how many of the
   35,666 `spatial_geocode` (and the 3,803 POI-bearing) joins are actually wrong. Zero behaviour
   change — pure visibility.
2. **Rooftop anchoring:** build the brand→POI index, thread it into `ResolverContext`, populate RT
   `coords` on brand+proximity match, let Step-4 place them. Re-resolve the affected set.
3. **Brand-aware typing** during compile.
4. **Measure:** re-run the agreement check; target ≥99% brand↔parcel agreement on POI-backed
   transactions, and drive down unflagged `spatial_geocode` joins.

Recommended order: 1 → 2 → 3, because step 1 turns "I think things land wrong" into an exact,
auditable list and a before/after metric for step 2.
