from __future__ import annotations

import json
import time
from contextlib import nullcontext
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from app.storage.state_backend import LocalStateBackend
from app.storage.tenant_store import TenantRegistryError, TenantStore
from tests.conditional_state_support import (
    ConflictingLocalBackend,
    MemoryS3Client,
    s3_backend,
)


class _SlowLocalBackend(LocalStateBackend):
    """Make overlapping read-modify-write sequences deterministic in tests."""

    def read_text(self, relative_path: str) -> str | None:
        raw = super().read_text(relative_path)
        time.sleep(0.005)
        return raw


@pytest.mark.parametrize(
    "tenant_id",
    [
        "",
        " ",
        " tenant-a",
        "tenant-a ",
        ".",
        "..",
        "tenant/a",
        "tenant\\a",
        "tenant\x00a",
        "tenant\na",
        "tenant\x7fa",
    ],
)
def test_rejects_unsafe_tenant_id_before_registry_write(
    tmp_path: Path,
    tenant_id: str,
) -> None:
    store = TenantStore(tmp_path)

    with pytest.raises(ValueError, match="Invalid tenant_id"):
        store.create_tenant(tenant_id, "Unsafe")

    assert not (tmp_path / "tenants.json").exists()


def test_forged_record_is_not_read_authenticated_or_modified(tmp_path: Path) -> None:
    store = TenantStore(tmp_path)
    store.create_tenant("tenant-a", "Tenant A")
    api_key = store.rotate_api_key("tenant-a")
    path = tmp_path / "tenants.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["tenant-a"]["tenant_id"] = "tenant-b"
    path.write_text(json.dumps(payload), encoding="utf-8")
    forged_bytes = path.read_bytes()

    assert store.get_tenant("tenant-a") is None
    assert store.list_tenants() == []
    assert store.find_tenant_by_api_key(api_key) is None

    for operation in (
        lambda: store.update_tenant("tenant-a", display_name="Overwritten"),
        lambda: store.set_custom_hint("tenant-a", "tech_decision", "Overwritten"),
        lambda: store.delete_custom_hint("tenant-a", "tech_decision"),
        lambda: store.rotate_api_key("tenant-a"),
    ):
        with pytest.raises(ValueError, match="ownership mismatch"):
            operation()
        assert path.read_bytes() == forged_bytes


def test_malformed_record_is_excluded_without_hiding_valid_tenants(
    tmp_path: Path,
) -> None:
    store = TenantStore(tmp_path)
    store.create_tenant("tenant-a", "Tenant A")
    store.create_tenant("tenant-b", "Tenant B")
    path = tmp_path / "tenants.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["tenant-b"]["allowed_bundles"] = "tech_decision"
    path.write_text(json.dumps(payload), encoding="utf-8")
    malformed_bytes = path.read_bytes()

    assert store.get_tenant("tenant-b") is None
    assert [tenant.tenant_id for tenant in store.list_tenants()] == ["tenant-a"]

    with pytest.raises(ValueError, match="allowed_bundles"):
        store.update_tenant("tenant-b", display_name="Overwritten")
    assert path.read_bytes() == malformed_bytes


@pytest.mark.parametrize(
    "raw",
    [
        "{not-json",
        "[]",
        '{"tenant-a": {}, "tenant-a": {}}',
    ],
)
def test_invalid_registry_stops_reads_and_writes_without_replacement(
    tmp_path: Path,
    raw: str,
) -> None:
    path = tmp_path / "tenants.json"
    path.write_text(raw, encoding="utf-8")
    store = TenantStore(tmp_path)
    original_bytes = path.read_bytes()

    with pytest.raises(ValueError, match="Invalid tenant registry"):
        store.list_tenants()
    with pytest.raises(ValueError, match="Invalid tenant registry"):
        store.create_tenant("tenant-b", "Tenant B")

    assert path.read_bytes() == original_bytes


def test_duplicate_active_api_key_hash_is_ambiguous(tmp_path: Path) -> None:
    store = TenantStore(tmp_path)
    store.create_tenant("tenant-a", "Tenant A")
    store.create_tenant("tenant-b", "Tenant B")
    api_key = store.rotate_api_key("tenant-a")
    path = tmp_path / "tenants.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["tenant-b"]["api_key_hash"] = payload["tenant-a"]["api_key_hash"]
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert store.find_tenant_by_api_key(api_key) is None


def test_independent_instances_preserve_concurrent_tenant_creates(
    tmp_path: Path,
) -> None:
    backend = _SlowLocalBackend(tmp_path)
    stores = [TenantStore(tmp_path, backend=backend) for _ in range(20)]
    for store in stores:
        store._lock = nullcontext()

    def create(index: int) -> str:
        tenant_id = f"tenant-{index:02d}"
        return stores[index].create_tenant(tenant_id, f"Tenant {index}").tenant_id

    with ThreadPoolExecutor(max_workers=20) as executor:
        created = set(executor.map(create, range(20)))

    assert created == {f"tenant-{index:02d}" for index in range(20)}
    assert {
        tenant.tenant_id for tenant in TenantStore(tmp_path).list_tenants()
    } == created


