from __future__ import annotations

from pathlib import Path

from scripts import run_local_procurement_smoke as runner


class _FakeProcess:
    def __init__(self) -> None:
        self.terminated = False
        self.killed = False
        self.returncode = None

    def poll(self):
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = 0

    def wait(self, timeout: float | None = None) -> int:
        self.returncode = 0
        return 0

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9


class _FakeCompleted:
    def __init__(self, returncode: int = 0) -> None:
        self.returncode = returncode


def test_run_local_procurement_smoke_starts_server_and_runs_smoke(tmp_path: Path, monkeypatch) -> None:
    launched: list[dict[str, object]] = []
    waited: list[str] = []
    smoke_calls: list[dict[str, object]] = []
    fake_process = _FakeProcess()

    def _fake_popen(command, cwd=None, env=None):
        launched.append(
            {
                "command": list(command),
                "cwd": cwd,
                "env": dict(env or {}),
            }
        )
        return fake_process

    def _fake_wait(base_url: str, *, process=None, timeout_seconds: float = 20.0, interval_seconds: float = 0.5):
        waited.append(base_url)
        assert process is fake_process

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

    monkeypatch.setattr(runner.subprocess, "Popen", _fake_popen)
    monkeypatch.setattr(runner.subprocess, "run", _fake_run)
    monkeypatch.setattr(runner, "_wait_for_health", _fake_wait)

    result = runner.run_local_procurement_smoke(
        data_dir=tmp_path / "proc-smoke-data",
        procurement_url_or_number="20260405001-00",
        g2b_api_key="g2b-live-test-key",
        port=8877,
    )

    assert result == 0
    assert len(launched) == 1
    assert len(smoke_calls) == 1
    server_command = launched[0]["command"]
    assert server_command[:3] == [runner.sys.executable, "-m", "uvicorn"]
    assert "app.main:app" in server_command
    assert "--port" in server_command
    assert "8877" in server_command

    server_env = launched[0]["env"]
    assert server_env["DATA_DIR"] == str(tmp_path / "proc-smoke-data")
    assert server_env["DECISIONDOC_PROVIDER"] == "mock"
    assert server_env["DECISIONDOC_PROCUREMENT_COPILOT_ENABLED"] == "1"
    assert server_env["DECISIONDOC_API_KEY"] == runner.DEFAULT_API_KEY
    assert server_env["DECISIONDOC_OPS_KEY"] == runner.DEFAULT_OPS_KEY
    assert server_env["JWT_SECRET_KEY"] == runner.DEFAULT_JWT_SECRET
    assert server_env["G2B_API_KEY"] == "g2b-live-test-key"

    assert waited == ["http://127.0.0.1:8877"]

    smoke_call = smoke_calls[0]
    assert smoke_call["command"] == [runner.sys.executable, "scripts/smoke.py"]
    smoke_env = smoke_call["env"]
    assert smoke_env["SMOKE_BASE_URL"] == "http://127.0.0.1:8877"
    assert smoke_env["SMOKE_API_KEY"] == runner.DEFAULT_API_KEY
    assert smoke_env["SMOKE_PROVIDER"] == "mock"
    assert smoke_env["SMOKE_INCLUDE_PROCUREMENT"] == "1"
    assert smoke_env["SMOKE_PROCUREMENT_URL_OR_NUMBER"] == "20260405001-00"
    assert smoke_env["SMOKE_OPS_KEY"] == runner.DEFAULT_OPS_KEY
    assert smoke_env["G2B_API_KEY"] == "g2b-live-test-key"
    assert fake_process.terminated is True


def test_main_requires_procurement_smoke_env(monkeypatch) -> None:
    monkeypatch.delenv("SMOKE_PROCUREMENT_URL_OR_NUMBER", raising=False)
    monkeypatch.delenv("G2B_API_KEY", raising=False)

    try:
        runner.main([])
    except SystemExit as exc:
        message = str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected SystemExit when procurement smoke env is missing")

    assert "SMOKE_PROCUREMENT_URL_OR_NUMBER" in message


def test_preflight_reports_missing_required_env(monkeypatch, capsys, tmp_path: Path) -> None:
    monkeypatch.delenv("SMOKE_PROCUREMENT_URL_OR_NUMBER", raising=False)
    monkeypatch.delenv("G2B_API_KEY", raising=False)
    monkeypatch.delenv("SMOKE_TENANT_ID", raising=False)
    monkeypatch.delenv("PROCUREMENT_SMOKE_USERNAME", raising=False)
    monkeypatch.delenv("PROCUREMENT_SMOKE_PASSWORD", raising=False)

    result = runner.main(
        [
            "--preflight",
            "--port",
            "8892",
            "--data-dir",
            str(tmp_path / "proc-smoke-data"),
        ]
    )

    captured = capsys.readouterr().out
    assert result == 1
    assert "[missing] SMOKE_PROCUREMENT_URL_OR_NUMBER" in captured
    assert "[missing] G2B_API_KEY" in captured
    assert "--port 8892" in captured


