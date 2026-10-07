"""Bundle prompt hygiene: no duplicated bundle hints, one evidence rule for numbers."""

import pytest

from app.bundle_catalog.registry import BUNDLE_REGISTRY
from app.domain.schema import SCHEMA_VERSION, build_bundle_prompt

EVIDENCE_RULE = "다른 지시가 구체적 수치나 정량 지표를 요구해도 근거가 없으면 수치를 만들지 말고"


def _prompt(bundle_id: str) -> str:
    requirements = {"title": "합성 점검", "goal": "프롬프트 구성 확인", "bundle_type": bundle_id}
    return build_bundle_prompt(requirements, SCHEMA_VERSION, BUNDLE_REGISTRY[bundle_id])


@pytest.mark.parametrize("bundle_id", sorted(BUNDLE_REGISTRY))
def test_bundle_hint_appears_once(bundle_id):
    hint = BUNDLE_REGISTRY[bundle_id].prompt_hint
    if not hint:
        pytest.skip("bundle has no prompt_hint")
    first_line = hint.strip().splitlines()[0]

    assert _prompt(bundle_id).count(first_line) == 1


@pytest.mark.parametrize("bundle_id", sorted(BUNDLE_REGISTRY))
def test_numbers_require_evidence_and_rule_takes_precedence(bundle_id):
    prompt = _prompt(bundle_id)

    assert EVIDENCE_RULE in prompt
    assert "구체적 수치 반드시 포함" not in prompt
    # The precedence rule comes after the bundle and style instructions it overrides.
    assert prompt.rindex(EVIDENCE_RULE) > prompt.index("schema=")


def test_proposal_hint_asks_for_evidence_not_invented_numbers():
    hint = BUNDLE_REGISTRY["proposal_kr"].prompt_hint

    assert "어떤 근거와 측정 방법으로 증명할 것인가" in hint
    assert "수치로 증명할 것인가" not in hint
