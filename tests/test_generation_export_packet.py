from __future__ import annotations

import io
import json
import struct
import subprocess
import sys
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.services.generation_export_cache import GenerationExportCache, generation_export_cache
from app.services.generation_export_packet import (
    AUTHORITY_FALSE,
    MANIFEST_PATH,
    ExportPacketBuildError,
    GenerationExportPacketError,
    _canonical_json_bytes,
    _write_zip_entry,
    build_generation_export_packet,
    canonicalize_export_formats,
    verify_generation_export_packet,
)
from tests.async_helper import run_async


DOCS = [{"doc_type": "adr", "markdown": "# ADR\n\n검증 본문"}]


def _build_packet(formats: str = "docx,hwp") -> dict:
    return run_async(
        build_generation_export_packet(
            docs=DOCS,
            title="Unsafe / title\\..\x00 with control\ncharacters",
            tenant_id="tenant-a",
            request_id="source-request-1",
            formats=formats,
        )
    )


def _repack(entries: dict[str, bytes], order: list[str]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for path in order:
            _write_zip_entry(archive, path, entries[path])
    return output.getvalue()


def _packet_entries(packet: bytes) -> tuple[dict[str, bytes], list[str]]:
    with zipfile.ZipFile(io.BytesIO(packet)) as archive:
        names = archive.namelist()
        return {name: archive.read(name) for name in names}, names


def _with_central_metadata_drift(content: bytes, field: str) -> bytes:
    data = bytearray(content)
    offset = data.index(b"PK\x01\x02")
    offsets = {
        "timestamp": (14, "<H", 34),
        "create_system": (4, "<H", 20),
        "create_version": (4, "<H", (3 << 8) | 21),
        "extract_version": (6, "<H", 21),
        "flag_bits": (8, "<H", 0x800),
        "volume": (34, "<H", 1),
        "internal_attr": (36, "<H", 1),
        "external_attr": (38, "<I", 0o100600 << 16),
    }
    relative_offset, format_code, value = offsets[field]
    struct.pack_into(format_code, data, offset + relative_offset, value)
    return bytes(data)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (" HWP,docx,DOCX,pdf ", ("docx", "pdf", "hwp")),
        (("pptx", "xlsx", "pptx"), ("xlsx", "pptx")),
    ],
)
def test_canonicalize_export_formats_trims_deduplicates_and_orders(raw, expected):
    assert canonicalize_export_formats(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ("", " , ", "docx,,pdf", "docx,unknown", ("docx", "unknown")),
)
def test_canonicalize_export_formats_rejects_unknown_or_empty_sets(raw):
    from app.services.generation_export_packet import ExportFormatInvalidError

    with pytest.raises(ExportFormatInvalidError):
        canonicalize_export_formats(raw)


def test_packet_uses_fixed_paths_and_canonical_manifest_for_unsafe_title():
    packet = _build_packet("hwp,docx")
    evidence = verify_generation_export_packet(packet["content"])

    assert evidence["verified"] is True
    assert evidence["artifact_count"] == 2
    with zipfile.ZipFile(io.BytesIO(packet["content"])) as archive:
        assert archive.namelist() == [
            "artifacts/document.docx",
            "artifacts/document.hwpx",
            MANIFEST_PATH,
        ]
        assert {info.date_time for info in archive.infolist()} == {(1980, 1, 1, 0, 0, 0)}
        assert {info.external_attr >> 16 for info in archive.infolist()} == {0o100644}
        manifest_bytes = archive.read(MANIFEST_PATH)
    manifest = json.loads(manifest_bytes)
    assert manifest_bytes == _canonical_json_bytes(manifest)
    assert manifest["source"]["title"].startswith("Unsafe /")
    assert manifest["authority"] == {
        "approval_authorized": False,
        "aws_execution_authorized": False,
        "dataset_upload_authorized": False,
        "deployment_authorized": False,
        "g2b_submission_authorized": False,
        "provider_execution_authorized": False,
        "training_execution_authorized": False,
    }


