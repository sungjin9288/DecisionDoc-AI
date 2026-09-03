"""Build and independently verify deterministic generated-document export packets."""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import zipfile
from collections.abc import Sequence
from typing import Any

from app.services.docx_service import build_docx
from app.services.excel_service import build_excel
from app.services.hwp_service import build_hwp
from app.services.pptx_service import build_pptx_from_docs


PACKET_SCHEMA = "decisiondoc.generate_export_review_packet.v1"
PERSISTED_PACKET_SCHEMA = "decisiondoc.generated_document_review_packet.v1"
MANIFEST_PATH = "export_packet_manifest.json"
FORMAT_ORDER = ("docx", "pdf", "xlsx", "hwp", "pptx")
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
MAX_PACKET_SIZE_BYTES = 50 * 1024 * 1024
MAX_ARTIFACT_SIZE_BYTES = 40 * 1024 * 1024
MAX_UNCOMPRESSED_SIZE_BYTES = 50 * 1024 * 1024
MAX_MANIFEST_SIZE_BYTES = 1024 * 1024
ZIP_CREATE_SYSTEM = 3
ZIP_VERSION = 20
ZIP_EXTERNAL_ATTR = 0o100644 << 16

PACKET_SHA256_HEADER = "X-DecisionDoc-Export-Packet-SHA256"
MANIFEST_SHA256_HEADER = "X-DecisionDoc-Export-Manifest-SHA256"
VERIFIED_HEADER = "X-DecisionDoc-Export-Verified"
ARTIFACT_COUNT_HEADER = "X-DecisionDoc-Export-Artifact-Count"
OPERATIONAL_APPROVAL_HEADER = "X-DecisionDoc-Operational-Approval"

