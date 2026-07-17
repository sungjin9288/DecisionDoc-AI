"""Tenant-scoped usage metering with verified monthly summaries."""

from __future__ import annotations

import json
import math
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.storage.state_backend import StateBackend, StateBackendError, get_state_backend
from app.storage.state_lock import state_lock
from app.tenant import require_tenant_id


class UsageStoreError(RuntimeError):
    """Raised when persisted usage authority cannot be trusted."""


@dataclass
class UsageEvent:
    event_id: str
    tenant_id: str
    user_id: str
    timestamp: str
    event_type: str
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
    year_month: str
    total_generations: int
    total_tokens: int
    total_cost_usd: float
    by_bundle: dict[str, dict[str, int | float]]
    by_user: dict[str, dict[str, int | float]]
    by_model: dict[str, dict[str, int | float]]
    last_updated: str


_EVENT_TYPES = frozenset({"doc.generate", "doc.download", "api.call", "storage.write"})
_YEAR_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_MAX_RECORD_ATTEMPTS = 32
_EVENT_CONTENT_TYPE = "application/x-ndjson; charset=utf-8"
_SUMMARY_CONTENT_TYPE = "application/json; charset=utf-8"


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise UsageStoreError(f"Duplicate key in usage state: {key!r}")
        result[key] = value
    return result


