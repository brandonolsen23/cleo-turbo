# Clean / Determination Boundary

> **Scope spec, valid-within-scope under `data-doctrine.md` (the locked master).**
> Extends **D1** (the three buckets) by fixing where the Evidence/Interpretation cut
> falls *inside a single source record*. Proposes **D9** (below) for Brandon's
> approval; the master stays untouched until then. Empirical backing:
> `rt-compiled-field-disposition.md`. Altitude picture:
> `clean-vs-determination-boundary-flow.svg`. Where this touches the property/entity
> model it defers to `unified-property-model-plan.md` and `parcel-resolution-spec.md`.

## The boundary: a pure-function test

A field is **Evidence (clean)** only if it is a pure function of one source document:
same input, same output, forever, with no external data and no other record consulted.
If producing it needs a geocoder, a parcel file, a PIN-to-ARN cross-reference, the
brand registry, or another record, it is **Interpretation** and belongs in the
determination layer, never written back into the clean record.

This is D1's Evidence/Interpretation line drawn precisely. D1 named the buckets; it did
not say where the cut runs within a source projection. The test: could I produce this
field from this one document alone, with a rule that is always right? Yes = clean.
No = determination.

## Classify, don't determine, in clean

Clean may **classify** (what a datum *is*, by static rule on the record's own content:
this token is a postal code, this line is a legal description). Clean never
**determines** (what to conclude, where the answer can be wrong and needs a confidence:
is this ARN accurate given the acreage). Classification is definitional and
deterministic; determination is judgment. The address civic/legal/unit split is clean
if it is rule-based on the string; "which party token is the owner brand" is a
determination (it uses the brand registry).

## What this changes in practice

1. **Eviction.** Today's RT clean record violates D1: it embeds `parcel.resolved_arn`,
   `geocoded_coords.*`, and the `parcel.*` block, all geocoder/parcel-file outputs
   (Interpretation) sitting inside an Evidence projection. These move out of clean into
   determination outputs.
2. **Gather everything, decide nothing (in clean).** Clean carries every stated data
   point with multiplicity preserved: all property addresses + variations, all stated
   PINs, stated ARN when present, acreage, legal description. Nothing dropped, nothing
   chosen. A field with no declared home is a build-time failure.
3. **Determination is layered and append-only** (D1 Interpretation lifecycle):
   discover (geocode, PIN to ARN, ARN to geometry/acreage) then reconcile (dedupe ARNs,
   stated-vs-geocoded ARN, sum-of-parcel-acres vs stated acres) then resolve entities
   (PRO_ per distinct ARN; GRP_/CON_ fuzzy). Hard evidence first; fuzzy calls build on
   it. Determinations never mutate clean; they append and replay on rebuild.
4. **Provenance on every fact** (D8): stated ARN and geocoded ARN coexist as two tagged
   facts, never merged at compile.

## Why it matters (evidence)

From `rt-compiled-field-disposition.md` (RT corpus, n ~= 126k): 24% of RT records carry
more than one property address (max 14) and the compiler silently drops all but the
first; PINs are stated on 100% of records, ARNs on ~62%; where both a stated and a
geocoded ARN exist they **disagree 21% of the time**. The stated/geocoded conflict and
the acreage cross-check (stated `site.acreage` vs summed parcel geometry) are the
reconciliation signals that only exist if clean carries the raw facts and determination
is a separate, later, append-only stage.

---

## Proposed amendment to `data-doctrine.md` (for Brandon's approval)

**Add to Section 1 (Decisions):**

| # | Decision | Rationale |
|---|---|---|
| D9 | **The Evidence/Interpretation cut runs inside a single source record, and it is a pure-function test.** A field is Evidence (clean) only if it is a pure function of one source document: same input, same output, no external data (geocoder, parcel file, PIN-to-ARN cross-reference, brand registry) and no other record consulted. Anything requiring those is Interpretation and lives in the determination layer, never written back into clean. Corollary: clean *classifies* (what a datum is, by static rule) but never *determines* (what to conclude, which can be wrong). | D1 named the buckets but not where the Evidence/Interpretation line falls within a source projection. RT clean records currently violate D1 by embedding `parcel.resolved_arn` and `geocoded_coords` (Interpretation) beside stated `site.pin`/`legal`/`acreage` (Evidence). The pure-function test makes the cut mechanical: clean becomes rebuildable and cacheable, resolution becomes an append-only determination re-runnable without re-parsing. Backing: `rt-compiled-field-disposition.md`. |

**Add to Section 8.2 (docs/):**

| Document | Disposition |
|---|---|
| `clean-vs-determination-boundary.md`, `rt-compiled-field-disposition.md` | Valid-within-scope. D9's corollary spec plus the field-level disposition ledger it rests on. Reconcile with `field-contract.md` and `parcel-resolution-spec.md` on next pass. |

---

*The entity model discussed alongside this (PRO_ = one per distinct ARN;
transaction-to-ARN many-to-many replacing the scalar link) is NOT asserted here as new
doctrine. It must be reconciled with `unified-property-model-plan.md` and
`parcel-resolution-spec.md` before it earns a decision.*
