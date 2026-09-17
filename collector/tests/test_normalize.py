from genshin_collector.normalize import (
    infer_features, parse_resources, parse_seller, parse_availability, security_hint
)


def test_standard_c6_not_counted_as_limited():
    f = infer_features("EU AR55 Jean C6 Furina C6 $40")
    assert f["limited_c6_count"] == 1
    assert f["limited_c6_characters"] == ["Furina"]


def test_c6r1_and_favorite_detected():
    f = infer_features("EU Venti C6R1 account", ["Venti"])
    assert f["c6r1_count"] == 1
    assert f["limited_c6_count"] == 1
    assert f["favorite_character_names"] == ["Venti"]


def test_resource_parsing_k_primos():
    primos, intertwined, pulls = parse_resources("38.4k primogems and 40 intertwined fates")
    assert primos == 38400
    assert intertwined == 40
    assert pulls == 280


def test_ambiguous_wishes_are_not_counted_as_limited_pulls():
    primos, intertwined, pulls = parse_resources("500 wishes ready")
    assert primos is None and intertwined is None and pulls is None


def test_seller_and_availability():
    text = "Seller: phamtan BUY NOW 7 days protection"
    assert parse_seller(text) == "phamtan"
    assert parse_availability(text) == "BUY NOW"


def test_sold_takes_precedence_over_available():
    assert parse_availability("This offer is sold out. Similar products available now.") == "Sold/Closed"


def test_security_risk_penalty():
    safe = security_hint("original owner full access", "7 days", True)
    risky = security_hint("negative primogems chargeback risk", "7 days", True)
    assert safe > risky
    assert risky < 50


def test_sold_by_does_not_mean_sold_listing():
    assert parse_availability("Sold by alpha123 - BUY NOW") == "BUY NOW"


def test_character_tags_capture_roster_signature_without_duplicate_aliases():
    f = infer_features("EU Raiden C0 Raiden Shogun Furina Jean account")
    assert "Raiden Shogun" in f["character_tags"]
    assert "Furina" in f["character_tags"]
    assert "Jean" in f["character_tags"]
    assert f["character_tags"].count("Raiden Shogun") == 1


def test_generic_unavailable_text_does_not_fake_sold_status():
    assert parse_availability("Service unavailable in one country. Seller: alpha BUY NOW") == "BUY NOW"


def test_contextual_listing_closed_is_sold_status():
    assert parse_availability("This listing is closed. Similar offers available now") == "Sold/Closed"
