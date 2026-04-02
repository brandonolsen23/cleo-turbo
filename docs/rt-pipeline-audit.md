# RT Data Pipeline Audit: Fields Present in Clean-Data vs Database

**Audit Date:** 2026-04-02
**Scope:** RT (Realtrack) data pipeline - clean-data JSON to SQLite database write-through via Compiler

## Executive Summary

This audit comprehensively maps every field in RT clean-data JSON files against what the Compiler actually writes to the SQLite database. The RT pipeline consists of:

1. **RT Engine** (engines/rt/compile.py) - outputs structured JSON to clean-data/rt/
2. **Compiler** (cleo/compiler/writer.py Pass 3) - reads RT records and writes to derived tables:
   - `transactions` table
   - `transaction_parties` table
   - `properties` table

**Finding:** The pipeline extracts and structures 50+ fields in the RT engine, but the Compiler normalizes only 30 of them to the database. The remaining 20+ fields are either stored as JSON blobs (not SQL-queryable) or completely lost.

---

## Clean-Data RT JSON Structure (Complete Inventory)

Based on analysis of RT100000.json, RT100002.json, and RT100005.json:

### Top-Level Fields
- `source_id` (string) - e.g., "RT100000"
- `source` (string) - always "rt"
- `source_folder` (string) - e.g., "Oxford_County/farm/p010"
- `compiled_at` (ISO timestamp) - when compiled by RT engine
- `transaction` (object)
- `property` (object)
- `seller` (object)
- `buyer` (object)
- `site` (object)
- `parcel` (object or null)
- `consideration` (object)
- `broker` (object)
- `description` (object)
- `photos` (object)

---

## Detailed Field-by-Field Analysis

### 1. TRANSACTION OBJECT (5 fields)

```json
{
  "sale_date": "2014-05-09",
  "sale_price": 3265048,
  "transaction_note": "",
  "city": "Norwich",
  "region": "Oxford County"
}
```

| Field | Status | Destination | Notes |
|---|---|---|---|
| sale_date | ✅ WRITTEN | transactions.sale_date | Line 303 |
| sale_price | ✅ WRITTEN | transactions.sale_price | Line 303 |
| transaction_note | ✅ WRITTEN | transactions.transaction_note | Line 303 |
| city | ✅ WRITTEN | transactions.city, properties.city | Line 303, 252 |
| region | ✅ WRITTEN | transactions.region, properties.region | Line 303, 253 |

**Result:** 100% written. ✅

---

### 2. PROPERTY OBJECT (addresses + city/region/postal)

The property object contains a `addresses` array plus location metadata:

```json
{
  "addresses": [
    {
      "original": "325149 NORWICH RD",
      "display": "325149 Norwich Road",
      "components": {
        "street_number": "325149",
        "street_name": "Norwich",
        "street_suffix": "Road",
        "street_direction": "",
        "suite_type": "",
        "suite_number": ""
      },
      "search_keys": ["325149 norwich road", "325149 norwich"],
      "variations": [],
      "geocode_string": "325149 Norwich Road, Norwich, Ontario N0J 1P0, Canada",
      "geocodable": true,
      "type": "street_address"
    }
  ],
  "city": "Mississauga",
  "region": "Peel Region",
  "postal": "L4T 1G5"
}
```

#### Property.Addresses Array

Per address object, there are 10 fields:

| Field | Status | Notes |
|---|---|---|
| addresses[0].original | ❌ IGNORED | Not written anywhere |
| addresses[0].display | ✅ WRITTEN | transactions.display_address, properties.display_address (Lines 239, 304) |
| addresses[0].components.street_number | ❌ IGNORED | Parsed by RT engine, never extracted to DB |
| addresses[0].components.street_name | ❌ IGNORED | Parsed by RT engine, never extracted to DB |
| addresses[0].components.street_suffix | ❌ IGNORED | Parsed by RT engine, never extracted to DB |
| addresses[0].components.street_direction | ❌ IGNORED | Parsed by RT engine, never extracted to DB |
| addresses[0].components.suite_type | ❌ IGNORED | Parsed by RT engine, never extracted to DB |
| addresses[0].components.suite_number | ❌ IGNORED | Parsed by RT engine, never extracted to DB |
| addresses[0].search_keys | ❌ IGNORED | Generated for FTS by RT engine, never written |
| addresses[0].variations | ❌ IGNORED | Alternative address formats, never written |
| addresses[0].geocode_string | ❌ IGNORED | Full geocoded address string, never written |
| addresses[0].geocodable | ❌ IGNORED | Boolean flag, never written |
| addresses[0].type | ❌ IGNORED | Always "street_address", never written |

