"""Unit tests for cleo.resolver.address_canonical.canonicalize_address."""
import pytest

from cleo.resolver.address_canonical import canonicalize_address


# ──────────────────────── city amalgamation ────────────────────────

def test_city_scarborough_rolls_up_to_toronto():
    assert canonicalize_address(
        "scarborough", "2555", "eglinton", "ave", "east", "suite", "212"
    ) == "toronto|2555|eglinton|ave|east|suite|212"


def test_city_north_york_rolls_up_to_toronto():
    assert canonicalize_address(
        "North York", "100", "Yonge", "st", "", "", ""
    ) == "toronto|100|yonge|st||suite|"


def test_city_nepean_rolls_up_to_ottawa():
    assert canonicalize_address(
        "Nepean", "1", "Foo", "rd", "", "", ""
    ) == "ottawa|1|foo|rd||suite|"


def test_city_unknown_passes_through_lowercased():
    assert canonicalize_address(
        "Burlington", "100", "lakeshore", "rd", "", "suite", "1"
    ) == "burlington|100|lakeshore|rd||suite|1"


def test_city_already_canonical_unchanged():
    assert canonicalize_address(
        "toronto", "2555", "eglinton", "ave", "east", "suite", "212"
    ) == "toronto|2555|eglinton|ave|east|suite|212"


# ──────────────────────── suite_type synonyms ────────────────────────

def test_suite_type_unit_canonicalizes_to_suite():
    assert canonicalize_address(
        "toronto", "1", "main", "st", "", "unit", "5"
    ) == "toronto|1|main|st||suite|5"


def test_suite_type_ste_canonicalizes_to_suite():
    assert canonicalize_address(
        "toronto", "1", "main", "st", "", "Ste", "5"
    ) == "toronto|1|main|st||suite|5"


def test_suite_type_hash_canonicalizes_to_suite():
    assert canonicalize_address(
        "toronto", "1", "main", "st", "", "#", "5"
    ) == "toronto|1|main|st||suite|5"


def test_suite_type_empty_with_number_becomes_suite():
    # Per spec §suite_type_synonyms.json: "" is in the suite group.
    assert canonicalize_address(
        "toronto", "1", "main", "st", "", "", "5"
    ) == "toronto|1|main|st||suite|5"


def test_suite_type_floor_canonicalizes_to_floor():
    assert canonicalize_address(
        "toronto", "1", "main", "st", "", "FL", "12"
    ) == "toronto|1|main|st||floor|12"


def test_suite_type_apt_canonicalizes_to_apartment():
    assert canonicalize_address(
        "toronto", "1", "main", "st", "", "apt", "5"
    ) == "toronto|1|main|st||apartment|5"


def test_suite_type_unknown_passes_through_lowercased():
    assert canonicalize_address(
        "toronto", "1", "main", "st", "", "Lobby", ""
    ) == "toronto|1|main|st||lobby|"


# ──────────────────────── suite_number normalization ────────────────────────

def test_suite_number_strips_leading_zeros():
    assert canonicalize_address(
        "toronto", "1", "main", "st", "", "suite", "0212"
    ) == "toronto|1|main|st||suite|212"


def test_suite_number_uppercases_letter_suffix():
    assert canonicalize_address(
        "toronto", "1", "main", "st", "", "suite", "212a"
    ) == "toronto|1|main|st||suite|212A"


def test_suite_number_combined_zeros_and_letter():
    assert canonicalize_address(
        "toronto", "1", "main", "st", "", "suite", "0212a"
    ) == "toronto|1|main|st||suite|212A"


def test_suite_number_empty_stays_empty():
    assert canonicalize_address(
        "toronto", "1", "main", "st", "", "suite", ""
    ) == "toronto|1|main|st||suite|"


def test_suite_number_pure_letters_unchanged_except_case():
    assert canonicalize_address(
        "toronto", "1", "main", "st", "", "suite", "ph"
    ) == "toronto|1|main|st||suite|PH"


# ──────────────────────── strict empty handling ────────────────────────

def test_empty_street_direction_does_not_borrow():
    a = canonicalize_address("toronto", "1", "main", "st", "east", "suite", "5")
    b = canonicalize_address("toronto", "1", "main", "st", "",     "suite", "5")
    assert a != b
    assert a.endswith("|east|suite|5")
    assert b.endswith("||suite|5")


def test_none_components_treated_as_empty():
    assert canonicalize_address(
        None, "1", None, "st", None, None, None
    ) == "|1||st||suite|"


def test_whitespace_only_components_treated_as_empty():
    assert canonicalize_address(
        "  ", "1", "  ", "st", "  ", "  ", "  "
    ) == "|1||st||suite|"


# ──────────────────────── Dan Hagler dedup integration ────────────────────────

def test_dan_hagler_eglinton_212_collapses_to_one_key():
    a = canonicalize_address("scarborough", "2555", "eglinton", "avenue", "east", "suite", "212")
    b = canonicalize_address("toronto",     "2555", "eglinton", "avenue", "east", "suite", "212")
    c = canonicalize_address("toronto",     "2555", "eglinton", "avenue", "east", "unit",  "212")
    d = canonicalize_address("scarborough", "2555", "eglinton", "avenue", "east", "suite", "0212")
    assert a == b == c == d == "toronto|2555|eglinton|avenue|east|suite|212"


def test_dan_hagler_eglinton_212_vs_222_kept_distinct():
    twelve = canonicalize_address("scarborough", "2555", "eglinton", "avenue", "east", "suite", "212")
    twenty_two = canonicalize_address("scarborough", "2555", "eglinton", "avenue", "east", "suite", "222")
    assert twelve != twenty_two


# ──────────────────────── deterministic / stable ────────────────────────

def test_function_is_deterministic():
    args = ("scarborough", "2555", "eglinton", "avenue", "east", "unit", "0212a")
    result_1 = canonicalize_address(*args)
    result_2 = canonicalize_address(*args)
    assert result_1 == result_2 == "toronto|2555|eglinton|avenue|east|suite|212A"
