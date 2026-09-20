from __future__ import annotations

from market_v1.discord import ps5_payload
from market_v1.ps5 import (
    PS5Offer,
    PS5Store,
    alert_tier,
    parse_idealo_product,
    parse_playstation_direct,
    parse_source,
)


THRESHOLDS = {
    "digital": {
        "new": {"good": 519.99, "excellent": 469.99},
        "certified_refurbished": {"good": 499.99, "excellent": 449.99},
    },
    "disc": {
        "new": {"good": 569.99, "excellent": 519.99},
        "certified_refurbished": {"good": 549.99, "excellent": 499.99},
    },
}


def test_idealo_title_fallback_uses_new_console_price_not_used_tab():
    html = """
      <html><head><title>Sony PlayStation 5 Slim Digital Edition ab 499,00 €</title></head>
      <body><h1>PlayStation 5 Slim Digital</h1>B-Ware & Gebraucht ab 399,00 €</body></html>
    """
    rows = parse_idealo_product(html, {
        "name": "Idealo Digital", "model": "digital", "condition": "new",
        "title": "Sony PlayStation 5 Slim Digital Edition",
    }, "https://example.test/digital")
    assert len(rows) == 1
    assert rows[0].price_eur == 499
    assert rows[0].condition == "new"
    assert alert_tier(rows[0], THRESHOLDS) == "good"


def test_geizhals_title_fallback_accepts_currency_before_price():
    html = """
      <html><head><title>Sony PlayStation 5 Slim Digital Edition - 825GB weiß ab € 574,00 (2026)</title></head></html>
    """
    rows = parse_idealo_product(html, {
        "name": "Geizhals Digital", "model": "digital", "condition": "new",
        "title": "Sony PlayStation 5 Slim Digital Edition 825GB", "seller": "Geizhals Preisvergleich",
    }, "https://example.test/digital")
    assert len(rows) == 1
    assert rows[0].price_eur == 574
    assert rows[0].seller == "Geizhals Preisvergleich"
    assert rows[0].availability == "price_comparison"


def test_playstation_direct_catalog_finds_only_supported_consoles():
    html = """
      <body>
        <div>PlayStation®5 Pro Konsole - 2 TB</div><div>899</div>
        <div>PlayStation®5 Digital Edition Konsole - 825 GB</div><div>599</div>
        <div>PlayStation®5 Konsole - 1 TB</div><div>649</div>
        <div>Generalüberholt und Zertifiziert PlayStation®5 Konsole (Modellgruppe - Slim)</div><div>549</div>
        <div>Generalüberholt und Zertifiziert PlayStation®5 Digital Edition Konsole</div><div>499</div>
        <div>DualSense Controller für PS5</div><div>84</div>
        <div>Disc-Laufwerk für PS5 Digital Edition</div><div>119</div>
      </body>
    """
    rows = parse_playstation_direct(
        html, {"name": "PlayStation Direct"}, "https://direct.playstation.test/ps5",
    )
    assert {(row.model, row.condition, row.price_eur) for row in rows} == {
        ("digital", "new", 599),
        ("disc", "new", 649),
        ("disc", "certified_refurbished", 549),
        ("digital", "certified_refurbished", 499),
    }


def test_playstation_direct_uses_product_api_for_exact_price_stock_and_link():
    html = """
      <div class="product-card-wrapper js-product-tile" data-product-code="DIGITAL-DE">
        <a href="/de-de/buy-consoles/ps5-digital"></a>
        <div class="product-card-details__name">PlayStation®5 Digital Edition Konsole - 825 GB</div>
        <div class="text-product-price js-actual-price">
          <span class="js-actual-price-whole">599</span><span class="js-actual-price-fraction">99</span>
        </div>
        <button class="js-add-to-cart hide">In den Einkaufswagen</button>
        <div class="js-out-stock-wrpr hide">Nicht verfügbar</div>
      </div>
      <div class="product-card-wrapper js-product-tile" data-product-code="REFURB-DE">
        <a href="/de-de/buy-consoles/ps5-refurb"></a>
        <div class="product-card-details__name">Generalüberholt und Zertifiziert PlayStation®5 Konsole</div>
        <div class="text-product-price js-actual-price">
          <span class="js-actual-price-whole">519</span><span class="js-actual-price-fraction">99</span>
        </div>
        <button class="js-add-to-cart hide">In den Einkaufswagen</button>
        <div class="js-out-stock-wrpr hide">Nicht verfügbar</div>
      </div>
    """
    products = {
        "DIGITAL-DE": {
            "code": "DIGITAL-DE", "purchasable": True,
            "stock": {"stockLevelStatus": "outOfStock"}, "price": {"value": 599.99},
        },
        "REFURB-DE": {
            "code": "REFURB-DE", "purchasable": True,
            "stock": {"stockLevelStatus": "inStock"}, "price": {"value": 519.99},
        },
    }
    rows = parse_playstation_direct(
        html, {"name": "PlayStation Direct"}, "https://direct.playstation.test/de-de/hardware/ps5", products,
    )
    assert [(row.price_eur, row.availability) for row in rows] == [
        (599.99, "out_of_stock"), (519.99, "in_stock"),
    ]
    assert rows[0].url == "https://direct.playstation.test/de-de/buy-consoles/ps5-digital"
    assert alert_tier(rows[0], THRESHOLDS) is None
    assert alert_tier(rows[1], THRESHOLDS) == "good"