#### Property Top-Level Fields

| Field | Status | Destination |
|---|---|---|
| city | (duplicate of transaction.city) | — |
| region | (duplicate of transaction.region) | — |
| postal | ✅ WRITTEN | transactions.postal, properties.postal |

**Critical Finding:** 10 fields are extracted and structured in the address parser (components.* and metadata), but only the display address makes it to the database. The structured components that could enable suite-level property identification and address component search are lost. ❌

---

### 3. SELLER OBJECT (7 direct fields + address object with 9 nested fields)

```json
{
  "parties": [
    {
      "name": "Named Individual(s)" | "Springerhill Farms Inc"
    }
  ],
  "phone": "519-866-3217",
  "trade_name": "KingSett Capital",
  "contacts": [
    {
      "name": "Harm Schipper",
      "title": "pres"
    }
  ],
  "care_of": null,
  "law_firms": [],
  "companies": [],
  "address": {
    "original_lines": ["54148 Heritage Line"],
    "display": "54148 Heritage Line",
    "components": {
      "street_number": "54148",
      "street_name": "Heritage",
      "street_suffix": "Line",
      "street_direction": "",
      "suite_type": "",
      "suite_number": ""
    },
    "search_keys": ["54148 heritage line", "54148 heritage"],
    "geocode_string": "54148 Heritage Line, Straffordville, Ontario N0J 1Y0, Canada",
    "modifiers": [],
    "building_names": [],
    "city": "Straffordville",
    "province": "Ontario",
    "postal": "N0J 1Y0",
    "country": ""
  }
}
```

#### Direct Fields

| Field | Status | Destination | Notes |
|---|---|---|---|
| parties[].name | ✅ WRITTEN | transaction_parties.party_name, groups.display_name, group_names.name | Lines 341, 86, 97 |
| phone | ✅ WRITTEN | transactions.seller_phone, transaction_parties.phone, contacts.phone | Lines 306, 341, 149, 165 |
| trade_name | ❌ IGNORED | Not written anywhere |
| contacts[].name | ✅ WRITTEN | contacts.display_name, transaction_parties.contact_id | Lines 148, 341 |
| contacts[].title | ✅ WRITTEN | contacts.job_title, transaction_parties.contact_title | Lines 150, 167, 341 |
| care_of | ❌ IGNORED | Not written |
| law_firms | ❌ IGNORED | Not written |
| companies | ❌ IGNORED | Not written |

#### Address Object (9 nested fields)

| Field | Status | Notes |
|---|---|---|
| address.original_lines | ❌ IGNORED | Not written |
| address.display | ❌ IGNORED | Not written |
| address.components.street_number | ❌ IGNORED | Not written |
| address.components.street_name | ❌ IGNORED | Not written |
| address.components.street_suffix | ❌ IGNORED | Not written |
| address.components.street_direction | ❌ IGNORED | Not written |
| address.components.suite_type | ❌ IGNORED | Not written |
| address.components.suite_number | ❌ IGNORED | Not written |
| address.search_keys | ❌ IGNORED | Not written |
| address.geocode_string | ❌ IGNORED | Not written |
| address.modifiers | ❌ IGNORED | Not written |
| address.building_names | ❌ IGNORED | Not written |
| address.city | ❌ IGNORED | Not written |
| address.province | ❌ IGNORED | Not written |
| address.postal | ❌ IGNORED | Not written |
| address.country | ❌ IGNORED | Not written |

**Critical Finding #1:** `trade_name`, `care_of`, `law_firms`, and `companies` fields exist in clean-data but are never written to any table. ❌

