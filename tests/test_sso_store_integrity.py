from __future__ import annotations

import ast
import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.storage.sso_store import (
    SSOConfig,
    SSOProvider,
    SSOSecretError,
    SSOStore,
    SSOStoreError,
    get_sso_store,
)
from app.storage.state_backend import LocalStateBackend, S3StateBackend


_NOW = "2026-07-17T00:00:00+00:00"


class _SlowLocalBackend(LocalStateBackend):
    def read_text(self, relative_path: str) -> str | None:
        raw = super().read_text(relative_path)
        time.sleep(0.005)
        return raw


class _Body:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


class _MemoryS3Client:
    def __init__(self, *, read_delay: float = 0.0) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.read_delay = read_delay

    def put_object(
        self,
        *,
        Bucket: str,
        Key: str,
        Body: bytes,
        ContentType: str,
    ) -> None:
        _ = ContentType
        self.objects[(Bucket, Key)] = Body

    def get_object(self, *, Bucket: str, Key: str) -> dict:
        time.sleep(self.read_delay)
        data = self.objects.get((Bucket, Key))
        if data is None:
            error = Exception("NoSuchKey")
            error.response = {"Error": {"Code": "NoSuchKey"}}
            raise error
        return {"Body": _Body(data)}


def _s3_backend(
    client: _MemoryS3Client | None = None,
    *,
    read_delay: float = 0.0,
) -> tuple[S3StateBackend, _MemoryS3Client]:
    selected_client = client or _MemoryS3Client(read_delay=read_delay)
    backend = S3StateBackend(
        bucket="unit-bucket",
        prefix="decisiondoc-ai/state/",
        s3_client=selected_client,
    )
    return backend, selected_client


def _record(tenant_id: str = "alpha") -> dict:
    config = SSOConfig(tenant_id=tenant_id, updated_at=_NOW)
    record = asdict(config)
    record["provider"] = config.provider.value
    return record


def _json_record(**changes: object) -> str:
    return json.dumps({**_record(), **changes})


def _client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_STORAGE", "local")
    monkeypatch.setenv("DECISIONDOC_STATE_STORAGE", "local")
    monkeypatch.setenv("JWT_SECRET_KEY", "sso-integrity-test-secret-key-32chars")
    monkeypatch.setenv("SSO_ENCRYPTION_KEY", "sso-integrity-encryption-key")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    from app.main import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


def _admin_headers() -> dict[str, str]:
    from app.services.auth_service import create_access_token

    token = create_access_token("user-1", "system", "admin", "admin")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _clear_sso_state_caches() -> None:
    import app.storage.sso_store as sso_store

    sso_store._sso_stores.clear()
    sso_store._sso_locks.clear()
    yield
    sso_store._sso_stores.clear()
    sso_store._sso_locks.clear()


@pytest.mark.parametrize(
    "tenant_id",
    [" tenant", "tenant ", ".", "..", "tenant/a", "tenant\\a", "tenant\na"],
)
def test_sso_store_rejects_unsafe_tenant_before_state_access(
    tmp_path: Path,
    tenant_id: str,
) -> None:
    with pytest.raises(ValueError, match="Invalid tenant_id"):
        SSOStore(tenant_id, data_dir=tmp_path)
    with pytest.raises(ValueError, match="Invalid tenant_id"):
        get_sso_store(tenant_id, data_dir=tmp_path)

    assert not (tmp_path / "tenants").exists()


def test_missing_sso_state_is_ephemeral_and_scoped_to_data_root(
    tmp_path: Path,
) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first = get_sso_store("alpha", data_dir=first_root)
    same = get_sso_store("alpha", data_dir=first_root)
    second = get_sso_store("alpha", data_dir=second_root)

    assert first is same
    assert first is not second
    assert first.get().provider == SSOProvider.DISABLED
    assert second.get().provider == SSOProvider.DISABLED
    assert not (first_root / "tenants").exists()
    assert not (second_root / "tenants").exists()