FORMAT_SPECS: dict[str, dict[str, str]] = {
    "docx": {
        "path": "artifacts/document.docx",
        "media_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    },
    "pdf": {
        "path": "artifacts/document.pdf",
        "media_type": "application/pdf",
    },
    "xlsx": {
        "path": "artifacts/document.xlsx",
        "media_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    },
    "hwp": {
        "path": "artifacts/document.hwpx",
        "media_type": "application/hwp+zip",
    },
    "pptx": {
        "path": "artifacts/document.pptx",
        "media_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    },
}

# This is deliberately a closed object.  Packet integrity proves that these
# values were present in these bytes; it does not authenticate an issuer.
AUTHORITY_FALSE = {
    "approval_authorized": False,
    "aws_execution_authorized": False,
    "dataset_upload_authorized": False,
    "deployment_authorized": False,
    "g2b_submission_authorized": False,
    "provider_execution_authorized": False,
    "training_execution_authorized": False,
}

TRANSIENT_SOURCE_KEYS = {"request_id", "tenant_id", "title"}
PERSISTED_SOURCE_KEYS = {
    "bundle_id",
    "document_source_sha256",
    "project_document_id",
    "project_id",
    "request_id",
    "tenant_id",
    "title",
}


class GenerationExportPacketError(ValueError):
    """Base error whose detail must not be returned in an HTTP response."""


class ExportFormatInvalidError(GenerationExportPacketError):
    """Raised when an export format query cannot form a supported request."""


class ExportPacketBuildError(GenerationExportPacketError):
    """Raised when conversion or packet self-verification cannot complete."""


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _canonical_json_bytes(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("utf-8")


def _safe_converter_title(title: str) -> str:
    """Keep control characters out of downstream document-format generators."""
    sanitized = "".join(
        " " if ord(character) < 32 or 127 <= ord(character) <= 159 else character
        for character in title
    ).strip()
    return sanitized or "Document"


def canonicalize_export_formats(formats: str | Sequence[str]) -> tuple[str, ...]:
    """Return a de-duplicated canonical export format order or a stable error."""
    if isinstance(formats, str):
        raw_tokens = formats.split(",")
    elif isinstance(formats, Sequence):
        raw_tokens = list(formats)
    else:
        raise ExportFormatInvalidError("formats must be a string or sequence")

    requested: set[str] = set()
    for raw_token in raw_tokens:
        if not isinstance(raw_token, str):
            raise ExportFormatInvalidError("format token must be a string")
        token = raw_token.strip().lower()
        if not token:
            raise ExportFormatInvalidError("format token must not be empty")
        if token not in FORMAT_SPECS:
            raise ExportFormatInvalidError("unsupported format")
        requested.add(token)
    if not requested:
        raise ExportFormatInvalidError("at least one format is required")
    return tuple(fmt for fmt in FORMAT_ORDER if fmt in requested)


async def _convert_artifact(
    fmt: str,
    *,
    docs: list[dict[str, Any]],
    title: str,
) -> bytes:
    if fmt == "docx":
        return await asyncio.to_thread(build_docx, docs, title=title)
    if fmt == "pdf":
        from app.services.pdf_service import build_pdf

        return await build_pdf(docs, title=title)
    if fmt == "xlsx":
        return await asyncio.to_thread(build_excel, docs, title=title)
    if fmt == "hwp":
        return await asyncio.to_thread(build_hwp, docs, title=title)
    if fmt == "pptx":
        return await asyncio.to_thread(build_pptx_from_docs, docs, title=title)
    raise ExportPacketBuildError("unsupported conversion")


def _write_zip_entry(archive: zipfile.ZipFile, path: str, content: bytes) -> None:
    info = zipfile.ZipInfo(path, date_time=ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = ZIP_CREATE_SYSTEM
    info.external_attr = ZIP_EXTERNAL_ATTR
    info.extra = b""
    info.comment = b""
    archive.writestr(
        info,
        content,
        compress_type=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    )


def _build_zip(artifacts: list[tuple[str, bytes]], manifest_bytes: bytes) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, content in artifacts:
            _write_zip_entry(archive, path, content)
        _write_zip_entry(archive, MANIFEST_PATH, manifest_bytes)
    return output.getvalue()


async def build_generation_export_packet(
    *,
    docs: list[dict[str, Any]],
    title: str,
    tenant_id: str,
    request_id: str,
    formats: str | Sequence[str],
) -> dict[str, Any]:
    """Convert every requested artifact in memory, then self-verify the ZIP."""
    if not all(isinstance(value, str) and value for value in (title, tenant_id, request_id)):
        raise ExportPacketBuildError("source binding is invalid")
    return await _build_export_packet(
        docs=docs,
        title=title,
        formats=formats,
        schema=PACKET_SCHEMA,
        packet_persisted=False,
        source={
            "request_id": request_id,
            "tenant_id": tenant_id,
            "title": title,
        },
    )


async def build_generated_document_review_packet(
    *,
    docs: list[dict[str, Any]],
    title: str,
    tenant_id: str,
    project_id: str,
    project_document_id: str,
    request_id: str,
    bundle_id: str,
    document_source_sha256: str,
    formats: str | Sequence[str],
) -> dict[str, Any]:
    """Build a deterministic packet bound to one persisted project document."""
    source = {
        "bundle_id": bundle_id,
        "document_source_sha256": document_source_sha256,
        "project_document_id": project_document_id,
        "project_id": project_id,
        "request_id": request_id,
        "tenant_id": tenant_id,
        "title": title,
    }
    if any(not isinstance(value, str) or not value for value in source.values()):
        raise ExportPacketBuildError("source binding is invalid")
    if not _is_sha256(document_source_sha256):
        raise ExportPacketBuildError("source fingerprint is invalid")
    return await _build_export_packet(
        docs=docs,
        title=title,
        formats=formats,
        schema=PERSISTED_PACKET_SCHEMA,
        packet_persisted=True,
        source=source,
    )


async def _build_export_packet(
    *,
    docs: list[dict[str, Any]],
    title: str,
    formats: str | Sequence[str],
    schema: str,
    packet_persisted: bool,
    source: dict[str, str],
) -> dict[str, Any]:
    canonical_formats = canonicalize_export_formats(formats)

    artifacts: list[tuple[str, bytes]] = []
    manifest_artifacts: list[dict[str, Any]] = []
    converter_title = _safe_converter_title(title)
    try:
        for fmt in canonical_formats:
            content = await _convert_artifact(fmt, docs=docs, title=converter_title)
            if not isinstance(content, bytes) or not content:
                raise ExportPacketBuildError("converter returned no artifact")
            if len(content) > MAX_ARTIFACT_SIZE_BYTES:
                raise ExportPacketBuildError("artifact exceeds packet size limit")
            spec = FORMAT_SPECS[fmt]
            path = spec["path"]
            artifacts.append((path, content))
            manifest_artifacts.append(
                {
                    "conversion_succeeded": True,
                    "format": fmt,
                    "media_type": spec["media_type"],
                    "path": path,
                    "sha256": _sha256(content),
                    "size_bytes": len(content),
                }
            )
    except GenerationExportPacketError:
        raise
    except Exception as exc:
        raise ExportPacketBuildError("artifact conversion failed") from exc

    manifest = {
        "artifacts": manifest_artifacts,
        "authority": dict(AUTHORITY_FALSE),
        "human_review_completed": False,
        "packet_persisted": packet_persisted,
        "review_only": True,
        "schema": schema,
        "source": source,
    }
    manifest_bytes = _canonical_json_bytes(manifest)
    packet = _build_zip(artifacts, manifest_bytes)
    if len(packet) > MAX_PACKET_SIZE_BYTES:
        raise ExportPacketBuildError("packet exceeds size limit")

    try:
        evidence = verify_generation_export_packet(packet)
    except GenerationExportPacketError:
        raise
    except Exception as exc:
        raise ExportPacketBuildError("packet verification failed") from exc
    return {
        "content": packet,
        "manifest": manifest,
        "manifest_bytes": manifest_bytes,
        "packet_sha256": evidence["packet_sha256"],
        "manifest_sha256": evidence["manifest_sha256"],
        "artifact_count": evidence["artifact_count"],
    }


def _validate_zip_metadata(member: zipfile.ZipInfo) -> None:
    if member.is_dir() or member.date_time != ZIP_TIMESTAMP:
        raise GenerationExportPacketError("packet ZIP metadata is invalid")
    if member.compress_type != zipfile.ZIP_DEFLATED:
        raise GenerationExportPacketError("packet ZIP compression is invalid")
    if (
        member.create_system != ZIP_CREATE_SYSTEM
        or member.create_version != ZIP_VERSION
        or member.extract_version != ZIP_VERSION
        or member.reserved != 0
        or member.volume != 0
        or member.internal_attr != 0
        or member.external_attr != ZIP_EXTERNAL_ATTR
    ):
        raise GenerationExportPacketError("packet ZIP permissions are invalid")
    if member.filename != member.orig_filename or member.extra or member.comment or member.flag_bits != 0:
        raise GenerationExportPacketError("packet ZIP entry has unsupported metadata")
    if member.file_size > MAX_ARTIFACT_SIZE_BYTES:
        raise GenerationExportPacketError("packet ZIP entry exceeds size limit")


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _validate_manifest(manifest_bytes: bytes, entries: dict[str, bytes]) -> dict[str, Any]:
    try:
        text = manifest_bytes.decode("utf-8")
        manifest = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GenerationExportPacketError("packet manifest is not UTF-8 JSON") from exc
    if not isinstance(manifest, dict) or manifest_bytes != _canonical_json_bytes(manifest):
        raise GenerationExportPacketError("packet manifest is not canonical JSON")
    if set(manifest) != {
        "artifacts",
        "authority",
        "human_review_completed",
        "packet_persisted",
        "review_only",
        "schema",
        "source",
    }:
        raise GenerationExportPacketError("packet manifest keys are invalid")
    schema = manifest.get("schema")
    schema_rules = {
        PACKET_SCHEMA: (False, TRANSIENT_SOURCE_KEYS),
        PERSISTED_PACKET_SCHEMA: (True, PERSISTED_SOURCE_KEYS),
    }
    if schema not in schema_rules:
        raise GenerationExportPacketError("packet schema is invalid")
    if manifest.get("review_only") is not True:
        raise GenerationExportPacketError("packet review boundary is invalid")
    if manifest.get("human_review_completed") is not False:
        raise GenerationExportPacketError("packet human review state is invalid")
    expected_persisted, expected_source_keys = schema_rules[schema]
    if manifest.get("packet_persisted") is not expected_persisted:
        raise GenerationExportPacketError("packet persistence state is invalid")
    authority = manifest.get("authority")
    if (
        not isinstance(authority, dict)
        or set(authority) != set(AUTHORITY_FALSE)
        or any(value is not False for value in authority.values())
    ):
        raise GenerationExportPacketError("packet authority boundary is invalid")

    source = manifest.get("source")
    if not isinstance(source, dict) or set(source) != expected_source_keys:
        raise GenerationExportPacketError("packet source binding is invalid")
    if any(not isinstance(source[key], str) or not source[key] for key in source):
        raise GenerationExportPacketError("packet source binding is invalid")
    if schema == PERSISTED_PACKET_SCHEMA and not _is_sha256(
        source["document_source_sha256"]
    ):
        raise GenerationExportPacketError("packet source fingerprint is invalid")

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not 1 <= len(artifacts) <= len(FORMAT_ORDER):
        raise GenerationExportPacketError("packet artifacts are invalid")
    expected_formats: list[str] = []
    expected_paths: list[str] = []
    for artifact in artifacts:
        if not isinstance(artifact, dict) or set(artifact) != {
            "conversion_succeeded",
            "format",
            "media_type",
            "path",
            "sha256",
            "size_bytes",
        }:
            raise GenerationExportPacketError("packet artifact contract is invalid")
        fmt = artifact.get("format")
        if not isinstance(fmt, str) or fmt not in FORMAT_SPECS:
            raise GenerationExportPacketError("packet artifact format is invalid")
        spec = FORMAT_SPECS[fmt]
        if artifact.get("path") != spec["path"] or artifact.get("media_type") != spec["media_type"]:
            raise GenerationExportPacketError("packet artifact path is invalid")
        if artifact.get("conversion_succeeded") is not True:
            raise GenerationExportPacketError("packet conversion evidence is invalid")
        size_bytes = artifact.get("size_bytes")
        sha256 = artifact.get("sha256")
        if (
            not isinstance(size_bytes, int)
            or isinstance(size_bytes, bool)
            or not 0 < size_bytes <= MAX_ARTIFACT_SIZE_BYTES
            or not isinstance(sha256, str)
            or len(sha256) != 64
            or any(char not in "0123456789abcdef" for char in sha256)
        ):
            raise GenerationExportPacketError("packet artifact hash metadata is invalid")
        path = spec["path"]
        content = entries.get(path)
        if content is None or len(content) != size_bytes or _sha256(content) != sha256:
            raise GenerationExportPacketError("packet artifact content does not match manifest")
        expected_formats.append(fmt)
        expected_paths.append(path)
    if len(set(expected_formats)) != len(expected_formats):
        raise GenerationExportPacketError("packet formats are duplicated")
    canonical_formats = [fmt for fmt in FORMAT_ORDER if fmt in expected_formats]
    if expected_formats != canonical_formats:
        raise GenerationExportPacketError("packet artifact order is invalid")
    if set(entries) != {MANIFEST_PATH, *expected_paths}:
        raise GenerationExportPacketError("packet membership is invalid")
    return manifest


def verify_generation_export_packet(content: bytes) -> dict[str, Any]:
    """Verify a packet from ZIP bytes alone without writing or calling external services."""
    if not isinstance(content, bytes) or not content or len(content) > MAX_PACKET_SIZE_BYTES:
        raise GenerationExportPacketError("packet size is invalid")
    try:
        with zipfile.ZipFile(io.BytesIO(content), "r") as archive:
            if archive.comment:
                raise GenerationExportPacketError("packet ZIP comment is invalid")
            members = archive.infolist()
            names = [member.filename for member in members]
            known_paths = {MANIFEST_PATH, *(spec["path"] for spec in FORMAT_SPECS.values())}
            if (
                not members
                or len(names) != len(set(names))
                or any(name not in known_paths for name in names)
                or MANIFEST_PATH not in names
            ):
                raise GenerationExportPacketError("packet ZIP membership is invalid")
            expected_order = [
                FORMAT_SPECS[fmt]["path"] for fmt in FORMAT_ORDER if FORMAT_SPECS[fmt]["path"] in names
            ] + [MANIFEST_PATH]
            if names != expected_order:
                raise GenerationExportPacketError("packet ZIP member order is invalid")
            for member in members:
                _validate_zip_metadata(member)
                if (
                    member.filename == MANIFEST_PATH
                    and member.file_size > MAX_MANIFEST_SIZE_BYTES
                ):
                    raise GenerationExportPacketError("packet manifest exceeds size limit")
            if sum(member.file_size for member in members) > MAX_UNCOMPRESSED_SIZE_BYTES:
                raise GenerationExportPacketError("packet ZIP total size is invalid")
            entries = {name: archive.read(name) for name in names}
    except GenerationExportPacketError:
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        raise GenerationExportPacketError("packet ZIP cannot be read") from exc

    manifest_bytes = entries[MANIFEST_PATH]
    manifest = _validate_manifest(manifest_bytes, entries)
    canonical_artifacts = [
        (FORMAT_SPECS[fmt]["path"], entries[FORMAT_SPECS[fmt]["path"]])
        for fmt in FORMAT_ORDER
        if FORMAT_SPECS[fmt]["path"] in entries
    ]
    if _build_zip(canonical_artifacts, manifest_bytes) != content:
        raise GenerationExportPacketError("packet bytes are not canonical")
    return {
        "artifact_count": len(manifest["artifacts"]),
        "formats": [artifact["format"] for artifact in manifest["artifacts"]],
        "manifest": manifest,
        "manifest_sha256": _sha256(manifest_bytes),
        "packet_persisted": manifest["packet_persisted"],
        "packet_sha256": _sha256(content),
        "schema": manifest["schema"],
        "source": manifest["source"],
        "verified": True,
    }


async def prepare_generation_export_packet_delivery(
    *,
    docs: list[dict[str, Any]],
    title: str,
    tenant_id: str,
    request_id: str,
    formats: str | Sequence[str],
) -> dict[str, Any]:
    """Build, independently verify, and describe one safe HTTP packet delivery."""
    delivery = await build_generation_export_packet(
        docs=docs,
        title=title,
        tenant_id=tenant_id,
        request_id=request_id,
        formats=formats,
    )
    packet_sha256 = delivery["packet_sha256"]
    delivery["filename"] = f"decisiondoc-export-{packet_sha256}.zip"
    delivery["headers"] = {
        "Cache-Control": "no-store",
        "Content-Disposition": f'attachment; filename="decisiondoc-export-{packet_sha256}.zip"',
        "X-Content-Type-Options": "nosniff",
        PACKET_SHA256_HEADER: packet_sha256,
        MANIFEST_SHA256_HEADER: delivery["manifest_sha256"],
        VERIFIED_HEADER: "true",
        ARTIFACT_COUNT_HEADER: str(delivery["artifact_count"]),
        OPERATIONAL_APPROVAL_HEADER: "false",
    }
    return delivery


def build_generation_export_packet_sync(**kwargs: Any) -> dict[str, Any]:
    """Small convenience wrapper for local tools; route code uses the async API."""
    return asyncio.run(build_generation_export_packet(**kwargs))
