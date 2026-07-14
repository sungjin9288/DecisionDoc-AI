from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from scripts import check_completion_readiness as readiness


def _clear_completion_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in (
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "ANTHROPIC_API_KEY",
        "DECISIONDOC_LIVE_FALLBACK_FORCE_OPENAI_FAILURE",
        "SMOKE_BASE_URL",
        "SMOKE_API_KEY",
        "G2B_API_KEY",
        "ALLOWED_ORIGINS",
        "DECISIONDOC_API_KEYS",
        "DECISIONDOC_API_KEY",
    ):
        env.pop(key, None)
    return env


def test_completion_readiness_reports_remaining_external_blockers(tmp_path: Path) -> None:
    result = readiness.check_completion_readiness(
        env=_clear_completion_env(),
        prod_env_file=tmp_path / ".env.prod",
    )

    assert result["schema_version"] == "decisiondoc.completion_readiness.v1"
    assert result["ok"] is False
    milestones = {item["id"]: item for item in result["milestones"]}
    assert milestones["M1"]["status"] == "blocked"
    assert milestones["M1"]["missing_env"] == [
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "ANTHROPIC_API_KEY",
        "DECISIONDOC_LIVE_FALLBACK_FORCE_OPENAI_FAILURE",
    ]
    assert milestones["M2"]["missing_env"] == [
        "SMOKE_BASE_URL",
        "SMOKE_API_KEY",
        "G2B_API_KEY",
    ]
    assert milestones["M6"]["status"] == "blocked"
    assert "prod env file not found" in milestones["M6"]["blockers"][0]


