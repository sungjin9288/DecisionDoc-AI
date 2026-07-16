"""Tenant-scoped generation history for each user."""

from __future__ import annotations

import json
import math
import os
import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from app.storage.state_backend import StateBackend, get_state_backend
from app.tenant import require_tenant_id


MAX_HISTORY_PER_USER = 50

_history_locks: dict[Path, threading.RLock] = {}
_history_locks_guard = threading.Lock()


class HistoryStoreError(ValueError):
    """Raised when persisted generation history cannot be trusted."""


def _lock_for_path(path: Path) -> threading.RLock:
    with _history_locks_guard:
        return _history_locks.setdefault(path.resolve(), threading.RLock())


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise HistoryStoreError(f"Duplicate key in history state: {key!r}")
        result[key] = value
    return result


@dataclass
class HistoryEntry:
    entry_id: str
    tenant_id: str
    user_id: str
    bundle_id: str
    bundle_name: str
    title: str
    request_id: str
    created_at: str
    bundle_type: str = ""
    project_id: str = ""
    score: float = 0.0
    tags: list | None = None
    applied_references: list[dict] | None = None
    docs: list[dict] | None = None
    visual_assets: list[dict] | None = None
    knowledge_promoted: bool = False
    knowledge_project_id: str = ""
    knowledge_promoted_at: str = ""
    knowledge_document_count: int = 0
    knowledge_quality_tier: str = ""
    knowledge_success_state: str = ""
    knowledge_documents: list[dict] | None = None


