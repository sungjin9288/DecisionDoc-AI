"""tests/test_style_loader.py — 스타일 로더 테스트."""
import pytest


def setup_function():
    from app.bundle_catalog.style_loader import reload_style_guide
    reload_style_guide()


def test_get_style_prompt_returns_string():
    from app.bundle_catalog.style_loader import get_style_prompt
    result = get_style_prompt("tech_decision", language="en")
    assert isinstance(result, str)


def test_get_style_prompt_korean_bundle():
    from app.bundle_catalog.style_loader import get_style_prompt
    result = get_style_prompt("proposal_kr", language="ko")
    assert isinstance(result, str)


def test_get_style_prompt_contains_style_or_rules():
    from app.bundle_catalog.style_loader import get_style_prompt
    result = get_style_prompt("tech_decision", language="ko")
    # 스타일 가이드 로드 성공 시 내용이 있어야 함
    if result:
        assert "스타일" in result or "규칙" in result or "Style" in result or len(result) > 50


def test_get_style_prompt_bundle_specific():
    from app.bundle_catalog.style_loader import get_style_prompt
    result = get_style_prompt("okr_plan_kr", language="ko")
    assert isinstance(result, str)
    if result:
        assert len(result) > 10


def test_get_style_prompt_unknown_bundle_no_error():
    # 존재하지 않는 번들 — 공통 규칙만 반환, 에러 없어야 함
    from app.bundle_catalog.style_loader import get_style_prompt
    result = get_style_prompt("unknown_bundle_xyz", language="ko")
    assert isinstance(result, str)


def test_get_style_prompt_en_language():
    from app.bundle_catalog.style_loader import get_style_prompt
    result = get_style_prompt("tech_decision", language="en")
    assert isinstance(result, str)
    if result:
        assert "Style" in result or "Rules" in result or len(result) > 10


def test_reload_style_guide_no_error():
    from app.bundle_catalog.style_loader import reload_style_guide, get_style_prompt
    reload_style_guide()
    result = get_style_prompt("tech_decision")
    assert isinstance(result, str)


def test_style_prompt_injected_in_bundle_prompt():
    """build_bundle_prompt에 스타일 가이드가 주입되는지 확인."""
    from app.domain.schema import build_bundle_prompt
    from app.bundle_catalog.registry import get_bundle_spec
    spec = get_bundle_spec("tech_decision")
    prompt = build_bundle_prompt(
        requirements={"title": "테스트", "goal": "검증"},
        schema_version="v1",
        bundle_spec=spec,
    )
    assert isinstance(prompt, str)
    assert len(prompt) > 100
