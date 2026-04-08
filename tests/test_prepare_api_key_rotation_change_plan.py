from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_script_module(module_name: str, relative_path: str):
    path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_infer_repo_slug_supports_ssh_and_https(monkeypatch):
    script = _load_script_module(
        "decisiondoc_prepare_api_key_rotation_change_plan_repo_slug",
        "scripts/prepare_api_key_rotation_change_plan.py",
    )

    monkeypatch.setattr(script, "_run", lambda command, cwd=script.REPO_ROOT: "git@github.com:sungjin9288/DecisionDoc-AI.git")
    assert script._infer_repo_slug() == "sungjin9288/DecisionDoc-AI"

    monkeypatch.setattr(
        script,
        "_run",
        lambda command, cwd=script.REPO_ROOT: "https://github.com/sungjin9288/DecisionDoc-AI.git",
    )
    assert script._infer_repo_slug() == "sungjin9288/DecisionDoc-AI"


def test_select_run_url_prefers_same_sha_success():
    script = _load_script_module(
        "decisiondoc_prepare_api_key_rotation_change_plan_same_sha",
        "scripts/prepare_api_key_rotation_change_plan.py",
    )
    runs = [
        {
            "display_title": "deploy-smoke [dev] @ main",
            "conclusion": "success",
            "head_sha": "older",
            "html_url": "https://example.com/older",
        },
        {
            "display_title": "deploy-smoke [dev] @ main",
            "conclusion": "success",
            "head_sha": "target-sha",
            "html_url": "https://example.com/current",
        },
    ]

    selected = script._select_run_url(runs, stage="dev", head_sha="target-sha")

    assert selected == "https://example.com/current"


def test_select_run_url_falls_back_to_placeholder_when_missing():
    script = _load_script_module(
        "decisiondoc_prepare_api_key_rotation_change_plan_missing_run",
        "scripts/prepare_api_key_rotation_change_plan.py",
    )

    selected = script._select_run_url([], stage="prod", head_sha="target-sha")

    assert selected == "<RUN_ID_OR_URL>"


def test_main_writes_output_with_discovered_runs(tmp_path: Path, monkeypatch, capsys):
    script = _load_script_module(
        "decisiondoc_prepare_api_key_rotation_change_plan_main",
        "scripts/prepare_api_key_rotation_change_plan.py",
    )

    monkeypatch.setattr(script, "_infer_repo_slug", lambda: "sungjin9288/DecisionDoc-AI")
    monkeypatch.setattr(script, "_get_head_sha", lambda: "abc123")
    monkeypatch.setattr(
        script,
        "_fetch_workflow_runs",
        lambda repo_slug: [
            {
                "display_title": "deploy-smoke [dev] @ main",
                "conclusion": "success",
                "head_sha": "abc123",
                "html_url": "https://github.com/example/dev",
            },
            {
                "display_title": "deploy-smoke [prod] @ main",
                "conclusion": "success",
                "head_sha": "abc123",
                "html_url": "https://github.com/example/prod",
            },
        ],
    )
    output_path = tmp_path / "rotation-plan.md"

    exit_code = script.main(
        [
            "--stage",
            "prod",
            "--ticket",
            "CHG-2026-0410",
            "--owner",
            "Sungjin",
            "--old-key-label",
            "api-key-v1",
            "--new-key-label",
            "api-key-v2",
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    rendered = output_path.read_text(encoding="utf-8")
    assert "CHG-2026-0410" in rendered
    assert "Sungjin" in rendered
    assert "abc123" in rendered
    assert "https://github.com/example/dev" in rendered
    assert "https://github.com/example/prod" in rendered
    assert "gh secret set DECISIONDOC_API_KEYS -R sungjin9288/DecisionDoc-AI" in rendered
    assert "Old key label | api-key-v1" in rendered
    assert "New key label | api-key-v2" in rendered
    captured = capsys.readouterr()
    assert "wrote plan to" in captured.err
