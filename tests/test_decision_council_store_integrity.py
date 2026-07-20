from __future__ import annotations

import ast
import hashlib
import json
import threading
import time
from contextlib import nullcontext
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

import pytest
from fastapi.testclient import TestClient

from app.schemas import (
    DecisionCouncilSessionResponse,
    NormalizedProcurementOpportunity,
    ProcurementDecisionUpsert,
    ProcurementRecommendation,
)
from app.storage.decision_council_store import (
    DecisionCouncilStore,
    DecisionCouncilStoreError,
)
from app.storage.state_backend import LocalStateBackend, S3StateBackend


class _SlowLocalBackend(LocalStateBackend):
    def read_text(self, relative_path: str) -> str | None:
        raw = super().read_text(relative_path)
        time.sleep(0.005)
        return raw


class _RecordingLocalBackend(LocalStateBackend):
    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.writes: list[str] = []

    def write_text(
        self,
        relative_path: str,
        text: str,
        *,
        content_type: str = "application/json; charset=utf-8",
    ) -> None:
        self.writes.append(relative_path)
        super().write_text(relative_path, text, content_type=content_type)

    def write_text_if_absent(
        self,
        relative_path: str,
        text: str,
        *,
        content_type: str = "application/json; charset=utf-8",
    ) -> bool:
        self.writes.append(relative_path)
        return super().write_text_if_absent(
            relative_path,
            text,
            content_type=content_type,
        )

    def replace_text_if_equal(
        self,
        relative_path: str,
        *,
        expected: str,
        replacement: str,
        content_type: str = "application/json; charset=utf-8",
    ) -> bool:
        self.writes.append(relative_path)
        return super().replace_text_if_equal(
            relative_path,
            expected=expected,
            replacement=replacement,
            content_type=content_type,
        )


class _ConflictingLocalBackend(LocalStateBackend):
    def __init__(self, root: Path, *, conflict_suffix: str) -> None:
        super().__init__(root)
        self.conflict_suffix = conflict_suffix
        self.attempts = 0

    def write_text_if_absent(
        self,
        relative_path: str,
        text: str,
        *,
        content_type: str = "application/json; charset=utf-8",
    ) -> bool:
        if relative_path.endswith(self.conflict_suffix):
            self.attempts += 1
            return False
        return super().write_text_if_absent(
            relative_path,
            text,
            content_type=content_type,
        )

    def replace_text_if_equal(
        self,
        relative_path: str,
        *,
        expected: str,
        replacement: str,
        content_type: str = "application/json; charset=utf-8",
    ) -> bool:
        if relative_path.endswith(self.conflict_suffix):
            self.attempts += 1
            return False
        return super().replace_text_if_equal(
            relative_path,
            expected=expected,
            replacement=replacement,
            content_type=content_type,
        )


class _Body:
    def __init__(self, raw: bytes) -> None:
        self._raw = raw

    def read(self) -> bytes:
        return self._raw


class _MemoryS3Client:
    def __init__(self, *, read_delay: float = 0.0) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.read_delay = read_delay
        self._lock = threading.Lock()
        self._fail_after_key_fragment: str | None = None
        self._after_failed_write: Callable[[], None] | None = None

    @staticmethod
    def _etag(raw: bytes) -> str:
        return f'"{hashlib.sha256(raw).hexdigest()}"'

    @staticmethod
    def _error(code: str) -> Exception:
        error = RuntimeError(code)
        error.response = {"Error": {"Code": code}}
        return error

    def fail_after_next_conditional_write(
        self,
        *,
        key_fragment: str,
        after_write: Callable[[], None] | None = None,
    ) -> None:
        self._fail_after_key_fragment = key_fragment
        self._after_failed_write = after_write

    def put_object(
        self,
        *,
        Bucket: str,
        Key: str,
        Body: bytes,
        ContentType: str,
        IfNoneMatch: str | None = None,
        IfMatch: str | None = None,
    ) -> None:
        _ = ContentType
        with self._lock:
            current = self.objects.get((Bucket, Key))
            if IfNoneMatch == "*" and current is not None:
                raise self._error("PreconditionFailed")
            if IfMatch is not None and (
                current is None or self._etag(current) != IfMatch
            ):
                raise self._error("PreconditionFailed")
            self.objects[(Bucket, Key)] = Body
            fail_after_write = (
                (IfNoneMatch is not None or IfMatch is not None)
                and self._fail_after_key_fragment is not None
                and self._fail_after_key_fragment in Key
            )
            if fail_after_write:
                self._fail_after_key_fragment = None
                after_write = self._after_failed_write
                self._after_failed_write = None
            else:
                after_write = None

        if not fail_after_write:
            return
        if after_write is not None:
            after_write()
        raise self._error("InternalError")

    def get_object(self, *, Bucket: str, Key: str) -> dict:
        time.sleep(self.read_delay)
        with self._lock:
            raw = self.objects.get((Bucket, Key))
        if raw is None:
            raise self._error("NoSuchKey")
        return {"Body": _Body(raw), "ETag": self._etag(raw)}


