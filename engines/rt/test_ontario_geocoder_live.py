"""
Live integration test for OntarioGeocoderClient.
Runs 5 test addresses through the geocoder and validates results.

Run from project root:
    python3 engines/rt/test_ontario_geocoder_live.py
"""

import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from parcel_resolver.ontario_geocoder import OntarioGeocoderClient

TEST_CASES = [
    {
        "address": "107 Edward St, St. Thomas, ON",
        "expected_lat_range": (42.78, 42.79),
        "expected_lng_range": (-81.18, -81.17),
        "notes": "The original problem address — Shoppers Drug Mart",
    },
    {
        "address": "300 Water St, Peterborough, ON",
        "expected_lat_range": (44.29, 44.31),
        "expected_lng_range": (-78.33, -78.31),
        "notes": "Heartbeat address — should always work",
    },
    {
        "address": "1027 Yonge Street, Toronto, ON",
        "expected_lat_range": (43.67, 43.68),
        "expected_lng_range": (-79.40, -79.38),
        "notes": "Downtown Toronto office",
    },
    {
        "address": "5250 Orbitor Drive, Mississauga, ON",
        "expected_lat_range": (43.63, 43.65),
        "expected_lng_range": (-79.62, -79.60),
        "notes": "Peel Region industrial",
    },
    {
        "address": "390 King Street East, Cobourg, ON",
        "expected_lat_range": (43.95, 43.97),
        "expected_lng_range": (-78.17, -78.15),
        "notes": "Northumberland comm-ind-land",
    },
]


def main():
    print("=" * 60)
    print("Ontario Geocoder — Live Integration Test")
    print("=" * 60)
    print()

    passed = 0
    failed = 0

    with OntarioGeocoderClient(delay=0.5, headless=True, verbose=True) as client:
        for i, tc in enumerate(TEST_CASES):
            addr = tc["address"]
            print(f"\n--- Test {i+1}/{len(TEST_CASES)}: {addr}")
            print(f"    Notes: {tc['notes']}")

            result = client.geocode(addr)

            if result is None:
                print(f"    FAIL: No result returned")
                failed += 1
                continue

            lat = result["lat"]
            lng = result["lng"]
            score = result["score"]
            addr_type = result["addr_type"]

            print(f"    Result: lat={lat:.6f}, lng={lng:.6f}")
            print(f"    Score: {score}, Type: {addr_type}")
            print(f"    Match: {result['match_addr']}")

            # Validate lat/lng in expected range
            lat_ok = tc["expected_lat_range"][0] <= lat <= tc["expected_lat_range"][1]
            lng_ok = tc["expected_lng_range"][0] <= lng <= tc["expected_lng_range"][1]

            if lat_ok and lng_ok:
                print(f"    PASS ✓")
                passed += 1
            else:
                print(f"    FAIL: coords out of range")
                print(f"      Expected lat: {tc['expected_lat_range']}, got {lat}")
                print(f"      Expected lng: {tc['expected_lng_range']}, got {lng}")
                failed += 1

        # Test cache hit
        print(f"\n--- Cache test: re-geocoding first address")
        result2 = client.geocode(TEST_CASES[0]["address"])
        if result2 is not None:
            print(f"    Cache hit confirmed (stats: cache_hits={client.stats['cache_hits']})")
        else:
            print(f"    FAIL: cache returned None")

        client.print_stats()

    print()
    print(f"{'=' * 60}")
    print(f"Results: {passed} passed, {failed} failed out of {len(TEST_CASES)}")
    print(f"{'=' * 60}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
