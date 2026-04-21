from __future__ import annotations

from pathlib import Path

from scripts.finalize_uat_session import (
    build_uat_summary_markdown,
    finalize_uat_session,
    summarize_uat_payload,
)


def test_summarize_uat_payload_marks_ready_when_all_entries_closed() -> None:
    payload = {
        "session_title": "business-uat",
        "session_file": "/tmp/session.md",
        "entries": [
            {
                "scenario": "시나리오 1. 기본 사업 제안서 생성",
                "recorded_at": "2026-04-21T10:00:00+00:00",
                "bundle": "proposal_kr",
                "generation_status": "성공 (HTTP 200)",
                "export_status": "성공 (HTTP 200, files=4)",
                "visual_asset_status": "미검증",
                "history_restore_status": "미검증",
                "issues": "-",
                "follow_up": "아니오",
            },
            {
                "scenario": "시나리오 5. history 복원 + 재export",
                "recorded_at": "2026-04-21T13:00:00+00:00",
                "bundle": "presentation_kr",
                "generation_status": "성공 (HTTP 200)",
                "export_status": "PPTX 재수출 성공 (HTTP 200, ppt/media/image1.png 확인)",
                "visual_asset_status": "성공 - history detail에 visual_assets 2건 유지",
                "history_restore_status": "성공 - /history/{entry_id}에서 slide_outline 복원 확인",
                "issues": "없음",
                "follow_up": "아니오",
            },
        ],
    }

    summary = summarize_uat_payload(payload)

    assert summary["status"] == "READY_FOR_PILOT"
    assert summary["entry_count"] == 2
    assert summary["scenario_count"] == 2
    assert summary["blockers"] == []
    assert summary["follow_ups"] == []


def test_summarize_uat_payload_uses_latest_retry_entry_for_scenario_status() -> None:
    payload = {
        "session_title": "business-uat",
        "session_file": "/tmp/session.md",
        "entries": [
            {
                "scenario": "시나리오 2. 첨부 기반 제안서 생성",
                "recorded_at": "2026-04-21T09:57:24+00:00",
                "bundle": "proposal_kr",
                "generation_status": "성공 (HTTP 200)",
                "export_status": "미검증",
                "visual_asset_status": "미검증",
                "history_restore_status": "미검증",
                "issues": "내용 품질 이슈: 근거 없는 세부사항 hallucination",
                "follow_up": "예 - 실제 PDF/PPTX/HWPX 첨부와 품질 보정 필요",
            },
            {
                "scenario": "시나리오 2 3차 재시험. sparse attachment AI 접근 문장 polish 검증",
                "recorded_at": "2026-04-21T11:06:38+00:00",
                "bundle": "proposal_kr",
                "generation_status": "성공 (HTTP 200)",
                "export_status": "미검증",
                "visual_asset_status": "미검증",
                "history_restore_status": "미검증",
                "issues": "없음",
                "follow_up": "아니오 - sparse attachment proposal_kr 기준 핵심 품질 이슈 해소",
            },
        ],
    }

    summary = summarize_uat_payload(payload)

    assert summary["status"] == "READY_FOR_PILOT"
    assert summary["scenario_count"] == 1
    assert summary["blockers"] == []
    assert summary["follow_ups"] == []


def test_finalize_uat_session_writes_summary_markdown(tmp_path: Path) -> None:
    session_file = tmp_path / "uat-session-20260421T091014Z-business-uat.md"
    session_file.write_text(
        """# UAT Session — business-uat

## 5. 결과 기록

### UAT 기록 — 시나리오 3. visual asset 생성 및 export 일관성
- 일시: 2026-04-21T11:20:20.733811+00:00
- 담당자: sungjin
- 시나리오: 시나리오 3. visual asset 생성 및 export 일관성
- 사용 번들: proposal_kr
- 입력 데이터: custom visual payload
- 첨부 파일:
  - 없음
- 결과:
  - 생성 성공/실패: 성공 (visual-assets 200)
  - export 성공/실패: 성공 (DOCX/PDF/PPTX/HWPX 모두 200)
  - visual asset 일치 여부: 성공
  - history 복원 여부: 미검증
- 품질 메모: export 일관성 확인
- 실패/이슈: 없음
- 후속 조치 필요 여부: 아니오

### UAT 기록 — 시나리오 5. history 복원 + 재export
- 일시: 2026-04-21T13:01:07.336275+00:00
- 담당자: sungjin
- 시나리오: 시나리오 5. history 복원 + 재export
- 사용 번들: presentation_kr
- 입력 데이터: synthetic JWT admin context
- 첨부 파일:
  - 없음
- 결과:
  - 생성 성공/실패: 성공 (HTTP 200)
  - export 성공/실패: PPTX 재수출 성공 (HTTP 200, ppt/media/image1.png 확인)
  - visual asset 일치 여부: 성공 - history detail에 visual_assets 2건 유지
  - history 복원 여부: 성공 - /history/{entry_id}에서 slide_outline 복원 확인
- 품질 메모: history restore roundtrip OK
- 실패/이슈: 없음
- 후속 조치 필요 여부: 아니오
""",
        encoding="utf-8",
    )

    summary, output_path = finalize_uat_session(session_file=session_file, output_dir=tmp_path)

    assert summary["status"] == "READY_FOR_PILOT"
    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert "# UAT Final Summary — business-uat" in content
    assert "overall_status: **READY_FOR_PILOT**" in content
    assert "시나리오 5. history 복원 + 재export" in content
    assert "ppt/media/image1.png" in content
