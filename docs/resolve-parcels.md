# Resolve Parcels — Stage Reference

> How the RT engine links transactions to physical parcels via the Ontario provincial
> AgMaps API. This document covers the data flow, decision logic, caching, token
> management, and the distinction between bulk and incremental runs.
>
> Last updated: 2026-03-26

---

## What This Stage Does

Every Realtrack transaction references a piece of land. The Resolve Parcels stage
takes the ARN, PIN, or address from each record and resolves it to a **parcel polygon**
— the actual boundary of the land that was transacted. This polygon lives in
`clean-data/parcels/` and is referenced by every Clean Record that touches that parcel.

The parcel is the **universal linker** in Cleo. It's how transactions, POIs, and
GeoWarehouse data all connect to the same physical piece of land.

---

## Data Flow

```
INPUTS                              STAGE                               OUTPUTS
──────                              ─────                               ───────

engines/rt/pipeline/                                                    clean-data/parcels/
  addresses/*.json  ──────────┐                                         {arn}.json
  (126K files)                │     ┌──────────────────────┐            (one per unique parcel,
  Each has:                   ├────→│   Resolve Parcels    │──────────→  grows permanently)
  • arn.api_format            │     │                      │
  • pin.api_format            │     │  1. Check cache      │            engines/rt/pipeline/
  • geocode_string            │     │  2. Query API        │              parcel_links/*.json
                              │     │  3. Cache result     │──────────→  (one per addresses file,
clean-data/parcels/           │     │  4. Write link       │              links record to parcel)
  {arn}.json  ────────────────┘     └──────────────────────┘
  (parcel cache — currently
   67,137 from v3 seed)

                                         │
                                         │ queries
                                         ▼

                                    AgMaps API
                                    (Ontario provincial
                                     parcel service)
```

### Input: `engines/rt/pipeline/addresses/*.json`

Each file has `arn` and `pin` objects with an `api_format` field (the normalized
query-ready format), plus `geocode_string` on each address for spatial fallback.
Only ARN is queryable on the AgMaps API. PIN is stored but cannot be used for
direct parcel lookups on this endpoint.

Example:
```json
{
  "rt_id": "RT100000",
  "arn": { "original": "19 04 023 100 06300", "api_format": "19040231000630000000" },
  "pin": { "original": "00063-0124", "api_format": "000630124" },
  "property": {
    "addresses": [{
      "geocode_string": "325149 Norwich Road, Norwich, Ontario N0J 1P0, Canada",
      "geocodable": true
    }]
  }
}
```

### Input: `clean-data/parcels/{arn}.json` (the parcel cache)

One file per unique parcel. Seeded from v3 data (67,137 files). Grows permanently
as new parcels are discovered via API. Never deleted by engine rebuilds.

```json
{
  "arn": "19040231000630000000",
  "geometry": { "type": "Polygon", "coordinates": [[...]] },
  "centroid": [42.866, -80.722],
  "attributes": { "OGF_ID": 1932376313, ... }
}
```

### Output: `engines/rt/pipeline/parcel_links/{filename}.json`

One file per addresses file. Records the resolution result for that record.

```json
{
  "rt_id": "RT100000",
  "resolved_arn": "19040231000630000000",
  "method": "arn_cache",
  "parcel_file": "19040231000630000000.json"
}
```

If unresolved:
```json
{
  "rt_id": "RT100000",
  "resolved_arn": null,
  "method": "unresolved",
  "reason": "no_arn_no_pin_no_geocodable_address"
}
```

The Compile stage reads both `addresses/` and `parcel_links/` to build Clean Records.

---

## Resolution Chain

For each record, the resolver tries methods in order of confidence. It stops at the
first success.

