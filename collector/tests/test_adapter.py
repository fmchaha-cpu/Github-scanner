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


def test_playerauctions_profile_seller_and_card_boundary():
    a = adapter()
    html = """
    <section>
      <div class='offer'>
        <a href='/genshin-impact-account/111111a-first/'>EU AR55 Columbina C6</a>
        <a href='/store/game188/'>game188</a><span>Instant</span><span>$24.60</span><span>BUY NOW</span>
      </div>
      <div class='offer'>
        <a href='/genshin-impact-account/222222a-second/'>EU AR55 Varesa C6</a>
        <a href='/store/MJjiang0018/'>MJjiang0018</a><span>Instant</span><span>$54.99</span><span>BUY NOW</span>
      </div>
    </section>
    """
    rows = sorted(a._parse_cards('https://www.playerauctions.com/genshin-impact-account/eu/', html), key=lambda r: r.external_id)
    assert len(rows) == 2
    assert rows[0].seller == 'game188'
    assert rows[0].price_value == 24.60
    assert rows[1].seller == 'MJjiang0018'
    assert rows[1].price_value == 54.99


def test_epicnpc_profile_seller_and_buying_thread_filtered():
    a = GenericMarketplaceAdapter(name='EpicNPC', scans=[], detail_patterns=[r'/threads/'])
    html = """
    <div class='structItem'>
      <a href='/threads/eu-chasca-c6.12345/'>EU Chasca C6 + Sign $90</a>
      <a href='/members/flautiz.567/'>Flautiz</a><span>$90.00</span>
    </div>
    <div class='structItem'>
      <a href='/threads/buying-quick-sale.99999/'>Buying quick sale accounts</a>
      <a href='/members/buyer.777/'>buyer</a>
    </div>
    """
    rows = a._parse_cards('https://www.epicnpc.com/forums/genshin-impact-eu-accounts.2156/', html)
    assert len(rows) == 1
    assert rows[0].seller == 'Flautiz'
    assert rows[0].price_value == 90
    assert rows[0].limited_c6_count == 1


def test_probe_records_detail_links_and_challenge_signals():
    a = adapter()
    html = """<html><head><title>Just a Moment...</title></head><body>
    <div>Verify you are human</div><a href='/genshin-impact-account/123456a-x/'>offer</a>
    </body></html>"""
    probe = a._probe_html('https://www.playerauctions.com/genshin-impact-account/eu/', html, 'http', 200, 12)
    assert probe.detail_link_count == 1
    assert 'human_check' in probe.blocked_signals or 'challenge' in probe.blocked_signals
    suspicious, reason = a._page_is_suspicious(probe, True)
    assert suspicious
    assert reason and 'blocked_or_challenge' in reason


def test_fetch_falls_back_to_browser_when_http_has_zero_listing_links():
    import asyncio
    a = adapter()
    weak = '<html><body>' + ('navigation text ' * 500) + '</body></html>'
    good = "<html><body><a href='/genshin-impact-account/123456a-x/'>EU AR55 Venti C6 $40</a>" + ('x ' * 3000) + '</body></html>'

    async def fake_http(url):
        return weak, 200, 10, url, {"content-type": "text/html"}

    async def fake_browser(url):
        return good, 50, url, 200, {"content-type": "text/html"}, False

    a._http_fetch = fake_http
    a._browser_fetch = fake_browser
    fetched = asyncio.run(a._fetch('https://www.playerauctions.com/genshin-impact-account/eu/', expect_listing_links=True))
    assert fetched.mode == 'browser'
    assert fetched.detail_link_count == 1
    assert fetched.fallback_reason == 'zero_detail_links'


def test_verification_plan_includes_calibration_samples():
    from genshin_collector.models import ListingObservation
    a = GenericMarketplaceAdapter(
        name='test', scans=[], detail_patterns=[r'/x/'], deep_verify_limit=2,
        deep_verify_hard_cap=4, calibration_verify_sample=2,
    )
    rows = []
    for i in range(5):
        row = ListingObservation(platform='test', url=f'https://x.test/x/{i}', title=f'row {i}', server='EU', price_value=50+i)
        row.is_candidate = i < 2
        row.collector_priority = 90-i
        rows.append(row)
    plan = a._verification_plan(rows)
    reasons = [reason for _, reason in plan]
    assert reasons.count('candidate') == 2
    assert reasons.count('calibration_gap') == 2


