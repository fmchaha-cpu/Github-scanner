from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
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

BLOCK_SIGNALS = {
    "captcha": ("captcha", "recaptcha", "hcaptcha"),
    "human_check": ("verify you are human", "are you a human", "checking your browser"),
    "access_denied": ("access denied", "request blocked", "temporarily blocked"),
    "challenge": ("cf-chl-", "challenge-platform", "just a moment..."),
}

PROFILE_HREF_PATTERNS = (
    "/members/", "/member/", "/users/", "/user/", "/seller/", "/store/", "/profile/",
)


@dataclass
class FetchPage:
    html: str
    mode: str
    http_status: int | None
    elapsed_ms: int
    html_bytes: int
    text_chars: int
    anchor_count: int
    detail_link_count: int
    page_title: str | None
    content_hash: str
    blocked_signals: list[str]
    sample_detail_urls: list[str]
    final_url: str | None = None
    unmatched_listing_like_count: int = 0
    sample_unmatched_listing_like_urls: list[str] | None = None
    fallback_reason: str | None = None
    http_probe_html_bytes: int | None = None
    http_probe_text_chars: int | None = None
    http_probe_detail_link_count: int | None = None
    http_probe_content_hash: str | None = None
    http_probe_blocked_signals: list[str] | None = None
    http_probe_final_url: str | None = None
    http_probe_unmatched_listing_like_count: int | None = None
    http_probe_sample_unmatched_listing_like_urls: list[str] | None = None


