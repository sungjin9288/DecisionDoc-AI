"""tests/test_sso.py — SSO system tests (storage, auth services, API endpoints).

Coverage (20+ tests):
  Storage       : SSOStore get/save/is_enabled, encrypt/decrypt
  LDAP          : _determine_role, test_ldap_connection (no server), ldap_auth error handling
  SAML          : build_authn_request (basic), parse_saml_response (basic), sp_metadata
  GCloud        : build_gcloud_auth_url URL params, exchange_gcloud_code (mock)
  API endpoints : GET/PUT /admin/sso/config, POST /admin/sso/test-ldap,
                  GET /saml/metadata, GET /saml/login (redirect),
                  POST /auth/ldap-login (no ldap → 400), GET /sso/gcloud (redirect)
"""
from __future__ import annotations
import json
import os
import pytest
from fastapi.testclient import TestClient

TEST_JWT_SECRET_KEY = "test-secret-key-for-sso-testing-32chars!!"
TEST_SSO_STORE_SECRET_KEY = "test-key-32chars-padding-padding!!"


# ── module-level cache cleanup ────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _reset_sso_store_cache():
    """Clear the sso_stores singleton cache before/after each test."""
    from app.storage import sso_store as _ss
    _ss._sso_stores.clear()
    yield
    _ss._sso_stores.clear()


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_TEMPLATE_VERSION", "v1")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_JWT_SECRET_KEY)
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    from app.main import create_app
    return TestClient(create_app(), raise_server_exceptions=False)


@pytest.fixture
def admin_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_TEMPLATE_VERSION", "v1")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_JWT_SECRET_KEY)
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    from app.main import create_app
    app = create_app()
    tc = TestClient(app, raise_server_exceptions=False)
    # Register first user (becomes admin) then login
    tc.post(
        "/auth/register",
        json={
            "username": "admin",
            "display_name": "Admin",
            "email": "a@t.com",
            "password": "Admin@1234",
        },
    )
    res = tc.post("/auth/login", json={"username": "admin", "password": "Admin@1234"})
    token = res.json().get("access_token", "")
    tc.headers.update({"Authorization": f"Bearer {token}"})
    return tc, tmp_path


# ── SSOStore tests ─────────────────────────────────────────────────────────────

def test_sso_store_default_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_SSO_STORE_SECRET_KEY)
    from app.storage.sso_store import SSOStore, SSOProvider
    store = SSOStore("t1")
    cfg = store.get()
    assert cfg.provider == SSOProvider.DISABLED


def test_sso_store_save_and_get(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_SSO_STORE_SECRET_KEY)
    from app.storage.sso_store import SSOStore, SSOProvider
    store = SSOStore("t2")
    cfg = store.get()
    cfg.provider = SSOProvider.LDAP
    cfg.ldap.server_url = "ldap://dc.test:389"
    store.save(cfg)
    # Re-load from a fresh instance
    store2 = SSOStore("t2")
    cfg2 = store2.get()
    assert cfg2.provider == SSOProvider.LDAP
    assert cfg2.ldap.server_url == "ldap://dc.test:389"


def test_sso_store_encrypt_decrypt(tmp_path, monkeypatch):
    pytest.importorskip("cryptography", reason="cryptography package not installed")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_SSO_STORE_SECRET_KEY)
    from app.storage.sso_store import SSOStore
    store = SSOStore("t3")
    plain = "super-secret-password"
    encrypted = store.encrypt_secret(plain)
    assert encrypted != plain
    assert encrypted != ""
    decrypted = store.decrypt_secret(encrypted)
    assert decrypted == plain


