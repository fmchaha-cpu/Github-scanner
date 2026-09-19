from __future__ import annotations

import hashlib
import re
from urllib.parse import urljoin, urlparse

PRICE_PATTERNS = [
    re.compile(r"(?P<sym>[$€£])\s*(?P<value>\d{1,6}(?:[.,]\d{1,2})?)"),
    re.compile(r"(?P<value>\d{1,6}(?:[.,]\d{1,2})?)\s*(?P<code>USD|EUR|GBP)\b", re.I),
]
AR_RE = re.compile(r"\bAR\s*[-: /|]?\s*(\d{1,2})\b", re.I)
# Marketplace titles frequently concatenate gender and AR (e.g. ``MaleAR55`` / ``FemaleAR 55``).
# Keep this as a separate, narrow fallback so ordinary words containing ``ar`` are never interpreted as rank.
AR_GENDER_RE = re.compile(r"(?:male|female|famale)\s*[/|_-]?\s*AR\s*[-: /|]?\s*(\d{1,2})\b", re.I)
PRIMO_RE = re.compile(r"(?<!\d)(\d{3,7})\s*\+?\s*(?:primogem|primo(?:gems?)?)", re.I)
PRIMO_K_RE = re.compile(r"(?<![\d.])(\d{1,3}(?:[.,]\d{1,2})?)\s*[kK]\s*\+?\s*(?:primogem|primo(?:gems?)?)", re.I)
# Marketplace sellers commonly misspell "intertwined" as "interwined".
# Keep the currency term mandatory so unrelated quantities are never counted as pulls.
IF_RE = re.compile(r"(?<!\d)(\d{1,4})\s*\+?\s*(?:intertwined|interwined|interwoven)\s*(?:fate|destiny)?", re.I)
IF_LABEL_FIRST_RE = re.compile(
    r"(?:intertwined|interwined|interwoven)\s*(?:fate|destiny)?\s*[:：]?\s*(\d{1,4})(?:\s*-\s*(\d{1,4}))?\s*\+?",
    re.I,
)
DIRECT_PULL_RE = re.compile(r"(?<!\d)(\d{2,4})\s*\+?\s*(?:limited\s*)?(?:wishes|pulls)\b", re.I)

# Standard-banner 5-stars must never be promoted as "limited C6".
STANDARD_5_STAR_CHARACTERS = {
    "jean", "mona", "diluc", "keqing", "qiqi", "tighnari", "dehya", "yumemizuki mizuki", "mizuki"
}

# Known limited / market-relevant 5-stars. This list is intentionally explicit to prevent
# random title fragments before "C6" from being counted as a character.
KNOWN_LIMITED_CHARACTERS = [
    "Venti", "Klee", "Tartaglia", "Childe", "Zhongli", "Albedo", "Ganyu", "Xiao", "Hu Tao",
    "Eula", "Kazuha", "Kamisato Ayaka", "Ayaka", "Yoimiya", "Raiden Shogun", "Raiden",
    "Sangonomiya Kokomi", "Kokomi", "Arataki Itto", "Itto", "Shenhe", "Yae Miko", "Ayato",
    "Yelan", "Cyno", "Nilou", "Nahida", "Wanderer", "Alhaitham", "Baizhu", "Lyney",
    "Neuvillette", "Wriothesley", "Furina", "Navia", "Xianyun", "Chiori", "Arlecchino",
    "Clorinde", "Sigewinne", "Emilie", "Mualani", "Kinich", "Xilonen", "Chasca", "Mavuika",
    "Citlali", "Varesa", "Escoffier", "Skirk", "Ineffa", "Lauma", "Flins", "Columbina",
    "Sandrone", "Zibai", "Odette",
]

LEGACY_TERMS = [
    "festering desire", "cinnabar spindle", "dodoco tales", "luxurious sea-lord",
    "oathsworn eye", "fading twilight", "toukabou shigure", "ibis piercer",
    "ultimate overlord's mega magic sword", "aloy", "event weapon", "legacy",
    "windblume ode", "mailed flower", "fleuve cendre ferryman", "old event weapon",
]
HISTORY_TERMS = [
    "day 1", "day one", "launch account", "2020", "2021", "old main", "old account",
    "abandoned main", "returning account", "veteran account", "first owner", "original owner",
    "played since", "since launch", "since 1.0", "since version 1", "retired account",
    "quit genshin", "quitting genshin", "personal account", "main account",
]
OLD_ALT_TERMS = [
    "old alt", "old secondary", "secondary account", "alt account", "abandoned alt",
    "unused account", "rarely played", "spare account", "second account",
]
DISCOVERY_TERMS = [
    "low exploration", "unexplored", "many quests", "quests left", "story left",
    "world quests left", "not explored", "exploration unfinished", "regions untouched",
    "lots of exploration left", "many regions left", "unfinished story", "archon quest left",
]
RESOURCE_TERMS = [
    "fragile resin", "crowns", "crown of insight", "mora", "hero's wit", "heros wit",
    "talent books", "weapon materials", "billet", "dream solvent", "sanctifying elixir",
    "artifact xp", "stardust", "starglitter", "transient resin",
]
MANUFACTURED_TERMS = [
    "reroll", "stock account", "fresh account", "random gender", "safe and stable, send now",
    "mass account", "farm account", "starter account", "unlinked stock", "automatic delivery",
]
RISK_TERM_MAP = {
    "negative_primos": ["negative primogem", "negative primo", "negative gems"],
    "chargeback": ["chargeback", "charged back", "payment dispute"],
    "recovery": ["recovery risk", "seller can recover", "original email unavailable"],
    "cheat_or_hack": ["cheated account", "hacked account", "hack used", "cheat used", "modded"],
    "botting": ["bot farm", "botted", "botting", "scripted farming", "script farm"],
    "ban_warning": ["ban risk", "ban warning", "suspended before"],
}

