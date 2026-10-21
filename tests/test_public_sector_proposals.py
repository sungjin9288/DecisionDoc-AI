"""Proposal outline from the RFP, the proposal check and in-process export."""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from app.public_sector.crosswalk import build_crosswalk
from app.public_sector.export import export_drafts
from app.public_sector.models import PLACEHOLDER, RfpProfile
from app.public_sector.profile_check import check_profile
from app.public_sector.proposals import REQUIREMENTS_CHAPTER, check_proposal, plan_outline, proposal_skeleton
from app.public_sector.readers import ReaderError, read_document
from app.public_sector.requirements import trace_requirements
from scripts.publicdoc import EXIT_FINDINGS, EXIT_PASSED, main

BASE = {
    "schema_version": "publicdoc.rfp_profile.v1",
    "project": {"name": "[합성] 문서관리시스템 고도화"},
    "requirements": [
        {"id": "SFR-001", "category": "기능", "name": "통합 검색"},
        {"id": "SER-001", "category": "보안", "name": "개인정보 암호화"},
    ],
    "evaluation_items": [{"name": "사업 이해도", "points": 30}, {"name": "기술 부문", "points": 60}],
}
OUTLINE = [
    {"title": "Ⅰ. 제안 개요", "evaluation_items": ["사업 이해도"]},
    {"title": "Ⅱ. 기술 부문", "evaluation_items": ["기술 부문"], "requirement_ids": ["SFR-001"], "guidance": "기능별 구현 방안"},
]
FILLED = """# [합성] 문서관리시스템 고도화 제안서

## Ⅰ. 제안 개요
사업 목표를 정리한다.

## Ⅱ. 기술 부문
SFR-001 통합 검색을 제공한다.

## 요구사항별 대응 방안
요구사항마다 대응 방안을 적는다.

### 개인정보 암호화
SER-001 저장 시 암호화한다.
"""


def _profile(**extra) -> RfpProfile:
    return RfpProfile.model_validate({**BASE, **extra})


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_outline_follows_evaluation_items_and_collects_unclaimed_requirements() -> None:
    planned = plan_outline(_profile())

    assert [(s.title, s.level) for s in planned] == [
        ("사업 이해도", 1), ("기술 부문", 1), (REQUIREMENTS_CHAPTER, 1), ("통합 검색", 2), ("개인정보 암호화", 2),
    ]
    assert not any(section.prescribed for section in planned)


def test_prescribed_outline_keeps_rfp_order_and_claims_requirements() -> None:
    planned = plan_outline(_profile(outline=OUTLINE))

    assert [s.title for s in planned] == ["Ⅰ. 제안 개요", "Ⅱ. 기술 부문", REQUIREMENTS_CHAPTER, "개인정보 암호화"]
    assert planned[1].prescribed and planned[1].requirement_ids == ("SFR-001",)
    skeleton = proposal_skeleton(_profile(outline=OUTLINE))
    assert "## Ⅱ. 기술 부문" in skeleton
    assert f"{PLACEHOLDER} 평가항목: 기술 부문(60점) · 대응 요구사항: SFR-001(본문에 고유번호를 적는다) · RFP 작성 요령: 기능별 구현 방안" in skeleton


def test_unwritten_skeleton_fails_and_does_not_count_placeholder_ids_as_answers(tmp_path: Path) -> None:
    profile = _profile(outline=OUTLINE)
    skeleton = read_document(_write(tmp_path, "skeleton.md", proposal_skeleton(profile)))

    assert trace_requirements(profile, skeleton)["missing"] == ["SFR-001", "SER-001"]
    report = check_proposal(skeleton, profile)
    codes = [finding["code"] for finding in report["findings"]]
    assert codes.count("requirement_missing") == 2 and "placeholder_left" in codes
    assert "missing_section" not in codes and report["passed"] is False


def test_filled_proposal_passes_and_missing_prescribed_section_is_an_error(tmp_path: Path) -> None:
    profile = _profile(outline=OUTLINE)

    assert check_proposal(read_document(_write(tmp_path, "ok.md", FILLED)), profile)["passed"] is True
    without_tech = FILLED.replace("## Ⅱ. 기술 부문\nSFR-001 통합 검색을 제공한다.\n", "")
    report = check_proposal(read_document(_write(tmp_path, "bad.md", without_tech)), profile)
    errors = [(f["code"], f["message"]) for f in report["findings"] if f["severity"] == "error"]
    assert ("missing_section", "'Ⅱ. 기술 부문' 목차가 없다") in errors
    assert ("requirement_missing", "요구사항 SFR-001에 대응한 본문이 없다") in errors


def test_crosswalk_uses_outline_titles_when_items_name_no_headings(tmp_path: Path) -> None:
    report = build_crosswalk(_profile(outline=OUTLINE), read_document(_write(tmp_path, "ok.md", FILLED)))

    assert [[p["heading"] for p in row["placements"]] for row in report["rows"]] == [["Ⅰ. 제안 개요"], ["Ⅱ. 기술 부문"]]
    assert report["unmapped"] == []


def test_profile_check_reports_outline_references() -> None:
    outline = [*OUTLINE, {"title": "Ⅲ. 기타", "evaluation_items": ["가격"], "requirement_ids": ["SFR-009"]}]
    findings = {(f["code"], f["severity"]) for f in check_profile(_profile(outline=outline))["findings"]}

    assert {("outline_unknown_item", "error"), ("outline_unknown_requirement", "error")} <= findings
    missing_item = check_profile(_profile(outline=OUTLINE[:1]))["findings"]
    assert [f["target"] for f in missing_item if f["code"] == "item_without_section"] == ["기술 부문"]


def test_export_writes_body_only_files_and_rejects_non_markdown(tmp_path: Path) -> None:
    draft = _write(tmp_path, "제안서.md", FILLED)

    written = export_drafts([draft], ["hwpx", "docx"], "[합성] 제안서", tmp_path / "out", "정성제안서")

    assert [path.name for path in written] == ["정성제안서.hwpx", "정성제안서.docx"]
    with zipfile.ZipFile(io.BytesIO(written[0].read_bytes())) as archive:
        section = archive.read("Contents/section0.xml").decode("utf-8")
    assert "SFR-001 통합 검색을 제공한다." in section and "완성형 문서 패키지" not in section
    with pytest.raises(ReaderError):
        export_drafts([tmp_path / "제안서.docx"], ["hwpx"], "제목", tmp_path / "out")
    with pytest.raises(ReaderError):
        export_drafts([draft], ["pptx"], "제목", tmp_path / "out")


def test_proposal_cli_commands(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    profile = _write(tmp_path, "profile.json", _profile(outline=OUTLINE).model_dump_json())
    skeleton = tmp_path / "skeleton.md"
    filled = _write(tmp_path, "filled.md", FILLED)

    assert main(["proposal-skeleton", "--profile", str(profile), "--out", str(skeleton)]) == EXIT_PASSED
    assert main(["proposal-check", "--profile", str(profile), str(skeleton), "--out", str(tmp_path / "a.json")]) == EXIT_FINDINGS
    assert main(["proposal-check", "--profile", str(profile), str(filled), "--out", str(tmp_path / "b.json")]) == EXIT_PASSED
    assert main(["export", str(filled), "--title", "제안서", "--formats", "hwpx", "--out-dir", str(tmp_path / "out")]) == EXIT_PASSED
    assert (tmp_path / "out" / "제안서.hwpx").is_file()
    capsys.readouterr()
