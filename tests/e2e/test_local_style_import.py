import pytest
from playwright.sync_api import expect


@pytest.mark.parametrize("width", [390, 1280])
def test_local_style_import_reload(page, live_server, tmp_path, width):
    page.set_viewport_size({"width": width, "height": 900})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.route("**/*", lambda route: route.continue_()
               if route.request.url.startswith(live_server["base_url"] + "/") else route.abort())
    page.locator('.bundle-card').first.click()
    page.click('#style-manage-btn')
    page.click('#style-create-btn')
    page.fill('#new-style-name', 'Local source import')
    with page.expect_response(lambda r: r.url.endswith('/styles') and r.request.method == 'POST') as created:
        page.click('[data-style-create-submit]')
    profile_id = created.value.json()['profile_id']
    marker = 'Source-grounded example for document generation.'
    with page.expect_file_chooser() as chooser:
        page.click('[data-style-detail-action="import-file"]')
    with page.expect_response(lambda r: r.url.endswith('/import-examples')) as imported:
        chooser.value.set_files({"name": "source.txt", "mimeType": "text/plain", "buffer": marker.encode()})
    assert imported.value.status == 200
    assert imported.value.json()['provider_calls'] == 0
    expect(page.locator('.style-example-item')).to_contain_text('source.txt')
    page.reload()
    page.locator('.bundle-card').first.click()
    page.click('#style-manage-btn')
    page.locator(f'[data-style-profile-id="{profile_id}"]').click()
    page.locator('.style-example-item summary').click()
    expect(page.locator('.sample-sentence')).to_contain_text(marker)
    page.locator('.style-example-item').scroll_into_view_if_needed()
    page.screenshot(path=str(tmp_path / 'local-style-import.png'))
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    with page.expect_response(lambda r: '/examples/' in r.url and r.request.method == 'DELETE') as removed:
        page.click('[data-style-detail-action="remove-example"]')
    assert removed.value.status == 200
    expect(page.locator('.style-example-item')).to_have_count(0)
    page.reload()
    page.locator('.bundle-card').first.click()
    page.click('#style-manage-btn')
    page.locator(f'[data-style-profile-id="{profile_id}"]').click()
    expect(page.locator('.style-example-item')).to_have_count(0)
    page.once('dialog', lambda dialog: dialog.accept())
    with page.expect_response(lambda r: r.url.endswith('/styles/' + profile_id) and r.request.method == 'DELETE') as deleted:
        page.click('[data-style-detail-action="delete"]')
    assert deleted.value.status == 200
    expect(page.locator(f'[data-style-profile-id="{profile_id}"]')).to_have_count(0)
    page.reload()
    page.locator('.bundle-card').first.click()
    page.click('#style-manage-btn')
    expect(page.locator(f'[data-style-profile-id="{profile_id}"]')).to_have_count(0)
    assert not errors


@pytest.mark.parametrize('width', [390, 1280])
def test_default_style_setting_persists(page, live_server, width):
    page.set_viewport_size({'width': width, 'height': 900})
    page.route('**/*', lambda route: route.continue_()
               if route.request.url.startswith(live_server['base_url'] + '/') else route.abort())
    profile_id = page.evaluate("""async () => {
        const headers={...getAuthHeaders(),'Content-Type':'application/json'};
        const created=await fetch('/styles',{method:'POST',headers,body:JSON.stringify({name:'Default target'})});
        if (!created.ok) throw new Error('Create failed');
        const target=await created.json();
        const other=await fetch('/styles',{method:'POST',headers,body:JSON.stringify({name:'Previous default'})});
        if (!other.ok) throw new Error('Create failed');
        const otherId=(await other.json()).profile_id;
        const configured=await fetch('/styles/'+otherId+'/set-default',{method:'POST',headers});
        if (!configured.ok) throw new Error('Setup failed');
        return target.profile_id;
    }""")
    page.locator('.bundle-card').first.click()
    page.click('#style-manage-btn')
    page.locator(f'[data-style-profile-id="{profile_id}"]').click()
    with page.expect_response(lambda response: response.url.endswith('/set-default')) as configured:
        page.click('[data-style-detail-action="set-default"]')
    assert configured.value.status == 200
    expect(page.locator('[data-style-detail-action="set-default"]')).to_have_count(0)
    page.reload()
    page.locator('.bundle-card').first.click()
    page.click('#style-manage-btn')
    expect(page.locator(f'[data-style-profile-id="{profile_id}"] .default-badge')).to_be_visible()
    page.click('#style-return-btn')
    expect(page.locator(f'#inline-style-select option[value="{profile_id}"]')).to_contain_text('★')
