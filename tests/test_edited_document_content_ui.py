from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright


INDEX = Path(__file__).resolve().parents[1] / "app/static/index.html"


@pytest.fixture
def content_page():
    html = INDEX.read_text(encoding="utf-8")
    functions = html[
        html.index("  function buildGeneratedApprovalSource("):
        html.index("  function getCurrentApprovalRequestSource(")
    ]
    export = html[
        html.index("  async function _buildExportedBlob("):
        html.index("  async function exportDocument(")
    ]
    review = html[html.index("  function _getMarkdownContent("):html.index("  function _showReviewModal(")]
    knowledge = html[
        html.index("  function _normalizeKnowledgePromotionTarget("):
        html.index("  function _getActiveKnowledgePromotionTarget(")
    ]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.route("**/*", lambda route: route.abort())
        page.add_script_tag(content="""
            let generatedDocs = [];
            let activeTab = 0;
            const lastMeta = {request_id: 'request', bundle_id: 'bundle'};
            let lastRequestPayload = {title: 'Draft', project_id: 'project'};
            const lastVisualAssets = [];
            const selectedBundle = {id: 'tech_decision'};
            const getGovOptions = () => null;
            let getAuthHeaders = () => ({});
            window.fetch = async (url, options) => {
                window.exportRequest = {url, body: JSON.parse(options.body)};
                return {ok: true, blob: async () => new Blob(['export'])};
            };
        """ + functions + export + review + knowledge)
        yield page
        browser.close()


@pytest.mark.parametrize("edited", [None, "", "Changed content"])
def test_export_and_approval_preserve_explicit_empty_edits(content_page, edited):
    doc = {"doc_type": "adr", "markdown": "Original content"}
    if edited is not None:
        doc["_editedMarkdown"] = edited
    expected = "Original content" if edited is None else edited
    page = content_page
    page.evaluate("doc => { generatedDocs = [doc]; }", doc)
    assert page.evaluate("buildEditedExportDocsPayload(generatedDocs)[0].markdown") == expected
    assert page.evaluate("buildGeneratedApprovalSource().docs[0].markdown") == expected
    page.evaluate("_buildExportedBlob('docx')")
    assert page.evaluate("exportRequest.url") == "/generate/export-edited"
    assert page.evaluate("exportRequest.body.docs[0].markdown") == expected
    assert page.evaluate("generatedDocs[0].markdown") == "Original content"
    assert page.evaluate("_getMarkdownContent()") == expected


def test_empty_edit_is_not_promoted_as_original_knowledge(content_page):
    content_page.evaluate("""() => { generatedDocs = [
        {doc_type: 'adr', markdown: 'Original content', _editedMarkdown: ''}
    ]; }""")
    assert content_page.evaluate("_buildKnowledgePromotionState().docs") == []
    assert content_page.evaluate("""_normalizeKnowledgePromotionTarget({
        projectId: 'project', title: 'Draft', bundleType: 'tech_decision',
        docs: generatedDocs
    })""") is None


def test_explicit_original_export_ignores_edits(content_page):
    assert content_page.evaluate("""() => buildEditedExportDocsPayload([
        {doc_type: 'adr', markdown: 'Original', _editedMarkdown: ''}
    ], {preferEdited: false})[0].markdown""") == "Original"


@pytest.mark.parametrize("row,expected", [
    (r"| File | C:\docs\d.docx | A \| B |", ["File", r"C:\docs\d.docx", "A | B"]),
    (r"Name | value\|", ["Name", "value|"]),
    (r"Name | value\\|", ["Name", "value\\"]),
    ("Name | C:\\docs\\", ["Name", "C:\\docs\\"]),
    (r"| Name | <img src=x onerror=alert(1)> \| <script>bad()</script> |",
     ["Name", "<img src=x onerror=alert(1)> | <script>bad()</script>"]),
])
def test_table_cells_preserve_escaped_content_without_html_execution(content_page, row, expected):
    html = INDEX.read_text(encoding="utf-8")
    helpers = html[html.index("  function escapeHtml("):html.index("  function makeButtonAccessible(")]
    parser = html[html.index("  function sanitizeMarkdownHref("):html.index("  function renderMarkdown(")]
    content_page.add_script_tag(content=helpers + parser)
    content_page.evaluate("""row => {
        document.body.innerHTML = '<table><tbody><tr>' + splitMarkdownTableRow(row)
            .map(cell => '<td>' + cell + '</td>').join('') + '</tr></tbody></table>';
    }""", row)
    assert content_page.locator('td').all_text_contents() == expected
    assert content_page.locator('table img, table script').count() == 0


