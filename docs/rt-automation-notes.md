# RT Pipeline Automation Notes

How to automate RT transaction processing so new scrapes flow through automatically.

## Current Pipeline (Manual)

The RT pipeline has 8 sequential stages. Currently each runs manually:

```
Raw HTML pages → [1] Extract + Assemble → [2] Classify → [3] Address Normalize
→ [4] PIN Bridge → [5] Geocode Preflight → [6] Geocode → [7] Parcel Resolve
→ [8] Compile → [9] Database Rebuild
```

### Stage Details

| Stage | Script | Input | Output | Runtime |
|-------|--------|-------|--------|---------|
| Extract + Assemble | `engines/rt/run_pipeline.py` | `raw-data/rt/pages/` | `pipeline/assembled/` | ~10 min |
| Classify | `engines/rt/run_classifier.py` | `pipeline/assembled/` | `pipeline/classified/` | ~15 min |
| Address Normalize | `engines/rt/address_normalizer/run.py` | `pipeline/classified/` | `pipeline/addresses/` | ~20 min |
| PIN Bridge | `parcel_resolver.pin_bridge` | `pipeline/addresses/` + GW data | updates `pipeline/addresses/` | ~2 min |
| Geocode Preflight | `parcel_resolver.geocode --preflight` | `pipeline/addresses/` | geocode queue | ~2 min |
| Geocode | `parcel_resolver.geocode --run` | geocode queue | geocode cache | varies (API calls) |
| Parcel Resolve | `parcel_resolver.resolve` | `pipeline/addresses/` + caches | `pipeline/parcel_links/` | ~30 min |
| Compile | `engines/rt/compile.py` | classified + addresses + parcel_links | `clean-data/rt/` | ~15 min |
| Database Rebuild | `rebuild.py` | `clean-data/{rt,gw,osm}/` | `data/cleo.db` | ~30 min |

### Orchestrator

`engines/rt/run_all.py` already chains stages 3-9 (normalize through rebuild). Stages 1-2 (extract + classify) run separately because they're the initial scrape processing.

```bash
# Full pipeline from raw HTML
cd engines/rt && python3 run_pipeline.py      # extract + assemble
cd engines/rt && python3 run_classifier.py    # classify
cd $PROJECT_ROOT && python3 engines/rt/run_all.py  # normalize → resolve → compile → rebuild
```

## Automation Strategy: RT Watcher (Modeled on GW Watcher)

The GW watcher (`engines/gw/watcher.py`) already implements the pattern we want:
- Watches `~/Downloads/GeoWarehouse/gw-ingest-data/` for new HTML files
- Batches them on a configurable interval
- Runs the full pipeline: ingest → parse → normalize → resolve → compile
- Does **incremental** DB updates (no full rebuild needed)

### Option A: Full-Pipeline RT Watcher (Recommended for Auto-Scrape)

For an auto-scraper that produces new raw HTML pages continuously:

```
Watch folder → Extract + Assemble → Classify → Address Normalize
→ PIN Bridge → Parcel Resolve → Compile → Incremental DB Update
```

Key design decisions:
1. **Watch folder**: `~/Downloads/Realtrack/rt-ingest-data/` (or wherever the scraper dumps HTML)
2. **Batch interval**: 30-60 seconds (RT files come in batches per region/page)
3. **Incremental DB update**: Like the GW watcher, bypass full rebuild. Insert new transactions directly, create/update properties, link contacts.
4. **Dedup**: Check if RT ID already exists in `pipeline/assembled/` before processing

### Option B: Incremental-Only Watcher (Simpler)

If the scraper handles extract+classify itself and drops clean JSON directly:

```
Watch clean-data/rt/ for new files → Incremental DB insert
```

This is simpler but loses the full pipeline's address normalization and parcel resolution.

## Incremental DB Update Design

The GW watcher's incremental update pattern should be replicated for RT:

```python
# Pseudocode for RT incremental DB update
def incremental_update(clean_record):
    conn = get_connection()
    registry = IDRegistry(conn)
    registry.load()
    
    arn = clean_record['parcel']['resolved_arn']
    
    if arn:
        # Check if property exists
        row = conn.execute("SELECT id FROM properties WHERE arn = ?", (arn,))
        if row:
            property_id = row[0]
            # Update property metadata if richer
        else:
            # Create new property via registry
            property_id = registry.get_or_create_property_id(arn)
            # Insert property with parcel geometry
    
    # Insert transaction
    conn.execute("INSERT OR IGNORE INTO transactions ...")
    
    # Insert parties, contacts, brokers
    # Update transaction_count on property
    # Update most_recent_sale_price/date
    
    conn.commit()
    registry.save_counters()
```

### Key Fields for RT Incremental Insert

From a clean RT record, the incremental updater needs to write to:
- `transactions` — the core transaction record
- `transaction_parties` — seller/buyer parties
- `transaction_mailing_addresses` — mailing addresses from parties
- `transaction_brokers` — broker firms
- `transaction_broker_agents` — individual agents
- `properties` — create if new ARN, update fields
- `contacts` — create if new name fingerprint
- `groups` — create if new normalized company name

## Auto-Scrape Integration Points

When building the RT auto-scraper, it needs to:

1. **Output format**: Drop HTML files in the same structure the pipeline expects:
   ```
   raw-data/rt/pages/{Region}/{property_type}/p{NNN}/
     ├── detail_{position}.html
     ├── export.json
     └── results.html
   ```

2. **Signal new files**: Either:
   - Drop files in a watch folder (like GW watcher pattern)
   - Write a manifest/queue file listing new page folders to process
   - Use filesystem events (inotify/fswatch)

3. **Rate limiting**: RT likely has rate limits. The scraper should handle:
   - Exponential backoff on 429/503
   - Session management (cookies, login)
   - Region-based scheduling to avoid hammering one area

4. **Idempotency**: The pipeline already handles duplicates (dedup by RT ID in compile step), so re-scraping the same transaction is safe.

## Implementation Priority

1. **Build the incremental DB updater for RT** (mirrors `gw/watcher.py` Step 6)
2. **Build the RT watcher** (watches for new assembled+classified files, runs normalize → resolve → compile → incremental update)
3. **Build the auto-scraper** (separate project — headless browser, handles login, pagination, downloads)
4. **Connect scraper → watcher** (scraper drops files, watcher picks them up)

## Environment Notes

- All pipeline scripts use `PROJECT_ROOT` relative paths
- Config is in `engines/rt/config.json` (points to raw-data source folder)
- The parcel resolver needs an AgMaps token for ARN lookups (stored in `.token` files)
- Geocoding needs a Mapbox API key (stored in env or config)
- The PIN bridge needs GW assessment data in `clean-data/gw/` to cross-reference PINs
