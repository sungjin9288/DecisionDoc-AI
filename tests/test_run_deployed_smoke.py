from __future__ import annotations

import importlib.util
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


def test_run_deployed_smoke_uses_env_file_defaults(tmp_path: Path, monkeypatch) -> None:
    runner = _load_script_module("decisiondoc_run_deployed_smoke_defaults", "scripts/run_deployed_smoke.py")
    env_file = tmp_path / ".env.prod"
    env_file.write_text(
        "\n".join(
            [
                "ALLOWED_ORIGINS=https://dawool.decisiondoc.kr",
                "DECISIONDOC_API_KEYS=runtime-key-1,runtime-key-2",
                "DECISIONDOC_PROVIDER=openai",
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
    assert "[ok] SMOKE_BASE_URL=https://admin.decisiondoc.kr" in captured
    assert "[ok] SMOKE_API_KEY=set" in captured
    assert "[ok] SMOKE_PROVIDER=openai" in captured
