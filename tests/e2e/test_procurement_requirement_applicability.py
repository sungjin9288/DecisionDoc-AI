"""Real local requirement review and export, without external calls."""
import io
import json
from pathlib import Path
from urllib.parse import urlsplit
import zipfile

import pytest
from playwright.sync_api import expect

from tests.e2e.test_procurement_multi_opportunity import _project, scoped_server as scoped_server

pytestmark = pytest.mark.e2e


def _login(page, server, auth=None):
    auth = auth or server["auth"]
    page.goto(server["base_url"])
    page.fill("#login-username", auth["username"])
    page.fill("#login-password", auth["password"])
    with page.expect_response(lambda response: response.url.endswith("/auth/login")) as logged_in:
        page.click("#login-btn")
    assert logged_in.value.status == 200, logged_in.value.text()
    page.wait_for_function("() => Boolean(_currentUser?.sub) && !document.getElementById('login-screen')")


def _open_project(page, project_id):
    page.evaluate("switchPage('project-page')")
    page.evaluate("id => loadProjectDetail(id)", project_id)
    page.wait_for_function("() => _procurementRequirementsState?.status === 'ready'")


def _ready(page):
    project_id = _project(page)["project_id"]
    page.evaluate("switchPage('project-page')")
    page.evaluate("id => loadProjectDetail(id)", project_id)
    page.fill("#project-procurement-url-input", "A")
    page.click("#project-procurement-import-submit")
    page.wait_for_function("() => Boolean(_currentProjectDetail?.procurementDecision?.decision_id)")
    page.click("#project-procurement-refresh-submit")
    page.wait_for_function("() => Boolean(_currentProjectDetail?.procurementDecision?.recommendation)")
    page.wait_for_function("() => _procurementRequirementsState?.status === 'ready'")
    return project_id


def _context(browser, viewport):
    context = browser.new_context(viewport=viewport, service_workers="block", accept_downloads=True)
    context.route("**/*", lambda route: route.continue_() if urlsplit(route.request.url).hostname == "127.0.0.1" else route.abort())
    context.add_init_script("localStorage.setItem('onboarding_done', '1');")
    return context


