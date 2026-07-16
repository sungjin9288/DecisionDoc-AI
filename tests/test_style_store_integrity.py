from __future__ import annotations

import ast
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.storage.state_backend import LocalStateBackend, S3StateBackend
from app.storage.style_store import (
    StyleExample,
    StyleStore,
    StyleStoreError,
    ToneGuide,
    get_style_store,
)


_NOW = "2026-07-16T00:00:00+00:00"


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
    *,
    read_delay: float = 0.0,
) -> tuple[S3StateBackend, _MemoryS3Client]:
    client = _MemoryS3Client(read_delay=read_delay)
    backend = S3StateBackend(
        bucket="unit-bucket",
        prefix="decisiondoc-ai/state/",
        s3_client=client,
    )
    return backend, client


def _tone(marker: str = "") -> dict:
    return {
        "formality": marker,
        "density": "",
        "perspective": "",
        "custom_rules": [],
        "forbidden_words": [],
        "preferred_words": [],
    }


def _record(
    profile_id: str,
    *,
    tenant_id: str = "alpha",
    is_default: bool = False,
) -> dict:
    return {
        "profile_id": profile_id,
        "tenant_id": tenant_id,
        "name": f"Profile {profile_id}",
        "description": "",
        "tone_guide": _tone(),
        "examples": [],
        "bundle_overrides": {},
        "is_default": is_default,
        "created_by": "user-1",
        "created_at": _NOW,
        "updated_at": _NOW,
    }


def _example(example_id: str) -> StyleExample:
    return StyleExample(
        example_id=example_id,
        source_filename="source.txt",
        bundle_id=None,
        extracted_patterns=["direct"],
        sample_sentences=["A concise sentence."],
        uploaded_at=_NOW,
        uploaded_by="user-1",
    )


def _client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("JWT_SECRET_KEY", "style-integrity-test-secret-key")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    from app.main import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


@pytest.mark.parametrize(
    "tenant_id",
    [" tenant", "tenant ", ".", "..", "tenant/a", "tenant\\a", "tenant\na"],
)
def test_style_store_rejects_unsafe_tenant_before_state_access(
    tmp_path: Path,
    tenant_id: str,
) -> None:
    with pytest.raises(ValueError, match="Invalid tenant_id"):
        StyleStore(tenant_id, data_dir=tmp_path)

    assert not (tmp_path / "tenants").exists()


def test_missing_style_state_read_has_no_side_effect(tmp_path: Path) -> None:
    store = StyleStore("alpha", data_dir=tmp_path)

    assert store.list_profiles() == []
    assert store.get_default() is None
    assert not store._path.exists()


@pytest.mark.parametrize(
    ("raw", "error"),
    [
        ("", "Invalid style profile state document"),
        ("[]", "Invalid style profile state"),
        ('{"same":{},"same":{}}', "Invalid style profile state document"),
        (json.dumps({"profile": []}), "Invalid style profile record"),
        (
            json.dumps({"profile": {"tenant_id": "alpha"}}),
            "Invalid style profile fields",
        ),
        (
            json.dumps({"wrong-key": _record("profile")}),
            "Style profile storage identity mismatch",
        ),
        (
            json.dumps({"profile": {**_record("profile"), "tone_guide": {}}}),
            "Invalid tone guide",
        ),
        (
            json.dumps(
                {
                    "first": _record("first", is_default=True),
                    "second": _record("second", is_default=True),
                }
            ),
            "Multiple default style profiles",
        ),
    ],
)
def test_untrusted_style_state_stops_read_and_write_without_replacement(
    tmp_path: Path,
    raw: str,
    error: str,
) -> None:
    path = tmp_path / "tenants/alpha/style_profiles.json"
    path.parent.mkdir(parents=True)
    path.write_text(raw, encoding="utf-8")
    original_bytes = path.read_bytes()
    store = StyleStore("alpha", data_dir=tmp_path)

    with pytest.raises(StyleStoreError, match=error):
        store.list_profiles()
    with pytest.raises(StyleStoreError, match=error):
        store.create("New", "", "user-1")

    assert path.read_bytes() == original_bytes


def test_foreign_style_profile_remains_hidden_and_preserved(tmp_path: Path) -> None:
    path = tmp_path / "tenants/alpha/style_profiles.json"
    path.parent.mkdir(parents=True)
    foreign = {"tenant_id": "beta", "opaque": {"keep": True}}
    path.write_text(json.dumps({"foreign": foreign}), encoding="utf-8")
    store = StyleStore("alpha", data_dir=tmp_path)

    created = store.create("Owned", "", "user-1")

    assert [profile.profile_id for profile in store.list_profiles()] == [
        created.profile_id
    ]
    persisted = json.loads(path.read_text(encoding="utf-8"))
    assert persisted["foreign"] == foreign


