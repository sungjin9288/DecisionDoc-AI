from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from scripts.playtest_procurement_stale_share_demo import (
    DEFAULT_MANIFEST_NAME,
    build_focused_review_url,
    playtest_procurement_stale_share_demo,
)


class _FakeLocator:
    def __init__(self, page, selector: str) -> None:
        self._page = page
        self._selector = selector

    @property
    def first(self):
        return self

    def inner_text(self) -> str:
        return self._page.text_by_selector.get(self._selector, "")

    def is_disabled(self) -> bool:
        return self._selector in self._page.disabled_selectors

    def click(self, **kwargs) -> None:
        self._page.click(self._selector)


class _FakePage:
    def __init__(self) -> None:
        self._base_url = "http://127.0.0.1:8879"
        self._focused_review_url = build_focused_review_url(self._base_url, "system", "proj-1")
        self.visited_urls: list[str] = []
        self.waited_selectors: list[str] = []
        self.waited_functions: list[str] = []
        self.evaluated_scripts: list[str] = []
        self.fills: list[tuple[str, str]] = []
        self.clicked: list[str] = []
        self.screenshots: list[str] = []
        self.text_by_selector = {
            ".location-procurement-focus": "제안서 현재 procurement 대비 이전 council 기준",
            ".decision-council-panel": "Decision Council v1 bid_decision_kr proposal_kr",
            '[data-shared-decision-council-warning="stale_procurement"]': "현재 procurement 대비 이전 council 기준",
        }
        self._location_procurement_opened = False
        self._force_modal_visible = False
        self.disabled_selectors = {
            '[data-decision-council-generate-proposal="proj-1"]',
        }

    def goto(self, url: str) -> None:
        self.visited_urls.append(url)

    def wait_for_selector(self, selector: str, timeout: int | None = None, state: str | None = None) -> None:
        self.waited_selectors.append(selector)
        current_url = self.visited_urls[-1] if self.visited_urls else ""
        button_selector = '[data-location-procurement-stale-share-focus-review="system"][data-location-procurement-project="proj-1"]'
        if selector == button_selector and state == "visible":
            raise PlaywrightTimeoutError("focused review CTA is not visible in the fake playtest page")
        if current_url == self._base_url:
            if selector == "#location-procurement-modal" and state == "visible":
                if not self._location_procurement_opened and not self._force_modal_visible:
                    raise PlaywrightTimeoutError("location procurement modal is still hidden")

    def wait_for_function(self, script: str) -> None:
        self.waited_functions.append(script)

    def fill(self, selector: str, value: str) -> None:
        self.fills.append((selector, value))

    def click(self, selector: str) -> None:
        self.clicked.append(selector)

    def evaluate(self, script: str):
        self.evaluated_scripts.append(script)
        if 'window.openLocationProcurementFocusedStaleShareReview("system", "proj-1")' in script:
            self._location_procurement_opened = True
        if "location-procurement-modal" in script and "style.display = 'flex'" in script:
            self._force_modal_visible = True
        return None

    def locator(self, selector: str) -> _FakeLocator:
        return _FakeLocator(self, selector)

    def screenshot(self, *, path: str, full_page: bool = False) -> None:
        Path(path).write_bytes(b"fake-image")
        self.screenshots.append(path)


class _FallbackFakePage(_FakePage):
    def __init__(self) -> None:
        super().__init__()
        self._focused_restore_failures_remaining = 1

    def wait_for_selector(self, selector: str, timeout: int | None = None, state: str | None = None) -> None:
        self.waited_selectors.append(selector)
        current_url = self.visited_urls[-1] if self.visited_urls else ""
        if (
            current_url == self._focused_review_url
            and selector == "#location-procurement-modal"
            and state == "visible"
            and self._focused_restore_failures_remaining > 0
        ):
            self._focused_restore_failures_remaining -= 1
            raise PlaywrightTimeoutError("focused review url restore did not finish")
        super().wait_for_selector(selector, timeout=timeout, state=state)
        return None