```
Record has ARN?
  │
  ├─ YES ─→ [1] Check parcel cache for ARN
  │              ├─ HIT  → resolved (method: arn_cache)
  │              └─ MISS → [2] Query API by ARN
  │                            ├─ FOUND → cache parcel, resolved (method: arn_api)
  │                            └─ NOT FOUND → fall through to spatial
  │
  └─ Has geocodable address? (ARN failed or absent)
       │
       ├─ YES ─→ [3] Geocode address to lat/lng (fresh, not reusing old coords)
       │              → [4] Query API by spatial point
       │                    ├─ FOUND → extract ARN, cache parcel,
       │                    │          resolved (method: spatial_api)
       │                    └─ NOT FOUND → unresolved
       │
       └─ NO ──→ unresolved (method: unresolved, reason: no identifiers)
```

### PIN — Why It's Not In The Chain

The AgMaps Assessment Parcel layer (MapServer/0) does **not** have a PIN field.
The only queryable identifier is `ASSESSMENT_ROLL_NUMBER`. Querying by `PIN`
returns HTTP 400 "Failed to execute query."

The v3 codebase had a `query_by_pin()` method but it silently failed on this
endpoint — the v3 parcel cache shows sources of `api_arn` and `api_spatial`
only, never `api_pin`. PIN resolution never actually worked via direct query.

Records with PIN but no ARN (~22% of data) must be resolved via spatial queries
(geocode the property address to coordinates, then point-in-polygon query).
A separate PIN-to-ARN lookup service could be added in the future if one is found.

### Method Confidence Levels

| Method | Confidence | Description |
|---|---|---|
| `arn_cache` | Highest | ARN matched a cached parcel. No API call needed. |
| `arn_api` | High | ARN queried against API, parcel found. Deterministic — ARN is a unique key. |
| `spatial_api` | Low | Address geocoded, point used for spatial query. Depends on geocode accuracy. |
| `unresolved` | None | All methods exhausted. |

### Why This Order

- **ARN is a unique key.** One ARN = one parcel. If we have an ARN and it's in the
  cache, we're done in microseconds. If we query the API, we get exactly one result.
  No ambiguity.

- **Spatial is a last resort.** Geocoding introduces error (wrong side of the street,
  centroid of a postal code instead of the actual address). The spatial query then
  returns whichever parcel contains that point, which may not be the right one for
  ambiguous locations. We only use this when we have nothing better.

---

## The Parcel Cache

`clean-data/parcels/` is the permanent parcel store. It has three properties:

1. **Keyed by ARN.** One file per unique 20-digit ARN. Filename = ARN.
2. **Grows permanently.** New parcels are added, never removed. An engine rebuild
   does not touch the parcel cache.
3. **Shared across all sources.** RT, OSM, Brand, and GeoWarehouse records all
   reference the same parcel files. The cache is source-agnostic.

### Current State

| Metric | Value |
|---|---|
| Parcels in cache (from v3 seed) | 67,137 |
| Unique ARNs in our RT data | 49,787 |
| Already cached | 36,442 (73.2%) |
| ARNs needing API lookup | 13,345 (26.8%) |
| Records with no ARN (need spatial) | ~43,381 (34.4% of 126K) |

### Cache Lookup

Before any API call, the resolver checks if `clean-data/parcels/{arn}.json` exists.
This is a filesystem check — fast and simple. No in-memory index needed.

Records without an ARN cannot use the cache directly — they must be resolved via
spatial queries, which will discover an ARN and add it to the cache for future use.

---

## AgMaps API

### Service

Ontario's Assessment Parcel Map layer, served via ArcGIS REST:

```
https://ws.lioservices.lrc.gov.on.ca/arcgis4/rest/services/AIA/Assessment_Parcel_Map/MapServer/0
```

All queries append `/query` to this base URL.

### Authentication

The API requires a session token obtained from the AgMaps web viewer. Tokens are
temporary (expire after several hours).

