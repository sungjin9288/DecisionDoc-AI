"""Opportunity selection and pinned document flows in an isolated browser."""
from __future__ import annotations

from uuid import uuid4
from urllib.parse import urlsplit
from unittest.mock import Mock
import threading
import time

import pytest
import uvicorn
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


@pytest.fixture
def page(playwright, live_server):
    browser = playwright.chromium.launch()
    context = browser.new_context(service_workers='block')
    context.route('**/*', lambda route: route.continue_() if urlsplit(route.request.url).hostname == '127.0.0.1' else route.abort())
    context.add_init_script("localStorage.setItem('onboarding_done', '1');")
    page = context.new_page()
    page.goto(live_server['base_url'])
    page.fill('#login-username', live_server['auth']['username'])
    page.fill('#login-password', live_server['auth']['password'])
    page.click('#login-btn')
    page.wait_for_selector('.bundle-card')
    yield page
    context.close()
    browser.close()


def _project(page):
    return page.evaluate("""async () => {
        const response = await fetch('/projects', {
            method: 'POST', headers: {'Content-Type': 'application/json', ...getAuthHeaders()},
            body: JSON.stringify({name: 'Opportunity selection', fiscal_year: 2026}),
        });
        if (!response.ok) throw new Error(await response.text());
        return response.json();
    }""")


def _selection_fixture(page, project_id, *, recommended=False):
    ids = [str(uuid4()), str(uuid4())]
    state = {'active_decision_id': ids[0], 'selection_revision': 2}
    commands = []
    items = [dict(decision_id=value, decision_revision=1, title=f'Opportunity {label}',
                  source_id=label, source_kind='g2b') for value, label in zip(ids, ['A', 'B'])]
    details = {f"opportunities/{item['decision_id']}": item for item in items}

    def route(request):
        suffix = request.request.url.split('/procurement/', 1)[-1].split('?', 1)[0]
        if request.request.method == 'POST':
            commands.append((suffix, request.request.post_data_json))
        if suffix == 'opportunities':
            request.fulfill(json={**state, 'items': items, 'total': 2, 'limit': 100, 'offset': 0})
        elif suffix in details:
            item = details[suffix]
            request.fulfill(json={'decision_revision': 1, 'decision': {
                'decision_id': item['decision_id'], 'opportunity': item, 'notes': '',
                'hard_filters': [], 'missing_data': [],
                'recommendation': {'value': 'GO', 'rationale': 'Local fixture'} if recommended else None,
            }})
        elif suffix == 'selection':
            payload = request.request.post_data_json
            assert payload['expected_selection_revision'] == state['selection_revision']
            state.update(active_decision_id=payload['decision_id'],
                         selection_revision=state['selection_revision'] + 1)
            request.fulfill(json={'receipt': dict(state)})
        elif suffix == 'reviews':
            request.fulfill(json={'reviews': []})
        else:
            request.continue_()

    page.route(f'**/projects/{project_id}/procurement/**', route)
    return ids, state, commands


@pytest.mark.parametrize('subresource', ['requirements', 'requirements/sources'])
def test_selection_fixture_delegates_opportunity_subresources(subresource):
    page = Mock()
    ids, _, commands = _selection_fixture(page, 'project')
    handler = page.route.call_args.args[1]
    route = Mock()
    route.request.url = (
        f'http://127.0.0.1/projects/project/procurement/opportunities/{ids[0]}'
        f'/{subresource}?expected_decision_revision=1'
    )
    route.request.method = 'GET'

    handler(route)

    route.continue_.assert_called_once_with()
    route.fulfill.assert_not_called()
    assert commands == []


def test_select_only_changes_selection_and_survives_reload(page):
    project = _project(page)
    project_id = project['project_id']
    ids, state, commands = _selection_fixture(page, project_id)
    page.evaluate("switchPage('project-page')")
    page.evaluate('(id) => loadProjectDetail(id)', project_id)
    selector = page.get_by_role('combobox', name='공고', exact=True)
    expect(selector).to_have_value(ids[0])
    selector.select_option(ids[1])
    expect(page.locator('[data-active-decision]')).to_have_attribute('data-active-decision', ids[1])
    expect(selector).to_have_value(ids[1])
    assert state['active_decision_id'] == ids[1]
    assert [command[0] for command in commands] == ['selection']
    page.evaluate('(id) => loadProjectDetail(id)', project_id)
    expect(selector).to_have_value(ids[1])


