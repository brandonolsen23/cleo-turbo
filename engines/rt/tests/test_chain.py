"""Tests for the parcel resolution chain with cross-validation."""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from rt.parcel_resolver.chain import resolve_record, _haversine_m


class MockClient:
    """Mock AgMapsClient for testing."""

    def __init__(self, arn_results=None, point_results=None):
        self.arn_results = arn_results or {}
        self.point_results = point_results or {}

    def query_by_arn(self, arn):
        return self.arn_results.get(arn)

    def query_by_point(self, lat, lng):
        key = f'{lat:.4f},{lng:.4f}'
        return self.point_results.get(key)


def _make_parcel(arn, lat=43.5, lng=-79.5):
    return {
        'arn': arn,
        'geometry': {'type': 'Polygon', 'coordinates': []},
        'centroid': [lat, lng],
    }


class TestHaversine:

    def test_same_point(self):
        assert _haversine_m(43.5, -79.5, 43.5, -79.5) == 0

    def test_known_distance(self):
        # ~111km per degree latitude
        dist = _haversine_m(43.0, -79.5, 44.0, -79.5)
        assert 110000 < dist < 112000

    def test_small_distance(self):
        dist = _haversine_m(43.5, -79.5, 43.5001, -79.5001)
        assert dist < 20  # < 20 meters


class TestCrossValidation:

    def test_arn_verified_both_agree(self):
        """ARN and spatial return same parcel → arn_verified."""
        arn = '12345678901234500000'
        parcel = _make_parcel(arn)
        client = MockClient(
            arn_results={arn: parcel},
            point_results={'43.5000,-79.5000': parcel},
        )
        result = resolve_record(arn, {'lat': 43.5, 'lng': -79.5}, client)
        assert result['method'] == 'arn_verified'
        assert result['resolved_arn'] == arn

    def test_spatial_override_disagree(self):
        """ARN and spatial return different parcels → trust spatial."""
        wrong_arn = '11111111111111100000'
        right_arn = '22222222222222200000'
        client = MockClient(
            arn_results={wrong_arn: _make_parcel(wrong_arn, 44.0, -80.0)},
            point_results={'43.5000,-79.5000': _make_parcel(right_arn)},
        )
        result = resolve_record(wrong_arn, {'lat': 43.5, 'lng': -79.5}, client)
        assert result['method'] == 'spatial_override'
        assert result['resolved_arn'] == right_arn

    def test_arn_only_no_coords(self):
        """ARN resolves but no coords to validate → arn_unverified."""
        arn = '12345678901234500000'
        client = MockClient(arn_results={arn: _make_parcel(arn)})
        result = resolve_record(arn, None, client)
        assert result['method'] == 'arn_unverified'
        assert result['resolved_arn'] == arn

    def test_spatial_only_no_arn(self):
        """No ARN, resolved via spatial → spatial_geocode."""
        arn_result = '12345678901234500000'
        client = MockClient(
            point_results={'43.5000,-79.5000': _make_parcel(arn_result)},
        )
        result = resolve_record('', {'lat': 43.5, 'lng': -79.5}, client)
        assert result['method'] == 'spatial_geocode'
        assert result['resolved_arn'] == arn_result

    def test_arn_too_far_from_geocoded(self):
        """ARN resolves but centroid is >500m from geocoded address → rejected.

        Uses an ARN unlikely to be in the real parcel cache.
        """
        arn = '99988877766655500000'
        # Parcel centroid at 44.0, -80.0 — far from geocoded 43.5, -79.5
        client = MockClient(arn_results={arn: _make_parcel(arn, 44.0, -80.0)})
        result = resolve_record(arn, {'lat': 43.5, 'lng': -79.5}, client)
        assert result['method'] == 'unresolved'
        assert 'too_far' in result['reason']

    def test_neither_resolves(self):
        """No ARN, no coords → unresolved."""
        client = MockClient()
        result = resolve_record('', None, client)
        assert result['method'] == 'unresolved'
        assert result['reason'] == 'no_identifiers'

    def test_arn_miss_spatial_succeeds(self):
        """ARN doesn't exist in AgMaps, but spatial finds parcel."""
        wrong_arn = '99999999999999900000'
        right_arn = '12345678901234500000'
        client = MockClient(
            arn_results={},  # wrong ARN not found
            point_results={'43.5000,-79.5000': _make_parcel(right_arn)},
        )
        result = resolve_record(wrong_arn, {'lat': 43.5, 'lng': -79.5}, client)
        assert result['method'] == 'spatial_geocode'
        assert result['resolved_arn'] == right_arn

    def test_both_fail(self):
        """ARN not found, spatial returns nothing."""
        client = MockClient()
        result = resolve_record('99999999999999900000', {'lat': 43.5, 'lng': -79.5}, client)
        assert result['method'] == 'unresolved'
        assert result['reason'] == 'both_failed'


class TestResolverStatsAlignment:
    """Verify the resolver stats dict has all possible chain method values."""

    def test_all_chain_methods_in_stats(self):
        """Every method the chain can return must be a key in the resolver stats dict."""
        # All possible methods from chain.py
        chain_methods = {
            'arn_cache', 'arn_api', 'arn_verified', 'arn_unverified',
            'spatial_geocode', 'spatial_override', 'unresolved',
        }

        # Read the stats dict from resolve.py
        import ast
        with open('engines/rt/parcel_resolver/resolve.py') as f:
            source = f.read()

        # The stats dict should contain all chain methods
        for method in chain_methods:
            assert f"'{method}'" in source, f"Method '{method}' not found in resolve.py stats dict"
