"""Unit tests for cleo.atoms.normalize — one test function per normalizer.

Each test covers:
  - None input -> None
  - Empty / whitespace -> None
  - 3-5 realistic cases from the docstring examples
  - 1-2 edge cases
"""

import pytest
from cleo.atoms.normalize import (
    normalize_brand,
    tokenize_brand,
    normalize_contact_name,
    normalize_phone,
    normalize_street_number,
    normalize_street_name,
    normalize_street_suffix,
    normalize_street_direction,
    normalize_suite_type,
    normalize_suite_number,
    normalize_city,
    normalize_province,
    normalize_postal,
    normalize_country,
)


# ── normalize_brand ───────────────────────────────────────────────────

def test_normalize_brand():
    # None / empty
    assert normalize_brand(None) is None
    assert normalize_brand("") is None
    assert normalize_brand("   ") is None

    # Docstring examples
    assert normalize_brand("KingSett Capital Inc.") == "kingsett capital"
    assert normalize_brand("H&R REIT") == "h&r reit"
    assert normalize_brand("The  Regional  Group") == "the regional group"
    assert normalize_brand("c/o Plazacorp Investments Ltd") == "c o plazacorp investments"

    # Edge cases
    # & survives, punctuation removed
    assert normalize_brand("DH Management Ltd.") == "dh management"
    assert normalize_brand("RioCan Real Estate Investment Trust") == "riocan real estate investment trust"
    # Parens become spaces and collapse
    assert normalize_brand("Smith (Holdings) Corp.") == "smith holdings"
    # Multiple punctuation types
    assert normalize_brand("Oxford, Properties; Group.") == "oxford properties group"


# ── tokenize_brand ────────────────────────────────────────────────────

def test_tokenize_brand():
    # None / empty
    assert tokenize_brand(None) == []
    assert tokenize_brand("") == []

    # Docstring examples
    assert tokenize_brand("kingsett capital") == ["kingsett", "capital"]
    assert tokenize_brand("the regional group") == ["regional", "group"]
    assert tokenize_brand("h&r reit") == ["h&r", "reit"]
    assert tokenize_brand("c o plazacorp investments") == ["plazacorp", "investments"]

    # Edge cases
    # Tokens < 2 chars dropped, stopwords dropped
    assert tokenize_brand("a of the co") == []
    # Deduplication preserves order
    assert tokenize_brand("kingsett kingsett capital") == ["kingsett", "capital"]
    # & as standalone is a stopword
    assert tokenize_brand("h & r block") == ["block"]


# ── normalize_contact_name ────────────────────────────────────────────

def test_normalize_contact_name():
    # None / empty
    assert normalize_contact_name(None, None) is None
    assert normalize_contact_name("", "") is None
    assert normalize_contact_name(" ", " ") is None

    # Docstring examples
    assert normalize_contact_name("Dan", "Hagler") == "dan hagler"
    assert normalize_contact_name("Mr. Peter", "Aghar") == "peter aghar"
    assert normalize_contact_name("Jonathan", "Gitlin Jr.") == "jonathan gitlin"
    assert normalize_contact_name(None, "Smith") == "smith"

    # Edge cases
    # First only
    assert normalize_contact_name("Alice", None) == "alice"
    # Multiple honorifics (unusual but should still strip first)
    assert normalize_contact_name("Dr.", "Richards") == "richards"
    # Suffix variants
    assert normalize_contact_name("Robert", "Evans III") == "robert evans"
    assert normalize_contact_name("Henry", "Park Sr.") == "henry park"
    # Lowercase honorific passthrough (already handled)
    assert normalize_contact_name("mrs Jane", "Doe") == "jane doe"


# ── normalize_phone ───────────────────────────────────────────────────

def test_normalize_phone():
    # None / empty
    assert normalize_phone(None) is None
    assert normalize_phone("") is None
    assert normalize_phone("   ") is None

    # Docstring examples
    assert normalize_phone("(416) 687-6700") == "4166876700"
    assert normalize_phone("+1 416 687 6700") == "4166876700"
    assert normalize_phone("1-416-687-6700") == "4166876700"
    assert normalize_phone("416.687.6700") == "4166876700"
    assert normalize_phone("ext 234") is None

    # Edge cases
    # Too short after stripping non-digits
    assert normalize_phone("123") is None
    assert normalize_phone("000000") is None  # 6 digits — below threshold
    # 7-digit number stays intact
    assert normalize_phone("867-5309") == "8675309"
    # 11-digit starting with 1 → strip leading 1
    assert normalize_phone("14165551234") == "4165551234"
    # 11-digit NOT starting with 1 → keep all 11
    assert normalize_phone("24165551234") == "24165551234"


# ── normalize_street_number ───────────────────────────────────────────

