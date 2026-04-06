from __future__ import annotations

from pathlib import Path

from scripts import run_stage_procurement_smoke as runner


class _FakeCompleted:
    def __init__(self, returncode: int = 0) -> None:
        self.returncode = returncode


def test_run_stage_procurement_smoke_runs_smoke_with_expected_env(monkeypatch) -> None:
    smoke_calls: list[dict[str, object]] = []

    def _fake_run(command, cwd=None, env=None, check=False):
        smoke_calls.append(
            {
                "command": list(command),
                "cwd": cwd,
                "env": dict(env or {}),
                "check": check,
            }
        )
        return _FakeCompleted(returncode=0)

    monkeypatch.setattr(runner.subprocess, "run", _fake_run)

    result = runner.run_stage_procurement_smoke(
        base_url="https://stage.example.com/",
        api_key="stage-api-key",
        procurement_url_or_number="20260405001-00",
        g2b_api_key="g2b-live-test-key",
        provider="mock",
        timeout_sec=45.0,
        ops_key="stage-ops-key",
        tenant_id="tenant-stage",
        username="smoke-user",
        password="smoke-pass",
    )

    assert result == 0
    assert len(smoke_calls) == 1
    smoke_call = smoke_calls[0]
    assert smoke_call["command"] == [runner.sys.executable, "scripts/smoke.py"]
    smoke_env = smoke_call["env"]
    assert smoke_env["SMOKE_BASE_URL"] == "https://stage.example.com"
    assert smoke_env["SMOKE_API_KEY"] == "stage-api-key"
    assert smoke_env["SMOKE_PROVIDER"] == "mock"
    assert smoke_env["SMOKE_TIMEOUT_SEC"] == "45.0"
    assert smoke_env["SMOKE_INCLUDE_PROCUREMENT"] == "1"
    assert smoke_env["SMOKE_PROCUREMENT_URL_OR_NUMBER"] == "20260405001-00"
    assert smoke_env["G2B_API_KEY"] == "g2b-live-test-key"
    assert smoke_env["SMOKE_OPS_KEY"] == "stage-ops-key"
    assert smoke_env["SMOKE_TENANT_ID"] == "tenant-stage"
    assert smoke_env["PROCUREMENT_SMOKE_USERNAME"] == "smoke-user"
    assert smoke_env["PROCUREMENT_SMOKE_PASSWORD"] == "smoke-pass"


def test_main_requires_stage_smoke_env(monkeypatch) -> None:
    monkeypatch.delenv("SMOKE_BASE_URL", raising=False)
    monkeypatch.delenv("SMOKE_API_KEY", raising=False)
    monkeypatch.delenv("SMOKE_PROCUREMENT_URL_OR_NUMBER", raising=False)
    monkeypatch.delenv("G2B_API_KEY", raising=False)

    try:
        runner.main([])
    except SystemExit as exc:
        message = str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected SystemExit when stage procurement smoke env is missing")

    assert "SMOKE_BASE_URL" in message


def test_preflight_reports_missing_required_env(monkeypatch, capsys) -> None:
    monkeypatch.delenv("SMOKE_BASE_URL", raising=False)
    monkeypatch.delenv("SMOKE_API_KEY", raising=False)
    monkeypatch.delenv("SMOKE_PROCUREMENT_URL_OR_NUMBER", raising=False)
    monkeypatch.delenv("G2B_API_KEY", raising=False)

    result = runner.main(["--preflight"])

    captured = capsys.readouterr().out
    assert result == 1
    assert "[missing] SMOKE_BASE_URL" in captured
    assert "[missing] SMOKE_API_KEY" in captured
    assert "[missing] SMOKE_PROCUREMENT_URL_OR_NUMBER" in captured
    assert "[missing] G2B_API_KEY" in captured


def test_print_env_template_outputs_copy_paste_command(capsys) -> None:
    result = runner.main(["--print-env-template"])

    captured = capsys.readouterr().out
    assert result == 0
    assert "export SMOKE_BASE_URL=https://your-stage.example.com" in captured
    assert "export SMOKE_API_KEY=your-stage-api-key" in captured
    assert "export G2B_API_KEY=your-data-go-kr-key" in captured
    assert "export SMOKE_PROCUREMENT_URL_OR_NUMBER=20260405001-00" in captured
    assert ".venv/bin/python scripts/run_stage_procurement_smoke.py" in captured
    assert str(runner.DEFAULT_ENV_FILE) in captured


def test_preflight_uses_env_file_values(tmp_path: Path, capsys) -> None:
    env_file = tmp_path / "stage-proc-smoke.env"
    env_file.write_text(
        "\n".join(
            [
                "SMOKE_BASE_URL=https://stage.example.com",
                "SMOKE_API_KEY=file-based-api-key",
                "G2B_API_KEY=file-based-g2b-key",
                "SMOKE_PROCUREMENT_URL_OR_NUMBER=20260405001-00",
                "SMOKE_TENANT_ID=tenant-from-file",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = runner.main(
        [
            "--preflight",
            "--env-file",
            str(env_file),
        ]
    )

    captured = capsys.readouterr().out
    assert result == 0
    assert "[ok] SMOKE_BASE_URL" in captured
    assert "[ok] SMOKE_API_KEY" in captured
    assert "[ok] G2B_API_KEY" in captured
    assert "[ok] SMOKE_PROCUREMENT_URL_OR_NUMBER" in captured
    assert "[info] SMOKE_TENANT_ID=set" in captured
    assert f"--env-file {env_file}" in captured
