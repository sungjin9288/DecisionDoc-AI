#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = REPO_ROOT / ".env.prod"
SUPPORTED_PROVIDERS = {"openai", "gemini", "claude", "local", "mock"}
SUPPORTED_STORAGES = {"local", "s3"}


def _load_env_file(env_file: Path) -> dict[str, str]:
    resolved = Path(env_file).expanduser()
    if not resolved.exists():
        raise SystemExit(f"Env file not found: {resolved}")
    loaded: dict[str, str] = {}
    for lineno, raw_line in enumerate(resolved.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            raise SystemExit(f"Invalid env file line {lineno}: {resolved}")
        key, value = line.split("=", 1)
        normalized_key = key.strip()
        if not normalized_key:
            raise SystemExit(f"Invalid env file line {lineno}: {resolved}")
        normalized_value = value.strip()
        if (
            len(normalized_value) >= 2
            and normalized_value[0] == normalized_value[-1]
            and normalized_value[0] in {'"', "'"}
        ):
            normalized_value = normalized_value[1:-1]
        loaded[normalized_key] = normalized_value
    return loaded


def _is_placeholder(value: str) -> bool:
    normalized = str(value or "").strip()
    if not normalized:
        return True
    lower = normalized.lower()
    if normalized.startswith("<") and normalized.endswith(">"):
        return True
    placeholder_values = {
        "your-ops-key",
        "your-secret-key-here",
        "key1,key2",
        "my-bucket",
        "https://yourdomain.com",
        "http://localhost:3000,http://localhost:8000",
        "sk-...",
        "sk-ant-...",
        "aiza...",
    }
    if lower in placeholder_values:
        return True
    if "changeme" in lower or "replace-me" in lower:
        return True
    return False


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _validate_required(env: dict[str, str], errors: list[str]) -> None:
    for key in ("DECISIONDOC_ENV", "DECISIONDOC_PROVIDER", "DECISIONDOC_STORAGE", "JWT_SECRET_KEY", "ALLOWED_ORIGINS"):
        if _is_placeholder(env.get(key, "")):
            errors.append(f"{key} is missing or still uses a placeholder value")


def _validate_provider(env: dict[str, str], errors: list[str], warnings: list[str]) -> list[str]:
    providers = _split_csv(env.get("DECISIONDOC_PROVIDER", ""))
    if not providers:
        errors.append("DECISIONDOC_PROVIDER is required")
        return []
    unknown = [provider for provider in providers if provider not in SUPPORTED_PROVIDERS]
    if unknown:
        errors.append(f"Unsupported DECISIONDOC_PROVIDER value(s): {', '.join(unknown)}")
    if env.get("DECISIONDOC_ENV", "").strip() != "prod":
        errors.append("DECISIONDOC_ENV must be prod for production deployment")
    if "openai" in providers:
        openai_key = env.get("OPENAI_API_KEY", "").strip()
        if _is_placeholder(openai_key):
            errors.append("OPENAI_API_KEY is missing or still uses a placeholder value")
        elif not (openai_key.startswith("sk-") or openai_key.startswith("sk-proj-")):
            errors.append("OPENAI_API_KEY does not look like a real OpenAI API key")
    if "gemini" in providers:
        gemini_key = env.get("GEMINI_API_KEY", "").strip()
        if _is_placeholder(gemini_key):
            errors.append("GEMINI_API_KEY is missing or still uses a placeholder value")
    if "claude" in providers:
        claude_key = env.get("ANTHROPIC_API_KEY", "").strip()
        if _is_placeholder(claude_key):
            errors.append("ANTHROPIC_API_KEY is missing or still uses a placeholder value")
    if "mock" in providers:
        warnings.append("DECISIONDOC_PROVIDER includes mock; verify this is intentional for prod")
    return providers


def _validate_storage(env: dict[str, str], errors: list[str]) -> None:
    storage = env.get("DECISIONDOC_STORAGE", "").strip()
    if storage not in SUPPORTED_STORAGES:
        errors.append(f"Unsupported DECISIONDOC_STORAGE value: {storage or '<empty>'}")
        return
    if storage == "s3" and _is_placeholder(env.get("DECISIONDOC_S3_BUCKET", "")):
        errors.append("DECISIONDOC_S3_BUCKET is required when DECISIONDOC_STORAGE=s3")


def _validate_keys(env: dict[str, str], errors: list[str], warnings: list[str]) -> None:
    jwt_secret = env.get("JWT_SECRET_KEY", "").strip()
    if jwt_secret and len(jwt_secret) < 32:
        errors.append("JWT_SECRET_KEY must be at least 32 characters long")

    api_keys = _split_csv(env.get("DECISIONDOC_API_KEYS", ""))
    if not api_keys:
        errors.append("DECISIONDOC_API_KEYS must contain at least one runtime API key")
    if any(_is_placeholder(key) for key in api_keys):
        errors.append("DECISIONDOC_API_KEYS contains a placeholder value")
    if len(api_keys) != len(set(api_keys)):
        errors.append("DECISIONDOC_API_KEYS contains duplicate values")

    ops_key = env.get("DECISIONDOC_OPS_KEY", "").strip()
    if _is_placeholder(ops_key):
        errors.append("DECISIONDOC_OPS_KEY is missing or still uses a placeholder value")
    elif ops_key in api_keys:
        errors.append("DECISIONDOC_OPS_KEY must be different from DECISIONDOC_API_KEYS")

    legacy_api_key = env.get("DECISIONDOC_API_KEY", "").strip()
    if legacy_api_key:
        if _is_placeholder(legacy_api_key):
            errors.append("DECISIONDOC_API_KEY is set but still uses a placeholder value")
        elif legacy_api_key not in api_keys:
            warnings.append("DECISIONDOC_API_KEY is not included in DECISIONDOC_API_KEYS overlap list")


def _validate_origins(env: dict[str, str], expected_origin: str, errors: list[str], warnings: list[str]) -> None:
    raw_origins = env.get("ALLOWED_ORIGINS", "").strip()
    origins = _split_csv(raw_origins)
    if not origins:
        errors.append("ALLOWED_ORIGINS must contain at least one origin")
        return
    if any(_is_placeholder(origin) for origin in origins):
        errors.append("ALLOWED_ORIGINS contains a placeholder value")
    if expected_origin:
        if expected_origin not in origins:
            errors.append(f"ALLOWED_ORIGINS does not include expected origin: {expected_origin}")
    for origin in origins:
        if not origin.startswith("https://"):
            warnings.append(f"ALLOWED_ORIGINS contains a non-HTTPS origin: {origin}")


def validate_prod_env(env: dict[str, str], *, expected_origin: str = "") -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    _validate_required(env, errors)
    _validate_provider(env, errors, warnings)
    _validate_storage(env, errors)
    _validate_keys(env, errors, warnings)
    _validate_origins(env, expected_origin.strip(), errors, warnings)
    return errors, warnings


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate a DecisionDoc production env file before rollout.",
    )
    parser.add_argument(
        "--env-file",
        default=str(DEFAULT_ENV_FILE),
        help="Path to the env file to validate. Default: .env.prod in repo root",
    )
    parser.add_argument(
        "--expected-origin",
        default="",
        help="Require ALLOWED_ORIGINS to include this origin",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    env_file = Path(args.env_file).expanduser()
    env = _load_env_file(env_file)
    errors, warnings = validate_prod_env(env, expected_origin=str(args.expected_origin or ""))

    print(f"Validated env file: {env_file}")
    if warnings:
        for warning in warnings:
            print(f"WARN  {warning}")
    if errors:
        for error in errors:
            print(f"FAIL  {error}")
        return 1

    print("PASS  Production env preflight passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
