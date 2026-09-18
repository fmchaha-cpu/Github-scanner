from __future__ import annotations


def budget_fit(price: float | None, preferred_max: float) -> str:
    """A preference label, deliberately not an eligibility gate."""
    if price is None:
        return "unknown"
    return "preferred" if price <= preferred_max else "above_preferred"


def genshin_alert_tier(row: dict) -> str | None:
    priority = float(row.get("collector_priority") or 0)
    identity = bool(row.get("identity_verified"))
    strict_live = bool(row.get("strict_live"))
    favorite = float(row.get("favorite_character_fit") or 0)
    alert_candidate = bool(row.get("is_alert_candidate"))
    if identity and strict_live and (priority >= 72 or favorite >= 70):
        return "dream"
    if alert_candidate and priority >= 68:
        return "strong"
    if identity and priority >= 62:
        return "review"
    return None


def warframe_alert_tier(row: dict) -> str | None:
    if row.get("evidence_level") != "CLAIM_EVIDENCE" or not row.get("detail_verified"):
        return None
    score = float(row.get("evidence_score") or 0)
    items = row.get("prime_items") or []
    if score >= 88 or len(items) >= 3:
        return "dream"
    if score >= 72 and items:
        return "strong"
    return "review"
