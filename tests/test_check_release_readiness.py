from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_release_readiness.py"


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
    (worktree / "README.md").write_text("# release readiness fixture\n", encoding="utf-8")
    _run_git(worktree, "add", "README.md")
    _run_git(worktree, "commit", "-m", "initial main commit")
    _run_git(worktree, "remote", "add", "origin", str(remote))
    _run_git(worktree, "push", "-u", "origin", "main")
    return worktree


def _run_script(repo: Path, tag: str, *extra_args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(SCRIPT_PATH), tag, "--repo", str(repo), *extra_args],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_check_release_readiness_accepts_clean_main_commit(tmp_path: Path) -> None:
    repo = _init_release_repo(tmp_path)
    release_commit = _run_git(repo, "rev-parse", "HEAD")

    completed = _run_script(repo, "v2.3.4")

    assert completed.returncode == 0, completed.stderr
    assert "PASS release readiness check passed" in completed.stdout
    assert "tag=v2.3.4" in completed.stdout
    assert f"target_commit={release_commit}" in completed.stdout
    assert "source=refs/remotes/origin/main" in completed.stdout
    assert "next_action=git tag v2.3.4 && git push origin v2.3.4" in completed.stdout


def test_check_release_readiness_rejects_non_numeric_semver_tag(tmp_path: Path) -> None:
    repo = _init_release_repo(tmp_path)

    completed = _run_script(repo, "vfoo.bar.baz")

    assert completed.returncode == 1
    assert "release tag must match vMAJOR.MINOR.PATCH" in completed.stderr


def test_check_release_readiness_rejects_tracked_working_tree_changes(tmp_path: Path) -> None:
    repo = _init_release_repo(tmp_path)
    (repo / "README.md").write_text("# dirty release readiness fixture\n", encoding="utf-8")

    completed = _run_script(repo, "v2.3.5")

    assert completed.returncode == 1
    assert "tracked working tree changes exist" in completed.stderr


def test_check_release_readiness_rejects_off_main_target_commit(tmp_path: Path) -> None:
    repo = _init_release_repo(tmp_path)
    _run_git(repo, "checkout", "--orphan", "release-candidate")
    (repo / "README.md").write_text("# off-main release candidate\n", encoding="utf-8")
    _run_git(repo, "add", "README.md")
    _run_git(repo, "commit", "-m", "off-main release candidate")
    release_commit = _run_git(repo, "rev-parse", "HEAD")

    completed = _run_script(repo, "v2.3.6")

    assert completed.returncode == 1
    assert f"target commit is not reachable from refs/remotes/origin/main: {release_commit}" in completed.stderr


def test_check_release_readiness_rejects_existing_remote_tag(tmp_path: Path) -> None:
    repo = _init_release_repo(tmp_path)
    _run_git(repo, "tag", "v2.3.7")
    _run_git(repo, "push", "origin", "v2.3.7")
    _run_git(repo, "tag", "-d", "v2.3.7")

    completed = _run_script(repo, "v2.3.7")

    assert completed.returncode == 1
    assert "remote tag already exists on origin: v2.3.7" in completed.stderr


def test_check_release_readiness_rejects_remote_tag_lookup_failure(tmp_path: Path) -> None:
    repo = _init_release_repo(tmp_path)

    completed = _run_script(repo, "v2.3.8", "--remote", "missing", "--no-fetch")

    assert completed.returncode == 1
    assert "failed to check remote tag on missing" in completed.stderr
