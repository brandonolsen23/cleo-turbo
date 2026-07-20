"""
URL source — discovery (url-source-spec.md §5, crawl step).

One portfolio/index URL in -> the group profile + the list of individual
property-page URLs out. Structure-agnostic: a real browser renders the page and
runs a generic "reveal everything" pass (set filter dropdowns to ALL, click
load-more, scroll to trigger lazy-load), then Claude decides which of the page's
links are individual property pages and pulls the group's profile. No per-site
URL patterns are hardcoded — that is what keeps it robust across site layouts.
"""
from __future__ import annotations
import base64
import anthropic

from .extract import MODEL, RENDER_MAX_CHARS, _fetch_text

# Group-level profile (contract extension — keyed by GRP_, not by ARN).
_GROUP_SCHEMA = {
    "type": "object",
    "properties": {
        "canonical_name": {"type": ["string", "null"], "description": "Public owner/group name, e.g. 'Fieldgate Commercial'."},
        "aliases": {"type": "array", "items": {"type": "string"}},
        "business_lines": {"type": "array", "items": {"type": "string"}, "description": "owner|developer|property_manager|brokerage"},
        "about_summary": {"type": ["string", "null"], "description": "Short company history/description if shown on the page."},
        "affiliated_companies": {"type": "array", "items": {"type": "string"}, "description": "Parent, subsidiary, or related brands (e.g. Fieldgate Homes)."},
        "founded": {"type": ["string", "null"]},
        "corp_address": {"type": ["string", "null"]},
        "corp_phone": {"type": ["string", "null"]},
        "website": {"type": ["string", "null"]},
        "domain": {"type": ["string", "null"]},
        "people": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": ["string", "null"]}, "title": {"type": ["string", "null"]}}}},
        "confidence": {"type": ["number", "null"]},
    },
    "required": ["canonical_name"],
}

DISCOVER_SCHEMA = {
    "type": "object",
    "properties": {
        "is_list_page": {"type": "boolean", "description": "true if this page lists MULTIPLE properties; false if it is a single property's own detail page."},
        "group": _GROUP_SCHEMA,
        "property_urls": {
            "type": "array",
            "description": "One entry per INDIVIDUAL property page found among the page's links.",
            "items": {"type": "object", "properties": {
                "url": {"type": "string"},
                "name": {"type": ["string", "null"]}}, "required": ["url"]},
        },
        "about_url": {"type": ["string", "null"], "description": "Link to the company's About/Company page if one is present among the links."},
        "site_structure_notes": {"type": ["string", "null"]},
    },
    "required": ["is_list_page", "group", "property_urls"],
}

DISCOVER_SYSTEM = (
    "You are given a rendered web page from a commercial real estate owner/developer: its visible TEXT, "
    "a full-page SCREENSHOT, and the list of every link (href + anchor text) on the page.\n"
    "Your job is DISCOVERY, not property extraction:\n"
    "1. Decide is_list_page: true if the page lists multiple properties, false if it is one property's own page.\n"
    "2. From the links, return in property_urls ONLY the links that lead to an INDIVIDUAL property's own page. "
    "Judge this from the anchor text and href together. EXCLUDE navigation, header/footer, social media, "
    "category/region filters, pagination, login, and the company's own About/Contact pages.\n"
    "3. Fill the group profile: canonical owner name, any affiliated/parent/related companies, a short about "
    "summary and founding info IF shown, head-office address/phone, website, and named people with titles.\n"
    "4. If a link points to an About/Company page, put it in about_url.\n"
    "5. Unknown fields are null. NEVER invent a URL that is not in the provided link list.\n"
    "Emit via the emit_discovery tool only."
)


_ALL_OPTION_LABELS = {
    "all", "all properties", "show all", "view all", "any",
    "all categories", "all locations", "all regions", "all cities", "all types",
}
_LOAD_MORE_LABELS = ["load more", "show more", "view all", "see all", "show all"]


