#!/usr/bin/env python3
"""Validate a DecisionDoc future-feature admission record."""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)


RECORD_SCHEMA_VERSION = "decisiondoc.future_feature_gate.v1"
RESULT_SCHEMA_VERSION = "decisiondoc.future_feature_gate.validation.v1"
TEMPLATE_GATE_ID = "draft-feature-gate-id"
TEMPLATE_MARKER = "<replace>"

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
GateId = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z0-9][a-z0-9._-]{2,79}$"),
]
TextList = Annotated[list[NonEmptyText], Field(min_length=1)]


class StrictRecord(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class EvidenceReference(StrictRecord):
    kind: Literal["repository", "test", "user_feedback", "external_source"]
    reference: NonEmptyText
    observation: NonEmptyText


class VerificationStep(StrictRecord):
    command: NonEmptyText
    proves: NonEmptyText


class AuthorityScope(StrictRecord):
    review_only: bool
    allowed_effects: TextList
    excluded_effects: TextList
    separate_approval_required_for: TextList

    @field_validator(
        "allowed_effects",
        "excluded_effects",
        "separate_approval_required_for",
    )
    @classmethod
    def require_unique_values(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("must not contain duplicate values")
        return value


class GateDecision(StrictRecord):
    status: Literal["draft", "approved", "deferred", "rejected"]
    rationale: NonEmptyText
    decided_by: NonEmptyText | None
    decided_at: NonEmptyText | None

    @model_validator(mode="after")
    def validate_decision_metadata(self) -> GateDecision:
        if self.status == "draft":
            if self.decided_by is not None or self.decided_at is not None:
                raise ValueError("draft decision metadata must be null")
            return self

        if self.decided_by is None or self.decided_at is None:
            raise ValueError("terminal decisions require decided_by and decided_at")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", self.decided_at) is None:
            raise ValueError("decided_at must use YYYY-MM-DDTHH:MM:SSZ")
        try:
            datetime.strptime(self.decided_at, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError as exc:
            raise ValueError("decided_at must use YYYY-MM-DDTHH:MM:SSZ") from exc
        return self


class FutureFeatureGate(StrictRecord):
    schema_version: Literal[RECORD_SCHEMA_VERSION]
    gate_id: GateId
    title: NonEmptyText
    target_user: NonEmptyText
    observed_problem: NonEmptyText
    evidence: Annotated[list[EvidenceReference], Field(min_length=1)]
    current_workaround: NonEmptyText
    desired_outcome: NonEmptyText
    acceptance_criteria: TextList
    affected_boundaries: TextList
    authority_scope: AuthorityScope
    local_verification: Annotated[list[VerificationStep], Field(min_length=1)]
    decision: GateDecision

    @field_validator("acceptance_criteria", "affected_boundaries")
    @classmethod
    def require_unique_values(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("must not contain duplicate values")
        return value


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON value is not allowed: {value}")


def _load_record(path: Path) -> dict[str, Any]:
    payload = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_strict_object,
        parse_constant=_reject_constant,
    )
    if not isinstance(payload, dict):
        raise ValueError("future feature gate JSON root must be an object")
    return payload


def _format_validation_error(error: dict[str, Any]) -> str:
    location = ".".join(str(part) for part in error["loc"])
    return f"{location}: {error['msg']}" if location else str(error["msg"])


def _contains_template_marker(value: Any) -> bool:
    if isinstance(value, str):
        return TEMPLATE_MARKER in value
    if isinstance(value, list):
        return any(_contains_template_marker(item) for item in value)
    if isinstance(value, dict):
        return any(_contains_template_marker(item) for item in value.values())
    return False


def validate_future_feature_gate(
    payload: dict[str, Any],
    *,
    require_approved: bool = False,
) -> dict[str, Any]:
    gate_id = payload.get("gate_id")
    raw_decision = payload.get("decision")
    decision_status = (
        raw_decision.get("status") if isinstance(raw_decision, dict) else None
    )

    try:
        record = FutureFeatureGate.model_validate(payload)
    except ValidationError as exc:
        errors = [_format_validation_error(error) for error in exc.errors()]
        record_valid = False
        admitted = False
    else:
        errors = []
        record_valid = True
        gate_id = record.gate_id
        decision_status = record.decision.status
        admitted = decision_status == "approved"

        if admitted and (
            record.gate_id == TEMPLATE_GATE_ID or _contains_template_marker(payload)
        ):
            errors.append("approved record must replace all draft template markers")
            record_valid = False
            admitted = False

    if require_approved and not admitted:
        if decision_status != "approved":
            errors.append("decision.status must be approved before implementation")
        elif not record_valid:
            errors.append("record must be valid before implementation")

    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "status": "passed" if not errors else "failed",
        "record_valid": record_valid,
        "admitted_for_implementation": admitted,
        "decision_identity_verified": False,
        "operational_authority_granted": False,
        "require_approved": require_approved,
        "gate_id": gate_id,
        "decision_status": decision_status,
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "record",
        type=Path,
        help="path to a future feature gate JSON record",
    )
    parser.add_argument("--require-approved", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        payload = _load_record(args.record)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        result = {
            "schema_version": RESULT_SCHEMA_VERSION,
            "status": "failed",
            "record_valid": False,
            "admitted_for_implementation": False,
            "decision_identity_verified": False,
            "operational_authority_granted": False,
            "require_approved": bool(args.require_approved),
            "gate_id": None,
            "decision_status": None,
            "errors": [str(exc)],
        }
    else:
        result = validate_future_feature_gate(
            payload,
            require_approved=bool(args.require_approved),
        )

    if args.json:
        print(
            json.dumps(
                result,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    elif result["status"] == "passed":
        print("PASS future feature gate record validated")
        print(
            "admitted_for_implementation="
            f"{str(result['admitted_for_implementation']).lower()}"
        )
    else:
        print("FAIL future feature gate record validation failed")
        for error in result["errors"]:
            print(f"ERROR {error}")
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
