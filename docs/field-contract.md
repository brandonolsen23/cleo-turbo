# Cleo Turbo — Canonical Field Contract

**Status:** Draft v1 · 2026-07-17 · governs the shared ingestion spine
**Companion:** the Field Flow Mind Map artifact (`cleo-field-flow-mindmap`)

---

## 1. Why this exists

Every data source in Cleo is different at the front (Realtrack HTML, a GeoWarehouse report, an OSM node, a website page). But everything they describe is the same handful of things: a property, an address, a parcel, an owner, a price, some physical details. This contract is the single definition of *those* things. It says: for any source, here is the exact set of fields you map your raw data into, here is the unit and processor each one uses, and here is where it ends up.

Two rules make it work:

1. **A source never invents its own version of a shared field.** An address is an address; it goes through the shared address engine whether it came from RT or a website. Same for land size, building size, and owner names.
2. **A field the contract doesn't cover is a deliberate extension, not a silent add.** When a new source brings something genuinely new (a Zoning source bringing bylaw references, say), that field gets named, typed, given a home, and wired into compile on purpose — and it joins this contract so the next source inherits it.

The backbone remains the **ARN**. Every record, from every source, resolves to an ARN and links to everything else through it.

---

## 2. The canonical blocks

Every source's staging step maps its raw data into these blocks. Not every source fills every block (GW has no transaction event; a website has no consideration). Empty is fine and expected — *absent from the block* means "the source said nothing," which is different from "we never looked."

### Block A — Provenance *(mandatory, every record)*

| Field | Type | Notes |
|---|---|---|
| `source` | text | `rt` `gw` `osm` `url` … |
| `source_id` | text | RT_ID / GW_ID / OSM_ID / URL slug |
| `source_url` | text | the page/report the data came from (web + provenance) |
| `source_file` | text | raw file on disk, where applicable |
| `captured_at` / `compiled_at` | ISO datetime | |
| `confidence` | 0–1 | how sure we are of this record |
| `web_asserted` / `registry_confirmed` | bool | registry/GW outranks web |

### Block B — Transaction / Event *(optional)*

| Field | Type | Unit | Owner |
|---|---|---|---|
| `sale_date` | date | ISO | — |
| `sale_price` | int | CAD | — |
| `event_type` | text | transfer / sale / listing | — |
| `transaction_note` | text | | — |

### Block C — Address *(SHARED — cleo/address + cleo/resolver)*

The one block that must be identical across all sources. Raw address text in, canonical structure out.

| Field | Type | Owner |
|---|---|---|
| `original` | text | staging (verbatim) |
| `display` | text | `cleo/address` formatter |
| `components{}` | object | `cleo/address/decompose` — street_number, street_name, street_suffix, street_direction, suite_type, suite_number |
| `geocode_string` | text | **`build_geocode_string` (to be promoted to cleo/address)** — one assembler for all sources |
| `city` / `region` / `municipality` | text | staging |
| `postal` / `province` / `country` | text | staging |

