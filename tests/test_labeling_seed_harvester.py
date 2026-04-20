"""Tests for the seed harvester — extracts search seeds from a party view."""

import pytest
from cleo.labeling.seed_harvester import harvest_seeds


def test_harvest_covers_all_field_types():
    view = {
        "source_id": "RT148276", "side": "buyer",
        "party_rows": [
            {"party_name": "Niagara Falls Shopping Centre Inc", "phone": "416-265-5055", "contact_id": None},
            {"party_name": None, "phone": None, "contact_id": "CON_1"},
        ],
        "trade_name": "DH Management Inc",
        "care_of": "c/o DH Properties",
        "companies_other": ["DH Properties"],
        "law_firms": ["Smith LLP"],
        "contacts": [{"name": "Dan Hagler", "phone": "416-265-5055", "role": "Pres"}],
        "mailing": {"display": "180 Shorting Rd, Toronto M1S 3S7"},
        "phones": ["416-265-5055"],
    }
    seeds = harvest_seeds(view)
    by_type = {(s["field_type"], s["term"]) for s in seeds}

    assert ("party_name", "Niagara Falls Shopping Centre Inc") in by_type
    assert ("trade_name", "DH Management Inc") in by_type
    assert ("care_of", "c/o DH Properties") in by_type
    assert ("company_other", "DH Properties") in by_type
    assert ("law_firm", "Smith LLP") in by_type
    assert ("contact_name", "Dan Hagler") in by_type
    assert ("address", "180 Shorting Rd, Toronto M1S 3S7") in by_type
    assert ("phone", "416-265-5055") in by_type


def test_harvest_dedups_and_strips():
    view = {
        "source_id": "RT1", "side": "buyer",
        "party_rows": [{"party_name": "  Acme Corp  ", "phone": None, "contact_id": None}],
        "trade_name": "Acme Corp",  # same as party_name — should still appear once per field_type
        "care_of": None, "companies_other": [], "law_firms": [],
        "contacts": [], "mailing": None, "phones": [],
    }
    seeds = harvest_seeds(view)

    # Same term "Acme Corp" under different field_types — both kept (they trigger different searches)
    terms_by_type = {(s["field_type"], s["term"]) for s in seeds}
    assert ("party_name", "Acme Corp") in terms_by_type
    assert ("trade_name", "Acme Corp") in terms_by_type


def test_harvest_ignores_blanks_and_none():
    view = {
        "source_id": "RT1", "side": "buyer",
        "party_rows": [{"party_name": "", "phone": "   ", "contact_id": None}],
        "trade_name": None, "care_of": "",
        "companies_other": ["", None, "Real Co"], "law_firms": [],
        "contacts": [{"name": None, "phone": ""}],
        "mailing": {"display": ""},
        "phones": [],
    }
    seeds = harvest_seeds(view)
    assert len(seeds) == 1
    assert seeds[0]["term"] == "Real Co"
    assert seeds[0]["field_type"] == "company_other"
