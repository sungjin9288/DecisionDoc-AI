from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.procurement_decision_package_service import (  # noqa: E402
    build_procurement_review_packet,
    verify_procurement_review_packet,
    write_bytes_atomic,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create or verify a deterministic procurement review packet."
    )
    subparsers = parser.add_subparsers(dest="operation", required=True)

    create_parser = subparsers.add_parser("create")
    create_parser.add_argument("source_dir", type=Path)
    create_parser.add_argument("--packet", type=Path, required=True)

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("packet", type=Path)

    return parser.parse_args()


def _emit(result: dict[str, object], *, exit_code: int) -> int:
    print(json.dumps(result, indent=2))
    return exit_code


def _context(args: argparse.Namespace) -> tuple[Path | None, Path]:
    if args.operation == "create":
        return args.source_dir, args.packet
    return None, args.packet


def _success_result(
    *,
    operation: str,
    source_dir: Path | None,
    packet_path: Path,
    packet_content: bytes,
    verification: dict[str, object],
) -> dict[str, object]:
    return {
        "status": "passed",
        "operation": operation,
        "source_dir": str(source_dir) if source_dir is not None else None,
        "packet_path": str(packet_path),
        "packet_sha256": hashlib.sha256(packet_content).hexdigest(),
        "packet_size_bytes": len(packet_content),
        **verification,
    }


def _failure_result(
    *,
    operation: str,
    source_dir: Path | None,
    packet_path: Path,
    exc: Exception,
) -> dict[str, object]:
    return {
        "status": "failed",
        "operation": operation,
        "source_dir": str(source_dir) if source_dir is not None else None,
        "packet_path": str(packet_path),
        "error_type": type(exc).__name__,
        "error": str(exc),
    }


def main() -> int:
    args = _parse_args()
    source_dir, packet_path = _context(args)
    try:
        if args.operation == "create":
            assert source_dir is not None
            packet_content, _ = build_procurement_review_packet(source_dir)
            write_bytes_atomic(packet_path, packet_content)
        packet_content = packet_path.read_bytes()
        verification = verify_procurement_review_packet(packet_content)
    except Exception as exc:
        return _emit(
            _failure_result(
                operation=args.operation,
                source_dir=source_dir,
                packet_path=packet_path,
                exc=exc,
            ),
            exit_code=1,
        )

    return _emit(
        _success_result(
            operation=args.operation,
            source_dir=source_dir,
            packet_path=packet_path,
            packet_content=packet_content,
            verification=verification,
        ),
        exit_code=0,
    )


if __name__ == "__main__":
    raise SystemExit(main())
