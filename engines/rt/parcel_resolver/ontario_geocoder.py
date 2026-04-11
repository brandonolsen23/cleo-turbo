"""
Ontario Address Locator client — geocodes Ontario addresses via the
provincial GeocodeServer, accessed through the AgMaps web proxy.

Requires a Playwright browser session to authenticate with the proxy.
Session is managed automatically: heartbeat checks every N calls,
auto-refresh on failure, hard stop on rate limiting.

Usage:
    from parcel_resolver.ontario_geocoder import OntarioGeocoderClient

    with OntarioGeocoderClient() as client:
        result = client.geocode("107 Edward St, St. Thomas, ON")
        # result = {
        #   "lat": 42.785, "lng": -81.176,
        #   "score": 100, "addr_type": "PointAddress",
        #   "match_addr": "107 Edward Street, ST THOMAS, ONTARIO",
        #   "loc_name": "PARCEL_PCCF"
        # }
"""

import json
import time
import sys

from playwright.sync_api import sync_playwright


AGMAPS_URL = (
    "https://www.lioapplications.lrc.gov.on.ca/AgMaps/Index.html"
    "?viewer=AgMaps.AgMaps&locale=en-CA"
)

GEOCODER_BASE = (
    "https://intra.ws.lioservices.lrc.gov.on.ca/arcgis1/rest/services"
    "/Geocoders/Ontario_Address_Locator/GeocodeServer"
)

PROXY_BASE = (
    "https://www.lioapplications.lrc.gov.on.ca/services/proxy/proxy.ashx"
)

# Known-good address for heartbeat checks
HEARTBEAT_ADDRESS = "300 Water St, Peterborough, ON"

# Rate limiting
DEFAULT_DELAY = 1.0      # 1 req/sec (conservative to avoid throttling)
HEARTBEAT_INTERVAL = 100  # Check session every N calls

# Throttle detection
MAX_CONSECUTIVE_ERRORS = 3
ERROR_RATE_WINDOW = 100
MAX_ERROR_RATE = 0.10     # 10% errors in rolling window → pause
PAUSE_DURATION = 60       # Seconds to pause before retry
MIN_SCORE = 0             # Return all results, let caller filter


class ThrottleError(Exception):
    """Raised when rate limiting is detected. Pipeline should STOP."""
    pass


class SessionError(Exception):
    """Raised when the browser session cannot be established."""
    pass


