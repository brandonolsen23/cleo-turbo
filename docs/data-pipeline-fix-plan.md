## COMPREHENSIVE IMPLEMENTATION PLAN: CLEO TURBO DATA GAPS

> **STATUS: IMPLEMENTED** — All 9 phases were implemented on 2026-04-02.
> Code changes in: `schema.py`, `writer.py`, `transactions.py`, `properties.py`, `contacts.py`, `gw.py`, `types/index.ts`.
> Pending: first rebuild to populate the new tables with data.

Based on analysis of the codebase, clean-data structures, current database schema, compiler passes, and API routes, here is a step-by-step plan to capture all 76+ dropped fields. The plan is organized into 6 independently deployable phases.

---

## PHASE 1: RT Mailing Address Fields (Seller/Buyer Side)
**Complexity: Medium | Risk: Low | Effort: 2-3 days**

**Dependencies:** None
**Deployable:** Yes (independently)

### Problem
Clean-data RT transactions contain full mailing addresses for both seller and buyer sides (32 nested fields across address components, city, province, postal, geocode_string), but these are stored nowhere in the database or API responses.

### Solution

#### Schema Changes (schema.py)
Create new table `transaction_mailing_addresses`:

```sql
CREATE TABLE transaction_mailing_addresses (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id       TEXT NOT NULL REFERENCES transactions(source_id),
    side            TEXT NOT NULL,  -- 'seller' or 'buyer'
    display         TEXT,
    street_number   TEXT,
    street_name     TEXT,
    street_suffix   TEXT,
    street_direction TEXT,
    suite_type      TEXT,
    suite_number    TEXT,
    city            TEXT,
    province        TEXT,
    postal          TEXT,
    country         TEXT,
    geocode_string  TEXT,
    UNIQUE(source_id, side)
);
CREATE INDEX idx_tx_addr_source ON transaction_mailing_addresses(source_id);
CREATE INDEX idx_tx_addr_city ON transaction_mailing_addresses(city);
```

Also add two columns to `transactions` table for quick access:
- `seller_mailing_city TEXT` (denormalized for filters)
- `buyer_mailing_city TEXT` (denormalized for filters)

#### Writer.py Changes (Pass 3: Properties + Transactions)
**Lines 296-313:** After transaction INSERT, immediately insert mailing address records.

Add after line 313 (after tx_count increment):

```python
# Insert seller mailing address
seller_addr = rec.get('seller', {}).get('address', {})
if seller_addr.get('display'):
    conn.execute(
        "INSERT INTO transaction_mailing_addresses "
        "(source_id, side, display, street_number, street_name, street_suffix, "
        "street_direction, suite_type, suite_number, city, province, postal, "
        "country, geocode_string) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (source_id, 'seller',
         seller_addr.get('display', ''),
         seller_addr.get('components', {}).get('street_number', ''),
         seller_addr.get('components', {}).get('street_name', ''),
         seller_addr.get('components', {}).get('street_suffix', ''),
         seller_addr.get('components', {}).get('street_direction', ''),
         seller_addr.get('components', {}).get('suite_type', ''),
         seller_addr.get('components', {}).get('suite_number', ''),
         seller_addr.get('city', ''),
         seller_addr.get('province', ''),
         seller_addr.get('postal', ''),
         seller_addr.get('country', ''),
         seller_addr.get('geocode_string', ''))
    )

# Insert buyer mailing address
buyer_addr = rec.get('buyer', {}).get('address', {})
if buyer_addr.get('display'):
    conn.execute(
        "INSERT INTO transaction_mailing_addresses "
        "(source_id, side, display, street_number, street_name, street_suffix, "
        "street_direction, suite_type, suite_number, city, province, postal, "
        "country, geocode_string) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (source_id, 'buyer',
         buyer_addr.get('display', ''),
         buyer_addr.get('components', {}).get('street_number', ''),
         buyer_addr.get('components', {}).get('street_name', ''),
         buyer_addr.get('components', {}).get('street_suffix', ''),
         buyer_addr.get('components', {}).get('street_direction', ''),
         buyer_addr.get('components', {}).get('suite_type', ''),
         buyer_addr.get('components', {}).get('suite_number', ''),
         buyer_addr.get('city', ''),
         buyer_addr.get('province', ''),
         buyer_addr.get('postal', ''),
         buyer_addr.get('country', ''),
         buyer_addr.get('geocode_string', ''))
    )

# Denormalize cities to transactions for filtering
if seller_addr.get('city'):
    conn.execute("UPDATE transactions SET seller_mailing_city = ? WHERE source_id = ?",
                (seller_addr['city'], source_id))
if buyer_addr.get('city'):
    conn.execute("UPDATE transactions SET buyer_mailing_city = ? WHERE source_id = ?",
                (buyer_addr['city'], source_id))
```