def test_normalize_street_number():
    # None / empty
    assert normalize_street_number(None) is None
    assert normalize_street_number("") is None
    assert normalize_street_number("  ") is None

    # Docstring examples
    assert normalize_street_number("030") == "30"
    assert normalize_street_number("30A") == "30a"
    assert normalize_street_number("0030-32") == "30-32"

    # Edge cases
    assert normalize_street_number("1") == "1"
    assert normalize_street_number("0001") == "1"
    # Mixed alphabetic (lowercase)
    assert normalize_street_number("12B") == "12b"
    # No leading zeros to strip
    assert normalize_street_number("500") == "500"


# ── normalize_street_name ─────────────────────────────────────────────

def test_normalize_street_name():
    # None / empty
    assert normalize_street_name(None) is None
    assert normalize_street_name("") is None
    assert normalize_street_name("   ") is None

    # Docstring examples
    assert normalize_street_name("Wellington") == "wellington"
    assert normalize_street_name("St. John's") == "saint johns"
    assert normalize_street_name("St Clair") == "saint clair"
    assert normalize_street_name("Bay") == "bay"
    assert normalize_street_name("O'Connor") == "oconnor"

    # Edge cases
    # "ft" expansion
    assert normalize_street_name("Ft. York") == "fort york"
    assert normalize_street_name("Mt. Pleasant") == "mount pleasant"
    # "St" alone should NOT expand (no following word) — stays as-is
    assert normalize_street_name("St") == "st"
    # Extra whitespace collapses
    assert normalize_street_name("King   Street") == "king street"
    # Mixed case
    assert normalize_street_name("QUEEN") == "queen"


# ── normalize_street_suffix ───────────────────────────────────────────

def test_normalize_street_suffix():
    # None / empty
    assert normalize_street_suffix(None) is None
    assert normalize_street_suffix("") is None
    assert normalize_street_suffix("  ") is None

    # Docstring examples
    assert normalize_street_suffix("St") == "street"
    assert normalize_street_suffix("Ave.") == "avenue"
    assert normalize_street_suffix("Blvd") == "boulevard"
    assert normalize_street_suffix("Road") == "road"

    # Additional table entries
    assert normalize_street_suffix("Dr") == "drive"
    assert normalize_street_suffix("Cres") == "crescent"
    assert normalize_street_suffix("Pkwy") == "parkway"
    assert normalize_street_suffix("Hwy") == "highway"
    assert normalize_street_suffix("Conc") == "concession"
    assert normalize_street_suffix("Sdrd") == "sideroad"

    # Unknown suffix — lowercased passthrough
    assert normalize_street_suffix("Mews") == "mews"
    # Case insensitive
    assert normalize_street_suffix("BLVD") == "boulevard"


# ── normalize_street_direction ────────────────────────────────────────

def test_normalize_street_direction():
    # None / empty
    assert normalize_street_direction(None) is None
    assert normalize_street_direction("") is None
    assert normalize_street_direction("  ") is None

    # Docstring examples
    assert normalize_street_direction("W") == "west"
    assert normalize_street_direction("NE") == "northeast"
    assert normalize_street_direction("North") == "north"

    # All cardinals
    assert normalize_street_direction("S") == "south"
    assert normalize_street_direction("E") == "east"
    assert normalize_street_direction("NW") == "northwest"
    assert normalize_street_direction("SE") == "southeast"
    assert normalize_street_direction("SW") == "southwest"

    # With dots
    assert normalize_street_direction("N.") == "north"

    # Unknown — passthrough lowercased
    assert normalize_street_direction("SSW") == "ssw"


# ── normalize_suite_type ──────────────────────────────────────────────

def test_normalize_suite_type():
    # None / empty
    assert normalize_suite_type(None) is None
    assert normalize_suite_type("") is None
    assert normalize_suite_type("  ") is None

    # Docstring examples
    assert normalize_suite_type("Suite") == "suite"
    assert normalize_suite_type("Ste.") == "suite"
    assert normalize_suite_type("PO Box") == "po_box"
    assert normalize_suite_type("P.O. Box") == "po_box"
    assert normalize_suite_type("Floor") == "floor"

    # Other entries
    assert normalize_suite_type("Unit") == "unit"
    assert normalize_suite_type("Apt") == "unit"
    assert normalize_suite_type("Apartment") == "unit"
    assert normalize_suite_type("Penthouse") == "penthouse"
    assert normalize_suite_type("PH") == "penthouse"

    # Case insensitive
    assert normalize_suite_type("SUITE") == "suite"
    assert normalize_suite_type("flr") == "floor"

    # Unknown — lowercased passthrough
    assert normalize_suite_type("Mezzanine") == "mezzanine"


# ── normalize_suite_number ────────────────────────────────────────────

