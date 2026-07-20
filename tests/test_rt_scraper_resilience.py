"""Resilience tests for the RT daily scraper.

These cover the two failure modes that were silently killing the 7:30am
launchd run in mid-July 2026:

  1. Transient RealTrack disconnects ("Server disconnected without sending a
     response" / read timeouts) crashing a request instead of retrying.
  2. An exception in the verification pass aborting an otherwise-successful
     sweep (and, with it, the run metadata and a clean exit code).
"""

import httpx
import pytest

from engines.rt.scraper import shared
from engines.rt.scraper.shared import RealtrackSession
from engines.rt.scraper import daily_scraper


class _FakeResp:
    def __init__(self, status_code=200, text="ok"):
        self.status_code = status_code
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("bad status", request=None, response=None)


def _session_without_login():
    """Build a RealtrackSession without performing the network login."""
    return object.__new__(RealtrackSession)


def test_request_retries_transient_then_succeeds(monkeypatch):
    monkeypatch.setattr(shared.time, "sleep", lambda *_: None)
    calls = {"n": 0}
    good = _FakeResp(200)

    class FakeClient:
        def request(self, method, path, **kwargs):
            calls["n"] += 1
            if calls["n"] < 3:
                raise httpx.RemoteProtocolError("Server disconnected")
            return good

    s = _session_without_login()
    s.client = FakeClient()
    resp = s.get("/?page=search")
    assert resp is good
    assert calls["n"] == 3  # failed twice, succeeded on the third try


def test_request_gives_up_after_max_tries(monkeypatch):
    monkeypatch.setattr(shared.time, "sleep", lambda *_: None)
    calls = {"n": 0}

    class FakeClient:
        def request(self, method, path, **kwargs):
            calls["n"] += 1
            raise httpx.ReadTimeout("read timed out")

    s = _session_without_login()
    s.client = FakeClient()
    with pytest.raises(httpx.ReadTimeout):
        s.post("/?page=results", data={})
    assert calls["n"] == shared._REQUEST_TRIES


def test_request_retries_on_5xx(monkeypatch):
    monkeypatch.setattr(shared.time, "sleep", lambda *_: None)
    seq = [_FakeResp(503), _FakeResp(200)]

    class FakeClient:
        def request(self, method, path, **kwargs):
            return seq.pop(0)

    s = _session_without_login()
    s.client = FakeClient()
    resp = s.get("/x")
    assert resp.status_code == 200
    assert seq == []  # both responses consumed: one 503 retry, then 200


def test_verify_failure_does_not_abort_daily_run(monkeypatch, tmp_path):
    """A crash in verify_completeness must not fail the run or lose the sweep.

    The sweep's detail pages are already on disk for the watcher; a transient
    disconnect during the completeness check should be swallowed, metadata
    still written, and the function should return normally (exit 0).
    """
    monkeypatch.setattr(daily_scraper, "DAILY_DIR", tmp_path)
    monkeypatch.setattr(daily_scraper, "load_credentials", lambda: ("u", "p"))
    monkeypatch.setattr(daily_scraper, "load_existing_rt_ids", lambda *_a: set())

    class FakeSession:
        def __init__(self, *a, **k):
            pass

        def close(self):
            pass

    monkeypatch.setattr(daily_scraper, "RealtrackSession", FakeSession)
    monkeypatch.setattr(
        daily_scraper, "discover_property_types",
        lambda *_a, **_k: dict(shared.KNOWN_SF3_VALUES),
    )
    # Sweep succeeds: 5 found in range, 5 newly downloaded.
    monkeypatch.setattr(
        daily_scraper, "run_sweep",
        lambda *a, **k: (5, 5, 0, ["RT1", "RT2"]),
    )

    def boom(*a, **k):
        raise httpx.RemoteProtocolError("Server disconnected")

    monkeypatch.setattr(daily_scraper, "verify_completeness", boom)

    # Must NOT raise, despite verify blowing up mid-run.
    new_count = daily_scraper.run_daily(lookback_days=14)
    assert new_count == 5

    # Metadata was still written, proving we reached the end cleanly.
    run_jsons = list(tmp_path.glob("*/_run.json"))
    assert run_jsons, "run metadata should be written even when verify fails"
