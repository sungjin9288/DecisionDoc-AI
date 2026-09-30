"""app/middleware/audit_records.py — Pure audit helpers: path matching, resource identity, result.

Split from app/middleware/audit.py; re-exported there for existing importers.
"""
from __future__ import annotations

import re

from fastapi import Request


def _get_client_ip(request: Request) -> str:
    from app.middleware.rate_limit import _get_client_ip as _rl_get_ip
    return _rl_get_ip(request)


def _resolve_resource_identity(
    action: str,
    path: str,
    *,
    procurement_project_id: str,
    decision_council_project_id: str,
    decision_council_session_id: str,
) -> tuple[str, str]:
    resource_id = (
        decision_council_session_id
        if action.startswith("decision_council.") and decision_council_session_id
        else _extract_resource_id(path) or decision_council_project_id or procurement_project_id
    )
    resource_type = (
        "decision_council"
        if action.startswith("decision_council.")
        else
        "procurement"
        if action.startswith("procurement.") and procurement_project_id
        else _infer_resource_type(path)
    )
    return resource_type, resource_id


def _resolve_result(status_code: int) -> str:
    if status_code < 400:
        return "success"
    if status_code in (401, 403):
        return "blocked"
    return "failure"


def _path_matches(actual: str, pattern: str) -> bool:
    """Check whether *actual* path matches a pattern with {id} placeholders."""
    # Escape everything except {id} placeholders, then replace placeholders
    parts = re.split(r"(\{[^}]+\})", pattern)
    regex = "".join(
        "[^/]+" if p.startswith("{") else re.escape(p) for p in parts
    )
    return bool(re.fullmatch(regex, actual))


def _infer_resource_type(path: str) -> str:
    if "/decision-council" in path:
        return "decision_council"
    if "/approvals" in path:
        return "approval"
    if "/procurement" in path:
        return "procurement"
    if "/share" in path:
        return "share"
    if "/projects" in path:
        return "project"
    if "/admin/users" in path:
        return "user"
    if "/generate" in path:
        return "document"
    if "/auth" in path:
        return "user"
    if "/styles" in path:
        return "style"
    return "system"


def _extract_resource_id(path: str) -> str:
    """Extract the last UUID-like segment from the path."""
    parts = path.strip("/").split("/")
    for part in reversed(parts):
        if re.match(r"[0-9a-f\-]{8,}", part):
            return part
    return ""