**Token fetch process:**
1. Open AgMaps viewer in headless Chromium (via Playwright)
2. Accept the disclaimer dialog
3. Capture the token from network traffic to `ws.lioservices.lrc.gov.on.ca/arcgis4*`
4. Validate against the service metadata endpoint
5. Save to `.env` as `AGMAPS_TOKEN=...`

**Token expiry detection:**
- HTTP 498 status code
- JSON response containing `"error"` with message about token

**Mid-run token refresh:**
When a query fails with token expiry:
1. Save all progress (cache to disk)
2. Fetch fresh token via Playwright (3 retries, exponential backoff: 10s, 20s, 30s)
3. Retry the failed query with new token
4. Continue the run

### Query: By ARN

```
GET {BASE}/query?
  where=ASSESSMENT_ROLL_NUMBER='{arn_20}'
  &outFields=*
  &returnGeometry=true
  &outSR=4326
  &f=json
  &token={TOKEN}
```

Returns exactly 0 or 1 features. The ARN is a unique key.

### Query: By PIN

```
GET {BASE}/query?
  where=PIN='{pin_9}'
  &outFields=*
  &returnGeometry=true
  &outSR=4326
  &f=json
  &token={TOKEN}
```

Returns 0 or 1 features. The response includes the ARN, which is extracted and
used to key the cache entry.

### Query: By Spatial Point

```
GET {BASE}/query?
  geometry={lng-0.0002},{lat-0.0002},{lng+0.0002},{lat+0.0002}
  &geometryType=esriGeometryEnvelope
  &inSR=4326
  &spatialRel=esriSpatialRelIntersects
  &outFields=*
  &returnGeometry=true
  &outSR=4326
  &f=json
  &token={TOKEN}
```

The 0.0002-degree buffer (~15m) creates a small bounding box around the point.
May return multiple features if parcels overlap the buffer. The resolver picks the
parcel whose polygon actually contains the point.

### Response Format

```json
{
  "features": [{
    "attributes": {
      "OBJECTID": 12345,
      "ASSESSMENT_ROLL_NUMBER": "19040231000630000000",
      "PIN": "081450123",
      ...
    },
    "geometry": {
      "rings": [[[-81.28, 42.93], [-81.28, 42.94], ...]]
    }
  }]
}
```

The `rings` format (ArcGIS) is converted to GeoJSON `Polygon` for storage:
```json
{ "type": "Polygon", "coordinates": [rings] }
```

### Rate Limiting

0.4 seconds minimum between API requests. This is enforced by the client, not the
server. Prevents overwhelming the provincial service.

---

## Bulk Run vs Incremental Run

### Bulk Run (First Time)

The initial run processes all 126K addresses files:

1. **Build work list:** Scan all addresses files. For each unique ARN, check if
   it's already in the parcel cache. Collect:
   - ARNs needing API lookup (~13,345)
   - PINs needing API lookup (records with PIN but no ARN, minus any whose PIN
     resolves to an already-cached ARN)
   - Records needing spatial resolution (no ARN, no PIN)

2. **Process ARN lookups first.** These are the fastest and most reliable.
   Each successful lookup adds to the cache, which may satisfy PIN lookups later.

3. **Process PIN lookups.** Each successful lookup discovers an ARN. Check if that
   ARN was already cached (it might have been discovered via a different record's
   ARN lookup). If not, the API response includes the parcel geometry.

4. **Process spatial lookups last.** These require geocoding first (separate API),
   then the AgMaps spatial query. Slowest and least reliable.

5. **Write parcel_links.** For every addresses file, write a corresponding
   parcel_links file recording the resolution result.

**Estimated API calls for bulk run:**
- ARN lookups: ~13,345 uncached ARNs (at 0.4s each = ~89 minutes)
- Spatial lookups: records with no ARN (~34% of data = ~43K records). These need
  geocoding first (Mapbox/Geocodio), then AgMaps spatial query. Many will share
  the same parcel, so actual unique spatial queries will be lower. Not built yet.