SELLER_PATTERNS = [
    re.compile(r"\b(?:seller|sold by|merchant|vendor)\s*[:\-]?\s*([A-Za-z0-9_.-]{2,40})", re.I),
    re.compile(r"\b(?:seller name|shop)\s*[:\-]?\s*([A-Za-z0-9_. -]{2,50})", re.I),
]

LIVE_TERMS = ("buy now", "jetzt kaufen", "in stock", "available now", "available")
SOLD_TERMS = ("sold out", "out of stock", "listing ended", "listing closed", "offer ended", "item sold")


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def sha256_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8", errors="ignore")).hexdigest()


def absolute_url(base: str, href: str) -> str:
    return urljoin(base, href)


def parse_price(text: str):
    for p in PRICE_PATTERNS:
        m = p.search(text or "")
        if not m:
            continue
        value = float(m.group("value").replace(",", "."))
        sym = m.groupdict().get("sym")
        code = m.groupdict().get("code")
        currency = code.upper() if code else {"$": "USD", "€": "EUR", "£": "GBP"}.get(sym)
        return value, currency
    return None, None


def parse_server(text: str):
    t = f" {(text or '').lower()} "
    if re.search(r"\b(eu|europe|european)\b", t):
        return "EU"
    if re.search(r"\b(na|america|american)\b", t):
        return "NA"
    if re.search(r"\basia\b", t):
        return "ASIA"
    if re.search(r"\b(tw|hk|mo|taiwan|hong kong)\b", t):
        return "TW/HK/MO"
    return None


def parse_ar(text: str):
    raw = text or ""
    m = AR_RE.search(raw) or AR_GENDER_RE.search(raw)
    if not m:
        return None
    value = int(m.group(1))
    return value if 1 <= value <= 60 else None


def parse_resources(text: str):
    text = text or ""
    primos = None
    intertwined = None
    m = PRIMO_RE.search(text)
    if m:
        primos = int(m.group(1))
    else:
        m = PRIMO_K_RE.search(text)
        if m:
            primos = int(round(float(m.group(1).replace(",", ".")) * 1000))

    m = IF_RE.search(text)
    if m:
        intertwined = int(m.group(1))
    else:
        m = IF_LABEL_FIRST_RE.search(text)
        if m:
            intertwined = max(int(value) for value in m.groups() if value is not None)

    pulls = None
    if primos is not None or intertwined is not None:
        # Canonical rule: Limited_Pulls = Primogems/160 + Intertwined Fates only.
        pulls = (primos or 0) / 160 + (intertwined or 0)
    return primos, intertwined, pulls


def parse_seller(text: str) -> str | None:
    text = clean_text(text)
    for pattern in SELLER_PATTERNS:
        m = pattern.search(text)
        if m:
            value = clean_text(m.group(1)).strip(" -|")
            if 2 <= len(value) <= 50:
                return value
    return None


def parse_availability(text: str) -> str | None:
    low = (text or "").lower()
    # Historical status is high-impact, so generic words like "closed" or "unavailable"
    # are not enough by themselves. Require listing/offer/item context or strong stock wording.
    contextual_sold = re.search(
        r"\b(?:this\s+)?(?:listing|offer|item)\s+(?:is\s+)?(?:sold|closed|unavailable|ended)\b",
        low,
    )
    if any(x in low for x in SOLD_TERMS) or contextual_sold:
        return "Sold/Closed"
    if "buy now" in low or "jetzt kaufen" in low:
        return "BUY NOW"
    if "in stock" in low:
        return "In Stock"
    if "available now" in low:
        return "Available"
    return None


def count_terms(text: str, terms: list[str]) -> int:
    t = (text or "").lower()
    return sum(1 for term in terms if term in t)


