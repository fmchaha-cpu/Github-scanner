from __future__ import annotations

import asyncio
import re
from urllib.parse import urljoin
import httpx
from bs4 import BeautifulSoup, Tag
from tenacity import retry, stop_after_attempt, wait_exponential

from .base import SourceAdapter, ScanResult
from ..models import ListingObservation, CoverageRow
from ..normalize import clean_text, parse_price, parse_server, parse_ar, parse_resources, infer_features, infer_external_id, sha256_text
from ..detector import enrich_and_score

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/153 Safari/537.36"


class GenericMarketplaceAdapter(SourceAdapter):
    def __init__(self, name: str, scans: list[dict], detail_patterns: list[str], use_browser_fallback: bool = True, deep_verify_limit: int = 5):
        self.name = name
        self.scans = scans
        self.detail_patterns = [re.compile(p, re.I) for p in detail_patterns]
        self.use_browser_fallback = use_browser_fallback
        self.deep_verify_limit = deep_verify_limit

    def _is_detail_url(self, url: str) -> bool:
        return any(p.search(url) for p in self.detail_patterns)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8), reraise=True)
    async def _http_fetch(self, url: str) -> str:
        async with httpx.AsyncClient(headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}, timeout=30, follow_redirects=True) as client:
            r = await client.get(url)
            r.raise_for_status()
            return r.text

    async def _browser_fetch(self, url: str) -> str:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(user_agent=UA, viewport={"width": 1440, "height": 1200})
            await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            try:
                await page.wait_for_load_state("networkidle", timeout=15_000)
            except Exception:
                pass
            html = await page.content()
            await browser.close()
            return html

    async def _fetch(self, url: str) -> tuple[str, str]:
        try:
            html = await self._http_fetch(url)
            if len(html) >= 5000:
                return html, "http"
        except Exception:
            html = ""
        if self.use_browser_fallback:
            return await self._browser_fetch(url), "browser"
        if html:
            return html, "http-short"
        raise RuntimeError("fetch_failed")

    @staticmethod
    def _card_for_anchor(a: Tag) -> str:
        # Ascend until we capture enough surrounding text to include price/seller but avoid whole page.
        node: Tag | None = a
        best = clean_text(a.get_text(" ", strip=True))
        for _ in range(6):
            if not node or not isinstance(node.parent, Tag):
                break
            node = node.parent
            text = clean_text(node.get_text(" ", strip=True))
            if 80 <= len(text) <= 2600:
                best = text
            if len(text) > 2600:
                break
        return best

    def _parse_cards(self, base_url: str, html: str) -> list[ListingObservation]:
        soup = BeautifulSoup(html, "html.parser")
        found: dict[str, ListingObservation] = {}
        for a in soup.find_all("a", href=True):
            href = urljoin(base_url, a["href"])
            if not self._is_detail_url(href):
                continue
            text = self._card_for_anchor(a)
            title = clean_text(a.get_text(" ", strip=True)) or text[:300]
            if len(title) < 4:
                continue
            price, currency = parse_price(text)
            server = parse_server(text)
            ar = parse_ar(text)
            primos, intertwined, pulls = parse_resources(text)
            features = infer_features(text)
            availability = None
            low = text.lower()
            if "buy now" in low or "jetzt kaufen" in low:
                availability = "BUY NOW"
            elif "in stock" in low:
                availability = "In Stock"
            instant = "instant" in low or "sofort" in low
            protection = None
            m = re.search(r"(\d{1,3})\s*(?:day|days|tage)\s+[^.]{0,50}(?:protection|schutz)", text, re.I)
            if m:
                protection = f"{m.group(1)} days"
            # Card-level extraction is intentionally conservative on seller/data confidence.
            confidence = 72.0
            if server and price is not None:
                confidence += 8
            if availability:
                confidence += 5
            obs = ListingObservation(
                platform=self.name,
                external_id=infer_external_id(self.name, href, text),
                url=href,
                title=title[:1000],
                server=server,
                ar=ar,
                price_value=price,
                currency=currency,
                availability=availability,
                instant_delivery=instant,
                after_sale_protection=protection,
                raw_text=text[:12000],
                raw_hash=sha256_text(text),
                data_confidence=min(confidence, 90.0),
                primogems=primos,
                intertwined=intertwined,
                limited_pulls=pulls,
                **features,
            )
            found[href] = enrich_and_score(obs)
        return list(found.values())


    def _parse_detail(self, original: ListingObservation, html: str) -> ListingObservation:
        soup = BeautifulSoup(html, "html.parser")
        text = clean_text(soup.get_text(" ", strip=True))
        h1 = soup.find("h1")
        title = clean_text(h1.get_text(" ", strip=True)) if h1 else original.title
        price, currency = parse_price(text)
        server = parse_server(text)
        ar = parse_ar(text)
        primos, intertwined, pulls = parse_resources(text)
        features = infer_features(text)
        low = text.lower()
        availability = None
        if "buy now" in low or "jetzt kaufen" in low:
            availability = "BUY NOW"
        elif "in stock" in low:
            availability = "In Stock"
        elif any(x in low for x in ["sold out", "sold", "closed"]):
            availability = "Sold/Closed"

        mismatches = []
        if original.server and server and original.server != server:
            mismatches.append("server")
        if original.price_value is not None and price is not None and abs(original.price_value - price) > 0.01:
            mismatches.append("price")
        if original.limited_c6_count and features["limited_c6_count"] < original.limited_c6_count:
            mismatches.append("c6")

        original.title = title[:1000] or original.title
        original.raw_text = text[:20000]
        original.raw_hash = sha256_text(text)
        original.price_value = price if price is not None else original.price_value
        original.currency = currency or original.currency
        original.server = server or original.server
        original.ar = ar or original.ar
        original.primogems = primos if primos is not None else original.primogems
        original.intertwined = intertwined if intertwined is not None else original.intertwined
        original.limited_pulls = pulls if pulls is not None else original.limited_pulls
        for k, v in features.items():
            setattr(original, k, v)
        original.availability = availability or original.availability
        original.instant_delivery = original.instant_delivery or ("instant" in low or "sofort" in low)
        if mismatches:
            original.data_confidence = min(original.data_confidence or 70, 45)
            original.availability = "identity mismatch / unconfirmed"
            original.detector_reason = (original.detector_reason or "") + ",identity_mismatch:" + "+".join(mismatches)
            original.is_alert_candidate = False
        else:
            original.data_confidence = min(98.0, max(original.data_confidence or 70, 95.0 if availability else 90.0))
        return enrich_and_score(original)

    async def _deep_verify(self, rows: list[ListingObservation]) -> list[ListingObservation]:
        # Verify only highest-priority rows to keep request volume modest.
        candidates = sorted([r for r in rows if r.is_candidate], key=lambda r: r.collector_priority, reverse=True)[: self.deep_verify_limit]
        by_url = {r.url: r for r in rows}
        for row in candidates:
            try:
                html, _mode = await self._fetch(row.url)
                by_url[row.url] = self._parse_detail(row, html)
            except Exception:
                # Failure is not evidence of LIVE status. Keep card data but cap confidence.
                row.data_confidence = min(row.data_confidence or 70, 82)
                row.is_alert_candidate = False
                row.detector_reason = (row.detector_reason or "") + ",detail_fetch_failed"
                by_url[row.url] = row
        return list(by_url.values())

    async def scan(self) -> ScanResult:
        listings: dict[str, ListingObservation] = {}
        coverage: list[CoverageRow] = []
        errors: list[str] = []
        for spec in self.scans:
            url = spec["url"]
            family = spec.get("family", "generic")
            label = spec.get("label", url)
            try:
                html, mode = await self._fetch(url)
                rows = self._parse_cards(url, html)
                for row in rows:
                    listings[row.url] = row
                coverage.append(CoverageRow(
                    platform=self.name,
                    query_family=family,
                    query_text=label,
                    page_label=spec.get("page_label", "seed"),
                    status=f"ok:{mode}",
                    result_count=len(rows),
                ))
            except Exception as exc:
                msg = f"{self.name}:{family}:{url}: {type(exc).__name__}: {exc}"
                errors.append(msg)
                coverage.append(CoverageRow(
                    platform=self.name,
                    query_family=family,
                    query_text=label,
                    page_label=spec.get("page_label", "seed"),
                    status="error",
                    error=msg[:1000],
                ))
        verified = await self._deep_verify(list(listings.values()))
        return ScanResult(verified, coverage, errors)
