from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_script_module():
    path = REPO_ROOT / "scripts" / "package_company_handoff.py"
    spec = importlib.util.spec_from_file_location("decisiondoc_package_company_handoff", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["decisiondoc_package_company_handoff"] = module
    spec.loader.exec_module(module)
    return module


def test_package_company_handoff_runs_bundle_verify_archive_and_writes_reports(monkeypatch, tmp_path: Path) -> None:
    packager = _load_script_module()
    calls: dict[str, object] = {}
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()

    def fake_create(**kwargs):
        calls["create"] = kwargs
        return {
            "ok": True,
            "bundle_dir": str(bundle_dir),
            "manifest_path": str(bundle_dir / "manifest.json"),
            "prepare_result": {"ok": True},
            "source": {
                "source_commit": "fixturecommit",
                "source_describe": "v1.1.58-fixture",
                "source_exact_tag": "",
                "expected_release_tag": "v1.1.58",
                "exact_release_tag": False,
                "dirty": False,
                "warnings": ["fixture warning"],
            },
            "warnings": ["fixture warning"],
            "errors": [],
        }

    def fake_verify(*, bundle_or_manifest):
        calls["verify"] = bundle_or_manifest
        return {
            "ok": True,
            "errors": [],
            "checked_artifacts": 15,
            "release_tag": "v1.1.58",
        }

    def fake_archive(**kwargs):
        calls["archive"] = kwargs
        return {
            "ok": True,
            "errors": [],
            "archive_path": str(tmp_path / "bundle.zip"),
            "sha256_path": str(tmp_path / "bundle.zip.sha256"),
            "archive_sha256": "abc123",
            "archive_size_bytes": 123,
        }

    monkeypatch.setattr(packager.create_company_handoff_bundle, "create_company_handoff_bundle", fake_create)
    monkeypatch.setattr(packager.verify_company_handoff_bundle, "verify_company_handoff_bundle", fake_verify)
    monkeypatch.setattr(packager.archive_company_handoff_bundle, "archive_company_handoff_bundle", fake_archive)

    result = packager.package_company_handoff(
        output_dir=Path("output/pdf"),
        report_dir=tmp_path / "reports",
        bundle_root=tmp_path / "bundles",
        bundle_name="bundle",
        skip_build=True,
        force_archive=True,
    )

    assert result["ok"] is True
    assert result["summary"]["checked_artifacts"] == 15
    assert result["summary"]["source_describe"] == "v1.1.58-fixture"
    assert result["summary"]["exact_release_tag"] is False
    assert result["warnings"] == ["fixture warning"]
    assert calls["create"] == {
        "output_dir": Path("output/pdf"),
        "report_dir": tmp_path / "reports",
        "bundle_root": tmp_path / "bundles",
        "skip_prepare": False,
        "skip_build": True,
        "bundle_name": "bundle",
    }
    assert calls["verify"] == bundle_dir
    assert calls["archive"] == {
        "bundle_dir": bundle_dir,
        "force": True,
        "skip_verify": True,
    }
    latest = tmp_path / "reports" / "package-latest.json"
    assert latest.exists()
    assert json.loads(latest.read_text(encoding="utf-8"))["ok"] is True
    assert len(result["reports"]) == 2


def test_package_company_handoff_stops_when_bundle_creation_fails(monkeypatch, tmp_path: Path) -> None:
    packager = _load_script_module()
    calls: dict[str, bool] = {}

    monkeypatch.setattr(
        packager.create_company_handoff_bundle,
        "create_company_handoff_bundle",
        lambda **kwargs: {"ok": False, "errors": ["bundle failed"], "bundle_dir": "", "manifest_path": ""},
    )
    monkeypatch.setattr(
        packager.verify_company_handoff_bundle,
        "verify_company_handoff_bundle",
        lambda **kwargs: calls.setdefault("verify_called", True),
    )

    result = packager.package_company_handoff(report_dir=tmp_path / "reports")

    assert result["ok"] is False
    assert result["failed_stage"] == "bundle"
    assert result["errors"] == ["bundle failed"]
    assert "verify_called" not in calls
    assert (tmp_path / "reports" / "package-latest.json").exists()


def test_package_company_handoff_stops_when_verification_fails(monkeypatch, tmp_path: Path) -> None:
    packager = _load_script_module()
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()

    monkeypatch.setattr(
        packager.create_company_handoff_bundle,
        "create_company_handoff_bundle",
        lambda **kwargs: {
            "ok": True,
            "errors": [],
            "bundle_dir": str(bundle_dir),
            "manifest_path": str(bundle_dir / "manifest.json"),
        },
    )
    monkeypatch.setattr(
        packager.verify_company_handoff_bundle,
        "verify_company_handoff_bundle",
        lambda **kwargs: {"ok": False, "errors": ["hash mismatch"], "checked_artifacts": 1},
    )

    result = packager.package_company_handoff(report_dir=tmp_path / "reports")

    assert result["ok"] is False
    assert result["failed_stage"] == "verify"
    assert result["archive"] is None
    assert result["errors"] == ["hash mismatch"]


def test_package_company_handoff_stops_when_archive_fails(monkeypatch, tmp_path: Path) -> None:
    packager = _load_script_module()
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()

    monkeypatch.setattr(
        packager.create_company_handoff_bundle,
        "create_company_handoff_bundle",
        lambda **kwargs: {
            "ok": True,
            "errors": [],
            "bundle_dir": str(bundle_dir),
            "manifest_path": str(bundle_dir / "manifest.json"),
        },
    )
    monkeypatch.setattr(
        packager.verify_company_handoff_bundle,
        "verify_company_handoff_bundle",
        lambda **kwargs: {"ok": True, "errors": [], "checked_artifacts": 15},
    )
    monkeypatch.setattr(
        packager.archive_company_handoff_bundle,
        "archive_company_handoff_bundle",
        lambda **kwargs: {"ok": False, "errors": ["archive exists"]},
    )

    result = packager.package_company_handoff(report_dir=tmp_path / "reports")

    assert result["ok"] is False
    assert result["failed_stage"] == "archive"
    assert result["errors"] == ["archive exists"]