class _ReauthFallbackFakePage(_FakePage):
    def __init__(self) -> None:
        super().__init__()
        self._reauth_completed = False

    def goto(self, url: str) -> None:
        self.visited_urls.append(url)
        if url == self._base_url and len(self.visited_urls) >= 2:
            self._location_procurement_opened = False
            self._force_modal_visible = False

    def wait_for_selector(self, selector: str, timeout: int | None = None, state: str | None = None) -> None:
        self.waited_selectors.append(selector)
        current_url = self.visited_urls[-1] if self.visited_urls else ""
        base_url_visits = self.visited_urls.count(self._base_url)
        button_selector = '[data-location-procurement-stale-share-focus-review="system"][data-location-procurement-project="proj-1"]'
        if selector == button_selector and state == "visible":
            raise PlaywrightTimeoutError("focused review CTA is not visible in the fake playtest page")
        if current_url == self._base_url and selector == ".bundle-card" and state == "visible":
            if not self._reauth_completed and len(self.visited_urls) >= 2:
                raise PlaywrightTimeoutError("session restore returned to login screen")
        if current_url == self._base_url and selector == "#login-screen" and state == "visible":
            if not self._reauth_completed and len(self.visited_urls) >= 2:
                return None
        if current_url == self._focused_review_url and selector == "#location-procurement-modal" and state == "visible":
            raise PlaywrightTimeoutError("focused review url restore did not finish")
        if current_url == self._base_url and selector == "#location-procurement-modal" and state == "visible":
            if not self._location_procurement_opened and not self._force_modal_visible:
                raise PlaywrightTimeoutError("location procurement modal is still hidden")
            if base_url_visits <= 1:
                raise PlaywrightTimeoutError("modal restore did not finish")
            if self._reauth_completed and self._force_modal_visible:
                return None
            raise PlaywrightTimeoutError("modal remained hidden after focused review reload")
        return None

    def evaluate(self, script: str):
        super().evaluate(script)
        if script == "document.getElementById('login-form')?.requestSubmit()" and len(self.visited_urls) >= 2:
            self._reauth_completed = True
        return None


class _FakeContext:
    def __init__(self, page: _FakePage) -> None:
        self._page = page

    def new_page(self) -> _FakePage:
        return self._page

    def close(self) -> None:
        return None


class _FakeBrowser:
    def __init__(self, page: _FakePage) -> None:
        self._page = page
        self.launch_kwargs: dict[str, object] = {}

    def new_context(self) -> _FakeContext:
        return _FakeContext(self._page)

    def close(self) -> None:
        return None


class _FakeChromium:
    def __init__(self, page: _FakePage) -> None:
        self._page = page
        self.launch_calls: list[dict[str, object]] = []

    def launch(self, **kwargs):
        self.launch_calls.append(kwargs)
        browser = _FakeBrowser(self._page)
        browser.launch_kwargs = kwargs
        return browser


class _FakePlaywrightManager:
    def __init__(self, page: _FakePage) -> None:
        self.chromium = _FakeChromium(page)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_playtest_procurement_stale_share_demo_uses_manifest_and_captures_screenshots(tmp_path: Path) -> None:
    manifest = {
        "base_url": "http://127.0.0.1:8879",
        "seed": {
            "username": "stale_demo_admin",
            "password": "DemoPass123!",
            "project_id": "proj-1",
            "share_id": "share-1",
            "shared_bundle_id": "proposal_kr",
            "internal_focused_review_url": "http://127.0.0.1:8879/?focus=proj-1",
            "public_share_url": "http://127.0.0.1:8879/shared/share-1",
        },
        "verification": {
            "project_id": "proj-1",
            "share_id": "share-1",
            "bundle_id": "proposal_kr",
            "internal_focused_review_url": "http://127.0.0.1:8879/?focus=proj-1",
            "public_share_url": "http://127.0.0.1:8879/shared/share-1",
            "stale_status_copy": "현재 procurement 대비 이전 council 기준",
        },
    }
    data_dir = tmp_path / "demo-data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / DEFAULT_MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    fake_page = _FakePage()

    result = playtest_procurement_stale_share_demo(
        data_dir=data_dir,
        output_dir=str(tmp_path / "screens"),
        playwright_factory=lambda: _FakePlaywrightManager(fake_page),
    )

    assert result.bundle_id == "proposal_kr"
    assert result.project_id == "proj-1"
    assert result.share_id == "share-1"
    assert Path(result.focused_review_screenshot).exists()
    assert Path(result.public_share_screenshot).exists()
    assert fake_page.visited_urls == [
        "http://127.0.0.1:8879",
        build_focused_review_url("http://127.0.0.1:8879", "system", "proj-1"),
        "http://127.0.0.1:8879/shared/share-1",
    ]
    assert ("#login-username", "stale_demo_admin") in fake_page.fills
    assert ("#login-password", "DemoPass123!") in fake_page.fills
    assert "document.getElementById('login-form')?.requestSubmit()" in fake_page.evaluated_scripts
    assert any("onboarding_done" in script for script in fake_page.evaluated_scripts)
    assert '.location-procurement-focus [data-location-procurement-open]' in fake_page.clicked