def test_ps5_offer_identity_does_not_change_with_price():
    offer = PS5Offer(
        source="Test", url="https://example.test/ps5", title="PS5 Disc Edition",
        model="disc", condition="new", price_eur=569,
    )
    key = offer.offer_key
    offer.price_eur = 519
    offer.source = "Another comparison portal"
    offer.url = "https://example.test/a-different-link"
    assert offer.offer_key == key


def test_generic_jsonld_accepts_new_but_not_uncertified_refurbished():
    html = """
      <script type="application/ld+json">
      {"@context":"https://schema.org","@graph":[
        {"@type":"Product","name":"Sony PlayStation 5 Slim Digital Edition",
         "url":"/new","offers":{"@type":"Offer","price":"499.00","priceCurrency":"EUR"}},
        {"@type":"Product","name":"Sony PlayStation 5 Slim Disc Refurbished",
         "url":"/used","offers":{"@type":"Offer","price":"399.00","priceCurrency":"EUR"}}
      ]}
      </script>
    """
    rows = parse_source(html, {
        "name": "Retailer", "kind": "jsonld", "condition": "new",
    }, "https://example.test/catalog")
    assert [(row.model, row.condition, row.price_eur) for row in rows] == [("digital", "new", 499)]


def test_store_deduplicates_and_realerts_only_after_meaningful_drop(tmp_path):
    store = PS5Store(str(tmp_path / "ps5.sqlite3"))
    offer = PS5Offer(
        source="Test", url="https://example.test/ps5", title="PS5 Digital Edition",
        model="digital", condition="new", price_eur=519, availability="in_stock",
    )
    assert store.observe(offer, "good", 10)
    store.mark_alerted(offer, "good")
    assert not store.observe(offer, "good", 10)

    offer.source = "Another comparison portal"
    offer.url = "https://example.test/new-best-link"
    offer.price_eur = 515
    assert not store.observe(offer, "good", 10)
    stored = store.db.execute("SELECT source, url FROM ps5_offers WHERE offer_key=?", (offer.offer_key,)).fetchone()
    assert tuple(stored) == ("Another comparison portal", "https://example.test/new-best-link")
    offer.price_eur = 509
    assert store.observe(offer, "good", 10)
    store.mark_alerted(offer, "good")
    offer.price_eur = 469
    assert store.observe(offer, "excellent", 10)
    store.close()


def test_ps5_discord_payload_suppresses_mentions():
    payload = ps5_payload("excellent", {
        "title": "@everyone PS5 Digital", "url": "https://example.test/deal",
        "model": "digital", "condition": "new", "price_eur": 449,
        "source": "Test", "availability": "in_stock",
    }, {"digital": {"new": 599}})
    assert payload["allowed_mentions"] == {"parse": []}
    assert "@everyone" not in payload["embeds"][0]["title"]
    assert payload["embeds"][0]["url"] == "https://example.test/deal"
    assert any(field["value"] == "auf Lager" for field in payload["embeds"][0]["fields"])


def test_unknown_or_unavailable_offer_never_alerts():
    offer = PS5Offer(
        source="Test", url="https://example.test/ps5", title="PS5 Disc Edition",
        model="disc", condition="new", price_eur=399, availability="out_of_stock",
    )
    assert alert_tier(offer, THRESHOLDS) is None
    offer.availability = "unknown"
    assert alert_tier(offer, THRESHOLDS) is None
    offer.availability = "in_stock"
    assert alert_tier(offer, THRESHOLDS) == "excellent"
