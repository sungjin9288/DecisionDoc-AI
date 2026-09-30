from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
from playwright.sync_api import expect
from tests.browser_pages import isolated_page


INDEX = Path(__file__).resolve().parents[1] / "app/static/index.html"


@pytest.fixture
def style_page(browser):
    html = INDEX.read_text(encoding="utf-8")
    css = html.split("<style>", 1)[1].split("</style>", 1)[0]
    helpers = html[html.index("  function escapeHtml("):html.index("  function makeButtonAccessible(")]
    functions = html[html.index("  async function loadStyleDetail("):html.index("  async function setDefaultStyle(")]
    with isolated_page(browser, viewport={"width": 390, "height": 844}) as page:
        page.set_default_timeout(5000)
        page.route("**/*", lambda route: route.abort())
        page.set_content(f"<style>{css}</style><div id='style-list'></div><div id='style-detail'></div>")
        page.add_script_tag(content="""
            const $id = id => document.getElementById(id);
            const _bundleNameMap = {tech_decision: '기술 의사결정'};
            const getAuthHeaders = () => (window.testAuthHeaders || {});
            const getTenantHeaders = () => ({});
            const notifications = [];
            function showNotification(message, type) { notifications.push({message, type}); }
            const profile = {
                profile_id: 'manual-ui', name: 'Manual', description: '',
                is_default: true, tone_guide: {}, bundle_overrides: {}, examples: []
            };
            let pendingSave;
            let pendingRefresh;
            let deferRefresh = false;
            let postCount = 0;
            window.fetch = async (url, options = {}) => {
                if (options.method === 'POST') {
                    postCount++;
                    return await new Promise(resolve => { pendingSave = resolve; });
                }
                if (deferRefresh) return await new Promise(resolve => { pendingRefresh = resolve; });
                return {ok: true, json: async () => profile};
            };
        """ + helpers + functions + "\nrenderStyleDetail(profile);")
        yield page


@pytest.mark.parametrize("outcome", ["success", "http_error", "network_error"])
def test_style_creation_single_flight_and_failure_preserves_input(style_page, outcome):
    page = style_page
    html = INDEX.read_text(encoding="utf-8")
    page.add_script_tag(content=html[
        html.index("  function showCreateStyleModal("):
        html.index("  function showAddBundleOverrideModal(")
    ])
    page.evaluate("""() => {
        window.createRequests = [];
        window.fetch = async (url, options = {}) => {
            if (options.method === 'POST') {
                createRequests.push(JSON.parse(options.body));
                return new Promise((resolve, reject) => {
                    window.finishCreate = resolve;
                    window.failCreate = reject;
                });
            }
            return {ok:true, json:async()=>profile};
        };
        showCreateStyleModal();
    }""")
    page.fill("#new-style-name", "Lifecycle profile")
    page.fill("#new-style-desc", "Preserved description")
    page.click("[data-style-create-submit]")
    page.evaluate("void submitCreateStyleProfile(document.querySelector('.modal-overlay'))")
    assert page.evaluate("createRequests.length") == 1
    for selector in ("#new-style-name", "#new-style-desc",
                     "[data-style-create-submit]", "[data-style-modal-close]"):
        expect(page.locator(selector)).to_be_disabled()

    if outcome == "success":
        page.evaluate("finishCreate({ok:true, json:async()=>profile})")
        expect(page.locator("[data-style-create-submit]")).to_have_count(0)
        assert page.evaluate("notifications.at(-1).type") == "success"
        return
    if outcome == "http_error":
        page.evaluate("finishCreate({ok:false, text:async()=> 'Unavailable'})")
    else:
        page.evaluate("failCreate(new Error('Network unavailable'))")
    expect(page.locator("[data-style-create-submit]")).to_be_enabled()
    expect(page.locator("[data-style-modal-close]")).to_be_enabled()
    expect(page.locator("#new-style-name")).to_be_enabled()
    expect(page.locator("#new-style-desc")).to_be_enabled()
    expect(page.locator("#new-style-name")).to_have_value("Lifecycle profile")
    expect(page.locator("#new-style-desc")).to_have_value("Preserved description")
    assert page.evaluate("createRequests.length") == 1
    assert page.evaluate("notifications.at(-1).type") == "error"
    page.click("[data-style-modal-close]")
    expect(page.locator("[data-style-create-submit]")).to_have_count(0)


