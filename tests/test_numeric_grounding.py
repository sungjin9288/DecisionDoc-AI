from app.eval.numeric_grounding import review_numeric_grounding


def test_numeric_grounding_accepts_source_numbers_and_normalizes_currency() -> None:
    review = review_numeric_grounding(
        {
            "context": "예산은 65억 원이며 사업 기간은 24개월이다.",
        },
        {
            "overview": "계약 금액은 6,500,000,000원이며 전체 사업 기간은 24개월이다.",
        },
    )

    assert review["status"] == "passed"
    assert review["unsupported_count"] == 0
    assert review["source_tokens"] == ["24개월", "6500000000원"]
    assert review["output_tokens"] == ["24개월", "6500000000원"]
    assert review["proves_factual_truth"] is False


def test_numeric_grounding_reports_unsupported_claims_with_context() -> None:
    review = review_numeric_grounding(
        {"goal": "위험 감지 품질을 개선한다."},
        {
            "quality_plan": (
                "## 품질 기준\n"
                "- 위험 감지 정확도 92% 이상\n"
                "- 장애 복구 시간 30분 이내\n"
            ),
        },
    )

    assert review["status"] == "review_required"
    assert review["unsupported_count"] == 2
    assert {claim["token"] for claim in review["unsupported_claims"]} == {"92%", "30분"}
    assert all(claim["document_type"] == "quality_plan" for claim in review["unsupported_claims"])
    assert any("위험 감지 정확도" in claim["excerpt"] for claim in review["unsupported_claims"])


def test_numeric_grounding_does_not_treat_plain_section_numbers_as_claims() -> None:
    review = review_numeric_grounding(
        {},
        {"plan": "1. 착수\n2. 설계\n3단계 추진 체계\n4분할 레이아웃\nPython 3.11"},
    )

    assert review["status"] == "passed"
    assert review["output_tokens"] == []