#### API Changes (transactions.py)
**Lines 54-74:** Expand browse_transactions SELECT to include mailing cities.

**Lines 102-127:** In transaction_detail, join and include mailing addresses:

```python
# Get mailing addresses
seller_addr = db.execute(
    "SELECT * FROM transaction_mailing_addresses WHERE source_id = ? AND side = 'seller'",
    (source_id,)
).fetchone()
result["seller_mailing_address"] = dict(seller_addr) if seller_addr else None

buyer_addr = db.execute(
    "SELECT * FROM transaction_mailing_addresses WHERE source_id = ? AND side = 'buyer'",
    (source_id,)
).fetchone()
result["buyer_mailing_address"] = dict(buyer_addr) if buyer_addr else None
```

#### Frontend Types (types/index.ts)
Add to `TransactionDetail`:
```typescript
seller_mailing_address?: {
  display: string | null;
  street_number: string | null;
  street_name: string | null;
  street_suffix: string | null;
  street_direction: string | null;
  suite_type: string | null;
  suite_number: string | null;
  city: string | null;
  province: string | null;
  postal: string | null;
  country: string | null;
  geocode_string: string | null;
} | null;

buyer_mailing_address?: {
  display: string | null;
  street_number: string | null;
  street_name: string | null;
  street_suffix: string | null;
  street_direction: string | null;
  suite_type: string | null;
  suite_number: string | null;
  city: string | null;
  province: string | null;
  postal: string | null;
  country: string | null;
  geocode_string: string | null;
} | null;
```

#### Testing
- Run compiler: Verify 2 mailing address records per RT transaction
- Query: `SELECT COUNT(*) FROM transaction_mailing_addresses WHERE side = 'seller'`
- API: GET /transactions/{source_id} includes mailing addresses with all subfields
- Check real transaction with non-empty addresses

---

## PHASE 2: RT Party Metadata (Trade Name, Care Of, Law Firms, Companies)
**Complexity: Medium | Risk: Low | Effort: 2-3 days**

**Dependencies:** None
**Deployable:** Yes (independently)

### Problem
Each seller/buyer side has 4 metadata fields that could identify corporations or law firms (`trade_name`, `care_of`, `law_firms`, `companies`), but they're never extracted.

### Solution

#### Schema Changes (schema.py)
Create new table `transaction_party_metadata`:

```sql
CREATE TABLE transaction_party_metadata (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id       TEXT NOT NULL REFERENCES transactions(source_id),
    side            TEXT NOT NULL,  -- 'seller' or 'buyer'
    trade_name      TEXT,
    care_of         TEXT,
    law_firms_json  TEXT,  -- JSON array of strings
    companies_json  TEXT,  -- JSON array of strings
    UNIQUE(source_id, side)
);
CREATE INDEX idx_tx_meta_source ON transaction_party_metadata(source_id);
```

#### Writer.py Changes (Pass 3)
After inserting mailing addresses (end of address insertion block, before line 316 where transaction parties are processed):

```python
# Insert party metadata
seller_meta = rec.get('seller', {})
if seller_meta.get('trade_name') or seller_meta.get('care_of') or seller_meta.get('law_firms') or seller_meta.get('companies'):
    conn.execute(
        "INSERT INTO transaction_party_metadata "
        "(source_id, side, trade_name, care_of, law_firms_json, companies_json) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (source_id, 'seller',
         seller_meta.get('trade_name', ''),
         seller_meta.get('care_of', ''),
         json.dumps(seller_meta.get('law_firms', [])),
         json.dumps(seller_meta.get('companies', [])))
    )

buyer_meta = rec.get('buyer', {})
if buyer_meta.get('trade_name') or buyer_meta.get('care_of') or buyer_meta.get('law_firms') or buyer_meta.get('companies'):
    conn.execute(
        "INSERT INTO transaction_party_metadata "
        "(source_id, side, trade_name, care_of, law_firms_json, companies_json) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (source_id, 'buyer',
         buyer_meta.get('trade_name', ''),
         buyer_meta.get('care_of', ''),
         json.dumps(buyer_meta.get('law_firms', [])),
         json.dumps(buyer_meta.get('companies', [])))
    )
```

#### API Changes (transactions.py)
In transaction_detail (line 102-127), after party details:

