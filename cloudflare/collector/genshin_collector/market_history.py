from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from .models import ListingObservation

HISTORICAL_STATUS_WEIGHTS = {
    "SOLD_CONFIRMED": 1.00,
    "SOLD_CLAIMED": 0.65,
    "EXPIRED_REMOVED": 0.25,
    "OUTCOME_UNKNOWN": 0.15,
    "RISK_CONTAMINATED": 0.05,
}

ACTIVE_STATUSES = {"STRICT_LIVE", "ACTIVE_UNCONFIRMED"}
HISTORICAL_STATUSES = set(HISTORICAL_STATUS_WEIGHTS)


def normalize_market_status(o: ListingObservation) -> tuple[str, float, str]:
    """Conservatively label an observation.

    SOLD_CONFIRMED means the *exact public listing page* explicitly presents the listing
    as ended/sold and identity evidence is strong. It does NOT prove the transaction
    settled at the displayed asking price.
    """
    availability = (o.availability or "").lower()
    sold = any(x in availability for x in ("sold", "closed", "unavailable", "out of stock", "ended"))
    if o.risk_flags and sold:
        return "RISK_CONTAMINATED", 0.25, "sold_or_closed_with_security_risk"
    if sold and o.verification_level == "detail" and o.identity_verified:
        return "SOLD_CONFIRMED", 0.92, "exact_detail_page_sold_or_closed"
    if sold:
        return "SOLD_CLAIMED", 0.65, "listing_text_claims_sold_or_closed"
    if o.strict_live:
        return "STRICT_LIVE", 0.97, "identity_verified_live_control"
    return "ACTIVE_UNCONFIRMED", min(0.85, (o.data_confidence or 60) / 100), "observed_in_market_scan"


def _bucket(value: float | int | None, size: int) -> str:
    if value is None:
        return "?"
    return str(int(float(value) // size) * size)


def relisting_fingerprint(o: ListingObservation) -> str:
    """Stable-ish coarse fingerprint used only to suggest duplicates/relistings.

    It intentionally avoids seller/title so a cross-platform relisting can still match.
    It is never used to auto-merge records.
    """
    payload = {
        "server": o.server or "?",
        "ar": _bucket(o.ar, 3),
        "c6": sorted(x.lower() for x in o.limited_c6_characters),
        "c6r1": sorted(x.lower() for x in o.c6r1_characters),
        "characters": sorted(x.lower() for x in o.character_tags)[:20],
        "pulls": _bucket(o.limited_pulls, 100),
        "legacy": min(o.legacy_hits, 4),
        "history": min(o.history_hits, 4),
        "discovery": min(o.discovery_hits, 4),
        "resources": min(o.resource_hits, 4),
        "old_alt": min(o.old_alt_hits, 3),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _jaccard(a: list[str] | None, b: list[str] | None) -> float:
    sa = {x.lower() for x in (a or [])}
    sb = {x.lower() for x in (b or [])}
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _num_similarity(a: float | int | None, b: float | int | None, scale: float) -> float:
    if a is None and b is None:
        return 0.65  # unknown-to-unknown should not be treated as perfect evidence
    if a is None or b is None:
        return 0.35
    return max(0.0, 1.0 - abs(float(a) - float(b)) / scale)


def comparable_similarity(a: ListingObservation | dict[str, Any], b: ListingObservation | dict[str, Any]) -> float:
    """0..1 similarity for price-comparable selection.

    Currency is intentionally *not* converted here. Callers must only compare rows in the
    same currency unless they add an explicit dated FX layer later.
    """
    if isinstance(a, ListingObservation):
        a = a.model_dump()
    if isinstance(b, ListingObservation):
        b = b.model_dump()

    if a.get("server") and b.get("server") and a.get("server") != b.get("server"):
        return 0.0
    if a.get("currency") and b.get("currency") and a.get("currency") != b.get("currency"):
        return 0.0

    parts: list[tuple[float, float]] = [
        (_num_similarity(a.get("ar"), b.get("ar"), 20), 0.08),
        (_num_similarity(a.get("limited_c6_count", 0), b.get("limited_c6_count", 0), 3), 0.18),
        (_num_similarity(a.get("c6r1_count", 0), b.get("c6r1_count", 0), 2), 0.10),
        (_jaccard(a.get("limited_c6_characters"), b.get("limited_c6_characters")), 0.18),
        (_jaccard(a.get("c6r1_characters"), b.get("c6r1_characters")), 0.07),
        (_jaccard(a.get("character_tags"), b.get("character_tags")), 0.11),
        (_num_similarity(a.get("limited_pulls"), b.get("limited_pulls"), 800), 0.08),
        (_num_similarity(a.get("history_richness"), b.get("history_richness"), 100), 0.07),
        (_num_similarity(a.get("discovery_headroom"), b.get("discovery_headroom"), 100), 0.07),
        (_num_similarity(a.get("resource_richness"), b.get("resource_richness"), 100), 0.06),
        (_num_similarity(a.get("legacy_collector_value"), b.get("legacy_collector_value"), 100), 0.04),
        (_jaccard(a.get("archetypes"), b.get("archetypes")), 0.04),
    ]
    return max(0.0, min(1.0, sum(score * weight for score, weight in parts) / sum(w for _, w in parts)))


def recency_weight(age_days: float | None) -> float:
    if age_days is None:
        return 0.65
    age_days = max(0.0, float(age_days))
    return max(0.25, 0.5 ** (age_days / 270.0))


def comparable_evidence_weight(status: str, similarity: float, risk_hits: int = 0, age_days: float | None = 0) -> float:
    base = HISTORICAL_STATUS_WEIGHTS.get(status, 0.0)
    if risk_hits:
        base *= 0.15
    # Keep mediocre comps and very old market phases from dominating.
    return base * max(0.0, min(1.0, similarity)) ** 2 * recency_weight(age_days)


def weighted_median(values: list[tuple[float, float]]) -> float | None:
    rows = sorted((float(v), float(w)) for v, w in values if w > 0)
    if not rows:
        return None
    total = sum(w for _, w in rows)
    target = total / 2
    acc = 0.0
    for value, weight in rows:
        acc += weight
        if acc >= target:
            return value
    return rows[-1][0]


def robust_weighted_summary(values: list[tuple[float, float]]) -> dict[str, float | int | None]:
    """Weighted median plus a robust weighted spread estimate.

    We avoid pretending a tiny historical sample has precise statistics.
    """
    med = weighted_median(values)
    if med is None:
        return {"count": 0, "effective_weight": 0.0, "weighted_median": None, "mad": None}
    deviations = [(abs(v - med), w) for v, w in values if w > 0]
    mad = weighted_median(deviations)
    return {
        "count": sum(1 for _, w in values if w > 0),
        "effective_weight": round(sum(w for _, w in values if w > 0), 3),
        "weighted_median": round(med, 2),
        "mad": round(mad, 2) if mad is not None else None,
    }
