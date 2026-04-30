from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_script_module():
    path = REPO_ROOT / "scripts" / "create_company_handoff_bundle.py"
    spec = importlib.util.spec_from_file_location("decisiondoc_create_company_handoff_bundle", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["decisiondoc_create_company_handoff_bundle"] = module
    spec.loader.exec_module(module)
    return module


def _write_file(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)


def _write_fixture_repo(repo: Path, bundler) -> None:
    for pdf in bundler.check_company_handoff_ready.REQUIRED_PDFS:
        _write_file(repo / "output" / "pdf" / pdf.path, b"%PDF-" + pdf.path.encode("utf-8"))
    for doc in bundler.HANDOFF_DOCUMENTS:
        _write_file(repo / doc, f"# {doc}\n".encode("utf-8"))
    for script in bundler.HANDOFF_SCRIPTS:
        _write_file(repo / script, f"#!/usr/bin/env python3\n# {script}\n".encode("utf-8"))
    readiness = {
        "ok": True,
        "release_tag": bundler.check_company_handoff_ready.LATEST_RELEASE_TAG,
    }
    _write_file(
        repo / "reports" / "company-handoff" / "latest.json",
        json.dumps(readiness).encode("utf-8"),
    )


def test_create_company_handoff_bundle_copies_artifacts_and_writes_manifest(tmp_path: Path) -> None:
    bundler = _load_script_module()
    _write_fixture_repo(tmp_path, bundler)

    result = bundler.create_company_handoff_bundle(
        repo_root=tmp_path,
        skip_prepare=True,
        bundle_name="bundle-test",
    )

    assert result["ok"] is True
    bundle_dir = Path(result["bundle_dir"])
    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["schema"] == "decisiondoc_company_handoff_bundle.v1"
    assert manifest["release_tag"] == "v1.1.58"
    assert manifest["artifact_count"] == 15
    assert (bundle_dir / "output" / "pdf" / "decisiondoc_ai_meeting_onepager_ko.pdf").exists()
    assert (bundle_dir / "docs" / "deployment" / "admin_v1_handoff.md").exists()
    assert (bundle_dir / "scripts" / "verify_company_handoff_bundle.py").exists()
    assert (bundle_dir / "reports" / "company-handoff" / "latest.json").exists()
    assert (bundle_dir / "README.md").exists()
    assert all(item["sha256"] for item in manifest["artifacts"])
    assert {item["bundle_path"] for item in manifest["artifacts"]} >= {
        "README.md",
        "scripts/verify_company_handoff_bundle.py",
    }


def test_create_company_handoff_bundle_runs_prepare_first(monkeypatch, tmp_path: Path) -> None:
    bundler = _load_script_module()
    _write_fixture_repo(tmp_path, bundler)
    calls: dict[str, object] = {}

    def fake_prepare(**kwargs):
        calls["prepare_kwargs"] = kwargs
        return {
            "ok": True,
            "errors": [],
        }

    monkeypatch.setattr(bundler.prepare_company_handoff, "prepare_company_handoff", fake_prepare)

    result = bundler.create_company_handoff_bundle(
        repo_root=tmp_path,
        output_dir=Path("output/pdf"),
        report_dir=Path("reports/company-handoff"),
        skip_build=True,
        bundle_name="bundle-test",
    )

    assert result["ok"] is True
    assert calls["prepare_kwargs"] == {
        "output_dir": Path("output/pdf"),
        "report_dir": Path("reports/company-handoff"),
        "skip_build": True,
    }


def test_create_company_handoff_bundle_stops_when_prepare_fails(monkeypatch, tmp_path: Path) -> None:
    bundler = _load_script_module()

    monkeypatch.setattr(
        bundler.prepare_company_handoff,
        "prepare_company_handoff",
        lambda **kwargs: {"ok": False, "errors": ["prepare failed"]},
    )

    result = bundler.create_company_handoff_bundle(repo_root=tmp_path)

    assert result["ok"] is False
    assert result["errors"] == ["prepare failed"]
    assert result["bundle_dir"] == ""


def test_create_company_handoff_bundle_requires_latest_report(tmp_path: Path) -> None:
    bundler = _load_script_module()
    _write_file(tmp_path / "output" / "pdf" / "placeholder.pdf", b"%PDF-placeholder")

    result = bundler.create_company_handoff_bundle(repo_root=tmp_path, skip_prepare=True)

    assert result["ok"] is False
    assert "company handoff readiness report is missing" in result["errors"][0]
