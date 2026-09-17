import json
from pathlib import Path

from genshin_collector.adapters.generic import GenericMarketplaceAdapter


def zeus_adapter():
    return GenericMarketplaceAdapter(
        name="ZeusX",
        scans=[],
        detail_patterns=[r"/game/genshin-impact/13/accounts/"],
        favorite_characters=["Venti"],
    )


def test_hidden_captcha_script_does_not_mark_real_marketplace_page_blocked():
    a = zeus_adapter()
    html = """
    <html><head><title>Genshin accounts</title>
    <script>window.captchaProvider = 'loaded'; const challenge = false;</script></head>
    <body><div class='card'>
      <a href='/game/genshin-impact/13/accounts/eu-ar55-venti-12345'>EU AR55 Venti C6</a>
      <span>$49.99</span>
    </div></body></html>
    """
    assert a._quick_block_signals(html) == []
    probe = a._probe_html("https://zeusx.com/game/genshin-impact/13/accounts", html, "browser", 200, 10)
    assert probe.detail_link_count == 1
    assert probe.blocked_signals == []


def test_visible_human_check_is_still_detected():
    a = zeus_adapter()
    html = "<html><head><title>Just a moment...</title></head><body>Verify you are human</body></html>"
    signals = a._quick_block_signals(html)
    assert "human_check" in signals or "challenge" in signals


def test_zeusx_card_seller_can_come_from_profile_image_alt():
    a = zeus_adapter()
    html = """
    <section><div class='card'>
      <a href='/game/genshin-impact/13/accounts/eu-ar55-venti-c6-12345'>EU|AR55|Venti C6</a>
      <span>$49.99</span>
      <a href='/seller/beads-shop-709483'><img src='avatar.png' alt='Beads Shop'></a>
    </div></section>
    """
    rows = a._parse_cards("https://zeusx.com/game/genshin-impact/13/accounts", html)
    assert len(rows) == 1
    assert rows[0].seller == "Beads Shop"
    assert rows[0].field_sources["seller"] == "profile_link"


def test_detail_sidebar_seller_and_buy_control_produce_strong_identity():
    a = zeus_adapter()
    card_html = """
    <div class='card'>
      <a href='/game/genshin-impact/13/accounts/eu-ar55-venti-c6-12345'>EU|AR55|Venti C6</a>
      <span>$49.99</span>
      <a href='/seller/beads-shop-709483'>Beads Shop</a>
    </div>
    """
    row = a._parse_cards("https://zeusx.com/game/genshin-impact/13/accounts", card_html)[0]
    detail_html = """
    <html><body>
      <main>
        <h1>EU AR55 Venti C6 account</h1>
        <div>Price $49.99. Server: EU. Venti C6. Full access.</div>
        <button>Buy Now</button>
      </main>
      <aside><a href='/seller/beads-shop-709483'><img alt='Beads Shop'></a></aside>
    </body></html>
    """
    verified = a._parse_detail(row, detail_html)
    assert verified.seller == "Beads Shop"
    assert verified.availability == "BUY NOW"
    assert verified.field_sources["seller"] == "detail_profile_link"
    assert verified.field_sources["availability"] == "detail_control"
    assert verified.identity_verified
    assert verified.strict_live


def test_historical_seed_has_expected_evidence_mix():
    seed_path = Path(__file__).resolve().parents[2] / "historical_seed_tracker_v26.json"
    payload = json.loads(seed_path.read_text(encoding="utf-8"))
    records = payload["records"]
    assert len(records) == 17
    confirmed = [r for r in records if r["market_status"] == "SOLD_CONFIRMED"]
    assert len(confirmed) >= 8
    assert all(r["currency"] == "USD" for r in records)


def test_related_listing_sold_control_does_not_override_current_buy_button():
    a = zeus_adapter()
    html = """
    <html><body>
      <main><button>Buy Now</button></main>
      <section class='related'>
        <a href='/game/genshin-impact/13/accounts/other-listing-999'><span>Sold</span></a>
      </section>
    </body></html>
    """
    soup = __import__('bs4').BeautifulSoup(html, 'html.parser')
    availability, source = a._availability_from_controls(
        soup, 'https://zeusx.com/game/genshin-impact/13/accounts/current-listing-123'
    )
    assert availability == 'BUY NOW'
    assert source == 'detail_control'


def test_related_listing_buy_control_is_ignored_for_current_sold_listing():
    a = zeus_adapter()
    html = """
    <html><body>
      <main><button disabled>Sold Out</button></main>
      <section class='related'>
        <a href='/game/genshin-impact/13/accounts/other-listing-999'>Buy Now</a>
      </section>
    </body></html>
    """
    soup = __import__('bs4').BeautifulSoup(html, 'html.parser')
    availability, source = a._availability_from_controls(
        soup, 'https://zeusx.com/game/genshin-impact/13/accounts/current-listing-123'
    )
    assert availability == 'Sold/Closed'
    assert source == 'detail_control'
