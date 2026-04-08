from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
IMPORT_SCRIPT = REPO_ROOT / "scripts" / "import-github-actions-env-file.sh"
APPLY_SCRIPT = REPO_ROOT / "scripts" / "apply-github-actions-config.sh"


def _write_source_env(path: Path, *, include_api_keys: bool) -> None:
    lines = [
        "AWS_REGION=ap-northeast-2",
        "DECISIONDOC_API_KEY=repo-api-key",
        "DECISIONDOC_OPS_KEY=repo-ops-key",
        "AWS_ROLE_ARN_DEV=arn:aws:iam::123456789012:role/dev",
        "DECISIONDOC_S3_BUCKET_DEV=decisiondoc-dev",
        "DECISIONDOC_PROCUREMENT_COPILOT_ENABLED_DEV=1",
    ]
    if include_api_keys:
        lines.append("DECISIONDOC_API_KEYS=repo-api-key,next-api-key")
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