def _s3_backend(
    client: _MemoryS3Client | None = None,
) -> tuple[S3StateBackend, _MemoryS3Client]:
    selected_client = client or _MemoryS3Client()
    return (
        S3StateBackend(
            bucket="unit-bucket",
            prefix="decisiondoc-ai/state/",
            s3_client=selected_client,
        ),
        selected_client,
    )


def _path(root: Path, tenant_id: str = "alpha") -> Path:
    return root / f"tenants/{tenant_id}/decision_council_sessions.json"


def _s3_key(tenant_id: str = "alpha") -> tuple[str, str]:
    return (
        "unit-bucket",
        f"decisiondoc-ai/state/tenants/{tenant_id}/decision_council_sessions.json",
    )


def _session(
    project_id: str = "proj-1",
    *,
    tenant_id: str = "alpha",
    session_id: str | None = None,
) -> DecisionCouncilSessionResponse:
    return DecisionCouncilSessionResponse.model_validate(
        {
            "session_id": session_id or f"session-{project_id}",
            "session_key": DecisionCouncilStore.build_session_key(
                project_id=project_id,
                use_case="public_procurement",
                target_bundle_type="bid_decision_kr",
            ),
            "session_revision": 1,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "use_case": "public_procurement",
            "target_bundle_type": "bid_decision_kr",
            "goal": f"Review {project_id}",
            "source_procurement_decision_id": f"decision-{project_id}",
            "created_at": "2026-07-17T00:00:00+00:00",
            "updated_at": "2026-07-17T00:00:00+00:00",
            "role_opinions": [
                {
                    "role": "Requirement Analyst",
                    "stance": "support",
                    "summary": "Requirements are clear.",
                }
            ],
            "consensus": {
                "alignment": "aligned",
                "recommended_direction": "proceed",
                "summary": "Proceed with the documented evidence.",
            },
            "handoff": {
                "target_bundle_type": "bid_decision_kr",
                "recommended_direction": "proceed",
                "drafting_brief": "Keep the decision tied to verified evidence.",
                "source_procurement_decision_id": f"decision-{project_id}",
            },
        }
    )


def _stored(session: DecisionCouncilSessionResponse) -> dict:
    return DecisionCouncilStore._to_dict(session)


def test_missing_decision_council_reads_do_not_create_local_or_s3_state(
    tmp_path: Path,
) -> None:
    local = DecisionCouncilStore(base_dir=str(tmp_path))
    backend, client = _s3_backend()
    remote = DecisionCouncilStore(base_dir="/virtual/data", backend=backend)

    assert local.get_latest(tenant_id="alpha", project_id="proj-missing") is None
    assert remote.get_latest(tenant_id="alpha", project_id="proj-missing") is None
    assert not (tmp_path / "tenants").exists()
    assert client.objects == {}


def test_local_decision_council_write_uses_the_selected_backend(tmp_path: Path) -> None:
    backend = _RecordingLocalBackend(tmp_path)
    store = DecisionCouncilStore(base_dir=str(tmp_path), backend=backend)

    store.upsert_latest(_session(), tenant_id="alpha")

    assert backend.writes == ["tenants/alpha/decision_council_sessions.json"]


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"{not-json",
        b"{}",
        b'[{"tenant_id":"alpha","tenant_id":"alpha"}]',
        b"\xff\xfe",
    ],
)
def test_invalid_decision_council_document_stops_reads_and_writes(
    tmp_path: Path,
    raw: bytes,
) -> None:
    path = _path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_bytes(raw)
    store = DecisionCouncilStore(base_dir=str(tmp_path))

    with pytest.raises(DecisionCouncilStoreError):
        store.get_latest(tenant_id="alpha", project_id="proj-1")
    with pytest.raises(DecisionCouncilStoreError):
        store.upsert_latest(_session(), tenant_id="alpha")

    assert path.read_bytes() == raw


