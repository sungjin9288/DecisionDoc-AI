from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from pathlib import Path

import pytest

from app.storage.state_backend import LocalStateBackend, S3StateBackend
from app.storage.trajectory_store import (
    TrajectoryReviewConflictError,
    TrajectoryStore,
    TrajectoryStoreError,
)
from tests.conditional_state_support import (
    ConflictingLocalBackend,
    MemoryS3Client,
)


def _trajectory(
    trajectory_id: str,
    *,
    title: str | None = None,
) -> dict:
    return {
        "trajectory_id": trajectory_id,
        "schema_version": "document_ops_trajectory_v1",
        "created_at": "2026-07-20T00:00:00+00:00",
        "request_id": f"req-{trajectory_id}",
        "task_type": "decision_brief",
        "input": {
            "requirements": {
                "title": title or trajectory_id,
            }
        },
        "final_output": f"Decision brief for {title or trajectory_id}",
        "skill": {
            "name": "decision_brief",
            "version": "1",
        },
        "qa": {},
        "human_review_status": "pending",
        "human_feedback": {"accepted": False},
    }


def _without_process_lock(store: TrajectoryStore) -> TrajectoryStore:
    store._lock = nullcontext()
    return store


def _s3_backend(client: MemoryS3Client) -> S3StateBackend:
    return S3StateBackend(
        bucket="trajectory-state",
        prefix="state/",
        s3_client=client,
    )


def test_trajectory_store_uses_selected_state_backend(tmp_path: Path) -> None:
    backend_root = tmp_path / "selected-state"
    backend = LocalStateBackend(backend_root)
    store = TrajectoryStore(tmp_path / "unused-data-root", backend=backend)

    store.save(_trajectory("trj_selected_backend"), tenant_id="alpha")

    relative_path = "tenants/alpha/trajectories.jsonl"
    assert backend.read_text(relative_path) is not None
    assert not (
        tmp_path / "unused-data-root" / "tenants" / "alpha" / "trajectories.jsonl"
    ).exists()


@pytest.mark.parametrize("backend_kind", ["local", "s3"])
def test_independent_workers_preserve_concurrent_trajectory_appends(
    tmp_path: Path,
    backend_kind: str,
) -> None:
    local_root = tmp_path / "state"
    client = MemoryS3Client(read_delay=0.001)

    def new_store() -> TrajectoryStore:
        backend = (
            LocalStateBackend(local_root)
            if backend_kind == "local"
            else _s3_backend(client)
        )
        return _without_process_lock(
            TrajectoryStore(tmp_path / "runtime", backend=backend)
        )

    def save(index: int) -> str:
        return new_store().save(
            _trajectory(f"trj_concurrent_{index:02d}"),
            tenant_id="alpha",
        )

    with ThreadPoolExecutor(max_workers=20) as executor:
        trajectory_ids = list(executor.map(save, range(20)))

    records = new_store().get_records(tenant_id="alpha")
    assert {record["trajectory_id"] for record in records} == set(trajectory_ids)
    assert len(records) == 20


def test_concurrent_duplicate_append_is_idempotent_without_process_lock(
    tmp_path: Path,
) -> None:
    client = MemoryS3Client(read_delay=0.001)

    def save() -> str:
        store = _without_process_lock(
            TrajectoryStore(tmp_path, backend=_s3_backend(client))
        )
        return store.save(_trajectory("trj_same"), tenant_id="alpha")

    with ThreadPoolExecutor(max_workers=12) as executor:
        trajectory_ids = list(executor.map(lambda _: save(), range(12)))

    reader = TrajectoryStore(tmp_path, backend=_s3_backend(client))
    assert trajectory_ids == ["trj_same"] * 12
    assert [
        record["trajectory_id"] for record in reader.get_records(tenant_id="alpha")
    ] == ["trj_same"]


def test_same_trajectory_identity_rejects_different_content(
    tmp_path: Path,
) -> None:
    store = TrajectoryStore(tmp_path)
    store.save(
        _trajectory("trj_collision", title="Original"),
        tenant_id="alpha",
    )
    before = store.backend.read_text("tenants/alpha/trajectories.jsonl")

    with pytest.raises(
        TrajectoryStoreError,
        match="different content",
    ):
        store.save(
            _trajectory("trj_collision", title="Replacement"),
            tenant_id="alpha",
        )

    assert store.backend.read_text("tenants/alpha/trajectories.jsonl") == before


