from __future__ import annotations

import asyncio

import pytest

from genshin_collector.api import MarketApi
from genshin_collector.models import ListingObservation


def test_send_listings_uses_small_batches(monkeypatch):
    api = MarketApi("https://example.invalid", "token")
    calls = []

    async def fake_post(path, payload):
        calls.append((path, len(payload["listings"])))
        return {"received": len(payload["listings"]), "changed": 0}

    monkeypatch.setattr(api, "_post", fake_post)
    rows = [ListingObservation(platform="X", url=f"https://x/{i}", title=str(i)) for i in range(19)]
    result = asyncio.run(api.send_listings("scan", rows))

    assert result["received"] == 19
    assert [n for _, n in calls] == [8, 8, 3]


def test_send_listings_caps_requested_batch_size(monkeypatch):
    api = MarketApi("https://example.invalid", "token")
    sizes = []

    async def fake_post(path, payload):
        sizes.append(len(payload["listings"]))
        return {"received": len(payload["listings"]), "changed": 0}

    monkeypatch.setattr(api, "_post", fake_post)
    rows = [ListingObservation(platform="X", url=f"https://x/{i}", title=str(i)) for i in range(41)]
    asyncio.run(api.send_listings("scan", rows, batch_size=999))
    assert sizes == [20, 20, 1]


def test_fast_listing_batches_request_sparse_observations(monkeypatch):
    api = MarketApi("https://example.invalid", "token")
    policies = []

    async def fake_post(path, payload):
        policies.append(payload["observation_policy"])
        return {"received": len(payload["listings"]), "changed": 0}

    monkeypatch.setattr(api, "_post", fake_post)
    rows = [ListingObservation(platform="X", url="https://x/1", title="one")]
    asyncio.run(api.send_listings("scan", rows, observation_policy="changes_only"))
    assert policies == ["changes_only"]