```python
# Get party metadata
seller_meta = db.execute(
    "SELECT * FROM transaction_party_metadata WHERE source_id = ? AND side = 'seller'",
    (source_id,)
).fetchone()
if seller_meta:
    seller_meta_dict = dict(seller_meta)
    seller_meta_dict["law_firms"] = json.loads(seller_meta_dict.get("law_firms_json", "[]"))
    seller_meta_dict["companies"] = json.loads(seller_meta_dict.get("companies_json", "[]"))
    del seller_meta_dict["law_firms_json"]
    del seller_meta_dict["companies_json"]
    result["seller_party_metadata"] = seller_meta_dict
else:
    result["seller_party_metadata"] = None

buyer_meta = db.execute(
    "SELECT * FROM transaction_party_metadata WHERE source_id = ? AND side = 'buyer'",
    (source_id,)
).fetchone()
if buyer_meta:
    buyer_meta_dict = dict(buyer_meta)
    buyer_meta_dict["law_firms"] = json.loads(buyer_meta_dict.get("law_firms_json", "[]"))
    buyer_meta_dict["companies"] = json.loads(buyer_meta_dict.get("companies_json", "[]"))
    del buyer_meta_dict["law_firms_json"]
    del buyer_meta_dict["companies_json"]
    result["buyer_party_metadata"] = buyer_meta_dict
else:
    result["buyer_party_metadata"] = None
```

#### Frontend Types (types/index.ts)
Add to `TransactionDetail`:
```typescript
seller_party_metadata?: {
  trade_name: string | null;
  care_of: string | null;
  law_firms: string[];
  companies: string[];
} | null;

buyer_party_metadata?: {
  trade_name: string | null;
  care_of: string | null;
  law_firms: string[];
  companies: string[];
} | null;
```

#### Testing
- Verify 2 metadata records per RT transaction
- Find transaction with non-empty trade_name or law_firms
- API: GET /transactions/{source_id} returns party metadata

---

## PHASE 3: RT Site/Parcel Refined Fields (PIN Display, ARN Display, Method, Location, Surface Rights)
**Complexity: Low | Risk: Very Low | Effort: 1-2 days**

**Dependencies:** None
**Deployable:** Yes (independently)

### Problem
Clean-data RT has detailed parcel resolution fields (`pin.display`, `arn.display`, `pin.multiple`, `parcel.method`, `site.location`, `site.surface_rights_only`) but writer.py only uses `api_format` versions and ignores resolution metadata.

### Solution

#### Schema Changes (schema.py)
Add 6 columns to `transactions` table:

```python
# In transactions CREATE TABLE, add:
pin_display     TEXT,
arn_display     TEXT,
pin_multiple    INTEGER DEFAULT 0,
parcel_method   TEXT,
location        TEXT,
surface_rights_only INTEGER DEFAULT 0,
```

#### Writer.py Changes (Pass 3)
**Lines 235-241:** Expand transaction INSERT to capture display and metadata fields.

Modify lines 296-313 transaction INSERT:

```python
conn.execute(
    "INSERT OR IGNORE INTO transactions (source_id, property_id, arn, sale_date, sale_price, "
    "transaction_note, display_address, city, region, postal, seller_parties, buyer_parties, "
    "seller_phone, buyer_phone, description, acreage, pin, legal_description, "
    "pin_display, arn_display, pin_multiple, parcel_method, location, surface_rights_only, "
    "consideration_json, broker_json, photos_json, source_folder) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
    "?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
    (source_id, property_id, arn,
     tx.get('sale_date'), tx.get('sale_price'), tx.get('transaction_note', ''),
     display_address, tx.get('city', ''), tx.get('region', ''), prop.get('postal', ''),
     json.dumps(seller_parties), json.dumps(buyer_parties),
     rec.get('seller', {}).get('phone', ''), rec.get('buyer', {}).get('phone', ''),
     rec.get('description', {}).get('description', ''),
     site.get('acreage'), pin, site.get('legal_description', ''),
     site.get('pin', {}).get('display', ''),  # NEW: pin_display
     site.get('arn', {}).get('display', ''),  # NEW: arn_display
     site.get('pin', {}).get('multiple', 0) or 0,  # NEW: pin_multiple (boolean as 0/1)
     parcel_info.get('method', ''),  # NEW: parcel_method
     site.get('location', ''),  # NEW: location
     site.get('surface_rights_only', 0) or 0,  # NEW: surface_rights_only (boolean as 0/1)
     json.dumps(rec.get('consideration', {})),
     json.dumps(rec.get('broker', {})),
     json.dumps(rec.get('photos', {})),
     rec.get('source_folder', ''))
)
```

#### API Changes (transactions.py)
**Lines 54-74:** browse_transactions already returns pin (api_format); no additional changes needed for browse.

**Lines 102-127:** transaction_detail already returns all columns via `SELECT *`, so display fields will be included automatically.

#### Frontend Types (types/index.ts)
Add to `TransactionDetail`:
```typescript
pin_display: string | null;
arn_display: string | null;
pin_multiple: boolean;
parcel_method: string | null;
location: string | null;
surface_rights_only: boolean;
```

#### Testing
- Verify fields populated in transactions table
- Query with .get_parcel_method = 'spatial_geocode' or 'arn_cache'
- API: Check transaction detail response for all 6 new fields

