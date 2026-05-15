from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/create_report_quality_pilot_pack.py"
VALIDATOR_PATH = REPO_ROOT / "docs/specs/report_quality_learning/validate_correction_artifact.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


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
