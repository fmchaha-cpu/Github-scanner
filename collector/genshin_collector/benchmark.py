from __future__ import annotations

import argparse
import json
from pathlib import Path

from .detector import enrich_and_score
from .models import ListingObservation
from .normalize import infer_features, parse_ar, parse_availability, parse_price, parse_resources, parse_seller, parse_server, security_hint, sha256_text


def evaluate_case(case: dict) -> tuple[bool, list[str], dict]:
    text = str(case.get("text") or "")
    price, currency = parse_price(text)
    primos, intertwined, pulls = parse_resources(text)
    favorites = list(case.get("favorite_characters") or [])
    features = infer_features(text, favorites)
    seller = parse_seller(text)
    obs = ListingObservation(
        platform="benchmark", url=f"benchmark://{case.get('id','case')}", title=text[:500],
        external_id=str(case.get("id") or "case"), seller=seller, server=parse_server(text), ar=parse_ar(text),
        price_value=price, currency=currency, availability=parse_availability(text), raw_text=text,
        raw_hash=sha256_text(text), data_confidence=80.0, security_hint=security_hint(text, None, bool(seller)),
        primogems=primos, intertwined=intertwined, limited_pulls=pulls, **features,
    )
    enrich_and_score(obs)
    expect = case.get("expect") or {}
    errors: list[str] = []
    checks = {
        "server": obs.server,
        "limited_c6_count": obs.limited_c6_count,
        "candidate": obs.is_candidate,
        "alert_candidate": obs.is_alert_candidate,
    }
    for key, actual in checks.items():
        if key in expect and actual != expect[key]: errors.append(f"{key}: expected {expect[key]!r}, got {actual!r}")
    if expect.get("reason_contains") and expect["reason_contains"] not in (obs.detector_reason or ""):
        errors.append(f"reason missing {expect['reason_contains']!r}: {obs.detector_reason}")
    if expect.get("risk_contains") and expect["risk_contains"] not in obs.risk_flags:
        errors.append(f"risk flag missing {expect['risk_contains']!r}: {obs.risk_flags}")
    if "risk_flags" in expect and obs.risk_flags != expect["risk_flags"]:
        errors.append(f"risk_flags expected {expect['risk_flags']!r}, got {obs.risk_flags!r}")
    if expect.get("favorite_contains") and expect["favorite_contains"] not in obs.favorite_character_names:
        errors.append(f"favorite missing {expect['favorite_contains']!r}: {obs.favorite_character_names}")
    if expect.get("archetype_contains") and expect["archetype_contains"] not in obs.archetypes:
        errors.append(f"archetype missing {expect['archetype_contains']!r}: {obs.archetypes}")
    result = {
        "id": case.get("id"), "passed": not errors, "errors": errors, "priority": obs.collector_priority,
        "reason": obs.detector_reason, "archetypes": obs.archetypes, "risk_flags": obs.risk_flags,
        "limited_c6_count": obs.limited_c6_count, "limited_pulls": obs.limited_pulls,
    }
    return not errors, errors, result


def run_cases(path: Path) -> int:
    payload = json.loads(path.read_text(encoding="utf-8"))
    results = []
    for case in payload.get("cases", []):
        ok, _errors, result = evaluate_case(case)
        results.append(result)
    passed = sum(bool(r["passed"]) for r in results)
    print(json.dumps({"benchmark_version": "v0.9", "passed": passed, "total": len(results), "results": results}, indent=2))
    return 0 if passed == len(results) else 1


def cli() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default=str(Path(__file__).resolve().parents[1] / "benchmarks" / "known_cases.json"))
    args = parser.parse_args()
    raise SystemExit(run_cases(Path(args.cases)))


if __name__ == "__main__":
    cli()