---

## PHASE 4: RT Description & Site Enhanced Fields (More Info URL, PIN/ARN Structured, Surface Rights)
**Complexity: Low | Risk: Very Low | Effort: 1-2 days**

**Dependencies:** None (but complements Phase 3)
**Deployable:** Yes (independently)

### Problem
Clean-data RT `description.more_info_url` is ignored. Already addressed PIN/ARN in Phase 3.

### Solution

#### Schema Changes (schema.py)
Add 1 column to `transactions` table:

```python
more_info_url   TEXT,
```

#### Writer.py Changes (Pass 3)
Modify the transaction INSERT from Phase 3 to include:

```python
description.get('more_info_url', '')  # Add to VALUES list
```

Add column to INSERT parameter list between `surface_rights_only` and `consideration_json`.

#### API Changes
Automatic (via SELECT *)

#### Frontend Types
Add to `TransactionDetail`:
```typescript
more_info_url: string | null;
```

#### Testing
- Query transactions where more_info_url IS NOT NULL
- Verify URL format validation if needed

---

## PHASE 5: RT Consideration & Broker Data Denormalization
**Complexity: Medium | Risk: Medium | Effort: 2-3 days**

**Dependencies:** None
**Deployable:** Yes (independently)

### Problem
Clean-data RT has rich `consideration` (cash, debt, chattels, charges) and `broker` (brokerage, agents, phone) data currently stored as unparsed JSON blobs. This makes filtering/reporting difficult.

### Solution

#### Schema Changes (schema.py)

Create new tables:

```sql
CREATE TABLE transaction_consideration (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id       TEXT NOT NULL UNIQUE REFERENCES transactions(source_id),
    cash            INTEGER,
    debt            INTEGER,
    chattels        INTEGER,
    other           INTEGER,
    charges_json    TEXT,  -- JSON array of strings
    created_at      TEXT DEFAULT (datetime('now'))
);
CREATE INDEX idx_tx_cons_source ON transaction_consideration(source_id);
CREATE INDEX idx_tx_cons_cash ON transaction_consideration(cash);

CREATE TABLE transaction_brokers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id       TEXT NOT NULL REFERENCES transactions(source_id),
    broker_name     TEXT,
    phone           TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE transaction_broker_agents (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    broker_id       INTEGER NOT NULL REFERENCES transaction_brokers(id),
    agent_name      TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_tx_broker_source ON transaction_brokers(source_id);
CREATE INDEX idx_tx_agent_broker ON transaction_broker_agents(broker_id);
```

#### Writer.py Changes (Pass 3)
After transaction INSERT, process consideration and broker:

```python
# Extract and denormalize consideration
consideration = rec.get('consideration', {})
if consideration:
    conn.execute(
        "INSERT OR REPLACE INTO transaction_consideration "
        "(source_id, cash, debt, chattels, other, charges_json) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (source_id,
         consideration.get('cash'),
         consideration.get('debt'),
         consideration.get('chattels'),
         consideration.get('other'),
         json.dumps(consideration.get('charges', [])))
    )

# Extract and denormalize brokers
broker_data = rec.get('broker', {})
brokers = broker_data.get('brokers', [])
for broker in brokers:
    broker_name = broker.get('brokerage', '')
    broker_phone = broker.get('phone', '')
    agents = broker.get('agents', [])
    
    if broker_name or broker_phone or agents:
        cursor = conn.execute(
            "INSERT INTO transaction_brokers (source_id, broker_name, phone) "
            "VALUES (?, ?, ?)",
            (source_id, broker_name, broker_phone)
        )
        broker_id = cursor.lastrowid
        
        for agent_name in agents:
            conn.execute(
                "INSERT INTO transaction_broker_agents (broker_id, agent_name) "
                "VALUES (?, ?)",
                (broker_id, agent_name)
            )
```

#### API Changes (transactions.py)
In transaction_detail, after loading JSON fields:

```python
# Parse consideration
consideration_rec = db.execute(
    "SELECT * FROM transaction_consideration WHERE source_id = ?", (source_id,)
).fetchone()
if consideration_rec:
    cons_dict = dict(consideration_rec)
    cons_dict["charges"] = json.loads(cons_dict.get("charges_json", "[]"))
    del cons_dict["charges_json"]
    del cons_dict["id"]
    del cons_dict["created_at"]
    result["consideration"] = cons_dict
else:
    result["consideration"] = None

# Parse brokers with agents
brokers_result = []
broker_recs = db.execute(
    "SELECT * FROM transaction_brokers WHERE source_id = ? ORDER BY id",
    (source_id,)
).fetchall()
for broker_rec in broker_recs:
    broker_dict = dict(broker_rec)
    agents = db.execute(
        "SELECT agent_name FROM transaction_broker_agents WHERE broker_id = ? ORDER BY id",
        (broker_rec['id'],)
    ).fetchall()
    broker_dict["agents"] = [a["agent_name"] for a in agents]
    del broker_dict["id"]
    del broker_dict["source_id"]
    del broker_dict["created_at"]
    brokers_result.append(broker_dict)
result["brokers"] = brokers_result
```