def test_factory_cache_is_scoped_to_explicit_backend(tmp_path: Path) -> None:
    first_backend = LocalStateBackend(tmp_path)
    second_backend = LocalStateBackend(tmp_path)

    first = get_sso_store("alpha", data_dir=tmp_path, backend=first_backend)
    same = get_sso_store("alpha", data_dir=tmp_path, backend=first_backend)
    second = get_sso_store("alpha", data_dir=tmp_path, backend=second_backend)

    assert first is same
    assert first is not second


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "{not-json",
        "[]",
        '{"tenant_id":"alpha","tenant_id":"other"}',
        json.dumps({key: value for key, value in _record().items() if key != "oauth2"}),
        _json_record(unexpected="field"),
        _json_record(provider="unknown"),
        _json_record(ldap={**_record()["ldap"], "tls": "false"}),
        _json_record(saml={"idp_entity_id": "missing-fields"}),
        _json_record(gcloud={**_record()["gcloud"], "allowed_domains": "example.com"}),
        _json_record(gcloud={**_record()["gcloud"], "default_role": "owner"}),
        _json_record(oauth2={**_record()["oauth2"], "client_secret": "plaintext"}),
        _json_record(updated_at="2026-07-17T00:00:00"),
    ],
)
def test_untrusted_sso_state_stops_reads_and_writes_without_replacement(
    tmp_path: Path,
    raw: str,
) -> None:
    path = tmp_path / "tenants/alpha/sso_config.json"
    path.parent.mkdir(parents=True)
    path.write_text(raw, encoding="utf-8")
    original_bytes = path.read_bytes()
    store = SSOStore("alpha", data_dir=tmp_path)
    replacement = SSOConfig(tenant_id="alpha", updated_at=_NOW)

    operations = (
        store.get,
        store.is_sso_enabled,
        lambda: store.save(replacement),
        lambda: store.update(lambda config: setattr(config, "updated_at", _NOW)),
    )
    for operation in operations:
        with pytest.raises(SSOStoreError):
            operation()
        assert path.read_bytes() == original_bytes


def test_invalid_caller_config_is_rejected_before_write(tmp_path: Path) -> None:
    store = SSOStore("alpha", data_dir=tmp_path)
    invalid_tenant = SSOConfig(tenant_id="other", updated_at=_NOW)
    plaintext_secret = SSOConfig(tenant_id="alpha", updated_at=_NOW)
    plaintext_secret.ldap.bind_password = "plaintext"
    invalid_role = SSOConfig(tenant_id="alpha", updated_at=_NOW)
    invalid_role.gcloud.default_role = "owner"

    for config in (invalid_tenant, plaintext_secret, invalid_role):
        with pytest.raises(ValueError):
            store.save(config)

    assert not (tmp_path / "tenants").exists()


def test_foreign_sso_state_is_hidden_and_preserved(tmp_path: Path) -> None:
    path = tmp_path / "tenants/alpha/sso_config.json"
    path.parent.mkdir(parents=True)
    foreign = _record("other")
    foreign["provider"] = "ldap"
    path.write_text(json.dumps(foreign), encoding="utf-8")
    original_bytes = path.read_bytes()
    store = SSOStore("alpha", data_dir=tmp_path)

    assert store.get().provider == SSOProvider.DISABLED
    with pytest.raises(SSOStoreError, match="preserved"):
        store.save(SSOConfig(tenant_id="alpha", updated_at=_NOW))
    with pytest.raises(SSOStoreError, match="preserved"):
        store.update(lambda config: setattr(config, "updated_at", _NOW))
    assert path.read_bytes() == original_bytes


def test_tenantless_legacy_state_can_be_read_and_claimed(tmp_path: Path) -> None:
    path = tmp_path / "tenants/alpha/sso_config.json"
    path.parent.mkdir(parents=True)
    legacy = _record()
    legacy.pop("tenant_id")
    legacy["provider"] = "ldap"
    legacy["ldap"]["server_url"] = "ldap://legacy.example"
    path.write_text(json.dumps(legacy), encoding="utf-8")
    store = SSOStore("alpha", data_dir=tmp_path)

    loaded = store.get()
    assert loaded.provider == SSOProvider.LDAP
    assert loaded.ldap.server_url == "ldap://legacy.example"

    store.update(lambda config: setattr(config, "updated_at", _NOW))
    claimed = json.loads(path.read_text(encoding="utf-8"))
    assert claimed["tenant_id"] == "alpha"


def test_secret_decryption_fails_closed_after_key_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("cryptography")
    monkeypatch.setenv("SSO_ENCRYPTION_KEY", "first-encryption-key")
    store = SSOStore("alpha", data_dir=tmp_path)
    encrypted = store.encrypt_secret("sensitive-value")

    monkeypatch.setenv("SSO_ENCRYPTION_KEY", "rotated-without-migration")
    with pytest.raises(SSOSecretError, match="cannot be decrypted"):
        store.decrypt_secret(encrypted)


def test_store_read_rejects_secret_encrypted_with_unknown_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("cryptography")
    monkeypatch.setenv("SSO_ENCRYPTION_KEY", "first-encryption-key")
    store = SSOStore("alpha", data_dir=tmp_path)
    config = SSOConfig(tenant_id="alpha", updated_at=_NOW)
    config.ldap.bind_password = store.encrypt_secret("sensitive-value")
    store.save(config)
    path = tmp_path / "tenants/alpha/sso_config.json"
    original_bytes = path.read_bytes()

    monkeypatch.setenv("SSO_ENCRYPTION_KEY", "rotated-without-migration")
    with pytest.raises(SSOStoreError, match="Invalid encrypted LDAP password"):
        store.get()
    assert path.read_bytes() == original_bytes


