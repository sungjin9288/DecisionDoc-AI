#!/usr/bin/env python3
"""Prove the complete Report Quality pilot handoff with local mock data."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence

from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.report_quality_pilot_package import (  # noqa: E402
    verify_pilot_review_package,
)
from scripts.apply_report_quality_review_decisions import (  # noqa: E402
    apply_review_decisions,
    create_review_decision_template,
)
from scripts.create_report_quality_pilot_pack import (  # noqa: E402
    create_report_quality_pilot_pack,
)
from scripts.local_write_once import write_bytes_once  # noqa: E402
from scripts.manage_report_quality_pilot_handoff import (  # noqa: E402
    finalize_report_quality_pilot_handoff,
    write_verified_handoff_browser_summary,
)
from scripts.report_quality_pilot_handoff_demo_receipt import (  # noqa: E402
    ARTIFACT_COUNT,
    COMPLETED_STAGES,
    EXPECTED_EXECUTION_MODE,
    EXPECTED_EXTERNAL_ACTIONS,
    SCHEMA_VERSION,
    validate_demo_receipt,
)
from scripts.run_report_quality_learning_demo import (  # noqa: E402
    DemoError,
    create_ready_report_quality_artifact,
    local_demo_environment,
    now_iso,
    request_json,
    validate_ready_report_quality_export,
)


DEFAULT_RECEIPT_PATH = (
    Path(tempfile.gettempdir())
    / "decisiondoc-report-quality-pilot-handoff-demo.json"
)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _resolve_receipt_path(path: Path) -> Path:
    expanded = path.expanduser()
    if expanded.is_symlink():
        raise ValueError("symlink demo receipt outputs are not allowed")
    resolved = expanded.resolve()
    if resolved.suffix.lower() != ".json":
        raise ValueError("demo receipt output must use the .json extension")
    if resolved.exists():
        raise ValueError(f"refusing to overwrite existing demo receipt: {resolved}")
    return resolved


def _create_api_pilot_package(
    client: TestClient,
    *,
    artifact_ids: Sequence[str],
) -> dict[str, Any]:
    ordered_ids = list(reversed(artifact_ids))
    preview = request_json(
        client,
        "POST",
        "/report-workflows/learning/correction-artifacts/pilot-export/preview",
        payload={"artifact_ids": ordered_ids},
    )
    if preview.get("ordered_artifact_ids") != ordered_ids:
        raise DemoError("pilot preview did not preserve the requested artifact order")
    if preview.get("validation") != {
        "ok": True,
        "resolved_artifact_count": ARTIFACT_COUNT,
        "ready_artifact_count": ARTIFACT_COUNT,
    }:
        raise DemoError("pilot preview did not confirm three ready artifacts")

    response = client.post(
        "/report-workflows/learning/correction-artifacts/pilot-export/package",
        json={
            "artifact_ids": ordered_ids,
            "preview_sha256": preview["export_sha256"],
        },
    )
    if response.status_code != 200:
        raise DemoError(
            "pilot package request returned "
            f"HTTP {response.status_code}: {response.text}"
        )
    package = response.content
    package_sha256 = _sha256(package)
    if response.headers.get("x-decisiondoc-pilot-package-sha256") != package_sha256:
        raise DemoError("pilot package response SHA-256 header does not match its bytes")
    if response.headers.get("x-decisiondoc-training-authorized") != "false":
        raise DemoError("pilot package response crossed the training authorization boundary")

    manifest = verify_pilot_review_package(package)
    if manifest.get("ordered_artifact_ids") != ordered_ids:
        raise DemoError("verified pilot package artifact order is incorrect")
    return {
        "content": package,
        "sha256": package_sha256,
        "export_sha256": preview["export_sha256"],
        "ordered_artifact_ids": ordered_ids,
        "manifest": manifest,
    }


def _complete_local_handoff(
    root: Path,
    *,
    source_package: dict[str, Any],
) -> dict[str, Any]:
    source_path = root / "report-quality-pilot-source.zip"
    write_bytes_once(source_path, source_package["content"], label="demo source package")

    imported = create_report_quality_pilot_pack(
        batch_id="local-pilot-handoff-demo",
        output_root=root / "review-packs",
        source_package=source_path,
    )
    pack_dir = Path(imported["output_dir"])
    decisions_path = pack_dir / "review_decisions.demo-accepted.json"
    receipt_path = pack_dir / "review_decision_application_receipt.demo.json"
    create_review_decision_template(
        pack_dir=pack_dir,
        output_path=decisions_path,
    )
    review = apply_review_decisions(
        pack_dir=pack_dir,
        decisions_path=decisions_path,
        require_ready=True,
        receipt_path=receipt_path,
    )
    if review.get("ok") is not True or review.get("ready_decisions") != ARTIFACT_COUNT:
        raise DemoError("simulated local review did not produce three ready decisions")

    handoff_path = root / "report-quality-pilot-handoff.zip"
    handoff = finalize_report_quality_pilot_handoff(
        pack_dir=pack_dir,
        output_path=handoff_path,
    )
    browser_summary_path = root / "report-quality-pilot-handoff-summary.html"
    verified = write_verified_handoff_browser_summary(
        handoff_path.read_bytes(),
        output_path=browser_summary_path,
    )
    if verified.get("browser_summary_sha256") != _sha256(browser_summary_path.read_bytes()):
        raise DemoError("verified browser summary SHA-256 does not match its output bytes")
    if verified.get("ordered_artifact_ids") != source_package["ordered_artifact_ids"]:
        raise DemoError("final handoff artifact order differs from the API package")

    return {
        "review": review,
        "handoff": handoff,
        "verification": verified,
    }


def run_demo() -> dict[str, Any]:
    """Run the mock API, simulated review, and verified handoff as one local proof."""
    with tempfile.TemporaryDirectory(
        prefix="decisiondoc-report-quality-pilot-handoff-demo-"
    ) as temporary_dir:
        root = Path(temporary_dir)
        with local_demo_environment(root / "runtime"):
            from app.main import create_app

            with TestClient(create_app()) as client:
                artifacts = [
                    create_ready_report_quality_artifact(
                        client,
                        title=f"Report quality pilot handoff demo {index}",
                    )
                    for index in range(1, ARTIFACT_COUNT + 1)
                ]
                artifact_ids = [artifact["artifact_id"] for artifact in artifacts]
                exported = validate_ready_report_quality_export(
                    client,
                    expected_artifact_ids=artifact_ids,
                )
                source_package = _create_api_pilot_package(
                    client,
                    artifact_ids=artifact_ids,
                )

            local = _complete_local_handoff(root, source_package=source_package)

    review = local["review"]
    handoff = local["handoff"]
    verification = local["verification"]
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "status": "passed",
        "generated_at": now_iso(),
        "execution_mode": dict(EXPECTED_EXECUTION_MODE),
        "api_pilot_package": {
            "artifact_count": ARTIFACT_COUNT,
            "ready_artifact_count": exported["ready_artifact_count"],
            "ordered_artifact_ids": source_package["ordered_artifact_ids"],
            "export_sha256": source_package["export_sha256"],
            "package_sha256": source_package["sha256"],
            "package_validation_passed": True,
        },
        "local_review": {
            "source_bound": True,
            "decision_count": review["decision_count"],
            "ready_decisions": review["ready_decisions"],
            "receipt_sha256": review["receipt_sha256"],
            "simulated": True,
        },
        "handoff": {
            "artifact_count": verification["artifact_count"],
            "ordered_artifact_ids": verification["ordered_artifact_ids"],
            "package_sha256": handoff["package_sha256"],
            "browser_summary_sha256": verification["browser_summary_sha256"],
            "exact_browser_summary_verified": True,
            "source_bound": verification["source_bound"],
            "training_authorized": verification["training_authorized"],
            "temporary_artifacts_retained": False,
        },
        "completed_stages": list(COMPLETED_STAGES),
        "external_actions": dict(EXPECTED_EXTERNAL_ACTIONS),
    }
    validate_demo_receipt(receipt)
    return receipt


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the full local mock Report Quality pilot handoff and write a "
            "write-once JSON receipt."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_RECEIPT_PATH,
        help=f"Receipt path (default: {DEFAULT_RECEIPT_PATH})",
    )
    return parser.parse_args(list(argv))


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    try:
        output_path = _resolve_receipt_path(args.output)
        receipt = run_demo()
        write_bytes_once(output_path, _json_bytes(receipt), label="demo receipt")
    except (DemoError, OSError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
                ensure_ascii=False,
            )
        )
        return 1

    print(json.dumps(receipt, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
