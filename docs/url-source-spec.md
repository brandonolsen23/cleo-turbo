# URL Source Spec (reconciled M2 / Portfolio Capture)

**Status:** v1.1, 2026-07-17. Contract-aligned. Adds the robust content-acquisition architecture + eval-based definition of done.
**Supersedes:** the "Extraction protocol" and per-property schema in `docs/portfolio-capture-build-plan.md` (M2), which predates the field contract.
**Depends on:** `docs/field-contract.md` (the buckets), `cleo/resolver` (address to ARN), `cleo/address` (Bucket C).

---

## 1. What it does

Paste an owner's website URL. Cleo renders and crawls it, an AI extracts one **group** (e.g. Plaza REIT) and **many properties**, each property resolves to an ARN through the shared contract, and the results land in the master property list under that one group. Ownership that never traded through Realtrack (dark assets) gets filled in from what the owner publicly claims.

**The fan-out is the core rule:** one URL yields **one GROUP object + a PROPERTIES array**, never collapsed. Each property becomes its own atomic record (its own `source_id`, e.g. `URL00001`), fills its own buckets, and resolves to its own ARN, exactly like one Realtrack transaction is one record.

**Where the fragility lives (read this first):** the extractor (classification) is structure-agnostic — an LLM reads a table, a list, a property page, a PDF, or a screenshot equally well. *All* robustness risk lives in **content acquisition**: reliably delivering the *complete* content of an arbitrary site to the extractor. A plain HTTP GET is not enough (proven 2026-07-17: Eastcourt's full tenant roster and site-plan PDF are JavaScript-rendered and invisible to a bare fetch — the model correctly bucketed what it got and flagged the gap, but it was fed a skeleton). So we harden the front end, not the extractor, and we never write per-site parsers.

---

## 2. What changed from the old M2 (contract reconciliation)

| Old M2 | Reconciled |
|---|---|
| Flat `street_address` handed to the resolver | Address is **Bucket C**: the adapter runs it through `cleo/address` decompose + `build_geocode_string` before `resolve()`. |
| Captures `acreage` | Land converts to canonical **`land_size_sqft`** (Wave 2). |
| No resolver stamp | Every resolved property carries the **Wave 2 stamp**: `method`, `confidence`, `reason`. |
| "Human review before commit" | **No human pre-review.** Anything that resolves to an ARN enters the master, stamped; AI sanity check auto-flags; human corrects at point of use (§7). |
| Plain fetch, one page | **Render + vision + crawl** across the whole site (§5), because a bare fetch under-captures JS sites. |
| "Works on the demo URL" | **Multi-site eval** is the definition of done (§11). |

---

## 3. Extraction schema (the durable artifact)

The AI is locked to this structure via forced tool-use. Bucket tags in comments. **Unknown fields are explicitly `null`, never guessed.**

```
{
  "group": {                                  // Bucket F (once) + Bucket A provenance
    "canonical_name": str,                    //   public owner name -> normalize_brand -> GRP_ (matches existing)
    "aliases": [str], "business_lines": [str],//   owner|developer|property_manager|brokerage
    "corp_address": str, "corp_phone": str, "domain": str, "website": str,
    "people": [ {"name": str, "title": str} ],
    "confidence": 0.0-1.0
  },
  "properties": [                             // MANY — each becomes its own URL##### record
    {
      "property_name": str,                   // Bucket H — marketing/building name, NEVER the address
      "address": { "street_address": str,     // Bucket C — civic line with street number only
                   "city": str, "province": str, "postal": str },
      "site": { "property_type": str, "retail_subtype": str,          // Bucket E
                "land": { "value": num, "unit": "sqft|acres|sf" } },  //   -> land_size_sqft
      "detail": { "total_sqft": num, "units": int, "floors": int,     // Bucket H
                  "parking": str, "vacancy": str, "asking_rate": str, "pdf_links": [str] },
      "tenants": [ {"name": str, "unit": str, "sqft": num, "is_anchor": bool} ],  // Bucket H
      "ownership": { "relationship": "owns|manages|lists|unclear", "reasoning": str }  // Bucket F
    }
  ],
  "meta": { "site_structure_notes": str, "data_quality_notes": str }  // gaps, claimed-vs-found, ambiguities
}
```

The resolver's stamp (Bucket D: `resolved_arn`, `method`, `confidence`, `reason`, geometry) is added downstream by the resolve step; the AI never guesses an ARN.

---

## 4. Extraction protocol (what keeps the AI consistent)

1. **Forced tool-use, schema-locked.** The model fills the schema above or the call fails.
2. **Classification rules (the switchboard):** civic address only in `address.street_address`; marketing/building name only in `property_name`; tenant names only in `tenants[]`; owner name only in `group.canonical_name`. The address block is the only thing that reaches the resolver.
3. **Nulls, never guesses.**
4. **Judgment with reasoning:** `ownership.relationship` includes `reasoning`.
5. **Deterministic validation after the AI, before resolve:** an `address` with no leading street number is not resolvable (`_address_resolvable=false`) and is not sent to the resolver — it becomes a name-only record (§6 step e).

---

## 5. Content acquisition (the robust front end)

Layered on purpose so no single failure mode sinks a site. One code path, no per-site parsers.

1. **Render, don't fetch.** Load every page in headless **Playwright** (already in the stack for the geocoder), execute JS, wait for content, expand `load-more` / pagination / tabs where present.
2. **Text + screenshot (vision).** Capture the rendered text *and* a full-page screenshot; feed both to Claude. Vision covers styled tables, interactive maps with pins, and image-based layouts that text scraping misses. This is the main robustness lever, one path handles most structures.
3. **Discover the property set.** From the entry URL's rendered links/nav, crawl same-domain property/portfolio pages (each rendered). Handle: all-on-one-list-page, link-to-detail-pages, paginated lists, and downloadable PDF portfolios. Never assume one page is the whole portfolio.
4. **PDF path.** Linked portfolio / site-plan / leasing PDFs -> extract text (+ page screenshots for vision) -> same extractor.
5. **Merge + dedup.** Combine per-resource extractions into one group + a deduped property array (key: address or name). When a property appears on both the list page and its own detail page, the richer detail page wins.
6. **Completeness check + graceful degradation.** Reconcile found-count against any site-claimed count (e.g. "48 properties"); surface the gap, never bury it. Keep the model's `data_quality_notes` per property. **Never emit a partial result that looks complete.** Capture what we can, flag what we couldn't. A record that says "listed by Plaza, address captured, tenants missing" is honest and useful; a silently-truncated portfolio is a trap.

---

## 6. Pipeline: URL to Output Properties

```
raw-data/url/{group}/  -> engines/url/ (acquire[§5] -> extract[§3/4] -> resolve -> compile) -> clean-data/url/ -> compiler -> master
```

1. **Acquire** (§5): render + screenshot + crawl + PDF -> complete content per resource.
2. **Extract** (§3/4) per resource -> `{group, properties[]}`; validate; **merge + dedup** across resources.
3. **Resolve the group once:** `canonical_name` -> `normalize_brand` -> `GRP_`, matching an existing group (no duplicate). Store `group_profile`, `group_aliases`, `group_match_keys`.
4. **For each property (its own record, `URL#####`):**
   a. Address -> **Bucket C** (`decompose` + `build_geocode_string`).
   b. `resolve()` -> `resolved_arn` + `method` + `confidence` + `reason` (the stamp).
   c. `site.land` -> `land_size_sqft`; `detail` -> `property_capture`; `tenants[]` -> `property_tenants`.
   d. **Mint / link by ARN:** in master -> link; not in master -> **add it** with the resolver's cached geometry. Owner link -> the group's `GRP_` with `relationship`. Stamp method/confidence/web provenance.
   e. **No ARN (unresolved):** keep the record, unlinked, flagged with `reason`. Never force a wrong ARN.
5. **Compile / rebuild** surfaces everything.

---

## 7. Trust model (stamp + flag, no pre-review)

- **Mint threshold = has an ARN.** Confidence sets the *badge*, not a gate. Only unresolved (no ARN) records stay unlinked.
- **Stamp, visible in-app.** Web-captured properties show `method`/`confidence` and a "web, unverified" badge below the strong tiers.
- **AI sanity check at ingest** (does the resolved parcel's address roughly match the scraped one; is the type plausible for the portfolio) auto-opens an `issues` row on suspicious ones. It flags, never blocks.
- **Correct at point of use.** A flag writes to `issues` and routes to either an **override** (`manual_owner_links`, instant, one record) or a **rule fix** (resolver/clustering, via Claude, a whole class). No review queue.

---

## 8. Multiplicity rules (the fan-out)

- One URL = one group + N property records. Never collapse the array.
- Each property: unique `source_id`, own JSON, own ARN.
- Group resolved once; its `GRP_` stamped on all N.
- Two properties -> same ARN: one master property, both records behind it.
- Property resolves to an ARN Realtrack attributes elsewhere: **flagged conflict**, RT owner not clobbered.

---

## 9. Where it lands

`raw-data/url/`, `clean-data/url/` (one record per property); `properties` (master, minted/linked by ARN, stamped); `property_capture`, `property_tenants` (detail by ARN); `manual_owner_links` (property -> `GRP_` + relationship); `group_profile`, `group_aliases`, `group_match_keys` (group + attach keys).

---

## 10. Build sequence

1. **This spec** (done).
2. **Extractor — classification** (done, `cleo/url_source/extract.py`): schema-locked, verified consistent on a fully-supplied page.
3. **Content acquisition** (§5): render + screenshot/vision + crawl + PDF + merge/dedup + completeness. **This is the current fragile gap.**
4. **Resolve + stamp + link:** per property, Bucket C -> `resolve()` -> ARN + stamp; group -> `GRP_`. (Resolver-runs-standalone proven 2026-07-17.)
5. **Write to Cleo:** mint/link by ARN (new ARNs expand master), write capture + tenants + owner links.
6. **Surface + flag:** confidence badge + flag button + AI sanity check.

---

## 11. Definition of done (the eval)

Robust means it passes a **multi-site eval**, not one happy-path URL. Sites (deliberately different structures, from the build plan): **Plaza** (single property page + JS portfolio), **Rosart**, **Strongman**, **Biddington**.

Per site, measured automatically:
- **Completeness:** properties found vs the site's claimed count; PDFs and JS-loaded content captured.
- **Correctness:** every field in the right bucket (address vs name vs tenant vs owner); `_address_resolvable` accurate.
- **Honesty:** gaps reported in `data_quality_notes`, not hidden.

A new site that breaks it is almost always an **acquisition** fix (a render wait, a pagination click, a PDF path), not a new parser. The eval says so immediately, and it is the regression guard for every future site.

---

## 12. Out of scope (v1)

Contact enrichment as a separate step (email-pattern, Apollo/ZoomInfo, RECO, GW ATTN names); scheduled re-capture; conflict-resolution UI beyond the flag.