def test_same_content_retry_keeps_legacy_path_owned_record_unchanged(
    tmp_path: Path,
) -> None:
    backend = LocalStateBackend(tmp_path)
    relative_path = "tenants/alpha/trajectories.jsonl"
    legacy_record = _trajectory("trj_legacy_retry")
    raw = json.dumps(legacy_record, sort_keys=True) + "\n"
    backend.write_text(
        relative_path,
        raw,
        content_type="application/x-ndjson; charset=utf-8",
    )
    store = TrajectoryStore(tmp_path, backend=backend)

    assert (
        store.save(
            _trajectory("trj_legacy_retry"),
            tenant_id="alpha",
        )
        == "trj_legacy_retry"
    )
    assert backend.read_text(relative_path) == raw


def test_concurrent_reviews_preserve_versions_and_history(
    tmp_path: Path,
) -> None:
    client = MemoryS3Client(read_delay=0.001)
    seed = TrajectoryStore(tmp_path, backend=_s3_backend(client))
    seed.save(_trajectory("trj_review"), tenant_id="alpha")

    def review(index: int) -> dict:
        store = _without_process_lock(
            TrajectoryStore(tmp_path, backend=_s3_backend(client))
        )
        result = store.mark_reviewed(
            "trj_review",
            tenant_id="alpha",
            accepted=index % 2 == 0,
            reviewer=f"reviewer-{index}",
            notes=f"review-{index}",
            quality_score=0.8,
        )
        assert result is not None
        return result

    with ThreadPoolExecutor(max_workers=20) as executor:
        list(executor.map(review, range(20)))

    record = seed.get_record("trj_review", tenant_id="alpha")
    assert record is not None
    assert record["human_feedback"]["review_version"] == 20
    assert len(record["human_review_history"]) == 19
    assert not any(key.startswith("_") for key in record)


def test_expected_review_version_allows_one_concurrent_winner(
    tmp_path: Path,
) -> None:
    client = MemoryS3Client(read_delay=0.001)
    TrajectoryStore(tmp_path, backend=_s3_backend(client)).save(
        _trajectory("trj_expected_version"),
        tenant_id="alpha",
    )

    def review(reviewer: str) -> str:
        store = _without_process_lock(
            TrajectoryStore(tmp_path, backend=_s3_backend(client))
        )
        try:
            store.mark_reviewed(
                "trj_expected_version",
                tenant_id="alpha",
                accepted=True,
                reviewer=reviewer,
                notes=reviewer,
                expected_review_version=0,
            )
        except TrajectoryReviewConflictError:
            return "conflict"
        return "saved"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(review, ["reviewer-a", "reviewer-b"]))

    assert sorted(outcomes) == ["conflict", "saved"]


def test_lost_append_response_reconciles_after_successor_append(
    tmp_path: Path,
) -> None:
    client = MemoryS3Client()
    first = _without_process_lock(
        TrajectoryStore(tmp_path, backend=_s3_backend(client))
    )
    successor = _without_process_lock(
        TrajectoryStore(tmp_path, backend=_s3_backend(client))
    )
    client.fail_after_next_conditional_write(
        key_fragment="trajectories.jsonl",
        after_write=lambda: successor.save(
            _trajectory("trj_successor"),
            tenant_id="alpha",
        ),
    )

    assert first.save(_trajectory("trj_original"), tenant_id="alpha") == "trj_original"
    assert {
        record["trajectory_id"] for record in first.get_records(tenant_id="alpha")
    } == {"trj_original", "trj_successor"}


def test_lost_review_response_reconciles_after_successor_review(
    tmp_path: Path,
) -> None:
    client = MemoryS3Client()
    first = _without_process_lock(
        TrajectoryStore(tmp_path, backend=_s3_backend(client))
    )
    successor = _without_process_lock(
        TrajectoryStore(tmp_path, backend=_s3_backend(client))
    )
    first.save(_trajectory("trj_review_loss"), tenant_id="alpha")
    client.fail_after_next_conditional_write(
        key_fragment="trajectories.jsonl",
        after_write=lambda: successor.mark_reviewed(
            "trj_review_loss",
            tenant_id="alpha",
            accepted=False,
            reviewer="second-reviewer",
            notes="successor",
        ),
    )

    original = first.mark_reviewed(
        "trj_review_loss",
        tenant_id="alpha",
        accepted=True,
        reviewer="first-reviewer",
        notes="original",
    )

    assert original is not None
    assert original["human_feedback"]["review_version"] == 1
    current = first.get_record("trj_review_loss", tenant_id="alpha")
    assert current is not None
    assert current["human_feedback"]["review_version"] == 2
    assert current["human_feedback"]["reviewer"] == "second-reviewer"
    assert current["human_review_history"][0]["reviewer"] == "first-reviewer"