def begin_style_analysis(page):
    page.evaluate("""() => {
        window.testAuthHeaders = {Authorization:'Bearer fixture', 'X-Tenant-Id':'tenant-a'};
        window.analysisCalls = [];
        window.refreshCalls = 0;
        window.fetch = async (url, options = {}) => {
            if (options.method === 'POST') {
                analysisCalls.push({url, headers:options.headers,
                    filename:options.body.get('files').name});
                return await new Promise(resolve => { pendingSave = resolve; });
            }
            refreshCalls++;
            return {ok:true, json:async()=>profile};
        };
    }""")
    page.locator('#style-file-input').set_input_files(
        {"name": "sample.txt", "mimeType": "text/plain", "buffer": b"Sample style."}
    )
    page.wait_for_function('analysisCalls.length === 1')


def test_style_analysis_carries_auth_and_blocks_duplicate_upload(style_page):
    page = style_page
    begin_style_analysis(page)
    page.evaluate("void analyzeStyleDocuments('manual-ui')")
    assert page.evaluate('analysisCalls.length') == 1
    assert page.evaluate('analysisCalls[0].headers') == {
        'Authorization': 'Bearer fixture', 'X-Tenant-Id': 'tenant-a'
    }
    expect(page.locator('[data-style-detail-action="pick-file"]')).to_be_disabled()
    page.evaluate("pendingSave({ok:false, text:async()=> 'Analysis unavailable'})")
    expect(page.locator('[data-style-detail-action="pick-file"]')).to_be_enabled()
    assert page.evaluate('notifications.at(-1).type') == 'error'


@pytest.mark.parametrize('change', ['profile', 'auth'])
def test_style_analysis_ignores_result_after_context_change(style_page, change):
    page = style_page
    begin_style_analysis(page)
    if change == 'profile':
        page.evaluate("renderStyleDetail({...profile, profile_id:'next', name:'Next'})")
    else:
        page.evaluate("window.testAuthHeaders = {Authorization:'Bearer other'}")
    page.evaluate("""() => {
        notifications.length = 0;
        pendingSave({ok:true, json:async()=>({analyzed:[{}], failed:[]})});
    }""")
    page.wait_for_function("!document.querySelector('#style-file-input').disabled")
    assert page.evaluate('refreshCalls') == 0
    assert page.evaluate('notifications.length') == 0
    if change == 'profile':
        expect(page.locator('#style-detail h3')).to_have_text('Next')


def test_style_analysis_reports_partial_success(style_page):
    page = style_page
    begin_style_analysis(page)
    page.evaluate("pendingSave({ok:true, json:async()=>({analyzed:[{}], failed:[{error:'Invalid file'}]})})")
    page.wait_for_function("notifications.at(-1).type === 'warn'")
    assert page.evaluate('refreshCalls') == 1
    expect(page.locator('[data-style-detail-action="pick-file"]')).to_be_enabled()


def test_manual_style_failure_preserves_input_and_blocks_double_submit(style_page):
    page = style_page
    page.locator("#style-example-name").fill("Manual example")
    page.locator("#style-example-sentences").fill("A preferred sentence.")
    save = page.locator("#style-example-save")
    save.click()
    expect(save).to_be_disabled()
    assert page.evaluate("postCount") == 1
    page.evaluate("pendingSave({ok:false, status:422, text:async()=> 'Invalid example', json:async()=>({detail:'Invalid example'})})")
    expect(save).to_be_enabled()
    expect(page.locator("#style-example-name")).to_have_value("Manual example")
    expect(page.locator("#style-example-sentences")).to_have_value("A preferred sentence.")
    assert page.evaluate("notifications.at(-1).type") == "error"


def test_manual_style_success_renders_saved_text_without_markup(style_page, tmp_path):
    page = style_page
    label = "<img src=x onerror=alert(1)>"
    sentence = "<script>alert(1)</script> Preferred sentence."
    page.locator("#style-example-name").fill(label)
    page.locator("#style-example-sentences").fill(sentence)
    page.locator("#style-example-save").click()
    page.evaluate("""({label, sentence}) => {
        profile.examples = [{example_id:'saved', source_filename:label,
            bundle_id:'<img src=x onerror=alert(2)>', sample_sentences:[sentence], extracted_patterns:[]}];
        pendingSave({ok:true, json:async()=>({example_id:'saved'})});
    }""", {"label": label, "sentence": sentence})
    expect(page.locator(".style-example-item")).to_contain_text(label)
    expect(page.locator(".sample-sentence")).to_contain_text(sentence)
    assert page.locator(".style-example-item img, .style-example-item script").count() == 0
    expect(page.locator("#style-example-name")).to_have_value("")
    expect(page.locator("#style-example-sentences")).to_have_value("")
    path = Path(os.environ.get("MANUAL_STYLE_SCREENSHOT_DIR", tmp_path))
    path.mkdir(parents=True, exist_ok=True)
    page.locator("#style-example-name").scroll_into_view_if_needed()
    page.screenshot(path=str(path / "manual-style-mobile.png"))