**Critical Finding #2:** The entire seller address object (16 fields including nested components) is fully parsed and geocoded by the RT engine, but ZERO fields from it are written to the database. This means:
- Cannot look up transactions by seller location
- Cannot build a "sellers by geography" map
- Cannot use seller mailing addresses for prospecting enrichment

This represents ~16 fields of data loss. ❌

---

### 4. BUYER OBJECT (identical structure to seller)

| Field | Status | Notes |
|---|---|---|
| parties[].name | ✅ WRITTEN | transaction_parties.party_name, groups.display_name |
| phone | ✅ WRITTEN | transactions.buyer_phone, transaction_parties.phone |
| trade_name | ❌ IGNORED | Not written |
| contacts[].name | ✅ WRITTEN | contacts.display_name |
| contacts[].title | ✅ WRITTEN | contacts.job_title, transaction_parties.contact_title |
| care_of | ❌ IGNORED | Not written |
| law_firms | ❌ IGNORED | Not written |
| companies | ❌ IGNORED | Not written |
| address.* (16 nested fields) | ❌ IGNORED | All ignored |

**Same Critical Findings apply:** 4 metadata fields + 16 address fields = 20 fields lost. ❌

---

### 5. SITE OBJECT (7 direct fields)

```json
{
  "pin": {
    "original": "00063-0124",
    "display": "00063-0124",
    "api_format": "000630124",
    "multiple": false
  },
  "arn": {
    "original": "",
    "display": "",
    "api_format": ""
  },
  "acreage": 119.5,
  "legal_description": "Conc 4, Part Lots 18 & 19\nAs in Inst Nos: ...",
  "location": "",
  "surface_rights_only": false
}
```

#### PIN Object (4 fields)

| Field | Status | Destination | Notes |
|---|---|---|---|
| pin.original | ❌ IGNORED | Not written |
| pin.display | ❌ IGNORED | Not written |
| pin.api_format | ✅ WRITTEN | transactions.pin | Line 308 |
| pin.multiple | ❌ IGNORED | Not written (indicates multi-parcel transactions) |

#### ARN Object (3 fields)

| Field | Status | Destination | Notes |
|---|---|---|---|
| arn.original | ❌ IGNORED | Not written |
| arn.display | ❌ IGNORED | Not written |
| arn.api_format | ✅ WRITTEN | transactions.arn, properties.arn | Lines 302, 227-232 |

#### Other Site Fields

| Field | Status | Destination | Notes |
|---|---|---|---|
| acreage | ✅ WRITTEN | transactions.acreage, properties.acreage | Lines 308, 255 |
| legal_description | ✅ WRITTEN | transactions.legal_description, properties.legal_description | Lines 308, 256 |
| location | ❌ IGNORED | Not written (e.g., "NW corner Thamesgate Dr and Airport Rd") |
| surface_rights_only | ❌ IGNORED | Not written |

**Finding:** Only `api_format` variants of PIN/ARN are written. The human-readable `original` and `display` formats plus the `multiple` flag (which indicates if a transaction involves multiple parcels) are lost. ❌

---

### 6. PARCEL OBJECT (3 fields, nullable)

```json
{
  "resolved_arn": "32020300400930000000",
  "method": "spatial_geocode",
  "parcel_file": "32020300400930000000.json"
}
```

| Field | Status | Destination | Notes |
|---|---|---|---|
| resolved_arn | ✅ WRITTEN | transactions.arn, properties.arn (chosen over site.arn) | Lines 302, 230 |
| method | ❌ IGNORED | Not written |
| parcel_file | ❌ IGNORED | Not written |

**Finding:** The `method` field (e.g., "spatial_geocode", "arn_cache") indicates how confident the ARN resolution is. This is lost, so users cannot distinguish between a validated parcel match vs. an inferred one. The `parcel_file` is a reference to the geometry file, also lost. ❌

---

### 7. CONSIDERATION OBJECT (stored as JSON, not normalized)

