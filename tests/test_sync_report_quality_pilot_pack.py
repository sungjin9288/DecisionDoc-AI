from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
CREATE_SCRIPT_PATH = REPO_ROOT / "scripts/create_report_quality_pilot_pack.py"
SYNC_SCRIPT_PATH = REPO_ROOT / "scripts/sync_report_quality_pilot_pack.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _create_pack(tmp_path: Path) -> Path:
    create_script = _load_module(CREATE_SCRIPT_PATH, "create_report_quality_pilot_pack")
    result = create_script.create_report_quality_pilot_pack(
        batch_id="pilot-rqc-sync",
        output_root=tmp_path,
        sample_count=3,
        reviewer="pm-reviewer",
    )
    return Path(result["output_dir"])


def test_sync_report_quality_pilot_pack_writes_jsonl_from_drafts(tmp_path):
    sync_script = _load_module(SYNC_SCRIPT_PATH, "sync_report_quality_pilot_pack")
    pack_dir = _create_pack(tmp_path)
    first_draft = pack_dir / "drafts/pilot-rqc-sync_sample_001.json"
    payload = json.loads(first_draft.read_text(encoding="utf-8"))
    payload["before"]["planning_summary"] = "AI 초안은 문제 정의와 실행 계획의 연결이 약함"
    first_draft.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    result = sync_script.sync_report_quality_pilot_pack(pack_dir=pack_dir, min_records=3)

    assert result["ok"] is True
    assert result["artifact_count"] == 3
    assert result["ready_artifacts"] == 0
    assert result["output_written"] is True
    output_path = Path(result["output_path"])
    assert result["output_sha256"] == hashlib.sha256(output_path.read_bytes()).hexdigest()
    lines = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 3
    assert lines[0]["before"]["planning_summary"] == "AI 초안은 문제 정의와 실행 계획의 연결이 약함"
    assert result["side_effect_boundary"]["provider_fine_tune_api_called"] is False


def test_sync_report_quality_pilot_pack_require_ready_fails_for_pending_drafts(tmp_path):
    sync_script = _load_module(SYNC_SCRIPT_PATH, "sync_report_quality_pilot_pack")
    pack_dir = _create_pack(tmp_path)
    output_path = pack_dir / "pilot-rqc-sync-drafts.jsonl"
    original_output = output_path.read_bytes()
    first_draft = pack_dir / "drafts/pilot-rqc-sync_sample_001.json"
    first_draft.write_text(first_draft.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    result = sync_script.sync_report_quality_pilot_pack(
        pack_dir=pack_dir,
        min_records=3,
        require_ready=True,
    )

    assert result["ok"] is False
    assert result["ready_artifacts"] == 0
    assert "not all artifacts are ready_for_learning" in "\n".join(result["errors"])
    assert result["output_written"] is False
    assert result["output_sha256"] is None
    assert result["side_effect_boundary"]["writes_local_jsonl"] is False
    assert output_path.read_bytes() == original_output


def test_sync_failure_does_not_create_or_redirect_output(tmp_path):
    sync_script = _load_module(SYNC_SCRIPT_PATH, "sync_report_quality_pilot_pack_output_guard")
    pack_dir = _create_pack(tmp_path)
    blocked_output = tmp_path / "blocked.jsonl"

    result = sync_script.sync_report_quality_pilot_pack(
        pack_dir=pack_dir,
        output_path=blocked_output,
        min_records=3,
        require_ready=True,
    )

    assert result["ok"] is False
    assert result["output_written"] is False
    assert not blocked_output.exists()

    symlink_output = tmp_path / "linked.jsonl"
    symlink_output.symlink_to("target.jsonl")
    with pytest.raises(ValueError, match="symlink output files are not allowed"):
        sync_script.sync_report_quality_pilot_pack(
            pack_dir=pack_dir,
            output_path=symlink_output,
        )

    with pytest.raises(ValueError, match="output path must use the .jsonl extension"):
        sync_script.sync_report_quality_pilot_pack(
            pack_dir=pack_dir,
            output_path=tmp_path / "not-jsonl.json",
        )


def test_sync_report_quality_pilot_pack_rejects_source_manifest_drift(tmp_path):
    sync_script = _load_module(SYNC_SCRIPT_PATH, "sync_report_quality_pilot_pack_manifest_drift")
    pack_dir = _create_pack(tmp_path)
    manifest = {
        "report_type": "report_quality_pilot_source_manifest",
        "schema_version": "decisiondoc_report_quality_pilot_source_manifest.v1",
        "batch_id": "pilot-rqc-sync",
        "source": {
            "artifact_count": 2,
            "artifact_ids": [
                "pilot-rqc-sync_sample_001",
                "pilot-rqc-sync_sample_002",
            ],
            "format": "jsonl",
            "order_preserved": True,
            "sha256": "a" * 64,
            "tenant_id": "system",
        },
        "validation": {
            "all_valid": True,
            "all_ready_for_learning": True,
            "unique_artifact_ids": True,
            "single_tenant": True,
        },
        "side_effect_boundary": {
            "external_dataset_upload_started": False,
            "provider_fine_tune_api_called": False,
            "provider_job_created": False,
            "training_execution_started": False,
            "model_promotion_started": False,
        },
    }
    (pack_dir / "SOURCE_MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="source order does not match drafts"):
        sync_script.sync_report_quality_pilot_pack(pack_dir=pack_dir, min_records=3)

    manifest["source"]["artifact_count"] = 3
    manifest["source"]["artifact_ids"].append("pilot-rqc-sync_sample_003")
    manifest["side_effect_boundary"]["training_execution_started"] = True
    (pack_dir / "SOURCE_MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="no-training side-effect boundary is invalid"):
        sync_script.sync_report_quality_pilot_pack(pack_dir=pack_dir, min_records=3)

    external_manifest = tmp_path / "external-source-manifest.json"
    external_manifest.write_text(json.dumps(manifest), encoding="utf-8")
    source_manifest_path = pack_dir / "SOURCE_MANIFEST.json"
    source_manifest_path.unlink()
    source_manifest_path.symlink_to(external_manifest)
    with pytest.raises(ValueError, match="symlink source manifests are not allowed"):
        sync_script.sync_report_quality_pilot_pack(pack_dir=pack_dir, min_records=3)


def test_sync_report_quality_pilot_pack_cli_outputs_json(tmp_path, capsys):
    sync_script = _load_module(SYNC_SCRIPT_PATH, "sync_report_quality_pilot_pack")
    pack_dir = _create_pack(tmp_path)

    exit_code = sync_script.main([str(pack_dir), "--min-records", "3", "--json"])

    assert exit_code == 0
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is True
    assert result["artifact_count"] == 3
    assert Path(result["output_path"]).exists()


def test_sync_report_quality_pilot_pack_cli_require_ready_returns_nonzero(tmp_path, capsys):
    sync_script = _load_module(SYNC_SCRIPT_PATH, "sync_report_quality_pilot_pack")
    pack_dir = _create_pack(tmp_path)

    exit_code = sync_script.main([str(pack_dir), "--require-ready", "--min-records", "3"])

    assert exit_code == 1
    out = capsys.readouterr().out
    assert "FAIL report quality pilot pack sync blocked" in out
    assert "output_written=false" in out
    assert "not all artifacts are ready_for_learning" in out
