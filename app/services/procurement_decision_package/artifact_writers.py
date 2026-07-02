"""Atomic artifact writers and Markdown rendering for the decision package.

This module is intentionally local and deterministic. It does not call providers,
AWS, training, model promotion, or service-resume paths.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.services.procurement_decision_package.json_helpers import (
    _bool_label,
    _require_mapping,
)

def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp.{uuid4().hex}")
    with tmp.open("w", encoding="utf-8") as file_obj:
        file_obj.write(text)
        file_obj.flush()
        os.fsync(file_obj.fileno())
    os.replace(tmp, path)


def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    write_text_atomic(path, json.dumps(data, indent=2, sort_keys=False) + "\n")


def _render_decision_summary(package: dict[str, Any]) -> str:
    recommendation = package["recommendation"]
    recommendation_reason = package["recommendation_reason"]
    hard_filters = "\n".join(
        _render_decision_summary_hard_filter(item)
        for item in package["hard_filters"]
    )
    next_actions = "\n".join(
        _render_decision_summary_next_action(item)
        for item in package["bid_readiness_checklist"]
    )
    boundary_note = package["reviewer_handoff"]["non_authorization_note"]

    return f"""# Procurement Decision Summary

Recommendation: `{recommendation}`

{recommendation_reason}

## Hard Filters

{hard_filters}

## Next Actions

{next_actions}

## Boundary

{boundary_note}
"""


def _render_decision_summary_hard_filter(item: dict[str, str]) -> str:
    return f"- `{item['filter_id']}`: {item['status']} - {item['reason']}"


def _render_decision_summary_next_action(item: dict[str, str]) -> str:
    return f"- {item['label']} (`{item['status']}`, owner: {item['owner']})"


def _render_evidence_summary(package: dict[str, Any]) -> str:
    evidence_rows = [
        f"- `{item['evidence_id']}` ({item['type']}): {item['summary']}"
        for item in package["evidence_summary"]
    ]
    return "\n".join([
        "# Evidence Summary",
        "",
        *evidence_rows,
    ])


def _render_bid_readiness_checklist(package: dict[str, Any]) -> str:
    checklist_rows = []
    for item in package["bid_readiness_checklist"]:
        checklist_rows.append(
            f"| {item['label']} | `{item['status']}` | "
            f"{item['owner']} | `{item['required_before']}` |"
        )
    return "\n".join([
        "# Bid Readiness Checklist",
        "",
        "| Item | Status | Owner | Required Before |",
        "|---|---|---|---|",
        *checklist_rows,
    ])


def _render_signoff_summary(package: dict[str, Any]) -> str:
    pending_signoff = _require_mapping(
        package["pending_signoff"],
        "package.pending_signoff",
    )

    return f"""# Sign-Off Summary

Status: `{pending_signoff['status']}`

Reviewer: `{pending_signoff['reviewer']}`

Scope: `{pending_signoff['signoff_scope']}`

Operational approval: `{_bool_label(pending_signoff['operational_approval'])}`

## Boundary

{package['reviewer_handoff']['non_authorization_note']}
"""
