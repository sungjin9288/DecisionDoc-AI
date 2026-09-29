from uuid import uuid4

import pytest
from playwright.sync_api import expect


@pytest.mark.parametrize('width', [390, 1280])
def test_knowledge_upload_reload_and_project_isolation(page, live_server, tmp_path, width):
    page.set_viewport_size({'width': width, 'height': 900})
    page.route('**/*', lambda route: route.continue_()
               if route.request.url.startswith(live_server['base_url'] + '/') else route.abort())
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    ids = page.evaluate("""async suffix => {
        const ids=[];
        for (const name of ['Knowledge A','Knowledge B']) {
            const response=await fetch('/projects',{method:'POST',
                headers:{...getAuthHeaders(),'Content-Type':'application/json'},
                body:JSON.stringify({name:name+' '+suffix})});
            if (!response.ok) throw new Error('Project setup failed');
            ids.push((await response.json()).project_id);
        }
        return ids;
    }""", uuid4().hex[:8])
    page.evaluate("switchPage('knowledge-page')")
    page.select_option('#knowledge-project-select', ids[0])
    page.locator('#knowledge-analyze-style').uncheck()
    marker = 'PROJECT_KNOWLEDGE_EVIDENCE: use only this project source.'
    with page.expect_response(lambda r: r.url.endswith('/documents') and r.request.method == 'POST') as uploaded:
        page.locator('#knowledge-file-input').set_input_files(
            {'name': 'source-' + 'a' * 80 + '.txt', 'mimeType': 'text/plain', 'buffer': marker.encode()})
    assert uploaded.value.status == 200
    expect(page.locator('#knowledge-doc-count')).to_have_text('1')
    expect(page.locator('#knowledge-upload-status')).to_contain_text('완료')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.locator('#knowledge-upload-status').scroll_into_view_if_needed()
    page.screenshot(path=str(tmp_path / 'knowledge-uploaded.png'))
    page.select_option('#knowledge-project-select', ids[1])
    expect(page.locator('#knowledge-doc-count')).to_have_text('0')
    expect(page.locator('#knowledge-upload-status')).to_be_hidden()
    page.reload()
    page.evaluate("switchPage('knowledge-page')")
    page.select_option('#knowledge-project-select', ids[0])
    expect(page.locator('#knowledge-doc-count')).to_have_text('1')
    context = page.evaluate("""async id => {
        const response=await fetch('/knowledge/'+id+'/context',{headers:getAuthHeaders()});
        if (!response.ok) throw new Error('Context read failed');
        return response.json();
    }""", ids[0])
    assert marker in context['context']
    assert not errors