@pytest.mark.parametrize(
    "records",
    [
        [{**_stored(_session()), "session_key": "forged:key"}],
        [
            _stored(_session()),
            _stored(_session(session_id="session-duplicate")),
        ],
        [
            _stored(_session("proj-1", session_id="session-shared")),
            _stored(_session("proj-2", session_id="session-shared")),
        ],
    ],
)
def test_owned_decision_council_identity_drift_fails_closed(
    tmp_path: Path,
    records: list[dict],
) -> None:
    path = _path(tmp_path)
    path.parent.mkdir(parents=True)
    original = json.dumps(records, ensure_ascii=False).encode()
    path.write_bytes(original)
    store = DecisionCouncilStore(base_dir=str(tmp_path))

    with pytest.raises(DecisionCouncilStoreError):
        store.get_latest(tenant_id="alpha", project_id="proj-1")
    with pytest.raises(DecisionCouncilStoreError):
        store.upsert_latest(_session("proj-new"), tenant_id="alpha")

    assert path.read_bytes() == original


def test_fake_s3_decision_council_corruption_is_preserved() -> None:
    backend, client = _s3_backend()
    client.objects[_s3_key()] = b"{not-json"
    store = DecisionCouncilStore(base_dir="/virtual/data", backend=backend)

    with pytest.raises(DecisionCouncilStoreError):
        store.upsert_latest(_session(), tenant_id="alpha")

    assert client.objects[_s3_key()] == b"{not-json"


def test_independent_local_and_s3_stores_preserve_concurrent_sessions(
    tmp_path: Path,
) -> None:
    local_stores = [
        DecisionCouncilStore(
            base_dir=str(tmp_path),
            backend=_SlowLocalBackend(tmp_path),
        )
        for _ in range(20)
    ]
    client = _MemoryS3Client(read_delay=0.005)
    s3_stores = [
        DecisionCouncilStore(
            base_dir="/virtual/data",
            backend=_s3_backend(client)[0],
        )
        for _ in range(20)
    ]
    for store in [*local_stores, *s3_stores]:
        store._lock = lambda _tenant_id: nullcontext()

    def save(store: DecisionCouncilStore, index: int) -> None:
        store.upsert_latest(_session(f"proj-{index}"), tenant_id="alpha")

    with ThreadPoolExecutor(max_workers=20) as executor:
        list(executor.map(save, local_stores, range(20)))
    with ThreadPoolExecutor(max_workers=20) as executor:
        list(executor.map(save, s3_stores, range(20)))

    local_records = json.loads(_path(tmp_path).read_text(encoding="utf-8"))
    s3_records = json.loads(client.objects[_s3_key()])
    expected = {f"proj-{index}" for index in range(20)}
    assert {record["project_id"] for record in local_records} == expected
    assert {record["project_id"] for record in s3_records} == expected


def test_concurrent_same_council_session_keeps_identity_and_every_revision() -> None:
    client = _MemoryS3Client(read_delay=0.002)
    stores = [
        DecisionCouncilStore(
            base_dir=f"/virtual/data-{index}",
            backend=_s3_backend(client)[0],
        )
        for index in range(20)
    ]
    for store in stores:
        store._lock = lambda _tenant_id: nullcontext()

    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(
            executor.map(
                lambda item: item[1].upsert_latest(
                    _session("proj-shared").model_copy(
                        update={"goal": f"Review revision {item[0]}"}
                    ),
                    tenant_id="alpha",
                ),
                enumerate(stores),
            )
        )

    latest = stores[0].get_latest(tenant_id="alpha", project_id="proj-shared")
    assert latest is not None
    assert latest.session_id == "session-proj-shared"
    assert latest.session_revision == 20
    assert sum(operation == "created" for _, operation in results) == 1
    assert sum(operation == "updated" for _, operation in results) == 19


def test_council_create_reconciles_commit_then_successor_update() -> None:
    client = _MemoryS3Client()
    primary = DecisionCouncilStore(
        base_dir="/virtual/primary",
        backend=_s3_backend(client)[0],
    )
    successor = DecisionCouncilStore(
        base_dir="/virtual/successor",
        backend=_s3_backend(client)[0],
    )
    primary._lock = lambda _tenant_id: nullcontext()
    successor._lock = lambda _tenant_id: nullcontext()

    client.fail_after_next_conditional_write(
        key_fragment="decision_council_sessions.json",
        after_write=lambda: successor.upsert_latest(
            _session("proj-shared").model_copy(update={"goal": "Successor review"}),
            tenant_id="alpha",
        ),
    )
    created, operation = primary.upsert_latest(
        _session("proj-shared").model_copy(update={"goal": "Initial review"}),
        tenant_id="alpha",
    )

    latest = primary.get_latest(tenant_id="alpha", project_id="proj-shared")
    assert operation == "created"
    assert created.goal == "Initial review"
    assert latest is not None
    assert latest.goal == "Successor review"
    assert latest.session_revision == 2


