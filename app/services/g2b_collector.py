"""app/services/g2b_collector.py — 나라장터 (G2B) procurement announcement collector.

Method A: 공공데이터포털 Open API
  - Endpoint: apis.data.go.kr/1230000/BidPublicInfoService
  - Returns: structured JSON (title, budget, deadline, issuer, etc.)
  - Requires: G2B_API_KEY env var from data.go.kr

Method B: URL scraping via Playwright
  - Input: any g2b.go.kr URL or announcement number
  - Returns: full page text for RFP parsing
  - No API key required
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import re
import socket
from urllib.parse import urlparse
from dataclasses import dataclass
from typing import Any

_log = logging.getLogger("decisiondoc.g2b")

_G2B_ALLOWED_DOMAINS = {
    "g2b.go.kr", "www.g2b.go.kr",
    "apis.data.go.kr", "data.go.kr",
    "data.g2b.go.kr",
    "www.kstnet.or.kr",
}

_G2B_SEARCH_ENDPOINTS = (
    "getBidPblancListInfoServc",
    "getBidPblancListInfoThng",
    "getBidPblancListInfoCnstwk",
)
_G2B_RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
_G2B_MAX_ATTEMPTS = 3
_G2B_RETRY_BASE_DELAY_SECONDS = 0.4


def _validate_scrape_url(url: str) -> None:
    """Validate URL before fetching — prevents SSRF attacks."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"허용되지 않는 URL 스킴: {parsed.scheme}")
        hostname = (parsed.hostname or "").lower()
        if not hostname:
            raise ValueError("URL에 호스트명이 없습니다.")
        if hostname == "localhost":
            raise ValueError("내부 주소로의 접근이 차단되었습니다.")
        try:
            literal_ip = ipaddress.ip_address(hostname)
        except ValueError:
            literal_ip = None
        if literal_ip is not None:
            if (
                literal_ip.is_private
                or literal_ip.is_loopback
                or literal_ip.is_link_local
                or literal_ip.is_unspecified
            ):
                raise ValueError("내부 주소로의 접근이 차단되었습니다.")
        if hostname == "metadata.google.internal":
            raise ValueError("클라우드 메타데이터 주소가 차단되었습니다.")
        # Allow only known G2B domains
        if not any(
            hostname == d or hostname.endswith("." + d)
            for d in _G2B_ALLOWED_DOMAINS
        ):
            raise ValueError(f"허용되지 않는 도메인: {hostname}")
        # Resolve hostname and check for private IPs
        try:
            resolved_ip = socket.gethostbyname(hostname)
            ip = ipaddress.ip_address(resolved_ip)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_unspecified:
                raise ValueError(f"내부 IP 주소가 차단되었습니다: {resolved_ip}")
        except socket.gaierror:
            pass  # Can't resolve — allow (may be valid in cloud environments)
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"URL 검증 실패: {e}") from e

G2B_API_BASE = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService"


async def _request_g2b_json(
    client,
    endpoint: str,
    *,
    params: dict[str, object],
    log_context: str,
) -> dict[str, Any]:
    import httpx

    last_error: Exception | None = None
    for attempt in range(1, _G2B_MAX_ATTEMPTS + 1):
        response = await client.get(endpoint, params=params)
        try:
            response.raise_for_status()
            payload = response.json()
            return payload if isinstance(payload, dict) else {}
        except Exception as exc:
            last_error = exc
            status_code = getattr(response, "status_code", 0)
            if status_code in _G2B_RETRY_STATUS_CODES and attempt < _G2B_MAX_ATTEMPTS:
                _log.warning(
                    "[G2B] %s attempt %d/%d returned %s; retrying",
                    log_context,
                    attempt,
                    _G2B_MAX_ATTEMPTS,
                    status_code,
                )
                await asyncio.sleep(_G2B_RETRY_BASE_DELAY_SECONDS * attempt)
                continue
            raise
    if last_error is not None:
        raise last_error
    raise httpx.HTTPError(f"[G2B] {log_context} failed without a response")


