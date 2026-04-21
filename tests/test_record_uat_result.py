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


def test_record_uat_result_appends_entry_to_session_file(tmp_path: Path, capsys) -> None:
    script = _load_script_module("decisiondoc_record_uat_result", "scripts/record_uat_result.py")
    session_file = tmp_path / "uat-session.md"
    session_file.write_text("# UAT Session — business-uat\n\n## 5. 결과 기록\n", encoding="utf-8")

    result = script.main(
        [
            "--session-file",
            str(session_file),
            "--owner",
            "qa-user",
            "--scenario",
            "시나리오 1. 기본 사업 제안서 생성",
            "--bundle",
            "proposal_kr",
            "--input-data",
            "국토교통 제안 요청 기본 입력",
            "--attachments",
            "intro.pdf, concept.pptx",
            "--generation-status",
            "성공",
            "--export-status",
            "DOCX/PDF 성공",
            "--visual-asset-status",
            "일치",
            "--history-restore-status",
            "확인 완료",
            "--quality-notes",
            "문서 구조는 안정적이나 결론 문장이 다소 장문임",
            "--issues",
            "없음",
            "--follow-up",
            "아니오",
        ]
    )

    captured = capsys.readouterr().out
    content = session_file.read_text(encoding="utf-8")
    assert result == 0
    assert "Recorded UAT result:" in captured
    assert "### UAT 기록 — 시나리오 1. 기본 사업 제안서 생성" in content
    assert "- 담당자: qa-user" in content
    assert "  - intro.pdf" in content
    assert "  - concept.pptx" in content
    assert "  - 생성 성공/실패: 성공" in content
    assert "- 품질 메모: 문서 구조는 안정적이나 결론 문장이 다소 장문임" in content


def test_record_uat_result_requires_existing_session_file(tmp_path: Path) -> None:
    script = _load_script_module("decisiondoc_record_uat_result_missing", "scripts/record_uat_result.py")
    missing_path = tmp_path / "missing.md"

    try:
        script.main(
            [
                "--session-file",
                str(missing_path),
                "--scenario",
                "시나리오 1",
            ]
        )
    except SystemExit as exc:
        assert str(exc) == f"Session file not found: {missing_path}"
    else:
        raise AssertionError("Expected SystemExit for missing session file")
