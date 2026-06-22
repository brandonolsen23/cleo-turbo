"""Stage 1 — unit tests for parcel-resolution verification.

Pure/offline: field-match canonicalization, tier assignment, geocode cache.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from cleo.resolver import verify as v
from cleo.resolver import geocode_cache as gc


# ── field_match canonicalization ────────────────────────────────────
def test_fmatch_suffix_abbreviation():
    assert v.field_match("107", "Edward St", "St Thomas",
                         "107", "Edward Street", "ST THOMAS")


def test_fmatch_case_insensitive_mc():
    assert v.field_match("4410", "Mccordick Road", "Gloucester",
                         "4410", "McCordick Rd", "GLOUCESTER")


def test_fmatch_leading_saint_not_treated_as_suffix():
    assert v.field_match("100", "St Clair Ave", "Toronto",
                         "100", "St Clair Avenue", "TORONTO")


def test_fmatch_house_mismatch_fails():
    assert not v.field_match("107", "Edward St", "St Thomas",
                             "101", "Edward Street", "ST THOMAS")


def test_fmatch_ordinal_word_vs_digit_does_not_match():
    # Known edge: geocoder digit form vs spelled form -> NOT equal (-> review)
    assert not v.field_match("10", "10th Ave", "Toronto",
                             "10", "Tenth Avenue", "TORONTO")


def test_fmatch_city_period_and_prefix():
    assert v.field_match("1", "Main St", "St. Thomas",
                         "1", "Main Street", "CITY OF ST THOMAS")


# ── tier assignment ─────────────────────────────────────────────────
def test_tier_verified():
    assert v.assign_tier(loc_name="PARCEL_PCCF", addr_type="PointAddress",
                         containment="contained", fmatch=True) == v.VERIFIED


def test_tier_probable_pointaddress_no_fieldmatch():
    assert v.assign_tier(loc_name="PARCEL_MUN", addr_type="PointAddress",
                         containment="contained", fmatch=False) == v.PROBABLE


def test_tier_review_interpolated():
    assert v.assign_tier(loc_name="Roads_Locator", addr_type="StreetAddress",
                         containment="contained", fmatch=False) == v.REVIEW


def test_tier_review_not_contained():
    assert v.assign_tier(loc_name="PARCEL_PCCF", addr_type="PointAddress",
                         containment="nearest_centroid", fmatch=True) == v.REVIEW


def test_tier_review_on_disagreement():
    assert v.assign_tier(loc_name="PARCEL_PCCF", addr_type="PointAddress",
                         containment="contained", fmatch=True,
                         agrees_with_placement=False) == v.REVIEW


# ── tier_for (full-result mapping) ──────────────────────────────────
def test_tier_for_strong_methods():
    assert v.tier_for("verified", None, None, None, False) == v.VERIFIED
    assert v.tier_for("spatial_consensus", None, None, None, False) == v.VERIFIED
    assert v.tier_for("spatial_coords", None, None, None, False) == v.VERIFIED


def test_tier_for_weak_methods_are_review():
    assert v.tier_for("arn_only", None, None, None, False) == v.REVIEW
    assert v.tier_for("pin_bridge", None, None, None, False) == v.REVIEW
    assert v.tier_for("unresolved", None, None, None, False) == v.REVIEW


def test_tier_for_geocode_uses_signals():
    assert v.tier_for("spatial_geocode", "PARCEL_PCCF", "PointAddress",
                      "contained", True) == v.VERIFIED
    assert v.tier_for("spatial_geocode", "Roads_Locator", "StreetAddress",
                      "nearest_centroid", False) == v.REVIEW


# ── geocode cache ───────────────────────────────────────────────────
def test_cache_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(gc, "CACHE_DIR", str(tmp_path))
    addr = "123 Example Rd, Sometown, ON"
    assert not gc.cache_has(addr)
    gc.cache_write(addr, {"lat": 1.0, "lng": 2.0})
    assert gc.cache_has(addr)
    assert gc.cache_read_safe(addr) == {"lat": 1.0, "lng": 2.0}


def test_cache_stores_miss(tmp_path, monkeypatch):
    monkeypatch.setattr(gc, "CACHE_DIR", str(tmp_path))
    addr = "404 Nowhere St, Nullville, ON"
    gc.cache_write(addr, None)
    assert gc.cache_has(addr)               # a miss is remembered
    assert gc.cache_read_safe(addr) is None


def test_cache_canonical_key_is_stable():
    assert gc.canonical_key("107 Edward St., ST THOMAS, ON.") == \
           gc.canonical_key("107   edward st  st thomas on")
