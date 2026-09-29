import pytest
from playwright.sync_api import expect

from tests.test_manual_style_ui import style_page  # noqa: F401


@pytest.mark.parametrize("stale", [False, "profile", "auth"])
def test_local_import_single_flight_and_stale_results(style_page, stale):  # noqa: F811
    page = style_page
    page.locator('#style-local-file-input').set_input_files(
        {"name": "source.txt", "mimeType": "text/plain", "buffer": b"Evidence first."}
    )
    page.evaluate("void importStyleExamples('manual-ui')")
    assert page.evaluate("postCount") == 1
    expect(page.locator('[data-style-detail-action="import-file"]')).to_be_disabled()
    if stale == "profile":
        page.evaluate("document.getElementById('style-detail').dataset.styleDetailProfileId='other'")
    elif stale == "auth":
        page.evaluate("window.testAuthHeaders={Authorization:'changed'}")
    page.evaluate("pendingSave({ok:true, json:async()=>({method:'local_text',provider_calls:0,imported:[{}],failed:[{}]})})")
    expect(page.locator('[data-style-detail-action="import-file"]')).to_be_enabled()
    if stale:
        assert page.evaluate("notifications.length") == 0
    else:
        assert page.evaluate("notifications.at(-1).type") == "warn"


def test_local_import_limit_and_uncertain_response(style_page):  # noqa: F811
    page = style_page
    file = {"name": "source.txt", "mimeType": "text/plain", "buffer": b"Evidence."}
    page.locator('#style-local-file-input').set_input_files([file] * 9)
    assert page.evaluate("postCount") == 0
    page.locator('#style-local-file-input').set_input_files(file)
    page.evaluate("pendingSave({ok:false})")
    expect(page.locator('[data-style-detail-action="import-file"]')).to_be_enabled()
    assert page.evaluate("postCount") == 1
    assert "목록" in page.evaluate("notifications.at(-1).message")
    assert page.locator('#style-local-file-input').input_value() == ""
