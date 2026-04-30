from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import zipfile


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_script_module():
    path = REPO_ROOT / "scripts" / "archive_company_handoff_bundle.py"
    spec = importlib.util.spec_from_file_location("decisiondoc_archive_company_handoff_bundle", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["decisiondoc_archive_company_handoff_bundle"] = module
    spec.loader.exec_module(module)
    return module


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_valid_bundle(tmp_path: Path) -> Path:
    bundle_dir = tmp_path / "company-handoff-fixture"
    readme = bundle_dir / "README.md"
    readme.parent.mkdir(parents=True, exist_ok=True)
    readme.write_text("# Fixture\n", encoding="utf-8")
    verifier = bundle_dir / "scripts" / "verify_company_handoff_bundle.py"
    verifier.parent.mkdir(parents=True, exist_ok=True)
    verifier.write_text("# verifier\n", encoding="utf-8")
    manifest = {
        "schema": "decisiondoc_company_handoff_bundle.v1",
        "release_tag": "v1.1.59",
        "artifact_count": 2,
        "artifacts": [
            {
                "path": "README.md",
                "bundle_path": "README.md",
                "size_bytes": readme.stat().st_size,
                "sha256": _sha256(readme.read_bytes()),
            },
            {
                "path": "scripts/verify_company_handoff_bundle.py",
                "bundle_path": "scripts/verify_company_handoff_bundle.py",
                "size_bytes": verifier.stat().st_size,
                "sha256": _sha256(verifier.read_bytes()),
            },
        ],
    }
    (bundle_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return bundle_dir


def test_archive_company_handoff_bundle_creates_zip_and_sha256_sidecar(tmp_path: Path) -> None:
    archiver = _load_script_module()
    bundle_dir = _write_valid_bundle(tmp_path)

    result = archiver.archive_company_handoff_bundle(bundle_dir=bundle_dir)

    assert result["ok"] is True
    archive_path = Path(result["archive_path"])
    sha256_path = Path(result["sha256_path"])
    assert archive_path.exists()
    assert sha256_path.exists()
    assert sha256_path.read_text(encoding="utf-8").startswith(result["archive_sha256"])
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
    assert f"{bundle_dir.name}/README.md" in names
    assert f"{bundle_dir.name}/scripts/verify_company_handoff_bundle.py" in names
    assert f"{bundle_dir.name}/manifest.json" in names


def test_archive_company_handoff_bundle_refuses_existing_outputs_without_force(tmp_path: Path) -> None:
    archiver = _load_script_module()
    bundle_dir = _write_valid_bundle(tmp_path)
    output_path = tmp_path / "handoff.zip"
    output_path.write_bytes(b"existing")

    result = archiver.archive_company_handoff_bundle(bundle_dir=bundle_dir, output_path=output_path)

    assert result["ok"] is False
    assert "archive output already exists" in result["errors"][0]


def test_archive_company_handoff_bundle_allows_force_overwrite(tmp_path: Path) -> None:
    archiver = _load_script_module()
    bundle_dir = _write_valid_bundle(tmp_path)
    output_path = tmp_path / "handoff.zip"
    output_path.write_bytes(b"existing")

    result = archiver.archive_company_handoff_bundle(bundle_dir=bundle_dir, output_path=output_path, force=True)

    assert result["ok"] is True
    assert output_path.read_bytes() != b"existing"


def test_archive_company_handoff_bundle_stops_when_verification_fails(tmp_path: Path) -> None:
    archiver = _load_script_module()
    bundle_dir = _write_valid_bundle(tmp_path)
    (bundle_dir / "README.md").write_text("mutated\n", encoding="utf-8")

    result = archiver.archive_company_handoff_bundle(bundle_dir=bundle_dir)

    assert result["ok"] is False
    assert result["archive_path"] == ""
    assert "bundle verification failed" in result["errors"][0]
