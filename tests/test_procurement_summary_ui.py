"""Render the production procurement summary with controlled decision states."""
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright


INDEX = Path(__file__).resolve().parents[1] / "app/static/index.html"


@pytest.fixture(params=[(390, 844), (1440, 1000)], ids=["mobile", "desktop"])
def summary_page(request):
    html = INDEX.read_text(encoding="utf-8")
    ranges = [
        ("  function escapeHtml(", "  function makeButtonAccessible("),
        ("  function getProcurementRecommendationMeta(", "  function getProcurementBundleLabel("),
        ("  function formatProcurementActivityTime(", "  function getRecentProcurementOverrideReasons("),
        ("  function renderProcurementSummary(", "  function renderProcurementDecisionCouncilPanel("),
    ]
    source = "\n".join(html[html.index(start):html.index(end)] for start, end in ranges)
    styles = html[html.index("<style>") + len("<style>"):html.index("</style>")]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": request.param[0], "height": request.param[1]})
        page.route("**/*", lambda route: route.abort())
        page.set_content(f'<style>{styles}</style><main id="summary" style="padding:16px"></main>')
        page.add_script_tag(content=source)
        yield page
        browser.close()


def _render(page, **state):
    decision = {"opportunity": {"title": "공공 문서 구축", "issuer": "테스트 기관"}, **state}
    page.evaluate("decision => document.getElementById('summary').innerHTML = renderProcurementSummary(decision)", decision)
    return page.locator(".procurement-summary-list").inner_text()


def test_imported_or_reevaluated_state_does_not_claim_readiness(summary_page):
    text = _render(summary_page, recommendation=None, checklist_items=[], missing_data=[])
    assert "즉시 조치 항목 없음" not in text
    assert "누락 정보: 평가 전" in text
    assert "우선 조치: 판단 갱신 필요" in text

    text = _render(summary_page, recommendation=None, checklist_items=[], missing_data=[],
                   hard_filters=[{"status": "pass", "blocking": False}])
    assert "누락 정보: 없음" in text
    assert "우선 조치: 판단 갱신 필요" in text


def test_blocked_and_unknown_items_are_visible_before_routine_actions(summary_page):
    items = [
        {"status": "action_needed", "title": f"일반 조치 {number}"} for number in range(3)
    ] + [
        {"status": "unknown", "title": "인력 증빙 미확인"},
        {"status": "blocked", "title": "필수 인증 미충족"},
        {"status": "ready", "title": "완료 항목"},
    ]
    text = _render(summary_page, recommendation={"value": "NO_GO"}, checklist_items=items)
    priority = text.split("우선 조치:")[1].split("최근 override")[0]
    assert "차단: 필수 인증 미충족" in priority
    assert "확인 필요: 인력 증빙 미확인" in priority
    assert priority.index("필수 인증") < priority.index("인력 증빙") < priority.index("일반 조치 0")
    assert "완료 항목" not in priority
    assert summary_page.evaluate("decision => getProcurementActionNeededCount(decision)", {"checklist_items": items}) == 3
    artifact = INDEX.parents[2] / "output/playwright" / f"procurement-summary-{summary_page.viewport_size['width']}.png"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    summary_page.locator("#summary").screenshot(path=str(artifact))


def test_missing_checklist_is_not_treated_as_all_ready(summary_page):
    text = _render(summary_page, recommendation={"value": "GO"}, checklist_items=[])
    assert "우선 조치: 체크리스트 미확인" in text
    text = _render(summary_page, recommendation={"value": "GO"},
                   checklist_items=[{"status": "ready", "title": "확인 완료"}])
    assert "우선 조치: 현재 평가상 즉시 조치 항목 없음" in text


def test_priority_text_is_escaped_and_long_words_do_not_overflow(summary_page):
    title = '<img src=x onerror="window.injected=true">' + "long-evidence-" * 35
    text = _render(summary_page, recommendation={"value": "NO_GO"},
                   checklist_items=[{"status": "blocked", "title": title}])
    assert title in text
    assert summary_page.locator("#summary img").count() == 0
    assert summary_page.evaluate("window.injected === undefined")
    assert summary_page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    assert summary_page.locator(".procurement-summary-list").evaluate("el => el.scrollWidth <= el.clientWidth")
