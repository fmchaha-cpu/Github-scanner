from __future__ import annotations

import pytest

from genshin_collector.api import MarketApi
from genshin_collector.models import ListingObservation


@pytest.mark.asyncio
async def test_send_listings_uses_small_batches(monkeypatch):
    api = MarketApi("https://example.invalid", "token")
    calls = []

    async def fake_post(path, payload):
        calls.append((path, len(payload["listings"])))
        return {"received": len(payload["listings"]), "changed": 0}

    monkeypatch.setattr(api, "_post", fake_post)
    rows = [ListingObservation(platform="X", url=f"https://x/{i}", title=str(i)) for i in range(19)]
    result = await api.send_listings("scan", rows)

    assert result["received"] == 19
    assert [n for _, n in calls] == [8, 8, 3]


@pytest.mark.asyncio
async def test_send_listings_caps_requested_batch_size(monkeypatch):
    api = MarketApi("https://example.invalid", "token")
    sizes = []

    async def fake_post(path, payload):
        sizes.append(len(payload["listings"]))
        return {"received": len(payload["listings"]), "changed": 0}

    monkeypatch.setattr(api, "_post", fake_post)
    rows = [ListingObservation(platform="X", url=f"https://x/{i}", title=str(i)) for i in range(41)]
    await api.send_listings("scan", rows, batch_size=999)
    assert sizes == [20, 20, 1]
