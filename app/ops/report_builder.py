import json
from typing import Any


class ReportBuilderMixin:
    """Incident report persistence (S3 JSON/Markdown) for OpsInvestigationService."""

    def _write_reports(self, *, report_prefix: str, report: dict[str, Any]) -> None:
        report_json_key = f"{report_prefix}report.json"
        report_md_key = f"{report_prefix}report.md"
        report_json = json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")
        report_md = self._build_markdown(report).encode("utf-8")
        bucket = self._bucket()
        s3 = self._s3()
        s3.put_object(Bucket=bucket, Key=report_json_key, Body=report_json, ContentType="application/json")
        self._s3_put_count += 1
        s3.put_object(Bucket=bucket, Key=report_md_key, Body=report_md, ContentType="text/markdown; charset=utf-8")
        self._s3_put_count += 1

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