#### Frontend Types (types/index.ts)
Update `BrokerData`:
```typescript
export interface BrokerData {
  brokers?: {
    broker_name?: string | null;
    phone?: string | null;
    agents?: string[];
  }[];
}
```

Add to `TransactionDetail`:
```typescript
consideration?: {
  cash: number | null;
  debt: number | null;
  chattels: number | null;
  other: number | null;
  charges: string[];
} | null;

brokers?: {
  broker_name: string | null;
  phone: string | null;
  agents: string[];
}[];
```

#### Testing
- Run compiler and verify records in transaction_consideration and transaction_brokers
- API: GET /transactions/{source_id} returns properly structured consideration and brokers
- Check transaction with multiple brokers and agents

---

## PHASE 6: GW Pipeline Gaps (Sales History, Registry Metadata, Quality Flags, Assessment Denormalization)
**Complexity: High | Risk: Medium | Effort: 4-5 days**

**Dependencies:** None
**Deployable:** Yes (independently, but high impact)

### Problem
GW pipeline drops 17+ critical fields:
- **Entire `sales_history` array** (5 fields: date, amount, type, party_to, notes) — CRITICAL
- **Registry metadata**: land_registry_status, registration_type, lro
- **Quality flags**: has_mpac_data, is_active, address_parsed, parcel_resolved, issues
- **Property/Assessment municipality** (appears in 2 places)
- **Assessment fields**: property_code, frontage, depth, site_area (partially captured, need normalization)

### Solution

#### Schema Changes (schema.py)

Create new tables:

```sql
CREATE TABLE gw_sales_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    gw_id           TEXT NOT NULL REFERENCES gw_assessments(gw_id),
    sale_date       TEXT,
    amount          INTEGER,
    sale_type       TEXT,  -- 'Transfer', 'Mortgage', etc.
    party_to        TEXT,  -- Name of party receiving the property
    notes           TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);
CREATE INDEX idx_gw_sales_gw_id ON gw_sales_history(gw_id);
CREATE INDEX idx_gw_sales_date ON gw_sales_history(sale_date);
CREATE INDEX idx_gw_sales_amount ON gw_sales_history(amount);
```

Modify `gw_assessments` table to add:

```python
# Add these columns to gw_assessments CREATE TABLE:
land_registry_status TEXT,
registration_type    TEXT,
lro                  TEXT,
municipality         TEXT,
has_mpac_data        INTEGER DEFAULT 0,
is_active            INTEGER DEFAULT 0,
address_parsed       INTEGER DEFAULT 0,
parcel_resolved      INTEGER DEFAULT 0,
```

Modify `properties` table to add:

```python
# Add to properties CREATE TABLE:
gw_municipality      TEXT,
```

#### Writer.py Changes (Pass 5: GW Assessments)
**Lines 500-615:** Expand GW data extraction and denormalization.

Modify assessment INSERT (lines 583-604) to include new fields:

```python
conn.execute(
    "INSERT OR IGNORE INTO gw_assessments (id, gw_id, property_id, arn, pin, "
    "assessed_value, valuation_date, zoning, property_code, property_description, "
    "ownership_type, frontage_ft, depth_ft, site_area_sqft, acreage, "
    "owner_name, owner_mailing, legal_description, source_file, "
    "land_registry_status, registration_type, lro, municipality, "
    "has_mpac_data, is_active, address_parsed, parcel_resolved) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
    (a_id, gw_id, a_property_id, arn_api, gw.get('pin', ''),
     assessment.get('assessed_value'),
     assessment.get('valuation_date', ''),
     assessment.get('zoning', ''),
     assessment.get('property_code', ''),
     assessment.get('property_description', ''),
     gw.get('registry', {}).get('ownership_type', ''),
     assessment.get('frontage_ft'),
     assessment.get('depth_ft'),
     assessment.get('site_area_sqft'),
     assessment.get('acreage'),
     assessment.get('owner_names_mpac', ''),
     assessment.get('owner_mailing_address', ''),
     assessment.get('legal_description', ''),
     gw.get('source_file', ''),
     gw.get('registry', {}).get('land_registry_status', ''),  # NEW
     gw.get('registry', {}).get('registration_type', ''),     # NEW
     gw.get('registry', {}).get('lro', ''),                   # NEW
     assessment.get('municipality', ''),                       # NEW
     1 if gw.get('quality', {}).get('has_mpac_data') else 0,  # NEW
     1 if gw.get('quality', {}).get('is_active') else 0,      # NEW
     1 if gw.get('quality', {}).get('address_parsed') else 0, # NEW
     1 if gw.get('quality', {}).get('parcel_resolved') else 0) # NEW
)
```

