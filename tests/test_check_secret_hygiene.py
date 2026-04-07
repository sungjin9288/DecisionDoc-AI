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