def test_tenantless_style_profile_is_rejected_as_untrusted(tmp_path: Path) -> None:
    path = tmp_path / "tenants/alpha/style_profiles.json"
    path.parent.mkdir(parents=True)
    profile = _record("legacy")
    profile.pop("tenant_id")
    path.write_text(json.dumps({"legacy": profile}), encoding="utf-8")

    with pytest.raises(StyleStoreError, match="Invalid style profile tenant identity"):
        StyleStore("alpha", data_dir=tmp_path).list_profiles()


def test_invalid_caller_state_is_rejected_before_write(tmp_path: Path) -> None:
    store = StyleStore("alpha", data_dir=tmp_path)

    with pytest.raises(ValueError, match="Invalid style profile name"):
        store.create(" ", "", "user-1")
    assert not store._path.exists()

    profile = store.create("Valid", "", "user-1")
    original_bytes = store._path.read_bytes()
    invalid_tone = ToneGuide(custom_rules=["valid", 1])  # type: ignore[list-item]
    with pytest.raises(StyleStoreError, match="Invalid tone custom_rules"):
        store.update_tone_guide(profile.profile_id, invalid_tone)
    with pytest.raises(StyleStoreError, match="Invalid example upload timestamp"):
        store.add_example(
            profile.profile_id,
            StyleExample(
                example_id="example-1",
                source_filename="source.txt",
                bundle_id=None,
                extracted_patterns=[],
                sample_sentences=[],
                uploaded_at="not-a-timestamp",
                uploaded_by="user-1",
            ),
        )
    assert store._path.read_bytes() == original_bytes


def test_duplicate_generated_profile_and_example_identity_do_not_overwrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixed_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    monkeypatch.setattr("app.storage.style_store.uuid.uuid4", lambda: fixed_id)
    store = StyleStore("alpha", data_dir=tmp_path)
    profile = store.create("First", "", "user-1")
    original_bytes = store._path.read_bytes()

    with pytest.raises(StyleStoreError, match="Duplicate style profile identity"):
        store.create("Second", "", "user-1")
    assert store._path.read_bytes() == original_bytes

    store.add_example(profile.profile_id, _example("same-example"))
    example_bytes = store._path.read_bytes()
    with pytest.raises(StyleStoreError, match="Duplicate style example identity"):
        store.add_example(profile.profile_id, _example("same-example"))
    assert store._path.read_bytes() == example_bytes


def test_independent_local_style_stores_preserve_concurrent_creates(
    tmp_path: Path,
) -> None:
    stores = [
        StyleStore("alpha", data_dir=tmp_path, backend=_SlowLocalBackend(tmp_path))
        for _ in range(20)
    ]

    with ThreadPoolExecutor(max_workers=20) as executor:
        list(
            executor.map(
                lambda item: item[1].create(f"Profile {item[0]}", "", "user-1"),
                enumerate(stores),
            )
        )

    profiles = StyleStore("alpha", data_dir=tmp_path).list_profiles()
    assert len(profiles) == 20
    assert len([profile for profile in profiles if profile.is_default]) == 1


def test_independent_local_style_stores_preserve_concurrent_overrides(
    tmp_path: Path,
) -> None:
    creator = StyleStore("alpha", data_dir=tmp_path)
    profile = creator.create("Shared", "", "user-1")
    stores = [
        StyleStore("alpha", data_dir=tmp_path, backend=_SlowLocalBackend(tmp_path))
        for _ in range(20)
    ]

    with ThreadPoolExecutor(max_workers=20) as executor:
        list(
            executor.map(
                lambda item: item[1].set_bundle_override(
                    profile.profile_id,
                    f"bundle-{item[0]}",
                    ToneGuide(formality=f"tone-{item[0]}"),
                ),
                enumerate(stores),
            )
        )

    reloaded = creator.get(profile.profile_id)
    assert reloaded is not None
    assert set(reloaded.bundle_overrides) == {
        f"bundle-{index}" for index in range(20)
    }


def test_style_round_trip_through_fake_s3() -> None:
    backend, client = _s3_backend()
    store = StyleStore("alpha", data_dir="/virtual/data", backend=backend)
    profile = store.create("S3 style", "", "user-1")
    store.update_tone_guide(profile.profile_id, ToneGuide(formality="formal"))
    key = (
        "unit-bucket",
        "decisiondoc-ai/state/tenants/alpha/style_profiles.json",
    )

    assert key in client.objects
    reloaded = StyleStore("alpha", data_dir="/virtual/data", backend=backend).get(
        profile.profile_id
    )
    assert reloaded is not None
    assert reloaded.tone_guide.formality == "formal"