def test_preflight_passes_when_required_env_is_present(monkeypatch, capsys, tmp_path: Path) -> None:
    monkeypatch.setenv("SMOKE_PROCUREMENT_URL_OR_NUMBER", "20260405001-00")
    monkeypatch.setenv("G2B_API_KEY", "g2b-live-test-key")
    monkeypatch.setenv("SMOKE_TENANT_ID", "system")

    result = runner.main(
        [
            "--preflight",
            "--data-dir",
            str(tmp_path / "proc-smoke-data"),
        ]
    )

    captured = capsys.readouterr().out
    assert result == 0
    assert "[ok] SMOKE_PROCUREMENT_URL_OR_NUMBER" in captured
    assert "[ok] G2B_API_KEY" in captured
    assert "[info] SMOKE_TENANT_ID=set" in captured


def test_print_env_template_outputs_copy_paste_command(capsys, tmp_path: Path) -> None:
    result = runner.main(
        [
            "--print-env-template",
            "--port",
            "8893",
            "--data-dir",
            str(tmp_path / "proc-smoke-data"),
        ]
    )

    captured = capsys.readouterr().out
    assert result == 0
    assert "export G2B_API_KEY=your-data-go-kr-key" in captured
    assert "export SMOKE_PROCUREMENT_URL_OR_NUMBER=20260405001-00" in captured
    assert "export JWT_SECRET_KEY=test-local-procurement-smoke-secret-32chars" in captured
    assert f"JWT_SECRET_KEY={runner.DEFAULT_JWT_SECRET}" in captured
    assert "--port 8893" in captured
    assert str(runner.DEFAULT_ENV_FILE) in captured


def test_preflight_uses_env_file_values(tmp_path: Path, capsys) -> None:
    env_file = tmp_path / "proc-smoke.env"
    env_file.write_text(
        "\n".join(
            [
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
    assert "[ok] SMOKE_PROCUREMENT_URL_OR_NUMBER" in captured
    assert "[ok] G2B_API_KEY" in captured
    assert "[info] SMOKE_TENANT_ID=set" in captured
    assert f"JWT_SECRET_KEY={runner.DEFAULT_JWT_SECRET}" in captured
    assert f"--env-file {env_file}" in captured


def test_run_local_procurement_smoke_uses_env_file_optional_values(tmp_path: Path, monkeypatch) -> None:
    launched: list[dict[str, object]] = []
    waited: list[str] = []
    smoke_calls: list[dict[str, object]] = []
    fake_process = _FakeProcess()
    env_file = tmp_path / "proc-smoke.env"
    env_file.write_text(
        "\n".join(
            [
                "SMOKE_TENANT_ID=tenant-from-file",
                "PROCUREMENT_SMOKE_USERNAME=file-user",
                "PROCUREMENT_SMOKE_PASSWORD=file-pass",
                "JWT_SECRET_KEY=file-jwt-secret",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    def _fake_popen(command, cwd=None, env=None):
        launched.append({"command": list(command), "cwd": cwd, "env": dict(env or {})})
        return fake_process

    def _fake_wait(base_url: str, *, process=None, timeout_seconds: float = 20.0, interval_seconds: float = 0.5):
        waited.append(base_url)
        assert process is fake_process

    def _fake_run(command, cwd=None, env=None, check=False):
        smoke_calls.append({"command": list(command), "cwd": cwd, "env": dict(env or {}), "check": check})
        return _FakeCompleted(returncode=0)

    monkeypatch.setattr(runner.subprocess, "Popen", _fake_popen)
    monkeypatch.setattr(runner.subprocess, "run", _fake_run)
    monkeypatch.setattr(runner, "_wait_for_health", _fake_wait)

    env_overrides = runner._load_env_file(env_file)
    result = runner.run_local_procurement_smoke(
        data_dir=tmp_path / "proc-smoke-data",
        procurement_url_or_number="20260405001-00",
        g2b_api_key="g2b-live-test-key",
        port=8877,
        env_overrides=env_overrides,
    )

    assert result == 0
    server_env = launched[0]["env"]
    assert server_env["JWT_SECRET_KEY"] == "file-jwt-secret"
    smoke_env = smoke_calls[0]["env"]
    assert smoke_env["SMOKE_TENANT_ID"] == "tenant-from-file"
    assert smoke_env["PROCUREMENT_SMOKE_USERNAME"] == "file-user"
    assert smoke_env["PROCUREMENT_SMOKE_PASSWORD"] == "file-pass"
