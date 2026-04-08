from __future__ import annotations

from pathlib import Path

from app.schemas import (
    NormalizedProcurementOpportunity,
    ProcurementDecisionUpsert,
)
from app.storage.approval_store import ApprovalStore
from app.storage.bookmark_store import BookmarkStore
from app.storage.history_store import HistoryEntry, HistoryStore
from app.storage.meeting_recording_store import MeetingRecordingStore
from app.storage.notification_store import NotificationStore
from app.storage.procurement_store import ProcurementDecisionStore
from app.storage.project_store import ProjectStore
from app.storage.share_store import ShareStore
from app.storage.state_backend import S3StateBackend
from app.storage.tenant_store import TenantStore
from app.storage.user_store import UserRole, UserStore


class _FakeBody:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


class _FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, ContentType: str) -> None:
        _ = ContentType
        self.objects[(Bucket, Key)] = Body

    def get_object(self, *, Bucket: str, Key: str) -> dict:
        data = self.objects.get((Bucket, Key))
        if data is None:
            exc = Exception("NoSuchKey")
            exc.response = {"Error": {"Code": "NoSuchKey"}}
            raise exc
        return {"Body": _FakeBody(data)}

    def head_object(self, *, Bucket: str, Key: str) -> dict:
        if (Bucket, Key) not in self.objects:
            exc = Exception("NotFound")
            exc.response = {"Error": {"Code": "404"}}
            raise exc
        return {}

    def list_objects_v2(self, *, Bucket: str, Prefix: str) -> dict:
        contents = [
            {"Key": key}
            for (bucket, key), _value in self.objects.items()
            if bucket == Bucket and key.startswith(Prefix)
        ]
        return {"Contents": contents}


def _backend() -> tuple[S3StateBackend, _FakeS3Client]:
    client = _FakeS3Client()
    return (
        S3StateBackend(
            bucket="unit-bucket",
            prefix="decisiondoc-ai/state/",
            s3_client=client,
        ),
        client,
    )


def test_tenant_store_persists_to_s3_state_backend():
    backend, client = _backend()
    store = TenantStore(Path("/virtual/data"), backend=backend)

    tenant = store.create_tenant("alpha", "Alpha Team")

    assert tenant.tenant_id == "alpha"
    assert ("unit-bucket", "decisiondoc-ai/state/tenants.json") in client.objects
    reloaded = TenantStore(Path("/virtual/data"), backend=backend).get_tenant("alpha")
    assert reloaded is not None
    assert reloaded.display_name == "Alpha Team"


def test_user_store_persists_to_s3_state_backend():
    backend, client = _backend()
    store = UserStore(Path("/virtual/data/tenants/alpha"), backend=backend)

    user = store.create("alpha", "alice", "Alice", "alice@test.com", "Secure123", UserRole.ADMIN)

    assert user.username == "alice"
    assert ("unit-bucket", "decisiondoc-ai/state/tenants/alpha/users.json") in client.objects
    reloaded = UserStore(Path("/virtual/data/tenants/alpha"), backend=backend).get_by_username("alpha", "alice")
    assert reloaded is not None
    assert reloaded.role == UserRole.ADMIN


def test_project_and_approval_stores_persist_to_s3_state_backend():
    backend, client = _backend()
    project_store = ProjectStore(base_dir="/virtual/data", backend=backend)
    approval_store = ApprovalStore(base_dir="/virtual/data", backend=backend)

    project = project_store.create("alpha", name="S3 Project")
    approval = approval_store.create(
        tenant_id="alpha",
        request_id="req-1",
        bundle_id="bid_decision_kr",
        title="Approval",
        drafter="alice",
        docs=[{"doc_type": "memo", "markdown": "# hi"}],
    )

    assert ("unit-bucket", "decisiondoc-ai/state/tenants/alpha/projects.json") in client.objects
    assert ("unit-bucket", "decisiondoc-ai/state/tenants/alpha/approvals.json") in client.objects
    assert ProjectStore(base_dir="/virtual/data", backend=backend).get(project.project_id, tenant_id="alpha") is not None
    assert ApprovalStore(base_dir="/virtual/data", backend=backend).get(approval.approval_id, tenant_id="alpha") is not None


