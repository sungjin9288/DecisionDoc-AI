"""Ops investigation and post-deploy report schemas."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class OpsInvestigateRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    window_minutes: int = Field(default=30, ge=1, le=180)
    reason: str = Field(default="", max_length=200)
    stage: Literal["dev", "prod"] | None = None
    force: bool = False
    notify: bool = True


class OpsInvestigateResponse(BaseModel):
    incident_id: str
    summary: dict[str, Any]
    statuspage_incident_url: str | None = None
    report_s3_key: str
    report_md_key: str | None = None
    incident_key: str = ""
    deduped: bool = False
    statuspage_posted: bool | None = None
    statuspage_skipped: bool | None = None
    statuspage_error: str | None = None
    report_json_key: str | None = None  # deprecated: identical to report_s3_key


class PostDeployReportSummary(BaseModel):
    file: str
    status: str
    base_url: str
    started_at: str
    finished_at: str
    skip_smoke: bool = False
    error: str | None = None
    provider_routes: dict[str, str] | None = None
    provider_route_checks: dict[str, str] | None = None
    provider_policy_checks: dict[str, str] | None = None
    provider_policy_issues: dict[str, list[str]] | None = None
    smoke_response_code: str | None = None
    provider_error_code: str | None = None
    smoke_message: str | None = None
    retry_after_seconds: int | None = None
    smoke_exception_type: str | None = None
    smoke_results_available: bool = False
    smoke_results: list[str] = Field(default_factory=list)
    report_workflow_smoke_results_available: bool = False
    report_workflow_smoke_results: list[str] = Field(default_factory=list)


class PostDeployReportCheck(BaseModel):
    name: str
    status: str
    exit_code: int | None = None
    smoke_response_code: str | None = None
    provider_error_code: str | None = None
    smoke_message: str | None = None
    retry_after_seconds: int | None = None
    smoke_exception_type: str | None = None
    failure_line: str | None = None
    stdout: str | None = None
    stderr: str | None = None
    smoke_results_available: bool = False
    smoke_results: list[str] = Field(default_factory=list)
    report_workflow_smoke_results_available: bool = False
    report_workflow_smoke_results: list[str] = Field(default_factory=list)


class PostDeployLatestDetailsResponse(BaseModel):
    status: str
    base_url: str = "-"
    started_at: str = "-"
    finished_at: str = "-"
    skip_smoke: bool = False
    error: str | None = None
    checks: list[PostDeployReportCheck] = Field(default_factory=list)
    provider_routes: dict[str, str] | None = None
    provider_route_checks: dict[str, str] | None = None
    provider_policy_checks: dict[str, str] | None = None
    provider_policy_issues: dict[str, list[str]] | None = None
    smoke_response_code: str | None = None
    provider_error_code: str | None = None
    smoke_message: str | None = None
    retry_after_seconds: int | None = None
    smoke_exception_type: str | None = None
    smoke_results_available: bool = False
    smoke_results: list[str] = Field(default_factory=list)
    report_workflow_smoke_results_available: bool = False
    report_workflow_smoke_results: list[str] = Field(default_factory=list)


class OpsPostDeployReportsResponse(BaseModel):
    report_dir: str
    index_file: str
    latest_report: str
    updated_at: str
    reports: list[PostDeployReportSummary]
    latest_details: PostDeployLatestDetailsResponse | None = None


class OpsPostDeployReportDetailResponse(BaseModel):
    report_dir: str
    report_file: str
    report_path: str
    details: dict[str, Any]


class OpsPostDeployRunRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    skip_smoke: bool = False


class OpsPostDeployRunResponse(BaseModel):
    run_id: str
    status: str
    exit_code: int | None = None
    started_at: str
    finished_at: str
    report_dir: str
    report_file: str | None = None
    report_path: str | None = None
    stdout_tail: list[str] = Field(default_factory=list)
    stderr_tail: list[str] = Field(default_factory=list)
    command: str | None = None
