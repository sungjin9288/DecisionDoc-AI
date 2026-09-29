"""Deletion results must belong to the current style view and authenticated user."""
import pytest
from playwright.sync_api import expect

from tests.test_manual_style_ui import INDEX, style_page  # noqa: F401


@pytest.fixture
def deletion_page(style_page):  # noqa: F811
    page = style_page
    html = INDEX.read_text(encoding="utf-8")
    page.add_script_tag(content=html[
        html.index("  async function setDefaultStyle("):html.index("  function showCreateStyleModal(")
    ])
    page.evaluate("""() => {
        window.confirm = () => true;
        window.refreshCount = 0;
        window.deleteCount = 0;
        window.loadStyleProfiles = async () => { refreshCount++; };
        window.loadStyleDetail = async () => { refreshCount++; };
        window.fetch = async () => {
            deleteCount++;
            return new Promise((resolve, reject) => {window.finishDelete=resolve; window.failDelete=reject;});
        };
    }""")
    return page


CALLS = ["deleteStyleProfile('manual-ui')", "removeBundleOverride('manual-ui', 'tech_decision')",
         "removeStyleExample('manual-ui', 'example')"]


@pytest.mark.parametrize("call", CALLS)
@pytest.mark.parametrize("outcome", ["success", "http", "network", "profile", "auth", "rerender"])
def test_deletion_results_and_view_ownership(deletion_page, call, outcome):
    page = deletion_page
    page.evaluate("void " + call)
    if outcome == "profile":
        page.evaluate("document.getElementById('style-detail').dataset.styleDetailProfileId='other'")
    elif outcome == "auth":
        page.evaluate("window.testAuthHeaders={Authorization:'new-user'}")
    elif outcome == "rerender":
        page.evaluate("renderStyleDetail(profile)")
    if outcome == "network":
        page.evaluate("failDelete(new Error('Connection lost'))")
    else:
        page.evaluate("finishDelete({ok:" + ("false" if outcome == "http" else "true") + ",status:503})")
    page.wait_for_function("!document.getElementById('style-detail').hasAttribute('aria-busy')")
    if outcome == "success":
        assert page.evaluate("refreshCount") == 1
    else:
        assert page.evaluate("refreshCount") == 0
        expect(page.locator('#style-detail')).to_be_visible()
        assert page.evaluate("notifications.filter(n => n.type === 'success').length") == 0
        if outcome in ("http", "network"):
            assert page.evaluate("notifications.at(-1).type") == "error"
        else:
            assert page.evaluate("notifications.length") == 0


@pytest.mark.parametrize("call", CALLS)
def test_deletion_single_flight(deletion_page, call):
    page = deletion_page
    page.evaluate("void " + call)
    page.evaluate("void " + call)
    assert page.evaluate("deleteCount") == 1
    page.evaluate("finishDelete({ok:false,status:503})")
    page.wait_for_function("!document.getElementById('style-detail').hasAttribute('aria-busy')")
    page.evaluate("void " + call)
    assert page.evaluate("deleteCount") == 2
    page.evaluate("finishDelete({ok:false,status:503})")


@pytest.mark.parametrize("change", ["profile", "auth", "rerender"])
def test_late_list_refresh_keeps_current_view(style_page, change):  # noqa: F811
    page = style_page
    html = INDEX.read_text(encoding="utf-8")
    page.add_script_tag(content=html[
        html.index("  async function loadStyleProfiles("):html.index("  function renderStyleList(")
    ])
    page.evaluate("""() => {
        window.renderCount=0;
        window.renderStyleList=() => {renderCount++;};
        window.fetch=async()=>new Promise(resolve=>{window.finishList=resolve;});
        void loadStyleProfiles();
    }""")
    if change == "profile":
        page.evaluate("document.getElementById('style-detail').dataset.styleDetailProfileId='other'")
    elif change == "auth":
        page.evaluate("window.testAuthHeaders={Authorization:'new-user'}")
    else:
        page.evaluate("renderStyleDetail(profile)")
    page.evaluate("finishList({ok:true,json:async()=>({profiles:[]})})")
    assert page.evaluate("renderCount") == 0
