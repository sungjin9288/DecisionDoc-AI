#!/usr/bin/env python3
"""Capture repeatable local mock browser evidence for the H126-H128 review chain."""

# ruff: noqa: E402
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping
from uuid import uuid4

from playwright.sync_api import sync_playwright


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.schemas import (
    NormalizedProcurementOpportunity,
    ProcurementChecklistItem,
    ProcurementDecisionUpsert,
    ProcurementHardFilterResult,
    ProcurementRecommendation,
    ProcurementScoreBreakdownItem,
)
from app.schemas.decision_evidence import (
    GuidedDecisionReviewDispositionReceipt,
    GuidedDecisionReviewHandoffResponse,
    GuidedDecisionReviewRecheckReceipt,
    require_complete_guided_decision_review_handoff,
    require_complete_guided_decision_review_recheck_receipt,
)
from app.services.guided_decision_review_service import GuidedDecisionReviewService
from app.storage.procurement_store import ProcurementDecisionStore
from scripts.capture_ui_flow_evidence import (
    LocalServer,
    _start_local_server,
    _stop_local_server,
)


SCHEMA_VERSION = "decisiondoc.guided_review_local_demo.v1"
RECEIPT_SCOPE = (
    "repeatable local mock browser capture for H126-H128 Guided Decision Review"
)
DEFAULT_ARTIFACT_DIR = REPO_ROOT / "evidence"
DEFAULT_RECEIPT_PATH = (
    DEFAULT_ARTIFACT_DIR / "cli-logs" / "guided_review_h126_h128_demo.json"
)
SCREENSHOT_DIRECTORY = "screenshots"
DOWNLOAD_DIRECTORY = "cli-logs"

STEP_ORDER = (
    "project_created",
    "decision_evidence_map_loaded",
    "guided_review_rendered",
    "handoff_downloaded",
    "unchanged_recheck_downloaded",
    "acknowledged_unchanged_disposition_downloaded",
)
SCREENSHOT_FILENAMES = {
    "project_created": "guided-review-demo-01-project-created.png",
    "guided_review": "guided-review-demo-02-guided-review.png",
    "handoff": "guided-review-demo-03-handoff.png",
    "unchanged_recheck": "guided-review-demo-04-unchanged-recheck.png",
    "disposition": "guided-review-demo-05-disposition.png",
}
DOWNLOAD_FILENAMES = {
    "handoff": "guided-review-demo-h126-handoff.json",
    "recheck": "guided-review-demo-h127-unchanged-recheck.json",
    "disposition": "guided-review-demo-h128-acknowledged-unchanged-disposition.json",
}
EXCLUDED_EXTERNAL_ACTIONS = (
    "provider_api_execution",
    "g2b_live_api_execution",
    "aws_runtime_execution",
    "dataset_upload",
    "training_execution",
    "model_promotion",
    "production_service_resume",
    "bid_submission",
    "legal_approval",
    "contractual_commitment",
)
AUTHORITY_FIELDS = (
    "mutation",
    "approval",
    "export_execution",
    "provider_call",
    "bid_submission",
    "legal_contractual_commitment",
)
STAGE_OBSERVATIONS = {
    "Decision": "needs_attention",
    "Evidence": "needs_attention",
    "Review": "not_observed",
    "Documents": "not_observed",
}
UNOBSERVED_STAGE_REASON = (
    "Review and Documents remain not_observed because the local capture creates no "
    "persisted procurement review or project document."
)
TOP_LEVEL_FIELDS = {
    "schema_version",
    "status",
    "scope",
    "local_environment",
    "steps",
    "screenshots",
    "downloaded_receipts",
    "contracts",
    "stage_observations",
    "unobserved_stage_reason",
    "browser_boundary",
    "excluded_external_actions",
    "browser_http_errors",
}
BINDING_FIELDS = {"filename", "size_bytes", "sha256"}


@dataclass(frozen=True)
class GuidedReviewDemoEvidenceResult:
    screenshots: dict[str, Path]
    downloaded_receipts: dict[str, Path]
    receipt_path: Path
    browser_http_errors: list[dict[str, str | int]]


