"""
Address-health audit — independent OSM/Nominatim cross-check of every resolved
property.

READ-ONLY on cleo.db (SELECT only). Results go to a SEPARATE address_health.db,
so this never modifies resolution data and never locks the live DB. For each
property with a stored (lat,lng) and an address, geocode the address via OSM and
measure the distance between OUR stored point and OSM's. A large gap flags a
likely mis-placement — both the obvious Class-1 misses and the silent Class-2
"confidently inside the wrong parcel" cases the internal signals can't see.
"""
from __future__ import annotations
import os, sys, math, sqlite3, argparse, threading
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from cleo.resolver.osm_geocode import OSMGeocoderClient  # noqa: E402

SRC_DB = os.path.join(ROOT, "data", "cleo.db")
OUT_DB = os.path.join(ROOT, "data", "address_health.db")


def haversine_m(lat1, lng1, lat2, lng2):
    R = 6_371_000
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def bucket(d):
    if d is None:
        return "osm_no_result"
    if d <= 50:
        return "agree"
    if d <= 250:
        return "minor"
    if d <= 1000:
        return "moderate"
    if d <= 5000:
        return "major"
    return "gross"


_local = threading.local()


def _client():
    if not hasattr(_local, "c"):
        _local.c = OSMGeocoderClient()
    return _local.c


def _addr(row):
    disp = (row["display_address"] or "").strip()
    if not disp:
        return None
    parts = [disp, (row["city"] or "").strip(),
             (row["region"] or "ON").strip(), (row["postal"] or "").strip()]
    return ", ".join(p for p in parts if p)


def check(row):
    addr = _addr(row)
    if not addr:
        return (row["id"], row["arn"], row["lat"], row["lng"],
                None, None, None, None, None, "no_address")
    g = _client().geocode(addr)
    if not g:
        return (row["id"], row["arn"], row["lat"], row["lng"],
                None, None, None, None, addr, "osm_no_result")
    d = haversine_m(row["lat"], row["lng"], g["lat"], g["lng"])
    return (row["id"], row["arn"], row["lat"], row["lng"],
            g["lat"], g["lng"], round(d, 1), g.get("addr_type"), addr, bucket(d))


INSERT = ("INSERT OR REPLACE INTO address_health(property_id,arn,stored_lat,"
          "stored_lng,osm_lat,osm_lng,distance_m,osm_addr_type,queried_address,"
          "bucket) VALUES(?,?,?,?,?,?,?,?,?,?)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    src = sqlite3.connect(SRC_DB)
    src.row_factory = sqlite3.Row
    q = ("SELECT id,arn,display_address,city,region,postal,lat,lng FROM properties "
         "WHERE lat IS NOT NULL AND lng IS NOT NULL")
    if args.limit:
        q += f" LIMIT {args.limit}"
    rows = src.execute(q).fetchall()
    src.close()
    print(f"{len(rows):,} properties to check  (workers={args.workers})", flush=True)

    out = sqlite3.connect(OUT_DB)
    out.execute("""CREATE TABLE IF NOT EXISTS address_health(
        property_id TEXT PRIMARY KEY, arn TEXT, stored_lat REAL, stored_lng REAL,
        osm_lat REAL, osm_lng REAL, distance_m REAL, osm_addr_type TEXT,
        queried_address TEXT, bucket TEXT,
        checked_at TEXT DEFAULT (datetime('now')))""")
    out.execute("CREATE INDEX IF NOT EXISTS ix_ah_bucket ON address_health(bucket)")
    out.commit()

    done, batch = 0, []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for res in ex.map(check, rows):
            batch.append(res)
            done += 1
            if len(batch) >= 500:
                out.executemany(INSERT, batch)
                out.commit()
                batch = []
                print(f"  {done:,}/{len(rows):,}", flush=True)
    if batch:
        out.executemany(INSERT, batch)
        out.commit()

    print("=== distance buckets ===", flush=True)
    order = ("CASE bucket WHEN 'agree' THEN 1 WHEN 'minor' THEN 2 WHEN 'moderate' THEN 3 "
             "WHEN 'major' THEN 4 WHEN 'gross' THEN 5 WHEN 'osm_no_result' THEN 6 ELSE 7 END")
    for b, n in out.execute(f"SELECT bucket,COUNT(*) FROM address_health GROUP BY bucket ORDER BY {order}"):
        print(f"  {b:14s} {n:,}", flush=True)
    out.close()


if __name__ == "__main__":
    main()
