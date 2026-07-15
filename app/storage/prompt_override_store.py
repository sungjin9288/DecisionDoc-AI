"""PromptOverrideStore — 런타임 프롬프트 개선 오버라이드 저장소.

저평점 피드백 패턴 분석 결과를 번들별로 저장하고,
다음 문서 생성 시 build_bundle_prompt()에 자동 주입됩니다.
"""
from __future__ import annotations

import functools
import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.storage.base import atomic_write_text
from app.tenant import require_tenant_id

_log = logging.getLogger("decisiondoc.storage.prompt_override")


class PromptOverrideStore:
    """Thread-safe JSON store for per-bundle prompt improvement overrides.

    Storage: data/tenants/{tenant_id}/prompt_overrides.json
    Shape: {bundle_id: OverrideRecord, ...}
    """

    def __init__(self, data_dir: Path, *, tenant_id: str) -> None:
        self._tenant_id = require_tenant_id(tenant_id)
        tenant_dir = Path(data_dir) / "tenants" / self._tenant_id
        tenant_dir.mkdir(parents=True, exist_ok=True)
        self._path = tenant_dir / "prompt_overrides.json"
        self._lock = threading.Lock()

    # ── Internal helpers ──────────────────────────────────────────────────

    def _load(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            # Back up corrupted file before resetting state
            try:
                ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
                backup = self._path.with_suffix(f".corrupted.{ts}.json")
                self._path.rename(backup)
                _log.error(
                    "Corrupted prompt_overrides store backed up to %s: %s", backup.name, exc
                )
            except OSError:
                _log.error(
                    "prompt_overrides store corrupted and could not be backed up: %s", exc
                )
            return {}

    def _persist(self, data: dict[str, Any]) -> None:
        atomic_write_text(
            self._path,
            json.dumps(data, ensure_ascii=False, indent=2),
        )

    def _owns(self, record: Any) -> bool:
        if not isinstance(record, dict):
            return False
        stored_tenant_id = record.get("tenant_id")
        return stored_tenant_id is None or stored_tenant_id == self._tenant_id

    # ── Public API ────────────────────────────────────────────────────────

    def save_override(
        self,
        bundle_id: str,
        override_hint: str,
        trigger_reason: str,
        avg_score_before: float = 0.0,
    ) -> None:
        """저평점 패턴 분석 결과를 오버라이드로 저장 (기존 오버라이드 덮어쓰기).

        Args:
            bundle_id: 번들 식별자 (예: "tech_decision")
            override_hint: 프롬프트에 주입할 개선 지시 문자열
            trigger_reason: "low_rating_pattern" | "llm_judge_feedback"
            avg_score_before: 오버라이드 적용 전 휴리스틱 평균 점수
        """
        with self._lock:
            data = self._load()
            existing = data.get(bundle_id)
            if existing is not None and not self._owns(existing):
                raise ValueError("Prompt override tenant does not match store tenant")
            data[bundle_id] = {
                "bundle_id": bundle_id,
                "tenant_id": self._tenant_id,
                "override_hint": override_hint,
                "trigger_reason": trigger_reason,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "applied_count": existing.get("applied_count", 0) if existing else 0,
                "avg_score_before": avg_score_before,
            }
            self._persist(data)

    def get_override(self, bundle_id: str) -> dict[str, Any] | None:
        """번들 오버라이드 조회. 없으면 None."""
        with self._lock:
            record = self._load().get(bundle_id)
            return record if self._owns(record) else None

    def increment_applied(self, bundle_id: str) -> None:
        """생성 프롬프트에 오버라이드가 사용될 때마다 카운트 증가."""
        with self._lock:
            data = self._load()
            record = data.get(bundle_id)
            if self._owns(record):
                record["applied_count"] = record.get("applied_count", 0) + 1
                self._persist(data)

    def list_overrides(self) -> list[dict[str, Any]]:
        """모든 오버라이드 레코드 목록 반환."""
        with self._lock:
            return [record for record in self._load().values() if self._owns(record)]

    def delete_override(self, bundle_id: str) -> None:
        """특정 번들의 오버라이드 삭제."""
        with self._lock:
            data = self._load()
            if self._owns(data.get(bundle_id)):
                del data[bundle_id]
                self._persist(data)


@functools.lru_cache(maxsize=50)
def get_override_store(tenant_id: str) -> "PromptOverrideStore":
    """Return a cached PromptOverrideStore for the given tenant."""
    from pathlib import Path
    data_dir = Path(os.getenv("DATA_DIR", "./data"))
    return PromptOverrideStore(data_dir, tenant_id=tenant_id)


def clear_override_store_cache() -> None:
    """Invalidate the store factory cache (call after tenant update)."""
    get_override_store.cache_clear()
