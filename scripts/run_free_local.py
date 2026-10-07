#!/usr/bin/env python3
"""Run DecisionDoc locally with cloud providers and cloud storage disabled."""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from app.free_mode import is_free_local_llm_url  # noqa: E402


_CLEARED_ENV_NAMES = (
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "ANTHROPIC_API_KEY",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_SECURITY_TOKEN",
    "DECISIONDOC_OPS_KEY",
    "SERPER_API_KEY",
    "BRAVE_API_KEY",
    "TAVILY_API_KEY",
    "G2B_API_KEY",
    "STATUSPAGE_PAGE_ID",
    "STATUSPAGE_API_KEY",
    "STRIPE_SECRET_KEY",
    "STRIPE_PUBLISHABLE_KEY",
    "STRIPE_PRO_PRICE_ID",
    "STRIPE_ENTERPRISE_PRICE_ID",
    "STRIPE_WEBHOOK_SECRET",
    "SMTP_HOST",
    "SMTP_USER",
    "SMTP_PASSWORD",
    "SLACK_WEBHOOK_URL",
    "VOICE_BRIEF_API_BASE_URL",
    "VOICE_BRIEF_API_BEARER_TOKEN",
)
_REMOVED_AWS_CREDENTIAL_SOURCES = (
    "AWS_PROFILE",
    "AWS_DEFAULT_PROFILE",
    "AWS_CONTAINER_CREDENTIALS_FULL_URI",
    "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
    "AWS_WEB_IDENTITY_TOKEN_FILE",
    "AWS_ROLE_ARN",
)
_PRINTED_ENV_NAMES = (
    "DECISIONDOC_FREE_MODE",
    "DECISIONDOC_ENV",
    "DECISIONDOC_PROVIDER",
    "DECISIONDOC_PROVIDER_GENERATION",
    "DECISIONDOC_PROVIDER_ATTACHMENT",
    "DECISIONDOC_PROVIDER_VISUAL",
    "DECISIONDOC_STORAGE",
    "DECISIONDOC_STATE_STORAGE",
    "DATA_DIR",
    "EXPORT_DIR",
    "FINETUNE_AUTO_ENABLED",
    "DECISIONDOC_SEARCH_ENABLED",
    "DECISIONDOC_PROCUREMENT_COPILOT_ENABLED",
    "AWS_EC2_METADATA_DISABLED",
    "LOCAL_LLM_BASE_URL",
    "LOCAL_LLM_MODEL",
)
_DEFAULT_LOCAL_LLM_BASE_URL = "http://localhost:11434/v1"


def build_free_environment(
    source: Mapping[str, str],
    *,
    provider: str,
    data_dir: Path,
) -> dict[str, str]:
    env = dict(source)
    resolved_data_dir = data_dir.expanduser().resolve()
    env.update(
        {
            "DECISIONDOC_FREE_MODE": "1",
            "DECISIONDOC_ENV": "dev",
            "ENVIRONMENT": "development",
            "DECISIONDOC_PROVIDER": provider,
            "DECISIONDOC_PROVIDER_GENERATION": provider,
            "DECISIONDOC_PROVIDER_ATTACHMENT": "mock",
            "DECISIONDOC_PROVIDER_VISUAL": "mock",
            "DECISIONDOC_STORAGE": "local",
            "DECISIONDOC_STATE_STORAGE": "local",
            "DATA_DIR": str(resolved_data_dir),
            "EXPORT_DIR": str(resolved_data_dir),
            "FINETUNE_AUTO_ENABLED": "0",
            "DECISIONDOC_SEARCH_ENABLED": "0",
            "DECISIONDOC_PROCUREMENT_COPILOT_ENABLED": "0",
            "AWS_EC2_METADATA_DISABLED": "true",
            "AWS_SHARED_CREDENTIALS_FILE": os.devnull,
            "AWS_CONFIG_FILE": os.devnull,
        }
    )
    for name in _CLEARED_ENV_NAMES:
        env[name] = ""
    for name in _REMOVED_AWS_CREDENTIAL_SOURCES:
        env.pop(name, None)
    configured_base_url = env.get("LOCAL_LLM_BASE_URL", "").strip()
    env["LOCAL_LLM_BASE_URL"] = (
        configured_base_url
        if is_free_local_llm_url(configured_base_url)
        else _DEFAULT_LOCAL_LLM_BASE_URL
    )
    env["LOCAL_LLM_MODEL"] = (
        env.get("LOCAL_LLM_MODEL", "").strip()
        or "llama3.1:8b"
    )
    env["LOCAL_LLM_API_KEY"] = (
        env.get("LOCAL_LLM_API_KEY", "").strip()
        or "local"
    )
    return env