def test_pending_manual_save_does_not_reopen_previous_profile(style_page):
    page = style_page
    page.locator("#style-example-name").fill("Previous profile")
    page.locator("#style-example-sentences").fill("A sentence.")
    page.locator("#style-example-save").click()
    page.evaluate("renderStyleDetail({...profile, profile_id:'next-profile', name:'Next profile'})")
    page.evaluate("pendingSave({ok:true, json:async()=>({example_id:'saved'})})")
    expect(page.locator("#style-detail h3")).to_have_text("Next profile")
    expect(page.locator("#style-example-save")).to_be_enabled()
    assert page.evaluate("notifications.length") == 0


def test_manual_refresh_does_not_replace_newer_profile(style_page):
    page = style_page
    page.locator("#style-example-name").fill("Previous profile")
    page.locator("#style-example-sentences").fill("A sentence.")
    page.locator("#style-example-save").click()
    page.evaluate("deferRefresh = true; pendingSave({ok:true, json:async()=>({example_id:'saved'})})")
    page.wait_for_function("typeof pendingRefresh === 'function'")
    page.evaluate("renderStyleDetail({...profile, profile_id:'next-profile', name:'Next profile'})")
    page.evaluate("pendingRefresh({ok:true, json:async()=>profile})")
    expect(page.locator("#style-detail h3")).to_have_text("Next profile")


def test_style_management_navigation_returns_to_generation(style_page):
    page = style_page
    html = INDEX.read_text(encoding="utf-8")
    buttons = [re.search(rf'<button id="{name}"[^>]*>.*?</button>', html).group(0)
               for name in ("style-manage-btn", "style-return-btn")]
    page.set_content(f"<main>{buttons[0]}</main><div id='style-page' style='display:none'>{buttons[1]}</div>")
    switcher = html[html.index("  window.switchPage ="):html.index("  /* ── DocumentOps Agent UI")]
    start = html.index("  $id('style-manage-btn')?.addEventListener")
    end = html.index("  });", html.index("  $id('style-return-btn')", start)) + len("  });")
    # switchPage invalidates project/procurement detail state on every non-project page.
    stubs = (
        "let profileLoads=0; let inlineLoads=0; let _projectDetailLoadId=0; let invalidations=0;"
        " function loadStyleProfiles(){profileLoads++} function loadStylesInline(){inlineLoads++}"
        " function invalidateProcurementRequirements(){invalidations++}"
    )
    page.add_script_tag(content=stubs + switcher + html[start:end])
    page.locator("#style-manage-btn").click()
    expect(page.locator("#style-page")).to_be_visible()
    expect(page.locator("main")).to_be_hidden()
    assert page.evaluate("profileLoads") == 1
    assert page.evaluate("invalidations") == 1
    page.locator("#style-return-btn").click()
    expect(page.locator("main")).to_be_visible()
    expect(page.locator("#style-page")).to_be_hidden()
    assert page.evaluate("inlineLoads") == 1


def test_inline_style_refresh_preserves_selection_and_clears_deleted_id(style_page):
    page = style_page
    html = INDEX.read_text(encoding="utf-8")
    page.set_content("<select id='inline-style-select'></select><div id='inline-style-desc'></div>")
    start = html.index("  let _cachedStyleProfiles =")
    end = html.index("  async function loadStyleProfiles()", start)
    page.add_script_tag(content=html[start:end])
    page.evaluate("""() => {
        window.fetch = async () => ({ok:true, json:async()=>({profiles:[
            {profile_id:'a', name:'A', is_default:true},
            {profile_id:'b', name:'B', description:'Selected'}]})});
        window._selectedStyleId = 'b';
    }""")
    page.evaluate("loadStylesInline()")
    expect(page.locator("#inline-style-select")).to_have_value("b")
    expect(page.locator("#inline-style-desc")).to_have_text("Selected")
    page.evaluate("window._selectedStyleId = 'deleted'; loadStylesInline()")
    expect(page.locator("#inline-style-select")).to_have_value("a")
    page.evaluate("window._selectedStyleId = null; loadStylesInline()")
    expect(page.locator("#inline-style-select")).to_have_value("")


def test_profile_and_tone_values_are_literal_text(style_page):
    page = style_page
    value = '\"><img src=x onerror=alert(1)>'
    rule = '</textarea><img src=x onerror=alert(2)>'
    page.evaluate("""({value, rule}) => renderStyleDetail({...profile,
        name:value, description:value,
        tone_guide:{custom_rules:[rule], preferred_words:[value], forbidden_words:[value]},
        bundle_overrides:{[value]:{formality:value, density:value}}
    })""", {"value": value, "rule": rule})
    assert page.locator("#style-detail img, #style-detail script").count() == 0
    expect(page.locator("#style-detail h3")).to_have_text(value)
    expect(page.locator("#tone-rules")).to_have_value(rule)
    expect(page.locator("#tone-preferred")).to_have_value(value)
    expect(page.locator("#tone-forbidden")).to_have_value(value)
    assert page.evaluate("collectToneFormValues().custom_rules") == [rule]


