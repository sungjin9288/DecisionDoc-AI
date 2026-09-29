"""Default-style mutation and detail reads must retain view ownership."""
import pytest
from playwright.sync_api import expect

from tests.test_manual_style_ui import INDEX, style_page  # noqa: F401


@pytest.mark.parametrize('outcome', ['success', 'http', 'network', 'auth', 'profile'])
def test_default_setting_single_flight_and_stale_results(style_page, outcome):  # noqa: F811
    page = style_page
    html = INDEX.read_text(encoding='utf-8')
    page.add_script_tag(content=html[html.index('  async function setDefaultStyle('):html.index('  async function deleteStyleProfile(')])
    page.evaluate("""() => {
        renderStyleDetail({...profile,is_default:false});
        window.calls=0; window.refreshes=0;
        window.loadStyleDetail=async()=>{refreshes++;};
        window.fetch=async()=>{
            calls++;
            return new Promise((resolve,reject)=>{window.finishDefault=resolve;window.failDefault=reject;});
        };
        void setDefaultStyle('manual-ui');
        void setDefaultStyle('manual-ui');
    }""")
    assert page.evaluate('calls') == 1
    if outcome == 'auth':
        page.evaluate("window.testAuthHeaders={Authorization:'new-user'}")
    elif outcome == 'profile':
        page.evaluate("renderStyleDetail({...profile,profile_id:'other',name:'Other',is_default:false})")
    if outcome == 'network':
        page.evaluate("failDefault(new Error('Lost response'))")
    else:
        page.evaluate("finishDefault({ok:" + ('false' if outcome == 'http' else 'true') + ",text:async()=> 'Unavailable'})")
    expect(page.locator('[data-style-detail-action="set-default"]')).to_be_enabled()
    assert page.evaluate('refreshes') == (1 if outcome == 'success' else 0)
    if outcome in ('profile', 'auth'):
        assert page.evaluate('notifications.length') == 0
    else:
        assert page.evaluate('notifications.at(-1).type') == ('success' if outcome == 'success' else 'error')


@pytest.mark.parametrize('change', ['auth', 'profile', 'back', 'mismatched_response'])
def test_detail_read_does_not_replace_current_view(style_page, change):  # noqa: F811
    page = style_page
    page.evaluate("""() => {
        window.fetch=async()=>new Promise(resolve=>{window.finishDetail=resolve;});
        void loadStyleDetail('manual-ui');
    }""")
    if change == 'auth':
        page.evaluate("window.testAuthHeaders={Authorization:'other'}")
    elif change == 'profile':
        page.evaluate("renderStyleDetail({...profile,profile_id:'other',name:'Other'})")
    elif change == 'back':
        page.evaluate("document.getElementById('style-detail').dataset.styleDetailProfileId=''")
    page.evaluate("finishDetail({ok:true,json:async()=>({...profile,name:'Late response',profile_id:" + ("'wrong'" if change == 'mismatched_response' else "'manual-ui'") + "})})")
    expect(page.locator('#style-detail h3')).not_to_have_text('Late response')


def test_newest_detail_request_wins(style_page):  # noqa: F811
    page = style_page
    page.evaluate("""() => {
        window.reads=[];
        window.fetch=async()=>new Promise(resolve=>reads.push(resolve));
        void loadStyleDetail('old');
        void loadStyleDetail('new');
        reads[1]({ok:true,json:async()=>({...profile,profile_id:'new',name:'Newest'})});
    }""")
    expect(page.locator('#style-detail h3')).to_have_text('Newest')
    page.evaluate("reads[0]({ok:true,json:async()=>({...profile,profile_id:'old',name:'Old'})})")
    expect(page.locator('#style-detail h3')).to_have_text('Newest')