def test_independent_instances_bootstrap_system_tenant_once(tmp_path: Path) -> None:
    backend = _SlowLocalBackend(tmp_path)
    stores = [TenantStore(tmp_path, backend=backend) for _ in range(20)]
    for store in stores:
        store._lock = nullcontext()

    with ThreadPoolExecutor(max_workers=20) as executor:
        tenants = list(executor.map(lambda store: store.ensure_system_tenant(), stores))

    assert {tenant.tenant_id for tenant in tenants} == {"system"}
    assert [tenant.tenant_id for tenant in TenantStore(tmp_path).list_tenants()] == [
        "system"
    ]


def test_independent_instances_allow_only_one_duplicate_create(tmp_path: Path) -> None:
    backend = _SlowLocalBackend(tmp_path)
    stores = [TenantStore(tmp_path, backend=backend) for _ in range(20)]
    for store in stores:
        store._lock = nullcontext()

    def create(store: TenantStore) -> bool:
        try:
            store.create_tenant("tenant-a", "Tenant A")
        except ValueError as exc:
            assert "already exists" in str(exc)
            return False
        return True

    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(create, stores))

    assert results.count(True) == 1
    assert [tenant.tenant_id for tenant in TenantStore(tmp_path).list_tenants()] == [
        "tenant-a"
    ]


def test_independent_s3_instances_preserve_concurrent_tenant_creates() -> None:
    client = MemoryS3Client(read_delay=0.005)
    stores = [
        TenantStore(
            Path(f"/virtual/data-{index}"),
            backend=s3_backend(client)[0],
        )
        for index in range(20)
    ]
    for store in stores:
        store._lock = nullcontext()

    def create(index: int) -> str:
        tenant_id = f"tenant-{index:02d}"
        return (
            stores[index]
            .create_tenant(
                tenant_id,
                f"Tenant {index}",
            )
            .tenant_id
        )

    with ThreadPoolExecutor(max_workers=20) as executor:
        created = set(executor.map(create, range(20)))

    assert {tenant.tenant_id for tenant in stores[0].list_tenants()} == created


def test_tenant_create_reconciles_commit_then_successor_update() -> None:
    client = MemoryS3Client()
    primary = TenantStore(
        Path("/virtual/primary"),
        backend=s3_backend(client)[0],
    )
    successor = TenantStore(
        Path("/virtual/successor"),
        backend=s3_backend(client)[0],
    )
    primary._lock = nullcontext()
    successor._lock = nullcontext()

    client.fail_after_next_conditional_write(
        key_fragment="tenants.json",
        after_write=lambda: successor.update_tenant(
            "tenant-a",
            display_name="Successor name",
        ),
    )
    created = primary.create_tenant("tenant-a", "Initial name")

    persisted = primary.get_tenant("tenant-a")
    assert created.display_name == "Initial name"
    assert persisted is not None
    assert persisted.display_name == "Successor name"


def test_api_key_rotation_reconciles_commit_then_successor_hint() -> None:
    client = MemoryS3Client()
    primary = TenantStore(
        Path("/virtual/primary"),
        backend=s3_backend(client)[0],
    )
    successor = TenantStore(
        Path("/virtual/successor"),
        backend=s3_backend(client)[0],
    )
    primary._lock = nullcontext()
    successor._lock = nullcontext()
    primary.create_tenant("tenant-a", "Tenant A")

    client.fail_after_next_conditional_write(
        key_fragment="tenants.json",
        after_write=lambda: successor.set_custom_hint(
            "tenant-a",
            "tech_decision",
            "Keep the decision concise.",
        ),
    )
    api_key = primary.rotate_api_key("tenant-a")

    assert primary.find_tenant_by_api_key(api_key) == "tenant-a"
    assert (
        primary.get_custom_hint("tenant-a", "tech_decision")
        == "Keep the decision concise."
    )


def test_api_key_rotation_rejects_superseded_lost_response() -> None:
    client = MemoryS3Client()
    primary = TenantStore(
        Path("/virtual/primary"),
        backend=s3_backend(client)[0],
    )
    successor = TenantStore(
        Path("/virtual/successor"),
        backend=s3_backend(client)[0],
    )
    primary._lock = nullcontext()
    successor._lock = nullcontext()
    primary.create_tenant("tenant-a", "Tenant A")
    successor_key: str | None = None

    def rotate_successor() -> None:
        nonlocal successor_key
        successor_key = successor.rotate_api_key("tenant-a")

    client.fail_after_next_conditional_write(
        key_fragment="tenants.json",
        after_write=rotate_successor,
    )

    with pytest.raises(TenantRegistryError, match="Failed to persist"):
        primary.rotate_api_key("tenant-a")

    assert successor_key is not None
    assert primary.find_tenant_by_api_key(successor_key) == "tenant-a"


