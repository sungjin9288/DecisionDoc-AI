"""Focused regression coverage for immutable generation style snapshots."""
from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient

from app.providers.mock_provider import MockProvider
from app.schemas.generate import GenerateRequest
from app.services.generation.errors import (
    StyleProfileNotFoundError,
    StyleSnapshotInvalidError,
)
from app.services.generation_service import GenerationService
from app.storage.state_backend import LocalStateBackend
from app.storage.style_store import StyleStore, ToneGuide, get_style_store
from app.storage.style_store_validation import StyleStoreError


class CapturingMockProvider(MockProvider):
    def __init__(self) -> None:
        self.calls = 0
        self.payloads: list[dict] = []
        self.prompts: list[str] = []

    def generate_bundle(
        self,
        requirements,
        *,
        schema_version,
        request_id,
        bundle_spec=None,
        feedback_hints="",
    ):
        from app.domain.schema import build_bundle_prompt

        self.calls += 1
        self.payloads.append(dict(requirements))
        self.prompts.append(
            build_bundle_prompt(
                requirements,
                schema_version,
                bundle_spec,
                feedback_hints=feedback_hints,
            )
        )
        return super().generate_bundle(
            requirements,
            schema_version=schema_version,
            request_id=request_id,
            bundle_spec=bundle_spec,
            feedback_hints=feedback_hints,
        )


def _configure_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.setenv("DECISIONDOC_CACHE_ENABLED", "0")
    monkeypatch.setenv("DECISIONDOC_PROVIDER_GENERATION", "")
    monkeypatch.setenv("DECISIONDOC_PROVIDER_ATTACHMENT", "")
    monkeypatch.setenv("DECISIONDOC_PROVIDER_VISUAL", "")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    monkeypatch.setattr("app.main.load_dotenv", lambda *args, **kwargs: None)


def _make_service(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    provider: CapturingMockProvider,
    *,
    data_dir: Path | None = None,
    state_backend: LocalStateBackend | None = None,
) -> GenerationService:
    _configure_environment(monkeypatch, tmp_path)
    root = data_dir or (tmp_path / "generation-state")
    backend = state_backend or LocalStateBackend(root)
    return GenerationService(
        provider_factory=lambda: provider,
        template_dir=Path("app/templates/v1"),
        data_dir=root,
        state_backend=backend,
    )


def _add_style(store: StyleStore, name: str, marker: str) -> str:
    profile = store.create(name, "", "style-test")
    store.update_tone_guide(
        profile.profile_id,
        ToneGuide(custom_rules=[marker]),
    )
    return profile.profile_id


def _make_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    _configure_environment(monkeypatch, tmp_path)
    from app.main import create_app

    return TestClient(create_app())


def _client_style_store(client: TestClient, tenant_id: str) -> StyleStore:
    return get_style_store(
        tenant_id,
        data_dir=client.app.state.data_dir,
        backend=client.app.state.state_backend,
    )


