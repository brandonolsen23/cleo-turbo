"""
Shared utilities for Realtrack scrapers.

Extracted from search_scraper.py so that daily_scraper.py can reuse
the session, HTML parsing, and file I/O logic without importing the
entire bulk scraper.
"""

import json
import logging
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import httpx

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
RAW_DIR = PROJECT_ROOT / "raw-data" / "rt"
PAGES_DIR = RAW_DIR / "pages"
CLEAN_DIR = PROJECT_ROOT / "clean-data" / "rt"

REALTRACK_BASE = "https://realtrack.com"
RESULTS_PER_PAGE = 50

log = logging.getLogger("rt.scraper")

# ---------------------------------------------------------------------------
# Request resilience
# ---------------------------------------------------------------------------
# RealTrack intermittently drops the connection mid-request
# ("Server disconnected without sending a response") or stalls past the read
# timeout, especially during the burst of requests in the verification pass.
# These are transient flakiness, not real failures, so every request retries
# transparently with backoff before giving up. This keeps a single network
# blip from aborting the whole daily run.
_RETRYABLE_EXC = (httpx.TransportError,)
_RETRYABLE_STATUS = frozenset({502, 503, 504})
_REQUEST_TRIES = 4
_REQUEST_BACKOFF = 5  # seconds; multiplied by attempt number, capped at 30

# ---------------------------------------------------------------------------
# Known sf3 values (verified from live search form, Apr 2026)
# ---------------------------------------------------------------------------

KNOWN_SF3_VALUES: Dict[str, str] = {
    "multiRes": "Multi Residential",
    "indBldg": "Industrial Buildings",
    "officeBldg": "Office Buildings",
    "retailBldg": "Retail Buildings",
    "hotelMotel": "Hotels/Motels",
    "restaurantBar": "Restaurants/Bars",
    "otherImprv": "Other Buildings",
    "comIndLand": "Com/Ind Land",
    "resLand": "Res/Rural Land",
    "farmLand": "Farms/Farmland",
    "otherLand": "Other Land",
}

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Pagination total: .pagination(15750, {
TOTAL_PATTERN = re.compile(r"\.pagination\((\d+),")
# RT ID from detail footer
RT_ID_PATTERN = re.compile(r"RT\d+")
# Detail link skip indices
SKIP_PATTERN = re.compile(r'href="\?page=details&(?:amp;)?skip=(\d+)"')
# sf3 select options
SF3_OPTION_PATTERN = re.compile(
    r'<option\s+value="([^"]*)"[^>]*>([^<]+)</option>'
)

# ---------------------------------------------------------------------------
# Atomic file writes
# ---------------------------------------------------------------------------

def atomic_write(path: Path, content: str) -> None:
    """Write content to a file atomically (write to temp, then rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, str(path))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_write_json(path: Path, data) -> None:
    """Write JSON data to a file atomically."""
    atomic_write(path, json.dumps(data, indent=2))


# ---------------------------------------------------------------------------
# HTML parsing helpers
# ---------------------------------------------------------------------------

def extract_total(html: str) -> Optional[int]:
    """Extract total result count from pagination JS on results page."""
    match = TOTAL_PATTERN.search(html)
    return int(match.group(1)) if match else None


def extract_skip_indices(html: str) -> List[int]:
    """Extract detail skip indices from results page links."""
    matches = SKIP_PATTERN.findall(html)
    return sorted(set(int(s) for s in matches))


def extract_rt_id(html: str) -> Optional[str]:
    """Extract RT ID from detail page footer."""
    match = re.search(
        r'<font color="#848484">(\d+\s*/\s*\d+)(?:&nbsp;|\s)+(RT\d+)</font>',
        html,
    )
    if match:
        return match.group(2)
    # Fallback: find any RT ID pattern near end of page
    all_matches = RT_ID_PATTERN.findall(html[-500:])
    return all_matches[-1] if all_matches else None


def parse_export_tsv(text: str) -> List[Dict[str, str]]:
    """Parse export page TSV into list of dicts."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").strip().split("\n")
    if not lines:
        return []
    headers = [h.strip().lower() for h in lines[0].split("\t")]
    if len(headers) < 5:
        return []
    records = []
    for line in lines[1:]:
        if not line.strip():
            continue
        cells = line.split("\t")
        record = {
            headers[i]: cells[i].strip() if i < len(cells) else ""
            for i in range(len(headers))
        }
        records.append(record)
    return records


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------

def retry(fn, retries=3, label="request"):
    """Retry a function up to `retries` times with backoff."""
    for attempt in range(retries):
        try:
            return fn()
        except Exception as e:
            wait = (attempt + 1) * 5
            if attempt < retries - 1:
                log.warning(
                    "%s attempt %d/%d failed: %s — retrying in %ds",
                    label, attempt + 1, retries, e, wait,
                )
                time.sleep(wait)
            else:
                raise


# ---------------------------------------------------------------------------
# Realtrack session
# ---------------------------------------------------------------------------

class RealtrackSession:
    """Authenticated httpx session for Realtrack.com."""

    def __init__(self, username: str, password: str):
        self.client = httpx.Client(
            base_url=REALTRACK_BASE,
            follow_redirects=True,
            timeout=60.0,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
            },
        )
        self._login(username, password)

    def _login(self, username: str, password: str) -> None:
        log.info("Logging in to Realtrack...")
        resp = retry(
            lambda: self.client.post(
                "/?page=login",
                data={
                    "username": username,
                    "password": password,
                    "function": "login",
                },
            ),
            label="login",
        )
        resp.raise_for_status()
        if "page=signout" in resp.text and "Successful Login" in resp.text:
            log.info("Login successful.")
        else:
            log.error("Login failed — check credentials.")
            sys.exit(1)

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        """Issue a request, retrying transparently on transient network
        errors and 5xx responses. Raises the last error only after all
        attempts are exhausted; otherwise returns a status-checked response.
        """
        last_exc: Optional[Exception] = None
        for attempt in range(1, _REQUEST_TRIES + 1):
            try:
                resp = self.client.request(method, path, **kwargs)
            except _RETRYABLE_EXC as exc:
                last_exc = exc
                if attempt >= _REQUEST_TRIES:
                    break
                wait = min(attempt * _REQUEST_BACKOFF, 30)
                log.warning(
                    "%s %s failed (attempt %d/%d): %s — retrying in %ds",
                    method, path, attempt, _REQUEST_TRIES, exc, wait,
                )
                time.sleep(wait)
                continue
            if (resp.status_code in _RETRYABLE_STATUS
                    and attempt < _REQUEST_TRIES):
                wait = min(attempt * _REQUEST_BACKOFF, 30)
                log.warning(
                    "%s %s -> HTTP %d (attempt %d/%d) — retrying in %ds",
                    method, path, resp.status_code, attempt,
                    _REQUEST_TRIES, wait,
                )
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp
        # Only reachable when every attempt raised a transport error.
        raise last_exc  # type: ignore[misc]

    def get(self, path: str) -> httpx.Response:
        return self._request("GET", path)

    def post(self, path: str, data: dict) -> httpx.Response:
        return self._request("POST", path, data=data)

    def close(self):
        self.client.close()


