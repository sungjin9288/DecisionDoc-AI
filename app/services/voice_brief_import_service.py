"""Voice Brief document-package pull import for project documents."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import httpx

from app.storage.project_store import ProjectDocument, ProjectStore


VOICE_BRIEF_IMPORT_BUNDLE_ID = "voice_brief_import"
VOICE_BRIEF_IMPORT_DOC_TYPE = "voice_brief_summary"


class VoiceBriefImportError(Exception):
    """Base import error for Voice Brief integration."""


class VoiceBriefImportBlockedError(VoiceBriefImportError):
    """Raised when the source document should not be imported."""

    def __init__(
        self,
        code: str,
        message: str,
    ) -> None:
        super().__init__(message)
        self.code = code


class VoiceBriefRemoteError(VoiceBriefImportError):
    """Raised when the upstream Voice Brief API cannot be consumed."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_body: str = "",
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


@dataclass
class VoiceBriefImportResult:
    operation: str
    source_key: str
    document: ProjectDocument
    voice_brief_document: dict[str, Any]


class VoiceBriefImportService:
    """Fetch an approved Voice Brief document package and persist it into a project."""

    def __init__(
        self,
        *,
        base_url: str,
        bearer_token: str | None = None,
        timeout_seconds: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        resolved_base_url = base_url.strip().rstrip("/")
        if not resolved_base_url:
            raise ValueError("Voice Brief base_url is required.")

        self._base_url = resolved_base_url
        self._bearer_token = bearer_token.strip() if bearer_token else None
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    def import_into_project(
        self,
        *,
        project_store: ProjectStore,
        project_id: str,
        tenant_id: str,
        recording_id: str,
        revision_id: str | None = None,
    ) -> VoiceBriefImportResult:
        voice_brief_document = self.get_document_package(
            recording_id=recording_id,
            revision_id=revision_id,
        )
        summary_revision_id = str(voice_brief_document.get("summaryRevisionId") or "").strip()

        if not summary_revision_id:
            raise VoiceBriefImportBlockedError(
                "missing_summary_revision",
                "Voice Brief document package is missing summaryRevisionId.",
            )

        if voice_brief_document.get("summarySyncStatus") == "stale":
            raise VoiceBriefImportBlockedError(
                "stale_summary",
                "Voice Brief summary is stale. Regenerate the summary before importing.",
            )

        if voice_brief_document.get("summaryReviewStatus") != "approved":
            raise VoiceBriefImportBlockedError(
                "unapproved_summary",
                "Voice Brief summary is not approved. Review and approve it before importing.",
            )

        source_recording_id = str(voice_brief_document.get("recordingId") or recording_id).strip()
        source_key = f"{source_recording_id}:{summary_revision_id}"
        docs = [
            {
                "doc_type": VOICE_BRIEF_IMPORT_DOC_TYPE,
                "markdown": str(voice_brief_document.get("markdown") or ""),
            }
        ]
        tags = self._build_tags(voice_brief_document)
        document, operation = project_store.upsert_voice_brief_document(
            project_id=project_id,
            tenant_id=tenant_id,
            request_id=source_key,
            title=str(
                voice_brief_document.get("documentTitle")
                or f"Voice Brief import {source_recording_id}"
            ),
            docs=docs,
            tags=tags,
            generated_at=str(voice_brief_document.get("generatedAt") or ""),
            source_recording_id=source_recording_id,
            source_summary_revision_id=summary_revision_id,
            source_review_status=self._optional_str(
                voice_brief_document.get("summaryReviewStatus")
            ),
            source_sync_status=self._optional_str(
                voice_brief_document.get("summarySyncStatus")
            ),
            source_use_case=self._optional_str(voice_brief_document.get("useCase")),
            source_audio_url=self._resolve_audio_url(voice_brief_document),
        )

        return VoiceBriefImportResult(
            operation=operation,
            source_key=source_key,
            document=document,
            voice_brief_document=voice_brief_document,
        )

    def get_document_package(
        self,
        *,
        recording_id: str,
        revision_id: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, str] = {}
        if revision_id:
            params["revisionId"] = revision_id

        try:
            with self._build_client() as client:
                response = client.get(
                    f"/recordings/{recording_id}/document-package",
                    params=params or None,
                )
        except httpx.RequestError as exc:
            raise VoiceBriefRemoteError(
                f"Voice Brief request failed: {exc}",
            ) from exc

        if response.status_code == 404:
            raise VoiceBriefRemoteError(
                "Voice Brief recording or summary revision was not found.",
                status_code=404,
                response_body=response.text,
            )

        if response.status_code >= 400:
            raise VoiceBriefRemoteError(
                "Voice Brief request failed.",
                status_code=response.status_code,
                response_body=response.text,
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise VoiceBriefRemoteError(
                "Voice Brief returned invalid JSON.",
                status_code=response.status_code,
                response_body=response.text,
            ) from exc

        document = payload.get("document")
        if not isinstance(document, dict):
            raise VoiceBriefRemoteError(
                "Voice Brief response is missing the document payload.",
                status_code=response.status_code,
                response_body=response.text,
            )
        return document

    def _build_client(self) -> httpx.Client:
        headers: dict[str, str] = {}
        if self._bearer_token:
            headers["authorization"] = f"Bearer {self._bearer_token}"

        return httpx.Client(
            base_url=self._base_url,
            headers=headers,
            timeout=self._timeout_seconds,
            transport=self._transport,
        )

    def _build_tags(self, voice_brief_document: dict[str, Any]) -> list[str]:
        tags: list[str] = ["voice-brief"]
        use_case = self._optional_str(voice_brief_document.get("useCase"))
        if use_case:
            tags.append(use_case)

        raw_tags = voice_brief_document.get("tags")
        if isinstance(raw_tags, list):
            for item in raw_tags:
                value = self._optional_str(item)
                if value:
                    tags.append(value)

        deduped: list[str] = []
        seen: set[str] = set()
        for item in tags:
            normalized = item.strip()
            if not normalized:
                continue
            key = normalized.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(normalized)
        return deduped

    def _resolve_audio_url(self, voice_brief_document: dict[str, Any]) -> str | None:
        metadata = voice_brief_document.get("metadata")
        if not isinstance(metadata, dict):
            return None

        audio_asset = metadata.get("audioAsset")
        if not isinstance(audio_asset, dict):
            return None

        download_url = self._optional_str(audio_asset.get("downloadUrl"))
        if not download_url:
            return None

        return urljoin(f"{self._base_url}/", download_url)

    @staticmethod
    def _optional_str(value: Any) -> str | None:
        if value is None:
            return None
        resolved = str(value).strip()
        return resolved or None
