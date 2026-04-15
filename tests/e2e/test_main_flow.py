"""Playwright E2E tests — core user flows."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import uuid
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


def test_generate_landing_shows_ai_rank_roster(page):
    page.wait_for_selector("#ai-rank-roster", timeout=5000)
    assert page.locator("#ai-rank-roster").is_visible()
    assert page.locator("#ai-rank-roster .ai-rank-card").count() == 3
    assert page.locator("#ai-rank-roster .ai-rank-card .ai-rank-title", has_text="최종 승인 AI").count() == 1
    assert page.locator("#ai-rank-roster .ai-rank-card .ai-rank-title", has_text="제안/영업 리드 AI").count() == 1
    assert page.locator("#ai-rank-roster .ai-rank-card .ai-rank-title", has_text="수행 리드 AI").count() == 1


def test_ai_rank_roster_bd_action_opens_g2b_search(page):
    page.wait_for_selector("#ai-rank-roster", timeout=5000)
    page.locator('[data-ai-rank="proposal_bd"]').click()
    page.locator("#ai-rank-status-action").click()

    page.wait_for_selector('#category-filter .cat-btn.active[data-cat="gov"]', timeout=5000)
    page.wait_for_selector("#g2b-search-tab", state="visible", timeout=5000)
    assert page.locator("#g2b-content").is_visible()
    assert page.locator("#g2b-search-input").evaluate("el => document.activeElement === el")
    assert page.input_value("#f-audience") == "mixed"


def test_ai_rank_roster_pm_action_focuses_project_context(page):
    page.wait_for_selector("#ai-rank-roster", timeout=5000)
    page.locator('[data-ai-rank="delivery_pm"]').click()
    page.locator("#ai-rank-status-action").click()

    page.wait_for_selector('#category-filter .cat-btn.active[data-cat="gov"]', timeout=5000)
    assert page.input_value("#f-audience") == "technical"
    assert page.locator('#tone-chips .chip.active').get_attribute("data-tone") == "detailed"
    assert page.locator("#project-select").evaluate("el => document.activeElement === el")


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

    pg.get_by_role("link", name="관리자 계정 만들기").click()
    pg.wait_for_selector("#register-form", timeout=5000)
    assert pg.get_by_role("heading", name="관리자 계정 만들기").inner_text() == "관리자 계정 만들기"

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
        "Password forms should have" in message
        for message in console_messages
    )
    assert not any(
        "[PWA] SW registered" in message
        for message in console_messages
    )
    assert not any(
        "cdn.tailwindcss.com should not be used in production" in message
        for message in console_messages
    )
    assert not any(
        "Executing inline event handler violates" in message
        for message in console_messages
    )

    ctx.close()
    browser.close()


def test_ops_dashboard_post_deploy_panel_renders_with_ops_key(playwright, live_server):
    console_messages: list[str] = []
    browser = playwright.chromium.launch()
    ctx = browser.new_context()
    ctx.add_init_script("localStorage.setItem('onboarding_done', '1');")
    pg = ctx.new_page()
    pg.on("console", lambda msg: console_messages.append(msg.text))

    pg.goto(f"{live_server['base_url']}?ops=1")
    pg.wait_for_selector("#ops-panel", timeout=10000)
    pg.wait_for_selector("#ops-post-deploy-report", timeout=10000)

    assert "Ops Key 또는 admin 로그인 세션이 있어야 배포 리포트를 조회할 수 있습니다." in pg.locator(
        "#ops-post-deploy-report"
    ).inner_text()
    assert "Admin 로그인 후 SSO 설정을 불러올 수 있습니다." in pg.locator(
        "#sso-form-container"
    ).inner_text()
    assert "Admin 로그인 후 요금제 정보를 확인할 수 있습니다." in pg.locator(
        "#billing-panel"
    ).inner_text()
    assert "admin 로그인 없이도 아래 `Ops Key` 입력으로 배포 리포트 조회와 운영 조사 기능을 사용할 수 있습니다." in pg.locator(
        "#login-screen"
    ).inner_text()

    pg.fill("#ops-key-input", live_server["ops_key"])
    pg.evaluate(
        """async () => {
          localStorage.setItem('dd_ops_key', document.querySelector('#ops-key-input')?.value || '');
          await window.loadOpsPostDeployReports();
        }"""
    )

    pg.wait_for_function(
        "() => document.querySelector('#ops-post-deploy-report')?.innerText.includes('Latest report')"
    )
    panel_text = pg.locator("#ops-post-deploy-report").inner_text()
    assert "post-deploy-20260414T041000Z.json" in panel_text
    assert "post-deploy-20260414T031000Z.json" in panel_text
    assert "health" in panel_text
    assert "smoke" in panel_text
    assert "https://admin.decisiondoc.kr" in panel_text
    assert "JSON 보기" in panel_text
    assert "JSON 다운로드" in panel_text
    assert pg.locator("#ops-post-deploy-failures-only").count() == 1
    assert pg.locator("#ops-post-deploy-search").count() == 1

    pg.fill("#ops-post-deploy-search", "031000")
    pg.wait_for_function(
        """() => {
          const report = document.querySelector('#ops-post-deploy-report');
          const detail = document.querySelector('#ops-post-deploy-detail');
          const buttons = document.querySelectorAll('[data-report-detail-btn]');
          return report?.innerText.includes('1 / 2건')
            && buttons.length === 1
            && detail?.innerText.includes('post-deploy-20260414T031000Z.json');
        }"""
    )
    assert pg.locator('[data-report-detail-btn="post-deploy-20260414T031000Z.json"]').count() == 1
    assert pg.locator("#ops-post-deploy-run-btn").count() == 1
    assert pg.locator("#ops-post-deploy-run-skip-smoke").count() == 1
    assert pg.locator("#ops-post-deploy-compare-left").count() == 1
    assert pg.locator("#ops-post-deploy-compare-right").count() == 1

    pg.select_option("#ops-post-deploy-compare-left", "post-deploy-20260414T041000Z.json")
    pg.select_option("#ops-post-deploy-compare-right", "post-deploy-20260414T031000Z.json")
    pg.click("#ops-post-deploy-compare-run-btn")
    pg.wait_for_function(
        """() => {
          const compare = document.querySelector('#ops-post-deploy-compare-result');
          return compare?.innerText.includes('체크 차이') && compare?.innerText.includes('smoke');
        }"""
    )
    compare_text = pg.locator("#ops-post-deploy-compare-result").inner_text()
    assert "exit 17" in compare_text

    pg.click("#ops-post-deploy-clear-filters-btn")
    pg.wait_for_function(
        "() => document.querySelectorAll('[data-report-detail-btn]').length === 2"
    )

    pg.check("#ops-post-deploy-failures-only")
    pg.wait_for_function(
        """() => {
          const report = document.querySelector('#ops-post-deploy-report');
          const detail = document.querySelector('#ops-post-deploy-detail');
          const buttons = document.querySelectorAll('[data-report-detail-btn]');
          return report?.innerText.includes('1 / 2건')
            && report?.innerText.includes('필터 적용됨')
            && buttons.length === 1
            && detail?.innerText.includes('post-deploy-20260414T031000Z.json');
        }"""
    )
    assert "docker compose ps failed with exit code 17" in pg.locator(
        "#ops-post-deploy-report"
    ).inner_text()

    pg.click("#ops-post-deploy-clear-filters-btn")
    pg.wait_for_function(
        """() => {
          const report = document.querySelector('#ops-post-deploy-report');
          return document.querySelectorAll('[data-report-detail-btn]').length === 2
            && !report?.innerText.includes('필터 적용됨');
        }"""
    )

    pg.get_by_role("button", name="JSON 보기").click()
    pg.wait_for_selector("#ops-post-deploy-raw pre", timeout=5000)
    raw_json = pg.locator("#ops-post-deploy-raw").inner_text()
    assert '"latest_report": "post-deploy-20260414T041000Z.json"' in raw_json
    assert '"status": "passed"' in raw_json
    assert '"name": "health"' in raw_json

    pg.get_by_role("button", name="JSON 숨기기").click()
    assert not pg.locator("#ops-post-deploy-raw").is_visible()

    detail_text = pg.locator("#ops-post-deploy-detail").inner_text()
    assert "선택한 리포트" in detail_text
    assert "post-deploy-20260414T041000Z.json" in detail_text
    assert "smoke 포함" in detail_text

    pg.locator('[data-report-detail-btn="post-deploy-20260414T031000Z.json"]').click()
    pg.wait_for_function(
        "() => document.querySelector('#ops-post-deploy-detail')?.innerText.includes('post-deploy-20260414T031000Z.json')"
    )
    selected_detail = pg.locator("#ops-post-deploy-detail").inner_text()
    assert "post-deploy-20260414T031000Z.json" in selected_detail
    assert "docker compose ps failed with exit code 17" in selected_detail
    assert "실패" in selected_detail
    assert "exit 17" in selected_detail
    assert not console_messages

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


def test_generate_from_documents_modal_flow(page, tmp_path):
    """JWT-authenticated browser session should generate docs from uploaded files."""
    sample = tmp_path / "upload-notes.txt"
    sample.write_text(
        "Project title: E2E upload flow\n"
        "Goal: Verify browser upload generation\n"
        "Constraints: Preserve auditability.\n",
        encoding="utf-8",
    )

    page.locator(".bundle-card").first.click()
    page.get_by_role("button", name="📚 문서로 초안 생성").click()
    page.wait_for_selector("#from-documents-modal", state="visible", timeout=5000)
    page.set_input_files("#from-documents-file-input", str(sample))
    page.fill("#from-documents-title", "업로드 기반 생성")
    page.fill("#from-documents-goal", "브라우저에서 업로드 후 문서를 생성한다.")
    page.click("#from-documents-submit-btn")

    page.wait_for_selector("#from-documents-modal", state="hidden", timeout=30000)
    page.wait_for_selector("#results", state="visible", timeout=30000)
    assert page.locator("#tab-bar .tab-btn").count() == 2
    assert page.locator("#tab-bar .tab-btn").nth(0).inner_text() == "adr"
    assert page.locator("#tab-bar .tab-btn").nth(1).inner_text() == "onepager"
    assert page.locator("#doc-pane").is_visible()


def test_results_flow_can_reopen_page_sketch(page):
    _generate_to_results(page, "페이지 스케치 테스트", "문서 구성을 다시 확인")
    page.wait_for_selector("#results-storyboard", state="visible", timeout=30000)
    assert page.locator("#results-storyboard-cards .slide-card").count() > 0
    assert page.locator("#results-storyboard-cards .slide-card-badge").count() >= 3
    assert page.locator("#results-storyboard-cards .slide-card-meter-fill").count() > 0
    assert page.locator("#results-storyboard-cards .slide-card-coverage-note").count() > 0
    assert "왜 이 점수인가?" in page.locator("#results-storyboard-cards .slide-card-coverage-note").first.inner_text()
    page.locator("#results-storyboard-cards .slide-card").first.click()
    page.wait_for_selector("#doc-pane .doc-section-focus", timeout=5000)
    page.click("#sketch-again-btn")
    page.wait_for_selector("#sketch-panel", state="visible", timeout=30000)
    assert page.locator("#sketch-page-cards .slide-card").count() > 0


def test_results_flow_can_recompose_as_ppt_bundle(page):
    _generate_to_results(page, "PPT 재구성 테스트", "발표 자료로 다시 구성")
    page.wait_for_selector("#results-storyboard", state="visible", timeout=30000)
    page.click("#storyboard-ppt-btn")
    page.wait_for_selector('.bundle-card.selected[data-id="presentation_kr"]', timeout=5000)
    page.wait_for_selector("#sketch-panel", state="visible", timeout=30000)
    page.wait_for_selector("#sketch-slides", state="visible", timeout=30000)
    assert page.locator("#sketch-slide-cards .slide-card").count() > 0


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


def test_project_detail_shows_procurement_panel_and_doc_actions(page, live_server):
    project_id = _create_project_with_document(page)
    token = page.evaluate("localStorage.getItem('dd_access_token')")
    request = urllib_request.Request(
        f"{live_server['base_url']}/projects/{project_id}",
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


def test_project_detail_shows_procurement_ai_role_board(page, live_server):
    project_id = _create_project_with_document(page, name="조달 AI 역할 상황판")
    token = page.evaluate("localStorage.getItem('dd_access_token')")
    request = urllib_request.Request(
        f"{live_server['base_url']}/projects/{project_id}",
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    with urllib_request.urlopen(request, timeout=5) as response:
        project = json.loads(response.read().decode("utf-8"))

    procurement_decision = {
        "opportunity": {
            "title": "AI 민원상담 플랫폼 구축",
            "issuer": "조달청",
            "budget": "3억원",
            "deadline": "2026-04-01",
            "source_id": "R26BK01398367",
        },
        "hard_filters": [],
        "checklist_items": [{"title": "파트너 확약", "status": "action_needed"}],
        "missing_data": ["파트너 확약서"],
        "soft_fit_score": 72,
        "recommendation": {
            "value": "CONDITIONAL_GO",
            "summary": "핵심 역량은 부합하지만 파트너 확약이 필요합니다.",
        },
        "notes": (
            "[override_reason ts=2026-03-29T00:00:00+00:00 actor=exec-review]\n"
            "예산 집행 우선순위 재조정으로 조건부 재검토\n"
            "[/override_reason]\n\n"
            "[override_reason ts=2026-03-31T00:00:00+00:00 actor=bd-lead]\n"
            "전략 고객 유지 차원에서 예외적으로 proposal 검토 진행\n"
            "[/override_reason]"
        ),
    }

    page.evaluate("switchPage('project-page')")
    page.wait_for_selector(".project-card", timeout=10000)
    page.evaluate(
        """({ project, procurementDecision }) => {
          renderProjectDetail(project, procurementDecision, { procurementEnabled: true });
          document.getElementById('project-list').style.display = 'none';
          document.getElementById('project-detail').style.display = 'block';
        }""",
        {"project": project, "procurementDecision": procurement_decision},
    )

    page.wait_for_selector(".procurement-role-board", timeout=10000)
    page.wait_for_selector(".procurement-owner-strip", timeout=10000)
    page.wait_for_selector("#procurement-role-brief", timeout=10000)
    assert "최종 승인 AI" in page.locator(".procurement-owner-pill", has_text="Current").inner_text()
    assert "결재 흐름" in page.locator(".procurement-owner-pill", has_text="Next").inner_text()
    assert page.locator('[data-procurement-handoff-step="delivery_pm"].done').count() == 1
    assert page.locator('[data-procurement-handoff-step="executive"].active').count() == 1
    assert page.locator(".procurement-role-card").count() == 3
    assert page.locator('.procurement-role-card[data-procurement-role="executive"].active').count() == 1
    assert page.locator("#procurement-role-brief.executive").count() == 1
    assert page.locator(".procurement-role-brief-avatar.executive").count() == 1
    assert "최종 승인 AI 브리핑" in page.locator(".procurement-role-brief-title").inner_text()
    assert "전략 고객 유지 차원에서 예외적으로 proposal 검토 진행" in page.locator("#project-procurement-override-reason").input_value()
    assert "최근 작성자 bd-lead" in page.locator(".procurement-override-meta").inner_text()
    assert page.locator("#project-procurement-override-submit", has_text="Override 사유 저장").count() == 1
    assert page.locator(".procurement-override-history-item").count() == 2
    assert "전략 고객 유지 차원에서 예외적으로 proposal 검토 진행" in page.locator(".procurement-override-history-list").inner_text()
    assert "예산 집행 우선순위 재조정으로 조건부 재검토" in page.locator(".procurement-override-history-list").inner_text()
    assert page.locator('.procurement-override-history-item.active').count() == 1
    page.locator('[data-procurement-override-history-index="1"]').click()
    assert "예산 집행 우선순위 재조정으로 조건부 재검토" in page.locator("#project-procurement-override-reason").input_value()
    assert page.locator('[data-procurement-override-history-index="1"].active').count() == 1
    assert page.locator('[data-procurement-brief-action="executive"]', has_text="결재 요청").count() == 1
    assert page.locator(".procurement-role-brief-section", has_text="Recent Activity").count() == 1
    assert page.locator(".procurement-role-brief-log li", has_text="Approval").count() == 1
    assert page.locator(".procurement-role-brief-log-time").count() >= 3
    assert page.locator(".procurement-role-card", has_text="제안/영업 리드 AI").locator("button", has_text="판단 갱신").count() == 1
    assert page.locator(".procurement-role-card", has_text="수행 리드 AI").locator("button", has_text="수행계획 생성").count() == 1
    assert page.locator(".procurement-role-card", has_text="최종 승인 AI").locator("button", has_text="결재 요청").count() == 1
    page.locator('[data-procurement-role="proposal_bd"]').click()
    page.locator('[data-procurement-brief-tab="proposal_bd"]').click()
    assert "제안/영업 리드 AI 브리핑" in page.locator(".procurement-role-brief-title").inner_text()
    assert page.locator('[data-procurement-brief-action="proposal_bd"]', has_text="판단 갱신").count() == 1
    assert page.locator('.procurement-role-card[data-procurement-role="proposal_bd"].active').count() == 1
    assert page.locator("#procurement-role-brief.proposal_bd").count() == 1
    page.locator('[data-procurement-brief-tab="delivery_pm"]').click()
    assert "수행 리드 AI 브리핑" in page.locator(".procurement-role-brief-title").inner_text()
    assert page.locator('[data-procurement-brief-action="delivery_pm"]', has_text="수행계획 생성").count() == 1
    assert page.locator(".procurement-role-brief-avatar.delivery_pm").count() == 1
    assert page.locator("#procurement-role-brief.delivery_pm").count() == 1


def test_project_detail_shows_override_guidance_for_no_go_downstream(page, live_server):
    project_id = _create_project_with_document(page, name="조달 Override Guidance")
    token = page.evaluate("localStorage.getItem('dd_access_token')")
    request = urllib_request.Request(
        f"{live_server['base_url']}/projects/{project_id}",
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    with urllib_request.urlopen(request, timeout=5) as response:
        project = json.loads(response.read().decode("utf-8"))

    project["documents"].append(
        {
            "doc_id": "proposal-downstream-doc",
            "bundle_id": "proposal_kr",
            "title": "예외 진행 제안서",
            "generated_at": "2026-03-31T08:30:00+00:00",
        }
    )
    procurement_decision = {
        "opportunity": {
            "title": "데이터 거버넌스 고도화",
            "issuer": "행정안전부",
            "budget": "4억원",
            "deadline": "2026-04-15",
            "source_id": "R26BK01999999",
        },
        "hard_filters": [{"blocking": True, "status": "fail", "code": "capability_gap"}],
        "checklist_items": [{"title": "필수 레퍼런스 보강", "status": "action_needed"}],
        "missing_data": ["파트너 확약서"],
        "soft_fit_score": 41,
        "recommendation": {
            "value": "NO_GO",
            "summary": "핵심 capability gap이 있어 현재는 NO_GO가 적절합니다.",
        },
        "notes": "",
    }

    page.evaluate("switchPage('project-page')")
    page.wait_for_selector(".project-card", timeout=10000)
    page.evaluate(
        """({ project, procurementDecision }) => {
          renderProjectDetail(project, procurementDecision, { procurementEnabled: true });
          document.getElementById('project-list').style.display = 'none';
          document.getElementById('project-detail').style.display = 'block';
        }""",
        {"project": project, "procurementDecision": procurement_decision},
    )

    page.wait_for_selector(".procurement-override-guidance.warning", timeout=10000)
    assert "NO_GO 예외 진행 사유 기록 필요" in page.locator(".procurement-override-guidance").inner_text()
    assert "최종 승인 AI가 NO_GO 예외 진행 사유를 먼저 기록" in page.locator(".procurement-owner-head").inner_text()
    assert page.locator(".procurement-role-card", has_text="최종 승인 AI").locator("button", has_text="Override 사유 기록").count() == 1
    assert page.locator('[data-procurement-brief-action="executive"]', has_text="Override 사유 기록").count() == 1
    assert "Override required" in page.locator(".procurement-role-brief-meta").inner_text()
    page.locator(".procurement-override-guidance button", has_text="사유 입력으로 이동").click()
    assert page.evaluate("document.activeElement && document.activeElement.id") == "project-procurement-override-reason"


def test_project_detail_shows_decision_council_panel_and_provenance(page, live_server):
    project_id = _create_project_with_document(page, name="Decision Council UI")
    token = page.evaluate("localStorage.getItem('dd_access_token')")
    request = urllib_request.Request(
        f"{live_server['base_url']}/projects/{project_id}",
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    with urllib_request.urlopen(request, timeout=5) as response:
        project = json.loads(response.read().decode("utf-8"))

    project["documents"][0]["source_decision_council_session_id"] = "council-session-ui"
    project["documents"][0]["source_decision_council_session_revision"] = 2
    project["documents"][0]["source_decision_council_direction"] = "proceed_with_conditions"
    project["documents"][0]["approval_status"] = "in_review"
    project["documents"].append(
        {
            "doc_id": "proposal-council-doc-ui",
            "request_id": "req-e2e-proposal-council",
            "bundle_id": "proposal_kr",
            "title": "입찰 제안서 초안",
            "generated_at": "2026-04-02T10:00:00+00:00",
            "approval_status": "draft",
            "source_decision_council_session_id": "council-session-ui",
            "source_decision_council_session_revision": 2,
            "source_decision_council_direction": "proceed_with_conditions",
        }
    )

    procurement_decision = {
        "opportunity": {
            "title": "공공데이터 품질 고도화 사업",
            "issuer": "행정안전부",
            "budget": "5억원",
            "deadline": "2026-05-10",
            "source_id": "R26BK05550001",
        },
        "hard_filters": [],
        "checklist_items": [{"title": "컨소시엄 파트너 확약", "status": "action_needed"}],
        "missing_data": ["최근 3년 공공 레퍼런스 확인서"],
        "soft_fit_score": 76,
        "recommendation": {
            "value": "CONDITIONAL_GO",
            "summary": "핵심 역량은 부합하지만 증빙 보완이 선행되어야 합니다.",
        },
        "notes": "",
    }
    council_session = {
        "session_id": "council-session-ui",
        "session_key": f"{project_id}:public_procurement:bid_decision_kr",
        "session_revision": 2,
        "tenant_id": "system",
        "project_id": project_id,
        "use_case": "public_procurement",
        "target_bundle_type": "bid_decision_kr",
        "supported_bundle_types": ["bid_decision_kr", "proposal_kr"],
        "goal": "입찰 참여 여부와 조건, 리스크를 경영진이 빠르게 검토할 수 있게 정리한다.",
        "context": "전략 고객 유지 관점에서 파트너 협의가 병행 중이다.",
        "constraints": "대외 확정 표현 없이 조건부 진행 근거만 정리한다.",
        "source_procurement_decision_id": "decision-ui-1",
        "source_snapshot_ids": ["snap-ui-1"],
        "created_at": "2026-04-02T09:00:00+00:00",
        "updated_at": "2026-04-02T09:00:00+00:00",
        "role_opinions": [
            {
                "role": "Requirement Analyst",
                "stance": "support",
                "summary": "요구사항과 당사 capability는 대체로 부합합니다.",
                "evidence_refs": [],
                "risks": [],
                "disagreements": [],
                "recommended_actions": [],
            },
            {
                "role": "Risk Reviewer",
                "stance": "caution",
                "summary": "증빙 미확보 상태를 확정 사실처럼 쓰면 안 됩니다.",
                "evidence_refs": [],
                "risks": [],
                "disagreements": [],
                "recommended_actions": [],
            },
            {
                "role": "Domain Strategist",
                "stance": "support",
                "summary": "조건만 닫히면 전략적으로 진행 가치가 있습니다.",
                "evidence_refs": [],
                "risks": [],
                "disagreements": [],
                "recommended_actions": [],
            },
            {
                "role": "Compliance Reviewer",
                "stance": "caution",
                "summary": "컨소시엄 및 실적 증빙은 별도 gate로 남겨야 합니다.",
                "evidence_refs": [],
                "risks": [],
                "disagreements": [],
                "recommended_actions": [],
            },
            {
                "role": "Drafting Lead",
                "stance": "support",
                "summary": "조건, 리스크, 열린 질문을 분리해 decision memo로 정리해야 합니다.",
                "evidence_refs": [],
                "risks": [],
                "disagreements": [],
                "recommended_actions": [],
            },
        ],
        "disagreements": [
            "전략 가치는 높지만 증빙 미확보를 확정 사실처럼 다루면 안 된다는 이견이 남아 있습니다.",
        ],
        "risks": [
            "컨소시엄 파트너 확약이 아직 확정되지 않았습니다.",
            "최근 3년 공공 레퍼런스 증빙이 필요합니다.",
        ],
        "consensus": {
            "alignment": "mixed",
            "recommended_direction": "proceed_with_conditions",
            "summary": "Council은 조건부 진행을 권고하며, 보완 조건과 리스크를 분리해 전달해야 한다고 봅니다.",
            "strategy_options": [
                "조건부 Go로 정리하고 보완 조건을 별도 gate로 제시",
            ],
            "disagreements": [
                "전략 가치와 증빙 리스크 사이의 균형을 어떻게 표현할지 의견이 갈립니다.",
            ],
            "top_risks": [
                "파트너 확약 누락",
            ],
            "conditions": [
                "컨소시엄 파트너 확약을 문서화해야 합니다.",
            ],
            "open_questions": [
                "최근 3년 공공 레퍼런스 확인서는 확보됐는가?",
            ],
        },
        "handoff": {
            "target_bundle_type": "bid_decision_kr",
            "recommended_direction": "proceed_with_conditions",
            "drafting_brief": "조건부 진행 방향과 보완 gate를 분리한 bid_decision_kr를 작성합니다.",
            "must_include": [
                "최종 권고 방향: proceed_with_conditions",
            ],
            "must_address": [
                "컨소시엄 파트너 확약",
                "최근 3년 공공 레퍼런스 증빙",
            ],
            "must_not_claim": [
                "파트너 확약이 완료됐다고 단정하지 말 것",
            ],
            "open_questions": [
                "최근 3년 공공 레퍼런스 확인서는 확보됐는가?",
            ],
            "source_procurement_decision_id": "decision-ui-1",
        },
    }

    page.evaluate("switchPage('project-page')")
    page.wait_for_selector(".project-card", timeout=10000)
    page.evaluate(
        """({ project, procurementDecision, councilSession }) => {
          renderProjectDetail(project, procurementDecision, {
            procurementEnabled: true,
            decisionCouncilSession: councilSession,
          });
          document.getElementById('project-list').style.display = 'none';
          document.getElementById('project-detail').style.display = 'block';
        }""",
        {
            "project": project,
            "procurementDecision": procurement_decision,
            "councilSession": council_session,
        },
    )

    page.wait_for_selector(".decision-council-panel", timeout=10000)
    assert page.locator(".decision-council-panel", has_text="Decision Council v1").count() == 1
    assert "입찰 참여 여부와 조건, 리스크" in page.locator("#project-decision-council-goal").input_value()
    assert page.locator('[data-decision-council-session="council-session-ui"]').count() == 1
    assert page.locator(".decision-council-chip.warning", has_text="조건부 진행").count() >= 1
    assert page.locator(".decision-council-role-card").count() == 5
    assert page.locator(".decision-council-linked-doc", has_text="현재 council handoff").count() == 2
    assert page.locator(".decision-council-linked-doc", has_text="proposal_kr").count() == 1
    assert page.locator(".doc-item .tag", has_text="Council v1 r2").count() == 2
    assert page.locator(".doc-item .tag", has_text="조건부 진행").count() == 2
    assert page.locator('[data-decision-council-doc-status="current"]', has_text="현재 council 기준").count() == 2
    assert page.locator('[data-decision-council-doc-followup]').count() == 0


def test_project_detail_marks_stale_decision_council_and_blocks_generate(page, live_server):
    project_id = _create_project_with_document(page, name="Decision Council Stale UI")
    token = page.evaluate("localStorage.getItem('dd_access_token')")
    request = urllib_request.Request(
        f"{live_server['base_url']}/projects/{project_id}",
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    with urllib_request.urlopen(request, timeout=5) as response:
        project = json.loads(response.read().decode("utf-8"))

    project["documents"][0]["source_decision_council_session_id"] = "council-session-stale-ui"
    project["documents"][0]["source_decision_council_session_revision"] = 1
    project["documents"][0]["source_decision_council_direction"] = "proceed"
    project["documents"].append(
        {
            "doc_id": "proposal-council-doc-stale-ui",
            "request_id": "req-e2e-stale-proposal-council",
            "bundle_id": "proposal_kr",
            "title": "이전 council 기준 제안서",
            "generated_at": "2026-04-01T09:30:00+00:00",
            "approval_status": "draft",
            "source_decision_council_session_id": "council-session-stale-ui",
            "source_decision_council_session_revision": 1,
            "source_decision_council_direction": "proceed",
        }
    )
    procurement_decision = {
        "opportunity": {
            "title": "공공 AI 분석 사업",
            "issuer": "조달청",
            "budget": "6억원",
            "deadline": "2026-06-15",
            "source_id": "R26BK07770003",
        },
        "hard_filters": [],
        "checklist_items": [{"title": "레퍼런스 증빙 최신화", "status": "action_needed"}],
        "missing_data": ["최신 공공 구축 실적 확인"],
        "soft_fit_score": 61,
        "recommendation": {
            "value": "NO_GO",
            "summary": "현재 기준으로는 즉시 진행보다 재검토가 필요합니다.",
        },
        "notes": "",
    }
    council_session = {
        "session_id": "council-session-stale-ui",
        "session_key": f"{project_id}:public_procurement:bid_decision_kr",
        "session_revision": 1,
        "tenant_id": "system",
        "project_id": project_id,
        "use_case": "public_procurement",
        "target_bundle_type": "bid_decision_kr",
        "supported_bundle_types": ["bid_decision_kr", "proposal_kr"],
        "goal": "이전 recommendation 기준의 전략 방향을 정리한다.",
        "context": "",
        "constraints": "",
        "source_procurement_decision_id": "decision-stale-ui",
        "source_procurement_updated_at": "2026-04-01T09:00:00+00:00",
        "source_procurement_recommendation_value": "GO",
        "source_procurement_missing_data_count": 0,
        "source_procurement_action_needed_count": 0,
        "source_procurement_blocking_hard_filter_count": 0,
        "source_snapshot_ids": ["snap-stale-ui"],
        "created_at": "2026-04-01T09:00:00+00:00",
        "updated_at": "2026-04-01T09:00:00+00:00",
        "current_procurement_binding_status": "stale",
        "current_procurement_binding_reason_code": "procurement_updated",
        "current_procurement_binding_summary": "현재 procurement recommendation 또는 checklist가 council 실행 이후 갱신되어 다시 실행해야 합니다.",
        "current_procurement_updated_at": "2026-04-03T09:00:00+00:00",
        "current_procurement_recommendation_value": "NO_GO",
        "current_procurement_missing_data_count": 1,
        "current_procurement_action_needed_count": 1,
        "current_procurement_blocking_hard_filter_count": 0,
        "role_opinions": [
            {
                "role": "Requirement Analyst",
                "stance": "support",
                "summary": "이전 상태 기준에서는 진행 근거가 충분했습니다.",
                "evidence_refs": [],
                "risks": [],
                "disagreements": [],
                "recommended_actions": [],
            },
            {
                "role": "Risk Reviewer",
                "stance": "caution",
                "summary": "최신 증빙 기준으로는 재검토가 필요합니다.",
                "evidence_refs": [],
                "risks": [],
                "disagreements": [],
                "recommended_actions": [],
            },
            {
                "role": "Domain Strategist",
                "stance": "support",
                "summary": "전략 가치는 있으나 최신 recommendation을 따라야 합니다.",
                "evidence_refs": [],
                "risks": [],
                "disagreements": [],
                "recommended_actions": [],
            },
            {
                "role": "Compliance Reviewer",
                "stance": "caution",
                "summary": "현재 checklist와 맞지 않는 표현은 stale입니다.",
                "evidence_refs": [],
                "risks": [],
                "disagreements": [],
                "recommended_actions": [],
            },
            {
                "role": "Drafting Lead",
                "stance": "caution",
                "summary": "다시 실행 전에는 최신 bid_decision_kr handoff로 쓰면 안 됩니다.",
                "evidence_refs": [],
                "risks": [],
                "disagreements": [],
                "recommended_actions": [],
            },
        ],
        "disagreements": ["현재 checklist와 이전 council 방향이 어긋납니다."],
        "risks": ["최신 실적 증빙이 미확인입니다."],
        "consensus": {
            "alignment": "mixed",
            "recommended_direction": "proceed",
            "summary": "이전 실행 시점에는 진행 방향으로 정리됐습니다.",
            "strategy_options": ["이전 판단 기준 유지"],
            "disagreements": [],
            "top_risks": ["최신 실적 증빙 미확인"],
            "conditions": [],
            "open_questions": [],
        },
        "handoff": {
            "target_bundle_type": "bid_decision_kr",
            "recommended_direction": "proceed",
            "drafting_brief": "이전 recommendation 기준의 bid_decision_kr 작성",
            "must_include": [],
            "must_address": ["최신 실적 증빙"],
            "must_not_claim": [],
            "open_questions": [],
            "source_procurement_decision_id": "decision-stale-ui",
        },
    }

    page.evaluate("switchPage('project-page')")
    page.wait_for_selector(".project-card", timeout=10000)
    page.evaluate(
        """({ project, procurementDecision, councilSession }) => {
          renderProjectDetail(project, procurementDecision, {
            procurementEnabled: true,
            decisionCouncilSession: councilSession,
          });
          document.getElementById('project-list').style.display = 'none';
          document.getElementById('project-detail').style.display = 'block';
        }""",
        {
            "project": project,
            "procurementDecision": procurement_decision,
            "councilSession": council_session,
        },
    )

    page.wait_for_selector('[data-decision-council-binding="stale"]', timeout=10000)
    assert page.locator('[data-decision-council-binding="stale"]', has_text="현재 procurement 기준과 council handoff가 어긋났습니다.").count() == 1
    assert page.locator('[data-decision-council-binding="stale"]', has_text="council 기준 2026-04-01 → 현재 procurement 2026-04-03").count() == 1
    assert page.locator('[data-decision-council-binding="stale"]', has_text="당시 권고안 GO → 현재 NO_GO").count() == 1
    assert page.locator('[data-decision-council-binding="stale"]', has_text="현재 action needed 1건").count() == 1
    assert page.locator('[data-decision-council-binding="stale"]', has_text="현재 missing data 1건").count() == 1
    assert page.locator(".decision-council-chip.danger", has_text="Stale handoff").count() >= 1
    assert page.locator("#project-decision-council-run-submit", has_text="Decision Council 다시 실행").count() == 1
    assert page.locator('[data-decision-council-generate]').is_disabled()
    assert page.locator('[data-decision-council-generate-proposal]').is_disabled()
    assert page.locator(".decision-council-linked-doc", has_text="이전 council 기준").count() == 2
    assert page.locator(".decision-council-linked-doc", has_text="proposal_kr 문서는 이 이전 council 기준").count() == 1
    assert page.locator('[data-decision-council-doc-status="stale_procurement"]', has_text="현재 procurement 대비 이전 council 기준").count() == 2
    stale_doc = page.locator(".doc-item").filter(
        has=page.locator('[data-decision-council-doc-status="stale_procurement"]')
    ).first
    stale_doc.locator('[data-decision-council-doc-followup="stale_procurement"]').click()
    assert page.locator("#project-decision-council-run-submit").evaluate("el => document.activeElement === el")
    page.evaluate(
        """() => {
          window.__lastCouncilDocGuard = '';
          window.confirm = (message) => {
            window.__lastCouncilDocGuard = message;
            return false;
          };
        }"""
    )
    stale_doc.locator("button", has_text="결재 요청").click()
    page.wait_for_timeout(200)
    assert "현재 procurement 대비 이전 council 기준" in page.evaluate("window.__lastCouncilDocGuard")
    assert page.locator(".approval-modal-overlay").count() == 0
    page.evaluate("() => { window.confirm = () => true; }")
    stale_doc.locator("button", has_text="결재 요청").click()
    page.wait_for_selector(".approval-modal-overlay", timeout=5000)
    assert page.locator('[data-approval-decision-council-warning="stale_procurement"]', has_text="현재 procurement 대비 이전 council 기준").count() == 1
    assert page.locator('[data-approval-decision-council-followup="stale_procurement"]', has_text="Council 다시 실행").count() == 1
    page.locator('[data-approval-decision-council-followup="stale_procurement"]').click()
    page.wait_for_selector(".approval-modal-overlay", state="hidden", timeout=5000)
    assert page.locator("#project-decision-council-run-submit").evaluate("el => document.activeElement === el")
    page.evaluate("() => { window.confirm = () => true; }")
    stale_doc.locator("button", has_text="결재 요청").click()
    page.wait_for_selector(".approval-modal-overlay", timeout=5000)
    page.locator(".approval-modal-overlay button", has_text="취소").click()
    page.wait_for_selector(".approval-modal-overlay", state="hidden", timeout=5000)
    stale_doc.locator("button", has_text="공유").click()
    page.wait_for_selector('[data-share-decision-council-warning="stale_procurement"]', timeout=5000)
    assert page.locator('[data-share-decision-council-warning="stale_procurement"]', has_text="현재 procurement 대비 이전 council 기준").count() == 1
    assert page.locator('[data-share-decision-council-followup="stale_procurement"]', has_text="Council 다시 실행").count() == 1
    shared_path = page.locator("#share-url-input").input_value()
    page.locator('[data-share-decision-council-followup="stale_procurement"]').click()
    page.wait_for_selector(".modal-overlay", state="hidden", timeout=5000)
    assert page.locator("#project-decision-council-run-submit").evaluate("el => document.activeElement === el")
    stale_doc.locator("button", has_text="공유").click()
    page.wait_for_selector('[data-share-decision-council-warning="stale_procurement"]', timeout=5000)
    shared_path = page.locator("#share-url-input").input_value()
    page.goto(f"{live_server['base_url']}{shared_path}")
    page.wait_for_selector('[data-shared-decision-council-warning="stale_procurement"]', timeout=5000)
    assert page.locator('[data-shared-decision-council-warning="stale_procurement"]', has_text="현재 procurement 대비 이전 council 기준").count() == 1
    assert page.locator('[data-shared-decision-council-warning="stale_procurement"]', has_text="현재 procurement recommendation 또는 checklist가 바뀌어").count() == 1


def test_project_detail_decision_council_run_posts_goal_and_refreshes(page, live_server):
    project_id = _create_project_with_document(page, name="Decision Council Run")
    token = page.evaluate("localStorage.getItem('dd_access_token')")
    request = urllib_request.Request(
        f"{live_server['base_url']}/projects/{project_id}",
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    with urllib_request.urlopen(request, timeout=5) as response:
        project = json.loads(response.read().decode("utf-8"))

    procurement_decision = {
        "opportunity": {
            "title": "AI 민원 분석 사업",
            "issuer": "조달청",
            "budget": "4억원",
            "deadline": "2026-06-01",
            "source_id": "R26BK06660002",
        },
        "hard_filters": [],
        "checklist_items": [],
        "missing_data": [],
        "soft_fit_score": 84,
        "recommendation": {
            "value": "GO",
            "summary": "즉시 진행 가능한 상태입니다.",
        },
        "notes": "",
    }

    captured: list[dict] = []

    def handle_council_run(route):
        captured.append(route.request.post_data_json)
        route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps(
                {
                    "session_id": "council-run-ui",
                    "session_key": f"{project_id}:public_procurement:bid_decision_kr",
                    "session_revision": 1,
                    "tenant_id": "system",
                    "project_id": project_id,
                    "use_case": "public_procurement",
                    "target_bundle_type": "bid_decision_kr",
                    "supported_bundle_types": ["bid_decision_kr", "proposal_kr"],
                    "goal": captured[0]["goal"],
                    "context": captured[0].get("context", ""),
                    "constraints": captured[0].get("constraints", ""),
                    "source_procurement_decision_id": "decision-run-ui",
                    "source_snapshot_ids": [],
                    "created_at": "2026-04-02T10:00:00+00:00",
                    "updated_at": "2026-04-02T10:00:00+00:00",
                    "operation": "created",
                    "role_opinions": [],
                    "disagreements": [],
                    "risks": [],
                    "consensus": {
                        "alignment": "aligned",
                        "recommended_direction": "proceed",
                        "summary": "즉시 진행 방향으로 합의했습니다.",
                        "strategy_options": [],
                        "disagreements": [],
                        "top_risks": [],
                        "conditions": [],
                        "open_questions": [],
                    },
                    "handoff": {
                        "target_bundle_type": "bid_decision_kr",
                        "recommended_direction": "proceed",
                        "drafting_brief": "즉시 진행 판단을 정리합니다.",
                        "must_include": [],
                        "must_address": [],
                        "must_not_claim": [],
                        "open_questions": [],
                        "source_procurement_decision_id": "decision-run-ui",
                    },
                }
            ),
        )

    page.route(f"**/projects/{project_id}/decision-council/run", handle_council_run)
    page.evaluate("switchPage('project-page')")
    page.wait_for_selector(".project-card", timeout=10000)
    page.evaluate(
        """({ project, procurementDecision }) => {
          renderProjectDetail(project, procurementDecision, { procurementEnabled: true });
          document.getElementById('project-list').style.display = 'none';
          document.getElementById('project-detail').style.display = 'block';
          window.__decisionCouncilReloaded = '';
          window.loadProjectDetail = async (projectId) => {
            window.__decisionCouncilReloaded = projectId;
          };
        }""",
        {"project": project, "procurementDecision": procurement_decision},
    )

    page.fill("#project-decision-council-goal", "입찰 진행 방향을 경영진 보고용으로 정리한다.")
    page.fill("#project-decision-council-context", "전략 고객 유지 맥락이 있다.")
    page.fill("#project-decision-council-constraints", "대외 확정 표현은 금지한다.")
    page.locator("#project-decision-council-run-submit").click()

    page.wait_for_selector("#project-decision-council-status.success", timeout=10000)
    assert "자동 반영" in page.locator("#project-decision-council-status").inner_text()
    assert captured[0]["goal"] == "입찰 진행 방향을 경영진 보고용으로 정리한다."
    assert captured[0]["context"] == "전략 고객 유지 맥락이 있다."
    assert captured[0]["constraints"] == "대외 확정 표현은 금지한다."
    assert page.evaluate("window.__decisionCouncilReloaded") == project_id


def test_project_detail_blocks_no_go_downstream_until_override_reason(page, live_server):
    from app.schemas import (
        NormalizedProcurementOpportunity,
        ProcurementChecklistItem,
        ProcurementDecisionUpsert,
        ProcurementHardFilterResult,
        ProcurementRecommendation,
    )
    from app.storage.procurement_store import ProcurementDecisionStore

    project_id = _create_project_with_document(page, name="조달 Downstream Guard")
    procurement_store = ProcurementDecisionStore(base_dir=os.environ["DATA_DIR"])
    procurement_store.upsert(
        ProcurementDecisionUpsert(
            project_id=project_id,
            tenant_id="system",
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b",
                source_id="R26-E2E-001",
                title="공공 데이터 운영 고도화",
                issuer="조달청",
            ),
            hard_filters=[
                ProcurementHardFilterResult(
                    code="capability_gap",
                    label="핵심 수행역량",
                    status="fail",
                    blocking=True,
                    reason="필수 운영 실적 부족",
                )
            ],
            checklist_items=[
                ProcurementChecklistItem(
                    category="staffing",
                    title="전담 PM 확보",
                    status="action_needed",
                    severity="high",
                )
            ],
            recommendation=ProcurementRecommendation(
                value="NO_GO",
                summary="핵심 운영 실적 부족으로 예외 승인 없이는 downstream 진행 불가",
            ),
        )
    )
    page.evaluate("switchPage('project-page')")
    page.evaluate("(projectId) => loadProjectDetail(projectId)", project_id)

    page.wait_for_selector(".procurement-override-guidance.warning", timeout=10000)
    page.wait_for_selector('[data-procurement-bundle="proposal_kr"]:not([disabled])', timeout=10000)
    page.locator('[data-procurement-bundle="proposal_kr"]').click()

    _wait_until_text_contains(
        page,
        "#project-procurement-status",
        "override 사유를 먼저 저장하세요",
        timeout_ms=10000,
    )
    assert page.evaluate("document.activeElement && document.activeElement.id") == "project-procurement-override-reason"


def test_locations_page_shows_procurement_quality_summary(page):
    from app.schemas import (
        NormalizedProcurementOpportunity,
        ProcurementDecisionUpsert,
        ProcurementHardFilterResult,
        ProcurementRecommendation,
    )
    from app.storage.audit_store import AuditLog, AuditStore
    from app.storage.procurement_store import ProcurementDecisionStore

    project_id = _create_project_with_document(page, name="거점 조달 품질 요약")
    procurement_store = ProcurementDecisionStore(base_dir=os.environ["DATA_DIR"])
    procurement_store.upsert(
        ProcurementDecisionUpsert(
            project_id=project_id,
            tenant_id="system",
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b",
                source_id="R26-E2E-LOC-001",
                title="거점 조달 품질 요약",
                issuer="조달청",
            ),
            hard_filters=[
                ProcurementHardFilterResult(
                    code="capability_gap",
                    label="핵심 수행역량",
                    status="fail",
                    blocking=True,
                    reason="필수 운영 실적 부족",
                )
            ],
            recommendation=ProcurementRecommendation(
                value="NO_GO",
                summary="override 사유 없이는 downstream 진행 불가",
            ),
        )
    )
    AuditStore("system").append(
        AuditLog(
            log_id=str(uuid.uuid4()),
            tenant_id="system",
            timestamp=datetime.now(timezone.utc).isoformat(timespec="microseconds"),
            user_id="e2e-admin",
            username="e2e_admin",
            user_role="admin",
            ip_address="127.0.0.1",
            user_agent="playwright",
            action="procurement.downstream_blocked",
            resource_type="procurement",
            resource_id=project_id,
            resource_name="",
            result="failure",
            detail={
                "project_id": project_id,
                "bundle_type": "proposal_kr",
                "error_code": "procurement_override_reason_required",
                "recommendation": "NO_GO",
            },
            session_id="sess-e2e-procurement-summary",
        )
    )

    page.evaluate("switchPage('locations-page')")
    page.wait_for_selector(".location-card", timeout=10000)
    page.locator('[data-location-procurement="system"]').click()

    page.wait_for_selector("#location-procurement-modal", state="visible", timeout=10000)
    modal = page.locator("#location-procurement-modal-body")
    _wait_until_text_contains(
        page,
        "#location-procurement-modal-body",
        "Blocked downstream 시도",
        timeout_ms=10000,
    )
    assert "Blocked downstream 시도" in modal.inner_text()
    assert "최근 override reason 미기입으로 차단된 downstream 시도는" in modal.inner_text()
    assert "Override 필요로 downstream 차단" in modal.inner_text()
    assert "procurement_override_reason_required" in modal.inner_text()


def test_locations_page_stale_share_risk_strip_opens_review_preset(page):
    from app.schemas import (
        NormalizedProcurementOpportunity,
        ProcurementDecisionUpsert,
        ProcurementRecommendation,
    )
    from app.storage.audit_store import AuditLog, AuditStore
    from app.storage.procurement_store import ProcurementDecisionStore
    from app.storage.project_store import ProjectStore
    from app.storage.share_store import ShareStore
    from app.storage.tenant_store import TenantStore

    project_id = _create_project_with_document(page, name="거점 stale share 위험 카드")
    TenantStore(Path(os.environ["DATA_DIR"])).create_tenant("t-clean-location", "정상 거점")
    project_store = ProjectStore(base_dir=os.environ["DATA_DIR"])
    project = project_store.get(project_id, tenant_id="system")
    assert project is not None
    assert project.documents
    procurement_store = ProcurementDecisionStore(base_dir=os.environ["DATA_DIR"])
    procurement_store.upsert(
        ProcurementDecisionUpsert(
            project_id=project_id,
            tenant_id="system",
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b",
                source_id="R26-E2E-LOC-STALE-001",
                title="거점 stale share 위험 카드",
                issuer="조달청",
            ),
            recommendation=ProcurementRecommendation(
                value="NO_GO",
                summary="stale public share 노출 확인 필요",
            ),
        )
    )
    share_store = ShareStore("system")
    share = share_store.create(
        tenant_id="system",
        request_id="req-e2e-loc-stale-share",
        title="거점 stale share",
        created_by="e2e_admin",
        bundle_id="bid_decision_kr",
        decision_council_document_status="stale_procurement",
        decision_council_document_status_tone="danger",
        decision_council_document_status_copy="현재 procurement 대비 이전 council 기준",
        decision_council_document_status_summary="현재 procurement recommendation 또는 checklist가 바뀌어 외부 공유 전 재확인이 필요합니다.",
    )
    share_store.increment_access(share.share_id)
    AuditStore("system").append(
        AuditLog(
            log_id=str(uuid.uuid4()),
            tenant_id="system",
            timestamp=datetime.now(timezone.utc).isoformat(timespec="microseconds"),
            user_id="e2e-admin",
            username="e2e_admin",
            user_role="admin",
            ip_address="127.0.0.1",
            user_agent="playwright",
            action="share.create",
            resource_type="share",
            resource_id=share.share_id,
            resource_name="",
            result="success",
            detail={
                "project_id": project_id,
                "share_project_document_id": project.documents[0].doc_id,
                "bundle_type": "bid_decision_kr",
                "share_decision_council_document_status": "stale_procurement",
                "share_decision_council_document_status_tone": "danger",
                "share_decision_council_document_status_copy": "현재 procurement 대비 이전 council 기준",
                "share_decision_council_document_status_summary": "현재 procurement recommendation 또는 checklist가 바뀌어 외부 공유 전 재확인이 필요합니다.",
            },
            session_id="sess-e2e-loc-stale-share",
        )
    )

    page.evaluate("switchPage('locations-page')")
    page.wait_for_selector(".location-card", timeout=10000)
    page.evaluate(
        """() => {
          window.__openedSharedUrl = null;
          window.__copiedSharedUrl = null;
          window.confirm = () => true;
          window.open = (url) => {
            window.__openedSharedUrl = url;
            return null;
          };
          Object.defineProperty(window.navigator, 'clipboard', {
            configurable: true,
            value: {
              writeText: (text) => {
                window.__copiedSharedUrl = text;
                return Promise.resolve();
              },
            },
          });
        }"""
    )
    tenant_order = page.locator('[data-location-procurement]').evaluate_all(
        "(nodes) => nodes.map((node) => node.getAttribute('data-location-procurement'))"
    )
    assert tenant_order.index("system") < tenant_order.index("t-clean-location")
    card_selector = '.location-card:has([data-location-procurement="system"])'
    card = page.locator(".location-card").filter(
        has=page.locator('[data-location-procurement="system"]')
    ).first
    _wait_until_text_contains(
        page,
        card_selector,
        "stale public 노출 1개가 남아 있습니다.",
        timeout_ms=10000,
    )
    card_text = card.inner_text()
    assert "공개 중 1개" in card_text
    assert "최근 public 열람 1개" in card_text
    assert "우선 확인: 입찰 의사결정 문서" in card_text
    assert "현재 procurement 대비 이전 council 기준" in card_text
    assert "활성 공유 링크 · 조회 1회" in card_text
    assert "최근 stale 공유: e2e_admin" in card_text
    assert "· 1회" in card_text
    card.locator('button:has-text("공유 링크 복사")').click()
    copied_url = page.evaluate("() => window.__copiedSharedUrl")
    assert copied_url is not None
    assert copied_url.endswith(f"/shared/{share.share_id}")
    card.locator('button:has-text("외부 공유 review 링크")').click()
    tenant_review_url = page.evaluate("() => window.__copiedSharedUrl")
    assert tenant_review_url is not None
    assert "location_procurement_tenant=system" in tenant_review_url
    assert "location_procurement_activity_actions=share.create" in tenant_review_url
    assert "location_procurement_focus_project" not in tenant_review_url
    card.locator('button:has-text("위험 문서 review 링크")').click()
    focused_review_url = page.evaluate("() => window.__copiedSharedUrl")
    assert focused_review_url is not None
    assert "location_procurement_tenant=system" in focused_review_url
    assert f"location_procurement_focus_project={project_id}" in focused_review_url
    assert "location_procurement_activity_actions=share.create" in focused_review_url
    card.locator('button:has-text("공유 링크 열기")').click()
    assert page.evaluate("() => window.__openedSharedUrl") == f"/shared/{share.share_id}"
    card.locator('[data-location-procurement-stale-share-focus-review="system"]').click()
    page.wait_for_selector("#location-procurement-modal", state="visible", timeout=10000)
    page.wait_for_selector('[data-location-procurement-preset="stale_share_review"].active', timeout=5000)
    page.wait_for_selector(f'[data-location-procurement-focus="{project_id}"]', timeout=5000)
    focused_text = page.locator(f'[data-location-procurement-focus="{project_id}"]').inner_text()
    assert "외부 공유 기준" in focused_text
    assert "활성 공유 링크" in focused_text
    page.locator('#location-procurement-modal .btn-secondary').last.click()
    page.wait_for_selector("#location-procurement-modal", state="hidden", timeout=5000)
    page.locator('[data-location-procurement-stale-share-review="system"]').click()
    page.wait_for_selector("#location-procurement-modal", state="visible", timeout=10000)
    page.wait_for_selector('[data-location-procurement-preset="stale_share_review"].active', timeout=5000)
    page.wait_for_selector('[data-location-procurement-activity-filter="share.create"].active', timeout=5000)
    modal_text = page.locator("#location-procurement-modal-body").inner_text()
    assert "외부 공유 재확인 queue" in modal_text
    assert "현재 procurement 대비 이전 council 기준" in modal_text
    assert "활성 공유 링크" in modal_text
    page.evaluate("closeLocationProcurementSummary()")
    page.wait_for_selector("#location-procurement-modal", state="hidden", timeout=5000)
    card = page.locator(".location-card").filter(
        has=page.locator('[data-location-procurement="system"]')
    ).first
    card.locator('button:has-text("공유 링크 비활성화")').click()
    page.wait_for_function(
        """() => {
          const trigger = document.querySelector('[data-location-procurement="system"]');
          if (!trigger) return false;
          const card = trigger.closest('.location-card');
          return Boolean(card) && !card.innerText.includes('stale public 노출');
        }""",
        timeout=10000,
    )
    updated_card_text = page.locator(".location-card").filter(
        has=page.locator('[data-location-procurement="system"]')
    ).first.inner_text()
    assert "stale public 노출" not in updated_card_text
    shared_status = page.evaluate(
        """async (shareId) => {
          const res = await fetch(`/shared/${shareId}`);
          return res.status;
        }""",
        share.share_id,
    )
    assert shared_status == 404


def test_location_procurement_summary_opens_project_override_flow(page):
    from app.schemas import (
        NormalizedProcurementOpportunity,
        ProcurementDecisionUpsert,
        ProcurementHardFilterResult,
        ProcurementRecommendation,
    )
    from app.storage.audit_store import AuditLog, AuditStore
    from app.storage.procurement_store import ProcurementDecisionStore

    project_id = _create_project_with_document(page, name="거점 모달 점프 테스트")
    procurement_store = ProcurementDecisionStore(base_dir=os.environ["DATA_DIR"])
    procurement_store.upsert(
        ProcurementDecisionUpsert(
            project_id=project_id,
            tenant_id="system",
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b",
                source_id="R26-E2E-LOC-002",
                title="거점 모달 점프 테스트",
                issuer="조달청",
            ),
            hard_filters=[
                ProcurementHardFilterResult(
                    code="capability_gap",
                    label="핵심 수행역량",
                    status="fail",
                    blocking=True,
                    reason="필수 운영 실적 부족",
                )
            ],
            recommendation=ProcurementRecommendation(
                value="NO_GO",
                summary="override 사유 기록이 필요한 상태",
            ),
        )
    )

    AuditStore("system").append(
        AuditLog(
            log_id=str(uuid.uuid4()),
            tenant_id="system",
            timestamp=datetime.now(timezone.utc).isoformat(timespec="microseconds"),
            user_id="e2e-admin",
            username="e2e_admin",
            user_role="admin",
            ip_address="127.0.0.1",
            user_agent="playwright",
            action="procurement.downstream_blocked",
            resource_type="procurement",
            resource_id=project_id,
            resource_name="",
            result="failure",
            detail={
                "project_id": project_id,
                "bundle_type": "proposal_kr",
                "error_code": "procurement_override_reason_required",
                "recommendation": "NO_GO",
            },
            session_id="sess-e2e-procurement-jump",
        )
    )

    page.evaluate("switchPage('locations-page')")
    page.wait_for_selector(".location-card", timeout=10000)
    page.locator('[data-location-procurement="system"]').click()

    page.wait_for_selector("#location-procurement-modal", state="visible", timeout=10000)
    page.evaluate(
        """() => {
          window.__copiedProjectProcurementLink = null;
          Object.defineProperty(navigator, 'clipboard', {
            configurable: true,
            value: {
              writeText: async (text) => { window.__copiedProjectProcurementLink = text; },
            },
          });
        }"""
    )
    page.locator(
        f'#location-procurement-modal .location-procurement-event [data-location-procurement-copy-project-link="{project_id}"]'
    ).first.click()
    copied_from_summary = page.evaluate("window.__copiedProjectProcurementLink")
    assert copied_from_summary is not None
    assert f"project_id={project_id}" in copied_from_summary
    assert "project_procurement_context=" in copied_from_summary
    assert "project_procurement_return_tenant=system" in copied_from_summary
    summary_url_state = page.evaluate(
        """() => Object.fromEntries(new URLSearchParams(location.search).entries())"""
    )
    assert summary_url_state["location_procurement_tenant"] == "system"
    assert "project_id" not in summary_url_state
    page.locator('#location-procurement-modal .btn-secondary').last.click()
    page.wait_for_selector("#location-procurement-modal", state="hidden", timeout=5000)
    page.locator('[data-location-procurement="system"]').click()
    page.wait_for_selector("#location-procurement-modal", state="visible", timeout=10000)
    _wait_until_text_contains(
        page,
        "#location-procurement-modal-body",
        "Remediation 링크 공유",
        timeout_ms=10000,
    )
    modal_text = page.locator("#location-procurement-modal-body").inner_text()
    assert "tenant summary" in modal_text
    assert "blocked remediation" in modal_text
    assert "Remediation handoff queue" in modal_text
    assert "공유됨, 아직 미열람" in modal_text
    page.locator('[data-location-procurement-preset="handoff_review"]').click()
    page.wait_for_selector('[data-location-procurement-preset="handoff_review"].active', timeout=5000)
    page.wait_for_selector(
        '[data-location-procurement-activity-filter="procurement.remediation_link_copied"].active',
        timeout=5000,
    )
    handoff_url_state = page.evaluate(
        """() => Object.fromEntries(new URLSearchParams(location.search).entries())"""
    )
    assert handoff_url_state["location_procurement_activity_actions"] == (
        "procurement.remediation_link_copied,procurement.remediation_link_opened"
    )
    page.locator(
        f'#location-procurement-modal .location-procurement-candidate[data-location-procurement-project="{project_id}"] [data-location-procurement-open="{project_id}"]'
    ).first.click()

    page.wait_for_selector("#project-detail", state="visible", timeout=10000)
    page.wait_for_selector("#project-procurement-override-reason", timeout=10000)
    page.wait_for_selector(
        '[data-project-procurement-remediation="blocked_event"]',
        timeout=10000,
    )
    assert page.locator("#project-detail").inner_text().find("거점 모달 점프 테스트") >= 0
    remediation = page.locator("#project-procurement-remediation-strip")
    assert "Blocked downstream remediation 필요" in remediation.inner_text()
    assert "거점 조달 품질 요약" in remediation.inner_text()
    assert "proposal_kr" not in remediation.inner_text()
    assert "제안서 생성 시도가 override 사유 미기입으로 차단되었습니다." in remediation.inner_text()
    assert page.evaluate("document.activeElement && document.activeElement.id") == "project-procurement-override-reason"
    url_state = page.evaluate(
        """() => Object.fromEntries(new URLSearchParams(location.search).entries())"""
    )
    assert url_state["project_id"] == project_id
    assert url_state["project_procurement_return_tenant"] == "system"
    assert "project_procurement_context" in url_state
    assert "location_procurement_tenant" not in url_state
    page.evaluate("window.__copiedProjectProcurementLink = null;")
    page.locator(f'[data-project-procurement-copy-link="{project_id}"]').click()
    copied_project_link = page.evaluate("window.__copiedProjectProcurementLink")
    assert copied_project_link is not None
    assert f"project_id={project_id}" in copied_project_link
    assert "project_procurement_context=" in copied_project_link
    assert "project_procurement_return_tenant=system" in copied_project_link
    page.evaluate(
        """() => {
          _currentProjectDetail = null;
          _projectProcurementRemediationContext = null;
          _projectProcurementSummaryReturnContext = null;
          const detailEl = document.getElementById('project-detail');
          const listEl = document.getElementById('project-list');
          if (detailEl) detailEl.style.display = 'none';
          if (listEl) listEl.style.display = 'block';
          switchPage('locations-page');
        }"""
    )
    assert page.evaluate("restoreProjectProcurementDetailFromUrl()") is True
    page.wait_for_selector("#project-detail", state="visible", timeout=10000)
    page.wait_for_selector(
        '[data-project-procurement-remediation="blocked_event"]',
        timeout=10000,
    )
    page.wait_for_selector(
        '[data-project-procurement-return="system"]',
        timeout=10000,
    )
    assert page.evaluate("document.activeElement && document.activeElement.id") == "project-procurement-override-reason"
    page.evaluate(
        """() => {
          _locationProcurementCandidateOrder = 'stale_unresolved';
          _locationProcurementCandidateScope = 'resolved_only';
          _locationProcurementCandidateStatusFilters = ['resolved'];
          _locationProcurementActivityActionFilters = ['procurement.downstream_resolved'];
        }"""
    )
    page.locator(f'[data-project-procurement-return="system"]').click()
    page.wait_for_selector("#location-procurement-modal", state="visible", timeout=10000)
    _wait_until_text_contains(
        page,
        "#location-procurement-modal-body",
        "Blocked downstream 시도",
        timeout_ms=10000,
    )
    _wait_until_text_contains(
        page,
        "#location-procurement-modal-body",
        "Remediation 링크 열람",
        timeout_ms=10000,
    )
    returned_url_state = page.evaluate(
        """() => Object.fromEntries(new URLSearchParams(location.search).entries())"""
    )
    assert returned_url_state["location_procurement_tenant"] == "system"
    assert returned_url_state["location_procurement_focus_project"] == project_id
    assert "project_id" not in returned_url_state
    assert "location_procurement_candidate_scope" not in returned_url_state
    assert "location_procurement_candidate_statuses" not in returned_url_state
    returned_modal_text = page.locator("#location-procurement-modal-body").inner_text()
    assert "shared link restore" in returned_modal_text
    assert "열람 기준" in returned_modal_text
    assert "열람됨, 미해소" in returned_modal_text
    page.locator(
        f'#location-procurement-modal .location-procurement-event [data-location-procurement-open="{project_id}"]'
    ).first.click()
    page.wait_for_selector("#project-detail", state="visible", timeout=10000)
    page.locator(f'[data-procurement-remediation-dismiss="{project_id}"]').click()
    assert page.locator("#project-procurement-remediation-strip").count() == 0


def test_location_procurement_summary_blocked_event_retries_after_override_reason(page):
    from app.schemas import (
        NormalizedProcurementOpportunity,
        ProcurementDecisionUpsert,
        ProcurementHardFilterResult,
        ProcurementRecommendation,
    )
    from app.storage.audit_store import AuditLog, AuditStore
    from app.storage.procurement_store import ProcurementDecisionStore

    project_id = _create_project_with_document(page, name="거점 모달 재시도 테스트")
    procurement_store = ProcurementDecisionStore(base_dir=os.environ["DATA_DIR"])

    def seed_resolved_candidate(name: str, source_id: str) -> str:
        candidate_project_id = _create_project_with_document(page, name=name)
        procurement_store.upsert(
            ProcurementDecisionUpsert(
                project_id=candidate_project_id,
                tenant_id="system",
                opportunity=NormalizedProcurementOpportunity(
                    source_kind="g2b",
                    source_id=source_id,
                    title=name,
                    issuer="조달청",
                ),
                hard_filters=[
                    ProcurementHardFilterResult(
                        code="reference_gap",
                        label="유사 레퍼런스",
                        status="fail",
                        blocking=True,
                        reason="유사 실적 부족",
                    )
                ],
                recommendation=ProcurementRecommendation(
                    value="NO_GO",
                    summary="기존 override 이후 resolved 상태",
                ),
            )
        )
        page.evaluate(
            """async ({ projectId }) => {
              const token = localStorage.getItem('dd_access_token');
              const headers = {
                'Content-Type': 'application/json',
                ...(token ? { Authorization: `Bearer ${token}` } : {}),
              };
              const added = await fetch(`/projects/${projectId}/documents`, {
                method: 'POST',
                headers,
                body: JSON.stringify({
                  request_id: `req-${projectId}-proposal`,
                  bundle_id: 'proposal_kr',
                  title: '기존 예외 진행 제안서',
                  docs: [{ doc_type: 'proposal', markdown: '# 기존 제안서' }],
                }),
              });
              if (!added.ok) throw new Error(`project document add failed: ${added.status}`);
            }""",
            {"projectId": candidate_project_id},
        )
        audit_store = AuditStore("system")
        audit_store.append(
            AuditLog(
                log_id=str(uuid.uuid4()),
                tenant_id="system",
                timestamp=datetime.now(timezone.utc).isoformat(timespec="microseconds"),
                user_id="ops-admin",
                username="ops_admin",
                user_role="admin",
                ip_address="127.0.0.1",
                user_agent="playwright",
                action="procurement.downstream_blocked",
                resource_type="procurement",
                resource_id=candidate_project_id,
                resource_name="",
                result="failure",
                detail={
                    "project_id": candidate_project_id,
                    "bundle_type": "proposal_kr",
                    "error_code": "procurement_override_reason_required",
                    "recommendation": "NO_GO",
                },
                session_id=f"sess-{candidate_project_id}-blocked",
            )
        )
        audit_store.append(
            AuditLog(
                log_id=str(uuid.uuid4()),
                tenant_id="system",
                timestamp=datetime.now(timezone.utc).isoformat(timespec="microseconds"),
                user_id="ops-admin",
                username="ops_admin",
                user_role="admin",
                ip_address="127.0.0.1",
                user_agent="playwright",
                action="procurement.downstream_resolved",
                resource_type="procurement",
                resource_id=candidate_project_id,
                resource_name="",
                result="success",
                detail={
                    "project_id": candidate_project_id,
                    "bundle_type": "proposal_kr",
                    "recommendation": "NO_GO",
                },
                session_id=f"sess-{candidate_project_id}-resolved",
            )
        )
        return candidate_project_id

    seed_resolved_candidate("가-해소 후보 1", "R26-E2E-LOC-101")
    seed_resolved_candidate("가-해소 후보 2", "R26-E2E-LOC-102")
    seed_resolved_candidate("가-해소 후보 3", "R26-E2E-LOC-103")
    seed_resolved_candidate("가-해소 후보 4", "R26-E2E-LOC-104")

    procurement_store.upsert(
        ProcurementDecisionUpsert(
            project_id=project_id,
            tenant_id="system",
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b",
                source_id="R26-E2E-LOC-003",
                title="거점 모달 재시도 테스트",
                issuer="조달청",
            ),
            hard_filters=[
                ProcurementHardFilterResult(
                    code="capability_gap",
                    label="핵심 수행역량",
                    status="fail",
                    blocking=True,
                    reason="필수 운영 실적 부족",
                )
            ],
            recommendation=ProcurementRecommendation(
                value="NO_GO",
                summary="override 사유 저장 후 retry가 필요한 상태",
            ),
        )
    )
    page.evaluate(
        """async ({ projectId }) => {
          const token = localStorage.getItem('dd_access_token');
          const headers = {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          };
          const added = await fetch(`/projects/${projectId}/documents`, {
            method: 'POST',
            headers,
            body: JSON.stringify({
              request_id: 'req-e2e-procurement-rfp-analysis',
              bundle_id: 'rfp_analysis_kr',
              title: '선행 RFP 분석',
              docs: [{ doc_type: 'rfp_analysis', markdown: '# 선행 분석' }],
            }),
          });
          if (!added.ok) throw new Error(`project document add failed: ${added.status}`);
        }""",
        {"projectId": project_id},
    )

    AuditStore("system").append(
        AuditLog(
            log_id=str(uuid.uuid4()),
            tenant_id="system",
            timestamp=datetime.now(timezone.utc).isoformat(timespec="microseconds"),
            user_id="e2e-admin",
            username="e2e_admin",
            user_role="admin",
            ip_address="127.0.0.1",
            user_agent="playwright",
            action="procurement.downstream_blocked",
            resource_type="procurement",
            resource_id=project_id,
            resource_name="",
            result="failure",
            detail={
                "project_id": project_id,
                "bundle_type": "proposal_kr",
                "error_code": "procurement_override_reason_required",
                "recommendation": "NO_GO",
            },
            session_id="sess-e2e-procurement-retry",
        )
    )

    page.evaluate("switchPage('locations-page')")
    page.wait_for_selector(".location-card", timeout=10000)
    page.locator('[data-location-procurement="system"]').click()

    page.wait_for_selector("#location-procurement-modal", state="visible", timeout=10000)
    page.evaluate(
        """() => {
          window.__copiedProjectProcurementLink = null;
          Object.defineProperty(navigator, 'clipboard', {
            configurable: true,
            value: {
              writeText: async (text) => { window.__copiedProjectProcurementLink = text; },
            },
          });
        }"""
    )
    page.locator(
        f'#location-procurement-modal .location-procurement-event [data-location-procurement-copy-project-link="{project_id}"]'
    ).first.click()
    copied_link = page.evaluate("window.__copiedProjectProcurementLink")
    assert copied_link is not None
    page.locator('#location-procurement-modal .btn-secondary').last.click()
    page.wait_for_selector("#location-procurement-modal", state="hidden", timeout=5000)
    page.evaluate(
        """(copiedLink) => {
          const url = new URL(copiedLink, window.location.origin);
          history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`);
          _currentProjectDetail = null;
          _projectProcurementRemediationContext = null;
          _projectProcurementSummaryReturnContext = null;
          const detailEl = document.getElementById('project-detail');
          const listEl = document.getElementById('project-list');
          if (detailEl) detailEl.style.display = 'none';
          if (listEl) listEl.style.display = 'block';
          switchPage('locations-page');
        }""",
        copied_link,
    )
    assert page.evaluate("restoreProjectProcurementDetailFromUrl()") is True
    page.wait_for_selector("#project-detail", state="visible", timeout=10000)
    page.evaluate("focusProcurementOverrideReason()")
    page.wait_for_selector("#project-procurement-override-reason", state="visible", timeout=10000)
    assert page.locator(".doc-item").count() == 2

    page.fill(
        "#project-procurement-override-reason",
        "전략 고객 유지 목적상 proposal 초안까지는 예외 검토를 진행합니다.",
    )
    page.click("#project-procurement-override-submit")

    _wait_until_text_contains(
        page,
        "#project-procurement-status",
        "같은 화면에서 다시 시도할 수 있습니다.",
        timeout_ms=10000,
    )
    page.evaluate("switchPage('locations-page')")
    page.wait_for_selector(".location-card", timeout=10000)
    page.locator('[data-location-procurement="system"]').click()
    page.wait_for_selector("#location-procurement-modal", state="visible", timeout=10000)
    modal = page.locator("#location-procurement-modal-body")
    _wait_until_text_contains(
        page,
        "#location-procurement-modal-body",
        "Retry 대기",
        timeout_ms=10000,
    )
    page.locator('[data-location-procurement-scope="unresolved_only"]').click()
    page.wait_for_selector('[data-location-procurement-scope="unresolved_only"].active', timeout=5000)
    assert "Retry 대기" in modal.inner_text()
    assert "운영 기준" in modal.inner_text()
    assert "가장 오래 미해소 follow-up" in modal.inner_text()
    assert "미해소 follow-up" in modal.inner_text()
    assert "현재 미해소 queue 기준 candidate는 1개" in modal.inner_text()
    assert "최근 blocked downstream 이후 override 사유는 저장되었고, 아직 retry 완료는 확인되지 않았습니다." in modal.inner_text()
    assert "가-해소 후보" not in modal.inner_text()
    oldest_button = page.get_by_role("button", name="가장 오래 미해소 열기")
    assert oldest_button.is_visible()
    oldest_button.click()
    page.wait_for_selector("#project-procurement-remediation-strip", timeout=10000)
    remediation = page.locator("#project-procurement-remediation-strip")
    assert "retry 완료가 확인되지 않았습니다." in remediation.inner_text()
    page.evaluate("switchPage('locations-page')")
    page.wait_for_selector(".location-card", timeout=10000)
    page.locator('[data-location-procurement="system"]').click()
    page.wait_for_selector("#location-procurement-modal", state="visible", timeout=10000)
    modal = page.locator("#location-procurement-modal-body")
    _wait_until_text_contains(
        page,
        "#location-procurement-modal-body",
        "Retry 대기",
        timeout_ms=10000,
    )
    assert page.locator('[data-location-procurement-scope="unresolved_only"].active').count() == 1
    candidate_button = page.locator(
        f'#location-procurement-modal .location-procurement-candidate [data-location-procurement-open="{project_id}"]'
    ).first
    assert "retry" in candidate_button.inner_text().lower()
    candidate_button.click()

    page.wait_for_selector("#project-procurement-remediation-strip", timeout=10000)
    remediation = page.locator("#project-procurement-remediation-strip")
    remediation_text = remediation.inner_text()
    assert (
        "retry 완료가 확인되지 않았습니다." in remediation_text
        or "현재 override 사유가 저장되어 있습니다." in remediation_text
    )
    retry_button = remediation.locator("button").first
    retry_label = retry_button.inner_text()
    assert "제안서" in retry_label
    assert "다시 시도" in retry_label
    assert page.locator('[data-project-procurement-return="system"]').is_visible()

    retry_button.click()

    page.locator(".doc-item").nth(2).wait_for(timeout=15000)
    page.wait_for_selector("#project-procurement-remediation-strip", state="detached", timeout=10000)
    assert page.locator(".doc-item").count() == 3

    page.locator('[data-project-procurement-return="system"]').click()
    page.wait_for_selector("#location-procurement-modal", state="visible", timeout=10000)
    modal = page.locator("#location-procurement-modal-body")
    _wait_until_text_contains(
        page,
        "#location-procurement-modal-body",
        "Override 후 downstream 완료",
        timeout_ms=10000,
    )
    focus_card = page.locator(f'[data-location-procurement-focus="{project_id}"]')
    assert focus_card.is_visible()
    assert "방금 확인한 프로젝트" in focus_card.inner_text()
    assert "거점 모달 재시도 테스트" in focus_card.inner_text()
    assert page.locator('[data-location-procurement-scope="unresolved_only"].active').count() == 1
    assert "현재 미해소 queue 기준 candidate는 0개" in modal.inner_text()
    assert "queue 밖 candidate는" in modal.inner_text()
    assert "방금 확인한 프로젝트 이벤트는 context 유지를 위해 함께 표시합니다." in modal.inner_text()
    assert "Remediation handoff queue" in modal.inner_text()
    assert "열람 후 해소" in modal.inner_text()
    resolved_only_button = page.get_by_role("button", name="해소됨 candidate 보기")
    assert resolved_only_button.is_visible()
    assert "현재 미해소 override candidate가 없습니다." in modal.inner_text()
    assert "해소됨" in modal.inner_text()
    assert "Override 후 downstream 완료" in modal.inner_text()
    assert "override 이후 downstream까지 다시 이어진 건은 5건" in modal.inner_text()
    page.locator('[data-location-procurement-preset="handoff_review"]').click()
    page.wait_for_selector('[data-location-procurement-preset="handoff_review"].active', timeout=5000)
    page.wait_for_selector(
        '[data-location-procurement-activity-filter="procurement.remediation_link_copied"].active',
        timeout=5000,
    )
    page.wait_for_selector(
        '[data-location-procurement-activity-filter="procurement.remediation_link_opened"].active',
        timeout=5000,
    )
    handoff_focus_card = page.locator(f'[data-location-procurement-focus="{project_id}"]')
    assert "열람 후 해소" in handoff_focus_card.inner_text()

    page.locator('[data-location-procurement-scope="resolved_only"]').click()
    page.wait_for_selector('[data-location-procurement-scope="resolved_only"].active', timeout=5000)
    highlighted_candidate = page.locator(
        f'#location-procurement-modal .location-procurement-candidate.highlighted[data-location-procurement-project="{project_id}"]'
    ).first
    assert highlighted_candidate.is_visible()
    assert "방금 확인한 프로젝트" in highlighted_candidate.inner_text()
    assert "해소됨" in highlighted_candidate.inner_text()


def test_location_procurement_summary_can_toggle_stale_first_override_candidates(page):
    from app.schemas import (
        NormalizedProcurementOpportunity,
        ProcurementDecisionUpsert,
        ProcurementHardFilterResult,
        ProcurementRecommendation,
    )
    from app.storage.audit_store import AuditLog, AuditStore
    from app.storage.procurement_store import ProcurementDecisionStore

    procurement_store = ProcurementDecisionStore(base_dir=os.environ["DATA_DIR"])
    audit_store = AuditStore("system")

    def seed_no_go_candidate(
        name: str,
        source_id: str,
        override_reason: str,
        *,
        resolved: bool = False,
    ) -> str:
        candidate_project_id = _create_project_with_document(page, name=name)
        procurement_store.upsert(
            ProcurementDecisionUpsert(
                project_id=candidate_project_id,
                tenant_id="system",
                opportunity=NormalizedProcurementOpportunity(
                    source_kind="g2b",
                    source_id=source_id,
                    title=name,
                    issuer="조달청",
                ),
                hard_filters=[
                    ProcurementHardFilterResult(
                        code="capability_gap",
                        label="핵심 수행역량",
                        status="fail",
                        blocking=True,
                        reason="필수 운영 실적 부족",
                    )
                ],
                recommendation=ProcurementRecommendation(
                    value="NO_GO",
                    summary="override 사유 저장 후 retry 대기 상태",
                ),
            )
        )
        page.evaluate(
            """async ({ projectId }) => {
              const token = localStorage.getItem('dd_access_token');
              const headers = {
                'Content-Type': 'application/json',
                ...(token ? { Authorization: `Bearer ${token}` } : {}),
              };
              const added = await fetch(`/projects/${projectId}/documents`, {
                method: 'POST',
                headers,
                body: JSON.stringify({
                  request_id: `req-${projectId}-rfp-analysis`,
                  bundle_id: 'rfp_analysis_kr',
                  title: '선행 RFP 분석',
                  docs: [{ doc_type: 'rfp_analysis', markdown: '# 선행 분석' }],
                }),
              });
              if (!added.ok) throw new Error(`project document add failed: ${added.status}`);
            }""",
            {"projectId": candidate_project_id},
        )
        audit_store.append(
            AuditLog(
                log_id=str(uuid.uuid4()),
                tenant_id="system",
                timestamp=datetime.now(timezone.utc).isoformat(timespec="microseconds"),
                user_id="ops-admin",
                username="ops_admin",
                user_role="admin",
                ip_address="127.0.0.1",
                user_agent="playwright",
                action="procurement.downstream_blocked",
                resource_type="procurement",
                resource_id=candidate_project_id,
                resource_name="",
                result="failure",
                detail={
                    "project_id": candidate_project_id,
                    "bundle_type": "proposal_kr",
                    "error_code": "procurement_override_reason_required",
                    "recommendation": "NO_GO",
                },
                session_id=f"sess-{candidate_project_id}-blocked",
            )
        )
        page.evaluate(
            """async ({ projectId, reason }) => {
              const token = localStorage.getItem('dd_access_token');
              const headers = {
                'Content-Type': 'application/json',
                ...(token ? { Authorization: `Bearer ${token}` } : {}),
              };
              const saved = await fetch(`/projects/${projectId}/procurement/override-reason`, {
                method: 'POST',
                headers,
                body: JSON.stringify({ reason }),
              });
              if (!saved.ok) throw new Error(`override save failed: ${saved.status}`);
            }""",
            {"projectId": candidate_project_id, "reason": override_reason},
        )
        if resolved:
            audit_store.append(
                AuditLog(
                    log_id=str(uuid.uuid4()),
                    tenant_id="system",
                    timestamp=datetime.now(timezone.utc).isoformat(timespec="microseconds"),
                    user_id="ops-admin",
                    username="ops_admin",
                    user_role="admin",
                    ip_address="127.0.0.1",
                    user_agent="playwright",
                    action="procurement.downstream_resolved",
                    resource_type="procurement",
                    resource_id=candidate_project_id,
                    resource_name="",
                    result="success",
                    detail={
                        "project_id": candidate_project_id,
                        "bundle_type": "proposal_kr",
                        "recommendation": "NO_GO",
                    },
                    session_id=f"sess-{candidate_project_id}-resolved",
                )
            )
        return candidate_project_id

    def seed_monitor_candidate(name: str, source_id: str) -> str:
        candidate_project_id = _create_project_with_document(page, name=name)
        procurement_store.upsert(
            ProcurementDecisionUpsert(
                project_id=candidate_project_id,
                tenant_id="system",
                opportunity=NormalizedProcurementOpportunity(
                    source_kind="g2b",
                    source_id=source_id,
                    title=name,
                    issuer="조달청",
                ),
                hard_filters=[
                    ProcurementHardFilterResult(
                        code="reference_gap",
                        label="유사 레퍼런스",
                        status="fail",
                        blocking=True,
                        reason="추가 운영 검토가 필요한 상태",
                    )
                ],
                recommendation=ProcurementRecommendation(
                    value="NO_GO",
                    summary="운영 모니터링 상태",
                ),
            )
        )
        page.evaluate(
            """async ({ projectId }) => {
              const token = localStorage.getItem('dd_access_token');
              const headers = {
                'Content-Type': 'application/json',
                ...(token ? { Authorization: `Bearer ${token}` } : {}),
              };
              const added = await fetch(`/projects/${projectId}/documents`, {
                method: 'POST',
                headers,
                body: JSON.stringify({
                  request_id: `req-${projectId}-proposal`,
                  bundle_id: 'proposal_kr',
                  title: '후속 제안서 초안',
                  docs: [{ doc_type: 'proposal', markdown: '# monitor proposal' }],
                }),
              });
              if (!added.ok) throw new Error(`project document add failed: ${added.status}`);
            }""",
            {"projectId": candidate_project_id},
        )
        audit_store.append(
            AuditLog(
                log_id=str(uuid.uuid4()),
                tenant_id="system",
                timestamp=datetime.now(timezone.utc).isoformat(timespec="microseconds"),
                user_id="ops-admin",
                username="ops_admin",
                user_role="admin",
                ip_address="127.0.0.1",
                user_agent="playwright",
                action="procurement.evaluate",
                resource_type="procurement",
                resource_id=candidate_project_id,
                resource_name="",
                result="success",
                detail={"project_id": candidate_project_id},
                session_id=f"sess-{candidate_project_id}-monitor",
            )
        )
        return candidate_project_id

    older_project_id = seed_no_go_candidate(
        "나-오래된 retry 후보",
        "R26-E2E-LOC-201",
        "먼저 저장된 override 사유입니다.",
    )
    page.wait_for_timeout(50)
    newer_project_id = seed_no_go_candidate(
        "가-최근 retry 후보",
        "R26-E2E-LOC-202",
        "나중에 저장된 override 사유입니다.",
    )
    page.wait_for_timeout(50)
    resolved_project_id = seed_no_go_candidate(
        "다-resolved 후보",
        "R26-E2E-LOC-203",
        "이미 retry 완료된 override 사유입니다.",
        resolved=True,
    )
    page.wait_for_timeout(50)
    monitor_project_id = seed_monitor_candidate(
        "라-monitor 후보",
        "R26-E2E-LOC-204",
    )

    page.evaluate(
        """() => {
          localStorage.removeItem('dd_location_procurement_summary_prefs');
          if (typeof clearLocationProcurementSummaryUrlState === 'function') {
            clearLocationProcurementSummaryUrlState();
          }
          if (typeof clearProjectProcurementDetailUrlState === 'function') {
            clearProjectProcurementDetailUrlState();
          }
        }"""
    )

    page.evaluate("switchPage('locations-page')")
    page.wait_for_selector(".location-card", timeout=10000)
    page.locator('[data-location-procurement="system"]').click()

    page.wait_for_selector("#location-procurement-modal", state="visible", timeout=10000)
    modal = page.locator("#location-procurement-modal-body")
    _wait_until_text_contains(
        page,
        "#location-procurement-modal-body",
        "Retry 대기",
        timeout_ms=10000,
    )
    candidate_order = page.locator("#location-procurement-modal .location-procurement-candidate").evaluate_all(
        "(nodes) => nodes.map((node) => node.getAttribute('data-location-procurement-project'))"
    )
    assert candidate_order.index(newer_project_id) < candidate_order.index(older_project_id)
    assert resolved_project_id in candidate_order
    assert page.locator('[data-location-procurement-order="latest_followup"].active').count() == 1

    page.locator('[data-location-procurement-order="stale_unresolved"]').click()
    page.wait_for_selector('[data-location-procurement-order="stale_unresolved"].active', timeout=5000)
    candidate_order = page.locator("#location-procurement-modal .location-procurement-candidate").evaluate_all(
        "(nodes) => nodes.map((node) => node.getAttribute('data-location-procurement-project'))"
    )
    assert candidate_order.index(older_project_id) < candidate_order.index(newer_project_id)
    assert candidate_order.index(newer_project_id) < candidate_order.index(resolved_project_id)

    page.locator('[data-location-procurement-scope="unresolved_only"]').click()
    page.wait_for_selector('[data-location-procurement-scope="unresolved_only"].active', timeout=5000)
    candidate_order = page.locator("#location-procurement-modal .location-procurement-candidate").evaluate_all(
        "(nodes) => nodes.map((node) => node.getAttribute('data-location-procurement-project'))"
    )
    visible_seeded_unresolved = [
        project_id
        for project_id in candidate_order
        if project_id in {older_project_id, newer_project_id, resolved_project_id, monitor_project_id}
    ]
    assert visible_seeded_unresolved == [older_project_id, newer_project_id]
    assert "현재 미해소 queue 기준 candidate는" in modal.inner_text()
    assert "queue 밖 candidate는" in modal.inner_text()
    assert page.get_by_role("button", name="전체 candidate 보기").is_visible()
    assert page.get_by_role("button", name="review backlog 보기").is_visible()
    ready_to_retry_filter = page.locator('[data-location-procurement-status-filter="ready_to_retry"]')
    assert ready_to_retry_filter.count() == 1
    assert "Retry 대기" in ready_to_retry_filter.inner_text()
    assert page.locator('[data-location-procurement-scope="monitor_only"]').count() == 1
    assert page.locator('[data-location-procurement-preset="retry_queue"]').count() == 1
    assert page.locator('[data-location-procurement-preset="resolved_review"]').count() == 1
    page.locator('[data-location-procurement-preset="resolved_review"]').click()
    page.wait_for_selector('[data-location-procurement-preset="resolved_review"].active', timeout=5000)
    page.wait_for_selector('[data-location-procurement-scope="resolved_only"].active', timeout=5000)
    page.wait_for_selector(
        '[data-location-procurement-activity-filter="procurement.downstream_resolved"].active',
        timeout=5000,
    )
    assert "세부 활동: Override 후 downstream 완료" in modal.inner_text()
    page.locator('[data-location-procurement-preset="retry_queue"]').click()
    page.wait_for_selector('[data-location-procurement-preset="retry_queue"].active', timeout=5000)
    page.wait_for_selector('[data-location-procurement-scope="unresolved_only"].active', timeout=5000)
    page.wait_for_selector('[data-location-procurement-status-filter="ready_to_retry"].active', timeout=5000)
    assert "세부 상태: Retry 대기" in modal.inner_text()
    assert modal.inner_text().count("Retry 대기") >= 2
    assert page.locator(
        f'#location-procurement-modal .location-procurement-candidate[data-location-procurement-project="{resolved_project_id}"]'
    ).count() == 0

    page.get_by_role("button", name="review backlog 보기").click()
    page.wait_for_selector('[data-location-procurement-scope="review_only"].active', timeout=5000)
    assert "세부 상태: 전체 상태" in modal.inner_text()
    candidate_order = page.locator("#location-procurement-modal .location-procurement-candidate").evaluate_all(
        "(nodes) => nodes.map((node) => node.getAttribute('data-location-procurement-project'))"
    )
    assert older_project_id not in candidate_order
    assert newer_project_id not in candidate_order
    assert resolved_project_id in candidate_order
    assert "현재 review backlog 기준 candidate는" in modal.inner_text()
    assert "현재 범위 활동:" in modal.inner_text()
    assert "현재 범위 queue KPI" in modal.inner_text()
    assert "현재 범위 candidate" in modal.inner_text()
    assert page.get_by_role("button", name="미해소 candidate 보기").is_visible()
    assert page.locator('[data-location-procurement-status-filter="resolved"]').count() == 1
    assert page.locator('[data-location-procurement-status-filter="monitor"]').count() == 1
    assert "해소됨 (" in modal.inner_text()
    assert "모니터링 (" in modal.inner_text()
    assert page.locator('[data-location-procurement-activity-filter="procurement.downstream_resolved"]').count() == 1
    page.locator('[data-location-procurement-activity-filter="procurement.downstream_resolved"]').click()
    page.wait_for_selector(
        '[data-location-procurement-activity-filter="procurement.downstream_resolved"].active',
        timeout=5000,
    )
    assert "세부 활동: Override 후 downstream 완료" in modal.inner_text()
    event_titles = page.locator("#location-procurement-modal .location-procurement-event-title").evaluate_all(
        "(nodes) => nodes.map((node) => node.textContent.trim())"
    )
    assert event_titles
    assert set(event_titles) == {"Override 후 downstream 완료"}
    assert page.locator('[data-location-procurement-activity-clear="true"]').count() == 1
    page.locator('[data-location-procurement-activity-clear="true"]').click()
    page.wait_for_selector(
        '[data-location-procurement-activity-filter="procurement.downstream_resolved"]:not(.active)',
        timeout=5000,
    )
    page.locator('[data-location-procurement-status-filter="monitor"]').click()
    page.wait_for_selector('[data-location-procurement-status-filter="monitor"].active', timeout=5000)
    candidate_order = page.locator("#location-procurement-modal .location-procurement-candidate").evaluate_all(
        "(nodes) => nodes.map((node) => node.getAttribute('data-location-procurement-project'))"
    )
    assert older_project_id not in candidate_order
    assert newer_project_id not in candidate_order
    assert resolved_project_id not in candidate_order
    assert monitor_project_id in candidate_order
    assert "세부 상태: 모니터링" in modal.inner_text()
    assert "현재 범위 활동:" in modal.inner_text()
    assert "현재 범위 queue KPI" in modal.inner_text()
    assert "현재 범위 blocked" in modal.inner_text()
    assert page.locator('[data-location-procurement-status-clear="true"]').count() == 1
    page.locator('[data-location-procurement-status-clear="true"]').click()
    page.wait_for_selector('[data-location-procurement-status-filter="monitor"]:not(.active)', timeout=5000)

    page.locator('[data-location-procurement-scope="monitor_only"]').click()
    page.wait_for_selector('[data-location-procurement-scope="monitor_only"].active', timeout=5000)
    candidate_order = page.locator("#location-procurement-modal .location-procurement-candidate").evaluate_all(
        "(nodes) => nodes.map((node) => node.getAttribute('data-location-procurement-project'))"
    )
    visible_seeded_monitor = [
        project_id
        for project_id in candidate_order
        if project_id in {older_project_id, newer_project_id, resolved_project_id, monitor_project_id}
    ]
    assert visible_seeded_monitor == [monitor_project_id]
    assert "현재 모니터링 review 기준 candidate가 없습니다." not in modal.inner_text()
    assert page.get_by_role("button", name="미해소 candidate 보기").is_visible()

    page.locator('[data-location-procurement-scope="unresolved_only"]').click()
    page.wait_for_selector('[data-location-procurement-scope="unresolved_only"].active', timeout=5000)
    candidate_order = page.locator("#location-procurement-modal .location-procurement-candidate").evaluate_all(
        "(nodes) => nodes.map((node) => node.getAttribute('data-location-procurement-project'))"
    )
    visible_seeded_unresolved = [
        project_id
        for project_id in candidate_order
        if project_id in {older_project_id, newer_project_id, resolved_project_id, monitor_project_id}
    ]
    assert visible_seeded_unresolved == [older_project_id, newer_project_id]

    page.locator(
        f'#location-procurement-modal .location-procurement-candidate [data-location-procurement-open="{older_project_id}"]'
    ).first.click()
    page.wait_for_selector("#project-procurement-remediation-strip", timeout=10000)
    remediation = page.locator("#project-procurement-remediation-strip")
    remediation_text = remediation.inner_text()
    assert (
        "retry 완료가 확인되지 않았습니다." in remediation_text
        or "현재 override 사유가 저장되어 있습니다." in remediation_text
    )
    assert "나-오래된 retry 후보" in page.locator("#project-detail").inner_text()
    assert page.locator('[data-project-procurement-return="system"]').is_visible()

    page.locator('[data-project-procurement-return="system"]').click()
    page.wait_for_selector("#location-procurement-modal", state="visible", timeout=10000)
    _wait_until_text_contains(
        page,
        "#location-procurement-modal-body",
        "Retry 대기",
        timeout_ms=10000,
    )
    assert page.locator('[data-location-procurement-order="stale_unresolved"].active').count() == 1
    assert page.locator('[data-location-procurement-scope="unresolved_only"].active').count() == 1
    candidate_order = page.locator("#location-procurement-modal .location-procurement-candidate").evaluate_all(
        "(nodes) => nodes.map((node) => node.getAttribute('data-location-procurement-project'))"
    )
    visible_seeded_unresolved = [
        project_id
        for project_id in candidate_order
        if project_id in {older_project_id, newer_project_id, resolved_project_id, monitor_project_id}
    ]
    assert visible_seeded_unresolved == [older_project_id, newer_project_id]
    assert page.locator(
        f'#location-procurement-modal .location-procurement-candidate [data-location-procurement-open="{newer_project_id}"]'
    ).count() >= 1
    assert page.locator(
        f'#location-procurement-modal .location-procurement-candidate[data-location-procurement-project="{resolved_project_id}"]'
    ).count() == 0
    page.locator('[data-location-procurement-preset="retry_queue"]').click()
    page.wait_for_selector('[data-location-procurement-preset="retry_queue"].active', timeout=5000)
    page.wait_for_selector('[data-location-procurement-status-filter="ready_to_retry"].active', timeout=5000)
    stored_preferences = page.evaluate(
        """() => {
          const raw = JSON.parse(localStorage.getItem('dd_location_procurement_summary_prefs') || '{}');
          return raw.system || null;
        }"""
    )
    url_state = page.evaluate(
        """() => Object.fromEntries(new URLSearchParams(location.search).entries())"""
    )
    assert stored_preferences == {
        "candidateView": "stale_unresolved",
        "candidateScope": "unresolved_only",
        "candidateStatusFilters": ["ready_to_retry"],
        "activityActionFilters": [],
    }
    assert url_state["location_procurement_tenant"] == "system"
    assert url_state["location_procurement_candidate_view"] == "stale_unresolved"
    assert url_state["location_procurement_candidate_scope"] == "unresolved_only"
    assert url_state["location_procurement_candidate_statuses"] == "ready_to_retry"
    assert "location_procurement_activity_actions" not in url_state
    page.evaluate(
        """() => {
          window.__copiedLocationProcurementLink = null;
          Object.defineProperty(navigator, 'clipboard', {
            configurable: true,
            value: {
              writeText: async (text) => { window.__copiedLocationProcurementLink = text; },
            },
          });
        }"""
    )
    page.locator('[data-location-procurement-copy-link="true"]').first.click()
    copied_link = page.evaluate("window.__copiedLocationProcurementLink")
    assert copied_link is not None
    assert "location_procurement_tenant=system" in copied_link
    assert "location_procurement_candidate_view=stale_unresolved" in copied_link
    assert "location_procurement_candidate_scope=unresolved_only" in copied_link
    assert "location_procurement_candidate_statuses=ready_to_retry" in copied_link
    saved_search = page.evaluate("location.search")

    page.locator('#location-procurement-modal .btn-secondary').last.click()
    page.wait_for_selector("#location-procurement-modal", state="hidden", timeout=5000)
    cleared_search = page.evaluate("location.search")
    assert "location_procurement_tenant" not in cleared_search
    page.evaluate(
        """() => {
          _locationProcurementSummaryModalState = null;
          _locationProcurementCandidateOrder = 'latest_followup';
          _locationProcurementCandidateScope = 'all';
          _locationProcurementCandidateStatusFilters = [];
          _locationProcurementActivityActionFilters = [];
        }"""
    )
    page.evaluate("(savedSearch) => history.replaceState({}, '', location.pathname + savedSearch)", saved_search)
    page.evaluate("restoreLocationProcurementSummaryFromUrl()")
    page.wait_for_selector("#location-procurement-modal", state="visible", timeout=10000)
    _wait_until_text_contains(
        page,
        "#location-procurement-modal-body",
        "Retry 대기",
        timeout_ms=10000,
    )
    assert page.locator('[data-location-procurement-order="stale_unresolved"].active').count() == 1
    assert page.locator('[data-location-procurement-scope="unresolved_only"].active').count() == 1
    assert page.locator('[data-location-procurement-status-filter="ready_to_retry"].active').count() == 1
    assert page.locator('[data-location-procurement-preset="retry_queue"].active').count() == 1
    candidate_order = page.locator("#location-procurement-modal .location-procurement-candidate").evaluate_all(
        "(nodes) => nodes.map((node) => node.getAttribute('data-location-procurement-project'))"
    )
    visible_seeded_unresolved = [
        project_id
        for project_id in candidate_order
        if project_id in {older_project_id, newer_project_id, resolved_project_id, monitor_project_id}
    ]
    assert visible_seeded_unresolved == [older_project_id, newer_project_id]


def test_location_procurement_summary_stale_share_review_preset_filters_share_activity(page):
    page.evaluate("switchPage('locations-page')")
    page.evaluate(
        """() => {
          const data = {
            tenant: { tenant_id: 'system', display_name: 'System' },
            procurement: {
              decision: { projects_with_procurement_state: 1, avg_soft_fit_score: 0.71 },
              handoff: {
                remediation_queue_count: 0,
                remediation_queue_status_counts: {},
                remediation_queue: [],
                approval_status_counts: {},
              },
              sharing: {
                stale_external_share_queue_count: 1,
                active_stale_external_share_queue_count: 1,
                active_accessed_stale_external_share_queue_count: 1,
                active_unaccessed_stale_external_share_queue_count: 0,
                inactive_stale_external_share_queue_count: 0,
                missing_stale_external_share_record_count: 0,
                stale_external_share_status_counts: { stale_procurement: 1 },
                stale_external_share_queue: [
                  {
                    project_id: 'proj-stale-share',
                    project_name: '외부 공유 프로젝트',
                    project_document_id: 'doc-stale-share-1',
                    project_document_title: 'Stale council 기반 의사결정 문서',
                    bundle_type: 'bid_decision_kr',
                    decision_council_document_status: 'stale_procurement',
                    decision_council_document_status_tone: 'danger',
                    decision_council_document_status_copy: '현재 procurement 대비 이전 council 기준',
                    decision_council_document_status_summary: '현재 procurement recommendation 또는 checklist가 바뀌어 외부 공유 전 재확인이 필요합니다.',
                    latest_shared_at: '2026-03-31T00:40:00+00:00',
                    latest_shared_by_username: 'admin',
                    stale_share_count: 2,
                    share_id: 'share-stale-001',
                    share_url: '/shared/share-stale-001',
                    share_record_found: true,
                    share_is_active: true,
                    share_access_count: 2,
                    share_last_accessed_at: '2026-04-02T09:15:00+00:00',
                    share_expires_at: '2026-04-07T00:00:00+00:00',
                  },
                ],
              },
              outcomes: {
                override_candidate_count: 0,
                override_candidates_needing_followup: 0,
                override_candidate_status_counts: {},
                scope_override_candidate_status_counts: {},
                override_candidate_view: 'latest_followup',
                override_candidate_scope: 'all',
                override_candidate_status_filters: [],
                override_candidates: [],
                visible_override_candidate_count: 0,
                visible_recent_event_count: 1,
                projects_with_downstream_handoff: 0,
              },
              activity: {
                action_counts: { 'share.create': 2 },
                scope_action_counts: { 'share.create': 2 },
                visible_action_counts: { 'share.create': 2 },
                activity_action_filters: [],
                recent_events: [
                  {
                    timestamp: '2026-03-31T00:40:00+00:00',
                    action: 'share.create',
                    result: 'success',
                    resource_type: 'share',
                    linked_project_id: 'proj-stale-share',
                    linked_project_name: '외부 공유 프로젝트',
                    linked_approval_id: null,
                    error_code: null,
                    bundle_type: 'bid_decision_kr',
                    recommendation: null,
                    procurement_operation: null,
                    procurement_context_kind: null,
                    share_decision_council_document_status: 'stale_procurement',
                    share_decision_council_document_status_copy: '현재 procurement 대비 이전 council 기준',
                    share_decision_council_document_status_summary: '현재 procurement recommendation 또는 checklist가 바뀌어 외부 공유 전 재확인이 필요합니다.',
                    share_project_document_id: 'doc-stale-share-1',
                  },
                ],
              },
            },
          };
          const modal = document.getElementById('location-procurement-modal');
          const body = document.getElementById('location-procurement-modal-body');
          _locationProcurementSummaryModalState = {
            data,
            focusProjectId: '',
            tenantId: '',
            candidateView: 'latest_followup',
            candidateScope: 'all',
            candidateStatusFilters: [],
            activityActionFilters: [],
          };
          _locationProcurementCandidateOrder = 'latest_followup';
          _locationProcurementCandidateScope = 'all';
          _locationProcurementCandidateStatusFilters = [];
          _locationProcurementActivityActionFilters = [];
          window.__openedSharedUrl = null;
          window.__copiedSharedUrl = null;
          window.open = (url) => {
            window.__openedSharedUrl = url;
            return null;
          };
          Object.defineProperty(window.navigator, 'clipboard', {
            configurable: true,
            value: {
              writeText: (text) => {
                window.__copiedSharedUrl = text;
                return Promise.resolve();
              },
            },
          });
          modal.style.display = 'flex';
          body.innerHTML = renderLocationProcurementSummary(data, '');
        }"""
    )

    page.wait_for_timeout(200)
    page.wait_for_selector('[data-location-procurement-preset="stale_share_review"]', state="visible", timeout=5000)
    pre_modal_text = page.locator("#location-procurement-modal-body").inner_text()
    assert "현재 stale public 노출이 남아 있는 공유 링크는 1개입니다." in pre_modal_text
    assert "최근 public 열람이 확인된 stale 링크는 1개입니다." in pre_modal_text
    page.locator('button:has-text("외부 공유 review 열기")').click()
    assert page.locator('[data-location-procurement-preset="stale_share_review"]').count() == 1
    assert page.locator('[data-location-procurement-preset="stale_share_review"]').inner_text() == '외부 공유 review (1)'
    page.wait_for_selector('[data-location-procurement-preset="stale_share_review"].active', timeout=5000)
    page.wait_for_selector('[data-location-procurement-activity-filter="share.create"].active', timeout=5000)
    modal_text = page.locator("#location-procurement-modal-body").inner_text()
    assert "외부 공유 재확인 queue" in modal_text
    assert "활성 링크 1" in modal_text
    assert "최근 public 열람 있음 1" in modal_text
    assert "아직 열람 없음 0" in modal_text
    assert "비활성 링크 0" in modal_text
    assert "누적 stale share event 2" in modal_text
    assert "Stale council 기반 의사결정 문서" in modal_text
    assert "활성 공유 링크" in modal_text
    assert "최근 public 열람 있음" in modal_text
    assert "최근 stale 공유: admin · 2회" in modal_text
    assert "공유 링크 상태: 활성 공유 링크 · 조회 2회 · 최근 열람 2026-04-02 · 2026-04-07 만료" in modal_text
    assert "세부 활동: Stale council 문서 공유" in modal_text
    assert "공유 문서 기준: 현재 procurement 대비 이전 council 기준" in modal_text
    assert "외부 공유 전 재확인이 필요합니다." in modal_text
    page.locator('#location-procurement-modal-body button:has-text("공유 링크 복사")').click()
    copied_url = page.evaluate("() => window.__copiedSharedUrl")
    assert copied_url is not None
    assert copied_url.endswith("/shared/share-stale-001")
    page.locator('#location-procurement-modal-body button:has-text("공유 링크 열기")').click()
    assert page.evaluate("() => window.__openedSharedUrl") == "/shared/share-stale-001"


def test_g2b_search_result_click_selects_announcement(page):
    page.evaluate(
        """() => {
          const g2bContent = document.getElementById('g2b-content');
          const searchTab = document.getElementById('g2b-search-tab');
          if (g2bContent) g2bContent.style.display = 'block';
          if (searchTab) searchTab.style.display = 'block';
          _g2bLastResults = [{
            bid_number: '20250317001-00',
            title: 'AI 기반 공공서비스 구축',
            issuer: '조달청',
            budget: '3억원',
            deadline: '2026-04-01',
            detail_url: 'https://www.g2b.go.kr/pt/menu/selectSubFrame.do?bidNtceNo=20250317001-00',
          }];
          _renderG2BSearchResults(_g2bLastResults);
        }"""
    )

    page.wait_for_selector("#g2b-search-results .g2b-result-item", state="visible", timeout=10000)
    page.locator("#g2b-search-results .g2b-result-item").first.click()

    assert page.input_value("#f-title") == "AI 기반 공공서비스 구축"
    assert "20250317001-00" in page.input_value("#f-context")


def test_g2b_oneclick_proposal_button_handles_hyphenated_bid_number(page):
    page.evaluate(
        """() => {
          const g2bContent = document.getElementById('g2b-content');
          const searchTab = document.getElementById('g2b-search-tab');
          if (g2bContent) g2bContent.style.display = 'block';
          if (searchTab) searchTab.style.display = 'block';
          _g2bLastResults = [{
            bid_number: '20250317001-00',
            title: 'AI 기반 공공서비스 구축',
            issuer: '조달청',
            budget: '3억원',
            deadline: '2026-04-01',
            detail_url: 'https://www.g2b.go.kr/pt/menu/selectSubFrame.do?bidNtceNo=20250317001-00',
          }];
          _renderG2BSearchResults(_g2bLastResults);
        }"""
    )

    page.wait_for_selector("#g2b-search-results .g2b-oneclick-btn", state="visible", timeout=10000)
    page.locator("#g2b-search-results .g2b-oneclick-btn").first.click()

    assert page.input_value("#f-title") == "AI 기반 공공서비스 구축"
    assert "20250317001-00" in page.input_value("#f-context")