class HistoryStore:
    """Thread-safe JSONL history scoped to a single tenant."""

    _optional_string_fields = (
        "bundle_type",
        "project_id",
        "knowledge_project_id",
        "knowledge_promoted_at",
        "knowledge_quality_tier",
        "knowledge_success_state",
    )
    _record_list_fields = (
        "applied_references",
        "docs",
        "visual_assets",
        "knowledge_documents",
    )

    def __init__(
        self,
        tenant_id: str,
        base_dir: str | Path | None = None,
        *,
        backend: StateBackend | None = None,
    ) -> None:
        self.tenant_id = require_tenant_id(tenant_id)
        self._base = Path(base_dir or os.getenv("DATA_DIR", "data"))
        self._relative_path = str(Path("tenants") / self.tenant_id / "history.jsonl")
        self._path = self._base / self._relative_path
        self._backend = backend or get_state_backend(data_dir=self._base)
        self._lock = _lock_for_path(self._path)

    def _owns(self, entry: dict[str, Any]) -> bool:
        stored_tenant_id = entry.get("tenant_id")
        return stored_tenant_id is None or stored_tenant_id == self.tenant_id

    def _validate_record(self, entry: object) -> dict[str, Any]:
        if not isinstance(entry, dict):
            raise HistoryStoreError("Invalid history record")

        stored_tenant_id = entry.get("tenant_id")
        if stored_tenant_id is not None:
            if not isinstance(stored_tenant_id, str) or not stored_tenant_id:
                raise HistoryStoreError("Invalid history identity")
            if stored_tenant_id != self.tenant_id:
                return entry

        required_strings = (
            "entry_id",
            "user_id",
            "bundle_id",
            "bundle_name",
            "title",
            "request_id",
            "created_at",
        )
        if any(not isinstance(entry.get(field), str) for field in required_strings):
            raise HistoryStoreError("Invalid history record")
        identity_fields = ("entry_id", "user_id", "bundle_id", "request_id")
        if any(not entry[field] for field in identity_fields):
            raise HistoryStoreError("Invalid history identity")

        for field in self._optional_string_fields:
            if field in entry and not isinstance(entry[field], str):
                raise HistoryStoreError("Invalid history record")

        score = entry.get("score", 0.0)
        if (
            isinstance(score, bool)
            or not isinstance(score, (int, float))
            or not math.isfinite(score)
        ):
            raise HistoryStoreError("Invalid history score")

        tags = entry.get("tags", [])
        if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
            raise HistoryStoreError("Invalid history tags")
        for field in self._record_list_fields:
            records = entry.get(field, [])
            if not isinstance(records, list) or any(
                not isinstance(record, dict) for record in records
            ):
                raise HistoryStoreError("Invalid history document list")

        if "starred" in entry and not isinstance(entry["starred"], bool):
            raise HistoryStoreError("Invalid history favorite state")
        if "knowledge_promoted" in entry and not isinstance(
            entry["knowledge_promoted"], bool
        ):
            raise HistoryStoreError("Invalid history promotion state")
        document_count = entry.get("knowledge_document_count", 0)
        if (
            isinstance(document_count, bool)
            or not isinstance(document_count, int)
            or document_count < 0
        ):
            raise HistoryStoreError("Invalid history document count")

        try:
            datetime.fromisoformat(entry["created_at"])
            promoted_at = entry.get("knowledge_promoted_at", "")
            if promoted_at:
                datetime.fromisoformat(promoted_at)
        except ValueError as exc:
            raise HistoryStoreError("Invalid history timestamp") from exc
        return entry

    def _validate_entries(self, entries: object) -> list[dict[str, Any]]:
        if not isinstance(entries, list):
            raise HistoryStoreError("Invalid history state")

        entry_ids: set[str] = set()
        for entry in entries:
            self._validate_record(entry)
            if not self._owns(entry):
                continue
            entry_id = entry["entry_id"]
            if entry_id in entry_ids:
                raise HistoryStoreError("Duplicate history identity")
            entry_ids.add(entry_id)
        return entries

    def _load(self) -> list[dict[str, Any]]:
        raw = self._backend.read_text(self._relative_path)
        if raw is None or not raw.strip():
            return []

        entries: list[dict[str, Any]] = []
        for line_number, line in enumerate(raw.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                entry = json.loads(line, object_pairs_hook=_unique_object)
                self._validate_record(entry)
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                raise HistoryStoreError(
                    f"Invalid history state at line {line_number}"
                ) from exc
            entries.append(entry)
        return self._validate_entries(entries)

    def _save(self, entries: list[dict[str, Any]]) -> None:
        self._validate_entries(entries)
        payload = "".join(
            f"{json.dumps(entry, ensure_ascii=False)}\n" for entry in entries
        )
        self._backend.write_text(
            self._relative_path,
            payload,
            content_type="application/x-ndjson; charset=utf-8",
        )

    @staticmethod
    def _sanitize_entry(
        entry: dict[str, Any],
        *,
        include_docs: bool = False,
        include_visual_assets: bool = False,
    ) -> dict[str, Any]:
        item = dict(entry)
        if not include_docs:
            item.pop("docs", None)
        if not include_visual_assets:
            item["visual_asset_count"] = len(item.get("visual_assets") or [])
            item.pop("visual_assets", None)
        return item

    @staticmethod
    def _sanitize_visual_assets(visual_assets: list[dict] | None) -> list[dict]:
        sanitized: list[dict] = []
        for asset in visual_assets or []:
            if not isinstance(asset, dict):
                continue
            sanitized.append(
                {
                    "asset_id": str(asset.get("asset_id") or "").strip(),
                    "doc_type": str(asset.get("doc_type") or "").strip(),
                    "slide_title": str(asset.get("slide_title") or "").strip(),
                    "visual_type": str(asset.get("visual_type") or "").strip(),
                    "visual_brief": str(asset.get("visual_brief") or "").strip(),
                    "layout_hint": str(asset.get("layout_hint") or "").strip(),
                    "source_kind": str(asset.get("source_kind") or "").strip(),
                    "source_model": str(asset.get("source_model") or "").strip(),
                    "prompt": str(asset.get("prompt") or "").strip(),
                    "media_type": str(asset.get("media_type") or "").strip(),
                    "encoding": str(asset.get("encoding") or "base64").strip()
                    or "base64",
                    "content_base64": str(asset.get("content_base64") or "").strip(),
                }
            )
        return sanitized[:12]

    def _record_from_entry(self, entry: HistoryEntry) -> dict[str, Any]:
        record = asdict(entry)
        if record["bundle_type"] == "":
            record["bundle_type"] = entry.bundle_id
        for field in ("tags", *self._record_list_fields):
            if record[field] is None:
                record[field] = []
        self._validate_record(record)
        record["visual_assets"] = self._sanitize_visual_assets(record["visual_assets"])
        return self._validate_record(record)

    def add(self, entry: HistoryEntry) -> None:
        if entry.tenant_id != self.tenant_id:
            raise ValueError("History entry tenant does not match store tenant")
        record = self._record_from_entry(entry)

        with self._lock:
            entries = self._load()
            if any(
                self._owns(item) and item["entry_id"] == entry.entry_id
                for item in entries
            ):
                raise HistoryStoreError("Duplicate history identity")
            entries.insert(0, record)
            user_entries = [
                item
                for item in entries
                if self._owns(item) and item["user_id"] == entry.user_id
            ][:MAX_HISTORY_PER_USER]
            other_entries = [
                item
                for item in entries
                if not self._owns(item) or item["user_id"] != entry.user_id
            ]
            self._save(other_entries + user_entries)

    def get_for_user(self, user_id: str, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            entries = self._load()
        return [
            self._sanitize_entry(entry)
            for entry in entries
            if self._owns(entry) and entry["user_id"] == user_id
        ][:limit]

    def get_entry(self, entry_id: str, user_id: str) -> dict[str, Any] | None:
        with self._lock:
            entries = self._load()
        for entry in entries:
            if (
                self._owns(entry)
                and entry["entry_id"] == entry_id
                and entry["user_id"] == user_id
            ):
                return self._sanitize_entry(
                    entry,
                    include_docs=True,
                    include_visual_assets=True,
                )
        return None

    def update_visual_assets(
        self,
        entry_id: str,
        user_id: str,
        visual_assets: list[dict] | None,
    ) -> bool:
        if visual_assets is not None and (
            not isinstance(visual_assets, list)
            or any(not isinstance(asset, dict) for asset in visual_assets)
        ):
            raise HistoryStoreError("Invalid history document list")
        sanitized_assets = self._sanitize_visual_assets(visual_assets)
        with self._lock:
            entries = self._load()
            for entry in entries:
                if (
                    self._owns(entry)
                    and entry["entry_id"] == entry_id
                    and entry["user_id"] == user_id
                ):
                    entry["visual_assets"] = sanitized_assets
                    self._save(entries)
                    return True
        return False

    def delete(self, entry_id: str, user_id: str) -> None:
        with self._lock:
            entries = self._load()
            remaining = [
                entry
                for entry in entries
                if not (
                    self._owns(entry)
                    and entry["entry_id"] == entry_id
                    and entry["user_id"] == user_id
                )
            ]
            if len(remaining) != len(entries):
                self._save(remaining)

    def toggle_favorite(self, entry_id: str, user_id: str) -> bool:
        """Toggle and return the favorite state of an owned history entry."""
        with self._lock:
            entries = self._load()
            for entry in entries:
                if (
                    self._owns(entry)
                    and entry["entry_id"] == entry_id
                    and entry["user_id"] == user_id
                ):
                    entry["starred"] = not entry.get("starred", False)
                    self._save(entries)
                    return entry["starred"]
        return False

    def mark_promoted(
        self,
        request_id: str,
        *,
        project_id: str,
        document_count: int,
        quality_tier: str,
        success_state: str,
        promoted_at: str,
        knowledge_documents: list[dict] | None = None,
        user_id: str | None = None,
    ) -> int:
        """Mark matching history entries as promoted to the knowledge library."""
        if not isinstance(request_id, str):
            raise HistoryStoreError("Invalid history identity")
        if not request_id:
            return 0
        if any(
            not isinstance(value, str)
            for value in (project_id, quality_tier, success_state, promoted_at)
        ):
            raise HistoryStoreError("Invalid history promotion state")
        if user_id is not None and (not isinstance(user_id, str) or not user_id):
            raise HistoryStoreError("Invalid history identity")
        if (
            isinstance(document_count, bool)
            or not isinstance(document_count, int)
            or document_count < 0
        ):
            raise HistoryStoreError("Invalid history document count")
        if knowledge_documents is not None and (
            not isinstance(knowledge_documents, list)
            or any(not isinstance(document, dict) for document in knowledge_documents)
        ):
            raise HistoryStoreError("Invalid history document list")
        try:
            datetime.fromisoformat(promoted_at)
        except ValueError as exc:
            raise HistoryStoreError("Invalid history timestamp") from exc

        documents = [
            {
                "doc_id": str(document.get("doc_id") or "").strip(),
                "doc_type": str(document.get("doc_type") or "").strip(),
                "filename": str(document.get("filename") or "").strip(),
                "quality_tier": str(document.get("quality_tier") or "").strip(),
                "success_state": str(document.get("success_state") or "").strip(),
            }
            for document in (knowledge_documents or [])
            if isinstance(document, dict) and str(document.get("doc_id") or "").strip()
        ]

        updated = 0
        with self._lock:
            entries = self._load()
            for entry in entries:
                if not self._owns(entry) or entry["request_id"] != request_id:
                    continue
                if user_id and entry["user_id"] != user_id:
                    continue
                entry["knowledge_promoted"] = True
                entry["knowledge_project_id"] = project_id
                entry["knowledge_promoted_at"] = promoted_at
                entry["knowledge_document_count"] = document_count
                entry["knowledge_quality_tier"] = quality_tier
                entry["knowledge_success_state"] = success_state
                entry["knowledge_documents"] = documents
                updated += 1
            if updated:
                self._save(entries)
        return updated

    def get_favorites(self, user_id: str) -> list[dict[str, Any]]:
        with self._lock:
            entries = self._load()
        return [
            self._sanitize_entry(entry)
            for entry in entries
            if self._owns(entry)
            and entry["user_id"] == user_id
            and entry.get("starred", False)
        ]

    def search(self, user_id: str, q: str, limit: int = 20) -> list[dict[str, Any]]:
        q_lower = q.strip().lower()
        if not q_lower:
            return self.get_for_user(user_id, limit)
        with self._lock:
            entries = self._load()

        results = []
        for entry in entries:
            if not self._owns(entry) or entry["user_id"] != user_id:
                continue
            haystack = " ".join(
                [
                    entry["title"],
                    entry["bundle_name"],
                    entry["bundle_id"],
                    " ".join(entry.get("tags") or []),
                ]
            ).lower()
            if q_lower in haystack:
                results.append(self._sanitize_entry(entry))
        return results[:limit]
