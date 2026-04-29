from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_release_tag_source.py"


def _run_git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _init_release_repo(tmp_path: Path) -> Path:
    remote = tmp_path / "origin.git"
    worktree = tmp_path / "worktree"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True, text=True)
    subprocess.run(["git", "init", str(worktree)], check=True, capture_output=True, text=True)
    _run_git(worktree, "checkout", "-b", "main")
    _run_git(worktree, "config", "user.email", "ci@example.com")
    _run_git(worktree, "config", "user.name", "CI")
    (worktree / "README.md").write_text("# release source fixture\n", encoding="utf-8")
    _run_git(worktree, "add", "README.md")
    _run_git(worktree, "commit", "-m", "initial main commit")
    _run_git(worktree, "remote", "add", "origin", str(remote))
    _run_git(worktree, "push", "-u", "origin", "main")
    return worktree


def _run_script(repo: Path, tag: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(SCRIPT_PATH), tag, "--repo", str(repo)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_check_release_tag_source_accepts_annotated_tag_on_main(tmp_path: Path) -> None:
    repo = _init_release_repo(tmp_path)
    release_commit = _run_git(repo, "rev-parse", "HEAD")
    _run_git(repo, "tag", "-a", "v2.0.0", "-m", "release v2.0.0", release_commit)

    completed = _run_script(repo, "v2.0.0")

    assert completed.returncode == 0
    assert "PASS release tag source validation passed" in completed.stdout
    assert f"commit={release_commit}" in completed.stdout
    assert "source=refs/remotes/origin/main" in completed.stdout


def test_check_release_tag_source_blocks_tag_outside_main(tmp_path: Path) -> None:
    repo = _init_release_repo(tmp_path)
    _run_git(repo, "checkout", "--orphan", "off-main-release")
    (repo / "README.md").write_text("# off-main release\n", encoding="utf-8")
    _run_git(repo, "add", "README.md")
    _run_git(repo, "commit", "-m", "off-main release")
    release_commit = _run_git(repo, "rev-parse", "HEAD")
    _run_git(repo, "tag", "-a", "v2.0.1", "-m", "release v2.0.1", release_commit)

    completed = _run_script(repo, "v2.0.1")

    assert completed.returncode == 1
    assert "FAIL release tag does not point to a commit reachable" in completed.stderr
    assert f"commit={release_commit}" in completed.stderr
    assert "required_source=refs/remotes/origin/main" in completed.stderr


def test_check_release_tag_source_rejects_non_release_tag_name(tmp_path: Path) -> None:
    repo = _init_release_repo(tmp_path)
    _run_git(repo, "tag", "not-a-release")

    completed = _run_script(repo, "not-a-release")

    assert completed.returncode == 2
    assert "Invalid release tag" in completed.stderr
