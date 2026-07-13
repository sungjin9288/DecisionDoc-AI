from __future__ import annotations

import importlib.util
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
    output_path = Path(result["output_path"])
    lines = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 3
    assert lines[0]["before"]["planning_summary"] == "AI 초안은 문제 정의와 실행 계획의 연결이 약함"
    assert result["side_effect_boundary"]["provider_fine_tune_api_called"] is False


def test_sync_report_quality_pilot_pack_require_ready_fails_for_pending_drafts(tmp_path):
    sync_script = _load_module(SYNC_SCRIPT_PATH, "sync_report_quality_pilot_pack")
    pack_dir = _create_pack(tmp_path)

    result = sync_script.sync_report_quality_pilot_pack(
        pack_dir=pack_dir,
        min_records=3,
        require_ready=True,
    )

    assert result["ok"] is False
    assert result["ready_artifacts"] == 0
    assert "not all artifacts are ready_for_learning" in "\n".join(result["errors"])
    assert Path(result["output_path"]).exists()


def test_sync_report_quality_pilot_pack_rejects_source_manifest_drift(tmp_path):
    sync_script = _load_module(SYNC_SCRIPT_PATH, "sync_report_quality_pilot_pack_manifest_drift")
    pack_dir = _create_pack(tmp_path)
    manifest = {
        "source": {
            "artifact_ids": [
                "pilot-rqc-sync_sample_001",
                "pilot-rqc-sync_sample_002",
            ]
        }
    }
    (pack_dir / "SOURCE_MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="source order does not match drafts"):
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
    assert "FAIL report quality pilot pack synced" in out
    assert "not all artifacts are ready_for_learning" in out