def _load_document_editor(page, *, section_rewrite=False):
    html = INDEX.read_text(encoding="utf-8")
    start = html.index("  function showDoc(")
    if "  function captureCurrentDocumentEdits(" in html:
        start = html.index("  function captureCurrentDocumentEdits(")
    page.set_content('<div id="doc-pane"></div><button id="edit-btn">Edit</button>')
    page.add_script_tag(content=html[
        html.index("  function escapeHtml("):html.index("  function makeButtonAccessible(")
    ] + html[
        html.index("  function sanitizeMarkdownHref("):html.index("  function setStatus(")
    ])
    rewrite = html[
        html.index("  function addSectionRewriteButtons("):
        html.index("  /* ═", html.index("  function showSectionRewriteModal("))
    ] if section_rewrite else 'const addSectionRewriteButtons = () => {};'
    page.add_script_tag(content="""
        const $id = id => document.getElementById(id);
        const safeMarkdown = renderMarkdown;
    """ + rewrite + html[start:html.index("  /* ── Copy", start)] + html[
        html.index("  let isEditing = false;"):html.index("  /* ── PDF 내보내기", html.index("  let isEditing = false;"))
    ])


def _load_export_actions(page):
    _load_document_editor(page)
    html = INDEX.read_text(encoding='utf-8')
    page.evaluate("""() => {
        document.body.insertAdjacentHTML('beforeend', '<button id="export-btn">Markdown</button>');
        window.requests = [];
        window.downloads = [];
        window.notices = [];
        window.fetch = async (url, options) => {
            requests.push({url, body:JSON.parse(options.body)});
            return {ok:true, blob:async()=>new Blob(['converted']), json:async()=>({files:[]})};
        };
        window._triggerBrowserDownload = (blob, filename, label) => downloads.push({blob, filename, label});
        window.showNotification = (...args) => notices.push(args);
        window.setStatus = () => {};
        window.showPostDownloadPrompt = () => {};
        window.showFeedbackCard = () => {};
    }""")
    page.add_script_tag(content=html[
        html.index("  /* ── Export ─"):html.index("  $id('sketch-again-btn')")
    ] + html[
        html.index("  async function exportDocument("):
        html.index("  /* ── Cancel button", html.index("  async function exportDocument("))
    ])


@pytest.mark.parametrize('edited', ['한글 초안\n\n| 경로 | 값 |\n| --- | --- |\n| C:\\docs | A \\| B |', ''])
def test_markdown_download_uses_active_live_draft_without_network(content_page, edited):
    page = content_page
    _load_export_actions(page)
    page.evaluate("""() => {
        generatedDocs = [{doc_type:'adr', markdown:'Other'}, {doc_type:'onepager', markdown:'Original'}];
        activeTab = 1; showDoc(1);
    }""")
    page.click('#edit-btn')
    page.locator('#doc-pane textarea').fill(edited)
    page.click('#export-btn')
    assert page.evaluate('requests') == []
    assert page.evaluate('downloads.length') == 1
    assert page.evaluate('downloads[0].blob.text()') == edited
    assert page.evaluate('downloads[0].blob.type') == 'text/markdown;charset=utf-8'
    assert page.evaluate('downloads[0].filename') == 'Draft-onepager.md'
    assert page.evaluate('generatedDocs[1].markdown') == 'Original'
    assert page.evaluate('generatedDocs[0]._editedMarkdown') is None


@pytest.mark.parametrize('format', ['docx', 'pdf', 'excel', 'hwp', 'pptx'])
def test_format_download_without_documents_never_regenerates(content_page, format):
    page = content_page
    _load_export_actions(page)
    page.evaluate("format => exportDocument(format, 'export-btn', '', format, format)", format)
    assert page.evaluate('requests') == []
    assert page.evaluate('downloads') == []


def test_markdown_download_without_request_payload_and_failure_preserves_draft(content_page):
    page = content_page
    _load_export_actions(page)
    page.evaluate("""() => {
        lastRequestPayload = null;
        generatedDocs = [{doc_type:'adr', markdown:'Original', _editedMarkdown:'Local draft'}];
        activeTab = 0; showDoc(0);
        window._triggerBrowserDownload = () => {throw new Error('Download blocked');};
    }""")
    page.click('#export-btn')
    assert page.evaluate('requests') == []
    assert page.evaluate('_getMarkdownContent()') == 'Local draft'
    assert page.evaluate("notices.some(([,level]) => level === 'error')")
    assert page.locator('#export-btn').is_enabled()


