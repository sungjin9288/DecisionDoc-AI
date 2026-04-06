"""tests/test_g2b.py — Tests for G2B (나라장터) collector service and endpoints.

Coverage:
- _extract_bid_number: URL params, direct number, no match
- _format_budget: 억원, 만원, raw number, empty, non-numeric
- _extract_*_from_text: title, issuer, budget, deadline
- search_announcements: no API key → empty, API success (mock), API error
- fetch_announcement_detail: URL scrape path, bid+key API path, not found
- /g2b/status: key configured / not configured
- /g2b/search: returns results, missing q → 422
- /g2b/fetch: 200 with fields, not found → 404
"""
from __future__ import annotations

import builtins
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from tests.async_helper import run_async

# ── Test client helper ────────────────────────────────────────────────────────

def _make_client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.delenv("DECISIONDOC_API_KEY",  raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    # Always clear G2B_API_KEY so tests are hermetic.
    # Tests that need it set explicitly via monkeypatch.setenv AFTER this call.
    monkeypatch.delenv("G2B_API_KEY", raising=False)
    from app.main import create_app
    return TestClient(create_app())


# ── _extract_bid_number ───────────────────────────────────────────────────────

class TestExtractBidNumber:
    def _call(self, value: str) -> str:
        from app.services.g2b_collector import _extract_bid_number
        return _extract_bid_number(value)

    def test_url_param_format(self):
        url = "https://www.g2b.go.kr/pt/menu/selectSubFrame.do?bidNtceNo=20250317001-00&other=1"
        assert self._call(url) == "20250317001-00"

    def test_direct_number_long(self):
        assert self._call("20250317001-00") == "20250317001-00"

    def test_direct_alphanumeric_bid_number(self):
        assert self._call("R26BK01398367") == "R26BK01398367"

    def test_raw_digits_only(self):
        # 10+ digits treated as a bid number
        assert self._call("2025031700") == "2025031700"

    def test_short_string_returns_empty(self):
        assert self._call("12345") == ""

    def test_plain_text_no_match(self):
        assert self._call("국가 디지털 전환 사업") == ""

    def test_url_without_bid_number(self):
        assert self._call("https://example.com/page?foo=bar") == ""


# ── _format_budget ────────────────────────────────────────────────────────────

class TestFormatBudget:
    def _call(self, v) -> str:
        from app.services.g2b_collector import _format_budget
        return _format_budget(v)

    def test_billions(self):
        assert self._call("500000000") == "5억원"

    def test_ten_thousands(self):
        assert self._call("50000") == "5만원"

    def test_small_number(self):
        assert self._call("9999") == "9,999원"

    def test_empty_string(self):
        assert self._call("") == ""

    def test_non_numeric(self):
        # Should return the original string on conversion failure
        result = self._call("미정")
        assert result == "미정"

    def test_float_string(self):
        assert self._call("500000000.0") == "5억원"


# ── _extract_*_from_text ──────────────────────────────────────────────────────

class TestExtractFromText:
    def test_extract_issuer_공고기관(self):
        from app.services.g2b_collector import _extract_issuer_from_text
        text = "공고기관: 행정안전부\n사업명: 디지털 전환"
        assert _extract_issuer_from_text(text) == "행정안전부"

    def test_extract_issuer_발주기관_fallback(self):
        from app.services.g2b_collector import _extract_issuer_from_text
        text = "발주기관: 국토교통부\n기타 정보"
        assert _extract_issuer_from_text(text) == "국토교통부"

    def test_extract_issuer_not_found(self):
        from app.services.g2b_collector import _extract_issuer_from_text
        assert _extract_issuer_from_text("관련 없는 텍스트") == ""

    def test_extract_budget_추정가격(self):
        from app.services.g2b_collector import _extract_budget_from_text
        text = "추정가격: 5억원\n사업명: 구축 사업"
        assert _extract_budget_from_text(text) == "5억원"

    def test_extract_budget_사업예산(self):
        from app.services.g2b_collector import _extract_budget_from_text
        text = "사업예산: 300만원"
        assert _extract_budget_from_text(text) == "300만원"

    def test_extract_budget_not_found(self):
        from app.services.g2b_collector import _extract_budget_from_text
        assert _extract_budget_from_text("금액 정보 없음") == ""

    def test_extract_deadline(self):
        from app.services.g2b_collector import _extract_deadline_from_text
        text = "입찰마감: 2025-12-31 17:00"
        result = _extract_deadline_from_text(text)
        assert "2025-12-31" in result

    def test_extract_deadline_dot_format(self):
        from app.services.g2b_collector import _extract_deadline_from_text
        text = "입찰마감: 2025.12.31 18:00"
        result = _extract_deadline_from_text(text)
        assert "2025.12.31" in result

    def test_extract_deadline_not_found(self):
        from app.services.g2b_collector import _extract_deadline_from_text
        assert _extract_deadline_from_text("날짜 정보 없음") == ""

    def test_extract_title_from_text(self):
        from app.services.g2b_collector import _extract_title_from_text
        text = "1페이지\n\nAI 기반 공공서비스 고도화 사업\n발주기관: 행안부"
        result = _extract_title_from_text(text)
        assert "사업" in result

    def test_extract_title_empty_text(self):
        from app.services.g2b_collector import _extract_title_from_text
        assert _extract_title_from_text("") == ""


# ── search_announcements ──────────────────────────────────────────────────────

class TestSearchAnnouncements:
    def test_no_api_key_returns_empty(self):
        from app.services.g2b_collector import search_announcements
        result = run_async(search_announcements("테스트", api_key=""))
        assert result == []

    def test_api_success_returns_announcements(self):
        from app.services.g2b_collector import search_announcements

        mock_response = {
            "response": {
                "body": {
                    "items": [
                        {
                            "bidNtceNo": "20250317001-00",
                            "bidNtceNm": "AI 디지털 전환 사업",
                            "ntceInsttNm": "행정안전부",
                            "asignBdgtAmt": "500000000",
                            "bidNtceDt": "2025-03-17",
                            "bidClseDt": "2025-04-17",
                            "bidMthdNm": "일반경쟁",
                            "ntceKindNm": "용역",
                        }
                    ]
                }
            }
        }

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = mock_response

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__  = AsyncMock(return_value=False)
        mock_client.get        = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            results = run_async(
                search_announcements("AI", api_key="test-key")
            )

        assert len(results) == 1
        assert results[0].bid_number == "20250317001-00"
        assert results[0].title == "AI 디지털 전환 사업"
        assert results[0].issuer == "행정안전부"
        assert results[0].budget == "5억원"
        assert results[0].source == "api"

    def test_api_error_returns_empty(self):
        from app.services.g2b_collector import search_announcements

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__  = AsyncMock(return_value=False)
        mock_client.get        = AsyncMock(side_effect=Exception("연결 실패"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            results = run_async(
                search_announcements("테스트", api_key="test-key")
            )

        assert results == []


# ── fetch_announcement_detail ─────────────────────────────────────────────────

class TestFetchAnnouncementDetail:
    def test_url_goes_to_scrape_path_when_no_api_key(self):
        """Without API key + Playwright not available → returns None."""
        from app.services.g2b_collector import fetch_announcement_detail

        with patch("app.services.g2b_collector._scrape_announcement_text",
                   new=AsyncMock(return_value="")):
            result = run_async(
                fetch_announcement_detail(
                    "https://www.g2b.go.kr/pt/menu/selectSubFrame.do",
                    api_key="",
                )
            )
        assert result is None

    def test_url_scrape_path_returns_announcement(self):
        from app.services.g2b_collector import fetch_announcement_detail

        scraped = (
            "공고기관: 행정안전부\n"
            "AI 기반 공공서비스 구축 사업\n"
            "추정가격: 3억원\n"
            "입찰마감: 2025-12-31 18:00"
        )
        with patch("app.services.g2b_collector._scrape_announcement_text",
                   new=AsyncMock(return_value=scraped)):
            result = run_async(
                fetch_announcement_detail(
                    "https://www.g2b.go.kr/somepage",
                    api_key="",
                )
            )

        assert result is not None
        assert result.source == "scrape"
        assert result.issuer == "행정안전부"
        assert result.budget == "3억원"
        assert "2025-12-31" in result.deadline

    def test_not_found_returns_none(self):
        from app.services.g2b_collector import fetch_announcement_detail

        # Non-URL + no API key → None
        result = run_async(
            fetch_announcement_detail("국가디지털전환", api_key="")
        )
        assert result is None

    def test_bid_number_with_api_key_uses_api(self):
        from app.services.g2b_collector import fetch_announcement_detail

        api_item = {
            "response": {
                "body": {
                    "item": {
                        "bidNtceNm": "API 연동 테스트 사업",
                        "ntceInsttNm": "과기부",
                        "asignBdgtAmt": "1000000000",
                        "bidNtceDt": "2025-03-01",
                        "bidClseDt": "2025-04-01",
                        "bidMthdNm": "제한경쟁",
                        "ntceKindNm": "용역",
                    }
                }
            }
        }

        mock_resp = MagicMock()
        mock_resp.json.return_value = api_item

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__  = AsyncMock(return_value=False)
        mock_client.get        = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_client), \
             patch("app.services.g2b_collector._scrape_announcement_text",
                   new=AsyncMock(return_value="스크래핑된 공고 전문")):
            result = run_async(
                fetch_announcement_detail("20250317001-00", api_key="test-key")
            )

        assert result is not None
        assert result.title == "API 연동 테스트 사업"
        assert result.budget == "10억원"
        assert result.raw_text == "스크래핑된 공고 전문"

    def test_alphanumeric_bid_number_with_api_key_uses_search_fallback(self):
        from app.services.g2b_collector import G2BAnnouncement, fetch_announcement_detail

        fallback = G2BAnnouncement(
            bid_number="R26BK01398367",
            title="2026년 국가유산청 5급 승진후보자 등 직원 역량강화 사업",
            issuer="국가유산청",
            budget="8500만원",
            announcement_date="2026-03-21",
            deadline="2026-03-31 10:00:00",
            bid_type="전자입찰",
            category="등록공고",
            detail_url="https://www.g2b.go.kr/pt/menu/selectSubFrame.do?bidNtceNo=R26BK01398367",
            attachments=[],
            raw_text="",
            source="api",
        )

        with patch(
            "app.services.g2b_collector._fetch_via_api",
            new=AsyncMock(return_value=None),
        ), patch(
            "app.services.g2b_collector._search_announcement_by_bid_number",
            new=AsyncMock(return_value=fallback),
        ), patch(
            "app.services.g2b_collector._scrape_announcement_text",
            new=AsyncMock(return_value=""),
        ):
            result = run_async(
                fetch_announcement_detail("R26BK01398367", api_key="test-key")
            )

        assert result is not None
        assert result.bid_number == "R26BK01398367"
        assert result.issuer == "국가유산청"
        assert result.source == "api"

    def test_url_scrape_path_falls_back_to_http_when_playwright_missing(self):
        from app.services.g2b_collector import _scrape_announcement_text

        html_body = """
        <html>
          <body>
            <h1>AI 기반 공공서비스 구축 사업</h1>
            <p>공고기관: 행정안전부</p>
            <p>추정가격: 3억원</p>
          </body>
        </html>
        """

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.text = html_body

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        original_import = builtins.__import__

        def import_side_effect(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "playwright.async_api":
                raise ImportError("playwright missing")
            return original_import(name, globals, locals, fromlist, level)

        with patch("builtins.__import__", side_effect=import_side_effect), patch(
            "httpx.AsyncClient",
            return_value=mock_client,
        ):
            text = run_async(
                _scrape_announcement_text(
                    "https://www.g2b.go.kr/pt/menu/selectSubFrame.do?bidNtceNo=R26BK01398367"
                )
            )

        assert "AI 기반 공공서비스 구축 사업" in text
        assert "공고기관: 행정안전부" in text

    def test_url_with_api_key_uses_http_scrape_fallback_when_api_lookup_fails(self):
        from app.services.g2b_collector import fetch_announcement_detail

        html_body = """
        <html>
          <body>
            <h1>AI 기반 공공서비스 구축 사업</h1>
            <p>공고기관: 행정안전부</p>
            <p>추정가격: 3억원</p>
            <p>입찰마감: 2025-12-31 18:00</p>
          </body>
        </html>
        """

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.text = html_body

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        original_import = builtins.__import__

        def import_side_effect(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "playwright.async_api":
                raise ImportError("playwright missing")
            return original_import(name, globals, locals, fromlist, level)

        with patch("builtins.__import__", side_effect=import_side_effect), patch(
            "httpx.AsyncClient",
            return_value=mock_client,
        ), patch(
            "app.services.g2b_collector._fetch_via_api",
            new=AsyncMock(return_value=None),
        ), patch(
            "app.services.g2b_collector._search_announcement_by_bid_number",
            new=AsyncMock(return_value=None),
        ):
            result = run_async(
                fetch_announcement_detail(
                    "https://www.g2b.go.kr/pt/menu/selectSubFrame.do?bidNtceNo=R26BK01398367",
                    api_key="test-key",
                )
            )

        assert result is not None
        assert result.source == "scrape"
        assert result.issuer == "행정안전부"
        assert result.budget == "3억원"

    def test_bid_number_with_api_key_retries_transient_502_before_success(self):
        from app.services.g2b_collector import fetch_announcement_detail

        request = httpx.Request("GET", "https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoCnstwk")
        transient = httpx.Response(502, request=request, text="Bad Gateway")
        success = httpx.Response(
            200,
            request=request,
            json={
                "response": {
                    "body": {
                        "item": {
                            "bidNtceNm": "API 재시도 테스트 사업",
                            "ntceInsttNm": "조달청",
                            "asignBdgtAmt": "300000000",
                            "bidNtceDt": "2026-03-27",
                            "bidClseDt": "2026-04-03",
                            "bidMthdNm": "전자입찰",
                            "ntceKindNm": "용역",
                        }
                    }
                }
            },
        )

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=[transient, success])

        with patch("httpx.AsyncClient", return_value=mock_client), patch(
            "app.services.g2b_collector._scrape_announcement_text",
            new=AsyncMock(return_value="스크래핑 전문"),
        ), patch(
            "app.services.g2b_collector._retry_sleep",
            new=AsyncMock(),
        ) as sleep_mock:
            result = run_async(fetch_announcement_detail("20260327001-00", api_key="test-key"))

        assert result is not None
        assert result.title == "API 재시도 테스트 사업"
        assert result.raw_text == "스크래핑 전문"
        assert mock_client.get.await_count == 2
        sleep_mock.assert_awaited_once()

    def test_alphanumeric_search_fallback_retries_transient_502_before_match(self):
        from app.services.g2b_collector import _search_announcement_by_bid_number

        request = httpx.Request("GET", "https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServc")
        transient = httpx.Response(502, request=request, text="Bad Gateway")
        success = httpx.Response(
            200,
            request=request,
            json={
                "response": {
                    "body": {
                        "items": [
                            {
                                "bidNtceNo": "R26BK01398367",
                                "bidNtceNm": "2026년 국가유산청 5급 승진후보자 등 직원 역량강화 사업",
                                "ntceInsttNm": "국가유산청",
                                "asignBdgtAmt": "85000000",
                                "bidNtceDt": "2026-03-21",
                                "bidClseDt": "2026-03-31 10:00:00",
                                "bidMthdNm": "전자입찰",
                                "ntceKindNm": "등록공고",
                            }
                        ]
                    }
                }
            },
        )

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=[transient, success])

        with patch("httpx.AsyncClient", return_value=mock_client), patch(
            "app.services.g2b_collector._retry_sleep",
            new=AsyncMock(),
        ) as sleep_mock:
            result = run_async(_search_announcement_by_bid_number("R26BK01398367", "test-key"))

        assert result is not None
        assert result.bid_number == "R26BK01398367"
        assert result.issuer == "국가유산청"
        assert mock_client.get.await_count == 2
        sleep_mock.assert_awaited_once()


# ── /g2b/status ───────────────────────────────────────────────────────────────

class TestG2BStatus:
    def test_status_no_key(self, tmp_path, monkeypatch):
        client = _make_client(tmp_path, monkeypatch)
        # Patch at module level so the endpoint receives an empty key regardless
        # of what G2B_API_KEY is in the host environment.
        with patch("app.routers.g2b.get_g2b_api_key", return_value=""):
            res = client.get("/g2b/status")
        assert res.status_code == 200
        data = res.json()
        assert data["api_key_configured"] is False
        assert data["api_key_preview"] is None
        assert "setup_url" in data

    def test_status_with_key(self, tmp_path, monkeypatch):
        client = _make_client(tmp_path, monkeypatch)
        monkeypatch.setenv("G2B_API_KEY", "abcdef12345678")  # set after client (read at request time)
        res = client.get("/g2b/status")
        assert res.status_code == 200
        data = res.json()
        assert data["api_key_configured"] is True
        assert data["api_key_preview"] and "..." in data["api_key_preview"]


# ── /g2b/search ───────────────────────────────────────────────────────────────

class TestG2BSearch:
    def test_no_api_key_returns_empty_results(self, tmp_path, monkeypatch):
        client = _make_client(tmp_path, monkeypatch)
        # Patch at module level so the endpoint (and search_announcements) sees no key.
        with patch("app.routers.g2b.get_g2b_api_key", return_value=""), \
             patch("app.services.g2b_collector.search_announcements",
                   new=AsyncMock(return_value=[])):
            res = client.get("/g2b/search?q=AI+구축")
        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 0
        assert data["results"] == []

    def test_missing_q_returns_422(self, tmp_path, monkeypatch):
        client = _make_client(tmp_path, monkeypatch)
        res = client.get("/g2b/search")
        assert res.status_code == 422

    def test_with_mock_api_results(self, tmp_path, monkeypatch):
        from app.services.g2b_collector import G2BAnnouncement

        fake = [
            G2BAnnouncement(
                bid_number="20250317001-00",
                title="테스트 사업",
                issuer="행정안전부",
                budget="5억원",
                announcement_date="2025-03-17",
                deadline="2025-04-17",
                bid_type="일반경쟁",
                category="용역",
                detail_url="https://www.g2b.go.kr/...",
                attachments=[],
                raw_text="",
                source="api",
            )
        ]

        client = _make_client(tmp_path, monkeypatch)
        monkeypatch.setenv("G2B_API_KEY", "test-key")  # set after client (read at request time)

        with patch(
            "app.services.g2b_collector.search_announcements",
            new=AsyncMock(return_value=fake),
        ):
            res = client.get("/g2b/search?q=테스트")

        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 1
        assert data["results"][0]["bid_number"] == "20250317001-00"
        assert data["results"][0]["title"] == "테스트 사업"


# ── /g2b/fetch ────────────────────────────────────────────────────────────────

class TestG2BFetch:
    def test_not_found_returns_404(self, tmp_path, monkeypatch):
        client = _make_client(tmp_path, monkeypatch)
        with patch(
            "app.services.g2b_collector.fetch_announcement_detail",
            new=AsyncMock(return_value=None),
        ):
            res = client.post(
                "/g2b/fetch",
                json={"url_or_number": "https://www.g2b.go.kr/nonexistent"},
            )
        assert res.status_code == 404

    def test_found_returns_200_with_fields(self, tmp_path, monkeypatch):
        from app.services.g2b_collector import G2BAnnouncement

        fake = G2BAnnouncement(
            bid_number="20250317001-00",
            title="AI 기반 구축 사업",
            issuer="행정안전부",
            budget="5억원",
            announcement_date="2025-03-17",
            deadline="2025-04-17 18:00",
            bid_type="일반경쟁",
            category="용역",
            detail_url="https://www.g2b.go.kr/...",
            attachments=[],
            raw_text="공고 전문 텍스트입니다.",
            source="scrape",
        )
        client = _make_client(tmp_path, monkeypatch)

        with patch(
            "app.services.g2b_collector.fetch_announcement_detail",
            new=AsyncMock(return_value=fake),
        ):
            res = client.post(
                "/g2b/fetch",
                json={"url_or_number": "https://www.g2b.go.kr/something"},
            )

        assert res.status_code == 200
        data = res.json()
        assert data["announcement"]["bid_number"] == "20250317001-00"
        assert data["announcement"]["title"] == "AI 기반 구축 사업"
        assert "extracted_fields" in data
        assert "structured_context" in data
        assert "행정안전부" in data["structured_context"]

    def test_missing_body_returns_422(self, tmp_path, monkeypatch):
        client = _make_client(tmp_path, monkeypatch)
        res = client.post("/g2b/fetch", json={})
        assert res.status_code == 422
