import json
import logging
import os
from collections import Counter
from datetime import datetime
from typing import Any

from app.ops.investigation_helpers import _to_int

logger = logging.getLogger("decisiondoc.ops")


class MetricsCollectorMixin:
    """CloudWatch metrics/logs collection and summary building for OpsInvestigationService."""

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
            self._cw_metric_calls += 1
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
            logger.warning("CloudWatch metrics collection failed", exc_info=True)
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
            self._cw_log_calls += 1
            response = self._logs().filter_log_events(**params)
            events = response.get("events", [])
            if not isinstance(events, list):
                events = []
            self._log_events_returned = len(events)
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
            logger.warning("CloudWatch Logs collection failed", exc_info=True)

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