def _contains_name(text: str, name: str) -> bool:
    return re.search(rf"(?<![A-Za-z]){re.escape(name)}(?![A-Za-z])", text, re.I) is not None


def _constellation_characters(text: str, rank: str) -> list[str]:
    matches: list[str] = []
    for name in sorted(KNOWN_LIMITED_CHARACTERS, key=len, reverse=True):
        if name.lower() in STANDARD_5_STAR_CHARACTERS:
            continue
        if re.search(rf"(?<![A-Za-z]){re.escape(name)}\s*{rank}\b", text or "", re.I):
            canonical = "Tartaglia" if name.lower() == "childe" else name
            if canonical.lower() not in {x.lower() for x in matches}:
                matches.append(canonical)
    return matches


def infer_features(text: str, favorite_characters: list[str] | None = None):
    text = text or ""
    c6r1_names = _constellation_characters(text, r"C6\s*R1")
    c6_names = _constellation_characters(text, r"C6")
    # C6R1 does not satisfy a word-boundary after C6, so explicitly union both sets.
    c6_names = list(dict.fromkeys(c6_names + c6r1_names))

    # Broad character signature improves comparables and relisting suggestions.
    # Exact word boundaries reduce accidental substring matches.
    character_tags: list[str] = []
    tag_names = list(KNOWN_LIMITED_CHARACTERS) + [
        "Jean", "Mona", "Diluc", "Keqing", "Qiqi", "Tighnari", "Dehya", "Mizuki"
    ]
    aliases = {"Childe": "Tartaglia", "Raiden": "Raiden Shogun", "Ayaka": "Kamisato Ayaka",
               "Kokomi": "Sangonomiya Kokomi", "Itto": "Arataki Itto"}
    seen_tags: set[str] = set()
    for name in sorted(tag_names, key=len, reverse=True):
        if _contains_name(text, name):
            canonical = aliases.get(name, name)
            key = canonical.lower()
            if key not in seen_tags:
                character_tags.append(canonical)
                seen_tags.add(key)

    favorites = []
    for name in favorite_characters or []:
        if _contains_name(text, name):
            favorites.append(name)

    risk_flags = [flag for flag, terms in RISK_TERM_MAP.items() if count_terms(text, terms) > 0]
    manufactured_hits = count_terms(text, MANUFACTURED_TERMS)
    return {
        "limited_c6_count": len(c6_names),
        "c6r1_count": len(c6r1_names),
        "multi_c6": len(c6_names) >= 2,
        "limited_c6_characters": c6_names,
        "c6r1_characters": c6r1_names,
        "character_tags": character_tags,
        "legacy_hits": count_terms(text, LEGACY_TERMS),
        "history_hits": count_terms(text, HISTORY_TERMS),
        "discovery_hits": count_terms(text, DISCOVERY_TERMS),
        "resource_hits": count_terms(text, RESOURCE_TERMS),
        "manufactured_hits": manufactured_hits,
        "risk_hits": len(risk_flags),
        "old_alt_hits": count_terms(text, OLD_ALT_TERMS),
        "favorite_character_names": favorites,
        "risk_flags": risk_flags,
    }


def security_hint(text: str, after_sale_protection: str | None = None, seller_present: bool = False) -> float:
    low = (text or "").lower()
    score = 55.0
    if seller_present:
        score += 5
    if after_sale_protection:
        score += 10
    if "original owner" in low or "first owner" in low:
        score += 8
    if "full access" in low or "email change" in low or "change email" in low:
        score += 5
    if any(x in low for x in ["no email bound", "email unbound", "unlinked email"]):
        score += 5

    flags = [flag for flag, terms in RISK_TERM_MAP.items() if count_terms(text, terms) > 0]
    penalties = {
        "negative_primos": 55,
        "chargeback": 40,
        "recovery": 40,
        "cheat_or_hack": 55,
        "botting": 35,
        "ban_warning": 50,
    }
    score -= sum(penalties.get(flag, 25) for flag in flags)
    if count_terms(text, MANUFACTURED_TERMS) > 0:
        score -= 8
    return max(0.0, min(100.0, score))


def infer_external_id(platform: str, url: str, text: str = "") -> str | None:
    if platform.lower() == "playerauctions":
        m = re.search(r"/genshin-impact-account/(\d+)a", url)
        if m:
            return m.group(1)
    if platform.lower() == "zeusx":
        path = urlparse(url).path.rstrip("/")
        if path:
            return hashlib.sha1(path.encode()).hexdigest()[:16]
    if platform.lower() in {"epicnpc", "playerup"}:
        m = re.search(r"/threads/[^./]*\.(\d+)", url)
        if m:
            return m.group(1)
    m = re.search(r"\b(?:listing|offer|item)[-_ ]?(?:id)?[:# ]*(\d{5,})\b", text or "", re.I)
    return m.group(1) if m else None