def _append_domain(store: SSOStore, domain: str) -> None:
    def change(config: SSOConfig) -> None:
        config.gcloud.allowed_domains.append(domain)
        config.updated_at = _NOW

    store.update(change)


def test_independent_local_stores_preserve_concurrent_partial_updates(
    tmp_path: Path,
) -> None:
    backend = _SlowLocalBackend(tmp_path)
    stores = [SSOStore("alpha", data_dir=tmp_path, backend=backend) for _ in range(12)]
    domains = [f"team-{index}.example" for index in range(len(stores))]

    with ThreadPoolExecutor(max_workers=len(stores)) as executor:
        list(executor.map(lambda pair: _append_domain(*pair), zip(stores, domains)))

    assert sorted(stores[0].get().gcloud.allowed_domains) == sorted(domains)


def test_independent_s3_stores_preserve_concurrent_partial_updates(
    tmp_path: Path,
) -> None:
    client = _MemoryS3Client(read_delay=0.005)
    backends = [_s3_backend(client)[0] for _ in range(12)]
    stores = [
        SSOStore("alpha", data_dir=tmp_path, backend=backend) for backend in backends
    ]
    domains = [f"remote-{index}.example" for index in range(len(stores))]

    with ThreadPoolExecutor(max_workers=len(stores)) as executor:
        list(executor.map(lambda pair: _append_domain(*pair), zip(stores, domains)))

    assert sorted(stores[0].get().gcloud.allowed_domains) == sorted(domains)


def test_sso_routes_use_public_factory_with_application_state_backend() -> None:
    tree = ast.parse(Path("app/routers/sso.py").read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "get_sso_store"
    ]

    assert len(calls) == 1
    assert {keyword.arg for keyword in calls[0].keywords} >= {"data_dir", "backend"}


def test_sso_api_rejects_invalid_payload_before_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(tmp_path, monkeypatch)
    headers = _admin_headers()

    unknown_provider = client.put(
        "/admin/sso/config",
        json={"provider": "unknown"},
        headers=headers,
    )
    extra_field = client.put(
        "/admin/sso/config",
        json={"ldap": {"server_url": "ldap://example", "unknown": True}},
        headers=headers,
    )
    wrong_type = client.put(
        "/admin/sso/config",
        json={"ldap": {"tls": "true"}},
        headers=headers,
    )
    oversized_domain = client.put(
        "/admin/sso/config",
        json={"gcloud": {"allowed_domains": ["x" * 254]}},
        headers=headers,
    )

    assert unknown_provider.status_code == 422
    assert extra_field.status_code == 422
    assert wrong_type.status_code == 422
    assert oversized_domain.status_code == 422
    assert not (tmp_path / "tenants/system/sso_config.json").exists()


