"""Tests for ARN and PIN normalization."""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from rt.address_normalizer.pin_arn import normalize_arn, normalize_pin


class TestARNNormalization:

    def test_standard_15_digit(self):
        result = normalize_arn('21 10 100 025 27110')
        assert result['api_format'] == '21101000252711000000'

    def test_no_spaces(self):
        result = normalize_arn('211010002527110')
        assert result['api_format'] == '21101000252711000000'

    def test_preserves_original(self):
        result = normalize_arn('21 10 100 025 27110')
        assert result['original'] == '21 10 100 025 27110'

    def test_empty_string(self):
        result = normalize_arn('')
        assert result['api_format'] == ''

    def test_none(self):
        result = normalize_arn(None)
        assert result['api_format'] == ''

    def test_rejects_registry_number_hr(self):
        result = normalize_arn('HR-120738')
        assert result['api_format'] == ''

    def test_rejects_registry_number_at(self):
        result = normalize_arn('AT-3700975')
        assert result['api_format'] == ''

    def test_rejects_registry_number_kl(self):
        result = normalize_arn('KL-90916')
        assert result['api_format'] == ''

    def test_rejects_decimal_number(self):
        result = normalize_arn('61.14769')
        assert result['api_format'] == ''

    def test_rejects_short_digits(self):
        result = normalize_arn('33333')
        assert result['api_format'] == ''

    def test_rejects_12_digits(self):
        result = normalize_arn('123456789012')
        assert result['api_format'] == ''

    def test_accepts_13_digits(self):
        result = normalize_arn('1234567890123')
        assert result['api_format'] != ''

    def test_accepts_14_digits(self):
        result = normalize_arn('12345678901234')
        assert result['api_format'] != ''

    def test_pads_to_20(self):
        result = normalize_arn('342104054016920')
        assert len(result['api_format']) == 20
        assert result['api_format'] == '34210405401692000000'


class TestPINNormalization:

    def test_standard_9_digit_with_dash(self):
        result = normalize_pin('14024-0032')
        assert result['api_format'] == '140240032'

    def test_standard_9_digit_no_dash(self):
        result = normalize_pin('140240032')
        assert result['api_format'] == '140240032'

    def test_does_not_truncate_10_digit(self):
        result = normalize_pin('21102-02000')
        assert result['api_format'] == '2110202000'
        assert len(result['api_format']) == 10

    def test_pads_short_pin(self):
        result = normalize_pin('12345')
        assert result['api_format'] == '123450000'

    def test_empty_string(self):
        result = normalize_pin('')
        assert result['api_format'] == ''

    def test_multiple_pins(self):
        result = normalize_pin('14024-0032 and 14024-0033')
        assert result['multiple'] is True
        assert '140240032' in result['api_format']
        assert '140240033' in result['api_format']

    def test_comma_separated(self):
        result = normalize_pin('14024-0032, 14024-0033')
        assert result['multiple'] is True