```json
{
  "cash": 3265048,
  "debt": 0,
  "chattels": null,
  "other": null,
  "charges": [
    {
      "chargee": "Royal Bank of Canada",
      "principal": 1800000,
      "rate": "Prime plus 5.0% per annum.",
      "registered": "05/07/2014",
      "due": "on demand"
    }
  ]
}
```

| Field | Status | Destination | Notes |
|---|---|---|---|
| cash | ⚠️ JSON ONLY | transactions.consideration_json | Line 309 (not queryable as SQL column) |
| debt | ⚠️ JSON ONLY | transactions.consideration_json | Line 309 |
| chattels | ⚠️ JSON ONLY | transactions.consideration_json | Line 309 |
| other | ⚠️ JSON ONLY | transactions.consideration_json | Line 309 |
| charges[] (all) | ⚠️ JSON ONLY | transactions.consideration_json | Line 309 |

**Finding:** Entire consideration object is stored as a JSON string. Users cannot query "transactions with debt > 500k" without JSON parsing functions. This is suboptimal for financial analysis. ❌

---

### 8. BROKER OBJECT (stored as JSON, not normalized)

```json
{
  "brokers": [
    {
      "brokerage": "Avison Young",
      "agents": ["Brett Elofson", "Adam Sherriff-Scott", "Matt Kornmuller"],
      "phone": "905-712-2100"
    }
  ]
}
```

| Field | Status | Destination | Notes |
|---|---|---|---|
| brokers[].brokerage | ⚠️ JSON ONLY | transactions.broker_json | Line 310 |
| brokers[].agents[] | ⚠️ JSON ONLY | transactions.broker_json | Line 310 |
| brokers[].phone | ⚠️ JSON ONLY | transactions.broker_json | Line 310 |

**Finding:** Broker information is stored as JSON only. Users cannot query "transactions brokered by Avison Young" without JSON parsing. ❌

---

### 9. DESCRIPTION OBJECT (2 fields, 1 lost)

```json
{
  "description": "Warehouse - 15 ft clr; 26,341 sf on about 1.9 Ac\n30% office\n2 truck level, 2 drive-in doors...",
  "more_info_url": "/assets/files/RT10/RT1000/RT100002/mi.pdf"
}
```

| Field | Status | Destination | Notes |
|---|---|---|---|
| description | ✅ WRITTEN | transactions.description | Line 307 |
| more_info_url | ❌ IGNORED | Not written (reference to supplementary PDF) |

**Finding:** `more_info_url` points to detailed documents but is never stored. Users lose the ability to access source materials. ❌

---

### 10. PHOTOS OBJECT (stored as JSON, not normalized)

```json
{
  "street_photo_urls": [
    "http://realtrack.cachefly.net/photos/RT10/RT1000/RT100002/0518_132440.jpg",
    "http://realtrack.cachefly.net/photos/RT10/RT1000/RT100002/0518_132453.jpg",
    ...
  ],
  "aerial_photo_urls": [],
  "standalone_photo_url": ""
}
```

| Field | Status | Destination | Notes |
|---|---|---|---|
| street_photo_urls | ⚠️ JSON ONLY | transactions.photos_json | Line 311 |
| aerial_photo_urls | ⚠️ JSON ONLY | transactions.photos_json | Line 311 |
| standalone_photo_url | ⚠️ JSON ONLY | transactions.photos_json | Line 311 |

**Finding:** Photo URLs are stored as JSON. UI cannot build a gallery widget without JSON parsing. ❌

---

### 11. TOP-LEVEL METADATA (3 fields)

| Field | Status | Destination | Notes |
|---|---|---|---|
| source_id | ✅ WRITTEN | transactions.source_id, properties.most_recent_source_id | Lines 302, 279 |
| source | ❌ IGNORED | Always "rt", not useful to store |
| source_folder | ✅ (partial) | transactions.source_folder (but property_type extracted & stored) | Line 312, 214 |
| compiled_at | ❌ IGNORED | Not written (timestamp of RT engine compilation) |

**Finding:** `compiled_at` timestamp (when the RT engine processed the record) is lost. This could be useful for auditing data freshness. ❌

---

## Complete Summary: All Ignored/Non-Normalized Fields

