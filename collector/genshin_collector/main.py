from __future__ import annotations

import argparse
import asyncio
import os
import uuid
from collections import Counter
from pathlib import Path

from . import __version__
from .api import MarketApi
from .config import load_config
from .adapters.generic import GenericMarketplaceAdapter
from .models import CoverageRow


def _quality_metrics(rows, coverage, errors) -> dict:
    n = len(rows)
    if n == 0:
        completeness = {}
    else:
        completeness = {
            "price_pct": round(100 * sum(r.price_value is not None for r in rows) / n, 1),
            "server_pct": round(100 * sum(bool(r.server) for r in rows) / n, 1),
            "seller_pct": round(100 * sum(bool(r.seller) for r in rows) / n, 1),
            "availability_pct": round(100 * sum(bool(r.availability) for r in rows) / n, 1),
            "external_id_pct": round(100 * sum(bool(r.external_id) for r in rows) / n, 1),
            "detail_verified_pct": round(100 * sum(r.verification_level == "detail" for r in rows) / n, 1),
            "identity_verified_pct": round(100 * sum(r.identity_verified for r in rows) / n, 1),
            "strict_live_pct": round(100 * sum(r.strict_live for r in rows) / n, 1),
        }

    by_platform = Counter(r.platform for r in rows)
    archetypes = Counter()
    for r in rows:
        for archetype in (r.archetypes or [r.archetype or "Unknown"]):
            archetypes[archetype] += 1
    reasons = Counter()
    quality_flags = Counter()
    risk_flags = Counter()
    for row in rows:
        for reason in (row.detector_reason or "").split(","):
            if reason:
                reasons[reason] += 1
        for flag in row.quality_flags:
            quality_flags[flag] += 1
        for flag in row.risk_flags:
            risk_flags[flag] += 1

    coverage_status = Counter(c.status for c in coverage)
    coverage_families = Counter(c.query_family for c in coverage if c.status.startswith("ok:"))
    searched_rows = [c for c in coverage if c.status.startswith("ok:")]
    zero_hit_searches = [
        {
            "platform": c.platform,
            "family": c.query_family,
            "query": c.query_text,
            "page": c.page_label,
        }
        for c in searched_rows if c.result_count == 0
    ]

    improvement_signals: list[str] = []
    if completeness.get("seller_pct", 100) < 60:
        improvement_signals.append("seller_extraction_low")
    if completeness.get("server_pct", 100) < 70:
        improvement_signals.append("server_extraction_low")
    if completeness.get("price_pct", 100) < 75:
        improvement_signals.append("price_extraction_low")
    if n and completeness.get("detail_verified_pct", 100) < 8:
        improvement_signals.append("deep_verification_coverage_low")
    if zero_hit_searches:
        improvement_signals.append("zero_hit_queries_present")
    if errors:
        improvement_signals.append("source_errors_present")
    if n >= 25 and sum(r.market_status in {"SOLD_CONFIRMED", "SOLD_CLAIMED", "EXPIRED_REMOVED"} for r in rows) < 3:
        improvement_signals.append("historical_comparable_pool_still_small")
    if n and sum(bool(r.relisting_fingerprint) for r in rows) / n < 0.95:
        improvement_signals.append("relisting_fingerprint_coverage_low")

    return {
        "listing_count": n,
        "candidate_count": sum(r.is_candidate for r in rows),
        "review_gate_count": sum(r.is_alert_candidate for r in rows),
        "identity_verified_count": sum(r.identity_verified for r in rows),
        "strict_live_count": sum(r.strict_live for r in rows),
        "risk_flagged_count": sum(bool(r.risk_flags) for r in rows),
        "market_statuses": dict(Counter(r.market_status for r in rows)),
        "historical_anchor_observations": sum(r.market_status in {"SOLD_CONFIRMED", "SOLD_CLAIMED"} for r in rows),
        "fingerprint_groups": len({r.relisting_fingerprint for r in rows if r.relisting_fingerprint}),
        "completeness": completeness,
        "by_platform": dict(by_platform),
        "archetypes": dict(archetypes),
        "top_reasons": reasons.most_common(15),
        "top_quality_flags": quality_flags.most_common(15),
        "risk_flags": dict(risk_flags),
        "coverage_status": dict(coverage_status),
        "coverage_families": dict(coverage_families),
        "zero_hit_searches": zero_hit_searches[:30],
        "error_count": len(errors),
        "improvement_signals": improvement_signals,
    }


