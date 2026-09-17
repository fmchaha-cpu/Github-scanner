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


def _pct(num: int, den: int) -> float:
    return round(100 * num / den, 1) if den else 0.0


def _quality_metrics(rows, coverage, errors) -> dict:
    n = len(rows)
    completeness = {
        "price_pct": _pct(sum(r.price_value is not None for r in rows), n),
        "server_pct": _pct(sum(bool(r.server) for r in rows), n),
        "seller_pct": _pct(sum(bool(r.seller) for r in rows), n),
        "availability_pct": _pct(sum(bool(r.availability) for r in rows), n),
        "external_id_pct": _pct(sum(bool(r.external_id) for r in rows), n),
        "detail_verified_pct": _pct(sum(r.verification_level == "detail" for r in rows), n),
        "identity_verified_pct": _pct(sum(r.identity_verified for r in rows), n),
        "strict_live_pct": _pct(sum(r.strict_live for r in rows), n),
        "avg_extraction_quality": round(
            sum(float(r.extraction_quality or 0) for r in rows) / n, 1
        ) if n else 0.0,
    }

    by_platform = Counter(r.platform for r in rows)
    platform_quality: dict[str, dict] = {}
    for platform in sorted(by_platform):
        pr = [r for r in rows if r.platform == platform]
        pn = len(pr)
        candidates = [r for r in pr if r.is_candidate]
        platform_quality[platform] = {
            "listings": pn,
            "candidates": len(candidates),
            "price_pct": _pct(sum(r.price_value is not None for r in pr), pn),
            "server_pct": _pct(sum(bool(r.server) for r in pr), pn),
            "seller_pct": _pct(sum(bool(r.seller) for r in pr), pn),
            "availability_pct": _pct(sum(bool(r.availability) for r in pr), pn),
            "detail_verified_pct": _pct(sum(r.verification_level == "detail" for r in pr), pn),
            "candidate_detail_verified_pct": _pct(sum(r.verification_level == "detail" for r in candidates), len(candidates)),
            "identity_verified_pct": _pct(sum(r.identity_verified for r in pr), pn),
            "strict_live_pct": _pct(sum(r.strict_live for r in pr), pn),
            "avg_extraction_quality": round(sum(float(r.extraction_quality or 0) for r in pr) / pn, 1) if pn else 0.0,
        }

    archetypes = Counter()
    reasons = Counter()
    quality_flags = Counter()
    risk_flags = Counter()
    verification_reasons = Counter()
    parser_strategies = Counter()
    for r in rows:
        for archetype in (r.archetypes or [r.archetype or "Unknown"]):
            archetypes[archetype] += 1
        for reason in (r.detector_reason or "").split(","):
            if reason:
                reasons[reason] += 1
        for flag in r.quality_flags:
            quality_flags[flag] += 1
        for flag in r.risk_flags:
            risk_flags[flag] += 1
        if r.verification_reason:
            verification_reasons[r.verification_reason] += 1
        if r.parser_strategy:
            parser_strategies[r.parser_strategy] += 1

    coverage_status = Counter(c.status for c in coverage)
    coverage_families = Counter(c.query_family for c in coverage if c.status.startswith("ok:"))
    searched_rows = [c for c in coverage if c.status.startswith("ok:")]
    zero_hit_searches = [
        {
            "platform": c.platform, "family": c.query_family, "query": c.query_text,
            "page": c.page_label, "fetch_mode": c.fetch_mode,
            "detail_links": c.detail_link_count, "fallback_reason": c.fallback_reason,
            "blocked_signals": c.blocked_signals, "final_url": c.final_url,
            "unmatched_listing_like_count": c.unmatched_listing_like_count,
            "sample_unmatched_listing_like_urls": c.sample_unmatched_listing_like_urls,
            "http_probe_detail_links": c.http_probe_detail_link_count,
            "http_probe_blocked_signals": c.http_probe_blocked_signals,
        }
        for c in searched_rows if c.result_count == 0
    ]

    coverage_diagnostics: dict[str, dict] = {}
    content_groups: dict[tuple[str, str], list] = {}
    http_content_groups: dict[tuple[str, str], list] = {}
    for platform in sorted({c.platform for c in searched_rows}):
        pc = [c for c in searched_rows if c.platform == platform]
        pages = len(pc)
        detail_links = sum(int(c.detail_link_count or 0) for c in pc)
        parsed = sum(int(c.parsed_count if c.parsed_count is not None else c.result_count or 0) for c in pc)
        fallback_pages = sum(bool(c.fallback_reason) for c in pc)
        browser_pages = sum(c.fetch_mode == "browser" for c in pc)
        blocked_pages = sum(bool(c.blocked_signals) for c in pc)
        http_probe_blocked_pages = sum(bool(c.http_probe_blocked_signals) for c in pc)
        zero_detail = sum((c.detail_link_count or 0) == 0 for c in pc)
        zero_parsed = sum((c.parsed_count if c.parsed_count is not None else c.result_count or 0) == 0 for c in pc)
        unmatched_listing_like = sum(int(c.unmatched_listing_like_count or 0) for c in pc)
        http_unmatched_listing_like = sum(int(c.http_probe_unmatched_listing_like_count or 0) for c in pc)
        redirected_http_pages = sum(bool(c.http_probe_final_url and c.final_url and c.http_probe_final_url != c.final_url) for c in pc)
        elapsed = [int(c.elapsed_ms) for c in pc if c.elapsed_ms is not None]
        hashes = [c.content_hash for c in pc if c.content_hash]
        for c in pc:
            if c.content_hash:
                content_groups.setdefault((platform, c.content_hash), []).append(c)
            if c.http_probe_content_hash:
                http_content_groups.setdefault((platform, c.http_probe_content_hash), []).append(c)
        coverage_diagnostics[platform] = {
            "pages": pages,
            "browser_pages": browser_pages,
            "browser_pct": _pct(browser_pages, pages),
            "fallback_pages": fallback_pages,
            "fallback_pct": _pct(fallback_pages, pages),
            "blocked_pages": blocked_pages,
            "http_probe_blocked_pages": http_probe_blocked_pages,
            "zero_detail_link_pages": zero_detail,
            "zero_parsed_pages": zero_parsed,
            "unmatched_listing_like_links": unmatched_listing_like,
            "http_probe_unmatched_listing_like_links": http_unmatched_listing_like,
            "redirected_http_pages": redirected_http_pages,
            "detail_links": detail_links,
            "parsed_rows": parsed,
            "parse_yield_pct": _pct(parsed, detail_links) if detail_links else 0.0,
            "avg_elapsed_ms": round(sum(elapsed) / len(elapsed), 0) if elapsed else None,
            "unique_content_hashes": len(set(hashes)),
        }

    repeated_content = []
    for (platform, content_hash), group in content_groups.items():
        distinct_paths = {c.path_key for c in group if c.path_key}
        if len(distinct_paths) >= 3:
            repeated_content.append({
                "platform": platform,
                "content_hash": content_hash,
                "paths": len(distinct_paths),
                "queries": [c.query_text for c in group[:8]],
                "page_titles": list(dict.fromkeys(c.page_title for c in group if c.page_title))[:4],
            })

    repeated_http_content = []
    for (platform, content_hash), group in http_content_groups.items():
        distinct_paths = {c.path_key for c in group if c.path_key}
        if len(distinct_paths) >= 3:
            repeated_http_content.append({
                "platform": platform,
                "content_hash": content_hash,
                "paths": len(distinct_paths),
                "queries": [c.query_text for c in group[:8]],
            })

    fallback_reasons = Counter(c.fallback_reason for c in searched_rows if c.fallback_reason)
    blocked_signals = Counter(sig for c in searched_rows for sig in (c.blocked_signals or []))
    http_probe_blocked_signals = Counter(sig for c in searched_rows for sig in (c.http_probe_blocked_signals or []))

    improvement_signals: list[str] = []
    if completeness.get("seller_pct", 100) < 60:
        improvement_signals.append("seller_extraction_low")
    if completeness.get("server_pct", 100) < 70:
        improvement_signals.append("server_extraction_low")
    if completeness.get("price_pct", 100) < 75:
        improvement_signals.append("price_extraction_low")
    if n and completeness.get("detail_verified_pct", 100) < 10:
        improvement_signals.append("deep_verification_coverage_low")
    if zero_hit_searches:
        improvement_signals.append("zero_hit_queries_present")
    if errors:
        improvement_signals.append("source_errors_present")
    if blocked_signals:
        improvement_signals.append("blocking_or_challenge_detected")
    if http_probe_blocked_signals:
        improvement_signals.append("http_probe_blocking_detected")
    if repeated_content:
        improvement_signals.append("same_content_across_queries")
    if repeated_http_content:
        improvement_signals.append("same_http_probe_content_across_queries")
    if n >= 25 and sum(r.market_status in {"SOLD_CONFIRMED", "SOLD_CLAIMED", "EXPIRED_REMOVED"} for r in rows) < 3:
        improvement_signals.append("historical_comparable_pool_still_small")
    if n and sum(bool(r.relisting_fingerprint) for r in rows) / n < 0.95:
        improvement_signals.append("relisting_fingerprint_coverage_low")
    if n and verification_reasons.get("calibration", 0) == 0:
        improvement_signals.append("no_calibration_sample_verified")

    for platform, d in coverage_diagnostics.items():
        if d["pages"] >= 1 and d["parsed_rows"] == 0:
            improvement_signals.append(f"source_zero_yield:{platform}")
        if d["detail_links"] >= 5 and d["parse_yield_pct"] < 55:
            improvement_signals.append(f"parser_yield_low:{platform}")
        if d["unmatched_listing_like_links"] > 0 or d["http_probe_unmatched_listing_like_links"] > 0:
            improvement_signals.append(f"detail_pattern_drift_suspected:{platform}")
        if d["http_probe_blocked_pages"] > 0:
            improvement_signals.append(f"http_probe_blocked:{platform}")
    for platform, pq in platform_quality.items():
        if pq.get("seller_pct", 100) < 40 and pq.get("listings", 0) >= 5:
            improvement_signals.append(f"seller_extraction_low:{platform}")

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
        "platform_quality": platform_quality,
        "coverage_diagnostics": coverage_diagnostics,
        "verification_reasons": dict(verification_reasons),
        "parser_strategies": dict(parser_strategies),
        "top_reasons": reasons.most_common(15),
        "top_quality_flags": quality_flags.most_common(20),
        "risk_flags": dict(risk_flags),
        "coverage_status": dict(coverage_status),
        "coverage_families": dict(coverage_families),
        "zero_hit_searches": zero_hit_searches[:40],
        "repeated_content_groups": repeated_content[:20],
        "repeated_http_probe_content_groups": repeated_http_content[:20],
        "fallback_reasons": dict(fallback_reasons),
        "blocked_signals": dict(blocked_signals),
        "http_probe_blocked_signals": dict(http_probe_blocked_signals),
        "error_count": len(errors),
        "improvement_signals": list(dict.fromkeys(improvement_signals)),
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
    deep_verify_hard_cap = int(collector_cfg.get("deep_verify_hard_cap_per_source", 16))
    calibration_verify_sample = int(collector_cfg.get("calibration_verify_sample_per_source", 2))

    scan_id = str(uuid.uuid4())
    api = MarketApi(api_url, api_token)
    await api.start_scan(scan_id, __version__, notes="scheduled collector v0.6 observability+adaptive-verification+history")

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
                deep_verify_hard_cap=int(source.get("deep_verify_hard_cap", deep_verify_hard_cap)),
                calibration_verify_sample=int(source.get("calibration_verify_sample", calibration_verify_sample)),
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
            code="SCAN_QUALITY_V06",
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
                code="SCAN_FAILED_V06",
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
