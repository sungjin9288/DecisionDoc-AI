from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.procurement_decision_package_service import (  # noqa: E402
    apply_procurement_review_draft,
    build_pending_procurement_review_receipt,
    record_procurement_review_decision,
    render_procurement_review_receipt_workspace,
    validate_procurement_review_receipt,
    write_bytes_atomic,
)


DEFAULT_REVIEW_WORKSPACE_NAME = "procurement_review_receipt.html"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create, record, or validate a procurement review receipt."
    )
    subparsers = parser.add_subparsers(dest="operation", required=True)

    for operation in ("init", "validate"):
        operation_parser = subparsers.add_parser(operation)
        operation_parser.add_argument("packet", type=Path)
        operation_parser.add_argument("--receipt", type=Path, required=True)

    record_parser = subparsers.add_parser("record")
    record_parser.add_argument("packet", type=Path)
    record_parser.add_argument("--receipt", type=Path, required=True)
    record_parser.add_argument("--reviewer", required=True)
    record_parser.add_argument("--decision", required=True)
    record_parser.add_argument("--rationale", required=True)
    record_parser.add_argument("--reviewed-at", required=True)

    render_parser = subparsers.add_parser("render")
    render_parser.add_argument("packet", type=Path)
    render_parser.add_argument("--receipt", type=Path, required=True)
    render_parser.add_argument("--output", type=Path)

    apply_parser = subparsers.add_parser("apply-draft")
    apply_parser.add_argument("packet", type=Path)
    apply_parser.add_argument("--receipt", type=Path, required=True)
    apply_parser.add_argument("--draft", type=Path, required=True)
    return parser.parse_args()


def _read_json_object(path: Path, *, label: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be an object")
    return payload


def _read_receipt(path: Path) -> dict[str, Any]:
    return _read_json_object(path, label="procurement review receipt")


def _write_receipt(path: Path, receipt: dict[str, Any]) -> None:
    content = (json.dumps(receipt, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    write_bytes_atomic(path, content)


def _review_workspace_path(args: argparse.Namespace) -> Path:
    receipt_path = args.receipt.resolve()
    requested = args.output or Path(DEFAULT_REVIEW_WORKSPACE_NAME)
    output_path = (
        requested.resolve()
        if requested.is_absolute()
        else (receipt_path.parent / requested).resolve()
    )
    if output_path.parent != receipt_path.parent:
        raise ValueError("procurement review workspace must be written beside the receipt")
    if output_path in {receipt_path, args.packet.resolve()}:
        raise ValueError("procurement review workspace must not overwrite source evidence")
    return output_path


def _render_review_workspace(
    args: argparse.Namespace,
    *,
    receipt: dict[str, Any],
    receipt_content: bytes,
    packet_content: bytes,
) -> None:
    output_path = _review_workspace_path(args)
    packet_link = Path(
        os.path.relpath(args.packet.resolve(), output_path.parent)
    ).as_posix()
    receipt_link = Path(
        os.path.relpath(args.receipt.resolve(), output_path.parent)
    ).as_posix()
    workspace = render_procurement_review_receipt_workspace(
        receipt,
        packet_content,
        receipt_content=receipt_content,
        packet_path=packet_link,
        receipt_path=receipt_link,
    )
    write_bytes_atomic(output_path, workspace.encode("utf-8"))


def _success_result(
    *,
    args: argparse.Namespace,
    receipt_content: bytes,
    validation: dict[str, Any],
) -> dict[str, object]:
    return {
        "status": "passed",
        "operation": args.operation,
        "packet_path": str(args.packet),
        "receipt_path": str(args.receipt),
        "receipt_sha256": hashlib.sha256(receipt_content).hexdigest(),
        "receipt_size_bytes": len(receipt_content),
        **validation,
    }


def _failure_result(args: argparse.Namespace, exc: Exception) -> dict[str, object]:
    return {
        "status": "failed",
        "operation": args.operation,
        "packet_path": str(args.packet),
        "receipt_path": str(args.receipt),
        "error_type": type(exc).__name__,
        "error": str(exc),
    }


def _emit(result: dict[str, object], *, exit_code: int) -> int:
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return exit_code


def main() -> int:
    args = _parse_args()
    try:
        packet_content = args.packet.read_bytes()
        if args.operation == "init":
            if args.receipt.exists():
                raise ValueError(
                    f"refusing to overwrite existing review receipt: {args.receipt}"
                )
            receipt = build_pending_procurement_review_receipt(packet_content)
            validate_procurement_review_receipt(receipt, packet_content)
            _write_receipt(args.receipt, receipt)
        elif args.operation == "record":
            receipt = _read_receipt(args.receipt)
            receipt = record_procurement_review_decision(
                receipt,
                packet_content,
                reviewer=args.reviewer,
                decision=args.decision,
                rationale=args.rationale,
                reviewed_at=args.reviewed_at,
            )
            _write_receipt(args.receipt, receipt)
        elif args.operation == "apply-draft":
            source_receipt_content = args.receipt.read_bytes()
            receipt = _read_receipt(args.receipt)
            draft = _read_json_object(args.draft, label="procurement review draft")
            receipt = apply_procurement_review_draft(
                receipt,
                draft,
                packet_content,
                receipt_content=source_receipt_content,
            )
            if args.receipt.read_bytes() != source_receipt_content:
                raise ValueError(
                    "procurement review receipt changed while the draft was being applied"
                )
            _write_receipt(args.receipt, receipt)
        else:
            receipt = _read_receipt(args.receipt)

        receipt_content = args.receipt.read_bytes()
        validation = validate_procurement_review_receipt(receipt, packet_content)
        if args.operation == "render":
            _render_review_workspace(
                args,
                receipt=receipt,
                receipt_content=receipt_content,
                packet_content=packet_content,
            )
    except Exception as exc:
        return _emit(_failure_result(args, exc), exit_code=1)

    return _emit(
        _success_result(
            args=args,
            receipt_content=receipt_content,
            validation=validation,
        ),
        exit_code=0,
    )


if __name__ == "__main__":
    raise SystemExit(main())