def test_markdown_download_with_no_active_document_does_not_export_stale_pane(content_page):
    page = content_page
    _load_export_actions(page)
    page.evaluate("document.getElementById('doc-pane').innerHTML='<div class=doc-pane-content>Old</div>'")
    page.click('#export-btn')
    assert page.evaluate('requests') == []
    assert page.evaluate('downloads') == []


def test_markdown_download_sanitizes_filename_without_changing_content(content_page):
    page = content_page
    _load_export_actions(page)
    page.evaluate("""() => {
        lastRequestPayload.title = 'Folder/문서:초안';
        generatedDocs = [{doc_type:'adr', markdown:'Exact\\r\\nsource\\n'}];
        activeTab = 0; showDoc(0);
    }""")
    page.click('#export-btn')
    assert page.evaluate('downloads[0].filename') == 'Folder_문서_초안-adr.md'
    assert page.evaluate('downloads[0].blob.text()') == 'Exact\r\nsource\n'


@pytest.mark.parametrize('status', [200, 503])
def test_format_download_only_converts_current_draft_and_never_falls_back(content_page, status):
    page = content_page
    _load_export_actions(page)
    page.evaluate("""status => {
        generatedDocs = [{doc_type:'adr', markdown:'Original', _editedMarkdown:''}];
        window.fetch = async (url, options) => {
            requests.push({url, body:JSON.parse(options.body)});
            return {ok:status===200,status,blob:async()=>new Blob(['converted']),json:async()=>({message:'Unavailable'})};
        };
    }""", status)
    page.evaluate("exportDocument('docx', 'export-btn', '', 'docx', 'Word')")
    requests = page.evaluate('requests')
    assert len(requests) == 1
    assert requests[0]['url'] == '/generate/export-edited'
    assert requests[0]['body']['docs'][0]['markdown'] == ''
    assert requests[0]['body']['generate_missing_visuals'] is False
    assert page.evaluate('downloads.length') == (1 if status == 200 else 0)
    assert page.evaluate('generatedDocs[0].markdown') == 'Original'
    assert page.evaluate('generatedDocs[0]._editedMarkdown') == ''


def _open_section_rewrite(page, markdown, index=0):
    _load_document_editor(page, section_rewrite=True)
    page.evaluate("""markdown => {
        generatedDocs = [{doc_type:'adr', markdown}]; activeTab = 0; showDoc(0);
        window.notices = [];
        window.showNotification = (...args) => notices.push(args);
        window.requests = [];
        window.fetch = (url, options) => new Promise(resolve => {
            requests.push({url, body:JSON.parse(options.body), resolve});
        });
    }""", markdown)
    page.locator('.section-rewrite-btn').nth(index).click()
    page.locator('#rewrite-instruction').fill('Make the section clearer')


@pytest.mark.parametrize('newline', ['\n', '\r\n'])
def test_section_rewrite_updates_draft_and_preserves_surrounding_source(content_page, newline):
    page = content_page
    prefix = '# Document\n\n## Same title\nFirst section\n\n## Same title\n'
    body = '\n| File | Value |\n| --- | --- |\n| C:\\docs | A \\| B |\n\n```text\n## Not a section\n```\n\n'
    suffix = '# Appendix\nUntouched\n'
    prefix, body, suffix = (text.replace('\n', newline) for text in (prefix, body, suffix))
    original = prefix + body + suffix
    _open_section_rewrite(page, original, index=1)
    page.click('#rewrite-confirm')
    request = page.evaluate('requests[0].body')
    assert request['current_content'] == body.strip()
    assert request['section_title'] == 'Same title'
    rewritten = 'New **content**\n\n| Key | Value |\n| --- | --- |\n| File | C:\\docs |'
    page.evaluate("text => requests[0].resolve({ok:true,json:async()=>({rewritten:text})})", rewritten)
    expected = prefix + rewritten.replace('\n', newline) + newline * 2 + suffix
    page.wait_for_function('!document.querySelector(".rewrite-modal-overlay")')
    assert page.evaluate('_getMarkdownContent()') == expected
    assert page.evaluate('buildEditedExportDocsPayload(generatedDocs)[0].markdown') == expected
    assert page.evaluate('buildGeneratedApprovalSource().docs[0].markdown') == expected
    assert page.evaluate('generatedDocs[0].markdown') == original
    page.click('#edit-btn')
    assert page.locator('#doc-pane textarea').input_value() == expected.replace('\r\n', '\n')