def test_untrusted_fake_s3_style_state_is_preserved() -> None:
    backend, client = _s3_backend()
    key = (
        "unit-bucket",
        "decisiondoc-ai/state/tenants/alpha/style_profiles.json",
    )
    client.objects[key] = b"{not-json"
    store = StyleStore("alpha", data_dir="/virtual/data", backend=backend)

    with pytest.raises(StyleStoreError, match="Invalid style profile state document"):
        store.create("New", "", "user-1")

    assert client.objects[key] == b"{not-json"


def test_independent_fake_s3_style_stores_preserve_concurrent_mutations() -> None:
    backend, _ = _s3_backend(read_delay=0.005)
    stores = [
        StyleStore("alpha", data_dir="/virtual/data", backend=backend)
        for _ in range(20)
    ]

    with ThreadPoolExecutor(max_workers=20) as executor:
        profiles = list(
            executor.map(
                lambda item: item[1].create(f"Profile {item[0]}", "", "user-1"),
                enumerate(stores),
            )
        )
    target_id = profiles[0].profile_id
    with ThreadPoolExecutor(max_workers=20) as executor:
        list(
            executor.map(
                lambda item: item[1].set_bundle_override(
                    target_id,
                    f"bundle-{item[0]}",
                    ToneGuide(formality=f"tone-{item[0]}"),
                ),
                enumerate(stores),
            )
        )

    reloaded = StyleStore("alpha", data_dir="/virtual/data", backend=backend)
    assert len(reloaded.list_profiles()) == 20
    target = reloaded.get(target_id)
    assert target is not None
    assert len(target.bundle_overrides) == 20


def test_initialize_defaults_preserves_existing_default(tmp_path: Path) -> None:
    store = StyleStore("alpha", data_dir=tmp_path)
    custom = store.create("Custom default", "", "user-1")

    store.initialize_defaults()

    profiles = store.list_profiles()
    defaults = [profile for profile in profiles if profile.is_default]
    assert [profile.profile_id for profile in defaults] == [custom.profile_id]
    assert len([profile for profile in profiles if profile.is_system]) == 3


def test_style_store_factory_is_scoped_by_data_root(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first = get_style_store("alpha", data_dir=first_root)
    same = get_style_store("alpha", data_dir=first_root)
    second = get_style_store("alpha", data_dir=second_root)

    assert first is same
    assert first is not second
    first.create("First", "", "user-1")
    assert second.list_profiles() == []


def test_style_routes_use_public_factory_with_application_state_backend() -> None:
    tree = ast.parse(Path("app/routers/styles.py").read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "get_style_store"
    ]
    private_loads = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr == "_load"
    ]

    assert len(calls) == 1
    assert {keyword.arg for keyword in calls[0].keywords} >= {"data_dir", "backend"}
    assert private_loads == []


def test_style_api_rejects_invalid_payload_before_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(tmp_path, monkeypatch)

    empty_response = client.post("/styles", json={"name": ""})
    control_response = client.post("/styles", json={"name": "bad\nname"})
    extra_response = client.put(
        "/styles/missing/tone",
        json={"formality": "formal", "unknown": True},
    )

    assert empty_response.status_code == 422
    assert control_response.status_code == 422
    assert extra_response.status_code == 422
    assert not (tmp_path / "tenants/system/style_profiles.json").exists()


def test_style_api_uses_application_state_s3_backend(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(tmp_path, monkeypatch)
    backend, s3_client = _s3_backend()
    client.app.state.state_backend = backend

    response = client.post("/styles", json={"name": "Remote style"})

    assert response.status_code == 200
    key = (
        "unit-bucket",
        "decisiondoc-ai/state/tenants/system/style_profiles.json",
    )
    assert key in s3_client.objects
    assert not (tmp_path / "tenants/system/style_profiles.json").exists()


def test_style_api_preserves_corrupt_state_across_read_and_write_routes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "tenants/system/style_profiles.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"{not-json")
    client = _client(tmp_path, monkeypatch)

    list_response = client.get("/styles")
    create_response = client.post("/styles", json={"name": "New"})

    assert list_response.status_code == 500
    assert list_response.json()["code"] == "INTERNAL_ERROR"
    assert create_response.status_code == 500
    assert create_response.json()["code"] == "INTERNAL_ERROR"
    assert path.read_bytes() == b"{not-json"


def test_prompt_build_does_not_silently_omit_corrupt_style_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "tenants/alpha/style_profiles.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"{not-json")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.bundle_catalog.registry import get_bundle_spec
    from app.domain.schema import _current_tenant_id, build_bundle_prompt

    _current_tenant_id.value = "alpha"
    try:
        with pytest.raises(StyleStoreError, match="Invalid style profile state document"):
            build_bundle_prompt(
                {"title": "Style integrity"},
                "v1",
                get_bundle_spec("tech_decision"),
            )
    finally:
        _current_tenant_id.value = None

    assert path.read_bytes() == b"{not-json"
