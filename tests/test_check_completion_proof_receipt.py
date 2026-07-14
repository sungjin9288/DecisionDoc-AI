from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts import check_completion_proof_receipt as checker
from scripts.check_completion_readiness import MILESTONE_COMMANDS

MILESTONE_TITLES = {
    "M1": "Live provider proof",
    "M2": "G2B live procurement smoke",
    "M6": "Deployment and post-deploy smoke proof",
}


def _valid_receipt(*, milestone_id: str = "M1", command: str | None = None) -> dict[str, object]:
    resolved_command = command or MILESTONE_COMMANDS[milestone_id][0]
    return {
        "schema_version": "decisiondoc.completion_proof_receipt.v2",
        "scope": "proof receipt only; documents approved external proof without executing additional external actions",
        "milestone_id": milestone_id,
        "title": MILESTONE_TITLES[milestone_id],
        "status": "passed",
        "command": resolved_command,
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
        "excluded_external_actions": checker.excluded_external_actions_for(milestone_id, resolved_command),
    }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_completion_proof_receipt_accepts_current_contract(tmp_path: Path) -> None:
    receipt_path = tmp_path / "m1-proof.json"
    _write_json(receipt_path, _valid_receipt())

    result = checker.check_completion_proof_receipt(receipt_path)

    assert result["schema_version"] == "decisiondoc.completion_proof_receipt_check.v2"
    assert result["ok"] is True
    assert result["summary"]["milestone_id"] == "M1"
    assert result["summary"]["status"] == "passed"
    assert "provider API execution" not in result["external_actions_excluded"]
    assert "G2B live API execution" in result["external_actions_excluded"]


def test_completion_proof_receipt_excludes_only_unexecuted_actions(tmp_path: Path) -> None:
    executed_actions = {
        "M1": ("provider API execution", MILESTONE_COMMANDS["M1"][0]),
        "M2": ("G2B live API execution", MILESTONE_COMMANDS["M2"][1]),
        "M6": ("AWS runtime execution", MILESTONE_COMMANDS["M6"][1]),
    }

    for milestone_id, (executed_action, command) in executed_actions.items():
        receipt_path = tmp_path / f"{milestone_id}-proof.json"
        payload = _valid_receipt(milestone_id=milestone_id, command=command)
        _write_json(receipt_path, payload)

        result = checker.check_completion_proof_receipt(receipt_path)

        assert executed_action not in result["external_actions_excluded"]
        assert len(result["external_actions_excluded"]) == 9


def test_completion_proof_receipt_preflight_keeps_runtime_action_excluded(tmp_path: Path) -> None:
    for milestone_id, expected_action in (
        ("M2", "G2B live API execution"),
        ("M6", "AWS runtime execution"),
    ):
        receipt_path = tmp_path / f"{milestone_id}-preflight-proof.json"
        payload = _valid_receipt(milestone_id=milestone_id)
        _write_json(receipt_path, payload)

        result = checker.check_completion_proof_receipt(receipt_path)

        assert expected_action in result["external_actions_excluded"]
        assert len(result["external_actions_excluded"]) == 10


def test_completion_proof_receipt_rejects_readiness_exclusion_list(tmp_path: Path) -> None:
    receipt_path = tmp_path / "m1-proof.json"
    payload = _valid_receipt()
    payload["excluded_external_actions"] = [
        "provider API execution",
        *payload["excluded_external_actions"],
    ]
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
    assert "excluded_external_actions drifted" in result["error"]


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
    assert result["schema_version"] == "decisiondoc.completion_proof_receipt_check.v2"


def test_completion_proof_evidence_helpers_strip_url_credentials_and_query() -> None:
    sensitive_url = "https://operator:password@stage.example.com/path?serviceKey=secret#fragment"

    assert checker.safe_evidence_host(sensitive_url) == "stage.example.com"
    assert checker.safe_evidence_identifier(sensitive_url, fallback="configured") == "url-host:stage.example.com"
    assert checker.safe_evidence_identifier("20260405001-00", fallback="configured") == "20260405001-00"