def test_sso_api_uses_application_state_s3_backend(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(tmp_path, monkeypatch)
    backend, s3_client = _s3_backend()
    client.app.state.state_backend = backend

    response = client.put(
        "/admin/sso/config",
        json={"provider": "ldap", "ldap": {"server_url": "ldap://remote"}},
        headers=_admin_headers(),
    )

    assert response.status_code == 200
    key = (
        "unit-bucket",
        "decisiondoc-ai/state/tenants/system/sso_config.json",
    )
    assert key in s3_client.objects
    assert not (tmp_path / "tenants/system/sso_config.json").exists()


def test_sso_api_preserves_corrupt_state_across_read_and_write_routes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "tenants/system/sso_config.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"{not-json")
    client = _client(tmp_path, monkeypatch)
    headers = _admin_headers()

    read_response = client.get("/admin/sso/config", headers=headers)
    write_response = client.put(
        "/admin/sso/config",
        json={"provider": "ldap"},
        headers=headers,
    )

    assert read_response.status_code == 500
    assert read_response.json()["code"] == "INTERNAL_ERROR"
    assert write_response.status_code == 500
    assert write_response.json()["code"] == "INTERNAL_ERROR"
    assert path.read_bytes() == b"{not-json"


def test_sso_api_masked_secret_preserves_cipher_and_empty_secret_clears_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("cryptography")
    client = _client(tmp_path, monkeypatch)
    headers = _admin_headers()
    path = tmp_path / "tenants/system/sso_config.json"

    first = client.put(
        "/admin/sso/config",
        json={"provider": "ldap", "ldap": {"bind_password": "secret-value"}},
        headers=headers,
    )
    first_record = json.loads(path.read_text(encoding="utf-8"))
    encrypted = first_record["ldap"]["bind_password"]
    preserved = client.put(
        "/admin/sso/config",
        json={"ldap": {"bind_password": "***", "server_url": "ldap://new"}},
        headers=headers,
    )
    second_record = json.loads(path.read_text(encoding="utf-8"))
    cleared = client.put(
        "/admin/sso/config",
        json={"ldap": {"bind_password": ""}},
        headers=headers,
    )
    final_record = json.loads(path.read_text(encoding="utf-8"))

    assert first.status_code == 200
    assert encrypted and encrypted != "secret-value"
    assert preserved.status_code == 200
    assert second_record["ldap"]["bind_password"] == encrypted
    assert second_record["ldap"]["server_url"] == "ldap://new"
    assert cleared.status_code == 200
    assert final_record["ldap"]["bind_password"] == ""


def test_saml_routes_receive_decrypted_private_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("cryptography")
    client = _client(tmp_path, monkeypatch)
    store = get_sso_store(
        "system",
        data_dir=tmp_path,
        backend=client.app.state.state_backend,
    )
    config = SSOConfig(tenant_id="system", provider=SSOProvider.SAML, updated_at=_NOW)
    config.saml.sp_private_key = store.encrypt_secret("private-key-value")
    store.save(config)
    observed: list[str] = []

    def build_metadata(saml_config) -> str:
        observed.append(saml_config.sp_private_key)
        return "<xml/>"

    monkeypatch.setattr(
        "app.services.sso.saml_auth.build_sp_metadata",
        build_metadata,
    )
    response = client.get("/saml/metadata")

    assert response.status_code == 200
    assert observed == ["private-key-value"]


def test_saml_login_sets_relay_state_cookie(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(tmp_path, monkeypatch)
    store = get_sso_store(
        "system",
        data_dir=tmp_path,
        backend=client.app.state.state_backend,
    )
    store.update(lambda config: setattr(config, "provider", SSOProvider.SAML))

    response = client.get("/saml/login", follow_redirects=False)

    assert response.status_code in (302, 307)
    assert "saml_relay_state=" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=none" in response.headers["set-cookie"]
    assert "Secure" in response.headers["set-cookie"]


def test_saml_acs_rejects_missing_relay_state_before_parsing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(tmp_path, monkeypatch)
    store = get_sso_store(
        "system",
        data_dir=tmp_path,
        backend=client.app.state.state_backend,
    )
    store.update(lambda config: setattr(config, "provider", SSOProvider.SAML))
    parsed: list[str] = []

    def parse(*args, **kwargs):
        parsed.append("called")
        return None

    monkeypatch.setattr("app.services.sso.saml_auth.parse_saml_response", parse)
    response = client.post(
        "/saml/acs",
        data={"SAMLResponse": "unsigned-response"},
    )

    assert response.status_code == 400
    assert parsed == []


def test_saml_acs_rejects_unsigned_response_with_matching_relay_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(tmp_path, monkeypatch)
    store = get_sso_store(
        "system",
        data_dir=tmp_path,
        backend=client.app.state.state_backend,
    )

    def configure(config: SSOConfig) -> None:
        config.provider = SSOProvider.SAML
        config.saml.idp_certificate = "untrusted-test-certificate"
        config.updated_at = _NOW

    store.update(configure)
    client.cookies.set("saml_relay_state", "relay-state")
    response = client.post(
        "/saml/acs",
        data={"SAMLResponse": "unsigned-response", "RelayState": "relay-state"},
    )

    assert response.status_code == 401


def test_ldap_login_uses_strict_input_and_returns_browser_tokens(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.sso.ldap_auth import LDAPUser

    client = _client(tmp_path, monkeypatch)
    store = get_sso_store(
        "system",
        data_dir=tmp_path,
        backend=client.app.state.state_backend,
    )
    store.update(lambda config: setattr(config, "provider", SSOProvider.LDAP))
    monkeypatch.setattr(
        "app.services.sso.ldap_auth.authenticate_ldap",
        lambda config, username, password: LDAPUser(
            username=username,
            display_name="Directory User",
            email="directory@example.com",
            role="member",
        ),
    )

    invalid = client.post("/auth/ldap-login", json=[])
    extra = client.post(
        "/auth/ldap-login",
        json={"username": "directory", "password": "secret", "extra": True},
    )
    response = client.post(
        "/auth/ldap-login",
        json={"username": "directory", "password": "secret"},
    )

    assert invalid.status_code == 422
    assert extra.status_code == 422
    assert response.status_code == 200
    payload = response.json()
    assert payload["token"] == payload["access_token"]
    assert payload["refresh_token"]
    assert payload["user"]["username"] == "directory"


def test_gcloud_callback_rejects_missing_state_before_exchange(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(tmp_path, monkeypatch)
    exchanges: list[str] = []

    def exchange(*args, **kwargs):
        exchanges.append("called")
        return None

    monkeypatch.setattr("app.services.sso.gcloud_auth.exchange_gcloud_code", exchange)
    response = client.get("/sso/gcloud/callback?code=provider-code")

    assert response.status_code == 400
    assert exchanges == []
