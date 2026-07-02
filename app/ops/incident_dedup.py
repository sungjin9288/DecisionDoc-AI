import hashlib
import logging
from datetime import datetime
from typing import Any

from app.observability.logging import log_event
from app.ops.investigation_helpers import _parse_iso_utc

logger = logging.getLogger("decisiondoc.ops")


class IncidentDedupMixin:
    """Incident key derivation, dedup-window checks, and KPI logging for OpsInvestigationService."""

    def _reset_kpi_counters(self) -> None:
        self._cw_metric_calls = 0
        self._cw_log_calls = 0
        self._log_events_returned = 0
        self._s3_put_count = 0

    def _build_incident_key(
        self,
        *,
        stage: str,
        window_minutes: int,
        reason_norm: str,
        now: datetime,
        bucket_seconds: int,
    ) -> str:
        bucket = int(now.timestamp()) // bucket_seconds
        material = f"{stage}|{window_minutes}|{bucket}|{reason_norm}"
        digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]
        return f"inc-{digest}"

    def _emit_kpi_log(
        self,
        *,
        request_id: str,
        incident_key: str,
        deduped: bool,
        force: bool,
        notify: bool,
        window_minutes: int,
        started: float,
        metrics_ms: int,
        logs_ms: int,
        report_ms: int,
        s3_ms: int,
        statuspage_ms: int,
        statuspage_posted: bool,
        error_code: str | None,
    ) -> None:
        event = {
            "event": "ops.investigate.completed",
            "request_id": request_id,
            "incident_key": incident_key,
            "deduped": deduped,
            "force": force,
            "notify": notify,
            "window_minutes": window_minutes,
            "latency_ms_total": self._elapsed_ms(started),
            "metrics_ms": max(0, metrics_ms),
            "logs_ms": max(0, logs_ms),
            "report_ms": max(0, report_ms),
            "s3_ms": max(0, s3_ms),
            "statuspage_ms": max(0, statuspage_ms),
            "cw_metric_calls": self._cw_metric_calls,
            "cw_log_calls": self._cw_log_calls,
            "log_events_returned": self._log_events_returned,
            "s3_put_count": self._s3_put_count,
            "statuspage_posted": statuspage_posted,
        }
        if error_code:
            event["error_code"] = error_code
        log_event(logger, event)

    def _is_dedupe_hit(self, index_data: dict[str, Any], *, now: datetime, ttl_seconds: int) -> bool:
        updated_at = _parse_iso_utc(str(index_data.get("updated_at", "")))
        if updated_at is None:
            return False
        age_seconds = int((now - updated_at).total_seconds())
        return age_seconds >= 0 and age_seconds < ttl_seconds

    def _should_post_dedupe_update(self, *, index_data: dict[str, Any], now: datetime, min_seconds: int) -> bool:
        status = self._index_status(index_data)
        last_update = _parse_iso_utc(str(status.get("last_update_at", "")))
        if last_update is None:
            return True
        return int((now - last_update).total_seconds()) >= min_seconds

    def _index_status(self, index_data: dict[str, Any] | None) -> dict[str, Any]:
        if isinstance(index_data, dict):
            status = index_data.get("statuspage")
            if isinstance(status, dict):
                return dict(status)
        return {}

    def _index_statuspage_url(self, index_data: dict[str, Any]) -> str | None:
        status = self._index_status(index_data)
        url = status.get("incident_url")
        if isinstance(url, str) and url:
            return url
        return None