@dataclass
class G2BAnnouncement:
    bid_number: str           # 입찰공고번호
    title: str                # 공고명
    issuer: str               # 공고기관
    budget: str               # 추정가격
    announcement_date: str    # 공고일시
    deadline: str             # 입찰마감일시
    bid_type: str             # 입찰방식
    category: str             # 업무구분 (용역/물품/공사)
    detail_url: str           # 상세 URL
    attachments: list[str]    # 첨부파일명 목록
    raw_text: str             # 공고 전문 (스크래핑)
    source: str               # "api" | "scrape"


async def search_announcements(
    keyword: str,
    category: str = "서비스",
    days_back: int = 7,
    max_results: int = 10,
    api_key: str = "",
) -> list[G2BAnnouncement]:
    """Search G2B announcements by keyword via Open API.

    Falls back to empty list if API key not configured.
    """
    if not api_key:
        _log.warning("[G2B] API key not configured. Set G2B_API_KEY.")
        return []

    from datetime import datetime, timedelta

    # G2B API enforces a 7-day maximum range (error code 07 otherwise)
    days_back = min(days_back, 7)

    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=days_back)

    params: dict = {
        "serviceKey": api_key,
        "type": "json",
        "numOfRows": max_results,
        "pageNo": 1,
        "inqryDiv": 1,
        "inqryBgnDt": start_dt.strftime("%Y%m%d0000"),
        "inqryEndDt": end_dt.strftime("%Y%m%d2359"),
    }

    if keyword:
        params["bidNtceNm"] = keyword

    endpoint = f"{G2B_API_BASE}/getBidPblancListInfoServc"

    try:
        import httpx

        async with httpx.AsyncClient(timeout=30) as client:
            data = await _request_g2b_json(
                client,
                endpoint,
                params=params,
                log_context="API search",
            )

            # G2B API error envelope (e.g. error code 07 = date range exceeded)
            if isinstance(data, dict) and "nkoneps.com.response.ResponseError" in data:
                err = data["nkoneps.com.response.ResponseError"]
                hdr = err.get("header", {}) if isinstance(err, dict) else {}
                _log.error(
                    "[G2B] API error %s: %s",
                    hdr.get("resultCode", "?"),
                    hdr.get("resultMsg", str(err)[:200]),
                )
                return []

            _log.warning("[G2B] Raw response keys: %s", list(data.keys()) if isinstance(data, dict) else type(data))
            _log.warning("[G2B] Response body: %s", str(data)[:500])

            items = (
                data.get("response", {})
                    .get("body", {})
                    .get("items") or []
            )
            if isinstance(items, dict):
                items = [items]

            _log.warning("[G2B] items count: %d, totalCount: %s",
                len(items),
                data.get("response", {}).get("body", {}).get("totalCount", "?")
            )

            results: list[G2BAnnouncement] = []
            for item in items or []:
                results.append(G2BAnnouncement(
                    bid_number=item.get("bidNtceNo", ""),
                    title=item.get("bidNtceNm", ""),
                    issuer=item.get("ntceInsttNm", ""),
                    budget=_format_budget(item.get("asignBdgtAmt", "")),
                    announcement_date=item.get("bidNtceDt", ""),
                    deadline=item.get("bidClseDt", ""),
                    bid_type=item.get("bidMthdNm", ""),
                    category=item.get("ntceKindNm", ""),
                    detail_url=_build_detail_url(item.get("bidNtceNo", "")),
                    attachments=[],
                    raw_text="",
                    source="api",
                ))
            return results

    except Exception as exc:
        _log.error("[G2B] API search failed: %s", exc)
        return []


