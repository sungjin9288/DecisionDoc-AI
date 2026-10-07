"""Local-use UI fixes found in the Human UAT pre-check (2026-10-07)."""

import re
from pathlib import Path

import pytest

from tests.browser_pages import isolated_page

INDEX = Path(__file__).resolve().parents[1] / "app" / "static" / "index.html"
HTML = INDEX.read_text(encoding="utf-8")


def _function(name: str) -> str:
    start = HTML.index(f"  function {name}(")
    end = HTML.index("\n  }\n", start) + len("\n  }\n")
    return HTML[start:end]


@pytest.fixture
def helpers_page(browser):
    with isolated_page(browser) as page:
        page.route("**/*", lambda route: route.abort())
        page.set_content("<p>helpers</p>")
        page.add_script_tag(
            content="\n".join(_function(name) for name in ("_docTabLabel", "_shortId", "formatProcurementBudget"))
        )
        yield page


@pytest.mark.parametrize(
    ("markdown", "doc_type", "expected"),
    [
        ("# 사업 이해: [합성] 문서관리\n\n본문", "business_understanding", "사업 이해"),
        ("# ADR: Redis 도입\n", "adr", "ADR"),
        ("# 회의록\n", "meeting_summary", "회의록"),
        ("본문만 있음", "tech_proposal", "tech proposal"),
        ("# " + "가" * 40 + "\n", "expected_impact", "expected impact"),
    ],
)
def test_document_tabs_use_rendered_document_names(helpers_page, markdown, doc_type, expected):
    label = helpers_page.evaluate("doc => _docTabLabel(doc)", {"markdown": markdown, "doc_type": doc_type})

    assert label == expected


@pytest.mark.parametrize(
    ("budget", "expected"),
    [("100000000", "100,000,000원"), ("1,500,000", "1,500,000원"), ("1억 원", "1억 원"), ("", "—"), (None, "—")],
)
def test_procurement_budget_is_readable(helpers_page, budget, expected):
    assert helpers_page.evaluate("value => formatProcurementBudget(value)", budget) == expected


def test_long_ids_are_shortened_for_display(helpers_page):
    assert helpers_page.evaluate("() => _shortId('67480a6a-85b8-4d2c-9c41-63d90cf59621')") == "67480a6a…"
    assert helpers_page.evaluate("() => _shortId('short-id')") == "short-id"


def test_result_and_compare_tabs_use_document_names():
    assert "btn.textContent = _docTabLabel(doc);" in HTML
    assert "tb.textContent = _docTabLabel(doc);" in HTML
    assert "doc.doc_type.replace(/_/g, ' ')" not in HTML


def test_knowledge_modals_close_with_escape_and_have_accessible_close():
    for modal_id in ("knowledge-context-modal", "knowledge-temporal-graph-modal"):
        assert f'data-close-modal="{modal_id}" aria-label="닫기"' in HTML
    escape_block = HTML[HTML.index("// Escape — 스케치 패널 닫기, 모달 닫기"):]
    escape_block = escape_block[:escape_block.index("// 비교 모달 닫기")]
    assert "[data-close-modal]" in escape_block and "closableModal.style.display = 'none'" in escape_block


def test_location_cards_refresh_after_member_creation_and_unassigned_badge_is_explicit():
    create_success = HTML[HTML.index("closeLocationCreateUserModal();\n      await openLocationUsersPanel(tenantId);"):]
    assert create_success.split("} catch", 1)[0].count("void loadLocations();") == 1
    assert "'🗂️ 배정된 업무 AI 없음'" in HTML


def test_rendered_markdown_tables_have_cell_borders_and_padding():
    rule = re.search(r"\.doc-pane-content th, \.doc-pane-content td,[^{]*\{([^}]*)\}", HTML)
    assert rule and "border:" in rule.group(1) and "padding:" in rule.group(1)