AGENT_API_KEY_FILENAME = ".agent-api-key"
_PROCUREMENT_FACTORY = "app.main:create_procurement_multi_opportunity_app"


def ensure_agent_api_key(data_dir: Path) -> Path:
    """Create (0600) or reuse the local key that scripts/decisiondoc_author.py sends."""
    key_path = data_dir.expanduser().resolve() / AGENT_API_KEY_FILENAME
    if key_path.is_file() and key_path.read_text(encoding="utf-8").strip():
        return key_path
    key_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = key_path.with_name(f"{key_path.name}.tmp")
    fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(secrets.token_urlsafe(32))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, key_path)
    return key_path


def existing_procurement_state(data_dir: Path) -> list[Path]:
    root = data_dir.expanduser().resolve() / "tenants"
    return sorted(root.glob("*/procurement_decisions.json")) if root.is_dir() else []


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run DecisionDoc in fail-closed no-cost local mode."
    )
    parser.add_argument("--provider", choices=("mock", "local"), default="mock")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--data-dir", type=Path, default=Path("./data/free-local"))
    parser.add_argument("--reload", action="store_true")
    parser.add_argument(
        "--print-env",
        action="store_true",
        help="Print the non-secret enforced environment and exit.",
    )
    parser.add_argument(
        "--agent-api-key",
        action="store_true",
        help="Create or reuse <data-dir>/.agent-api-key for scripts/decisiondoc_author.py.",
    )
    parser.add_argument(
        "--procurement-multi-opportunity",
        action="store_true",
        help="Opt in to the multi-opportunity procurement flow for this data dir.",
    )
    parser.add_argument(
        "--procurement-existing-data-checked",
        action="store_true",
        help="Allow the opt-in on a data dir whose procurement state passed preflight.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(list(argv) if argv is not None else None)
    if not 1 <= args.port <= 65535:
        raise SystemExit("--port must be between 1 and 65535")

    env = build_free_environment(
        os.environ,
        provider=args.provider,
        data_dir=args.data_dir,
    )
    app_target = ["app.main:app"]
    if args.procurement_multi_opportunity:
        existing = existing_procurement_state(args.data_dir)
        if existing and not args.procurement_existing_data_checked:
            raise SystemExit(
                "Existing procurement state found:\n  "
                + "\n  ".join(str(path) for path in existing)
                + "\nRun scripts/procurement_transition_preflight.py on a copy first, "
                "then add --procurement-existing-data-checked, or use a new --data-dir."
            )
        env["DECISIONDOC_PROCUREMENT_COPILOT_ENABLED"] = "1"
        app_target = ["--factory", _PROCUREMENT_FACTORY]
    if args.print_env:
        for name in _PRINTED_ENV_NAMES:
            print(f"{name}={env[name]}")
        return 0
    if args.agent_api_key:
        key_path = ensure_agent_api_key(args.data_dir)
        env["DECISIONDOC_API_KEYS"] = key_path.read_text(encoding="utf-8").strip()
        print(f"Agent API key file: {key_path}", flush=True)

    command = [
        sys.executable,
        "-m",
        "uvicorn",
        *app_target,
        "--host",
        args.host,
        "--port",
        str(args.port),
    ]
    if args.reload:
        command.append("--reload")
    print(
        f"Starting DecisionDoc free local mode at http://{args.host}:{args.port} "
        f"(provider={args.provider}, storage=local, "
        f"procurement_multi_opportunity={args.procurement_multi_opportunity})",
        flush=True,
    )
    os.execvpe(command[0], command, env)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