@pytest.mark.parametrize("viewport", [{"width": 1440, "height": 1000}, {"width": 390, "height": 844}], ids=["desktop", "mobile"])
def test_requirement_review_export_source_change(playwright, scoped_server, viewport, monkeypatch, tmp_path):
    from app.services import g2b_collector
    from app.services.procurement_decision_package.review_packet import verify_procurement_review_packet

    collect = g2b_collector.fetch_announcement_detail
    raw_text = "공고 A\r\n😀 검토 대상 원문 <script>unsafe()</script>\r\n마지막 줄"

    async def unicode_source(**kwargs):
        result = await collect(**kwargs)
        result.raw_text = raw_text
        return result

    monkeypatch.setattr(g2b_collector, "fetch_announcement_detail", unicode_source)
    browser = playwright.chromium.launch()
    context = _context(browser, viewport)
    member_context = None
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        _login(page, scoped_server)
        project_id = _ready(page)
        decision_id = page.evaluate("_currentProjectDetail.procurementDecision.decision_id")
        before = page.evaluate("JSON.stringify(_currentProjectDetail.procurementDecision)")
        page.click('[data-requirement-action="add"]')
        page.fill("#procurement-requirement-title", "내부 검토 대상 범위")
        page.select_option("#procurement-requirement-category", "executive_approval_internal_readiness")
        page.select_option("#procurement-requirement-source", "0")
        page.locator("#procurement-requirement-raw-text").evaluate("element => element.setSelectionRange(0, element.value.length)")
        page.click("#procurement-requirement-use-selection")
        expect(page.locator("#procurement-requirement-selected-quote")).to_have_text(raw_text)
        page.click("#procurement-requirement-save")
        row = page.locator(".procurement-requirement-row")
        expect(row).to_have_count(1)
        expect(page.locator('[data-requirement-count="unknown"]')).to_have_text("미확인 1")
        assert page.evaluate("_procurementRequirementsState.requirements[0].quote") == raw_text
        assert page.evaluate("_procurementRequirementsState.requirements[0].quote_end") == len(raw_text)
        page.click('[data-requirement-action="edit"]')
        page.select_option("#procurement-requirement-applicability", "not_applicable")
        page.fill("#procurement-requirement-rationale", "이번 범위에서 제외하며 운영 승인은 별도입니다.")
        page.click("#procurement-requirement-save")
        expect(page.locator('[data-requirement-count="not_applicable"]')).to_have_text("해당 없음 (N/A) 1")
        assert page.evaluate("JSON.stringify(_currentProjectDetail.procurementDecision)") == before
        row.locator("summary").click()
        expect(row).to_contain_text("이번 범위에서 제외")

        member = {"username": "applicability-reviewer", "password": "Password123!"}
        created = page.evaluate("""async account => {
            const response = await fetch('/admin/users', {method: 'POST',
                headers: {'Content-Type': 'application/json', ...getAuthHeaders()},
                body: JSON.stringify({...account, display_name: 'Assigned reviewer',
                    email: 'reviewer@example.test', role: 'member'})});
            return response.status;
        }""", member)
        assert created == 200
        page.fill("#project-procurement-reviewer-input", member["username"])
        with page.expect_download() as download:
            with page.expect_response(lambda response: "/procurement/review-packet?" in response.url) as exported:
                page.click("#project-procurement-review-packet-submit")
            assert exported.value.status == 200, exported.value.text()
        packet = Path(download.value.path()).read_bytes()
        assert verify_procurement_review_packet(packet)["schema_version"].endswith(".v3")
        with zipfile.ZipFile(io.BytesIO(packet)) as archive:
            projection = json.loads(archive.read("decision_package.json"))["package"]["requirement_applicability"]
            assert projection["requirements"][0]["quote"] == raw_text
            output = tmp_path / "artifacts"
            output.mkdir(parents=True, exist_ok=True)
            if viewport["width"] == 1440:
                (output / "procurement-step8-requirements.docx").write_bytes(archive.read("requirement_applicability.docx"))
                (output / "procurement-step8-review.html").write_bytes(archive.read("procurement_review.html"))
        page.wait_for_function("() => _procurementRequirementsState?.status === 'ready'")
        page.locator('#notification-container button[aria-label="닫기"]').evaluate_all("buttons => buttons.forEach(button => button.click())")
        section = page.locator("#project-procurement-requirements")
        section.evaluate("element => element.scrollIntoView({block: 'start'})")
        row.locator("summary").click()
        box = section.bounding_box()
        assert box and box["x"] >= 0 and box["x"] + box["width"] <= viewport["width"]
        assert section.evaluate("el => el.scrollWidth <= el.clientWidth + 1")
        page.screenshot(path=str(output / f'procurement-step8-{viewport["width"]}.png'))

        member_context = _context(browser, viewport)
        member_page = member_context.new_page()
        _login(member_page, scoped_server, member)
        _open_project(member_page, project_id)
        expect(member_page.locator('[data-requirement-count="not_applicable"]')).to_have_text("해당 없음 (N/A) 1")
        expect(member_page.locator('[data-requirement-action="add"]')).to_have_count(0)
        expect(member_page.locator('[data-requirement-action="edit"]')).to_have_count(0)
        assert "actor_id" not in member_page.evaluate("JSON.stringify(_procurementRequirementsState.requirements)")

        app = scoped_server["app"]
        service = app.state.procurement_applicability_service
        captured = service.capture(project_id, tenant_id="system", decision_id=decision_id)
        path = captured.entry.record.source_snapshots[-1].storage_path
        source = json.loads(service._backend.read_bytes(path))
        source["announcement"]["raw_text"] = "새로 변경된 검토 범위"
        service._backend.write_text(path, json.dumps(source, ensure_ascii=False))
        requirements_path = f'/projects/{project_id}/procurement/opportunities/{decision_id}/requirements'
        with page.expect_response(lambda response: (
            urlsplit(response.url).path == requirements_path
            and response.request.method == 'GET'
        )) as refreshed_requirements:
            page.click('[data-requirement-action="refresh"]')
        assert refreshed_requirements.value.status == 200, refreshed_requirements.value.text()
        expect(page.locator('[data-requirement-count="stale"]')).to_have_text("원문 변경 1")
        expect(page.locator('[data-requirement-count="not_applicable"]')).to_have_text("해당 없음 (N/A) 0")
        expect(page.locator('[data-requirement-count="unknown"]')).to_have_text("미확인 1")
        expect(page.locator('[data-requirement-action="edit"]')).to_be_disabled()
        row.locator("summary").click()
        expect(row).to_contain_text("해당 없음 (N/A)")
        expect(row.locator("blockquote")).to_have_text(raw_text)
        _open_project(member_page, project_id)
        expect(member_page.locator('[data-requirement-count="stale"]')).to_have_text("원문 변경 1")
        assert errors == []
    finally:
        if member_context is not None:
            member_context.close()
        context.close()
        browser.close()


@pytest.mark.parametrize("change", ["page", "auth"])
def test_delayed_source_response_does_not_restore_invalid_editor(playwright, scoped_server, change):
    browser = playwright.chromium.launch()
    context = _context(browser, {"width": 1200, "height": 900})
    page = context.new_page()
    try:
        _login(page, scoped_server)
        _ready(page)
        held = []
        page.route("**/requirements/sources?*", lambda route: held.append(route))
        page.click('[data-requirement-action="add"]')
        page.wait_for_function("() => Boolean(_procurementRequirementsState?.editor)")
        if change == "page":
            page.evaluate("switchPage('generate-page')")
        else:
            page.evaluate("() => { _authSessionRevision += 1; invalidateProcurementRequirements(); }")
        assert len(held) == 1
        held[0].fulfill(json={"decision_id": "old", "decision_revision": 3, "sources": [], "operational_approval": False})
        expect(page.locator("#procurement-requirement-form")).to_have_count(0)
        assert page.evaluate("_procurementRequirementsState") is None
    finally:
        context.close()
        browser.close()
