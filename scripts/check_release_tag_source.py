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


def _is_release_tag(tag: str) -> bool:
    return bool(RELEASE_TAG_PATTERN.fullmatch(tag.strip()))


def check_release_tag_source(
    *,
    repo: Path,
    tag: str,
    remote: str = "origin",
    branch: str = "main",
    fetch: bool = True,
) -> tuple[bool, str, str]:
    if not _is_release_tag(tag):
        raise SystemExit(f"Invalid release tag: {tag}. Expected vMAJOR.MINOR.PATCH, for example v1.2.3.")

    resolved_repo = Path(repo).expanduser().resolve()
    remote_ref = f"refs/remotes/{remote}/{branch}"
    if fetch:
        _run_git(
            resolved_repo,
            [
                "fetch",
                "--no-tags",
                "--prune",
                remote,
                f"+refs/heads/{branch}:{remote_ref}",
            ],
        )

    release_commit = _git_stdout(resolved_repo, ["rev-parse", f"{tag}^{{commit}}"])
    ancestor_check = _run_git(resolved_repo, ["merge-base", "--is-ancestor", release_commit, remote_ref], check=False)
    return ancestor_check.returncode == 0, release_commit, remote_ref


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate that a vMAJOR.MINOR.PATCH release tag points to a commit reachable from origin/main."
    )
    parser.add_argument("tag", help="Release tag to validate, for example v1.2.3")
    parser.add_argument("--repo", type=Path, default=REPO_ROOT, help=f"Git repository path. Default: {REPO_ROOT}")
    parser.add_argument("--remote", default="origin", help="Remote name that owns the protected branch. Default: origin")
    parser.add_argument("--branch", default="main", help="Protected release source branch. Default: main")
    parser.add_argument("--no-fetch", action="store_true", help="Skip fetching the remote branch before validation")
    args = parser.parse_args(argv)

    try:
        is_valid, release_commit, remote_ref = check_release_tag_source(
            repo=args.repo,
            tag=args.tag,
            remote=args.remote,
            branch=args.branch,
            fetch=not args.no_fetch,
        )
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        stdout = (exc.stdout or "").strip()
        detail = stderr or stdout or str(exc)
        print(f"FAIL release tag source validation failed: {detail}", file=sys.stderr)
        return 2
    except SystemExit as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 2

    if is_valid:
        print("PASS release tag source validation passed")
        print(f"tag={args.tag}")
        print(f"commit={release_commit}")
        print(f"source={remote_ref}")
        return 0

    print("FAIL release tag does not point to a commit reachable from the protected release source", file=sys.stderr)
    print(f"tag={args.tag}", file=sys.stderr)
    print(f"commit={release_commit}", file=sys.stderr)
    print(f"required_source={remote_ref}", file=sys.stderr)
    print("required_action=move the release tag to a verified main commit before pushing/rerunning CD", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