@pytest.mark.parametrize('change', ['cancel', 'edit', 'tab', 'source', 'auth', 'hidden'])
def test_section_rewrite_late_response_does_not_replace_current_draft(content_page, change):
    page = content_page
    original = '## Section\nOriginal body\n'
    _open_section_rewrite(page, original)
    page.click('#rewrite-confirm')
    if change == 'cancel':
        page.click('#rewrite-cancel')
    elif change == 'edit':
        page.click('#edit-btn')
        page.locator('#doc-pane textarea').fill('Manual draft')
    elif change == 'tab':
        page.evaluate("generatedDocs.push({doc_type:'onepager',markdown:'Other'}); activeTab=1; showDoc(1)")
    elif change == 'source':
        page.evaluate("generatedDocs[0]._editedMarkdown = 'Newer source'")
    elif change == 'auth':
        page.evaluate("getAuthHeaders = () => ({Authorization:'changed'})")
    else:
        page.evaluate("document.getElementById('doc-pane').style.display='none'")
    page.evaluate("requests[0].resolve({ok:true,json:async()=>({rewritten:'Late result'})})")
    page.wait_for_timeout(30)
    assert page.evaluate('generatedDocs[0]._editedMarkdown') == {
        'edit': 'Manual draft', 'source': 'Newer source'
    }.get(change)
    assert not page.evaluate("notices.some(([text]) => text.includes('✅'))")
    assert 'Late result' not in page.locator('#doc-pane').inner_text()


def test_section_rewrite_heading_text_is_not_interpreted_as_html(content_page):
    page = content_page
    _open_section_rewrite(page, '## <img src=x onerror=alert(1)>\nBody\n')
    assert page.locator('.rewrite-modal-overlay img').count() == 0
    assert '<img src=x onerror=alert(1)>' in page.locator('.rewrite-modal h4').inner_text()


@pytest.mark.parametrize('response', [None, '', '   ', 17])
def test_section_rewrite_invalid_response_preserves_source_and_instruction(content_page, response):
    page = content_page
    original = '## Section\nOriginal\n'
    _open_section_rewrite(page, original)
    page.click('#rewrite-confirm')
    page.evaluate("document.getElementById('rewrite-confirm').onclick()")
    assert page.evaluate('requests.length') == 1
    page.evaluate("value => requests[0].resolve({ok:true,json:async()=>({rewritten:value})})", response)
    page.wait_for_function("!document.getElementById('rewrite-confirm').disabled")
    assert page.evaluate('_getMarkdownContent()') == original
    assert page.locator('#rewrite-instruction').input_value() == 'Make the section clearer'


def test_section_rewrite_ignores_nested_quote_headings_and_handles_empty_last_section(content_page):
    page = content_page
    original = '## Parent\nBody\n\n> ## Quoted\n> Keep\n\n### Empty'
    _open_section_rewrite(page, original, index=1)
    assert page.locator('.section-rewrite-btn').count() == 2
    page.click('#rewrite-confirm')
    assert page.evaluate('requests[0].body.current_content') == ''
    page.evaluate("requests[0].resolve({ok:true,json:async()=>({rewritten:'Added body'})})")
    page.wait_for_function('!document.querySelector(".rewrite-modal-overlay")')
    assert page.evaluate('_getMarkdownContent()') == original + '\nAdded body\n'


def test_section_rewrite_uses_current_document_bundle_not_selected_card(content_page):
    page = content_page
    page.evaluate("lastRequestPayload.bundle_type = 'meeting_minutes'")
    _open_section_rewrite(page, '## Section\nBody\n')
    page.click('#rewrite-confirm')
    assert page.evaluate('requests[0].body.bundle_id') == 'meeting_minutes'


