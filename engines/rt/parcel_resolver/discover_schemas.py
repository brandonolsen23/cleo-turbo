"""
Schema Discovery — Capture full raw API responses from Ontario Geocoder
and AgMaps parcel service to audit available fields.

Run from project root:
    cd ~/cleo-turbo
    python -m engines.rt.parcel_resolver.discover_schemas

Output: engines/rt/parcel_resolver/_schema_discovery.json
"""

import json
import os
import sys
import time

# ── AgMaps token ──────────────────────────────────────────────────────

def get_token():
    """Get a valid AgMaps token (load saved or fetch fresh)."""
    from .token import load_token, refresh_token
    token = load_token()
    if token:
        print("  Using saved AgMaps token.")
        return token
    print("  No saved token — fetching fresh one via browser...")
    return refresh_token()


# ── Task 1: AgMaps service metadata ──────────────────────────────────

def discover_agmaps_metadata(token):
    """Hit the service metadata endpoint to get all field definitions."""
    import requests

    base = (
        "https://ws.lioservices.lrc.gov.on.ca/arcgis4/rest/services"
        "/AIA/Assessment_Parcel_Map/MapServer/0"
    )

    print("\n═══ AgMaps Service Metadata ═══")
    print(f"  URL: {base}?f=json")

    resp = requests.get(base, params={"f": "json", "token": token}, timeout=30)
    data = resp.json()

    # Extract field definitions
    fields = data.get("fields", [])
    print(f"\n  Fields ({len(fields)}):")
    for f in fields:
        print(f"    {f['name']:40s}  type={f.get('type', '?'):30s}  alias={f.get('alias', '')}")

    return {
        "endpoint": base,
        "field_count": len(fields),
        "fields": fields,
        "full_metadata": data,
    }


# ── Task 2: AgMaps sample parcel query ───────────────────────────────

def discover_agmaps_parcel(token):
    """Query a known parcel and dump the FULL raw feature response."""
    import requests

    base = (
        "https://ws.lioservices.lrc.gov.on.ca/arcgis4/rest/services"
        "/AIA/Assessment_Parcel_Map/MapServer/0"
    )

    # Use a well-known ARN (90 Signet Drive, North York — RT100001)
    test_arn = "19080133200075000000"

    print(f"\n═══ AgMaps Parcel Query (ARN: {test_arn}) ═══")

    resp = requests.get(
        f"{base}/query",
        params={
            "where": f"ASSESSMENT_ROLL_NUMBER='{test_arn}'",
            "outFields": "*",
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "json",
            "token": token,
        },
        timeout=30,
    )
    data = resp.json()

    features = data.get("features", [])
    if not features:
        print("  WARNING: No features returned for this ARN.")
        return {"arn": test_arn, "raw_response": data}

    feature = features[0]
    attrs = feature.get("attributes", {})
    geom = feature.get("geometry", {})

    print(f"\n  Attributes ({len(attrs)} fields):")
    for k, v in attrs.items():
        val_str = str(v)
        if len(val_str) > 80:
            val_str = val_str[:77] + "..."
        print(f"    {k:40s}  = {val_str}")

    print(f"\n  Geometry keys: {list(geom.keys())}")
    rings = geom.get("rings", [])
    if rings:
        print(f"  Ring count: {len(rings)}, points in first ring: {len(rings[0])}")

    return {
        "arn": test_arn,
        "attribute_keys": list(attrs.keys()),
        "attributes": attrs,
        "geometry_keys": list(geom.keys()),
        "ring_count": len(rings),
        "full_feature": feature,
    }


# ── Task 3: Ontario geocoder full response ───────────────────────────