def test_tone_autosave_keeps_values_from_the_edited_profile(style_page):
    page = style_page
    page.evaluate("""() => {
        window.savedTone = null;
        window.fetch = async (url, options) => {
            window.savedTone = {url, body:JSON.parse(options.body)};
            return {ok:true};
        };
    }""")
    page.locator("#tone-rules").fill("Rules for A")
    page.evaluate("autoSaveTone('manual-ui'); renderStyleDetail({...profile, profile_id:'b', tone_guide:{custom_rules:['Rules for B']}})")
    page.wait_for_function("window.savedTone !== null")
    assert page.evaluate("window.savedTone.url") == "/styles/manual-ui/tone"
    assert page.evaluate("window.savedTone.body.custom_rules") == ["Rules for A"]
    expect(page.locator("#tone-rules")).to_have_value("Rules for B")
    assert page.evaluate("notifications.length") == 0


def test_tone_autosave_preserves_edits_to_both_profiles(style_page):
    page = style_page
    page.evaluate("""() => {
        window.toneWrites = [];
        window.fetch = async (url, options) => {
            window.toneWrites.push({url, body:JSON.parse(options.body)});
            return {ok:true};
        };
    }""")
    page.locator("#tone-rules").fill("Rules for A")
    page.evaluate("autoSaveTone('manual-ui'); renderStyleDetail({...profile, profile_id:'b', tone_guide:{custom_rules:['Rules for B']}}); autoSaveTone('b')")
    page.wait_for_function("window.toneWrites.length === 2")
    assert page.evaluate("window.toneWrites.map(write => [write.url, write.body.custom_rules])") == [
        ["/styles/manual-ui/tone", ["Rules for A"]],
        ["/styles/b/tone", ["Rules for B"]],
    ]


def test_tone_autosave_does_not_write_after_auth_context_changes(style_page):
    page = style_page
    page.evaluate("""() => {
        window.toneWrites = 0;
        window.fetch = async () => { window.toneWrites++; return {ok:true}; };
        window.testAuthHeaders = {'X-Tenant-ID':'tenant-a'};
        autoSaveTone('manual-ui');
        window.testAuthHeaders = {'X-Tenant-ID':'tenant-b'};
    }""")
    page.wait_for_function("_toneAutoSaveTimers.size === 0")
    assert page.evaluate("window.toneWrites") == 0


@pytest.mark.parametrize("first_ok", [True, False])
def test_tone_autosave_serializes_same_profile_edits(style_page, first_ok):
    page = style_page
    page.evaluate("""() => {
        window.toneWrites = [];
        window.fetch = async (url, options) => {
            toneWrites.push(JSON.parse(options.body).custom_rules);
            if (toneWrites.length === 1) {
                return await new Promise(resolve => { window.finishFirst = resolve; });
            }
            return {ok:true};
        };
    }""")
    page.locator('#tone-rules').fill('First edit')
    page.evaluate("autoSaveTone('manual-ui')")
    page.wait_for_function('toneWrites.length === 1')
    page.locator('#tone-rules').fill('Latest edit')
    page.evaluate("autoSaveTone('manual-ui')")
    page.wait_for_function('_toneAutoSaveTimers.size === 0')
    assert page.evaluate('toneWrites') == [['First edit']]
    page.evaluate("ok => finishFirst({ok, text:async()=> 'Save failed'})", first_ok)
    page.wait_for_function('toneWrites.length === 2')
    assert page.evaluate('toneWrites') == [['First edit'], ['Latest edit']]
    page.wait_for_function("notifications.length === 1")
    assert page.evaluate('notifications[0].type') == 'success'


def test_queued_tone_save_checks_auth_again_before_sending(style_page):
    page = style_page
    page.evaluate("""() => {
        window.toneWrites = 0;
        window.fetch = async () => {
            toneWrites++;
            return await new Promise(resolve => { window.finishFirst = resolve; });
        };
        autoSaveTone('manual-ui');
    }""")
    page.wait_for_function('toneWrites === 1')
    page.locator('#tone-rules').fill('Queued edit')
    page.evaluate("autoSaveTone('manual-ui')")
    page.wait_for_function('_toneAutoSaveTimers.size === 0')
    assert page.evaluate('toneWrites') == 1
    page.evaluate("window.testAuthHeaders = {Authorization:'Bearer changed'}; finishFirst({ok:true})")
    page.wait_for_function('_toneAutoSaveRequests.size === 0')
    assert page.evaluate('toneWrites') == 1
    assert page.evaluate('notifications.length') == 0
