from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import run_report_quality_pilot_handoff_demo as demo


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts/run_report_quality_pilot_handoff_demo.py"


def test_report_quality_pilot_handoff_demo_completes_full_local_chain(
    monkeypatch,
) -> None:
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "openai")
    monkeypatch.setenv("DECISIONDOC_PROVIDER_GENERATION", "gemini")
    monkeypatch.setenv("DECISIONDOC_PROVIDER_ATTACHMENT", "claude")
    monkeypatch.setenv("DECISIONDOC_PROVIDER_VISUAL", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "local-demo-openai-key")
    monkeypatch.setenv("GEMINI_API_KEY", "local-demo-gemini-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "local-demo-anthropic-key")

    receipt = demo.run_demo()

    assert receipt["status"] == "passed"
    assert receipt["execution_mode"] == {
        "provider": "mock",
        "storage": "temporary_local",
        "runtime_data_persisted": False,
        "review_evidence": "simulated_demo_input",
        "human_review_claimed": False,
    }
    assert receipt["api_pilot_package"]["artifact_count"] == 3
    assert receipt["api_pilot_package"]["ready_artifact_count"] == 3
    assert receipt["api_pilot_package"]["package_validation_passed"] is True
    assert len(receipt["api_pilot_package"]["ordered_artifact_ids"]) == 3
    assert receipt["local_review"]["source_bound"] is True
    assert receipt["local_review"]["decision_count"] == 3
    assert receipt["local_review"]["ready_decisions"] == 3
    assert receipt["local_review"]["simulated"] is True
    assert receipt["handoff"]["artifact_count"] == 3
    assert receipt["handoff"]["exact_browser_summary_verified"] is True
    assert receipt["handoff"]["source_bound"] is True
    assert receipt["handoff"]["training_authorized"] is False
    assert receipt["handoff"]["temporary_artifacts_retained"] is False
    assert receipt["completed_stages"][-1] == "browser_summary_verified"
    assert all(value is False for value in receipt["external_actions"].values())
    assert os.environ["DECISIONDOC_PROVIDER"] == "openai"
    assert os.environ["DECISIONDOC_PROVIDER_GENERATION"] == "gemini"
    assert os.environ["DECISIONDOC_PROVIDER_ATTACHMENT"] == "claude"
    assert os.environ["DECISIONDOC_PROVIDER_VISUAL"] == "openai"
    assert os.environ["OPENAI_API_KEY"] == "local-demo-openai-key"
    assert os.environ["GEMINI_API_KEY"] == "local-demo-gemini-key"
    assert os.environ["ANTHROPIC_API_KEY"] == "local-demo-anthropic-key"


def test_report_quality_pilot_handoff_demo_cli_writes_once(tmp_path: Path) -> None:
    receipt_path = tmp_path / "pilot-handoff-demo.json"
    environment = os.environ.copy()
    environment.update(
        {
            "DECISIONDOC_PROVIDER": "openai",
            "DECISIONDOC_PROVIDER_GENERATION": "gemini",
            "DECISIONDOC_PROVIDER_ATTACHMENT": "claude",
            "DECISIONDOC_PROVIDER_VISUAL": "openai",
            "OPENAI_API_KEY": "must-not-appear-in-demo-receipt",
        }
    )
    command = [sys.executable, str(SCRIPT_PATH), "--output", str(receipt_path)]

    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    stdout_receipt = json.loads(completed.stdout)
    persisted_bytes = receipt_path.read_bytes()
    assert json.loads(persisted_bytes) == stdout_receipt
    assert stdout_receipt["execution_mode"]["provider"] == "mock"
    assert stdout_receipt["execution_mode"]["human_review_claimed"] is False
    assert stdout_receipt["handoff"]["exact_browser_summary_verified"] is True
    assert "must-not-appear-in-demo-receipt" not in completed.stdout
    assert "must-not-appear-in-demo-receipt" not in completed.stderr

    repeated = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert repeated.returncode == 1
    assert "refusing to overwrite existing demo receipt" in repeated.stdout
    assert receipt_path.read_bytes() == persisted_bytes


def test_report_quality_pilot_handoff_demo_rejects_unsafe_output_before_run(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        demo,
        "run_demo",
        lambda: pytest.fail("demo must not run for an invalid receipt output"),
    )

    wrong_extension = tmp_path / "receipt.txt"
    assert demo.main(["--output", str(wrong_extension)]) == 1
    assert not wrong_extension.exists()

    target = tmp_path / "target.json"
    receipt_link = tmp_path / "receipt.json"
    receipt_link.symlink_to(target)
    assert demo.main(["--output", str(receipt_link)]) == 1
    assert receipt_link.is_symlink()
    assert not target.exists()
