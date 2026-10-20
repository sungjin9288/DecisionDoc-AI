"""Stage reports: sections by basis, the fulfilment table and the skeleton round trip."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.public_sector.models import RfpProfile
from app.public_sector.readers import read_document
from app.public_sector.report_types import REPORT_TYPES
from app.public_sector.reports import PLACEHOLDER, check_report, report_skeleton

PROFILE = RfpProfile.model_validate({
    "schema_version": "publicdoc.rfp_profile.v1",
    "project": {"name": "[합성] 문서관리시스템 고도화"},
    "tasks": [{"id": "T-01", "name": "현행 문서 이관"}, {"id": "T-02", "name": "통합 검색 구축"}],
    "commitments": [{"id": "C-01", "name": "PM 1명 상주", "source": "제안서 p.41"}],
})


def _read(tmp_path: Path, text: str, name: str = "report.md"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return read_document(path)


def _filled(skeleton: str, statuses: dict[str, str]) -> str:
    lines = []
    for line in skeleton.splitlines():
        if line.startswith(PLACEHOLDER):
            line = "" if "상태는" in line else "내용을 적었다."
        for obligation_id, status in statuses.items():
            if f"| {obligation_id} |" in line:
                line = line.replace("| 확인 필요 |", f"| {status} |")
        lines.append(line)
    return "\n".join(lines)


@pytest.mark.parametrize("type_id", sorted(REPORT_TYPES))
def test_every_skeleton_is_recognised_section_by_section(tmp_path: Path, type_id: str) -> None:
    report_type = REPORT_TYPES[type_id]
    report = check_report(_read(tmp_path, report_skeleton(report_type, PROFILE)), report_type, PROFILE)

    assert report["sections_found"] == sorted(section.title for section in report_type.sections)
    assert not any(f["code"] == "missing_section" for f in report["findings"])
    assert any(f["code"] == "placeholder_left" for f in report["findings"]) and report["passed"] is False


def test_filled_interim_report_passes(tmp_path: Path) -> None:
    report_type = REPORT_TYPES["interim_report"]
    text = _filled(report_skeleton(report_type, PROFILE), {"T-01": "완료", "T-02": "진행 중", "C-01": "완료"})

    report = check_report(_read(tmp_path, text), report_type, PROFILE)

    assert report["findings"] == [] and report["passed"] is True
    assert [(item["id"], item["status"]) for item in report["fulfilment"]] == [("T-01", "완료"), ("T-02", "진행 중"), ("C-01", "완료")]


def test_fulfilment_table_errors_and_pending_warning(tmp_path: Path) -> None:
    report_type = REPORT_TYPES["completion_report"]
    text = _filled(report_skeleton(report_type, PROFILE), {"T-01": "진행 중", "C-01": "완료"})
    text = "\n".join(line for line in text.splitlines() if "| C-01 |" not in line)

    findings = {f["code"]: f for f in check_report(_read(tmp_path, text), report_type, PROFILE)["findings"]}

    assert findings["status_invalid"]["severity"] == "error"  # 진행 중 is not a completion status
    assert findings["status_pending"]["severity"] == "warning"  # T-02 left as 확인 필요
    assert "C-01" in findings["obligation_missing"]["message"]


def test_missing_official_section_is_an_error_and_convention_a_warning(tmp_path: Path) -> None:
    plan = "# 사업수행계획서\n\n## Ⅰ. 사업명\n가\n\n## Ⅱ. 품질관리 방안\n나\n\n## Ⅲ. 주간 보고서 양식\n다\n"
    report = check_report(_read(tmp_path, plan), REPORT_TYPES["execution_plan"])
    missing = {f["message"]: f["severity"] for f in report["findings"] if f["code"] == "missing_section"}

    assert "'품질보증' 섹션이 없다" not in missing  # 품질관리 is the body-text name of the same item
    assert missing["'보고계획' 섹션이 없다"] == "error"  # "주간 보고서 양식" is not the reporting plan
    assert len(missing) == 14

    start = check_report(_read(tmp_path, "# 착수보고서\n\n## 1. 사업 개요\n내용\n"), REPORT_TYPES["start_report"])
    assert {f["severity"] for f in start["findings"]} == {"warning"}


def test_moe_policy_report_checks_abstract_length(tmp_path: Path) -> None:
    report_type = REPORT_TYPES["policy_research_moe"]
    sections = "\n\n".join(f"## {section.title}\n본문" for section in report_type.sections[1:])
    short = check_report(_read(tmp_path, f"# 보고서\n\n## 초록\n짧은 초록\n\n{sections}\n"), report_type)
    right = check_report(_read(tmp_path, f"# 보고서\n\n## 초록\n{'가' * 500}\n\n{sections}\n"), report_type)

    assert [f["code"] for f in short["findings"]] == ["section_length"]
    assert right["findings"] == []