class OntarioGeocoderClient:
    """Ontario Address Locator client with managed Playwright session.

    Use as a context manager:
        with OntarioGeocoderClient() as client:
            result = client.geocode("107 Edward St, St. Thomas, ON")

    Or manage lifecycle manually:
        client = OntarioGeocoderClient()
        client.start()
        result = client.geocode(...)
        client.close()
    """

    def __init__(self, delay=DEFAULT_DELAY, headless=True, verbose=True):
        self.delay = delay
        self.headless = headless
        self.verbose = verbose

        # Playwright state
        self._playwright = None
        self._browser = None
        self._page = None

        # Rate tracking
        self._call_count = 0
        self._last_call_time = 0
        self._consecutive_errors = 0
        self._error_window = []   # Rolling window of (timestamp, success_bool)

        # Dedup cache: geocode_string → result dict
        self._cache = {}

        # Stats
        self.stats = {
            'calls': 0,
            'cache_hits': 0,
            'point_address': 0,
            'street_address': 0,
            'postal': 0,
            'no_result': 0,
            'errors': 0,
            'session_refreshes': 0,
        }

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    # ----------------------------------------------------------------
    # Lifecycle
    # ----------------------------------------------------------------

    def start(self):
        """Launch browser and establish AgMaps session."""
        if self.verbose:
            print('Ontario Geocoder — starting session...')

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self.headless)
        self._establish_session()

        if self.verbose:
            print('  Session ready.')

    def close(self):
        """Clean up browser resources."""
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
        self._browser = None
        self._playwright = None
        self._page = None

    def _establish_session(self):
        """Navigate to AgMaps and accept disclaimer to activate proxy session."""
        if self._page:
            try:
                self._page.close()
            except Exception:
                pass

        context = self._browser.new_context()
        self._page = context.new_page()

        self._page.goto(AGMAPS_URL, wait_until="networkidle", timeout=60000)

        # Accept disclaimer dialog
        for selector in [
            "button:has-text('Accept')",
            "button:has-text('I Accept')",
            "button:has-text('Agree')",
            "button:has-text('OK')",
            "input[type='button'][value='Accept']",
            "input[type='button'][value='I Accept']",
        ]:
            try:
                btn = self._page.locator(selector).first
                if btn.is_visible(timeout=2000):
                    btn.click()
                    break
            except Exception:
                continue

        self._page.wait_for_timeout(2000)

    def _refresh_session(self):
        """Re-establish the AgMaps session (e.g., after timeout)."""
        self.stats['session_refreshes'] += 1
        if self.verbose:
            print(f'  Refreshing session (refresh #{self.stats["session_refreshes"]})...')

        try:
            self._establish_session()
            # Verify with heartbeat
            result = self._raw_geocode(HEARTBEAT_ADDRESS)
            if result is None:
                raise SessionError("Heartbeat failed after session refresh")
            if self.verbose:
                print('  Session refreshed successfully.')
        except Exception as e:
            raise SessionError(f"Failed to refresh session: {e}")

    def capture_agmaps_token(self):
        """Capture a fresh AgMaps token from the existing browser session.

        Opens a new tab, loads AgMaps, captures the token from network traffic
        to ws.lioservices.lrc.gov.on.ca/arcgis4, then closes the tab.

        This avoids spawning a second Playwright instance (which crashes
        with "Sync API inside asyncio loop" errors).

        Returns:
            str: The token string.
        Raises:
            RuntimeError: If token cannot be captured.
        """
        if not self._browser:
            raise RuntimeError("Browser not running — call start() first")

        captured_token = None

        def handle_request(request):
            nonlocal captured_token
            if "ws.lioservices.lrc.gov.on.ca/arcgis4" in request.url and "token=" in request.url:
                for param in request.url.split("?")[-1].split("&"):
                    if param.startswith("token="):
                        captured_token = param.split("=", 1)[1]

        context = self._browser.new_context()
        page = context.new_page()
        page.on("request", handle_request)

        try:
            page.goto(AGMAPS_URL, wait_until="networkidle", timeout=60000)

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
                        break
                except Exception:
                    continue

            import time as _time
            deadline = _time.time() + 30
            while not captured_token and _time.time() < deadline:
                page.wait_for_timeout(500)

        finally:
            try:
                page.close()
                context.close()
            except Exception:
                pass

        if not captured_token:
            raise RuntimeError("Failed to capture AgMaps token from browser session")

        if self.verbose:
            print(f'  Captured fresh AgMaps token via existing browser')

        from .token import save_token
        save_token(captured_token)

        return captured_token

    # ----------------------------------------------------------------
    # Core geocoding
    # ----------------------------------------------------------------

    def geocode(self, address):
        """Geocode a single Ontario address.

        Args:
            address: Address string (e.g., "107 Edward St, St. Thomas, ON").
                     Remove ", Canada" suffix before calling — this is Ontario-only.

        Returns:
            dict with lat, lng, score, addr_type, match_addr, loc_name
            or None if no result / below score threshold.
        """
        # Strip ", Canada" if present
        clean = address.replace(', Canada', '').strip()

        # Dedup cache check
        cache_key = clean.upper()
        if cache_key in self._cache:
            self.stats['cache_hits'] += 1
            return self._cache[cache_key]

        # Heartbeat check
        if self._call_count > 0 and self._call_count % HEARTBEAT_INTERVAL == 0:
            self._heartbeat()

        # Throttle
        self._throttle()

        # Make the call
        result = self._geocode_with_retry(clean)

        # Cache result
        self._cache[cache_key] = result

        # Track stats
        self.stats['calls'] += 1
        self._call_count += 1

        if result is None:
            self.stats['no_result'] += 1
        elif result['addr_type'] == 'PointAddress':
            self.stats['point_address'] += 1
        elif result['addr_type'] in ('StreetAddress', 'StreetName'):
            self.stats['street_address'] += 1
        elif result['addr_type'] == 'Postal':
            self.stats['postal'] += 1

        return result

    def geocode_batch(self, addresses):
        """Geocode a list of addresses with progress reporting.

        Args:
            addresses: list of address strings

        Returns:
            list of result dicts (same length as input, None for failures)
        """
        results = []
        total = len(addresses)
        start_time = time.time()

        for i, addr in enumerate(addresses):
            result = self.geocode(addr)
            results.append(result)

            if self.verbose and (i + 1) % 100 == 0:
                elapsed = time.time() - start_time
                rate = (i + 1) / elapsed if elapsed > 0 else 0
                eta = (total - i - 1) / rate if rate > 0 else 0
                print(
                    f'  [{i+1:,}/{total:,}] '
                    f'{rate:.1f}/sec  '
                    f'cache:{self.stats["cache_hits"]}  '
                    f'point:{self.stats["point_address"]}  '
                    f'street:{self.stats["street_address"]}  '
                    f'none:{self.stats["no_result"]}  '
                    f'err:{self.stats["errors"]}  '
                    f'ETA:{eta/60:.0f}m'
                )

        return results

    def _geocode_with_retry(self, address, max_retries=3):
        """Geocode with pause + session refresh on failure."""
        for attempt in range(max_retries + 1):
            try:
                result = self._raw_geocode(address)
                self._record_success()
                return result
            except Exception as e:
                if attempt < max_retries:
                    # Wait before retrying — empty responses are often transient
                    wait = 10 * (attempt + 1)  # 10s, 20s, 30s
                    if self.verbose:
                        print(f'  Geocode error (attempt {attempt + 1}): {e}')
                        print(f'  Waiting {wait}s before retry...')
                    time.sleep(wait)
                    try:
                        self._refresh_session()
                    except SessionError:
                        if attempt == max_retries - 1:
                            self._record_error()
                            raise
                else:
                    self._record_error()
                    self.stats['errors'] += 1
                    return None

    def _raw_geocode(self, address):
        """Execute a single geocode call via the browser proxy.

        Returns dict with lat, lng, score, addr_type, match_addr, loc_name
        or None if no candidates.
        """
        js_code = """
        (addr) => {
            const url = "%s?%s/findAddressCandidates" +
                "?SingleLine=" + encodeURIComponent(addr) +
                "&outFields=*&maxLocations=3&outSR=4326&f=json";
            return fetch(url).then(r => r.text());
        }
        """ % (PROXY_BASE, GEOCODER_BASE)

        raw = self._page.evaluate(js_code, address)
        data = json.loads(raw)

        if 'error' in data:
            error_msg = data['error'].get('message', str(data['error']))
            raise RuntimeError(f"Geocoder error: {error_msg}")

        candidates = data.get('candidates', [])
        if not candidates:
            return None

        # Return best candidate with ALL attributes from the geocoder.
        # The Ontario Address Locator returns 44 attributes per candidate.
        # Previously we only captured 6 — now we capture everything so the
        # unified resolver can use Comp_score, parsed address components, etc.
        c = candidates[0]
        loc = c.get('location', {})
        attrs = c.get('attributes', {})

        score = c.get('score', 0)
        if score < MIN_SCORE:
            return None

        result = {
            # Core fields (backward compatible)
            'lat': loc.get('y'),
            'lng': loc.get('x'),
            'score': score,
            'addr_type': attrs.get('Addr_type', ''),
            'match_addr': c.get('address', ''),
            'loc_name': attrs.get('Loc_name', ''),

            # Component-level scoring — the gold field for confidence.
            # e.g., "House=100; StName=100; suftype=100; City=100"
            'comp_score': attrs.get('Comp_score', ''),

            # Parsed address components from geocoder
            'house': attrs.get('House', ''),
            'street_name': attrs.get('StreetName', ''),
            'suf_type': attrs.get('SufType', ''),
            'pre_dir': attrs.get('PreDir', ''),
            'suf_dir': attrs.get('SufDir', ''),
            'city': attrs.get('City', ''),
            'state': attrs.get('State', ''),
            'postal': attrs.get('ZIP', ''),
            'county': attrs.get('County', ''),
            'side': attrs.get('Side', ''),

            # Sub-address components
            'sub_addr_type': attrs.get('SubAddrType', ''),
            'sub_addr_unit': attrs.get('SubAddrUnit', ''),
            'bldg_sub_addr_type': attrs.get('BldgSubAddrType', ''),
            'bldg_sub_addr_unit': attrs.get('BldgSubAddrUnit', ''),

            # Full candidates for fallback analysis
            'all_candidates': [
                {
                    'lat': cand.get('location', {}).get('y'),
                    'lng': cand.get('location', {}).get('x'),
                    'score': cand.get('score', 0),
                    'address': cand.get('address', ''),
                    'attributes': cand.get('attributes', {}),
                }
                for cand in candidates
            ],
        }

        return result

    # ----------------------------------------------------------------
    # Throttle & rate limiting
    # ----------------------------------------------------------------

    def _throttle(self):
        """Enforce minimum delay between requests."""
        elapsed = time.time() - self._last_call_time
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_call_time = time.time()

    def _record_success(self):
        """Record a successful call for throttle tracking."""
        self._consecutive_errors = 0
        self._error_window.append((time.time(), True))
        self._trim_error_window()

    def _record_error(self):
        """Record a failed call and check throttle thresholds."""
        self._consecutive_errors += 1
        self._error_window.append((time.time(), False))
        self._trim_error_window()

        # Hard stop: 3 consecutive errors
        if self._consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
            raise ThrottleError(
                f"HARD STOP: {MAX_CONSECUTIVE_ERRORS} consecutive geocode errors. "
                f"Possible rate limiting. Pipeline stopped to prevent being blocked. "
                f"Total calls made: {self.stats['calls']}. "
                f"Review and restart manually."
            )

        # Rolling window error rate check
        if len(self._error_window) >= ERROR_RATE_WINDOW:
            errors = sum(1 for _, success in self._error_window if not success)
            error_rate = errors / len(self._error_window)

            if error_rate >= MAX_ERROR_RATE:
                if self.verbose:
                    print(
                        f'  WARNING: Error rate {error_rate:.0%} exceeds '
                        f'{MAX_ERROR_RATE:.0%} threshold. '
                        f'Pausing {PAUSE_DURATION}s before retry...'
                    )

                time.sleep(PAUSE_DURATION)

                # Try one more call as a test
                try:
                    test = self._raw_geocode(HEARTBEAT_ADDRESS)
                    if test is not None:
                        if self.verbose:
                            print('  Pause successful — resuming.')
                        self._error_window.clear()
                        return
                except Exception:
                    pass

                raise ThrottleError(
                    f"HARD STOP: Error rate {error_rate:.0%} persists after "
                    f"{PAUSE_DURATION}s pause. Possible rate limiting or service "
                    f"outage. Total calls: {self.stats['calls']}. "
                    f"Review and restart manually."
                )

    def _trim_error_window(self):
        """Keep rolling window at max size."""
        while len(self._error_window) > ERROR_RATE_WINDOW:
            self._error_window.pop(0)

    def _heartbeat(self):
        """Verify session is alive with a test geocode call."""
        try:
            result = self._raw_geocode(HEARTBEAT_ADDRESS)
            if result is None:
                raise RuntimeError("Heartbeat returned no result")
            if self.verbose:
                print(f'  Heartbeat OK (call #{self._call_count})')
        except Exception as e:
            if self.verbose:
                print(f'  Heartbeat FAILED: {e}')
            self._refresh_session()

    # ----------------------------------------------------------------
    # Reporting
    # ----------------------------------------------------------------

    def print_stats(self):
        """Print summary statistics."""
        s = self.stats
        total = s['calls'] + s['cache_hits']
        print()
        print(f'Ontario Geocoder — Summary')
        print(f'  Total requests:      {total:,}')
        print(f'  API calls:           {s["calls"]:,}')
        print(f'  Cache hits:          {s["cache_hits"]:,}')
        print(f'  PointAddress:        {s["point_address"]:,}')
        print(f'  StreetAddress:       {s["street_address"]:,}')
        print(f'  Postal:              {s["postal"]:,}')
        print(f'  No result:           {s["no_result"]:,}')
        print(f'  Errors:              {s["errors"]:,}')
        print(f'  Session refreshes:   {s["session_refreshes"]:,}')
        if s['calls'] > 0:
            success = s['point_address'] + s['street_address'] + s['postal']
            print(f'  Success rate:        {success*100/s["calls"]:.1f}%')
