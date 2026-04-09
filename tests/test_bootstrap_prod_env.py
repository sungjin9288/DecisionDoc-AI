from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_script_module(module_name: str, relative_path: str):
    path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_bootstrap_prod_env_renders_admin_profile(tmp_path: Path) -> None:
    bootstrap = _load_script_module("decisiondoc_bootstrap_prod_env_admin", "scripts/bootstrap_prod_env.py")
    output = tmp_path / ".env.prod"

    rendered_path = bootstrap.bootstrap_prod_env(
        profile="admin",
        output_file=output,
        openai_api_key="sk-proj-admin-test-key",
    )

    assert rendered_path == output
    contents = output.read_text(encoding="utf-8")
    assert "DECISIONDOC_ENV=prod" in contents
    assert "ALLOWED_ORIGINS=https://admin.decisiondoc.kr" in contents
    assert "OPENAI_API_KEY=sk-proj-admin-test-key" in contents
    assert "<admin-jwt-secret>" not in contents
    assert "<admin-api-keys>" not in contents
    assert "<admin-ops-key>" not in contents


def test_bootstrap_prod_env_can_override_origin_and_keys(tmp_path: Path) -> None:
    bootstrap = _load_script_module("decisiondoc_bootstrap_prod_env_override", "scripts/bootstrap_prod_env.py")
    output = tmp_path / ".env.prod"

    rendered_path = bootstrap.bootstrap_prod_env(
        profile="dawool",
        output_file=output,
        openai_api_key="sk-dawool-test-key",
        origin="https://pilot.decisiondoc.kr",
        jwt_secret="jwt-secret-32chars-jwt-secret-32chars",
        api_key="custom-api-key",
        ops_key="custom-ops-key",
    )

    assert rendered_path == output
    contents = output.read_text(encoding="utf-8")
    assert "ALLOWED_ORIGINS=https://pilot.decisiondoc.kr" in contents
    assert "JWT_SECRET_KEY=jwt-secret-32chars-jwt-secret-32chars" in contents
    assert "DECISIONDOC_API_KEYS=custom-api-key" in contents
    assert "DECISIONDOC_OPS_KEY=custom-ops-key" in contents


def test_bootstrap_prod_env_refuses_overwrite_without_force(tmp_path: Path) -> None:
    bootstrap = _load_script_module("decisiondoc_bootstrap_prod_env_force", "scripts/bootstrap_prod_env.py")
    output = tmp_path / ".env.prod"
    output.write_text("EXISTING=1\n", encoding="utf-8")

    try:
        bootstrap.bootstrap_prod_env(
            profile="admin",
            output_file=output,
            openai_api_key="sk-proj-existing-key",
        )
    except SystemExit as exc:
        message = str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected SystemExit when output exists without --force")

    assert "Output file already exists" in message
