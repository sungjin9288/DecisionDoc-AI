from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
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
def test_auth_session_store_retention_preview_is_read_only_and_aggregate_only(
    tmp_path,
    monkeypatch,
    backend_kind,
):
    import app.storage.auth_session_store as auth_session_module

    if backend_kind == "s3":
        backend, _ = s3_backend()
        store = AuthSessionStore("tenant-a", backend=backend)
    else:
        store = _store(tmp_path)
        backend = store._backend

    now = datetime(2026, 7, 23, 12, tzinfo=timezone.utc)
    clock = [now - timedelta(days=100)]
    monkeypatch.setattr(auth_session_module, "_utcnow", lambda: clock[0])

    expired = store.create(user_id="user-expired", credential_version=0)
    assert store.set_label(
        expired,
        user_id="user-expired",
        credential_version=0,
        label="private expired label",
    )
    revoked = store.create(user_id="user-revoked", credential_version=0)
    assert store.set_label(
        revoked,
        user_id="user-revoked",
        credential_version=0,
        label="private revoked label",
    )
    clock[0] = now - timedelta(days=80)
    assert store.revoke(revoked, user_id="user-revoked")

    clock[0] = now - timedelta(days=10)
    recent_revoked = store.create(user_id="user-recent", credential_version=0)
    clock[0] = now - timedelta(days=5)
    assert store.revoke(recent_revoked, user_id="user-recent")
    active = store.create(user_id="user-active", credential_version=0)

    prefix = "tenants/tenant-a/auth_sessions"
    paths = backend.list_prefix(prefix)
    original = {path: backend.read_text(path) for path in paths}
    clock[0] = now

    preview = store.preview_retention(retention_days=30)

    assert preview == {
        "contract_version": "auth-session-retention-preview.v1",
        "generated_at": now.isoformat(),
        "retention_days": 30,
        "eligible_before": (now - timedelta(days=30)).isoformat(),
        "inspected_sessions": 4,
        "eligible_sessions": 2,
        "eligible_by_reason": {"expired": 1, "revoked": 1},
        "active_sessions": 1,
        "retained_inactive_sessions": 1,
        "oldest_eligible_inactive_at": (now - timedelta(days=80)).isoformat(),
        "read_only": True,
        "deletion_authorized": False,
    }
    serialized = json.dumps(preview, ensure_ascii=False)
    for private_value in (
        expired,
        revoked,
        recent_revoked,
        active,
        "user-expired",
        "private expired label",
        "private revoked label",
    ):
        assert private_value not in serialized
    assert {path: backend.read_text(path) for path in paths} == original


def test_auth_session_store_retention_preview_rejects_invalid_policy_and_corrupt_prefix(
    tmp_path,
):
    store = _store(tmp_path)
    store.create(user_id="user-a", credential_version=0)
    corrupt_path = (
        tmp_path
        / "tenants"
        / "tenant-a"
        / "auth_sessions"
        / f"{'f' * 32}.json"
    )
    corrupt = b'{"session_id":"duplicate","session_id":"forged"}'
    corrupt_path.write_bytes(corrupt)

    with pytest.raises(ValueError, match="retention_days"):
        store.preview_retention(retention_days=0)
    with pytest.raises(ValueError, match="retention_days"):
        store.preview_retention(retention_days=3651)
    with pytest.raises(AuthSessionStoreError):
        store.preview_retention(retention_days=30)

    assert corrupt_path.read_bytes() == corrupt


@pytest.mark.parametrize("backend_kind", ["local", "s3"])
def test_auth_session_store_compares_retention_policies_from_one_inspection(
    tmp_path,
    monkeypatch,
    backend_kind,
):
    import app.storage.auth_session_store as auth_session_module

    if backend_kind == "s3":
        backend, _ = s3_backend()
        store = AuthSessionStore("tenant-a", backend=backend)
    else:
        store = _store(tmp_path)
        backend = store._backend

    now = datetime(2026, 7, 23, 12, tzinfo=timezone.utc)
    clock = [now - timedelta(days=500)]
    monkeypatch.setattr(auth_session_module, "_utcnow", lambda: clock[0])

    very_old = store.create(user_id="user-very-old", credential_version=0)
    clock[0] = now - timedelta(days=100)
    old_expired = store.create(user_id="user-expired", credential_version=0)
    clock[0] = now - timedelta(days=170)
    old_revoked = store.create(user_id="user-revoked", credential_version=0)
    clock[0] = now - timedelta(days=150)
    assert store.revoke(old_revoked, user_id="user-revoked")
    clock[0] = now - timedelta(days=10)
    recent_revoked = store.create(user_id="user-recent", credential_version=0)
    active = store.create(user_id="user-active", credential_version=0)
    clock[0] = now - timedelta(days=5)
    assert store.revoke(recent_revoked, user_id="user-recent")

    prefix = "tenants/tenant-a/auth_sessions"
    paths = backend.list_prefix(prefix)
    original = {path: backend.read_text(path) for path in paths}
    clock[0] = now

    comparison = store.compare_retention_policies()

    assert comparison == {
        "contract_version": "auth-session-retention-comparison.v1",
        "generated_at": now.isoformat(),
        "policy_days": [30, 90, 180, 365],
        "inspected_sessions": 5,
        "active_sessions": 1,
        "policies": [
            {
                "retention_days": 30,
                "eligible_before": (now - timedelta(days=30)).isoformat(),
                "eligible_sessions": 3,
                "eligible_by_reason": {"expired": 2, "revoked": 1},
                "retained_inactive_sessions": 1,
                "oldest_eligible_inactive_at": (
                    now - timedelta(days=470)
                ).isoformat(),
            },
            {
                "retention_days": 90,
                "eligible_before": (now - timedelta(days=90)).isoformat(),
                "eligible_sessions": 2,
                "eligible_by_reason": {"expired": 1, "revoked": 1},
                "retained_inactive_sessions": 2,
                "oldest_eligible_inactive_at": (
                    now - timedelta(days=470)
                ).isoformat(),
            },
            {
                "retention_days": 180,
                "eligible_before": (now - timedelta(days=180)).isoformat(),
                "eligible_sessions": 1,
                "eligible_by_reason": {"expired": 1, "revoked": 0},
                "retained_inactive_sessions": 3,
                "oldest_eligible_inactive_at": (
                    now - timedelta(days=470)
                ).isoformat(),
            },
            {
                "retention_days": 365,
                "eligible_before": (now - timedelta(days=365)).isoformat(),
                "eligible_sessions": 1,
                "eligible_by_reason": {"expired": 1, "revoked": 0},
                "retained_inactive_sessions": 3,
                "oldest_eligible_inactive_at": (
                    now - timedelta(days=470)
                ).isoformat(),
            },
        ],
        "read_only": True,
        "deletion_authorized": False,
        "snapshot_atomic": False,
        "requires_recheck_before_mutation": True,
    }
    serialized = json.dumps(comparison, ensure_ascii=False)
    for private_value in (
        very_old,
        old_expired,
        old_revoked,
        recent_revoked,
        active,
        "user-very-old",
        "user-expired",
        "user-revoked",
    ):
        assert private_value not in serialized
    assert {path: backend.read_text(path) for path in paths} == original