def test_manual_example_generation_and_edited_docx_lifecycle(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    provider = CapturingMockProvider()
    client.app.state.service.provider_factory = lambda: provider

    def unexpected_provider(*args, **kwargs):
        pytest.fail("style registration and edited export must not call a provider")

    monkeypatch.setattr("app.providers.factory.get_provider_for_bundle", unexpected_provider)
    monkeypatch.setattr("app.routers.generate.export.get_provider_for_capability", unexpected_provider)
    created = client.post("/styles", json={"name": "Lifecycle style"})
    assert created.status_code == 200
    profile_id = created.json()["profile_id"]
    marker = "MANUAL_LIFECYCLE_EXAMPLE: state evidence before recommendations."
    added = client.post(
        f"/styles/{profile_id}/examples",
        json={"label": "Evidence first", "sample_sentences": [marker], "bundle_id": "tech_decision"},
    )
    assert added.status_code == 200
    assert provider.calls == 0
    profile_before = client.get(f"/styles/{profile_id}").json()
    payload = {
        "title": "Local lifecycle",
        "goal": "Compare options with explicit evidence and a reversible decision",
        "bundle_type": "tech_decision",
        "style_profile_id": profile_id,
    }
    generated = client.post("/generate", json=payload)
    assert generated.status_code == 200, generated.text
    assert provider.calls == 1
    assert marker in provider.prompts[-1]
    assert provider.payloads[-1]["_style_snapshot"]["id"] == profile_id
    docs = [{"doc_type": doc["doc_type"], "markdown": doc["markdown"]}
            for doc in generated.json()["docs"]]
    assert docs and all(doc["markdown"].strip() for doc in docs)
    edit = "HUMAN_EDIT: budget < 100 & evidence > assumptions."
    docs[0]["markdown"] += "\n\n" + edit
    exported = client.post(
        "/generate/export-edited",
        json={"title": payload["title"], "format": "docx", "docs": docs},
    )
    assert exported.status_code == 200, exported.text
    assert exported.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert provider.calls == 1
    with ZipFile(BytesIO(exported.content)) as archive:
        assert archive.testzip() is None
        document = ElementTree.fromstring(archive.read("word/document.xml"))
    text = "".join(document.itertext())
    assert edit in text
    assert payload["title"] in text
    assert client.get(f"/styles/{profile_id}").json() == profile_before

    removed = client.delete(f"/styles/{profile_id}/examples/{added.json()['example_id']}")
    assert removed.status_code == 200
    regenerated = client.post("/generate", json=payload)
    assert regenerated.status_code == 200, regenerated.text
    assert provider.calls == 2
    assert marker not in provider.prompts[-1]
    assert client.get(f"/styles/{profile_id}").json()["examples"] == []


def test_selected_style_snapshot_overrides_default_without_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = CapturingMockProvider()
    service = _make_service(tmp_path, monkeypatch, provider)
    store = get_style_store("tenant-a", data_dir=service.data_dir, backend=service.state_backend)
    default_id = _add_style(store, "Default A", "DEFAULT_A_MARKER")
    selected_id = _add_style(store, "Selected B", "SELECTED_B_MARKER")

    service.generate_documents(
        GenerateRequest(
            title="Style selection",
            goal="Use the selected profile",
            style_profile_id=selected_id,
        ),
        request_id="selected-style",
        tenant_id="tenant-a",
    )

    assert store.get_default().profile_id == default_id
    snapshot = provider.payloads[0]["_style_snapshot"]
    assert set(snapshot) == {"version", "id", "prompt"}
    assert snapshot["id"] == selected_id
    assert snapshot["version"]
    assert "SELECTED_B_MARKER" in snapshot["prompt"]
    assert "style_profile_id" not in provider.payloads[0]
    assert "SELECTED_B_MARKER" in provider.prompts[0]
    assert "DEFAULT_A_MARKER" not in provider.prompts[0]


def test_omitted_style_resolves_current_tenant_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = CapturingMockProvider()
    service = _make_service(tmp_path, monkeypatch, provider)
    store = get_style_store("tenant-a", data_dir=service.data_dir, backend=service.state_backend)
    default_id = _add_style(store, "Default A", "OMITTED_DEFAULT_MARKER")

    service.generate_documents(
        GenerateRequest(title="Default style", goal="Use tenant default"),
        request_id="omitted-style",
        tenant_id="tenant-a",
    )

    assert provider.payloads[0]["_style_snapshot"]["id"] == default_id
    assert "OMITTED_DEFAULT_MARKER" in provider.prompts[0]


def test_style_snapshot_uses_service_data_root_and_backend(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = CapturingMockProvider()
    service_root = tmp_path / "bound-state"
    fallback_root = tmp_path / "dotenv-state"
    backend = LocalStateBackend(service_root)
    service = _make_service(
        tmp_path,
        monkeypatch,
        provider,
        data_dir=service_root,
        state_backend=backend,
    )
    monkeypatch.setenv("DATA_DIR", str(fallback_root))
    store = get_style_store("tenant-a", data_dir=service_root, backend=backend)
    selected_id = _add_style(store, "Bound state", "BOUND_BACKEND_MARKER")

    service.generate_documents(
        GenerateRequest(
            title="Bound store",
            goal="Read the service state binding",
            style_profile_id=selected_id,
        ),
        request_id="bound-state",
        tenant_id="tenant-a",
    )

    assert "BOUND_BACKEND_MARKER" in provider.prompts[0]
    assert not (fallback_root / "tenants" / "tenant-a" / "style_profiles.json").exists()


def test_style_snapshot_cache_misses_after_style_content_update(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DECISIONDOC_CACHE_ENABLED", "1")
    provider = CapturingMockProvider()
    service = _make_service(tmp_path, monkeypatch, provider)
    monkeypatch.setenv("DECISIONDOC_CACHE_ENABLED", "1")
    store = get_style_store("tenant-a", data_dir=service.data_dir, backend=service.state_backend)
    selected_id = _add_style(store, "Selected", "STYLE_VERSION_ONE")
    request = GenerateRequest(
        title="Style cache",
        goal="Bind cache key to content",
        style_profile_id=selected_id,
    )

    first = service.generate_documents(request, request_id="cache-1", tenant_id="tenant-a")
    repeated = service.generate_documents(request, request_id="cache-2", tenant_id="tenant-a")
    store.update_tone_guide(selected_id, ToneGuide(custom_rules=["STYLE_VERSION_TWO"]))
    changed = service.generate_documents(request, request_id="cache-3", tenant_id="tenant-a")

    assert first["metadata"]["cache_hit"] is False
    assert repeated["metadata"]["cache_hit"] is True
    assert changed["metadata"]["cache_hit"] is False
    assert provider.calls == 2
    assert "STYLE_VERSION_TWO" in provider.prompts[-1]


def test_default_change_and_deleted_explicit_style_do_not_reuse_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DECISIONDOC_CACHE_ENABLED", "1")
    provider = CapturingMockProvider()
    service = _make_service(tmp_path, monkeypatch, provider)
    monkeypatch.setenv("DECISIONDOC_CACHE_ENABLED", "1")
    store = get_style_store("tenant-a", data_dir=service.data_dir, backend=service.state_backend)
    first_id = _add_style(store, "Default A", "DEFAULT_VERSION_A")
    second_id = _add_style(store, "Default B", "DEFAULT_VERSION_B")
    default_request = GenerateRequest(title="Default cache", goal="Track default changes")

    service.generate_documents(default_request, request_id="default-1", tenant_id="tenant-a")
    service.generate_documents(default_request, request_id="default-2", tenant_id="tenant-a")
    store.set_default(second_id)
    changed_default = service.generate_documents(
        default_request,
        request_id="default-3",
        tenant_id="tenant-a",
    )

    selected_request = GenerateRequest(
        title="Deleted style",
        goal="Reject removed profiles",
        style_profile_id=second_id,
    )
    service.generate_documents(selected_request, request_id="deleted-1", tenant_id="tenant-a")
    calls_before_delete = provider.calls
    store.delete(second_id)

    with pytest.raises(StyleProfileNotFoundError):
        service.generate_documents(selected_request, request_id="deleted-2", tenant_id="tenant-a")

    assert first_id != second_id
    assert changed_default["metadata"]["cache_hit"] is False
    assert "DEFAULT_VERSION_B" in provider.prompts[-1]
    assert provider.calls == calls_before_delete


def test_snapshot_is_read_once_and_bound_despite_default_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = CapturingMockProvider()
    service = _make_service(tmp_path, monkeypatch, provider)
    store = get_style_store("tenant-a", data_dir=service.data_dir, backend=service.state_backend)
    _add_style(store, "Default A", "RACE_DEFAULT_A")
    next_default_id = _add_style(store, "Default B", "RACE_DEFAULT_B")
    original_get_default = StyleStore.get_default
    reads = 0

    def counted_get_default(self: StyleStore):
        nonlocal reads
        reads += 1
        return original_get_default(self)

    class RacingProvider(CapturingMockProvider):
        def generate_bundle(self, *args, **kwargs):
            store.set_default(next_default_id)
            return super().generate_bundle(*args, **kwargs)

    monkeypatch.setattr(StyleStore, "get_default", counted_get_default)
    racing_provider = RacingProvider()
    service.provider_factory = lambda: racing_provider

    service.generate_documents(
        GenerateRequest(title="Style race", goal="Keep one snapshot"),
        request_id="style-race",
        tenant_id="tenant-a",
    )

    assert reads == 1
    assert "RACE_DEFAULT_A" in racing_provider.prompts[0]
    assert "RACE_DEFAULT_B" not in racing_provider.prompts[0]


def test_preflight_result_is_discarded_before_cross_tenant_backend_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider_a = CapturingMockProvider()
    provider_b = CapturingMockProvider()
    service_a = _make_service(
        tmp_path,
        monkeypatch,
        provider_a,
        data_dir=tmp_path / "tenant-a-state",
    )
    service_b = _make_service(
        tmp_path,
        monkeypatch,
        provider_b,
        data_dir=tmp_path / "tenant-b-state",
    )
    selected_a = _add_style(
        get_style_store("tenant-a", data_dir=service_a.data_dir, backend=service_a.state_backend),
        "Selected A",
        "PREFLIGHT_TENANT_A_MARKER",
    )
    _add_style(
        get_style_store("tenant-b", data_dir=service_b.data_dir, backend=service_b.state_backend),
        "Default B",
        "SERVICE_TENANT_B_MARKER",
    )
    preflight_request = GenerateRequest(
        title="Preflight isolation",
        goal="Discard preflight style state",
        style_profile_id=selected_a,
    )

    service_a.resolve_style_snapshot(preflight_request, tenant_id="tenant-a")
    service_b.generate_documents(
        preflight_request.model_copy(update={"style_profile_id": None}),
        request_id="cross-tenant-backend",
        tenant_id="tenant-b",
    )

    assert "SERVICE_TENANT_B_MARKER" in provider_b.prompts[0]
    assert "PREFLIGHT_TENANT_A_MARKER" not in provider_b.prompts[0]
    assert provider_a.calls == 0


def test_model_copy_resolves_current_selected_style_and_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = CapturingMockProvider()
    service = _make_service(tmp_path, monkeypatch, provider)
    store = get_style_store("tenant-a", data_dir=service.data_dir, backend=service.state_backend)
    selected_b = _add_style(store, "Selected B", "SELECTED_B_GLOBAL_MARKER")
    selected_c = _add_style(store, "Selected C", "SELECTED_C_GLOBAL_MARKER")
    store.set_bundle_override(
        selected_b,
        "proposal_kr",
        ToneGuide(custom_rules=["SELECTED_B_PROPOSAL_MARKER"]),
    )
    store.set_bundle_override(
        selected_c,
        "proposal_kr",
        ToneGuide(custom_rules=["SELECTED_C_PROPOSAL_MARKER"]),
    )
    preflight_request = GenerateRequest(
        title="Copied request",
        goal="Resolve current request fields",
        bundle_type="tech_decision",
        style_profile_id=selected_b,
    )

    service.resolve_style_snapshot(preflight_request, tenant_id="tenant-a")
    copied_request = preflight_request.model_copy(
        update={"bundle_type": "proposal_kr", "style_profile_id": selected_c}
    )
    service.generate_documents(
        copied_request,
        request_id="copied-request",
        tenant_id="tenant-a",
    )

    snapshot = provider.payloads[0]["_style_snapshot"]
    assert snapshot["id"] == selected_c
    assert "SELECTED_C_PROPOSAL_MARKER" in provider.prompts[0]
    assert "SELECTED_B_GLOBAL_MARKER" not in provider.prompts[0]
    assert "SELECTED_B_PROPOSAL_MARKER" not in provider.prompts[0]


def test_malformed_private_style_snapshot_fails_closed() -> None:
    from app.services.generation.style_context import style_prompt_from_snapshot

    malformed_snapshots = (
        {},
        {"version": "style-snapshot-v1:not-a-hash", "id": "profile", "prompt": "x"},
        {"version": "style-snapshot-v1:" + "a" * 64, "id": "", "prompt": "x"},
        {"version": "style-snapshot-v1:" + "a" * 64, "id": None, "prompt": ""},
        {"version": "style-snapshot-v1:none", "id": "profile", "prompt": ""},
        {"version": "style-snapshot-v1:none", "id": None, "prompt": "injected"},
        {"version": "style-snapshot-v1:" + "a" * 64, "id": "profile", "prompt": None},
        {"version": "style-snapshot-v1:" + "a" * 64, "id": "profile", "prompt": "x", "extra": True},
    )

    for snapshot in malformed_snapshots:
        with pytest.raises(StyleSnapshotInvalidError):
            style_prompt_from_snapshot(snapshot)


def test_direct_prompt_rejects_explicit_style_without_tenant_context() -> None:
    from app.bundle_catalog.registry import get_bundle_spec
    from app.domain.schema import build_bundle_prompt

    with pytest.raises(StyleProfileNotFoundError):
        build_bundle_prompt(
            {
                "title": "Direct prompt",
                "goal": "Require a tenant for an explicit style",
                "style_profile_id": "default-consulting",
            },
            "v1",
            get_bundle_spec("tech_decision"),
        )


def test_direct_prompt_resolves_explicit_style_from_current_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.bundle_catalog.registry import get_bundle_spec
    from app.domain.schema import (
        _current_generation_data_dir,
        _current_generation_state_backend,
        _current_tenant_id,
        build_bundle_prompt,
    )

    _configure_environment(monkeypatch, tmp_path)
    backend = LocalStateBackend(tmp_path / "direct-state")
    store = get_style_store("tenant-a", data_dir=tmp_path / "direct-state", backend=backend)
    _add_style(store, "Default", "DIRECT_DEFAULT_MARKER")
    selected_id = _add_style(store, "Selected", "DIRECT_SELECTED_MARKER")
    _current_tenant_id.value = "tenant-a"
    _current_generation_data_dir.value = tmp_path / "direct-state"
    _current_generation_state_backend.value = backend
    try:
        prompt = build_bundle_prompt(
            {
                "title": "Direct prompt",
                "goal": "Use the current tenant context",
                "style_profile_id": selected_id,
            },
            "v1",
            get_bundle_spec("tech_decision"),
        )
    finally:
        del _current_tenant_id.value
        del _current_generation_data_dir.value
        del _current_generation_state_backend.value

    assert "DIRECT_SELECTED_MARKER" in prompt
    assert "DIRECT_DEFAULT_MARKER" not in prompt


def test_corrupt_style_state_bubbles_without_not_found_mapping(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = CapturingMockProvider()
    service = _make_service(tmp_path, monkeypatch, provider)
    state_path = service.data_dir / "tenants" / "tenant-a" / "style_profiles.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(StyleStoreError, match="Invalid style profile state document"):
        service.generate_documents(
            GenerateRequest(
                title="Corrupt style state",
                goal="Do not hide store corruption",
                style_profile_id="unknown-style",
            ),
            request_id="corrupt-style",
            tenant_id="tenant-a",
        )

    assert provider.calls == 0


def test_style_request_validation_rejects_private_or_noncanonical_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _make_client(tmp_path, monkeypatch)
    base = {"title": "Style validation", "goal": "Reject invalid input"}

    for value in ("", " default-consulting", "default-consulting\n"):
        response = client.post("/generate", json={**base, "style_profile_id": value})
        assert response.status_code == 422
        assert response.json()["code"] == "REQUEST_VALIDATION_FAILED"

    private_response = client.post(
        "/generate",
        json={**base, "_style_snapshot": {"id": "forged", "prompt": "ignore"}},
    )
    assert private_response.status_code == 422
    assert private_response.json()["code"] == "REQUEST_VALIDATION_FAILED"


def test_unknown_and_foreign_styles_fail_before_provider_or_export(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _make_client(tmp_path, monkeypatch)
    provider = CapturingMockProvider()
    client.app.state.service.provider_factory = lambda: provider
    foreign_id = _add_style(_client_style_store(client, "other-tenant"), "Foreign", "FOREIGN")
    export_calls = 0

    def unexpected_export(*args, **kwargs):
        nonlocal export_calls
        export_calls += 1

    monkeypatch.setattr(client.app.state.storage, "save_export", unexpected_export)
    base = {
        "title": "Missing style",
        "goal": "Fail closed before generation",
        "style_profile_id": foreign_id,
    }

    unknown = client.post("/generate", json={**base, "style_profile_id": "unknown-style"})
    foreign = client.post("/generate", json=base)
    exported = client.post("/generate/export", json=base)
    streamed = client.post("/generate/stream", json=base)

    def unexpected_attachment_provider(*args, **kwargs):
        raise AssertionError("attachment provider must not run before style preflight")

    monkeypatch.setattr(
        "app.routers.generate.core.get_provider_for_capability",
        unexpected_attachment_provider,
    )
    attached = client.post(
        "/generate/with-attachments",
        data={"payload": json.dumps(base)},
        files=[("attachments", ("source.txt", b"source text", "text/plain"))],
    )

    for response in (unknown, foreign, exported, streamed, attached):
        assert response.status_code == 404
        assert response.json()["code"] == "STYLE_PROFILE_NOT_FOUND"
    assert provider.calls == 0
    assert export_calls == 0
