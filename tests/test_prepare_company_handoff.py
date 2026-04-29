from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_script_module():
    path = REPO_ROOT / "scripts" / "prepare_company_handoff.py"
    spec = importlib.util.spec_from_file_location("decisiondoc_prepare_company_handoff", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["decisiondoc_prepare_company_handoff"] = module
    spec.loader.exec_module(module)
    return module


def test_prepare_company_handoff_builds_pack_and_writes_report(monkeypatch, tmp_path: Path) -> None:
    preparer = _load_script_module()
    calls: dict[str, object] = {}

    def fake_build_main(argv):
        calls["build_argv"] = argv
        return 0

    def fake_check(**kwargs):
        calls["check_kwargs"] = kwargs
        return {
            "ok": True,
            "errors": [],
            "generated_at": "2026-04-29T00:00:00Z",
        }

    def fake_write_reports(**kwargs):
        calls["report_kwargs"] = kwargs
        return [str(tmp_path / "reports" / "latest.json")]

    monkeypatch.setattr(preparer.build_sales_pack, "main", fake_build_main)
    monkeypatch.setattr(preparer.check_company_handoff_ready, "check_company_handoff_ready", fake_check)
    monkeypatch.setattr(preparer.check_company_handoff_ready, "_write_reports", fake_write_reports)

    result = preparer.prepare_company_handoff(
        output_dir=tmp_path / "pdf",
        report_dir=tmp_path / "reports",
    )

    assert result["ok"] is True
    assert calls["build_argv"] == ["--output-dir", str(tmp_path / "pdf")]
    assert calls["check_kwargs"] == {"output_dir": tmp_path / "pdf", "skip_pdf_check": False}
    assert calls["report_kwargs"]["report_dir"] == tmp_path / "reports"
    assert result["reports"] == [str(tmp_path / "reports" / "latest.json")]


def test_prepare_company_handoff_can_skip_build(monkeypatch, tmp_path: Path) -> None:
    preparer = _load_script_module()
    calls: dict[str, object] = {}

    def fail_build_main(argv):
        raise AssertionError(f"build should be skipped: {argv}")

    def fake_check(**kwargs):
        calls["check_kwargs"] = kwargs
        return {
            "ok": True,
            "errors": [],
            "generated_at": "2026-04-29T00:00:00Z",
        }

    monkeypatch.setattr(preparer.build_sales_pack, "main", fail_build_main)
    monkeypatch.setattr(preparer.check_company_handoff_ready, "check_company_handoff_ready", fake_check)
    monkeypatch.setattr(preparer.check_company_handoff_ready, "_write_reports", lambda **kwargs: [])

    result = preparer.prepare_company_handoff(
        output_dir=tmp_path / "pdf",
        report_dir=tmp_path / "reports",
        skip_build=True,
    )

    assert result["ok"] is True
    assert result["build_result"] is None
    assert calls["check_kwargs"] == {"output_dir": tmp_path / "pdf", "skip_pdf_check": False}


def test_prepare_company_handoff_html_only_uses_markdown_gate(monkeypatch, tmp_path: Path) -> None:
    preparer = _load_script_module()
    calls: dict[str, object] = {}

    def fake_build_main(argv):
        calls["build_argv"] = argv
        return 0

    def fake_check(**kwargs):
        calls["check_kwargs"] = kwargs
        return {
            "ok": True,
            "errors": [],
            "generated_at": "2026-04-29T00:00:00Z",
        }

    monkeypatch.setattr(preparer.build_sales_pack, "main", fake_build_main)
    monkeypatch.setattr(preparer.check_company_handoff_ready, "check_company_handoff_ready", fake_check)
    monkeypatch.setattr(preparer.check_company_handoff_ready, "_write_reports", lambda **kwargs: [])

    result = preparer.prepare_company_handoff(
        output_dir=tmp_path / "pdf",
        report_dir=tmp_path / "reports",
        html_only=True,
    )

    assert result["ok"] is True
    assert calls["build_argv"] == ["--output-dir", str(tmp_path / "pdf"), "--html-only"]
    assert calls["check_kwargs"] == {"output_dir": tmp_path / "pdf", "skip_pdf_check": True}


def test_prepare_company_handoff_stops_when_build_fails(monkeypatch, tmp_path: Path) -> None:
    preparer = _load_script_module()

    monkeypatch.setattr(preparer.build_sales_pack, "main", lambda argv: 7)
    monkeypatch.setattr(
        preparer.check_company_handoff_ready,
        "check_company_handoff_ready",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("readiness should not run")),
    )

    result = preparer.prepare_company_handoff(
        output_dir=tmp_path / "pdf",
        report_dir=tmp_path / "reports",
    )

    assert result["ok"] is False
    assert result["build_result"] == 7
    assert result["errors"] == ["sales pack build failed with exit code 7"]