def _reveal_all(page):
    """Generic 'show everything' pass so filtered/lazy lists fully populate.
    Best-effort: every step is guarded so a site that lacks it is a no-op."""
    # 1) Set every <select> to an ALL-like option.
    try:
        for sel in page.query_selector_all("select"):
            for opt in sel.query_selector_all("option"):
                label = (opt.inner_text() or "").strip().lower()
                if label in _ALL_OPTION_LABELS:
                    try:
                        sel.select_option(value=opt.get_attribute("value"))
                        page.wait_for_timeout(700)
                    except Exception:
                        pass
                    break
    except Exception:
        pass
    # 2) Click load-more / view-all buttons until they stop appearing.
    for _ in range(6):
        clicked = False
        for label in _LOAD_MORE_LABELS:
            try:
                btn = page.query_selector(f"text=/^{label}$/i")
                if btn and btn.is_visible():
                    btn.click(timeout=1500)
                    page.wait_for_timeout(900)
                    clicked = True
            except Exception:
                pass
        if not clicked:
            break
    # 3) Scroll to the bottom to trigger infinite/lazy loading.
    try:
        for _ in range(6):
            page.mouse.wheel(0, 20000)
            page.wait_for_timeout(400)
    except Exception:
        pass


def render_list_page(url: str, timeout_ms: int = 45000):
    """Render an index page, reveal all rows, and return
    (visible_text, screenshot_png|None, links[{href,text}]).
    Degrades to a plain fetch (text only, links from raw HTML skipped) if the
    browser can't run."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return _fetch_text(url), None, []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1366, "height": 1024})
            try:
                page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            except Exception:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(1500)
            _reveal_all(page)
            page.wait_for_timeout(1200)
            text = page.inner_text("body")[:RENDER_MAX_CHARS]
            links = page.eval_on_selector_all(
                "a[href]",
                "els => els.map(e => ({href: e.href, text: (e.innerText||'').trim().slice(0,80)}))",
            )
            shot = page.screenshot(full_page=True)
            browser.close()
    except Exception as exc:
        try:
            return _fetch_text(url), None, []
        except Exception:
            raise RuntimeError(f"could not acquire {url}: {exc}")
    # Dedupe links, drop non-content schemes.
    seen, cleaned = set(), []
    for l in links:
        href = (l.get("href") or "").strip()
        if not href or href in seen:
            continue
        low = href.lower()
        if low.startswith(("mailto:", "tel:", "javascript:")) or href.endswith("#"):
            continue
        seen.add(href)
        cleaned.append({"href": href, "text": l.get("text") or ""})
    return text, shot, cleaned


def _links_block(links: list) -> str:
    lines = [f"{i}. {l['href']}  |  {l['text']}" for i, l in enumerate(links)]
    return "\n".join(lines) if lines else "(no links captured)"


def discover_from_url(url: str, model: str = MODEL) -> dict:
    """Render an index/portfolio page and classify it: group profile + the
    individual property-page URLs. Structure-agnostic (Claude reasons over the
    links; no per-site URL patterns)."""
    text, shot, links = render_list_page(url)
    content = [{"type": "text", "text": (
        f"Source URL: {url}\n\nRENDERED PAGE TEXT:\n{text}\n\n"
        f"ALL LINKS ON THE PAGE (index. href | anchor text):\n{_links_block(links)}"
    )}]
    if shot:
        content.append({"type": "text", "text": "Full-page SCREENSHOT of the same page:"})
        content.append({"type": "image", "source": {
            "type": "base64", "media_type": "image/png",
            "data": base64.b64encode(shot).decode()}})
    msg = anthropic.Anthropic().messages.create(
        model=model, max_tokens=4096, system=DISCOVER_SYSTEM,
        tools=[{"name": "emit_discovery", "description": "Emit discovery result.", "input_schema": DISCOVER_SCHEMA}],
        tool_choice={"type": "tool", "name": "emit_discovery"},
        messages=[{"role": "user", "content": content}],
    )
    result = None
    for block in msg.content:
        if getattr(block, "type", None) == "tool_use":
            result = block.input
            break
    if result is None:
        raise RuntimeError("model did not emit the discovery tool")
    result["_source_url"] = url
    result["_links_seen"] = len(links)
    return result
