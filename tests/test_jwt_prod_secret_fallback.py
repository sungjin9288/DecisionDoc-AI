"""Production must never sign or accept JWTs with the built-in development key.

Regression for a split production check: ``create_app`` treated
``DECISIONDOC_ENV=prod`` as production (the SAM template sets only that),
while ``get_jwt_secret_key`` looked at ``ENVIRONMENT`` alone. A prod
deployment without ``JWT_SECRET_KEY`` therefore signed tokens with the public
development default, and a token forged with it skipped the API key gate.
"""
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient

from app.config import _DEV_JWT_SECRET_KEY


def _prod_env(tmp_path, monkeypatch, **overrides):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_TEMPLATE_VERSION", "v1")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.setenv("DECISIONDOC_ENV", "prod")
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    monkeypatch.setenv("DECISIONDOC_API_KEY", "expected-key")
    for name, value in overrides.items():
        monkeypatch.setenv(name, value)


def _forged_admin_token() -> str:
    payload = {
        "sub": "attacker",
        "tenant_id": "system",
        "role": "admin",
        "username": "attacker",
        "credential_version": 0,
        "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
    }
    return jwt.encode(payload, _DEV_JWT_SECRET_KEY, algorithm="HS256")


@pytest.mark.parametrize(
    "env",
    [
        {"DECISIONDOC_ENV": "prod"},
        {"DECISIONDOC_ENV": "production"},
        {"DECISIONDOC_ENV": "dev", "ENVIRONMENT": "production"},
        {"DECISIONDOC_ENV": "dev", "ENVIRONMENT": "prod"},
    ],
)
def test_production_without_jwt_secret_fails_at_startup(tmp_path, monkeypatch, env):
    _prod_env(tmp_path, monkeypatch, **env)
    from app.main import create_app

    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        create_app()


def test_jwt_secret_key_refuses_dev_default_when_decisiondoc_env_is_prod(monkeypatch):
    monkeypatch.setenv("DECISIONDOC_ENV", "prod")
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    from app.config import get_jwt_secret_key

    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        get_jwt_secret_key()


def test_jwt_secret_key_rejects_short_key_when_decisiondoc_env_is_prod(monkeypatch):
    monkeypatch.setenv("DECISIONDOC_ENV", "prod")
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.setenv("JWT_SECRET_KEY", "tooshort")
    from app.config import get_jwt_secret_key

    with pytest.raises(RuntimeError, match="too short"):
        get_jwt_secret_key()


def test_forged_dev_key_token_is_rejected_in_prod(tmp_path, monkeypatch):
    _prod_env(tmp_path, monkeypatch, JWT_SECRET_KEY="p" * 48)
    from app.main import create_app

    client = TestClient(create_app())
    response = client.post(
        "/generate",
        headers={"Authorization": f"Bearer {_forged_admin_token()}"},
        json={"title": "t", "goal": "g"},
    )
    assert response.status_code == 401


def test_dev_without_jwt_secret_still_starts(tmp_path, monkeypatch):
    _prod_env(tmp_path, monkeypatch, DECISIONDOC_ENV="dev")
    from app.main import create_app

    create_app()
