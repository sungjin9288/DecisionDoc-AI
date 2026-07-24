"""Canonicalization helpers shared by Decision Evidence Map projection modules."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from pydantic import BaseModel


MAX_NODES = 200
MAX_EDGES = 400
NODE_TYPE_ORDER = {
    "source": 0,
    "claim": 1,
    "recommendation": 2,
    "alternative": 3,
    "risk": 4,
    "document": 5,
    "review": 6,
    "approval": 7,
    "export": 8,
    "requirement": 9,
}


def as_mapping(value: object | None) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Mapping):
        return dict(value)
    raise TypeError(
        "Decision evidence inputs must be mappings, Pydantic models, or dataclasses"
    )


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def text(value: object) -> str:
    return str(value or "").strip()


def list_of_text(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in (text(item) for item in value) if item]


def mapping_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [as_mapping(item) for item in value if item is not None]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def procurement_requirement_node_ids(record: object | None) -> list[str]:
    """Return the canonical requirement IDs supplied to downstream generation."""
    procurement = as_mapping(record)
    decision_id = text(procurement.get("decision_id"))
    if not decision_id:
        return []

    node_ids: list[str] = []
    for item in mapping_list(procurement.get("hard_filters"))[:8]:
        code = text(item.get("code"))
        if code:
            node_ids.append(f"requirement:{decision_id}:hard_filter:{code}")

    actionable = [
        (index, item)
        for index, item in enumerate(mapping_list(procurement.get("checklist_items")))
        if text(item.get("status")) in {"blocked", "action_needed"}
    ]
    for index, item in actionable[:10]:
        title = text(item.get("title"))
        if title:
            node_ids.append(
                f"requirement:{decision_id}:checklist:{index}:{sha256(title)[:12]}"
            )

    for index, missing in enumerate(list_of_text(procurement.get("missing_data"))[:8]):
        node_ids.append(
            f"requirement:{decision_id}:missing_data:{index}:{sha256(missing)[:12]}"
        )
    return sorted(node_ids)
