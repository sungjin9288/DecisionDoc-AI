"""RFP profile validation and the publicdoc CLI exit codes."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.public_sector.models import RfpProfile, load_profile
from app.public_sector.profile_check import check_profile
from scripts.publicdoc import EXIT_FINDINGS, EXIT_INVALID_INPUT, EXIT_PASSED, main

PROFILE = {
    "schema_version": "publicdoc.rfp_profile.v1",
    "project": {"name": "[합성] 문서관리시스템 고도화", "issuer": "가상 기관"},
    "requirements": [
        {"id": "SFR-001", "category": "기능", "name": "통합 검색 기능"},
        {"id": "SER-001", "category": "보안", "name": "개인정보 암호화"},
    ],
    "evaluation_items": [
        {"name": "사업 이해도", "points": 30, "kind": "정성", "headings": ["사업 이해"]},
        {"name": "기술 부문", "points": 60, "kind": "정성", "headings": ["기술 부문"]},
    ],
    "submission": {"formats": ["pdf"], "max_total_mb": 300, "page_limit": 100, "blind_evaluation": False},
    "scoring": {"technical": 90, "price": 10, "pass_ratio": 0.85},
}
DRAFT = "# 제안서\n\n## 사업 이해\n개요\n\n## 기술 부문\nSFR-001 통합 검색과 SER-001 암호화를 제공한다.\n"


def _write(tmp_path: Path, name: str, content: str | dict) -> str:
    path = tmp_path / name
    path.write_text(content if isinstance(content, str) else json.dumps(content, ensure_ascii=False), encoding="utf-8")
    return str(path)


def test_profile_rejects_unknown_fields_and_wrong_types() -> None:
    with pytest.raises(ValidationError):
        RfpProfile.model_validate({**PROFILE, "deadline": "2026-11-01"})
    with pytest.raises(ValidationError):
        RfpProfile.model_validate({**PROFILE, "scoring": {"technical": "90"}})


def test_complete_profile_passes_and_reports_nothing_unknown(tmp_path: Path) -> None:
    report = check_profile(load_profile(_write(tmp_path, "p.json", PROFILE)))

    assert report["passed"] is True
    assert report["counts"] == {"error": 0, "warning": 0, "info": 0}


def test_profile_check_separates_errors_warnings_and_unknown_conditions() -> None:
    profile = RfpProfile.model_validate({
        "schema_version": "publicdoc.rfp_profile.v1",
        "project": {"name": "합성"},
        "requirements": [{"id": "SFR-001", "category": "기능요건"}, {"id": "SFR-1"}],
        "evaluation_items": [{"name": "기술", "points": 50}],
        "scoring": {"technical": 90},
    })

    report = check_profile(profile)
    codes = {finding["code"]: finding["severity"] for finding in report["findings"]}

    assert report["passed"] is False
    assert codes["duplicate_id"] == "error"
    assert codes["unofficial_category"] == "warning"
    assert codes["points_mismatch"] == "warning"
    unknown = {f["target"] for f in report["findings"] if f["code"] == "unknown_condition"}
    assert {"제출 형식", "블라인드 평가 여부", "협상적격 기준"} <= unknown


def test_cli_exit_codes_and_written_tables(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    profile = _write(tmp_path, "profile.json", PROFILE)
    draft = _write(tmp_path, "draft.md", DRAFT)
    table = tmp_path / "대비표.md"

    assert main(["check-profile", profile]) == EXIT_PASSED
    assert main(["trace", profile, draft, "--table", str(table), "--out", str(tmp_path / "trace.json")]) == EXIT_PASSED
    assert "| SER-001 | 보안 | 개인정보 암호화 |" in table.read_text(encoding="utf-8")
    assert main(["crosswalk", profile, draft, "--out", str(tmp_path / "cw.json")]) == EXIT_PASSED

    missing = _write(tmp_path, "missing.md", "# 제안서\n\n## 사업 이해\nSFR-001만 다룬다.\n")
    assert main(["trace", profile, missing, "--out", str(tmp_path / "t2.json")]) == EXIT_FINDINGS

    assert main(["trace", _write(tmp_path, "bad.json", {"schema_version": "x"}), draft]) == EXIT_INVALID_INPUT
    assert main(["text", str(tmp_path / "rfp.pptx")]) == EXIT_INVALID_INPUT
    capsys.readouterr()


def test_cli_text_marks_headings(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["text", _write(tmp_path, "draft.md", DRAFT)]) == EXIT_PASSED
    assert "## 기술 부문" in capsys.readouterr().out


@pytest.mark.parametrize("path", ["work/과업/rfp.hwpx", "output/uat/draft.md"])
def test_session_work_folders_named_in_the_skills_stay_out_of_git(path: str) -> None:
    import subprocess

    root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(["git", "check-ignore", "-q", path], cwd=root, check=False)

    assert completed.returncode == 0, f"{path} may hold customer material and must stay gitignored"
