from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import unquote, urljoin, urlparse

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

SAFE_HEADER_NAMES = (
    "content-type", "server", "retry-after", "cf-mitigated", "x-cache", "x-served-by", "x-request-id",
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
    http_probe_http_status: int | None = None
    http_probe_html_bytes: int | None = None
    http_probe_text_chars: int | None = None
    http_probe_detail_link_count: int | None = None
    http_probe_content_hash: str | None = None
    http_probe_blocked_signals: list[str] | None = None
    http_probe_final_url: str | None = None
    http_probe_unmatched_listing_like_count: int | None = None
    http_probe_sample_unmatched_listing_like_urls: list[str] | None = None
    safe_headers: dict[str, str] | None = None
    http_probe_safe_headers: dict[str, str] | None = None
    browser_early_blocked: bool = False


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
        control_verify_sample: int = 1,
        merit_verify_sample: int = 4,
        circuit_breaker_enabled: bool = True,
        circuit_breaker_blocked_threshold: int = 1,
        circuit_breaker_zero_yield_threshold: int = 4,
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
        self.control_verify_sample = max(0, control_verify_sample)
        self.merit_verify_sample = max(0, merit_verify_sample)
        self.circuit_breaker_enabled = bool(circuit_breaker_enabled)
        self.circuit_breaker_blocked_threshold = max(1, int(circuit_breaker_blocked_threshold))
        self.circuit_breaker_zero_yield_threshold = max(2, int(circuit_breaker_zero_yield_threshold))
        self.favorite_characters = favorite_characters or []
        self.rotation_value = datetime.now(timezone.utc).hour if rotation_value is None else rotation_value
        self._playwright = None
        self._browser = None
        self._context = None

    def _is_detail_url(self, url: str) -> bool:
        return any(p.search(url) for p in self.detail_patterns)

    @staticmethod
    def _generic_anchor_label(value: str) -> bool:
        low = clean_text(value).lower()
        return low in {
            "buy now", "purchase now", "view", "view offer", "view details", "details",
            "instant", "more", "open", "select", "image", "offer",
        }

    def _anchor_title(self, a: Tag) -> str:
        """Return the richest title-like label available on one product anchor.

        PlayerAuctions commonly links the same product from the title, image and BUY NOW button.
        Treating the final button anchor as the title was the main v0.8 quality regression.
        """
        candidates = [clean_text(a.get_text(" ", strip=True))]
        for attr in ("aria-label", "title"):
            if a.get(attr):
                candidates.append(clean_text(str(a.get(attr))))
        img = a.find("img")
        if img:
            for attr in ("alt", "title", "aria-label"):
                if img.get(attr):
                    candidates.append(clean_text(str(img.get(attr))))
        candidates = [c for c in candidates if c]
        if not candidates:
            return ""
        return max(candidates, key=lambda c: (not self._generic_anchor_label(c), len(c)))

    def _url_server_ar_hints(self, url: str) -> tuple[str | None, int | None]:
        """Conservative product-slug hints, currently only for PlayerAuctions.

        Examples observed in live URLs include ``eumalear-55``, ``eufemalear55``,
        ``namalear-53`` and ``asia-male-ar60``.  We only accept hints on a numeric
        PlayerAuctions product URL, never on generic navigation/category links.
        """
        if self.name.lower() != "playerauctions":
            return None, None
        path = unquote(urlparse(url).path).lower()
        if not re.search(r"/genshin-impact-account/\d+a", path):
            return None, None
        tail = path.split("/genshin-impact-account/", 1)[1]
        server: str | None = None
        ar: int | None = None
        patterns = [
            ("EU", r"(?:eu|europe)(?:[-_ ]?(?:male|female|famale))?[-_ ]?ar[-_ ]?(\d{1,2})"),
            ("NA", r"(?:na|america|american)(?:[-_ ]?(?:male|female|famale))?[-_ ]?ar[-_ ]?(\d{1,2})"),
            ("ASIA", r"asia(?:[-_ ]?(?:male|female|famale))?[-_ ]?ar[-_ ]?(\d{1,2})"),
            ("TW/HK/MO", r"(?:tw|hk|mo|taiwan|hong[-_ ]?kong)(?:[-_ ]?(?:male|female|famale))?[-_ ]?ar[-_ ]?(\d{1,2})"),
        ]
        for label, pat in patterns:
            m = re.search(pat, tail, re.I)
            if m:
                server = label
                value = int(m.group(1))
                ar = value if 1 <= value <= 60 else None
                return server, ar

        # Separate server/rank fallbacks cover slugs like ``[eu]-...-ar55`` after URL encoding.
        if re.search(r"(?:^|[^a-z])(eu|europe)(?:[^a-z]|$)", tail):
            server = "EU"
        elif re.search(r"(?:^|[^a-z])(na|america|american)(?:[^a-z]|$)", tail):
            server = "NA"
        elif re.search(r"(?:^|[^a-z])asia(?:[^a-z]|$)", tail):
            server = "ASIA"
        elif re.search(r"(?:^|[^a-z])(tw|hk|mo|taiwan|hong[-_ ]?kong)(?:[^a-z]|$)", tail):
            server = "TW/HK/MO"
        m_ar = re.search(r"(?:^|[^a-z])ar[-_ ]?(\d{1,2})(?:[^0-9]|$)", tail, re.I)
        if m_ar:
            value = int(m_ar.group(1))
            ar = value if 1 <= value <= 60 else None
        return server, ar

    def _context_server_hint(self, base_url: str) -> str | None:
        path = urlparse(base_url).path.lower()
        if self.name.lower() == "playerauctions" and re.search(r"/genshin-impact-account/eu(?:/|$)", path):
            return "EU"
        if self.name.lower() == "epicnpc" and "eu-accounts" in path:
            return "EU"
        return None

    @staticmethod
    def _title_score(title: str, obs: ListingObservation | None = None) -> float:
        text = clean_text(title)
        if not text:
            return -100.0
        low = text.lower()
        score = min(len(text), 500) / 50.0
        if low in {"buy now", "view", "details", "instant", "offer", "image"}:
            score -= 50
        if parse_server(text):
            score += 8
        if parse_ar(text) is not None:
            score += 5
        if re.search(r"\bC[1-6]\b|C6R[1-5]", text, re.I):
            score += 7
        if obs is not None:
            score += min(10, len(obs.character_tags or []))
            score += min(6, (obs.limited_c6_count or 0) * 3)
        return score

    def _merge_card_observations(self, left: ListingObservation, right: ListingObservation) -> ListingObservation:
        """Merge repeated anchors/discovery paths for the same exact product URL.

        v0.8 correctly discovered hundreds of PlayerAuctions products, but the same product can be
        linked by title/image/BUY NOW.  The old `found[href] = obs` let the last generic button
        overwrite the rich title row.  v0.9 merges evidence instead and records conflicts.
        """
        out = left.model_copy(deep=True)
        left_score = self._title_score(out.title, out)
        right_score = self._title_score(right.title, right)
        if right_score > left_score:
            out.title = right.title
            if right.field_sources.get("title"):
                out.field_sources["title"] = right.field_sources["title"]

        conflicts: list[str] = []
        for field in ("price_value", "currency", "server", "ar", "seller", "availability", "external_id"):
            lv = getattr(out, field)
            rv = getattr(right, field)
            if lv in (None, "") and rv not in (None, ""):
                setattr(out, field, rv)
                if right.field_sources.get(field.replace("price_value", "price")):
                    key = field.replace("price_value", "price")
                    out.field_sources[key] = right.field_sources[key]
            elif rv not in (None, "") and lv not in (None, ""):
                if field == "price_value":
                    try:
                        different = abs(float(lv) - float(rv)) > 0.01
                    except Exception:
                        different = lv != rv
                else:
                    different = str(lv).lower() != str(rv).lower()
                if different:
                    conflicts.append(field.replace("price_value", "price"))

        # Resource fragments can be split across different anchors/containers. Keep the richest value.
        for field in ("primogems", "intertwined", "limited_pulls"):
            lv, rv = getattr(out, field), getattr(right, field)
            if rv is not None and (lv is None or float(rv) > float(lv)):
                setattr(out, field, rv)
                if right.field_sources.get("resources"):
                    out.field_sources["resources"] = right.field_sources["resources"]

        out.instant_delivery = bool(out.instant_delivery or right.instant_delivery)
        if not out.after_sale_protection and right.after_sale_protection:
            out.after_sale_protection = right.after_sale_protection
        out.discovery_paths = list(dict.fromkeys((out.discovery_paths or []) + (right.discovery_paths or [])))
        out.quality_flags = list(dict.fromkeys((out.quality_flags or []) + (right.quality_flags or [])))
        for field, source in (right.field_sources or {}).items():
            out.field_sources.setdefault(field, source)

        raw_parts = []
        for part in (out.raw_text, right.raw_text, out.title, right.title):
            part = clean_text(part or "")
            if part and part not in raw_parts:
                raw_parts.append(part)
        combined = " | ".join(raw_parts)[:20000]
        out.raw_text = combined
        out.raw_hash = sha256_text(combined)

        # Recompute feature evidence from the union of same-product fragments.
        features = infer_features(combined, self.favorite_characters)
        for k, v in features.items():
            setattr(out, k, v)
        primos, intertwined, pulls = parse_resources(combined)
        if primos is not None and (out.primogems is None or primos > out.primogems):
            out.primogems = primos
        if intertwined is not None and (out.intertwined is None or intertwined > out.intertwined):
            out.intertwined = intertwined
        if pulls is not None and (out.limited_pulls is None or pulls > out.limited_pulls):
            out.limited_pulls = pulls

        out.data_confidence = max(float(out.data_confidence or 0), float(right.data_confidence or 0))
        out.security_hint = security_hint(combined, out.after_sale_protection, bool(out.seller))
        for field in conflicts:
            flag = f"card_conflict:{field}"
            if flag not in out.quality_flags:
                out.quality_flags.append(flag)
        if conflicts:
            out.data_confidence = min(out.data_confidence or 70, 72)
        out.parser_strategy = "anchor_merged_v09"
        out = self._finalize_market_meta(enrich_and_score(out))
        out.extraction_quality = self._extraction_quality(out)
        return out

    @staticmethod
    def _safe_headers(headers) -> dict[str, str]:
        out: dict[str, str] = {}
        for name in SAFE_HEADER_NAMES:
            try:
                value = headers.get(name)
            except Exception:
                value = None
            if value:
                out[name] = str(value)[:300]
        return out

    @staticmethod
    def _quick_block_signals(html: str) -> list[str]:
        # Only inspect user-visible text/title for block signals. Many legitimate marketplace
        # pages ship CAPTCHA/challenge library names inside scripts even when the page is usable.
        # Treating raw script source as a block signal caused false positives and prematurely
        # stopped dynamic hydration on ZeusX/PlayerUp in v0.7.
        soup = BeautifulSoup(html or "", "html.parser")
        title = clean_text(soup.title.get_text(" ", strip=True)) if soup.title else ""
        for tag in soup.find_all(["script", "style", "noscript", "template"]):
            tag.decompose()
        visible = clean_text(soup.get_text(" ", strip=True))
        low = f"{title} {visible[:30000]}".lower()
        return [name for name, terms in BLOCK_SIGNALS.items() if any(term in low for term in terms)]

    def _quick_detail_link_count(self, base_url: str, html: str) -> int:
        soup = BeautifulSoup(html or "", "html.parser")
        seen: set[str] = set()
        for a in soup.find_all("a", href=True):
            href = urljoin(base_url, a.get("href", ""))
            if self._is_detail_url(href):
                seen.add(href)
        return len(seen)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8), reraise=True)
    async def _http_fetch(self, url: str) -> tuple[str, int, int, str, dict[str, str]]:
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
            # Keep HTTP error bodies/statuses for diagnostics instead of turning every 403/429
            # into an opaque HTTPStatusError. Network/timeout failures still retry.
            r = await client.get(url)
            elapsed = int((time.perf_counter() - started) * 1000)
            return r.text, r.status_code, elapsed, str(r.url), self._safe_headers(r.headers)

    async def _ensure_browser(self):
        if self._context is not None:
            return
        from playwright.async_api import async_playwright
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)
        self._context = await self._browser.new_context(
            user_agent=UA, viewport={"width": 1440, "height": 1200}, locale="en-US"
        )

    async def _close_browser(self):
        try:
            if self._context is not None:
                await self._context.close()
        finally:
            self._context = None
        try:
            if self._browser is not None:
                await self._browser.close()
        finally:
            self._browser = None
        try:
            if self._playwright is not None:
                await self._playwright.stop()
        finally:
            self._playwright = None

    async def _browser_fetch(self, url: str) -> tuple[str, int, str, int | None, dict[str, str], bool]:
        await self._ensure_browser()
        started = time.perf_counter()
        page = await self._context.new_page()
        response = None
        early_blocked = False
        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            # Challenge pages are often obvious immediately. Returning early avoids waiting
            # ~15 seconds for a network-idle state that will never produce marketplace cards.
            await page.wait_for_timeout(550)
            html = await page.content()
            initial_block_signals = self._quick_block_signals(html)
            initial_detail_links = self._quick_detail_link_count(page.url or url, html)
            # Return early only for a real zero-yield challenge page. If listing links are already
            # present, keep waiting so seller/profile widgets and product controls can hydrate.
            if initial_block_signals and initial_detail_links == 0:
                early_blocked = True
            else:
                try:
                    await page.wait_for_load_state("networkidle", timeout=8_000)
                except Exception:
                    pass
                settle_ms = 950 if self.name.lower() in {"zeusx", "playerup"} else 650
                await page.wait_for_timeout(settle_ms)
                html = await page.content()
            final_url = page.url
            status = response.status if response is not None else None
            headers = self._safe_headers(await response.all_headers()) if response is not None else {}
        finally:
            await page.close()
        return html, int((time.perf_counter() - started) * 1000), final_url, status, headers, early_blocked

    def _looks_listing_like_url(self, href: str) -> bool:
        path = urlparse(href).path.lower()
        name = self.name.lower()
        if name == "playerauctions":
            # Category/filter URLs such as /eu/, /c6/ and /furina/ are navigation, not parser drift.
            # A real PA product URL contains a numeric offer id followed by ``a``.
            return re.search(r"/genshin-impact-account/\d+a(?:$|[!%/_-])", path, re.I) is not None
        if name in {"epicnpc", "playerup"}:
            return "/threads/" in path
        if name == "zeusx":
            return "/item/" in path or "/listing/" in path or ("/genshin-impact/" in path and "/accounts/" in path)
        return any(token in path for token in ("/offer/", "/listing/", "/threads/"))

    def _probe_html(
        self, url: str, html: str, mode: str, http_status: int | None, elapsed_ms: int,
        fallback_reason: str | None = None, final_url: str | None = None,
        safe_headers: dict[str, str] | None = None, browser_early_blocked: bool = False,
    ) -> FetchPage:
        soup = BeautifulSoup(html or "", "html.parser")
        text = clean_text(soup.get_text(" ", strip=True))
        blocked = self._quick_block_signals(html or "")
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
            safe_headers=safe_headers or {}, browser_early_blocked=browser_early_blocked,
        )

    @staticmethod
    def _page_is_suspicious(probe: FetchPage, expect_listing_links: bool) -> tuple[bool, str | None]:
        if probe.http_status is not None and probe.http_status >= 400:
            return True, f"http_status:{probe.http_status}"
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
            html, status, elapsed, final_url, headers = await self._http_fetch(url)
            http_probe = self._probe_html(
                url, html, "http", status, elapsed, final_url=final_url, safe_headers=headers
            )
            http_probe.http_probe_http_status = http_probe.http_status
            http_probe.http_probe_html_bytes = http_probe.html_bytes
            http_probe.http_probe_text_chars = http_probe.text_chars
            http_probe.http_probe_detail_link_count = http_probe.detail_link_count
            http_probe.http_probe_content_hash = http_probe.content_hash
            http_probe.http_probe_blocked_signals = list(http_probe.blocked_signals)
            http_probe.http_probe_final_url = http_probe.final_url
            http_probe.http_probe_unmatched_listing_like_count = http_probe.unmatched_listing_like_count
            http_probe.http_probe_sample_unmatched_listing_like_urls = list(http_probe.sample_unmatched_listing_like_urls or [])
            http_probe.http_probe_safe_headers = dict(http_probe.safe_headers or {})
            suspicious, reason = self._page_is_suspicious(http_probe, expect_listing_links)
            if not suspicious:
                return http_probe
            http_error = reason
        except Exception as exc:
            http_error = f"http_error:{type(exc).__name__}"

        if self.use_browser_fallback:
            html, elapsed, final_url, status, headers, early_blocked = await self._browser_fetch(url)
            browser_probe = self._probe_html(
                url, html, "browser", status, elapsed, fallback_reason=http_error, final_url=final_url,
                safe_headers=headers, browser_early_blocked=early_blocked,
            )
            if http_probe is not None:
                browser_probe.http_probe_http_status = http_probe.http_status
                browser_probe.http_probe_html_bytes = http_probe.html_bytes
                browser_probe.http_probe_text_chars = http_probe.text_chars
                browser_probe.http_probe_detail_link_count = http_probe.detail_link_count
                browser_probe.http_probe_content_hash = http_probe.content_hash
                browser_probe.http_probe_blocked_signals = list(http_probe.blocked_signals)
                browser_probe.http_probe_final_url = http_probe.final_url
                browser_probe.http_probe_unmatched_listing_like_count = http_probe.unmatched_listing_like_count
                browser_probe.http_probe_sample_unmatched_listing_like_urls = list(http_probe.sample_unmatched_listing_like_urls or [])
                browser_probe.http_probe_safe_headers = dict(http_probe.safe_headers or {})
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
        for _ in range(12):
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
                # PlayerAuctions often puts seller/profile metadata one ancestor above the
                # price + BUY NOW wrapper. Keep climbing until that profile evidence appears.
                if self.name.lower() != "playerauctions" or profile_links > 0:
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

    def _seller_from_card_with_source(
        self, node: Tag, base_url: str, detail_url: str, title: str
    ) -> tuple[str | None, str | None]:
        text = clean_text(node.get_text(" ", strip=True))
        labeled = parse_seller(text)
        if labeled:
            return labeled, "card_text_label"
        banned = {"buy now", "tradeguardian", "trade guardian", "tg free", "next", "last", "selling", "buying"}
        title_low = title.lower()
        candidates: list[str] = []
        for a in node.find_all("a", href=True):
            href = urljoin(base_url, a.get("href", ""))
            label = clean_text(a.get_text(" ", strip=True))
            if not label:
                img = a.find("img")
                label = clean_text((img.get("alt") if img else "") or a.get("aria-label") or a.get("title") or "")
            low = label.lower()
            if not label or href == detail_url or self._is_detail_url(href):
                continue
            if low in banned or low in title_low or len(label) > 50 or parse_price(label)[0] is not None:
                continue
            if self._looks_like_profile_href(href) and re.fullmatch(r"[A-Za-z0-9_. -]{2,50}", label):
                candidates.append(label)
        return (candidates[0], "profile_link") if candidates else (None, None)

    def _seller_from_detail_with_source(
        self, soup: BeautifulSoup, detail_url: str, title: str
    ) -> tuple[str | None, str | None]:
        # Detail pages often render seller identity in a sidebar outside <main>. Search the whole
        # document, but only accept labels attached to profile/store URLs to avoid nav contamination.
        banned = {"seller", "seller profile", "view profile", "profile", "shop", "store", "buy now", "contact seller"}
        for a in soup.find_all("a", href=True):
            href = urljoin(detail_url, a.get("href", ""))
            if not self._looks_like_profile_href(href):
                continue
            label = clean_text(a.get_text(" ", strip=True))
            if not label:
                img = a.find("img")
                label = clean_text((img.get("alt") if img else "") or a.get("aria-label") or a.get("title") or "")
            low = label.lower()
            if not label or low in banned or low in title.lower() or len(label) > 50:
                continue
            if re.fullmatch(r"[A-Za-z0-9_. -]{2,50}", label):
                return label, "detail_profile_link"
        # Labeled detail text is a weaker fallback than a profile URL because marketplace
        # boilerplate can contain generic phrases such as "seller verification".
        body_text = clean_text((soup.body or soup).get_text(" ", strip=True))
        labeled = parse_seller(body_text)
        if labeled:
            return labeled, "detail_text_label"
        return None, None

    def _availability_from_controls(self, soup: BeautifulSoup, detail_url: str | None = None) -> tuple[str | None, str | None]:
        # Interactive controls are much stronger live evidence than generic marketing text.
        # Ignore links that clearly point at a *different* marketplace listing so a related-items
        # carousel cannot accidentally mark the current account sold/live. Prefer positive buy
        # controls when both buy and sold labels exist elsewhere on the page.
        sold_exact = {"sold", "sold out", "listing ended", "unavailable", "out of stock"}
        buy_exact = {"buy now", "purchase now", "buy item", "buy account", "add to cart", "checkout"}
        controls: list[tuple[str, Tag]] = []
        # Native interactive controls are strongest. Some marketplaces (notably ZeusX) render
        # purchase controls as role=button or styled div/span nodes, so accept those only when
        # their visible label is an *exact* buy/sold phrase and their class/id also looks like a
        # purchase-state control. This keeps unrelated marketing text from becoming live evidence.
        native = list(soup.find_all(["button", "a", "input"]))
        semantic = list(soup.select('[role="button"]'))
        styled = []
        for node in soup.find_all(["div", "span"]):
            label = clean_text(node.get_text(" ", strip=True) or node.get("aria-label") or node.get("title") or "")
            low = label.lower().strip()
            attrs = " ".join([
                str(node.get("id") or ""),
                " ".join(str(x) for x in (node.get("class") or [])),
                str(node.get("data-testid") or ""),
            ]).lower()
            if (low in buy_exact or low in sold_exact) and re.search(r"buy|purchase|cart|checkout|sold|availability|order", attrs):
                styled.append(node)

        seen_nodes: set[int] = set()
        for node in [*native, *semantic, *styled]:
            if id(node) in seen_nodes:
                continue
            seen_nodes.add(id(node))
            if node.name == "input":
                label = clean_text(str(node.get("value") or node.get("aria-label") or ""))
            else:
                label = clean_text(node.get_text(" ", strip=True) or node.get("aria-label") or node.get("title") or "")
            low = label.lower().strip()
            if low not in buy_exact and low not in sold_exact:
                continue
            if node.name == "a" and detail_url and node.get("href"):
                href = urljoin(detail_url, str(node.get("href")))
                if self._is_detail_url(href) and href.rstrip("/") != detail_url.rstrip("/"):
                    continue
            controls.append((low, node))
        if any(low in buy_exact for low, _ in controls):
            return "BUY NOW", "detail_control"
        if any(low in sold_exact for low, _ in controls):
            return "Sold/Closed", "detail_control"
        return None, None

    def _seller_from_card(self, node: Tag, base_url: str, detail_url: str, title: str) -> str | None:
        seller, _source = self._seller_from_card_with_source(node, base_url, detail_url, title)
        return seller

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

    def _parse_cards(self, base_url: str, html: str, server_hint: str | None = None) -> list[ListingObservation]:
        soup = BeautifulSoup(html, "html.parser")
        found: dict[str, ListingObservation] = {}
        context_server = server_hint or self._context_server_hint(base_url)
        for a in soup.find_all("a", href=True):
            href = urljoin(base_url, a["href"])
            if not self._is_detail_url(href):
                continue
            text, node = self._card_for_anchor(a, base_url)
            title = self._anchor_title(a) or text[:300]
            if len(title) < 4 or self._skip_forum_non_sale(title):
                continue

            price, currency = parse_price(text)
            title_server = parse_server(title)
            url_server, url_ar = self._url_server_ar_hints(href)
            text_server = parse_server(text)
            server = title_server or text_server or url_server or context_server
            title_ar = parse_ar(title)
            text_ar = parse_ar(text)
            ar = title_ar or text_ar or url_ar
            seller, seller_source = self._seller_from_card_with_source(node, base_url, href, title)
            primos, intertwined, pulls = parse_resources(text)
            features = infer_features(text, self.favorite_characters)
            availability = parse_availability(text)
            instant = "instant" in text.lower() or "sofort" in text.lower()
            protection = self._protection(text)
            external_id = infer_external_id(self.name, href, text)

            field_sources: dict[str, str] = {"title": "anchor_text"}
            if price is not None:
                field_sources["price"] = "card_text"
            if currency:
                field_sources["currency"] = "card_text"
            if server:
                if title_server:
                    field_sources["server"] = "card_title"
                elif text_server:
                    field_sources["server"] = "card_text"
                elif url_server:
                    field_sources["server"] = "url_slug"
                else:
                    field_sources["server"] = "query_context"
            if ar is not None:
                if title_ar is not None:
                    field_sources["ar"] = "card_title"
                elif text_ar is not None:
                    field_sources["ar"] = "card_text"
                else:
                    field_sources["ar"] = "url_slug"
            if seller:
                field_sources["seller"] = seller_source or "card_text"
            if availability:
                field_sources["availability"] = "card_text"
            if external_id:
                field_sources["external_id"] = "url"
            if primos is not None or intertwined is not None or pulls is not None:
                field_sources["resources"] = "card_text"
            if features.get("limited_c6_count") or features.get("character_tags"):
                field_sources["characters"] = "card_text"

            confidence = 66.0
            if server and price is not None:
                confidence += 8
            if availability:
                confidence += 4
            if seller:
                confidence += 6
            if external_id:
                confidence += 3

            obs = ListingObservation(
                platform=self.name,
                external_id=external_id,
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
                parser_strategy="anchor_local_v09",
                field_sources=field_sources,
                **features,
            )
            obs.extraction_quality = self._extraction_quality(obs)
            obs = self._finalize_market_meta(enrich_and_score(obs))
            if href in found:
                found[href] = self._merge_card_observations(found[href], obs)
            else:
                found[href] = obs
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

        # Verification-derived flags describe one detail fetch only. Clear stale flags before
        # rebuilding them so later successful checks can actually improve the quality metrics.
        transient_prefixes = (
            "identity_mismatch:", "detail_missing_", "detail_weak_",
            "detail_fetch_failed:", "deep_verify:",
        )
        original.quality_flags = [
            f for f in original.quality_flags if not any(f.startswith(p) for p in transient_prefixes)
        ]

        soup = BeautifulSoup(html, "html.parser")
        text = clean_text(soup.get_text(" ", strip=True))
        main_node = soup.find("main") or soup.find("article") or soup.body or soup
        main_text = clean_text(main_node.get_text(" ", strip=True))
        structured = self._structured_product(soup)
        h1 = soup.find("h1")
        if h1:
            title = clean_text(h1.get_text(" ", strip=True))
            title_source = "detail_h1"
        elif structured.get("title"):
            title = str(structured.get("title"))
            title_source = "jsonld"
        else:
            title = original.title
            title_source = original.field_sources.get("title", "card_fallback")

        parsed_price, parsed_currency = parse_price(main_text)
        structured_price = structured.get("price")
        price = structured_price if structured_price is not None else parsed_price
        currency = structured.get("currency", parsed_currency)

        seller: str | None = None
        seller_source: str | None = None
        if structured.get("seller"):
            seller = str(structured.get("seller"))
            seller_source = "jsonld"
        else:
            seller, seller_source = self._seller_from_detail_with_source(soup, original.url, title)

        detail_server = parse_server(title)
        server_source: str | None = "detail_title" if detail_server else None
        if not detail_server:
            m_server = re.search(
                r"(?:server(?:\s*/\s*region)?|region)\s*[:\-]?\s*(EU|Europe|European|NA|America|American|Asia|TW|HK|MO|Taiwan|Hong Kong)\b",
                main_text,
                re.I,
            )
            if m_server:
                detail_server = parse_server(m_server.group(0))
                server_source = "detail_labeled_text"
        server = detail_server or original.server

        detail_ar = parse_ar(f"{title} {main_text[:12000]}")
        ar = detail_ar or original.ar
        primos, intertwined, pulls = parse_resources(f"{title} {main_text[:16000]}")
        features = infer_features(f"{title} {main_text[:16000]}", self.favorite_characters)
        if structured.get("availability"):
            availability = str(structured.get("availability"))
            availability_source = "jsonld"
        else:
            availability, availability_source = self._availability_from_controls(soup, original.url)
            if not availability:
                availability = parse_availability(main_text)
                availability_source = "detail_text" if availability else None
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

        field_sources = dict(original.field_sources)
        field_sources["title"] = title_source
        if price is not None:
            field_sources["price"] = "jsonld" if structured_price is not None else "detail_text"
        if currency:
            field_sources["currency"] = "jsonld" if structured.get("currency") else "detail_text"
        if seller:
            field_sources["seller"] = seller_source or "detail_text"
        if detail_server:
            field_sources["server"] = server_source or "detail_text"
        if detail_ar is not None:
            field_sources["ar"] = "detail_text"
        if primos is not None or intertwined is not None or pulls is not None:
            field_sources["resources"] = "detail_text"
        if features.get("limited_c6_count") or features.get("character_tags"):
            field_sources["characters"] = "detail_text"
        if availability:
            field_sources["availability"] = availability_source or "detail_text"
        if original.external_id:
            field_sources.setdefault("external_id", "url")

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
        original.field_sources = field_sources

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

        original.parser_strategy = "detail_structured_v09" if structured else "detail_text_v09"
        # enrich_and_score() also refreshes generic missing/not-detail flags.
        verified = self._finalize_market_meta(enrich_and_score(original))
        verified.extraction_quality = self._extraction_quality(verified)
        return verified

    def _verification_plan(self, rows: list[ListingObservation]) -> list[tuple[ListingObservation, str]]:
        candidates = sorted(
            [r for r in rows if r.is_candidate],
            key=lambda r: (r.collector_priority, -(r.price_value or 10**9)),
            reverse=True,
        )
        # v0.9 makes deep_verify_limit meaningful: reserve part of the hard cap for discovery,
        # calibration and control instead of letting a large candidate set consume every detail fetch.
        candidate_budget = min(self.deep_verify_limit, self.deep_verify_hard_cap)
        selected: list[tuple[ListingObservation, str]] = [
            (r, "candidate") for r in candidates[:candidate_budget]
        ]
        selected_urls = {r.url for r, _ in selected}
        remaining = max(0, self.deep_verify_hard_cap - len(selected))

        # Merit probes rescue potentially valuable rows whose card is incomplete (especially PA rows
        # before server/seller hydration).  Price is required so generic navigation never gets probed.
        merit_pool = [
            r for r in rows
            if r.url not in selected_urls
            and r.price_value is not None and r.price_value <= 200
            and (
                r.limited_c6_count > 0 or r.c6r1_count > 0 or r.multi_c6
                or bool(r.favorite_character_names)
                or (r.limited_pulls is not None and r.limited_pulls >= 250)
                or r.history_hits > 0 or r.legacy_hits > 0 or r.old_alt_hits > 0
                or len(r.character_tags or []) >= 4
            )
        ]
        merit_pool.sort(key=lambda r: (
            int(r.limited_c6_count > 0), int(bool(r.favorite_character_names)),
            int(r.server == "EU"), int(not r.server), int(not r.seller),
            r.collector_priority, -(r.price_value or 10**9),
        ), reverse=True)
        merit_n = min(self.merit_verify_sample, remaining)
        for row in merit_pool[:merit_n]:
            selected.append((row, "merit_probe"))
            selected_urls.add(row.url)
        remaining = max(0, self.deep_verify_hard_cap - len(selected))

        # Gap calibration deliberately targets incomplete cards. This measures whether detail pages
        # can repair missing seller/server/availability instead of only validating already-good rows.
        calibration_pool = [r for r in rows if r.url not in selected_urls]
        calibration_pool.sort(key=lambda r: (
            int(not r.seller) + int(not r.availability) + int(not r.server) + int(r.price_value is None),
            int(r.server == "EU" and (r.price_value or 10**9) <= 150),
            r.collector_priority,
        ), reverse=True)
        gap_n = min(self.calibration_verify_sample, remaining)
        for row in calibration_pool[:gap_n]:
            selected.append((row, "calibration_gap"))
            selected_urls.add(row.url)
        remaining = max(0, self.deep_verify_hard_cap - len(selected))

        # A small complete-card control sample is crucial for false-negative measurement.
        control_pool = [
            r for r in rows
            if r.url not in selected_urls and r.price_value is not None and r.server and r.seller
        ]
        control_pool.sort(key=lambda r: sha256_text(r.url))
        control_n = min(self.control_verify_sample, remaining)
        for row in control_pool[:control_n]:
            selected.append((row, "control"))
            selected_urls.add(row.url)

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
        breaker_active = False
        breaker_reason: str | None = None
        blocked_zero_streak = 0
        zero_yield_streak = 0

        try:
            for spec in self.scans:
                url = spec["url"]
                family = spec.get("family", "generic")
                label = spec.get("label", url)
                page_label_seed = spec.get("page_label", "seed")

                if not self._rotation_active(spec):
                    coverage.append(CoverageRow(
                        platform=self.name, query_family=family, query_text=label,
                        page_label=page_label_seed,
                        path_key=self._path_key(self.name, family, url, page_label_seed),
                        status="skipped:rotation", result_count=0,
                    ))
                    continue

                if breaker_active:
                    coverage.append(CoverageRow(
                        platform=self.name, query_family=family, query_text=label,
                        page_label=page_label_seed,
                        path_key=self._path_key(self.name, family, url, page_label_seed),
                        status="skipped:circuit_breaker", result_count=0,
                        circuit_breaker_reason=breaker_reason,
                    ))
                    continue

                max_pages = max(1, min(int(spec.get("max_pages", 1)), 6))
                queue: list[tuple[str, str]] = [(url, page_label_seed)]
                page_n = 0

                while queue and page_n < max_pages and not breaker_active:
                    page_url, page_label = queue.pop(0)
                    if page_url in fetched_pages:
                        continue
                    fetched_pages.add(page_url)
                    page_n += 1

                    fetched: FetchPage | None = None
                    try:
                        fetched = await self._fetch(page_url, expect_listing_links=True)
                        rows = self._parse_cards(page_url, fetched.html, server_hint=spec.get("server_hint"))
                        stable_page_label = page_label if page_n == 1 else f"auto-page-{page_n}"
                        path_key = self._path_key(self.name, family, url, stable_page_label)
                        for row in rows:
                            if path_key not in row.discovery_paths:
                                row.discovery_paths.append(path_key)
                            previous = listings.get(row.url)
                            if previous:
                                row.discovery_paths = list(dict.fromkeys(previous.discovery_paths + row.discovery_paths))
                                row = self._merge_card_observations(previous, row)
                            listings[row.url] = row

                        blocked_zero = bool(
                            len(rows) == 0
                            and (fetched.detail_link_count or 0) == 0
                            and (
                                fetched.browser_early_blocked
                                or bool(fetched.blocked_signals)
                                or (fetched.http_status is not None and fetched.http_status in {401, 403, 429})
                            )
                        )
                        if blocked_zero:
                            blocked_zero_streak += 1
                        elif rows:
                            blocked_zero_streak = 0

                        if len(rows) == 0 and (fetched.detail_link_count or 0) == 0 and not blocked_zero:
                            zero_yield_streak += 1
                        elif rows:
                            zero_yield_streak = 0

                        breaker_now = False
                        if self.circuit_breaker_enabled:
                            if blocked_zero_streak >= self.circuit_breaker_blocked_threshold:
                                breaker_now = True
                                breaker_reason = f"blocked_zero_yield:{'+'.join(fetched.blocked_signals) or fetched.http_status or 'challenge'}"
                            elif zero_yield_streak >= self.circuit_breaker_zero_yield_threshold:
                                breaker_now = True
                                breaker_reason = f"repeated_zero_yield:{zero_yield_streak}"

                        coverage_status = f"blocked:{fetched.mode}" if blocked_zero else f"ok:{fetched.mode}"
                        coverage.append(CoverageRow(
                            platform=self.name, query_family=family, query_text=label,
                            page_label=stable_page_label, path_key=path_key,
                            status=coverage_status, result_count=len(rows),
                            fetch_mode=fetched.mode, http_status=fetched.http_status, elapsed_ms=fetched.elapsed_ms,
                            html_bytes=fetched.html_bytes, text_chars=fetched.text_chars, anchor_count=fetched.anchor_count,
                            detail_link_count=fetched.detail_link_count, parsed_count=len(rows), page_title=fetched.page_title,
                            content_hash=fetched.content_hash, blocked_signals=fetched.blocked_signals,
                            sample_detail_urls=fetched.sample_detail_urls, fallback_reason=fetched.fallback_reason,
                            parser_strategy="anchor_merge_v09", final_url=fetched.final_url,
                            unmatched_listing_like_count=fetched.unmatched_listing_like_count,
                            sample_unmatched_listing_like_urls=fetched.sample_unmatched_listing_like_urls or [],
                            http_probe_http_status=fetched.http_probe_http_status,
                            http_probe_html_bytes=fetched.http_probe_html_bytes,
                            http_probe_text_chars=fetched.http_probe_text_chars,
                            http_probe_detail_link_count=fetched.http_probe_detail_link_count,
                            http_probe_content_hash=fetched.http_probe_content_hash,
                            http_probe_blocked_signals=fetched.http_probe_blocked_signals or [],
                            http_probe_final_url=fetched.http_probe_final_url,
                            http_probe_unmatched_listing_like_count=fetched.http_probe_unmatched_listing_like_count,
                            http_probe_sample_unmatched_listing_like_urls=fetched.http_probe_sample_unmatched_listing_like_urls or [],
                            safe_headers=fetched.safe_headers or {},
                            http_probe_safe_headers=fetched.http_probe_safe_headers or {},
                            browser_early_blocked=fetched.browser_early_blocked,
                            circuit_breaker_triggered=breaker_now,
                            circuit_breaker_reason=breaker_reason if breaker_now else None,
                        ))

                        if breaker_now:
                            breaker_active = True
                            queue.clear()
                            continue

                        if page_n < max_pages:
                            for href in self._pagination_links(page_url, fetched.html):
                                if href not in fetched_pages and all(href != u for u, _ in queue):
                                    queue.append((href, f"auto-page-{page_n + 1}"))
                    except Exception as exc:
                        msg = f"{self.name}:{family}:{page_url}: {type(exc).__name__}: {exc}"
                        errors.append(msg)
                        error_row = CoverageRow(
                            platform=self.name, query_family=family, query_text=label, page_label=page_label,
                            path_key=self._path_key(self.name, family, url, page_label),
                            status="error", error=msg[:1000],
                        )
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
                            error_row.parser_strategy = "anchor_merge_v09"
                            error_row.final_url = fetched.final_url
                            error_row.unmatched_listing_like_count = fetched.unmatched_listing_like_count
                            error_row.sample_unmatched_listing_like_urls = list(fetched.sample_unmatched_listing_like_urls or [])
                            error_row.http_probe_http_status = fetched.http_probe_http_status
                            error_row.http_probe_html_bytes = fetched.http_probe_html_bytes
                            error_row.http_probe_text_chars = fetched.http_probe_text_chars
                            error_row.http_probe_detail_link_count = fetched.http_probe_detail_link_count
                            error_row.http_probe_content_hash = fetched.http_probe_content_hash
                            error_row.http_probe_blocked_signals = list(fetched.http_probe_blocked_signals or [])
                            error_row.http_probe_final_url = fetched.http_probe_final_url
                            error_row.http_probe_unmatched_listing_like_count = fetched.http_probe_unmatched_listing_like_count
                            error_row.http_probe_sample_unmatched_listing_like_urls = list(fetched.http_probe_sample_unmatched_listing_like_urls or [])
                            error_row.safe_headers = dict(fetched.safe_headers or {})
                            error_row.http_probe_safe_headers = dict(fetched.http_probe_safe_headers or {})
                            error_row.browser_early_blocked = fetched.browser_early_blocked
                        coverage.append(error_row)
        finally:
            await self._close_browser()

        verified = await self._deep_verify(list(listings.values()))
        # Deep verification may lazily open a browser after the index-session close above. Close it again.
        await self._close_browser()
        return ScanResult(verified, coverage, errors)
