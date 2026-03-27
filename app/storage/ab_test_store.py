"""ABTestStore — per-bundle A/B prompt variant test tracker.

각 번들별로 두 가지 프롬프트 변형(variant_a / variant_b)을 A/B 테스트하고,
충분한 샘플이 쌓이면 우승 변형을 PromptOverrideStore에 저장합니다.

Storage: data/ab_tests.json
Shape: {bundle_id: ABTestRecord, ...}
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

_log = logging.getLogger("decisiondoc.storage.ab_test")


class ABTestStore:
    """Thread-safe JSON store for per-bundle A/B prompt variant tests."""

    def __init__(self, data_dir: Path, tenant_id: str = "system") -> None:
        self._tenant_id = tenant_id
        tenant_dir = Path(data_dir) / "tenants" / tenant_id
        tenant_dir.mkdir(parents=True, exist_ok=True)
        self._path = tenant_dir / "ab_tests.json"
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
                    "Corrupted ab_tests store backed up to %s: %s", backup.name, exc
                )
            except OSError:
                _log.error("ab_tests store corrupted and could not be backed up: %s", exc)
            return {}

    def _persist(self, data: dict[str, Any]) -> None:
        self._path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ── Public API ────────────────────────────────────────────────────────

    def create_test(
        self,
        bundle_id: str,
        variant_a_hint: str,
        variant_b_hint: str,
        min_samples: int = 5,
    ) -> None:
        """Create a new A/B test. Replaces any existing test for this bundle.

        Args:
            bundle_id: Bundle identifier (e.g. "tech_decision")
            variant_a_hint: Prompt improvement hint for variant A
            variant_b_hint: Prompt improvement hint for variant B
            min_samples: Minimum results per variant before concluding
        """
        with self._lock:
            data = self._load()
            data[bundle_id] = {
                "bundle_id": bundle_id,
                "status": "active",
                "variant_a_hint": variant_a_hint,
                "variant_b_hint": variant_b_hint,
                "min_samples": min_samples,
                "generation_count": 0,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "concluded_at": None,
                "winner": None,
                "winner_avg_score": None,
                "results": {
                    "variant_a": [],
                    "variant_b": [],
                },
            }
            self._persist(data)

    def get_active_test(self, bundle_id: str) -> dict[str, Any] | None:
        """Return the active A/B test for a bundle, or None."""
        with self._lock:
            data = self._load()
            test = data.get(bundle_id)
            if test and test.get("status") == "active":
                return test
            return None

    def get_next_variant(self, bundle_id: str) -> str | None:
        """Atomically determine and return the next variant to use.

        Uses round-robin assignment based on generation_count:
          - even count → 'variant_a'
          - odd count  → 'variant_b'

        Increments generation_count. Returns None if no active test exists.
        """
        with self._lock:
            data = self._load()
            test = data.get(bundle_id)
            if not test or test.get("status") != "active":
                return None
            count = test.get("generation_count", 0)
            variant = "variant_a" if count % 2 == 0 else "variant_b"
            test["generation_count"] = count + 1
            self._persist(data)
            return variant

    def record_result(
        self,
        bundle_id: str,
        variant: str,
        heuristic_score: float,
        llm_score: float | None = None,
    ) -> None:
        """Append an eval result for the given variant.

        Args:
            bundle_id: Bundle identifier
            variant: 'variant_a' or 'variant_b'
            heuristic_score: Heuristic eval score (0–1)
            llm_score: Optional LLM judge score (1–5)
        """
        if variant not in ("variant_a", "variant_b"):
            return
        with self._lock:
            data = self._load()
            test = data.get(bundle_id)
            if not test or test.get("status") != "active":
                return
            results = test.setdefault("results", {"variant_a": [], "variant_b": []})
            results.setdefault(variant, []).append({
                "heuristic_score": heuristic_score,
                "llm_score": llm_score,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            })
            self._persist(data)

    def evaluate_and_conclude(self, bundle_id: str) -> str | None:
        """Check if both variants have enough samples and conclude if so.

        Returns:
            Winner name ('variant_a' or 'variant_b') if concluded, else None.

        Side effect on conclude:
            Saves winner's hint to PromptOverrideStore (trigger_reason='ab_test_winner').
        """
        winner: str | None = None
        winner_hint: str = ""

        with self._lock:
            data = self._load()
            test = data.get(bundle_id)
            if not test or test.get("status") != "active":
                return None

            min_samples = test.get("min_samples", 5)
            results = test.get("results", {})
            a_results = results.get("variant_a", [])
            b_results = results.get("variant_b", [])

            if len(a_results) < min_samples or len(b_results) < min_samples:
                return None

            # Compare average heuristic scores; variant_a wins on tie
            a_avg = sum(r["heuristic_score"] for r in a_results) / len(a_results)
            b_avg = sum(r["heuristic_score"] for r in b_results) / len(b_results)

            winner = "variant_a" if a_avg >= b_avg else "variant_b"
            winner_hint = test.get(f"{winner}_hint", "")
            winner_avg = round(a_avg if winner == "variant_a" else b_avg, 3)

            test["status"] = "concluded"
            test["concluded_at"] = datetime.now(timezone.utc).isoformat()
            test["winner"] = winner
            test["winner_avg_score"] = winner_avg
            self._persist(data)

        # Save winner hint to PromptOverrideStore (outside lock to avoid deadlock)
        if winner_hint:
            try:
                from app.storage.prompt_override_store import PromptOverrideStore
                data_dir = Path(os.getenv("DATA_DIR", "./data"))
                override_store = PromptOverrideStore(data_dir)
                override_store.save_override(
                    bundle_id=bundle_id,
                    override_hint=winner_hint,
                    trigger_reason="ab_test_winner",
                    avg_score_before=0.0,
                )
            except Exception as exc:
                _log.error(
                    "[ABTest] Failed to save winner hint to PromptOverrideStore "
                    "bundle=%s winner=%s: %s",
                    bundle_id, winner, exc,
                )

        return winner

    def list_active_tests(self) -> list[dict[str, Any]]:
        """Return all active A/B tests."""
        with self._lock:
            data = self._load()
            return [t for t in data.values() if t.get("status") == "active"]

    def list_concluded_tests(self) -> list[dict[str, Any]]:
        """Return all concluded A/B tests."""
        with self._lock:
            data = self._load()
            return [t for t in data.values() if t.get("status") == "concluded"]

    def delete_test(self, bundle_id: str) -> None:
        """Delete the A/B test for a bundle (used by reset endpoint)."""
        with self._lock:
            data = self._load()
            if bundle_id in data:
                del data[bundle_id]
                self._persist(data)


@functools.lru_cache(maxsize=50)
def get_ab_test_store(tenant_id: str = "system") -> "ABTestStore":
    """Return a cached ABTestStore for the given tenant."""
    from pathlib import Path
    data_dir = Path(os.getenv("DATA_DIR", "./data"))
    return ABTestStore(data_dir, tenant_id=tenant_id)


def clear_ab_test_store_cache() -> None:
    """Invalidate the store factory cache (call after tenant update)."""
    get_ab_test_store.cache_clear()
