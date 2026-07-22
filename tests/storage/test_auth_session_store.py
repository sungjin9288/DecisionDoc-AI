from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json

import pytest

from app.storage.auth_session_store import AuthSessionStore, AuthSessionStoreError
from tests.conditional_state_support import s3_backend


def _store(tmp_path) -> AuthSessionStore:
    return AuthSessionStore("tenant-a", data_dir=tmp_path)


def test_auth_session_store_revokes_one_exact_authority(tmp_path):
    store = _store(tmp_path)
    first = store.create(user_id="user-a", credential_version=2)
    second = store.create(user_id="user-a", credential_version=2)

    assert first != second
    assert store.is_current(first, user_id="user-a", credential_version=2)
    assert store.is_current(second, user_id="user-a", credential_version=2)

    assert store.revoke(first, user_id="user-a") is True
    assert store.is_current(first, user_id="user-a", credential_version=2) is False
    assert store.is_current(second, user_id="user-a", credential_version=2) is True


def test_auth_session_store_lists_only_active_matching_authority_newest_first(
    tmp_path,
    monkeypatch,
):
    import app.storage.auth_session_store as auth_session_module

    base = datetime(2026, 7, 22, tzinfo=timezone.utc)
    observed_times = iter(base + timedelta(minutes=offset) for offset in range(7))
    monkeypatch.setattr(auth_session_module, "_utcnow", lambda: next(observed_times))
    store = _store(tmp_path)

    older = store.create(user_id="user-a", credential_version=2)
    newer = store.create(user_id="user-a", credential_version=2)
    revoked = store.create(user_id="user-a", credential_version=2)
    store.create(user_id="user-b", credential_version=2)
    store.create(user_id="user-a", credential_version=1)
    assert store.revoke(revoked, user_id="user-a") is True

    active = store.list_active(user_id="user-a", credential_version=2)

    assert [record["session_id"] for record in active] == [newer, older]
    assert all(record["revoked_at"] is None for record in active)


def test_auth_session_store_list_fails_closed_on_unexpected_child_without_rewrite(
    tmp_path,
):
    store = _store(tmp_path)
    store.create(user_id="user-a", credential_version=0)
    unexpected = (
        tmp_path
        / "tenants"
        / "tenant-a"
        / "auth_sessions"
        / "unexpected.txt"
    )
    payload = b"do-not-rewrite"
    unexpected.write_bytes(payload)

    with pytest.raises(AuthSessionStoreError):
        store.list_active(user_id="user-a", credential_version=0)

    assert unexpected.read_bytes() == payload


def test_auth_session_store_lists_and_revokes_selected_s3_backend_authority():
    backend, _ = s3_backend()
    store = AuthSessionStore("tenant-a", backend=backend)
    current = store.create(user_id="user-a", credential_version=3)
    other = store.create(user_id="user-a", credential_version=3)

    assert {
        record["session_id"]
        for record in store.list_active(user_id="user-a", credential_version=3)
    } == {current, other}
    assert store.revoke(other, user_id="user-a") is True
    assert [
        record["session_id"]
        for record in store.list_active(user_id="user-a", credential_version=3)
    ] == [current]


@pytest.mark.parametrize("backend_kind", ["local", "s3"])
def test_auth_session_store_sets_and_clears_owned_session_label(
    tmp_path,
    backend_kind,
):
    if backend_kind == "s3":
        backend, _ = s3_backend()
        store = AuthSessionStore("tenant-a", backend=backend)
    else:
        store = _store(tmp_path)

    session_id = store.create(user_id="user-a", credential_version=3)

    assert store.set_label(
        session_id,
        user_id="user-a",
        credential_version=3,
        label="업무용 Mac",
    ) is True
    assert store.list_active(user_id="user-a", credential_version=3)[0]["label"] == "업무용 Mac"

    assert store.set_label(
        session_id,
        user_id="user-a",
        credential_version=3,
        label=None,
    ) is True
    assert store.list_active(user_id="user-a", credential_version=3)[0]["label"] is None