async def fetch_announcement_detail(
    url_or_number: str,
    api_key: str = "",
) -> G2BAnnouncement | None:
    """Fetch full announcement details from URL or bid number.

    Supports:
    - g2b.go.kr URLs (any format)
    - Bid numbers (e.g., ``"20250317001-00"``)
    - Direct announcement text URLs
    """
    bid_number = _extract_bid_number(url_or_number)

    # Try API first if key available
    if api_key and bid_number:
        announcement = await _fetch_via_api(bid_number, api_key)
        if announcement is None:
            announcement = await _search_announcement_by_bid_number(bid_number, api_key)
        if announcement:
            scraped_text = await _scrape_announcement_text(announcement.detail_url)
            announcement.raw_text = scraped_text
            return announcement

    # Fall back to scraping
    if url_or_number.startswith("http"):
        _validate_scrape_url(url_or_number)  # Raises ValueError if invalid
        scraped_text = await _scrape_announcement_text(url_or_number)
        if scraped_text:
            return G2BAnnouncement(
                bid_number=bid_number or "",
                title=_extract_title_from_text(scraped_text),
                issuer=_extract_issuer_from_text(scraped_text),
                budget=_extract_budget_from_text(scraped_text),
                announcement_date="",
                deadline=_extract_deadline_from_text(scraped_text),
                bid_type="",
                category="",
                detail_url=url_or_number,
                attachments=[],
                raw_text=scraped_text,
                source="scrape",
            )

    return None


async def _fetch_via_api(bid_number: str, api_key: str) -> G2BAnnouncement | None:
    """Fetch single announcement detail via API."""
    params = {
        "serviceKey": api_key,
        "type": "json",
        "bidNtceNo": bid_number,
    }
    endpoint = f"{G2B_API_BASE}/getBidPblancListInfoCnstwk"

    try:
        import httpx

        async with httpx.AsyncClient(timeout=30) as client:
            data = await _request_g2b_json(
                client,
                endpoint,
                params=params,
                log_context=f"API detail fetch for {bid_number}",
            )
            item = (
                data.get("response", {})
                    .get("body", {})
                    .get("item", {})
            )
            if not item:
                return None

            return G2BAnnouncement(
                bid_number=bid_number,
                title=item.get("bidNtceNm", ""),
                issuer=item.get("ntceInsttNm", ""),
                budget=_format_budget(item.get("asignBdgtAmt", "")),
                announcement_date=item.get("bidNtceDt", ""),
                deadline=item.get("bidClseDt", ""),
                bid_type=item.get("bidMthdNm", ""),
                category=item.get("ntceKindNm", ""),
                detail_url=_build_detail_url(bid_number),
                attachments=[],
                raw_text="",
                source="api",
            )
    except Exception as exc:
        _log.error("[G2B] API detail fetch failed for %s: %s", bid_number, exc)
        return None


async def _search_announcement_by_bid_number(
    bid_number: str,
    api_key: str,
) -> G2BAnnouncement | None:
    """Search recent announcements by identifier across G2B categories.

    Some active announcements use alphanumeric identifiers such as
    ``R26BK01398367`` and are not returned by the detail endpoint used for
    numeric-style bid numbers. For those cases, fall back to recent keyword
    search and filter by exact bid number.
    """
    from datetime import datetime, timedelta

    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=7)

    try:
        import httpx

        async with httpx.AsyncClient(timeout=30) as client:
            for endpoint_name in _G2B_SEARCH_ENDPOINTS:
                params: dict = {
                    "serviceKey": api_key,
                    "type": "json",
                    "numOfRows": 20,
                    "pageNo": 1,
                    "inqryDiv": 1,
                    "inqryBgnDt": start_dt.strftime("%Y%m%d0000"),
                    "inqryEndDt": end_dt.strftime("%Y%m%d2359"),
                    "bidNtceNm": bid_number,
                }
                endpoint = f"{G2B_API_BASE}/{endpoint_name}"
                data = await _request_g2b_json(
                    client,
                    endpoint,
                    params=params,
                    log_context=f"API search fallback for {bid_number} via {endpoint_name}",
                )

                items = (
                    data.get("response", {})
                    .get("body", {})
                    .get("items")
                    or []
                )
                if isinstance(items, dict):
                    items = [items]

                for item in items:
                    if item.get("bidNtceNo", "") != bid_number:
                        continue
                    return G2BAnnouncement(
                        bid_number=bid_number,
                        title=item.get("bidNtceNm", ""),
                        issuer=item.get("ntceInsttNm", ""),
                        budget=_format_budget(item.get("asignBdgtAmt", "")),
                        announcement_date=item.get("bidNtceDt", ""),
                        deadline=item.get("bidClseDt", ""),
                        bid_type=item.get("bidMthdNm", ""),
                        category=item.get("ntceKindNm", ""),
                        detail_url=_build_detail_url(bid_number),
                        attachments=[],
                        raw_text="",
                        source="api",
                    )
    except Exception as exc:
        _log.error("[G2B] API search fallback failed for %s: %s", bid_number, exc)

    return None


