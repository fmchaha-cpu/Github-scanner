from __future__ import annotations

import argparse
import asyncio
import os
import uuid
from pathlib import Path

from . import __version__
from .api import MarketApi
from .config import load_config
from .adapters.generic import GenericMarketplaceAdapter


async def run(config_path: str):
    cfg = load_config(config_path)
    api_url = os.environ.get("MARKET_API_URL", "").strip()
    api_token = os.environ.get("MARKET_API_TOKEN", "").strip()
    if not api_url or not api_token:
        raise SystemExit("MARKET_API_URL and MARKET_API_TOKEN must be set")

    scan_id = str(uuid.uuid4())
    api = MarketApi(api_url, api_token)
    await api.start_scan(scan_id, __version__, notes="scheduled collector")

    all_listings = {}
    all_coverage = []
    all_errors = []
    source_count = 0

    try:
        for source in cfg.get("sources", []):
            if not source.get("enabled", True):
                continue
            source_count += 1
            adapter = GenericMarketplaceAdapter(
                name=source["name"],
                scans=source.get("scans", []),
                detail_patterns=source.get("detail_patterns", []),
                use_browser_fallback=source.get("use_browser_fallback", True),
            )
            result = await adapter.scan()
            for o in result.listings:
                all_listings[o.url] = o
            all_coverage.extend(result.coverage)
            all_errors.extend(result.errors)

        await api.send_coverage(scan_id, all_coverage)
        rows = list(all_listings.values())
        await api.send_listings(scan_id, rows)
        candidates = sum(1 for r in rows if r.is_candidate)
        status = "ok" if not all_errors else "partial"
        await api.finish_scan(scan_id, status, source_count, len(rows), candidates, len(all_errors), notes="; ".join(all_errors[:5]) or None)
        print(f"scan={scan_id} sources={source_count} listings={len(rows)} candidates={candidates} errors={len(all_errors)}")
    except Exception as exc:
        try:
            await api.finish_scan(scan_id, "failed", source_count, len(all_listings), 0, len(all_errors)+1, notes=str(exc))
        finally:
            raise


def cli():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(Path(__file__).resolve().parents[1] / "sources.yaml"))
    args = parser.parse_args()
    asyncio.run(run(args.config))


if __name__ == "__main__":
    cli()
