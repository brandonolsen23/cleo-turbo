"""AI-driven HQ enrichment for an auto_group.

Given a group's display_name (and optionally a website URL), fetches the
homepage + Contact/About sub-pages, feeds the text to Claude with a focused
prompt, and returns a structured proposal:

    {
        "primary_address": "<full address string>",
        "primary_address_canonical": "<city|num|name|suf|dir|stype|snum>",
        "website": "<confirmed URL>",
        "primary_phone": "<formatted phone>",
        "evidence_snippets": ["...", "..."],
        "confidence": 0..1,
        "reasoning": "...",
    }

User reviews via the API and accepts some/all of the fields. No DB writes
happen here — that's the caller's responsibility.
"""
from __future__ import annotations
import json
import re
import os
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx


CLAUDE_MODEL = "claude-sonnet-4-6"  # latest Sonnet 4.6 (per cutoff guidance)
MAX_PAGE_CHARS = 12_000  # cap per page to keep prompt size reasonable
HTTP_TIMEOUT = 15.0


_CONTACT_PATH_RE = re.compile(
    r'href=["\']([^"\']*(?:contact|about|imprint|legal)[^"\']*)["\']',
    re.IGNORECASE,
)


def _normalise_url(url: str) -> str:
    url = url.strip()
    if not url:
        return url
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def _strip_html_to_text(html: str) -> str:
    """Quick-and-dirty HTML → text. Good enough for Claude to read."""
    # Drop scripts/styles
    html = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    # Tags → spaces, collapse whitespace
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _fetch_text(url: str, client: httpx.Client) -> Optional[str]:
    try:
        r = client.get(url, headers={"User-Agent": "CleoTurbo/1.0 (+brandon@cleo)"})
        if r.status_code >= 400:
            return None
        text = _strip_html_to_text(r.text)
        return text[:MAX_PAGE_CHARS]
    except Exception:
        return None


def _discover_contact_pages(html: str, base_url: str, limit: int = 3) -> list[str]:
    """Find <a href="..."> links containing 'contact' or 'about'."""
    found: list[str] = []
    seen: set[str] = set()
    for m in _CONTACT_PATH_RE.finditer(html):
        href = m.group(1)
        abs_url = urljoin(base_url, href)
        # Same-host only
        if urlparse(abs_url).netloc != urlparse(base_url).netloc:
            continue
        if abs_url in seen or abs_url == base_url:
            continue
        seen.add(abs_url)
        found.append(abs_url)
        if len(found) >= limit:
            break
    return found


def _build_prompt(display_name: str, pages: list[tuple[str, str]]) -> str:
    pages_block = "\n\n".join(
        f"--- Page: {url} ---\n{text}"
        for url, text in pages
    )
    return f"""You are extracting headquarters identity data for a Canadian commercial real estate company called "{display_name}".

Below is text scraped from the company's website. Extract the following fields if present:

- primary_address: a single, plain-English HQ street address (e.g. "3280 Bloor Street West, Suite 1400, Toronto, ON")
- primary_address_canonical: the same address normalised in the Cleo Turbo canonical format
  `city|street_number|street_name|street_suffix|street_direction|suite_type|suite_number`
  (lowercase parts; suite_type is one of: suite, floor, unit, penthouse, po_box; empty parts kept as empty strings)
  Example: "toronto|3280|bloor|street|west|suite|1400"
- website: the company's primary website URL (https://...)
- primary_phone: the main reception/contact phone number, formatted as the page presents it
- evidence_snippets: up to 3 verbatim short quotes (≤120 chars each) from the pages that support your extraction
- confidence: 0.0-1.0, your confidence that the extracted address really is this company's HQ
- reasoning: 1-2 sentence rationale

If a field can't be confidently extracted, return null for it (not a guess).
Prefer text from a Contact, About, or Imprint page over the homepage when available.
Output ONLY valid JSON matching this schema:

{{
  "primary_address": string | null,
  "primary_address_canonical": string | null,
  "website": string | null,
  "primary_phone": string | null,
  "evidence_snippets": string[],
  "confidence": number,
  "reasoning": string
}}

Pages:
{pages_block}
"""


def _make_anthropic_client():
    import anthropic
    return anthropic.Anthropic()


def propose_hq_enrichment(
    *,
    display_name: str,
    canonical_stem: str,
    website_url: Optional[str] = None,
) -> dict:
    """Fetch the company's website + Claude-extract HQ identity.

    If website_url is omitted, raises — we don't currently auto-discover. The
    UI should prompt the user for a URL if it doesn't have one.
    """
    if not website_url:
        raise ValueError("website_url is required (auto-discovery not implemented yet)")

    homepage_url = _normalise_url(website_url)

    with httpx.Client(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
        try:
            r = client.get(homepage_url, headers={"User-Agent": "CleoTurbo/1.0"})
        except Exception as exc:
            raise RuntimeError(f"failed to fetch {homepage_url}: {exc}")
        if r.status_code >= 400:
            raise RuntimeError(f"{homepage_url} returned HTTP {r.status_code}")

        raw_homepage_html = r.text
        homepage_text = _strip_html_to_text(raw_homepage_html)[:MAX_PAGE_CHARS]

        # Discover contact/about pages, fetch them
        contact_urls = _discover_contact_pages(raw_homepage_html, homepage_url, limit=3)
        pages = [(homepage_url, homepage_text)]
        for sub_url in contact_urls:
            text = _fetch_text(sub_url, client)
            if text:
                pages.append((sub_url, text))

    prompt = _build_prompt(display_name, pages)

    client = _make_anthropic_client()
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    # Extract text content
    text_out = ""
    for block in message.content:
        if getattr(block, "type", None) == "text":
            text_out += block.text

    # Strip markdown fences if any
    text_out = re.sub(r"^```(?:json)?\s*", "", text_out.strip())
    text_out = re.sub(r"\s*```$", "", text_out.strip())

    try:
        result = json.loads(text_out)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Claude returned non-JSON response: {exc} — text: {text_out[:200]}")

    # Always include the source pages we fed it (for the UI's "evidence" panel)
    result["_source_pages"] = [u for u, _ in pages]
    return result
