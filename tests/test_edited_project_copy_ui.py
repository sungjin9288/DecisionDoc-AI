from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright


@pytest.fixture
def copy_page():
    html = (Path(__file__).resolve().parents[1] / "app/static/index.html").read_text()
    functions = html[
        html.index("  const editedProjectDrafts =") : html.index(
            "  function buildGeneratedApprovalSource("
        )
    ]
    payload = html[
        html.index("  function buildEditedExportDocsPayload(") : html.index(
            "  function getCurrentApprovalRequestSource("
        )
    ]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.route(
            "**/*",
            lambda route: route.fulfill(
                content_type="text/html",
                body='<button id="save-edited-copy-btn">Save</button>',
            ),
        )
        page.goto("http://127.0.0.1/copy-ui-test")
        page.add_script_tag(
            content="""
            const $id = id => document.getElementById(id);
            let isEditing = false;
            let generatedDocs = [{doc_type:'adr', markdown:'Original', _editedMarkdown:'Edited'}];
            let lastRequestPayload = {project_id:'project', title:'Edited'};
            let lastMeta = {};
            let identityHeaders = {Authorization:'synthetic'};
            const getAuthHeaders = () => identityHeaders;
            const notifications = [];
            const showNotification = (message, type) => notifications.push({message, type});
            const requests = [];
            window.fetch = async (url, options) => {
                requests.push(JSON.parse(options.body));
                return new Promise((resolve, reject) => { window.resolveSave = resolve; window.rejectSave = reject; });
            };
        """
            + functions
            + payload
            + """
            editedProjectDrafts.set(generatedDocs, {
                source:{document:{doc_id:'parent', title:'Original'}, parent_sha256:'a'.repeat(64)},
                identity:JSON.stringify(getAuthHeaders()), pending:null
            });
        """
        )
        yield page
        browser.close()


def test_lost_response_retry_preserves_exact_operation(copy_page):
    page = copy_page
    page.click("#save-edited-copy-btn")
    page.evaluate("saveEditedProjectCopy()")
    assert page.evaluate("requests.length") == 1
    page.evaluate("rejectSave(new Error('Connection lost'))")
    expect(page.locator("#save-edited-copy-btn")).to_be_enabled()
    page.evaluate("generatedDocs[0]._editedMarkdown = 'New unsaved input'")
    page.click("#save-edited-copy-btn")
    assert page.evaluate("requests[0]") == page.evaluate("requests[1]")
    page.evaluate("""() => {
        const request = requests[1];
        resolveSave({ok:true, json:async()=>({project_id:'project', operation_id:request.operation_id,
            operational_approval:false, parent_sha256:'b'.repeat(64), document:{doc_id:'copy',
            title:request.title, request_id:'', source_kind:'edited_copy', doc_snapshot:JSON.stringify(request.docs),
            edited_copy:{parent_id:'parent', parent_sha256:request.parent_sha256}}})});
    }""")
    expect(page.locator("#save-edited-copy-btn")).to_be_enabled()
    assert page.evaluate("generatedDocs[0]._editedMarkdown") == "New unsaved input"
    assert "아직 저장되지 않았습니다" in page.evaluate("notifications.at(-1).message")


@pytest.mark.parametrize(
    "change", ["generatedDocs = []", "identityHeaders = {Authorization:'other'}"]
)
def test_stale_save_response_is_ignored(copy_page, change):
    page = copy_page
    page.click("#save-edited-copy-btn")
    page.evaluate(change)
    page.evaluate("resolveSave({ok:true,json:async()=>({})})")
    expect(page.locator("#save-edited-copy-btn")).to_be_enabled()
    assert page.evaluate("notifications.length") == 0


def test_validation_failure_keeps_edits_and_allows_corrected_request(copy_page):
    page = copy_page
    page.click("#save-edited-copy-btn")
    page.evaluate("resolveSave({ok:false,status:422})")
    expect(page.locator("#save-edited-copy-btn")).to_be_enabled()
    assert page.evaluate("generatedDocs[0]._editedMarkdown") == "Edited"
    page.click("#save-edited-copy-btn")
    assert page.evaluate("requests[0].operation_id !== requests[1].operation_id")
    page.evaluate("resolveSave({ok:false,status:422})")
    expect(page.locator("#save-edited-copy-btn")).to_be_enabled()
