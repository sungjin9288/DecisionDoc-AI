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
    build_procurement_reviewed_package,
    verify_procurement_reviewed_package,
    write_bytes_atomic,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create or verify a completed procurement review package."
    )
    subparsers = parser.add_subparsers(dest="operation", required=True)

    create_parser = subparsers.add_parser("create")
    create_parser.add_argument("packet", type=Path)
    create_parser.add_argument("--receipt", type=Path, required=True)
    create_parser.add_argument("--output", type=Path, required=True)

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("package", type=Path)
    return parser.parse_args()


def _read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("procurement review receipt must be an object")
    return value


def _paths(args: argparse.Namespace) -> tuple[Path | None, Path | None, Path]:
    if args.operation == "create":
        return args.packet, args.receipt, args.output
    return None, None, args.package


def _emit(result: dict[str, object], *, exit_code: int) -> int:
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return exit_code


def _success_result(
    *,
    args: argparse.Namespace,
    source_packet_path: Path | None,
    receipt_path: Path | None,
    package_path: Path,
    package_content: bytes,
    verification: dict[str, Any],
) -> dict[str, object]:
    return {
        "status": "passed",
        "operation": args.operation,
        "source_packet_path": str(source_packet_path) if source_packet_path else None,
        "receipt_path": str(receipt_path) if receipt_path else None,
        "package_path": str(package_path),
        "package_sha256": hashlib.sha256(package_content).hexdigest(),
        "package_size_bytes": len(package_content),
        **verification,
    }


def _failure_result(
    *,
    args: argparse.Namespace,
    source_packet_path: Path | None,
    receipt_path: Path | None,
    package_path: Path,
    exc: Exception,
) -> dict[str, object]:
    return {
        "status": "failed",
        "operation": args.operation,
        "source_packet_path": str(source_packet_path) if source_packet_path else None,
        "receipt_path": str(receipt_path) if receipt_path else None,
        "package_path": str(package_path),
        "error_type": type(exc).__name__,
        "error": str(exc),
    }


def main() -> int:
    args = _parse_args()
    source_packet_path, receipt_path, package_path = _paths(args)
    try:
        if package_path.suffix.lower() != ".zip":
            raise ValueError("procurement reviewed package output must use a .zip extension")
        if args.operation == "create":
            assert source_packet_path is not None and receipt_path is not None
            resolved_sources = {source_packet_path.resolve(), receipt_path.resolve()}
            if package_path.resolve() in resolved_sources:
                raise ValueError("procurement reviewed package must not overwrite source evidence")
            if package_path.exists():
                raise ValueError(
                    f"refusing to overwrite existing reviewed package: {package_path}"
                )
            packet_content = source_packet_path.read_bytes()
            receipt_content = receipt_path.read_bytes()
            receipt = _read_json_object(receipt_path)
            package_content, _ = build_procurement_reviewed_package(
                packet_content,
                receipt,
                receipt_content=receipt_content,
            )
            verify_procurement_reviewed_package(package_content)
            write_bytes_atomic(package_path, package_content)
        package_content = package_path.read_bytes()
        verification = verify_procurement_reviewed_package(package_content)
    except Exception as exc:
        return _emit(
            _failure_result(
                args=args,
                source_packet_path=source_packet_path,
                receipt_path=receipt_path,
                package_path=package_path,
                exc=exc,
            ),
            exit_code=1,
        )

    return _emit(
        _success_result(
            args=args,
            source_packet_path=source_packet_path,
            receipt_path=receipt_path,
            package_path=package_path,
            package_content=package_content,
            verification=verification,
        ),
        exit_code=0,
    )


if __name__ == "__main__":
    raise SystemExit(main())
