"""Submission package check: formats, size, separate files, page limits and blind evaluation."""
from __future__ import annotations

from pathlib import Path

import pytest
from docx import Document

from app.public_sector.models import RfpProfile
from app.public_sector.submission import check_submission
from scripts.publicdoc import EXIT_FINDINGS, EXIT_PASSED, main
from tests.async_helper import run_async

COMPANY = "(주)가상솔루션"
LONG_BODY = "\n".join(f"- 세부 설명 {index}: 수행 방안을 설명한다." for index in range(80))


def _profile(**submission) -> RfpProfile:
    return RfpProfile.model_validate({
        "schema_version": "publicdoc.rfp_profile.v1",
        "project": {"name": "[합성] 문서관리시스템 고도화"},
        "submission": submission,
    })


@pytest.fixture(scope="module")
def proposal_pdf(tmp_path_factory: pytest.TempPathFactory) -> bytes:
    from app.services.pdf_service import build_pdf

    markdown = f"# 정성 제안서\n\n## 사업 이해\n{LONG_BODY}\n"
    return run_async(build_pdf([{"doc_type": "tech_proposal", "markdown": markdown}], "[합성] 제안서"))


def _package(tmp_path: Path, proposal_pdf: bytes) -> Path:
    folder = tmp_path / "제출"
    folder.mkdir()
    (folder / "정성제안서.pdf").write_bytes(proposal_pdf)
    (folder / "요약본.pdf").write_bytes(proposal_pdf)
    return folder


def test_conditions_from_the_profile_are_checked(tmp_path: Path, proposal_pdf: bytes) -> None:
    folder = _package(tmp_path, proposal_pdf)
    (folder / "가격제안서.hwpx").write_bytes(b"PK")

    report = check_submission(
        _profile(formats=["pdf"], max_total_mb=0.001, separate_files=["정성 제안서", "정량 제안서"],
                 page_limit=1, summary_page_limit=1, blind_evaluation=False),
        [folder],
    )
    codes = {(f["code"], f["target"]) for f in report["findings"]}

    assert ("format_not_allowed", "가격제안서.hwpx") in codes
    assert ("over_size", "") in codes
    assert ("separate_file_not_found", "정량 제안서") in codes and ("separate_file_not_found", "정성 제안서") not in codes
    assert {("over_page_limit", "정성제안서.pdf"), ("over_page_limit", "요약본.pdf")} <= codes
    assert report["passed"] is False
    assert all(f["code"] != "unknown_condition" for f in report["findings"])


def test_unknown_conditions_are_reported_not_assumed(tmp_path: Path, proposal_pdf: bytes) -> None:
    report = check_submission(_profile(), [_package(tmp_path, proposal_pdf)])

    unknown = [f["message"] for f in report["findings"] if f["code"] == "unknown_condition"]
    assert unknown == ["제출 형식 확인 필요", "전체 용량 한도 확인 필요", "본문 쪽수 제한 확인 필요", "블라인드 평가 여부 확인 필요"]
    assert report["passed"] is True and report["files"][0]["pages"] > 1


def test_blind_evaluation_finds_identifiers_in_metadata_body_and_names(tmp_path: Path) -> None:
    folder = tmp_path / "제출"
    folder.mkdir()
    document = Document()
    document.add_paragraph("수행사는 검색 품질을 보장한다.")
    document.core_properties.author = COMPANY
    document.save(folder / "정성제안서.docx")
    (folder / "가상솔루션_요약.md").write_text(f"# 요약\n{COMPANY}가 수행한다.\n", encoding="utf-8")
    profile = _profile(blind_evaluation=True)

    assert [f["code"] for f in check_submission(profile, [folder])["findings"]] == ["unknown_condition", "unknown_condition", "unknown_condition", "identifiers_missing"]
    findings = check_submission(profile, [folder], [COMPANY, "가상솔루션"])["findings"]
    exposed = {(f["target"], f["message"]) for f in findings if f["code"] == "identifier_exposed"}

    assert ("정성제안서.docx", f"메타데이터에 '{COMPANY}'이(가) 있다") in exposed
    assert ("가상솔루션_요약.md", "본문에 '가상솔루션'이(가) 있다") in exposed
    assert ("가상솔루션_요약.md", "파일 이름에 '가상솔루션'이(가) 있다") in exposed
    assert not any(target == "정성제안서.docx" and message.startswith("본문") for target, message in exposed)


def test_submission_cli_exit_codes(tmp_path: Path, proposal_pdf: bytes, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _package(tmp_path, proposal_pdf)
    ok = tmp_path / "ok.json"
    ok.write_text(_profile(formats=["pdf"], max_total_mb=300, blind_evaluation=False).model_dump_json(), encoding="utf-8")
    strict = tmp_path / "strict.json"
    strict.write_text(_profile(formats=["hwpx"]).model_dump_json(), encoding="utf-8")

    assert main(["submission", str(ok), str(folder), "--out", str(tmp_path / "r1.json")]) == EXIT_PASSED
    assert main(["submission", str(strict), str(folder), "--out", str(tmp_path / "r2.json")]) == EXIT_FINDINGS
    capsys.readouterr()
