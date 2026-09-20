from __future__ import annotations

import argparse
import asyncio
import json
import os

from .discord import ps5_payload, send
from .ps5 import PS5Store, alert_tier, scan


async def run(config_path: str) -> int:
    outcome, cfg = await scan(config_path)
    db_path = os.environ.get("PS5_STATE_DB", "/var/lib/genshin-scanner/ps5-deals.sqlite3")
    webhook = (
        os.environ.get("DISCORD_WEBHOOK_PS5", "").strip()
        or os.environ.get("DISCORD_WEBHOOK_GENSHIN", "").strip()
        or os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    )
    store = PS5Store(db_path)
    alerts_sent = 0
    alerts_eligible = 0
    alert_errors: list[str] = []
    try:
        for offer in outcome.offers:
            tier = alert_tier(offer, cfg.get("thresholds") or {})
            should_alert = store.observe(offer, tier, float(cfg.get("minimum_alert_price_drop_eur", 10)))
            if not should_alert or tier is None:
                continue
            alerts_eligible += 1
            if not webhook:
                continue
            try:
                await send(webhook, ps5_payload(tier, offer.as_dict(), cfg.get("reference_prices") or {}))
                store.mark_alerted(offer, tier)
                alerts_sent += 1
            except Exception as exc:
                alert_errors.append(f"{offer.source} {offer.model}: {type(exc).__name__}: {exc}")
        outcome.errors.extend(alert_errors)
        store.record_scan(outcome, alerts_sent)
    finally:
        store.close()

    summary = {
        "scanner": "ps5-deal-watcher",
        "scan_id": outcome.scan_id,
        "started_at": outcome.started_at,
        "finished_at": outcome.finished_at,
        "sources_attempted": outcome.sources_attempted,
        "offers_found": len(outcome.offers),
        "alerts_eligible": alerts_eligible,
        "alerts_sent": alerts_sent,
        "discord_configured": bool(webhook),
        "errors": outcome.errors,
        "offers": [
            {
                "source": row.source,
                "model": row.model,
                "condition": row.condition,
                "price_eur": row.price_eur,
                "availability": row.availability,
                "title": row.title,
                "url": row.url,
                "tier": alert_tier(row, cfg.get("thresholds") or {}),
            }
            for row in outcome.offers
        ],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    all_sources_failed = outcome.sources_attempted > 0 and len(outcome.errors) >= outcome.sources_attempted and not outcome.offers
    return 1 if all_sources_failed or alert_errors else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="German PS5 Disc/Digital deal watcher")
    parser.add_argument("--config", default="ps5_sources.yaml")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.config)))


if __name__ == "__main__":
    main()
