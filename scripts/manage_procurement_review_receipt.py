from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.procurement_decision_package_service import (  # noqa: E402
    build_pending_procurement_review_receipt,
    record_procurement_review_decision,
    validate_procurement_review_receipt,
    write_bytes_atomic,
)


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
    return parser.parse_args()


def _read_receipt(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("procurement review receipt must be an object")
    return payload


def _write_receipt(path: Path, receipt: dict[str, Any]) -> None:
    content = (json.dumps(receipt, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    write_bytes_atomic(path, content)


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
        else:
            receipt = _read_receipt(args.receipt)

        receipt_content = args.receipt.read_bytes()
        validation = validate_procurement_review_receipt(receipt, packet_content)
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
