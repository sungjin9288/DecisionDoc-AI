"""Cold-process transition and offline whole-fixture restore, never live DATA_DIR."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace
from uuid import uuid4


REPO_ROOT = Path(__file__).resolve().parents[1]
RESULT_PREFIX = "PROCUREMENT_PROBE_RESULT="
STATE_PATH = "tenants/system/procurement_decisions.json"
BOOTSTRAP = """
import json, socket, sys, dotenv
dotenv.load_dotenv = lambda *args, **kwargs: False
def no_network(*args, **kwargs):
    raise AssertionError("Network calls are forbidden in the restart fixture")
socket.create_connection = no_network
socket.socket.connect = no_network
socket.socket.connect_ex = no_network
from tests.test_procurement_transition_process import _child_probe
_child_probe(json.load(sys.stdin))
"""


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _inventory(root: Path) -> dict[str, str]:
    return {str(path.relative_to(root)): _sha(path.read_bytes())
            for path in root.rglob("*") if path.is_file()}


def _run_child(root: Path, mode: str, evidence: dict | None = None) -> dict:
    environment = {
        "PATH": os.environ.get("PATH", os.defpath),
        "PYTHONPATH": os.pathsep.join(filter(None, [str(REPO_ROOT), os.environ.get("PYTHONPATH")])),
        "PYTHONDONTWRITEBYTECODE": "1",
        "DATA_DIR": str(root),
        "DECISIONDOC_ENV": "dev",
        "DECISIONDOC_PROVIDER": "mock",
        "DECISIONDOC_STORAGE": "local",
        "DECISIONDOC_API_KEY": "test-key",
        "DECISIONDOC_PROCUREMENT_COPILOT_ENABLED": "1",
        "AWS_SHARED_CREDENTIALS_FILE": os.devnull,
        "AWS_CONFIG_FILE": os.devnull,
        "AWS_EC2_METADATA_DISABLED": "true",
    }
    completed = subprocess.run(
        [sys.executable, "-B", "-c", BOOTSTRAP],
        input=json.dumps({"mode": mode, "evidence": evidence}),
        cwd=root.parent, env=environment, capture_output=True, text=True, timeout=90,
    )
    assert completed.returncode == 0, completed.stderr[-10000:]
    results = [line.removeprefix(RESULT_PREFIX) for line in completed.stdout.splitlines()
               if line.startswith(RESULT_PREFIX)]
    assert len(results) == 1, completed.stdout[-3000:]
    return json.loads(results[0])


def _child_probe(payload: dict) -> None:
    # Imports happen only after the subprocess disables dotenv and network calls.
    from fastapi.testclient import TestClient
    from app.main import create_app
    from scripts.procurement_transition_preflight import inspect_state
    from tests.test_procurement_applicability_lifecycle import _complete, _packet
    from tests.test_procurement_multi_opportunity import _payload
    from tests.test_procurement_review_authorization import _login_existing, _ready_project
    from tests.test_procurement_scoped_lifecycle import API_HEADERS, _login_admin
    from tests.test_procurement_transition_lifecycle import _attach_source, _legacy_packet, _saved_evidence

    mode = payload["mode"]
    assert mode in {"seed", "transition", "check", "restore"}
    expected = payload["evidence"]
    app = create_app(procurement_multi_opportunity_enabled=mode in {"transition", "check"})
    backend = app.state.state_backend
    with TestClient(app) as client:
        app_scope = SimpleNamespace(app=app, client=client, backend=backend)
        if mode == "seed":
            admin = _login_admin(client)
            project_id = _ready_project(client, admin, name="Offline backup fixture")
            record = _attach_source(app_scope, project_id)
            scope = SimpleNamespace(**vars(app_scope), project_id=project_id, base=f"/projects/{project_id}")
            packet = _legacy_packet(scope, admin)
            completed = _complete(scope, packet, admin)
            assert completed.status_code == 200, completed.text
            result = {
                "project_id": project_id, "decision_id": record.decision_id,
                "legacy_packet_sha256": _sha(packet.content),
                "legacy_completed_sha256": _sha(completed.content),
            }
        else:
            project_id = expected["project_id"]
            scope = SimpleNamespace(**vars(app_scope), project_id=project_id, base=f"/projects/{project_id}")
            assert _sha(backend.read_bytes(STATE_PATH)) == expected["state_sha256"]
            before_evidence = _saved_evidence(backend)
            admin = _login_existing(client, "scoped-admin")
            sha = expected["legacy_packet_sha256"]
            packet = client.get(scope.base + f"/procurement/reviews/{sha}/packet", headers=admin)
            assert packet.status_code == 200, packet.text
            assert _sha(packet.content) == sha
            completed = _complete(scope, packet, admin)
            assert completed.status_code == 200, completed.text
            assert _sha(completed.content) == expected["legacy_completed_sha256"]
            assert _saved_evidence(backend) == before_evidence
            result = dict(expected)
            if mode == "transition":
                selection = {"decision_id": expected["decision_id"], "expected_selection_revision": 0,
                             "operation_id": str(uuid4())}
                selected = client.post(scope.base + "/procurement/selection", json=selection, headers=API_HEADERS)
                assert selected.status_code == 200, selected.text
                imported = app.state.procurement_opportunity_store.import_opportunity(
                    _payload("B", project=project_id, tenant="system"), expected_selection_revision=0,
                    expected_decision_revision=0, operation_id=str(uuid4()),
                )
                assert _saved_evidence(backend) == before_evidence
                bound = _packet(scope, expected["decision_id"], 1, admin)
                assert bound.status_code == 200, bound.text
                bound_completed = _complete(scope, bound, admin)
                assert bound_completed.status_code == 200, bound_completed.text
                result.update(selection=selection, selection_response=selected.json(),
                              active_decision_id=imported.decision_id,
                              bound_packet_sha256=_sha(bound.content),
                              bound_completed_sha256=_sha(bound_completed.content))
            elif mode == "check":
                listed = client.get(scope.base + "/procurement/opportunities", headers=API_HEADERS)
                assert listed.status_code == 200, listed.text
                assert listed.json()["total"] == 2
                assert listed.json()["active_decision_id"] == expected["active_decision_id"]
                replay = client.post(scope.base + "/procurement/selection",
                                     json=expected["selection"], headers=API_HEADERS)
                assert replay.status_code == 200, replay.text
                assert replay.json() == expected["selection_response"]
                sha = expected["bound_packet_sha256"]
                bound = client.get(scope.base + f"/procurement/reviews/{sha}/packet", headers=admin)
                assert bound.status_code == 200, bound.text
                assert _sha(bound.content) == sha
                bound_completed = _complete(scope, bound, admin)
                assert bound_completed.status_code == 200, bound_completed.text
                assert _sha(bound_completed.content) == expected["bound_completed_sha256"]
            else:
                assert not hasattr(app.state, "procurement_opportunity_store")
                record = app.state.procurement_store.get(project_id, tenant_id="system")
                assert record.decision_id == expected["decision_id"]
            if mode != "transition":
                assert _sha(backend.read_bytes(STATE_PATH)) == expected["state_sha256"]
                assert _saved_evidence(backend) == before_evidence
        raw = backend.read_bytes(STATE_PATH)
        report = inspect_state(raw, tenant_id="system")
        assert report["state_contract_status"] == "pass"
        assert report["legacy_reader_compatible"] == (mode in {"seed", "restore"})
        result.update(state_sha256=_sha(raw), pid=os.getpid(),
                      evidence={path: _sha(content) for path, content in _saved_evidence(backend).items()})
    print(RESULT_PREFIX + json.dumps(result, sort_keys=True))


def test_cold_process_transition_and_whole_fixture_restore(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    # A hostile working-directory dotenv must never activate a real provider.
    (tmp_path / ".env").write_text("DECISIONDOC_PROVIDER=openai\nDECISIONDOC_STORAGE=s3\n")
    seeded = _run_child(source, "seed")
    baseline = _inventory(source)
    assert STATE_PATH in baseline
    backup = tmp_path / "backup"
    shutil.copytree(source, backup)
    assert _inventory(backup) == baseline

    rehearsal = tmp_path / "rehearsal"
    shutil.copytree(backup, rehearsal)
    transitioned = _run_child(rehearsal, "transition", seeded)
    assert transitioned["state_sha256"] != seeded["state_sha256"]
    assert set(transitioned["evidence"]) > set(seeded["evidence"])
    for path, digest in seeded["evidence"].items():
        assert transitioned["evidence"][path] == digest
    reopened = _run_child(rehearsal, "check", transitioned)
    assert reopened["state_sha256"] == transitioned["state_sha256"]
    assert reopened["evidence"] == transitioned["evidence"]
    v2_inventory = _inventory(rehearsal)

    restored = tmp_path / "restored"
    shutil.copytree(backup, restored)
    assert _inventory(restored) == baseline
    recovered = _run_child(restored, "restore", seeded)
    assert recovered["state_sha256"] == seeded["state_sha256"]
    assert recovered["evidence"] == seeded["evidence"]
    assert _inventory(source) == _inventory(backup) == baseline
    assert _inventory(rehearsal) == v2_inventory
    assert os.getpid() not in {result["pid"] for result in (seeded, transitioned, reopened, recovered)}