def test_playtest_procurement_stale_share_demo_falls_back_to_locations_review_cta(tmp_path: Path) -> None:
    manifest = {
        "base_url": "http://127.0.0.1:8879",
        "seed": {
            "username": "stale_demo_admin",
            "password": "DemoPass123!",
            "project_id": "proj-1",
            "share_id": "share-1",
            "shared_bundle_id": "proposal_kr",
            "internal_focused_review_url": "http://127.0.0.1:8879/?focus=proj-1",
            "public_share_url": "http://127.0.0.1:8879/shared/share-1",
        },
        "verification": {
            "tenant_id": "system",
            "project_id": "proj-1",
            "share_id": "share-1",
            "bundle_id": "proposal_kr",
            "internal_focused_review_url": "http://127.0.0.1:8879/?focus=proj-1",
            "public_share_url": "http://127.0.0.1:8879/shared/share-1",
            "stale_status_copy": "현재 procurement 대비 이전 council 기준",
        },
    }
    data_dir = tmp_path / "demo-data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / DEFAULT_MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    fake_page = _FallbackFakePage()

    result = playtest_procurement_stale_share_demo(
        data_dir=data_dir,
        output_dir=str(tmp_path / "screens"),
        playwright_factory=lambda: _FakePlaywrightManager(fake_page),
    )

    assert result.bundle_id == "proposal_kr"
    assert fake_page.visited_urls == [
        "http://127.0.0.1:8879",
        build_focused_review_url("http://127.0.0.1:8879", "system", "proj-1"),
        "http://127.0.0.1:8879/shared/share-1",
    ]
    assert 'window.openLocationProcurementFocusedStaleShareReview("system", "proj-1")' in fake_page.evaluated_scripts


def test_playtest_procurement_stale_share_demo_reauthenticates_when_base_reload_returns_login(tmp_path: Path) -> None:
    manifest = {
        "base_url": "http://127.0.0.1:8879",
        "seed": {
            "username": "stale_demo_admin",
            "password": "DemoPass123!",
            "project_id": "proj-1",
            "share_id": "share-1",
            "shared_bundle_id": "proposal_kr",
            "internal_focused_review_url": "http://127.0.0.1:8879/?focus=proj-1",
            "public_share_url": "http://127.0.0.1:8879/shared/share-1",
        },
        "verification": {
            "tenant_id": "system",
            "project_id": "proj-1",
            "share_id": "share-1",
            "bundle_id": "proposal_kr",
            "internal_focused_review_url": "http://127.0.0.1:8879/?focus=proj-1",
            "public_share_url": "http://127.0.0.1:8879/shared/share-1",
            "stale_status_copy": "현재 procurement 대비 이전 council 기준",
        },
    }
    data_dir = tmp_path / "demo-data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / DEFAULT_MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    fake_page = _ReauthFallbackFakePage()

    result = playtest_procurement_stale_share_demo(
        data_dir=data_dir,
        output_dir=str(tmp_path / "screens"),
        playwright_factory=lambda: _FakePlaywrightManager(fake_page),
    )

    assert result.bundle_id == "proposal_kr"
    assert fake_page.visited_urls == [
        "http://127.0.0.1:8879",
        build_focused_review_url("http://127.0.0.1:8879", "system", "proj-1"),
        "http://127.0.0.1:8879",
        "http://127.0.0.1:8879/shared/share-1",
    ]
    assert fake_page.evaluated_scripts.count("document.getElementById('login-form')?.requestSubmit()") == 2
    assert fake_page.evaluated_scripts.count(
        'window.openLocationProcurementFocusedStaleShareReview("system", "proj-1")'
    ) == 2
    assert any(
        "location-procurement-modal" in script and "style.display = 'flex'" in script
        for script in fake_page.evaluated_scripts
    )
