from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_script_module(module_name: str, relative_path: str):
    path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _write_deployment_env(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "ALLOWED_ORIGINS=https://admin.decisiondoc.kr",
                "DECISIONDOC_API_KEYS=deployment-secret-api-key",
                "DECISIONDOC_PROVIDER=mock",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_run_deployed_smoke_uses_env_file_defaults(tmp_path: Path, monkeypatch) -> None:
    runner = _load_script_module("decisiondoc_run_deployed_smoke_defaults", "scripts/run_deployed_smoke.py")
    env_file = tmp_path / ".env.prod"
    env_file.write_text(
        "\n".join(
            [
                "ALLOWED_ORIGINS=https://dawool.decisiondoc.kr",
                "DECISIONDOC_API_KEYS=runtime-key-1,runtime-key-2",
                "DECISIONDOC_PROVIDER=openai",
                "SMOKE_TIMEOUT_SEC=75",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    compose_file = tmp_path / "docker-compose.prod.yml"
    compose_file.write_text("services: {}\n", encoding="utf-8")
    calls: list[list[str]] = []

    def _fake_run(command, cwd=None, check=False):
        _ = cwd, check
        calls.append(list(command))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(runner.subprocess, "run", _fake_run)

    result = runner.run_deployed_smoke(
        env_file=env_file,
        compose_file=compose_file,
        service="app",
    )

    assert result == 0
    assert calls == [
        [
            "docker",
            "compose",
            "--env-file",
            str(env_file),
            "-f",
            str(compose_file),
            "exec",
            "-T",
            "-e",
            "SMOKE_BASE_URL=https://dawool.decisiondoc.kr",
            "-e",
            "SMOKE_API_KEY=runtime-key-1",
            "-e",
            "SMOKE_PROVIDER=openai",
            "-e",
            "SMOKE_TIMEOUT_SEC=75",
            "app",
            "python",
            "scripts/smoke.py",
        ]
    ]


def test_run_deployed_smoke_allows_cli_overrides(tmp_path: Path, monkeypatch) -> None:
    runner = _load_script_module("decisiondoc_run_deployed_smoke_override", "scripts/run_deployed_smoke.py")
    env_file = tmp_path / ".env.prod"
    env_file.write_text(
        "\n".join(
            [
                "ALLOWED_ORIGINS=https://admin.decisiondoc.kr",
                "DECISIONDOC_API_KEYS=runtime-key-1",
                "DECISIONDOC_PROVIDER=mock",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    compose_file = tmp_path / "docker-compose.prod.yml"
    compose_file.write_text("services: {}\n", encoding="utf-8")
    calls: list[list[str]] = []

    def _fake_run(command, cwd=None, check=False):
        _ = cwd, check
        calls.append(list(command))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(runner.subprocess, "run", _fake_run)

    result = runner.run_deployed_smoke(
        env_file=env_file,
        compose_file=compose_file,
        service="web",
        base_url="https://custom.example.com",
        api_key="override-key",
        provider="gemini",
    )

    assert result == 0
    command = calls[0]
    assert "SMOKE_BASE_URL=https://custom.example.com" in command
    assert "SMOKE_API_KEY=override-key" in command
    assert "SMOKE_PROVIDER=gemini" in command
    assert "SMOKE_TIMEOUT_SEC=60" in command
    assert command[-3:] == ["web", "python", "scripts/smoke.py"]


def test_preflight_uses_legacy_api_key_fallback(tmp_path: Path, capsys) -> None:
    runner = _load_script_module("decisiondoc_run_deployed_smoke_preflight", "scripts/run_deployed_smoke.py")
    env_file = tmp_path / ".env.prod"
    env_file.write_text(
        "\n".join(
            [
                "ALLOWED_ORIGINS=https://admin.decisiondoc.kr",
                "DECISIONDOC_API_KEY=legacy-runtime-key",
                "DECISIONDOC_PROVIDER=openai",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = runner.main(
        [
            "--env-file",
            str(env_file),
            "--preflight",
        ]
    )

    captured = capsys.readouterr().out
    assert result == 0
    assert "[ok] SMOKE_BASE_URL host=admin.decisiondoc.kr" in captured
    assert "[ok] SMOKE_API_KEY" in captured
    assert "[ok] SMOKE_PROVIDER=openai" in captured
    assert "[ok] SMOKE_TIMEOUT_SEC=60" in captured
    assert "- POST /generate/with-attachments (no key) -> 401" in captured
    assert "- POST /generate/with-attachments (auth) -> 200" in captured
    assert "- POST /generate/from-documents (auth) -> 200" in captured


def test_run_deployed_smoke_honors_timeout_override(tmp_path: Path, monkeypatch) -> None:
    runner = _load_script_module("decisiondoc_run_deployed_smoke_timeout_override", "scripts/run_deployed_smoke.py")
    env_file = tmp_path / ".env.prod"
    env_file.write_text(
        "\n".join(
            [
                "ALLOWED_ORIGINS=https://admin.decisiondoc.kr",
                "DECISIONDOC_API_KEYS=runtime-key-1",
                "DECISIONDOC_PROVIDER=openai",
                "SMOKE_TIMEOUT_SEC=75",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    compose_file = tmp_path / "docker-compose.prod.yml"
    compose_file.write_text("services: {}\n", encoding="utf-8")
    calls: list[list[str]] = []

    def _fake_run(command, cwd=None, check=False):
        _ = cwd, check
        calls.append(list(command))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(runner.subprocess, "run", _fake_run)

    result = runner.run_deployed_smoke(
        env_file=env_file,
        compose_file=compose_file,
        service="app",
        timeout_sec="90",
    )

    assert result == 0
    assert "SMOKE_TIMEOUT_SEC=90" in calls[0]


def test_print_env_template_lists_document_upload_smoke_checks(tmp_path: Path, capsys) -> None:
    runner = _load_script_module("decisiondoc_run_deployed_smoke_env_template", "scripts/run_deployed_smoke.py")
    env_file = tmp_path / ".env.prod"
    compose_file = tmp_path / "docker-compose.prod.yml"
    compose_file.write_text("services: {}\n", encoding="utf-8")

    result = runner.main(
        [
            "--env-file",
            str(env_file),
            "--compose-file",
            str(compose_file),
            "--print-env-template",
        ]
    )

    captured = capsys.readouterr().out
    assert result == 0
    assert "Smoke checks" in captured
    assert "- POST /generate/export-edited PDF (auth) -> 200" in captured
    assert "- POST /generate/export-edited HWPX (auth) -> 200" in captured
    assert "- POST /generate/with-attachments (no key) -> 401" in captured
    assert "- POST /generate/with-attachments (auth) -> 200" in captured
    assert "- POST /generate/from-documents (no key) -> 401" in captured
    assert "- POST /generate/from-documents (auth) -> 200" in captured


def test_deployed_preflight_writes_valid_blocked_proof_receipt_without_secrets(tmp_path: Path) -> None:
    runner = _load_script_module("decisiondoc_run_deployed_smoke_receipt_preflight", "scripts/run_deployed_smoke.py")
    env_file = tmp_path / ".env.prod"
    receipt_path = tmp_path / "m6-preflight.json"
    _write_deployment_env(env_file)

    result = runner.main(
        [
            "--env-file",
            str(env_file),
            "--preflight",
            "--proof-receipt",
            str(receipt_path),
        ]
    )

    receipt_text = receipt_path.read_text(encoding="utf-8")
    receipt = json.loads(receipt_text)
    assert result == 0
    assert receipt["status"] == "blocked"
    assert receipt["command"].endswith("--preflight")
    assert "AWS runtime execution" in receipt["excluded_external_actions"]
    assert "deployment-secret-api-key" not in receipt_text
    assert runner.proof_receipts.check_completion_proof_receipt(receipt_path)["ok"] is True


def test_deployed_preflight_records_missing_inputs_before_returning_error(tmp_path: Path, capsys) -> None:
    runner = _load_script_module("decisiondoc_run_deployed_smoke_receipt_blocked", "scripts/run_deployed_smoke.py")
    env_file = tmp_path / ".env.prod"
    receipt_path = tmp_path / "m6-blocked.json"
    env_file.write_text("DECISIONDOC_PROVIDER=mock\n", encoding="utf-8")

    result = runner.main(
        [
            "--env-file",
            str(env_file),
            "--preflight",
            "--proof-receipt",
            str(receipt_path),
        ]
    )

    output = capsys.readouterr().out
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert result == 1
    assert "[missing] SMOKE_BASE_URL" in output
    assert "[missing] SMOKE_API_KEY" in output
    assert receipt["status"] == "blocked"
    assert "missing required inputs" in receipt["evidence_summary"]
    assert "AWS runtime execution" in receipt["excluded_external_actions"]
    assert runner.proof_receipts.check_completion_proof_receipt(receipt_path)["ok"] is True


def test_deployed_smoke_writes_failed_proof_receipt_before_returning_error(tmp_path: Path, monkeypatch) -> None:
    runner = _load_script_module("decisiondoc_run_deployed_smoke_receipt_failure", "scripts/run_deployed_smoke.py")
    env_file = tmp_path / ".env.prod"
    compose_file = tmp_path / "docker-compose.prod.yml"
    receipt_path = tmp_path / "m6-failed.json"
    _write_deployment_env(env_file)
    compose_file.write_text("services: {}\n", encoding="utf-8")
    monkeypatch.setattr(runner.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=9))

    result = runner.main(
        [
            "--env-file",
            str(env_file),
            "--compose-file",
            str(compose_file),
            "--proof-receipt",
            str(receipt_path),
        ]
    )

    receipt_text = receipt_path.read_text(encoding="utf-8")
    receipt = json.loads(receipt_text)
    assert result == 9
    assert receipt["status"] == "failed"
    assert "exit code 9" in receipt["evidence_summary"]
    assert "AWS runtime execution" not in receipt["excluded_external_actions"]
    assert "deployment-secret-api-key" not in receipt_text
    assert runner.proof_receipts.check_completion_proof_receipt(receipt_path)["ok"] is True
