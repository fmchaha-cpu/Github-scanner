from genshin_collector.models import ListingObservation
from genshin_collector.market_history import (
    comparable_similarity, comparable_evidence_weight, normalize_market_status,
    relisting_fingerprint, robust_weighted_summary,
)


def listing(**kw):
    base = dict(
        platform="test", url="https://example.test/x", title="EU AR55 Furina C6",
        server="EU", ar=55, price_value=100, currency="EUR",
        limited_c6_count=1, limited_c6_characters=["Furina"],
        history_richness=40, discovery_headroom=50, resource_richness=30,
        legacy_collector_value=20, archetypes=["Value C6 / Collector"],
    )
    base.update(kw)
    return ListingObservation(**base)


def test_exact_detail_sold_becomes_confirmed_status_not_live():
    o = listing(availability="Sold/Closed", verification_level="detail", identity_verified=True)
    status, confidence, evidence = normalize_market_status(o)
    assert status == "SOLD_CONFIRMED"
    assert confidence >= .9
    assert "detail" in evidence


def test_card_sold_is_only_claimed():
    o = listing(availability="Sold/Closed", verification_level="card", identity_verified=False)
    assert normalize_market_status(o)[0] == "SOLD_CLAIMED"


def test_strict_live_status():
    o = listing(strict_live=True, availability="BUY NOW", identity_verified=True)
    assert normalize_market_status(o)[0] == "STRICT_LIVE"


def test_same_features_have_high_comparable_similarity():
    a = listing(url="https://example.test/a")
    b = listing(url="https://example.test/b", ar=56, price_value=120)
    assert comparable_similarity(a, b) > .9


def test_different_server_or_currency_blocks_comparable():
    a = listing(url="https://example.test/a")
    assert comparable_similarity(a, listing(url="x", server="NA")) == 0
    assert comparable_similarity(a, listing(url="y", currency="USD")) == 0


def test_confirmed_sale_outweighs_removed_listing():
    assert comparable_evidence_weight("SOLD_CONFIRMED", .9) > comparable_evidence_weight("EXPIRED_REMOVED", .9) * 3


def test_risk_contaminated_anchor_is_nearly_ignored():
    safe = comparable_evidence_weight("SOLD_CONFIRMED", .9, 0)
    risky = comparable_evidence_weight("SOLD_CONFIRMED", .9, 1)
    assert risky < safe * .2


def test_relisting_fingerprint_ignores_url_and_price():
    a = listing(url="https://one.test/a", price_value=100)
    b = listing(url="https://two.test/b", price_value=130)
    assert relisting_fingerprint(a) == relisting_fingerprint(b)


def test_weighted_summary_resists_weak_outlier():
    summary = robust_weighted_summary([(100, 1.0), (110, 1.0), (999, .05)])
    assert summary["weighted_median"] in {100.0, 110.0}
    assert summary["effective_weight"] == 2.05


def test_old_evidence_decays_but_keeps_floor():
    recent = comparable_evidence_weight("SOLD_CONFIRMED", .9, 0, age_days=0)
    old = comparable_evidence_weight("SOLD_CONFIRMED", .9, 0, age_days=1000)
    assert old < recent
    assert old >= recent * .24
