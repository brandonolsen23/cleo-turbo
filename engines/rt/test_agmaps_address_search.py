"""
Test script — can AgMaps resolve addresses directly to parcels?

Probes the ArcGIS REST server to find geocoding/address search endpoints,
then tests "107 Edward St, St. Thomas" to see if it returns the correct parcel.

Run from project root:
    python engines/rt/test_agmaps_address_search.py
"""

import json
import requests
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from parcel_resolver.token import load_token, refresh_token

BASE = "https://ws.lioservices.lrc.gov.on.ca/arcgis4/rest/services"
PARCEL_URL = f"{BASE}/AIA/Assessment_Parcel_Map/MapServer/0"

TEST_ADDRESS = "107 Edward St, St. Thomas"


def get_token():
    token = load_token()
    if token:
        print(f"Using saved token: {token[:20]}...")
        return token
    print("Fetching fresh token...")
    token = refresh_token()
    print(f"Got token: {token[:20]}...")
    return token


def probe_services(token):
    """List all services on the ArcGIS server."""
    print("\n=== Probing ArcGIS Services ===")

    # Check the root services directory
    for path in [
        f"{BASE}",
        f"{BASE}/AIA",
    ]:
        print(f"\nGET {path}?f=json")
        resp = requests.get(path, params={"f": "json", "token": token}, timeout=15)
        if resp.ok:
            data = resp.json()
            if "services" in data:
                for svc in data["services"]:
                    print(f"  {svc.get('name', '?')} ({svc.get('type', '?')})")
            if "folders" in data:
                for folder in data["folders"]:
                    print(f"  [folder] {folder}")
            if "error" in data:
                print(f"  Error: {data['error']}")
        else:
            print(f"  HTTP {resp.status_code}")


def test_find_endpoint(token):
    """Try the MapServer 'find' operation — searches across fields."""
    print("\n=== Test: MapServer /find ===")

    url = f"{BASE}/AIA/Assessment_Parcel_Map/MapServer/find"
    params = {
        "searchText": TEST_ADDRESS,
        "contains": "true",
        "searchFields": "",
        "layers": "0",
        "returnGeometry": "true",
        "f": "json",
        "token": token,
    }
    print(f"GET {url}")
    print(f"  searchText: {TEST_ADDRESS}")
    resp = requests.get(url, params=params, timeout=15)
    data = resp.json()

    if "error" in data:
        print(f"  Error: {data['error']}")
    elif "results" in data:
        print(f"  Results: {len(data['results'])}")
        for r in data["results"][:3]:
            attrs = r.get("attributes", {})
            print(f"    ARN: {attrs.get('ASSESSMENT_ROLL_NUMBER', 'N/A')}")
            print(f"    Attrs: {json.dumps(attrs, indent=6)}")
    else:
        print(f"  Response keys: {list(data.keys())}")
        print(f"  {json.dumps(data, indent=2)[:500]}")


def test_geocode_services(token):
    """Look for GeocodeServer services on the ArcGIS platform."""
    print("\n=== Test: GeocodeServer Lookup ===")

    # Common Ontario geocoding endpoints
    geocode_urls = [
        f"{BASE}/AIA/Geocode/GeocodeServer",
        f"{BASE}/AIA/Address_Geocode/GeocodeServer",
        f"{BASE}/Geocode/GeocodeServer",
        f"{BASE}/Locators/GeocodeServer",
        # The Ontario GeoPortal sometimes uses this pattern
        "https://ws.lioservices.lrc.gov.on.ca/arcgis4/rest/services/AIA/Geocode_Service/GeocodeServer",
    ]

    for url in geocode_urls:
        print(f"\nGET {url}?f=json")
        try:
            resp = requests.get(url, params={"f": "json", "token": token}, timeout=10)
            if resp.ok:
                data = resp.json()
                if "error" not in data:
                    print(f"  FOUND! Service info: {json.dumps(data, indent=2)[:300]}")
                    # Try findAddressCandidates
                    test_geocode_address(url, token)
                    return url
                else:
                    print(f"  Error: {data['error'].get('message', '?')}")
            else:
                print(f"  HTTP {resp.status_code}")
        except Exception as e:
            print(f"  Exception: {e}")

    return None


def test_geocode_address(geocode_url, token):
    """If we found a GeocodeServer, try findAddressCandidates."""
    print(f"\n=== Test: findAddressCandidates ===")

    url = f"{geocode_url}/findAddressCandidates"

    # Try both single-line and structured address
    for params in [
        {
            "SingleLine": TEST_ADDRESS,
            "outFields": "*",
            "f": "json",
            "token": token,
        },
        {
            "Address": "107 Edward St",
            "City": "St. Thomas",
            "Region": "Ontario",
            "outFields": "*",
            "f": "json",
            "token": token,
        },
    ]:
        print(f"  Params: {params}")
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        if "candidates" in data:
            print(f"  Candidates: {len(data['candidates'])}")
            for c in data["candidates"][:3]:
                print(f"    {c.get('address', '?')} — score: {c.get('score', '?')}")
                print(f"    Location: {c.get('location', {})}")
        elif "error" in data:
            print(f"  Error: {data['error']}")
        else:
            print(f"  Response: {json.dumps(data, indent=2)[:300]}")


def test_query_with_address(token):
    """Try querying the parcel layer with address-like WHERE clause."""
    print("\n=== Test: Parcel Layer WHERE clause (address fields?) ===")

    # First, check what fields are available
    url = f"{PARCEL_URL}"
    resp = requests.get(url, params={"f": "json", "token": token}, timeout=10)
    data = resp.json()

    if "fields" in data:
        print("  Available fields:")
        for field in data["fields"]:
            print(f"    {field['name']} ({field.get('type', '?')})")
    else:
        print(f"  Response keys: {list(data.keys())}")
        if "error" in data:
            print(f"  Error: {data['error']}")


def test_identify(token):
    """Try the identify operation (what the map UI might use on click)."""
    print("\n=== Test: MapServer /identify ===")

    url = f"{BASE}/AIA/Assessment_Parcel_Map/MapServer/identify"
    # Use rough coords for 107 Edward St, St. Thomas
    params = {
        "geometry": "-81.177,42.785",
        "geometryType": "esriGeometryPoint",
        "sr": "4326",
        "layers": "all:0",
        "tolerance": "5",
        "mapExtent": "-81.18,42.78,-81.17,42.79",
        "imageDisplay": "600,400,96",
        "returnGeometry": "true",
        "f": "json",
        "token": token,
    }
    resp = requests.get(url, params=params, timeout=15)
    data = resp.json()

    if "results" in data:
        print(f"  Results: {len(data['results'])}")
        for r in data["results"][:3]:
            attrs = r.get("attributes", {})
            print(f"    ARN: {attrs.get('ASSESSMENT_ROLL_NUMBER', 'N/A')}")
    elif "error" in data:
        print(f"  Error: {data['error']}")


if __name__ == "__main__":
    token = get_token()

    # 1. List what services exist
    probe_services(token)

    # 2. Check fields on the parcel layer
    test_query_with_address(token)

    # 3. Try MapServer /find (text search across layers)
    test_find_endpoint(token)

    # 4. Try MapServer /identify (point-based, like clicking the map)
    test_identify(token)

    # 5. Look for a dedicated GeocodeServer
    test_geocode_services(token)

    print("\n=== Done ===")
    print("If none of the above returned address-based results, the AgMaps")
    print("address search in the UI is likely handled by a separate service")
    print("(e.g. Ontario Geocoder) that we'd need to identify from the")
    print("AgMaps viewer's network traffic.")
