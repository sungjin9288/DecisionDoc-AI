"""Redacted audit projection for generated-document review handoffs."""
from __future__ import annotations

from typing import Any

from fastapi import Request


RULES: dict[tuple[str, str], str] = {
    (
        "POST",
        "/projects/{id}/documents/{id}/generated-reviews",
    ): "generated_document_review.prepare",
    ("GET", "/generated-document-reviews"): "generated_document_review.inbox_view",
    (
        "GET",
        "/projects/{id}/generated-document-reviews",
    ): "generated_document_review.project_history_view",
    (
        "GET",
        "/projects/{id}/generated-document-reviews/{id}/packet",
    ): "generated_document_review.packet_download",
}


def _is_generated_document_review_action(action: str) -> bool:
    return action.startswith("generated_document_review.")


def redact_principal(
    action: str,
    principal: tuple[str, str, str, str],
) -> tuple[str, str, str, str]:
    if _is_generated_document_review_action(action):
        _, username, user_role, _ = principal
        return "", username, user_role, ""
    return principal


def redact_network(
    action: str,
    network: tuple[str, str],
) -> tuple[str, str]:
    if _is_generated_document_review_action(action):
        return "", ""
    return network


def detail(request: Request) -> dict[str, Any]:
    detail: dict[str, Any] = {}
    text_fields = {
        "generated_document_review_project_id": "project_id",
        "generated_document_review_document_id": "document_id",
        "generated_document_review_packet_sha256": "packet_sha256",
        "generated_document_review_status": "review_status",
        "generated_document_review_access_scope": "access_scope",
        "generated_document_review_source_status": "source_status",
    }
    for state_field, detail_field in text_fields.items():
        value = getattr(request.state, state_field, "") or ""
        if value:
            detail[detail_field] = value
    replay = getattr(request.state, "generated_document_review_replay", None)
    if replay is not None:
        detail["replay"] = replay
    operational_approval = getattr(
        request.state,
        "generated_document_review_operational_approval",
        None,
    )
    if operational_approval is not None:
        detail["operational_approval"] = operational_approval
    return detail
