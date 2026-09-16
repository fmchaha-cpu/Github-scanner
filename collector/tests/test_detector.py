from genshin_collector.models import ListingObservation
from genshin_collector.detector import enrich_and_score


def test_cheap_eu_c6_is_candidate():
    o = ListingObservation(
        platform="test", url="https://example.test/1", title="EU AR55 Furina C6", server="EU", ar=55,
        price_value=40, currency="USD", limited_c6_count=1, data_confidence=90,
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
    assert r.archetype == "Dormant Veteran"
