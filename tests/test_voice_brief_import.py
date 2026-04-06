from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.voice_brief_import_service import (
    VoiceBriefImportBlockedError,
    VoiceBriefImportService,
)
from app.storage.project_store import ProjectStore


def _store(tmp_path: Path) -> ProjectStore:
    return ProjectStore(base_dir=str(tmp_path))


def _create_project(store: ProjectStore, tenant_id: str = "default") -> str:
    project = store.create(
        tenant_id=tenant_id,
        name="Voice Brief 연결 프로젝트",
        description="",
        client="",
        contract_number="",
        fiscal_year=2026,
    )
    return project.project_id


def _build_document_package(
    *,
    recording_id: str = "rec_123",
    summary_revision_id: str = "summary_123",
    review_status: str = "approved",
    sync_status: str = "in_sync",
    markdown: str = "# Summary\n\n회의 요약 본문",
    title: str = "Weekly sync documentation",
    audio_download_url: str = "/assets/asset_123",
) -> dict:
    return {
        "documentTitle": title,
        "generatedAt": "2026-03-25T10:00:00Z",
        "recordingId": recording_id,
        "useCase": "meeting",
        "summarySyncStatus": sync_status,
        "summaryRevisionId": summary_revision_id,
        "summaryReviewStatus": review_status,
        "activeSummaryRevisionId": summary_revision_id,
        "tags": ["meeting", "approved"],
        "metadata": {
            "sourceType": "mobile_recording",
            "language": "ko",
            "durationSec": 1800,
            "speakerCount": 3,
            "transcriptSegmentCount": 24,
            "audioAsset": {
                "assetKey": "asset_123",
                "mimeType": "audio/m4a",
                "bytesStored": 2048,
                "storedAt": "2026-03-25T10:00:00Z",
                "downloadUrl": audio_download_url,
            },
        },
        "sections": [
            {
                "id": "summary",
                "label": "Summary",
                "markdown": markdown,
            }
        ],
        "markdown": markdown,
    }


def _service_with_packages(*packages: dict | httpx.Response) -> VoiceBriefImportService:
    queue = list(packages)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.startswith("/recordings/")
        item = queue.pop(0)
        if isinstance(item, httpx.Response):
            return item
        return httpx.Response(200, json={"document": item})

    return VoiceBriefImportService(
        base_url="http://voice-brief.local",
        transport=httpx.MockTransport(handler),
    )


class TestVoiceBriefImportService:
    def test_import_creates_project_document_with_source_metadata(self, tmp_path):
        store = _store(tmp_path)
        project_id = _create_project(store)
        service = _service_with_packages(_build_document_package())

        result = service.import_into_project(
            project_store=store,
            project_id=project_id,
            tenant_id="default",
            recording_id="rec_123",
        )

        assert result.operation == "created"
        assert result.outcome == "created"
        assert result.document_id == result.document.doc_id
        assert result.source_recording_id == "rec_123"
        assert result.source_summary_revision_id == "summary_123"
        imported = store.get(project_id, tenant_id="default")
        assert imported is not None
        assert len(imported.documents) == 1
        document = imported.documents[0]
        assert document.bundle_id == "voice_brief_import"
        assert document.source_kind == "voice_brief"
        assert document.source_recording_id == "rec_123"
        assert document.source_summary_revision_id == "summary_123"
        assert document.source_review_status == "approved"
        assert document.source_sync_status == "in_sync"
        assert document.source_use_case == "meeting"
        assert document.source_audio_url == "http://voice-brief.local/assets/asset_123"
        assert "voice-brief" in document.tags
        assert "meeting" in document.tags
        assert "회의 요약 본문" in document.doc_snapshot

    def test_import_reuses_same_source_key_and_updates_existing_document(self, tmp_path):
        store = _store(tmp_path)
        project_id = _create_project(store)
        service = _service_with_packages(
            _build_document_package(markdown="# Summary\n\n첫 번째 버전"),
            _build_document_package(markdown="# Summary\n\n수정된 버전"),
        )

        first = service.import_into_project(
            project_store=store,
            project_id=project_id,
            tenant_id="default",
            recording_id="rec_123",
        )
        second = service.import_into_project(
            project_store=store,
            project_id=project_id,
            tenant_id="default",
            recording_id="rec_123",
        )

        project = store.get(project_id, tenant_id="default")
        assert project is not None
        assert first.operation == "created"
        assert second.operation == "updated"
        assert first.document_id == second.document_id
        assert second.source_recording_id == "rec_123"
        assert second.source_summary_revision_id == "summary_123"
        assert len(project.documents) == 1
        assert project.documents[0].doc_id == first.document.doc_id
        assert "수정된 버전" in project.documents[0].doc_snapshot

    def test_import_updates_existing_document_when_same_recording_gets_new_revision(self, tmp_path):
        store = _store(tmp_path)
        project_id = _create_project(store)
        service = _service_with_packages(
            _build_document_package(
                summary_revision_id="summary_123",
                markdown="# Summary\n\n첫 번째 승인 버전",
            ),
            _build_document_package(
                summary_revision_id="summary_124",
                markdown="# Summary\n\n두 번째 승인 버전",
            ),
        )

        first = service.import_into_project(
            project_store=store,
            project_id=project_id,
            tenant_id="default",
            recording_id="rec_123",
        )
        second = service.import_into_project(
            project_store=store,
            project_id=project_id,
            tenant_id="default",
            recording_id="rec_123",
        )

        project = store.get(project_id, tenant_id="default")
        assert project is not None
        assert first.operation == "created"
        assert second.operation == "updated"
        assert first.document_id == second.document_id
        assert second.source_recording_id == "rec_123"
        assert second.source_summary_revision_id == "summary_124"
        assert len(project.documents) == 1
        assert project.documents[0].doc_id == first.document.doc_id
        assert project.documents[0].source_summary_revision_id == "summary_124"
        assert project.documents[0].request_id == "rec_123:summary_124"
        assert "두 번째 승인 버전" in project.documents[0].doc_snapshot

    @pytest.mark.parametrize(
        ("review_status", "sync_status", "expected_code"),
        [
            ("approved", "stale", "stale_summary"),
            ("draft", "in_sync", "unapproved_summary"),
        ],
    )
    def test_import_blocks_non_publishable_voice_brief_summary(
        self,
        tmp_path,
        review_status,
        sync_status,
        expected_code,
    ):
        store = _store(tmp_path)
        project_id = _create_project(store)
        service = _service_with_packages(
            _build_document_package(
                review_status=review_status,
                sync_status=sync_status,
            )
        )

        with pytest.raises(VoiceBriefImportBlockedError) as exc_info:
            service.import_into_project(
                project_store=store,
                project_id=project_id,
                tenant_id="default",
                recording_id="rec_123",
            )

        assert exc_info.value.code == expected_code


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("VOICE_BRIEF_API_BASE_URL", "http://voice-brief.local")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    return TestClient(create_app())


