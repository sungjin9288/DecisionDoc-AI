from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright


INDEX = Path(__file__).resolve().parents[1] / "app/static/index.html"


@pytest.fixture
def sketch_page():
    html = INDEX.read_text(encoding="utf-8")
    helpers = html[html.index("  function escapeHtml("):html.index("  function makeButtonAccessible(")]
    functions = html[html.index("  function _captureSketchEdits("):html.index("  function rerunSketchFromCurrentPayload(")]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.route("**/*", lambda route: route.abort())
        ids = ["sketch-sections", "sketch-search-badge", "sketch-pages", "sketch-slides",
               "sketch-search-snippets", "sketch-page-cards", "sketch-slide-cards", "sketch-snippets-list"]
        page.set_content("".join(f'<div id="{name}"></div>' for name in ids))
        page.add_script_tag(content="const $id = id => document.getElementById(id);" + helpers + functions)
        yield page
        browser.close()


@pytest.mark.parametrize("presentation", [False, True])
def test_sketch_renders_provider_text_literally_and_preserves_edits(sketch_page, presentation):
    page = sketch_page
    text = '<img src=x onerror="window.injected=true"> & <b>literal</b>'
    sketch = {"sections": [{"heading": text, "bullets": [text]}],
              "has_search": True, "search_snippets": [text]}
    if presentation:
        sketch["ppt_slides"] = [{"page": 1, "title": text, "key_content": text}]
    page.evaluate("sketch => renderSketch(sketch)", sketch)
    assert page.locator("img, b").count() == 0
    assert page.evaluate("window.injected === undefined")
    expect(page.locator(".sketch-heading")).to_have_text(text)
    expect(page.locator("#sketch-page-cards .slide-title")).to_have_text(text)
    expect(page.locator("#sketch-page-cards .slide-content")).to_have_text(text)
    expect(page.locator(".snippet-item")).to_have_text(text)
    if presentation:
        expect(page.locator("#sketch-slide-cards .slide-title")).to_have_text(text)
        expect(page.locator("#sketch-slide-cards .slide-content")).to_have_text(text)
    page.locator(".sketch-heading").fill("Edited <title>")
    page.locator(".sketch-section li").fill("Budget < 100 & scope > 0")
    assert page.evaluate("_captureSketchEdits()") == (
        "\n\n[구성 스케치]\n### Edited <title>\n- Budget < 100 & scope > 0"
    )


def test_empty_sketch_clears_editable_sections_and_hides_optional_results(sketch_page):
    page = sketch_page
    page.evaluate("renderSketch({sections:[{heading:'First',bullets:['One']}],has_search:true,search_snippets:['Source']})")
    page.evaluate("renderSketch({sections:[]})")
    expect(page.locator(".sketch-section")).to_have_count(0)
    for name in ("sketch-search-badge", "sketch-pages", "sketch-slides", "sketch-search-snippets"):
        expect(page.locator(f"#{name}")).to_be_hidden()
    assert page.evaluate("_captureSketchEdits()") == ""


@pytest.fixture
def sketch_requests(sketch_page):
    page = sketch_page
    html = INDEX.read_text(encoding="utf-8")
    start = html.index("  /* ── runSketch: Step 1")
    end = html.index("  /* ── Capture user sketch edits", start)
    page.evaluate("""() => {
        document.body.insertAdjacentHTML('beforeend',
            '<div id="sketch-panel"></div><button id="generate-btn">Generate</button>');
    }""")
    page.add_script_tag(content="""
        let _sketchPayloadJson = null;
        let _lastSketchResult = null;
        const selectedBundle = {icon:'', name_ko:'Document'};
        const getAuthHeaders = () => ({});
        const statuses = [];
        const setStatus = (...args) => statuses.push(args);
        const updateStepProgress = () => {};
        const requests = [];
        const _fetchJsonWithProviderRetry = fetcher => fetcher();
        window.fetch = (url, options) => new Promise((resolve, reject) => {
            requests.push({resolve, reject, body:options.body});
        });
    """ + html[start:end])
    return page


@pytest.mark.parametrize("old_failed", [False, True])
def test_sketch_older_response_cannot_replace_latest_result(sketch_requests, old_failed):
    page = sketch_requests
    page.evaluate("void runSketch('old'); void runSketch('new')")
    page.evaluate("requests[1].resolve({sections:[{heading:'Latest', bullets:[]}]})")
    expect(page.locator('.sketch-heading')).to_have_text('Latest')
    page.evaluate("""failed => {
        if (failed) requests[0].reject(new Error('Old failure'));
        else requests[0].resolve({sections:[{heading:'Old', bullets:[]}]});
    }""", old_failed)
    expect(page.locator('.sketch-heading')).to_have_text('Latest')
    assert page.evaluate('_lastSketchResult.sections[0].heading') == 'Latest'
    assert page.evaluate('_sketchPayloadJson') == 'new'
    assert page.evaluate('statuses.at(-1)') == ['', '']


def test_sketch_old_completion_does_not_unlock_new_pending_request(sketch_requests):
    page = sketch_requests
    page.evaluate("void runSketch('old'); void runSketch('new'); $id('generate-btn').disabled = true")
    page.evaluate("requests[0].resolve({sections:[{heading:'Old', bullets:[]}]})")
    expect(page.locator('#generate-btn')).to_be_disabled()
    expect(page.locator('#sketch-panel')).to_be_hidden()
    assert page.evaluate('_lastSketchResult') is None
    page.evaluate("requests[1].reject(new Error('Latest failure'))")
    expect(page.locator('#generate-btn')).to_be_enabled()
    assert page.evaluate('statuses.at(-1)[1]') == 'error'