def test_probe_surfaces_unmatched_listing_like_urls_for_pattern_drift():
    a = GenericMarketplaceAdapter(
        name='PlayerAuctions', scans=[], detail_patterns=[r'/genshin-impact-account/\d+a-old-format/']
    )
    html = """<html><body>
    <a href='/genshin-impact-account/987654a-new-slug/'>EU AR55 Furina C6 $40</a>
    </body></html>"""
    probe = a._probe_html(
        'https://www.playerauctions.com/genshin-impact-account/', html, 'http', 200, 10,
        final_url='https://www.playerauctions.com/genshin-impact-account/'
    )
    assert probe.detail_link_count == 0
    assert probe.unmatched_listing_like_count == 1
    assert '987654a-new-slug' in probe.sample_unmatched_listing_like_urls[0]


def test_scan_preserves_fetch_diagnostics_when_parser_raises():
    import asyncio
    from genshin_collector.adapters.generic import FetchPage

    a = GenericMarketplaceAdapter(
        name='PlayerAuctions',
        scans=[{'family': 'eu_all', 'label': 'EU', 'url': 'https://example.test/genshin-impact-account/eu/'}],
        detail_patterns=[r'/genshin-impact-account/\d+a'],
        deep_verify_limit=0,
    )

    async def fake_fetch(url, expect_listing_links=False):
        return FetchPage(
            html='<html><body>x</body></html>', mode='browser', http_status=None, elapsed_ms=25,
            html_bytes=6000, text_chars=1200, anchor_count=4, detail_link_count=0,
            page_title='EU offers', content_hash='abc', blocked_signals=['challenge'], sample_detail_urls=[],
            final_url=url, fallback_reason='zero_detail_links',
            http_probe_html_bytes=5500, http_probe_text_chars=1000, http_probe_detail_link_count=0,
            http_probe_content_hash='def', http_probe_blocked_signals=['challenge'],
        )

    def bad_parse(base_url, html):
        raise ValueError('parser broke')

    a._fetch = fake_fetch
    a._parse_cards = bad_parse
    result = asyncio.run(a.scan())
    assert result.errors
    assert result.coverage[0].status == 'error'
    assert result.coverage[0].fetch_mode == 'browser'
    assert result.coverage[0].fallback_reason == 'zero_detail_links'
    assert result.coverage[0].http_probe_content_hash == 'def'


def test_scan_circuit_breaker_stops_repeated_blocked_source_paths():
    import asyncio
    from genshin_collector.adapters.generic import FetchPage

    scans = [
        {'family': 'one', 'label': 'one', 'url': 'https://example.test/one'},
        {'family': 'two', 'label': 'two', 'url': 'https://example.test/two'},
        {'family': 'three', 'label': 'three', 'url': 'https://example.test/three'},
    ]
    a = GenericMarketplaceAdapter(
        name='PlayerAuctions', scans=scans, detail_patterns=[r'/genshin-impact-account/\d+a'],
        deep_verify_limit=0, circuit_breaker_enabled=True, circuit_breaker_blocked_threshold=1,
    )
    calls = []
    async def fake_fetch(url, expect_listing_links=False):
        calls.append(url)
        return FetchPage(
            html='<html><body>Just a moment... challenge-platform</body></html>', mode='browser',
            http_status=403, elapsed_ms=700, html_bytes=2000, text_chars=40, anchor_count=0,
            detail_link_count=0, page_title='Just a moment', content_hash='blocked',
            blocked_signals=['challenge'], sample_detail_urls=[], final_url=url,
            browser_early_blocked=True,
        )
    a._fetch = fake_fetch
    result = asyncio.run(a.scan())
    assert calls == ['https://example.test/one']
    assert result.coverage[0].status == 'blocked:browser'
    assert result.coverage[0].circuit_breaker_triggered is True
    assert [r.status for r in result.coverage[1:]] == ['skipped:circuit_breaker', 'skipped:circuit_breaker']
