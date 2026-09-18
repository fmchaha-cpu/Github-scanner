from __future__ import annotations

import asyncio
import hashlib
import re
import uuid
from urllib.parse import urljoin, urlparse

import httpx
import yaml
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from .models import ScanOutcome, WarframeFounderListing, utcnow_iso
from .policy import budget_fit


FOUNDER_RE = re.compile(r"\b(?:founder|founders|founder's|grand\s+master|master\s+founder)\b", re.I)
PRIME_PATTERNS = {
    "Excalibur Prime": re.compile(r"\bexcalibur\s+prime\b", re.I),
    "Lato Prime": re.compile(r"\blato\s+prime\b", re.I),
    "Skana Prime": re.compile(r"\bskana\s+prime\b", re.I),
}
PRICE_RE = re.compile(r"(?:(USD|EUR|GBP)\s*)?([$€£])?\s*([0-9][0-9,.]{0,9})", re.I)
BLOCKED_MARKERS = ("captcha", "access denied", "cloudflare ray id", "verify you are human", "just a moment")


def _clean(text: str, limit: int = 4000) -> str:
    return " ".join(text.split())[:limit]


def _price(text: str) -> tuple[float | None, str | None]:
    for match in PRICE_RE.finditer(text):
        prefix, symbol, number = match.groups()
        raw = number.replace(",", "")
        try:
            value = float(raw)
        except ValueError:
            continue
        if value < 10 or value > 100_000:
            continue
        raw_currency = prefix or {"$": "USD", "€": "EUR", "£": "GBP"}.get(symbol or "")
        currency = raw_currency.upper() if raw_currency else None
        if currency:
            return value, currency
    return None, None


def analyse_claim(
    platform: str, url: str, title: str, detail_text: str | None,
    seller: str | None = None, preferred_budget_max: float = 300.0,
) -> WarframeFounderListing:
    card = _clean(title)
    detail = _clean(detail_text or "", 30_000)
    combined = f"{card} {detail}"
    founder_hits = sorted({m.group(0).lower() for m in FOUNDER_RE.finditer(combined)})
    prime_items = [name for name, pattern in PRIME_PATTERNS.items() if pattern.search(combined)]
    detail_founder = bool(FOUNDER_RE.search(detail))
    detail_items = [name for name, pattern in PRIME_PATTERNS.items() if pattern.search(detail)]
    claim_evidence = bool(detail and detail_founder and detail_items)

    score = 18.0 if founder_hits else 0.0
    score += min(54.0, 18.0 * len(detail_items))
    score += 14.0 if detail_founder else 0.0
    score += 10.0 if len(detail_items) == 3 else 0.0
    score = min(100.0, score)
    price, currency = _price(combined)
    snippets = []
    for needle in ["founder", "excalibur prime", "lato prime", "skana prime"]:
        pos = detail.lower().find(needle)
        if pos >= 0:
            snippets.append(detail[max(0, pos - 70):pos + len(needle) + 90])

    return WarframeFounderListing(
        platform=platform,
        url=url,
        title=card or url,
        seller=seller,
        price_value=price,
        currency=currency,
        evidence_level="CLAIM_EVIDENCE" if claim_evidence else "POTENTIAL_LEAD",
        founder_terms=founder_hits,
        prime_items=prime_items,
        evidence_snippets=list(dict.fromkeys(snippets))[:4],
        evidence_score=score,
        detail_verified=bool(detail),
        alert_eligible=claim_evidence,
        budget_fit=budget_fit(price, preferred_budget_max),
    )


def _candidate_links(html: str, base_url: str, patterns: list[str]) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    compiled = [re.compile(p, re.I) for p in patterns]
    found: dict[str, str] = {}
    for anchor in soup.select("a[href]"):
        href = urljoin(base_url, str(anchor.get("href") or ""))
        if urlparse(href).scheme not in {"http", "https"}:
            continue
        if compiled and not any(p.search(href) for p in compiled):
            continue
        parent = anchor.find_parent(["article", "li", "div"]) or anchor
        text = _clean(parent.get_text(" ", strip=True), 1200)
        if FOUNDER_RE.search(text) or any(p.search(text) for p in PRIME_PATTERNS.values()):
            found[href.split("#", 1)[0]] = text
    return list(found.items())


