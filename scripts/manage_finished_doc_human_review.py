#!/usr/bin/env python3
"""Create, draft, update, and validate finished-document human review receipts."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Sequence
from uuid import uuid4


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.eval.human_review_receipt import (  # noqa: E402
    apply_human_review_draft,
    build_pending_human_review_receipt,
    record_bundle_review,
    validate_human_review_receipt,
)
from app.eval.finished_document_packet import (  # noqa: E402
    build_finished_document_review_packet,
    verify_finished_document_review_packet,
)
from app.services.human_review_preview import build_human_review_summary  # noqa: E402


RECEIPT_FILENAME = "human_review_receipt.json"
SUMMARY_FILENAME = "human_review.html"
PACKET_FILENAME = "finished_document_review_packet.zip"
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


def _write_bytes_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f"{path.name}.tmp.{uuid4().hex}")
    try:
        with temporary_path.open("wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _write_text_atomic(path: Path, content: str) -> None:
    _write_bytes_atomic(path, content.encode("utf-8"))


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    content = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    _write_text_atomic(path, content)


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


def _load_bundle_documents(
    evidence_dir: Path,
    manifest: dict[str, Any],
) -> dict[str, dict[str, str]]:
    root = evidence_dir.resolve()
    bundles = manifest.get("bundles")
    if not isinstance(bundles, dict):
        raise ValueError("evidence manifest bundles must be an object")

    documents: dict[str, dict[str, str]] = {}
    for bundle_type, bundle in bundles.items():
        if not isinstance(bundle, dict):
            raise ValueError("evidence manifest bundle records must be objects")
        markdown_files = bundle.get("markdown_docs")
        if not isinstance(markdown_files, dict):
            raise ValueError("bundle markdown_docs must be an object")

        bundle_documents: dict[str, str] = {}
        for document_type, value in markdown_files.items():
            if not isinstance(value, str) or not value.strip():
                raise ValueError("Markdown document path must be a non-empty string")
            relative_path = PurePosixPath(value)
            if relative_path.is_absolute() or ".." in relative_path.parts:
                raise ValueError(f"Markdown document path must stay inside the evidence directory: {value}")
            path = root / relative_path.as_posix()
            try:
                resolved = path.resolve(strict=True)
            except (OSError, RuntimeError) as exc:
                raise ValueError(f"Markdown document is missing: {value}") from exc
            if path.is_symlink() or not resolved.is_relative_to(root) or not resolved.is_file():
                raise ValueError(f"Markdown document must be a regular evidence file: {value}")
            bundle_documents[str(document_type)] = resolved.read_text(encoding="utf-8")
        documents[str(bundle_type)] = bundle_documents
    return documents


def _summary_path(receipt_path: Path, requested_output: Path | None = None) -> Path:
    requested_output = requested_output or Path(SUMMARY_FILENAME)
    output_path = (
        requested_output
        if requested_output.is_absolute()
        else receipt_path.parent / requested_output
    ).resolve()
    if output_path.parent != receipt_path.parent.resolve():
        raise ValueError("review summary output must be beside the receipt")
    return output_path


def _write_summary(
    *,
    receipt_path: Path,
    receipt: dict[str, Any],
    manifest: dict[str, Any],
    validation: dict[str, Any],
    output: Path | None = None,
) -> Path:
    if not validation["ok"]:
        raise ValueError(f"cannot render an invalid receipt: {validation['errors']}")
    output_path = _summary_path(receipt_path, output)
    summary = build_human_review_summary(
        manifest=manifest,
        receipt=receipt,
        validation=validation,
        receipt_sha256=_sha256(receipt_path),
        bundle_documents=_load_bundle_documents(receipt_path.parent, manifest),
        receipt_path=receipt_path.name,
    )
    _write_text_atomic(output_path, summary)
    return output_path


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
    summary_path = _write_summary(
        receipt_path=output_path,
        receipt=receipt,
        manifest=manifest,
        validation=result,
    )
    return {
        "ok": True,
        "command": "init",
        "receipt_path": str(output_path),
        "summary_path": str(summary_path),
        **result,
    }


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
    summary_path = _write_summary(
        receipt_path=receipt_path,
        receipt=updated,
        manifest=manifest,
        validation=result,
    )
    return {
        "ok": True,
        "command": "record",
        "receipt_path": str(receipt_path),
        "summary_path": str(summary_path),
        **result,
    }


def _validate_receipt(args: argparse.Namespace) -> dict[str, Any]:
    receipt_path = args.receipt.resolve()
    _, result = _validation_for_path(receipt_path)
    return {"command": "validate", "receipt_path": str(receipt_path), **result}


def _apply_draft(args: argparse.Namespace) -> dict[str, Any]:
    receipt_path = args.receipt.resolve()
    draft_path = args.draft.resolve()
    receipt, before = _validation_for_path(receipt_path)
    if not before["ok"]:
        raise ValueError(f"receipt is invalid before draft application: {before['errors']}")

    manifest_path = _manifest_for_receipt(receipt_path, receipt)
    manifest = _read_json(manifest_path)
    draft = _read_json(draft_path)
    source_receipt_sha256 = _sha256(receipt_path)
    manifest_sha256 = _sha256(manifest_path)
    updated = apply_human_review_draft(
        receipt,
        draft,
        manifest,
        receipt_sha256=source_receipt_sha256,
        manifest_sha256=manifest_sha256,
        receipt_path=receipt_path.name,
    )
    result = validate_human_review_receipt(
        updated,
        manifest,
        manifest_sha256=manifest_sha256,
    )
    if not result["ok"]:
        raise ValueError(f"updated receipt is invalid: {result['errors']}")
    if _sha256(receipt_path) != source_receipt_sha256:
        raise ValueError("receipt changed while the review draft was being applied")

    _write_json_atomic(receipt_path, updated)
    summary_path = _write_summary(
        receipt_path=receipt_path,
        receipt=updated,
        manifest=manifest,
        validation=result,
    )
    return {
        "ok": True,
        "command": "apply-draft",
        "draft_path": str(draft_path),
        "receipt_path": str(receipt_path),
        "summary_path": str(summary_path),
        "draft_review_count": len(draft["reviews"]),
        **result,
    }


def _render_summary(args: argparse.Namespace) -> dict[str, Any]:
    receipt_path = args.receipt.resolve()
    receipt, result = _validation_for_path(receipt_path)
    manifest = _read_json(_manifest_for_receipt(receipt_path, receipt))
    summary_path = _write_summary(
        receipt_path=receipt_path,
        receipt=receipt,
        manifest=manifest,
        validation=result,
        output=args.output,
    )
    return {
        "command": "render",
        "receipt_path": str(receipt_path),
        "summary_path": str(summary_path),
        **result,
    }


def _package_review(args: argparse.Namespace) -> dict[str, Any]:
    receipt_path = args.receipt.resolve()
    receipt, result = _validation_for_path(receipt_path)
    if not result["ok"]:
        raise ValueError(f"receipt is invalid: {result['errors']}")
    if not result["completed"]:
        raise ValueError("review packet requires every bundle review to be accepted")

    requested_output = args.output or Path(PACKET_FILENAME)
    output_path = (
        requested_output
        if requested_output.is_absolute()
        else receipt_path.parent / requested_output
    ).resolve()
    if output_path.suffix.lower() != ".zip":
        raise ValueError("review packet output must use a .zip extension")

    manifest_path = _manifest_for_receipt(receipt_path, receipt)
    manifest = _read_json(manifest_path)
    summary_path = _write_summary(
        receipt_path=receipt_path,
        receipt=receipt,
        manifest=manifest,
        validation=result,
    )
    packet_content, packet_manifest = build_finished_document_review_packet(
        evidence_dir=receipt_path.parent,
        manifest=manifest,
        receipt=receipt,
    )
    packet_validation = verify_finished_document_review_packet(packet_content)
    if not packet_validation["ok"]:
        raise ValueError(f"generated review packet is invalid: {packet_validation['errors']}")

    _write_bytes_atomic(output_path, packet_content)
    return {
        "ok": True,
        "command": "package",
        "receipt_path": str(receipt_path),
        "summary_path": str(summary_path),
        "packet_path": str(output_path),
        "packet_sha256": hashlib.sha256(packet_content).hexdigest(),
        "entry_count": packet_validation["entry_count"],
        "artifact_count": packet_manifest["summary"]["artifact_count"],
        "status": packet_manifest["status"],
    }


def _verify_packet(args: argparse.Namespace) -> dict[str, Any]:
    packet_path = args.packet.resolve()
    content = packet_path.read_bytes()
    result = verify_finished_document_review_packet(content)
    packet_manifest = result.get("packet_manifest")
    packet_manifest = packet_manifest if isinstance(packet_manifest, dict) else {}
    summary = packet_manifest.get("summary")
    summary = summary if isinstance(summary, dict) else {}
    return {
        "command": "verify-packet",
        "packet_path": str(packet_path),
        "packet_sha256": hashlib.sha256(content).hexdigest(),
        "ok": result["ok"],
        "status": packet_manifest.get("status"),
        "entry_count": result["entry_count"],
        "artifact_count": summary.get("artifact_count"),
        "errors": result["errors"],
    }


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

    apply_draft_parser = subparsers.add_parser(
        "apply-draft",
        help="Validate and atomically apply a browser-generated review draft.",
    )
    apply_draft_parser.add_argument("receipt", type=Path)
    apply_draft_parser.add_argument("draft", type=Path)
    apply_draft_parser.set_defaults(handler=_apply_draft)

    render_parser = subparsers.add_parser("render", help="Render the local reviewer workspace.")
    render_parser.add_argument("receipt", type=Path)
    render_parser.add_argument("--output", type=Path)
    render_parser.set_defaults(handler=_render_summary)

    package_parser = subparsers.add_parser(
        "package",
        help="Build a verified ZIP from a completed review receipt.",
    )
    package_parser.add_argument("receipt", type=Path)
    package_parser.add_argument("--output", type=Path)
    package_parser.set_defaults(handler=_package_review)

    verify_packet_parser = subparsers.add_parser(
        "verify-packet",
        help="Verify a finished-document review packet ZIP.",
    )
    verify_packet_parser.add_argument("packet", type=Path)
    verify_packet_parser.set_defaults(handler=_verify_packet)
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
