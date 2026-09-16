from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

PRICE_PATTERNS = [
    re.compile(r"(?P<sym>[$€£])\s*(?P<value>\d{1,6}(?:[.,]\d{1,2})?)"),
    re.compile(r"(?P<value>\d{1,6}(?:[.,]\d{1,2})?)\s*(?P<code>USD|EUR|GBP)\b", re.I),
]
AR_RE = re.compile(r"\bAR\s*[-: ]?\s*(\d{1,2})\b", re.I)
PRIMO_RE = re.compile(r"(?<!\d)(\d{3,6})\s*\+?\s*(?:primogem|primo(?:gems?)?)", re.I)
IF_RE = re.compile(r"(?<!\d)(\d{1,4})\s*\+?\s*(?:intertwined|interwoven)\s*(?:fate|destiny)?", re.I)
C6_RE = re.compile(r"\b([A-Za-zÀ-ÿ' -]{2,25})\s*C6\b", re.I)
C6R1_RE = re.compile(r"\b([A-Za-zÀ-ÿ' -]{2,25})\s*C6\s*R1\b", re.I)

LEGACY_TERMS = [
    "festering desire", "cinnabar spindle", "dodoco tales", "luxurious sea-lord",
    "oathsworn eye", "fading twilight", "toukabou shigure", "ibis piercer",
    "ultimate overlord's mega magic sword", "aloy", "event weapon", "legacy",
]
HISTORY_TERMS = [
    "day 1", "day one", "launch account", "2020", "2021", "old main",
    "old account", "abandoned main", "returning account", "veteran account",
    "first owner", "original owner", "played since",
]
DISCOVERY_TERMS = [
    "low exploration", "unexplored", "many quests", "quests left", "story left",
    "world quests left", "not explored", "exploration unfinished", "regions untouched",
]
RESOURCE_TERMS = [
    "fragile resin", "crowns", "crown of insight", "mora", "hero's wit",
    "talent books", "weapon materials", "billet", "dream solvent", "sanctifying elixir",
]


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
    t = f" {text.lower()} "
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
    m = AR_RE.search(text or "")
    if not m:
        return None
    value = int(m.group(1))
    return value if 1 <= value <= 60 else None


def parse_resources(text: str):
    primos = None
    intertwined = None
    m = PRIMO_RE.search(text or "")
    if m:
        primos = int(m.group(1))
    m = IF_RE.search(text or "")
    if m:
        intertwined = int(m.group(1))
    pulls = None
    if primos is not None or intertwined is not None:
        pulls = (primos or 0) / 160 + (intertwined or 0)
    return primos, intertwined, pulls


def count_terms(text: str, terms: list[str]) -> int:
    t = (text or "").lower()
    return sum(1 for term in terms if term in t)


def infer_features(text: str):
    lower = (text or "").lower()
    c6_names = [clean_text(m.group(1)) for m in C6_RE.finditer(text or "")]
    c6r1_names = [clean_text(m.group(1)) for m in C6R1_RE.finditer(text or "")]
    limited_c6_count = len(set(x.lower() for x in c6_names))
    c6r1_count = len(set(x.lower() for x in c6r1_names))
    return {
        "limited_c6_count": limited_c6_count,
        "c6r1_count": c6r1_count,
        "multi_c6": limited_c6_count >= 2,
        "legacy_hits": count_terms(text, LEGACY_TERMS),
        "history_hits": count_terms(text, HISTORY_TERMS),
        "discovery_hits": count_terms(text, DISCOVERY_TERMS),
        "resource_hits": count_terms(text, RESOURCE_TERMS),
    }


def infer_external_id(platform: str, url: str, text: str = "") -> str | None:
    if platform.lower() == "playerauctions":
        m = re.search(r"/genshin-impact-account/(\d+)a", url)
        if m:
            return m.group(1)
    if platform.lower() == "zeusx":
        # ZeusX detail URLs vary; keep a stable URL-derived key when no public ID is obvious.
        path = urlparse(url).path.rstrip("/")
        if path:
            return hashlib.sha1(path.encode()).hexdigest()[:16]
    m = re.search(r"\b(?:listing|offer|item)[-_ ]?(?:id)?[:# ]*(\d{5,})\b", text or "", re.I)
    return m.group(1) if m else None