# ---------------------------------------------------------------------------
# Credentials loader
# ---------------------------------------------------------------------------

def load_credentials() -> Tuple[str, str]:
    """Load Realtrack credentials from env vars or .env files.

    Returns (username, password) or exits with an error message.
    """
    username = os.environ.get("REALTRACK_USER", "").strip()
    password = os.environ.get("REALTRACK_PASS", "").strip()
    if not username or not password:
        for env_path in [
            PROJECT_ROOT / "engines" / "rt" / "scraper" / ".env",
            PROJECT_ROOT / ".env",
            Path.home() / "cleo-turbo" / ".env",
        ]:
            if env_path.is_file():
                with open(env_path) as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("#") or "=" not in line:
                            continue
                        key, val = line.split("=", 1)
                        key, val = key.strip(), val.strip()
                        if key == "REALTRACK_USER" and not username:
                            username = val
                        elif key == "REALTRACK_PASS" and not password:
                            password = val
                if username and password:
                    break

    if not username or not password:
        log.error("Set REALTRACK_USER and REALTRACK_PASS environment variables,")
        log.error("or create engines/rt/scraper/.env with:")
        log.error("  REALTRACK_USER=your_username")
        log.error("  REALTRACK_PASS=your_password")
        sys.exit(1)

    return username, password


# ---------------------------------------------------------------------------
# Property type discovery
# ---------------------------------------------------------------------------

def discover_property_types(session: RealtrackSession) -> Dict[str, str]:
    """Parse the search form to discover all current sf3 (property type) values.

    Returns dict of {value: label}, e.g. {"retailBldg": "Retail Buildings"}.
    Raises a warning if new types are found that aren't in KNOWN_SF3_VALUES.
    """
    resp = session.get("/?page=search")
    html = resp.text

    # Find the sf3 select block
    select_match = re.search(
        r'<select[^>]*name="sf3"[^>]*>(.*?)</select>',
        html,
        re.DOTALL,
    )
    if not select_match:
        log.warning("Could not find sf3 <select> on search form — using known values")
        return dict(KNOWN_SF3_VALUES)

    select_html = select_match.group(1)
    discovered = {}
    for match in SF3_OPTION_PATTERN.finditer(select_html):
        value, label = match.group(1), match.group(2).strip()
        if value:  # skip the empty "All Property Types" option
            discovered[value] = label

    # Check for new types
    new_types = set(discovered.keys()) - set(KNOWN_SF3_VALUES.keys())
    if new_types:
        log.warning(
            "NEW property types found on Realtrack: %s",
            ", ".join(f"{v} ({discovered[v]})" for v in sorted(new_types)),
        )

    missing_types = set(KNOWN_SF3_VALUES.keys()) - set(discovered.keys())
    if missing_types:
        log.warning(
            "Property types REMOVED from Realtrack: %s",
            ", ".join(sorted(missing_types)),
        )

    return discovered
