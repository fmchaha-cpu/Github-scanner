from __future__ import annotations

import argparse
import asyncio
import os
import uuid
from urllib.parse import urlparse

from . import __version__
from .api import MarketApi
from .models import ListingObservation, CoverageRow
from .normalize import infer_external_id
from .adapters.generic import GenericMarketplaceAdapter


def infer_platform(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "playerauctions" in host: return "PlayerAuctions"
    if "zeusx" in host: return "ZeusX"
    if "epicnpc" in host: return "EpicNPC"
    if "eldorado" in host: return "Eldorado"
    if "g2g" in host: return "G2G"
    if "playerup" in host: return "PlayerUp"
    return host or "Manual"


async def run(url: str, platform: str | None = None):
    api_url = os.environ.get("MARKET_API_URL", "").strip()
    token = os.environ.get("MARKET_API_TOKEN", "").strip()
    if not api_url or not token:
        raise SystemExit("MARKET_API_URL and MARKET_API_TOKEN must be set")
    platform = platform or infer_platform(url)
    scan_id = str(uuid.uuid4())
    api = MarketApi(api_url, token)
    await api.start_scan(scan_id, __version__, notes="manual exact-URL ingest")
    adapter = GenericMarketplaceAdapter(platform, [], [r".*"], use_browser_fallback=True, deep_verify_limit=1)
    try:
        html, mode = await adapter._fetch(url)
        base = ListingObservation(platform=platform, external_id=infer_external_id(platform, url), url=url, title=url, data_confidence=60)
        row = adapter._parse_detail(base, html)
        await api.send_coverage(scan_id, [CoverageRow(platform=platform, query_family="manual_exact_url", query_text=url, page_label="exact", status=f"ok:{mode}", result_count=1)])
        await api.send_listings(scan_id, [row])
        await api.finish_scan(scan_id, "ok", 1, 1, 1 if row.is_candidate else 0, 0, notes="manual exact URL")
        print(row.model_dump_json(indent=2))
    except Exception as exc:
        await api.send_coverage(scan_id, [CoverageRow(platform=platform, query_family="manual_exact_url", query_text=url, page_label="exact", status="error", error=str(exc))])
        await api.finish_scan(scan_id, "failed", 1, 0, 0, 1, notes=str(exc))
        raise


def cli():
    p = argparse.ArgumentParser()
    p.add_argument("url")
    p.add_argument("--platform", default=None)
    args = p.parse_args()
    asyncio.run(run(args.url, args.platform))

if __name__ == "__main__":
    cli()