**Resumability:** The run is resumable. If interrupted:
- Parcels already cached stay cached (files on disk).
- Parcel links already written stay written.
- Re-running skips any record that already has a parcel_links file.

### Incremental Run (New Data)

When new RT data comes through (new scrape), only new records need resolution:

1. Run Extract → Classify → Normalize on the new data.
2. Run Resolve Parcels. It scans addresses files and checks for existing
   parcel_links files. Only new records (no parcel_links file yet) are processed.
3. For those new records, the cache check happens first. If the new transaction
   is on a property we've already resolved (same ARN), it's an instant cache hit.
   No API call needed.
4. Only genuinely new parcels (new ARNs, new PINs, new addresses) hit the API.

**In steady state, most new records will be cache hits.** The parcel cache grows
monotonically and covers the majority of Ontario commercial properties after the
bulk run.

---

## File Structure

```
engines/rt/
├── parcel_resolver/              # The Resolve Parcels stage code
│   ├── __init__.py
│   ├── resolve.py                # Orchestrator — scans addresses, runs chain, writes links
│   ├── agmaps.py                 # AgMaps API client (ARN, PIN, spatial queries)
│   ├── token.py                  # Token fetch via Playwright + refresh logic
│   └── geocode.py                # Address geocoding for spatial fallback
├── pipeline/
│   ├── addresses/                # INPUT  (from Normalize stage)
│   ├── parcel_links/             # OUTPUT (one per addresses file)
│   └── ...

clean-data/
├── parcels/                      # SHARED parcel cache (one JSON per ARN)
│   ├── 19040231000630000000.json
│   ├── 32040300301100100000.json
│   └── ... (67,137 seeded + grows)
```

---

## Decision Log

**Why individual files instead of one big JSON for the parcel cache?**
The v3 cache was a single 69MB JSON file. Loading/saving it on every run is slow and
fragile. Individual files mean: cache lookups are filesystem checks, new parcels are
appended without loading the whole cache, and partial runs don't risk corrupting a
monolithic file.

**Why not reuse lat/lng from previous runs?**
The address normalizer has been improved since v3. Reusing old coordinates would
carry forward old geocoding errors. Fresh geocode strings from the current normalizer
produce better results. Only the parcel polygons (which are provincial data, not
our computation) are reused.

**Why parcel_links as a separate pipeline output instead of modifying addresses files?**
Stages should not modify previous stages' output. The addresses files are the output
of the Normalize stage. The Resolve Parcels stage reads them and writes its own
output. The Compile stage reads both. This keeps stages independent and re-runnable.

**Why process ARNs before PINs before spatial?**
Each ARN lookup that succeeds adds a parcel to the cache. A PIN lookup may discover
that its ARN was already cached from a different record's ARN lookup. Processing in
confidence order maximizes cache hits and minimizes API calls.

---

## Build Plan

### Resolution Logic (per record)

```
1. Does the record have an ARN?
   │
   ├─ YES → Does clean-data/parcels/{arn}.json exist?
   │         ├─ YES → DONE. Link record to that parcel. (method: arn_cache)
   │         └─ NO  → Call API with ARN.
   │                   ├─ API returns parcel → Save to cache + link record. DONE. (method: arn_api)
   │                   └─ API returns nothing → Fall through to spatial.
   │
   2. Does the record have a geocodable address?
   │
   ├─ YES → Geocode the address to lat/lng (fresh, using geocode_string).
   │         Got coords? → Call API with spatial point query.
   │         ├─ API returns parcel → Save to cache + link record. DONE. (method: spatial_api)
   │         └─ API returns nothing → UNRESOLVED.
   │
   └─ NO  → UNRESOLVED.
```

Notes:
- **PIN is NOT queryable** on the AgMaps Assessment Parcel layer (MapServer/0).
  The service only exposes: OGF_ID, ASSESSMENT_ROLL_NUMBER, and date fields.
  Records with PIN-only must be resolved via spatial (geocode → point query).
  PIN-to-ARN bridging may be possible via a different service in the future.
