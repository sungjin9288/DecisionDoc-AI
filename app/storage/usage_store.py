"""app/storage/usage_store.py — Append-only usage metering store.

Storage:
  data/tenants/{tenant_id}/usage.jsonl      — raw event log
  data/tenants/{tenant_id}/usage_summary.json — monthly aggregates
"""
from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any


@dataclass
class UsageEvent:
    event_id: str
    tenant_id: str
    user_id: str
    timestamp: str
    event_type: str       # "doc.generate" | "doc.download" | "api.call" | "storage.write"
    bundle_id: str | None
    tokens_input: int
    tokens_output: int
    tokens_total: int
    cost_usd: float
    model: str
    request_id: str


@dataclass
class UsageSummary:
    tenant_id: str
    year_month: str       # "2025-03"
    total_generations: int
    total_tokens: int
    total_cost_usd: float
    by_bundle: dict       # bundle_id -> {count, tokens, cost}
    by_user: dict         # user_id -> {count, tokens, cost}
    by_model: dict        # model -> {count, tokens, cost}
    last_updated: str


# Per-tenant locks for thread safety
_tenant_locks: dict[str, threading.Lock] = {}
_locks_meta: threading.Lock = threading.Lock()


def _get_tenant_lock(tenant_id: str) -> threading.Lock:
    with _locks_meta:
        if tenant_id not in _tenant_locks:
            _tenant_locks[tenant_id] = threading.Lock()
        return _tenant_locks[tenant_id]


