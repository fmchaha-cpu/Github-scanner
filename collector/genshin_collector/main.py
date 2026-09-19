from __future__ import annotations

import argparse
import asyncio
import json
import os
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .api import MarketApi
from .config import load_config
from .adapters.generic import GenericMarketplaceAdapter
from .models import CoverageRow


WORKER_API_VERSION = "1.1"


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
            "merged_anchor_count": sum(r.parser_strategy in {"anchor_merged_v09", "anchor_merged_v10"} for r in pr),
            "price_plausibility_flagged": sum(any(f.startswith("price_implausible:") for f in r.quality_flags) for r in pr),
            "detail_blocked_count": sum(any(f.startswith("detail_blocked:") for f in r.quality_flags) for r in pr),
            "merit_unconfirmed_count": sum(any(f.startswith("detail_missing_merit_evidence") or f.startswith("detail_unconfirmed_c6") for f in r.quality_flags) for r in pr),
            "server_hydrated_url_or_context_pct": _pct(
                sum((r.field_sources or {}).get("server") in {"url_slug", "query_context"} for r in pr), pn
            ),
            "seller_from_profile_pct": _pct(
                sum((r.field_sources or {}).get("seller") in {"profile_link", "detail_profile_link"} for r in pr), pn
            ),
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

    field_source_usage: dict[str, dict[str, dict[str, int]]] = {}
    for r in rows:
        platform_map = field_source_usage.setdefault(r.platform, {})
        for field, source in (r.field_sources or {}).items():
            source_counts = platform_map.setdefault(field, {})
            source_counts[source] = source_counts.get(source, 0) + 1

    stale_quality_flag_count = sum(
        r.verification_level == "detail" and "not_detail_verified" in r.quality_flags for r in rows
    )

    coverage_status = Counter(c.status for c in coverage)
    coverage_families = Counter(c.query_family for c in coverage if c.status.startswith("ok:"))
    avoided_fetches_by_platform = Counter(
        c.platform for c in coverage if c.status in {"skipped:circuit_breaker", "skipped:cooldown"}
    )
    requests_avoided = sum(avoided_fetches_by_platform.values())
    searched_rows = [c for c in coverage if c.status.startswith("ok:") or c.status.startswith("blocked:")]
    zero_hit_searches = [
        {
            "platform": c.platform, "family": c.query_family, "query": c.query_text,
            "page": c.page_label, "fetch_mode": c.fetch_mode,
            "detail_links": c.detail_link_count, "fallback_reason": c.fallback_reason,
            "blocked_signals": c.blocked_signals, "final_url": c.final_url,
            "unmatched_listing_like_count": c.unmatched_listing_like_count,
            "sample_unmatched_listing_like_urls": c.sample_unmatched_listing_like_urls,
            "http_probe_detail_links": c.http_probe_detail_link_count,
            "http_probe_http_status": c.http_probe_http_status,
            "http_probe_blocked_signals": c.http_probe_blocked_signals,
            "browser_early_blocked": c.browser_early_blocked,
            "circuit_breaker_triggered": c.circuit_breaker_triggered,
            "circuit_breaker_reason": c.circuit_breaker_reason,
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
        early_blocked_pages = sum(bool(c.browser_early_blocked) for c in pc)
        breaker_triggers = sum(bool(c.circuit_breaker_triggered) for c in pc)
        http_statuses = Counter(str(c.http_probe_http_status) for c in pc if c.http_probe_http_status is not None)
        final_statuses = Counter(str(c.http_status) for c in pc if c.http_status is not None)
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
            "browser_early_blocked_pages": early_blocked_pages,
            "circuit_breaker_triggers": breaker_triggers,
            "http_probe_statuses": dict(http_statuses),
            "final_statuses": dict(final_statuses),
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
    if n and sum(bool(r.relisting_fingerprint) for r in rows) / n < 0.95:
        improvement_signals.append("relisting_fingerprint_coverage_low")
    if n and verification_reasons.get("calibration_gap", 0) == 0:
        improvement_signals.append("no_calibration_gap_sample_verified")
    if n and verification_reasons.get("control", 0) == 0:
        improvement_signals.append("no_control_sample_verified")
    if stale_quality_flag_count:
        improvement_signals.append("stale_quality_flags_detected")

    for platform, d in coverage_diagnostics.items():
        if d["pages"] >= 1 and d["parsed_rows"] == 0:
            improvement_signals.append(f"source_zero_yield:{platform}")
        if d["detail_links"] >= 5 and d["parse_yield_pct"] < 55:
            improvement_signals.append(f"parser_yield_low:{platform}")
        if d["unmatched_listing_like_links"] > 0 or d["http_probe_unmatched_listing_like_links"] > 0:
            improvement_signals.append(f"detail_pattern_drift_suspected:{platform}")
        if d["http_probe_blocked_pages"] > 0:
            improvement_signals.append(f"http_probe_blocked:{platform}")
        if d.get("circuit_breaker_triggers", 0) > 0:
            improvement_signals.append(f"circuit_breaker_triggered:{platform}")
    for platform, pq in platform_quality.items():
        if pq.get("seller_pct", 100) < 40 and pq.get("listings", 0) >= 5:
            improvement_signals.append(f"seller_extraction_low:{platform}")

    price_plausibility_flags = sum(
        any(f.startswith("price_implausible:") for f in r.quality_flags) for r in rows
    )
    detail_blocked_count = sum(
        any(f.startswith("detail_blocked:") for f in r.quality_flags) for r in rows
    )
    merit_unconfirmed_count = sum(
        any(f.startswith("detail_missing_merit_evidence") or f.startswith("detail_unconfirmed_c6") for f in r.quality_flags)
        for r in rows
    )
    identity_mismatch_breakdown = Counter()
    for r in rows:
        for flag in r.quality_flags:
            if flag.startswith("identity_mismatch:"):
                for part in flag.split(":", 1)[1].split("+"):
                    if part:
                        identity_mismatch_breakdown[part] += 1
    identity_diagnostics = {
        "detail_attempted": sum(bool(r.verification_reason) for r in rows),
        "detail_verified": sum(r.verification_level == "detail" for r in rows),
        "identity_verified": sum(r.identity_verified for r in rows),
        "strict_live": sum(r.strict_live for r in rows),
        "detail_blocked": detail_blocked_count,
        "price_plausibility_flagged": price_plausibility_flags,
        "merit_unconfirmed": merit_unconfirmed_count,
        "mismatch_breakdown": dict(identity_mismatch_breakdown),
    }
    if price_plausibility_flags:
        improvement_signals.append("price_plausibility_anomalies_present")
    if detail_blocked_count:
        improvement_signals.append("detail_verification_blocked_pages_present")
    if identity_diagnostics["detail_verified"] >= 5 and identity_diagnostics["identity_verified"] == 0:
        improvement_signals.append("identity_verification_zero_yield")

    return {
        "listing_count": n,
        "candidate_count": sum(r.is_candidate for r in rows),
        "review_gate_count": sum(r.is_alert_candidate for r in rows),
        "identity_verified_count": sum(r.identity_verified for r in rows),
        "strict_live_count": sum(r.strict_live for r in rows),
        "risk_flagged_count": sum(bool(r.risk_flags) for r in rows),
        "market_statuses": dict(Counter(r.market_status for r in rows)),
        # Backward-compatible v0.7 name: this counts only historical outcomes directly observed
        # during the current marketplace scan, NOT the persistent historical D1 repertoire.
        "historical_anchor_observations": sum(r.market_status in {"SOLD_CONFIRMED", "SOLD_CLAIMED"} for r in rows),
        "current_scan_historical_anchor_observations": sum(r.market_status in {"SOLD_CONFIRMED", "SOLD_CLAIMED"} for r in rows),
        "fingerprint_groups": len({r.relisting_fingerprint for r in rows if r.relisting_fingerprint}),
        "completeness": completeness,
        "by_platform": dict(by_platform),
        "platform_quality": platform_quality,
        "coverage_diagnostics": coverage_diagnostics,
        "verification_reasons": dict(verification_reasons),
        "parser_strategies": dict(parser_strategies),
        "field_source_usage": field_source_usage,
        "stale_quality_flag_count": stale_quality_flag_count,
        "identity_diagnostics": identity_diagnostics,
        "top_reasons": reasons.most_common(15),
        "top_quality_flags": quality_flags.most_common(20),
        "risk_flags": dict(risk_flags),
        "coverage_status": dict(coverage_status),
        "coverage_families": dict(coverage_families),
        "requests_avoided": requests_avoided,
        "avoided_fetches_by_platform": dict(avoided_fetches_by_platform),
        "zero_hit_searches": zero_hit_searches[:40],
        "repeated_content_groups": repeated_content[:20],
        "repeated_http_probe_content_groups": repeated_http_content[:20],
        "fallback_reasons": dict(fallback_reasons),
        "blocked_signals": dict(blocked_signals),
        "http_probe_blocked_signals": dict(http_probe_blocked_signals),
        "error_count": len(errors),
        "improvement_signals": list(dict.fromkeys(improvement_signals)),
    }


def _version_major_minor(value: object) -> str:
    text = str(value or "").strip().lstrip("v")
    parts = text.split(".")
    return ".".join(parts[:2]) if len(parts) >= 2 else text


def _compact_source_health(rows: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict) or not row.get("platform"):
            continue
        out[str(row["platform"])] = {
            "status": row.get("status"),
            "consecutive_blocked": row.get("consecutive_blocked"),
            "consecutive_zero_yield": row.get("consecutive_zero_yield"),
            "cooldown_until": row.get("cooldown_until"),
            "last_reason": row.get("last_reason"),
        }
    return out


def _profile_source(source: dict, profile: str, fast_cfg: dict) -> dict | None:
    if profile == "full":
        return source
    scans = [
        {**spec, "max_pages": min(int(spec.get("max_pages", 1)), int(fast_cfg.get("max_pages_per_scan", 1)))}
        for spec in (source.get("scans") or [])
        if spec.get("fast", False)
    ]
    if not source.get("fast_enabled", True) or not scans:
        return None
    return {
        **source,
        "scans": scans,
        "deep_verify_limit": int(fast_cfg.get("deep_verify_limit_per_source", 2)),
        "deep_verify_hard_cap": int(fast_cfg.get("deep_verify_hard_cap_per_source", 3)),
        "calibration_verify_sample": int(fast_cfg.get("calibration_verify_sample_per_source", 0)),
        "control_verify_sample": int(fast_cfg.get("control_verify_sample_per_source", 0)),
        "merit_verify_sample": int(fast_cfg.get("merit_verify_sample_per_source", 1)),
        "plausibility_verify_sample": int(fast_cfg.get("plausibility_verify_sample_per_source", 0)),
    }


async def run(config_path: str, profile: str = "full"):
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
    control_verify_sample = int(collector_cfg.get("control_verify_sample_per_source", 1))
    merit_verify_sample = int(collector_cfg.get("merit_verify_sample_per_source", 4))
    plausibility_verify_sample = int(collector_cfg.get("plausibility_verify_sample_per_source", 2))
    auto_import_historical_seed = bool(collector_cfg.get("auto_import_historical_seed", True))
    fast_cfg = cfg.get("fast_profile", {}) or {}

    scan_id = str(uuid.uuid4())
    api = MarketApi(api_url, api_token)

    worker_health: dict = {}
    worker_health_error: str | None = None
    try:
        payload = await api.get_health()
        worker_health = payload if isinstance(payload, dict) else {}
    except Exception as exc:
        worker_health_error = f"{type(exc).__name__}: {exc}"

    # Fail closed on a stale Worker even outside GitHub Actions. A collector/Worker mismatch can
    # silently drop provenance or historical telemetry, which is worse than a short explicit failure.
    expected_worker = WORKER_API_VERSION
    if worker_health_error:
        raise SystemExit(f"Worker health check failed before scan: {worker_health_error}")
    worker_version = str(worker_health.get("version") or "unknown")
    if _version_major_minor(worker_version) != expected_worker:
        raise SystemExit(
            f"Worker version mismatch: collector expects {expected_worker}, Worker reports {worker_version}. "
            "Deploy the v1.0 Worker and migration 0006 before running the collector."
        )
    required_capabilities = {"source_health", "field_provenance", "historical_stats", "comparables", "multi_game", "warframe_founder", "smart_scan_profiles", "sparse_snapshots"}
    worker_capabilities = {str(x) for x in (worker_health.get("capabilities") or [])}
    missing_capabilities = sorted(required_capabilities - worker_capabilities)
    if missing_capabilities:
        raise SystemExit(f"Worker missing required capabilities: {missing_capabilities}")

    # v0.9 self-heals the historical seed gap. The import endpoint is idempotent, and we only
    # call it when the persistent tracker seed is missing/incomplete. A seed failure is recorded
    # as telemetry but never blocks a live-market scan.
    historical_seed_state: dict = {"enabled": auto_import_historical_seed and profile == "full", "attempted": False}
    if auto_import_historical_seed and profile == "full":
        seed_path = Path(__file__).resolve().parents[2] / "historical_seed_tracker_v26.json"
        try:
            seed_payload = json.loads(seed_path.read_text(encoding="utf-8"))
            expected_seed = len(seed_payload.get("records") or [])
            before = await api.get_historical_stats()
            before_seed = int((before or {}).get("tracker_seed_records", 0) or 0)
            historical_seed_state.update({"expected": expected_seed, "before": before_seed})
            if before_seed < expected_seed:
                historical_seed_state["attempted"] = True
                result = await api.import_historical(seed_payload)
                historical_seed_state["imported"] = int((result or {}).get("imported", 0) or 0)
                historical_seed_state["import_errors"] = list((result or {}).get("errors") or [])[:5]
                after = await api.get_historical_stats()
                historical_seed_state["after"] = int((after or {}).get("tracker_seed_records", 0) or 0)
                if historical_seed_state["after"] < expected_seed:
                    historical_seed_state["error"] = "seed_verification_incomplete"
            else:
                historical_seed_state["after"] = before_seed
        except Exception as exc:
            historical_seed_state["error"] = f"{type(exc).__name__}: {exc}"

    await api.start_scan(scan_id, __version__, notes=f"v1.1 VPS collector; profile={profile}; sparse-fast-observations")

    source_health_error: str | None = None
    try:
        source_health_payload = await api.get_source_health()
        source_health_rows = source_health_payload.get("sources", source_health_payload.get("rows", [])) if isinstance(source_health_payload, dict) else []
    except Exception as exc:
        # Source-health is an optimization only. A temporary API/read failure must never stop scanning.
        source_health_error = f"{type(exc).__name__}: {exc}"
        source_health_rows = []
    source_health = {str(r.get("platform")): r for r in source_health_rows if isinstance(r, dict) and r.get("platform")}

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

            profiled_source = _profile_source(source, profile, fast_cfg)
            if profiled_source is None:
                all_coverage.append(CoverageRow(
                    platform=source.get("name", "Unknown"),
                    query_family="fast_profile",
                    query_text="source or routes reserved for the full scan",
                    page_label="n/a",
                    path_key=f"{source.get('name', 'Unknown')}|fast_profile",
                    status="not_searched:fast_profile",
                    result_count=0,
                ))
                continue
            source = profiled_source

            platform_name = source.get("name", "Unknown")
            health = source_health.get(platform_name) or {}
            cooldown_until = health.get("cooldown_until")
            cooldown_active = False
            if cooldown_until:
                try:
                    cooldown_active = datetime.fromisoformat(str(cooldown_until).replace("Z", "+00:00")) > datetime.now(timezone.utc)
                except Exception:
                    cooldown_active = False
            if cooldown_active:
                all_coverage.append(CoverageRow(
                    platform=platform_name, query_family="source_health_cooldown",
                    query_text="source temporarily cooled down after repeated blocked/zero-yield probes",
                    page_label="n/a", path_key=f"{platform_name}|cooldown", status="skipped:cooldown",
                    result_count=0, circuit_breaker_reason=str(health.get("last_reason") or "persistent_source_health_cooldown"),
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
                control_verify_sample=int(source.get("control_verify_sample", control_verify_sample)),
                merit_verify_sample=int(source.get("merit_verify_sample", merit_verify_sample)),
                plausibility_verify_sample=int(source.get("plausibility_verify_sample", plausibility_verify_sample)),
                circuit_breaker_enabled=bool(source.get("circuit_breaker_enabled", True)),
                circuit_breaker_blocked_threshold=int(source.get("circuit_breaker_blocked_threshold", 1)),
                circuit_breaker_zero_yield_threshold=int(source.get("circuit_breaker_zero_yield_threshold", 4)),
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
        send_result = await api.send_listings(
            scan_id,
            rows,
            observation_policy="changes_only" if profile == "fast" else "full",
        )
        candidates = sum(1 for r in rows if r.is_candidate)
        metrics = _quality_metrics(rows, all_coverage, all_errors)
        metrics["changed_count"] = send_result.get("changed", 0)
        metrics["scan_profile"] = profile
        metrics["favorite_characters_configured"] = favorite_characters

        worker_version = str(worker_health.get("version") or "unknown")
        metrics["worker_api"] = {
            "expected_version": expected_worker,
            "reported_version": worker_version,
            "compatible": _version_major_minor(worker_version) == expected_worker,
            "health_error": worker_health_error,
            "source_health_error": source_health_error,
        }
        metrics["source_health_state"] = _compact_source_health(source_health_rows)
        metrics["historical_seed_state"] = historical_seed_state
        if historical_seed_state.get("error"):
            metrics["improvement_signals"].append("historical_seed_auto_import_failed")
        if worker_health_error:
            metrics["improvement_signals"].append("worker_health_unavailable")
        elif _version_major_minor(worker_version) != expected_worker:
            metrics["improvement_signals"].append("worker_version_mismatch")
        if source_health_error:
            metrics["improvement_signals"].append("source_health_api_unavailable")

        historical_stats: dict = {}
        historical_stats_error: str | None = None
        try:
            hist_payload = await api.get_historical_stats()
            historical_stats = hist_payload if isinstance(hist_payload, dict) else {}
        except Exception as exc:
            historical_stats_error = f"{type(exc).__name__}: {exc}"
        metrics["historical_pool"] = {
            "total": int(historical_stats.get("total", 0) or 0),
            "imported": int(historical_stats.get("imported", 0) or 0),
            "tracker_seed_records": int(historical_stats.get("tracker_seed_records", 0) or 0),
            "sold_confirmed": int((historical_stats.get("by_status") or {}).get("SOLD_CONFIRMED", 0) or 0),
            "sold_claimed": int((historical_stats.get("by_status") or {}).get("SOLD_CLAIMED", 0) or 0),
            "expired_removed": int((historical_stats.get("by_status") or {}).get("EXPIRED_REMOVED", 0) or 0),
            "risk_contaminated": int((historical_stats.get("by_status") or {}).get("RISK_CONTAMINATED", 0) or 0),
            "error": historical_stats_error,
        }
        if historical_stats_error:
            metrics["improvement_signals"].append("historical_stats_unavailable")
        elif metrics["historical_pool"]["total"] < 30:
            metrics["improvement_signals"].append("historical_comparable_pool_still_small")
        if not historical_stats_error and metrics["historical_pool"]["sold_confirmed"] < 8:
            metrics["improvement_signals"].append("confirmed_sold_pool_thin")

        # Passive market-intelligence pass: compare only the top current candidates against the
        # persistent historical repertoire. This does not change alert decisions yet; it gives us
        # measured evidence for future scoring/backtests.
        candidate_comparables: list[dict] = []
        comp_errors = 0
        ranked_candidates = sorted(
            [r for r in rows if r.is_candidate],
            key=lambda r: (r.collector_priority, -(r.price_value or 10**9)), reverse=True,
        )[:8]
        for row in ranked_candidates:
            try:
                comp = await api.get_comparables(row.url, limit=30)
                hs = comp.get("historical_summary", {}) if isinstance(comp, dict) else {}
                candidate_comparables.append({
                    "platform": row.platform, "url": row.url, "title": row.title[:220],
                    "price": row.price_value, "currency": row.currency,
                    "priority": row.collector_priority,
                    "historical_count": int(hs.get("count", 0) or 0),
                    "sold_confirmed_count": int(hs.get("sold_confirmed_count", 0) or 0),
                    "weighted_median": hs.get("weighted_median"),
                    "mad": hs.get("mad"),
                    "effective_weight": hs.get("effective_weight"),
                    "comparison_confidence": hs.get("comparison_confidence", "very_low"),
                    "price_vs_historical_median_pct": comp.get("target_vs_historical_weighted_median_pct"),
                    "raw_comparable_count": int(comp.get("raw_comparable_count", 0) or 0),
                    "dedup_historical_count": int(comp.get("dedup_historical_count", 0) or 0),
                })
            except Exception:
                comp_errors += 1
        metrics["candidate_comparables"] = candidate_comparables
        metrics["candidate_comparable_errors"] = comp_errors
        comparable_any = sum(c.get("historical_count", 0) >= 1 for c in candidate_comparables)
        comparable_ready = sum(
            c.get("historical_count", 0) >= 2 and c.get("comparison_confidence") in {"low", "medium", "high"}
            for c in candidate_comparables
        )
        # Backward-compatible field remains the *usable* coverage metric. v0.10 also reports any
        # historical coverage explicitly so "6 candidates have comps but coverage=0" is no longer ambiguous.
        metrics["candidate_comparable_coverage_pct"] = _pct(comparable_ready, len(ranked_candidates))
        metrics["candidate_comparable_any_coverage_pct"] = _pct(comparable_any, len(ranked_candidates))
        metrics["candidate_comparable_usable_coverage_pct"] = _pct(comparable_ready, len(ranked_candidates))
        metrics["candidate_comparable_very_low_confidence_count"] = sum(
            c.get("comparison_confidence") == "very_low" for c in candidate_comparables
        )
        if ranked_candidates and comparable_ready < max(1, len(ranked_candidates) // 2):
            metrics["improvement_signals"].append("candidate_historical_comparable_coverage_low")

        metrics["improvement_signals"] = list(dict.fromkeys(metrics["improvement_signals"]))
        severity = "warning" if metrics["improvement_signals"] or all_errors else "info"
        await api.send_system_event(
            component="collector",
            severity=severity,
            code="SCAN_QUALITY_V10",
            message=(
                f"scan {scan_id}: {len(rows)} listings, {candidates} candidates, "
                f"{metrics['identity_verified_count']} identity-verified, historical_pool={metrics['historical_pool']['total']}, "
                f"{len(all_errors)} errors"
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
            process_disappearance=profile == "full",
            create_quality_snapshot=profile == "full",
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
                code="SCAN_FAILED_V09",
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
                process_disappearance=profile == "full",
                create_quality_snapshot=profile == "full",
            )
        finally:
            raise


def cli():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(Path(__file__).resolve().parents[1] / "sources.yaml"))
    parser.add_argument("--profile", choices=["full", "fast"], default="full")
    args = parser.parse_args()
    asyncio.run(run(args.config, profile=args.profile))


if __name__ == "__main__":
    cli()