def test_packet_is_byte_identical_for_same_source_and_canonical_format_set():
    first = _build_packet("hwp,docx,docx")
    second = _build_packet("DOCX, HWP")

    assert first["content"] == second["content"]


def test_packet_is_byte_identical_for_all_supported_formats():
    first = _build_packet("pptx,pdf,hwp,xlsx,docx")
    second = _build_packet("DOCX,HWP,PDF,XLSX,PPTX")

    assert first["content"] == second["content"]
    assert verify_generation_export_packet(first["content"])["artifact_count"] == 5


def test_packet_verifier_rejects_tampered_artifact_and_extra_member():
    packet = _build_packet()
    entries, names = _packet_entries(packet["content"])
    entries["artifacts/document.docx"] += b"tampered"
    with pytest.raises(GenerationExportPacketError):
        verify_generation_export_packet(_repack(entries, names))

    entries, names = _packet_entries(packet["content"])
    entries["artifacts/extra.txt"] = b"no"
    with pytest.raises(GenerationExportPacketError):
        verify_generation_export_packet(_repack(entries, [*names[:-1], "artifacts/extra.txt", MANIFEST_PATH]))


@pytest.mark.parametrize(
    ("authority_key", "drift"),
    [
        (authority_key, drift)
        for authority_key in AUTHORITY_FALSE
        for drift in (True, 0, 1, None, "")
    ],
)
def test_packet_verifier_rejects_every_authority_value_type_drift(authority_key, drift):
    packet = _build_packet()
    entries, names = _packet_entries(packet["content"])
    manifest = json.loads(entries[MANIFEST_PATH])
    manifest["authority"][authority_key] = drift
    entries[MANIFEST_PATH] = _canonical_json_bytes(manifest)
    with pytest.raises(GenerationExportPacketError):
        verify_generation_export_packet(_repack(entries, names))


@pytest.mark.parametrize("mutation", ("missing", "extra"))
def test_packet_verifier_rejects_authority_key_set_drift(mutation):
    packet = _build_packet()
    entries, names = _packet_entries(packet["content"])
    manifest = json.loads(entries[MANIFEST_PATH])
    if mutation == "missing":
        manifest["authority"].pop("approval_authorized")
    else:
        manifest["authority"]["unexpected_authority"] = False
    entries[MANIFEST_PATH] = _canonical_json_bytes(manifest)
    with pytest.raises(GenerationExportPacketError):
        verify_generation_export_packet(_repack(entries, names))


def test_packet_verifier_rejects_prefix_and_trailing_bytes():
    packet = _build_packet()
    with pytest.raises(GenerationExportPacketError):
        verify_generation_export_packet(b"prefix" + packet["content"])
    with pytest.raises(GenerationExportPacketError):
        verify_generation_export_packet(packet["content"] + b"trailing")


@pytest.mark.parametrize(
    "field",
    (
        "timestamp",
        "create_system",
        "create_version",
        "extract_version",
        "flag_bits",
        "volume",
        "internal_attr",
        "external_attr",
    ),
)
def test_packet_verifier_rejects_every_mutable_zip_metadata_drift(field):
    packet = _build_packet()
    with pytest.raises(GenerationExportPacketError):
        verify_generation_export_packet(_with_central_metadata_drift(packet["content"], field))


def test_packet_build_is_all_or_nothing_when_converter_fails(monkeypatch):
    def fail_converter(*args, **kwargs):
        raise RuntimeError("converter failed")

    monkeypatch.setattr("app.services.generation_export_packet.build_docx", fail_converter)
    with pytest.raises(ExportPacketBuildError):
        _build_packet("docx,hwp")