class UsageStore:
    """Record usage with conditional writes and verify derived summaries."""

    _EVENT_FIELDS = {
        "event_id",
        "tenant_id",
        "user_id",
        "timestamp",
        "event_type",
        "bundle_id",
        "tokens_input",
        "tokens_output",
        "tokens_total",
        "cost_usd",
        "model",
        "request_id",
    }
    _SUMMARY_FIELDS = {
        "tenant_id",
        "year_month",
        "total_generations",
        "total_tokens",
        "total_cost_usd",
        "by_bundle",
        "by_user",
        "by_model",
        "last_updated",
    }
    _BUCKET_FIELDS = {"count", "tokens", "cost"}

    def __init__(
        self,
        data_dir: Path | None = None,
        *,
        tenant_id: str,
        backend: StateBackend | None = None,
    ) -> None:
        self._tenant_id = require_tenant_id(tenant_id)
        self._data_dir = Path(data_dir or os.getenv("DATA_DIR", "./data"))
        self._event_relative_path = str(
            Path("tenants") / self._tenant_id / "usage.jsonl"
        )
        self._summary_relative_path = str(
            Path("tenants") / self._tenant_id / "usage_summary.json"
        )
        self._jsonl_path = self._data_dir / self._event_relative_path
        self._summary_path = self._data_dir / self._summary_relative_path
        self._backend = backend or get_state_backend(data_dir=self._data_dir)
        self._lock = state_lock(
            self._backend,
            data_dir=self._data_dir,
            relative_path=str(Path("tenants") / self._tenant_id / "usage_authority"),
        )

    @staticmethod
    def _text(
        value: object,
        *,
        field_name: str,
        allow_empty: bool = False,
    ) -> str:
        if not isinstance(value, str):
            raise UsageStoreError(f"Invalid usage {field_name}")
        if not allow_empty and not value:
            raise UsageStoreError(f"Invalid usage {field_name}")
        if value != value.strip() or any(
            ord(character) < 32 or ord(character) == 127 for character in value
        ):
            raise UsageStoreError(f"Invalid usage {field_name}")
        return value

    @staticmethod
    def _datetime(value: object, *, field_name: str) -> datetime:
        if not isinstance(value, str) or not value or value != value.strip():
            raise UsageStoreError(f"Invalid usage {field_name}")
        if (
            len(value) < 20
            or value[4] != "-"
            or value[7] != "-"
            or value[10] != "T"
            or _YEAR_MONTH.fullmatch(value[:7]) is None
        ):
            raise UsageStoreError(f"Invalid usage {field_name}")
        try:
            timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise UsageStoreError(f"Invalid usage {field_name}") from exc
        if timestamp.tzinfo is None or timestamp.utcoffset() != timezone.utc.utcoffset(timestamp):
            raise UsageStoreError(f"Invalid usage {field_name}")
        return timestamp

    @classmethod
    def _timestamp(cls, value: object, *, field_name: str) -> str:
        if not isinstance(value, str):
            raise UsageStoreError(f"Invalid usage {field_name}")
        cls._datetime(value, field_name=field_name)
        return value

    @staticmethod
    def _nonnegative_int(value: object, *, field_name: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise UsageStoreError(f"Invalid usage {field_name}")
        return value

    @staticmethod
    def _nonnegative_number(value: object, *, field_name: str) -> float:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
        ):
            raise UsageStoreError(f"Invalid usage {field_name}")
        return float(value)

    def _validate_event(self, event: object, *, owned: bool) -> dict[str, Any]:
        if not isinstance(event, dict) or set(event) != self._EVENT_FIELDS:
            raise UsageStoreError("Invalid usage event fields")
        self._text(event.get("event_id"), field_name="event identity")
        tenant_id = self._text(event.get("tenant_id"), field_name="tenant identity")
        if owned and tenant_id != self._tenant_id:
            raise UsageStoreError("Usage event tenant ownership mismatch")
        self._text(event.get("user_id"), field_name="user identity", allow_empty=True)
        self._timestamp(event.get("timestamp"), field_name="event timestamp")
        if event.get("event_type") not in _EVENT_TYPES:
            raise UsageStoreError("Invalid usage event type")
        bundle_id = event.get("bundle_id")
        if bundle_id is not None:
            self._text(bundle_id, field_name="bundle identity")
        tokens_input = self._nonnegative_int(
            event.get("tokens_input"),
            field_name="input token count",
        )
        tokens_output = self._nonnegative_int(
            event.get("tokens_output"),
            field_name="output token count",
        )
        tokens_total = self._nonnegative_int(
            event.get("tokens_total"),
            field_name="total token count",
        )
        if tokens_total != tokens_input + tokens_output:
            raise UsageStoreError("Usage token totals do not match")
        self._nonnegative_number(event.get("cost_usd"), field_name="cost")
        self._text(event.get("model"), field_name="model identity")
        self._text(event.get("request_id"), field_name="request identity")
        return event

    def _parse_events(self, raw: str | None) -> list[dict[str, Any]]:
        if raw is None or raw == "":
            return []
        events: list[dict[str, Any]] = []
        event_ids: set[str] = set()
        for line_number, line in enumerate(raw.splitlines(), 1):
            if not line.strip():
                raise UsageStoreError(
                    f"Invalid blank line in usage state at line {line_number}"
                )
            try:
                event = json.loads(line, object_pairs_hook=_unique_object)
            except (json.JSONDecodeError, TypeError, UsageStoreError) as exc:
                raise UsageStoreError(
                    f"Invalid usage event at line {line_number}"
                ) from exc
            if not isinstance(event, dict):
                raise UsageStoreError(f"Invalid usage event at line {line_number}")
            tenant_id = event.get("tenant_id")
            if tenant_id != self._tenant_id:
                if not isinstance(tenant_id, str) or not tenant_id:
                    raise UsageStoreError("Invalid usage tenant identity")
                events.append(event)
                continue

            event = self._validate_event(event, owned=True)
            if event["event_id"] in event_ids:
                raise UsageStoreError("Duplicate usage event identity")
            event_ids.add(event["event_id"])
            events.append(event)
        return events

    def _owned_events(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [event for event in events if event.get("tenant_id") == self._tenant_id]

    def _derive_summaries(
        self,
        events: list[dict[str, Any]],
    ) -> dict[str, UsageSummary]:
        summaries: dict[str, UsageSummary] = {}
        for event in self._owned_events(events):
            year_month = event["timestamp"][:7]
            summary = summaries.get(year_month)
            if summary is None:
                summary = UsageSummary(
                    tenant_id=self._tenant_id,
                    year_month=year_month,
                    total_generations=0,
                    total_tokens=0,
                    total_cost_usd=0.0,
                    by_bundle={},
                    by_user={},
                    by_model={},
                    last_updated=event["timestamp"],
                )
                summaries[year_month] = summary

            if event["event_type"] == "doc.generate":
                summary.total_generations += 1
            summary.total_tokens += event["tokens_total"]
            summary.total_cost_usd += float(event["cost_usd"])
            if self._datetime(
                event["timestamp"],
                field_name="event timestamp",
            ) > self._datetime(
                summary.last_updated,
                field_name="summary timestamp",
            ):
                summary.last_updated = event["timestamp"]

            if event["bundle_id"] is not None:
                self._update_bucket(
                    summary.by_bundle,
                    event["bundle_id"],
                    event,
                )
            self._update_bucket(summary.by_user, event["user_id"], event)
            self._update_bucket(summary.by_model, event["model"], event)
        return summaries

    @staticmethod
    def _update_bucket(
        buckets: dict[str, dict[str, int | float]],
        key: str,
        event: dict[str, Any],
    ) -> None:
        bucket = buckets.setdefault(key, {"count": 0, "tokens": 0, "cost": 0.0})
        bucket["count"] += 1
        bucket["tokens"] += event["tokens_total"]
        bucket["cost"] += float(event["cost_usd"])

    def _validate_bucket_map(self, value: object, *, field_name: str) -> None:
        if not isinstance(value, dict):
            raise UsageStoreError(f"Invalid usage {field_name}")
        for key, bucket in value.items():
            self._text(key, field_name=f"{field_name} key", allow_empty=True)
            if not isinstance(bucket, dict) or set(bucket) != self._BUCKET_FIELDS:
                raise UsageStoreError(f"Invalid usage {field_name} bucket")
            self._nonnegative_int(bucket.get("count"), field_name="bucket count")
            self._nonnegative_int(bucket.get("tokens"), field_name="bucket tokens")
            self._nonnegative_number(bucket.get("cost"), field_name="bucket cost")

    def _validate_summary(self, value: object, *, year_month: str) -> UsageSummary:
        if not isinstance(value, dict) or set(value) != self._SUMMARY_FIELDS:
            raise UsageStoreError("Invalid usage summary fields")
        if value.get("tenant_id") != self._tenant_id:
            raise UsageStoreError("Usage summary tenant ownership mismatch")
        if value.get("year_month") != year_month:
            raise UsageStoreError("Usage summary month identity mismatch")
        self._nonnegative_int(
            value.get("total_generations"),
            field_name="summary generation count",
        )
        self._nonnegative_int(value.get("total_tokens"), field_name="summary token count")
        self._nonnegative_number(value.get("total_cost_usd"), field_name="summary cost")
        self._validate_bucket_map(value.get("by_bundle"), field_name="bundle summary")
        self._validate_bucket_map(value.get("by_user"), field_name="user summary")
        self._validate_bucket_map(value.get("by_model"), field_name="model summary")
        self._timestamp(value.get("last_updated"), field_name="summary timestamp")
        return UsageSummary(**value)

    @staticmethod
    def _summary_values(summary: UsageSummary) -> dict[str, Any]:
        value = asdict(summary)
        value.pop("last_updated")
        return value

    def _parse_and_verify_summaries(
        self,
        raw: str | None,
        derived: dict[str, UsageSummary],
    ) -> tuple[dict[str, Any], dict[str, UsageSummary]]:
        if raw is None:
            if derived:
                raise UsageStoreError("Usage summary is missing for persisted events")
            return {}, {}
        try:
            data = json.loads(raw, object_pairs_hook=_unique_object)
        except (json.JSONDecodeError, TypeError, UsageStoreError) as exc:
            raise UsageStoreError("Invalid usage summary document") from exc
        if not isinstance(data, dict):
            raise UsageStoreError("Invalid usage summary collection")

        owned: dict[str, UsageSummary] = {}
        for year_month, entry in data.items():
            if not isinstance(year_month, str) or _YEAR_MONTH.fullmatch(year_month) is None:
                raise UsageStoreError("Invalid usage summary month key")
            if not isinstance(entry, dict):
                raise UsageStoreError("Invalid usage summary entry")
            tenant_id = entry.get("tenant_id")
            if tenant_id != self._tenant_id:
                if not isinstance(tenant_id, str) or not tenant_id:
                    raise UsageStoreError("Invalid usage summary tenant identity")
                continue
            summary = self._validate_summary(entry, year_month=year_month)
            expected = derived.get(year_month)
            if expected is None:
                raise UsageStoreError("Usage summary has no matching events")
            if self._summary_values(summary) != self._summary_values(expected):
                raise UsageStoreError("Usage summary does not match event authority")
            if self._datetime(
                summary.last_updated,
                field_name="summary timestamp",
            ) < self._datetime(
                expected.last_updated,
                field_name="event timestamp",
            ):
                raise UsageStoreError("Usage summary timestamp predates its events")
            owned[year_month] = summary

        if set(owned) != set(derived):
            raise UsageStoreError("Usage summary coverage does not match event authority")
        return data, owned

    def _load_verified_state(
        self,
    ) -> tuple[str | None, list[dict[str, Any]], dict[str, Any], dict[str, UsageSummary]]:
        for _ in range(_MAX_RECORD_ATTEMPTS):
            state = self._load_or_repair_state()
            if state is not None:
                return state
        raise UsageStoreError(
            "Usage state changed too many times to read safely"
        )

    def _read_state_documents(
        self,
    ) -> tuple[str | None, list[dict[str, Any]], str | None]:
        event_raw = self._read_text(self._event_relative_path)
        events = self._parse_events(event_raw)
        summary_raw = self._read_text(self._summary_relative_path)
        return event_raw, events, summary_raw

    def _read_text(self, relative_path: str) -> str | None:
        try:
            return self._backend.read_text(relative_path)
        except (StateBackendError, UnicodeError) as exc:
            raise UsageStoreError("Usage state could not be read") from exc

    def _state_documents_changed(
        self,
        *,
        event_raw: str | None,
        summary_raw: str | None,
    ) -> bool:
        """Distinguish a concurrent two-document read from stable corruption."""
        current_event_raw = self._read_text(self._event_relative_path)
        current_summary_raw = self._read_text(self._summary_relative_path)
        return (
            current_event_raw != event_raw
            or current_summary_raw != summary_raw
        )

    def _summary_document(
        self,
        current: dict[str, Any],
        derived: dict[str, UsageSummary],
    ) -> str:
        for year_month in derived:
            existing = current.get(year_month)
            if (
                isinstance(existing, dict)
                and existing.get("tenant_id") != self._tenant_id
            ):
                raise UsageStoreError(
                    "Usage summary month is owned by another tenant"
                )

        updated = {
            year_month: entry
            for year_month, entry in current.items()
            if not isinstance(entry, dict)
            or entry.get("tenant_id") != self._tenant_id
        }
        updated.update(
            {
                year_month: asdict(summary)
                for year_month, summary in derived.items()
            }
        )
        return json.dumps(updated, ensure_ascii=False, indent=2)

    def _event_exists(
        self,
        events: list[dict[str, Any]],
        event: dict[str, Any],
    ) -> bool:
        for existing in self._owned_events(events):
            if existing["event_id"] != event["event_id"]:
                continue
            if existing != event:
                raise UsageStoreError(
                    "Usage event identity is already registered"
                )
            return True
        return False

    def _append_event_if_current(
        self,
        *,
        expected: str | None,
        replacement: str,
        event: dict[str, Any],
    ) -> bool:
        try:
            if expected is None:
                return self._backend.write_text_if_absent(
                    self._event_relative_path,
                    replacement,
                    content_type=_EVENT_CONTENT_TYPE,
                )
            return self._backend.replace_text_if_equal(
                self._event_relative_path,
                expected=expected,
                replacement=replacement,
                content_type=_EVENT_CONTENT_TYPE,
            )
        except StateBackendError as exc:
            try:
                observed = self._read_text(self._event_relative_path)
                observed_events = self._parse_events(observed)
            except UsageStoreError:
                pass
            else:
                if self._event_exists(observed_events, event):
                    return True
            raise UsageStoreError("Usage state could not be written") from exc

    def _summary_is_current_for_event(self, event: dict[str, Any]) -> bool:
        try:
            _event_raw, events, summary_raw = self._read_state_documents()
            if not self._event_exists(events, event):
                return False
            derived = self._derive_summaries(events)
            self._parse_and_verify_summaries(summary_raw, derived)
        except UsageStoreError:
            return False
        return True

    def _replace_summary_if_current(
        self,
        *,
        expected: str | None,
        replacement: str,
        event: dict[str, Any],
    ) -> bool:
        try:
            if expected is None:
                return self._backend.write_text_if_absent(
                    self._summary_relative_path,
                    replacement,
                    content_type=_SUMMARY_CONTENT_TYPE,
                )
            return self._backend.replace_text_if_equal(
                self._summary_relative_path,
                expected=expected,
                replacement=replacement,
                content_type=_SUMMARY_CONTENT_TYPE,
            )
        except StateBackendError as exc:
            if self._summary_is_current_for_event(event):
                return True
            raise UsageStoreError("Usage state could not be written") from exc

    def _load_or_repair_state(self) -> tuple[
        str | None,
        list[dict[str, Any]],
        dict[str, Any],
        dict[str, UsageSummary],
    ] | None:
        """Load verified state or finish one CAS-committed trailing event."""
        event_raw, events, summary_raw = self._read_state_documents()
        derived = self._derive_summaries(events)
        try:
            summary_data, summaries = self._parse_and_verify_summaries(
                summary_raw,
                derived,
            )
        except UsageStoreError as current_error:
            if self._state_documents_changed(
                event_raw=event_raw,
                summary_raw=summary_raw,
            ):
                return None
            if not events or events[-1].get("tenant_id") != self._tenant_id:
                raise

            prefix_derived = self._derive_summaries(events[:-1])
            try:
                summary_data, _prefix_summaries = (
                    self._parse_and_verify_summaries(
                        summary_raw,
                        prefix_derived,
                    )
                )
            except UsageStoreError:
                raise current_error

            replacement = self._summary_document(summary_data, derived)
            self._replace_summary_if_current(
                expected=summary_raw,
                replacement=replacement,
                event=events[-1],
            )
            return None

        return event_raw, events, summary_data, summaries

    def _finish_committed_event(self, event: dict[str, Any]) -> None:
        _event_raw, events, _summary_data, _summaries = (
            self._load_verified_state()
        )
        if self._event_exists(events, event):
            return
        raise UsageStoreError("Usage event was not persisted")

    def record(self, event: UsageEvent) -> bool:
        """Append one event and refresh all owned monthly summaries."""
        if not isinstance(event, UsageEvent):
            raise UsageStoreError("Invalid usage event")
        if event.tenant_id != self._tenant_id:
            raise ValueError("Usage event tenant ownership mismatch")
        event_data = self._validate_event(asdict(event), owned=True)

        with self._lock:
            for _ in range(_MAX_RECORD_ATTEMPTS):
                event_raw, events, summary_data, _summaries = (
                    self._load_verified_state()
                )
                if self._event_exists(events, event_data):
                    return False

                year_month = event.timestamp[:7]
                existing_month = summary_data.get(year_month)
                if (
                    isinstance(existing_month, dict)
                    and existing_month.get("tenant_id") != self._tenant_id
                ):
                    raise UsageStoreError(
                        "Usage summary month is owned by another tenant"
                    )

                separator = (
                    ""
                    if event_raw is None
                    or event_raw == ""
                    or event_raw.endswith("\n")
                    else "\n"
                )
                line = json.dumps(event_data, ensure_ascii=False) + "\n"
                replacement = f"{event_raw or ''}{separator}{line}"
                if not self._append_event_if_current(
                    expected=event_raw,
                    replacement=replacement,
                    event=event_data,
                ):
                    continue

                self._finish_committed_event(event_data)
                return True

        raise UsageStoreError(
            "Usage state changed too many times to persist safely"
        )

    def get_current_month(self) -> UsageSummary | None:
        return self.get_month(datetime.now(timezone.utc).strftime("%Y-%m"))

    def get_month(self, year_month: str) -> UsageSummary | None:
        if not isinstance(year_month, str) or _YEAR_MONTH.fullmatch(year_month) is None:
            raise UsageStoreError("Invalid usage month")
        with self._lock:
            _raw, _events, data, summaries = self._load_verified_state()
        if year_month in data and year_month not in summaries:
            raise UsageStoreError("Usage summary month is owned by another tenant")
        return summaries.get(year_month)

    def get_daily_usage(self, days: int = 30) -> list[dict[str, int | float | str]]:
        if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 366:
            raise UsageStoreError("Invalid usage history window")
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        with self._lock:
            _raw, events, _data, _summaries = self._load_verified_state()

        daily: dict[str, dict[str, int | float | str]] = {}
        for event in self._owned_events(events):
            timestamp = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
            if timestamp < cutoff:
                continue
            date_key = timestamp.strftime("%Y-%m-%d")
            bucket = daily.setdefault(
                date_key,
                {
                    "date": date_key,
                    "generations": 0,
                    "tokens": 0,
                    "cost": 0.0,
                },
            )
            if event["event_type"] == "doc.generate":
                bucket["generations"] += 1
            bucket["tokens"] += event["tokens_total"]
            bucket["cost"] += float(event["cost_usd"])
        return sorted(daily.values(), key=lambda item: str(item["date"]))

    def get_total_month_cost(self) -> float:
        summary = self.get_current_month()
        return summary.total_cost_usd if summary is not None else 0.0

    def check_limit(self, plan: Any) -> dict[str, int | float | bool]:
        summary = self.get_current_month()
        generations_used = summary.total_generations if summary is not None else 0
        tokens_used = summary.total_tokens if summary is not None else 0

        generations_limit = getattr(plan, "monthly_generations", None)
        tokens_limit = getattr(plan, "monthly_tokens", None)
        for field_name, value in (
            ("generation limit", generations_limit),
            ("token limit", tokens_limit),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < -1
            ):
                raise UsageStoreError(f"Invalid usage plan {field_name}")

        if generations_limit == -1 and tokens_limit == -1:
            return {
                "within_limit": True,
                "generations_used": generations_used,
                "generations_limit": generations_limit,
                "tokens_used": tokens_used,
                "tokens_limit": tokens_limit,
                "percent_used": 0,
            }

        generation_percent = (
            (generations_used / generations_limit) * 100
            if generations_limit > 0
            else 0.0
        )
        token_percent = (
            (tokens_used / tokens_limit) * 100
            if tokens_limit > 0
            else 0.0
        )
        within_limit = not (
            (generations_limit != -1 and generations_used >= generations_limit)
            or (tokens_limit != -1 and tokens_used >= tokens_limit)
        )
        return {
            "within_limit": within_limit,
            "generations_used": generations_used,
            "generations_limit": generations_limit,
            "tokens_used": tokens_used,
            "tokens_limit": tokens_limit,
            "percent_used": round(max(generation_percent, token_percent), 1),
        }