def discover_geocoder(token):
    """Geocode test addresses and dump FULL raw responses.

    Uses Playwright to establish the proxy session (same as production).
    """
    from playwright.sync_api import sync_playwright

    AGMAPS_URL = (
        "https://www.lioapplications.lrc.gov.on.ca/AgMaps/Index.html"
        "?viewer=AgMaps.AgMaps&locale=en-CA"
    )
    PROXY_BASE = (
        "https://www.lioapplications.lrc.gov.on.ca/services/proxy/proxy.ashx"
    )
    GEOCODER_BASE = (
        "https://intra.ws.lioservices.lrc.gov.on.ca/arcgis1/rest/services"
        "/Geocoders/Ontario_Address_Locator/GeocodeServer"
    )

    test_addresses = [
        "107 Edward St, St Thomas, ON",
        "90 Signet Drive, North York, ON",
        "300 Water St, Peterborough, ON",
    ]

    print("\n═══ Ontario Geocoder — Full Response Discovery ═══")
    print("  Starting Playwright session...")

    results = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        # Navigate and accept disclaimer
        page.goto(AGMAPS_URL, wait_until="networkidle", timeout=60000)
        for selector in [
            "button:has-text('Accept')",
            "button:has-text('I Accept')",
            "button:has-text('Agree')",
            "button:has-text('OK')",
            "input[type='button'][value='Accept']",
            "input[type='button'][value='I Accept']",
        ]:
            try:
                btn = page.locator(selector).first
                if btn.is_visible(timeout=2000):
                    btn.click()
                    break
            except Exception:
                continue

        page.wait_for_timeout(2000)
        print("  Session ready.")

        for addr in test_addresses:
            print(f"\n  Geocoding: \"{addr}\"")

            js_code = """
            (addr) => {
                const url = "%s?%s/findAddressCandidates" +
                    "?SingleLine=" + encodeURIComponent(addr) +
                    "&outFields=*&maxLocations=5&outSR=4326&f=json";
                return fetch(url).then(r => r.text());
            }
            """ % (PROXY_BASE, GEOCODER_BASE)

            raw = page.evaluate(js_code, addr)
            data = json.loads(raw)

            candidates = data.get("candidates", [])
            print(f"  Candidates returned: {len(candidates)}")

            if candidates:
                c = candidates[0]
                print(f"\n  Best candidate:")
                print(f"    address:    {c.get('address', '')}")
                print(f"    location:   {c.get('location', {})}")
                print(f"    score:      {c.get('score', '')}")
                print(f"    extent:     {c.get('extent', {})}")

                attrs = c.get("attributes", {})
                print(f"\n  Attributes ({len(attrs)} fields):")
                for k, v in attrs.items():
                    print(f"      {k:30s}  = {v}")

            # Also show top-level keys in the response (spatial reference, etc.)
            top_keys = [k for k in data.keys() if k != "candidates"]
            if top_keys:
                print(f"\n  Other top-level keys: {top_keys}")
                for k in top_keys:
                    v = data[k]
                    if isinstance(v, dict):
                        print(f"    {k}: {json.dumps(v)}")

            results[addr] = {
                "candidate_count": len(candidates),
                "candidates": candidates,
                "top_level_keys": {k: data[k] for k in top_keys},
                "full_response": data,
            }

            time.sleep(0.5)

        browser.close()

    return results


# ── Main ─────────────────────────────────────────────────────────────

def main():
    print("╔══════════════════════════════════════════════╗")
    print("║  Cleo Turbo — API Schema Discovery           ║")
    print("║  Capturing full raw responses from both APIs  ║")
    print("╚══════════════════════════════════════════════╝")
    print()

    token = get_token()

    output = {}

    # AgMaps metadata
    try:
        output["agmaps_metadata"] = discover_agmaps_metadata(token)
    except Exception as e:
        print(f"  ERROR querying AgMaps metadata: {e}")
        output["agmaps_metadata"] = {"error": str(e)}

    # AgMaps sample parcel
    try:
        output["agmaps_parcel"] = discover_agmaps_parcel(token)
    except Exception as e:
        print(f"  ERROR querying AgMaps parcel: {e}")
        output["agmaps_parcel"] = {"error": str(e)}

    # Ontario geocoder
    try:
        output["geocoder"] = discover_geocoder(token)
    except Exception as e:
        print(f"  ERROR querying geocoder: {e}")
        output["geocoder"] = {"error": str(e)}

    # Save results
    out_path = os.path.join(os.path.dirname(__file__), "_schema_discovery.json")
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\n{'='*60}")
    print(f"Results saved to: {out_path}")
    print(f"{'='*60}")

    # Quick summary
    print("\n── SUMMARY ──")

    if "agmaps_metadata" in output and "fields" in output.get("agmaps_metadata", {}):
        fields = output["agmaps_metadata"]["fields"]
        print(f"\nAgMaps service exposes {len(fields)} fields:")
        for f in fields:
            print(f"  {f['name']}")

    if "agmaps_parcel" in output and "attribute_keys" in output.get("agmaps_parcel", {}):
        keys = output["agmaps_parcel"]["attribute_keys"]
        # Compare to what we currently capture
        currently_kept = {"OGF_ID", "GEOMETRY_UPDATE_DATETIME", "EFFECTIVE_DATETIME",
                         "SYSTEM_DATETIME", "OBJECTID", "REFRESHED_DATETIME"}
        currently_dropped = {"ASSESSMENT_ROLL_NUMBER", "PIN",
                           "Shape", "Shape.STArea()", "Shape.STLength()"}
        unknown = set(keys) - currently_kept - currently_dropped
        if unknown:
            print(f"\n  NEW fields we don't capture yet: {unknown}")

    if "geocoder" in output:
        for addr, result in output["geocoder"].items():
            if "candidates" in result and result["candidates"]:
                attrs = result["candidates"][0].get("attributes", {})
                currently_kept_geo = {"Addr_type", "Loc_name"}
                unknown_geo = set(attrs.keys()) - currently_kept_geo
                if unknown_geo:
                    print(f"\n  Geocoder attributes beyond Addr_type/Loc_name: {unknown_geo}")
                break


if __name__ == "__main__":
    main()
