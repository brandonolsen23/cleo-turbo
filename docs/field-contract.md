# Cleo Turbo — Canonical Field Contract

**Status:** v2, updated 2026-07-17 (Waves 0-2 implemented and live)
**Companion:** the Field Flow Mind Map artifact (`cleo-field-flow-mindmap`)

---

## 1. What this is: the switchboard

Every data source is different at the front (Realtrack HTML, a GeoWarehouse report, an OSM node, a website page), but they all describe the same handful of things: a property, an address, a parcel, an owner, a price, some physical details. This contract is the single definition of those things.

Think of it as a switchboard at the start of the pipeline. A raw field comes in, the source's staging step decides which **bucket** it belongs to, and the bucket has a fixed way to turn it from raw into ingestion-ready. A new source never invents formatting; it only routes each piece to a bucket and lets the bucket's shared processor do the rest.

Two rules make it hold:

1. A source never invents its own version of a shared field. An address is an address; it goes through the shared address engine whether it came from RT or a website. Same for land size, building size, and owner names.
2. A field the contract does not cover is a deliberate extension, not a silent add. When a source brings something genuinely new (a Zoning source bringing bylaw references), that field gets named, typed, given a home, and wired into the compiler on purpose, and it joins this contract so the next source inherits it.

Two things to keep straight:

- **Most buckets are input** (the source fills them). **One bucket, Parcel/Resolution, is output**: the resolver computes it from the Address and Site buckets. A source does not fill it; it earns it by feeding the address bucket correctly.
- The whole switchboard produces the **ARN** (Assessment Roll Number). Every record from every source resolves to an ARN, and the ARN is the join key that links a property's RT sale, GW owner, POI, and website capture together.

---

## 2. The buckets (switchboard lanes)

### A. Provenance  *(every record, always)*
`source`, `source_id`, `source_url`, `source_file`, `captured_at`/`compiled_at`, `confidence`, `web_asserted`/`registry_confirmed`.
Format: verbatim. Registry/GW outranks web; web never overwrites a confirmed owner. Absent means "the source said nothing," which is different from "we never looked."

**Capture timestamp is mandatory and must be recoverable.** Every raw capture is
stamped with *when it was captured*, at capture time, encoded in the source path
or filename so it survives into the record and is re-derived on every rebuild —
never inferred from compile time. `captured_at` (the date the source was
obtained) is a different fact from `compiled_at`/`created_at` (when the DB last
rebuilt); conflating them makes every record look freshly ingested after each
rebuild. Today this is the `source_date` column: RT daily scrapes carry it in
`source_folder` (`_daily/YYYY-MM-DD_HHMMSS/...`), GW downloads carry it in
`source_file` (`geowarehouse-<ISO>.html`), and `cleo/compiler/writer.py` parses
both deterministically so freshness views ("Recent Records", data-quality) sort
by real capture time. A capture that lands with no recoverable timestamp (e.g.
the historical bulk RT import) is treated as **undated**, never as "captured
now." A source that cannot embed a capture timestamp in its raw output is not
contract-compliant — fix the capture, don't backfill with `now()`.

### B. Transaction / Event  *(optional: RT has it, GW sales history has it, a website usually does not)*
`sale_date`, `sale_price`, `event_type`, `transaction_note`.
Format: dates to ISO; prices to integer CAD.

### C. Address  *(SHARED, enforced)*
The most important lane. Any address text, from any source, takes one path:
- `cleo/address/decompose` breaks it into components: street_number, street_name, street_suffix, street_direction, suite_type, suite_number.
- `cleo/address/formatter.format_display` builds the display string.
- `cleo/address/geocode.build_geocode_string` builds the exact query sent to the Ontario geocoder (promoted to a single shared function in Wave 1; RT, GW, and future lanes all call it).
- Plus city, region/municipality, postal, province.
This lane feeds the resolver. Same physical address in, same result out, regardless of source.

### D. Parcel / Resolution  *(SHARED, OUTPUT: the resolver fills this, not the source)*
`resolved_arn` (the backbone), `method` (verified / spatial_consensus / spatial_geocode / spatial_override / spatial_coords / arn_only / pin_bridge / **unresolved** / error, never blank), `reason` (why it failed: no_address, geocode_miss, arn_miss_*, arn_too_far_Nm, spatial_miss, etc.), `confidence` (0-1), `pip_verified`, `tier` (verified/probable/review), `containment`, `loc_name`, `addr_type`, `geocode_score`, `field_match`, and the geometry `lat`, `lng`, `parcel_geojson`.
A source hands the resolver an address (Block C) and/or a PIN/ARN; the resolver returns this bucket.

### E. Site / Physical
`pin` (formatted to 20-digit api_format), **`land_size_sqft`** (canonical square feet), `building_size` (raw + parsed value + unit), `frontage_ft`, `depth_ft`, `legal_description`, `location`, `property_code`/`property_type`/`asset_class`, and `zoning` (extension slot for a future source).
Format: land size to sqft; building size to value + unit (never summed across mixed units); pin/arn to 20-digit api_format.

### F. Parties / Ownership  *(SHARED, enforced)*
`party_name`, `trade_name`, `care_of`, `companies`, `law_firms`, `side` (buyer/seller/owner), `phone`, `contacts` (name + title), and a `mailing_address` that itself goes through Block C.
Format: company names through `normalize_brand` to a stable `GRP_` id; people through a fingerprint to a stable `CON_` id; phones through `normalize_phone`. This is what lets "who owns this" span SPVs.

