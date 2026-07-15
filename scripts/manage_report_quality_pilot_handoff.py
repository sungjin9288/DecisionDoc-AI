#!/usr/bin/env python3
"""Create or verify a portable handoff for one reviewed Report Quality pilot."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.report_quality_learning import validate_correction_artifact  # noqa: E402
from scripts.local_write_once import write_bytes_once  # noqa: E402
from scripts.report_quality_pilot_pack_provenance import (  # noqa: E402
    SOURCE_MANIFEST_NAME,
    SOURCE_PACKAGE_MANIFEST_NAME,
    SOURCE_RECEIPT_NAME,
    load_pilot_pack,
)
from scripts.report_quality_pilot_review_evidence import (  # noqa: E402
    load_current_decision_receipt,
    load_current_review_manifest,
)
from scripts.report_quality_pilot_handoff_summary import (  # noqa: E402
    HTML_SUMMARY_NAME,
    SUMMARY_NAME,
    render_report_quality_pilot_handoff_html,
    render_report_quality_pilot_handoff_summary,
)
from scripts.report_quality_pilot_handoff_verifier import (  # noqa: E402
    MANIFEST_NAME,
    REPORT_TYPE,
    SCHEMA_VERSION,
    verify_report_quality_pilot_handoff,
    write_verified_handoff_browser_summary,
    write_verified_handoff_summary,
)
from scripts.sync_report_quality_pilot_pack import (  # noqa: E402
    sync_report_quality_pilot_pack,
)
from scripts.validate_report_quality_review_decision_receipt import (  # noqa: E402
    NO_EXTERNAL_ACTION_KEYS,
)


ENTRY_TIMESTAMP = (2020, 1, 1, 0, 0, 0)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _json_bytes(payload: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _read_json_object(content: bytes, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} must contain valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} root must be an object")
    return payload


def _read_jsonl(content: bytes) -> list[dict[str, Any]]:
    try:
        rows = [
            json.loads(line)
            for line in content.decode("utf-8").splitlines()
            if line.strip()
        ]
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            "reviewed pilot JSONL must contain valid UTF-8 JSON objects"
        ) from exc
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise ValueError("reviewed pilot JSONL must contain at least one JSON object")
    return rows


def _write_zip_entry(archive: zipfile.ZipFile, path: str, content: bytes) -> None:
    info = zipfile.ZipInfo(path, date_time=ENTRY_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    archive.writestr(
        info,
        content,
        compress_type=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    )


def _media_type(path: str) -> str:
    if path.endswith(".jsonl"):
        return "application/x-ndjson"
    if path.endswith(".html"):
        return "text/html; charset=utf-8"
    if path.endswith(".md"):
        return "text/markdown; charset=utf-8"
    return "application/json"


def _entry_record(path: str, content: bytes) -> dict[str, Any]:
    return {
        "path": path,
        "sha256": _sha256(content),
        "size_bytes": len(content),
        "media_type": _media_type(path),
    }


def _regular_file(path: Path, *, label: str) -> bytes:
    if path.is_symlink():
        raise ValueError(f"symlink {label} files are not allowed")
    if not path.is_file():
        raise ValueError(f"{label} file does not exist: {path}")
    return path.read_bytes()


def _resolve_output_path(
    output_path: Path | None, *, pack_dir: Path, jsonl_sha256: str
) -> Path:
    candidate = output_path or (
        pack_dir / f"report_quality_pilot_review_handoff_{jsonl_sha256[:12]}.zip"
    )
    expanded = candidate.expanduser()
    if expanded.is_symlink():
        raise ValueError("symlink handoff package outputs are not allowed")
    resolved = expanded.resolve()
    if resolved.suffix.lower() != ".zip":
        raise ValueError("handoff package output must use the .zip extension")
    if resolved.exists():
        raise ValueError(f"refusing to overwrite existing handoff package: {resolved}")
    return resolved


def _source_entries(pack_dir: Path, *, source_bound: bool) -> dict[str, bytes]:
    if not source_bound:
        return {}

    manifest_path = pack_dir / SOURCE_MANIFEST_NAME
    manifest_bytes = _regular_file(manifest_path, label="source manifest")
    manifest = _read_json_object(manifest_bytes, label="source manifest")
    required_names = [SOURCE_MANIFEST_NAME]
    if isinstance(manifest.get("receipt"), dict):
        required_names.append(SOURCE_RECEIPT_NAME)
    source = manifest.get("source")
    package = source.get("package") if isinstance(source, dict) else None
    if isinstance(package, dict) and package.get("manifest_path") is not None:
        required_names.append(SOURCE_PACKAGE_MANIFEST_NAME)
    return {
        f"source/{name}": _regular_file(
            pack_dir / name,
            label=f"source evidence {name}",
        )
        for name in required_names
    }


def _build_archive(entries: dict[str, bytes], manifest: dict[str, Any]) -> bytes:
    archive_entries = {**entries, MANIFEST_NAME: _json_bytes(manifest)}
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for path in sorted(archive_entries):
            _write_zip_entry(archive, path, archive_entries[path])
    return output.getvalue()


def create_report_quality_pilot_handoff(
    *,
    pack_dir: Path,
    jsonl_path: Path,
    output_path: Path | None = None,
) -> dict[str, Any]:
    resolved_pack_dir = pack_dir.expanduser().resolve()
    snapshot = load_pilot_pack(resolved_pack_dir)
    review_manifest = load_current_review_manifest(snapshot)
    decision_receipt = load_current_decision_receipt(snapshot)

    expanded_jsonl_path = jsonl_path.expanduser()
    if expanded_jsonl_path.is_symlink():
        raise ValueError("symlink reviewed pilot JSONL files are not allowed")
    resolved_jsonl_path = expanded_jsonl_path.resolve()
    if resolved_jsonl_path.suffix.lower() != ".jsonl":
        raise ValueError("reviewed pilot input must use the .jsonl extension")
    jsonl_bytes = _regular_file(resolved_jsonl_path, label="reviewed pilot JSONL")
    artifacts = _read_jsonl(jsonl_bytes)
    expected_artifacts = [draft.payload for draft in snapshot.drafts]
    if artifacts != expected_artifacts:
        raise ValueError(
            "reviewed pilot JSONL does not match the current draft order and content"
        )
    if not 3 <= len(artifacts) <= 5:
        raise ValueError(
            "reviewed pilot handoff must contain between 3 and 5 artifacts"
        )

    validations = [validate_correction_artifact(artifact) for artifact in artifacts]
    if any(
        validation.get("ok") is not True
        or validation.get("ready_for_learning") is not True
        for validation in validations
    ):
        raise ValueError(
            "reviewed pilot handoff requires valid ready_for_learning artifacts"
        )

    decision_path = Path(str(decision_receipt.validation["decision_path"]))
    decision_bytes = _regular_file(decision_path, label="review decision")
    entries = {
        "artifacts/ready_artifacts.jsonl": jsonl_bytes,
        "review/human_review_manifest.json": review_manifest.content,
        f"review/{decision_receipt.path.name}": decision_receipt.content,
        f"review/{decision_path.name}": decision_bytes,
        **{
            f"drafts/{draft.path.name}": draft.path.read_bytes()
            for draft in snapshot.drafts
        },
        **_source_entries(
            resolved_pack_dir,
            source_bound=snapshot.source_order_applied,
        ),
    }
    artifact_records = [
        {
            "artifact_id": draft.artifact_id,
            "draft_path": f"drafts/{draft.path.name}",
            "draft_sha256": draft.sha256,
        }
        for draft in snapshot.drafts
    ]
    manifest: dict[str, Any] = {
        "report_type": REPORT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "batch_id": resolved_pack_dir.name,
        "artifact_count": len(artifact_records),
        "ordered_artifact_ids": [item["artifact_id"] for item in artifact_records],
        "jsonl": {
            "path": "artifacts/ready_artifacts.jsonl",
            "sha256": _sha256(jsonl_bytes),
        },
        "review": {
            "manifest_path": "review/human_review_manifest.json",
            "manifest_sha256": review_manifest.sha256,
            "decision_receipt_path": f"review/{decision_receipt.path.name}",
            "decision_receipt_sha256": decision_receipt.sha256,
            "decision_file_path": f"review/{decision_path.name}",
            "decision_file_sha256": _sha256(decision_bytes),
        },
        "pack_binding": review_manifest.payload["pack_binding"],
        "artifacts": artifact_records,
        "source_evidence": sorted(
            path for path in entries if path.startswith("source/")
        ),
        "external_action_boundary": {key: False for key in NO_EXTERNAL_ACTION_KEYS},
    }
    summary_bytes = render_report_quality_pilot_handoff_summary(
        manifest,
        review_manifest.payload,
    ).encode("utf-8")
    html_summary_bytes = render_report_quality_pilot_handoff_html(
        manifest,
        review_manifest.payload,
    ).encode("utf-8")
    entries[SUMMARY_NAME] = summary_bytes
    entries[HTML_SUMMARY_NAME] = html_summary_bytes
    manifest["summary"] = {
        "path": SUMMARY_NAME,
        "sha256": _sha256(summary_bytes),
    }
    manifest["browser_summary"] = {
        "path": HTML_SUMMARY_NAME,
        "sha256": _sha256(html_summary_bytes),
    }
    manifest["entries"] = [
        _entry_record(path, content) for path, content in sorted(entries.items())
    ]
    package_bytes = _build_archive(entries, manifest)
    verification = verify_report_quality_pilot_handoff(package_bytes)
    resolved_output_path = _resolve_output_path(
        output_path,
        pack_dir=resolved_pack_dir,
        jsonl_sha256=manifest["jsonl"]["sha256"],
    )
    protected_paths = {
        resolved_jsonl_path,
        review_manifest.path.resolve(),
        decision_receipt.path.resolve(),
        decision_path.resolve(),
        *(draft.path.resolve() for draft in snapshot.drafts),
    }
    if resolved_output_path in protected_paths:
        raise ValueError("handoff package must not overwrite source evidence")
    write_bytes_once(
        resolved_output_path,
        package_bytes,
        label="handoff package",
    )
    return {
        "report_type": "report_quality_pilot_review_handoff_created",
        "ok": True,
        "pack_dir": str(resolved_pack_dir),
        "jsonl_path": str(resolved_jsonl_path),
        "output_path": str(resolved_output_path),
        "package_sha256": _sha256(package_bytes),
        "package_size_bytes": len(package_bytes),
        **verification,
        "side_effect_boundary": {
            "reads_local_review_evidence": True,
            "writes_local_handoff_package": True,
            **{key: False for key in NO_EXTERNAL_ACTION_KEYS},
        },
    }


def finalize_report_quality_pilot_handoff(
    *,
    pack_dir: Path,
    output_path: Path | None = None,
) -> dict[str, Any]:
    resolved_pack_dir = pack_dir.expanduser().resolve()
    with TemporaryDirectory(prefix="decisiondoc-report-quality-handoff-") as temp_dir:
        jsonl_path = Path(temp_dir) / "ready-artifacts.jsonl"
        sync_result = sync_report_quality_pilot_pack(
            pack_dir=resolved_pack_dir,
            output_path=jsonl_path,
            min_records=3,
            require_ready=True,
        )
        if not sync_result["ok"]:
            errors = "; ".join(sync_result["errors"]) or "ready sync did not pass"
            raise ValueError(f"reviewed pilot finalization blocked: {errors}")

        handoff = create_report_quality_pilot_handoff(
            pack_dir=resolved_pack_dir,
            jsonl_path=jsonl_path,
            output_path=output_path,
        )

    result = dict(handoff)
    result.pop("jsonl_path", None)
    return {
        **result,
        "report_type": "report_quality_pilot_review_handoff_finalized",
        "ready_sync": {
            "artifact_count": sync_result["artifact_count"],
            "jsonl_sha256": sync_result["output_sha256"],
            "review_manifest": sync_result["review_manifest"],
            "decision_receipt": sync_result["decision_receipt"],
        },
        "side_effect_boundary": {
            "reads_local_review_evidence": True,
            "writes_temporary_jsonl": True,
            "retains_standalone_jsonl": False,
            "writes_local_handoff_package": True,
            **{key: False for key in NO_EXTERNAL_ACTION_KEYS},
        },
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)

    create_parser = subparsers.add_parser(
        "create", help="Create one reviewed pilot handoff ZIP."
    )
    create_parser.add_argument("pack_dir", type=Path)
    create_parser.add_argument("--jsonl", type=Path, required=True)
    create_parser.add_argument("--output", type=Path, default=None)
    create_parser.add_argument("--json", action="store_true")

    finalize_parser = subparsers.add_parser(
        "finalize",
        help="Validate a reviewed pack and create its handoff ZIP in one step.",
    )
    finalize_parser.add_argument("pack_dir", type=Path)
    finalize_parser.add_argument("--output", type=Path, default=None)
    finalize_parser.add_argument("--json", action="store_true")

    verify_parser = subparsers.add_parser(
        "verify", help="Verify one reviewed pilot handoff ZIP."
    )
    verify_parser.add_argument("package", type=Path)
    summary_outputs = verify_parser.add_mutually_exclusive_group()
    summary_outputs.add_argument("--summary-output", type=Path, default=None)
    summary_outputs.add_argument("--browser-summary-output", type=Path, default=None)
    verify_parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    try:
        if args.operation == "create":
            result = create_report_quality_pilot_handoff(
                pack_dir=args.pack_dir,
                jsonl_path=args.jsonl,
                output_path=args.output,
            )
        elif args.operation == "finalize":
            result = finalize_report_quality_pilot_handoff(
                pack_dir=args.pack_dir,
                output_path=args.output,
            )
        else:
            package_path = args.package.expanduser()
            package_bytes = _regular_file(package_path, label="reviewed pilot handoff")
            if args.summary_output is not None:
                verification = write_verified_handoff_summary(
                    package_bytes,
                    output_path=args.summary_output,
                )
            elif args.browser_summary_output is not None:
                verification = write_verified_handoff_browser_summary(
                    package_bytes,
                    output_path=args.browser_summary_output,
                )
            else:
                verification = verify_report_quality_pilot_handoff(package_bytes)
            result = {
                "package_path": str(package_path.resolve()),
                "package_sha256": _sha256(package_bytes),
                "package_size_bytes": len(package_bytes),
                **verification,
            }
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        if getattr(args, "json", False):
            print(
                json.dumps(
                    {
                        "ok": False,
                        "operation": args.operation,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print(f"ERROR {exc}", file=sys.stderr)
        return 1

    if getattr(args, "json", False):
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("PASS reviewed Report Quality pilot handoff verified")
        print(f"artifact_count={result['artifact_count']}")
        print(f"summary_path={result['summary_path']}")
        print(f"summary_sha256={result['summary_sha256']}")
        if result.get("browser_summary_path"):
            print(f"browser_summary_path={result['browser_summary_path']}")
            print(f"browser_summary_sha256={result['browser_summary_sha256']}")
        print(f"jsonl_sha256={result['jsonl_sha256']}")
        print(f"package_sha256={result['package_sha256']}")
        if result.get("output_path"):
            print(f"output_path={result['output_path']}")
        if result.get("summary_output_path"):
            print(f"summary_output_path={result['summary_output_path']}")
        if result.get("browser_summary_output_path"):
            print(
                f"browser_summary_output_path={result['browser_summary_output_path']}"
            )
        print("training_boundary=not_authorized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
