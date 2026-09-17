from genshin_collector.adapters.generic import GenericMarketplaceAdapter


def adapter():
    return GenericMarketplaceAdapter(
        name="PlayerAuctions",
        scans=[],
        detail_patterns=[r"/genshin-impact-account/\d+a"],
        favorite_characters=["Venti"],
    )


def test_card_parse_and_detail_identity_success():
    a = adapter()
    card_html = """
    <div class="card">
      <a href="/genshin-impact-account/123456a-test/">EU AR55 Venti C6R1</a>
      <span>$99</span><span>Seller: alpha123</span><span>BUY NOW</span>
    </div>
    """
    rows = a._parse_cards("https://www.playerauctions.com/genshin-impact-account/eu/", card_html)
    assert len(rows) == 1
    row = rows[0]
    assert row.external_id == "123456"
    assert row.server == "EU"
    assert row.limited_c6_count == 1
    assert row.favorite_character_names == ["Venti"]

    detail_html = """
    <html><head>
    <script type="application/ld+json">
    {"@type":"Product","name":"EU AR55 Venti C6R1","offers":{"price":"99","priceCurrency":"USD","availability":"https://schema.org/InStock","seller":{"@type":"Organization","name":"alpha123"}}}
    </script>
    </head><body><h1>EU AR55 Venti C6R1</h1><div>Seller: alpha123 BUY NOW 30 days protection original owner full access</div></body></html>
    """
    verified = a._parse_detail(row, detail_html)
    assert verified.identity_verified
    assert verified.strict_live
    assert verified.data_confidence >= 95
    assert verified.is_alert_candidate


def test_detail_price_mismatch_blocks_identity():
    a = adapter()
    card_html = """
    <div><a href="/genshin-impact-account/123456a-test/">EU AR55 Venti C6R1</a>
    <span>$99</span><span>Seller: alpha123</span><span>BUY NOW</span></div>
    """
    row = a._parse_cards("https://www.playerauctions.com/genshin-impact-account/eu/", card_html)[0]
    detail_html = """
    <html><body><h1>EU AR55 Venti C6R1</h1>
    <div>$999 Seller: alpha123 BUY NOW original owner</div></body></html>
    """
    verified = a._parse_detail(row, detail_html)
    assert not verified.identity_verified
    assert not verified.strict_live
    assert verified.data_confidence <= 45
    assert any(x.startswith("identity_mismatch") for x in verified.quality_flags)


def test_rotation_skip_logic():
    a = GenericMarketplaceAdapter(
        name="test", scans=[], detail_patterns=[r"/x/"], rotation_value=5
    )
    assert a._rotation_active({"rotation": {"mod": 4, "slot": 1}})
    assert not a._rotation_active({"rotation": {"mod": 4, "slot": 2}})


def test_card_live_does_not_make_strict_live_without_detail_live_evidence():
    a = adapter()
    card_html = """
    <div><a href="/genshin-impact-account/123457a-test/">EU AR55 Venti C6R1</a>
    <span>$99</span><span>Seller: alpha123</span><span>BUY NOW</span></div>
    """
    row = a._parse_cards("https://www.playerauctions.com/genshin-impact-account/eu/", card_html)[0]
    detail_html = """
    <html><body><h1>EU AR55 Venti C6R1</h1>
    <div>$99 Seller: alpha123 30 days protection original owner</div></body></html>
    """
    verified = a._parse_detail(row, detail_html)
    assert verified.identity_verified
    assert not verified.strict_live


def test_unrelated_europe_text_is_not_detail_server_evidence():
    a = adapter()
    card_html = """
    <div><a href="/genshin-impact-account/123458a-test/">EU AR55 Venti C6R1</a>
    <span>$99</span><span>Seller: alpha123</span><span>BUY NOW</span></div>
    """
    row = a._parse_cards("https://www.playerauctions.com/genshin-impact-account/eu/", card_html)[0]
    detail_html = """
    <html><body><h1>Venti C6R1 account</h1>
    <div>$99 Seller: alpha123 BUY NOW 30 days protection</div>
    <footer>Company offices in Europe</footer></body></html>
    """
    verified = a._parse_detail(row, detail_html)
    assert not verified.identity_verified
    assert not verified.strict_live
    assert "detail_weak_server_evidence" in verified.quality_flags


def test_sold_detail_gets_historical_status_and_fingerprint():
    a = adapter()
    card_html = """
    <div><a href="/genshin-impact-account/123459a-test/">EU AR55 Venti C6R1</a>
    <span>$99</span><span>Seller: alpha123</span></div>
    """
    row = a._parse_cards("https://www.playerauctions.com/genshin-impact-account/eu/", card_html)[0]
    detail_html = """
    <html><head><script type="application/ld+json">
    {"@type":"Product","name":"EU AR55 Venti C6R1","offers":{"price":"99","priceCurrency":"USD","availability":"https://schema.org/OutOfStock","seller":{"@type":"Organization","name":"alpha123"}}}
    </script></head><body><h1>EU AR55 Venti C6R1</h1><div>Server: EU Seller: alpha123 Sold out</div></body></html>
    """
    verified = a._parse_detail(row, detail_html)
    assert verified.market_status == "SOLD_CONFIRMED"
    assert not verified.strict_live
    assert verified.relisting_fingerprint
