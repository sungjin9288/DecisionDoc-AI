from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright


INDEX = Path(__file__).resolve().parents[1] / "app/static/index.html"


@pytest.fixture
def notification_page():
    html = INDEX.read_text(encoding="utf-8")
    css = html.split("<style>", 1)[1].split("</style>", 1)[0]
    helpers = html[html.index("  function escapeHtml("):html.index("  function makeButtonAccessible(")]
    notify = html[html.index("  function showNotification("):html.index("  let _pendingProjectSelectorFocus")]
    post_download = html[html.index("  function showPostDownloadPrompt("):html.index("  function showFeedbackCard(")]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.route("**/*", lambda route: route.abort())
        page.set_content(f'<style>{css}</style><div id="notification-container" aria-live="polite"></div>')
        page.add_script_tag(content="""
            const $id = id => document.getElementById(id);
            window.notificationTimers = [];
            window.setTimeout = callback => notificationTimers.push(callback);
        """ + helpers + notify + post_download)
        yield page
        browser.close()


def test_notification_deduplicates_only_same_message_and_type(notification_page):
    page = notification_page
    page.evaluate("""() => {
        showNotification('Saved', 'success');
        showNotification('Saved', 'success');
        showNotification('Saved', 'error');
        showNotification('Other information');
    }""")
    expect(page.locator('.notification')).to_have_count(3)
    expect(page.get_by_role('alert')).to_have_text('Saved✕')
    assert page.evaluate('notificationTimers.length') == 3


@pytest.mark.parametrize('viewport', [
    {'width': 1280, 'height': 900},
    {'width': 390, 'height': 844},
    {'width': 320, 'height': 420},
])
def test_notification_stack_is_bounded_without_discarding_messages(notification_page, viewport):
    page = notification_page
    page.set_viewport_size(viewport)
    page.evaluate("""() => {
        for (let i = 0; i < 8; i++) showNotification(`${i}: ${'LongText'.repeat(20)}`);
    }""")
    expect(page.locator('.notification')).to_have_count(8)
    page.evaluate("Promise.all(document.getAnimations().map(animation => animation.finished))")
    bounds = page.locator('#notification-container').bounding_box()
    assert bounds is not None
    assert bounds['x'] >= 0
    assert bounds['x'] + bounds['width'] <= viewport['width']
    assert bounds['height'] <= min(320, viewport['height'] * 0.4) + 1
    assert page.locator('#notification-container').evaluate(
        "element => element.scrollHeight > element.clientHeight && element.scrollWidth <= element.clientWidth"
    )
    page.locator('.notification').last.get_by_role('button', name='닫기').click()
    expect(page.locator('.notification')).to_have_count(7)


def test_notification_text_and_expiry_do_not_affect_newer_message(notification_page):
    page = notification_page
    page.evaluate("showNotification('<img src=x onerror=alert(1)>', 'success')")
    expect(page.locator('.notification img')).to_have_count(0)
    expect(page.locator('.notification span')).to_have_text('<img src=x onerror=alert(1)>')
    page.get_by_role('button', name='닫기').click()
    page.evaluate("showNotification('New message', 'success'); notificationTimers[0]()")
    expect(page.locator('.notification span')).to_have_text('New message')
    page.evaluate('notificationTimers[1]()')
    expect(page.locator('.notification')).to_have_count(0)


def test_post_download_actions_remain_available_in_bounded_stack(notification_page, tmp_path):
    page = notification_page
    page.set_viewport_size({'width': 390, 'height': 420})
    page.evaluate("""() => {
        const compare = document.createElement('button');
        compare.id = 'compare-btn';
        compare.onclick = () => window.compared = true;
        document.body.appendChild(compare);
        showNotification('Saved', 'success');
        showNotification('Review required', 'error');
        showPostDownloadPrompt('Word');
    }""")
    page.evaluate("Promise.all(document.getAnimations().map(animation => animation.finished))")
    expect(page.locator('.notification')).to_have_count(3)
    prompt = page.locator('.notification').last
    expect(prompt.get_by_role('button')).to_have_count(4)
    page.screenshot(path=str(tmp_path / 'notification-actions.png'))
    prompt.get_by_role('button', name='비교하기').click()
    assert page.evaluate('window.compared') is True
    prompt.get_by_role('button', name='닫기').click()
    expect(page.get_by_role('alert')).to_have_text('Review required✕')