async def _scrape_announcement_text(url: str) -> str:
    """Scrape announcement page text via Playwright."""
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.set_extra_http_headers({"Accept-Language": "ko-KR,ko"})

            try:
                await page.goto(url, wait_until="networkidle", timeout=30_000)
                await page.wait_for_timeout(2_000)

                text: str = await page.evaluate("""() => {
                    const remove = document.querySelectorAll(
                        'script,style,nav,header,footer,.navigation'
                    );
                    remove.forEach(el => el.remove());
                    return document.body?.innerText || '';
                }""")

                await browser.close()
                return text[:15_000] if text else ""

            except Exception as exc:
                await browser.close()
                _log.warning("[G2B] Scrape failed for %s: %s", url, exc)
                return ""

    except ImportError:
        _log.error("[G2B] Playwright not available for scraping")
        return ""


# ── Pure utility functions ────────────────────────────────────────────────────

def _extract_bid_number(url_or_number: str) -> str:
    """Extract bid number from URL or return as-is."""
    raw = url_or_number.strip()
    # Pattern: 20250317001-00 (12+ digits dash 2 digits)
    match = re.search(r"\d{12,}-\d{2}", url_or_number)
    if match:
        return match.group()
    # Pattern in URL params: bidNtceNo=...
    match = re.search(r"bidNtceNo=([^&]+)", url_or_number)
    if match:
        return match.group(1)
    # Raw bid number:
    # - legacy numeric-only style (10+ digits)
    # - newer alphanumeric registration style such as R26BK01398367
    if re.match(r"^[A-Za-z0-9]{8,}(?:-\d{2})?$", raw) and re.search(r"\d", raw):
        return raw
    return ""


def _build_detail_url(bid_number: str) -> str:
    return (
        f"https://www.g2b.go.kr/pt/menu/selectSubFrame.do"
        f"?bidNtceNo={bid_number}"
    )


def _format_budget(amount_str: str) -> str:
    """Format a raw numeric budget string to a human-readable Korean form."""
    try:
        amount = int(float(str(amount_str)))
        if amount >= 100_000_000:
            return f"{amount // 100_000_000}억원"
        elif amount >= 10_000:
            return f"{amount // 10_000}만원"
        return f"{amount:,}원"
    except (ValueError, TypeError):
        return str(amount_str) if amount_str else ""


def _extract_title_from_text(text: str) -> str:
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    for line in lines[:20]:
        if len(line) > 10 and any(k in line for k in ("사업", "구축", "용역", "서비스", "개발")):
            return line[:100]
    return lines[0][:100] if lines else ""


def _extract_issuer_from_text(text: str) -> str:
    for pattern in (r"공고기관[:\s]+([^\n]+)", r"발주기관[:\s]+([^\n]+)"):
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()[:50]
    return ""


def _extract_budget_from_text(text: str) -> str:
    for pattern in (r"추정가격[:\s]+([\d,억만원]+)", r"사업예산[:\s]+([\d,억만원]+)"):
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return ""


def _extract_deadline_from_text(text: str) -> str:
    match = re.search(
        r"입찰마감[:\s]+(\d{4}[.\-]\d{2}[.\-]\d{2}[^가-힣]{0,20})",
        text,
    )
    if match:
        return match.group(1).strip()
    return ""