def test_sync_converters_run_off_the_event_loop(monkeypatch):
    observed: list[str] = []

    async def tracked_to_thread(func, *args, **kwargs):
        observed.append(func.__name__)
        return func(*args, **kwargs)

    monkeypatch.setattr("app.services.generation_export_packet.asyncio.to_thread", tracked_to_thread)
    monkeypatch.setattr("app.services.generation_export_packet.build_docx", lambda *_args, **_kwargs: b"docx")
    monkeypatch.setattr("app.services.generation_export_packet.build_excel", lambda *_args, **_kwargs: b"xlsx")
    monkeypatch.setattr("app.services.generation_export_packet.build_hwp", lambda *_args, **_kwargs: b"hwp")
    monkeypatch.setattr("app.services.generation_export_packet.build_pptx_from_docs", lambda *_args, **_kwargs: b"pptx")

    run_async(
        build_generation_export_packet(
            docs=DOCS,
            title="threaded",
            tenant_id="tenant-a",
            request_id="threaded-request",
            formats="docx,xlsx,hwp,pptx",
        )
    )

    assert observed == ["<lambda>", "<lambda>", "<lambda>", "<lambda>"]


def test_generation_export_cache_is_tenant_scoped_deep_copied_ttl_bounded_and_lru():
    now = [100.0]
    cache = GenerationExportCache(ttl_seconds=60, max_entries=2, clock=lambda: now[0])
    source_docs = [{"doc_type": "adr", "markdown": "original"}]
    cache.store(tenant_id="tenant-a", request_id="one", docs=source_docs, title="one")
    source_docs[0]["markdown"] = "changed after store"
    cached = cache.get(tenant_id="tenant-a", request_id="one")
    assert cached == ([{"doc_type": "adr", "markdown": "original"}], "one")
    assert cache.get(tenant_id="tenant-b", request_id="one") is None

    cached[0][0]["markdown"] = "changed after read"
    assert cache.get(tenant_id="tenant-a", request_id="one")[0][0]["markdown"] == "original"
    cache.store(tenant_id="tenant-a", request_id="two", docs=DOCS, title="two")
    assert cache.get(tenant_id="tenant-a", request_id="one") is not None
    cache.store(tenant_id="tenant-a", request_id="three", docs=DOCS, title="three")
    assert cache.get(tenant_id="tenant-a", request_id="two") is None
    now[0] += 60
    assert cache.get(tenant_id="tenant-a", request_id="one") is None


@pytest.fixture
def packet_client(tmp_path, monkeypatch):
    generation_export_cache.clear()
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_STORAGE", "local")
    monkeypatch.setenv("DECISIONDOC_STATE_STORAGE", "local")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.setenv("JWT_SECRET_KEY", "generation-export-packet-test-secret-key")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    from app.main import create_app

    with TestClient(create_app()) as client:
        yield client
    generation_export_cache.clear()


def _auth_headers(client: TestClient, *, tenant_id: str = "system") -> dict[str, str]:
    from app.services.auth_service import create_access_token
    from app.storage.user_store import get_user_store

    store = get_user_store(
        tenant_id,
        data_dir=client.app.state.data_dir,
        backend=client.app.state.state_backend,
    )
    user = store.get_by_username("packet-test-user")
    if user is None:
        user = store.create(
            username="packet-test-user",
            display_name="Packet Test User",
            email="packet-test@example.test",
            password="PacketTest1!",
            role="admin",
        )
    elif user.role.value != "admin":
        user = store.update(user.user_id, role="admin")
    token = create_access_token(user.user_id, tenant_id, user.role.value, user.username)
    return {"Authorization": f"Bearer {token}"}


def test_generate_and_stream_populate_source_cache(packet_client):
    headers = _auth_headers(packet_client)
    generated = packet_client.post("/generate", json={"title": "cache", "goal": "cache test"}, headers=headers)
    assert generated.status_code == 200
    assert generation_export_cache.get(tenant_id="system", request_id=generated.json()["request_id"]) is not None

    streamed = packet_client.post("/generate/stream", json={"title": "stream", "goal": "stream test"}, headers=headers)
    assert streamed.status_code == 200
    assert "event: complete" in streamed.text
    request_id = next(
        line.removeprefix("data: ")
        for line in streamed.text.splitlines()
        if line.startswith("data: {") and '"request_id"' in line
    )
    assert generation_export_cache.get(tenant_id="system", request_id=json.loads(request_id)["request_id"]) is not None


