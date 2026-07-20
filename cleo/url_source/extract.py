"""
URL source — isolated extraction step (url-source-spec.md, step 2).

Input a URL, fetch it, and get a contract-bucketed {group, properties[]} back
via a schema-locked Claude tool call. This module ONLY classifies + structures;
it does not resolve, mint, or write. Correct classification every time is the goal.
"""
from __future__ import annotations
import re
import httpx
import anthropic

from cleo.identity.enrich import _strip_html_to_text, MAX_PAGE_CHARS, HTTP_TIMEOUT

MODEL = "claude-sonnet-4-6"

# ── The contract-bucketed schema the model is LOCKED to (url-source-spec.md §3) ──
CAPTURE_SCHEMA = {
    "type": "object",
    "properties": {
        "group": {  # Bucket F (once) + provenance
            "type": "object",
            "properties": {
                "canonical_name": {"type": ["string", "null"], "description": "Public-facing owner/group name, e.g. 'Plaza REIT'. NOT a property name."},
                "aliases": {"type": "array", "items": {"type": "string"}},
                "business_lines": {"type": "array", "items": {"type": "string"}, "description": "owner|developer|property_manager|brokerage"},
                "corp_address": {"type": ["string", "null"]},
                "corp_phone": {"type": ["string", "null"]},
                "domain": {"type": ["string", "null"]},
                "website": {"type": ["string", "null"]},
                "people": {"type": "array", "items": {"type": "object", "properties": {
                    "name": {"type": ["string", "null"]}, "title": {"type": ["string", "null"]}}}},
                "confidence": {"type": ["number", "null"]},
            },
            "required": ["canonical_name"],
        },
        "properties": {  # MANY — each a distinct property
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "property_name": {"type": ["string", "null"], "description": "Marketing/building name (e.g. 'Eastcourt Plaza'). NEVER put this in address."},
                    "address": {  # Bucket C — civic address ONLY
                        "type": "object",
                        "properties": {
                            "street_address": {"type": ["string", "null"], "description": "Civic line with street number, e.g. '1380 Second Street East'. Null if only a name is given."},
                            "city": {"type": ["string", "null"]},
                            "province": {"type": ["string", "null"]},
                            "postal": {"type": ["string", "null"]},
                        },
                    },
                    "site": {  # Bucket E
                        "type": "object",
                        "properties": {
                            "property_type": {"type": ["string", "null"]},
                            "retail_subtype": {"type": ["string", "null"]},
                            "land": {"type": "object", "properties": {
                                "value": {"type": ["number", "null"]},
                                "unit": {"type": ["string", "null"], "description": "sqft|acres|sf"}}},
                        },
                    },
                    "detail": {  # Bucket H
                        "type": "object",
                        "properties": {
                            "total_sqft": {"type": ["number", "null"]},
                            "units": {"type": ["integer", "null"]},
                            "floors": {"type": ["integer", "null"]},
                            "parking": {"type": ["string", "null"]},
                            "vacancy": {"type": ["string", "null"]},
                            "asking_rate": {"type": ["string", "null"]},
                            "pdf_links": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                    "tenants": {"type": "array", "items": {"type": "object", "properties": {  # Bucket H
                        "name": {"type": ["string", "null"]},
                        "unit": {"type": ["string", "null"]},
                        "sqft": {"type": ["number", "null"]},
                        "is_anchor": {"type": ["boolean", "null"]}}}},
                    "ownership": {  # Bucket F
                        "type": "object",
                        "properties": {
                            "relationship": {"type": ["string", "null"], "description": "owns|manages|lists|unclear"},
                            "reasoning": {"type": ["string", "null"]}}},
                },
                "required": ["property_name", "address"],
            },
        },
        "meta": {"type": "object", "properties": {
            "site_structure_notes": {"type": ["string", "null"]},
            "data_quality_notes": {"type": ["string", "null"]}}},
    },
    "required": ["group", "properties"],
}

SYSTEM = (
    "You extract a commercial real estate owner's portfolio from web page text into a strict schema.\n"
    "CLASSIFICATION RULES (the switchboard — follow exactly):\n"
    "1. A civic address (street number + street name) goes ONLY in address.street_address.\n"
    "2. A property's marketing or building name (e.g. 'Eastcourt Plaza', 'Stadium Mall') goes ONLY in property_name. NEVER put a name in the address.\n"
    "3. Tenant/retailer names (No Frills, Shoppers, etc.) go ONLY in tenants[]. They are not the owner and not the property name.\n"
    "4. The owner/group name (e.g. 'Plaza REIT') goes in group.canonical_name, not on any property.\n"
    "5. Unknown fields are null. NEVER guess or infer a value that is not on the page.\n"
    "6. Return every DISTINCT property as its own item in properties[]. Do not merge them.\n"
    "7. For ownership.relationship, judge owns/manages/lists/unclear and give short reasoning.\n"
    "Emit via the emit_portfolio tool only."
)


def _fetch_text(url: str) -> str:
    with httpx.Client(timeout=HTTP_TIMEOUT, follow_redirects=True) as c:
        r = c.get(url, headers={"User-Agent": "CleoTurbo/1.0"})
        r.raise_for_status()
        return _strip_html_to_text(r.text)[:MAX_PAGE_CHARS]


def validate(result: dict) -> dict:
    """Deterministic post-check (spec §4): an address with no street number is
    not resolvable — mark it so the resolve step skips it rather than guessing."""
    for p in result.get("properties", []):
        sa = ((p.get("address") or {}).get("street_address") or "").strip()
        p["_address_resolvable"] = bool(re.match(r"^\s*\d", sa))
    return result


def extract_from_url(url: str, model: str = MODEL) -> dict:
    text = _fetch_text(url)
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=model,
        max_tokens=4096,
        system=SYSTEM,
        tools=[{"name": "emit_portfolio", "description": "Emit the extracted portfolio.", "input_schema": CAPTURE_SCHEMA}],
        tool_choice={"type": "tool", "name": "emit_portfolio"},
        messages=[{"role": "user", "content": f"Source URL: {url}\n\nPAGE TEXT:\n{text}"}],
    )
    result = None
    for block in msg.content:
        if getattr(block, "type", None) == "tool_use":
            result = block.input
            break
    if result is None:
        raise RuntimeError("model did not emit the tool")
    result["_source_url"] = url
    return validate(result)
