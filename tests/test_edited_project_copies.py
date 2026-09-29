from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from uuid import uuid4
import json
from unittest.mock import patch

import pytest

from app.schemas.edited_project_copies import SaveEditedCopyRequest
from app.services.edited_project_copy_service import (
    EditedCopyConflict,
    save_edited_copy,
    source_hash,
)
from app.storage.project_store import ProjectStore, ProjectStoreError
from tests.test_project_approval_store_integrity import _s3_backend


@pytest.fixture(params=["local", "s3"])
def source(tmp_path, request):
    backend = _s3_backend()[0] if request.param == "s3" else None
    store = ProjectStore(str(tmp_path), backend=backend)
    project = store.create(tenant_id="alpha", name="Project")
    doc = store.add_document(
        project.project_id,
        "original-request",
        "tech_decision",
        "Original",
        [{"doc_type": "adr", "markdown": "# Original"}],
        tenant_id="alpha",
    )
    payload = SaveEditedCopyRequest(
        operation_id=str(uuid4()),
        parent_sha256=source_hash(doc),
        title="Edited",
        docs=[{"doc_type": "adr", "markdown": "# Edited"}],
    )
    return store, project, doc, payload


def save(source, payload=None, **overrides):
    store, project, doc, default = source
    args = dict(
        tenant_id="alpha",
        actor_id="actor",
        project_id=project.project_id,
        parent_id=doc.doc_id,
        payload=payload or default,
    )
    args.update(overrides)
    return save_edited_copy(store, **args)


def test_copy_reload_replay_and_original_preservation(source):
    store, project, original, payload = source
    copy = save(source)
    restored = ProjectStore(store._base, backend=store._backend)
    docs = restored.get(project.project_id, tenant_id="alpha").documents
    assert asdict(docs[0]) == asdict(original)
    assert docs[1].doc_id == copy.doc_id
    assert json.loads(docs[1].doc_snapshot)[0]["markdown"] == "# Edited"
    assert docs[1].request_id == ""
    assert docs[1].approval_id is None and docs[1].approval_status is None
    assert (
        save_edited_copy(
            restored,
            tenant_id="alpha",
            actor_id="actor",
            project_id=project.project_id,
            parent_id=original.doc_id,
            payload=payload,
        ).doc_id
        == copy.doc_id
    )
    assert len(restored.get(project.project_id, tenant_id="alpha").documents) == 2


def test_conflicts_and_foreign_parent_preserve_state(source):
    store, _, _, payload = source
    save(source)
    before = store._backend.read_text("tenants/alpha/projects.json")
    with pytest.raises(EditedCopyConflict):
        save(source, payload.model_copy(update={"title": "Changed"}))
    with pytest.raises(EditedCopyConflict):
        save(
            source,
            payload.model_copy(
                update={"operation_id": str(uuid4()), "parent_sha256": "0" * 64}
            ),
        )
    with pytest.raises(KeyError):
        save(source, tenant_id="foreign")
    with pytest.raises(KeyError):
        save(
            source,
            parent_id="missing",
            payload=payload.model_copy(update={"operation_id": str(uuid4())}),
        )
    assert store._backend.read_text("tenants/alpha/projects.json") == before


def test_concurrent_exact_save_is_one_copy(source):
    with ThreadPoolExecutor(max_workers=6) as pool:
        ids = list(pool.map(lambda _: save(source).doc_id, range(12)))
    assert len(set(ids)) == 1
    store, project, _, _ = source
    assert len(store.get(project.project_id, tenant_id="alpha").documents) == 2


def test_corrupt_copy_is_not_rewritten(source):
    store, _, _, _ = source
    save(source)
    path = "tenants/alpha/projects.json"
    records = json.loads(store._backend.read_text(path))
    records[0]["documents"][1]["doc_snapshot"] = "[]"
    broken = json.dumps(records)
    store._backend.write_text(path, broken)
    with pytest.raises(ProjectStoreError):
        save(source)
    assert store._backend.read_text(path) == broken


def test_parent_changed_during_cas_is_not_overwritten(source):
    store, project, _, _ = source

    def race(path, *, expected, replacement, **kwargs):
        records = json.loads(expected)
        records[0]["documents"][0]["title"] = "Concurrent edit"
        store._backend.write_text(path, json.dumps(records))
        return False

    with patch.object(store._backend, "replace_text_if_equal", side_effect=race):
        with pytest.raises(EditedCopyConflict):
            save(source)
    docs = store.get(project.project_id, tenant_id="alpha").documents
    assert len(docs) == 1 and docs[0].title == "Concurrent edit"


def test_exact_replay_survives_parent_removal(source):
    store, project, parent, _ = source
    copy = save(source)
    store.remove_document(project.project_id, parent.doc_id, tenant_id="alpha")
    assert save(source).doc_id == copy.doc_id


def test_duplicate_operation_records_fail_closed(source):
    store, _, _, _ = source
    save(source)
    path = "tenants/alpha/projects.json"
    records = json.loads(store._backend.read_text(path))
    duplicate = {**records[0]["documents"][1], "doc_id": str(uuid4())}
    records[0]["documents"].append(duplicate)
    store._backend.write_text(path, json.dumps(records))
    with pytest.raises(ProjectStoreError):
        save(source)


@pytest.mark.parametrize(
    "docs",
    [
        [],
        [{"doc_type": "adr", "markdown": " "}],
        [
            {"doc_type": "adr", "markdown": "one"},
            {"doc_type": "adr", "markdown": "two"},
        ],
    ],
)
def test_invalid_content_rejected(docs):
    with pytest.raises(ValueError):
        SaveEditedCopyRequest(
            operation_id=str(uuid4()), parent_sha256="a" * 64, title="Copy", docs=docs
        )
