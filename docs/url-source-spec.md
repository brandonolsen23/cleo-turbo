# URL Source Spec (reconciled M2 / Portfolio Capture)

**Status:** v1, 2026-07-17. Contract-aligned.
**Supersedes:** the "Extraction protocol" and per-property schema in `docs/portfolio-capture-build-plan.md` (M2), which predates the field contract.
**Depends on:** `docs/field-contract.md` (the buckets), `cleo/resolver` (address to ARN), `cleo/address` (Bucket C).

---

## 1. What it does

Paste an owner's website URL. Cleo crawls it, an AI extracts one **group** (e.g. Plaza REIT) and **many properties**, each property resolves to an ARN through the shared contract, and the results land in the master property list under that one group. Ownership that never traded through Realtrack (dark assets) gets filled in from what the owner publicly claims.

**The fan-out is the core rule:** one URL yields **one GROUP object + a PROPERTIES array**. The array is never collapsed into a single record. Each property becomes its own atomic record (its own `source_id`, e.g. `URL00001`), fills its own buckets, and resolves to its own ARN, exactly like one Realtrack transaction is one record. The group is resolved once and stamped onto all N properties.

---

## 2. What changed from the old M2 (contract reconciliation)

| Old M2 | Reconciled |
|---|---|
| Flat `street_address` handed to the resolver | Address is **Bucket C**: the adapter runs it through `cleo/address` decompose + `build_geocode_string` before `resolve()`. The raw string is extraction output, not a resolver input. |
| Captures `acreage` | Land converts to canonical **`land_size_sqft`** (Wave 2). |
| No resolver stamp | Every resolved property carries the **Wave 2 stamp**: `method`, `confidence`, `reason` (Bucket D output). |
| "Human review before commit; nothing writes without a human yes" | **No human pre-review.** Anything that resolves to an ARN enters the master, stamped by confidence. An AI sanity check auto-flags the suspicious ones; the human corrects at point of use (see §6). |
| Implicitly per-URL | Fan-out made explicit: one group + N property records, never flattened. |

---

## 3. Extraction schema (the durable artifact)

The AI is locked to this structure via structured output. Bucket tags in comments. **Unknown fields are explicitly `null`, never guessed.**

```
{
  "group": {                                  // Bucket F (once) + Bucket A provenance
    "canonical_name": str,                    //   -> normalize_brand -> GRP_ (matches existing group)
    "aliases": [str],
    "business_lines": [str],                  //   owner | developer | property_manager | brokerage
    "corp_address": str, "corp_phone": str, "fax": str,
    "domain": str, "website": str, "emails": [str], "socials": [str],
    "partners": [str],
    "people": [ {"name": str, "title": str, "email": str, "phone": str} ],
    "source_url": str, "confidence": 0.0-1.0
  },
  "properties": [                             // MANY — each becomes its own URL##### record
    {
      "provenance":  { "source_url": str, "confidence": 0.0-1.0 },              // Bucket A
      "property_name": str,                                                      // Bucket H (marketing name — NOT the address)
      "address": { "street_address": str, "city": str,                          // Bucket C (raw civic line only)
                   "province": str, "postal": str },
      "site": { "property_type": str, "retail_subtype": str,                    // Bucket E
                "land": { "value": num, "unit": "sqft|acres|sf" } },            //   -> adapter converts to land_size_sqft
      "detail": { "total_sqft": num, "units": int, "floors": int,              // Bucket H
                  "parking": str, "vacancy": str, "asking_rate": str,
                  "pdf_links": [str], "photos": [str] },
      "tenants": [ {"name": str, "unit": str, "sqft": num, "is_anchor": bool} ],// Bucket H
      "ownership": { "relationship": "owns|manages|lists|unclear",             // Bucket F
                     "reasoning": str }
    }
  ],
  "meta": { "site_structure_notes": str, "data_quality_notes": str }
}
```

The resolver's stamp (Bucket D: `resolved_arn`, `method`, `confidence`, `reason`, geometry) is **not** in this schema. It is added downstream by the resolve step; the AI never guesses an ARN.

---

## 4. Extraction protocol (what keeps the AI consistent)

1. **Structured output, schema-locked.** The model fills the schema above or the call fails. It cannot invent a shape.
2. **Classification rules (the switchboard):** a civic address goes only in `address.street_address`; a marketing/mall name goes only in `property_name`; a tenant name only in `tenants[]`. The address block is the *only* thing that reaches the resolver.
3. **Nulls, never guesses.** Absent field = `null`. No inference, no filler.
4. **Judgment, with reasoning.** `ownership.relationship` (owns/manages/lists/unclear) must include `reasoning`, because owns-vs-manages is the one genuine judgment call.
5. **Deterministic validation after the AI, before resolve.** Code checks the output: an `address` block with no street number is not a resolvable address and is not sent to the resolver (it becomes a name-only record, §5 step 4e). The AI proposes; validation disposes.

