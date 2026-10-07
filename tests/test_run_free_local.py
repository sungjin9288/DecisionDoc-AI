"""Local runner opt-ins: agent API key and procurement multi-opportunity."""

import stat

import pytest

from scripts import run_free_local as runner


@pytest.fixture
def captured_exec(monkeypatch):
    calls = []
    monkeypatch.setattr(runner.os, "execvpe", lambda file, args, env: calls.append((args, env)))
    return calls


def test_agent_api_key_is_private_and_reused(tmp_path):
    first = runner.ensure_agent_api_key(tmp_path)
    second = runner.ensure_agent_api_key(tmp_path)

    assert first == second == tmp_path.resolve() / ".agent-api-key"
    assert stat.S_IMODE(first.stat().st_mode) == 0o600
    assert len(first.read_text(encoding="utf-8").strip()) >= 32


def test_agent_key_is_passed_to_server_but_not_printed(tmp_path, captured_exec, capsys):
    runner.main(["--data-dir", str(tmp_path), "--agent-api-key"])

    key = (tmp_path / ".agent-api-key").read_text(encoding="utf-8").strip()
    args, env = captured_exec[0]
    assert env["DECISIONDOC_API_KEYS"] == key
    assert "app.main:app" in args
    assert key not in capsys.readouterr().out


def test_default_run_has_no_agent_key_or_procurement_opt_in(tmp_path, captured_exec, monkeypatch):
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)

    runner.main(["--data-dir", str(tmp_path)])

    args, env = captured_exec[0]
    assert "DECISIONDOC_API_KEYS" not in env
    assert env["DECISIONDOC_PROCUREMENT_COPILOT_ENABLED"] == "0"
    assert "--factory" not in args
    assert not (tmp_path / ".agent-api-key").exists()


def test_procurement_opt_in_uses_factory_on_new_data_dir(tmp_path, captured_exec):
    runner.main(["--data-dir", str(tmp_path), "--procurement-multi-opportunity"])

    args, env = captured_exec[0]
    assert args[args.index("--factory") + 1] == "app.main:create_procurement_multi_opportunity_app"
    assert env["DECISIONDOC_PROCUREMENT_COPILOT_ENABLED"] == "1"


def test_procurement_opt_in_requires_preflight_for_existing_state(tmp_path, captured_exec):
    state = tmp_path / "tenants" / "system" / "procurement_decisions.json"
    state.parent.mkdir(parents=True)
    state.write_text("[]", encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        runner.main(["--data-dir", str(tmp_path), "--procurement-multi-opportunity"])
    assert "procurement_transition_preflight" in str(excinfo.value)
    assert captured_exec == []

    runner.main(["--data-dir", str(tmp_path), "--procurement-multi-opportunity", "--procurement-existing-data-checked"])
    assert "--factory" in captured_exec[0][0]
