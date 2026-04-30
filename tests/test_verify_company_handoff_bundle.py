from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_script_module():
    path = REPO_ROOT / "scripts" / "verify_company_handoff_bundle.py"
    spec = importlib.util.spec_from_file_location("decisiondoc_verify_company_handoff_bundle", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["decisiondoc_verify_company_handoff_bundle"] = module
    spec.loader.exec_module(module)
    return module


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_bundle(tmp_path: Path, *, body: bytes = b"%PDF-fixture") -> Path:
    bundle_dir = tmp_path / "bundle"
    artifact = bundle_dir / "output" / "pdf" / "fixture.pdf"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(body)
    manifest = {
        "schema": "decisiondoc_company_handoff_bundle.v1",
        "artifact_count": 1,
        "release_tag": "v1.1.59",
        "source": {
            "source_commit": "fixturecommit",
            "source_describe": "v1.1.59-fixture",
            "source_exact_tag": "",
            "expected_release_tag": "v1.1.59",
            "exact_release_tag": False,
            "dirty": False,
            "warnings": ["fixture warning"],
        },
        "warnings": ["fixture warning"],
        "artifacts": [
            {
                "path": "output/pdf/fixture.pdf",
                "bundle_path": "output/pdf/fixture.pdf",
                "size_bytes": len(body),
                "sha256": _sha256(body),
            }
        ],
    }
    (bundle_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return bundle_dir


def test_verify_company_handoff_bundle_passes_for_valid_bundle(tmp_path: Path) -> None:
    verifier = _load_script_module()
    bundle_dir = _write_bundle(tmp_path)

    result = verifier.verify_company_handoff_bundle(bundle_or_manifest=bundle_dir)

    assert result["ok"] is True
    assert result["checked_artifacts"] == 1
    assert result["release_tag"] == "v1.1.59"
    assert result["source"]["source_commit"] == "fixturecommit"
    assert result["warnings"] == ["fixture warning"]


def test_verify_company_handoff_bundle_accepts_manifest_path(tmp_path: Path) -> None:
    verifier = _load_script_module()
    bundle_dir = _write_bundle(tmp_path)

    result = verifier.verify_company_handoff_bundle(bundle_or_manifest=bundle_dir / "manifest.json")

    assert result["ok"] is True
    assert result["checked_artifacts"] == 1


def test_verify_company_handoff_bundle_detects_missing_artifact(tmp_path: Path) -> None:
    verifier = _load_script_module()
    bundle_dir = _write_bundle(tmp_path)
    (bundle_dir / "output" / "pdf" / "fixture.pdf").unlink()

    result = verifier.verify_company_handoff_bundle(bundle_or_manifest=bundle_dir)

    assert result["ok"] is False
    assert "artifact file is missing: output/pdf/fixture.pdf" in result["errors"]


def test_verify_company_handoff_bundle_detects_hash_mismatch(tmp_path: Path) -> None:
    verifier = _load_script_module()
    bundle_dir = _write_bundle(tmp_path)
    (bundle_dir / "output" / "pdf" / "fixture.pdf").write_bytes(b"%PDF-mutated")

    result = verifier.verify_company_handoff_bundle(bundle_or_manifest=bundle_dir)

    assert result["ok"] is False
    assert "artifact size mismatch: output/pdf/fixture.pdf (12 != 12)" not in result["errors"]
    assert "artifact sha256 mismatch: output/pdf/fixture.pdf" in result["errors"]


def test_verify_company_handoff_bundle_rejects_path_traversal(tmp_path: Path) -> None:
    verifier = _load_script_module()
    bundle_dir = _write_bundle(tmp_path)
    manifest_path = bundle_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"][0]["bundle_path"] = "../outside.txt"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = verifier.verify_company_handoff_bundle(bundle_or_manifest=bundle_dir)

    assert result["ok"] is False
    assert "unsafe artifact bundle_path: ../outside.txt" in result["errors"]


def test_verify_company_handoff_bundle_detects_secret_like_text(tmp_path: Path) -> None:
    verifier = _load_script_module()
    body = b"OPENAI_API_KEY=sk-live-secret"
    bundle_dir = _write_bundle(tmp_path, body=body)

    result = verifier.verify_company_handoff_bundle(bundle_or_manifest=bundle_dir)

    assert result["ok"] is False
    assert "forbidden secret-like text found in output/pdf/fixture.pdf: OPENAI_API_KEY=sk-" in result["errors"]


def test_verify_company_handoff_bundle_allows_documented_placeholder_assignments(tmp_path: Path) -> None:
    verifier = _load_script_module()
    body = b"DECISIONDOC_API_KEYS=<placeholder>\nDECISIONDOC_OPS_KEY=<placeholder>\n"
    bundle_dir = _write_bundle(tmp_path, body=body)

    result = verifier.verify_company_handoff_bundle(bundle_or_manifest=bundle_dir)

    assert result["ok"] is True
