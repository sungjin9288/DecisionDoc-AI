import io
import json
from uuid import uuid4
import zipfile

from tests.test_generated_document_reviews import client, _login, _create_user  # noqa: F401
from app.storage.audit_store import AuditStore
from app.storage.user_store import get_user_store


def test_session_save_reopen_download_and_access(client):  # noqa: F811
    admin = _login(client, "copy-admin")
    store = client.app.state.project_store
    project = store.create(tenant_id="system", name="Copies")
    original = store.add_document(
        project.project_id,
        "original",
        "tech_decision",
        "Original",
        [{"doc_type": "adr", "markdown": "# Original"}],
        tenant_id="system",
    )
    base = f"/projects/{project.project_id}/documents/{original.doc_id}"
    source = client.get(base + "/editable-source", headers=admin)
    assert source.status_code == 200
    payload = dict(
        operation_id=str(uuid4()),
        parent_sha256=source.json()["parent_sha256"],
        title="Edited",
        docs=[{"doc_type": "adr", "markdown": "# Edited persistence marker"}],
    )
    assert client.post(
        base + "/edited-copies",
        json=payload,
        headers={"X-DecisionDoc-Api-Key": "test-key"},
    ).status_code in (401, 403)
    viewer = _create_user(client, admin, "copy-viewer", role="viewer")
    assert (
        client.post(base + "/edited-copies", json=payload, headers=viewer).status_code
        == 403
    )
    saved = client.post(base + "/edited-copies", json=payload, headers=admin)
    assert saved.status_code == 200, saved.text
    document = saved.json()["document"]
    replay = client.post(base + "/edited-copies", json=payload, headers=admin)
    assert replay.json()["document"]["doc_id"] == document["doc_id"]
    assert (
        client.post(
            base + "/edited-copies", json={**payload, "title": "Changed"}, headers=admin
        ).status_code
        == 409
    )
    assert (
        client.post(
            base + "/edited-copies", json={**payload, "docs": []}, headers=admin
        ).status_code
        == 422
    )
    restored = client.get(f"/projects/{project.project_id}", headers=admin).json()[
        "documents"
    ]
    assert len(restored) == 2
    assert json.loads(restored[0]["doc_snapshot"])[0]["markdown"] == "# Original"
    result = client.get(
        f"/projects/{project.project_id}/documents/{document['doc_id']}/download/docx",
        headers=admin,
    )
    assert result.status_code == 200
    with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
        assert b"Edited persistence marker" in archive.read("word/document.xml")
    # A saved copy has no generation issuance, so it cannot enter the
    # generated-document review/verified-package path.
    copy_review = client.post(
        f"/projects/{project.project_id}/documents/{document['doc_id']}/generated-reviews",
        json={"reviewer": "copy-admin", "formats": ["docx"]},
        headers=admin,
    )
    assert copy_review.status_code == 409, copy_review.text
    assert copy_review.json()["detail"]["code"] == "generated_document_review_conflict"
    audit = AuditStore(
        "system",
        data_dir=client.app.state.data_dir,
        backend=client.app.state.state_backend,
    ).query(filters={"action": "generated_document_review.edited_copy_save"})
    successful = [
        row
        for row in audit
        if row.get("detail", {}).get("document_id") == document["doc_id"]
    ]
    assert successful
    for row in successful:
        assert (
            row["user_id"]
            == row["session_id"]
            == row["ip_address"]
            == row["user_agent"]
            == ""
        )
        assert "Edited persistence marker" not in json.dumps(row)
        assert payload["operation_id"] not in json.dumps(row)
    foreign = store.create(tenant_id="foreign", name="Foreign")
    foreign_doc = store.add_document(
        foreign.project_id,
        "foreign",
        "tech_decision",
        "Foreign",
        [{"doc_type": "adr", "markdown": "# Foreign"}],
        tenant_id="foreign",
    )
    assert (
        client.get(
            f"/projects/{foreign.project_id}/documents/{foreign_doc.doc_id}/editable-source",
            headers=admin,
        ).status_code
        == 404
    )
    users = get_user_store(
        "system",
        data_dir=client.app.state.data_dir,
        backend=client.app.state.state_backend,
    )
    users.deactivate(users.get_by_username("copy-admin").user_id)
    assert client.post(
        base + "/edited-copies", json=payload, headers=admin
    ).status_code in (401, 403)
    assert len(store.get(project.project_id, tenant_id="system").documents) == 2
