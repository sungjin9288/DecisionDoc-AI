"""eval_store.py — 평가 결과 영속 저장소 (JSON Lines 형식).

생성된 문서의 품질 점수를 data/eval_results.jsonl에 누적 저장하고
집계 통계를 제공합니다.
"""
from __future__ import annotations

import functools
import json
import logging
import os
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

_log = logging.getLogger("decisiondoc.eval.store")


@dataclass
class EvalRecord:
    """단일 문서 생성 건의 평가 결과."""
    request_id: str
    bundle_id: str
    timestamp: str                    # ISO 8601 UTC
    heuristic_score: float            # bundle_eval 휴리스틱 점수 (0.0 ~ 1.0)
    llm_score: float | None           # LLM-as-Judge 점수 (미실행 시 None)
    issues: list[str]                 # 발견된 품질 문제 목록
    doc_scores: dict[str, float]      # 문서 키별 점수 {doc_key: score}
    llm_feedbacks: list[str] = field(default_factory=list)  # LLM judge brief_feedback 목록


class EvalStore:
    """스레드 안전 JSON Lines 기반 평가 결과 저장소."""

    def __init__(self, data_dir: Path, tenant_id: str = "system") -> None:
        self._tenant_id = tenant_id
        tenant_dir = Path(data_dir) / "tenants" / tenant_id
        tenant_dir.mkdir(parents=True, exist_ok=True)
        self._path = tenant_dir / "eval_results.jsonl"
        self._lock = threading.Lock()

    def append(self, record: EvalRecord) -> None:
        """평가 결과를 파일에 추가 저장 (스레드 안전)."""
        with self._lock:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")

    def load_all(self) -> list[EvalRecord]:
        """저장된 모든 평가 결과 로드."""
        if not self._path.exists():
            return []
        records: list[EvalRecord] = []
        with self._lock:
            with self._path.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                        records.append(EvalRecord(**d))
                    except Exception as exc:
                        _log.warning("Skipping malformed eval record: %s", exc)
        return records

    def summary(self) -> dict[str, Any]:
        """평가 결과 집계 통계 반환."""
        records = self.load_all()
        if not records:
            return {"total": 0, "avg_heuristic": None, "by_bundle": {}}

        by_bundle: dict[str, list[float]] = {}
        total_h = 0.0
        for r in records:
            by_bundle.setdefault(r.bundle_id, []).append(r.heuristic_score)
            total_h += r.heuristic_score

        return {
            "total": len(records),
            "avg_heuristic": round(total_h / len(records), 3),
            "by_bundle": {
                bid: {
                    "count": len(scores),
                    "avg": round(sum(scores) / len(scores), 3),
                    "min": round(min(scores), 3),
                    "max": round(max(scores), 3),
                }
                for bid, scores in by_bundle.items()
            },
            "recent": [
                asdict(r)
                for r in sorted(records, key=lambda x: x.timestamp, reverse=True)[:10]
            ],
        }

    def get_bundle_history(self, bundle_id: str, limit: int = 50) -> list["EvalRecord"]:
        """특정 번들의 최근 평가 기록 반환 (최신 순)."""
        all_records = self.load_all()
        bundle_records = [r for r in all_records if r.bundle_id == bundle_id]
        return sorted(bundle_records, key=lambda x: x.timestamp, reverse=True)[:limit]

    def get_all_stats(self) -> dict[str, Any]:
        """전체 평가 집계: total_count, avg_heuristic, avg_llm, low_quality_count.

        low_quality_count: heuristic_score < 0.6 인 레코드 수.
        """
        records = self.load_all()
        if not records:
            return {
                "total_count": 0,
                "avg_heuristic": None,
                "avg_llm": None,
                "low_quality_count": 0,
            }

        total = len(records)
        avg_heuristic = round(sum(r.heuristic_score for r in records) / total, 3)

        llm_records = [r for r in records if r.llm_score is not None]
        avg_llm: float | None = None
        if llm_records:
            avg_llm = round(sum(r.llm_score for r in llm_records) / len(llm_records), 3)  # type: ignore[arg-type]

        low_quality_count = sum(1 for r in records if r.heuristic_score < 0.6)

        return {
            "total_count": total,
            "avg_heuristic": avg_heuristic,
            "avg_llm": avg_llm,
            "low_quality_count": low_quality_count,
        }

    def get_per_bundle_stats(self) -> dict[str, dict[str, Any]]:
        """번들별 집계: count, avg_heuristic, avg_llm, last_timestamp, recent_scores.

        recent_scores: 최근 10개의 heuristic_score 리스트 (트렌드 계산용).
        """
        records = self.load_all()
        by_bundle: dict[str, list["EvalRecord"]] = {}
        for r in records:
            by_bundle.setdefault(r.bundle_id, []).append(r)

        result: dict[str, dict[str, Any]] = {}
        for bundle_id, recs in by_bundle.items():
            sorted_recs = sorted(recs, key=lambda x: x.timestamp)
            count = len(sorted_recs)
            avg_h = round(sum(r.heuristic_score for r in sorted_recs) / count, 3)
            llm_recs = [r for r in sorted_recs if r.llm_score is not None]
            avg_llm: float | None = None
            if llm_recs:
                avg_llm = round(sum(r.llm_score for r in llm_recs) / len(llm_recs), 3)  # type: ignore[arg-type]
            last_ts = sorted_recs[-1].timestamp
            recent_scores = [r.heuristic_score for r in sorted_recs[-10:]]
            result[bundle_id] = {
                "count": count,
                "avg_heuristic": avg_h,
                "avg_llm": avg_llm,
                "last_timestamp": last_ts,
                "recent_scores": recent_scores,
            }
        return result


@functools.lru_cache(maxsize=50)
def get_eval_store(tenant_id: str = "system") -> "EvalStore":
    """Return a cached EvalStore for the given tenant."""
    from pathlib import Path
    data_dir = Path(os.getenv("DATA_DIR", "./data"))
    return EvalStore(data_dir, tenant_id=tenant_id)


def clear_eval_store_cache() -> None:
    """Invalidate the store factory cache (call after tenant update)."""
    get_eval_store.cache_clear()
