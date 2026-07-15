#!/usr/bin/env python3
"""Validate a persisted mock-only Report Quality pilot handoff demo receipt."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.report_quality_pilot_handoff_demo_receipt import (  # noqa: E402
    EXPECTED_EXTERNAL_ACTIONS,
    SCHEMA_VERSION,
    validate_demo_receipt,
)


CHECK_SCHEMA_VERSION = "decisiondoc.report_quality_pilot_handoff_demo_check.v1"
MAX_RECEIPT_SIZE_BYTES = 64 * 1024


def _read_receipt(path: Path) -> tuple[Path, bytes, dict[str, Any]]:
    expanded = path.expanduser()
    if expanded.is_symlink():
        raise ValueError("symlink demo receipt files are not allowed")
    resolved = expanded.resolve()
    if not resolved.is_file():
        raise ValueError(f"demo receipt does not exist: {resolved}")
    content = resolved.read_bytes()
    if len(content) > MAX_RECEIPT_SIZE_BYTES:
        raise ValueError("demo receipt is too large")
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("demo receipt must contain valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("demo receipt root must be an object")
    return resolved, content, payload


def check_demo_receipt(path: Path) -> dict[str, Any]:
    """Read and validate one receipt without writing files or calling external systems."""
    resolved, content, payload = _read_receipt(path)
    summary = validate_demo_receipt(payload)
    return {
        "schema_version": CHECK_SCHEMA_VERSION,
        "ok": True,
        "receipt_path": str(resolved),
        "receipt_sha256": hashlib.sha256(content).hexdigest(),
        "receipt_schema_version": SCHEMA_VERSION,
        "summary": summary,
        "external_actions_excluded": list(EXPECTED_EXTERNAL_ACTIONS),
        "side_effect_boundary": {
            "reads_local_receipt": True,
            "writes_local_files": False,
            "provider_api_execution": False,
            "aws_runtime_execution": False,
            "dataset_upload": False,
            "provider_job_creation": False,
            "training_execution": False,
            "model_promotion": False,
            "production_service_resume": False,
        },
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt_path", type=Path)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    try:
        result = check_demo_receipt(args.receipt_path)
    except (OSError, ValueError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("PASS report quality pilot handoff demo receipt validated")
        print(f"receipt_path={result['receipt_path']}")
        print(f"receipt_sha256={result['receipt_sha256']}")
        print(f"artifact_count={result['summary']['artifact_count']}")
        print("review_evidence=simulated_demo_input")
        print("human_review_claimed=false")
        print("training_boundary=not_authorized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
