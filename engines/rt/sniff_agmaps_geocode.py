"""
Sniff the AgMaps address search to find the geocoding service URL.

Opens AgMaps in a headless browser, performs an address search for
"107 Edward St, St. Thomas", and captures all network requests to
identify which geocoding endpoint the UI calls.

Run from project root:
    python3 engines/rt/sniff_agmaps_geocode.py
"""

import json
import time
from playwright.sync_api import sync_playwright

AGMAPS_URL = (
    "https://www.lioapplications.lrc.gov.on.ca/AgMaps/Index.html"
    "?viewer=AgMaps.AgMaps&locale=en-CA"
)

TEST_ADDRESS = "107 edward st st thomas"


def main():
    captured_requests = []

    def handle_request(request):
        url = request.url
        # Capture anything that looks like a geocoding/search call
        if any(kw in url.lower() for kw in [
            'geocod', 'find', 'search', 'address', 'locate', 'suggest',
            'candidates', 'place', 'edward',
        ]):
            captured_requests.append({
                'method': request.method,
                'url': url,
                'post_data': request.post_data,
            })

    def handle_response(response):
        url = response.url
        if any(kw in url.lower() for kw in [
            'geocod', 'find', 'search', 'address', 'locate', 'suggest',
            'candidates', 'place', 'edward',
        ]):
            try:
                body = response.text()
            except Exception:
                body = "(could not read body)"
            print(f"\n--- RESPONSE: {url[:120]} ---")
            print(f"  Status: {response.status}")
            # Truncate long bodies
            if len(body) > 1500:
                print(f"  Body (truncated): {body[:1500]}...")
            else:
                print(f"  Body: {body}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # visible so we can debug
        context = browser.new_context()
        page = context.new_page()

        page.on("request", handle_request)
        page.on("response", handle_response)

        print(f"Loading AgMaps viewer...")
        page.goto(AGMAPS_URL, wait_until="networkidle", timeout=60000)

        # Accept disclaimer
        print("Accepting disclaimer...")
        for selector in [
            "button:has-text('Accept')",
            "button:has-text('I Accept')",
            "button:has-text('Agree')",
            "button:has-text('OK')",
            "input[type='button'][value='Accept']",
            "input[type='button'][value='I Accept']",
        ]:
            try:
                btn = page.locator(selector).first
                if btn.is_visible(timeout=2000):
                    btn.click()
                    print(f"  Clicked: {selector}")
                    break
            except Exception:
                continue

        page.wait_for_timeout(3000)

        # Find the address search input — try different selectors
        print(f"\nSearching for address input field...")
        search_input = None
        for selector in [
            "input[placeholder*='address' i]",
            "input[placeholder*='Address' i]",
            "input[placeholder*='Find' i]",
            "input[placeholder*='Search' i]",
            "input[title*='address' i]",
            "input[title*='Address' i]",
            "input[id*='address' i]",
            "input[id*='search' i]",
            "input[id*='find' i]",
            "input[name*='address' i]",
            "input[type='text']",
        ]:
            try:
                el = page.locator(selector).first
                if el.is_visible(timeout=1000):
                    search_input = el
                    print(f"  Found input: {selector}")
                    break
            except Exception:
                continue

        if not search_input:
            # Try clicking the "Find an Address" tool first
            print("  Looking for Find Address button/tool...")
            for selector in [
                "text='Find an Address'",
                "button:has-text('Find')",
                "[title*='Find']",
                "[title*='Address']",
                "[aria-label*='Find']",
                "[aria-label*='Address']",
            ]:
                try:
                    btn = page.locator(selector).first
                    if btn.is_visible(timeout=1000):
                        btn.click()
                        print(f"  Clicked tool: {selector}")
                        page.wait_for_timeout(2000)
                        break
                except Exception:
                    continue

            # Try finding the input again
            for selector in ["input[type='text']", "input"]:
                try:
                    inputs = page.locator(selector).all()
                    for inp in inputs:
                        if inp.is_visible():
                            search_input = inp
                            print(f"  Found input after opening tool")
                            break
                except Exception:
                    continue

        if search_input:
            print(f"\nTyping address: {TEST_ADDRESS}")
            search_input.fill(TEST_ADDRESS)
            page.wait_for_timeout(1000)

            # Try pressing Enter or clicking Search
            print("Submitting search...")
            search_input.press("Enter")
            page.wait_for_timeout(2000)

            # Also try clicking a Search button
            for selector in [
                "button:has-text('Search')",
                "input[value='Search']",
                "button:has-text('Find')",
                "input[value='Find']",
            ]:
                try:
                    btn = page.locator(selector).first
                    if btn.is_visible(timeout=1000):
                        btn.click()
                        print(f"  Clicked: {selector}")
                        break
                except Exception:
                    continue

            # Wait for results
            page.wait_for_timeout(5000)
        else:
            print("  Could not find address input field!")
            print("  Taking screenshot for debugging...")

        # Print all captured requests
        print(f"\n\n{'='*60}")
        print(f"CAPTURED GEOCODING REQUESTS: {len(captured_requests)}")
        print(f"{'='*60}")
        for i, req in enumerate(captured_requests):
            print(f"\n[{i+1}] {req['method']} {req['url']}")
            if req['post_data']:
                print(f"    POST data: {req['post_data'][:500]}")

        # Also dump ALL requests in case we missed the right keyword
        print(f"\n\n{'='*60}")
        print("ALL network requests (last 10 seconds) — dumping full list")
        print(f"{'='*60}")

        page.wait_for_timeout(2000)
        browser.close()


if __name__ == "__main__":
    main()