async def scan(config_path: str) -> ScanOutcome:
    with open(config_path, "r", encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle) or {}
    started = utcnow_iso()
    scan_id = str(uuid.uuid4())
    results: dict[str, WarframeFounderListing] = {}
    errors: list[str] = []
    attempted = 0
    preferred_budget_max = float(cfg.get("preferred_budget_max", 300))
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/153 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.8",
    }
    timeout = httpx.Timeout(float(cfg.get("timeout_seconds", 25)), connect=12)

    playwright_manager = None
    browser = None
    browser_context = None

    async def fetch_public(client: httpx.AsyncClient, url: str, browser_fallback: bool) -> tuple[str, str]:
        nonlocal playwright_manager, browser, browser_context
        http_error: Exception | None = None
        try:
            response = await client.get(url)
            response.raise_for_status()
            lower = response.text.lower()
            if any(marker in lower for marker in BLOCKED_MARKERS):
                raise RuntimeError("public page returned an anti-bot/interstitial page")
            return response.text, str(response.url)
        except Exception as exc:
            http_error = exc
        if not browser_fallback:
            raise http_error

        if browser_context is None:
            playwright_manager = await async_playwright().start()
            browser = await playwright_manager.chromium.launch(headless=True)
            browser_context = await browser.new_context(user_agent=headers["User-Agent"], locale="en-US")
        page = await browser_context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=int(timeout.read * 1000))
            await page.wait_for_timeout(1200)
            html = await page.content()
            text = (await page.locator("body").inner_text()).lower()
            if any(marker in text for marker in BLOCKED_MARKERS):
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
                name = str(source.get("name") or "Unknown")
                try:
                    html, final_url = await fetch_public(client, str(source["url"]), bool(source.get("use_browser_fallback", True)))
                    links = _candidate_links(html, final_url, list(source.get("detail_patterns") or []))
                    limit = max(1, min(int(source.get("detail_limit", 6)), 12))
                    for url, card_text in links[:limit]:
                        await asyncio.sleep(float(source.get("request_delay_seconds", 0.8)))
                        try:
                            detail_html, detail_url = await fetch_public(client, url, bool(source.get("use_browser_fallback", True)))
                            soup = BeautifulSoup(detail_html, "html.parser")
                            detail_text = _clean(soup.get_text(" ", strip=True), 30_000)
                            row = analyse_claim(
                                name, detail_url, card_text, detail_text,
                                preferred_budget_max=preferred_budget_max,
                            )
                        except Exception as exc:
                            row = analyse_claim(name, url, card_text, None, preferred_budget_max=preferred_budget_max)
                            errors.append(f"{name} detail {url}: {type(exc).__name__}: {exc}")
                        old = results.get(row.url)
                        if old is None or row.evidence_score > old.evidence_score:
                            results[row.url] = row
                except Exception as exc:
                    errors.append(f"{name}: {type(exc).__name__}: {exc}")
    finally:
        if browser_context is not None:
            await browser_context.close()
        if browser is not None:
            await browser.close()
        if playwright_manager is not None:
            await playwright_manager.stop()

    rows = sorted(results.values(), key=lambda x: (x.alert_eligible, x.evidence_score), reverse=True)
    return ScanOutcome(
        game="warframe",
        scan_id=scan_id,
        started_at=started,
        finished_at=utcnow_iso(),
        sources_attempted=attempted,
        listings_found=len(rows),
        alert_eligible=sum(r.alert_eligible for r in rows),
        errors=errors,
        listings=rows,
    )


def stable_key(game: str, url: str, tier: str) -> str:
    return hashlib.sha256(f"{game}|{url}|{tier}".encode()).hexdigest()
