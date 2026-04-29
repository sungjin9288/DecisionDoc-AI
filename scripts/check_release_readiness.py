#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
RELEASE_TAG_PATTERN = re.compile(r"^v[0-9]+[.][0-9]+[.][0-9]+$")


def _run_git(repo: Path, args: Sequence[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=check,
        capture_output=True,
        text=True,
    )


def _git_stdout(repo: Path, args: Sequence[str]) -> str:
    return _run_git(repo, args).stdout.strip()


def _git_returncode(repo: Path, args: Sequence[str]) -> int:
    return _run_git(repo, args, check=False).returncode


def _remote_tag_status(repo: Path, *, remote: str, tag: str) -> tuple[bool, str]:
    completed = _run_git(repo, ["ls-remote", "--tags", remote, f"refs/tags/{tag}"], check=False)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        return False, detail or f"git ls-remote failed with exit code {completed.returncode}"
    return bool(completed.stdout.strip()), ""


def check_release_readiness(
    *,
    repo: Path,
    tag: str,
    remote: str = "origin",
    branch: str = "main",
    target_ref: str = "HEAD",
    fetch: bool = True,
) -> dict[str, object]:
    resolved_repo = Path(repo).expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []

    if not RELEASE_TAG_PATTERN.fullmatch(tag.strip()):
        errors.append(f"release tag must match vMAJOR.MINOR.PATCH: {tag}")

    current_branch = _git_stdout(resolved_repo, ["branch", "--show-current"])
    if current_branch != branch:
        errors.append(f"current branch must be {branch}; got {current_branch or 'detached HEAD'}")

    tracked_changes = _git_stdout(resolved_repo, ["status", "--porcelain", "--untracked-files=no"])
    if tracked_changes:
        errors.append("tracked working tree changes exist; commit or revert them before release")

    untracked_changes = _git_stdout(resolved_repo, ["status", "--porcelain", "--untracked-files=normal"])
    untracked_only = [line for line in untracked_changes.splitlines() if line.startswith("??")]
    if untracked_only:
        warnings.append(f"untracked files are present and were ignored: {len(untracked_only)}")

    if _git_returncode(resolved_repo, ["rev-parse", "--verify", f"refs/tags/{tag}"]) == 0:
        errors.append(f"local tag already exists: {tag}")

    if fetch:
        fetch_result = _run_git(
            resolved_repo,
            ["fetch", "--no-tags", "--prune", remote, f"+refs/heads/{branch}:refs/remotes/{remote}/{branch}"],
            check=False,
        )
        if fetch_result.returncode != 0:
            detail = (fetch_result.stderr or fetch_result.stdout).strip()
            errors.append(f"failed to fetch {remote}/{branch}: {detail}")

    remote_ref = f"refs/remotes/{remote}/{branch}"
    target_commit = ""
    try:
        target_commit = _git_stdout(resolved_repo, ["rev-parse", f"{target_ref}^{{commit}}"])
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        errors.append(f"target ref is not a commit: {target_ref} ({detail})")

    if target_commit and _git_returncode(resolved_repo, ["merge-base", "--is-ancestor", target_commit, remote_ref]) != 0:
        errors.append(f"target commit is not reachable from {remote_ref}: {target_commit}")

    remote_tag_exists, remote_tag_error = _remote_tag_status(resolved_repo, remote=remote, tag=tag)
    if remote_tag_error:
        errors.append(f"failed to check remote tag on {remote}: {remote_tag_error}")
    elif remote_tag_exists:
        errors.append(f"remote tag already exists on {remote}: {tag}")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "tag": tag,
        "target_ref": target_ref,
        "target_commit": target_commit,
        "current_branch": current_branch,
        "remote_ref": remote_ref,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check release tag readiness before creating or pushing a production tag.",
    )
    parser.add_argument("tag", help="Release tag to prepare, for example v1.2.3")
    parser.add_argument("--repo", type=Path, default=REPO_ROOT, help=f"Git repository path. Default: {REPO_ROOT}")
    parser.add_argument("--remote", default="origin", help="Remote name that owns the protected branch. Default: origin")
    parser.add_argument("--branch", default="main", help="Protected release source branch. Default: main")
    parser.add_argument("--target-ref", default="HEAD", help="Commit/ref the release tag will point to. Default: HEAD")
    parser.add_argument("--no-fetch", action="store_true", help="Skip fetching the protected branch before validation")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    try:
        result = check_release_readiness(
            repo=args.repo,
            tag=args.tag,
            remote=args.remote,
            branch=args.branch,
            target_ref=args.target_ref,
            fetch=not args.no_fetch,
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        print(f"FAIL release readiness check failed: {detail}", file=sys.stderr)
        return 2

    if result["ok"]:
        print("PASS release readiness check passed")
        print(f"tag={result['tag']}")
        print(f"target_commit={result['target_commit']}")
        print(f"source={result['remote_ref']}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
        print("next_action=git tag {tag} && git push {remote} {tag}".format(tag=args.tag, remote=args.remote))
        return 0

    print("FAIL release readiness check failed", file=sys.stderr)
    print(f"tag={result['tag']}", file=sys.stderr)
    print(f"target_commit={result['target_commit'] or '-'}", file=sys.stderr)
    for error in result["errors"]:
        print(f"ERROR {error}", file=sys.stderr)
    for warning in result["warnings"]:
        print(f"WARN {warning}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
