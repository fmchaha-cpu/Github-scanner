from genshin_collector.models import ListingObservation
from genshin_collector.detector import enrich_and_score


def test_cheap_eu_c6_is_candidate():
    o = ListingObservation(
        platform="test", url="https://example.test/1", title="EU AR55 Furina C6",
        server="EU", ar=55, price_value=40, currency="USD",
        limited_c6_count=1, limited_c6_characters=["Furina"], data_confidence=90,
    )
    r = enrich_and_score(o)
    assert r.is_candidate
    assert r.collector_priority >= 86


def test_dormant_veteran_can_surface_without_c6():
    o = ListingObservation(
        platform="test", url="https://example.test/2", title="old main", server="EU", ar=58,
        price_value=90, currency="EUR", history_hits=3, discovery_hits=2, legacy_hits=2,
        resource_hits=2, limited_pulls=120, data_confidence=90,
    )
    r = enrich_and_score(o)
    assert r.is_candidate
    assert r.archetype == "Dormant Veteran / Living History"


def test_favorite_c6_gets_high_fit():
    o = ListingObservation(
        platform="test", url="https://example.test/3", title="Venti C6", server="EU",
        price_value=100, currency="EUR", limited_c6_count=1,
        limited_c6_characters=["Venti"], favorite_character_names=["Venti"],
    )
    r = enrich_and_score(o)
    assert r.favorite_character_fit >= 90
    assert r.archetype == "Favorite Character Account"


def test_risk_flags_block_review_gate():
    o = ListingObservation(
        platform="test", url="https://example.test/4", title="Furina C6", server="EU",
        price_value=40, currency="EUR", seller="seller1", availability="BUY NOW",
        external_id="123", limited_c6_count=1, limited_c6_characters=["Furina"],
        data_confidence=97, security_hint=95, identity_verified=True, strict_live=True,
        risk_flags=["negative_primos"], risk_hits=1, verification_level="detail",
    )
    r = enrich_and_score(o)
    assert not r.is_alert_candidate
    assert "risk_signal" in r.detector_reason


def test_review_gate_requires_identity_and_security():
    base = dict(
        platform="test", url="https://example.test/5", title="Furina C6", server="EU",
        price_value=40, currency="EUR", seller="seller1", availability="BUY NOW",
        external_id="123", limited_c6_count=1, c6r1_count=1,
        limited_c6_characters=["Furina"], c6r1_characters=["Furina"],
        data_confidence=97, security_hint=90, verification_level="detail",
    )
    r = enrich_and_score(ListingObservation(**base, identity_verified=False, strict_live=False))
    assert not r.is_alert_candidate
    r2 = enrich_and_score(ListingObservation(**base, identity_verified=True, strict_live=True))
    assert r2.is_alert_candidate


def test_manufactured_stock_does_not_look_organic():
    o = ListingObservation(
        platform="test", url="https://example.test/6", title="stock",
        server="EU", price_value=20, manufactured_hits=3
    )
    r = enrich_and_score(o)
    assert r.organic_account_feel < 35
    assert r.archetype == "Manufactured Collector / Stock"
