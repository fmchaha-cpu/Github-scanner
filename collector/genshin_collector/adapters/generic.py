from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, Tag
from tenacity import retry, stop_after_attempt, wait_exponential

from .base import SourceAdapter, ScanResult
from ..models import ListingObservation, CoverageRow, utcnow_iso
from ..normalize import (
    clean_text, parse_price, parse_server, parse_ar, parse_resources, parse_seller,
    parse_availability, infer_features, infer_external_id, sha256_text, security_hint,
)
from ..detector import enrich_and_score
from ..market_history import normalize_market_status, relisting_fingerprint

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/153 Safari/537.36"


class GenericMarketplaceAdapter(SourceAdapter):
    def __init__(
        self,
        name: str,
        scans: list[dict],
        detail_patterns: list[str],
        use_browser_fallback: bool = True,
        deep_verify_limit: int = 8,
        favorite_characters: list[str] | None = None,
        rotation_value: int | None = None,
    ):
        self.name = name
        self.scans = scans
        self.detail_patterns = [re.compile(p, re.I) for p in detail_patterns]
        self.use_browser_fallback = use_browser_fallback
        self.deep_verify_limit = max(0, deep_verify_limit)
        self.favorite_characters = favorite_characters or []
        self.rotation_value = datetime.now(timezone.utc).hour if rotation_value is None else rotation_value

    def _is_detail_url(self, url: str) -> bool:
        return any(p.search(url) for p in self.detail_patterns)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8), reraise=True)
    async def _http_fetch(self, url: str) -> str:
        async with httpx.AsyncClient(
            headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"},
            timeout=30,
            follow_redirects=True,
        ) as client:
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
        node: Tag | None = a
        best = clean_text(a.get_text(" ", strip=True))
        for _ in range(6):
            if not node or not isinstance(node.parent, Tag):
                break
            node = node.parent
            text = clean_text(node.get_text(" ", strip=True))
            # Keep compact cards too; many marketplaces render title/price/seller in <80 chars.
            if len(best) < len(text) <= 2600:
                best = text
            if len(text) > 2600:
                break
        return best

    @staticmethod
    def _protection(text: str) -> str | None:
        m = re.search(r"(\d{1,3})\s*(?:day|days|tage)\s+[^.]{0,50}(?:protection|schutz)", text, re.I)
        return f"{m.group(1)} days" if m else None

    @staticmethod
    def _path_key(platform: str, family: str, seed_url: str, page_label: str) -> str:
        import hashlib
        seed = hashlib.sha1(seed_url.encode("utf-8")).hexdigest()[:12]
        return f"{platform}|{family}|{seed}|{page_label}"

    @staticmethod
    def _finalize_market_meta(obs: ListingObservation) -> ListingObservation:
        status, confidence, evidence = normalize_market_status(obs)
        obs.market_status = status
        obs.status_confidence = confidence
        obs.status_evidence = evidence
        obs.relisting_fingerprint = relisting_fingerprint(obs)
        return obs

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
            seller = parse_seller(text)
            primos, intertwined, pulls = parse_resources(text)
            features = infer_features(text, self.favorite_characters)
            availability = parse_availability(text)
            instant = "instant" in text.lower() or "sofort" in text.lower()
            protection = self._protection(text)

            confidence = 68.0
            if server and price is not None:
                confidence += 8
            if availability:
                confidence += 4
            if seller:
                confidence += 4

            obs = ListingObservation(
                platform=self.name,
                external_id=infer_external_id(self.name, href, text),
                url=href,
                title=title[:1000],
                seller=seller,
                server=server,
                ar=ar,
                price_value=price,
                currency=currency,
                availability=availability,
                instant_delivery=instant,
                after_sale_protection=protection,
                raw_text=text[:12000],
                raw_hash=sha256_text(text),
                data_confidence=min(confidence, 88.0),
                security_hint=security_hint(text, protection, bool(seller)),
                primogems=primos,
                intertwined=intertwined,
                limited_pulls=pulls,
                verification_level="card",
                **features,
            )
            found[href] = self._finalize_market_meta(enrich_and_score(obs))
        return list(found.values())

    @staticmethod
    def _iter_jsonld(value):
        if isinstance(value, dict):
            yield value
            for v in value.values():
                yield from GenericMarketplaceAdapter._iter_jsonld(v)
        elif isinstance(value, list):
            for item in value:
                yield from GenericMarketplaceAdapter._iter_jsonld(item)

    def _structured_product(self, soup: BeautifulSoup) -> dict:
        result: dict[str, object] = {}
        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            raw = script.string or script.get_text()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except Exception:
                continue
            for obj in self._iter_jsonld(payload):
                typ = str(obj.get("@type", "")).lower()
                if typ == "product" and obj.get("name") and "title" not in result:
                    result["title"] = clean_text(str(obj["name"]))
                offers = obj.get("offers")
                offer_rows = offers if isinstance(offers, list) else [offers] if isinstance(offers, dict) else []
                for offer in offer_rows:
                    if offer.get("price") is not None and "price" not in result:
                        try:
                            result["price"] = float(str(offer["price"]).replace(",", "."))
                        except ValueError:
                            pass
                    if offer.get("priceCurrency") and "currency" not in result:
                        result["currency"] = str(offer["priceCurrency"]).upper()
                    if offer.get("availability") and "availability" not in result:
                        av = str(offer["availability"]).lower()
                        if "instock" in av:
                            result["availability"] = "In Stock"
                        elif "outofstock" in av or "soldout" in av:
                            result["availability"] = "Sold/Closed"
                    seller = offer.get("seller")
                    if isinstance(seller, dict) and seller.get("name") and "seller" not in result:
                        result["seller"] = clean_text(str(seller["name"]))
                seller = obj.get("seller")
                if isinstance(seller, dict) and seller.get("name") and "seller" not in result:
                    result["seller"] = clean_text(str(seller["name"]))
        return result

    @staticmethod
    def _pagination_links(current_url: str, html: str, max_links: int = 8) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        current = urlparse(current_url)
        links: list[str] = []
        for a in soup.find_all("a", href=True):
            href = urljoin(current_url, a["href"])
            parsed = urlparse(href)
            if parsed.netloc != current.netloc:
                continue
            rel = {str(x).lower() for x in (a.get("rel") or [])}
            label = clean_text(a.get_text(" ", strip=True)).lower()
            looks_page = (
                "next" in rel
                or label in {"next", "next >", ">", "›", "»"}
                or re.search(r"(?:[?&]page=\d+|/page[-/]?\d+)", href, re.I)
            )
            if looks_page and href != current_url and href not in links:
                links.append(href)
            if len(links) >= max_links:
                break
        return links

    def _parse_detail(self, original: ListingObservation, html: str) -> ListingObservation:
        card_price = original.price_value
        card_server = original.server
        card_seller = original.seller
        card_c6_count = original.limited_c6_count

        soup = BeautifulSoup(html, "html.parser")
        text = clean_text(soup.get_text(" ", strip=True))
        main_node = soup.find("main") or soup.find("article") or soup.body or soup
        main_text = clean_text(main_node.get_text(" ", strip=True))
        structured = self._structured_product(soup)
        h1 = soup.find("h1")
        title = (
            clean_text(h1.get_text(" ", strip=True)) if h1
            else str(structured.get("title") or original.title)
        )

        parsed_price, parsed_currency = parse_price(main_text)
        structured_price = structured.get("price")
        price = structured_price if structured_price is not None else parsed_price
        currency = structured.get("currency", parsed_currency)
        seller = str(structured.get("seller")) if structured.get("seller") else parse_seller(main_text)

        detail_server = parse_server(title)
        if not detail_server:
            m_server = re.search(
                r"(?:server|region)\s*[:\-]?\s*(EU|Europe|European|NA|America|American|Asia|TW|HK|MO|Taiwan|Hong Kong)\b",
                main_text,
                re.I,
            )
            if m_server:
                detail_server = parse_server(m_server.group(0))
        server = detail_server or original.server

        ar = parse_ar(f"{title} {main_text[:12000]}") or original.ar
        primos, intertwined, pulls = parse_resources(f"{title} {main_text[:16000]}")
        features = infer_features(f"{title} {main_text[:16000]}", self.favorite_characters)
        availability = (
            str(structured.get("availability"))
            if structured.get("availability")
            else parse_availability(main_text)
        )
        protection = self._protection(main_text) or original.after_sale_protection

        mismatches: list[str] = []
        if card_server and detail_server and card_server != detail_server:
            mismatches.append("server")
        if card_price is not None and price is not None and abs(card_price - float(price)) > 0.01:
            mismatches.append("price")
        if card_seller and seller and card_seller.lower() != seller.lower():
            mismatches.append("seller")
        if card_c6_count and features["limited_c6_count"] < card_c6_count:
            mismatches.append("c6")

        original.title = title[:1000] or original.title
        original.raw_text = text[:20000]
        original.raw_hash = sha256_text(text)
        original.price_value = float(price) if price is not None else original.price_value
        original.currency = str(currency) if currency else original.currency
        original.seller = seller or original.seller
        original.server = server or original.server
        original.ar = ar or original.ar
        original.primogems = primos if primos is not None else original.primogems
        original.intertwined = intertwined if intertwined is not None else original.intertwined
        original.limited_pulls = pulls if pulls is not None else original.limited_pulls
        for k, v in features.items():
            setattr(original, k, v)
        original.availability = availability or original.availability
        original.instant_delivery = original.instant_delivery or ("instant" in text.lower() or "sofort" in text.lower())
        original.after_sale_protection = protection
        original.security_hint = security_hint(text, protection, bool(original.seller))
        original.verification_level = "detail"
        original.detail_verified_at = utcnow_iso()

        merit_evidence = bool(
            original.limited_c6_count
            or original.c6r1_count
            or (original.limited_pulls is not None and original.limited_pulls >= 300)
            or original.history_hits
            or original.legacy_hits
            or original.old_alt_hits
            or original.favorite_character_names
        )
        live = availability in {"BUY NOW", "In Stock", "Available"}

        # Identity-bound verification requires evidence from the detail page itself.
        price_evidence_strong = bool(
            structured_price is not None
            or (
                parsed_price is not None
                and card_price is not None
                and abs(float(parsed_price) - float(card_price)) <= 0.01
            )
        )
        server_evidence_strong = detail_server is not None
        identity_complete = bool(
            original.external_id
            and price_evidence_strong
            and server_evidence_strong
            and bool(seller)
            and merit_evidence
        )

        if mismatches:
            original.data_confidence = min(original.data_confidence or 70, 45)
            original.identity_verified = False
            original.strict_live = False
            original.availability = "identity mismatch / unconfirmed"
            original.quality_flags.append("identity_mismatch:" + "+".join(mismatches))
        else:
            original.identity_verified = identity_complete
            original.strict_live = bool(identity_complete and live)
            if original.strict_live:
                original.data_confidence = 97.0
            elif identity_complete:
                original.data_confidence = max(original.data_confidence or 70, 93.0)
            else:
                original.data_confidence = max(original.data_confidence or 70, 88.0)
                if not seller:
                    original.quality_flags.append("detail_missing_seller")
                if not availability:
                    original.quality_flags.append("detail_missing_availability")
                if not price_evidence_strong:
                    original.quality_flags.append("detail_weak_price_evidence")
                if not server_evidence_strong:
                    original.quality_flags.append("detail_weak_server_evidence")
                if not merit_evidence:
                    original.quality_flags.append("detail_missing_merit_evidence")

        return self._finalize_market_meta(enrich_and_score(original))

    async def _deep_verify(self, rows: list[ListingObservation]) -> list[ListingObservation]:
        candidates = sorted(
            [r for r in rows if r.is_candidate],
            key=lambda r: r.collector_priority,
            reverse=True,
        )[: self.deep_verify_limit]
        by_url = {r.url: r for r in rows}
        for row in candidates:
            try:
                html, _mode = await self._fetch(row.url)
                by_url[row.url] = self._parse_detail(row, html)
            except Exception as exc:
                row.data_confidence = min(row.data_confidence or 70, 82)
                row.is_alert_candidate = False
                row.identity_verified = False
                row.strict_live = False
                row.quality_flags.append(f"detail_fetch_failed:{type(exc).__name__}")
                by_url[row.url] = self._finalize_market_meta(enrich_and_score(row))
        return list(by_url.values())

    def _rotation_active(self, spec: dict) -> bool:
        rotation = spec.get("rotation")
        if not rotation:
            return True
        mod = int(rotation.get("mod", 1))
        slot = int(rotation.get("slot", 0))
        return mod <= 1 or self.rotation_value % mod == slot

    async def scan(self) -> ScanResult:
        listings: dict[str, ListingObservation] = {}
        coverage: list[CoverageRow] = []
        errors: list[str] = []
        fetched_pages: set[str] = set()

        for spec in self.scans:
            url = spec["url"]
            family = spec.get("family", "generic")
            label = spec.get("label", url)

            if not self._rotation_active(spec):
                coverage.append(CoverageRow(
                    platform=self.name,
                    query_family=family,
                    query_text=label,
                    page_label=spec.get("page_label", "seed"),
                    path_key=self._path_key(self.name, family, url, spec.get("page_label", "seed")),
                    status="skipped:rotation",
                    result_count=0,
                ))
                continue

            max_pages = max(1, min(int(spec.get("max_pages", 1)), 6))
            queue: list[tuple[str, str]] = [(url, spec.get("page_label", "seed"))]
            page_n = 0

            while queue and page_n < max_pages:
                page_url, page_label = queue.pop(0)
                if page_url in fetched_pages:
                    continue
                fetched_pages.add(page_url)
                page_n += 1

                try:
                    html, mode = await self._fetch(page_url)
                    rows = self._parse_cards(page_url, html)
                    stable_page_label = page_label if page_n == 1 else f"auto-page-{page_n}"
                    path_key = self._path_key(self.name, family, url, stable_page_label)
                    for row in rows:
                        if path_key not in row.discovery_paths:
                            row.discovery_paths.append(path_key)
                        previous = listings.get(row.url)
                        if previous:
                            row.discovery_paths = list(dict.fromkeys(previous.discovery_paths + row.discovery_paths))
                            # Keep the richer extraction when duplicate search paths see the same URL.
                            if (previous.data_confidence or 0) > (row.data_confidence or 0):
                                previous.discovery_paths = row.discovery_paths
                                row = previous
                        listings[row.url] = row
                    coverage.append(CoverageRow(
                        platform=self.name,
                        query_family=family,
                        query_text=label,
                        page_label=stable_page_label,
                        path_key=path_key,
                        status=f"ok:{mode}",
                        result_count=len(rows),
                    ))

                    if page_n < max_pages:
                        for href in self._pagination_links(page_url, html):
                            if href not in fetched_pages and all(href != u for u, _ in queue):
                                queue.append((href, f"auto-page-{page_n + 1}"))
                except Exception as exc:
                    msg = f"{self.name}:{family}:{page_url}: {type(exc).__name__}: {exc}"
                    errors.append(msg)
                    coverage.append(CoverageRow(
                        platform=self.name,
                        query_family=family,
                        query_text=label,
                        page_label=page_label,
                        path_key=self._path_key(self.name, family, url, page_label),
                        status="error",
                        error=msg[:1000],
                    ))

        verified = await self._deep_verify(list(listings.values()))
        return ScanResult(verified, coverage, errors)