async def run(config_path: str):
    cfg = load_config(config_path)
    api_url = os.environ.get("MARKET_API_URL", "").strip()
    api_token = os.environ.get("MARKET_API_TOKEN", "").strip()
    if not api_url or not api_token:
        raise SystemExit("MARKET_API_URL and MARKET_API_TOKEN must be set")

    preferences = cfg.get("preferences", {}) or {}
    favorite_characters = list(preferences.get("favorite_characters", []) or [])
    collector_cfg = cfg.get("collector", {}) or {}
    deep_verify_limit = int(collector_cfg.get("deep_verify_limit_per_source", 8))

    scan_id = str(uuid.uuid4())
    api = MarketApi(api_url, api_token)
    await api.start_scan(scan_id, __version__, notes="scheduled collector v0.5 history+quality+recall")

    all_listings = {}
    all_coverage = []
    all_errors = []
    source_count = 0

    try:
        for source in cfg.get("sources", []):
            if not source.get("enabled", True):
                # Explicitly record the coverage gap so quality reports never confuse disabled with searched/no-hit.
                all_coverage.append(CoverageRow(
                    platform=source.get("name", "Unknown"),
                    query_family="source_disabled",
                    query_text="source disabled or awaiting calibration",
                    page_label="n/a",
                    path_key=f"{source.get('name', 'Unknown')}|disabled",
                    status="not_searched:disabled",
                    result_count=0,
                ))
                continue
            source_count += 1
            adapter = GenericMarketplaceAdapter(
                name=source["name"],
                scans=source.get("scans", []),
                detail_patterns=source.get("detail_patterns", []),
                use_browser_fallback=source.get("use_browser_fallback", True),
                deep_verify_limit=int(source.get("deep_verify_limit", deep_verify_limit)),
                favorite_characters=favorite_characters,
            )
            result = await adapter.scan()
            for o in result.listings:
                previous = all_listings.get(o.url)
                if previous:
                    o.discovery_paths = list(dict.fromkeys(previous.discovery_paths + o.discovery_paths))
                    if (previous.data_confidence or 0) > (o.data_confidence or 0):
                        previous.discovery_paths = o.discovery_paths
                        o = previous
                all_listings[o.url] = o
            all_coverage.extend(result.coverage)
            all_errors.extend(result.errors)

        await api.send_coverage(scan_id, all_coverage)
        rows = list(all_listings.values())
        send_result = await api.send_listings(scan_id, rows)
        candidates = sum(1 for r in rows if r.is_candidate)
        metrics = _quality_metrics(rows, all_coverage, all_errors)
        metrics["changed_count"] = send_result.get("changed", 0)
        metrics["favorite_characters_configured"] = favorite_characters

        severity = "warning" if metrics["improvement_signals"] or all_errors else "info"
        await api.send_system_event(
            component="collector",
            severity=severity,
            code="SCAN_QUALITY_V05",
            message=(
                f"scan {scan_id}: {len(rows)} listings, {candidates} candidates, "
                f"{metrics['identity_verified_count']} identity-verified, {len(all_errors)} errors"
            ),
            details_json=metrics,
        )

        status = "ok" if not all_errors else "partial"
        await api.finish_scan(
            scan_id,
            status,
            source_count,
            len(rows),
            candidates,
            len(all_errors),
            notes="; ".join(all_errors[:5]) or None,
        )
        print(
            f"scan={scan_id} sources={source_count} listings={len(rows)} "
            f"candidates={candidates} identity={metrics['identity_verified_count']} "
            f"strict_live={metrics['strict_live_count']} review_gate={metrics['review_gate_count']} "
            f"errors={len(all_errors)}"
        )
        print(f"quality={metrics}")
    except Exception as exc:
        try:
            await api.send_system_event(
                component="collector",
                severity="error",
                code="SCAN_FAILED_V05",
                message=str(exc),
                details_json={"scan_id": scan_id, "errors": all_errors[:10]},
            )
        except Exception:
            pass
        try:
            await api.finish_scan(
                scan_id,
                "failed",
                source_count,
                len(all_listings),
                0,
                len(all_errors) + 1,
                notes=str(exc),
            )
        finally:
            raise


def cli():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(Path(__file__).resolve().parents[1] / "sources.yaml"))
    args = parser.parse_args()
    asyncio.run(run(args.config))


if __name__ == "__main__":
    cli()