def test_export_route_delivers_verified_packet_headers_and_hides_source_on_failure(packet_client, monkeypatch):
    headers = _auth_headers(packet_client)
    from app.routers.generate import _store_zip_docs

    _store_zip_docs("route-source", DOCS, "unsafe/route title", tenant_id="system")
    response = packet_client.get(
        "/generate/export-zip?request_id=route-source&formats=HWP,docx,docx",
        headers=headers,
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-decisiondoc-export-verified"] == "true"
    assert response.headers["x-decisiondoc-operational-approval"] == "false"
    evidence = verify_generation_export_packet(response.content)
    assert response.headers["x-decisiondoc-export-packet-sha256"] == evidence["packet_sha256"]
    assert response.headers["x-decisiondoc-export-manifest-sha256"] == evidence["manifest_sha256"]
    assert response.headers["x-decisiondoc-export-artifact-count"] == str(evidence["artifact_count"])
    assert response.headers["content-disposition"] == (
        f'attachment; filename="decisiondoc-export-{evidence["packet_sha256"]}.zip"'
    )
    from app.storage.audit_store import AuditStore

    audit_entries = AuditStore(
        "system",
        data_dir=packet_client.app.state.data_dir,
        backend=packet_client.app.state.state_backend,
    ).query()
    download_audit = next(entry for entry in audit_entries if entry["action"] == "doc.download")
    assert download_audit["detail"] == {
        "duration_ms": download_audit["detail"]["duration_ms"],
        "method": "GET",
        "path": "/generate/export-zip",
        "status_code": 200,
    }

    missing = packet_client.get("/generate/export-zip?request_id=missing", headers=headers)
    assert missing.status_code == 404
    assert missing.json()["code"] == "EXPORT_SOURCE_NOT_FOUND"
    assert missing.headers["cache-control"] == "no-store"
    assert missing.headers["x-content-type-options"] == "nosniff"

    packet_client.app.state.tenant_store.create_tenant("tenant-b", "Tenant B")
    foreign = packet_client.get(
        "/generate/export-zip?request_id=route-source",
        headers=_auth_headers(packet_client, tenant_id="tenant-b"),
    )
    assert foreign.status_code == missing.status_code
    assert foreign.json()["code"] == missing.json()["code"]
    assert foreign.json()["message"] == missing.json()["message"]
    assert foreign.headers["cache-control"] == missing.headers["cache-control"]

    invalid = packet_client.get(
        "/generate/export-zip?request_id=route-source&formats=docx,,pdf",
        headers=headers,
    )
    assert invalid.status_code == 400
    assert invalid.json()["code"] == "EXPORT_FORMAT_INVALID"
    assert invalid.headers["cache-control"] == "no-store"
    assert invalid.headers["x-content-type-options"] == "nosniff"

    async def fail_packet(**kwargs):
        raise ExportPacketBuildError("unsafe/route title should not be disclosed")

    monkeypatch.setattr("app.routers.generate.export_packet.prepare_generation_export_packet_delivery", fail_packet)
    failed = packet_client.get("/generate/export-zip?request_id=route-source", headers=headers)
    assert failed.status_code == 500
    assert failed.json()["code"] == "EXPORT_PACKET_FAILED"
    assert "unsafe" not in failed.text


def test_standalone_verifier_is_read_only_and_reports_verified_packet(tmp_path):
    packet = _build_packet()
    path = tmp_path / "packet.zip"
    path.write_bytes(packet["content"])
    result = subprocess.run(
        [sys.executable, "scripts/verify_generation_export_packet.py", str(path)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert json.loads(result.stdout)["status"] == "verified"
    assert path.read_bytes() == packet["content"]
