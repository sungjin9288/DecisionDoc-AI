from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
IMPORT_SCRIPT = REPO_ROOT / "scripts" / "import-github-actions-env-file.sh"
APPLY_SCRIPT = REPO_ROOT / "scripts" / "apply-github-actions-config.sh"


def _write_source_env(
    path: Path,
    *,
    include_api_keys: bool,
    stage: str = "dev",
    include_deploy: bool = False,
) -> None:
    stage_upper = stage.upper()
    deploy_prefix = "STAGING" if stage == "dev" else "PROD"
    lines = [
        "AWS_REGION=ap-northeast-2",
        "DECISIONDOC_API_KEY=repo-api-key",
        "DECISIONDOC_OPS_KEY=repo-ops-key",
        f"AWS_ROLE_ARN_{stage_upper}=arn:aws:iam::123456789012:role/{stage}",
        f"DECISIONDOC_S3_BUCKET_{stage_upper}=decisiondoc-{stage}",
        f"DECISIONDOC_PROCUREMENT_COPILOT_ENABLED_{stage_upper}=1",
    ]
    if include_api_keys:
        lines.append("DECISIONDOC_API_KEYS=repo-api-key,next-api-key")
    if include_deploy:
        lines.extend(
            [
                f"{deploy_prefix}_HOST={stage}.decisiondoc.internal",
                f"{deploy_prefix}_USER=ubuntu",
                f"{deploy_prefix}_SSH_KEY=test-private-key",
            ]
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_import_github_actions_env_file_copies_decisiondoc_api_keys(tmp_path: Path) -> None:
    source_env = tmp_path / "source.env"
    output_env = tmp_path / "github-actions.env"
    _write_source_env(source_env, include_api_keys=True)

    completed = subprocess.run(
        [
            "bash",
            str(IMPORT_SCRIPT),
            "--stage",
            "dev",
            "--source",
            str(source_env),
            "--output",
            str(output_env),
            "--force",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    output_text = output_env.read_text(encoding="utf-8")
    assert "DECISIONDOC_API_KEYS=repo-api-key,next-api-key\n" in output_text


def test_import_github_actions_env_file_copies_stage_deploy_secrets(tmp_path: Path) -> None:
    source_env = tmp_path / "source.env"
    output_env = tmp_path / "github-actions.env"
    _write_source_env(source_env, include_api_keys=False, stage="dev", include_deploy=True)

    completed = subprocess.run(
        [
            "bash",
            str(IMPORT_SCRIPT),
            "--stage",
            "dev",
            "--source",
            str(source_env),
            "--output",
            str(output_env),
            "--force",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    output_text = output_env.read_text(encoding="utf-8")
    assert "STAGING_HOST=dev.decisiondoc.internal\n" in output_text
    assert "STAGING_USER=ubuntu\n" in output_text
    assert "STAGING_SSH_KEY=test-private-key\n" in output_text
    assert "PROD_HOST=\n" in output_text


def test_import_github_actions_env_file_copies_prod_deploy_secrets(tmp_path: Path) -> None:
    source_env = tmp_path / "source.env"
    output_env = tmp_path / "github-actions.env"
    _write_source_env(source_env, include_api_keys=False, stage="prod", include_deploy=True)

    completed = subprocess.run(
        [
            "bash",
            str(IMPORT_SCRIPT),
            "--stage",
            "prod",
            "--source",
            str(source_env),
            "--output",
            str(output_env),
            "--force",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    output_text = output_env.read_text(encoding="utf-8")
    assert "PROD_HOST=prod.decisiondoc.internal\n" in output_text
    assert "PROD_USER=ubuntu\n" in output_text
    assert "PROD_SSH_KEY=test-private-key\n" in output_text
    assert "STAGING_HOST=\n" in output_text


def test_apply_github_actions_config_dry_run_includes_decisiondoc_api_keys_when_present(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / "github-actions.env"
    _write_source_env(env_file, include_api_keys=True)

    completed = subprocess.run(
        [
            "bash",
            str(APPLY_SCRIPT),
            "--stage",
            "dev",
            "--env-file",
            str(env_file),
            "--dry-run",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "secret   DECISIONDOC_API_KEYS" in completed.stdout


def test_apply_github_actions_config_dry_run_omits_decisiondoc_api_keys_when_absent(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / "github-actions.env"
    _write_source_env(env_file, include_api_keys=False)

    completed = subprocess.run(
        [
            "bash",
            str(APPLY_SCRIPT),
            "--stage",
            "dev",
            "--env-file",
            str(env_file),
            "--dry-run",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "secret   DECISIONDOC_API_KEYS" not in completed.stdout


def test_apply_github_actions_config_dry_run_includes_stage_deploy_secrets_when_present(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / "github-actions.env"
    _write_source_env(env_file, include_api_keys=False, stage="dev", include_deploy=True)

    completed = subprocess.run(
        [
            "bash",
            str(APPLY_SCRIPT),
            "--stage",
            "dev",
            "--env-file",
            str(env_file),
            "--dry-run",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "secret   STAGING_HOST" in completed.stdout
    assert "secret   STAGING_USER" in completed.stdout
    assert "secret   STAGING_SSH_KEY" in completed.stdout
