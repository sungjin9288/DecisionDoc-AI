from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_script_module(module_name: str, relative_path: str):
    path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_show_uat_session_prints_latest_entries(tmp_path: Path, capsys) -> None:
    script = _load_script_module("decisiondoc_show_uat_session", "scripts/show_uat_session.py")
    session_file = tmp_path / "uat-session.md"
    session_file.write_text(
        """# UAT Session — business-uat

## 5. 결과 기록

### UAT 기록 — 시나리오 1. 기본 사업 제안서 생성
- 일시: 2026-04-21T09:38:43+00:00
- 담당자: qa-user
- 시나리오: 시나리오 1. 기본 사업 제안서 생성
- 사용 번들: proposal_kr
- 입력 데이터: 국토교통 제안 요청 기본 입력
- 첨부 파일:
  - intro.pdf
- 결과:
  - 생성 성공/실패: 성공
  - export 성공/실패: DOCX/PDF 성공
  - visual asset 일치 여부: 일치
  - history 복원 여부: 확인 완료
- 품질 메모: 안정적
- 실패/이슈: 없음
- 후속 조치 필요 여부: 아니오

### UAT 기록 — 시나리오 2. 첨부 기반 제안서 생성
- 일시: 2026-04-21T10:10:00+00:00
- 담당자: qa-user
- 시나리오: 시나리오 2. 첨부 기반 제안서 생성
- 사용 번들: proposal_kr
- 입력 데이터: 첨부 기반
- 첨부 파일:
  - intro.pdf
  - concept.pptx
- 결과:
  - 생성 성공/실패: 성공
  - export 성공/실패: PDF 성공
  - visual asset 일치 여부: 일치
  - history 복원 여부: 확인 완료
- 품질 메모: 첨부 맥락 반영 양호
- 실패/이슈: 없음
- 후속 조치 필요 여부: 아니오
""",
        encoding="utf-8",
    )

    result = script.main(["--session-file", str(session_file), "--limit", "1"])

    captured = capsys.readouterr().out
    assert result == 0
    assert "Session title: business-uat" in captured
    assert "Recorded entries: 2" in captured
    assert "시나리오 2. 첨부 기반 제안서 생성" in captured
    assert "generation=성공" in captured
    assert "export=PDF 성공" in captured
    assert "시나리오 1. 기본 사업 제안서 생성" not in captured


def test_show_uat_session_requires_existing_file(tmp_path: Path) -> None:
    script = _load_script_module("decisiondoc_show_uat_session_missing", "scripts/show_uat_session.py")
    missing_path = tmp_path / "missing.md"

    try:
        script.main(["--session-file", str(missing_path)])
    except SystemExit as exc:
        assert str(exc) == f"Session file not found: {missing_path}"
    else:
        raise AssertionError("Expected SystemExit for missing session file")