After the assessment loop, insert sales history (before line 607):

```python
# Insert sales history
sales_history = gw.get('sales_history', [])
for sale in sales_history:
    conn.execute(
        "INSERT INTO gw_sales_history "
        "(gw_id, sale_date, amount, sale_type, party_to, notes) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (gw_id,
         sale.get('date', ''),
         sale.get('amount'),
         sale.get('type', ''),
         sale.get('party_to', ''),
         sale.get('notes', ''))
    )
```

Also enrich properties table with municipality (lines 520-545, in the GW enrich section):

```python
if updates:
    # Add municipality update
    gw_municipality = gw_prop.get('municipality', '')
    if gw_municipality:
        updates.append("gw_municipality = ?")
        params.append(gw_municipality)
    
    params.append(property_id)
    conn.execute(
        f"UPDATE properties SET {', '.join(updates)} WHERE id = ?",
        params
    )
```

And when creating new GW properties (lines 555-567):

```python
conn.execute(
    "INSERT OR IGNORE INTO properties (id, arn, display_address, city, postal, "
    "current_owner_name, transaction_count, primary_property_type, "
    "gw_municipality, lat, lng, parcel_geojson) "
    "VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?)",
    (pid, resolved_arn,
     gw_prop.get('display_address', ''),
     gw_prop.get('city', ''),
     gw_prop.get('postal', ''),
     gw_owner.get('name', ''),
     gw.get('registry', {}).get('property_type', '').lower() or 'commercial',
     gw_prop.get('municipality', ''),  # NEW
     p_lat, p_lng, parcel_geojson)
)
```

#### API Changes (gw.py)
**Lines 34-40:** Expand browse_assessments SELECT to include new fields:

```python
f"SELECT id, gw_id, property_id, arn, pin, assessed_value, valuation_date, "
f"zoning, property_code, property_description, ownership_type, "
f"frontage_ft, depth_ft, site_area_sqft, acreage, owner_name, "
f"land_registry_status, registration_type, lro, municipality, "
f"has_mpac_data, is_active, address_parsed, parcel_resolved "
f"FROM gw_assessments WHERE {where} ORDER BY gw_id LIMIT ? OFFSET ?"
```

**Lines 75-81:** Update gw_detail to include sales history:

```python
@router.get("/{gw_id}")
def gw_detail(gw_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    """Single GW assessment detail with sales history."""
    row = db.execute("SELECT * FROM gw_assessments WHERE id = ?", (gw_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="GW assessment not found")

    result = dict(row)
    
    # Get sales history
    sales = db.execute(
        "SELECT sale_date, amount, sale_type, party_to, notes FROM gw_sales_history "
        "WHERE gw_id = ? ORDER BY sale_date DESC",
        (gw_id,)
    ).fetchall()
    result["sales_history"] = [dict(s) for s in sales]
    
    return result
```

Add new endpoint for browse by GW ID (after gw_detail):

```python
@router.get("/gw-id/{gw_id}")
def gw_by_gw_id(gw_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    """Get all assessments for a GW ID (primary may have multiple assessments)."""
    rows = db.execute(
        "SELECT * FROM gw_assessments WHERE gw_id = ? ORDER BY id",
        (gw_id,)
    ).fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail="GW ID not found")
    
    result = [dict(r) for r in rows]
    
    # Get sales history for the GW ID (not per assessment)
    sales = db.execute(
        "SELECT sale_date, amount, sale_type, party_to, notes FROM gw_sales_history "
        "WHERE gw_id = ? ORDER BY sale_date DESC",
        (gw_id,)
    ).fetchall()
    
    return {"assessments": result, "sales_history": [dict(s) for s in sales]}
```

#### Frontend Types (types/index.ts)

Create new interface:

```typescript
export interface GwAssessment {
  id: string;
  gw_id: string;
  property_id: string | null;
  arn: string | null;
  pin: string | null;
  assessed_value: number | null;
  valuation_date: string | null;
  zoning: string | null;
  property_code: string | null;
  property_description: string | null;
  ownership_type: string | null;
  frontage_ft: number | null;
  depth_ft: number | null;
  site_area_sqft: number | null;
  acreage: number | null;
  owner_name: string | null;
  owner_mailing: string | null;
  legal_description: string | null;
  source_file: string | null;
  land_registry_status: string | null;  // NEW
  registration_type: string | null;     // NEW
  lro: string | null;                   // NEW
  municipality: string | null;          // NEW
  has_mpac_data: boolean;               // NEW
  is_active: boolean;                   // NEW
  address_parsed: boolean;              // NEW
  parcel_resolved: boolean;             // NEW
  created_at: string;
}

export interface GwSaleHistory {
  sale_date: string | null;
  amount: number | null;
  sale_type: string | null;
  party_to: string | null;
  notes: string | null;
}

export interface GwAssessmentDetail extends GwAssessment {
  sales_history: GwSaleHistory[];
}

export interface GwByIdResponse {
  assessments: GwAssessment[];
  sales_history: GwSaleHistory[];
}
```