### G. Financial
`cash`, `debt`, `chattels`, `other`, `charges[]`, `assessed_value`, `valuation_date`, `asking_rate`, `noi`.
Format: integers in CAD; dates ISO.

### H. Detail / Media  *(source-specific richness, keyed by ARN)*
`total_sqft`, `units`, `floors`, `parking`, `vacancy`, `tenants[]`, `pdf_links`, `photos`, `description`, `website`/`socials`.
Everything here attaches to a parcel by ARN, which is why the resolver has to run first. Defined but not yet wired for the URL source (see status #7).

---

## 3. Formatting rules (raw to ingestion-ready)

| Raw input | Bucket | Processor / rule |
|---|---|---|
| Address text | C | `cleo/address` decompose + formatter + `build_geocode_string` |
| PIN / ARN | D/E | api_format (20-digit, spaces stripped) |
| Land size (acres, sqft, ft x ft) | E | convert to `land_size_sqft` (acres x 43,560; measured sqft direct) |
| Building size (free-text) | E | parse to value + unit; never sum across units |
| Company / party name | F | `normalize_brand` -> `GRP_` |
| Person name | F | fingerprint -> `CON_` |
| Phone | F | `normalize_phone` |
| Date | B/G | ISO |
| Price / money | B/G | integer CAD |
| Owner->parcel link | D + owner_overrides | keyed by ARN; web never clobbers a registry owner |

---

## 4. Known-field registry

The machine-checkable version of Section 2: canonical field -> block -> type -> unit -> owning processor -> source(s) that populate it -> DB destination. Generate from the block tables above plus the DB schema so it is exhaustive; it is the thing a new source is diffed against. (Not yet generated as a file.)

---

## 5. Adding a new source (the procedure)

Adding a source is a fixed procedure, not a redesign.

1. **Inventory** the raw fields the source exposes.
2. **Route** each to a bucket: address -> C, property details/land -> E, owner/company -> F, price/date -> B/G, rich per-property detail -> H.
3. **Format** through the shared processor for that bucket. No source writes its own address, land-size, or name logic.
4. **Flag the leftovers.** Any raw field with no bucket is a proposed extension: name it, choose its block (or open a new one), set type + unit, decide its DB destination, add it to the registry.
5. **Wire** the extension into the clean-data record and the compiler intentionally.
6. **Write the adapter**: convert the source's format to a `ResolutionInput` (address-primary like RT/URL, or ARN-primary like GW), call the shared `resolve()`, and emit a clean-data record in the contract shape.
7. **Timestamp the capture.** The raw output must embed *when it was captured* in its filename or folder path (Block A), so `captured_at`/`source_date` is recoverable on every rebuild rather than collapsing to compile time. A source whose raw files carry no capture time is not compliant — fix the capture step, never stamp `now()` at ingest.

### Worked example: a Zoning source
- **Maps cleanly:** property address -> Block C (shared decompose + geocode + resolve to ARN). It attaches to the right parcel automatically, through the same engine as everything else.
- **New fields (extensions):** `zoning_code`, `zoning_class`, `bylaw_ref`, `official_plan_designation`, `permitted_uses[]`, `zoning_effective_date`.
- **The extension:** a new **Block I, Regulatory/Zoning**, and a new `property_zoning` table keyed by ARN (many zoning records over time per parcel, like `gw_sales_history`), rather than columns on `properties`.
- **Result:** zoning resolves addresses identically to RT/GW, its bylaw data lands in `property_zoning`, and "show me the zoning on this parcel" joins on ARN like everything else.

---

## 6. Status of the original drop-risks

| # | Item | Status |
|---|---|---|
| 5 | geocode_string built differently per source | **FIXED (Wave 1)** — shared `cleo/address/geocode.build_geocode_string` |
| 2 | GW dropped address components in its clean record | **FIXED (Wave 1)** — GW clean record carries components |
| 4 | land size not standardized | **FIXED (Wave 2, live)** — canonical `properties.land_size_sqft`; RT acres x 43,560, GW gap-fills from measured sqft |
| 3 | unresolved parcels stored as blank | **FIXED (Wave 2, live)** — `transactions.parcel_reason` added; method now reads `unresolved` with a reason |
| 1 | property-address components not in DB | **DECIDED (not a defect)** — components stay in clean-data; DB keeps display_address + ARN |
| 6 | POI addresses bypass the shared decomposer | **DEFERRED** (low priority; OSM resolves by coordinates) |
| 7 | URL detail tables have no writer | **OPEN (Wave 3 / Portfolio Capture M2)** — `property_capture` / `property_tenants` defined but unwired |

---

## 7. Where it is enforced (code) + run commands

- Address engine: `cleo/address/` (decompose, formatter, dictionaries, geocode).
- Resolver: `cleo/resolver/` (6-step chain, cache, PIP, pin bridge). Each engine has a thin `adapter.py`.
- Compiler: `cleo/compiler/` (reader iterates `clean-data/{src}/`, reconciler assigns stable IDs, writer builds derived tables keyed by ARN).
- Owner overrides / capture layer: `cleo/compiler/owner_overrides.py`, `cleo/compiler/portfolio_capture.py`.

Run (all via Desktop Commander / the project `.venv`):
- Regenerate RT clean-data: `cd engines/rt && .venv/bin/python compile.py` (supports `--limit`).
- Rebuild the DB from clean-data: `.venv/bin/python3 rebuild.py` (`--fresh` deletes + reseeds). Both honor `CLEO_DB_PATH` for scratch testing.