def test_meeting_recording_store_persists_metadata_and_audio_to_s3_state_backend():
    backend, client = _backend()
    store = MeetingRecordingStore(base_dir="/virtual/data", backend=backend)

    recording = store.create(
        tenant_id="alpha",
        project_id="proj-audio-1",
        filename="meeting.wav",
        content_type="audio/wav",
        raw=b"RIFF....fakewav",
    )

    metadata_key = (
        "unit-bucket",
        f"decisiondoc-ai/state/tenants/alpha/meeting_recordings/proj-audio-1/{recording.recording_id}/metadata.json",
    )
    audio_key = (
        "unit-bucket",
        f"decisiondoc-ai/state/tenants/alpha/meeting_recordings/proj-audio-1/{recording.recording_id}/audio.wav",
    )
    assert metadata_key in client.objects
    assert audio_key in client.objects
    reloaded = store.get(
        tenant_id="alpha",
        project_id="proj-audio-1",
        recording_id=recording.recording_id,
    )
    assert reloaded is not None
    assert reloaded.filename == "meeting.wav"
    assert store.read_audio_bytes(reloaded) == b"RIFF....fakewav"


def test_procurement_store_persists_record_and_snapshot_to_s3_state_backend():
    backend, client = _backend()
    store = ProcurementDecisionStore(base_dir="/virtual/data", backend=backend)

    record = store.upsert(
        ProcurementDecisionUpsert(
            project_id="proj-1",
            tenant_id="alpha",
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b",
                source_id="2026-0001",
                title="공공 AI 구축",
                issuer="행안부",
            ),
        )
    )
    snapshot = store.save_source_snapshot(
        tenant_id="alpha",
        project_id="proj-1",
        source_kind="g2b_import",
        payload={"bid_number": "2026-0001"},
    )

    assert record.project_id == "proj-1"
    assert ("unit-bucket", "decisiondoc-ai/state/tenants/alpha/procurement_decisions.json") in client.objects
    assert (
        "unit-bucket",
        f"decisiondoc-ai/state/tenants/alpha/procurement_snapshots/proj-1/{snapshot.snapshot_id}.json",
    ) in client.objects
    assert store.load_source_snapshot(
        tenant_id="alpha",
        project_id="proj-1",
        snapshot_id=snapshot.snapshot_id,
    ) == {"bid_number": "2026-0001"}


def test_share_store_persists_to_s3_state_backend():
    backend, client = _backend()
    store = ShareStore("alpha", backend=backend)

    link = store.create(
        tenant_id="alpha",
        request_id="req-1",
        title="Shared Doc",
        created_by="user-1",
        bundle_id="proposal_kr",
    )

    assert link.share_id
    assert ("unit-bucket", "decisiondoc-ai/state/tenants/alpha/shares.json") in client.objects
    reloaded = ShareStore("alpha", backend=backend).get(link.share_id)
    assert reloaded is not None
    assert reloaded["bundle_id"] == "proposal_kr"


def test_history_store_persists_to_s3_state_backend():
    backend, client = _backend()
    store = HistoryStore("alpha", base_dir="/virtual/data", backend=backend)

    store.add(
        HistoryEntry(
            entry_id="entry-1",
            tenant_id="alpha",
            user_id="user-1",
            bundle_id="bid_decision_kr",
            bundle_name="입찰 참여 의사결정 패키지",
            title="History Entry",
            request_id="req-1",
            created_at="2026-03-27T00:00:00+00:00",
        )
    )

    assert ("unit-bucket", "decisiondoc-ai/state/tenants/alpha/history.jsonl") in client.objects
    reloaded = HistoryStore("alpha", base_dir="/virtual/data", backend=backend).get_for_user("user-1")
    assert len(reloaded) == 1
    assert reloaded[0]["title"] == "History Entry"


def test_bookmark_store_persists_to_s3_state_backend():
    backend, client = _backend()
    store = BookmarkStore("alpha", base_dir="/virtual/data", backend=backend)

    store.add("user-1", {"bid_number": "R26BK01398367", "title": "공고", "issuer": "기관"})

    assert ("unit-bucket", "decisiondoc-ai/state/tenants/alpha/g2b_bookmarks.json") in client.objects
    reloaded = BookmarkStore("alpha", base_dir="/virtual/data", backend=backend).get_for_user("user-1")
    assert len(reloaded) == 1
    assert reloaded[0]["bid_number"] == "R26BK01398367"


def test_notification_store_persists_to_s3_state_backend():
    backend, client = _backend()
    store = NotificationStore("alpha", data_dir=Path("/virtual/data"), backend=backend)

    notif = store.create(
        tenant_id="alpha",
        recipient_id="user-1",
        event_type="system",
        title="알림",
        body="본문",
        context_type="system",
        context_id="ctx-1",
    )

    assert notif.notification_id
    assert ("unit-bucket", "decisiondoc-ai/state/tenants/alpha/notifications.json") in client.objects
    reloaded = NotificationStore("alpha", data_dir=Path("/virtual/data"), backend=backend).get_for_user("user-1")
    assert len(reloaded) == 1
    assert reloaded[0].title == "알림"
