#!/usr/bin/env python3
"""Sync edited Report Quality pilot draft JSON files back into a batch JSONL."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Sequence
from uuid import uuid4


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.report_quality_learning import validate_correction_artifact  # noqa: E402
from scripts.report_quality_pilot_pack_provenance import load_pilot_pack  # noqa: E402


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp.{uuid4().hex}")
    with tmp.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _default_output_path(pack_dir: Path) -> Path:
    existing = sorted(pack_dir.glob("*-drafts.jsonl"))
    if existing:
        return existing[0]
    return pack_dir / f"{pack_dir.name}-drafts.jsonl"


def sync_report_quality_pilot_pack(
    *,
    pack_dir: Path,
    output_path: Path | None = None,
    min_records: int = 3,
    require_ready: bool = False,
) -> dict[str, Any]:
    resolved_pack_dir = pack_dir.expanduser().resolve()
    snapshot = load_pilot_pack(resolved_pack_dir)
    drafts_dir = resolved_pack_dir / "drafts"
    min_records = max(1, int(min_records or 1))
    resolved_output_path = (
        output_path.expanduser().resolve()
        if output_path is not None
        else _default_output_path(resolved_pack_dir).resolve()
    )

    payloads: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    warnings: list[str] = []
    for draft in snapshot.drafts:
        path = draft.path
        payload = draft.payload
        validation = validate_correction_artifact(payload)
        payloads.append(payload)
        row = {
            "path": str(path),
            "artifact_id": validation.get("artifact_id"),
            "ok": bool(validation.get("ok")),
            "ready_for_learning": bool(validation.get("ready_for_learning")),
            "errors": list(validation.get("errors") or []),
            "warnings": list(validation.get("warnings") or []),
        }
        rows.append(row)
        for error in row["errors"]:
            errors.append(f"{path.name}: {error}")
        for warning in row["warnings"]:
            warnings.append(f"{path.name}: {warning}")

    artifact_count = len(rows)
    valid_artifacts = sum(1 for row in rows if row["ok"])
    ready_artifacts = sum(1 for row in rows if row["ready_for_learning"])
    if artifact_count < min_records:
        errors.append(f"artifact_count {artifact_count} is below min_records {min_records}")
    if require_ready and ready_artifacts != artifact_count:
        errors.append("not all artifacts are ready_for_learning")

    jsonl_text = "\n".join(
        json.dumps(payload, ensure_ascii=False, sort_keys=True)
        for payload in payloads
    )
    if jsonl_text:
        jsonl_text += "\n"
    _write_text_atomic(resolved_output_path, jsonl_text)

    ok = valid_artifacts == artifact_count and artifact_count >= min_records and (
        not require_ready or ready_artifacts == artifact_count
    )
    return {
        "report_type": "report_quality_pilot_pack_sync",
        "ok": ok,
        "pack_dir": str(resolved_pack_dir),
        "drafts_dir": str(drafts_dir),
        "output_path": str(resolved_output_path),
        "source_order_applied": snapshot.source_order_applied,
        "min_records": min_records,
        "require_ready": require_ready,
        "artifact_count": artifact_count,
        "valid_artifacts": valid_artifacts,
        "ready_artifacts": ready_artifacts,
        "not_ready_artifacts": artifact_count - ready_artifacts,
        "errors": errors,
        "warnings": warnings,
        "artifacts": rows,
        "side_effect_boundary": {
            "reads_local_draft_json": True,
            "writes_local_jsonl": True,
            "external_dataset_upload_started": False,
            "provider_fine_tune_api_called": False,
            "provider_job_created": False,
            "training_execution_started": False,
            "model_promotion_started": False,
        },
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sync Report Quality pilot draft JSON files into the batch JSONL.",
    )
    parser.add_argument("pack_dir", type=Path, help="Path to reports/report-quality/<batch-id>.")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--min-records", type=int, default=3)
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="Fail unless all synced artifacts are ready_for_learning.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable result.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    try:
        result = sync_report_quality_pilot_pack(
            pack_dir=args.pack_dir,
            output_path=args.output,
            min_records=args.min_records,
            require_ready=args.require_ready,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        status = "PASS" if result["ok"] else "FAIL"
        print(f"{status} report quality pilot pack synced")
        print(f"pack_dir={result['pack_dir']}")
        print(f"output_path={result['output_path']}")
        print(f"artifact_count={result['artifact_count']}")
        print(f"min_records={result['min_records']}")
        print(f"ready_artifacts={result['ready_artifacts']}")
        print(f"not_ready_artifacts={result['not_ready_artifacts']}")
        print("training_boundary=not_authorized")
        for error in result["errors"]:
            print(f"ERROR {error}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
