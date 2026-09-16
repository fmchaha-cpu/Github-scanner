from __future__ import annotations

from dataclasses import dataclass
from .models import ListingObservation

DETECTOR_VERSION = "v1.1"


def _cap(x: float) -> float:
    return max(0.0, min(100.0, x))


def enrich_and_score(o: ListingObservation) -> ListingObservation:
    # Explicit, conservative heuristics. This is a candidate detector, not the final ChatGPT judgment.
    history = _cap(o.history_hits * 22 + o.legacy_hits * 12)
    discovery = _cap(o.discovery_hits * 28)
    resource = 0.0
    if o.limited_pulls is not None:
        resource += min(70.0, o.limited_pulls / 8)
    resource += o.resource_hits * 10
    resource = _cap(resource)

    organic = 50.0
    if o.history_hits >= 2:
        organic += 20
    if o.discovery_hits >= 1:
        organic += 10
    raw = (o.raw_text or "").lower()
    if any(x in raw for x in ["reroll", "random gender", "safe and stable, send now", "stock account", "fresh account"]):
        organic -= 25
    organic = _cap(organic)

    legacy = _cap(o.legacy_hits * 25)
    experience_fit = _cap(history * .27 + discovery * .27 + resource * .18 + organic * .14 + legacy * .14)

    o.history_richness = history
    o.discovery_headroom = discovery
    o.resource_richness = resource
    o.organic_account_feel = organic
    o.legacy_collector_value = legacy
    o.personal_experience_fit = experience_fit
    o.detector_version = DETECTOR_VERSION

    reasons: list[str] = []
    priority = 0.0
    eu = o.server == "EU"
    price = o.price_value

    if eu:
        priority += 10
    elif o.server:
        priority -= 8

    if eu and price is not None and price <= 150:
        priority += 12
        reasons.append("EU<=150")

    if eu and o.limited_c6_count >= 1 and price is not None and price <= 60:
        priority = max(priority, 86)
        reasons.append("cheap_EU_C6")
    elif eu and o.limited_c6_count >= 1 and price is not None and price <= 100:
        priority = max(priority, 74)
        reasons.append("value_EU_C6")

    if eu and o.multi_c6 and price is not None and price <= 150:
        priority = max(priority, 94)
        reasons.append("EU_multi_C6<=150")

    if eu and o.c6r1_count >= 1 and price is not None and price <= 100:
        priority = max(priority, 90)
        reasons.append("EU_C6R1<=100")

    if eu and o.limited_pulls is not None:
        if o.limited_pulls >= 800 and (price is None or price <= 200):
            priority = max(priority, 93)
            reasons.append("EU_800plus_pulls")
        elif o.limited_pulls >= 500 and (price is None or price <= 150):
            priority = max(priority, 82)
            reasons.append("EU_500plus_pulls")

    if eu and experience_fit >= 65 and price is not None and price <= 150:
        priority = max(priority, 84)
        reasons.append("living_history_fit")
    if eu and history >= 60 and discovery >= 45 and resource >= 35 and price is not None and price <= 150:
        priority = max(priority, 92)
        reasons.append("dormant_veteran_combo")
    if eu and legacy >= 75 and price is not None and price <= 150:
        priority = max(priority, 88)
        reasons.append("legacy_rich")

    # Availability and data completeness help decide how urgently to inspect; they do NOT establish strict-live.
    if o.availability and any(x in o.availability.lower() for x in ["buy now", "in stock", "available"]):
        priority += 3
    if o.price_value is None or o.server is None:
        priority -= 10
        reasons.append("missing_core_field")

    priority = _cap(priority)
    o.collector_priority = priority
    o.detector_reason = ",".join(reasons) if reasons else "baseline"
    o.is_candidate = priority >= 60
    # Deliberately conservative: external collector never directly declares a purchase alert.
    o.is_alert_candidate = priority >= 92 and eu and o.data_confidence is not None and o.data_confidence >= 90

    if history >= 60 and discovery >= 35:
        o.archetype = "Dormant Veteran"
    elif legacy >= 75:
        o.archetype = "Living Archive"
    elif o.multi_c6 or o.limited_c6_count:
        o.archetype = "Value C6 / Collector"
    elif o.limited_pulls is not None and o.limited_pulls >= 400:
        o.archetype = "Resource Rich / Wish Heavy"
    elif organic <= 35:
        o.archetype = "Manufactured Collector / Stock"
    else:
        o.archetype = "General Roster"

    return o
