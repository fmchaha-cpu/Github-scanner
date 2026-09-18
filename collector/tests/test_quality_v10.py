import asyncio

from genshin_collector.adapters.generic import FetchPage, GenericMarketplaceAdapter
from genshin_collector.detector import DETECTOR_VERSION, enrich_and_score
from genshin_collector.main import WORKER_API_VERSION, _quality_metrics
from genshin_collector.models import ListingObservation


def epic_adapter(**kwargs):
    opts = dict(
        name="EpicNPC",
        scans=[],
        detail_patterns=[r"/threads/"],
        favorite_characters=["Venti", "Arlecchino"],
    )
    opts.update(kwargs)
    return GenericMarketplaceAdapter(**opts)


def test_v10_versions_and_worker_api_are_decoupled():
    assert DETECTOR_VERSION == "v2.7"
    assert WORKER_API_VERSION == "0.9"


def test_generic_domain_h1_does_not_destroy_rich_card_title_and_identity_can_verify_without_merit():
    a = epic_adapter()
    card = """
    <div class='structItem'>
      <a href='/threads/eu-venti-c6.12345/'>AR55 Venti C6 account $90</a>
      <a href='/members/flautiz.567/'>Flautiz</a>
      <span>$90.00</span>
    </div>
    """
    row = a._parse_cards("https://www.epicnpc.com/forums/genshin-impact-eu-accounts.2156/", card)[0]
    assert row.field_sources["server"] == "query_context"
    detail = """
    <html><body>
      <h1>www.epicnpc.com</h1>
      <main><div>Price: $90.00</div><button>Buy Now</button></main>
      <aside><a href='/members/flautiz.567/'>Flautiz</a></aside>
    </body></html>
    """
    verified = a._parse_detail(row, detail)
    assert "Venti C6" in verified.title
    assert verified.identity_verified
    assert verified.strict_live
    assert "detail_unconfirmed_c6" in verified.quality_flags
    assert "detail_missing_merit_evidence" in verified.quality_flags
    assert not verified.is_alert_candidate


def test_seller_identity_normalization_is_exact_not_fuzzy():
    a = epic_adapter()
    assert a._same_seller("Beads-Shop", "Beads Shop")
    assert a._same_seller("Seller: Alpha_123", "alpha123")
    assert not a._same_seller("alpha123", "alpha124")


def test_implausible_ultra_low_mature_price_is_held_from_candidate_alerting():
    a = epic_adapter()
    html = """
    <div class='structItem'>
      <a href='/threads/eu-whale-ar60-for-sale.3233084/'>EU Whale AR60 for sale $1.10</a>
      <a href='/members/example.10/'>Example</a>
      <span>$1.10</span>
    </div>
    """
    row = a._parse_cards("https://www.epicnpc.com/forums/genshin-impact-eu-accounts.2156/", html)[0]
    assert row.price_value == 1.10
    assert "price_implausible:ultra_low_mature" in row.quality_flags
    assert "price_plausibility_hold" in (row.detector_reason or "")
    assert not row.is_alert_candidate


def test_blocked_detail_page_preserves_card_observation_instead_of_parsing_challenge():
    a = epic_adapter(deep_verify_limit=1, deep_verify_hard_cap=1)
    row = ListingObservation(
        platform="EpicNPC",
        external_id="123",
        url="https://www.epicnpc.com/threads/example.123/",
        title="EU AR55 Venti C6 $90",
        server="EU",
        price_value=90,
        currency="USD",
        seller="Flautiz",
        limited_c6_count=1,
        limited_c6_characters=["Venti"],
        character_tags=["Venti"],
        is_candidate=True,
        collector_priority=90,
        field_sources={"server": "query_context", "seller": "profile_link"},
    )

    async def fake_fetch(*_args, **_kwargs):
        return FetchPage(
            html="<html><h1>www.epicnpc.com</h1><p>Verify you are human</p></html>",
            mode="browser", http_status=403, elapsed_ms=10, html_bytes=50,
            text_chars=30, anchor_count=0, detail_link_count=0,
            page_title="Just a moment...", content_hash="x", blocked_signals=["challenge"],
            sample_detail_urls=[], final_url=row.url,
        )

    a._fetch = fake_fetch  # type: ignore[method-assign]
    result = asyncio.run(a._deep_verify([row]))[0]
    assert result.verification_level == "card"
    assert not result.identity_verified
    assert any(f.startswith("detail_blocked:challenge") for f in result.quality_flags)
    assert "Venti C6" in result.title


def test_quality_metrics_expose_identity_and_plausibility_diagnostics():
    row = enrich_and_score(ListingObservation(
        platform="EpicNPC", url="https://x/threads/a.1/", title="EU AR60 whale $1.10",
        external_id="1", server="EU", price_value=1.10, currency="USD", seller="s",
        verification_reason="plausibility_probe",
        quality_flags=["price_implausible:ultra_low_mature", "detail_blocked:challenge"],
    ))
    metrics = _quality_metrics([row], [], [])
    assert metrics["identity_diagnostics"]["price_plausibility_flagged"] == 1
    assert metrics["identity_diagnostics"]["detail_blocked"] == 1


def test_unconfirmed_merit_blocks_alert_even_when_identity_and_live_are_strong():
    row = ListingObservation(
        platform="PlayerAuctions", url="https://x/item", title="EU AR55 Venti C6",
        external_id="999", server="EU", ar=55, price_value=99, currency="USD",
        seller="seller", availability="BUY NOW", data_confidence=97, security_hint=95,
        identity_verified=True, strict_live=True, limited_c6_count=1,
        limited_c6_characters=["Venti"], character_tags=["Venti"],
        favorite_character_names=["Venti"], quality_flags=["detail_unconfirmed_c6"],
        verification_level="detail",
    )
    scored = enrich_and_score(row)
    assert scored.collector_priority >= 92
    assert not scored.is_alert_candidate
