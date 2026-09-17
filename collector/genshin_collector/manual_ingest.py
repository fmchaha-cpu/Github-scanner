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

HISTORICAL_STATUSES = [
    "SOLD_CONFIRMED", "SOLD_CLAIMED", "EXPIRED_REMOVED", "OUTCOME_UNKNOWN", "RISK_CONTAMINATED"
]


def infer_platform(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "playerauctions" in host: return "PlayerAuctions"
    if "zeusx" in host: return "ZeusX"
    if "epicnpc" in host: return "EpicNPC"
    if "eldorado" in host: return "Eldorado"
    if "g2g" in host: return "G2G"
    if "playerup" in host: return "PlayerUp"
    return host or "Manual"


async def run(
    url: str,
    platform: str | None = None,
    historical_status: str | None = None,
    historical_confidence: float = 0.8,
    historical_evidence: str = "manual_exact_url_review",
    historical_notes: str | None = None,
):
    api_url = os.environ.get("MARKET_API_URL", "").strip()
    token = os.environ.get("MARKET_API_TOKEN", "").strip()
    if not api_url or not token:
        raise SystemExit("MARKET_API_URL and MARKET_API_TOKEN must be set")
    platform = platform or infer_platform(url)
    scan_id = str(uuid.uuid4())
    api = MarketApi(api_url, token)
    await api.start_scan(scan_id, __version__, notes="manual exact-URL ingest v0.5")
    adapter = GenericMarketplaceAdapter(platform, [], [r".*"], use_browser_fallback=True, deep_verify_limit=1)
    try:
        html, mode = await adapter._fetch(url)
        base = ListingObservation(
            platform=platform,
            external_id=infer_external_id(platform, url),
            url=url,
            title=url,
            data_confidence=60,
        )
        row = adapter._parse_detail(base, html)
        path_key = f"{platform}|manual_exact_url|exact"
        row.discovery_paths = [path_key]
        await api.send_coverage(scan_id, [CoverageRow(
            platform=platform,
            query_family="manual_exact_url",
            query_text=url,
            page_label="exact",
            path_key=path_key,
            status=f"ok:{mode}",
            result_count=1,
        )])
        await api.send_listings(scan_id, [row])
        await api.finish_scan(scan_id, "ok", 1, 1, 1 if row.is_candidate else 0, 0, notes="manual exact URL")
        if historical_status:
            await api.annotate_historical(
                listing_url=url,
                status=historical_status,
                confidence=historical_confidence,
                evidence=historical_evidence,
                notes=historical_notes,
            )
        print(row.model_dump_json(indent=2))
        if historical_status:
            print(f"historical_annotation={historical_status} confidence={historical_confidence}")
    except Exception as exc:
        await api.send_coverage(scan_id, [CoverageRow(
            platform=platform,
            query_family="manual_exact_url",
            query_text=url,
            page_label="exact",
            path_key=f"{platform}|manual_exact_url|exact",
            status="error",
            error=str(exc),
        )])
        await api.finish_scan(scan_id, "failed", 1, 0, 0, 1, notes=str(exc))
        raise


def cli():
    p = argparse.ArgumentParser()
    p.add_argument("url")
    p.add_argument("--platform", default=None)
    p.add_argument("--historical-status", choices=HISTORICAL_STATUSES, default=None)
    p.add_argument("--historical-confidence", type=float, default=0.8)
    p.add_argument("--historical-evidence", default="manual_exact_url_review")
    p.add_argument("--historical-notes", default=None)
    args = p.parse_args()
    asyncio.run(run(
        args.url, args.platform, args.historical_status,
        args.historical_confidence, args.historical_evidence, args.historical_notes,
    ))

if __name__ == "__main__":
    cli()