def test_role_brief_resets_to_selected_opportunity_owner(page):
    project_id = _project(page)['project_id']
    result = page.evaluate("""id => {
        const project = {project_id: id, name: 'Role scope', documents: [{
            doc_id: 'a-doc', bundle_id: 'bid_decision_kr', approval_status: 'approved',
            source_procurement_binding: {decision_id: 'a'}, docs: [],
        }]};
        const decision = decision_id => ({decision_id, opportunity: {title: decision_id},
            recommendation: {value: 'GO'}, missing_data: ['Owner'], hard_filters: []});
        const options = {procurementEnabled: true, procurementSelection: {
            items: [], active_decision_id: 'a', selection_revision: 1,
        }};
        renderProjectDetail(project, decision('a'), options);
        _activeProcurementRoleBrief = 'executive';
        renderProjectDetail(project, decision('b'), {...options, procurementSelection: {
            ...options.procurementSelection, active_decision_id: 'b', selection_revision: 2,
        }});
        return {role: _activeProcurementRoleBrief, expected: getProcurementOwnerState(
            project, decision('b'), []).currentOwner};
    }""", project_id)
    assert result['expected'] == 'delivery_pm'
    assert result['role'] == result['expected']


def test_project_reads_never_fall_back_to_service_worker_cache(page, live_server):
    script = page.request.get(live_server['base_url'] + '/sw.js').text()
    intercepted = page.evaluate("""script => {
        const handlers = {};
        const worker = {addEventListener: (name, handler) => handlers[name] = handler};
        new Function('self', 'location', 'caches', script)(worker, location, {});
        return ['/projects', '/projects/p', '/projects/p/procurement/opportunities',
                '/projects/p/decision-council'].map(path => {
            let intercepted = false;
            handlers.fetch({request: new Request(location.origin + path),
                respondWith: () => {intercepted = true;}});
            return intercepted;
        });
    }""", script)
    assert intercepted == [False] * 4


def test_generation_completion_from_previous_selection_does_not_replace_screen(page):
    project_id = _project(page)['project_id']
    ids, _, _ = _selection_fixture(page, project_id, recommended=True)
    page.evaluate("switchPage('project-page')")
    page.evaluate('(id) => loadProjectDetail(id)', project_id)
    pending = []
    page.route('**/generate/stream', lambda route: pending.append(route))
    page.evaluate("""() => {
        lastMeta = {request_id: 'unchanged'};
        const generate = generateProjectProcurementBundle;
        generateProjectProcurementBundle = (...args) => window.pendingGeneration = generate(...args);
    }""")
    page.locator('[data-procurement-bundle="bid_decision_kr"]').click()
    page.wait_for_function("() => document.querySelector('[data-procurement-bundle=bid_decision_kr]').disabled")
    page.get_by_role('combobox', name='공고', exact=True).select_option(ids[1])
    expect(page.locator('[data-active-decision]')).to_have_attribute('data-active-decision', ids[1])
    assert len(pending) == 1
    assert pending[0].request.post_data_json['procurement_decision_id'] == ids[0]
    assert pending[0].request.post_data_json['expected_procurement_decision_revision'] == 1
    pending[0].fulfill(content_type='text/event-stream', body='event: complete\ndata: {"request_id":"old-a","docs":[]}\n\n')
    page.evaluate('window.pendingGeneration')
    assert page.evaluate('lastMeta.request_id') == 'unchanged'
    expect(page.locator('[data-active-decision]')).to_have_attribute('data-active-decision', ids[1])


@pytest.mark.parametrize('change', ['selection', 'page'])
def test_council_refresh_does_not_announce_completion_on_another_selection(page, change):
    project_id = _project(page)['project_id']
    ids, _, _ = _selection_fixture(page, project_id, recommended=True)
    page.evaluate("switchPage('project-page')")
    page.evaluate('(id) => loadProjectDetail(id)', project_id)
    page.route(f'**/projects/{project_id}/decision-council/run?*', lambda route: route.fulfill(json={'operation': 'created'}))
    page.evaluate("""id => {
        window.councilStatuses = [];
        setDecisionCouncilActionStatus = (message, status) => councilStatuses.push(status);
        loadProjectDetail = async () => {
            _projectDetailLoadId += 1;
            await new Promise(resolve => window.finishCouncilRefresh = resolve);
        };
        document.getElementById('project-decision-council-goal').value = 'Local review';
        window.pendingCouncil = runProjectDecisionCouncil(id);
    }""", project_id)
    page.wait_for_function('() => typeof window.finishCouncilRefresh === "function"')
    page.evaluate("""({id, change}) => {
        if (change === 'selection') {
            _currentProjectDetail.procurementDecision.decision_id = id;
            _projectDetailLoadId += 1;
        } else {
            switchPage('generate');
        }
        window.finishCouncilRefresh();
    }""", {'id': ids[1], 'change': change})
    page.evaluate('window.pendingCouncil')
    assert 'success' not in page.evaluate('window.councilStatuses')


