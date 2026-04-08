from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_script_module(module_name: str, relative_path: str):
    path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_parse_decide_marker_extracts_supported_fields_only():
    parser = _load_script_module("decisiondoc_parse_decide_marker", "scripts/parse_decide_marker.py")
    body = """
Intro text

<!-- decide
title: Redis 세션 캐싱 도입
goal: HTTP 세션 동기화 병목 해소
context: 현재 동기 HTTP 호출 방식
constraints: AWS 환경, 팀 내 Redis 경험 없음
doc_types: adr,onepager
unsupported_key: should_be_ignored
-->
"""

    parsed = parser._parse_marker(body)

    assert parsed == {
        "title": "Redis 세션 캐싱 도입",
        "goal": "HTTP 세션 동기화 병목 해소",
        "context": "현재 동기 HTTP 호출 방식",
        "constraints": "AWS 환경, 팀 내 Redis 경험 없음",
        "doc_types": "adr,onepager",
    }


def test_format_pr_comment_orders_documents_and_includes_metadata(tmp_path: Path):
    formatter = _load_script_module("decisiondoc_format_pr_comment", "scripts/format_pr_comment.py")
    (tmp_path / "onepager.md").write_text("# One Pager\n", encoding="utf-8")
    (tmp_path / "adr.md").write_text("# ADR\n", encoding="utf-8")
    (tmp_path / "_metadata.json").write_text(
        '{"provider":"mock","bundle_id":"bundle-1234567890"}',
        encoding="utf-8",
    )

    comment = formatter.format_comment(tmp_path)

    assert "## 🤖 DecisionDoc AI — 자동 생성 문서" in comment
    assert "Provider: **mock**" in comment
    assert "Bundle: `bundle-12345..." in comment
    assert comment.index("ADR (Architecture Decision Record)") < comment.index("One Pager")
    assert "*이 코멘트는 [DecisionDoc AI](https://github.com)에 의해 자동 생성되었습니다." in comment


def test_notion_push_markdown_conversion_preserves_structure():
    notion_push = _load_script_module("decisiondoc_notion_push", "scripts/notion_push.py")
    markdown = "# Title\n\nParagraph line\n- bullet item\n## Section\n"

    blocks = notion_push._md_to_notion_blocks(markdown)

    assert [block["type"] for block in blocks] == [
        "heading_1",
        "paragraph",
        "bulleted_list_item",
        "heading_2",
    ]
    assert blocks[0]["heading_1"]["rich_text"][0]["text"]["content"] == "Title"
    assert blocks[2]["bulleted_list_item"]["rich_text"][0]["text"]["content"] == "bullet item"


def test_decide_parse_doc_types_rejects_unknown_values():
    decide = _load_script_module("decisiondoc_decide", "scripts/decide.py")

    assert decide._parse_doc_types("adr, onepager , eval_plan") == ["adr", "onepager", "eval_plan"]

    with pytest.raises(SystemExit):
        decide._parse_doc_types("adr,unknown")
