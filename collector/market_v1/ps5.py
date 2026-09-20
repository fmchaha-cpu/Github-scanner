from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urljoin

import httpx
import yaml
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from .models import utcnow_iso


PS5Model = Literal["disc", "digital"]
PS5Condition = Literal["new", "certified_refurbished"]

BLOCKED_MARKERS = (
    "captcha",
    "access denied",
    "cloudflare ray id",
    "verify you are human",
    "just a moment",
)
EXCLUDED_TITLE_TERMS = (
    "controller",
    "dualsense",
    "cover",
    "konsolen-cover",
    "disc drive",
    "disc-laufwerk",
    "headset",
    "playstation portal",
    "standfuß",
    "vertical stand",
    "ps vr",
    "playstation vr",
)
PRICE_RE = re.compile(r"(?<!\d)([2-8]\d{2}(?:[.,]\d{1,2})?)\s*(?:€|EUR)", re.I)
TITLE_PRICE_RE = re.compile(
    r"\bab\s*(?:(?:€|EUR)\s*)?([2-8]\d{2}(?:[.,]\d{1,2})?)\s*(?:€|EUR)?",
    re.I,
)
ALERTABLE_AVAILABILITY = frozenset({
    "in_stock",
    "low_stock",
    "instock",
    "limitedavailability",
    "onlineonly",
    "price_comparison",
    "preorder",
})


def _clean(value: object, limit: int = 800) -> str:
    return " ".join(str(value or "").split())[:limit]


def _number(value: object) -> float | None:
    raw = _clean(value).replace("\xa0", "").replace(" ", "")
    if not raw:
        return None
    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    try:
        value_float = float(raw)
    except ValueError:
        return None
    return value_float if 200 <= value_float <= 899 else None


def _is_ps5_console_title(title: str) -> bool:
    lowered = title.lower()
    has_ps5 = "playstation 5" in lowered or "playstation®5" in lowered or re.search(r"\bps5\b", lowered)
    return bool(has_ps5 and not any(term in lowered for term in EXCLUDED_TITLE_TERMS) and " pro" not in lowered)


def _model_from_title(title: str, default: str | None = None) -> PS5Model | None:
    lowered = title.lower()
    if "digital" in lowered or "ohne optisches" in lowered or "ohne disc" in lowered:
        return "digital"
    if "disc" in lowered or "standard edition" in lowered or "mit laufwerk" in lowered:
        return "disc"
    if default in {"disc", "digital"}:
        return default  # type: ignore[return-value]
    # Sony's unqualified current PS5 console is the disc model.
    return "disc" if "konsole" in lowered or "console" in lowered else None


def _condition_from_title(title: str, default: str | None = None) -> PS5Condition:
    lowered = title.lower()
    if "generalüberholt" in lowered or "refurbished" in lowered or "renewed" in lowered:
        return "certified_refurbished"
    if default == "certified_refurbished":
        return "certified_refurbished"
    return "new"


def _looks_refurbished(title: str) -> bool:
    lowered = title.lower()
    return any(term in lowered for term in ("generalüberholt", "refurbished", "renewed", "gebraucht", "b-ware"))


@dataclass(slots=True)
class PS5Offer:
    source: str
    url: str
    title: str
    model: PS5Model
    condition: PS5Condition
    price_eur: float
    seller: str | None = None
    availability: str = "unknown"
    observed_at: str = field(default_factory=utcnow_iso)

    @property
    def offer_key(self) -> str:
        # The watcher tracks the best German market price per selected slot, not
        # separate alerts from every comparison portal showing the same deal.
        identity = f"ps5-de|{self.model}|{self.condition}"
        return hashlib.sha256(identity.encode()).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        return {**asdict(self), "offer_key": self.offer_key}


@dataclass(slots=True)
class PS5ScanOutcome:
    scan_id: str
    started_at: str
    finished_at: str
    sources_attempted: int
    offers: list[PS5Offer]
    errors: list[str]


