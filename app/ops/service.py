import logging
import os
from datetime import datetime, timedelta
from time import perf_counter
from typing import Any, Callable

from app.config import is_enabled
from app.ops.aws_clients import AwsClientsMixin
from app.ops.incident_dedup import IncidentDedupMixin
from app.ops.investigation_helpers import (
    _env_int,
    _iso_utc,
    _normalize_reason_for_key,
    _sanitize_reason_for_storage,
)
from app.ops.metrics_collector import MetricsCollectorMixin
from app.ops.post_deploy import PostDeployMixin
from app.ops.report_builder import ReportBuilderMixin
from app.ops.statuspage import StatuspageClient

logger = logging.getLogger("decisiondoc.ops")


class OpsNotifyFailedError(Exception):
    pass


class OpsInvestigationService(
    PostDeployMixin,
    IncidentDedupMixin,
    ReportBuilderMixin,
    MetricsCollectorMixin,
    AwsClientsMixin,
):
    def __init__(
        self,
        *,
        cloudwatch_client: Any | None = None,
        logs_client: Any | None = None,
        s3_client: Any | None = None,
        statuspage_client: StatuspageClient | None = None,
        max_log_events: int = 100,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._cloudwatch_client = cloudwatch_client
        self._logs_client = logs_client
        self._s3_client = s3_client
        self.statuspage_client = statuspage_client or StatuspageClient()
        self.max_log_events = max_log_events
        self.now_provider = now_provider
        self._cw_metric_calls = 0
        self._cw_log_calls = 0
        self._log_events_returned = 0
        self._s3_put_count = 0

    def investigate(
        self,
        *,
        window_minutes: int,
        reason: str,
        stage: str,
        request_id: str,
        force: bool = False,
        notify: bool = True,
    ) -> dict[str, Any]:
        self._reset_kpi_counters()
        now = self._now()
        reason_norm = _normalize_reason_for_key(reason)
        reason_safe = _sanitize_reason_for_storage(reason)
        ttl_seconds = _env_int("DECISIONDOC_INVESTIGATE_DEDUP_TTL_SECONDS", 300)
        bucket_seconds = _env_int("DECISIONDOC_INVESTIGATE_BUCKET_SECONDS", 300)
        status_update_min_seconds = _env_int("DECISIONDOC_INVESTIGATE_STATUSPAGE_UPDATE_MIN_SECONDS", 600)
        statuspage_strict = is_enabled(os.getenv("DECISIONDOC_OPS_STATUSPAGE_STRICT", "0"))

        incident_key = self._build_incident_key(
            stage=stage,
            window_minutes=window_minutes,
            reason_norm=reason_norm,
            now=now,
            bucket_seconds=bucket_seconds,
        )
        index_key = self._index_key(incident_key)
        index_data = self._read_s3_json(index_key)
        started = perf_counter()
        metrics_ms = 0
        logs_ms = 0
        report_ms = 0
        s3_ms = 0
        statuspage_ms = 0

        if index_data and not force and self._is_dedupe_hit(index_data, now=now, ttl_seconds=ttl_seconds):
            status_url = self._index_statuspage_url(index_data)
            status_posted = False
            status_skipped = not notify
            status_error: str | None = None
            status = self._index_status(index_data)
            incident_id = status.get("incident_id", "")
            if (
                notify
                and incident_id
                and self._should_post_dedupe_update(
                index_data=index_data,
                now=now,
                min_seconds=status_update_min_seconds,
                )
            ):
                try:
                    status_started = perf_counter()
                    self.statuspage_client.post_investigating_update(incident_id=incident_id)
                    statuspage_ms += self._elapsed_ms(status_started)
                    status_posted = True
                    status["last_update_at"] = _iso_utc(now)
                    status["last_state"] = "investigating"
                    s3_started = perf_counter()
                    index_data["statuspage"] = status
                    self._write_s3_json(index_key, index_data)
                    s3_ms += self._elapsed_ms(s3_started)
                except Exception:
                    statuspage_ms += self._elapsed_ms(status_started)
                    status_error = "Status page notification failed."
                    logger.warning("Statuspage update failed (dedup path)", exc_info=True)
                    self._emit_kpi_log(
                        request_id=request_id,
                        incident_key=incident_key,
                        deduped=True,
                        force=force,
                        notify=notify,
                        window_minutes=window_minutes,
                        started=started,
                        metrics_ms=metrics_ms,
                        logs_ms=logs_ms,
                        report_ms=report_ms,
                        s3_ms=s3_ms,
                        statuspage_ms=statuspage_ms,
                        statuspage_posted=False,
                        error_code="OPS_NOTIFY_FAILED",
                    )
                    if statuspage_strict:
                        raise OpsNotifyFailedError("Incident notification failed.")

            summary = index_data.get("summary")
            if not isinstance(summary, dict):
                summary = {}
            latest_prefix = index_data.get("latest_report_prefix", "")
            report_key = f"{latest_prefix}report.json" if isinstance(latest_prefix, str) and latest_prefix else ""
            report_md_key_dedup = f"{latest_prefix}report.md" if isinstance(latest_prefix, str) and latest_prefix else None
            response = {
                "incident_id": incident_key,
                "incident_key": incident_key,
                "deduped": True,
                "summary": summary,
                "statuspage_incident_url": status_url,
                "report_s3_key": report_key,
                "report_json_key": report_key,
                "report_md_key": report_md_key_dedup,
                "statuspage_posted": status_posted,
                "statuspage_skipped": status_skipped,
                "statuspage_error": status_error,
            }
            self._emit_kpi_log(
                request_id=request_id,
                incident_key=incident_key,
                deduped=True,
                force=force,
                notify=notify,
                window_minutes=window_minutes,
                started=started,
                metrics_ms=metrics_ms,
                logs_ms=logs_ms,
                report_ms=report_ms,
                s3_ms=s3_ms,
                statuspage_ms=statuspage_ms,
                statuspage_posted=status_posted,
                error_code="OPS_NOTIFY_FAILED" if status_error else None,
            )
            return response

        metrics_started = perf_counter()
        metrics = self._collect_metrics(start=now - timedelta(minutes=window_minutes), end=now, stage=stage)
        metrics_ms = self._elapsed_ms(metrics_started)
        logs_started = perf_counter()
        logs = self._collect_logs(start=now - timedelta(minutes=window_minutes), end=now)
        logs_ms = self._elapsed_ms(logs_started)
        summary = self._build_summary(metrics=metrics, logs=logs)

        run_id = self._build_run_id(now)
        report_prefix = self._report_prefix(incident_key=incident_key, run_id=run_id)
        report_json_key = f"{report_prefix}report.json"
        report_md_key_new = f"{report_prefix}report.md"

        status = self._index_status(index_data)
        status_url = status.get("incident_url")
        status_posted = False
        status_skipped = not notify
        status_error: str | None = None
        if notify:
            try:
                status_started = perf_counter()
                if status.get("incident_id"):
                    self.statuspage_client.post_investigating_update(incident_id=status["incident_id"])
                    status_posted = True
                    status["last_state"] = "investigating"
                    status["last_update_at"] = _iso_utc(now)
                else:
                    created = self.statuspage_client.create_investigating_incident(stage=stage, incident_key=incident_key)
                    status_posted = True
                    status["incident_id"] = created["incident_id"]
                    status["incident_url"] = created.get("incident_url", "")
                    status["last_state"] = "investigating"
                    status["last_update_at"] = _iso_utc(now)
                statuspage_ms = self._elapsed_ms(status_started)
                status_url = status.get("incident_url")
            except Exception:
                statuspage_ms = self._elapsed_ms(status_started)
                status_error = "Status page notification failed."
                logger.warning("Statuspage notification failed (new investigation)", exc_info=True)
                if statuspage_strict:
                    self._emit_kpi_log(
                        request_id=request_id,
                        incident_key=incident_key,
                        deduped=False,
                        force=force,
                        notify=notify,
                        window_minutes=window_minutes,
                        started=started,
                        metrics_ms=metrics_ms,
                        logs_ms=logs_ms,
                        report_ms=report_ms,
                        s3_ms=s3_ms,
                        statuspage_ms=statuspage_ms,
                        statuspage_posted=False,
                        error_code="OPS_NOTIFY_FAILED",
                    )
                    raise OpsNotifyFailedError("Incident notification failed.")

        report_started = perf_counter()
        report = {
            "incident_id": incident_key,
            "incident_key": incident_key,
            "request_id": request_id,
            "stage": stage,
            "window_minutes": window_minutes,
            "deduped": False,
            "generated_at": _iso_utc(now),
            "window_start": _iso_utc(now - timedelta(minutes=window_minutes)),
            "window_end": _iso_utc(now),
            "reason": reason_safe,
            "summary": summary,
            "metrics": metrics,
            "signals": {
                "error_code_aggregation": logs["error_code_counts"],
                "sample_request_ids": logs["sample_request_ids"],
                "token_counts": logs["token_counts"],
            },
            "statuspage": {
                "posted": status_posted,
                "error": status_error,
                "incident_id": status.get("incident_id", ""),
                "incident_url": status_url,
            },
        }
        report_ms = self._elapsed_ms(report_started)
        s3_started = perf_counter()
        self._write_reports(report_prefix=report_prefix, report=report)

        next_index = {
            "incident_key": incident_key,
            "stage": stage,
            "window_minutes": window_minutes,
            "reason": reason_safe,
            "updated_at": _iso_utc(now),
            "ttl_seconds": ttl_seconds,
            "latest_report_prefix": report_prefix,
            "summary": summary,
            "statuspage": {
                "incident_id": status.get("incident_id", ""),
                "incident_url": status_url,
                "last_state": status.get("last_state", "investigating"),
                "last_update_at": status.get("last_update_at"),
            },
        }
        self._write_s3_json(index_key, next_index)
        s3_ms = self._elapsed_ms(s3_started)

        response = {
            "incident_id": incident_key,
            "incident_key": incident_key,
            "deduped": False,
            "summary": summary,
            "statuspage_incident_url": status_url,
            "report_s3_key": report_json_key,
            "report_json_key": report_json_key,
            "report_md_key": report_md_key_new,
            "statuspage_posted": status_posted,
            "statuspage_skipped": status_skipped,
            "statuspage_error": status_error,
        }
        self._emit_kpi_log(
            request_id=request_id,
            incident_key=incident_key,
            deduped=False,
            force=force,
            notify=notify,
            window_minutes=window_minutes,
            started=started,
            metrics_ms=metrics_ms,
            logs_ms=logs_ms,
            report_ms=report_ms,
            s3_ms=s3_ms,
            statuspage_ms=statuspage_ms,
            statuspage_posted=status_posted,
            error_code="OPS_NOTIFY_FAILED" if status_error else None,
        )
        return response
