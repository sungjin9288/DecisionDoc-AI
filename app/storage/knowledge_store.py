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
import time
import uuid
from pathlib import Path
from typing import Any

_log = logging.getLogger("decisiondoc.knowledge")

MAX_CONTEXT_CHARS = 8_000   # 생성 프롬프트에 주입할 최대 글자 수
MAX_DOCS_PER_PROJECT = 20   # 프로젝트당 최대 보관 문서 수


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
    ) -> None:
        self.doc_id = doc_id
        self.filename = filename
        self.text = text
        self.style_profile = style_profile or {}
        self.created_at = created_at or time.time()
        self.tags = tags or []

    def to_meta(self) -> dict[str, Any]:
        """index.json에 저장할 메타데이터 (text 제외)."""
        return {
            "doc_id": self.doc_id,
            "filename": self.filename,
            "text_len": len(self.text),
            "has_style": bool(self.style_profile),
            "created_at": self.created_at,
            "tags": self.tags,
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
        )

    def build_context(self, max_chars: int = MAX_CONTEXT_CHARS) -> str:
        """생성 프롬프트에 주입할 컨텍스트 문자열 반환.

        최신 문서 순으로 max_chars 이내에서 최대한 포함.
        """
        index = sorted(
            self._load_index(), key=lambda x: x.get("created_at", 0), reverse=True
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
            block = f"[참고문서: {meta['filename']}]\n{snippet}"
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
            f"[프로젝트 지식: {self.project_id}]\n"
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
