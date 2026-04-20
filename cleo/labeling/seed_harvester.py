"""Seed harvester — extracts (term, field_type) pairs from a party view.

Used by the labeling tool to auto-populate the search-seed queue whenever
a party is confirmed into a session (and for the anchor at session creation).
"""

from __future__ import annotations
from typing import List


def _clean(s) -> str:
    if s is None:
        return ""
    return str(s).strip()


def harvest_seeds(view: dict) -> List[dict]:
    """Return a list of {term, field_type} dicts harvested from a party view.

    Deduplicated within each field_type; a single term can appear under
    multiple field_types (e.g. "Acme Corp" as both party_name and trade_name),
    since each triggers a different search semantics.
    """
    seeds: List[dict] = []
    seen: set = set()

    def add(field_type: str, term: str):
        term = _clean(term)
        if not term:
            return
        key = (field_type, term)
        if key in seen:
            return
        seen.add(key)
        seeds.append({"field_type": field_type, "term": term})

    for row in view.get("party_rows") or []:
        add("party_name", row.get("party_name"))
        add("phone", row.get("phone"))

    add("trade_name", view.get("trade_name"))
    add("care_of", view.get("care_of"))

    for v in view.get("companies_other") or []:
        add("company_other", v)
    for v in view.get("law_firms") or []:
        add("law_firm", v)

    for c in view.get("contacts") or []:
        add("contact_name", c.get("name"))
        add("phone", c.get("phone"))

    mailing = view.get("mailing") or {}
    add("address", mailing.get("display"))

    for ph in view.get("phones") or []:
        add("phone", ph)

    return seeds