def test_review_receipts_are_bounded_and_private(tmp_path: Path) -> None:
    store = TrajectoryStore(tmp_path)
    store.save(_trajectory("trj_receipts"), tenant_id="alpha")

    for index in range(70):
        store.mark_reviewed(
            "trj_receipts",
            tenant_id="alpha",
            accepted=index % 2 == 0,
            reviewer=f"reviewer-{index}",
            notes=f"review-{index}",
        )

    raw = store.backend.read_text("tenants/alpha/trajectories.jsonl")
    assert raw is not None
    persisted = json.loads(raw)
    assert len(persisted["_review_mutation_ids"]) == 64
    assert "_append_id" in persisted
    assert "_incarnation" in persisted

    public = store.get_record("trj_receipts", tenant_id="alpha")
    assert public is not None
    assert not any(key.startswith("_") for key in public)


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "{not-json}\n",
        "[]\n",
        '{"trajectory_id":"first","trajectory_id":"second"}\n',
        '{"tenant_id":"alpha"}\n',
        (
            '{"trajectory_id":"trj_before_blank","tenant_id":"alpha"}\n'
            "\n"
            '{"trajectory_id":"trj_after_blank","tenant_id":"alpha"}\n'
        ),
        (
            '{"trajectory_id":"trj_bad_private","tenant_id":"alpha",'
            '"_review_mutation_ids":["bad"]}\n'
        ),
        ('{"trajectory_id":"trj_nonfinite","tenant_id":"alpha","quality":NaN}\n'),
    ],
)
def test_corrupt_trajectory_state_fails_closed_without_overwrite(
    tmp_path: Path,
    raw: str,
) -> None:
    backend = LocalStateBackend(tmp_path)
    relative_path = "tenants/alpha/trajectories.jsonl"
    backend.write_text(
        relative_path,
        raw,
        content_type="application/x-ndjson; charset=utf-8",
    )
    store = TrajectoryStore(tmp_path, backend=backend)

    with pytest.raises(TrajectoryStoreError):
        store.get_records(tenant_id="alpha")
    with pytest.raises(TrajectoryStoreError):
        store.save(_trajectory("trj_new"), tenant_id="alpha")

    assert backend.read_text(relative_path) == raw


def test_duplicate_identity_blocks_unrelated_mutation_without_overwrite(
    tmp_path: Path,
) -> None:
    backend = LocalStateBackend(tmp_path)
    relative_path = "tenants/alpha/trajectories.jsonl"
    owned = {
        **_trajectory("trj_duplicate"),
        "tenant_id": "alpha",
    }
    foreign = {
        **_trajectory("trj_duplicate"),
        "tenant_id": "beta",
    }
    raw = (
        "\n".join(json.dumps(record, sort_keys=True) for record in (owned, foreign))
        + "\n"
    )
    backend.write_text(
        relative_path,
        raw,
        content_type="application/x-ndjson; charset=utf-8",
    )
    store = TrajectoryStore(tmp_path, backend=backend)

    assert store.get_record("trj_duplicate", tenant_id="alpha") is None
    with pytest.raises(
        TrajectoryStoreError,
        match="Duplicate trajectory identity",
    ):
        store.save(_trajectory("trj_unrelated"), tenant_id="alpha")

    assert backend.read_text(relative_path) == raw


def test_trajectory_mutation_stops_after_bounded_conflicts(
    tmp_path: Path,
) -> None:
    backend = ConflictingLocalBackend(
        tmp_path,
        conflict_suffix="trajectories.jsonl",
    )
    store = _without_process_lock(TrajectoryStore(tmp_path, backend=backend))

    with pytest.raises(
        TrajectoryStoreError,
        match="changed too many times",
    ):
        store.save(_trajectory("trj_conflict"), tenant_id="alpha")

    assert backend.attempts == 32
    assert backend.read_text("tenants/alpha/trajectories.jsonl") is None
