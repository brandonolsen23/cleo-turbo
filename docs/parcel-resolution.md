# Parcel Resolution

Every data source in Cleo resolves to a parcel (identified by a 20-digit ARN). This document describes how records without an ARN get linked to parcels.

## Resolution Chain

Records are resolved in confidence order. Each method is tried; the first success wins.

### 1. ARN → Cache (fastest, no API call)
- Check `clean-data/parcels/{arn}.json`
- If file exists → resolved immediately
- ~67K parcels cached from previous runs

### 2. ARN → API (deterministic)
- Query AgMaps: `query_by_arn(arn)`
- Returns exactly 0 or 1 result
- Cache the parcel geometry on success
- Rate: 0.4s between requests

### 3. PIN → ARN Bridge (no API credits)
- Load GW clean records to build `{pin: arn}` lookup table
- ~673 PIN→ARN pairs from GeoWarehouse data
- Grows automatically as more GW HTML is captured
- Method: `pin_gw`

### 4. Geocode → Spatial (Mapbox + AgMaps)
- Geocode the address string via Mapbox → get lat/lng
- Spatial query AgMaps: `query_by_point(lat, lng)` → find parcel
- Only for tier-1 addresses (street number + street name + city)
- Method: `spatial_geocode`

### 5. Unresolved
- Record has no usable identifier or address
- Flagged for manual review
- Typically rural properties (concession roads, lot numbers)

## Geocoding Rules

**Pre-flight validation** — before any API calls:
1. Build the full geocode queue
2. Filter to tier-1 addresses only (has street number + name + city)
3. Deduplicate by geocode_string (same address = 1 API call)
4. Report exact count and estimated API usage
5. Save queue to `engines/rt/pipeline/geocode_queue.json`
6. User reviews and approves before execution

**Rate limiting:**
- 5 requests/second (200ms between requests)
- Half of Mapbox's 600/min limit — conservative
- On 429: **STOP immediately** — our rate is wrong, fix it
- On 5xx: pause 5 seconds, retry up to 3 times

**Result validation:**
- Relevance score ≥ 0.8
- Result must be in Ontario
- Result must be `address` type
- If validation fails → skip, don't waste spatial query

**Incremental saves:**
- Results saved every 100 geocodes
- Fully resumable — restart picks up where it left off

## Running the Pipeline

```bash
# Step 1: PIN→ARN bridge (zero API calls)
cd engines/rt && python -m parcel_resolver.pin_bridge

# Step 2: Build geocode queue (zero API calls)
python -m parcel_resolver.geocode --preflight

# Step 3: Review queue
cat pipeline/geocode_queue.json | python -m json.tool | head -20

# Step 4: Run geocoding (uses Mapbox credits)
python -m parcel_resolver.geocode --run

# Step 5: Run spatial resolver on geocoded results
python -m parcel_resolver.resolve

# Step 6: Recompile database
cd ../.. && python -c "from cleo.database.connection import get_connection; from cleo.compiler.writer import run_compiler; conn = get_connection(); run_compiler(conn); conn.close()"
```

## API Credits Budget

| Service | Free Tier | Our Rate | Notes |
|---|---|---|---|
| Mapbox Geocoding | 100K/month | 5/sec | Resets 1st of month |
| AgMaps Parcel | Unlimited | 2.5/sec | Government service, no billing |

## Data Flow

```
RT Record (no ARN)
  │
  ├─ Has PIN? → GW Lookup → ARN found? → Cache/API → Resolved
  │
  ├─ Has address? → Geocode (Mapbox) → lat/lng
  │                    │
  │                    └─ Spatial Query (AgMaps) → Parcel → Resolved
  │
  └─ Neither → Unresolved (manual review)
```
