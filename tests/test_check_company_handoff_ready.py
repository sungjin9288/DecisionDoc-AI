from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_script_module():
    path = REPO_ROOT / "scripts" / "check_company_handoff_ready.py"
    spec = importlib.util.spec_from_file_location("decisiondoc_check_company_handoff_ready", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["decisiondoc_check_company_handoff_ready"] = module
    spec.loader.exec_module(module)
    return module


def _write_fixture_doc(repo: Path, relative_path: str, body: str = "handoff fixture") -> None:
    path = repo / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# Fixture\n\n{body}\n\n" + ("내용\n" * 80), encoding="utf-8")


def _write_complete_handoff_docs(repo: Path) -> None:
    _write_fixture_doc(
        repo,
        "docs/deployment/admin_v1_handoff.md",
        "Admin v1.1.58 Acceptance Record 2026-04-30\n"
        "Admin v1.1.59 Acceptance Record 2026-04-30\n"
        "admin_v1_1_59_acceptance_20260430.md\n"
        "Sales Pack 인덱스",
    )
    _write_fixture_doc(
        repo,
        "docs/deployment/admin_v1_1_59_acceptance_20260430.md",
        "v1.1.59\n"
        "CD result | `success`\n"
        "Report Workflow ERP smoke\n"
        "ready for continued production use | `YES`",
    )
    _write_fixture_doc(
        repo,
        "docs/sales/company_delivery_guide.md",
        "키 전달은 별도 안전 채널로 분리합니다.\n"
        "절대 같이 보내지 말아야 하는 것",
    )
    _write_fixture_doc(repo, "docs/sales/README.md", "python3 scripts/build_sales_pack.py")
    for relative_path in (
        "docs/sales/meeting_onepager.md",
        "docs/sales/executive_intro.md",
        "docs/sales/notebooklm_comparison.md",
        "docs/sales/internal_deployment_brief.md",
        "docs/security_policy.md",
        "docs/v1_completion_snapshot.md",
    ):
        _write_fixture_doc(repo, relative_path)


def _write_complete_pdfs(repo: Path) -> None:
    output_dir = repo / "output" / "pdf"
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename in (
        "decisiondoc_ai_meeting_onepager_ko.pdf",
        "decisiondoc_ai_executive_intro_ko.pdf",
        "decisiondoc_ai_notebooklm_comparison_ko.pdf",
        "decisiondoc_ai_internal_deployment_brief_ko.pdf",
        "decisiondoc_ai_company_delivery_guide_ko.pdf",
    ):
        (output_dir / filename).write_bytes(b"%PDF-" + (b"0" * 2048))


def test_company_handoff_ready_passes_with_required_docs_and_pdfs(tmp_path: Path) -> None:
    checker = _load_script_module()
    _write_complete_handoff_docs(tmp_path)
    _write_complete_pdfs(tmp_path)

    result = checker.check_company_handoff_ready(repo_root=tmp_path)

    assert result["ok"] is True
    assert result["errors"] == []
    assert result["release_tag"] == "v1.1.59"
    assert result["source"]["expected_release_tag"] == "v1.1.59"
    assert "source_describe" in result["source"]
    assert result["manifest"]["markdown"][0]["exists"] is True
    assert result["manifest"]["pdfs"][0]["path"] == "output/pdf/decisiondoc_ai_meeting_onepager_ko.pdf"


def test_company_handoff_ready_fails_when_pdf_pack_is_missing(tmp_path: Path) -> None:
    checker = _load_script_module()
    _write_complete_handoff_docs(tmp_path)

    result = checker.check_company_handoff_ready(repo_root=tmp_path)

    assert result["ok"] is False
    assert "missing required PDF: output/pdf/decisiondoc_ai_meeting_onepager_ko.pdf" in result["errors"]


def test_company_handoff_ready_can_skip_pdf_check_for_markdown_only_gate(tmp_path: Path) -> None:
    checker = _load_script_module()
    _write_complete_handoff_docs(tmp_path)

    result = checker.check_company_handoff_ready(repo_root=tmp_path, skip_pdf_check=True)

    assert result["ok"] is True
    assert result["pdf_check"] is False


def test_company_handoff_ready_fails_when_latest_acceptance_is_stale(tmp_path: Path) -> None:
    checker = _load_script_module()
    _write_complete_handoff_docs(tmp_path)
    _write_complete_pdfs(tmp_path)
    acceptance = tmp_path / "docs" / "deployment" / "admin_v1_1_59_acceptance_20260430.md"
    acceptance.write_text("# Fixture\n\nv1.1.58\n\n" + ("내용\n" * 80), encoding="utf-8")

    result = checker.check_company_handoff_ready(repo_root=tmp_path)

    assert result["ok"] is False
    assert "required text not found in docs/deployment/admin_v1_1_59_acceptance_20260430.md: v1.1.59" in result["errors"]


def test_company_handoff_ready_rejects_secret_like_delivery_text(tmp_path: Path) -> None:
    checker = _load_script_module()
    _write_complete_handoff_docs(tmp_path)
    _write_complete_pdfs(tmp_path)
    delivery_guide = tmp_path / "docs" / "sales" / "company_delivery_guide.md"
    delivery_guide.write_text(
        "# Fixture\n\n키 전달은 별도 안전 채널로 분리합니다.\n"
        "절대 같이 보내지 말아야 하는 것\n"
        "OPENAI_API_KEY=sk-live-secret\n"
        + ("내용\n" * 80),
        encoding="utf-8",
    )

    result = checker.check_company_handoff_ready(repo_root=tmp_path)

    assert result["ok"] is False
    assert "forbidden secret-like text found in docs/sales/company_delivery_guide.md: OPENAI_API_KEY=sk-" in result["errors"]


def test_company_handoff_ready_writes_report_file(tmp_path: Path) -> None:
    checker = _load_script_module()
    _write_complete_handoff_docs(tmp_path)
    _write_complete_pdfs(tmp_path)
    report_file = tmp_path / "reports" / "company-handoff" / "readiness.json"

    result = checker.main(["--repo", str(tmp_path), "--report-file", str(report_file)])

    assert result == 0
    payload = json.loads(report_file.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["release_tag"] == "v1.1.59"
    assert payload["source"]["expected_release_tag"] == "v1.1.59"
    assert payload["manifest"]["pdfs"][0]["exists"] is True


def test_company_handoff_ready_writes_report_dir_latest(tmp_path: Path) -> None:
    checker = _load_script_module()
    _write_complete_handoff_docs(tmp_path)
    report_dir = tmp_path / "reports" / "company-handoff"

    result = checker.main(["--repo", str(tmp_path), "--skip-pdf-check", "--report-dir", str(report_dir)])

    assert result == 0
    latest = report_dir / "latest.json"
    assert latest.exists()
    timestamped = sorted(report_dir.glob("company-handoff-readiness-*.json"))
    assert len(timestamped) == 1
    payload = json.loads(latest.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["pdf_check"] is False
    assert payload["manifest"]["pdfs"] == []
