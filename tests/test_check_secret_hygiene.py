from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_secret_hygiene.py"
ACCESS_KEY_ID = "AKIA" + "1234567890ABCDEF"
SECRET_ACCESS_KEY = "abcd" * 10
SESSION_TOKEN = "token" * 8


def _init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True, text=True)


def _track_file(repo: Path, relative_path: str, content: str) -> Path:
    target = repo / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", relative_path], cwd=repo, check=True, capture_output=True, text=True)
    return target


def _run_secret_hygiene(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(SCRIPT_PATH)],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )


def test_secret_hygiene_passes_for_clean_tracked_files(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _track_file(tmp_path, "README.md", "# clean repo\n")

    completed = _run_secret_hygiene(tmp_path)

    assert completed.returncode == 0
    assert "Secret hygiene check passed." in completed.stdout


def test_secret_hygiene_allows_placeholder_and_env_reference_snippets(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _track_file(
        tmp_path,
        "docs/setup.md",
        (
            "Run the following commands with your own credentials:\n"
            "aws configure set aws_access_key_id <YOUR_ACCESS_KEY_ID> --profile default\n"
            "aws configure set aws_secret_access_key <YOUR_SECRET_ACCESS_KEY> --profile default\n"
            'aws configure set aws_session_token \"$AWS_SESSION_TOKEN\" --profile default\n'
            'AWS_ACCESS_KEY_ID=\"$AWS_ACCESS_KEY_ID\" '
            'AWS_SECRET_ACCESS_KEY=\"$AWS_SECRET_ACCESS_KEY\" '
            'AWS_SESSION_TOKEN=\"$AWS_SESSION_TOKEN\" '
            "python app.py\n"
        ),
    )

    completed = _run_secret_hygiene(tmp_path)

    assert completed.returncode == 0
    assert "Secret hygiene check passed." in completed.stdout


def test_secret_hygiene_allows_github_actions_secret_references(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _track_file(
        tmp_path,
        ".github/workflows/example.yml",
        (
            "jobs:\n"
            "  deploy:\n"
            "    steps:\n"
            "      - name: Configure AWS credentials\n"
            "        env:\n"
            "          AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}\n"
            "          AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}\n"
            "          AWS_SESSION_TOKEN: ${{ vars.AWS_SESSION_TOKEN }}\n"
        ),
    )

    completed = _run_secret_hygiene(tmp_path)

    assert completed.returncode == 0
    assert "Secret hygiene check passed." in completed.stdout


def test_secret_hygiene_flags_tracked_access_key_id(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _track_file(tmp_path, "app/config.py", f'AWS_ACCESS_KEY_ID = "{ACCESS_KEY_ID}"\n')

    completed = _run_secret_hygiene(tmp_path)

    assert completed.returncode == 1
    assert "Secret hygiene check failed." in completed.stderr
    assert f"app/config.py:1: possible AWS access key id {ACCESS_KEY_ID}" in completed.stderr
    assert "app/config.py:1: credential assignment pattern detected" in completed.stderr


def test_secret_hygiene_flags_secret_assignment_patterns(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _track_file(
        tmp_path,
        ".env.example",
        f"AWS_SECRET_ACCESS_KEY={SECRET_ACCESS_KEY}\n",
    )

    completed = _run_secret_hygiene(tmp_path)

    assert completed.returncode == 1
    assert ".env.example:1: credential assignment pattern detected" in completed.stderr


def test_secret_hygiene_flags_session_token_assignment_patterns(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _track_file(
        tmp_path,
        ".env.runtime",
        f'AWS_SESSION_TOKEN="{SESSION_TOKEN}"\n',
    )

    completed = _run_secret_hygiene(tmp_path)

    assert completed.returncode == 1
    assert ".env.runtime:1: credential assignment pattern detected" in completed.stderr


def test_secret_hygiene_flags_exported_shell_assignment_patterns(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _track_file(
        tmp_path,
        "scripts/env.sh",
        (
            f'export AWS_ACCESS_KEY_ID="{ACCESS_KEY_ID}"\n'
            f"export AWS_SECRET_ACCESS_KEY={SECRET_ACCESS_KEY}\n"
            f"export AWS_SESSION_TOKEN={SESSION_TOKEN}\n"
        ),
    )

    completed = _run_secret_hygiene(tmp_path)

    assert completed.returncode == 1
    assert f"scripts/env.sh:1: possible AWS access key id {ACCESS_KEY_ID}" in completed.stderr
    assert "scripts/env.sh:1: credential assignment pattern detected" in completed.stderr
    assert "scripts/env.sh:2: credential assignment pattern detected" in completed.stderr
    assert "scripts/env.sh:3: credential assignment pattern detected" in completed.stderr


def test_secret_hygiene_flags_inline_env_command_patterns(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _track_file(
        tmp_path,
        "scripts/run.sh",
        (
            f'AWS_ACCESS_KEY_ID="{ACCESS_KEY_ID}" '
            f"AWS_SECRET_ACCESS_KEY={SECRET_ACCESS_KEY} "
            f"AWS_SESSION_TOKEN={SESSION_TOKEN} "
            "python app.py\n"
        ),
    )

    completed = _run_secret_hygiene(tmp_path)

    assert completed.returncode == 1
    assert f"scripts/run.sh:1: possible AWS access key id {ACCESS_KEY_ID}" in completed.stderr
    assert "scripts/run.sh:1: credential assignment pattern detected" in completed.stderr


def test_secret_hygiene_flags_aws_configure_set_commands(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _track_file(
        tmp_path,
        "scripts/bootstrap.sh",
        (
            f'aws configure set aws_access_key_id "{ACCESS_KEY_ID}" --profile default\n'
            f"aws configure set aws_secret_access_key {SECRET_ACCESS_KEY} --profile default\n"
            f'aws configure set aws_session_token "{SESSION_TOKEN}" --profile default\n'
        ),
    )

    completed = _run_secret_hygiene(tmp_path)

    assert completed.returncode == 1
    assert f"scripts/bootstrap.sh:1: possible AWS access key id {ACCESS_KEY_ID}" in completed.stderr
    assert "scripts/bootstrap.sh:1: credential assignment pattern detected" in completed.stderr
    assert "scripts/bootstrap.sh:2: credential assignment pattern detected" in completed.stderr
    assert "scripts/bootstrap.sh:3: credential assignment pattern detected" in completed.stderr


def test_secret_hygiene_flags_json_assignment_patterns(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _track_file(
        tmp_path,
        "config/aws.json",
        (
            "{\n"
            f'  "AWS_ACCESS_KEY_ID": "{ACCESS_KEY_ID}",\n'
            f'  "AWS_SECRET_ACCESS_KEY": "{SECRET_ACCESS_KEY}",\n'
            f'  "AWS_SESSION_TOKEN": "{SESSION_TOKEN}"\n'
            "}\n"
        ),
    )

    completed = _run_secret_hygiene(tmp_path)

    assert completed.returncode == 1
    assert f"config/aws.json:2: possible AWS access key id {ACCESS_KEY_ID}" in completed.stderr
    assert "config/aws.json:2: credential assignment pattern detected" in completed.stderr
    assert "config/aws.json:3: credential assignment pattern detected" in completed.stderr
    assert "config/aws.json:4: credential assignment pattern detected" in completed.stderr


def test_secret_hygiene_flags_lowercase_yaml_assignment_patterns(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _track_file(
        tmp_path,
        "config/aws.yml",
        (
            f'aws_access_key_id: "{ACCESS_KEY_ID}"\n'
            f"aws_secret_access_key: {SECRET_ACCESS_KEY}\n"
        ),
    )

    completed = _run_secret_hygiene(tmp_path)

    assert completed.returncode == 1
    assert f"config/aws.yml:1: possible AWS access key id {ACCESS_KEY_ID}" in completed.stderr
    assert "config/aws.yml:1: credential assignment pattern detected" in completed.stderr
    assert "config/aws.yml:2: credential assignment pattern detected" in completed.stderr


def test_secret_hygiene_ignores_untracked_secret_files(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _track_file(tmp_path, "README.md", "# tracked clean file\n")
    (tmp_path / ".env").write_text(
        f"AWS_ACCESS_KEY_ID={ACCESS_KEY_ID}\n"
        f"AWS_SECRET_ACCESS_KEY={SECRET_ACCESS_KEY}\n",
        encoding="utf-8",
    )

    completed = _run_secret_hygiene(tmp_path)

    assert completed.returncode == 0
    assert "Secret hygiene check passed." in completed.stdout
