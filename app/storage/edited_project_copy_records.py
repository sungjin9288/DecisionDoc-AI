"""Validation shared by project-state reads and edited-copy creation."""

import hashlib
import json
from typing import TYPE_CHECKING, Any

from app.schemas.edited_project_copies import EditedCopyLineage, SaveEditedCopyRequest
from app.storage.project_state_mutation import ProjectStoreError, _unique_object

if TYPE_CHECKING:
    from app.storage.project_store import ProjectDocument


def canonical_hash(value: Any) -> str:
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(serialized.encode()).hexdigest()


def source_hash(doc: "ProjectDocument") -> str:
    try:
        docs = json.loads(doc.doc_snapshot, object_pairs_hook=_unique_object)
        if (
            not isinstance(docs, list)
            or not docs
            or any(not isinstance(d, dict) for d in docs)
        ):
            raise ValueError("invalid document snapshot")
        types = [d.get("doc_type") for d in docs]
        if (
            any(not isinstance(kind, str) or not kind for kind in types)
            or len(set(types)) != len(types)
            or any(not isinstance(d.get("markdown"), str) for d in docs)
        ):
            raise ValueError("invalid document content")
        source = {
            "docs": docs,
            "title": doc.title,
            "bundle_id": doc.bundle_id,
            "gov_options": doc.gov_options,
        }
        if doc.source_procurement_binding is not None:
            source["source_procurement_binding"] = doc.source_procurement_binding
        return canonical_hash(source)
    except (ValueError, TypeError) as exc:
        raise ProjectStoreError("Invalid source document") from exc


def validate_edited_copy(doc: "ProjectDocument") -> None:
    if doc.source_kind != "edited_copy" and doc.edited_copy is None:
        return
    try:
        lineage = EditedCopyLineage.model_validate(doc.edited_copy)
        payload = SaveEditedCopyRequest(
            operation_id=lineage.operation_id,
            parent_sha256=lineage.parent_sha256,
            title=doc.title,
            docs=json.loads(doc.doc_snapshot),
        )
        expected = canonical_hash(
            {
                "parent_id": lineage.parent_id,
                "actor_id": lineage.actor_id,
                "payload": payload.model_dump(),
            }
        )
        if (
            doc.source_kind != "edited_copy"
            or doc.request_id
            or doc.approval_id is not None
            or doc.approval_status is not None
            or source_hash(doc) != lineage.content_sha256
            or expected != lineage.request_sha256
        ):
            raise ValueError("edited-copy binding mismatch")
    except (ValueError, TypeError, KeyError) as exc:
        raise ProjectStoreError("Invalid edited project copy") from exc