@contextmanager
def _artifact_lock(artifact_dir: Path):
    lock_key = _sha256(str(artifact_dir.resolve()).encode("utf-8"))
    lock_name = f"decisiondoc-guided-review-{lock_key}.lock"
    lock_path = Path(tempfile.gettempdir()) / lock_name
    with lock_path.open("a+b") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _temporary_sibling(path: Path) -> Path:
    return path.with_name(f".{path.stem}.{uuid4().hex}.tmp{path.suffix}")


def _fsync_parent(path: Path) -> None:
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _replace_atomic(temporary: Path, path: Path) -> None:
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    _fsync_parent(path)


def _write_bytes_atomic(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = _temporary_sibling(path)
    try:
        with temporary.open("wb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_parent(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _write_json_atomic(path: Path, payload: Mapping[str, object]) -> None:
    _write_bytes_atomic(
        path,
        (
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8"),
    )


def _artifact_binding(path: Path) -> dict[str, object]:
    body = path.read_bytes()
    return {
        "filename": path.name,
        "size_bytes": len(body),
        "sha256": _sha256(body),
    }


def _require_exact_false_mapping(
    value: object,
    *,
    fields: tuple[str, ...],
    label: str,
) -> None:
    if not isinstance(value, Mapping) or set(value) != set(fields):
        raise ValueError(f"{label} fields are invalid")
    if any(value[field] is not False for field in fields):
        raise ValueError(f"{label} must keep every external action false")


def _require_no_sensitive_runtime_values(value: object) -> None:
    if isinstance(value, Mapping):
        for nested in value.values():
            _require_no_sensitive_runtime_values(nested)
        return
    if isinstance(value, list):
        for nested in value:
            _require_no_sensitive_runtime_values(nested)
        return
    if not isinstance(value, str):
        return
    forbidden = (
        "http://",
        "https://",
        "127.0.0.1",
        "localhost",
        "password",
        "access_token",
        "refresh_token",
    )
    if any(token in value.lower() for token in forbidden):
        raise ValueError("receipt contains a credential or remote URL value")


def _require_artifact_binding(
    value: object,
    *,
    artifact_dir: Path,
    expected_filename: str,
    label: str,
) -> bytes:
    if not isinstance(value, Mapping) or set(value) != BINDING_FIELDS:
        raise ValueError(f"{label} artifact binding fields are invalid")
    filename = value["filename"]
    if (
        not isinstance(filename, str)
        or filename != expected_filename
        or Path(filename).name != filename
        or "/" in filename
        or "\\" in filename
        or ".." in filename
    ):
        raise ValueError(f"{label} artifact basename is invalid")
    size_bytes = value["size_bytes"]
    if (
        not isinstance(size_bytes, int)
        or isinstance(size_bytes, bool)
        or size_bytes <= 0
    ):
        raise ValueError(f"{label} artifact size is invalid")
    if not _is_sha256(value["sha256"]):
        raise ValueError(f"{label} artifact hash is invalid")
    path = artifact_dir / filename
    if not path.is_file():
        raise ValueError(f"{label} artifact is missing")
    body = path.read_bytes()
    if len(body) != size_bytes or _sha256(body) != value["sha256"]:
        raise ValueError(f"{label} artifact binding does not match")
    return body


def _require_complete_disposition(
    receipt: GuidedDecisionReviewDispositionReceipt,
) -> None:
    missing = set(type(receipt).model_fields) - receipt.model_fields_set
    if missing:
        raise ValueError("disposition receipt is missing required contract fields")
    authority = receipt.authority
    missing_authority = set(type(authority).model_fields) - authority.model_fields_set
    if missing_authority:
        raise ValueError("disposition receipt authority is missing contract fields")
    require_complete_guided_decision_review_recheck_receipt(
        receipt.source_recheck_receipt,
    )


def build_guided_review_demo_receipt(
    *,
    screenshots: Mapping[str, Path],
    downloaded_receipts: Mapping[str, Path],
    browser_http_errors: list[dict[str, str | int]],
) -> dict[str, object]:
    """Build the stable, secret-free summary around locally retained artifacts."""
    handoff_binding = _artifact_binding(downloaded_receipts["handoff"])
    recheck_binding = _artifact_binding(downloaded_receipts["recheck"])
    disposition_binding = _artifact_binding(downloaded_receipts["disposition"])
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "passed",
        "scope": RECEIPT_SCOPE,
        "local_environment": {
            "server": "ephemeral",
            "provider": "mock",
            "storage": "temporary",
            "remote_url_used": False,
            "credentials_recorded": False,
        },
        "steps": list(STEP_ORDER),
        "screenshots": {
            key: _artifact_binding(path) for key, path in screenshots.items()
        },
        "downloaded_receipts": {
            "handoff": handoff_binding,
            "recheck": recheck_binding,
            "disposition": disposition_binding,
        },
        "contracts": {
            "decision_evidence_map": "decision_evidence_map.v1",
            "handoff": "guided-decision-review-handoff.v1",
            "handoff_sha256": handoff_binding["sha256"],
            "recheck": "guided-decision-review-recheck-receipt.v1",
            "recheck_sha256": recheck_binding["sha256"],
            "recheck_status": "unchanged",
            "disposition": "guided-decision-review-disposition-receipt.v1",
            "disposition_sha256": disposition_binding["sha256"],
            "review_disposition": "acknowledged_unchanged",
        },
        "stage_observations": dict(STAGE_OBSERVATIONS),
        "unobserved_stage_reason": UNOBSERVED_STAGE_REASON,
        "browser_boundary": {
            "page_memory_only": True,
            "handoff_persisted": False,
            "recheck_persisted": False,
            "disposition_receipt_persisted": False,
            "reviewer_identity_bound": False,
            "snapshot_atomic": False,
            "requires_recheck_before_reliance": True,
            "operational_approval": False,
            "authority": {field: False for field in AUTHORITY_FIELDS},
        },
        "excluded_external_actions": {
            action: False for action in EXCLUDED_EXTERNAL_ACTIONS
        },
        "browser_http_errors": browser_http_errors,
    }


def validate_guided_review_demo_receipt(
    payload: Mapping[str, object],
    *,
    artifact_dir: Path,
) -> None:
    """Independently bind persisted local evidence to canonical H126-H128 contracts."""
    artifact_dir = Path(artifact_dir).expanduser()
    if set(payload) != TOP_LEVEL_FIELDS:
        raise ValueError("guided review demo receipt fields are invalid")
    if payload["schema_version"] != SCHEMA_VERSION:
        raise ValueError("guided review demo receipt schema_version is unsupported")
    if payload["status"] != "passed":
        raise ValueError("guided review demo receipt status must be passed")
    if payload["scope"] != RECEIPT_SCOPE:
        raise ValueError("guided review demo receipt scope is invalid")
    if payload["local_environment"] != {
        "server": "ephemeral",
        "provider": "mock",
        "storage": "temporary",
        "remote_url_used": False,
        "credentials_recorded": False,
    }:
        raise ValueError("guided review demo receipt local environment is invalid")
    if payload["steps"] != list(STEP_ORDER):
        raise ValueError("guided review demo receipt steps are invalid")

    screenshots = payload["screenshots"]
    if not isinstance(screenshots, Mapping) or set(screenshots) != set(
        SCREENSHOT_FILENAMES
    ):
        raise ValueError("guided review demo receipt screenshots are invalid")
    for key, filename in SCREENSHOT_FILENAMES.items():
        _require_artifact_binding(
            screenshots[key],
            artifact_dir=artifact_dir / SCREENSHOT_DIRECTORY,
            expected_filename=filename,
            label=f"screenshot {key}",
        )

    downloads = payload["downloaded_receipts"]
    if not isinstance(downloads, Mapping) or set(downloads) != set(DOWNLOAD_FILENAMES):
        raise ValueError("guided review demo receipt downloaded receipts are invalid")
    downloaded_bodies = {
        key: _require_artifact_binding(
            downloads[key],
            artifact_dir=artifact_dir / DOWNLOAD_DIRECTORY,
            expected_filename=filename,
            label=f"{key} receipt",
        )
        for key, filename in DOWNLOAD_FILENAMES.items()
    }

    contracts = payload["contracts"]
    if not isinstance(contracts, Mapping) or contracts != {
        "decision_evidence_map": "decision_evidence_map.v1",
        "handoff": "guided-decision-review-handoff.v1",
        "handoff_sha256": contracts.get("handoff_sha256"),
        "recheck": "guided-decision-review-recheck-receipt.v1",
        "recheck_sha256": contracts.get("recheck_sha256"),
        "recheck_status": "unchanged",
        "disposition": "guided-decision-review-disposition-receipt.v1",
        "disposition_sha256": contracts.get("disposition_sha256"),
        "review_disposition": "acknowledged_unchanged",
    }:
        raise ValueError("guided review demo receipt contracts are invalid")
    for key in ("handoff", "recheck", "disposition"):
        if contracts[f"{key}_sha256"] != _sha256(downloaded_bodies[key]):
            raise ValueError(f"{key} artifact hash is not bound to the receipt")

    try:
        handoff = GuidedDecisionReviewHandoffResponse.model_validate_json(
            downloaded_bodies["handoff"],
            strict=True,
        )
        require_complete_guided_decision_review_handoff(handoff, "handoff")
        recheck = GuidedDecisionReviewRecheckReceipt.model_validate_json(
            downloaded_bodies["recheck"],
            strict=True,
        )
        disposition = GuidedDecisionReviewDispositionReceipt.model_validate_json(
            downloaded_bodies["disposition"],
            strict=True,
        )
    except ValueError as exc:
        raise ValueError("downloaded Guided Review artifact is invalid") from exc

    service = GuidedDecisionReviewService()
    if service.serialize(handoff) != downloaded_bodies["handoff"]:
        raise ValueError("handoff artifact is not canonical")
    if recheck.source_handoff_sha256 != contracts["handoff_sha256"]:
        raise ValueError("recheck source handoff binding does not match")
    validated_recheck = service.validate_recheck_receipt(
        recheck,
        expected_sha256=contracts["recheck_sha256"],
        expected_project_id=handoff.project_id,
    )
    if service.serialize_recheck(validated_recheck) != downloaded_bodies["recheck"]:
        raise ValueError("recheck artifact is not canonical")
    _require_complete_disposition(disposition)
    if disposition.source_recheck_receipt_sha256 != contracts["recheck_sha256"]:
        raise ValueError("disposition source recheck binding does not match")
    if (
        service.serialize_recheck(disposition.source_recheck_receipt)
        != downloaded_bodies["recheck"]
    ):
        raise ValueError("disposition nested recheck does not match artifact")
    expected_disposition = service.issue_disposition(
        source_recheck_receipt=validated_recheck,
        source_recheck_receipt_sha256=contracts["recheck_sha256"],
        review_disposition="acknowledged_unchanged",
        expected_project_id=handoff.project_id,
    )
    if disposition.model_dump(mode="json") != expected_disposition.model_dump(
        mode="json"
    ):
        raise ValueError("disposition binding does not match canonical receipt")
    if service.serialize_disposition(disposition) != downloaded_bodies["disposition"]:
        raise ValueError("disposition artifact is not canonical")

    if payload["stage_observations"] != STAGE_OBSERVATIONS:
        raise ValueError("guided review demo receipt stage observations are invalid")
    if payload["unobserved_stage_reason"] != UNOBSERVED_STAGE_REASON:
        raise ValueError(
            "guided review demo receipt unobserved stage reason is invalid"
        )
    boundary = payload["browser_boundary"]
    if not isinstance(boundary, Mapping) or boundary != {
        "page_memory_only": True,
        "handoff_persisted": False,
        "recheck_persisted": False,
        "disposition_receipt_persisted": False,
        "reviewer_identity_bound": False,
        "snapshot_atomic": False,
        "requires_recheck_before_reliance": True,
        "operational_approval": False,
        "authority": boundary.get("authority"),
    }:
        raise ValueError("guided review demo receipt browser boundary is invalid")
    _require_exact_false_mapping(
        boundary["authority"],
        fields=AUTHORITY_FIELDS,
        label="browser authority",
    )
    _require_exact_false_mapping(
        payload["excluded_external_actions"],
        fields=EXCLUDED_EXTERNAL_ACTIONS,
        label="excluded external actions",
    )
    if payload["browser_http_errors"] != []:
        raise ValueError("guided review demo receipt browser HTTP errors are not empty")
    _require_no_sensitive_runtime_values(payload)


def _capture_screenshot(page: Any, path: Path, selector: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = _temporary_sibling(path)
    try:
        page.locator(selector).scroll_into_view_if_needed()
        page.screenshot(path=str(temporary), full_page=False)
        _replace_atomic(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _read_download(download: Any) -> tuple[dict[str, object], bytes]:
    source_path = download.path()
    if source_path is None:
        raise RuntimeError("browser did not expose the Guided Review download")
    body = Path(source_path).read_bytes()
    payload = json.loads(body.decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("Guided Review download was not a JSON object")
    return payload, body


def _assert_false_authority(payload: Mapping[str, object]) -> None:
    authority = payload.get("authority")
    if (
        not isinstance(authority, Mapping)
        or set(authority) != set(AUTHORITY_FIELDS)
        or any(authority[field] is not False for field in AUTHORITY_FIELDS)
    ):
        raise RuntimeError("Guided Review response granted unexpected authority")


def _close_toasts(page: Any) -> None:
    close_buttons = page.locator("#notification-container .notification button")
    while close_buttons.count():
        close_buttons.first.click()


def _record_browser_http_error(
    response: Any,
    browser_http_errors: list[dict[str, str | int]],
) -> None:
    route = response.url.split("?")[0]
    if response.status < 400 or (
        response.status == 404 and route.endswith("/decision-council")
    ):
        return
    browser_http_errors.append(
        {"route": route.rsplit("/", 1)[-1], "status": response.status}
    )


def _project_id_from_browser(project_card: Any) -> str:
    project_id = project_card.first.get_attribute("data-project-open")
    if not isinstance(project_id, str) or not project_id:
        raise RuntimeError("browser did not return the created project id")
    return project_id


def _seed_populated_decision_evidence(*, data_dir: Path, project_id: str) -> None:
    """Use the local store's locked upsert path; this is not a G2B/provider call."""
    ProcurementDecisionStore(base_dir=str(data_dir)).upsert(
        ProcurementDecisionUpsert(
            project_id=project_id,
            tenant_id="system",
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b",
                source_id="LOCAL-GUIDED-REVIEW-001",
                title="로컬 Guided Review 증적 fixture",
                issuer="로컬 fixture",
                budget="4억원",
                deadline="2026-08-31 18:00",
            ),
            hard_filters=[
                ProcurementHardFilterResult(
                    code="security_plan",
                    label="보안 계획",
                    status="unknown",
                    blocking=True,
                    reason="로컬 fixture에서 보안 계획 담당자 확인이 필요합니다.",
                )
            ],
            score_breakdown=[
                ProcurementScoreBreakdownItem(
                    key="security_readiness",
                    label="보안 준비도",
                    score=62.0,
                    weight=0.2,
                    weighted_score=12.4,
                    summary="로컬 fixture의 보완 가능한 준비도입니다.",
                )
            ],
            soft_fit_score=72.0,
            soft_fit_status="scored",
            missing_data=["보안 계획 담당자"],
            checklist_items=[
                ProcurementChecklistItem(
                    category="security_plan",
                    title="보안 계획 담당자 지정",
                    status="action_needed",
                    severity="high",
                    remediation_note="실제 proposal 작업 전에 담당자를 지정합니다.",
                )
            ],
            recommendation=ProcurementRecommendation(
                value="CONDITIONAL_GO",
                summary="보안 계획 담당자를 지정한 뒤 검토를 진행합니다.",
                evidence=["Soft-fit score 72.0"],
                missing_data=["보안 계획 담당자"],
                remediation_notes=["보안 계획 담당자를 지정합니다."],
            ),
        )
    )


def _capture_browser_flow(
    *,
    server: LocalServer,
    data_dir: Path,
    artifact_dir: Path,
    playwright_factory: Callable[[], Any],
    headed: bool,
    slow_mo_ms: int,
) -> tuple[dict[str, Path], dict[str, Path], list[dict[str, str | int]]]:
    screenshots = {
        key: artifact_dir / SCREENSHOT_DIRECTORY / filename
        for key, filename in SCREENSHOT_FILENAMES.items()
    }
    downloads = {
        key: artifact_dir / DOWNLOAD_DIRECTORY / filename
        for key, filename in DOWNLOAD_FILENAMES.items()
    }
    browser_http_errors: list[dict[str, str | int]] = []

    with playwright_factory() as playwright:
        browser = playwright.chromium.launch(
            headless=not headed,
            slow_mo=int(slow_mo_ms or 0),
        )
        context = browser.new_context(viewport={"width": 1440, "height": 1100})
        context.add_init_script("localStorage.setItem('onboarding_done', '1');")
        page = context.new_page()
        page.on(
            "response",
            lambda response: _record_browser_http_error(response, browser_http_errors),
        )
        try:
            page.goto(server.base_url)
            page.wait_for_selector("#login-screen", state="visible", timeout=15000)
            page.fill("#login-username", server.username)
            page.fill("#login-password", server.password)
            page.click("#login-btn")
            page.wait_for_selector(".bundle-card", state="visible", timeout=15000)

            page.locator('[data-page="project-page"]').click()
            page.wait_for_selector(
                "#project-create-btn", state="visible", timeout=10000
            )
            page.click("#project-create-btn")
            page.fill("#proj-name", "Guided Review Local Demo")
            page.click("[data-project-modal-submit]")
            project_card = page.locator("#project-list [data-project-open]")
            project_card.wait_for(state="visible", timeout=15000)
            project_id = _project_id_from_browser(project_card)
            _seed_populated_decision_evidence(data_dir=data_dir, project_id=project_id)
            _close_toasts(page)
            _capture_screenshot(page, screenshots["project_created"], "#project-list")

            project_card.first.click()
            page.wait_for_selector(
                "#decision-evidence-map", state="visible", timeout=20000
            )
            page.wait_for_selector(
                "#guided-decision-review", state="visible", timeout=20000
            )
            _capture_screenshot(
                page, screenshots["guided_review"], "#guided-decision-review"
            )

            handoff_button = page.locator("[data-guided-decision-review-handoff]")
            with page.expect_download(timeout=15000) as handoff_download:
                handoff_button.click()
            handoff, handoff_body = _read_download(handoff_download.value)
            if handoff.get("contract_version") != "guided-decision-review-handoff.v1":
                raise RuntimeError("H126 handoff contract was not returned")
            _assert_false_authority(handoff)
            _write_bytes_atomic(downloads["handoff"], handoff_body)
            _close_toasts(page)
            _capture_screenshot(page, screenshots["handoff"], "#guided-decision-review")

            recheck_button = page.locator("[data-guided-decision-review-recheck]")
            with page.expect_download(timeout=15000) as recheck_download:
                recheck_button.click()
            recheck, recheck_body = _read_download(recheck_download.value)
            if (
                recheck.get("contract_version")
                != "guided-decision-review-recheck-receipt.v1"
                or recheck.get("review_state_status") != "unchanged"
                or recheck.get("source_handoff_sha256") != _sha256(handoff_body)
            ):
                raise RuntimeError("H127 unchanged recheck contract was not returned")
            _assert_false_authority(recheck)
            _write_bytes_atomic(downloads["recheck"], recheck_body)
            _close_toasts(page)
            _capture_screenshot(
                page, screenshots["unchanged_recheck"], "#guided-decision-review"
            )

            disposition_select = page.locator(
                "[data-guided-decision-review-disposition]"
            )
            disposition_select.select_option("acknowledged_unchanged")
            disposition_button = page.locator(
                "[data-guided-decision-review-disposition-download]"
            )
            with page.expect_download(timeout=15000) as disposition_download:
                disposition_button.click()
            disposition, disposition_body = _read_download(disposition_download.value)
            if (
                disposition.get("contract_version")
                != "guided-decision-review-disposition-receipt.v1"
                or disposition.get("review_disposition") != "acknowledged_unchanged"
                or disposition.get("source_recheck_receipt_sha256")
                != _sha256(recheck_body)
            ):
                raise RuntimeError("H128 disposition contract was not returned")
            _assert_false_authority(disposition)
            _write_bytes_atomic(downloads["disposition"], disposition_body)
            storage_keys = page.evaluate(
                """() => [localStorage, sessionStorage]
                  .flatMap(storage => Array.from(
                    { length: storage.length },
                    (_, index) => storage.key(index),
                  ))
                  .filter(key => key?.includes('guided'))"""
            )
            if storage_keys:
                raise RuntimeError("Guided Review state escaped browser page memory")
            _close_toasts(page)
            _capture_screenshot(
                page, screenshots["disposition"], "#guided-decision-review"
            )
        finally:
            context.close()
            browser.close()

    return screenshots, downloads, browser_http_errors


def capture_guided_review_demo_evidence(
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    receipt_path: Path = DEFAULT_RECEIPT_PATH,
    headed: bool = False,
    slow_mo_ms: int = 0,
    playwright_factory: Callable[[], Any] = sync_playwright,
) -> GuidedReviewDemoEvidenceResult:
    """Run a repeatable, local-only H126-H128 browser capture and restore env."""
    artifact_dir = Path(artifact_dir).expanduser()
    receipt_path = Path(receipt_path).expanduser()
    environment_before = dict(os.environ)
    try:
        with _artifact_lock(artifact_dir):
            with tempfile.TemporaryDirectory(
                prefix="decisiondoc-guided-review-demo-"
            ) as temporary:
                data_dir = Path(temporary)
                server: LocalServer | None = None
                try:
                    server = _start_local_server(data_dir)
                    (
                        screenshots,
                        downloads,
                        browser_http_errors,
                    ) = _capture_browser_flow(
                        server=server,
                        data_dir=data_dir,
                        artifact_dir=artifact_dir,
                        playwright_factory=playwright_factory,
                        headed=headed,
                        slow_mo_ms=slow_mo_ms,
                    )
                finally:
                    if server is not None:
                        _stop_local_server(server)

            receipt = build_guided_review_demo_receipt(
                screenshots=screenshots,
                downloaded_receipts=downloads,
                browser_http_errors=browser_http_errors,
            )
            validate_guided_review_demo_receipt(receipt, artifact_dir=artifact_dir)
            _write_json_atomic(receipt_path, receipt)
            return GuidedReviewDemoEvidenceResult(
                screenshots=screenshots,
                downloaded_receipts=downloads,
                receipt_path=receipt_path,
                browser_http_errors=browser_http_errors,
            )
    finally:
        os.environ.clear()
        os.environ.update(environment_before)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture repeatable local mock H126-H128 Guided Review evidence."
    )
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--receipt-path", default=str(DEFAULT_RECEIPT_PATH))
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Validate existing receipt-bound artifacts without starting a browser.",
    )
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--slow-mo-ms", type=int, default=0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    if args.check_only:
        receipt_path = Path(args.receipt_path).expanduser()
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("guided review demo receipt root must be an object")
        validate_guided_review_demo_receipt(
            payload,
            artifact_dir=Path(args.artifact_dir),
        )
        print("Validated persisted H126-H128 Guided Review demo evidence.")
        return 0

    result = capture_guided_review_demo_evidence(
        artifact_dir=Path(args.artifact_dir),
        receipt_path=Path(args.receipt_path),
        headed=bool(args.headed),
        slow_mo_ms=int(args.slow_mo_ms or 0),
    )
    print("Captured repeatable local H126-H128 Guided Review evidence.")
    print(f"receipt: {result.receipt_path}")
    print(f"screenshots: {len(result.screenshots)}")
    print(f"downloaded receipts: {len(result.downloaded_receipts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
