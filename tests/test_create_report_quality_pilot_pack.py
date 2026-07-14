from __future__ import annotations

import hashlib
import io
import importlib.util
import json
import zipfile
from pathlib import Path

import pytest

from app.services.report_quality_pilot_receipt import (
    build_pilot_export_receipt,
    serialize_pilot_export_receipt,
)
from app.services.report_quality_pilot_package import (
    build_pilot_review_package,
    read_pilot_review_package,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/create_report_quality_pilot_pack.py"
SYNC_PATH = REPO_ROOT / "scripts/sync_report_quality_pilot_pack.py"
VALIDATOR_PATH = REPO_ROOT / "docs/specs/report_quality_learning/validate_correction_artifact.py"
TEMPLATE_PATH = REPO_ROOT / "docs/specs/report_quality_learning/correction_artifact_template.json"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _ready_artifact(artifact_id: str, *, tenant_id: str = "tenant-a") -> dict:
    payload = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    payload["artifact_id"] = artifact_id
    payload["workflow_reference"]["tenant_id"] = tenant_id
    payload["quality_baseline"]["overall_score"] = 0.88
    for key in payload["quality_baseline"]["dimension_scores"]:
        payload["quality_baseline"]["dimension_scores"][key] = 0.86
    payload["correction"]["reviewer"] = "pm-reviewer"
    payload["correction"]["reviewed_at"] = "2026-07-14T09:00:00+09:00"
    for key in payload["correction"]["rationale_by_dimension"]:
        payload["correction"]["rationale_by_dimension"][key] = f"{key} manual review rationale"
    payload["learning_labels"]["accepted_for_learning"] = True
    payload["learning_labels"]["forbidden_terms_scan"] = "pass"
    payload["learning_labels"]["privacy_security_scan"] = "pass"
    payload["learning_labels"]["human_review_status"] = "accepted"
    payload["after"]["final_output_reference"] = f"report_workflow_snapshot:{artifact_id}"
    return payload


def _write_jsonl(path: Path, artifacts: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(artifact, ensure_ascii=False) for artifact in artifacts) + "\n",
        encoding="utf-8",
    )


def _source_receipt_bytes(source_path: Path, artifacts: list[dict]) -> bytes:
    export_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
    receipt = build_pilot_export_receipt(
        preview={
            "filename": f"report_quality_pilot_artifacts_{export_sha256[:12]}.jsonl",
            "export_sha256": export_sha256,
            "ordered_artifact_ids": [artifact["artifact_id"] for artifact in artifacts],
        },
        tenant_id=artifacts[0]["workflow_reference"]["tenant_id"],
        request_id="pilot-request-0001",
    )
    return serialize_pilot_export_receipt(receipt)


def _write_source_receipt(path: Path, source_path: Path, artifacts: list[dict]) -> None:
    path.write_bytes(_source_receipt_bytes(source_path, artifacts))


def _write_source_package(path: Path, source_path: Path, artifacts: list[dict]) -> dict:
    export_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
    preview = {
        "filename": f"report_quality_pilot_artifacts_{export_sha256[:12]}.jsonl",
        "export_sha256": export_sha256,
        "ordered_artifact_ids": [artifact["artifact_id"] for artifact in artifacts],
    }
    package, manifest = build_pilot_review_package(
        jsonl=source_path.read_text(encoding="utf-8"),
        receipt_bytes=_source_receipt_bytes(source_path, artifacts),
        preview=preview,
        tenant_id=artifacts[0]["workflow_reference"]["tenant_id"],
    )
    path.write_bytes(package)
    return manifest