def test_normalize_suite_number():
    # None / empty
    assert normalize_suite_number(None) is None
    assert normalize_suite_number("") is None
    assert normalize_suite_number("  ") is None

    # Docstring examples
    assert normalize_suite_number("4400") == "4400"
    assert normalize_suite_number("0200") == "200"
    assert normalize_suite_number("PH2") == "ph2"
    assert normalize_suite_number("A-12") == "a-12"

    # Edge cases
    # Surrounding parens stripped
    assert normalize_suite_number("(400)") == "400"
    # Leading zeros in numeric
    assert normalize_suite_number("0001") == "1"
    # Already clean
    assert normalize_suite_number("200") == "200"
    # Alpha preserved
    assert normalize_suite_number("B14") == "b14"


# ── normalize_city ────────────────────────────────────────────────────

def test_normalize_city():
    # None / empty
    assert normalize_city(None) is None
    assert normalize_city("") is None
    assert normalize_city("  ") is None

    # Docstring examples
    assert normalize_city("Toronto") == "toronto"
    assert normalize_city("Québec") == "quebec"
    assert normalize_city("St. John's") == "st johns"

    # Edge cases
    assert normalize_city("Mississauga") == "mississauga"
    # Diacritics stripped
    assert normalize_city("Montréal") == "montreal"
    # Extra whitespace
    assert normalize_city("  Ottawa  ") == "ottawa"
    # Apostrophe in name
    assert normalize_city("L'Orignal") == "lorignal"


# ── normalize_province ────────────────────────────────────────────────

def test_normalize_province():
    # None / empty
    assert normalize_province(None) is None
    assert normalize_province("") is None
    assert normalize_province("  ") is None

    # Docstring examples
    assert normalize_province("Ontario") == "ontario"
    assert normalize_province("ON") == "ontario"
    assert normalize_province("Québec") == "quebec"
    assert normalize_province("CA") == "ca"  # US state fallthrough

    # Other provinces
    assert normalize_province("BC") == "british_columbia"
    assert normalize_province("AB") == "alberta"
    assert normalize_province("MB") == "manitoba"
    assert normalize_province("NS") == "nova_scotia"
    assert normalize_province("NL") == "newfoundland"
    assert normalize_province("Newfoundland and Labrador") == "newfoundland"
    assert normalize_province("PE") == "prince_edward_island"

    # Abbreviation with period
    assert normalize_province("Ont") == "ontario"

    # Unknown / US state — lowercased passthrough
    assert normalize_province("NY") == "ny"


# ── normalize_postal ──────────────────────────────────────────────────

def test_normalize_postal():
    # None / empty
    assert normalize_postal(None) is None
    assert normalize_postal("") is None
    assert normalize_postal("  ") is None

    # Docstring examples
    assert normalize_postal("m5k 1h6") == "M5K1H6"
    assert normalize_postal("M5K1H6") == "M5K1H6"
    assert normalize_postal("90210") == "90210"
    assert normalize_postal("90210-1234") == "90210-1234"

    # Edge cases
    # Lowercase Canadian with space
    assert normalize_postal("k1a 0a9") == "K1A0A9"
    # Already uppercase, no space
    assert normalize_postal("K1A0A9") == "K1A0A9"
    # US ZIP only (no +4)
    assert normalize_postal("10001") == "10001"


# ── normalize_country ─────────────────────────────────────────────────

def test_normalize_country():
    # None / empty
    assert normalize_country(None) is None
    assert normalize_country("") is None
    assert normalize_country("  ") is None

    # Docstring examples
    assert normalize_country("Canada") == "canada"
    assert normalize_country("CA") == "canada"
    assert normalize_country("USA") == "united_states"

    # Other variants
    assert normalize_country("US") == "united_states"
    assert normalize_country("Can") == "canada"
    assert normalize_country("United States") == "united_states"
    assert normalize_country("United States of America") == "united_states"

    # Unknown — lowercased passthrough
    assert normalize_country("Mexico") == "mexico"
    assert normalize_country("UK") == "uk"


def test_normalize_postal_returns_none_for_invalid_format():
    from cleo.atoms.normalize import normalize_postal
    # 61 such values exist in the current corpus per the exploration report.
    assert normalize_postal("M4W 3E23") is None
    assert normalize_postal("L4L-1N4") is None
    assert normalize_postal("BB15006") is None
    assert normalize_postal("K2G 12E4") is None

def test_normalize_postal_still_accepts_valid_ca_and_us():
    from cleo.atoms.normalize import normalize_postal
    assert normalize_postal("m5k 1h6") == "M5K1H6"
    assert normalize_postal("M5K1H6") == "M5K1H6"
    assert normalize_postal("90210") == "90210"
    assert normalize_postal("90210-1234") == "90210-1234"
