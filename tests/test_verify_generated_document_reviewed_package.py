from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
import zipfile
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.generation_export_packet import (
    AUTHORITY_FALSE,
    build_generated_document_review_packet,
    verify_generation_export_packet,
)
from app.storage.generated_document_review_models import (
    MAX_REVIEWED_PACKAGE_SIZE_BYTES,
    RECORD_SCHEMA,
    REVIEWED_PACKAGE_MANIFEST_PATH,
    REVIEWED_PACKAGE_PACKET_PATH,
    REVIEWED_PACKAGE_RECEIPT_PATH,
    GeneratedDocumentReviewRecord,
    build_generated_document_reviewed_package,
)
from tests.async_helper import run_async


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/verify_generated_document_reviewed_package.py"
RESULT_SCHEMA = "decisiondoc.generated_document_reviewed_package.verification.v1"


@pytest.fixture(scope="module")
def reviewed_packages():
    source = {
        "tenant_id": "private-tenant",
        "project_id": "private-project",
        "project_document_id": "private-document",
        "request_id": "private-request",
        "bundle_id": "private-bundle",
        "title": "Private review title",
        "document_source_sha256": "a" * 64,
    }
    packet = run_async(
        build_generated_document_review_packet(
            docs=[
                {
                    "doc_type": "adr",
                    "markdown": "# Private source\n\nSynthetic evidence.",
                }
            ],
            formats=("docx",),
            **source,
        )
    )
    verified = verify_generation_export_packet(packet["content"])
    reviewer = {
        "user_id": "private-user",
        "username": "private-reviewer",
        "role": "member",
    }
    record = GeneratedDocumentReviewRecord(
        schema_version=RECORD_SCHEMA,
        **source,
        packet_sha256=verified["packet_sha256"],
        packet_size_bytes=len(packet["content"]),
        manifest_sha256=verified["manifest_sha256"],
        artifact_count=verified["artifact_count"],
        formats=verified["formats"],
        prepared_at="2026-09-05T00:00:00Z",
        creator_assignment={
            "user_id": "private-admin",
            "username": "creator",
            "role": "admin",
        },
        reviewer_assignment=reviewer,
        review_status="pending",
        review_only=True,
        packet_persisted=True,
        human_review_completed=False,
        operational_approval=False,
        authority=dict(AUTHORITY_FALSE),
    )
    return {
        decision: build_generated_document_reviewed_package(
            record,
            packet["content"],
            completion_assignment=reviewer,
            operation_id="11111111-1111-4111-8111-111111111111",
            decision=decision,
            rationale="Private rationale must never reach stdout or stderr.",
            reviewed_at="2026-09-05T00:05:00Z",
        )
        for decision in ("accepted", "changes_requested", "rejected")
    }


def _run_cli(path: Path):
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(path)],
        cwd=path.parent,
        env={"PATH": os.defpath},
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )


@pytest.mark.parametrize("decision", ("accepted", "changes_requested", "rejected"))
def test_cli_reports_only_deterministic_redacted_evidence(
    tmp_path, reviewed_packages, decision
):
    package, receipt, receipt_sha256 = reviewed_packages[decision]
    path = tmp_path / "private-path.zip"
    path.write_bytes(package)
    result = _run_cli(path)
    replay = _run_cli(path)

    assert result.returncode == replay.returncode == 0
    assert result.stderr == replay.stderr == ""
    assert result.stdout == replay.stdout
    summary = json.loads(result.stdout)
    assert summary["operational_approval"] is False
    assert summary == {
        "schema_version": RESULT_SCHEMA,
        "status": "verified",
        "packet_sha256": receipt["packet_sha256"],
        "completion_receipt_sha256": receipt_sha256,
        "reviewed_package_sha256": hashlib.sha256(package).hexdigest(),
        "reviewed_package_size_bytes": len(package),
        "review_decision": decision,
        "operational_approval": False,
    }
    assert "private" not in result.stdout.lower()
    assert receipt["completion_operation_id"] not in result.stdout
    assert path.read_bytes() == package
    assert list(tmp_path.iterdir()) == [path]


