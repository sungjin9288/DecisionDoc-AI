import hashlib
import json
import os
import re
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any, Callable
from uuid import uuid4

from app.ops.statuspage import StatuspageClient


class OpsNotifyFailedError(Exception):
    pass


def _to_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(round(value))
    return None


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        parsed = int(raw)
    except ValueError:
        return default
    if parsed <= 0:
        return default
    return parsed


def _iso_utc(dt: datetime) -> str:
    return dt.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso_utc(value: str) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _normalize_reason_for_key(reason: str) -> str:
    text = reason.replace("\r", " ").replace("\n", " ").strip().lower()
    text = re.sub(r"\s+", " ", text)
    if len(text) > 80:
        text = text[:80]
    return text


def _sanitize_reason_for_storage(reason: str) -> str:
    text = _normalize_reason_for_key(reason)
    text = re.sub(r"[^a-z0-9 .,:;!?()/_-]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > 80:
        text = text[:80]
    return text


class OpsInvestigationService:
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

    def investigate(
        self,
        *,
        window_minutes: int,
        reason: str,
        stage: str,
        request_id: str,
        force: bool = False,
    ) -> dict[str, Any]:
        now = self._now()
        reason_norm = _normalize_reason_for_key(reason)
        reason_safe = _sanitize_reason_for_storage(reason)
        ttl_seconds = _env_int("DECISIONDOC_INVESTIGATE_DEDUP_TTL_SECONDS", 300)
        bucket_seconds = _env_int("DECISIONDOC_INVESTIGATE_BUCKET_SECONDS", 300)
        status_update_min_seconds = _env_int("DECISIONDOC_INVESTIGATE_STATUSPAGE_UPDATE_MIN_SECONDS", 600)
        statuspage_strict = os.getenv("DECISIONDOC_OPS_STATUSPAGE_STRICT", "0").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

        incident_key = self._build_incident_key(
            stage=stage,
            window_minutes=window_minutes,
            reason_norm=reason_norm,
            now=now,
            bucket_seconds=bucket_seconds,
        )
        index_key = self._index_key(incident_key)
        index_data = self._read_s3_json(index_key)

        if index_data and not force and self._is_dedupe_hit(index_data, now=now, ttl_seconds=ttl_seconds):
            status_url = self._index_statuspage_url(index_data)
            status_posted = False
            status_error: str | None = None
            status = self._index_status(index_data)
            incident_id = status.get("incident_id", "")
            if incident_id and self._should_post_dedupe_update(
                index_data=index_data,
                now=now,
                min_seconds=status_update_min_seconds,
            ):
                try:
                    self.statuspage_client.post_investigating_update(incident_id=incident_id)
                    status_posted = True
                    status["last_update_at"] = _iso_utc(now)
                    status["last_state"] = "investigating"
                    index_data["statuspage"] = status
                    self._write_s3_json(index_key, index_data)
                except Exception:
                    status_error = "Status page notification failed."
                    if statuspage_strict:
                        raise OpsNotifyFailedError("Incident notification failed.")

            summary = index_data.get("summary")
            if not isinstance(summary, dict):
                summary = {}
            latest_prefix = index_data.get("latest_report_prefix", "")
            report_key = f"{latest_prefix}report.json" if isinstance(latest_prefix, str) and latest_prefix else ""
            return {
                "incident_id": incident_key,
                "incident_key": incident_key,
                "deduped": True,
                "summary": summary,
                "statuspage_incident_url": status_url,
                "report_s3_key": report_key,
                "statuspage_posted": status_posted,
                "statuspage_error": status_error,
            }

        metrics = self._collect_metrics(start=now - timedelta(minutes=window_minutes), end=now, stage=stage)
        logs = self._collect_logs(start=now - timedelta(minutes=window_minutes), end=now)
        summary = self._build_summary(metrics=metrics, logs=logs)

        run_id = self._build_run_id(now)
        report_prefix = self._report_prefix(incident_key=incident_key, run_id=run_id)
        report_json_key = f"{report_prefix}report.json"

        status = self._index_status(index_data)
        status_url = status.get("incident_url")
        status_posted = False
        status_error: str | None = None
        try:
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
            status_url = status.get("incident_url")
        except Exception:
            status_error = "Status page notification failed."
            if statuspage_strict:
                raise OpsNotifyFailedError("Incident notification failed.")

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

        return {
            "incident_id": incident_key,
            "incident_key": incident_key,
            "deduped": False,
            "summary": summary,
            "statuspage_incident_url": status_url,
            "report_s3_key": report_json_key,
            "statuspage_posted": status_posted,
            "statuspage_error": status_error,
        }

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

    def _write_reports(self, *, report_prefix: str, report: dict[str, Any]) -> None:
        report_json_key = f"{report_prefix}report.json"
        report_md_key = f"{report_prefix}report.md"
        report_json = json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")
        report_md = self._build_markdown(report).encode("utf-8")
        bucket = self._bucket()
        s3 = self._s3()
        s3.put_object(Bucket=bucket, Key=report_json_key, Body=report_json, ContentType="application/json")
        s3.put_object(Bucket=bucket, Key=report_md_key, Body=report_md, ContentType="text/markdown; charset=utf-8")

    def _build_markdown(self, report: dict[str, Any]) -> str:
        summary = report.get("summary", {})
        counts = summary.get("counts", {})
        p95 = summary.get("p95_timings_ms", {})
        statuspage = report.get("statuspage", {})
        lines = [
            "# Investigation Report",
            "",
            f"- incident_key: `{report.get('incident_key', '')}`",
            f"- stage: `{report.get('stage', '')}`",
            f"- window_minutes: `{report.get('window_minutes', '')}`",
            f"- generated_at: `{report.get('generated_at', '')}`",
            f"- statuspage_posted: `{statuspage.get('posted', False)}`",
            "",
            "## Summary Counts",
            "",
            f"- lambda_invocations: `{counts.get('lambda_invocations', 0)}`",
            f"- lambda_errors: `{counts.get('lambda_errors', 0)}`",
            f"- lambda_throttles: `{counts.get('lambda_throttles', 0)}`",
            f"- api_count: `{counts.get('api_count', 0)}`",
            f"- api_4xx: `{counts.get('api_4xx', 0)}`",
            f"- api_5xx: `{counts.get('api_5xx', 0)}`",
            f"- failed_events: `{counts.get('failed_events', 0)}`",
            f"- llm_usage_samples: `{counts.get('llm_usage_samples', 0)}`",
            "",
            "## P95 Timings (ms)",
            "",
            f"- lambda_duration: `{p95.get('lambda_duration', 0)}`",
            f"- api_integration_latency: `{p95.get('api_integration_latency', 0)}`",
            "",
            "## Top Error Codes",
            "",
        ]
        for item in summary.get("top_error_codes", []):
            if isinstance(item, dict):
                lines.append(f"- `{item.get('code', '')}`: `{item.get('count', 0)}`")
        return "\n".join(lines).strip() + "\n"

    def _collect_metrics(self, *, start: datetime, end: datetime, stage: str) -> dict[str, Any]:
        function_name = (
            os.getenv("DECISIONDOC_LAMBDA_FUNCTION_NAME", "").strip()
            or os.getenv("AWS_LAMBDA_FUNCTION_NAME", "").strip()
            or f"decisiondoc-ai-{stage}"
        )
        api_id = os.getenv("DECISIONDOC_HTTP_API_ID", "").strip()
        result = {
            "lambda": {
                "invocations": 0,
                "errors": 0,
                "throttles": 0,
                "duration_p95_ms": None,
            },
            "api_gateway": {
                "count": 0,
                "4xx": 0,
                "5xx": 0,
                "integration_latency_p95_ms": None,
            },
        }
        if not function_name:
            return result

        queries = [
            self._metric_query(
                query_id="lambda_invocations",
                namespace="AWS/Lambda",
                metric_name="Invocations",
                dimensions=[{"Name": "FunctionName", "Value": function_name}],
                stat="Sum",
            ),
            self._metric_query(
                query_id="lambda_errors",
                namespace="AWS/Lambda",
                metric_name="Errors",
                dimensions=[{"Name": "FunctionName", "Value": function_name}],
                stat="Sum",
            ),
            self._metric_query(
                query_id="lambda_throttles",
                namespace="AWS/Lambda",
                metric_name="Throttles",
                dimensions=[{"Name": "FunctionName", "Value": function_name}],
                stat="Sum",
            ),
            self._metric_query(
                query_id="lambda_duration_p95",
                namespace="AWS/Lambda",
                metric_name="Duration",
                dimensions=[{"Name": "FunctionName", "Value": function_name}],
                stat="p95",
            ),
        ]
        if api_id:
            dims = [{"Name": "ApiId", "Value": api_id}, {"Name": "Stage", "Value": stage}]
            queries.extend(
                [
                    self._metric_query(
                        query_id="api_count",
                        namespace="AWS/ApiGateway",
                        metric_name="Count",
                        dimensions=dims,
                        stat="Sum",
                    ),
                    self._metric_query(
                        query_id="api_4xx",
                        namespace="AWS/ApiGateway",
                        metric_name="4XXError",
                        dimensions=dims,
                        stat="Sum",
                    ),
                    self._metric_query(
                        query_id="api_5xx",
                        namespace="AWS/ApiGateway",
                        metric_name="5XXError",
                        dimensions=dims,
                        stat="Sum",
                    ),
                    self._metric_query(
                        query_id="api_integration_latency_p95",
                        namespace="AWS/ApiGateway",
                        metric_name="IntegrationLatency",
                        dimensions=dims,
                        stat="p95",
                    ),
                ]
            )

        try:
            response = self._cloudwatch().get_metric_data(
                MetricDataQueries=queries,
                StartTime=start,
                EndTime=end,
                ScanBy="TimestampDescending",
                MaxDatapoints=600,
            )
            metric_map = {item.get("Id"): item for item in response.get("MetricDataResults", []) if isinstance(item, dict)}
            result["lambda"]["invocations"] = self._sum_metric(metric_map.get("lambda_invocations"))
            result["lambda"]["errors"] = self._sum_metric(metric_map.get("lambda_errors"))
            result["lambda"]["throttles"] = self._sum_metric(metric_map.get("lambda_throttles"))
            result["lambda"]["duration_p95_ms"] = self._p95_metric(metric_map.get("lambda_duration_p95"))
            result["api_gateway"]["count"] = self._sum_metric(metric_map.get("api_count"))
            result["api_gateway"]["4xx"] = self._sum_metric(metric_map.get("api_4xx"))
            result["api_gateway"]["5xx"] = self._sum_metric(metric_map.get("api_5xx"))
            result["api_gateway"]["integration_latency_p95_ms"] = self._p95_metric(
                metric_map.get("api_integration_latency_p95")
            )
            return result
        except Exception:
            return result

    def _collect_logs(self, *, start: datetime, end: datetime) -> dict[str, Any]:
        error_codes: Counter[str] = Counter()
        sample_request_ids: list[str] = []
        token_prompt_sum = 0
        token_output_sum = 0
        token_total_sum = 0
        usage_samples = 0
        failed_events = 0
        events_scanned = 0

        log_group = os.getenv("DECISIONDOC_LOG_GROUP", "").strip() or self._default_lambda_log_group()
        if not log_group:
            return {
                "error_code_counts": {},
                "sample_request_ids": [],
                "failed_events": 0,
                "events_scanned": 0,
                "token_counts": {
                    "samples": 0,
                    "llm_prompt_tokens_sum": 0,
                    "llm_output_tokens_sum": 0,
                    "llm_total_tokens_sum": 0,
                    "llm_total_tokens_avg": 0,
                },
            }

        params = {
            "logGroupName": log_group,
            "startTime": int(start.timestamp() * 1000),
            "endTime": int(end.timestamp() * 1000),
            "limit": self.max_log_events,
        }
        try:
            response = self._logs().filter_log_events(**params)
            events = response.get("events", [])
            if not isinstance(events, list):
                events = []
            for event in events:
                if not isinstance(event, dict):
                    continue
                events_scanned += 1
                message = event.get("message", "")
                if not isinstance(message, str):
                    continue
                try:
                    payload = json.loads(message)
                except ValueError:
                    continue
                if not isinstance(payload, dict):
                    continue

                error_code = payload.get("error_code")
                if isinstance(error_code, str) and error_code:
                    error_codes[error_code] += 1
                if payload.get("event") == "request.failed":
                    failed_events += 1

                request_id = payload.get("request_id")
                if isinstance(request_id, str) and request_id and request_id not in sample_request_ids:
                    if len(sample_request_ids) < 10:
                        sample_request_ids.append(request_id)

                prompt_tokens = _to_int(payload.get("llm_prompt_tokens"))
                output_tokens = _to_int(payload.get("llm_output_tokens"))
                total_tokens = _to_int(payload.get("llm_total_tokens"))
                if total_tokens is None and prompt_tokens is None and output_tokens is None:
                    continue
                usage_samples += 1
                token_prompt_sum += prompt_tokens or 0
                token_output_sum += output_tokens or 0
                token_total_sum += total_tokens or 0
        except Exception:
            pass

        avg_total = int(round(token_total_sum / usage_samples)) if usage_samples > 0 else 0
        return {
            "error_code_counts": dict(error_codes),
            "sample_request_ids": sample_request_ids,
            "failed_events": failed_events,
            "events_scanned": events_scanned,
            "token_counts": {
                "samples": usage_samples,
                "llm_prompt_tokens_sum": token_prompt_sum,
                "llm_output_tokens_sum": token_output_sum,
                "llm_total_tokens_sum": token_total_sum,
                "llm_total_tokens_avg": avg_total,
            },
        }

    def _build_summary(self, *, metrics: dict[str, Any], logs: dict[str, Any]) -> dict[str, Any]:
        error_items = sorted(logs["error_code_counts"].items(), key=lambda item: (-item[1], item[0]))[:5]
        return {
            "counts": {
                "lambda_invocations": metrics["lambda"]["invocations"],
                "lambda_errors": metrics["lambda"]["errors"],
                "lambda_throttles": metrics["lambda"]["throttles"],
                "api_count": metrics["api_gateway"]["count"],
                "api_4xx": metrics["api_gateway"]["4xx"],
                "api_5xx": metrics["api_gateway"]["5xx"],
                "failed_events": logs["failed_events"],
                "log_events_scanned": logs["events_scanned"],
                "llm_usage_samples": logs["token_counts"]["samples"],
            },
            "p95_timings_ms": {
                "lambda_duration": metrics["lambda"]["duration_p95_ms"],
                "api_integration_latency": metrics["api_gateway"]["integration_latency_p95_ms"],
            },
            "top_error_codes": [{"code": code, "count": count} for code, count in error_items],
            "sample_request_ids": logs["sample_request_ids"],
        }

    def _metric_query(
        self,
        *,
        query_id: str,
        namespace: str,
        metric_name: str,
        dimensions: list[dict[str, str]],
        stat: str,
    ) -> dict[str, Any]:
        return {
            "Id": query_id,
            "MetricStat": {
                "Metric": {
                    "Namespace": namespace,
                    "MetricName": metric_name,
                    "Dimensions": dimensions,
                },
                "Period": 60,
                "Stat": stat,
            },
            "ReturnData": True,
        }

    def _sum_metric(self, item: dict[str, Any] | None) -> int:
        if not isinstance(item, dict):
            return 0
        values = item.get("Values")
        if not isinstance(values, list):
            return 0
        total = 0
        for value in values:
            numeric = _to_int(value)
            if numeric is not None:
                total += numeric
        return total

    def _p95_metric(self, item: dict[str, Any] | None) -> int | None:
        if not isinstance(item, dict):
            return None
        values = item.get("Values")
        if not isinstance(values, list) or not values:
            return None
        numeric_values = [v for v in (_to_int(value) for value in values) if v is not None]
        if not numeric_values:
            return None
        return max(numeric_values)

    def _default_lambda_log_group(self) -> str:
        function_name = os.getenv("AWS_LAMBDA_FUNCTION_NAME", "").strip()
        if not function_name:
            function_name = os.getenv("DECISIONDOC_LAMBDA_FUNCTION_NAME", "").strip()
        if not function_name:
            return ""
        return f"/aws/lambda/{function_name}"

    def _bucket(self) -> str:
        bucket = os.getenv("DECISIONDOC_S3_BUCKET", "").strip()
        if not bucket:
            raise RuntimeError("Ops investigation storage is not configured.")
        return bucket

    def _prefix(self) -> str:
        prefix = os.getenv("DECISIONDOC_S3_PREFIX", "decisiondoc-ai/").strip()
        if prefix and not prefix.endswith("/"):
            prefix = f"{prefix}/"
        return prefix

    def _index_key(self, incident_key: str) -> str:
        return f"{self._prefix()}reports/incidents/index/{incident_key}.json"

    def _report_prefix(self, *, incident_key: str, run_id: str) -> str:
        return f"{self._prefix()}reports/incidents/{incident_key}/{run_id}/"

    def _build_run_id(self, now: datetime) -> str:
        return f"{now.strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:4]}"

    def _read_s3_json(self, key: str) -> dict[str, Any] | None:
        try:
            obj = self._s3().get_object(Bucket=self._bucket(), Key=key)
            raw = obj["Body"].read().decode("utf-8")
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
            return None
        except Exception:
            return None

    def _write_s3_json(self, key: str, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self._s3().put_object(Bucket=self._bucket(), Key=key, Body=data, ContentType="application/json")

    def _cloudwatch(self):
        if self._cloudwatch_client is not None:
            return self._cloudwatch_client
        try:
            import boto3  # type: ignore
        except Exception as exc:  # pragma: no cover - runtime dependent
            raise RuntimeError("AWS SDK unavailable.") from exc
        self._cloudwatch_client = boto3.client("cloudwatch")
        return self._cloudwatch_client

    def _logs(self):
        if self._logs_client is not None:
            return self._logs_client
        try:
            import boto3  # type: ignore
        except Exception as exc:  # pragma: no cover - runtime dependent
            raise RuntimeError("AWS SDK unavailable.") from exc
        self._logs_client = boto3.client("logs")
        return self._logs_client

    def _s3(self):
        if self._s3_client is not None:
            return self._s3_client
        try:
            import boto3  # type: ignore
        except Exception as exc:  # pragma: no cover - runtime dependent
            raise RuntimeError("AWS SDK unavailable.") from exc
        self._s3_client = boto3.client("s3")
        return self._s3_client

    def _now(self) -> datetime:
        if self.now_provider is not None:
            now = self.now_provider()
            if now.tzinfo is None:
                return now.replace(tzinfo=UTC)
            return now.astimezone(UTC)
        return datetime.now(UTC)
