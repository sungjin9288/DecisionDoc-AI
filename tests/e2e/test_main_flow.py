"""Playwright E2E tests — core user flows."""
from __future__ import annotations

import json
from urllib import request as urllib_request

import pytest

pytestmark = pytest.mark.e2e


def _wait_until_any_visible(page, selectors: list[str], *, timeout_ms: int = 30000) -> str:
    """Poll locators until one becomes visible without using page-side eval."""
    deadline = timeout_ms // 250
    for _ in range(deadline):
        for selector in selectors:
            if page.locator(selector).is_visible():
                return selector
        page.wait_for_timeout(250)
    raise AssertionError(f"None of the selectors became visible: {selectors}")


def _wait_until_text_contains(page, selector: str, expected: str, *, timeout_ms: int = 5000) -> str:
    """Poll a locator's text until it contains the expected value."""
    deadline = max(timeout_ms // 250, 1)
    locator = page.locator(selector)
    for _ in range(deadline):
        if expected in locator.inner_text():
            return locator.inner_text()
        page.wait_for_timeout(250)
    raise AssertionError(f"{selector} did not contain {expected!r} within {timeout_ms}ms")


def _generate_to_results(page, title: str, goal: str) -> None:
    """Drive the current 2-step generate flow until results are visible."""
    page.wait_for_selector(".bundle-card", timeout=5000)
    page.locator(".bundle-card").first.click()
    page.fill("#f-title", title)
    page.fill("#f-goal", goal)
    page.click("#generate-btn")
    visible = _wait_until_any_visible(page, ["#sketch-panel", "#results"], timeout_ms=30000)
    if visible == "#sketch-panel":
        page.click("#sketch-confirm-btn")
    page.wait_for_selector("#results", state="visible", timeout=30000)


def _create_project_with_document(page, name: str = "조달 UI 테스트") -> str:
    return page.evaluate(
        """async ({ name }) => {
          const token = localStorage.getItem('dd_access_token');
          const headers = {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          };
          const created = await fetch('/projects', {
            method: 'POST',
            headers,
            body: JSON.stringify({ name, fiscal_year: 2026 }),
          });
          if (!created.ok) throw new Error(`project create failed: ${created.status}`);
          const project = await created.json();
          const added = await fetch(`/projects/${project.project_id}/documents`, {
            method: 'POST',
            headers,
            body: JSON.stringify({
              request_id: 'req-e2e-procurement',
              bundle_id: 'bid_decision_kr',
              title: '입찰 의사결정 문서',
              docs: [{ doc_type: 'go_no_go_memo', markdown: '# 결정 요약' }],
            }),
          });
          if (!added.ok) throw new Error(`project document add failed: ${added.status}`);
          return project.project_id;
        }""",
        {"name": name},
    )


# ── 기본 페이지 ──────────────────────────────────────────────────────────────

def test_page_loads(page):
    """Page title must contain 'DecisionDoc' and #bundle-grid must be visible."""
    page.wait_for_selector("#bundle-grid", timeout=5000)
    assert "DecisionDoc" in page.title()


def test_login_screen_bootstrap_has_no_sso_reference_error(playwright, live_server):
    console_messages: list[str] = []
    browser = playwright.chromium.launch()
    ctx = browser.new_context()
    pg = ctx.new_page()
    pg.on("console", lambda msg: console_messages.append(msg.text))

    pg.goto(live_server["base_url"])
    pg.wait_for_selector("#login-screen", timeout=10000)
    html = pg.content()

    assert pg.evaluate("document.body.classList.contains('auth-pending')")
    assert pg.locator("#login-form").count() == 1
    assert not pg.locator(".hero").is_visible()
    assert not pg.locator("#page-nav").is_visible()
    assert not pg.locator("#main-content").is_visible()
    assert not pg.locator("#mobile-bottom-nav").is_visible()
    assert "cdn.jsdelivr.net" not in html
    assert not any(
        "addSSOLoginButtons is not defined" in message
        for message in console_messages
    )
    assert not any(
        "Password field is not contained in a form" in message
        for message in console_messages
    )
    assert not any(
        "autocomplete attributes" in message
        for message in console_messages
    )
    assert not any(
        "cdn.tailwindcss.com should not be used in production" in message
        for message in console_messages
    )

    ctx.close()
    browser.close()


def test_bundle_selection_enables_generate_button(page):
    """Clicking a bundle card must enable the generate button."""
    page.wait_for_selector(".bundle-card", timeout=5000)
    assert page.locator("#generate-btn").is_disabled()
    page.locator(".bundle-card").first.click()
    assert not page.locator("#generate-btn").is_disabled()


# ── 생성 플로우 ───────────────────────────────────────────────────────────────

def test_generate_flow_produces_results(page):
    """Select bundle → fill form → generate → results section must appear with tabs."""
    _generate_to_results(page, "E2E 테스트", "E2E 목표")
    assert page.locator("#tab-bar .tab-btn").count() > 0


def test_export_flow(page):
    """After generation, clicking export-btn must show success text."""
    _generate_to_results(page, "내보내기 테스트", "내보내기 목표")
    page.click("#export-btn")
    _wait_until_text_contains(page, "#export-btn", "완료", timeout_ms=5000)


# ── 로컬스토리지 ──────────────────────────────────────────────────────────────

def test_localStorage_form_draft_saved(page):
    """Typing in the title field must persist the draft to localStorage."""
    page.wait_for_selector(".bundle-card", timeout=5000)
    page.fill("#f-title", "저장 테스트")
    page.fill("#f-goal", "목표")
    raw = page.evaluate("localStorage.getItem('dd_form_draft')")
    assert raw is not None
    draft = json.loads(raw)
    assert draft["title"] == "저장 테스트"


def test_history_saved_after_generate(page):
    """After a successful generate, dd_history must contain the latest entry."""
    _generate_to_results(page, "이력 테스트", "이력 확인")
    raw = page.evaluate("localStorage.getItem('dd_history')")
    assert raw is not None
    history = json.loads(raw)
    assert len(history) >= 1
    assert history[0]["title"] == "이력 테스트"


# ── 스케치 플로우 ─────────────────────────────────────────────────────────────

def test_sketch_or_results_appears_on_generate(page):
    """Either sketch panel or results must appear after clicking generate."""
    page.wait_for_selector(".bundle-card", timeout=5000)
    page.locator(".bundle-card").first.click()
    page.fill("#f-title", "스케치 테스트")
    page.fill("#f-goal", "스케치 목표 확인")
    page.click("#generate-btn")
    _wait_until_any_visible(page, ["#sketch-panel", "#results"], timeout_ms=30000)


def test_results_panel_has_content_after_generate(page):
    """Results panel must contain non-empty text after generation completes."""
    _generate_to_results(page, "구성안 테스트", "섹션 구성 확인")
    content = page.locator("#results").inner_text()
    assert len(content.strip()) > 0


# ── 번역 모달 ─────────────────────────────────────────────────────────────────

def test_translate_button_visible_after_generate(page):
    """translate-btn must exist in DOM after a successful generation."""
    _generate_to_results(page, "번역 버튼 테스트", "버튼 가시성 확인")
    assert page.locator("#translate-btn").count() > 0


def test_translate_button_click_opens_modal(page):
    """Clicking translate-btn must show the translation modal."""
    _generate_to_results(page, "번역 API 테스트", "API 호출 확인")

    translate_btn = page.locator("#translate-btn")
    if translate_btn.count() == 0:
        pytest.skip("translate-btn not found")
    translate_btn.click()
    page.wait_for_selector("#translate-modal", state="visible", timeout=5000)
    assert page.locator("#translate-content").inner_text().strip()


# ── AI 검토 모달 ──────────────────────────────────────────────────────────────

def test_review_button_visible_after_generate(page):
    """review-btn must exist in DOM after a successful generation."""
    _generate_to_results(page, "검토 버튼 테스트", "버튼 가시성 확인")
    assert page.locator("#review-btn").count() > 0


def test_review_button_click_opens_modal(page):
    """Clicking review-btn must show the review modal."""
    _generate_to_results(page, "검토 API 테스트", "검토 API 호출 확인")

    review_btn = page.locator("#review-btn")
    if review_btn.count() == 0:
        pytest.skip("review-btn not found")
    review_btn.click()
    page.wait_for_selector("#review-modal", state="visible", timeout=5000)
    assert page.locator("#review-modal").inner_text().strip()


# ── 다크모드 ──────────────────────────────────────────────────────────────────

def test_dark_mode_toggle(page):
    """Clicking dark-mode-toggle must flip the 'dark' class on body."""
    page.wait_for_selector(".bundle-card", timeout=5000)
    toggle = page.locator("#dark-mode-toggle")
    if toggle.count() == 0:
        pytest.skip("dark-mode-toggle not present")
    initial = page.evaluate("document.body.classList.contains('dark')")
    toggle.click()
    after = page.evaluate("document.body.classList.contains('dark')")
    assert after != initial


# ── 키보드 단축키 ─────────────────────────────────────────────────────────────

def test_keyboard_shortcut_ctrl_enter_triggers_generate(page):
    """Ctrl+Enter with a bundle selected and title filled must start generation."""
    page.wait_for_selector(".bundle-card", timeout=5000)
    page.locator(".bundle-card").first.click()
    page.fill("#f-title", "단축키 테스트")
    page.fill("#f-goal", "Ctrl+Enter 확인")
    page.keyboard.press("Control+Enter")
    visible = _wait_until_any_visible(page, ["#sketch-panel", "#results"], timeout_ms=30000)
    if visible == "#sketch-panel":
        page.click("#sketch-confirm-btn")
    page.wait_for_selector("#results", state="visible", timeout=30000)
    content = page.locator("#results").inner_text()
    assert len(content.strip()) > 0


def test_project_detail_shows_procurement_panel_and_doc_actions(page):
    project_id = _create_project_with_document(page)
    token = page.evaluate("localStorage.getItem('dd_access_token')")
    request = urllib_request.Request(
        f"http://127.0.0.1:18765/projects/{project_id}",
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    with urllib_request.urlopen(request, timeout=5) as response:
        project = json.loads(response.read().decode("utf-8"))

    page.evaluate("switchPage('project-page')")
    page.wait_for_selector(".project-card", timeout=10000)
    page.evaluate(
        """({ project }) => {
          renderProjectDetail(project, null, { procurementEnabled: true });
          document.getElementById('project-list').style.display = 'none';
          document.getElementById('project-detail').style.display = 'block';
        }""",
        {"project": project},
    )

    page.wait_for_selector("#project-procurement-url-input", timeout=10000)
    assert page.locator("text=Public Procurement Go/No-Go Copilot").count() >= 1
    assert page.locator("text=의사결정 문서 생성").count() >= 1
    assert page.locator("text=결재 요청").count() >= 1
    assert page.locator("text=공유").count() >= 1
