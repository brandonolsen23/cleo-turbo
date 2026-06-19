# Ingestion Audit + Parcel-as-Anchor Design

> Audit of the RT pipeline `parse → classify → normalize → resolve → rebuild`, evaluated
> against the goal: **the Parcel is the stable anchor; RT records, GW records, and the CRM all
> attach to it; improving/re-resolving ingestion must never break the system.** Grounded in the
> code (June 2026), `path:line` relative to repo root. Companion to `architecture-deep-dive.md`.

## 0. Executive summary

Your mental model is already ~80% implemented — implicitly. `properties.id` (a `PRO_` id) is
keyed by `arn UNIQUE NOT NULL` (`schema.py:22-23`): **one property row = one parcel.** That id is
stable across rebuilds because `id_mappings` maps ARN → `PRO_` and is never dropped
(`schema.py:636`). The CRM already anchors to it: `deals.property_id`, `sell_opportunities.property_id`,
`property_enrichment.property_id`, `activities.property_id`, `user_stars(entity_type='property')`,
and `list_members` all reference `properties(id)` (`schema.py:402,550,592,616,435,427`).

So "Parcel is the anchor" is real today. The problems you've felt come from four gaps, all fixable:

1. **The parcel is not a first-class entity** — it's fused into `properties`, which mixes parcel
   *identity* (ARN + geometry) with *derived enrichment* (owner, last sale, type, building size).
   A parcel only exists if some RT/GW record created its property row.
2. **Re-resolution can orphan the CRM.** `PRO_` is stable only while a parcel's ARN stays the
   same. The entire point of re-resolving is to *correct* a wrong ARN — and when a record moves
   from ARN A to ARN B, a property is only rebuilt for ARNs present in the new compile. CRM
   attached to the old (wrong) parcel can dangle. This is the single biggest threat to your
   "improve without breaking" goal (detail in §4).
3. **Join provenance is computed and thrown away.** The resolver produces `method`, `confidence`,
   and `pip_verified` for every join, but RT's compile keeps only `method`
   (`engines/rt/compile.py:108-120`) and the schema has no `confidence`/`pip_verified` column
   (`schema.py:51-97`). You literally cannot ask "show me joins that didn't verify." That blocks
   "clean up and verify data well."
4. **GW trusts its ARN with zero verification** and overwrites the owner; the GW watcher and the
   compiler write GW data with different rules. So GW is the most likely source of a wrong-parcel
   join, and it's the least checked (§3.4, §5).

The good news: the schema already anticipates this. Migration 019 calls `properties.id`
"parcel-level identity," and the `issues` table (migration 036) already defines categories
`rt_property_mismatch`, `parcel_geometry_wrong`, `parcel_mismatch`. The verification surface you
want was partly designed — just not wired.

## 1. Stage-by-stage audit

### parse (extract + assemble) — `engines/rt/run_pipeline.py`, `assembler.py`
Turns raw RT HTML (detail + export + results) into one assembled JSON per transaction. **Rigid
parts:** stable RT-ID keying; atomic writes; an address/price/date cross-check. **Fragile parts:**
the detail↔export↔results join is **positional** (`run_pipeline.py:110`) with an address fallback —
a misaligned page could mis-join silently. **Verifiability:** assembler sets `join_verified`, but
nothing downstream gates on it. *Recommendation: surface `join_verified=false` as a data-quality
issue rather than letting it pass.*

### classify — `engines/rt/classifier/`
Assigns property type / asset class. **Rule-based, not AI** (confirmed: zero Anthropic/OpenAI
calls anywhere in `engines/`). Deterministic and cheap. Low correctness risk; the main subtlety is
the long tail of free-text building-size units (handled in `building_size.py`). No parcel impact.

### normalize — `engines/rt/address_normalizer/` (shares `cleo/address/`)
Produces canonical display + geocodable address variants. This is the **input quality gate for
resolution** — the better the normalized address, the better the geocode. **Rigid:** single shared
formatter (`cleo/address/`) used by RT/GW/OSM, so address strings are consistent across sources
(important for cross-source agreement). **Verifiability:** normalization emits an `issues` list
(no_pin, no_arn, address_parse_failed) — currently informational.

