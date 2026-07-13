"""Build and verify completed finished-document review packets."""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from app.eval.human_review_receipt import validate_human_review_receipt


SCHEMA_VERSION = "decisiondoc.finished_document_review_packet.v1"
PACKET_MANIFEST_PATH = "packet_manifest.json"


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _relative_path(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("packet artifact path must be a non-empty string")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"packet artifact path must stay inside the evidence directory: {value}")
    return path.as_posix()


def _add_path(
    paths: dict[str, Mapping[str, Any] | None],
    value: Any,
    evidence: Mapping[str, Any] | None = None,
) -> None:
    path = _relative_path(value)
    if path == PACKET_MANIFEST_PATH:
        raise ValueError(f"packet artifact path is reserved: {path}")
    existing = paths.get(path)
    if existing is not None and evidence is not None and dict(existing) != dict(evidence):
        raise ValueError(f"conflicting evidence records for packet artifact: {path}")
    if path not in paths or evidence is not None:
        paths[path] = evidence


def _declared_artifacts(manifest: Mapping[str, Any]) -> dict[str, Mapping[str, Any] | None]:
    paths: dict[str, Mapping[str, Any] | None] = {}
    for path in ("manifest.json", "human_review_receipt.json", "human_review.html"):
        _add_path(paths, path)

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise ValueError("evidence manifest artifacts must be an object")
    for artifact in artifacts.values():
        if not isinstance(artifact, Mapping):
            raise ValueError("evidence manifest artifact records must be objects")
        _add_path(paths, artifact.get("path"), artifact)

    bundles = manifest.get("bundles")
    if not isinstance(bundles, Mapping) or not bundles:
        raise ValueError("evidence manifest must define at least one bundle")
    for bundle in bundles.values():
        if not isinstance(bundle, Mapping):
            raise ValueError("evidence manifest bundle records must be objects")

        response_snapshot = bundle.get("response_snapshot")
        if not isinstance(response_snapshot, Mapping):
            raise ValueError("bundle response_snapshot must be an object")
        _add_path(paths, response_snapshot.get("path"), response_snapshot)

        for field in ("markdown_docs", "exports", "preview_files"):
            values = bundle.get(field)
            if not isinstance(values, Mapping):
                raise ValueError(f"bundle {field} must be an object")
            for path in values.values():
                _add_path(paths, path)

        quality = bundle.get("quality")
        generated_markdown = quality.get("generated_markdown") if isinstance(quality, Mapping) else None
        if not isinstance(generated_markdown, Mapping):
            raise ValueError("bundle quality.generated_markdown must be an object")
        for artifact in generated_markdown.values():
            if not isinstance(artifact, Mapping):
                raise ValueError("generated Markdown evidence records must be objects")
            _add_path(paths, artifact.get("path"), artifact)
    return paths


def _read_artifacts(
    evidence_dir: Path,
    manifest: Mapping[str, Any],
) -> dict[str, bytes]:
    root = evidence_dir.resolve()
    artifacts: dict[str, bytes] = {}
    for relative_path, expected in _declared_artifacts(manifest).items():
        path = root / relative_path
        try:
            resolved = path.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise ValueError(f"packet artifact is missing: {relative_path}") from exc
        if path.is_symlink() or not resolved.is_relative_to(root) or not resolved.is_file():
            raise ValueError(f"packet artifact must be a regular file inside the evidence directory: {relative_path}")

        content = resolved.read_bytes()
        if expected is not None:
            expected_size = expected.get("size_bytes")
            expected_sha256 = expected.get("sha256")
            if expected_size != len(content):
                raise ValueError(f"packet artifact size does not match manifest: {relative_path}")
            if expected_sha256 != _sha256(content):
                raise ValueError(f"packet artifact SHA256 does not match manifest: {relative_path}")
        artifacts[relative_path] = content
    return artifacts