def test_api_key_rotation_rejects_lost_response_for_foreign_record() -> None:
    client = MemoryS3Client()
    backend = s3_backend(client)[0]
    primary = TenantStore(Path("/virtual/primary"), backend=backend)
    primary._lock = nullcontext()
    primary.create_tenant("tenant-a", "Tenant A")

    def forge_owner_after_commit() -> None:
        object_key = next(
            key for key in client.objects if key[1].endswith("tenants.json")
        )
        payload = json.loads(client.objects[object_key])
        payload["tenant-a"]["tenant_id"] = "tenant-b"
        client.objects[object_key] = json.dumps(payload).encode()

    client.fail_after_next_conditional_write(
        key_fragment="tenants.json",
        after_write=forge_owner_after_commit,
    )

    with pytest.raises(TenantRegistryError, match="Failed to persist"):
        primary.rotate_api_key("tenant-a")


def test_tenant_mutations_stop_after_bounded_conflicts(tmp_path: Path) -> None:
    backend = ConflictingLocalBackend(
        tmp_path,
        conflict_suffix="tenants.json",
    )
    store = TenantStore(tmp_path, backend=backend)
    store._lock = nullcontext()

    with pytest.raises(TenantRegistryError, match="changed too many times"):
        store.create_tenant("tenant-a", "Tenant A")

    assert backend.attempts == 32


def test_existing_tenant_mutation_stops_after_bounded_conflicts(
    tmp_path: Path,
) -> None:
    TenantStore(tmp_path).create_tenant("tenant-a", "Tenant A")
    backend = ConflictingLocalBackend(
        tmp_path,
        conflict_suffix="tenants.json",
    )
    store = TenantStore(tmp_path, backend=backend)
    store._lock = nullcontext()

    with pytest.raises(TenantRegistryError, match="changed too many times"):
        store.update_tenant("tenant-a", display_name="Blocked")

    assert backend.attempts == 32


def test_tenant_matching_old_metadata_name_remains_addressable(
    tmp_path: Path,
) -> None:
    store = TenantStore(tmp_path)

    created = store.create_tenant("_registry_mutation_ids", "Legacy Tenant")

    assert created.tenant_id == "_registry_mutation_ids"
    assert {tenant.tenant_id for tenant in store.list_tenants()} == {
        "_registry_mutation_ids"
    }


def test_tenant_private_state_is_hidden_and_bounded(tmp_path: Path) -> None:
    store = TenantStore(tmp_path)
    store.create_tenant("tenant-a", "Tenant A")
    for index in range(70):
        store.set_custom_hint(
            "tenant-a",
            f"bundle-{index}",
            f"Hint {index}",
        )

    public_ids = {tenant.tenant_id for tenant in store.list_tenants()}
    persisted = json.loads((tmp_path / "tenants.json").read_text(encoding="utf-8"))

    assert public_ids == {"tenant-a"}
    assert len(persisted[""]["_registry_mutation_ids"]) == 64


def test_invalid_tenant_mutation_history_fails_closed(tmp_path: Path) -> None:
    store = TenantStore(tmp_path)
    store.create_tenant("tenant-a", "Tenant A")
    path = tmp_path / "tenants.json"
    persisted = json.loads(path.read_text(encoding="utf-8"))
    persisted[""]["_registry_mutation_ids"] = [
        f"mutation-{index}" for index in range(65)
    ]
    path.write_text(json.dumps(persisted), encoding="utf-8")
    original = path.read_bytes()

    with pytest.raises(TenantRegistryError, match="mutation history"):
        store.list_tenants()
    with pytest.raises(TenantRegistryError, match="mutation history"):
        store.update_tenant("tenant-a", display_name="Blocked")

    assert path.read_bytes() == original


def test_null_tenant_mutation_history_fails_closed(tmp_path: Path) -> None:
    store = TenantStore(tmp_path)
    store.create_tenant("tenant-a", "Tenant A")
    path = tmp_path / "tenants.json"
    persisted = json.loads(path.read_text(encoding="utf-8"))
    persisted[""] = None
    path.write_text(json.dumps(persisted), encoding="utf-8")
    original = path.read_bytes()

    with pytest.raises(TenantRegistryError, match="mutation history"):
        store.list_tenants()
    with pytest.raises(TenantRegistryError, match="mutation history"):
        store.update_tenant("tenant-a", display_name="Blocked")

    assert path.read_bytes() == original
