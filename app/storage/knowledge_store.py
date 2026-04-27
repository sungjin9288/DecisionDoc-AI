"""app/storage/knowledge_store.py — 프로젝트별 문서 지식 저장소.

업로드된 파일에서 추출한 텍스트·스타일 프로필을 프로젝트 단위로 저장.
이후 문서 생성 시 컨텍스트로 자동 주입된다.

저장 구조 (로컬):
    data/knowledge/{project_id}/
        index.json          — 문서 목록 및 메타데이터
        {doc_id}.txt        — 추출된 원본 텍스트
        {doc_id}_style.json — 스타일 프로필 (선택)

컨텍스트 주입 형식:
    [프로젝트 지식: {project_id}]
    문서1: {filename} ...
    ---
    문서2: {filename} ...
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

_log = logging.getLogger("decisiondoc.knowledge")

MAX_CONTEXT_CHARS = 8_000   # 생성 프롬프트에 주입할 최대 글자 수
MAX_DOCS_PER_PROJECT = 20   # 프로젝트당 최대 보관 문서 수

_LEARNING_MODE_DEFAULT = "reference"
_QUALITY_TIER_DEFAULT = "working"
_LEARNING_MODE_LABELS = {
    "reference": "참고문서",
    "approved_output": "승인본",
    "capability_profile": "역량 프로필",
    "policy": "가이드/기준",
    "template": "우수 템플릿",
}
_QUALITY_TIER_LABELS = {
    "working": "working",
    "silver": "silver",
    "gold": "gold",
}
_LEARNING_MODE_WEIGHTS = {
    "reference": 120,
    "approved_output": 360,
    "capability_profile": 260,
    "policy": 200,
    "template": 220,
}
_QUALITY_TIER_WEIGHTS = {
    "working": 20,
    "silver": 80,
    "gold": 140,
}
_REFERENCE_SUCCESS_WEIGHTS = {
    "draft": 0,
    "reference": 20,
    "approved": 90,
    "awarded": 120,
}
_REFERENCE_SUCCESS_LABELS = {
    "draft": "초안",
    "reference": "참고",
    "approved": "승인",
    "awarded": "수주",
}
_ORGANIZATION_MATCH_SCORE = 80
_REPORT_WORKFLOW_MATCH_SCORE = 110
_REPORT_WORKFLOW_SOURCE_SCORE = 45


def _normalize_string(value: Any) -> str:
    return str(value or "").strip()


def _normalize_list(values: Any) -> list[str]:
    if not values:
        return []
    if isinstance(values, str):
        values = [item.strip() for item in values.split(",")]
    if not isinstance(values, list):
        return []
    normalized: list[str] = []
    for item in values:
        text = _normalize_string(item)
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _normalize_learning_mode(value: Any) -> str:
    normalized = _normalize_string(value).lower()
    return normalized if normalized in _LEARNING_MODE_LABELS else _LEARNING_MODE_DEFAULT


def _normalize_quality_tier(value: Any) -> str:
    normalized = _normalize_string(value).lower()
    return normalized if normalized in _QUALITY_TIER_WEIGHTS else _QUALITY_TIER_DEFAULT


def _normalize_success_state(value: Any) -> str:
    normalized = _normalize_string(value).lower()
    return normalized if normalized in _REFERENCE_SUCCESS_WEIGHTS else "draft"


def _normalize_reference_year(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if 1900 <= parsed <= 2100:
        return parsed
    return None


def _tokenize_reference_text(*values: str) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        text = _normalize_string(value).lower()
        if not text:
            continue
        tokens.update(re.findall(r"[0-9a-zA-Z가-힣]{2,}", text))
    return tokens


def _matches_text_scope(value: Any, expected: str) -> bool:
    actual = _normalize_string(value).lower()
    needle = _normalize_string(expected).lower()
    if not actual or not needle:
        return False
    return actual in needle or needle in actual


def _matches_report_workflow_id(value: Any, report_workflow_id: str) -> bool:
    source = _normalize_string(value)
    workflow_id = _normalize_string(report_workflow_id)
    if not source or not workflow_id:
        return False
    return (
        source == workflow_id
        or source.startswith(f"report_workflow:{workflow_id}:")
        or f":{workflow_id}:" in source
    )


def _is_report_workflow_source(value: Any) -> bool:
    source = _normalize_string(value).lower()
    return source == "report_workflow"


def _reference_recency_score(created_at: Any, *, now: float | None = None) -> int:
    try:
        created = float(created_at)
    except (TypeError, ValueError):
        return 0
    age_days = max(0.0, ((time.time() if now is None else now) - created) / 86_400)
    if age_days <= 30:
        return 32
    if age_days <= 180:
        return 18
    if age_days <= 365:
        return 8
    return 0


def _format_reference_ranking_reason(
    *,
    bundle_type: str | None,
    bundle_match: bool,
    applicable_bundles: list[str],
    success_state: str,
    quality_tier: str,
    overlap: int,
    organization_match: bool = False,
    report_workflow_match: bool = False,
    workflow_source: bool = False,
    recency_score: int = 0,
) -> str:
    reasons: list[str] = []
    if report_workflow_match:
        reasons.append("동일 Report Workflow 산출물")
    elif workflow_source:
        reasons.append("Report Workflow 승인본 출처")
    if organization_match:
        reasons.append("기관/고객 scope 일치")
    if bundle_match and bundle_type:
        reasons.append(f"bundle `{bundle_type}` 일치")
    elif bundle_type and applicable_bundles:
        reasons.append(f"적용 bundle {', '.join(applicable_bundles[:2])}")
    if success_state in ("approved", "awarded"):
        reasons.append(f"{_REFERENCE_SUCCESS_LABELS[success_state]} 결과물")
    if quality_tier in ("gold", "silver"):
        reasons.append(f"{_QUALITY_TIER_LABELS[quality_tier]} 등급")
    if overlap > 0:
        reasons.append(f"핵심어 {overlap}개 겹침")
    if recency_score:
        reasons.append("최근 등록 reference")
    if not reasons:
        reasons.append("기본 참고문서 조건 충족")
    return " · ".join(reasons)


def _build_reference_score_breakdown(
    *,
    learning_mode: str,
    quality_tier: str,
    success_state: str,
    overlap: int,
    bundle_type: str | None,
    bundle_match: bool,
    applicable_bundles: list[str],
    tag_count: int,
    organization_match: bool = False,
    report_workflow_match: bool = False,
    workflow_source: bool = False,
    recency_score: int = 0,
) -> list[dict[str, Any]]:
    breakdown: list[dict[str, Any]] = [
        {
            "label": "학습 분류",
            "detail": _LEARNING_MODE_LABELS[learning_mode],
            "score": _LEARNING_MODE_WEIGHTS[learning_mode],
        },
        {
            "label": "품질 등급",
            "detail": _QUALITY_TIER_LABELS[quality_tier],
            "score": _QUALITY_TIER_WEIGHTS[quality_tier],
        },
    ]
    success_score = _REFERENCE_SUCCESS_WEIGHTS[success_state]
    if success_score:
        breakdown.append(
            {
                "label": "활용 상태",
                "detail": _REFERENCE_SUCCESS_LABELS[success_state],
                "score": success_score,
            }
        )
    if overlap:
        breakdown.append(
            {
                "label": "핵심어 겹침",
                "detail": f"{overlap}개",
                "score": overlap * 28,
            }
        )
    if report_workflow_match:
        breakdown.append(
            {
                "label": "동일 workflow",
                "detail": "Report Workflow source_request_id 일치",
                "score": _REPORT_WORKFLOW_MATCH_SCORE,
            }
        )
    elif workflow_source:
        breakdown.append(
            {
                "label": "workflow 출처",
                "detail": "Report Workflow 승인본",
                "score": _REPORT_WORKFLOW_SOURCE_SCORE,
            }
        )
    if organization_match:
        breakdown.append(
            {
                "label": "기관 scope 일치",
                "detail": "source_organization 일치",
                "score": _ORGANIZATION_MATCH_SCORE,
            }
        )
    if bundle_match and bundle_type:
        breakdown.append(
            {
                "label": "bundle 일치",
                "detail": bundle_type,
                "score": 140,
            }
        )
    elif bundle_type and applicable_bundles:
        breakdown.append(
            {
                "label": "bundle 보정",
                "detail": ", ".join(applicable_bundles[:2]),
                "score": -20,
            }
        )
    tag_bonus = min(tag_count, 4) * 4
    if tag_bonus:
        breakdown.append(
            {
                "label": "태그 밀도",
                "detail": f"{min(tag_count, 4)}개 반영",
                "score": tag_bonus,
            }
        )
    if recency_score:
        breakdown.append(
            {
                "label": "최근성",
                "detail": "최근 등록 reference",
                "score": recency_score,
            }
        )
    return breakdown


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
        }


class KnowledgeStore:
    """프로젝트별 문서 지식을 로컬 파일로 저장/조회."""

    def __init__(self, project_id: str, data_dir: str | None = None) -> None:
        self.project_id = project_id
        base = Path(data_dir or os.getenv("DATA_DIR", "data"))
        self._dir = base / "knowledge" / project_id
        self._index_path = self._dir / "index.json"

    # ── 쓰기 ──────────────────────────────────────────────────────────────────

    def add_document(
        self,
        filename: str,
        text: str,
        style_profile: dict[str, Any] | None = None,
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
    ) -> KnowledgeEntry:
        """문서를 지식 저장소에 추가하고 KnowledgeEntry를 반환."""
        self._ensure_dir()
        doc_id = uuid.uuid4().hex[:12]
        entry = KnowledgeEntry(
            doc_id=doc_id,
            filename=filename,
            text=text,
            style_profile=style_profile,
            tags=tags,
            learning_mode=learning_mode,
            quality_tier=quality_tier,
            applicable_bundles=applicable_bundles,
            source_organization=source_organization,
            reference_year=reference_year,
            success_state=success_state,
            notes=notes,
            source_bundle_id=source_bundle_id,
            source_request_id=source_request_id,
            source_doc_type=source_doc_type,
        )
        self._save_entry(entry)
        _log.info(
            "[Knowledge] Added doc=%s file=%s project=%s",
            doc_id, filename, self.project_id,
        )
        return entry

    def update_style(self, doc_id: str, style_profile: dict[str, Any]) -> bool:
        """기존 문서의 스타일 프로필을 업데이트."""
        style_path = self._dir / f"{doc_id}_style.json"
        if not (self._dir / f"{doc_id}.txt").exists():
            return False
        self._atomic_write_json(style_path, style_profile)
        # index에서 has_style 갱신
        index = self._load_index()
        for item in index:
            if item["doc_id"] == doc_id:
                item["has_style"] = True
                break
        self._atomic_write_json(self._index_path, index)
        return True

    def update_metadata(self, doc_id: str, **fields: Any) -> bool:
        """문서의 학습용 메타데이터를 업데이트."""
        txt_path = self._dir / f"{doc_id}.txt"
        if not txt_path.exists():
            return False
        index = self._load_index()
        updated = False
        for item in index:
            if item.get("doc_id") != doc_id:
                continue
            if "tags" in fields and fields["tags"] is not None:
                item["tags"] = _normalize_list(fields["tags"])
            if "learning_mode" in fields and fields["learning_mode"] is not None:
                item["learning_mode"] = _normalize_learning_mode(fields["learning_mode"])
            if "quality_tier" in fields and fields["quality_tier"] is not None:
                item["quality_tier"] = _normalize_quality_tier(fields["quality_tier"])
            if "applicable_bundles" in fields and fields["applicable_bundles"] is not None:
                item["applicable_bundles"] = _normalize_list(fields["applicable_bundles"])
            if "source_organization" in fields and fields["source_organization"] is not None:
                item["source_organization"] = _normalize_string(fields["source_organization"])
            if "reference_year" in fields:
                item["reference_year"] = _normalize_reference_year(fields["reference_year"])
            if "success_state" in fields and fields["success_state"] is not None:
                item["success_state"] = _normalize_success_state(fields["success_state"])
            if "notes" in fields and fields["notes"] is not None:
                item["notes"] = _normalize_string(fields["notes"])
            if "source_bundle_id" in fields and fields["source_bundle_id"] is not None:
                item["source_bundle_id"] = _normalize_string(fields["source_bundle_id"])
            if "source_request_id" in fields and fields["source_request_id"] is not None:
                item["source_request_id"] = _normalize_string(fields["source_request_id"])
            if "source_doc_type" in fields and fields["source_doc_type"] is not None:
                item["source_doc_type"] = _normalize_string(fields["source_doc_type"])
            updated = True
            break
        if updated:
            self._atomic_write_json(self._index_path, index)
        return updated

    def delete_document(self, doc_id: str) -> bool:
        """문서 삭제. 존재하지 않으면 False."""
        txt_path = self._dir / f"{doc_id}.txt"
        if not txt_path.exists():
            return False
        txt_path.unlink(missing_ok=True)
        (self._dir / f"{doc_id}_style.json").unlink(missing_ok=True)
        index = [i for i in self._load_index() if i["doc_id"] != doc_id]
        self._atomic_write_json(self._index_path, index)
        _log.info("[Knowledge] Deleted doc=%s project=%s", doc_id, self.project_id)
        return True

    # ── 읽기 ──────────────────────────────────────────────────────────────────

    def list_documents(self) -> list[dict[str, Any]]:
        """프로젝트의 모든 문서 메타데이터 목록."""
        return self._load_index()

    def get_document(self, doc_id: str) -> KnowledgeEntry | None:
        """단일 문서 전체 조회. 없으면 None."""
        txt_path = self._dir / f"{doc_id}.txt"
        if not txt_path.exists():
            return None
        text = txt_path.read_text(encoding="utf-8")
        style_path = self._dir / f"{doc_id}_style.json"
        style = json.loads(style_path.read_text()) if style_path.exists() else {}
        meta = next(
            (m for m in self._load_index() if m["doc_id"] == doc_id), {}
        )
        return KnowledgeEntry(
            doc_id=doc_id,
            filename=meta.get("filename", ""),
            text=text,
            style_profile=style,
            created_at=meta.get("created_at"),
            tags=meta.get("tags", []),
            learning_mode=meta.get("learning_mode", _LEARNING_MODE_DEFAULT),
            quality_tier=meta.get("quality_tier", _QUALITY_TIER_DEFAULT),
            applicable_bundles=meta.get("applicable_bundles", []),
            source_organization=meta.get("source_organization", ""),
            reference_year=meta.get("reference_year"),
            success_state=meta.get("success_state", "draft"),
            notes=meta.get("notes", ""),
            source_bundle_id=meta.get("source_bundle_id", ""),
            source_request_id=meta.get("source_request_id", ""),
            source_doc_type=meta.get("source_doc_type", ""),
        )

    def find_promoted_document(
        self,
        *,
        source_request_id: str,
        source_doc_type: str,
        source_bundle_id: str = "",
    ) -> KnowledgeEntry | None:
        """Find an approved_output entry created from the same generation request/doc type."""
        request_id = _normalize_string(source_request_id)
        doc_type = _normalize_string(source_doc_type)
        bundle_id = _normalize_string(source_bundle_id)
        if not request_id or not doc_type:
            return None
        for meta in self._load_index():
            if meta.get("learning_mode") != "approved_output":
                continue
            if _normalize_string(meta.get("source_request_id")) != request_id:
                continue
            if _normalize_string(meta.get("source_doc_type")) != doc_type:
                continue
            meta_bundle_id = _normalize_string(meta.get("source_bundle_id"))
            if bundle_id and meta_bundle_id and meta_bundle_id != bundle_id:
                continue
            doc_id = meta.get("doc_id")
            if not doc_id:
                continue
            entry = self.get_document(str(doc_id))
            if entry is not None:
                return entry
        return None

    def rank_documents_for_context(
        self,
        *,
        bundle_type: str | None = None,
        title: str = "",
        goal: str = "",
        source_organization: str = "",
        report_workflow_id: str = "",
    ) -> list[dict[str, Any]]:
        query_tokens = _tokenize_reference_text(title, goal, bundle_type or "", source_organization)
        ranked: list[dict[str, Any]] = []
        for meta in self._load_index():
            tags = _normalize_list(meta.get("tags"))
            doc_tokens = _tokenize_reference_text(
                meta.get("filename", ""),
                " ".join(tags),
                " ".join(meta.get("applicable_bundles", []) or []),
                meta.get("source_organization", ""),
                meta.get("notes", ""),
            )
            overlap = len(query_tokens & doc_tokens)
            learning_mode = _normalize_learning_mode(meta.get("learning_mode"))
            quality_tier = _normalize_quality_tier(meta.get("quality_tier"))
            success_state = _normalize_success_state(meta.get("success_state"))
            applicable_bundles = _normalize_list(meta.get("applicable_bundles"))
            bundle_match = bool(bundle_type) and bundle_type in applicable_bundles
            organization_match = _matches_text_scope(meta.get("source_organization"), source_organization)
            report_workflow_match = (
                _matches_report_workflow_id(meta.get("source_request_id"), report_workflow_id)
                or _matches_report_workflow_id(meta.get("source_bundle_id"), report_workflow_id)
            )
            workflow_source = _is_report_workflow_source(meta.get("source_bundle_id"))
            recency_score = _reference_recency_score(meta.get("created_at"))
            tag_bonus = min(len(tags), 4) * 4
            score = (
                _LEARNING_MODE_WEIGHTS[learning_mode]
                + _QUALITY_TIER_WEIGHTS[quality_tier]
                + _REFERENCE_SUCCESS_WEIGHTS[success_state]
                + overlap * 28
                + (140 if bundle_match else 0)
                + (_ORGANIZATION_MATCH_SCORE if organization_match else 0)
                + (_REPORT_WORKFLOW_MATCH_SCORE if report_workflow_match else 0)
                + (_REPORT_WORKFLOW_SOURCE_SCORE if workflow_source and not report_workflow_match else 0)
                + recency_score
                + tag_bonus
            )
            if bundle_type and applicable_bundles and not bundle_match:
                score -= 20
            score_breakdown = _build_reference_score_breakdown(
                learning_mode=learning_mode,
                quality_tier=quality_tier,
                success_state=success_state,
                overlap=overlap,
                bundle_type=bundle_type,
                bundle_match=bundle_match,
                applicable_bundles=applicable_bundles,
                tag_count=len(tags),
                organization_match=organization_match,
                report_workflow_match=report_workflow_match,
                workflow_source=workflow_source,
                recency_score=recency_score,
            )
            scope_summary = _format_reference_ranking_reason(
                bundle_type=bundle_type,
                bundle_match=bundle_match,
                applicable_bundles=applicable_bundles,
                success_state=success_state,
                quality_tier=quality_tier,
                overlap=overlap,
                organization_match=organization_match,
                report_workflow_match=report_workflow_match,
                workflow_source=workflow_source,
                recency_score=recency_score,
            )
            ranked.append({
                **meta,
                "tags": tags,
                "learning_mode": learning_mode,
                "quality_tier": quality_tier,
                "success_state": success_state,
                "applicable_bundles": applicable_bundles,
                "score": score,
                "query_overlap": overlap,
                "bundle_match": bundle_match,
                "organization_match": organization_match,
                "report_workflow_match": report_workflow_match,
                "workflow_source": workflow_source,
                "recency_score": recency_score,
                "scope_summary": scope_summary,
                "learning_mode_label": _LEARNING_MODE_LABELS[learning_mode],
                "selection_reason": scope_summary,
                "score_breakdown": score_breakdown,
            })
        ranked.sort(
            key=lambda item: (item.get("score", 0), item.get("created_at", 0)),
            reverse=True,
        )
        return ranked

    def build_context(
        self,
        max_chars: int = MAX_CONTEXT_CHARS,
        *,
        bundle_type: str | None = None,
        title: str = "",
        goal: str = "",
        source_organization: str = "",
        report_workflow_id: str = "",
    ) -> str:
        """생성 프롬프트에 주입할 컨텍스트 문자열 반환.

        최신 문서 순으로 max_chars 이내에서 최대한 포함.
        """
        index = self.rank_documents_for_context(
            bundle_type=bundle_type,
            title=title,
            goal=goal,
            source_organization=source_organization,
            report_workflow_id=report_workflow_id,
        )
        if not index:
            return ""

        parts: list[str] = []
        total = 0
        for meta in index:
            txt_path = self._dir / f"{meta['doc_id']}.txt"
            if not txt_path.exists():
                continue
            text = txt_path.read_text(encoding="utf-8")
            snippet = text[:2_000]  # 문서당 최대 2000자
            header_lines = [f"[참고문서: {meta['filename']}]"]
            header_lines.append(
                f"- 학습 분류: {meta['learning_mode_label']} | 품질 등급: {meta['quality_tier']} | 활용 상태: {meta['success_state']}"
            )
            if meta.get("bundle_match") and bundle_type:
                header_lines.append(f"- 우선 적용 문서: {bundle_type}")
            elif meta.get("applicable_bundles"):
                header_lines.append(f"- 적용 문서: {', '.join(meta['applicable_bundles'])}")
            if meta.get("selection_reason"):
                header_lines.append(f"- 선정 이유: {meta['selection_reason']}")
            if meta.get("source_organization") or meta.get("reference_year"):
                org_bits = [meta.get("source_organization", "")]
                if meta.get("reference_year"):
                    org_bits.append(str(meta["reference_year"]))
                header_lines.append(f"- 출처: {' / '.join(bit for bit in org_bits if bit)}")
            if meta.get("notes"):
                header_lines.append(f"- 활용 메모: {meta['notes']}")
            block = "\n".join(header_lines) + f"\n{snippet}"
            if total + len(block) > max_chars:
                remaining = max_chars - total
                if remaining > 200:
                    parts.append(block[:remaining] + "\n...(생략)")
                break
            parts.append(block)
            total += len(block)

        if not parts:
            return ""
        return (
            f"[프로젝트 지식 학습 컨텍스트: {self.project_id}]\n"
            + "\n\n---\n\n".join(parts)
        )

    def build_style_context(self) -> str:
        """누적 스타일 프로필을 합산해 프롬프트용 문자열 반환."""
        index = self._load_index()
        styles: list[dict[str, Any]] = []
        for meta in index:
            if not meta.get("has_style"):
                continue
            style_path = self._dir / f"{meta['doc_id']}_style.json"
            if style_path.exists():
                styles.append(json.loads(style_path.read_text()))

        if not styles:
            return ""

        # 가장 최신 스타일을 우선 적용, 공통 패턴 수집
        latest = styles[-1]
        formality = latest.get("formality", "")
        density = latest.get("density", "")
        endings: list[str] = []
        for s in styles:
            endings.extend(s.get("sentence_endings", []))
        # 빈도 기준 상위 3개
        from collections import Counter
        top_endings = [e for e, _ in Counter(endings).most_common(3)]

        lines = ["[스타일 가이드 (학습된 문서 기반)]"]
        if formality:
            lines.append(f"- 문체: {formality}")
        if density:
            lines.append(f"- 밀도: {density}")
        if top_endings:
            lines.append(f"- 자주 쓰는 문장 종결: {', '.join(top_endings)}")
        if latest.get("summary"):
            lines.append(f"- 스타일 요약: {latest['summary']}")

        return "\n".join(lines)

    # ── 내부 헬퍼 ─────────────────────────────────────────────────────────────

    def _ensure_dir(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)

    def _load_index(self) -> list[dict[str, Any]]:
        if not self._index_path.exists():
            return []
        try:
            return json.loads(self._index_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []

    def _save_entry(self, entry: KnowledgeEntry) -> None:
        # 최대 문서 수 초과 시 가장 오래된 것 삭제
        index = self._load_index()
        if len(index) >= MAX_DOCS_PER_PROJECT:
            oldest = sorted(index, key=lambda x: x.get("created_at", 0))[0]
            self.delete_document(oldest["doc_id"])
            index = self._load_index()

        # 텍스트 저장
        self._atomic_write(self._dir / f"{entry.doc_id}.txt", entry.text)

        # 스타일 저장 (있을 때만)
        if entry.style_profile:
            self._atomic_write_json(
                self._dir / f"{entry.doc_id}_style.json", entry.style_profile
            )

        # 인덱스 갱신
        index.append(entry.to_meta())
        self._atomic_write_json(self._index_path, index)

    def _atomic_write(self, path: Path, text: str) -> None:
        import os as _os
        tmp = path.with_name(f"{path.name}.tmp.{uuid.uuid4().hex[:8]}")
        tmp.write_text(text, encoding="utf-8")
        tmp.flush() if hasattr(tmp, "flush") else None
        _os.replace(tmp, path)

    def _atomic_write_json(self, path: Path, data: Any) -> None:
        self._atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2))