class UsageStore:
    """Stateless usage store — all state is on disk. Thread-safe via per-tenant locks."""

    def __init__(self) -> None:
        self._data_dir = Path(os.getenv("DATA_DIR", "./data"))

    # ── Path helpers ──────────────────────────────────────────────────────────

    def _tenant_dir(self, tenant_id: str) -> Path:
        return self._data_dir / "tenants" / tenant_id

    def _jsonl_path(self, tenant_id: str) -> Path:
        return self._tenant_dir(tenant_id) / "usage.jsonl"

    def _summary_path(self, tenant_id: str) -> Path:
        return self._tenant_dir(tenant_id) / "usage_summary.json"

    # ── Core I/O ──────────────────────────────────────────────────────────────

    def _read_events(self, tenant_id: str) -> list[dict]:
        path = self._jsonl_path(tenant_id)
        if not path.exists():
            return []
        events: list[dict] = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except (json.JSONDecodeError, ValueError):
                    continue  # skip corrupt lines
        except OSError:
            pass
        return events

    def _load_summary(self, tenant_id: str, year_month: str) -> UsageSummary:
        path = self._summary_path(tenant_id)
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if year_month in data:
                    entry = data[year_month]
                    return UsageSummary(
                        tenant_id=tenant_id,
                        year_month=year_month,
                        total_generations=entry.get("total_generations", 0),
                        total_tokens=entry.get("total_tokens", 0),
                        total_cost_usd=entry.get("total_cost_usd", 0.0),
                        by_bundle=entry.get("by_bundle", {}),
                        by_user=entry.get("by_user", {}),
                        by_model=entry.get("by_model", {}),
                        last_updated=entry.get("last_updated", ""),
                    )
            except (OSError, json.JSONDecodeError, KeyError):
                pass
        # Return empty summary
        return UsageSummary(
            tenant_id=tenant_id,
            year_month=year_month,
            total_generations=0,
            total_tokens=0,
            total_cost_usd=0.0,
            by_bundle={},
            by_user={},
            by_model={},
            last_updated="",
        )

    def _save_summary(self, summary: UsageSummary) -> None:
        path = self._summary_path(summary.tenant_id)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Load existing data (all months)
        all_data: dict = {}
        if path.exists():
            try:
                all_data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                all_data = {}

        all_data[summary.year_month] = {
            "tenant_id": summary.tenant_id,
            "year_month": summary.year_month,
            "total_generations": summary.total_generations,
            "total_tokens": summary.total_tokens,
            "total_cost_usd": summary.total_cost_usd,
            "by_bundle": summary.by_bundle,
            "by_user": summary.by_user,
            "by_model": summary.by_model,
            "last_updated": summary.last_updated,
        }

        # Atomic write: tmp + rename
        tmp_path = path.with_name(f"{path.name}.tmp.{uuid.uuid4().hex}")
        try:
            tmp_path.write_text(
                json.dumps(all_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(tmp_path, path)
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

    def _update_summary(self, event: UsageEvent) -> None:
        year_month = event.timestamp[:7]  # "YYYY-MM"
        summary = self._load_summary(event.tenant_id, year_month)

        if event.event_type == "doc.generate":
            summary.total_generations += 1
        summary.total_tokens += event.tokens_total
        summary.total_cost_usd += event.cost_usd
        summary.last_updated = datetime.now(timezone.utc).isoformat()

        # by_bundle
        if event.bundle_id:
            bucket = summary.by_bundle.setdefault(
                event.bundle_id, {"count": 0, "tokens": 0, "cost": 0.0}
            )
            bucket["count"] += 1
            bucket["tokens"] += event.tokens_total
            bucket["cost"] += event.cost_usd

        # by_user
        user_bucket = summary.by_user.setdefault(
            event.user_id, {"count": 0, "tokens": 0, "cost": 0.0}
        )
        user_bucket["count"] += 1
        user_bucket["tokens"] += event.tokens_total
        user_bucket["cost"] += event.cost_usd

        # by_model
        model_bucket = summary.by_model.setdefault(
            event.model, {"count": 0, "tokens": 0, "cost": 0.0}
        )
        model_bucket["count"] += 1
        model_bucket["tokens"] += event.tokens_total
        model_bucket["cost"] += event.cost_usd

        self._save_summary(summary)

    # ── Public API ────────────────────────────────────────────────────────────

    def record(self, event: UsageEvent) -> None:
        """Append event to JSONL and update monthly summary atomically."""
        lock = _get_tenant_lock(event.tenant_id)
        with lock:
            path = self._jsonl_path(event.tenant_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps(asdict(event), ensure_ascii=False) + "\n"
            with path.open("a", encoding="utf-8") as f:
                f.write(line)
            self._update_summary(event)

    def get_current_month(self, tenant_id: str) -> UsageSummary | None:
        year_month = datetime.now(timezone.utc).strftime("%Y-%m")
        summary = self._load_summary(tenant_id, year_month)
        if summary.last_updated:
            return summary
        return None

    def get_month(self, tenant_id: str, year_month: str) -> UsageSummary | None:
        summary = self._load_summary(tenant_id, year_month)
        if summary.last_updated:
            return summary
        return None

    def get_daily_usage(self, tenant_id: str, days: int = 30) -> list[dict]:
        """Return list of {date, generations, tokens, cost} for the last N days."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        events = self._read_events(tenant_id)

        daily: dict[str, dict] = {}
        for evt in events:
            ts_str = evt.get("timestamp", "")
            if not ts_str:
                continue
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except ValueError:
                continue
            if ts < cutoff:
                continue
            date_key = ts.strftime("%Y-%m-%d")
            bucket = daily.setdefault(date_key, {"date": date_key, "generations": 0, "tokens": 0, "cost": 0.0})
            if evt.get("event_type") == "doc.generate":
                bucket["generations"] += 1
            bucket["tokens"] += evt.get("tokens_total", 0)
            bucket["cost"] += evt.get("cost_usd", 0.0)

        return sorted(daily.values(), key=lambda x: x["date"])

    def get_total_month_cost(self, tenant_id: str) -> float:
        summary = self.get_current_month(tenant_id)
        return summary.total_cost_usd if summary else 0.0

    def check_limit(self, tenant_id: str, plan: Any) -> dict:
        """Check whether usage is within plan limits.

        Returns:
            {within_limit, generations_used, generations_limit,
             tokens_used, tokens_limit, percent_used}
        """
        summary = self.get_current_month(tenant_id)
        generations_used = summary.total_generations if summary else 0
        tokens_used = summary.total_tokens if summary else 0

        generations_limit: int = plan.monthly_generations
        tokens_limit: int = plan.monthly_tokens

        if generations_limit == -1 and tokens_limit == -1:
            return {
                "within_limit": True,
                "generations_used": generations_used,
                "generations_limit": generations_limit,
                "tokens_used": tokens_used,
                "tokens_limit": tokens_limit,
                "percent_used": 0,
            }

        gen_pct = 0.0
        if generations_limit > 0:
            gen_pct = (generations_used / generations_limit) * 100

        token_pct = 0.0
        if tokens_limit > 0:
            token_pct = (tokens_used / tokens_limit) * 100

        percent_used = round(max(gen_pct, token_pct), 1)

        within_limit = True
        if generations_limit != -1 and generations_used >= generations_limit:
            within_limit = False
        if tokens_limit != -1 and tokens_used >= tokens_limit:
            within_limit = False

        return {
            "within_limit": within_limit,
            "generations_used": generations_used,
            "generations_limit": generations_limit,
            "tokens_used": tokens_used,
            "tokens_limit": tokens_limit,
            "percent_used": percent_used,
        }