def test_auth_session_store_retention_comparison_fails_closed_on_corrupt_prefix(
    tmp_path,
):
    store = _store(tmp_path)
    store.create(user_id="user-a", credential_version=0)
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
        store.compare_retention_policies()

    assert corrupt_path.read_bytes() == corrupt


@pytest.mark.parametrize("backend_kind", ["local", "s3"])
def test_auth_session_store_builds_read_only_retention_review_handoff(
    tmp_path,
    monkeypatch,
    backend_kind,
):
    import app.storage.auth_session_store as auth_session_module

    if backend_kind == "s3":
        backend, _ = s3_backend()
        store = AuthSessionStore("tenant-a", backend=backend)
    else:
        store = _store(tmp_path)
        backend = store._backend

    now = datetime(2026, 7, 23, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(auth_session_module, "_utcnow", lambda: now)
    session_id = store.create(user_id="private-user", credential_version=0)
    assert store.set_label(
        session_id,
        user_id="private-user",
        credential_version=0,
        label="private label",
    )
    prefix = "tenants/tenant-a/auth_sessions"
    paths = backend.list_prefix(prefix)
    original = {path: backend.read_text(path) for path in paths}

    handoff = store.build_retention_review_handoff(retention_days=90)

    comparison = handoff["comparison"]
    canonical_comparison = json.dumps(
        comparison,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    assert handoff == {
        "contract_version": "auth-session-retention-review-handoff.v1",
        "selected_policy_days": 90,
        "comparison": comparison,
        "comparison_sha256": hashlib.sha256(canonical_comparison).hexdigest(),
        "review_only": True,
        "policy_change_authorized": False,
        "deletion_authorized": False,
        "scheduler_authorized": False,
        "snapshot_atomic": False,
        "requires_recheck_before_mutation": True,
        "handoff_persisted": False,
    }
    serialized = json.dumps(handoff, ensure_ascii=False)
    assert session_id not in serialized
    assert "private-user" not in serialized
    assert "private label" not in serialized
    assert {path: backend.read_text(path) for path in paths} == original

    with pytest.raises(ValueError, match="retention_days"):
        store.build_retention_review_handoff(retention_days=31)


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

    family_emoji = "가족 👨‍👩‍👧‍👦"
    assert store.set_label(
        session_id,
        user_id="user-a",
        credential_version=3,
        label=family_emoji,
    ) is True
    assert store.list_active(user_id="user-a", credential_version=3)[0]["label"] == family_emoji

    assert store.set_label(
        session_id,
        user_id="user-a",
        credential_version=3,
        label=None,
    ) is True
    assert store.list_active(user_id="user-a", credential_version=3)[0]["label"] is None


@pytest.mark.parametrize(
    "label",
    [
        "office\u0085laptop",
        "office\u0085",
        "office\u2028laptop",
        "office\u202elaptop",
        "office\u2066laptop",
    ],
)
def test_auth_session_store_rejects_display_control_characters_without_rewrite(
    tmp_path,
    label,
):
    store = _store(tmp_path)
    session_id = store.create(user_id="user-a", credential_version=3)
    path = (
        tmp_path
        / "tenants"
        / "tenant-a"
        / "auth_sessions"
        / f"{session_id}.json"
    )
    original = path.read_bytes()

    with pytest.raises(ValueError, match="display control"):
        store.set_label(
            session_id,
            user_id="user-a",
            credential_version=3,
            label=label,
        )

    assert path.read_bytes() == original


def test_auth_session_store_rejects_persisted_display_control_without_rewrite(
    tmp_path,
):
    store = _store(tmp_path)
    session_id = store.create(user_id="user-a", credential_version=3)
    path = (
        tmp_path
        / "tenants"
        / "tenant-a"
        / "auth_sessions"
        / f"{session_id}.json"
    )
    record = json.loads(path.read_text(encoding="utf-8"))
    record["label"] = "office\u202elaptop"
    path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    corrupted = path.read_bytes()

    with pytest.raises(AuthSessionStoreError):
        store.is_current(session_id, user_id="user-a", credential_version=3)

    assert path.read_bytes() == corrupted


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
