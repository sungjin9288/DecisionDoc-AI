#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = REPO_ROOT / ".env.prod"
DEFAULT_COMPOSE_FILE = REPO_ROOT / "docker-compose.prod.yml"
DEFAULT_IMAGE = "decisiondoc-local"


def _run_command(
    command: list[str],
    *,
    label: str,
    extra_env: dict[str, str] | None = None,
) -> None:
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    completed = subprocess.run(command, cwd=REPO_ROOT, env=env, check=False)
    if completed.returncode != 0:
        raise SystemExit(f"{label} failed with exit code {completed.returncode}")


def deploy_compose_local(
    *,
    env_file: Path,
    compose_file: Path,
    image: str,
    build_context: Path,
    skip_build: bool = False,
    post_check: bool = False,
    base_url: str = "",
    skip_smoke: bool = False,
) -> int:
    resolved_env_file = Path(env_file).expanduser()
    resolved_compose_file = Path(compose_file).expanduser()
    resolved_build_context = Path(build_context).expanduser()

    if not resolved_env_file.exists():
        raise SystemExit(f"Env file not found: {resolved_env_file}")
    if not resolved_compose_file.exists():
        raise SystemExit(f"Compose file not found: {resolved_compose_file}")
    if not resolved_build_context.exists():
        raise SystemExit(f"Build context not found: {resolved_build_context}")

    normalized_image = str(image or "").strip()
    if not normalized_image:
        raise SystemExit("Image name is required")

    if not skip_build:
        _run_command(
            ["docker", "build", "-t", normalized_image, str(resolved_build_context)],
            label="docker build",
        )
        print(f"PASS docker build -> {normalized_image}", flush=True)

    compose_env = {"DOCKER_IMAGE": normalized_image}
    _run_command(
        [
            "docker",
            "compose",
            "--env-file",
            str(resolved_env_file),
            "-f",
            str(resolved_compose_file),
            "up",
            "-d",
            "--force-recreate",
        ],
        label="docker compose up",
        extra_env=compose_env,
    )
    print(f"PASS docker compose up -> {normalized_image}", flush=True)

    if post_check:
        command = [
            sys.executable,
            "scripts/post_deploy_check.py",
            "--env-file",
            str(resolved_env_file),
            "--compose-file",
            str(resolved_compose_file),
        ]
        if base_url:
            command.extend(["--base-url", base_url.strip()])
        if skip_smoke:
            command.append("--skip-smoke")
        _run_command(command, label="post deploy check")
        print("PASS post-deploy check", flush=True)

    return 0


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a local DecisionDoc image and roll it out via docker compose.",
    )
    parser.add_argument(
        "--env-file",
        default=str(DEFAULT_ENV_FILE),
        help="Path to the deployment env file. Default: .env.prod in repo root",
    )
    parser.add_argument(
        "--compose-file",
        default=str(DEFAULT_COMPOSE_FILE),
        help="Path to the docker compose file. Default: docker-compose.prod.yml",
    )
    parser.add_argument(
        "--image",
        default=DEFAULT_IMAGE,
        help="Docker image tag to build and inject into docker compose via DOCKER_IMAGE.",
    )
    parser.add_argument(
        "--build-context",
        default=str(REPO_ROOT),
        help="Docker build context. Default: repo root",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Skip docker build and only run docker compose up with the provided image tag.",
    )
    parser.add_argument(
        "--post-check",
        action="store_true",
        help="Run scripts/post_deploy_check.py after rollout completes.",
    )
    parser.add_argument(
        "--base-url",
        default="",
        help="Optional base URL to pass through to post_deploy_check.",
    )
    parser.add_argument(
        "--skip-smoke",
        action="store_true",
        help="When used with --post-check, skip the deployed smoke runner.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    return deploy_compose_local(
        env_file=Path(args.env_file),
        compose_file=Path(args.compose_file),
        image=args.image,
        build_context=Path(args.build_context),
        skip_build=bool(args.skip_build),
        post_check=bool(args.post_check),
        base_url=args.base_url,
        skip_smoke=bool(args.skip_smoke),
    )


if __name__ == "__main__":
    raise SystemExit(main())