### resolve — `cleo/resolver/chain.py` (RT only) — *the accuracy core*
Six steps: PIN→ARN bridge → ARN lookup (cache→AgMaps) → address geocode (all variants) →
coordinate PIP → cross-validation decision → PIP verify. **This is genuinely good** for RT:
multi-address consensus, a decision hierarchy, a >500 m centroid sanity check (`chain.py:398`), and
a point-in-polygon verify. **The problems are downstream of the decision:**
- PIP failure does **not** change the result — it only sets `pip_verified=False`, which is then
  discarded (`chain.py:436-438`).
- The spatial query has a **nearest-centroid fallback** that can return a *neighbouring* parcel
  when PIP never matches (`engines/rt/parcel_resolver/agmaps.py:185-198`), with no distance ceiling
  and no flag.
- The VERIFIED path skips the distance gate (only the ARN-only branch checks 500 m).
- **GW does not use this chain at all** (§3.4).

### rebuild — `cleo/compiler/writer.py` via `rebuild.py`
Drops the derived tables and rebuilds them from `clean-data/` + parcel links (6 passes). **Rigid &
correct for the anchor model:** CRM/system tables are never dropped; `PRO_/CON_/GRP_` ids are
re-derived from `id_mappings`, so a rebuild that doesn't change ARNs reproduces identical ids and
the CRM stays attached. **The fragility is re-resolution + ARN change** (§4), plus that GW arrives
through *two* code paths (compiler Pass 5 with COALESCE gap-fill vs the GW watcher's unconditional
overwrite, `engines/gw/watcher.py:213-225`) that can produce different rows for the same parcel.

## 2. What links to what today (the anchor map)

| Entity | Key | Anchored to parcel? |
|---|---|---|
| `properties` (= parcel) | `id=PRO_`, `arn UNIQUE` | **is** the parcel |
| `transactions` | `source_id` (RT id) | → `property_id` (parcel) via `resolved_arn` |
| `gw_assessments` / `gw_sales_history` | per parcel | → `property_id` via ARN |
| `pois` | OSM id | → `property_id` via ARN |
| CRM: deals, sell_opportunities, property_enrichment, activities, user_stars, list_members | own ids | → `properties(id)` (parcel) ✅ |
| CRM: buy_mandates, group/contact notes, group_contacts | own ids | → contacts/groups (people, not parcels) |
| stable-id store | `id_mappings(entity_type, anchor_key→entity_id)` | ARN → `PRO_` (never dropped) |

**Reading:** RT, GW, OSM, and the property-side CRM already converge on `properties(id)` = the
parcel. The anchor exists; it's just not *named* as a parcel and not *decoupled* from enrichment.

## 3. Where "wrong parcel" comes from (the verifiable pieces, and what's missing)

Each join should be a recorded, checkable assertion. Today most are computed and discarded.

| Assertion (a "verifiable piece") | Enforced today? | Where it should live |
|---|---|---|
| Resolved ARN exists as a real parcel | RT: yes (resolution requires it). GW: **no** | parcel table |
| Geocoded address within 500 m of ARN centroid | only in ARN-only branch (`chain.py:398`) | per-join provenance |
| Chosen point is inside the chosen parcel (PIP) | computed then **discarded** | `transactions.pip_verified` (new) |
| ≥2 RT address variants agree | yes (`chain.py:478`) | provenance (`method=spatial_consensus`) |
| One PIN → exactly one ARN | **no** (first-wins, `pin_bridge.py:42-46`) | flag to `issues` |
| Spatial result wasn't a nearest-centroid guess | **no** (`agmaps.py:185-198`) | flag to `issues` |
| **GW's ARN == the ARN RT resolved for the same address** | **no — nothing checks this** | `issues: rt_property_mismatch` |
| Join confidence ≥ threshold before it's trusted | **no** (0.40 join treated like 0.95) | `transactions.parcel_confidence` (new) |

### 3.4 GW is the weak link
GW resolves ARN-only — no geocode, no PIP, no cross-validation (`engines/gw/resolve_parcels.py:38-53`;
adapter sends `addresses=[], coords=None`). It then **overwrites** `current_owner_name` on whatever
property carries that ARN (`writer.py:1023-1026`). A mis-scraped or typo'd ARN in a GW report
silently attaches the wrong owner to the wrong parcel, and nothing catches it. For your core
scenario (one GW report + several RT transactions on one property), the RT side is multi-signal
verified; the GW side that overwrites the owner is unverified.

## 4. Re-resolution safety — the core of your concern

**Today it is safe *only if* ARNs don't change.** A rebuild with unchanged parcel links reproduces
identical `PRO_` ids and the CRM stays put. But re-resolving to *fix* a join changes an ARN, and:

- A property row is created only for ARNs present in the current compile (`writer.py:573-578`).
- If a transaction moves from wrong-ARN A to correct-ARN B and nothing else references A, property A
  is not rebuilt — but `id_mappings` still holds A→`PRO_(A)`, and any CRM rows on `PRO_(A)` now
  reference a parcel with no row. They dangle.

So the very operation you want to do safely (correct a parcel) is the one that can strand CRM.
**The fix is to make the Parcel first-class and give re-resolution an explicit re-point + remap
step** (§6, Stage B/D).

## 5. Provenance is the missing audit layer

The resolver emits a full signal trail (method, confidence, pip_verified, reason, signals), but:
RT compile keeps only `method` (`engines/rt/compile.py:108-120`); the DB stores only
`transactions.parcel_method` (`schema.py:76`) — **no confidence, no pip_verified**. The only
`confidence` column in the schema belongs to `discovery_evidence`, unrelated. Net: in the app you
cannot filter or audit joins by quality. Restoring this is the cheapest, highest-leverage,
non-breaking improvement.

## 6. Recommendation — a rigid, verifiable, re-resolve-safe pipeline

Staged so each step is shippable and the early ones are non-breaking. **No pipeline code until you
approve a stage.**

**Stage A — Provenance + verification surface (non-breaking, do first).**
Stop dropping `confidence`/`pip_verified`/`reason` at RT compile; add `parcel_confidence`,
`pip_verified`, `parcel_resolution_reason` columns to `transactions` (and GW). Add a verification
pass that writes failed assertions (PIP fail, nearest-centroid fallback, PIN→many-ARN, GW↔RT ARN
disagreement, confidence below threshold) into the existing `issues`/`data_issues` tables and
surfaces them in the Data Quality page. Outcome: every join becomes an auditable, filterable claim.
Nothing about the current join behaviour changes — you just gain x-ray vision.

**Stage B — Make the Parcel first-class.**
Introduce a `parcels` table keyed by ARN (authoritative geometry, centroid, source, resolution
provenance, a stable `PARC_`/ARN id). Repoint `transactions`, `gw_assessments`, `pois`, and the
property-side CRM to `parcel_id`. `properties` becomes a thin derived *enrichment* view over a
parcel (owner, last sale, type) — identity and enrichment cleanly separated. This is the structural
change that realizes your model and makes re-resolution a clean re-point of `transaction.parcel_id`.

**Stage C — GW parity + single write path.**
Route GW through the same resolver chain (geocode + PIP cross-validation), so a GW ARN is verified
against its address the way RT is, and record an explicit **GW↔RT agreement** check per parcel.
Collapse the GW watcher's incremental write and the compiler's Pass 5 into one code path (or make
the watcher write identical provenance + agreement flags) so a parcel's data never depends on which
path touched it last.

**Stage D — Re-resolution as a first-class, safe operation.**
A re-resolve compares old vs new `parcel_id` per record, re-points transactions to the corrected
parcel, and — when a parcel a user had CRM on turns out wrong — *flags it for review / offers a
migrate* rather than silently dangling. Because CRM anchors to the (now first-class) parcel, the
blast radius is contained and explicit.

## 7. Automation (keeping the app current)

Collection and ingestion stay **decoupled**, as you specified:

1. **RT collection (cloud, Apify):** a dumb, scheduled, httpx-only job — log in, date-windowed
   search, "is this RT ID new?", save HTML, done. No browser, no parsing, no DB. Manifest of known
   RT IDs in cloud storage guarantees no duplication. Runs even when your laptop is closed.
2. **GW collection (Chrome extension):** rebuild the always-on MV3 extension that saves the
   rendered GW DOM as `geowarehouse-<ISO>.html` into the watch folder (the pipeline's exact
   contract — *not* a PDF).
3. **Local ingestion (triggered by new saves):** pull new HTML → parse → classify → normalize →
   resolve → **verification gate** → rebuild. The verification gate (Stage A) decides what's
   trusted vs flagged, so the app stays current *and* you can see the quality of every new join.

The collectors never touch the DB; ingestion never scrapes. You can re-run ingestion / re-resolve
any time without re-collecting, and (after Stage B/D) without endangering the CRM.

## 8. Suggested order

A (provenance + verification — non-breaking, immediate value) → C (GW parity, the biggest accuracy
win) → B (first-class parcels, the structural unlock) → D (safe re-resolve). Automation (§7) can
proceed in parallel since collection is decoupled. Each is a separate, approve-before-code step.
