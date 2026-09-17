from __future__ import annotations

from .models import ListingObservation

DETECTOR_VERSION = "v2.6"


def _cap(x: float) -> float:
    return max(0.0, min(100.0, x))


def _intersects(a: list[str], b: list[str]) -> bool:
    bs = {x.lower() for x in b}
    return any(x.lower() in bs for x in a)


def _compute_extraction_quality(o: ListingObservation) -> float:
    score = 0.0
    score += 18 if o.price_value is not None else 0
    score += 18 if o.server else 0
    score += 14 if o.seller else 0
    score += 8 if o.ar is not None else 0
    score += 12 if o.availability else 0
    score += 10 if o.external_id else 0
    score += 10 if o.raw_hash else 0
    score += 10 if o.verification_level == "detail" else 0
    return _cap(score)


def enrich_and_score(o: ListingObservation) -> ListingObservation:
    # Candidate detector only. Market value/AVP and purchase decisions remain outside this heuristic layer.
    history = _cap(
        o.history_hits * 20 + o.legacy_hits * 10 + o.old_alt_hits * 12
        + (10 if o.ar is not None and o.ar >= 58 and o.manufactured_hits == 0 else 0)
    )
    discovery = _cap(o.discovery_hits * 26 + o.old_alt_hits * 8)

    resource = 0.0
    if o.limited_pulls is not None:
        resource += min(75.0, o.limited_pulls / 7)
    resource += o.resource_hits * 9
    resource = _cap(resource)

    organic = 50.0
    if o.history_hits >= 2:
        organic += 22
    if o.old_alt_hits >= 1:
        organic += 12
    if o.discovery_hits >= 1:
        organic += 8
    organic -= min(45, o.manufactured_hits * 18)
    organic -= min(30, o.risk_hits * 10)
    organic = _cap(organic)

    legacy = _cap(o.legacy_hits * 25)

    favorite = 0.0
    if o.favorite_character_names:
        favorite = 55.0
        if _intersects(o.favorite_character_names, o.limited_c6_characters):
            favorite = 94.0
        if _intersects(o.favorite_character_names, o.c6r1_characters):
            favorite = 100.0

    # Favorite fit contributes only when a configured favorite is actually present.
    if favorite > 0:
        experience_fit = _cap(
            history * .22 + discovery * .22 + resource * .16 + organic * .12 + legacy * .10 + favorite * .18
        )
    else:
        experience_fit = _cap(history * .27 + discovery * .27 + resource * .18 + organic * .14 + legacy * .14)

    o.history_richness = history
    o.discovery_headroom = discovery
    o.resource_richness = resource
    o.organic_account_feel = organic
    o.legacy_collector_value = legacy
    o.favorite_character_fit = favorite if o.favorite_character_names else None
    o.personal_experience_fit = experience_fit
    o.detector_version = DETECTOR_VERSION
    o.extraction_quality = _compute_extraction_quality(o)

    # Recompute state-derived flags from scratch so a successful detail check cannot
    # leave stale card-stage warnings such as `not_detail_verified` or `missing_seller`.
    derived_flags = {
        "missing_price", "missing_server", "missing_seller", "missing_availability",
        "risk_signal", "not_detail_verified",
    }
    flags = [f for f in dict.fromkeys(o.quality_flags) if f not in derived_flags]
    if o.price_value is None:
        flags.append("missing_price")
    if o.server is None:
        flags.append("missing_server")
    if not o.seller:
        flags.append("missing_seller")
    if not o.availability:
        flags.append("missing_availability")
    if o.risk_flags:
        flags.append("risk_signal")
    if o.verification_level != "detail":
        flags.append("not_detail_verified")
    o.quality_flags = list(dict.fromkeys(flags))

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
    if eu and price is not None and price <= 30 and o.ar is not None and o.ar >= 45:
        priority = max(priority, 62)
        reasons.append("cheap_mature_anomaly")

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

    if eu and favorite >= 90 and price is not None and price <= 150:
        priority = max(priority, 93)
        reasons.append("favorite_character_high_fit")
    elif eu and favorite >= 55 and price is not None and price <= 100:
        priority = max(priority, 72)
        reasons.append("favorite_character_present")

    if eu and experience_fit >= 65 and price is not None and price <= 150:
        priority = max(priority, 84)
        reasons.append("living_history_fit")
    if eu and history >= 60 and discovery >= 45 and resource >= 35 and price is not None and price <= 150:
        priority = max(priority, 92)
        reasons.append("dormant_veteran_combo")
    if eu and legacy >= 75 and price is not None and price <= 150:
        priority = max(priority, 88)
        reasons.append("legacy_rich")
    if eu and o.old_alt_hits >= 1 and discovery >= 35 and price is not None and price <= 150:
        priority = max(priority, 84)
        reasons.append("old_alt_discovery")

    if o.strict_live:
        priority += 3
    if o.price_value is None or o.server is None:
        priority -= 10
        reasons.append("missing_core_field")
    if o.risk_flags:
        priority -= 35
        reasons.append("risk_signal")
    if o.manufactured_hits and history < 40:
        priority -= min(12, o.manufactured_hits * 4)
        reasons.append("manufactured_signal")

    priority = _cap(priority)
    o.collector_priority = priority
    o.detector_reason = ",".join(reasons) if reasons else "baseline"
    o.is_candidate = priority >= 60

    # This flag means "send to human/ChatGPT crown-jewel review"; it is never an autonomous purchase alert.
    price_gate = price is not None and (price <= 150 or (price <= 200 and priority >= 96))
    o.is_alert_candidate = bool(
        priority >= 92
        and eu
        and price_gate
        and o.data_confidence is not None
        and o.data_confidence >= 95
        and o.security_hint is not None
        and o.security_hint >= 80
        and o.identity_verified
        and o.strict_live
        and not o.risk_flags
    )

    # Categories are parallel: a single account may satisfy several purchase motives.
    archetypes: list[str] = []
    if history >= 60 and discovery >= 35:
        archetypes.append("Dormant Veteran / Living History")
    if favorite >= 90:
        archetypes.append("Favorite Character Account")
    if o.multi_c6 or o.limited_c6_count:
        archetypes.append("Value C6 / Collector")
    if o.limited_pulls is not None and o.limited_pulls >= 400:
        archetypes.append("Resource Rich / Wish Heavy")
    if legacy >= 75:
        archetypes.append("Living Archive")
    if o.manufactured_hits > 0:
        archetypes.append("Manufactured Collector / Stock")
    if o.old_alt_hits >= 1 and discovery >= 25:
        archetypes.append("Old Alt / Abandoned Secondary")
    if o.ar is not None and o.ar <= 20:
        archetypes.append("Blank Slate / Reroll")
    if not archetypes:
        archetypes.append("General Roster")
    o.archetypes = archetypes

    # Backwards-compatible primary category; parallel categories remain in `archetypes`.
    primary_order = [
        "Favorite Character Account",
        "Dormant Veteran / Living History",
        "Living Archive",
        "Old Alt / Abandoned Secondary",
        "Value C6 / Collector",
        "Resource Rich / Wish Heavy",
        "Manufactured Collector / Stock",
        "Blank Slate / Reroll",
        "General Roster",
    ]
    o.archetype = next((x for x in primary_order if x in archetypes), archetypes[0])
    return o
