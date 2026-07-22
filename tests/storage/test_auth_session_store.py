from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from app.storage.auth_session_store import AuthSessionStore, AuthSessionStoreError


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