def test_auth_session_store_upgrades_legacy_v1_record_when_label_is_set(tmp_path):
    store = _store(tmp_path)
    session_id = store.create(user_id="user-a", credential_version=0)
    path = (
        tmp_path
        / "tenants"
        / "tenant-a"
        / "auth_sessions"
        / f"{session_id}.json"
    )
    legacy = json.loads(path.read_text(encoding="utf-8"))
    legacy["contract_version"] = "auth-session.v1"
    legacy.pop("label", None)
    path.write_text(json.dumps(legacy), encoding="utf-8")

    assert store.is_current(session_id, user_id="user-a", credential_version=0)
    assert store.list_active(user_id="user-a", credential_version=0)[0].get("label") is None
    assert store.set_label(
        session_id,
        user_id="user-a",
        credential_version=0,
        label="회의실 PC",
    ) is True

    upgraded = json.loads(path.read_text(encoding="utf-8"))
    assert upgraded["contract_version"] == "auth-session.v2"
    assert upgraded["label"] == "회의실 PC"


def test_auth_session_store_label_update_requires_current_owner_authority(tmp_path):
    store = _store(tmp_path)
    session_id = store.create(user_id="user-a", credential_version=2)

    assert store.set_label(
        session_id,
        user_id="user-b",
        credential_version=2,
        label="foreign",
    ) is False
    assert store.set_label(
        session_id,
        user_id="user-a",
        credential_version=3,
        label="stale",
    ) is False
    assert store.revoke(session_id, user_id="user-a") is True
    assert store.set_label(
        session_id,
        user_id="user-a",
        credential_version=2,
        label="revoked",
    ) is False


def test_auth_session_store_recovers_lost_s3_label_write_response():
    backend, client = s3_backend()
    store = AuthSessionStore("tenant-a", backend=backend)
    session_id = store.create(user_id="user-a", credential_version=0)
    client.fail_after_next_conditional_write(key_fragment=f"{session_id}.json")

    assert store.set_label(
        session_id,
        user_id="user-a",
        credential_version=0,
        label="개인 노트북",
    ) is True
    assert store.list_active(user_id="user-a", credential_version=0)[0]["label"] == "개인 노트북"


@pytest.mark.parametrize("backend_kind", ["local", "s3"])
def test_auth_session_store_revokes_all_other_active_sessions(
    tmp_path,
    backend_kind,
):
    if backend_kind == "s3":
        backend, _ = s3_backend()
        store = AuthSessionStore("tenant-a", backend=backend)
    else:
        store = _store(tmp_path)

    current = store.create(user_id="user-a", credential_version=3)
    first_other = store.create(user_id="user-a", credential_version=3)
    second_other = store.create(user_id="user-a", credential_version=3)
    foreign = store.create(user_id="user-b", credential_version=3)
    older_version = store.create(user_id="user-a", credential_version=2)

    assert store.revoke_others(
        current_session_id=current,
        user_id="user-a",
        credential_version=3,
    ) == 2
    assert store.revoke_others(
        current_session_id=current,
        user_id="user-a",
        credential_version=3,
    ) == 0

    assert store.is_current(current, user_id="user-a", credential_version=3)
    assert not store.is_current(first_other, user_id="user-a", credential_version=3)
    assert not store.is_current(second_other, user_id="user-a", credential_version=3)
    assert store.is_current(foreign, user_id="user-b", credential_version=3)
    assert store.is_current(older_version, user_id="user-a", credential_version=2)


def test_auth_session_store_bulk_revoke_validates_prefix_before_mutation(tmp_path):
    store = _store(tmp_path)
    current = store.create(user_id="user-a", credential_version=0)
    other = store.create(user_id="user-a", credential_version=0)
    corrupt_path = (
        tmp_path
        / "tenants"
        / "tenant-a"
        / "auth_sessions"
        / f"{'f' * 32}.json"
    )
    corrupt = b'{"session_id":"duplicate","session_id":"forged"}'
    corrupt_path.write_bytes(corrupt)

    with pytest.raises(AuthSessionStoreError):
        store.revoke_others(
            current_session_id=current,
            user_id="user-a",
            credential_version=0,
        )

    assert store.is_current(current, user_id="user-a", credential_version=0)
    assert store.is_current(other, user_id="user-a", credential_version=0)
    assert corrupt_path.read_bytes() == corrupt


