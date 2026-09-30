"""Offline state inspection must not become migration or activation authority."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import procurement_transition_preflight as preflight
from tests.test_procurement_multi_opportunity import (
    PATH, _import, _payload, _store,
)
from app.storage.procurement_store import ProcurementDecisionStore
from app.storage.state_backend import LocalStateBackend
from tests.test_procurement_store_integrity import _s3_backend


@pytest.fixture(params=["local", "fake-s3"])
def backend(request, tmp_path):
    return LocalStateBackend(tmp_path) if request.param == "local" else _s3_backend()[0]


@pytest.fixture
def legacy(backend):
    ProcurementDecisionStore(backend=backend).upsert(_payload())
    return json.loads(backend.read_text(PATH))[0]


def _inspect(rows, *, tenant_id="alpha"):
    return preflight.inspect_state(json.dumps(rows).encode(), tenant_id=tenant_id)


def test_legacy_inspection_is_pure_and_not_activation_authority(backend, legacy):
    before = backend.read_text(PATH)
    raw = before.encode()
    report = preflight.inspect_state(raw, tenant_id="alpha")
    assert report["state_contract_status"] == "pass"
    assert report["input_sha256"] == hashlib.sha256(raw).hexdigest()
    assert report["counts"] == {
        "projects": 1, "legacy_projects": 1, "v2_projects": 0,
        "decisions": 1, "requirements": 0, "snapshot_references": 0,
    }
    assert report["legacy_reader_compatible"] is True
    assert report["activation_allowed"] is False
    assert report["source_bytes_verified"] is False
    assert report["writes_performed"] is False
    assert backend.read_text(PATH) == before


def test_mixed_state_cannot_be_rolled_back_by_disabling_flag(backend, legacy):
    _import(_store(backend), payload=_payload("B", project="project-2"))
    before = backend.read_text(PATH)
    report = preflight.inspect_state(before.encode(), tenant_id="alpha")
    assert report["state_contract_status"] == "pass"
    assert report["counts"]["legacy_projects"] == 1
    assert report["counts"]["v2_projects"] == 1
    assert report["legacy_reader_compatible"] is False
    assert report["activation_allowed"] is False
    assert backend.read_text(PATH) == before


@pytest.mark.parametrize("kind,code", [
    ("foreign", "tenant_mismatch"),
    ("nonobject", "invalid_row"),
    ("unknown-schema", "invalid_project_state"),
    ("duplicate-project", "duplicate_project"),
    ("duplicate-decision", "duplicate_decision"),
    ("invalid-history", "invalid_project_state"),
    ("unknown-field", "invalid_project_state"),
])
def test_corrupt_or_unowned_rows_are_not_silently_skipped(legacy, kind, code):
    rows = [copy.deepcopy(legacy)]
    if kind == "foreign":
        rows[0]["tenant_id"] = "other"
    elif kind == "nonobject":
        rows.append(None)
    elif kind == "unknown-schema":
        rows[0]["schema_version"] = "future"
    elif kind.startswith("duplicate"):
        rows.append(copy.deepcopy(legacy))
        if kind == "duplicate-decision":
            rows[1]["project_id"] = "project-2"
    elif kind == "invalid-history":
        rows[0]["_mutation_ids"] = ["duplicate", "duplicate"]
    elif kind == "unknown-field":
        rows[0]["private_unrecognized_data"] = "do not drop"
    report = _inspect(rows)
    assert report["state_contract_status"] == "blocked"
    assert code in {item["code"] for item in report["issues"]}
    assert report["legacy_reader_compatible"] is None
    assert report["counts"] is None


@pytest.mark.parametrize("raw", [
    b"", b"{", b"{}", b"null", b"\xff", b'[{"a":1,"a":2}]',
    b"[NaN]", b"[Infinity]",
])
def test_invalid_json_is_blocked_without_echoing_input(raw):
    report = preflight.inspect_state(raw, tenant_id="alpha")
    assert report["state_contract_status"] == "blocked"
    assert report["issues"] == [{"code": "invalid_state_document"}]


def test_report_does_not_include_content_identifiers_or_validation_errors(legacy):
    legacy["notes"] = "private-note-do-not-print"
    legacy["opportunity"]["title"] = "private-title-do-not-print"
    for rows in ([legacy], [{**legacy, "project_id": "private/invalid/path"}]):
        rendered = json.dumps(_inspect(rows))
        for private in ("private-note", "private-title", legacy["decision_id"], "private/invalid/path"):
            assert private not in rendered


def test_empty_file_is_not_an_empty_state():
    assert preflight.inspect_state(b"[]", tenant_id="alpha")["state_contract_status"] == "pass"
    assert preflight.inspect_state(b"", tenant_id="alpha")["state_contract_status"] == "blocked"


@pytest.mark.parametrize("kind", ["active", "receipt", "revision", "snapshot"])
def test_v2_contract_corruption_is_rejected_without_repair(backend, kind):
    _import(_store(backend))
    before = backend.read_text(PATH)
    rows = json.loads(before)
    project = rows[0]
    if kind == "active":
        project["active_decision_id"] = "absent"
    elif kind == "receipt":
        project["receipts"][0]["decision_revision"] = 999
    elif kind == "revision":
        project["entries"][0]["decision_revision"] = True
    elif kind == "snapshot":
        snapshot = ProcurementDecisionStore(backend=backend).save_source_snapshot(
            tenant_id="other", project_id="project-1", source_kind="g2b_import", payload={},
        )
        project["entries"][0]["record"]["source_snapshots"] = [snapshot.model_dump(mode="json")]
    assert _inspect(rows)["issues"] == [{"row_index": 0, "code": "invalid_project_state"}]
    assert backend.read_text(PATH) == before


def test_valid_snapshot_metadata_does_not_claim_source_verification(backend):
    store = ProcurementDecisionStore(backend=backend)
    payload = _payload()
    payload.source_snapshots = [store.save_source_snapshot(
        tenant_id="alpha", project_id="project-1", source_kind="g2b_import", payload={},
    )]
    store.upsert(payload)
    report = preflight.inspect_state(backend.read_text(PATH).encode(), tenant_id="alpha")
    assert report["counts"]["snapshot_references"] == 1
    assert report["source_bytes_verified"] is False


@pytest.mark.parametrize("replace", [False, True])
def test_read_detects_edit_or_replacement_during_capture(tmp_path, monkeypatch, replace):
    path = tmp_path / "state.json"
    path.write_bytes(b"[]")
    fstat = os.fstat
    calls = 0

    def change_after_read(fd):
        nonlocal calls
        calls += 1
        if calls == 2:
            if replace:
                other = tmp_path / "new.json"
                other.write_bytes(b"[]")
                os.replace(other, path)
            else:
                path.write_bytes(b"[ ]")
        return fstat(fd)

    monkeypatch.setattr(preflight.os, "fstat", change_after_read)
    with pytest.raises(ValueError, match="changed"):
        preflight.read_state_file(path)


def test_invalid_tenant_stops_before_file_access(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("invalid scope must not read a file")
    monkeypatch.setattr(preflight, "read_state_file", forbidden)
    assert preflight.main(["--state-file", str(tmp_path / "missing"), "--tenant-id", "../alpha"]) == 2


@pytest.mark.parametrize("kind", ["missing", "directory", "symlink", "fifo", "oversize"])
def test_cli_refuses_unusable_input_without_creating_or_modifying_files(tmp_path, capsys, monkeypatch, kind):
    path = tmp_path / "state.json"
    if kind == "directory":
        path.mkdir()
    elif kind == "symlink":
        target = tmp_path / "target.json"
        target.write_bytes(b"[]")
        path.symlink_to(target)
    elif kind == "fifo":
        os.mkfifo(path)
    elif kind == "oversize":
        monkeypatch.setattr(preflight, "MAX_STATE_BYTES", 1)
        path.write_bytes(b"[]")
    before = set(tmp_path.iterdir())
    assert preflight.main(["--state-file", str(path), "--tenant-id", "alpha"]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["state_contract_status"] == "blocked"
    assert report["issues"] == [{"code": "input_unavailable"}]
    assert set(tmp_path.iterdir()) == before


def test_cli_hash_mismatch_does_not_parse_or_write(tmp_path, monkeypatch, capsys):
    path = tmp_path / "state.json"
    path.write_bytes(b"[]")
    def forbidden(*args, **kwargs):
        pytest.fail("hash mismatch must not parse state")
    monkeypatch.setattr(preflight, "inspect_state", forbidden)
    assert preflight.main([
        "--state-file", str(path), "--tenant-id", "alpha",
        "--expected-sha256", "0" * 64,
    ]) == 2
    assert json.loads(capsys.readouterr().out)["issues"] == [{"code": "input_hash_mismatch"}]
    assert path.read_bytes() == b"[]"


def test_direct_cli_ignores_env_and_does_not_initialize_app(tmp_path):
    path = tmp_path / "state.json"
    path.write_bytes(b"[]")
    (tmp_path / ".env").write_text("DECISIONDOC_ENV=prod\nDECISIONDOC_STORAGE=s3\n")
    forbidden_data = tmp_path / "must-not-create"
    script = Path(preflight.__file__).resolve()
    result = subprocess.run(
        [sys.executable, "-B", str(script), "--state-file", str(path),
         "--tenant-id", "alpha", "--expected-sha256", hashlib.sha256(b"[]").hexdigest()],
        cwd=tmp_path, env={**os.environ, "DATA_DIR": str(forbidden_data),
                           "DECISIONDOC_STORAGE": "s3", "DECISIONDOC_PROVIDER": "invalid"},
        capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout)["state_contract_status"] == "pass"
    assert not forbidden_data.exists()
    assert path.read_bytes() == b"[]"
