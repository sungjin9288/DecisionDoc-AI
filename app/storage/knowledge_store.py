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
        )

    def rank_documents_for_context(
        self,
        *,
        bundle_type: str | None = None,
        title: str = "",
        goal: str = "",
    ) -> list[dict[str, Any]]:
        query_tokens = _tokenize_reference_text(title, goal, bundle_type or "")
        ranked: list[dict[str, Any]] = []
        for meta in self._load_index():
            doc_tokens = _tokenize_reference_text(
                meta.get("filename", ""),
                " ".join(meta.get("tags", []) or []),
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
            score = (
                _LEARNING_MODE_WEIGHTS[learning_mode]
                + _QUALITY_TIER_WEIGHTS[quality_tier]
                + _REFERENCE_SUCCESS_WEIGHTS[success_state]
                + overlap * 28
                + (140 if bundle_match else 0)
                + min(len(meta.get("tags", []) or []), 4) * 4
            )
            if bundle_type and applicable_bundles and not bundle_match:
                score -= 20
            ranked.append({
                **meta,
                "learning_mode": learning_mode,
                "quality_tier": quality_tier,
                "success_state": success_state,
                "applicable_bundles": applicable_bundles,
                "score": score,
                "query_overlap": overlap,
                "bundle_match": bundle_match,
                "learning_mode_label": _LEARNING_MODE_LABELS[learning_mode],
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
    ) -> str:
        """생성 프롬프트에 주입할 컨텍스트 문자열 반환.

        최신 문서 순으로 max_chars 이내에서 최대한 포함.
        """
        index = self.rank_documents_for_context(
            bundle_type=bundle_type,
            title=title,
            goal=goal,
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
