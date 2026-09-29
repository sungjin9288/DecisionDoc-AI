"""Knowledge uploads must stay bound to the initiating project and auth context."""
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

INDEX = Path(__file__).resolve().parents[1] / 'app/static/index.html'


@pytest.fixture
def knowledge_page():
    html = INDEX.read_text(encoding='utf-8')
    functions = html[html.index('  async function knowledgeUploadFiles('):html.index('  async function deleteKnowledgeDoc(')]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.route('**/*', lambda route: route.abort())
        page.set_content('<div id="knowledge-upload-status"></div><div id="knowledge-doc-list"></div>'
                         '<span id="knowledge-doc-count">7</span><button id="knowledge-file-pick-btn">Upload</button>'
                         '<input id="knowledge-file-input" type="file">')
        page.add_script_tag(content="""
            let _knowledgeCurrentProject='project-a';
            let auth={Authorization:'user-a'};
            const getAuthHeaders=()=>({...auth});
            const $id=id=>document.getElementById(id);
            const escapeHtml=value=>String(value);
            const _knowledgeFileIcon=()=>'';
            const notifications=[];
            const showNotification=(...args)=>notifications.push(args);
            const refreshes=[];
            const loadKnowledgeDocs=async id=>refreshes.push(id);
            const requests=[]; const replies=[]; const timers=[];
            window.setTimeout=callback=>timers.push(callback);
            window.fetch=async (url,options)=>{
                requests.push({url,headers:options.headers});
                return new Promise(resolve=>replies.push(resolve));
            };
            const files=[new File(['One'],'one.txt'),new File(['Two'],'two.txt')];
        """ + functions)
        yield page
        browser.close()


@pytest.mark.parametrize('change', ['project', 'auth'])
def test_switch_stops_remaining_uploads(knowledge_page, change):
    page = knowledge_page
    page.evaluate('void knowledgeUploadFiles(files)')
    page.evaluate("_knowledgeCurrentProject='project-b'" if change == 'project' else "auth={Authorization:'user-b'}")
    page.evaluate('replies[0]({ok:true})')
    assert page.evaluate('requests.length') == 1
    page.evaluate('timers.forEach(callback=>callback())')
    assert page.evaluate('refreshes') == []
    assert page.evaluate('requests[0].url') == '/knowledge/project-a/documents'
    assert page.evaluate('requests[0].headers.Authorization') == 'user-a'


def test_batch_is_single_flight_and_refreshes_original_project(knowledge_page):
    page = knowledge_page
    page.evaluate('void knowledgeUploadFiles(files); void knowledgeUploadFiles(files)')
    assert page.evaluate('requests.length') == 1
    page.evaluate('replies[0]({ok:true})')
    assert page.evaluate('requests.length') == 2
    page.evaluate('replies[1]({ok:false,json:async()=>({detail:"Invalid file"})})')
    page.evaluate('timers.forEach(callback=>callback())')
    assert page.evaluate('refreshes') == ['project-a']
    assert 'Invalid file' in page.locator('#knowledge-upload-status').inner_text()


@pytest.mark.parametrize('change', ['project', 'auth'])
def test_late_document_list_does_not_replace_current_project(knowledge_page, change):
    page = knowledge_page
    html = INDEX.read_text(encoding='utf-8')
    # Replace the upload fixture's refresh stub only for the read-response test.
    source = html[html.index('  async function loadKnowledgeDocs('):html.index('  function wireKnowledgeDocActions(')]
    page.add_script_tag(content=source.replace('async function loadKnowledgeDocs(', 'async function readKnowledgeDocs('))
    page.evaluate("void readKnowledgeDocs('project-a')")
    page.evaluate("_knowledgeCurrentProject='project-b'" if change == 'project' else "auth={Authorization:'user-b'}")
    page.evaluate("document.getElementById('knowledge-doc-list').textContent='Current view'")
    page.evaluate('replies[0]({ok:true,json:async()=>({documents:[]})})')
    assert page.locator('#knowledge-doc-list').inner_text() == 'Current view'
    assert page.locator('#knowledge-doc-count').inner_text() == '7'
