"""
URL source — extraction (url-source-spec.md §3-§5).

Acquire complete page content (render in a real browser + full-page screenshot),
then classify it into the contract buckets via a schema-locked Claude tool call.
The classifier is structure-agnostic; robustness lives in acquisition (render+vision).
"""
from __future__ import annotations
import base64
import httpx
import anthropic

from cleo.identity.enrich import _strip_html_to_text, MAX_PAGE_CHARS, HTTP_TIMEOUT

MODEL = "claude-sonnet-4-6"
RENDER_MAX_CHARS = 40_000

# ── Contract-bucketed schema the model is LOCKED to (url-source-spec.md §3) ──
CAPTURE_SCHEMA = {
    "type": "object",
    "properties": {
        "group": {
            "type": "object",
            "properties": {
                "canonical_name": {"type": ["string", "null"], "description": "Public owner/group name, e.g. 'Plaza REIT'. NOT a property name."},
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
        "properties": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "property_name": {"type": ["string", "null"], "description": "Marketing/building name (e.g. 'Eastcourt Plaza'). NEVER put this in address."},
                    "address": {
                        "type": "object",
                        "properties": {
                            "street_address": {"type": ["string", "null"], "description": "Civic line with street number, e.g. '1380 Second Street East'. Null if only a name is given."},
                            "city": {"type": ["string", "null"]},
                            "province": {"type": ["string", "null"]},
                            "postal": {"type": ["string", "null"]},
                        },
                    },
                    "site": {
                        "type": "object",
                        "properties": {
                            "property_type": {"type": ["string", "null"]},
                            "retail_subtype": {"type": ["string", "null"]},
                            "land": {"type": "object", "properties": {
                                "value": {"type": ["number", "null"]},
                                "unit": {"type": ["string", "null"], "description": "sqft|acres|sf"}}},
                        },
                    },
                    "detail": {
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
                    "tenants": {"type": "array", "items": {"type": "object", "properties": {
                        "name": {"type": ["string", "null"]},
                        "unit": {"type": ["string", "null"]},
                        "sqft": {"type": ["number", "null"]},
                        "is_anchor": {"type": ["boolean", "null"]}}}},
                    "ownership": {
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
    "You extract a commercial real estate owner's portfolio from a web page into a strict schema.\n"
    "You are given the rendered page TEXT and, when available, a full-page SCREENSHOT. Use BOTH — the "
    "screenshot often shows tenants, tables, maps, or PDF links the plain text misses.\n"
    "CLASSIFICATION RULES (the switchboard — follow exactly):\n"
    "1. A civic address (street number + street name) goes ONLY in address.street_address.\n"
    "2. A property's marketing or building name (e.g. 'Eastcourt Plaza') goes ONLY in property_name. NEVER put a name in the address.\n"
    "3. Tenant/retailer names (No Frills, Dollarama, Tim Hortons, etc.) go ONLY in tenants[]. Capture EVERY tenant you can see in text or screenshot.\n"
    "4. The owner/group name (e.g. 'Plaza REIT') goes in group.canonical_name, not on any property.\n"
    "5. Capture pdf_links (site plans, leasing brochures) when present.\n"
    "6. Unknown fields are null. NEVER guess a value not on the page.\n"
    "7. Return every DISTINCT property as its own item in properties[]. Do not merge them.\n"
    "8. For ownership.relationship, judge owns/manages/lists/unclear and give short reasoning.\n"
    "9. In meta.data_quality_notes, state what you could NOT capture and any claimed-vs-found count gap.\n"
    "Emit via the emit_portfolio tool only."
)


def _fetch_text(url: str) -> str:
    """Plain HTTP fallback (text only, no JS). Used if the browser can't run."""
    with httpx.Client(timeout=HTTP_TIMEOUT, follow_redirects=True) as c:
        r = c.get(url, headers={"User-Agent": "CleoTurbo/1.0"})
        r.raise_for_status()
        return _strip_html_to_text(r.text)[:MAX_PAGE_CHARS]


def render_page(url: str, timeout_ms: int = 30000):
    """Render a page in headless Chromium so JS content is present.
    Returns (visible_text, screenshot_png_bytes | None). Degrades to a plain
    fetch (text only) if Playwright can't run."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return _fetch_text(url), None
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1366, "height": 1024})
            try:
                page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            except Exception:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(1500)  # let late JS settle
            text = page.inner_text("body")
            shot = page.screenshot(full_page=True)
            browser.close()
            return text[:RENDER_MAX_CHARS], shot
    except Exception as exc:
        try:
            return _fetch_text(url), None
        except Exception:
            raise RuntimeError(f"could not acquire {url}: {exc}")


def validate(result: dict) -> dict:
    """Extract is STAGING ONLY (url-source-spec.md §4): normalize structure and
    return. Whether a staged address can reach an ARN is the RESOLVER's call,
    not extract's — we deliberately make no resolvability judgment here."""
    for p in result.get("properties", []):
        p.setdefault("address", {})
        p.setdefault("tenants", [])
    return result


def extract_from_content(text: str, screenshot_png=None, source_url: str = "", model: str = MODEL) -> dict:
    content = [{"type": "text", "text": f"Source URL: {source_url}\n\nRENDERED PAGE TEXT:\n{text}"}]
    if screenshot_png:
        content.append({"type": "text", "text": "Full-page SCREENSHOT of the same page:"})
        content.append({"type": "image", "source": {
            "type": "base64", "media_type": "image/png",
            "data": base64.b64encode(screenshot_png).decode()}})
    msg = anthropic.Anthropic().messages.create(
        model=model, max_tokens=4096, system=SYSTEM,
        tools=[{"name": "emit_portfolio", "description": "Emit the extracted portfolio.", "input_schema": CAPTURE_SCHEMA}],
        tool_choice={"type": "tool", "name": "emit_portfolio"},
        messages=[{"role": "user", "content": content}],
    )
    result = None
    for block in msg.content:
        if getattr(block, "type", None) == "tool_use":
            result = block.input
            break
    if result is None:
        raise RuntimeError("model did not emit the tool")
    result["_source_url"] = source_url
    return validate(result)


def extract_from_url(url: str, model: str = MODEL) -> dict:
    text, shot = render_page(url)
    return extract_from_content(text, shot, source_url=url, model=model)