def test_council_mutations_stop_after_bounded_conflicts(
    tmp_path: Path,
) -> None:
    backend = _ConflictingLocalBackend(
        tmp_path,
        conflict_suffix="decision_council_sessions.json",
    )
    store = DecisionCouncilStore(base_dir=str(tmp_path), backend=backend)
    store._lock = lambda _tenant_id: nullcontext()

    with pytest.raises(
        DecisionCouncilStoreError,
        match="changed too many times",
    ):
        store.upsert_latest(_session(), tenant_id="alpha")

    assert backend.attempts == 32


def test_council_mutation_history_is_private_and_bounded(
    tmp_path: Path,
) -> None:
    store = DecisionCouncilStore(base_dir=str(tmp_path))
    store.upsert_latest(_session(), tenant_id="alpha")
    for index in range(70):
        store.upsert_latest(
            _session().model_copy(update={"goal": f"Review {index}"}),
            tenant_id="alpha",
        )

    public = store.get_latest(tenant_id="alpha", project_id="proj-1")
    persisted = json.loads(_path(tmp_path).read_text(encoding="utf-8"))[0]
    assert public is not None
    assert "_mutation_ids" not in public.model_dump(mode="json")
    assert len(persisted["_mutation_ids"]) == 64


def test_invalid_council_mutation_history_fails_closed(
    tmp_path: Path,
) -> None:
    store = DecisionCouncilStore(base_dir=str(tmp_path))
    store.upsert_latest(_session(), tenant_id="alpha")
    path = _path(tmp_path)
    records = json.loads(path.read_text(encoding="utf-8"))
    records[0]["_mutation_ids"] = [f"mutation-{index}" for index in range(65)]
    path.write_text(json.dumps(records), encoding="utf-8")
    original = path.read_bytes()

    with pytest.raises(
        DecisionCouncilStoreError,
        match="mutation history",
    ):
        store.get_latest(tenant_id="alpha", project_id="proj-1")
    with pytest.raises(
        DecisionCouncilStoreError,
        match="mutation history",
    ):
        store.upsert_latest(_session("proj-2"), tenant_id="alpha")

    assert path.read_bytes() == original


def test_app_constructs_decision_council_store_with_selected_state_backend() -> None:
    tree = ast.parse(Path("app/main.py").read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "DecisionCouncilStore"
    ]

    assert len(calls) == 1
    keywords = {keyword.arg for keyword in calls[0].keywords}
    assert {"base_dir", "backend"} <= keywords


def test_decision_council_api_reports_corrupt_state_without_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(tmp_path, monkeypatch)
    project = client.post(
        "/projects",
        json={"name": "Council integrity project", "fiscal_year": 2026},
        headers={"X-DecisionDoc-Api-Key": "test-key"},
    )
    assert project.status_code == 200
    project_id = project.json()["project_id"]
    client.app.state.procurement_store.upsert(
        ProcurementDecisionUpsert(
            project_id=project_id,
            tenant_id="system",
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b",
                source_id="G2B-INTEGRITY-1",
                title="Council integrity opportunity",
            ),
            recommendation=ProcurementRecommendation(
                value="GO",
                summary="Ready for council review.",
            ),
        )
    )
    path = _path(tmp_path, "system")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"{not-json")
    headers = {"X-DecisionDoc-Api-Key": "test-key"}

    responses = (
        client.get(f"/projects/{project_id}/decision-council", headers=headers),
        client.post(
            f"/projects/{project_id}/decision-council/run",
            json={"goal": "Keep corrupted state fail closed."},
            headers=headers,
        ),
    )

    assert all(response.status_code == 500 for response in responses)
    assert all(response.json()["code"] == "INTERNAL_ERROR" for response in responses)
    assert path.read_bytes() == b"{not-json"


def _client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_STORAGE", "local")
    monkeypatch.setenv("DECISIONDOC_STATE_STORAGE", "local")
    monkeypatch.setenv("DECISIONDOC_API_KEY", "test-key")
    monkeypatch.setenv("DECISIONDOC_PROCUREMENT_COPILOT_ENABLED", "1")
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    from app.main import create_app

    return TestClient(create_app(), raise_server_exceptions=False)