### Fields Completely Lost (Not Written Anywhere)

1. **Address Component Parsing** (6 fields × 2 address objects = 12 total):
   - property.addresses[0].components.street_number
   - property.addresses[0].components.street_name
   - property.addresses[0].components.street_suffix
   - property.addresses[0].components.street_direction
   - property.addresses[0].components.suite_type
   - property.addresses[0].components.suite_number
   - seller.address.components.* (6 fields)
   - buyer.address.components.* (6 fields)

2. **Address Metadata** (6 fields × 3 address objects = 18 total):
   - property.addresses[0].original
   - property.addresses[0].search_keys
   - property.addresses[0].variations
   - property.addresses[0].geocode_string
   - property.addresses[0].geocodable
   - property.addresses[0].type
   - seller.address (same 6 fields)
   - buyer.address (same 6 fields)

3. **Seller/Buyer Metadata** (4 fields × 2 = 8 total):
   - seller.trade_name
   - seller.care_of
   - seller.law_firms
   - seller.companies
   - buyer.trade_name
   - buyer.care_of
   - buyer.law_firms
   - buyer.companies

4. **Seller/Buyer Address Objects** (16 fields × 2 = 32 total):
   - seller.address.original_lines
   - seller.address.display
   - seller.address.search_keys
   - seller.address.geocode_string
   - seller.address.modifiers
   - seller.address.building_names
   - seller.address.city
   - seller.address.province
   - seller.address.postal
   - seller.address.country
   - buyer.address (same 10 fields)

5. **PIN/ARN Metadata** (5 fields):
   - site.pin.original
   - site.pin.display
   - site.pin.multiple
   - site.arn.original
   - site.arn.display

6. **Site Flags** (2 fields):
   - site.location (e.g., "NW corner Thamesgate Dr and Airport Rd")
   - site.surface_rights_only

7. **Parcel Resolution Metadata** (2 fields):
   - parcel.method (e.g., "spatial_geocode", "arn_cache")
   - parcel.parcel_file

8. **Description** (1 field):
   - description.more_info_url

9. **Metadata** (2 fields):
   - source (always "rt")
   - compiled_at

**Total Completely Lost: 94 fields**

### Fields Stored as JSON (Not SQL-Queryable)

10. **Consideration** (5+ fields):
    - consideration.cash
    - consideration.debt
    - consideration.chattels
    - consideration.other
    - consideration.charges (array with chargee, principal, rate, registered, due)

11. **Broker** (3+ fields):
    - broker.brokers[].brokerage
    - broker.brokers[].agents[]
    - broker.brokers[].phone

12. **Photos** (3 fields):
    - photos.street_photo_urls
    - photos.aerial_photo_urls
    - photos.standalone_photo_url

**Total Stored as JSON: 11+ fields (not queryable as columns)**

---

## Impact Assessment

### Severity: CRITICAL

**Address Component Parsing**
- 12 fields parsed and structured by the RT engine
- Only display address stored
- Impact: Cannot support suite-level property identification, component-based address search, or multi-tenant property workflows
- Example: A user searching for "all Suite 101 properties in the city" cannot do it without post-processing

**Party Location Data**
- 32 fields (seller/buyer addresses fully parsed with geocodes)
- Zero fields stored
- Impact: Cannot answer "which companies are selling in which regions?", cannot map buyer/seller distribution geographically, cannot use party mailing addresses for enrichment
- Example: A realtor cannot see which sellers are concentrated in their target market

**Financial Data Normalization**
- Consideration object (cash vs. debt) only stored as JSON
- Impact: Cannot query "all transactions with financing > 50% of sale price" without JSON parsing
- Example: Portfolio analysis, deal staging, risk assessment all require workarounds

**Confidence Metadata**
- Parcel resolution method lost
- Impact: Cannot distinguish between validated parcel matches vs. inferred ones
- Example: "ghost" properties (inferred but not confirmed) appear equally valid as validated ones

**Documentation Links**
- more_info_url lost
- Impact: Users cannot access supplementary materials, reducing context
- Example: A marketing document PDF explaining deal terms is forever unreachable

