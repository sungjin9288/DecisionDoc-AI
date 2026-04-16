from app.services.export_outline import presentation_points, summarize_export_docs


def test_presentation_points_split_long_sentence_into_clauses() -> None:
    text = (
        "본 제안은 핵심 정책 목표를 공공기관이 실제 운영 KPI로 관리할 수 있도록 데이터 통합, "
        "AI 분석, 운영 대시보드를 하나의 사업 범위로 묶은 안입니다."
    )
    points = presentation_points(text, max_len=48, max_points=4)
    assert len(points) >= 2
    assert any("AI 분석 · 운영 대시보드" in point for point in points)
    assert all(len(point) <= 48 for point in points)
    assert "AI 분석" not in points


def test_presentation_points_merges_short_enumeration_fragments() -> None:
    text = (
        "수행계획서는 계약 범위, 일정, 산출물, 투입 인력, 승인 게이트를 하나의 실행 문서로 정리한 결과물입니다."
    )
    points = presentation_points(text, max_len=40, max_points=4)
    assert any("계약 범위 · 일정 · 산출물" in point for point in points)
    assert not any(point == "일정" for point in points)


def test_summarize_export_docs_exposes_short_ppt_lead() -> None:
    docs = [
        {
            "doc_type": "business_understanding",
            "markdown": (
                "# 사업 이해\n\n"
                "첫 문장은 발표자료용 요약으로 충분히 짧아야 합니다. "
                "두 번째 문장은 문서형 상세 설명입니다."
            ),
        }
    ]
    summary = summarize_export_docs(docs)[0]
    assert summary["ppt_lead"] == "첫 문장은 발표자료용 요약으로 충분히 짧아야 합니다."
    assert "두 번째 문장" not in summary["ppt_lead"]


def test_summarize_export_docs_exposes_structured_section_and_metric_items() -> None:
    docs = [
        {
            "doc_type": "business_understanding",
            "markdown": (
                "# 사업 이해\n\n"
                "제안의 핵심 요약입니다.\n\n"
                "## 제안 요약\n\n"
                "| 항목 | 내용 |\n| --- | --- |\n| KPI | 운영 정렬 |\n\n"
                "## 사업 배경\n\n"
                "- 정책 배경\n"
            ),
        }
    ]
    summary = summarize_export_docs(docs)[0]
    assert summary["section_items"] == ["제안 요약", "사업 배경"]
    assert summary["metric_items"] == ["표 1개", "목록 1개"]
