"""Local uploaded knowledge is selected by project, never by another project."""
from tests.test_generation_style_selection import CapturingMockProvider, _make_client


def test_upload_preview_generation_and_removal(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    provider = CapturingMockProvider()
    client.app.state.service.provider_factory = lambda: provider

    def forbidden(*args, **kwargs):
        raise AssertionError('Text knowledge must not invoke analysis or OCR providers')

    monkeypatch.setattr('app.routers.knowledge.get_provider_for_capability', forbidden)
    ids = [client.post('/projects', json={'name': name}).json()['project_id'] for name in ('A', 'B')]
    docs = []
    for project_id, marker in zip(ids, ('PROJECT_A_SOURCE', 'PROJECT_B_SOURCE'), strict=True):
        uploaded = client.post(f'/knowledge/{project_id}/documents',
                               files={'file': ('source.txt', marker.encode(), 'text/plain')})
        assert uploaded.status_code == 200, uploaded.text
        docs.append(uploaded.json()['doc_id'])
    preview = client.get(f'/knowledge/{ids[0]}/context')
    assert preview.status_code == 200
    assert 'PROJECT_A_SOURCE' in preview.json()['context']
    assert 'PROJECT_B_SOURCE' not in preview.json()['context']
    request = {'title': 'Knowledge reuse', 'goal': 'Compare project source evidence', 'project_id': ids[0]}
    generated = client.post('/generate', json=request)
    assert generated.status_code == 200, generated.text
    assert 'PROJECT_A_SOURCE' in provider.prompts[-1]
    assert 'PROJECT_B_SOURCE' not in provider.prompts[-1]
    removed = client.delete(f'/knowledge/{ids[0]}/documents/{docs[0]}')
    assert removed.status_code == 200
    generated = client.post('/generate', json=request)
    assert generated.status_code == 200, generated.text
    assert 'PROJECT_A_SOURCE' not in provider.prompts[-1]
    assert client.get(f'/knowledge/{ids[1]}/documents').json()['count'] == 1