def test_auth_change_discards_generation_completion(page):
    project_id = _project(page)['project_id']
    _selection_fixture(page, project_id, recommended=True)
    page.evaluate("switchPage('project-page')")
    page.evaluate('(id) => loadProjectDetail(id)', project_id)
    pending = []
    page.route('**/generate/stream', lambda route: pending.append(route))
    page.evaluate("""id => {
        lastMeta = {request_id: 'current-session'};
        window.pendingGeneration = generateProjectProcurementBundle(id, 'bid_decision_kr');
    }""", project_id)
    page.wait_for_function("() => document.querySelector('[data-procurement-bundle=bid_decision_kr]').disabled")
    assert len(pending) == 1
    page.evaluate('_authSessionRevision += 1')
    pending[0].fulfill(content_type='text/event-stream', body='event: complete\ndata: {"request_id":"old-session"}\n\n')
    page.evaluate('window.pendingGeneration')
    assert page.evaluate('lastMeta.request_id') == 'current-session'


def test_selection_change_during_evaluation_does_not_start_recommendation(page):
    project_id = _project(page)['project_id']
    ids, _, commands = _selection_fixture(page, project_id)
    page.evaluate("switchPage('project-page')")
    page.evaluate('(id) => loadProjectDetail(id)', project_id)
    pending = []
    page.route(f'**/opportunities/{ids[0]}/evaluate', lambda route: pending.append(route))
    page.evaluate("""() => {
        const refresh = refreshProjectProcurementDecision;
        refreshProjectProcurementDecision = (...args) => window.pendingEvaluation = refresh(...args);
    }""")
    page.locator('#project-procurement-refresh-submit').click()
    page.get_by_role('combobox', name='공고', exact=True).select_option(ids[1])
    expect(page.locator('[data-active-decision]')).to_have_attribute('data-active-decision', ids[1])
    assert len(pending) == 1
    pending[0].fulfill(json={'receipt': {'decision_revision': 2}})
    page.evaluate('window.pendingEvaluation')
    assert [command[0] for command in commands] == ['selection']


@pytest.fixture
def scoped_server(tmp_path, monkeypatch):
    from app.main import create_app
    from app.services.g2b_collector import G2BAnnouncement
    from tests.e2e.conftest import _bootstrap_e2e_user, _reserve_local_port

    for key, value in {
        'DATA_DIR': str(tmp_path), 'DECISIONDOC_PROVIDER': 'mock',
        'DECISIONDOC_STORAGE': 'local', 'DECISIONDOC_ENV': 'dev',
        'DECISIONDOC_PROCUREMENT_COPILOT_ENABLED': '1',
        'DECISIONDOC_API_KEYS': 'scoped-e2e-key',
        'JWT_SECRET_KEY': 'scoped-e2e-secret-key-32chars-minimum',
    }.items():
        monkeypatch.setenv(key, value)

    calls = []

    async def collect(*, url_or_number, api_key):
        calls.append(url_or_number)
        return G2BAnnouncement(
            bid_number=url_or_number, title=f'공고 {url_or_number}', issuer='Local fixture',
            budget='100000000', announcement_date='2026-09-21', deadline='2030-01-01',
            bid_type='일반경쟁', category='용역', detail_url='', attachments=[],
            raw_text=f'공고 {url_or_number}: 문서 관리 시스템 구축', source='api',
        )

    monkeypatch.setattr('app.services.g2b_collector.fetch_announcement_detail', collect)
    app = create_app(procurement_multi_opportunity_enabled=True)
    port = _reserve_local_port()
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port,
                                           log_level='error', ws='none'))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.05)
        assert server.started
        base_url = f'http://127.0.0.1:{port}'
        auth = _bootstrap_e2e_user(base_url)
        yield {'base_url': base_url, 'auth': auth, 'app': app, 'calls': calls}
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        assert not thread.is_alive()