**Rule:** components are always produced and always preserved in the clean-data record, for every source. (Closes issues #2 and #6.)

### Block D — Parcel / Resolution *(SHARED — cleo/resolver output)*

| Field | Type | Notes |
|---|---|---|
| `resolved_arn` | 20-digit | the join key / backbone |
| `method` | text | verified / spatial_* / arn_* / pin_bridge / **unresolved** / error — never blank (closes #3) |
| `reason` | text | why unresolved (geocode_miss, pin_no_match…) — **new column** |
| `confidence` | 0–1 | |
| `pip_verified` | bool | |
| `tier` | text | verified / probable / review |
| `containment`, `loc_name`, `addr_type`, `geocode_score`, `field_match` | mixed | provenance |
| `lat`, `lng`, `parcel_geojson` | geo | the map polygon |

### Block E — Site / Physical

| Field | Type | Unit | Owner |
|---|---|---|---|
| `pin` (+ `pin_api`) | text | — | `cleo/address` pin formatter |
| **`land_size_sqft`** | number | **sq ft (canonical)** | land-size converter — acres derived for display (closes #4) |
| `building_size` | raw + value + unit | mixed (sf/units/rooms…) | `building_size.py` — never summed across units |
| `frontage_ft`, `depth_ft` | number | ft | pass-through |
| `legal_description` | text | | |
| `location` | text | | |
| `property_code` / `property_type` / `asset_class` | text | | classifier |
| `zoning` | text | | *(extension-ready; see §6)* |

### Block F — Parties / Ownership *(SHARED — normalize_brand → groups; fingerprint → contacts)*

| Field | Type | Owner |
|---|---|---|
| `party_name`, `trade_name`, `care_of`, `companies`, `law_firms` | text/list | `normalize_brand` → `GRP_` |
| `side` | text | buyer / seller / owner |
| `phone` | text | `normalize_phone` |
| `contacts[]` {name, title} | list | fingerprint → `CON_` |
| `mailing_address` | Block C shape | shared address engine |

### Block G — Financial

| Field | Type | Unit |
|---|---|---|
| `cash`, `debt`, `chattels`, `other` | int | CAD |
| `charges[]` {chargee, principal, rate, registered, due} | list | |
| `assessed_value`, `valuation_date` | int / date | CAD / — |
| `asking_rate`, `noi` | mixed | |

### Block H — Detail / Media *(source-specific richness, keyed by ARN)*

| Field | Type | Lands in |
|---|---|---|
| `total_sqft`, `units`, `floors`, `parking`, `vacancy` | mixed | `property_capture` |
| `tenants[]` {name, unit, sqft, is_anchor} | list | `property_tenants` |
| `pdf_links`, `photos` | list | `property_capture` / `transactions.photos_json` |
| `description`, `website`, `socials` | text | various |

---

## 3. Known-field registry

The registry is the machine-checkable version of §2: canonical field → block → type → unit → owning processor → source(s) that populate it → DB destination. It lives next to this doc and is the thing a new source is diffed against. (First build: generate it from the block tables above plus the DB schema so it's exhaustive.)

---

## 4. Standardization rules (the guarantees)

- **Address** — always through shared `decompose` + the promoted `build_geocode_string`. Same physical address produces the same geocoder query regardless of source. Components preserved in clean-data everywhere.
- **Land size** — one canonical field `land_size_sqft`. RT acres × 43,560; GW `site_area_sqft` direct; GW `lot_size_area` parsed instead of dropped. Acres derived at read time for display.
- **Building size** — raw + parsed value + unit. Never summed across mixed units.
- **Names** — `party_name` / `trade_name` / `care_of` / `companies` all feed `normalize_brand` → group `normalized_name` → stable `GRP_`. People → fingerprint → `CON_`.
- **Parcel method** — always the real method, including `unresolved`, never blank. `reason` always captured.
- **Provenance** — every captured field carries source + confidence; registry/GW beats web; web never overwrites a confirmed owner.

---

## 5. The 7 issues, as conformance tasks

| # | Issue | Contract section it satisfies | Wave |
|---|---|---|---|
| 5 | geocode_string built differently per source | §2 Block C — one `build_geocode_string` | 1 |
| 2 | GW drops address components | §2 Block C — components preserved everywhere | 1 |
| 6 | POI address bypasses decomposer | §2 Block C | 1 |
| 4 | land size not standardized | §2 Block E + §4 — `land_size_sqft` | 2 |
| 1 | property-address components not in DB | §2 Block C decision (display + ARN in DB) | 2 |
| 3 | unresolved stored as '' | §2 Block D — real method + reason | 2 |
| 7 | URL detail tables have no writer | §2 Block H — `property_capture` / `property_tenants` | 3 |

---

## 6. Adding a new source (the process)

This is the payoff. Adding a source is a fixed procedure, not a redesign.

1. **Inventory** the raw fields the source exposes.
2. **Map** each to a canonical block/field. Addresses → Block C, property details → Block E, owner/company → Block F, price → Block B/G.
3. **Route** mapped fields through the shared processors — no source writes its own address, land-size, or name logic.
4. **Flag the leftovers.** Any raw field with no canonical home is a proposed **extension**: name it, choose its block (or open a new block), set type + unit, decide its DB destination, add it to the registry.
5. **Wire** the extension into the clean-data record and the compiler intentionally.
6. **Write the adapter** — convert the source's format to `ResolutionInput`, call the shared `resolve()`, and emit a clean-data record in the contract shape.

### Worked example — a Zoning source

- **Maps cleanly (existing fields):** property address → Block C (shared decompose + geocode + resolve to ARN). Municipality, PIN → existing. So zoning data attaches to the right parcel automatically, through the same engine everything else uses.
- **New fields (extensions):** `zoning_code`, `zoning_class`, `bylaw_ref`, `official_plan_designation`, `permitted_uses[]`, `zoning_effective_date`. None have a home today.
- **Decision the extension forces:** a new block **I — Regulatory/Zoning** and a new DB table `property_zoning` keyed by ARN (many zoning records can attach to one parcel over time, like `gw_sales_history`), rather than columns on `properties`.
- **Result:** the zoning source resolves addresses identically to RT/GW, its bylaw data lands in `property_zoning`, and "show me the zoning on this parcel" joins on ARN like everything else.

---

## 7. Open decisions (defaults in force unless you change them)

| Decision | Default | Change it to |
|---|---|---|
| Canonical land-size unit | **Store `land_size_sqft`, derive acres** | store both, or leave per-source |
| Property-address components in DB | **Display + ARN in DB; components live in clean-data** | persist component columns on `properties` |
| Unresolved `reason` in DB | **Add `parcel_reason` column** | flip `''`→`'unresolved'` only, no reason |
| Contract home | proposed `docs/field-contract.md` in the repo | elsewhere |

---

## 8. Next steps

- Confirm or change §7 defaults.
- On a branch, tested against a copy of `data/cleo.db`: Wave 1 (issues 5, 2, 6) → Wave 2 (4, 1, 3) → Wave 3 (7).
- Generate the §3 registry as a checked-in file so future sources diff against it automatically.
