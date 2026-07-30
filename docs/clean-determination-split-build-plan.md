# Clean / Determination Split - Build Plan (RT)

> Scoped implementation plan for **D9** (see `clean-vs-determination-boundary.md`).
> Splits `engines/rt/compile.py` so the Clean Record contains only RT-derived data;
> parcel resolution and geocoding move to a separate determination artifact.
> Grounded in `engines/rt/compile.py` (read 2026-07-30). Behavior-preserving:
> the DB ends up with the same values, now provenance-tagged.

## The seam (verified in code)

`engines/rt/compile.py :: build_clean_record()` (lines 96-202) merges four inputs:
`classified` + `addresses` (both RT-derived) and `parcel_link` + `geocoded` (both
external). Only the latter two produce the blocks that violate D9. The stage already
writes per-record files to separate dirs (`pipeline/parcel_links/`, `pipeline/geocoded/`),
so the determination data already lives on disk apart from the RT parse - it is only
*merged* into the record at compile time.

## Eviction list (exact)

| block / field | current source | built at | disposition |
|---|---|---|---|
| `parcel` = {resolved_arn, method, reason, parcel_file, confidence, pip_verified, containment, loc_name, addr_type, geocode_score, field_match, tier} | `parcel_link` (`pipeline/parcel_links/`, the resolver) | compile.py:111-131, emitted :190 | **-> determination** |
| `geocoded_coords` = {lat, lng, relevance, place_name} | `geocoded` (`parcel_link.geocode` v2, or `pipeline/geocoded/` Mapbox) | compile.py:193, loaded :294-311 | **-> determination** |

**Stays in the Clean Record (all RT-derived):** `source_id`, `source`, `source_folder`,
`source_position`, `compiled_at`, `transaction`, `property` (normalized addresses),
`seller`, `buyer`, `site`, `consideration`, `broker`, `description`, `photos`.

**Critical detail - stated vs resolved:** `site.pin` and `site.arn` STAY (the RT's
*stated* identifiers, parsed by the addresses stage, no external lookup). Only
`parcel.resolved_arn` (the *resolved* one) evicts. After the split the clean record
carries the stated ARN; the determination layer carries the resolved ARN - the two
coexist as provenance-tagged facts (D8), never merged at parse time.

## Changes, by file

1. **`engines/rt/compile.py`** (becomes "assemble clean record"):
   - `build_clean_record()`: drop the `parcel_link` and `geocoded` params; delete the
     `parcel` block (111-131, 190) and the `geocoded_coords` key (193).
   - `run()`: stop loading `pipeline/parcel_links/` (278-281) and `pipeline/geocoded/`
     (292-311); stop the `with_parcel/without_parcel` stats (320-323).
   - `score_record()`: drop the +5 resolved-parcel term (68-70). Dedup already happens
     upstream in `dedup.py` (docstring), so the safety-net score no longer needs resolver
     output. Result: `clean-data/rt/*.json` is RT-only and pure - a pure function of the
     RT parse, independent of resolve.

2. **NEW determination step** (e.g. `engines/rt/determine.py`):
   - Reads `clean-data/rt/{RT_ID}.json` + `pipeline/parcel_links/` + `pipeline/geocoded/`.
   - Writes `determination/rt/{RT_ID}.json` = `{ parcel{...}, geocoded_coords{...} }`,
     keyed to `source_id`, each field tagged with method + confidence.
   - Resolver/candidate-layer internals are NOT redefined here - they are already speced
     in `parcel-resolution-spec.md`. This step only *lands* their output as a record.

3. **`cleo/compiler/writer.py` (Pass 3)** - the clean-data -> DB writer mapped by
   `rt-pipeline-audit.md`: read BOTH the clean record and the determination record; write
   the parcel/geocode columns tagged by origin (stated vs resolved). No new resolution
   logic; it changes where those columns are sourced.

4. **`engines/rt/process.py` STAGE_ORDER** - clean assembly no longer depends on resolve,
   so resolve + determine become an independent downstream pass. Aligns with the existing
   `--skip resolve` mode and improves incremental recompile (clean rarely changes;
   re-determine without re-parsing).

## Verification (per D6 - never at the DB level)

- Work on a `/tmp` copy of `cleo.db`.
- **Regression gate:** run the old path and the new path; diff the DB. Parcel/geocode
  values identical, now provenance-tagged. Zero change to any RT-derived column.
- **Field-reachability invariant** (from the disposition ledger): every RT-derived field
  has a home in the clean record; every evicted field has a home in the determination
  record; nothing is unaccounted for. Wire this as a test so a future schema change can't
  silently reintroduce a blend.

## Sequencing

- **This plan** = the eviction + determination artifact + DB-reads-both. Behavior-preserving.
- **Then (separate plans):** address classifier + `transaction_addresses` (fix the multi-
  address drop); `transaction`<->ARN many-to-many (retire the scalar link); reconciliation
  layer (stated vs resolved ARN, the 21% conflict; summed-vs-stated acreage).
- **Entity model** (PRO_/GRP_/CON_) -> `unified-property-model-plan.md`, not this plan.

## Relationship to existing docs (so this extends, not duplicates)

- **Extends:** `data-doctrine.md` D9 (proposed); `clean-vs-determination-boundary.md`
  (the principle); `field-contract.md` (defines what the clean record contains - this
  plan enforces where its output ends and determination begins).
- **Defers to:** `parcel-resolution-spec.md` (resolver = cached re-runnable candidate
  layer; its internals); `unified-property-model-plan.md` (entity model);
  `rt-compiled-field-disposition.md` (field-level disposition ledger + evidence).
- **Coordinates with:** `rt-pipeline-audit.md` (the clean-data -> DB write map, Pass 3);
  `incremental-recompile-plan.md` (recompile gating - the split improves it);
  `reprocess-plan.md` (stage reprocess - the split adds the determine boundary and
  enables re-determine without re-parse).
