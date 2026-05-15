#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.report_quality_learning import validate_correction_artifact  # noqa: E402


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("artifact root must be an object")
    return payload


def _is_jsonl_path(path: Path) -> bool:
    return path.suffix.lower() in {".jsonl", ".ndjson"}


def _validate_json_artifact(path: Path, *, require_ready: bool, min_records: int = 1) -> dict[str, Any]:
    try:
        payload = _load_json(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = {
            "ok": False,
            "ready_for_learning": False,
            "errors": [str(exc)],
            "warnings": [],
            "artifact_id": None,
            "schema_version": None,
        }
    else:
        result = validate_correction_artifact(payload)
    if require_ready and not result.get("ready_for_learning"):
        result = dict(result)
        errors = list(result.get("errors") or [])
        errors.append("artifact is not ready_for_learning")
        result["errors"] = errors
        result["ok"] = False
    if min_records > 1:
        result = dict(result)
        errors = list(result.get("errors") or [])
        errors.append(f"artifact_count 1 is below min_records {min_records}")
        result["errors"] = errors
        result["ok"] = False
    return result


def _validate_jsonl_artifacts(path: Path, *, require_ready: bool, min_records: int = 1) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    file_errors: list[str] = []
    file_warnings: list[str] = []

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return {
            "report_type": "report_quality_correction_artifact_file_validation",
            "source_format": "jsonl",
            "ok": False,
            "ready_for_learning": False,
            "require_ready": require_ready,
            "min_records": min_records,
            "artifact_count": 0,
            "valid_artifacts": 0,
            "ready_artifacts": 0,
            "not_ready_artifacts": 0,
            "errors": [str(exc)],
            "warnings": [],
            "results": [],
        }

    for line_no, raw_line in enumerate(lines, start=1):
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            payload = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            file_errors.append(f"line {line_no}: invalid JSON ({exc.msg})")
            continue
        if not isinstance(payload, dict):
            file_errors.append(f"line {line_no}: artifact root must be an object")
            continue
        validation = validate_correction_artifact(payload)
        results.append({
            "line": line_no,
            "artifact_id": validation.get("artifact_id"),
            "schema_version": validation.get("schema_version"),
            "ok": bool(validation.get("ok")),
            "ready_for_learning": bool(validation.get("ready_for_learning")),
            "errors": list(validation.get("errors") or []),
            "warnings": list(validation.get("warnings") or []),
        })

    artifact_count = len(results)
    valid_artifacts = sum(1 for item in results if item["ok"])
    ready_artifacts = sum(1 for item in results if item["ready_for_learning"])
    if artifact_count == 0 and not file_errors:
        file_errors.append("jsonl file contains no correction artifact records")
    if artifact_count < min_records:
        file_errors.append(f"artifact_count {artifact_count} is below min_records {min_records}")
    if require_ready and ready_artifacts != artifact_count:
        file_errors.append("not all artifacts are ready_for_learning")

    for item in results:
        for warning in item["warnings"]:
            file_warnings.append(f"line {item['line']}: {warning}")

    return {
        "report_type": "report_quality_correction_artifact_file_validation",
        "source_format": "jsonl",
        "ok": not file_errors and valid_artifacts == artifact_count,
        "ready_for_learning": not file_errors and artifact_count > 0 and ready_artifacts == artifact_count,
        "require_ready": require_ready,
        "min_records": min_records,
        "artifact_count": artifact_count,
        "valid_artifacts": valid_artifacts,
        "ready_artifacts": ready_artifacts,
        "not_ready_artifacts": artifact_count - ready_artifacts,
        "errors": file_errors,
        "warnings": file_warnings,
        "results": results,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a DecisionDoc report quality correction artifact.")
    parser.add_argument("artifact", type=Path, help="Path to correction artifact JSON or exported JSONL.")
    parser.add_argument(
        "--jsonl",
        action="store_true",
        help="Treat input as exported JSONL even if the file extension is not .jsonl/.ndjson.",
    )
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="Fail unless every artifact is ready_for_learning.",
    )
    parser.add_argument(
        "--min-records",
        type=int,
        default=1,
        help="Minimum artifact records required for a JSONL batch. Defaults to 1.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable validation result.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    is_jsonl = args.jsonl or _is_jsonl_path(args.artifact)
    min_records = max(1, int(args.min_records or 1))
    result = (
        _validate_jsonl_artifacts(args.artifact, require_ready=args.require_ready, min_records=min_records)
        if is_jsonl
        else _validate_json_artifact(args.artifact, require_ready=args.require_ready, min_records=min_records)
    )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif is_jsonl:
        if result["ok"]:
            print("PASS report quality correction artifact JSONL validated")
        else:
            print("FAIL report quality correction artifact JSONL validation failed")
        print(f"ready_for_learning={str(result['ready_for_learning']).lower()}")
        print(f"artifact_count={result['artifact_count']}")
        print(f"min_records={result['min_records']}")
        print(f"ready_artifacts={result['ready_artifacts']}")
        print(f"not_ready_artifacts={result['not_ready_artifacts']}")
        for error in result["errors"]:
            print(f"ERROR {error}")
        for item in result["results"]:
            for error in item["errors"]:
                print(f"ERROR line {item['line']}: {error}")
            for warning in item["warnings"]:
                print(f"WARN line {item['line']}: {warning}")
    elif result["ok"]:
        print("PASS report quality correction artifact validated")
        print(f"ready_for_learning={str(result['ready_for_learning']).lower()}")
        if result["artifact_id"]:
            print(f"artifact_id={result['artifact_id']}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    else:
        print("FAIL report quality correction artifact validation failed")
        print(f"ready_for_learning={str(result['ready_for_learning']).lower()}")
        for error in result["errors"]:
            print(f"ERROR {error}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
