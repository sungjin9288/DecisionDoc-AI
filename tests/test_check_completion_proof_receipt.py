from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts import check_completion_proof_receipt as checker
from scripts.check_completion_readiness import EXCLUDED_EXTERNAL_ACTIONS, MILESTONE_COMMANDS

MILESTONE_TITLES = {
    "M1": "Live provider proof",
    "M2": "G2B live procurement smoke",
    "M6": "Deployment and post-deploy smoke proof",
}


def _valid_receipt(*, milestone_id: str = "M1", command: str | None = None) -> dict[str, object]:
    return {
        "schema_version": "decisiondoc.completion_proof_receipt.v1",
        "scope": "proof receipt only; documents external proof result without executing external actions",
        "milestone_id": milestone_id,
        "title": MILESTONE_TITLES[milestone_id],
        "status": "passed",
        "command": command or MILESTONE_COMMANDS[milestone_id][0],
        "executed_at_utc": "2026-07-09T01:02:03Z",
        "environment_boundary": "approved manual live provider workflow; secret values redacted",
        "evidence_summary": f"{milestone_id} completion proof passed in the approved environment.",
        "evidence_refs": [
            "https://github.com/sungjin9288/DecisionDoc-AI/actions/runs/123",
        ],
        "remaining_limitations": [
            "This receipt covers M1 only and does not prove G2B or deployment smoke.",
        ],
        "secret_values_recorded": False,
        "excluded_external_actions": list(EXCLUDED_EXTERNAL_ACTIONS),
    }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_completion_proof_receipt_accepts_current_contract(tmp_path: Path) -> None:
    receipt_path = tmp_path / "m1-proof.json"
    _write_json(receipt_path, _valid_receipt())

    result = checker.check_completion_proof_receipt(receipt_path)

    assert result["schema_version"] == "decisiondoc.completion_proof_receipt_check.v1"
    assert result["ok"] is True
    assert result["summary"]["milestone_id"] == "M1"
    assert result["summary"]["status"] == "passed"
    assert "provider API execution" in result["external_actions_excluded"]


def test_completion_proof_receipt_accepts_runbook_commands(tmp_path: Path) -> None:
    runbook_commands = (
        ("M1", "gh workflow run live.yml --ref main -f provider=openai"),
        ("M1", "gh workflow run live.yml --ref main -f provider=gemini"),
        ("M1", "gh workflow run live.yml --ref main -f provider=claude"),
        ("M1", "gh workflow run live.yml --ref main -f provider='openai,gemini'"),
        ("M2", "python3 scripts/run_stage_procurement_smoke.py --env-file .env.prod --preflight"),
        ("M2", "python3 scripts/run_stage_procurement_smoke.py --env-file .env.prod"),
        ("M6", "python3 scripts/run_deployed_smoke.py --env-file .env.prod --preflight"),
        ("M6", "python3 scripts/run_deployed_smoke.py --env-file .env.prod"),
    )

    for milestone_id, command in runbook_commands:
        receipt_path = tmp_path / f"{milestone_id}-{len(command)}-proof.json"
        _write_json(receipt_path, _valid_receipt(milestone_id=milestone_id, command=command))

        result = checker.check_completion_proof_receipt(receipt_path)

        assert result["ok"] is True
        assert result["summary"]["milestone_id"] == milestone_id


def test_completion_proof_receipt_rejects_unapproved_command(tmp_path: Path) -> None:
    receipt_path = tmp_path / "m1-proof.json"
    payload = _valid_receipt()
    payload["command"] = "python3 arbitrary_script.py"
    _write_json(receipt_path, payload)

    completed = subprocess.run(
        ["python3", "scripts/check_completion_proof_receipt.py", str(receipt_path)],
        cwd=checker.ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    result = json.loads(completed.stdout)
    assert result["ok"] is False
    assert "not an allowed milestone command" in result["error"]


def test_completion_proof_receipt_rejects_secret_values(tmp_path: Path) -> None:
    receipt_path = tmp_path / "m1-proof.json"
    payload = _valid_receipt()
    payload["evidence_summary"] = "accidentally logged sk-1234567890abcdef"
    _write_json(receipt_path, payload)

    completed = subprocess.run(
        ["python3", "scripts/check_completion_proof_receipt.py", str(receipt_path)],
        cwd=checker.ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    result = json.loads(completed.stdout)
    assert result["ok"] is False
    assert "secret value" in result["error"]


def test_completion_proof_receipt_template_is_safe_but_not_completed() -> None:
    completed = subprocess.run(
        ["python3", "scripts/check_completion_proof_receipt.py", "--print-template", "M2"],
        cwd=checker.ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["milestone_id"] == "M2"
    assert payload["command"] == MILESTONE_COMMANDS["M2"][0]
    assert payload["secret_values_recorded"] is False
    assert "sk-" not in completed.stdout

    try:
        checker._validate_receipt(payload)
    except ValueError as exc:
        message = str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected unfinished template to be rejected")
    assert "placeholder" in message


def test_completion_proof_receipt_writes_check_result(tmp_path: Path) -> None:
    receipt_path = tmp_path / "m1-proof.json"
    check_path = tmp_path / "m1-proof-check.json"
    _write_json(receipt_path, _valid_receipt())

    completed = subprocess.run(
        [
            "python3",
            "scripts/check_completion_proof_receipt.py",
            str(receipt_path),
            "--write-result",
            "--result-path",
            str(check_path),
        ],
        cwd=checker.ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert check_path.exists()
    result = json.loads(check_path.read_text(encoding="utf-8"))
    assert result["ok"] is True
    assert result["schema_version"] == "decisiondoc.completion_proof_receipt_check.v1"