Add to PropertyBrowseItem:
```typescript
owner_group_id: string | null;  // NEW
```

Add to PropertyDetail (if not already present):
```typescript
gw_municipality: string | null;
```

#### Testing
- Run compiler: Verify sales_history records created
- Query: `SELECT COUNT(*) FROM gw_sales_history WHERE gw_id = 'GW00400'`
- API: GET /gw/{gw_id} returns all new fields + sales_history
- API: GET /gw/browse includes property_code, frontage, depth, municipality in results
- Frontend: GW detail view displays all registry metadata and quality flags
- Check property detail that has GW data to verify gw_municipality populated

---

## PHASE 7: Contact Browse Enhancement (Email, Mobile)
**Complexity: Low | Risk: Very Low | Effort: 1 day**

**Dependencies:** None (easy win)
**Deployable:** Yes (independently)

### Problem
ContactBrowseItem currently missing `email` and `mobile` fields even though they exist in the schema.

### Solution

#### API Changes (contacts.py)
**Lines 39-44:** Expand SELECT in browse_contacts:

```python
rows = db.execute(
    f"SELECT id, display_name, phone, email, mobile, company_name, status, transaction_count, "
    f"first_seen_date, last_seen_date, job_title "
    f"FROM contacts WHERE {where} ORDER BY {sort} {order} LIMIT ? OFFSET ?",
    params + [per_page, offset]
).fetchall()
```

#### Frontend Types (types/index.ts)
Update `ContactBrowseItem`:

```typescript
export interface ContactBrowseItem {
  id: string;
  display_name: string;
  phone: string | null;
  email: string | null;           // NEW
  mobile: string | null;          // NEW
  company_name: string | null;
  status: string;
  transaction_count: number;
  first_seen_date: string | null;
  last_seen_date: string | null;
  job_title: string | null;
}
```

#### Testing
- API: GET /contacts returns email and mobile in browse results
- Frontend: Contact browse table displays email/mobile columns

---

## PHASE 8: Properties Browse Enhancement (Owner Group ID)
**Complexity: Very Low | Risk: Very Low | Effort: <1 day**

**Dependencies:** None
**Deployable:** Yes (immediately)

### Problem
PropertyBrowseItem missing owner_group_id even though it's in the database.

### Solution

#### API Changes (properties.py)
**Lines 67-72:** Expand SELECT in browse_properties:

```python
rows = db.execute(
    f"SELECT p.id, p.arn, p.display_address, p.city, p.region, p.most_recent_sale_date, "
    f"p.most_recent_sale_price, p.current_owner_name, p.current_owner_group_id, "
    f"p.transaction_count, p.lat, p.lng "
    f"FROM properties p WHERE {where} ORDER BY p.{sort} {order} LIMIT ? OFFSET ?",
    params + [per_page, offset]
).fetchall()
```

#### Frontend Types
Update `PropertyBrowseItem` to include:

```typescript
owner_group_id: string | null;  // NEW
```

#### Testing
- API: GET /properties returns owner_group_id
- Can now filter/link properties to their owning groups

---

## PHASE 9: Transaction Party Type Reconciliation
**Complexity: Low | Risk: Low | Effort: 1-2 days**

**Dependencies:** All earlier phases (to understand impact)
**Deployable:** Yes (independently)

### Problem
TypeScript types define `seller_parties` and `buyer_parties` as `string[] | null` in some places but they're actually returned as `string[]` (JSON arrays parsed). Type mismatch in `PropertyTransactionParty` which has `contact_email` field never populated.

### Solution

#### Frontend Types (types/index.ts)
Fix `PropertyTransactionParty`:

```typescript
export interface PropertyTransactionParty {
  side: "buyer" | "seller";
  party_name: string | null;
  contact_title: string | null;
  phone: string | null;
  contact_id: string | null;
  group_id: string | null;
  contact_name: string | null;
  contact_phone: string | null;
  // REMOVED: contact_email (not currently populated by API)
  contact_email?: string | null;  // Optional, for future use
}
```

Fix `TransactionBrowseItem` and `TransactionDetail`:

```typescript
seller_parties: string[];  // CHANGE from string[] | null
buyer_parties: string[];   // CHANGE from string[] | null
```

