"""Dialog panels must be opaque so page text never shows through them.

The shared ``--surface`` token is translucent for page cards. A dialog panel
that uses it lets the page behind it bleed through its form fields.
"""

import re
from pathlib import Path

import pytest

from tests.browser_pages import isolated_page

INDEX = Path(__file__).resolve().parents[1] / "app" / "static" / "index.html"
STATIC_MODAL_IDS = (
    "create-location-modal",
    "location-key-modal",
    "location-users-modal",
    "location-user-create-modal",
    "location-user-edit-modal",
    "location-procurement-modal",
)
CLASS_PANELS = {
    "modal-box": '<div class="modal-overlay"><div class="modal-box" data-panel>내용</div></div>',
    "approval-modal-box": '<div class="approval-modal-box" data-panel>내용</div>',
    "generated-document-review-dialog": '<section class="generated-document-review-dialog" data-panel>내용</section>',
    "user-menu": '<div style="position:relative"><div class="user-menu" data-panel>메뉴</div></div>',
}

_ALPHA_SCRIPT = """element => {
  const match = getComputedStyle(element).backgroundColor.match(/rgba?\\(([^)]+)\\)/);
  const parts = match ? match[1].split(',').map(part => part.trim()) : [];
  return parts.length === 4 ? Number(parts[3]) : (parts.length === 3 ? 1 : 0);
}"""


@pytest.fixture(scope="module")
def page_markup():
    html = INDEX.read_text(encoding="utf-8")
    styles = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", html, re.S))
    body = html[html.index("<body"):html.index("</body>")]
    body = re.sub(r"<script\b[^>]*>.*?</script>", "", body, flags=re.S)
    return html, f"<style>{styles}</style>{body[body.index('>') + 1:]}"


@pytest.fixture
def modal_page(browser, page_markup):
    with isolated_page(browser, viewport={"width": 1280, "height": 900}) as page:
        page.route("**/*", lambda route: route.abort())
        page.set_content(page_markup[1])
        yield page


@pytest.mark.parametrize("modal_id", STATIC_MODAL_IDS)
def test_static_dialog_panels_are_opaque(modal_page, modal_id):
    alpha = modal_page.evaluate(
        """([modalId, script]) => {
          const overlay = document.getElementById(modalId);
          document.body.appendChild(overlay);
          overlay.style.display = 'flex';
          return (new Function('return ' + script))()(overlay.firstElementChild);
        }""",
        [modal_id, _ALPHA_SCRIPT],
    )
    assert alpha == 1, modal_id


@pytest.mark.parametrize("name", sorted(CLASS_PANELS))
def test_class_dialog_panels_are_opaque(modal_page, name):
    modal_page.evaluate("markup => document.body.insertAdjacentHTML('beforeend', markup)", CLASS_PANELS[name])
    panel = modal_page.locator("[data-panel]").last
    assert panel.evaluate(_ALPHA_SCRIPT) == 1, name


def test_shared_modal_box_has_padding_on_desktop(modal_page):
    modal_page.evaluate("markup => document.body.insertAdjacentHTML('beforeend', markup)", CLASS_PANELS["modal-box"])
    padding = modal_page.locator(".modal-box[data-panel]").evaluate("element => getComputedStyle(element).paddingTop")
    assert padding != "0px"


def test_create_project_dialog_uses_opaque_surface(page_markup):
    html = page_markup[0]
    function = html[html.index("function showCreateProjectModal("):]
    template = function[:function.index("📁 새 프로젝트 생성")]
    assert "background:var(--surface-solid" in template.replace(" ", "")
