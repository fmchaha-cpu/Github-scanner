from bs4 import BeautifulSoup

from genshin_collector.adapters.generic import GenericMarketplaceAdapter
from genshin_collector.models import ListingObservation
from genshin_collector.normalize import parse_ar


def pa_adapter(**kwargs):
    opts = dict(
        name="PlayerAuctions",
        scans=[],
        detail_patterns=[r"/genshin-impact-account/\d+a"],
        favorite_characters=["Venti", "Arlecchino"],
    )
    opts.update(kwargs)
    return GenericMarketplaceAdapter(**opts)


def test_pa_duplicate_title_and_buy_now_anchors_merge_instead_of_overwrite():
    a = pa_adapter()
    href = "/genshin-impact-account/296062141a%21kk1916eufemalear-55five-star7varesac6xilonen/"
    html = f"""
    <div class='offer-row'>
      <div class='product'>
        <a href='{href}'>KK1916 [EU] Female AR 55 | Varesa C6 + Xilonen</a>
        <a href='/store/MJjiang0018/'>MJjiang0018</a>
        <span class='price'>$54.99</span>
        <span>Instant Delivery</span>
        <a href='{href}'>BUY NOW</a>
      </div>
    </div>
    """
    rows = a._parse_cards("https://www.playerauctions.com/genshin-impact-account/eu/", html)
    assert len(rows) == 1
    row = rows[0]
    assert "Varesa C6" in row.title
    assert row.title != "BUY NOW"
    assert row.server == "EU"
    assert row.ar == 55
    assert row.seller == "MJjiang0018"
    assert row.price_value == 54.99
    assert row.availability == "BUY NOW"
    assert row.limited_c6_count == 1
    assert row.parser_strategy == "anchor_merged_v09"


def test_pa_url_slug_recovers_server_and_ar_when_card_label_is_generic():
    a = pa_adapter()
    html = """
    <div class='offer'>
      <a href='/genshin-impact-account/295389649a%21nnc2773namalear-53furina/'>BUY NOW</a>
      <span>$42.00</span>
    </div>
    """
    row = a._parse_cards("https://www.playerauctions.com/genshin-impact-account/", html)[0]
    assert row.server == "NA"
    assert row.ar == 53
    assert row.field_sources["server"] == "url_slug"
    assert row.field_sources["ar"] == "url_slug"


def test_pa_eu_query_context_hydrates_missing_server_conservatively():
    a = pa_adapter()
    html = """
    <div class='offer'>
      <a href='/genshin-impact-account/295389650a%21plain-product-slug/'>Furina account</a>
      <span>$45.00</span><span>BUY NOW</span>
    </div>
    """
    row = a._parse_cards("https://www.playerauctions.com/genshin-impact-account/eu/", html)[0]
    assert row.server == "EU"
    assert row.field_sources["server"] == "query_context"


def test_pa_category_links_are_not_counted_as_pattern_drift():
    a = pa_adapter()
    assert not a._looks_listing_like_url("https://www.playerauctions.com/genshin-impact-account/eu/")
    assert not a._looks_listing_like_url("https://www.playerauctions.com/genshin-impact-account/c6/")
    assert not a._looks_listing_like_url("https://www.playerauctions.com/genshin-impact-account/furina/")
    assert a._looks_listing_like_url("https://www.playerauctions.com/genshin-impact-account/296062141a%21abc/")


def test_parse_ar_accepts_marketplace_gender_concatenation_and_typo():
    assert parse_ar("EU MaleAR 55 Venti") == 55
    assert parse_ar("EU FemaleAR55 Furina") == 55
    assert parse_ar("EU FamaleAR-54 Varesa") == 54


def test_zeusx_server_region_label_and_semantic_buy_control_verify_identity():
    a = GenericMarketplaceAdapter(
        name="ZeusX", scans=[], detail_patterns=[r"/game/genshin-impact/13/accounts/"],
    )
    card = """
    <div class='card'>
      <a href='/game/genshin-impact/13/accounts/eu-ar55-venti-c6-12345'>EU AR55 Venti C6</a>
      <a href='/seller/beads-shop'>Beads Shop</a>
      <span>$49.99</span>
    </div>
    """
    row = a._parse_cards("https://zeusx.com/game/genshin-impact/13/accounts", card)[0]
    detail = """
    <html><body><main>
      <h1>Venti C6 account</h1>
      <div>Price: $49.99</div><div>Server/Region: Europe</div><div>Venti C6</div>
      <div role='button'>Buy Now</div>
    </main><aside><a href='/seller/beads-shop'>Beads Shop</a></aside></body></html>
    """
    verified = a._parse_detail(row, detail)
    assert verified.server == "EU"
    assert verified.availability == "BUY NOW"
    assert verified.identity_verified
    assert verified.strict_live


def test_zeusx_styled_buy_div_requires_control_like_attribute():
    a = GenericMarketplaceAdapter(name="ZeusX", scans=[], detail_patterns=[r"/accounts/"])
    weak = BeautifulSoup("<div><span>Buy Now</span></div>", "html.parser")
    assert a._availability_from_controls(weak)[0] is None
    strong = BeautifulSoup("<div class='purchase-button'>Buy Now</div>", "html.parser")
    assert a._availability_from_controls(strong)[0] == "BUY NOW"


def test_verification_plan_reserves_budget_for_merit_probe_and_calibration():
    a = GenericMarketplaceAdapter(
        name="PlayerAuctions", scans=[], detail_patterns=[r"/x/"],
        deep_verify_limit=2, deep_verify_hard_cap=5,
        merit_verify_sample=1, calibration_verify_sample=1, control_verify_sample=1,
    )
    rows = []
    for i in range(3):
        r = ListingObservation(platform="PlayerAuctions", url=f"https://x.test/x/c{i}", title=f"candidate {i}", price_value=70+i)
        r.is_candidate = True
        r.collector_priority = 100-i
        rows.append(r)
    merit = ListingObservation(platform="PlayerAuctions", url="https://x.test/x/merit", title="Venti C6", price_value=80)
    merit.limited_c6_count = 1
    merit.collector_priority = 70
    rows.append(merit)
    gap = ListingObservation(platform="PlayerAuctions", url="https://x.test/x/gap", title="gap", price_value=90)
    rows.append(gap)
    control = ListingObservation(platform="PlayerAuctions", url="https://x.test/x/control", title="control", price_value=95, server="EU", seller="alpha")
    rows.append(control)
    plan = a._verification_plan(rows)
    reasons = [reason for _, reason in plan]
    assert reasons.count("candidate") == 2
    assert "merit_probe" in reasons
    assert "calibration_gap" in reasons
    assert len(plan) <= 5
