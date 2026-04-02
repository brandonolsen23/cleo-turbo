"""Tests for address decomposition and classification."""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from rt.address_normalizer.decompose import _check_special_type, decompose
from rt.address_normalizer.expand import classify_address_type


class TestSpecialTypeDetection:

    def test_lot_continuation_simple(self):
        result = _check_special_type('21, 43 & 44')
        assert result is not None
        assert result['special_type'] == 'lot_continuation'

    def test_lot_continuation_many_numbers(self):
        result = _check_special_type('14, 15, 22, 23, 27')
        assert result is not None
        assert result['special_type'] == 'lot_continuation'

    def test_lot_continuation_ampersand(self):
        result = _check_special_type('28, 32, 33, 36 & 38')
        assert result is not None
        assert result['special_type'] == 'lot_continuation'

    def test_lot_continuation_with_dash(self):
        result = _check_special_type('100, 104 & 105')
        assert result is not None
        assert result['special_type'] == 'lot_continuation'

    def test_single_number_not_lot_continuation(self):
        result = _check_special_type('42')
        assert result is None  # passes through to normal decomposition

    def test_real_address_not_caught(self):
        result = _check_special_type('21 Maple Street')
        assert result is None

    def test_real_address_with_number(self):
        result = _check_special_type('5318 Yonge Street')
        assert result is None

    def test_lots_is_legal_description(self):
        result = _check_special_type('LOTS 6, 8, 14-18')
        assert result is not None
        assert result['special_type'] == 'legal_description'

    def test_plan_is_legal_description(self):
        result = _check_special_type('PLAN 33M-666')
        assert result is not None
        assert result['special_type'] == 'legal_description'

    def test_conc_is_legal_description(self):
        result = _check_special_type('CONC 9')
        assert result is not None
        assert result['special_type'] == 'legal_description'

    def test_po_box(self):
        result = _check_special_type('P.O. Box 123')
        assert result is not None
        assert result['special_type'] == 'po_box'

    def test_rural_route(self):
        result = _check_special_type('R.R. #3')
        assert result is not None
        assert result['special_type'] == 'rural_route'


class TestAddressClassification:

    def test_street_address(self):
        components = decompose('123 Maple Street')
        addr_type = classify_address_type(components)
        assert addr_type == 'street_address'

    def test_street_name_only(self):
        components = decompose('Hazeldean Road')
        addr_type = classify_address_type(components)
        assert addr_type == 'street_name_only'

    def test_lot_continuation_classified(self):
        components = decompose('21, 43 & 44')
        addr_type = classify_address_type(components)
        assert addr_type == 'lot_continuation'

    def test_legal_description_classified(self):
        components = decompose('PLAN 33M-666')
        addr_type = classify_address_type(components)
        assert addr_type == 'legal_description'

    def test_camelot_drive_is_street(self):
        components = decompose('59 Camelot Drive')
        addr_type = classify_address_type(components)
        assert addr_type == 'street_address'

    def test_charlotte_street_is_street(self):
        components = decompose('168 Charlotte Street')
        addr_type = classify_address_type(components)
        assert addr_type == 'street_address'
