"""Real local multi-session review lifecycle; no fulfilled or replaced API responses."""
from contextlib import ExitStack
from uuid import uuid4

import pytest
from playwright.sync_api import expect

from app.storage.generated_document_review_models import verify_generated_document_reviewed_package
from tests.e2e.test_main_flow import _generate_to_results


def _request(page, path, *, body=None):
    return page.evaluate("""async ({path,body}) => {
        const response=await fetch(path,{method:body===null?'GET':'POST',
            headers:{...getAuthHeaders(),'Content-Type':'application/json'},
            ...(body===null?{}:{body:JSON.stringify(body)})});
        return {status:response.status,body:await response.json()};
    }""", {'path': path, 'body': body})


def _open_project(page, project_id):
    page.evaluate("switchPage('project-page')")
    page.locator(f'[data-project-open="{project_id}"]').click()


@pytest.mark.parametrize('width', [1280, 390])
def test_real_review_assignment_completion_and_package(page, live_server, tmp_path, width):
    base_url = live_server['base_url']
    page.set_viewport_size({'width': width, 'height': 900})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.route('**/*', lambda route: route.continue_()
               if route.request.url.startswith(base_url + '/') else route.abort())
    suffix = uuid4().hex[:8]
    reviewer = 'reviewer_' + suffix
    outsider = 'outsider_' + suffix
    for username in (reviewer, outsider):
        created = _request(page, '/admin/users', body={
            'username': username, 'display_name': username, 'email': username + '@example.test',
            'password': 'ReviewLocal123!', 'role': 'member',
        })
        assert created['status'] == 200, created
    created = _request(page, '/projects', body={'name': 'Review lifecycle ' + suffix})
    assert created['status'] == 200, created
    project_id = created['body']['project_id']
    page.reload()
    page.locator('.bundle-card').first.click()
    page.select_option('#project-select', project_id)
    _generate_to_results(page, 'Local review evidence', 'Compare options with explicit review evidence')
    page.wait_for_function("""async id => {
        const r=await fetch('/projects/'+id,{headers:getAuthHeaders()});
        return (await r.json()).documents.length===1;
    }""", arg=project_id)
    original = _request(page, '/projects/' + project_id)['body']['documents'][0]
    _open_project(page, project_id)
    page.click('[data-project-detail-action="generated-document-review-create"]')
    page.select_option('[data-generated-document-review-reviewer]', reviewer)
    for checkbox in page.locator('[data-generated-document-review-format]').all():
        checkbox.set_checked(checkbox.get_attribute('value') == 'docx')
    with page.expect_response(lambda r: r.url.endswith('/generated-reviews')) as prepared:
        with page.expect_download() as packet:
            page.click('[data-generated-document-review-submit]')
    assert prepared.value.status == 200, prepared.value.text()
    packet_sha = prepared.value.headers['x-decisiondoc-packet-sha256']
    original_path = tmp_path / 'original-packet.zip'
    packet.value.save_as(original_path)
    complete_path = f'/projects/{project_id}/generated-document-reviews/{packet_sha}/complete'
    attempt = {'operation_id': str(uuid4()), 'decision': 'accepted', 'rationale': 'Unauthorized attempt'}
    # The existing API hides assignments from non-assignees with 404.
    assert _request(page, complete_path, body=attempt)['status'] == 404

    with ExitStack() as stack:
        sessions = {}
        for username in (reviewer, outsider):
            context = page.context.browser.new_context(viewport={'width': width, 'height': 900})
            stack.callback(context.close)
            context.add_init_script("localStorage.setItem('onboarding_done','1')")
            context.route('**/*', lambda route: route.continue_()
                          if route.request.url.startswith(base_url + '/') else route.abort())
            member = context.new_page()
            member.on('pageerror', lambda error: errors.append(str(error)))
            member.goto(base_url)
            member.fill('#login-username', username)
            member.fill('#login-password', 'ReviewLocal123!')
            with member.expect_response(lambda response: response.url.endswith('/auth/login')) as login:
                member.click('#login-btn')
            assert login.value.status == 200, login.value.text()
            # Reviewers need no document-generation AI assignment.
            expect(member.locator('#login-btn')).to_be_hidden()
            sessions[username] = member
        assert _request(sessions[outsider], complete_path, body=attempt)['status'] == 404
        pending = _request(page, f'/projects/{project_id}/generated-document-reviews')['body']['reviews'][0]
        assert pending['review_status'] == 'pending'
        member = sessions[reviewer]
        _open_project(member, project_id)
        member.click('[data-project-detail-action="generated-document-review-complete"]')
        member.fill('[data-generated-document-review-rationale]', 'Verified local source and document evidence.')
        with member.expect_response(lambda r: r.url.endswith('/complete')) as completed:
            with member.expect_download() as download:
                member.click('[data-generated-document-review-submit]')
        assert completed.value.status == 200, completed.value.text()
        assert completed.value.headers['x-decisiondoc-operational-approval'] == 'false'
        path = tmp_path / 'reviewed.zip'
        download.value.save_as(path)
        verified = verify_generated_document_reviewed_package(path.read_bytes())
        assert verified['receipt']['packet_sha256'] == packet_sha
        assert verified['receipt']['review_decision'] == 'accepted'
        from zipfile import ZipFile
        with ZipFile(path) as archive:
            assert archive.read('generated_document_review_packet.zip') == original_path.read_bytes()
        member.reload()
        _open_project(member, project_id)
        expect(member.locator('[data-project-detail-action="generated-document-review-complete"]')).to_have_count(0)
        with member.expect_download() as reopened:
            member.click('[data-project-detail-action="generated-document-reviewed-download"]')
        restored_path = tmp_path / 'restored-reviewed.zip'
        reopened.value.save_as(restored_path)
        assert restored_path.read_bytes() == path.read_bytes()
        member.screenshot(path=str(tmp_path / 'review-completed.png'))
        assert member.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert _request(page, '/projects/' + project_id)['body']['documents'][0]['doc_snapshot'] == original['doc_snapshot']
    assert not errors
