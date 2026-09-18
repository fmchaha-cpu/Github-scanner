from pathlib import Path

from market_v1.discord import AlertState, listing_payload
from market_v1.policy import budget_fit, genshin_alert_tier, warframe_alert_tier
from market_v1.warframe import _candidate_links, analyse_claim


def test_warframe_requires_detail_page_founder_and_prime_item():
    lead = analyse_claim("Test", "https://example.test/1", "Founder account", None)
    assert lead.evidence_level == "POTENTIAL_LEAD"
    assert not lead.alert_eligible

    credible = analyse_claim(
        "Test", "https://example.test/2", "Rare account €450",
        "Original Founder account with Excalibur Prime, Lato Prime and Skana Prime.",
    )
    assert credible.evidence_level == "CLAIM_EVIDENCE"
    assert credible.alert_eligible
    assert credible.budget_fit == "above_preferred"
    assert warframe_alert_tier(credible.model_dump()) == "dream"


def test_budget_is_label_not_hard_gate():
    assert budget_fit(900, 300) == "above_preferred"
    row = {
        "evidence_level": "CLAIM_EVIDENCE", "detail_verified": True,
        "evidence_score": 90, "price_value": 900, "prime_items": ["Excalibur Prime"],
    }
    assert warframe_alert_tier(row) == "dream"


def test_genshin_dream_can_be_outside_budget():
    row = {
        "collector_priority": 80, "identity_verified": True, "strict_live": True,
        "favorite_character_fit": 75, "price_value": 700,
    }
    assert genshin_alert_tier(row) == "dream"


def test_discord_suppresses_mentions_and_deduplicates(tmp_path: Path):
    payload = listing_payload("Warframe", "strong", {
        "title": "@everyone Founder", "url": "https://example.test/3",
        "evidence_level": "CLAIM_EVIDENCE", "prime_items": ["Excalibur Prime"],
    })
    assert payload["allowed_mentions"] == {"parse": []}
    assert "@everyone" not in payload["embeds"][0]["title"]

    state = AlertState(str(tmp_path / "alerts.sqlite3"))
    assert not state.seen("abc")
    state.mark("abc")
    assert state.seen("abc")


def test_playerup_style_relative_founder_link_is_discovered():
    html = """
    <li><a href='/accounts/warframeaccount/threads/founder-grand-master.123/'>
      Founder Grand Master with Excalibur Prime $800
    </a></li>
    """
    links = _candidate_links(html, "https://www.playerup.com/accounts/warframeaccount/", [r"/threads/"])
    assert links == [(
        "https://www.playerup.com/accounts/warframeaccount/threads/founder-grand-master.123/",
        "Founder Grand Master with Excalibur Prime $800",
    )]
