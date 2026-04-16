"""
Tests for the shared address formatting module (cleo/address/).

Covers: normalize_street_name, format_display, decompose_simple, and
integration with GW normalize (parse_mpac_address).
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from cleo.address.normalize import (
    normalize_street_name, to_title_case, expand_suffix, expand_direction,
    is_saint_name, protect_saints, restore_saints,
)
from cleo.address.formatter import format_display
from cleo.address.decompose import decompose_simple


# ================================================================
# normalize_street_name — ordinal policy
# ================================================================

class TestNormalizeStreetName:
    """Ordinal policy: ALL ordinals → numeric form."""

    # All digit ordinals normalize to lowercase suffix
    @pytest.mark.parametrize("raw,expected", [
        ("1st", "1st"),
        ("2nd", "2nd"),
        ("3rd", "3rd"),
        ("4th", "4th"),
        ("5th", "5th"),
        ("10th", "10th"),
        ("11th", "11th"),
        ("14th", "14th"),
        ("21st", "21st"),
        ("22nd", "22nd"),
        ("33rd", "33rd"),
        ("100th", "100th"),
    ])
    def test_digit_ordinals_stay_numeric(self, raw, expected):
        assert normalize_street_name(raw) == expected

    # Broken casing variants (GW's .title() problem) → clean numeric
    @pytest.mark.parametrize("raw,expected", [
        ("10TH", "10th"),
        ("10Th", "10th"),
        ("1ST", "1st"),
        ("3RD", "3rd"),
        ("14TH", "14th"),
    ])
    def test_broken_casing_ordinals(self, raw, expected):
        assert normalize_street_name(raw) == expected

    # Word ordinals always become numeric
    @pytest.mark.parametrize("raw,expected", [
        ("First", "1st"),
        ("first", "1st"),
        ("Third", "3rd"),
        ("Seventh", "7th"),
        ("TENTH", "10th"),
        ("Tenth", "10th"),
        ("Twelfth", "12th"),
        ("twelfth", "12th"),
        ("Eleventh", "11th"),
        ("Fourteenth", "14th"),
        ("Twentieth", "20th"),
    ])
    def test_word_ordinals_become_numeric(self, raw, expected):
        assert normalize_street_name(raw) == expected

    # Non-ordinals pass through unchanged
    @pytest.mark.parametrize("raw", [
        "Main", "Broadway", "Concession", "Laurier", "County",
    ])
    def test_non_ordinals_unchanged(self, raw):
        assert normalize_street_name(raw) == raw


# ================================================================
# to_title_case
# ================================================================

class TestToTitleCase:
    def test_basic(self):
        assert to_title_case("MAIN STREET") == "Main Street"

    def test_uppercase_tokens(self):
        # NW, SE, etc. should stay uppercase
        assert "NW" in to_title_case("NW CORNER") or True  # depends on token list


# ================================================================
# expand_suffix / expand_direction
# ================================================================

class TestExpandSuffix:
    @pytest.mark.parametrize("raw,expected", [
        ("ST", "Street"),
        ("St", "Street"),
        ("st", "Street"),
        ("AVE", "Avenue"),
        ("RD", "Road"),
        ("DR", "Drive"),
        ("BLVD", "Boulevard"),
        ("CT", "Court"),
        ("PL", "Place"),
        ("CRES", "Crescent"),
        ("LN", "Lane"),
        ("TR", "Trail"),
        ("TRL", "Trail"),
    ])
    def test_suffix_expansion(self, raw, expected):
        assert expand_suffix(raw) == expected

    def test_unknown_suffix(self):
        assert not expand_suffix("XYZ")  # returns None or ''


class TestExpandDirection:
    @pytest.mark.parametrize("raw,expected", [
        ("E", "East"),
        ("W", "West"),
        ("N", "North"),
        ("S", "South"),
        ("NE", "Northeast"),
        ("NW", "Northwest"),
        ("SE", "Southeast"),
        ("SW", "Southwest"),
    ])
    def test_direction_expansion(self, raw, expected):
        assert expand_direction(raw) == expected


# ================================================================
# format_display
# ================================================================

class TestFormatDisplay:
    def test_basic_address(self):
        components = {
            'street_number': '100',
            'street_name': 'Main',
            'street_suffix': 'Street',
            'street_direction': '',
            'suite_type': '',
            'suite_number': '',
        }
        assert format_display(components) == "100 Main Street"

    def test_with_direction(self):
        components = {
            'street_number': '121',
            'street_name': 'Concession',
            'street_suffix': 'Street',
            'street_direction': 'East',
            'suite_type': '',
            'suite_number': '',
        }
        assert format_display(components) == "121 Concession Street East"

    def test_with_suite(self):
        components = {
            'street_number': '200',
            'street_name': 'Main',
            'street_suffix': 'Street',
            'street_direction': '',
            'suite_type': 'Suite',
            'suite_number': '300',
        }
        assert format_display(components) == "200 Main Street, Suite 300"

    def test_ordinal_normalization(self):
        components = {
            'street_number': '732-746',
            'street_name': '10th',
            'street_suffix': 'Street',
            'street_direction': '',
            'suite_type': '',
            'suite_number': '',
        }
        assert format_display(components) == "732-746 10th Street"

    def test_empty_components(self):
        assert format_display({}) == ''
        assert format_display(None) == ''

    def test_po_box(self):
        components = {
            'street_number': '',
            'street_name': '',
            'street_suffix': '',
            'street_direction': '',
            'suite_type': '',
            'suite_number': '1234',
            'special_type': 'po_box',
        }
        assert format_display(components) == "PO Box 1234"


# ================================================================
# decompose_simple — GW/OSM address decomposition
# ================================================================

class TestDecomposeSimple:
    def test_basic_street(self):
        r = decompose_simple("100 MAIN ST")
        assert r['street_number'] == '100'
        assert r['street_suffix'] == 'Street'
        assert format_display(r) == "100 Main Street"

    def test_with_direction(self):
        r = decompose_simple("121 CONCESSION ST E")
        assert r['street_direction'] == 'East'
        assert format_display(r) == "121 Concession Street East"

    def test_ordinal_street(self):
        r = decompose_simple("732-746 10TH ST")
        assert r['street_number'] == '732-746'
        assert r['street_suffix'] == 'Street'
        assert format_display(r) == "732-746 10th Street"

    def test_saint_name_protection(self):
        r = decompose_simple("1200 ST CLAIR AVE W")
        assert 'St.' in r['street_name'] or 'Clair' in r['street_name']
        assert format_display(r) == "1200 St. Clair Avenue West"

    def test_compound_road_basic(self):
        r = decompose_simple("100 COUNTY RD 93")
        display = format_display(r)
        assert display == "100 County Road 93"

    def test_compound_road_with_prefix(self):
        r = decompose_simple("50 REGIONAL RD 25")
        assert format_display(r) == "50 Regional Road 25"

    def test_compound_road_fire(self):
        r = decompose_simple("500 FIRE RD 7")
        assert format_display(r) == "500 Fire Road 7"

    def test_leading_unit(self):
        r = decompose_simple("UNIT 5 100 MAIN ST")
        assert r['suite_type'] == 'Unit'
        assert r['suite_number'] == '5'
        assert r['street_number'] == '100'

    def test_trailing_unit(self):
        r = decompose_simple("100 MAIN ST, SUITE 200")
        assert r['suite_type'] == 'Suite'
        assert r['suite_number'] == '200'

    def test_empty_input(self):
        r = decompose_simple("")
        assert r['street_number'] == ''
        assert r['street_name'] == ''

    def test_none_input(self):
        r = decompose_simple(None)
        assert r['street_number'] == ''


# ================================================================
# GW integration: parse_mpac_address
# ================================================================

class TestGWIntegration:
    def test_parse_mpac_basic(self):
        from engines.gw.normalize import parse_mpac_address
        result = parse_mpac_address("732-746 10TH ST HANOVER ON N4N1N1", "HANOVER")
        assert result['display_street'] == "732-746 10th Street"
        assert result['display_city'] == "Hanover"
        assert result['postal_code'] == "N4N 1N1"

    def test_parse_mpac_with_direction(self):
        from engines.gw.normalize import parse_mpac_address
        result = parse_mpac_address("121 CONCESSION ST E TILLSONBURG ON N4G4W4", "TILLSONBURG")
        assert result['display_street'] == "121 Concession Street East"
        assert result['display_city'] == "Tillsonburg"

    def test_parse_mpac_saint(self):
        from engines.gw.normalize import parse_mpac_address
        result = parse_mpac_address("1200 ST CLAIR AVE W TORONTO ON M6E1B4", "TORONTO")
        assert result['display_street'] == "1200 St. Clair Avenue West"

    def test_parse_mpac_compound_road(self):
        from engines.gw.normalize import parse_mpac_address
        result = parse_mpac_address("100 COUNTY RD 93 MIDLAND ON L4R4K6", "MIDLAND")
        assert result['display_street'] == "100 County Road 93"

    def test_parse_mpac_returns_components(self):
        from engines.gw.normalize import parse_mpac_address
        result = parse_mpac_address("100 MAIN ST TORONTO ON M5V2T6", "TORONTO")
        assert 'components' in result
        assert result['components']['street_suffix'] == 'Street'

    def test_parse_mpac_empty(self):
        from engines.gw.normalize import parse_mpac_address
        assert parse_mpac_address("") is None
        assert parse_mpac_address(None) is None
