"""app/storage/usage_store.py — Append-only usage metering store.

Storage:
  data/tenants/{tenant_id}/usage.jsonl      — raw event log
  data/tenants/{tenant_id}/usage_summary.json — monthly aggregates
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from app.storage.base import atomic_write_text
from app.tenant import require_tenant_id


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


# Independent store instances that target the same tenant file share one lock.
_path_locks: dict[Path, threading.Lock] = {}
_path_locks_guard = threading.Lock()


def _lock_for_path(path: Path) -> threading.Lock:
    with _path_locks_guard:
        return _path_locks.setdefault(path.resolve(), threading.Lock())


class UsageStore:
    """Usage metering store bound to one tenant."""

    def __init__(self, data_dir: Path | None = None, *, tenant_id: str) -> None:
        self._tenant_id = require_tenant_id(tenant_id)
        self._data_dir = Path(data_dir or os.getenv("DATA_DIR", "./data"))
        self._tenant_dir = self._data_dir / "tenants" / self._tenant_id
        self._jsonl_path = self._tenant_dir / "usage.jsonl"
        self._summary_path = self._tenant_dir / "usage_summary.json"
        self._lock = _lock_for_path(self._jsonl_path)

    def _empty_summary(self, year_month: str) -> UsageSummary:
        return UsageSummary(
            tenant_id=self._tenant_id,
            year_month=year_month,
            total_generations=0,
            total_tokens=0,
            total_cost_usd=0.0,
            by_bundle={},
            by_user={},
            by_model={},
            last_updated="",
        )

    def _owns_event(self, event: Any) -> bool:
        return isinstance(event, dict) and event.get("tenant_id") == self._tenant_id

    # ── Core I/O ──────────────────────────────────────────────────────────────

    def _read_events(self) -> list[dict]:
        if not self._jsonl_path.exists():
            return []
        events: list[dict] = []
        try:
            for line in self._jsonl_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue  # skip corrupt lines
                if self._owns_event(event):
                    events.append(event)
        except OSError:
            pass
        return events

    def _load_summary(
        self,
        year_month: str,
        *,
        reject_foreign: bool = False,
    ) -> UsageSummary:
        if self._summary_path.exists():
            try:
                data = json.loads(self._summary_path.read_text(encoding="utf-8"))
                if year_month in data:
                    entry = data[year_month]
                    if not isinstance(entry, dict) or entry.get("tenant_id") != self._tenant_id:
                        if reject_foreign and isinstance(entry, dict):
                            raise ValueError("Usage summary tenant ownership mismatch")
                        return self._empty_summary(year_month)
                    return UsageSummary(
                        tenant_id=self._tenant_id,
                        year_month=year_month,
                        total_generations=entry.get("total_generations", 0),
                        total_tokens=entry.get("total_tokens", 0),
                        total_cost_usd=entry.get("total_cost_usd", 0.0),
                        by_bundle=entry.get("by_bundle", {}),
                        by_user=entry.get("by_user", {}),
                        by_model=entry.get("by_model", {}),
                        last_updated=entry.get("last_updated", ""),
                    )
            except (OSError, json.JSONDecodeError, KeyError, TypeError):
                pass
        return self._empty_summary(year_month)

    def _save_summary(self, summary: UsageSummary) -> None:
        if summary.tenant_id != self._tenant_id:
            raise ValueError("Usage summary tenant ownership mismatch")

        # Load existing data (all months)
        all_data: dict = {}
        if self._summary_path.exists():
            try:
                loaded = json.loads(self._summary_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    all_data = loaded
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

        atomic_write_text(
            self._summary_path,
            json.dumps(all_data, ensure_ascii=False, indent=2),
        )

    def _updated_summary(self, event: UsageEvent) -> UsageSummary:
        year_month = event.timestamp[:7]  # "YYYY-MM"
        summary = self._load_summary(year_month, reject_foreign=True)

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

        return summary

    # ── Public API ────────────────────────────────────────────────────────────

    def record(self, event: UsageEvent) -> None:
        """Persist an event and its monthly summary under one tenant lock."""
        if event.tenant_id != self._tenant_id:
            raise ValueError("Usage event tenant ownership mismatch")
        with self._lock:
            summary = self._updated_summary(event)
            line = json.dumps(asdict(event), ensure_ascii=False) + "\n"
            self._jsonl_path.parent.mkdir(parents=True, exist_ok=True)
            with self._jsonl_path.open("a", encoding="utf-8") as stream:
                stream.write(line)
                stream.flush()
                os.fsync(stream.fileno())
            self._save_summary(summary)

    def get_current_month(self) -> UsageSummary | None:
        year_month = datetime.now(timezone.utc).strftime("%Y-%m")
        summary = self._load_summary(year_month)
        if summary.last_updated:
            return summary
        return None

    def get_month(self, year_month: str) -> UsageSummary | None:
        summary = self._load_summary(year_month)
        if summary.last_updated:
            return summary
        return None

    def get_daily_usage(self, days: int = 30) -> list[dict]:
        """Return list of {date, generations, tokens, cost} for the last N days."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        events = self._read_events()

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

    def get_total_month_cost(self) -> float:
        summary = self.get_current_month()
        return summary.total_cost_usd if summary else 0.0

    def check_limit(self, plan: Any) -> dict:
        """Check whether usage is within plan limits.

        Returns:
            {within_limit, generations_used, generations_limit,
             tokens_used, tokens_limit, percent_used}
        """
        summary = self.get_current_month()
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
