"""
Test Ontario's GeocodeServer for address → coordinates resolution.

Found via AgMaps network sniffing:
  - GeocodeServer lives on arcgis1 (not arcgis4)
  - Accessed via proxy: lioapplications.lrc.gov.on.ca/services/proxy/proxy.ashx
  - Internal URL: intra.ws.lioservices.lrc.gov.on.ca/arcgis1/rest/services/...

Run from project root:
    python3 engines/rt/test_ontario_geocoder.py
"""

import json
import requests

# The proxy URL pattern from AgMaps network traffic
PROXY_BASE = "https://www.lioapplications.lrc.gov.on.ca/services/proxy/proxy.ashx"

# Possible internal geocoder URLs to try
GEOCODER_CANDIDATES = [
    "https://intra.ws.lioservices.lrc.gov.on.ca/arcgis1/rest/services/Geocode/GeocodeServer",
    "https://intra.ws.lioservices.lrc.gov.on.ca/arcgis1/rest/services/Locator/GeocodeServer",
    "https://intra.ws.lioservices.lrc.gov.on.ca/arcgis1/rest/services/GeocodingService/GeocodeServer",
    "https://intra.ws.lioservices.lrc.gov.on.ca/arcgis1/rest/services/Address/GeocodeServer",
    "https://intra.ws.lioservices.lrc.gov.on.ca/arcgis1/rest/services/AddressLocator/GeocodeServer",
    # Also try public arcgis1 directly
    "https://ws.lioservices.lrc.gov.on.ca/arcgis1/rest/services/Geocode/GeocodeServer",
    "https://ws.lioservices.lrc.gov.on.ca/arcgis1/rest/services/Locator/GeocodeServer",
]

TEST_ADDRESSES = [
    "107 Edward St, St. Thomas, ON",
    "99 Edward St, St. Thomas, ON",
    "300 Water St, Peterborough, ON",  # from AgMaps placeholder text
]


def try_geocoder(geocoder_url, use_proxy=True):
    """Try to access a geocoder URL, optionally through the proxy."""
    if use_proxy:
        url = f"{PROXY_BASE}?{geocoder_url}"
    else:
        url = geocoder_url

    print(f"\n--- Testing: {geocoder_url}")
    print(f"    Proxy: {use_proxy}")

    # First check if the service exists
    try:
        resp = requests.get(f"{url}?f=json" if "?" not in url else f"{url}&f=json",
                          timeout=15)
        if not resp.ok:
            print(f"    HTTP {resp.status_code}")
            return None

        data = resp.json()
        if "error" in data:
            print(f"    Error: {data['error'].get('message', data['error'])}")
            return None

        if "addressFields" in data or "singleLineAddressField" in data:
            print(f"    FOUND GeocodeServer!")
            if "addressFields" in data:
                fields = [f["name"] for f in data["addressFields"]]
                print(f"    Address fields: {fields}")
            if "singleLineAddressField" in data:
                print(f"    Single line field: {data['singleLineAddressField']['name']}")
            return url
        else:
            print(f"    Response keys: {list(data.keys())[:10]}")
            return None

    except Exception as e:
        print(f"    Exception: {e}")
        return None


def test_find_address(geocoder_url, address, use_proxy=True):
    """Call findAddressCandidates on the geocoder."""
    if use_proxy:
        base = f"{PROXY_BASE}?{geocoder_url}/findAddressCandidates"
    else:
        base = f"{geocoder_url}/findAddressCandidates"

    print(f"\n  Geocoding: '{address}'")

    params = {
        "SingleLine": address,
        "outFields": "*",
        "maxLocations": 5,
        "outSR": "4326",
        "f": "json",
    }

    try:
        resp = requests.get(base, params=params, timeout=15)
        data = resp.json()

        if "error" in data:
            print(f"    Error: {data['error']}")
            return

        candidates = data.get("candidates", [])
        print(f"    Candidates: {len(candidates)}")

        for i, c in enumerate(candidates[:3]):
            addr = c.get("address", "?")
            score = c.get("score", "?")
            loc = c.get("location", {})
            attrs = c.get("attributes", {})
            print(f"    [{i+1}] {addr}")
            print(f"        Score: {score}")
            print(f"        Location: {loc.get('x', '?')}, {loc.get('y', '?')}")
            if attrs:
                # Print interesting attributes
                for key in ["Loc_name", "Match_addr", "Addr_type", "City", "Region"]:
                    if key in attrs:
                        print(f"        {key}: {attrs[key]}")

    except Exception as e:
        print(f"    Exception: {e}")


def probe_arcgis1_services():
    """List services on arcgis1 to find the geocoder."""
    print("\n=== Probing arcgis1 services ===")

    for base in [
        "https://intra.ws.lioservices.lrc.gov.on.ca/arcgis1/rest/services",
        "https://ws.lioservices.lrc.gov.on.ca/arcgis1/rest/services",
    ]:
        for use_proxy in [True, False]:
            if use_proxy:
                url = f"{PROXY_BASE}?{base}?f=json"
            else:
                url = f"{base}?f=json"

            label = "(via proxy)" if use_proxy else "(direct)"
            print(f"\n  {base} {label}")

            try:
                resp = requests.get(url, timeout=15)
                if resp.ok:
                    data = resp.json()
                    if "services" in data:
                        for svc in data["services"]:
                            svc_type = svc.get("type", "?")
                            svc_name = svc.get("name", "?")
                            marker = " <<<< GEOCODER" if "Geocode" in svc_type else ""
                            print(f"    {svc_name} ({svc_type}){marker}")
                    if "folders" in data:
                        for folder in data["folders"]:
                            print(f"    [folder] {folder}")
                    if "error" in data:
                        print(f"    Error: {data['error'].get('message', data['error'])}")
                else:
                    print(f"    HTTP {resp.status_code}")
            except Exception as e:
                print(f"    Exception: {e}")


def main():
    # Step 1: Find the geocoder
    print("=" * 60)
    print("STEP 1: Find the Ontario GeocodeServer")
    print("=" * 60)

    probe_arcgis1_services()

    # Step 2: Try known candidates
    print("\n" + "=" * 60)
    print("STEP 2: Try geocoder URL candidates")
    print("=" * 60)

    working_url = None
    use_proxy = None

    for geocoder_url in GEOCODER_CANDIDATES:
        for proxy in [True, False]:
            result = try_geocoder(geocoder_url, use_proxy=proxy)
            if result:
                working_url = geocoder_url
                use_proxy = proxy
                break
        if working_url:
            break

    # Step 3: Test address geocoding
    if working_url:
        print("\n" + "=" * 60)
        print(f"STEP 3: Test address geocoding")
        print(f"  Geocoder: {working_url}")
        print(f"  Via proxy: {use_proxy}")
        print("=" * 60)

        for address in TEST_ADDRESSES:
            test_find_address(working_url, address, use_proxy=use_proxy)
    else:
        print("\n" + "=" * 60)
        print("Could not find a working GeocodeServer.")
        print("Check the full proxy URL from the AgMaps network traffic.")
        print("=" * 60)


if __name__ == "__main__":
    main()
