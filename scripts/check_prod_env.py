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
SUPPORTED_PROVIDER_PROFILES = {"standard", "quality-first"}
PROVIDER_ENV_KEYS = (
    "DECISIONDOC_PROVIDER",
    "DECISIONDOC_PROVIDER_GENERATION",
    "DECISIONDOC_PROVIDER_ATTACHMENT",
    "DECISIONDOC_PROVIDER_VISUAL",
)
CAPABILITY_PROVIDER_ENV = {
    "generation": "DECISIONDOC_PROVIDER_GENERATION",
    "attachment": "DECISIONDOC_PROVIDER_ATTACHMENT",
    "visual": "DECISIONDOC_PROVIDER_VISUAL",
}


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


def _resolve_provider_routes(
    env: dict[str, str],
) -> tuple[list[str], dict[str, list[str]], dict[str, bool]]:
    base_providers = _split_csv(env.get("DECISIONDOC_PROVIDER", ""))
    routes: dict[str, list[str]] = {"default": list(base_providers)}
    explicit_routes: dict[str, bool] = {}
    for capability, env_key in CAPABILITY_PROVIDER_ENV.items():
        raw = env.get(env_key, "").strip()
        explicit_routes[capability] = bool(raw)
        routes[capability] = _split_csv(raw) if raw else list(base_providers)
    return base_providers, routes, explicit_routes


def _validate_provider(
    env: dict[str, str],
    errors: list[str],
    warnings: list[str],
) -> tuple[list[str], dict[str, list[str]], dict[str, bool]]:
    base_providers, routes, explicit_routes = _resolve_provider_routes(env)
    if not base_providers:
        errors.append("DECISIONDOC_PROVIDER is required")
        return base_providers, routes, explicit_routes
    if env.get("DECISIONDOC_ENV", "").strip() != "prod":
        errors.append("DECISIONDOC_ENV must be prod for production deployment")

    all_providers: set[str] = set()
    for env_key in PROVIDER_ENV_KEYS:
        if env_key == "DECISIONDOC_PROVIDER":
            providers = list(base_providers)
        else:
            capability = next(
                (name for name, configured_env_key in CAPABILITY_PROVIDER_ENV.items() if configured_env_key == env_key),
                "",
            )
            providers = list(routes.get(capability, []))
        unknown = [provider for provider in providers if provider not in SUPPORTED_PROVIDERS]
        if unknown:
            errors.append(f"Unsupported {env_key} value(s): {', '.join(unknown)}")
        all_providers.update(providers)
        if "mock" in providers:
            warnings.append(f"{env_key} includes mock; verify this is intentional for prod")

    if "openai" in all_providers:
        openai_key = env.get("OPENAI_API_KEY", "").strip()
        if _is_placeholder(openai_key):
            errors.append("OPENAI_API_KEY is missing or still uses a placeholder value")
        elif not (openai_key.startswith("sk-") or openai_key.startswith("sk-proj-")):
            errors.append("OPENAI_API_KEY does not look like a real OpenAI API key")
    if "gemini" in all_providers:
        gemini_key = env.get("GEMINI_API_KEY", "").strip()
        if _is_placeholder(gemini_key):
            errors.append("GEMINI_API_KEY is missing or still uses a placeholder value")
    if "claude" in all_providers:
        claude_key = env.get("ANTHROPIC_API_KEY", "").strip()
        if _is_placeholder(claude_key):
            errors.append("ANTHROPIC_API_KEY is missing or still uses a placeholder value")
    return base_providers, routes, explicit_routes


def _validate_quality_first_provider_profile(
    env: dict[str, str],
    *,
    base_providers: list[str],
    routes: dict[str, list[str]],
    explicit_routes: dict[str, bool],
    errors: list[str],
) -> None:
    expected_default = {"claude", "gemini", "openai"}
    missing_default = expected_default - set(base_providers)
    if missing_default:
        errors.append(
            "DECISIONDOC_PROVIDER must include claude, gemini, openai when --provider-profile=quality-first"
        )
    if base_providers and base_providers[0] not in {"claude", "gemini"}:
        errors.append(
            "DECISIONDOC_PROVIDER must prioritize claude or gemini ahead of openai when --provider-profile=quality-first"
        )
    if any(provider in {"mock", "local"} for provider in base_providers):
        errors.append("DECISIONDOC_PROVIDER cannot include mock/local when --provider-profile=quality-first")

    for capability, env_key in CAPABILITY_PROVIDER_ENV.items():
        if not explicit_routes.get(capability):
            errors.append(f"{env_key} must be explicitly set when --provider-profile=quality-first")

    generation_route = routes.get("generation", [])
    if {"claude", "gemini"} - set(generation_route):
        errors.append(
            "DECISIONDOC_PROVIDER_GENERATION must include both claude and gemini when --provider-profile=quality-first"
        )
    if generation_route and generation_route[0] not in {"claude", "gemini"}:
        errors.append(
            "DECISIONDOC_PROVIDER_GENERATION must prioritize claude or gemini first when --provider-profile=quality-first"
        )
    if any(provider in {"mock", "local"} for provider in generation_route):
        errors.append("DECISIONDOC_PROVIDER_GENERATION cannot include mock/local when --provider-profile=quality-first")

    attachment_route = routes.get("attachment", [])
    if {"claude", "gemini"} - set(attachment_route):
        errors.append(
            "DECISIONDOC_PROVIDER_ATTACHMENT must include both claude and gemini when --provider-profile=quality-first"
        )
    if attachment_route and attachment_route[0] not in {"gemini", "claude"}:
        errors.append(
            "DECISIONDOC_PROVIDER_ATTACHMENT must prioritize gemini or claude first when --provider-profile=quality-first"
        )
    if any(provider in {"mock", "local"} for provider in attachment_route):
        errors.append("DECISIONDOC_PROVIDER_ATTACHMENT cannot include mock/local when --provider-profile=quality-first")

    visual_route = routes.get("visual", [])
    if visual_route != ["openai"]:
        errors.append(
            "DECISIONDOC_PROVIDER_VISUAL must be exactly openai when --provider-profile=quality-first because direct visual asset generation is only implemented for OpenAI in this deployment"
        )


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


def validate_prod_env(
    env: dict[str, str],
    *,
    expected_origin: str = "",
    provider_profile: str = "standard",
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    _validate_required(env, errors)
    base_providers, routes, explicit_routes = _validate_provider(env, errors, warnings)
    if provider_profile == "quality-first":
        _validate_quality_first_provider_profile(
            env,
            base_providers=base_providers,
            routes=routes,
            explicit_routes=explicit_routes,
            errors=errors,
        )
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
    parser.add_argument(
        "--provider-profile",
        choices=sorted(SUPPORTED_PROVIDER_PROFILES),
        default="standard",
        help="Provider routing policy to enforce. Use quality-first to require explicit multi-provider generation/attachment routes and an openai visual route.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    env_file = Path(args.env_file).expanduser()
    env = _load_env_file(env_file)
    errors, warnings = validate_prod_env(
        env,
        expected_origin=str(args.expected_origin or ""),
        provider_profile=str(args.provider_profile or "standard"),
    )

    print(f"Validated env file: {env_file}")
    print(f"Provider profile: {args.provider_profile}")
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