def test_create_report_quality_pilot_pack_writes_non_ready_drafts(tmp_path):
    script = _load_module(SCRIPT_PATH, "create_report_quality_pilot_pack")
    validator = _load_module(VALIDATOR_PATH, "validate_correction_artifact")

    result = script.create_report_quality_pilot_pack(
        batch_id="pilot-rqc-test",
        output_root=tmp_path,
        sample_count=3,
        tenant_id="tenant-a",
        reviewer="pm-reviewer",
    )

    assert result["batch_id"] == "pilot-rqc-test"
    assert result["sample_count"] == 3
    assert result["training_authorized"] is False
    index_path = Path(result["index_path"])
    jsonl_path = Path(result["jsonl_path"])
    assert index_path.exists()
    assert jsonl_path.exists()
    assert "training_authorized: `false`" in index_path.read_text(encoding="utf-8")

    lines = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 3
    for payload in lines:
        assert payload["workflow_reference"]["tenant_id"] == "tenant-a"
        assert payload["workflow_reference"]["learning_opt_in"] is True
        assert payload["workflow_reference"]["source_material_policy"] == "metadata_only"
        assert payload["learning_labels"]["accepted_for_learning"] is False
        assert payload["learning_labels"]["human_review_status"] == "pending"
        assert all(value is False for value in payload["training_boundary"].values())
        validation = validator.validate_correction_artifact(payload)
        assert validation["ok"] is True
        assert validation["ready_for_learning"] is False

    for draft_path in result["draft_paths"]:
        assert Path(draft_path).exists()


def test_create_report_quality_pilot_pack_cli_outputs_json(tmp_path, capsys):
    script = _load_module(SCRIPT_PATH, "create_report_quality_pilot_pack")

    exit_code = script.main([
        "--batch-id",
        "pilot-rqc-cli",
        "--output-root",
        str(tmp_path),
        "--sample-count",
        "2",
        "--json",
    ])

    assert exit_code == 0
    result = json.loads(capsys.readouterr().out)
    assert result["batch_id"] == "pilot-rqc-cli"
    assert result["sample_count"] == 2
    assert Path(result["index_path"]).exists()
    assert Path(result["jsonl_path"]).exists()