@pytest.mark.parametrize("backend_kind", ["local", "s3"])
def test_auth_session_store_revokes_all_active_sessions(
    tmp_path,
    backend_kind,
):
    if backend_kind == "s3":
        backend, _ = s3_backend()
        store = AuthSessionStore("tenant-a", backend=backend)
    else:
        store = _store(tmp_path)

    current = store.create(user_id="user-a", credential_version=3)
    first_other = store.create(user_id="user-a", credential_version=3)
    second_other = store.create(user_id="user-a", credential_version=3)
    foreign = store.create(user_id="user-b", credential_version=3)
    older_version = store.create(user_id="user-a", credential_version=2)

    assert store.revoke_all(
        current_session_id=current,
        user_id="user-a",
        credential_version=3,
    ) == 3

    assert not store.is_current(current, user_id="user-a", credential_version=3)
    assert not store.is_current(first_other, user_id="user-a", credential_version=3)
    assert not store.is_current(second_other, user_id="user-a", credential_version=3)
    assert store.is_current(foreign, user_id="user-b", credential_version=3)
    assert store.is_current(older_version, user_id="user-a", credential_version=2)


def test_auth_session_store_revoke_all_keeps_current_until_other_writes_finish(
    tmp_path,
    monkeypatch,
):
    store = _store(tmp_path)
    current = store.create(user_id="user-a", credential_version=0)
    store.create(user_id="user-a", credential_version=0)
    store.create(user_id="user-a", credential_version=0)
    original_revoke = store.revoke
    calls: list[str] = []

    def fail_after_one_other(session_id: str, *, user_id: str) -> bool:
        calls.append(session_id)
        if len(calls) == 2:
            raise AuthSessionStoreError("injected write failure")
        return original_revoke(session_id, user_id=user_id)

    monkeypatch.setattr(store, "revoke", fail_after_one_other)

    with pytest.raises(AuthSessionStoreError, match="injected write failure"):
        store.revoke_all(
            current_session_id=current,
            user_id="user-a",
            credential_version=0,
        )

    assert len(calls) == 2
    assert current not in calls
    assert not store.is_current(calls[0], user_id="user-a", credential_version=0)
    assert store.is_current(calls[1], user_id="user-a", credential_version=0)
    assert store.is_current(current, user_id="user-a", credential_version=0)


def test_auth_session_store_revoke_all_validates_prefix_before_mutation(tmp_path):
    store = _store(tmp_path)
    current = store.create(user_id="user-a", credential_version=0)
    other = store.create(user_id="user-a", credential_version=0)
    corrupt_path = (
        tmp_path
        / "tenants"
        / "tenant-a"
        / "auth_sessions"
        / f"{'f' * 32}.json"
    )
    corrupt = b'{"session_id":"duplicate","session_id":"forged"}'
    corrupt_path.write_bytes(corrupt)

    with pytest.raises(AuthSessionStoreError):
        store.revoke_all(
            current_session_id=current,
            user_id="user-a",
            credential_version=0,
        )

    assert store.is_current(current, user_id="user-a", credential_version=0)
    assert store.is_current(other, user_id="user-a", credential_version=0)
    assert corrupt_path.read_bytes() == corrupt


def test_auth_session_store_rejects_wrong_authority_without_mutation(tmp_path):
    store = _store(tmp_path)
    session_id = store.create(user_id="user-a", credential_version=2)

    assert store.is_current(session_id, user_id="user-b", credential_version=2) is False
    assert store.is_current(session_id, user_id="user-a", credential_version=3) is False
    assert store.revoke(session_id, user_id="user-b") is False
    assert store.is_current(session_id, user_id="user-a", credential_version=2) is True


def test_auth_session_store_preserves_corrupt_state(tmp_path):
    store = _store(tmp_path)
    session_id = store.create(user_id="user-a", credential_version=0)
    path = (
        tmp_path
        / "tenants"
        / "tenant-a"
        / "auth_sessions"
        / f"{session_id}.json"
    )
    corrupt = b'{"tenant_id":"tenant-a","tenant_id":"forged"}'
    path.write_bytes(corrupt)

    with pytest.raises(AuthSessionStoreError):
        store.is_current(session_id, user_id="user-a", credential_version=0)
    with pytest.raises(AuthSessionStoreError):
        store.revoke(session_id, user_id="user-a")

    assert path.read_bytes() == corrupt


def test_concurrent_auth_session_revoke_is_idempotent(tmp_path):
    creator = _store(tmp_path)
    session_id = creator.create(user_id="user-a", credential_version=0)
    stores = [_store(tmp_path) for _ in range(12)]

    with ThreadPoolExecutor(max_workers=len(stores)) as executor:
        results = list(
            executor.map(
                lambda store: store.revoke(session_id, user_id="user-a"),
                stores,
            )
        )

    assert results == [True] * len(stores)
    assert creator.is_current(
        session_id,
        user_id="user-a",
        credential_version=0,
    ) is False