def _walk_json(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def _jsonld_products(html: str, source: dict[str, Any], final_url: str) -> list[PS5Offer]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[PS5Offer] = []
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            payload = json.loads(script.string or script.get_text())
        except (json.JSONDecodeError, TypeError):
            continue
        for node in _walk_json(payload):
            node_type = node.get("@type")
            if isinstance(node_type, list):
                is_product = "Product" in node_type
            else:
                is_product = node_type == "Product"
            if not is_product:
                continue
            title = _clean(node.get("name"))
            if not _is_ps5_console_title(title):
                continue
            # Only Sony's explicitly certified catalogue is trusted as refurbished.
            # Retailer marketplace B-stock/used offers are outside the user's selected scope.
            if _looks_refurbished(title) and not source.get("certified_refurbished_source", False):
                continue
            offers = node.get("offers") or {}
            offer_nodes = offers if isinstance(offers, list) else [offers]
            for offer in offer_nodes:
                if not isinstance(offer, dict):
                    continue
                price = _number(offer.get("lowPrice") or offer.get("price"))
                currency = _clean(offer.get("priceCurrency") or "EUR").upper()
                if price is None or currency != "EUR":
                    continue
                model = _model_from_title(title, source.get("model"))
                if model is None:
                    continue
                condition = _condition_from_title(title, source.get("condition"))
                seller_node = offer.get("seller") or node.get("brand")
                seller = _clean(seller_node.get("name")) if isinstance(seller_node, dict) else _clean(seller_node)
                availability = _clean(offer.get("availability") or "unknown").rsplit("/", 1)[-1].lower()
                results.append(PS5Offer(
                    source=str(source["name"]),
                    url=urljoin(final_url, str(offer.get("url") or node.get("url") or final_url)),
                    title=title,
                    model=model,
                    condition=condition,
                    price_eur=price,
                    seller=seller or None,
                    availability=availability,
                ))
    return results


def parse_idealo_product(html: str, source: dict[str, Any], final_url: str) -> list[PS5Offer]:
    structured = _jsonld_products(html, source, final_url)
    if structured:
        # AggregateOffer and duplicate Product nodes can coexist; only the lowest relevant price matters.
        best = min(structured, key=lambda row: row.price_eur)
        best.availability = "price_comparison"
        return [best]

    soup = BeautifulSoup(html, "html.parser")
    page_title = _clean(soup.title.get_text(" ", strip=True) if soup.title else "")
    match = TITLE_PRICE_RE.search(page_title)
    if not match:
        for meta in soup.select('meta[property="product:price:amount"], meta[itemprop="lowPrice"], meta[itemprop="price"]'):
            price = _number(meta.get("content"))
            if price is not None:
                match_value = price
                break
        else:
            return []
    else:
        match_value = _number(match.group(1))
    if match_value is None:
        return []

    title = str(source.get("title") or page_title.split(" ab ", 1)[0])
    model = _model_from_title(title, source.get("model"))
    if model is None:
        return []
    return [PS5Offer(
        source=str(source["name"]),
        url=final_url,
        title=title,
        model=model,
        condition=_condition_from_title(title, source.get("condition")),
        price_eur=match_value,
        seller=_clean(source.get("seller") or source.get("name") or "Preisvergleich"),
        availability="price_comparison",
    )]


def _ps_direct_availability(product: dict[str, Any], card: Any) -> str:
    stock = product.get("stock") if isinstance(product.get("stock"), dict) else {}
    status = re.sub(r"[^a-z]", "", _clean(stock.get("stockLevelStatus")).lower())
    if status == "instock":
        return "in_stock" if product.get("purchasable", True) else "unavailable"
    if status == "lowstock":
        return "low_stock" if product.get("purchasable", True) else "unavailable"
    if status == "comingsoon":
        return "coming_soon"
    if status == "outofstock":
        return "out_of_stock"

    # Browser-rendered HTML is a secondary fallback. The raw Sony page contains all
    # controls hidden, so only a control whose `hide` class was removed is trusted.
    if card.select_one(".js-coming-soon-wrpr:not(.hide)"):
        return "coming_soon"
    if card.select_one(".js-out-stock-wrpr:not(.hide), .js-currently-unavailable-wrpr:not(.hide)"):
        return "out_of_stock"
    if card.select_one(".js-add-to-cart:not(.hide), .js-login-to-purchase:not(.hide)"):
        return "in_stock"
    return "catalogued"


def _ps_direct_card_price(card: Any, product: dict[str, Any]) -> float | None:
    product_price = product.get("price") if isinstance(product.get("price"), dict) else {}
    price = _number(product_price.get("value"))
    if price is not None:
        return price

    price_node = card.select_one(".js-discounted-price:not(.hide)") or card.select_one(".js-actual-price")
    if price_node is None:
        return None
    whole = price_node.select_one(".js-actual-price-whole")
    fraction = price_node.select_one(".js-actual-price-fraction")
    if whole is not None:
        whole_text = _clean(whole.get_text(" ", strip=True))
        fraction_text = _clean(fraction.get_text(" ", strip=True)) if fraction is not None else "00"
        price = _number(f"{whole_text}.{fraction_text}")
        if price is not None:
            return price
    match = PRICE_RE.search(_clean(price_node.get_text(" ", strip=True)))
    return _number(match.group(1)) if match else None


async def fetch_playstation_direct_products(
    client: httpx.AsyncClient,
    html: str,
    final_url: str,
) -> dict[str, dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    endpoint_node = soup.select_one("[data-products-url]")
    endpoint = _clean(endpoint_node.get("data-products-url")) if endpoint_node is not None else ""
    if not endpoint:
        raise RuntimeError("PlayStation Direct product API URL missing")

    codes: list[str] = []
    for node in soup.select("[data-product-code]"):
        for code in _clean(node.get("data-product-code")).split(","):
            code = code.strip()
            if code and code not in codes and re.fullmatch(r"[A-Za-z0-9_-]+-DE", code):
                codes.append(code)
    if not codes:
        raise RuntimeError("PlayStation Direct product codes missing")

    endpoint = urljoin(final_url, endpoint).replace(":userId", "anonymous")
    if endpoint.endswith("="):
        endpoint += ",".join(codes)
        response = await client.get(endpoint, headers={"Origin": "https://direct.playstation.com", "Referer": final_url})
    else:
        response = await client.get(
            endpoint,
            params={"productCodes": ",".join(codes)},
            headers={"Origin": "https://direct.playstation.com", "Referer": final_url},
        )
    response.raise_for_status()
    payload = response.json()
    products = payload.get("products") if isinstance(payload, dict) else None
    if not isinstance(products, list) or not products:
        raise RuntimeError("PlayStation Direct product API returned no products")
    return {
        str(product["code"]): product
        for product in products
        if isinstance(product, dict) and product.get("code")
    }


def parse_playstation_direct(
    html: str,
    source: dict[str, Any],
    final_url: str,
    dynamic_products: dict[str, dict[str, Any]] | None = None,
) -> list[PS5Offer]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select(".product-card-wrapper.js-product-tile")
    if cards:
        offers: list[PS5Offer] = []
        for card in cards:
            title_node = card.select_one(".product-card-details__name")
            title = _clean(title_node.get_text(" ", strip=True) if title_node is not None else "")
            if not _is_ps5_console_title(title):
                continue
            code = _clean(card.get("data-product-code"))
            if not code:
                code_node = card.select_one("[data-product-code]")
                code = _clean(code_node.get("data-product-code")) if code_node is not None else ""
            product = (dynamic_products or {}).get(code, {})
            price = _ps_direct_card_price(card, product)
            model = _model_from_title(title)
            if price is None or model is None:
                continue
            product_link = next(
                (
                    str(link.get("href"))
                    for link in card.select("a[href]")
                    if "playstation-plus" not in str(link.get("href"))
                ),
                final_url,
            )
            offers.append(PS5Offer(
                source=str(source["name"]),
                url=urljoin(final_url, product_link),
                title=title.rstrip("* "),
                model=model,
                condition=_condition_from_title(title),
                price_eur=price,
                seller="PlayStation Direct",
                availability=_ps_direct_availability(product, card),
            ))
        if offers:
            return offers

    structured = _jsonld_products(html, source, final_url)
    if structured:
        return structured

    strings = [_clean(part) for part in soup.stripped_strings if _clean(part)]
    offers: list[PS5Offer] = []
    for index, title in enumerate(strings):
        if not _is_ps5_console_title(title):
            continue
        price: float | None = None
        for candidate in strings[index + 1:index + 8]:
            if re.search(r"\b(?:GB|TB)\b", candidate, re.I):
                continue
            direct = _number(candidate.replace("€", "").strip())
            if direct is not None and ("€" in candidate or re.fullmatch(r"[2-8]\d{2}(?:[.,]\d{1,2})?", candidate)):
                price = direct
                break
            match = PRICE_RE.search(candidate)
            if match:
                price = _number(match.group(1))
                break
        if price is None:
            continue
        model = _model_from_title(title)
        if model is None:
            continue
        offers.append(PS5Offer(
            source=str(source["name"]),
            url=final_url,
            title=title,
            model=model,
            condition=_condition_from_title(title),
            price_eur=price,
            seller="PlayStation Direct",
            availability="catalogued",
        ))
    return offers


def parse_source(
    html: str,
    source: dict[str, Any],
    final_url: str,
    dynamic_products: dict[str, dict[str, Any]] | None = None,
) -> list[PS5Offer]:
    kind = str(source.get("kind") or "jsonld")
    if kind == "idealo_product":
        return parse_idealo_product(html, source, final_url)
    if kind == "playstation_direct":
        return parse_playstation_direct(html, source, final_url, dynamic_products)
    return _jsonld_products(html, source, final_url)


def alert_tier(offer: PS5Offer, thresholds: dict[str, Any]) -> str | None:
    if not is_alertable(offer):
        return None
    condition_rules = ((thresholds.get(offer.model) or {}).get(offer.condition) or {})
    excellent = _number(condition_rules.get("excellent"))
    good = _number(condition_rules.get("good"))
    if excellent is not None and offer.price_eur <= excellent:
        return "excellent"
    if good is not None and offer.price_eur <= good:
        return "good"
    return None


def is_alertable(offer: PS5Offer) -> bool:
    return offer.availability.lower() in ALERTABLE_AVAILABILITY


class PS5Store:
    def __init__(self, path: str):
        db_path = Path(path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(db_path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS ps5_offers (
                offer_key TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                url TEXT NOT NULL,
                title TEXT NOT NULL,
                model TEXT NOT NULL,
                condition TEXT NOT NULL,
                seller TEXT,
                availability TEXT NOT NULL,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                last_price_eur REAL NOT NULL,
                lowest_price_eur REAL NOT NULL,
                last_alerted_price_eur REAL,
                last_alerted_tier TEXT
            );
            CREATE TABLE IF NOT EXISTS ps5_price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                offer_key TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                price_eur REAL NOT NULL,
                UNIQUE(offer_key, observed_at),
                FOREIGN KEY(offer_key) REFERENCES ps5_offers(offer_key) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_ps5_history_offer_time
                ON ps5_price_history(offer_key, observed_at DESC);
            CREATE TABLE IF NOT EXISTS ps5_scan_runs (
                scan_id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                finished_at TEXT NOT NULL,
                sources_attempted INTEGER NOT NULL,
                offers_found INTEGER NOT NULL,
                alerts_sent INTEGER NOT NULL,
                errors_json TEXT NOT NULL
            );
        """)
        self.db.commit()

    def observe(self, offer: PS5Offer, tier: str | None, min_drop_eur: float) -> bool:
        current = self.db.execute(
            "SELECT * FROM ps5_offers WHERE offer_key=?", (offer.offer_key,),
        ).fetchone()
        if current is None:
            self.db.execute("""
                INSERT INTO ps5_offers(
                    offer_key, source, url, title, model, condition, seller, availability,
                    first_seen, last_seen, last_price_eur, lowest_price_eur
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                offer.offer_key, offer.source, offer.url, offer.title, offer.model, offer.condition,
                offer.seller, offer.availability, offer.observed_at, offer.observed_at,
                offer.price_eur, offer.price_eur,
            ))
            price_changed = True
        else:
            price_changed = abs(float(current["last_price_eur"]) - offer.price_eur) >= 0.01
            self.db.execute("""
                UPDATE ps5_offers SET
                    source=?, url=?, title=?, seller=?, availability=?, last_seen=?, last_price_eur=?,
                    lowest_price_eur=MIN(lowest_price_eur, ?)
                WHERE offer_key=?
            """, (
                offer.source, offer.url, offer.title, offer.seller, offer.availability, offer.observed_at,
                offer.price_eur, offer.price_eur, offer.offer_key,
            ))
        if price_changed:
            self.db.execute(
                "INSERT OR IGNORE INTO ps5_price_history(offer_key, observed_at, price_eur) VALUES (?,?,?)",
                (offer.offer_key, offer.observed_at, offer.price_eur),
            )
        self.db.commit()

        if tier is None:
            return False
        if current is None or current["last_alerted_price_eur"] is None:
            return True
        previous_tier = str(current["last_alerted_tier"] or "")
        tier_improved = previous_tier == "good" and tier == "excellent"
        price_improved = offer.price_eur <= float(current["last_alerted_price_eur"]) - min_drop_eur
        return tier_improved or price_improved

    def mark_alerted(self, offer: PS5Offer, tier: str) -> None:
        self.db.execute(
            "UPDATE ps5_offers SET last_alerted_price_eur=?, last_alerted_tier=? WHERE offer_key=?",
            (offer.price_eur, tier, offer.offer_key),
        )
        self.db.commit()

    def record_scan(self, outcome: PS5ScanOutcome, alerts_sent: int) -> None:
        self.db.execute("""
            INSERT OR REPLACE INTO ps5_scan_runs(
                scan_id, started_at, finished_at, sources_attempted,
                offers_found, alerts_sent, errors_json
            ) VALUES (?,?,?,?,?,?,?)
        """, (
            outcome.scan_id, outcome.started_at, outcome.finished_at, outcome.sources_attempted,
            len(outcome.offers), alerts_sent, json.dumps(outcome.errors, ensure_ascii=False),
        ))
        self.db.commit()

    def close(self) -> None:
        self.db.close()


async def scan(config_path: str) -> tuple[PS5ScanOutcome, dict[str, Any]]:
    with open(config_path, "r", encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle) or {}
    started_at = utcnow_iso()
    errors: list[str] = []
    attempted = 0
    found: dict[str, PS5Offer] = {}
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/153 Safari/537.36",
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.7",
    }
    timeout = httpx.Timeout(float(cfg.get("timeout_seconds", 30)), connect=12)
    playwright_manager = None
    browser = None
    browser_context = None

    async def fetch(client: httpx.AsyncClient, source: dict[str, Any]) -> tuple[str, str]:
        nonlocal playwright_manager, browser, browser_context
        url = str(source["url"])
        http_error: Exception | None = None
        try:
            response = await client.get(url)
            response.raise_for_status()
            lowered = response.text.lower()
            if any(marker in lowered for marker in BLOCKED_MARKERS):
                raise RuntimeError("public page returned an anti-bot/interstitial page")
            return response.text, str(response.url)
        except Exception as exc:
            http_error = exc
        if not source.get("use_browser_fallback", True):
            raise http_error

        if browser_context is None:
            playwright_manager = await async_playwright().start()
            browser = await playwright_manager.chromium.launch(headless=True)
            browser_context = await browser.new_context(user_agent=headers["User-Agent"], locale="de-DE")
        page = await browser_context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=int(timeout.read * 1000))
            await page.wait_for_timeout(int(source.get("browser_wait_ms", 1400)))
            html = await page.content()
            body = (await page.locator("body").inner_text()).lower()
            if any(marker in body for marker in BLOCKED_MARKERS):
                raise RuntimeError("browser reached a challenge page; no bypass attempted")
            return html, page.url
        except Exception as browser_error:
            raise RuntimeError(f"HTTP failed ({http_error}); browser fallback failed ({browser_error})") from browser_error
        finally:
            await page.close()

    try:
        async with httpx.AsyncClient(headers=headers, timeout=timeout, follow_redirects=True) as client:
            for source in cfg.get("sources", []):
                if not source.get("enabled", True):
                    continue
                attempted += 1
                try:
                    html, final_url = await fetch(client, source)
                    dynamic_products = None
                    if source.get("kind") == "playstation_direct":
                        dynamic_products = await fetch_playstation_direct_products(client, html, final_url)
                    rows = parse_source(html, source, final_url, dynamic_products)
                    if not rows:
                        raise RuntimeError("no matching PS5 console price found")
                    for row in rows:
                        # Keep one best purchasable offer per selected market slot. An
                        # unavailable lower price must never hide an actionable offer.
                        slot_key = f"{row.model}|{row.condition}"
                        old = found.get(slot_key)
                        if (
                            old is None
                            or (is_alertable(row) and not is_alertable(old))
                            or (is_alertable(row) == is_alertable(old) and row.price_eur < old.price_eur)
                        ):
                            found[slot_key] = row
                except Exception as exc:
                    errors.append(f"{source.get('name', 'Unknown')}: {type(exc).__name__}: {exc}")
    finally:
        if browser_context is not None:
            await browser_context.close()
        if browser is not None:
            await browser.close()
        if playwright_manager is not None:
            await playwright_manager.stop()

    outcome = PS5ScanOutcome(
        scan_id=str(uuid.uuid4()),
        started_at=started_at,
        finished_at=utcnow_iso(),
        sources_attempted=attempted,
        offers=sorted(found.values(), key=lambda row: (row.model, row.condition, row.price_eur)),
        errors=errors,
    )
    return outcome, cfg
