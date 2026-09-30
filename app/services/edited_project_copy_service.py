"""Append edited copies through the existing conditional project mutation."""

from datetime import datetime, timezone
import json
from typing import TYPE_CHECKING
from uuid import uuid4

from app.schemas.edited_project_copies import EditedCopyLineage, SaveEditedCopyRequest
from app.storage.edited_project_copy_records import (
    canonical_hash,
    source_hash,
    validate_edited_copy,
)

if TYPE_CHECKING:
    from app.storage.project_store import Project, ProjectDocument, ProjectStore


class EditedCopyConflict(ValueError):
    """A save operation or its parent no longer matches the requested snapshot."""


def save_edited_copy(
    store: "ProjectStore",
    *,
    tenant_id: str,
    actor_id: str,
    project_id: str,
    parent_id: str,
    payload: SaveEditedCopyRequest,
) -> "ProjectDocument":
    from app.storage.project_store import ProjectDocument

    payload = SaveEditedCopyRequest.model_validate(payload.model_dump())
    if not actor_id:
        raise ValueError("actor identity is required")
    request_hash = canonical_hash(
        {"parent_id": parent_id, "actor_id": actor_id, "payload": payload.model_dump()}
    )

    def append(project: "Project") -> tuple["ProjectDocument", bool]:
        for doc in project.documents:
            meta = doc.edited_copy
            if (
                meta
                and meta["actor_id"] == actor_id
                and meta["operation_id"] == payload.operation_id
            ):
                if meta["request_sha256"] != request_hash:
                    raise EditedCopyConflict("operation payload changed")
                return doc, False
        parent = next((d for d in project.documents if d.doc_id == parent_id), None)
        if parent is None:
            raise KeyError("parent document not found")
        if source_hash(parent) != payload.parent_sha256:
            raise EditedCopyConflict("parent document changed")
        parent_types = {d["doc_type"] for d in json.loads(parent.doc_snapshot)}
        if {d.doc_type for d in payload.docs} != parent_types:
            raise EditedCopyConflict("document types differ from parent")
        doc = ProjectDocument(
            doc_id=str(uuid4()),
            request_id="",
            bundle_id=parent.bundle_id,
            title=payload.title,
            generated_at=datetime.now(timezone.utc).isoformat(),
            approval_id=None,
            approval_status=None,
            tags=[],
            doc_snapshot=json.dumps(
                [d.model_dump() for d in payload.docs], ensure_ascii=False
            ),
            gov_options=parent.gov_options,
            file_size_chars=sum(len(d.markdown) for d in payload.docs),
            source_kind="edited_copy",
            source_procurement_binding=parent.source_procurement_binding,
        )
        doc.edited_copy = EditedCopyLineage(
            actor_id=actor_id,
            parent_id=parent_id,
            parent_sha256=payload.parent_sha256,
            operation_id=payload.operation_id,
            request_sha256=request_hash,
            content_sha256=source_hash(doc),
        ).model_dump()
        validate_edited_copy(doc)
        project.documents.append(doc)
        return doc, True

    return store._mutate_project(project_id, tenant_id=tenant_id, change=append)