class GenericMarketplaceAdapter(SourceAdapter):
    def __init__(
        self,
        name: str,
        scans: list[dict],
        detail_patterns: list[str],
        use_browser_fallback: bool = True,
        deep_verify_limit: int = 8,
        deep_verify_hard_cap: int = 16,
        calibration_verify_sample: int = 2,
        favorite_characters: list[str] | None = None,
        rotation_value: int | None = None,
    ):
        self.name = name
        self.scans = scans
        self.detail_patterns = [re.compile(p, re.I) for p in detail_patterns]
        self.use_browser_fallback = use_browser_fallback
        self.deep_verify_limit = max(0, deep_verify_limit)
        self.deep_verify_hard_cap = max(self.deep_verify_limit, deep_verify_hard_cap)
        self.calibration_verify_sample = max(0, calibration_verify_sample)
        self.favorite_characters = favorite_characters or []
        self.rotation_value = datetime.now(timezone.utc).hour if rotation_value is None else rotation_value

    def _is_detail_url(self, url: str) -> bool:
        return any(p.search(url) for p in self.detail_patterns)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8), reraise=True)
    async def _http_fetch(self, url: str) -> tuple[str, int, int, str]:
        started = time.perf_counter()
        async with httpx.AsyncClient(
            headers={
                "User-Agent": UA,
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
            timeout=30,
            follow_redirects=True,
        ) as client:
            r = await client.get(url)
            r.raise_for_status()
            elapsed = int((time.perf_counter() - started) * 1000)
            return r.text, r.status_code, elapsed, str(r.url)

    async def _browser_fetch(self, url: str) -> tuple[str, int, str]:
        from playwright.async_api import async_playwright
        started = time.perf_counter()
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(user_agent=UA, viewport={"width": 1440, "height": 1200})
            await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            try:
                await page.wait_for_load_state("networkidle", timeout=15_000)
            except Exception:
                pass
            # A short settle helps marketplaces that hydrate cards immediately after DOMContentLoaded.
            await page.wait_for_timeout(900)
            html = await page.content()
            final_url = page.url
            await browser.close()
        return html, int((time.perf_counter() - started) * 1000), final_url

    def _looks_listing_like_url(self, href: str) -> bool:
        path = urlparse(href).path.lower()
        name = self.name.lower()
        if name == "playerauctions":
            return "/genshin-impact-account/" in path and path.rstrip("/") != "/genshin-impact-account"
        if name in {"epicnpc", "playerup"}:
            return "/threads/" in path
        if name == "zeusx":
            return "/item/" in path or "/listing/" in path or ("/genshin-impact/" in path and "/accounts/" in path)
        return any(token in path for token in ("/offer/", "/listing/", "/threads/"))

    def _probe_html(self, url: str, html: str, mode: str, http_status: int | None, elapsed_ms: int, fallback_reason: str | None = None, final_url: str | None = None) -> FetchPage:
        soup = BeautifulSoup(html or "", "html.parser")
        text = clean_text(soup.get_text(" ", strip=True))
        low = (html or "").lower() + " " + text.lower()[:12000]
        blocked = [name for name, terms in BLOCK_SIGNALS.items() if any(term in low for term in terms)]
        anchors = soup.find_all("a", href=True)
        detail_urls: list[str] = []
        unmatched_listing_like: list[str] = []
        base_for_links = final_url or url
        for a in anchors:
            href = urljoin(base_for_links, a.get("href", ""))
            if self._is_detail_url(href):
                if href not in detail_urls:
                    detail_urls.append(href)
            elif self._looks_listing_like_url(href) and href not in unmatched_listing_like:
                unmatched_listing_like.append(href)
        title = clean_text(soup.title.get_text(" ", strip=True)) if soup.title else None
        return FetchPage(
            html=html or "", mode=mode, http_status=http_status, elapsed_ms=elapsed_ms,
            html_bytes=len((html or "").encode("utf-8", errors="ignore")),
            text_chars=len(text), anchor_count=len(anchors), detail_link_count=len(detail_urls),
            page_title=title[:300] if title else None, content_hash=sha256_text(html or ""),
            blocked_signals=blocked, sample_detail_urls=detail_urls[:5], final_url=final_url or url,
            unmatched_listing_like_count=len(unmatched_listing_like),
            sample_unmatched_listing_like_urls=unmatched_listing_like[:5], fallback_reason=fallback_reason,
        )

    @staticmethod
    def _page_is_suspicious(probe: FetchPage, expect_listing_links: bool) -> tuple[bool, str | None]:
        if probe.blocked_signals:
            return True, "blocked_or_challenge:" + "+".join(probe.blocked_signals)
        if probe.html_bytes < 5000 or probe.text_chars < 800:
            return True, "short_or_empty_html"
        if expect_listing_links and probe.detail_link_count == 0:
            return True, "zero_detail_links"
        return False, None

    async def _fetch(self, url: str, expect_listing_links: bool = False) -> FetchPage:
        http_probe: FetchPage | None = None
        http_error: str | None = None
        try:
            html, status, elapsed, final_url = await self._http_fetch(url)
            http_probe = self._probe_html(url, html, "http", status, elapsed, final_url=final_url)
            http_probe.http_probe_html_bytes = http_probe.html_bytes
            http_probe.http_probe_text_chars = http_probe.text_chars
            http_probe.http_probe_detail_link_count = http_probe.detail_link_count
            http_probe.http_probe_content_hash = http_probe.content_hash
            http_probe.http_probe_blocked_signals = list(http_probe.blocked_signals)
            http_probe.http_probe_final_url = http_probe.final_url
            http_probe.http_probe_unmatched_listing_like_count = http_probe.unmatched_listing_like_count
            http_probe.http_probe_sample_unmatched_listing_like_urls = list(http_probe.sample_unmatched_listing_like_urls or [])
            suspicious, reason = self._page_is_suspicious(http_probe, expect_listing_links)
            if not suspicious:
                return http_probe
            http_error = reason
        except Exception as exc:
            http_error = f"http_error:{type(exc).__name__}"

        if self.use_browser_fallback:
            html, elapsed, final_url = await self._browser_fetch(url)
            browser_probe = self._probe_html(url, html, "browser", None, elapsed, fallback_reason=http_error, final_url=final_url)
            if http_probe is not None:
                browser_probe.http_probe_html_bytes = http_probe.html_bytes
                browser_probe.http_probe_text_chars = http_probe.text_chars
                browser_probe.http_probe_detail_link_count = http_probe.detail_link_count
                browser_probe.http_probe_content_hash = http_probe.content_hash
                browser_probe.http_probe_blocked_signals = list(http_probe.blocked_signals)
                browser_probe.http_probe_final_url = http_probe.final_url
                browser_probe.http_probe_unmatched_listing_like_count = http_probe.unmatched_listing_like_count
                browser_probe.http_probe_sample_unmatched_listing_like_urls = list(http_probe.sample_unmatched_listing_like_urls or [])
            # If both paths are weak, still retain the richer page for diagnostics instead of hiding the failure.
            if http_probe and browser_probe.detail_link_count < http_probe.detail_link_count and not browser_probe.blocked_signals:
                http_probe.fallback_reason = f"browser_worse:{http_error or 'unknown'}"
                return http_probe
            return browser_probe

        if http_probe is not None:
            http_probe.mode = "http-suspicious"
            http_probe.fallback_reason = http_error
            return http_probe
        raise RuntimeError("fetch_failed")

    def _card_node_for_anchor(self, a: Tag, base_url: str) -> Tag:
        node: Tag = a
        best: Tag = a
        best_score = -1.0
        target = urljoin(base_url, a.get("href", ""))
        for _ in range(8):
            if not isinstance(node, Tag):
                break
            text = clean_text(node.get_text(" ", strip=True))
            if len(text) > 4200:
                break
            detail_urls = {
                urljoin(base_url, x.get("href", ""))
                for x in node.find_all("a", href=True)
                if self._is_detail_url(urljoin(base_url, x.get("href", "")))
            }
            other_details = len({u for u in detail_urls if u != target})
            price, _ = parse_price(text)
            profile_links = sum(
                1 for x in node.find_all("a", href=True)
                if any(p in urlparse(urljoin(base_url, x.get("href", ""))).path.lower() for p in PROFILE_HREF_PATTERNS)
            )
            metadata = int(price is not None) + int(profile_links > 0) + int(parse_availability(text) is not None)
            # Strongly prefer the smallest ancestor that contains this listing's metadata but no neighboring listing.
            score = metadata * 4 - other_details * 12 - max(0, len(text) - 1400) / 700
            if score > best_score and (other_details == 0 or best_score < 0):
                best, best_score = node, score
            if other_details > 0 and best_score >= 0:
                break
            if metadata >= 2 and other_details == 0:
                best = node
                break
            if not isinstance(node.parent, Tag):
                break
            node = node.parent
        return best

    def _card_for_anchor(self, a: Tag, base_url: str) -> tuple[str, Tag]:
        node = self._card_node_for_anchor(a, base_url)
        return clean_text(node.get_text(" ", strip=True)), node

    @staticmethod
    def _looks_like_profile_href(href: str) -> bool:
        path = urlparse(href).path.lower()
        return any(p in path for p in PROFILE_HREF_PATTERNS)

    def _seller_from_card(self, node: Tag, base_url: str, detail_url: str, title: str) -> str | None:
        text = clean_text(node.get_text(" ", strip=True))
        labeled = parse_seller(text)
        if labeled:
            return labeled
        banned = {"buy now", "tradeguardian", "trade guardian", "tg free", "next", "last", "selling", "buying"}
        title_low = title.lower()
        candidates: list[str] = []
        for a in node.find_all("a", href=True):
            href = urljoin(base_url, a.get("href", ""))
            label = clean_text(a.get_text(" ", strip=True))
            low = label.lower()
            if not label or href == detail_url or self._is_detail_url(href):
                continue
            if low in banned or low in title_low or len(label) > 50 or parse_price(label)[0] is not None:
                continue
            if self._looks_like_profile_href(href) and re.fullmatch(r"[A-Za-z0-9_. -]{2,50}", label):
                candidates.append(label)
        return candidates[0] if candidates else None

    def _skip_forum_non_sale(self, title: str) -> bool:
        if self.name.lower() not in {"epicnpc", "playerup"}:
            return False
        low = clean_text(title).lower()
        return bool(re.match(
            r"^(?:(?:\[(?:wtb|buying|buyer|looking)\])\s*|wtb\b|buying\b|buyer\b|looking\s+for\b|searching\s+for\b|want\s+to\s+buy\b|buy\s+account\b)",
            low,
        ))

    @staticmethod
    def _extraction_quality(obs: ListingObservation) -> float:
        checks = [
            obs.price_value is not None, bool(obs.currency), bool(obs.server), bool(obs.external_id),
            bool(obs.seller), bool(obs.availability), bool(obs.title),
        ]
        base = 100.0 * sum(checks) / len(checks)
        if obs.verification_level == "detail":
            base += 5
        if obs.quality_flags:
            base -= min(20, 3 * len(obs.quality_flags))
        return round(max(0.0, min(100.0, base)), 1)

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
            text, node = self._card_for_anchor(a, base_url)
            title = clean_text(a.get_text(" ", strip=True)) or text[:300]
            if len(title) < 4 or self._skip_forum_non_sale(title):
                continue

            price, currency = parse_price(text)
            server = parse_server(title) or parse_server(text)
            ar = parse_ar(title) or parse_ar(text)
            seller = self._seller_from_card(node, base_url, href, title)
            primos, intertwined, pulls = parse_resources(text)
            features = infer_features(text, self.favorite_characters)
            availability = parse_availability(text)
            instant = "instant" in text.lower() or "sofort" in text.lower()
            protection = self._protection(text)

            confidence = 66.0
            if server and price is not None:
                confidence += 8
            if availability:
                confidence += 4
            if seller:
                confidence += 6
            if infer_external_id(self.name, href, text):
                confidence += 3

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
                parser_strategy="anchor_local_v06",
                **features,
            )
            obs.extraction_quality = self._extraction_quality(obs)
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
        seller = str(structured.get("seller")) if structured.get("seller") else (parse_seller(main_text) or self._seller_from_card(main_node, original.url, original.url, title))

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

        original.parser_strategy = "detail_structured_v06" if structured else "detail_text_v06"
        original.extraction_quality = self._extraction_quality(original)
        return self._finalize_market_meta(enrich_and_score(original))

    def _verification_plan(self, rows: list[ListingObservation]) -> list[tuple[ListingObservation, str]]:
        candidates = sorted(
            [r for r in rows if r.is_candidate],
            key=lambda r: (r.collector_priority, -(r.price_value or 10**9)),
            reverse=True,
        )
        candidate_limit = min(len(candidates), self.deep_verify_hard_cap)
        # Keep the configured base budget, but expand automatically when the source produces
        # more promising candidates. Hard cap prevents one marketplace from consuming the run.
        candidate_limit = min(self.deep_verify_hard_cap, max(self.deep_verify_limit, candidate_limit))
        selected: list[tuple[ListingObservation, str]] = [(r, "candidate") for r in candidates[:candidate_limit]]
        selected_urls = {r.url for r, _ in selected}

        # Calibrate on non-candidates too. Prefer rows with missing seller/availability and cheap EU rows;
        # these samples expose false negatives and parser blind spots instead of only validating winners.
        calibration_pool = [r for r in rows if r.url not in selected_urls]
        calibration_pool.sort(key=lambda r: (
            int(not r.seller) + int(not r.availability) + int(not r.server),
            int(r.server == "EU" and (r.price_value or 10**9) <= 150),
            r.collector_priority,
        ), reverse=True)
        for row in calibration_pool[: self.calibration_verify_sample]:
            selected.append((row, "calibration"))
        return selected

    async def _deep_verify(self, rows: list[ListingObservation]) -> list[ListingObservation]:
        plan = self._verification_plan(rows)
        by_url = {r.url: r for r in rows}
        for row, reason in plan:
            row.verification_reason = reason
            try:
                fetched = await self._fetch(row.url, expect_listing_links=False)
                row.detail_fetch_mode = fetched.mode
                row.detail_fetch_fallback_reason = fetched.fallback_reason
                row.detail_http_status = fetched.http_status
                row.detail_html_bytes = fetched.html_bytes
                row.detail_blocked_signals = list(fetched.blocked_signals)
                verified = self._parse_detail(row, fetched.html)
                verified.verification_reason = reason
                if f"deep_verify:{reason}" not in verified.quality_flags:
                    verified.quality_flags.append(f"deep_verify:{reason}")
                verified.extraction_quality = self._extraction_quality(verified)
                by_url[row.url] = verified
            except Exception as exc:
                row.data_confidence = min(row.data_confidence or 70, 82)
                row.is_alert_candidate = False
                row.identity_verified = False
                row.strict_live = False
                row.quality_flags.append(f"detail_fetch_failed:{type(exc).__name__}")
                row.quality_flags.append(f"deep_verify:{reason}")
                row.extraction_quality = self._extraction_quality(row)
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

                fetched: FetchPage | None = None
                try:
                    fetched = await self._fetch(page_url, expect_listing_links=True)
                    rows = self._parse_cards(page_url, fetched.html)
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
                        status=f"ok:{fetched.mode}",
                        result_count=len(rows),
                        fetch_mode=fetched.mode,
                        http_status=fetched.http_status,
                        elapsed_ms=fetched.elapsed_ms,
                        html_bytes=fetched.html_bytes,
                        text_chars=fetched.text_chars,
                        anchor_count=fetched.anchor_count,
                        detail_link_count=fetched.detail_link_count,
                        parsed_count=len(rows),
                        page_title=fetched.page_title,
                        content_hash=fetched.content_hash,
                        blocked_signals=fetched.blocked_signals,
                        sample_detail_urls=fetched.sample_detail_urls,
                        fallback_reason=fetched.fallback_reason,
                        parser_strategy="anchor_local_v06",
                        final_url=fetched.final_url,
                        unmatched_listing_like_count=fetched.unmatched_listing_like_count,
                        sample_unmatched_listing_like_urls=fetched.sample_unmatched_listing_like_urls or [],
                        http_probe_html_bytes=fetched.http_probe_html_bytes,
                        http_probe_text_chars=fetched.http_probe_text_chars,
                        http_probe_detail_link_count=fetched.http_probe_detail_link_count,
                        http_probe_content_hash=fetched.http_probe_content_hash,
                        http_probe_blocked_signals=fetched.http_probe_blocked_signals or [],
                        http_probe_final_url=fetched.http_probe_final_url,
                        http_probe_unmatched_listing_like_count=fetched.http_probe_unmatched_listing_like_count,
                        http_probe_sample_unmatched_listing_like_urls=fetched.http_probe_sample_unmatched_listing_like_urls or [],
                    ))

                    if page_n < max_pages:
                        for href in self._pagination_links(page_url, fetched.html):
                            if href not in fetched_pages and all(href != u for u, _ in queue):
                                queue.append((href, f"auto-page-{page_n + 1}"))
                except Exception as exc:
                    msg = f"{self.name}:{family}:{page_url}: {type(exc).__name__}: {exc}"
                    errors.append(msg)
                    error_row = CoverageRow(
                        platform=self.name,
                        query_family=family,
                        query_text=label,
                        page_label=page_label,
                        path_key=self._path_key(self.name, family, url, page_label),
                        status="error",
                        error=msg[:1000],
                    )
                    # Preserve fetch evidence even when parsing/pagination fails afterwards.
                    if fetched is not None:
                        error_row.fetch_mode = fetched.mode
                        error_row.http_status = fetched.http_status
                        error_row.elapsed_ms = fetched.elapsed_ms
                        error_row.html_bytes = fetched.html_bytes
                        error_row.text_chars = fetched.text_chars
                        error_row.anchor_count = fetched.anchor_count
                        error_row.detail_link_count = fetched.detail_link_count
                        error_row.parsed_count = 0
                        error_row.page_title = fetched.page_title
                        error_row.content_hash = fetched.content_hash
                        error_row.blocked_signals = list(fetched.blocked_signals)
                        error_row.sample_detail_urls = list(fetched.sample_detail_urls)
                        error_row.fallback_reason = fetched.fallback_reason
                        error_row.parser_strategy = "anchor_local_v06"
                        error_row.final_url = fetched.final_url
                        error_row.unmatched_listing_like_count = fetched.unmatched_listing_like_count
                        error_row.sample_unmatched_listing_like_urls = list(fetched.sample_unmatched_listing_like_urls or [])
                        error_row.http_probe_html_bytes = fetched.http_probe_html_bytes
                        error_row.http_probe_text_chars = fetched.http_probe_text_chars
                        error_row.http_probe_detail_link_count = fetched.http_probe_detail_link_count
                        error_row.http_probe_content_hash = fetched.http_probe_content_hash
                        error_row.http_probe_blocked_signals = list(fetched.http_probe_blocked_signals or [])
                        error_row.http_probe_final_url = fetched.http_probe_final_url
                        error_row.http_probe_unmatched_listing_like_count = fetched.http_probe_unmatched_listing_like_count
                        error_row.http_probe_sample_unmatched_listing_like_urls = list(fetched.http_probe_sample_unmatched_listing_like_urls or [])
                    coverage.append(error_row)

        verified = await self._deep_verify(list(listings.values()))
        return ScanResult(verified, coverage, errors)