@pytest.mark.parametrize('viewport', [{'width': 1440, 'height': 1000}, {'width': 390, 'height': 844}], ids=['desktop', 'mobile'])
def test_real_local_opportunity_lifecycle(playwright, scoped_server, viewport, tmp_path):
    from app.services.generation_export_packet import verify_generation_export_packet

    browser = playwright.chromium.launch()
    context = browser.new_context(viewport=viewport, service_workers='block', accept_downloads=True)
    context.route('**/*', lambda route: route.continue_() if urlsplit(route.request.url).hostname == '127.0.0.1' else route.abort())
    context.add_init_script("localStorage.setItem('onboarding_done', '1');")
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    try:
        page.goto(scoped_server['base_url'])
        page.fill('#login-username', scoped_server['auth']['username'])
        page.fill('#login-password', scoped_server['auth']['password'])
        page.click('#login-btn')
        page.wait_for_selector('.bundle-card')
        project_id = _project(page)['project_id']
        page.evaluate("switchPage('project-page')")
        page.evaluate('(id) => loadProjectDetail(id)', project_id)
        selector = page.get_by_role('combobox', name='공고', exact=True)
        expect(selector).to_be_disabled()
        for source in ['A', 'B']:
            page.fill('#project-procurement-url-input', source)
            page.locator('#project-procurement-import-submit').click()
            expect(selector.locator('option')).to_have_count(1 if source == 'A' else 2)
            expect(selector).to_be_enabled()
            page.wait_for_function('(title) => _currentProjectDetail?.procurementDecision?.opportunity?.title === title', arg=f'공고 {source}')
        assert scoped_server['calls'] == ['A', 'B']
        ids = selector.locator('option').evaluate_all('(options) => options.map(option => option.value)')
        selector.select_option(ids[0])
        expect(page.locator('[data-active-decision]')).to_have_attribute('data-active-decision', ids[0])
        page.locator('#project-procurement-refresh-submit').click()
        page.wait_for_function('() => Boolean(_currentProjectDetail?.procurementDecision?.recommendation)')
        revision = page.evaluate('_currentProjectDetail.procurementDecisionRevision')
        assert revision == 3
        page.locator('#project-decision-council-run-submit').click()
        page.wait_for_function('() => Boolean(_currentProjectDetail?.decisionCouncilSession?.session_id)')
        page.fill('#project-procurement-reviewer-input', scoped_server['auth']['username'])
        with page.expect_download() as download:
            page.locator('#project-procurement-review-packet-submit').click()
        assert download.value.failure() is None
        complete = page.locator('[data-project-detail-action="procurement-review-complete"]')
        expect(complete).to_be_visible()
        page.locator('[id^="procurement-review-decision-"]').select_option('accepted')
        page.locator('[id^="procurement-review-rationale-"]').fill('로컬 출처와 내용을 검토했습니다.')
        page.once('dialog', lambda dialog: dialog.accept())
        with page.expect_download() as reviewed:
            with page.expect_response(lambda response: response.url.endswith('/complete')) as completed_response:
                complete.click()
            assert completed_response.value.status == 200, completed_response.value.text()
        assert reviewed.value.failure() is None
        page.wait_for_function("() => _currentProjectDetail?.procurementReviews?.some(review => review.review_status === 'completed')")
        page.locator('[data-procurement-bundle="bid_decision_kr"]').click()
        page.wait_for_function('() => Boolean(lastMeta?.request_id)', timeout=30000)
        page.wait_for_function('() => (_currentProjectDetail?.project?.documents || []).length > 0')
        documents = page.evaluate('_currentProjectDetail.project.documents')
        assert all(doc['source_procurement_binding']['decision_id'] == ids[0] for doc in documents)
        request_id = documents[0]['request_id']
        requirements_path = f'/projects/{project_id}/procurement/opportunities/{ids[1]}/requirements'
        with page.expect_response(lambda response: (
            urlsplit(response.url).path == requirements_path
            and response.request.method == 'GET'
        )) as selected_requirements:
            selector.select_option(ids[1])
        assert selected_requirements.value.status == 200, selected_requirements.value.text()
        expect(page.locator('[data-active-decision]')).to_have_attribute('data-active-decision', ids[1])
        assert page.evaluate('_currentProjectDetail.procurementReviews') == []
        assert page.evaluate('_currentProjectDetail.decisionCouncilSession') is None
        expect(page.locator('[data-document-opportunity]').first).to_have_attribute('data-document-opportunity', ids[0])
        page.reload()
        page.wait_for_selector('.bundle-card')
        page.evaluate("switchPage('project-page')")
        page.evaluate('(id) => loadProjectDetail(id)', project_id)
        expect(selector).to_have_value(ids[1])
        token = page.evaluate("localStorage.getItem('dd_access_token')")
        response = page.request.get(scoped_server['base_url'] + f'/generate/export-zip?request_id={request_id}&formats=docx', headers={'Authorization': f'Bearer {token}'})
        assert response.status == 200, response.text()
        verified = verify_generation_export_packet(response.body())
        assert verified['verified'] is True
        assert verified['source_procurement_binding']['decision_id'] == ids[0]
        area = page.locator('#project-decision-area')
        area.evaluate("element => element.scrollIntoView({block: 'start'})")
        box = selector.bounding_box()
        assert box and box['x'] >= 0 and box['x'] + box['width'] <= viewport['width']
        output = tmp_path / 'artifacts'
        output.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(output / f'procurement-step6-{viewport["width"]}.png'))
        page.locator('#project-documents-heading').evaluate("element => element.scrollIntoView({block: 'start'})")
        page.screenshot(path=str(output / f'procurement-step6-documents-{viewport["width"]}.png'))
        source_badge = page.locator('[data-document-opportunity]').first.bounding_box()
        assert source_badge and source_badge['height'] <= 32
        assert errors == []
    finally:
        context.close()
        browser.close()