def _packet_manifest(
    *,
    artifacts: Mapping[str, bytes],
    manifest: Mapping[str, Any],
    receipt: Mapping[str, Any],
) -> dict[str, Any]:
    manifest_content = artifacts["manifest.json"]
    receipt_content = artifacts["human_review_receipt.json"]
    try:
        stored_manifest = json.loads(manifest_content)
        stored_receipt = json.loads(receipt_content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("packet source manifest and receipt must be valid JSON") from exc
    if stored_manifest != dict(manifest):
        raise ValueError("packet manifest input does not match manifest.json")
    if stored_receipt != dict(receipt):
        raise ValueError("packet receipt input does not match human_review_receipt.json")

    manifest_sha256 = _sha256(manifest_content)
    receipt_evidence = receipt.get("evidence")
    if not isinstance(receipt_evidence, Mapping):
        raise ValueError("review receipt evidence must be an object")
    if receipt_evidence.get("manifest_sha256") != manifest_sha256:
        raise ValueError("review receipt is not bound to the current manifest")
    receipt_validation = validate_human_review_receipt(
        receipt,
        manifest,
        manifest_sha256=manifest_sha256,
    )
    if not receipt_validation["ok"]:
        raise ValueError(f"review receipt is invalid: {receipt_validation['errors']}")
    if not receipt_validation["completed"]:
        raise ValueError("review packet requires a completed human review receipt")

    bundle_reviews = receipt.get("bundle_reviews")
    if not isinstance(bundle_reviews, Mapping) or not bundle_reviews:
        raise ValueError("review receipt must define bundle reviews")
    if any(
        not isinstance(review, Mapping) or review.get("decision") != "accepted"
        for review in bundle_reviews.values()
    ):
        raise ValueError("review packet requires every bundle decision to be accepted")

    external_actions = receipt.get("external_actions_authorized")
    if (
        not isinstance(external_actions, Mapping)
        or not external_actions
        or any(value is not False for value in external_actions.values())
    ):
        raise ValueError("review packet must keep every external action unauthorized")

    records = [
        {
            "path": path,
            "size_bytes": len(content),
            "sha256": _sha256(content),
        }
        for path, content in sorted(artifacts.items())
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "completed",
        "created_at": receipt.get("updated_at"),
        "source": {
            "manifest_path": "manifest.json",
            "manifest_sha256": manifest_sha256,
            "manifest_schema_version": manifest.get("schema_version"),
            "receipt_path": "human_review_receipt.json",
            "receipt_sha256": _sha256(receipt_content),
            "receipt_schema_version": receipt.get("schema_version"),
        },
        "summary": {
            "bundle_count": len(bundle_reviews),
            "artifact_count": len(records),
        },
        "artifacts": records,
        "external_actions_authorized": dict(external_actions),
    }


def _zip_timestamp(value: Any) -> tuple[int, int, int, int, int, int]:
    if not isinstance(value, str):
        raise ValueError("review packet created_at must be an ISO-8601 timestamp")
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("review packet created_at must be an ISO-8601 timestamp") from exc
    if timestamp.tzinfo is None:
        raise ValueError("review packet created_at must include a timezone")
    utc_timestamp = timestamp.astimezone(timezone.utc)
    return (
        min(2107, max(1980, utc_timestamp.year)),
        utc_timestamp.month,
        utc_timestamp.day,
        utc_timestamp.hour,
        utc_timestamp.minute,
        utc_timestamp.second,
    )


def _write_zip_entry(
    archive: zipfile.ZipFile,
    *,
    path: str,
    content: bytes,
    timestamp: tuple[int, int, int, int, int, int],
) -> None:
    info = zipfile.ZipInfo(path, date_time=timestamp)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    archive.writestr(info, content, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def build_finished_document_review_packet(
    *,
    evidence_dir: Path,
    manifest: Mapping[str, Any],
    receipt: Mapping[str, Any],
) -> tuple[bytes, dict[str, Any]]:
    """Return deterministic ZIP bytes and their embedded packet manifest."""
    artifacts = _read_artifacts(evidence_dir, manifest)
    packet_manifest = _packet_manifest(
        artifacts=artifacts,
        manifest=manifest,
        receipt=receipt,
    )
    packet_manifest_content = (
        json.dumps(packet_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    timestamp = _zip_timestamp(packet_manifest["created_at"])

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for path, content in sorted(artifacts.items()):
            _write_zip_entry(archive, path=path, content=content, timestamp=timestamp)
        _write_zip_entry(
            archive,
            path=PACKET_MANIFEST_PATH,
            content=packet_manifest_content,
            timestamp=timestamp,
        )
    return output.getvalue(), packet_manifest


def verify_finished_document_review_packet(content: bytes) -> dict[str, Any]:
    """Verify packet membership and every hash in its embedded manifest."""
    errors: list[str] = []
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = [info.filename for info in archive.infolist() if not info.is_dir()]
            if len(names) != len(set(names)):
                errors.append("packet contains duplicate file names")
            if PACKET_MANIFEST_PATH not in names:
                return {"ok": False, "entry_count": len(names), "errors": ["packet manifest is missing"]}
            packet_manifest = json.loads(archive.read(PACKET_MANIFEST_PATH))
            if not isinstance(packet_manifest, dict):
                return {"ok": False, "entry_count": len(names), "errors": ["packet manifest must be an object"]}

            records = packet_manifest.get("artifacts")
            records = records if isinstance(records, list) else []
            expected_names = {PACKET_MANIFEST_PATH}
            records_by_path: dict[str, Mapping[str, Any]] = {}
            for record in records:
                if not isinstance(record, Mapping):
                    errors.append("packet artifact record must be an object")
                    continue
                path = record.get("path")
                if not isinstance(path, str):
                    errors.append("packet artifact record path must be a string")
                    continue
                try:
                    _relative_path(path)
                except ValueError as exc:
                    errors.append(str(exc))
                    continue
                records_by_path[path] = record
                expected_names.add(path)
                if path not in names:
                    errors.append(f"packet artifact is missing: {path}")
                    continue
                artifact = archive.read(path)
                if record.get("size_bytes") != len(artifact):
                    errors.append(f"packet artifact size is invalid: {path}")
                if record.get("sha256") != _sha256(artifact):
                    errors.append(f"packet artifact SHA256 is invalid: {path}")

            if set(names) != expected_names:
                errors.append("packet file list does not match the embedded manifest")
            if packet_manifest.get("schema_version") != SCHEMA_VERSION:
                errors.append("packet schema_version is invalid")
            if packet_manifest.get("status") != "completed":
                errors.append("packet status must be completed")
            summary = packet_manifest.get("summary")
            if not isinstance(summary, Mapping) or summary.get("artifact_count") != len(records):
                errors.append("packet artifact_count is invalid")
            source = packet_manifest.get("source")
            if not isinstance(source, Mapping):
                errors.append("packet source must be an object")
            else:
                manifest_record = records_by_path.get("manifest.json")
                receipt_record = records_by_path.get("human_review_receipt.json")
                if not manifest_record or source.get("manifest_sha256") != manifest_record.get("sha256"):
                    errors.append("packet source manifest SHA256 is invalid")
                if not receipt_record or source.get("receipt_sha256") != receipt_record.get("sha256"):
                    errors.append("packet source receipt SHA256 is invalid")
            actions = packet_manifest.get("external_actions_authorized")
            if (
                not isinstance(actions, Mapping)
                or not actions
                or any(value is not False for value in actions.values())
            ):
                errors.append("packet must keep every external action unauthorized")
            try:
                stored_manifest = json.loads(archive.read("manifest.json"))
                stored_receipt = json.loads(archive.read("human_review_receipt.json"))
                semantic_validation = validate_human_review_receipt(
                    stored_receipt,
                    stored_manifest,
                    manifest_sha256=_sha256(archive.read("manifest.json")),
                )
                if not semantic_validation["ok"] or not semantic_validation["completed"]:
                    errors.append("packet receipt is not a valid completed review")
                if actions != stored_receipt.get("external_actions_authorized"):
                    errors.append("packet authorization boundary does not match the receipt")
            except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
                errors.append(f"packet review evidence is invalid: {exc}")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, zipfile.BadZipFile, KeyError) as exc:
        return {"ok": False, "entry_count": 0, "errors": [f"invalid review packet: {exc}"]}

    return {
        "ok": not errors,
        "entry_count": len(names),
        "errors": errors,
        "packet_manifest": packet_manifest,
    }
