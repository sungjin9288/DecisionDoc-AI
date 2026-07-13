from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from scripts.run_report_quality_learning_demo import EXCLUDED_EXTERNAL_ACTIONS, run_demo


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts/run_report_quality_learning_demo.py"


def test_report_quality_learning_demo_completes_local_flow(monkeypatch) -> None:
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "openai")
    monkeypatch.setenv("DECISIONDOC_PROVIDER_GENERATION", "gemini")
    monkeypatch.setenv("DECISIONDOC_PROVIDER_ATTACHMENT", "claude")
    monkeypatch.setenv("DECISIONDOC_PROVIDER_VISUAL", "openai")

    receipt = run_demo()

    assert receipt["status"] == "passed"
    assert receipt["execution_mode"] == {
        "provider": "mock",
        "storage": "temporary_local",
        "runtime_data_persisted": False,
    }
    assert receipt["workflow"]["status"] == "final_approved"
    assert receipt["workflow"]["slide_count"] == 2
    assert receipt["quality_correction"]["ready_for_learning"] is True
    assert receipt["quality_correction"]["ready_artifact_count"] == 1
    assert receipt["quality_correction"]["exported_record_count"] == 1
    assert receipt["quality_correction"]["export_validation_passed"] is True
    assert receipt["quality_correction"]["preview_bound_save"] is True
    assert len(receipt["quality_correction"]["preview_fingerprint"]) == 64
    assert receipt["completed_stages"][-1] == "jsonl_export_validated"
    assert receipt["external_actions"] == {action: False for action in EXCLUDED_EXTERNAL_ACTIONS}
    assert os.environ["DECISIONDOC_PROVIDER"] == "openai"
    assert os.environ["DECISIONDOC_PROVIDER_GENERATION"] == "gemini"
    assert os.environ["DECISIONDOC_PROVIDER_ATTACHMENT"] == "claude"
    assert os.environ["DECISIONDOC_PROVIDER_VISUAL"] == "openai"


def test_report_quality_learning_demo_cli_writes_matching_receipt(tmp_path: Path) -> None:
    receipt_path = tmp_path / "receipt.json"
    environment = os.environ.copy()
    environment.update(
        {
            "DECISIONDOC_PROVIDER": "openai",
            "DECISIONDOC_PROVIDER_GENERATION": "gemini",
            "DECISIONDOC_PROVIDER_ATTACHMENT": "claude",
            "DECISIONDOC_PROVIDER_VISUAL": "openai",
        }
    )

    completed = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--output", str(receipt_path)],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    stdout_receipt = json.loads(completed.stdout)
    persisted_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert persisted_receipt == stdout_receipt
    assert persisted_receipt["status"] == "passed"
    assert persisted_receipt["execution_mode"]["provider"] == "mock"
    assert persisted_receipt["quality_correction"]["preview_bound_save"] is True
    assert len(persisted_receipt["quality_correction"]["preview_fingerprint"]) == 64
    assert all(value is False for value in persisted_receipt["external_actions"].values())