def test_sso_store_encrypt_empty(tmp_path, monkeypatch):
    """Empty string encrypt/decrypt is always safe (no crypto needed)."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_SSO_STORE_SECRET_KEY)
    from app.storage.sso_store import SSOStore
    store = SSOStore("t4")
    # Empty strings bypass crypto entirely
    assert store.encrypt_secret("") == ""
    assert store.decrypt_secret("") == ""


def test_sso_store_is_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_SSO_STORE_SECRET_KEY)
    from app.storage.sso_store import SSOStore, SSOProvider
    store = SSOStore("t5")
    assert not store.is_sso_enabled()
    cfg = store.get()
    cfg.provider = SSOProvider.LDAP
    store.save(cfg)
    # Reload to pick up saved state
    store2 = SSOStore("t5")
    assert store2.is_sso_enabled()


def test_sso_store_get_sso_store_factory(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_SSO_STORE_SECRET_KEY)
    from app.storage.sso_store import get_sso_store
    # Factory returns the same instance for the same tenant_id
    s1 = get_sso_store("tenant-x")
    s2 = get_sso_store("tenant-x")
    assert s1 is s2


# ── LDAP helper tests ──────────────────────────────────────────────────────────

def test_determine_role_admin():
    from app.services.sso.ldap_auth import _determine_role
    from app.storage.sso_store import LDAPConfig
    cfg = LDAPConfig(admin_group="CN=Admins,DC=corp,DC=local")
    role = _determine_role(cfg, ["CN=Admins,DC=corp,DC=local", "CN=Users"])
    assert role == "admin"


def test_determine_role_member():
    from app.services.sso.ldap_auth import _determine_role
    from app.storage.sso_store import LDAPConfig
    cfg = LDAPConfig(admin_group="CN=Admins,DC=corp", member_group="CN=Members,DC=corp")
    role = _determine_role(cfg, ["CN=Members,DC=corp"])
    assert role == "member"


def test_determine_role_viewer_fallback():
    from app.services.sso.ldap_auth import _determine_role
    from app.storage.sso_store import LDAPConfig
    cfg = LDAPConfig(admin_group="CN=Admins", member_group="CN=Members", viewer_group="CN=Viewers")
    role = _determine_role(cfg, ["CN=Other"])
    assert role == "viewer"


def test_determine_role_default_member_when_no_groups():
    from app.services.sso.ldap_auth import _determine_role
    from app.storage.sso_store import LDAPConfig
    cfg = LDAPConfig()
    role = _determine_role(cfg, [])
    assert role == "member"


def test_determine_role_admin_case_insensitive():
    from app.services.sso.ldap_auth import _determine_role
    from app.storage.sso_store import LDAPConfig
    cfg = LDAPConfig(admin_group="CN=ADMINS,DC=CORP")
    role = _determine_role(cfg, ["cn=admins,dc=corp"])
    assert role == "admin"


def test_ldap_test_connection_empty_url():
    from app.services.sso.ldap_auth import test_ldap_connection
    from app.storage.sso_store import LDAPConfig
    result = test_ldap_connection(LDAPConfig())
    assert result["ok"] is False
    msg = result["message"].lower()
    assert any(kw in msg for kw in ("server_url", "empty", "not installed", "ldap3"))


def test_ldap_test_connection_unreachable_host():
    from app.services.sso.ldap_auth import test_ldap_connection
    from app.storage.sso_store import LDAPConfig
    # Use a localhost port that's almost certainly not open
    result = test_ldap_connection(LDAPConfig(server_url="ldap://127.0.0.1:39999"))
    # Either ldap3 is missing (ok=False) or connection fails (ok=False)
    assert result["ok"] is False


# ── SAML tests ─────────────────────────────────────────────────────────────────

def test_build_authn_request_returns_url_and_state():
    from app.services.sso.saml_auth import build_authn_request
    from app.storage.sso_store import SAMLConfig
    cfg = SAMLConfig(
        idp_sso_url="https://idp.example.com/sso",
        sp_entity_id="https://sp.example.com",
        sp_acs_url="https://sp.example.com/saml/acs",
    )
    url, state = build_authn_request(cfg)
    assert "SAMLRequest" in url
    assert len(state) > 8


def test_parse_saml_response_invalid_returns_none():
    from app.services.sso.saml_auth import parse_saml_response
    from app.storage.sso_store import SAMLConfig
    cfg = SAMLConfig()
    import base64
    result = parse_saml_response(cfg, base64.b64encode(b"notvalid").decode())
    assert result is None


def test_build_sp_metadata_contains_entity_id():
    from app.services.sso.saml_auth import build_sp_metadata
    from app.storage.sso_store import SAMLConfig
    cfg = SAMLConfig(sp_entity_id="https://sp.example.com", sp_acs_url="https://sp.example.com/acs")
    xml = build_sp_metadata(cfg)
    assert "sp.example.com" in xml


def test_build_sp_metadata_contains_acs_url():
    from app.services.sso.saml_auth import build_sp_metadata
    from app.storage.sso_store import SAMLConfig
    cfg = SAMLConfig(sp_entity_id="https://sp.test", sp_acs_url="https://sp.test/saml/acs")
    xml = build_sp_metadata(cfg)
    assert "/saml/acs" in xml


# ── GCloud tests ───────────────────────────────────────────────────────────────

def test_build_gcloud_auth_url_params():
    from app.services.sso.gcloud_auth import build_gcloud_auth_url
    from app.storage.sso_store import GCloudConfig
    cfg = GCloudConfig(client_id="my-client-id", hd="agency.go.kr")
    url, state = build_gcloud_auth_url(cfg, "https://app.example.com/sso/gcloud/callback")
    assert "client_id=my-client-id" in url
    assert "hd=agency.go.kr" in url
    assert "state=" in url
    assert len(state) > 8


def test_build_gcloud_auth_url_no_hd():
    from app.services.sso.gcloud_auth import build_gcloud_auth_url
    from app.storage.sso_store import GCloudConfig
    cfg = GCloudConfig(client_id="cid", hd="")
    url, state = build_gcloud_auth_url(cfg, "https://example.com/cb")
    assert "hd=" not in url
    assert "cid" in url


def test_build_gcloud_auth_url_unique_states():
    """Each call should produce a different state token."""
    from app.services.sso.gcloud_auth import build_gcloud_auth_url
    from app.storage.sso_store import GCloudConfig
    cfg = GCloudConfig(client_id="cid")
    _, state1 = build_gcloud_auth_url(cfg, "https://example.com/cb")
    _, state2 = build_gcloud_auth_url(cfg, "https://example.com/cb")
    assert state1 != state2


# ── API endpoint tests ─────────────────────────────────────────────────────────

def test_get_sso_config_returns_200(admin_client):
    tc, _ = admin_client
    res = tc.get("/admin/sso/config")
    assert res.status_code == 200
    data = res.json()
    assert "provider" in data
    assert data["provider"] == "disabled"


def test_put_sso_config_update_provider(admin_client):
    tc, _ = admin_client
    res = tc.put("/admin/sso/config", json={"provider": "ldap", "ldap": {"server_url": "ldap://dc.test:389"}})
    assert res.status_code == 200
    # Verify via GET
    res2 = tc.get("/admin/sso/config")
    data = res2.json()
    assert data["provider"] == "ldap"
    assert data["ldap"]["server_url"] == "ldap://dc.test:389"


def test_put_sso_config_masks_secrets(admin_client):
    """bind_password is masked in GET response when encryption is available."""
    pytest.importorskip("cryptography", reason="cryptography package not installed")
    tc, _ = admin_client
    res = tc.put("/admin/sso/config", json={"provider": "ldap", "ldap": {"bind_password": "secret123"}})
    assert res.status_code == 200
    res2 = tc.get("/admin/sso/config")
    data = res2.json()
    # bind_password should be masked, not returned in plain text
    assert data["ldap"]["bind_password"] == "***"


def test_test_ldap_endpoint(admin_client):
    tc, _ = admin_client
    res = tc.post("/admin/sso/test-ldap")
    assert res.status_code == 200
    data = res.json()
    assert "ok" in data
    assert "message" in data


def test_saml_metadata_endpoint(client):
    res = client.get("/saml/metadata")
    assert res.status_code == 200
    assert "xml" in res.headers.get("content-type", "")


def test_saml_login_redirects(client):
    res = client.get("/saml/login", follow_redirects=False)
    # Should redirect to IdP (or return 307 if config empty)
    assert res.status_code in (302, 307)


def test_ldap_login_not_enabled(client):
    """POST /auth/ldap-login when SSO not set to ldap → 400."""
    res = client.post("/auth/ldap-login", json={"username": "u", "password": "p"})
    assert res.status_code == 400


def test_gcloud_login_redirects(client):
    res = client.get("/sso/gcloud", follow_redirects=False)
    assert res.status_code in (302, 307)


def test_sso_config_requires_admin(client):
    """Non-authenticated users cannot access SSO config."""
    res = client.get("/admin/sso/config")
    assert res.status_code in (401, 403)


def test_put_sso_config_requires_admin(client):
    """Non-authenticated users cannot update SSO config."""
    res = client.put("/admin/sso/config", json={"provider": "ldap"})
    assert res.status_code in (401, 403)


def test_put_sso_config_gcloud(admin_client):
    tc, _ = admin_client
    res = tc.put("/admin/sso/config", json={
        "provider": "gcloud",
        "gcloud": {"client_id": "goog-client-id", "hd": "example.go.kr"},
    })
    assert res.status_code == 200
    res2 = tc.get("/admin/sso/config")
    data = res2.json()
    assert data["provider"] == "gcloud"
    assert data["gcloud"]["client_id"] == "goog-client-id"
    assert data["gcloud"]["hd"] == "example.go.kr"


def test_put_sso_config_saml(admin_client):
    tc, _ = admin_client
    res = tc.put("/admin/sso/config", json={
        "provider": "saml",
        "saml": {
            "idp_entity_id": "https://idp.example.com",
            "idp_sso_url": "https://idp.example.com/sso",
            "sp_entity_id": "https://sp.example.com",
            "sp_acs_url": "https://sp.example.com/saml/acs",
        },
    })
    assert res.status_code == 200
    res2 = tc.get("/admin/sso/config")
    data = res2.json()
    assert data["provider"] == "saml"
    assert data["saml"]["idp_entity_id"] == "https://idp.example.com"


def test_put_sso_config_disable(admin_client):
    tc, _ = admin_client
    # First enable
    tc.put("/admin/sso/config", json={"provider": "ldap"})
    # Then disable
    res = tc.put("/admin/sso/config", json={"provider": "disabled"})
    assert res.status_code == 200
    res2 = tc.get("/admin/sso/config")
    assert res2.json()["provider"] == "disabled"