def test_completion_readiness_accepts_ready_prerequisites_from_env_files(tmp_path: Path) -> None:
    stage_env = tmp_path / "stage-procurement.env"
    stage_env.write_text(
        "\n".join(
            [
                "SMOKE_BASE_URL=https://stage.example.com",
                "SMOKE_API_KEY=stage-api-key",
                "G2B_API_KEY=g2b-api-key",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    prod_env = tmp_path / ".env.prod"
    prod_env.write_text(
        "\n".join(
            [
                "ALLOWED_ORIGINS=https://admin.example.com",
                "DECISIONDOC_API_KEYS=runtime-api-key",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    env = {
        "OPENAI_API_KEY": "openai-api-key",
        "GEMINI_API_KEY": "gemini-api-key",
        "ANTHROPIC_API_KEY": "anthropic-api-key",
        "DECISIONDOC_LIVE_FALLBACK_FORCE_OPENAI_FAILURE": "1",
    }

    result = readiness.check_completion_readiness(
        env=env,
        stage_env_file=stage_env,
        prod_env_file=prod_env,
    )

    assert result["ok"] is True
    assert {item["status"] for item in result["milestones"]} == {"ready_to_execute"}


def test_completion_readiness_accepts_single_env_file_for_all_remaining_milestones(tmp_path: Path) -> None:
    env_file = tmp_path / "completion-readiness.env"
    env_file.write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=openai-api-key",
                "GEMINI_API_KEY=gemini-api-key",
                "ANTHROPIC_API_KEY=anthropic-api-key",
                "DECISIONDOC_LIVE_FALLBACK_FORCE_OPENAI_FAILURE=1",
                "SMOKE_BASE_URL=https://stage.example.com",
                "SMOKE_API_KEY=stage-api-key",
                "G2B_API_KEY=g2b-api-key",
                "ALLOWED_ORIGINS=https://admin.example.com",
                "DECISIONDOC_API_KEYS=runtime-api-key",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = readiness.check_completion_readiness(
        env={},
        env_file=env_file,
    )

    assert result["ok"] is True
    assert {item["status"] for item in result["milestones"]} == {"ready_to_execute"}


def test_completion_readiness_accepts_exported_and_quoted_env_file_values(tmp_path: Path) -> None:
    env_file = tmp_path / "completion-readiness.env"
    env_file.write_text(
        "\n".join(
            [
                "export OPENAI_API_KEY='openai-api-key'",
                'GEMINI_API_KEY="gemini-api-key"',
                "ANTHROPIC_API_KEY=anthropic-api-key",
                "DECISIONDOC_LIVE_FALLBACK_FORCE_OPENAI_FAILURE=1",
                "SMOKE_BASE_URL=https://stage.example.com",
                "SMOKE_API_KEY=stage-api-key",
                "G2B_API_KEY=g2b-api-key",
                "ALLOWED_ORIGINS=https://admin.example.com",
                "DECISIONDOC_API_KEYS=runtime-api-key",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = readiness.check_completion_readiness(
        env={},
        env_file=env_file,
    )

    assert result["ok"] is True
    assert {item["status"] for item in result["milestones"]} == {"ready_to_execute"}


def test_completion_readiness_json_output_redacts_secret_values(tmp_path: Path) -> None:
    prod_env = tmp_path / ".env.prod"
    prod_env.write_text(
        "\n".join(
            [
                "ALLOWED_ORIGINS=https://admin.example.com",
                "DECISIONDOC_API_KEYS=prod-secret-key",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    env = _clear_completion_env()
    env.update(
        {
            "OPENAI_API_KEY": "openai-secret-key",
            "GEMINI_API_KEY": "gemini-secret-key",
            "ANTHROPIC_API_KEY": "anthropic-secret-key",
            "DECISIONDOC_LIVE_FALLBACK_FORCE_OPENAI_FAILURE": "1",
            "SMOKE_BASE_URL": "https://stage.example.com",
            "SMOKE_API_KEY": "stage-secret-key",
            "G2B_API_KEY": "g2b-secret-key",
        }
    )

    completed = subprocess.run(
        [
            "python3",
            "scripts/check_completion_readiness.py",
            "--json",
            "--prod-env-file",
            str(prod_env),
        ],
        cwd=readiness.REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["ok"] is True
    serialized = completed.stdout + completed.stderr
    for secret in (
        "openai-secret-key",
        "gemini-secret-key",
        "anthropic-secret-key",
        "stage-secret-key",
        "g2b-secret-key",
        "prod-secret-key",
    ):
        assert secret not in serialized


def test_completion_readiness_cli_env_file_redacts_secret_values(tmp_path: Path) -> None:
    env_file = tmp_path / "completion-readiness.env"
    env_file.write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=openai-env-file-secret",
                "GEMINI_API_KEY=gemini-env-file-secret",
                "ANTHROPIC_API_KEY=anthropic-env-file-secret",
                "DECISIONDOC_LIVE_FALLBACK_FORCE_OPENAI_FAILURE=1",
                "SMOKE_BASE_URL=https://stage.example.com",
                "SMOKE_API_KEY=stage-env-file-secret",
                "G2B_API_KEY=g2b-env-file-secret",
                "ALLOWED_ORIGINS=https://admin.example.com",
                "DECISIONDOC_API_KEYS=runtime-env-file-secret",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    env = _clear_completion_env()

    completed = subprocess.run(
        [
            "python3",
            "scripts/check_completion_readiness.py",
            "--json",
            "--env-file",
            str(env_file),
        ],
        cwd=readiness.REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["ok"] is True
    serialized = completed.stdout + completed.stderr
    for secret in (
        "openai-env-file-secret",
        "gemini-env-file-secret",
        "anthropic-env-file-secret",
        "stage-env-file-secret",
        "g2b-env-file-secret",
        "runtime-env-file-secret",
    ):
        assert secret not in serialized


def test_completion_readiness_prints_parseable_env_template_without_real_secret_values(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            "python3",
            "scripts/check_completion_readiness.py",
            "--print-env-template",
        ],
        cwd=readiness.REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert "OPENAI_API_KEY=" in completed.stdout
    assert "GEMINI_API_KEY=" in completed.stdout
    assert "ANTHROPIC_API_KEY=" in completed.stdout
    assert "DECISIONDOC_LIVE_FALLBACK_FORCE_OPENAI_FAILURE=1" in completed.stdout
    assert "G2B_API_KEY=" in completed.stdout
    assert "python3 scripts/" not in completed.stdout
    assert "sk-" not in completed.stdout
    assert completed.stderr == ""

    env_file = tmp_path / ".env.prod"
    env_file.write_text(completed.stdout, encoding="utf-8")
    values = readiness._load_env_file(env_file)
    assert values["OPENAI_API_KEY"] == ""
    assert values["DECISIONDOC_API_KEYS"] == ""

    result = readiness.check_completion_readiness(env={}, env_file=env_file)
    assert result["ok"] is False
    assert {item["status"] for item in result["milestones"]} == {"blocked"}


def test_completion_readiness_prints_local_proof_plan_without_secret_values() -> None:
    completed = subprocess.run(
        [
            "python3",
            "scripts/check_completion_readiness.py",
            "--print-proof-plan",
        ],
        cwd=readiness.REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert "mkdir -p reports/completion-readiness" in completed.stdout
    assert "python3 scripts/check_completion_readiness.py --env-file .env.prod" in completed.stdout
    assert "python3 scripts/check_completion_proof_receipt.py --print-template M1" in completed.stdout
    assert "run_stage_procurement_smoke.py --env-file .env.prod --preflight --proof-receipt" in completed.stdout
    assert "run_deployed_smoke.py --env-file .env.prod --proof-receipt" in completed.stdout
    assert "m2-g2b-stage-smoke-preflight.json" in completed.stdout
    assert "m2-g2b-stage-smoke-proof.json" in completed.stdout
    assert "check_completion_proof_receipt.py reports/completion-readiness/m6-deployment-smoke-preflight.json" in completed.stdout
    assert "python3 scripts/check_completion_proof_receipt.py reports/completion-readiness/m6-deployment-smoke-proof.json" in completed.stdout
    assert "your-openai-api-key" not in completed.stdout
    assert "sk-" not in completed.stdout
    assert completed.stderr == ""


def test_completion_readiness_writes_blocked_json_artifact(tmp_path: Path) -> None:
    output_path = tmp_path / "reports" / "completion-readiness.json"
    env = _clear_completion_env()

    completed = subprocess.run(
        [
            "python3",
            "scripts/check_completion_readiness.py",
            "--output",
            str(output_path),
            "--prod-env-file",
            str(tmp_path / ".env.prod"),
        ],
        cwd=readiness.REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    assert output_path.exists()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "decisiondoc.completion_readiness.v1"
    assert payload["ok"] is False
    assert {item["id"] for item in payload["milestones"]} == {"M1", "M2", "M6"}
    assert "provider API execution" in payload["external_actions_excluded"]


def test_completion_readiness_text_report_lists_excluded_external_actions(capsys, tmp_path: Path) -> None:
    result = readiness.check_completion_readiness(
        env=_clear_completion_env(),
        prod_env_file=tmp_path / ".env.prod",
    )

    readiness._print_text_report(result)

    captured = capsys.readouterr().out
    assert "DecisionDoc completion readiness" in captured
    assert "[blocked] M1 Live provider proof" in captured
    assert "provider API execution" in captured
    assert "bid submission" in captured
