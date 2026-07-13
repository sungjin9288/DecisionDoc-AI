#!/usr/bin/env python3
"""Create, update, and validate finished-document human review receipts."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence
from uuid import uuid4


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.eval.human_review_receipt import (  # noqa: E402
    build_pending_human_review_receipt,
    record_bundle_review,
    validate_human_review_receipt,
)


RECEIPT_FILENAME = "human_review_receipt.json"
MANIFEST_FILENAME = "manifest.json"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON document must be an object: {path}")
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f"{path.name}.tmp.{uuid4().hex}")
    try:
        with temporary_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _manifest_for_receipt(receipt_path: Path, receipt: dict[str, Any]) -> Path:
    evidence = receipt.get("evidence")
    if not isinstance(evidence, dict) or evidence.get("manifest_path") != MANIFEST_FILENAME:
        raise ValueError("receipt evidence.manifest_path must be manifest.json")
    return receipt_path.parent / MANIFEST_FILENAME


def _validation_for_path(receipt_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    receipt = _read_json(receipt_path)
    manifest_path = _manifest_for_receipt(receipt_path, receipt)
    manifest = _read_json(manifest_path)
    result = validate_human_review_receipt(
        receipt,
        manifest,
        manifest_sha256=_sha256(manifest_path),
    )
    return receipt, result


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _init_receipt(args: argparse.Namespace) -> dict[str, Any]:
    evidence_dir = args.evidence_dir.resolve()
    manifest_path = evidence_dir / MANIFEST_FILENAME
    requested_output = args.output or Path(RECEIPT_FILENAME)
    output_path = (
        requested_output
        if requested_output.is_absolute()
        else evidence_dir / requested_output
    ).resolve()
    if output_path.parent != evidence_dir:
        raise ValueError("receipt output must be inside the evidence directory")
    if output_path.exists():
        raise ValueError(f"refusing to overwrite existing receipt: {output_path}")

    manifest = _read_json(manifest_path)
    receipt = build_pending_human_review_receipt(
        manifest,
        manifest_sha256=_sha256(manifest_path),
    )
    result = validate_human_review_receipt(
        receipt,
        manifest,
        manifest_sha256=_sha256(manifest_path),
    )
    if not result["ok"]:
        raise ValueError(f"generated receipt is invalid: {result['errors']}")
    _write_json_atomic(output_path, receipt)
    return {"ok": True, "command": "init", "receipt_path": str(output_path), **result}


def _record_review(args: argparse.Namespace) -> dict[str, Any]:
    receipt_path = args.receipt.resolve()
    receipt, before = _validation_for_path(receipt_path)
    if not before["ok"]:
        raise ValueError(f"receipt is invalid before update: {before['errors']}")

    reviewed_at = args.reviewed_at or datetime.now(timezone.utc).isoformat()
    updated = record_bundle_review(
        receipt,
        bundle_type=args.bundle,
        reviewer=args.reviewer,
        factual_grounding=args.factual_grounding,
        visual_review=args.visual_review,
        notes=args.notes,
        reviewed_at=reviewed_at,
    )
    manifest_path = _manifest_for_receipt(receipt_path, updated)
    manifest = _read_json(manifest_path)
    result = validate_human_review_receipt(
        updated,
        manifest,
        manifest_sha256=_sha256(manifest_path),
    )
    if not result["ok"]:
        raise ValueError(f"updated receipt is invalid: {result['errors']}")
    _write_json_atomic(receipt_path, updated)
    return {"ok": True, "command": "record", "receipt_path": str(receipt_path), **result}


def _validate_receipt(args: argparse.Namespace) -> dict[str, Any]:
    receipt_path = args.receipt.resolve()
    _, result = _validation_for_path(receipt_path)
    return {"command": "validate", "receipt_path": str(receipt_path), **result}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create a pending receipt for an evidence package.")
    init_parser.add_argument("--evidence-dir", type=Path, required=True)
    init_parser.add_argument("--output", type=Path)
    init_parser.set_defaults(handler=_init_receipt)

    record_parser = subparsers.add_parser("record", help="Record one bundle review decision.")
    record_parser.add_argument("receipt", type=Path)
    record_parser.add_argument("--bundle", required=True)
    record_parser.add_argument("--reviewer", required=True)
    record_parser.add_argument(
        "--factual-grounding",
        choices=("passed", "needs_revision"),
        required=True,
    )
    record_parser.add_argument(
        "--visual-review",
        choices=("passed", "needs_revision"),
        required=True,
    )
    record_parser.add_argument("--notes", required=True)
    record_parser.add_argument("--reviewed-at")
    record_parser.set_defaults(handler=_record_review)

    validate_parser = subparsers.add_parser("validate", help="Validate a receipt against its manifest.")
    validate_parser.add_argument("receipt", type=Path)
    validate_parser.set_defaults(handler=_validate_receipt)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        result = args.handler(args)
    except (OSError, ValueError) as exc:
        _print_json({"ok": False, "command": args.command, "error": str(exc)})
        return 1

    _print_json(result)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
