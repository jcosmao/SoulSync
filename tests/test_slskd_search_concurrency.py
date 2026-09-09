"""slskd permits one concurrent API operation, and cannot carry many searches
on the network at once either. Both used to surface as "no results found",
which is indistinguishable from the track not existing.
"""

import asyncio

import pytest

from core import slskd_throttle
from core.soulseek_client import SlskdSearchRefused, SoulseekClient


@pytest.fixture(autouse=True)
def _reset():
    slskd_throttle._reset_for_tests()
    yield
    slskd_throttle._reset_for_tests()


def test_gate_admits_only_max_in_flight_at_once():
    peak = 0
    current = 0

    async def one():
        nonlocal peak, current
        async with slskd_throttle.searching():
            current += 1
            peak = max(peak, current)
            await asyncio.sleep(0.05)
            current -= 1

    async def main():
        await asyncio.gather(*(one() for _ in range(8)))

    asyncio.run(main())
    assert peak <= slskd_throttle.MAX_IN_FLIGHT
    assert peak > 0


def test_gate_is_released_when_the_body_raises():
    async def main():
        with pytest.raises(ValueError):
            async with slskd_throttle.searching():
                raise ValueError("boom")
        # A leaked permit would make every later search block forever.
        async with slskd_throttle.searching():
            pass

    asyncio.run(asyncio.wait_for(main(), timeout=5))


def _client():
    client = SoulseekClient()
    client.base_url = "http://slskd.test:5030"
    return client


def test_refused_creation_is_retried_then_succeeds(monkeypatch):
    """A 429 clears as soon as the previous request finishes, so retrying is
    the difference between a result and a track reported missing."""
    from core import soulseek_client as mod

    calls = []

    async def fake_make_request(self, method, endpoint, **kwargs):
        calls.append((method, endpoint))
        if len(calls) < 3:
            mod._search_create_refused.set(True)
            return None
        return {"id": "search-1"}

    monkeypatch.setattr(SoulseekClient, "_make_request", fake_make_request)
    monkeypatch.setattr(mod, "_SEARCH_CREATE_BACKOFF", 0.001)

    got = asyncio.run(_client()._create_search({"searchText": "x"}))
    assert got == {"id": "search-1"}
    assert len(calls) == 3


def test_creation_refused_throughout_raises_rather_than_returning_empty(monkeypatch):
    """The caller must be able to tell "slskd refused us" from "the network has
    nothing" — an empty result reads as the track being unavailable."""
    from core import soulseek_client as mod

    async def always_refused(self, method, endpoint, **kwargs):
        mod._search_create_refused.set(True)
        return None

    monkeypatch.setattr(SoulseekClient, "_make_request", always_refused)
    monkeypatch.setattr(mod, "_SEARCH_CREATE_BACKOFF", 0.001)

    with pytest.raises(SlskdSearchRefused):
        asyncio.run(_client()._create_search({"searchText": "x"}))


def test_a_real_failure_is_not_retried(monkeypatch):
    """400/405/500 return None as before: retrying them only wastes the budget."""
    calls = []

    async def bad_request(self, method, endpoint, **kwargs):
        calls.append(endpoint)
        return None            # no refusal flag set

    monkeypatch.setattr(SoulseekClient, "_make_request", bad_request)

    assert asyncio.run(_client()._create_search({"searchText": "x"})) is None
    assert len(calls) == 1


def test_search_reports_a_refusal_instead_of_an_empty_result(monkeypatch):
    """End to end: `search` raises rather than returning ([], []), so the
    download worker records a search error instead of "no results found"."""
    from core import soulseek_client as mod

    async def always_refused(self, method, endpoint, **kwargs):
        mod._search_create_refused.set(True)
        return None

    monkeypatch.setattr(SoulseekClient, "_make_request", always_refused)
    monkeypatch.setattr(mod, "_SEARCH_CREATE_BACKOFF", 0.001)

    with pytest.raises(SlskdSearchRefused):
        asyncio.run(_client().search("in the mood for noune", timeout=1))
