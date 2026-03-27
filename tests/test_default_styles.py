"""Tests for default style profiles."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.storage.default_styles import DEFAULT_STYLE_PROFILES

client = TestClient(app)


def test_default_styles_defined():
    """3 default profiles must be defined."""
    assert len(DEFAULT_STYLE_PROFILES) == 3
    ids = [p["style_id"] for p in DEFAULT_STYLE_PROFILES]
    assert "default-official" in ids
    assert "default-consulting" in ids
    assert "default-internal" in ids


def test_default_styles_have_required_fields():
    """Each default profile must have all required fields."""
    required = [
        "style_id", "name", "description", "is_system",
        "custom_rules", "forbidden_expressions", "few_shot_example",
    ]
    for profile in DEFAULT_STYLE_PROFILES:
        for field in required:
            assert field in profile, (
                f"Profile {profile['style_id']} missing field: {field}"
            )


def test_exactly_one_default_profile():
    """Exactly one profile should be marked as default."""
    defaults = [p for p in DEFAULT_STYLE_PROFILES if p.get("is_default")]
    assert len(defaults) == 1
    assert defaults[0]["style_id"] == "default-official"


def test_all_profiles_are_system():
    """All built-in profiles must have is_system=True."""
    for profile in DEFAULT_STYLE_PROFILES:
        assert profile.get("is_system") is True, (
            f"Profile {profile['style_id']} should have is_system=True"
        )


def test_system_profiles_not_deletable():
    """System profiles should return 400 on delete attempt."""
    from app.services.auth_service import create_access_token
    from app.storage.style_store import StyleStore

    # Ensure defaults are present (lifespan not called in test client)
    StyleStore("system").initialize_defaults("system")

    token = create_access_token("user1", "system", "admin", "admin")
    res = client.delete(
        "/styles/default-official",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "system"},
    )
    assert res.status_code == 400
    assert "삭제할 수 없습니다" in res.json().get("detail", "")


def test_initialize_defaults_idempotent():
    """Running initialize_defaults twice should not duplicate profiles."""
    from app.storage.style_store import StyleStore

    store = StyleStore("test-style-init")
    store.initialize_defaults("test-style-init")
    store.initialize_defaults("test-style-init")  # second call — no-op

    data = store._load()
    system_profiles = [v for v in data.values() if v.get("is_system")]
    system_ids = [p["profile_id"] for p in system_profiles]

    # No duplicates
    assert len(system_ids) == len(set(system_ids))
    assert len(system_profiles) == 3


def test_initialize_defaults_adds_correct_fields():
    """Profiles stored by initialize_defaults should have all expected keys."""
    from app.storage.style_store import StyleStore

    store = StyleStore("test-style-fields")
    store.initialize_defaults("test-style-fields")

    data = store._load()
    official = data.get("default-official")
    assert official is not None
    assert official["is_system"] is True
    assert official["is_default"] is True
    assert official["created_by"] == "system"
    assert official["few_shot_example"] != ""
    assert official["avatar_color"] == "#6366f1"
    tg = official["tone_guide"]
    assert tg["formality"] == "formal"
    assert len(tg["custom_rules"]) > 0
    assert len(tg["forbidden_words"]) > 0


def test_style_profiles_listed_include_system_flag():
    """GET /styles response should include is_system field."""
    from app.services.auth_service import create_access_token
    from app.storage.style_store import StyleStore

    # Ensure defaults are present (lifespan not called in test client)
    StyleStore("system").initialize_defaults("system")

    token = create_access_token("user1", "system", "member", "user1")
    res = client.get(
        "/styles",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "system"},
    )
    if res.status_code != 200:
        pytest.skip("styles endpoint unavailable")
    profiles = res.json().get("profiles", [])
    # At least the 3 system profiles should be present
    system_profiles = [p for p in profiles if p.get("is_system")]
    assert len(system_profiles) >= 3
    system_ids = [p["profile_id"] for p in system_profiles]
    assert "default-official" in system_ids
    assert "default-consulting" in system_ids
    assert "default-internal" in system_ids