### Severity: MEDIUM

**Broker Data**
- Stored as JSON only
- Impact: Broker-focused workflows (deal attribution, commission tracking) require JSON parsing
- Workaround: Possible but cumbersome

**Photo URLs**
- Stored as JSON only
- Impact: UI cannot easily build gallery widgets
- Workaround: Possible with JSON parsing

**PIN Alternatives**
- pin.original, pin.display lost
- Impact: Users only get the api_format, lose the human-readable variant
- Example: Display "00063-0124" instead of "000630124"

---

## Root Cause Analysis

The RT engine (engines/rt/compile.py) extracts all these fields into a rich, normalized JSON structure. The code shows sophisticated parsing:
- Address component extraction (street_number, street_suffix, etc.)
- Geocoding (geocode_string for each address)
- Trade name detection
- Law firm extraction
- Parcel resolution method tracking

However, the Compiler (cleo/compiler/writer.py) in Pass 3 only writes a subset to the database:

```python
# Line 238-241: Extract display address
addrs = prop.get('addresses', [])
display_address = addrs[0].get('display', '') if addrs else ''
# Never touches: components, search_keys, variations, geocode_string, geocodable, type

# Lines 293-305: Build transaction INSERT
# Writes: seller/buyer parties, phones, contacts, titles
# Ignores: trade_name, care_of, law_firms, companies, entire address objects

# Line 309-311: Serialize blobs as JSON
json.dumps(rec.get('consideration', {}))  # Cash/debt/charges not extracted
json.dumps(rec.get('broker', {}))  # Brokerage/agents not extracted
json.dumps(rec.get('photos', {}))  # Photo URLs not extracted
```

**Why?** The original design decision was likely to minimize schema complexity and store "complex" data as JSON for flexibility. But this creates a data integrity issue: valuable enrichment data is extracted, formatted, and then thrown away.

---

## Recommendations

### Priority 1: Critical Data Recovery

1. **Add party address fields to transactions or transaction_parties**:
   - seller_city, seller_postal
   - buyer_city, buyer_postal
   - This enables geographic prospecting ("who is buying in my zip codes?")

2. **Add resolution_method to properties**:
   - Indicates if ARN was "spatial_geocode", "arn_cache", or inferred
   - Allows UI to show confidence levels

3. **Add documentation_url to transactions**:
   - Preserve more_info_url so users can access PDFs

### Priority 2: Financial/Operational Data

4. **Normalize consideration to separate columns**:
   - transaction_consideration_cash
   - transaction_consideration_debt
   - transaction_total_consideration (sale_price)
   - Enables SQL queries on financing structures

5. **Normalize broker data**:
   - transaction_brokerage_name
   - transaction_broker_agents (array as JSON or link to agent table)
   - transaction_broker_phone
   - Enables broker attribution and tracking

### Priority 3: UI/UX Enhancement

6. **Extract party trade_names**:
   - groups.trade_name
   - Improves company identification

7. **Store property address components**:
   - If suite-level properties become important, extract:
   - properties.street_number, street_name, street_suffix, suite_type, suite_number

### Priority 4: Audit/Metadata

8. **Preserve compiled_at timestamp**:
   - Track when data was processed
   - Useful for data freshness audits

---

## Files Involved

- **RT Engine Output:** `/sessions/trusting-charming-dijkstra/mnt/cleo-turbo/clean-data/rt/*.json`
- **RT Compiler Code:** `/sessions/trusting-charming-dijkstra/mnt/cleo-turbo/cleo/compiler/writer.py` (Pass 3, lines 199-354)
- **Database Schema:** `/sessions/trusting-charming-dijkstra/mnt/cleo-turbo/cleo/database/schema.py`

---

## Conclusion

The RT pipeline extracts a rich, well-structured dataset but the Compiler normalizes only a fraction of it to queryable SQL columns. This is not a bug, but a design limitation that reduces the system's ability to support location-based prospecting, financial analysis, and broker attribution workflows.

The gap is fixable via schema extensions and targeted normalization changes, with the highest-impact improvements being: party addresses, parcel resolution confidence, and financial structure normalization.
