from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts import check_completion_readiness as readiness
from scripts import check_completion_readiness_result as checker


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _blocked_readiness_payload(tmp_path: Path) -> dict[str, object]:
    return readiness.check_completion_readiness(
        env={},
        prod_env_file=tmp_path / ".env.prod",
    )


def test_check_completion_readiness_result_accepts_current_receipt(tmp_path: Path) -> None:
    receipt_path = tmp_path / "completion-readiness.json"
    _write_json(receipt_path, _blocked_readiness_payload(tmp_path))

    result = checker.check_completion_readiness_result(receipt_path)

    assert result["schema_version"] == "decisiondoc.completion_readiness_check.v1"
    assert result["ok"] is True
    assert [item["id"] for item in result["milestones"]] == ["M1", "M2", "M6"]
    assert "provider API execution" in result["external_actions_excluded"]


def test_check_completion_readiness_result_rejects_schema_drift(tmp_path: Path) -> None:
    receipt_path = tmp_path / "completion-readiness.json"
    payload = _blocked_readiness_payload(tmp_path)
    payload["schema_version"] = "unexpected"
    _write_json(receipt_path, payload)

    try:
        checker.check_completion_readiness_result(receipt_path)
    except ValueError as exc:
        message = str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected schema drift to be rejected")

    assert "schema_version mismatch" in message


def test_check_completion_readiness_result_rejects_milestone_order_drift(tmp_path: Path) -> None:
    receipt_path = tmp_path / "completion-readiness.json"
    payload = _blocked_readiness_payload(tmp_path)
    milestones = list(payload["milestones"])
    payload["milestones"] = [milestones[1], milestones[0], milestones[2]]
    _write_json(receipt_path, payload)

    completed = subprocess.run(
        ["python3", "scripts/check_completion_readiness_result.py", str(receipt_path)],
        cwd=readiness.REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    result = json.loads(completed.stdout)
    assert result["ok"] is False
    assert "milestone id mismatch" in result["error"]


def test_check_completion_readiness_result_writes_check_receipt(tmp_path: Path) -> None:
    receipt_path = tmp_path / "completion-readiness.json"
    check_path = tmp_path / "completion-readiness-check.json"
    _write_json(receipt_path, _blocked_readiness_payload(tmp_path))

    completed = subprocess.run(
        [
            "python3",
            "scripts/check_completion_readiness_result.py",
            str(receipt_path),
            "--write-result",
            "--result-path",
            str(check_path),
        ],
        cwd=readiness.REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert check_path.exists()
    result = json.loads(check_path.read_text(encoding="utf-8"))
    assert result["ok"] is True
    assert result["schema_version"] == "decisiondoc.completion_readiness_check.v1"


def test_check_completion_readiness_result_requires_write_result_for_custom_result_path(tmp_path: Path) -> None:
    receipt_path = tmp_path / "completion-readiness.json"
    _write_json(receipt_path, _blocked_readiness_payload(tmp_path))

    completed = subprocess.run(
        [
            "python3",
            "scripts/check_completion_readiness_result.py",
            str(receipt_path),
            "--result-path",
            str(tmp_path / "check.json"),
        ],
        cwd=readiness.REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    result = json.loads(completed.stdout)
    assert result["ok"] is False
    assert "--result-path requires --write-result" in result["error"]