- Spatial requires a separate geocoding call first (Mapbox/Geocodio) to get lat/lng.
- Every API result gets cached. The cache only grows.

### Build Order

**Step 1: Parcel cache interface** (`engines/rt/parcel_resolver/cache.py`) — DONE

- `cache_has(arn)` → bool — checks if `clean-data/parcels/{arn}.json` exists
- `cache_read(arn)` → dict — reads and returns the parcel JSON
- `cache_write(arn, parcel)` → writes parcel JSON to `clean-data/parcels/{arn}.json`
- Tested: reads from 67K seeded cache, writes + reads back correctly.

**Step 2: AgMaps API client** (`engines/rt/parcel_resolver/agmaps.py`) — DONE

- `query_by_arn(arn)` → dict or None
- `query_by_point(lat, lng)` → dict or None (for spatial fallback)
- Converts ArcGIS `rings` response to GeoJSON `Polygon`
- 0.4s throttle between requests
- Detects token expiry (HTTP 498 or error in JSON response)
- Tested: ARN query returns valid polygon for known parcel (1476 Queen St W).

**Step 3: Token manager** (`engines/rt/parcel_resolver/token.py`) — DONE

- `fetch_token()` → str — opens AgMaps via Playwright, captures token from network traffic
- `refresh_token(max_retries=3)` → str — fetch with exponential backoff (10s, 20s, 30s)
- `load_token()` → str or None — loads saved token, validates before returning
- Saves token to `engines/rt/.agmaps_token` for reuse across runs
- Tested: auto-fetched token, validated, saved, reloaded successfully.

**Step 4: Resolution chain** (`engines/rt/parcel_resolver/chain.py`) — DONE

- `resolve_record(arn, geocode_string, client)` → dict
  - Returns `{"resolved_arn": "...", "method": "arn_cache|arn_api|spatial_api|unresolved", "reason": "..."}`
  - On token expiry: raises `TokenExpiredError` for the orchestrator to handle
- Tested: cache hits work; ARN API queries work; unresolved correctly flagged.

**Step 5: Orchestrator** (`engines/rt/parcel_resolver/resolve.py`) — DONE

- Scans `pipeline/addresses/*.json`
- Skips files that already have a `pipeline/parcel_links/` output (resumable)
- Extracts `arn.api_format` and first geocodable `geocode_string`
- On `TokenExpiredError`: calls token refresh, retries, continues
- Progress reporting every 500 records
- Run via: `python -m parcel_resolver.resolve` (from `engines/rt/`)
- Tested: --limit 10 run completed, 7 cache hits, 3 unresolved, 0 errors.

### Test Results

| Path | Status | Evidence |
|---|---|---|
| ARN → cache hit | TESTED | 7/10 records resolved via arn_cache |
| ARN → API → save to cache + link | TESTED | API returned valid polygon for known ARN (19040231000630000000) |
| Spatial (geocode → point query) | NOT BUILT | TODO: needs geocoding integration |
| Token auto-fetch | TESTED | Playwright fetched token automatically on first run |
| Token mid-run refresh | NOT YET TESTED | Needs a long run where token expires |
| Resumability | TESTED | Re-run skips already-resolved files |

### What's NOT covered yet

1. **ARN → API → cache write during a real run.** We tested the API client directly
   and confirmed it returns parcels and we can write to cache. But we haven't seen
   this path fire during an actual orchestrator run because our 10-record test only
   hit records where the ARN was already cached or not in the API at all.

2. **Spatial resolution.** Records with no ARN (34.4% of data) need geocoding first,
   then a spatial point query. This requires a geocoding provider (Mapbox/Geocodio).

3. **Token mid-run refresh.** The code handles it, but it hasn't been tested in a
   real long-running session where the token actually expires.