def _mutate_package(package: bytes, mutation: str) -> bytes:
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        entries = archive.infolist()
        contents = {entry.filename: archive.read(entry) for entry in entries}
    if mutation == "original_packet":
        return contents[REVIEWED_PACKAGE_PACKET_PATH]
    if mutation == "bad_deflate":
        entry = entries[1]
        start = (
            entry.header_offset + 30 + len(entry.filename.encode()) + len(entry.extra)
        )
        changed = bytearray(package)
        changed[start] = 0x07  # Reserved DEFLATE block type.
        return bytes(changed)
    if mutation == "packet":
        contents[REVIEWED_PACKAGE_PACKET_PATH] += b"tampered"
    elif mutation == "receipt":
        contents[REVIEWED_PACKAGE_RECEIPT_PATH] = b"{}\n"
    elif mutation == "manifest":
        contents[REVIEWED_PACKAGE_MANIFEST_PATH] = b"{}\n"
    elif mutation == "duplicate_json_key":
        contents[REVIEWED_PACKAGE_RECEIPT_PATH] = b'{"private":1,"private":2}\n'
    elif mutation == "deep_json":
        contents[REVIEWED_PACKAGE_RECEIPT_PATH] = (
            b'{"private":' + b"[" * 2000 + b"0" + b"]" * 2000 + b"}\n"
        )
    elif mutation in {"authority_type", "count_type", "decision_type"}:
        receipt = json.loads(contents[REVIEWED_PACKAGE_RECEIPT_PATH])
        if mutation == "authority_type":
            receipt["authority"]["approval_authorized"] = 0
        elif mutation == "count_type":
            receipt["packet"]["artifact_count"] = True
        else:
            receipt["review_decision"] = ["accepted"]
        receipt_bytes = (
            json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode()
        contents[REVIEWED_PACKAGE_RECEIPT_PATH] = receipt_bytes
        manifest = json.loads(contents[REVIEWED_PACKAGE_MANIFEST_PATH])
        manifest["entries"][1].update(
            sha256=hashlib.sha256(receipt_bytes).hexdigest(),
            size_bytes=len(receipt_bytes),
        )
        contents[REVIEWED_PACKAGE_MANIFEST_PATH] = (
            json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode()

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for entry in entries:
            archive.writestr(entry, contents[entry.filename])
        if mutation == "extra_member":
            archive.writestr("unexpected.txt", b"private")
        elif mutation == "duplicate_member":
            with pytest.warns(UserWarning, match="Duplicate name"):
                archive.writestr(entries[0], contents[entries[0].filename])
    return output.getvalue()


@pytest.mark.parametrize(
    "mutation",
    (
        "original_packet",
        "packet",
        "receipt",
        "manifest",
        "extra_member",
        "duplicate_member",
        "duplicate_json_key",
        "authority_type",
        "count_type",
        "decision_type",
        "bad_deflate",
        "deep_json",
    ),
)
def test_cli_rejects_malformed_packages_without_disclosure(
    tmp_path, reviewed_packages, mutation
):
    content = _mutate_package(reviewed_packages["accepted"][0], mutation)
    path = tmp_path / "private-invalid.zip"
    path.write_bytes(content)

    result = _run_cli(path)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == "verification failed\n"
    assert path.read_bytes() == content
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize(
    "kind",
    ("missing", "directory", "symlink", "dangling", "fifo", "empty", "oversized"),
)
def test_cli_rejects_nonregular_or_out_of_bounds_inputs(
    tmp_path, reviewed_packages, kind
):
    path = tmp_path / "private-input.zip"
    if kind == "directory":
        path.mkdir()
    elif kind in {"symlink", "dangling"}:
        target = tmp_path / "target.zip"
        if kind == "symlink":
            target.write_bytes(reviewed_packages["accepted"][0])
        path.symlink_to(target)
    elif kind == "fifo":
        os.mkfifo(path)
    elif kind in {"empty", "oversized"}:
        with path.open("wb") as stream:
            stream.truncate(
                0 if kind == "empty" else MAX_REVIEWED_PACKAGE_SIZE_BYTES + 1
            )
    before = path.lstat() if kind != "missing" else None

    result = _run_cli(path)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == "verification failed\n"
    if before is not None:
        after = path.lstat()
        assert (after.st_ino, after.st_mode, after.st_size, after.st_mtime_ns) == (
            before.st_ino,
            before.st_mode,
            before.st_size,
            before.st_mtime_ns,
        )
    else:
        assert not path.exists()
    if kind == "symlink":
        assert target.read_bytes() == reviewed_packages["accepted"][0]


@pytest.mark.parametrize("stage", ("open", "read"))
def test_cli_hides_io_errors(tmp_path, monkeypatch, capsys, reviewed_packages, stage):
    from scripts import verify_generated_document_reviewed_package as cli

    path = tmp_path / "private.zip"
    path.write_bytes(reviewed_packages["accepted"][0])

    @contextmanager
    def failing_open(*args, **kwargs):
        if stage == "open":
            raise PermissionError("private path and credential details")
        with open(*args, **kwargs) as stream:

            def fail_read(_size):
                raise OSError("private disk error")

            yield SimpleNamespace(fileno=stream.fileno, read=fail_read)

    monkeypatch.setattr(cli, "open", failing_open, raising=False)
    assert cli.main([str(path)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "verification failed\n"


@pytest.mark.parametrize("delta", (-1, 0, 1))
def test_cli_reads_with_a_fixed_limit_and_rejects_short_or_growing_input(
    tmp_path, reviewed_packages, monkeypatch, capsys, delta
):
    from scripts import verify_generated_document_reviewed_package as cli

    path = tmp_path / "private.zip"
    package = reviewed_packages["accepted"][0]
    path.write_bytes(package)
    reads = []

    @contextmanager
    def observed_open(*args, **kwargs):
        with open(*args, **kwargs) as stream:

            def observed_read(size):
                reads.append(size)
                content = stream.read(size)
                return content[:-1] if delta < 0 else content + b"x" * delta

            yield SimpleNamespace(fileno=stream.fileno, read=observed_read)

    monkeypatch.setattr(cli, "open", observed_open, raising=False)
    assert cli.main([str(path)]) == (0 if delta == 0 else 1)
    assert reads == [MAX_REVIEWED_PACKAGE_SIZE_BYTES + 1]
    captured = capsys.readouterr()
    if delta:
        assert captured.out == ""
        assert captured.err == "verification failed\n"
    else:
        assert json.loads(captured.out)["status"] == "verified"
        assert captured.err == ""
    assert path.read_bytes() == package


@pytest.mark.parametrize("delta", (-1, 1))
def test_cli_rechecks_open_descriptor_size_after_read(
    tmp_path, reviewed_packages, monkeypatch, capsys, delta
):
    from scripts import verify_generated_document_reviewed_package as cli

    path = tmp_path / "private.zip"
    path.write_bytes(reviewed_packages["accepted"][0])
    before = path.stat()
    observations = iter((before, SimpleNamespace(st_size=before.st_size + delta)))
    descriptors = []

    def observe_stat(fd):
        descriptors.append(fd)
        return next(observations)

    monkeypatch.setattr(cli.os, "fstat", observe_stat)
    assert cli.main([str(path)]) == 1
    assert len(descriptors) == 2 and descriptors[0] == descriptors[1]
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "verification failed\n"


def test_cli_fails_closed_without_safe_open_flags(tmp_path, monkeypatch, capsys):
    from scripts import verify_generated_document_reviewed_package as cli

    path = tmp_path / "private.zip"
    path.write_bytes(b"not a package")
    monkeypatch.delattr(cli.os, "O_NOFOLLOW")

    assert cli.main([str(path)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "verification failed\n"


def test_cli_preserves_argparse_usage_and_help(capsys):
    from scripts import verify_generated_document_reviewed_package as cli

    with pytest.raises(SystemExit) as missing:
        cli.main([])
    assert missing.value.code == 2
    assert "usage:" in capsys.readouterr().err
    with pytest.raises(SystemExit) as help_result:
        cli.main(["--help"])
    assert help_result.value.code == 0
    assert "does not authenticate" in " ".join(capsys.readouterr().out.split())


def test_cli_avoids_runtime_startup_network_credentials_and_writes(
    tmp_path, reviewed_packages
):
    path = tmp_path / "private.zip"
    content = reviewed_packages["accepted"][0]
    path.write_bytes(content)
    guard = r"""
import os
import runpy
import sys

def audit(event, args):
    if event == "import":
        name = args[0]
        blocked = ("app.main", "app.storage.state_backend",
                   "app.storage.generated_document_review_store", "dotenv", "boto3")
        assert not any(name == item or name.startswith(item + ".") for item in blocked), name
        if name.startswith("app.providers."):
            assert name == "app.providers.base", name
    if event == "open":
        path, mode, flags = args
        assert not flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
        if isinstance(path, str):
            assert not any(part in path.split(os.sep) for part in (".env", ".env.prod", ".aws", "credentials"))
    assert not event.startswith("socket."), event
    assert event not in ("subprocess.Popen", "os.system", "os.mkdir", "os.remove",
                         "os.rename", "os.rmdir", "os.truncate", "os.chmod", "os.symlink"), event

sys.addaudithook(audit)
sys.argv = sys.argv[1:]
runpy.run_path(sys.argv[0], run_name="__main__")
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", guard, str(SCRIPT), str(path)],
        cwd=tmp_path,
        env={"PATH": os.defpath},
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout)["status"] == "verified"
    assert path.read_bytes() == content
    assert list(tmp_path.iterdir()) == [path]
