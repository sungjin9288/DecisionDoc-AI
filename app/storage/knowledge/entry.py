"""app/storage/knowledge/entry.py — 단일 지식 문서 항목(KnowledgeEntry)."""
from __future__ import annotations

import time
from typing import Any

from app.storage.knowledge.constants import _LEARNING_MODE_DEFAULT, _QUALITY_TIER_DEFAULT
from app.storage.knowledge.normalizers import (
    _normalize_learning_mode,
    _normalize_list,
    _normalize_quality_tier,
    _normalize_reference_year,
    _normalize_string,
    _normalize_success_state,
)


class KnowledgeEntry:
    """단일 지식 문서 항목."""

    def __init__(
        self,
        doc_id: str,
        filename: str,
        text: str,
        style_profile: dict[str, Any] | None = None,
        created_at: float | None = None,
        tags: list[str] | None = None,
        learning_mode: str = _LEARNING_MODE_DEFAULT,
        quality_tier: str = _QUALITY_TIER_DEFAULT,
        applicable_bundles: list[str] | None = None,
        source_organization: str = "",
        reference_year: int | None = None,
        success_state: str = "draft",
        notes: str = "",
        source_bundle_id: str = "",
        source_request_id: str = "",
        source_doc_type: str = "",
        knowledge_scope: dict[str, Any] | None = None,
    ) -> None:
        self.doc_id = doc_id
        self.filename = filename
        self.text = text
        self.style_profile = style_profile or {}
        self.created_at = created_at or time.time()
        self.tags = tags or []
        self.learning_mode = _normalize_learning_mode(learning_mode)
        self.quality_tier = _normalize_quality_tier(quality_tier)
        self.applicable_bundles = _normalize_list(applicable_bundles)
        self.source_organization = _normalize_string(source_organization)
        self.reference_year = _normalize_reference_year(reference_year)
        self.success_state = _normalize_success_state(success_state)
        self.notes = _normalize_string(notes)
        self.source_bundle_id = _normalize_string(source_bundle_id)
        self.source_request_id = _normalize_string(source_request_id)
        self.source_doc_type = _normalize_string(source_doc_type)
        self.knowledge_scope = dict(knowledge_scope or {})

    def to_meta(self) -> dict[str, Any]:
        """index.json에 저장할 메타데이터 (text 제외)."""
        return {
            "doc_id": self.doc_id,
            "filename": self.filename,
            "text_len": len(self.text),
            "has_style": bool(self.style_profile),
            "created_at": self.created_at,
            "tags": self.tags,
            "learning_mode": self.learning_mode,
            "quality_tier": self.quality_tier,
            "applicable_bundles": self.applicable_bundles,
            "source_organization": self.source_organization,
            "reference_year": self.reference_year,
            "success_state": self.success_state,
            "notes": self.notes,
            "source_bundle_id": self.source_bundle_id,
            "source_request_id": self.source_request_id,
            "source_doc_type": self.source_doc_type,
            "knowledge_scope": self.knowledge_scope,
        }