Update `BrowseResponse`, `SearchResponse`, `PropertyDetail.transactions` to ensure consistent null handling.

#### Testing
- Verify no TypeScript errors in frontend builds
- Check transaction browse and detail views render correctly

---

## CRITICAL SEQUENCING & DEPLOYMENT STRATEGY

### Recommended Deployment Order

**Week 1 (Low Risk):**
1. **Phase 8** (30 min) - Properties browse owner_group_id
2. **Phase 7** (1 day) - Contact browse email/mobile
3. **Phase 3** (1-2 days) - RT site fields (PIN display, method, location)
4. **Phase 4** (1 day) - RT description URL

**Week 2 (Medium Risk):**
5. **Phase 1** (2-3 days) - RT mailing addresses
6. **Phase 2** (2-3 days) - RT party metadata (trade_name, law_firms, etc.)

**Week 3 (High Impact):**
7. **Phase 5** (2-3 days) - RT consideration & broker denormalization
8. **Phase 6** (4-5 days) - GW pipeline (sales history, registry metadata, quality flags)

**Week 4 (Cleanup):**
9. **Phase 9** (1-2 days) - TypeScript type reconciliation & testing

### Pre-Deployment Checklist (Each Phase)

Before deploying schema changes:
- [ ] Back up SQLite database
- [ ] Test migration on development copy
- [ ] Verify no foreign key constraint violations
- [ ] Check compiler run time with new data processing

Before deploying API changes:
- [ ] Run FastAPI validation
- [ ] Test all affected endpoints with curl/Postman
- [ ] Verify response JSON structure matches updated types

Before deploying frontend changes:
- [ ] Build TypeScript with no errors
- [ ] Update all components using affected types
- [ ] Test browse and detail views on all modified endpoints
- [ ] Check FTS indexes include new queryable fields if applicable

---

## RISK MATRIX & MITIGATION

| Phase | Risk | Mitigation |
|-------|------|-----------|
| 1-4 | Low | Independent tables, no FK impact; test on dev first |
| 5 | Medium | Broker/consideration parsing; validate JSON structure before insert |
| 6 | High | GW sales_history is CRITICAL; verify data exists in clean-data first |
| 7-8 | Very Low | Schema read-only additions; no data loss risk |
| 9 | Low | TypeScript types; caught by compiler |

---

## EXPECTED IMPACT POST-COMPLETION

- **Database:** 76+ fields now captured and queryable
- **APIs:** Full property, transaction, contact, and GW assessment data available
- **Frontend:** Browse views show owner groups, contact details; detail views show comprehensive transaction history with consideration, brokers, mailing addresses
- **Reporting:** Can now filter/analyze by consideration amounts, broker involvement, GW registry status, sales history across time
- **Data Integrity:** No more "phantom" fields in clean-data never reaching end users

---

## TESTING STRATEGY

### Compiler Verification
```sql
-- Verify Phase 1
SELECT COUNT(*) FROM transaction_mailing_addresses; -- Should = 2x RT transactions

-- Verify Phase 2
SELECT COUNT(*) FROM transaction_party_metadata; -- Should = 2x RT transactions

-- Verify Phase 5
SELECT COUNT(*) FROM transaction_consideration WHERE cash > 0;
SELECT COUNT(*) FROM transaction_brokers;

-- Verify Phase 6
SELECT COUNT(*) FROM gw_sales_history; -- Should > 0
SELECT COUNT(*) FROM gw_assessments WHERE land_registry_status IS NOT NULL;
```

### API Verification
- Each browse endpoint returns expected fields
- Each detail endpoint includes new nested objects
- FTS indexes still function (verify search endpoints)
- No 500 errors on affected routes

### Frontend Verification
- TypeScript compiles with no errors
- Browse tables display new columns
- Detail pages show new sections
- No console errors on loaded pages

---

### Critical Files for Implementation

1. **/sessions/trusting-charming-dijkstra/mnt/cleo-turbo/cleo/database/schema.py** - All schema changes (8 new tables, 20+ new columns)
2. **/sessions/trusting-charming-dijkstra/mnt/cleo-turbo/cleo/compiler/writer.py** - All data extraction and denormalization (5 passes modified, ~200 lines added)
3. **/sessions/trusting-charming-dijkstra/mnt/cleo-turbo/cleo/web/routes/transactions.py** - Transaction API enhancements (browse, detail)
4. **/sessions/trusting-charming-dijkstra/mnt/cleo-turbo/cleo/web/routes/gw.py** - GW API enhancements (browse, detail, sales history endpoint)
5. **/sessions/trusting-charming-dijkstra/mnt/cleo-turbo/frontend/src/types/index.ts** - TypeScript type updates (9 new interfaces, 30+ new fields)