def test_create_report_quality_pilot_pack_imports_ready_ui_export(tmp_path):
    script = _load_module(SCRIPT_PATH, "create_report_quality_pilot_pack_import")
    sync_script = _load_module(SYNC_PATH, "sync_report_quality_pilot_pack_import")
    source_path = tmp_path / "report_quality_pilot_artifacts.jsonl"
    receipt_path = tmp_path / "report_quality_pilot_receipt.json"
    artifact_ids = ["rqa_third", "rqa_first", "rqa_second"]
    artifacts = [_ready_artifact(artifact_id) for artifact_id in artifact_ids]
    _write_jsonl(source_path, artifacts)
    _write_source_receipt(receipt_path, source_path, artifacts)

    result = script.create_report_quality_pilot_pack(
        batch_id="pilot-rqc-import",
        output_root=tmp_path / "packs",
        source_jsonl=source_path,
        source_receipt=receipt_path,
    )

    assert result["source_mode"] == "exported_ready_jsonl"
    assert result["sample_count"] == 3
    assert result["ready_artifacts"] == 3
    assert result["training_authorized"] is False

    normalized = [
        json.loads(line)
        for line in Path(result["jsonl_path"]).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [artifact["artifact_id"] for artifact in normalized] == artifact_ids
    assert [Path(path).stem for path in result["draft_paths"]] == artifact_ids

    source_manifest = json.loads(Path(result["source_manifest_path"]).read_text(encoding="utf-8"))
    assert source_manifest["schema_version"] == "decisiondoc_report_quality_pilot_source_manifest.v3"
    assert source_manifest["source"]["artifact_ids"] == artifact_ids
    assert source_manifest["source"]["tenant_id"] == "tenant-a"
    assert source_manifest["source"]["sha256"] == hashlib.sha256(source_path.read_bytes()).hexdigest()
    assert source_manifest["validation"]["all_ready_for_learning"] is True
    assert source_manifest["validation"]["server_preview_verified"] is True
    assert source_manifest["receipt"]["request_id"] == "pilot-request-0001"
    assert source_manifest["receipt"]["sha256"] == hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    assert source_manifest["side_effect_boundary"]["training_execution_started"] is False
    assert Path(result["source_receipt_path"]).read_bytes() == receipt_path.read_bytes()

    index_text = Path(result["index_path"]).read_text(encoding="utf-8")
    assert "Report Workflow UI" in index_text
    assert source_manifest["source"]["sha256"] in index_text

    synced = sync_script.sync_report_quality_pilot_pack(
        pack_dir=Path(result["output_dir"]),
        min_records=3,
        require_ready=True,
    )
    assert synced["ok"] is True
    assert synced["ready_artifacts"] == 3
    assert synced["source_order_applied"] is True
    synced_artifacts = [
        json.loads(line)
        for line in Path(synced["output_path"]).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [artifact["artifact_id"] for artifact in synced_artifacts] == artifact_ids

    copied_receipt_path = Path(result["source_receipt_path"])
    copied_receipt_bytes = copied_receipt_path.read_bytes()
    copied_receipt_path.write_bytes(copied_receipt_bytes + b" ")
    with pytest.raises(ValueError, match="SHA-256 does not match source manifest"):
        sync_script.sync_report_quality_pilot_pack(
            pack_dir=Path(result["output_dir"]),
            min_records=3,
            require_ready=True,
        )
    copied_receipt_path.write_bytes(copied_receipt_bytes)

    source_manifest["source"]["path"] = str(Path("..") / ".." / source_path.name)
    Path(result["source_manifest_path"]).write_text(
        json.dumps(source_manifest, ensure_ascii=False),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="must not overwrite the imported source JSONL"):
        sync_script.sync_report_quality_pilot_pack(
            pack_dir=Path(result["output_dir"]),
            output_path=source_path,
            min_records=3,
            require_ready=True,
        )


def test_create_report_quality_pilot_pack_cli_imports_source_jsonl(tmp_path, capsys):
    script = _load_module(SCRIPT_PATH, "create_report_quality_pilot_pack_cli_import")
    source_path = tmp_path / "report_quality_pilot_artifacts.jsonl"
    receipt_path = tmp_path / "report_quality_pilot_receipt.json"
    artifacts = [_ready_artifact(f"rqa_{index}") for index in range(1, 4)]
    _write_jsonl(source_path, artifacts)
    _write_source_receipt(receipt_path, source_path, artifacts)

    exit_code = script.main([
        "--batch-id",
        "pilot-rqc-cli-import",
        "--output-root",
        str(tmp_path / "packs"),
        "--source-jsonl",
        str(source_path),
        "--source-receipt",
        str(receipt_path),
        "--json",
    ])

    assert exit_code == 0
    result = json.loads(capsys.readouterr().out)
    assert result["source_mode"] == "exported_ready_jsonl"
    assert result["sample_count"] == 3
    assert Path(result["source_manifest_path"]).exists()
    assert Path(result["source_receipt_path"]).exists()


def test_create_report_quality_pilot_pack_imports_verified_package(tmp_path):
    script = _load_module(SCRIPT_PATH, "create_report_quality_pilot_pack_package_import")
    sync_script = _load_module(SYNC_PATH, "sync_report_quality_pilot_pack_package_import")
    source_path = tmp_path / "report_quality_pilot_artifacts.jsonl"
    package_path = tmp_path / "report_quality_pilot_review_package.zip"
    artifact_ids = ["rqa_package_3", "rqa_package_1", "rqa_package_2"]
    artifacts = [_ready_artifact(artifact_id) for artifact_id in artifact_ids]
    _write_jsonl(source_path, artifacts)
    package_manifest = _write_source_package(package_path, source_path, artifacts)

    result = script.create_report_quality_pilot_pack(
        batch_id="pilot-rqc-package-import",
        output_root=tmp_path / "packs",
        source_package=package_path,
    )

    assert result["source_mode"] == "exported_ready_package"
    assert result["source_package_path"] == str(package_path.resolve())
    assert result["sample_count"] == 3
    source_manifest_path = Path(result["source_manifest_path"])
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    package_info = source_manifest["source"]["package"]
    assert source_manifest["source"]["artifact_ids"] == artifact_ids
    assert source_manifest["source"]["path"] == str(package_path.resolve())
    assert package_info["sha256"] == hashlib.sha256(package_path.read_bytes()).hexdigest()
    assert package_info["schema_version"] == package_manifest["schema_version"]
    assert package_info["request_id"] == source_manifest["receipt"]["request_id"]
    assert source_manifest["side_effect_boundary"]["reads_local_jsonl"] is False
    assert source_manifest["side_effect_boundary"]["reads_local_package"] is True
    package = read_pilot_review_package(package_path.read_bytes())
    assert Path(result["source_receipt_path"]).read_bytes() == package["receipt_bytes"]
    package_manifest_path = Path(result["source_package_manifest_path"])
    assert package_info["manifest_path"] == package_manifest_path.name
    assert package_manifest_path.read_bytes() == package["manifest_bytes"]

    package_path.unlink()

    synced = sync_script.sync_report_quality_pilot_pack(
        pack_dir=Path(result["output_dir"]),
        min_records=3,
        require_ready=True,
    )
    assert synced["ok"] is True
    assert synced["source_order_applied"] is True
    synced_artifacts = [
        json.loads(line)
        for line in Path(synced["output_path"]).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [artifact["artifact_id"] for artifact in synced_artifacts] == artifact_ids

    source_manifest["source"]["package"]["request_id"] = "different-request"
    source_manifest_path.write_text(json.dumps(source_manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="must match receipt.request_id"):
        sync_script.sync_report_quality_pilot_pack(
            pack_dir=Path(result["output_dir"]),
            min_records=3,
            require_ready=True,
        )


def test_create_report_quality_pilot_pack_cli_imports_verified_package(tmp_path, capsys):
    script = _load_module(SCRIPT_PATH, "create_report_quality_pilot_pack_package_cli")
    source_path = tmp_path / "report_quality_pilot_artifacts.jsonl"
    package_path = tmp_path / "report_quality_pilot_review_package.zip"
    artifacts = [_ready_artifact(f"rqa_package_{index}") for index in range(1, 4)]
    _write_jsonl(source_path, artifacts)
    _write_source_package(package_path, source_path, artifacts)

    exit_code = script.main([
        "--batch-id",
        "pilot-rqc-package-cli",
        "--output-root",
        str(tmp_path / "packs"),
        "--source-package",
        str(package_path),
        "--json",
    ])

    assert exit_code == 0
    result = json.loads(capsys.readouterr().out)
    assert result["source_mode"] == "exported_ready_package"
    assert result["source_package_path"] == str(package_path.resolve())


def test_create_report_quality_pilot_pack_rejects_tampered_or_ambiguous_package(tmp_path):
    script = _load_module(SCRIPT_PATH, "create_report_quality_pilot_pack_package_rejection")
    source_path = tmp_path / "report_quality_pilot_artifacts.jsonl"
    package_path = tmp_path / "report_quality_pilot_review_package.zip"
    artifacts = [_ready_artifact(f"rqa_package_{index}") for index in range(1, 4)]
    _write_jsonl(source_path, artifacts)
    _write_source_package(package_path, source_path, artifacts)

    package_link = tmp_path / "package-link.zip"
    package_link.symlink_to(package_path)
    with pytest.raises(ValueError, match="must not be a symlink"):
        script.create_report_quality_pilot_pack(
            batch_id="pilot-rqc-symlink-package",
            output_root=tmp_path / "packs",
            source_package=package_link,
        )

    tampered = io.BytesIO()
    with zipfile.ZipFile(package_path) as source, zipfile.ZipFile(tampered, "w") as target:
        for name in source.namelist():
            content = source.read(name)
            if name.endswith(".jsonl"):
                content += b"{}\n"
            target.writestr(name, content)
    package_path.write_bytes(tampered.getvalue())

    output_root = tmp_path / "packs"
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        script.create_report_quality_pilot_pack(
            batch_id="pilot-rqc-tampered-package",
            output_root=output_root,
            source_package=package_path,
        )
    assert not output_root.exists()

    with pytest.raises(ValueError, match="cannot be combined"):
        script.create_report_quality_pilot_pack(
            batch_id="pilot-rqc-ambiguous-package",
            output_root=output_root,
            source_package=package_path,
            source_jsonl=source_path,
        )


def test_create_report_quality_pilot_pack_rejects_preserved_package_manifest_drift(tmp_path):
    script = _load_module(SCRIPT_PATH, "create_report_quality_pilot_pack_manifest_drift")
    sync_script = _load_module(SYNC_PATH, "sync_report_quality_pilot_pack_manifest_drift")
    source_path = tmp_path / "report_quality_pilot_artifacts.jsonl"
    package_path = tmp_path / "report_quality_pilot_review_package.zip"
    artifacts = [_ready_artifact(f"rqa_package_{index}") for index in range(1, 4)]
    _write_jsonl(source_path, artifacts)
    _write_source_package(package_path, source_path, artifacts)

    result = script.create_report_quality_pilot_pack(
        batch_id="pilot-rqc-package-manifest-drift",
        output_root=tmp_path / "packs",
        source_package=package_path,
    )
    pack_dir = Path(result["output_dir"])
    manifest_path = Path(result["source_package_manifest_path"])
    original_bytes = manifest_path.read_bytes()
    manifest_path.write_bytes(original_bytes + b" ")

    with pytest.raises(ValueError, match="SHA-256 does not match source manifest"):
        sync_script.sync_report_quality_pilot_pack(
            pack_dir=pack_dir,
            min_records=3,
            require_ready=True,
        )

    package_manifest = json.loads(original_bytes)
    package_manifest["tenant_id"] = "tenant-b"
    tampered_bytes = json.dumps(package_manifest).encode("utf-8")
    manifest_path.write_bytes(tampered_bytes)
    source_manifest_path = Path(result["source_manifest_path"])
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    source_manifest["source"]["package"]["manifest_sha256"] = hashlib.sha256(
        tampered_bytes
    ).hexdigest()
    source_manifest_path.write_text(json.dumps(source_manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="tenant_id does not match source provenance"):
        sync_script.sync_report_quality_pilot_pack(
            pack_dir=pack_dir,
            min_records=3,
            require_ready=True,
        )

    manifest_path.unlink()
    manifest_path.symlink_to(package_path)
    with pytest.raises(ValueError, match="source package manifest must be a regular file"):
        sync_script.sync_report_quality_pilot_pack(
            pack_dir=pack_dir,
            min_records=3,
            require_ready=True,
        )


def test_create_report_quality_pilot_pack_reads_previous_v2_package_provenance(tmp_path):
    script = _load_module(SCRIPT_PATH, "create_report_quality_pilot_pack_v2_compat")
    sync_script = _load_module(SYNC_PATH, "sync_report_quality_pilot_pack_v2_compat")
    source_path = tmp_path / "report_quality_pilot_artifacts.jsonl"
    package_path = tmp_path / "report_quality_pilot_review_package.zip"
    artifacts = [_ready_artifact(f"rqa_package_{index}") for index in range(1, 4)]
    _write_jsonl(source_path, artifacts)
    _write_source_package(package_path, source_path, artifacts)

    result = script.create_report_quality_pilot_pack(
        batch_id="pilot-rqc-package-v2",
        output_root=tmp_path / "packs",
        source_package=package_path,
    )
    source_manifest_path = Path(result["source_manifest_path"])
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    source_manifest["schema_version"] = "decisiondoc_report_quality_pilot_source_manifest.v2"
    source_manifest["source"]["package"].pop("manifest_path")
    source_manifest_path.write_text(json.dumps(source_manifest), encoding="utf-8")
    Path(result["source_package_manifest_path"]).unlink()

    synced = sync_script.sync_report_quality_pilot_pack(
        pack_dir=Path(result["output_dir"]),
        min_records=3,
        require_ready=True,
    )
    assert synced["ok"] is True
    assert synced["source_order_applied"] is True


def test_create_report_quality_pilot_pack_rejects_invalid_source_batches(tmp_path):
    script = _load_module(SCRIPT_PATH, "create_report_quality_pilot_pack_invalid_import")
    source_path = tmp_path / "invalid.jsonl"
    output_root = tmp_path / "packs"

    _write_jsonl(source_path, [_ready_artifact("rqa_1"), _ready_artifact("rqa_2")])
    with pytest.raises(ValueError, match="between 3 and 5"):
        script.create_report_quality_pilot_pack(
            batch_id="pilot-too-small",
            output_root=output_root,
            source_jsonl=source_path,
        )
    assert not output_root.exists()

    _write_jsonl(
        source_path,
        [_ready_artifact("rqa_1"), _ready_artifact("rqa_1"), _ready_artifact("rqa_2")],
    )
    with pytest.raises(ValueError, match="artifact_ids must be unique"):
        script.create_report_quality_pilot_pack(
            batch_id="pilot-duplicate",
            output_root=output_root,
            source_jsonl=source_path,
        )

    not_ready = _ready_artifact("rqa_not_ready")
    not_ready["learning_labels"]["accepted_for_learning"] = False
    not_ready["learning_labels"]["human_review_status"] = "pending"
    _write_jsonl(source_path, [_ready_artifact("rqa_1"), _ready_artifact("rqa_2"), not_ready])
    with pytest.raises(ValueError, match="must be ready_for_learning"):
        script.create_report_quality_pilot_pack(
            batch_id="pilot-not-ready",
            output_root=output_root,
            source_jsonl=source_path,
        )

    _write_jsonl(
        source_path,
        [_ready_artifact("rqa_1"), _ready_artifact("../rqa_2"), _ready_artifact("rqa_3")],
    )
    with pytest.raises(ValueError, match="safe for a local filename"):
        script.create_report_quality_pilot_pack(
            batch_id="pilot-unsafe-artifact-id",
            output_root=output_root,
            source_jsonl=source_path,
        )

    _write_jsonl(
        source_path,
        [
            _ready_artifact("rqa_1", tenant_id="tenant-a"),
            _ready_artifact("rqa_2", tenant_id="tenant-b"),
            _ready_artifact("rqa_3", tenant_id="tenant-a"),
        ],
    )
    with pytest.raises(ValueError, match="one tenant"):
        script.create_report_quality_pilot_pack(
            batch_id="pilot-cross-tenant",
            output_root=output_root,
            source_jsonl=source_path,
        )

    valid_artifacts = [_ready_artifact(f"rqa_{index}") for index in range(1, 4)]
    _write_jsonl(source_path, valid_artifacts)
    receipt_path = tmp_path / "pilot_receipt.json"
    _write_source_receipt(receipt_path, source_path, valid_artifacts)

    with pytest.raises(ValueError, match="source_receipt is required"):
        script.create_report_quality_pilot_pack(
            batch_id="pilot-missing-receipt",
            output_root=output_root,
            source_jsonl=source_path,
        )

    receipt_payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt_payload["export"]["ordered_artifact_ids"] = list(reversed(
        receipt_payload["export"]["ordered_artifact_ids"]
    ))
    receipt_path.write_text(json.dumps(receipt_payload), encoding="utf-8")
    with pytest.raises(ValueError, match="artifact order does not match"):
        script.create_report_quality_pilot_pack(
            batch_id="pilot-stale-receipt",
            output_root=output_root,
            source_jsonl=source_path,
            source_receipt=receipt_path,
        )

    _write_source_receipt(receipt_path, source_path, valid_artifacts)
    receipt_payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt_payload["external_action_boundary"]["training_execution_authorized"] = True
    receipt_path.write_text(json.dumps(receipt_payload), encoding="utf-8")
    with pytest.raises(ValueError, match="external action boundary is invalid"):
        script.create_report_quality_pilot_pack(
            batch_id="pilot-authorized-receipt",
            output_root=output_root,
            source_jsonl=source_path,
            source_receipt=receipt_path,
        )

    _write_source_receipt(receipt_path, source_path, valid_artifacts)
    existing_pack = output_root / "pilot-existing"
    existing_pack.mkdir(parents=True)
    marker = existing_pack / "existing-review.txt"
    marker.write_text("preserve", encoding="utf-8")
    with pytest.raises(ValueError, match="output directory must be empty"):
        script.create_report_quality_pilot_pack(
            batch_id="pilot-existing",
            output_root=output_root,
            source_jsonl=source_path,
            source_receipt=receipt_path,
        )
    assert marker.read_text(encoding="utf-8") == "preserve"


def test_create_report_quality_pilot_pack_rejects_path_like_batch_id(tmp_path, capsys):
    script = _load_module(SCRIPT_PATH, "create_report_quality_pilot_pack_batch_path")

    exit_code = script.main([
        "--batch-id",
        "../outside",
        "--output-root",
        str(tmp_path),
    ])

    assert exit_code == 1
    assert "must not contain paths" in capsys.readouterr().err


def test_create_report_quality_pilot_pack_rejects_empty_batch_id(tmp_path, capsys):
    script = _load_module(SCRIPT_PATH, "create_report_quality_pilot_pack")

    exit_code = script.main([
        "--batch-id",
        " ",
        "--output-root",
        str(tmp_path),
    ])

    assert exit_code == 1
    assert "batch_id must be non-empty" in capsys.readouterr().err
