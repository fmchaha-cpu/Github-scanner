import json
from pathlib import Path

import pytest

from genshin_collector.benchmark import evaluate_case
from genshin_collector.detector import enrich_and_score, DETECTOR_VERSION
from genshin_collector.models import CoverageRow, ListingObservation


CASES = json.loads((Path(__file__).resolve().parents[1] / "benchmarks" / "known_cases.json").read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_benchmark_known_cases(case):
    ok, errors, _result = evaluate_case(case)
    assert ok, errors


def test_detail_verification_clears_stale_not_detail_verified_flag():
    row = ListingObservation(
        platform="test", url="https://example.test/1", title="EU AR55 Furina C6 40 USD",
        price_value=40, currency="USD", server="EU", seller="seller", availability="BUY NOW",
        external_id="1", verification_level="detail", quality_flags=["not_detail_verified", "missing_seller"],
    )
    out = enrich_and_score(row)
    assert "not_detail_verified" not in out.quality_flags
    assert "missing_seller" not in out.quality_flags


def test_detector_version_is_v26():
    assert DETECTOR_VERSION == "v2.6"


def test_v07_coverage_diagnostics_fields_roundtrip():
    row = CoverageRow(
        platform="PlayerAuctions", query_family="eu_all", status="blocked:browser",
        http_probe_http_status=403, safe_headers={"server": "cloudflare"},
        http_probe_safe_headers={"content-type": "text/html"}, browser_early_blocked=True,
        circuit_breaker_triggered=True, circuit_breaker_reason="challenge_zero_yield",
    )
    dumped = row.model_dump()
    assert dumped["http_probe_http_status"] == 403
    assert dumped["browser_early_blocked"] is True
    assert dumped["circuit_breaker_triggered"] is True
