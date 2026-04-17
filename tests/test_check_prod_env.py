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


def test_check_prod_env_accepts_valid_openai_prod_env(tmp_path: Path) -> None:
    checker = _load_script_module("decisiondoc_check_prod_env_valid", "scripts/check_prod_env.py")
    env_file = tmp_path / ".env.prod"
    env_file.write_text(
        "\n".join(
            [
                "DECISIONDOC_ENV=prod",
                "DECISIONDOC_PROVIDER=openai",
                "DECISIONDOC_STORAGE=local",
                "JWT_SECRET_KEY=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
                "ALLOWED_ORIGINS=https://dawool.decisiondoc.kr",
                "DECISIONDOC_API_KEYS=ddoc_api_key_1",
                "DECISIONDOC_OPS_KEY=ddoc_ops_key_1",
                "OPENAI_API_KEY=sk-proj-valid-openai-key",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    exit_code = checker.main(
        [
            "--env-file",
            str(env_file),
            "--expected-origin",
            "https://dawool.decisiondoc.kr",
        ]
    )

    assert exit_code == 0


def test_check_prod_env_rejects_placeholder_and_duplicate_keys(tmp_path: Path) -> None:
    checker = _load_script_module("decisiondoc_check_prod_env_invalid", "scripts/check_prod_env.py")
    env_file = tmp_path / ".env.prod"
    env_file.write_text(
        "\n".join(
            [
                "DECISIONDOC_ENV=prod",
                "DECISIONDOC_PROVIDER=openai",
                "DECISIONDOC_STORAGE=local",
                "JWT_SECRET_KEY=short-key",
                "ALLOWED_ORIGINS=https://dawool.decisiondoc.kr",
                "DECISIONDOC_API_KEYS=<dawool-api-keys>",
                "DECISIONDOC_OPS_KEY=<dawool-api-keys>",
                "OPENAI_API_KEY=<dawool-openai-api-key>",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    exit_code = checker.main(
        [
            "--env-file",
            str(env_file),
            "--expected-origin",
            "https://dawool.decisiondoc.kr",
        ]
    )

    assert exit_code == 1


def test_check_prod_env_rejects_expected_origin_mismatch(tmp_path: Path) -> None:
    checker = _load_script_module("decisiondoc_check_prod_env_origin", "scripts/check_prod_env.py")
    env_file = tmp_path / ".env.prod"
    env_file.write_text(
        "\n".join(
            [
                "DECISIONDOC_ENV=prod",
                "DECISIONDOC_PROVIDER=openai",
                "DECISIONDOC_STORAGE=local",
                "JWT_SECRET_KEY=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
                "ALLOWED_ORIGINS=https://admin.decisiondoc.kr",
                "DECISIONDOC_API_KEYS=ddoc_api_key_1",
                "DECISIONDOC_OPS_KEY=ddoc_ops_key_1",
                "OPENAI_API_KEY=sk-valid-openai-key",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    exit_code = checker.main(
        [
            "--env-file",
            str(env_file),
            "--expected-origin",
            "https://dawool.decisiondoc.kr",
        ]
    )

    assert exit_code == 1


def test_check_prod_env_accepts_valid_claude_prod_env(tmp_path: Path) -> None:
    checker = _load_script_module("decisiondoc_check_prod_env_claude", "scripts/check_prod_env.py")
    env_file = tmp_path / ".env.prod"
    env_file.write_text(
        "\n".join(
            [
                "DECISIONDOC_ENV=prod",
                "DECISIONDOC_PROVIDER=openai,claude",
                "DECISIONDOC_STORAGE=local",
                "JWT_SECRET_KEY=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
                "ALLOWED_ORIGINS=https://admin.decisiondoc.kr",
                "DECISIONDOC_API_KEYS=ddoc_api_key_1",
                "DECISIONDOC_OPS_KEY=ddoc_ops_key_1",
                "OPENAI_API_KEY=sk-proj-valid-openai-key",
                "ANTHROPIC_API_KEY=sk-ant-valid-key",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    exit_code = checker.main(
        [
            "--env-file",
            str(env_file),
            "--expected-origin",
            "https://admin.decisiondoc.kr",
        ]
    )

    assert exit_code == 0