@pytest.mark.parametrize("edited", ["Current draft\n\n| Path | Value |\n| --- | --- |\n| C:\\docs | A \\| B |", ""])
def test_live_draft_reaches_document_actions_before_edit_completion(content_page, edited):
    page = content_page
    _load_document_editor(page)
    html = INDEX.read_text(encoding="utf-8")
    page.evaluate("""() => {
        document.body.insertAdjacentHTML('beforeend',
            '<button id="copy-btn">Copy</button><button id="summary-btn">Summary</button>'
            + '<button id="review-btn">Review</button>');
        generatedDocs = [
            {doc_type: 'adr', markdown: 'Other original'},
            {doc_type: 'onepager', markdown: 'Original', _editedMarkdown: 'Previous draft'}
        ];
        activeTab = 1; showDoc(1);
        Object.defineProperty(navigator, 'clipboard', {value: {
            writeText: async text => { window.copied = text; }
        }});
        window.requests = [];
        window.fetch = async (url, options) => {
            window.requests.push({url, body: JSON.parse(options.body)});
            return {ok: false, status: 503};
        };
        window.showNotification = () => {};
    }""")
    page.add_script_tag(content=html[
        html.index("  /* ── Copy"):html.index("  function _showSummaryModal(")
    ] + html[
        html.index("  /* ── AI Review"):html.index("  function _getMarkdownContent(")
    ])
    page.click('#edit-btn')
    page.locator('.doc-pane-content').fill(edited)
    page.click('#copy-btn')
    assert page.evaluate('window.copied') == edited
    for action in ('summary', 'review'):
        page.click(f'#{action}-btn')
    requests = page.evaluate('window.requests')
    assert requests == ([
        {"url": "/generate/summary", "body": {"content": edited, "max_sentences": 3, "audience": "일반"}},
        {"url": "/generate/review", "body": {"content": edited, "bundle_type": ""}},
    ] if edited else [])
    assert page.locator('.doc-pane-content').input_value() == edited
    assert page.evaluate('buildEditedExportDocsPayload(generatedDocs)[1].markdown') == edited
    assert page.evaluate('buildGeneratedApprovalSource().docs[1].markdown') == edited
    assert page.evaluate('_buildKnowledgePromotionState().docs') == (
        [{"doc_type": "adr", "markdown": "Other original"}]
        + ([{"doc_type": "onepager", "markdown": edited}] if edited else [])
    )
    assert page.evaluate('_getMarkdownContent()') == edited
    assert page.evaluate('generatedDocs[1].markdown') == 'Original'
    assert page.evaluate('generatedDocs[0]._editedMarkdown') is None
    assert page.evaluate('buildEditedExportDocsPayload(generatedDocs, {preferEdited: false})[1].markdown') == 'Original'
    page.click('#edit-btn')
    page.click('#copy-btn')
    assert page.evaluate('window.copied') == edited


@pytest.mark.parametrize("markdown", [
    "# Heading\n\nParagraph\n\n\nLast line",
    "| Name | Value |\n| --- | --- |\n| Draft | A \\| B |",
    "```text\nfirst\n\n  indented\n```",
])
def test_edit_mode_without_changes_preserves_original_markdown(content_page, markdown):
    page = content_page
    _load_document_editor(page)
    page.evaluate("""markdown => {
        generatedDocs = [{doc_type: 'adr', markdown}]; activeTab = 0; showDoc(0);
    }""", markdown)
    for _ in range(2):
        page.click('#edit-btn')
        assert page.locator('.doc-pane-content').input_value() == markdown
        page.click('#edit-btn')
        assert page.evaluate('generatedDocs[0]._editedMarkdown') == markdown
        assert page.evaluate('generatedDocs[0].markdown') == markdown


def test_editing_second_document_and_switching_tabs_preserves_each_draft(content_page):
    page = content_page
    _load_document_editor(page)
    page.evaluate("""() => {
        generatedDocs = [
            {doc_type: 'adr', markdown: 'First original'},
            {doc_type: 'onepager', markdown: 'Second original'}
        ];
        activeTab = 1;
        showDoc(1);
    }""")
    page.click('#edit-btn')
    page.locator('.doc-pane-content').fill('Second edited')
    page.click('#edit-btn')
    assert page.evaluate('generatedDocs[1]._editedMarkdown') == 'Second edited'
    assert page.evaluate('generatedDocs[0]._editedMarkdown') is None
    page.evaluate('activeTab = 0; showDoc(0)')
    assert page.locator('.doc-pane-content').inner_text() == 'First original'
    page.evaluate('activeTab = 1; showDoc(1)')
    assert page.locator('.doc-pane-content').inner_text() == 'Second edited'
    page.click('#edit-btn')
    page.locator('.doc-pane-content').fill('')
    page.evaluate('activeTab = 0; showDoc(0)')
    page.locator('.doc-pane-content').fill('First edited')
    page.click('#edit-btn')
    assert page.evaluate('generatedDocs.map(d => d._editedMarkdown)') == ['First edited', '']
    page.evaluate('activeTab = 1; showDoc(1)')
    assert page.locator('.doc-pane-content').inner_text() == ''