class TestVoiceBriefImportApi:
    def test_import_endpoint_returns_503_when_voice_brief_is_not_configured(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        monkeypatch.setenv("VOICE_BRIEF_API_BASE_URL", "")
        monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
        monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
        client = TestClient(create_app())

        create_project_response = client.post(
            "/projects",
            json={"name": "Voice Brief disabled", "fiscal_year": 2026},
        )
        project_id = create_project_response.json()["project_id"]

        response = client.post(
            f"/projects/{project_id}/imports/voice-brief",
            json={"recording_id": "rec_123"},
        )

        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "voice_brief_not_configured"

    def test_import_endpoint_returns_explicit_metadata_for_first_import(self, client: TestClient):
        create_project_response = client.post(
            "/projects",
            json={"name": "Voice Brief explicit metadata", "fiscal_year": 2026},
        )
        project_id = create_project_response.json()["project_id"]
        client.app.state.voice_brief_import_service = _service_with_packages(
            _build_document_package(
                recording_id="rec_meta_123",
                summary_revision_id="summary_meta_123",
                markdown="# Summary\n\n메타데이터 검증",
            ),
        )

        response = client.post(
            f"/projects/{project_id}/imports/voice-brief",
            json={"recording_id": "rec_meta_123", "revision_id": "summary_meta_123"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["project_id"] == project_id
        assert payload["operation"] == "created"
        assert payload["import_outcome"] == "created"
        assert payload["source_key"] == "rec_meta_123:summary_meta_123"
        assert payload["document_id"] == payload["document"]["doc_id"]
        assert payload["source_recording_id"] == "rec_meta_123"
        assert payload["source_summary_revision_id"] == "summary_meta_123"
        assert payload["voice_brief"]["recording_id"] == "rec_meta_123"
        assert payload["voice_brief"]["summary_revision_id"] == "summary_meta_123"

    def test_import_endpoint_creates_then_updates_same_project_document(self, client: TestClient):
        create_project_response = client.post(
            "/projects",
            json={"name": "Voice Brief API 연동", "fiscal_year": 2026},
        )
        project_id = create_project_response.json()["project_id"]
        client.app.state.voice_brief_import_service = _service_with_packages(
            _build_document_package(markdown="# Summary\n\n처음 가져온 문서"),
            _build_document_package(markdown="# Summary\n\n다시 가져온 문서"),
        )

        first = client.post(
            f"/projects/{project_id}/imports/voice-brief",
            json={"recording_id": "rec_123", "revision_id": "summary_123"},
        )
        second = client.post(
            f"/projects/{project_id}/imports/voice-brief",
            json={"recording_id": "rec_123", "revision_id": "summary_123"},
        )
        project = client.get(f"/projects/{project_id}").json()

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["operation"] == "created"
        assert first.json()["import_outcome"] == "created"
        assert first.json()["source_recording_id"] == "rec_123"
        assert first.json()["source_summary_revision_id"] == "summary_123"
        assert first.json()["document_id"] == first.json()["document"]["doc_id"]
        assert second.json()["operation"] == "updated"
        assert second.json()["import_outcome"] == "updated"
        assert second.json()["source_recording_id"] == "rec_123"
        assert second.json()["source_summary_revision_id"] == "summary_123"
        assert second.json()["document_id"] == first.json()["document_id"]
        assert len(project["documents"]) == 1
        assert project["documents"][0]["source_recording_id"] == "rec_123"
        assert "다시 가져온 문서" in project["documents"][0]["doc_snapshot"]

    def test_import_endpoint_updates_same_document_for_new_revision_of_same_recording(self, client: TestClient):
        create_project_response = client.post(
            "/projects",
            json={"name": "Voice Brief 새 리비전 반영", "fiscal_year": 2026},
        )
        project_id = create_project_response.json()["project_id"]
        client.app.state.voice_brief_import_service = _service_with_packages(
            _build_document_package(
                summary_revision_id="summary_123",
                markdown="# Summary\n\n초기 승인 버전",
            ),
            _build_document_package(
                summary_revision_id="summary_124",
                markdown="# Summary\n\n최신 승인 버전",
            ),
        )

        first = client.post(
            f"/projects/{project_id}/imports/voice-brief",
            json={"recording_id": "rec_123", "revision_id": "summary_123"},
        )
        second = client.post(
            f"/projects/{project_id}/imports/voice-brief",
            json={"recording_id": "rec_123", "revision_id": "summary_124"},
        )
        project = client.get(f"/projects/{project_id}").json()

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["operation"] == "created"
        assert first.json()["import_outcome"] == "created"
        assert first.json()["document_id"] == first.json()["document"]["doc_id"]
        assert second.json()["operation"] == "updated"
        assert second.json()["import_outcome"] == "updated"
        assert second.json()["document_id"] == first.json()["document_id"]
        assert second.json()["source_recording_id"] == "rec_123"
        assert second.json()["source_summary_revision_id"] == "summary_124"
        assert len(project["documents"]) == 1
        assert project["documents"][0]["source_summary_revision_id"] == "summary_124"
        assert project["documents"][0]["request_id"] == "rec_123:summary_124"
        assert "최신 승인 버전" in project["documents"][0]["doc_snapshot"]

    def test_import_endpoint_returns_404_when_voice_brief_recording_is_missing(self, client: TestClient):
        create_project_response = client.post(
            "/projects",
            json={"name": "Voice Brief 404", "fiscal_year": 2026},
        )
        project_id = create_project_response.json()["project_id"]
        client.app.state.voice_brief_import_service = _service_with_packages(
            httpx.Response(404, json={"message": "not found"}),
        )

        response = client.post(
            f"/projects/{project_id}/imports/voice-brief",
            json={"recording_id": "rec_missing", "revision_id": "summary_missing"},
        )

        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "voice_brief_not_found"

    @pytest.mark.parametrize(
        ("review_status", "sync_status", "expected_code"),
        [
            ("approved", "stale", "stale_summary"),
            ("draft", "in_sync", "unapproved_summary"),
        ],
    )
    def test_import_endpoint_returns_409_for_blocked_summary_states(
        self,
        client: TestClient,
        review_status: str,
        sync_status: str,
        expected_code: str,
    ):
        create_project_response = client.post(
            "/projects",
            json={"name": "Voice Brief blocked state", "fiscal_year": 2026},
        )
        project_id = create_project_response.json()["project_id"]
        client.app.state.voice_brief_import_service = _service_with_packages(
            _build_document_package(
                review_status=review_status,
                sync_status=sync_status,
            )
        )

        response = client.post(
            f"/projects/{project_id}/imports/voice-brief",
            json={"recording_id": "rec_123"},
        )

        assert response.status_code == 409
        assert response.json()["detail"]["code"] == expected_code

    def test_import_endpoint_returns_502_when_voice_brief_upstream_is_unavailable(self, client: TestClient):
        create_project_response = client.post(
            "/projects",
            json={"name": "Voice Brief upstream 502", "fiscal_year": 2026},
        )
        project_id = create_project_response.json()["project_id"]
        client.app.state.voice_brief_import_service = _service_with_packages(
            httpx.Response(503, json={"message": "upstream unavailable"}),
        )

        response = client.post(
            f"/projects/{project_id}/imports/voice-brief",
            json={"recording_id": "rec_123"},
        )

        assert response.status_code == 502
        assert response.json()["detail"]["code"] == "voice_brief_upstream_error"

    def test_root_page_contains_voice_brief_import_controls(self, client: TestClient):
        response = client.get("/")

        assert response.status_code == 200
        assert "Voice Brief 요약 가져오기" in response.text
        assert "voice-brief-recording-id" in response.text
        assert "submitVoiceBriefImport" in response.text