---

## 5. Pipeline: URL to Output Properties

```
raw-data/url/{group}/   -> engines/url/  (crawl -> extract -> resolve -> compile) -> clean-data/url/ -> compiler -> master
```

1. **Crawl** (Playwright, already in the stack): discover portfolio/property/about/contact pages and PDFs; render JS.
2. **Extract** (Claude structured output to §3 schema) -> `{group, properties[]}`; run §4 validation.
3. **Resolve the group once:** `canonical_name` -> `normalize_brand` -> `GRP_`, matching an existing group if Plaza already exists in Cleo (no duplicate). Store `group_profile`, `group_aliases`, `group_match_keys`.
4. **For each property (its own record, `URL#####`):**
   a. Address -> **Bucket C** (`decompose` + `build_geocode_string`).
   b. `resolve()` -> `resolved_arn` + `method` + `confidence` + `reason` (the stamp).
   c. `site.land` -> `land_size_sqft`; `detail` -> `property_capture`; `tenants[]` -> `property_tenants`.
   d. **Mint / link by ARN:** ARN in master -> link. ARN not in master -> **add it to the master** with the resolver's cached geometry (expands coverage). Owner link -> the group's `GRP_` with `relationship`. Stamp `method`/`confidence`/`web` provenance on the record.
   e. **No ARN (unresolved):** keep the record, leave it unlinked, flag it with its `reason`. Never force it onto a wrong ARN.
5. **Compile / rebuild** surfaces everything (master properties, capture detail, tenant rosters, owner links).

---

## 6. Trust model (stamp + flag, no pre-review)

- **Mint threshold = has an ARN.** Anything that resolves enters the master. Confidence sets the *badge*, not a gate. Only unresolved (no ARN) records stay unlinked.
- **Stamp, visible in-app.** Web-captured properties show their `method`/`confidence` and a "web, unverified" badge below the strong tiers, so a 0.7 spatial match never masquerades as a verified one.
- **AI sanity check at ingest** (does the resolved parcel's address roughly match the scraped one; is the property type plausible for the portfolio) auto-opens an `issues` row on the suspicious ones. It flags, it never blocks.
- **Correct at point of use.** A flag in the app writes to `issues` and routes to one of two fixes: an **override** (`manual_owner_links`, instant) for one wrong record, or a **rule fix** (resolver/clustering, via Claude) when a whole class is wrong. No review queue.

---

## 7. Multiplicity rules (the fan-out, restated)

- One URL = one group + N property records. Never collapse the array.
- Each property: unique `source_id`, own JSON, own ARN.
- Group resolved once; its `GRP_` stamped on all N.
- Two properties -> same ARN: one master property, both records behind it (dedup by ARN).
- A property resolves to an ARN Realtrack already attributes elsewhere: **flagged conflict**, RT owner not clobbered (existing owner_overrides behaviour).

---

## 8. Where it lands

- `raw-data/url/`, `clean-data/url/` — source records (one per property).
- `properties` — master, minted/linked by ARN, stamped.
- `property_capture`, `property_tenants` — detail, keyed by ARN.
- `manual_owner_links` — property -> `GRP_`, with `relationship`.
- `group_profile`, `group_aliases`, `group_match_keys` — the group + its attach keys.

---

## 9. Build sequence

1. **This spec** (done).
2. **Extractor:** endpoint URL -> crawl -> schema-locked Claude extraction -> validate -> `{group, properties[]}`. Proven target: Plaza.
3. **Resolve + stamp + link:** per property, Bucket C -> `resolve()` -> ARN + stamp; group -> `GRP_`. (Resolver-runs-standalone already proven 2026-07-17.)
4. **Write to Cleo:** mint/link by ARN (new ARNs expand master), write capture + tenants + owner links.
5. **Surface + flag:** confidence badge + flag button + AI sanity check.

MVP for "Input URL -> Output Properties" = steps 2-4. Step 5 is the trust layer.

## 10. Out of scope (v1)

PDF site-plan parsing for GLA/units; contact enrichment as a separate step (email-pattern, Apollo/ZoomInfo, RECO, GW ATTN names); scheduled re-capture; conflict-resolution UI beyond the flag.
