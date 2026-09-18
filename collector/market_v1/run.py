from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys

from .api import V1Api
from .discord import AlertState, listing_payload, send
from .policy import genshin_alert_tier, warframe_alert_tier
from .warframe import scan as scan_warframe, stable_key


async def _notify(game: str, rows: list[dict], webhook: str, state: AlertState, tier_fn) -> tuple[int, list[str]]:
    if not webhook:
        return 0, []
    sent = 0
    errors: list[str] = []
    for row in rows:
        tier = tier_fn(row)
        if not tier:
            continue
        key = stable_key(game.lower(), str(row.get("url")), tier)
        if state.seen(key):
            continue
        try:
            await send(webhook, listing_payload(game, tier, row))
            state.mark(key)
            sent += 1
        except Exception as exc:
            errors.append(f"{game} Discord {row.get('url')}: {type(exc).__name__}: {exc}")
    return sent, errors


async def run(args) -> int:
    api_url = os.environ.get("MARKET_API_URL", "").strip()
    api_token = os.environ.get("MARKET_API_TOKEN", "").strip()
    if not api_url or not api_token:
        raise SystemExit("MARKET_API_URL and MARKET_API_TOKEN must be set")
    api = V1Api(api_url, api_token)
    state = AlertState(os.environ.get("ALERT_STATE_DB", ".state/alerts.sqlite3"))
    total_sent = 0
    operational_errors: list[str] = []

    if args.games in {"all", "genshin"}:
        command = [sys.executable, "-m", "genshin_collector.main", "--config", args.genshin_config]
        completed = subprocess.run(command, check=False)
        if completed.returncode:
            operational_errors.append(f"Genshin collector failed with exit code {completed.returncode}")
        else:
            try:
                recent = await api.get("/v1/candidates/recent?hours=3&limit=100")
                sent, errors = await _notify(
                    "Genshin", list(recent.get("candidates") or []),
                    os.environ.get("DISCORD_WEBHOOK_GENSHIN", os.environ.get("DISCORD_WEBHOOK_URL", "")),
                    state, genshin_alert_tier,
                )
                total_sent += sent
                operational_errors.extend(errors)
            except Exception as exc:
                operational_errors.append(f"Genshin alert phase: {type(exc).__name__}: {exc}")

    if args.games in {"all", "warframe"}:
        try:
            outcome = await scan_warframe(args.warframe_config)
            await api.send_warframe(outcome)
            sent, errors = await _notify(
                "Warframe", [row.model_dump() for row in outcome.listings],
                os.environ.get("DISCORD_WEBHOOK_WARFRAME", os.environ.get("DISCORD_WEBHOOK_URL", "")),
                state, warframe_alert_tier,
            )
            total_sent += sent
            operational_errors.extend(errors)
            if outcome.sources_attempted and not outcome.listings and len(outcome.errors) >= outcome.sources_attempted:
                operational_errors.append("Warframe: all public sources failed or were blocked")
            print(outcome.model_dump_json(indent=2))
        except Exception as exc:
            operational_errors.append(f"Warframe scan/upload: {type(exc).__name__}: {exc}")

    print(f"v1.0 complete; Discord alerts sent: {total_sent}")
    for error in operational_errors:
        print(f"ERROR: {error}", file=sys.stderr)
    return 1 if operational_errors else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Run separated Genshin and Warframe v1 scanners")
    parser.add_argument("--games", choices=["all", "genshin", "warframe"], default="all")
    parser.add_argument("--genshin-config", default="sources.yaml")
    parser.add_argument("--warframe-config", default="warframe_sources.yaml")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
