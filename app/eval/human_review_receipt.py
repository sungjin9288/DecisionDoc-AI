"""Human review receipts bound to a finished-document evidence manifest."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any, Mapping


SCHEMA_VERSION = "decisiondoc.finished_document_human_review.v1"
DRAFT_SCHEMA_VERSION = "decisiondoc.finished_document_human_review_draft.v1"
SCOPE = (
    "records factual and visual review decisions for local generated documents; "
    "does not authorize external actions"
)
DRAFT_SCOPE = (
    "proposes local human review updates; does not modify the receipt or authorize external actions"
)
REVIEW_STATES = {"not_reviewed", "passed", "needs_revision"}


def _pending_bundle_review() -> dict[str, str]:
    return {
        "factual_grounding": "not_reviewed",
        "visual_review": "not_reviewed",
        "decision": "pending",
        "reviewer": "",
        "reviewed_at": "",
        "notes": "",
    }


def build_pending_human_review_receipt(
    manifest: Mapping[str, Any],
    *,
    manifest_sha256: str,
) -> dict[str, Any]:
    if not _valid_sha256(manifest_sha256):
        raise ValueError("manifest_sha256 must be a 64-character hexadecimal digest")

    created_at = str(manifest.get("generated_at") or "")
    external_actions = manifest.get("external_actions")
    if not isinstance(external_actions, Mapping):
        raise ValueError("evidence manifest must define external_actions")

    bundles = manifest.get("bundles")
    if not isinstance(bundles, Mapping) or not bundles:
        raise ValueError("evidence manifest must define at least one bundle")

    return {
        "schema_version": SCHEMA_VERSION,
        "scope": SCOPE,
        "status": "pending",
        "created_at": created_at,
        "updated_at": created_at,
        "evidence": {
            "manifest_path": "manifest.json",
            "manifest_sha256": manifest_sha256,
            "manifest_schema_version": manifest.get("schema_version"),
            "manifest_generated_at": manifest.get("generated_at"),
        },
        "bundle_reviews": {
            str(bundle_type): _pending_bundle_review()
            for bundle_type in bundles
        },
        "external_actions_authorized": {
            str(action): False
            for action in external_actions
        },
    }


def _receipt_status(bundle_reviews: Mapping[str, Any]) -> str:
    decisions = {
        review.get("decision")
        for review in bundle_reviews.values()
        if isinstance(review, Mapping)
    }
    if decisions == {"accepted"}:
        return "completed"
    if "needs_revision" in decisions:
        return "needs_revision"
    return "pending"


def has_recorded_human_input(receipt: Mapping[str, Any]) -> bool:
    """Return whether a receipt contains a review decision or reviewer-authored data."""
    bundle_reviews = receipt.get("bundle_reviews")
    if not isinstance(bundle_reviews, Mapping):
        return True

    for review in bundle_reviews.values():
        if not isinstance(review, Mapping):
            return True
        if review.get("decision") != "pending":
            return True
        if review.get("factual_grounding") != "not_reviewed":
            return True
        if review.get("visual_review") != "not_reviewed":
            return True
        if any(review.get(field) for field in ("reviewer", "reviewed_at", "notes")):
            return True
    return False


def record_bundle_review(
    receipt: Mapping[str, Any],
    *,
    bundle_type: str,
    reviewer: str,
    factual_grounding: str,
    visual_review: str,
    notes: str,
    reviewed_at: str,
) -> dict[str, Any]:
    reviewer = reviewer.strip()
    notes = notes.strip()
    if not reviewer:
        raise ValueError("reviewer must not be empty")
    if not notes:
        raise ValueError("notes must not be empty")
    if factual_grounding not in REVIEW_STATES - {"not_reviewed"}:
        raise ValueError("factual_grounding must be passed or needs_revision")
    if visual_review not in REVIEW_STATES - {"not_reviewed"}:
        raise ValueError("visual_review must be passed or needs_revision")
    if not _valid_timestamp(reviewed_at):
        raise ValueError("reviewed_at must be an ISO-8601 timestamp with timezone")

    current_updated_at = _parse_timestamp(receipt.get("updated_at"))
    next_reviewed_at = _parse_timestamp(reviewed_at)
    if current_updated_at is None:
        raise ValueError("receipt updated_at must be an ISO-8601 timestamp with timezone")
    if next_reviewed_at is not None and next_reviewed_at < current_updated_at:
        raise ValueError("reviewed_at must not be earlier than the current receipt update time")

    updated = deepcopy(dict(receipt))
    bundle_reviews = updated.get("bundle_reviews")
    if not isinstance(bundle_reviews, dict) or bundle_type not in bundle_reviews:
        raise ValueError(f"unknown bundle_type: {bundle_type}")

    decision = (
        "accepted"
        if factual_grounding == "passed" and visual_review == "passed"
        else "needs_revision"
    )
    bundle_reviews[bundle_type] = {
        "factual_grounding": factual_grounding,
        "visual_review": visual_review,
        "decision": decision,
        "reviewer": reviewer,
        "reviewed_at": reviewed_at,
        "notes": notes,
    }
    updated["status"] = _receipt_status(bundle_reviews)
    updated["updated_at"] = reviewed_at
    return updated


def validate_human_review_draft(
    draft: Mapping[str, Any],
    receipt: Mapping[str, Any],
    manifest: Mapping[str, Any],
    *,
    receipt_sha256: str,
    manifest_sha256: str,
    receipt_path: str = "human_review_receipt.json",
) -> dict[str, Any]:
    errors: list[str] = []
    if set(draft) != {
        "schema_version",
        "scope",
        "created_at",
        "source",
        "reviews",
        "external_actions_authorized",
    }:
        errors.append("draft fields do not match the schema")
    if draft.get("schema_version") != DRAFT_SCHEMA_VERSION:
        errors.append("draft schema_version does not match")
    if draft.get("scope") != DRAFT_SCOPE:
        errors.append("draft scope does not match")

    created_at = _parse_timestamp(draft.get("created_at"))
    if created_at is None:
        errors.append("draft created_at must be an ISO-8601 timestamp with timezone")
    receipt_updated_at = _parse_timestamp(receipt.get("updated_at"))
    if created_at is not None and receipt_updated_at is not None and created_at < receipt_updated_at:
        errors.append("draft created_at must not be earlier than the current receipt update time")

    source = draft.get("source")
    if not _valid_sha256(receipt_sha256):
        errors.append("receipt_sha256 must be a 64-character hexadecimal digest")
    if not _valid_sha256(manifest_sha256):
        errors.append("manifest_sha256 must be a 64-character hexadecimal digest")
    expected_source = {
        "receipt_path": receipt_path,
        "receipt_sha256": receipt_sha256,
        "manifest_path": "manifest.json",
        "manifest_sha256": manifest_sha256,
    }
    if not isinstance(source, Mapping) or dict(source) != expected_source:
        errors.append("draft source does not match the current receipt and manifest")

    receipt_reviews = receipt.get("bundle_reviews")
    bundle_types = set(receipt_reviews) if isinstance(receipt_reviews, Mapping) else set()
    manifest_bundles = manifest.get("bundles")
    if not isinstance(manifest_bundles, Mapping) or set(manifest_bundles) != bundle_types:
        errors.append("receipt bundle reviews do not match manifest bundles")

    reviews = draft.get("reviews")
    review_count = 0
    if not isinstance(reviews, Mapping) or not reviews:
        errors.append("draft reviews must contain at least one bundle review")
        reviews = {}
    elif not set(reviews).issubset(bundle_types):
        errors.append("draft reviews contain an unknown bundle")

    expected_review_fields = {"factual_grounding", "visual_review", "reviewer", "notes"}
    for bundle_type, review in reviews.items():
        if not isinstance(review, Mapping):
            errors.append(f"{bundle_type} draft review must be an object")
            continue
        if set(review) != expected_review_fields:
            errors.append(f"{bundle_type} draft review fields do not match the schema")
            continue
        review_count += 1
        if review.get("factual_grounding") not in REVIEW_STATES - {"not_reviewed"}:
            errors.append(f"{bundle_type} factual_grounding must be passed or needs_revision")
        if review.get("visual_review") not in REVIEW_STATES - {"not_reviewed"}:
            errors.append(f"{bundle_type} visual_review must be passed or needs_revision")
        for field in ("reviewer", "notes"):
            value = review.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{bundle_type} {field} must not be empty")
            elif value != value.strip():
                errors.append(f"{bundle_type} {field} must not contain surrounding whitespace")

        current_review = receipt_reviews.get(bundle_type) if isinstance(receipt_reviews, Mapping) else None
        if isinstance(current_review, Mapping) and all(
            current_review.get(field) == review.get(field)
            for field in expected_review_fields
        ):
            errors.append(f"{bundle_type} draft review does not change the current receipt")

    expected_actions = receipt.get("external_actions_authorized")
    if (
        not isinstance(expected_actions, Mapping)
        or not expected_actions
        or any(value is not False for value in expected_actions.values())
    ):
        errors.append("receipt must keep every external action unauthorized")
    elif draft.get("external_actions_authorized") != dict(expected_actions):
        errors.append("draft must keep every external action unauthorized")

    return {
        "ok": not errors,
        "review_count": review_count,
        "errors": errors,
        "warnings": [
            "Applying a review draft records document review only and does not authorize external actions."
        ],
    }


def apply_human_review_draft(
    receipt: Mapping[str, Any],
    draft: Mapping[str, Any],
    manifest: Mapping[str, Any],
    *,
    receipt_sha256: str,
    manifest_sha256: str,
    receipt_path: str = "human_review_receipt.json",
) -> dict[str, Any]:
    validation = validate_human_review_draft(
        draft,
        receipt,
        manifest,
        receipt_sha256=receipt_sha256,
        manifest_sha256=manifest_sha256,
        receipt_path=receipt_path,
    )
    if not validation["ok"]:
        raise ValueError(f"human review draft is invalid: {validation['errors']}")

    updated = dict(receipt)
    reviews = draft["reviews"]
    for bundle_type, review in reviews.items():
        updated = record_bundle_review(
            updated,
            bundle_type=str(bundle_type),
            reviewer=review["reviewer"],
            factual_grounding=review["factual_grounding"],
            visual_review=review["visual_review"],
            notes=review["notes"],
            reviewed_at=draft["created_at"],
        )
    return updated


def _valid_timestamp(value: Any) -> bool:
    return _parse_timestamp(value) is not None


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return timestamp if timestamp.tzinfo is not None else None


def _valid_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdefABCDEF" for character in value)
    )


def validate_human_review_receipt(
    receipt: Mapping[str, Any],
    manifest: Mapping[str, Any],
    *,
    manifest_sha256: str,
) -> dict[str, Any]:
    errors: list[str] = []
    expected_fields = {
        "schema_version",
        "scope",
        "status",
        "created_at",
        "updated_at",
        "evidence",
        "bundle_reviews",
        "external_actions_authorized",
    }
    if set(receipt) != expected_fields:
        errors.append("receipt fields do not match the schema")
    if receipt.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version does not match")
    if receipt.get("scope") != SCOPE:
        errors.append("scope does not match")
    if not _valid_sha256(manifest_sha256):
        errors.append("manifest_sha256 must be a 64-character hexadecimal digest")
    if not _valid_timestamp(receipt.get("created_at")):
        errors.append("created_at must be an ISO-8601 timestamp with timezone")
    elif receipt.get("created_at") != manifest.get("generated_at"):
        errors.append("created_at must match the manifest generation time")
    if not _valid_timestamp(receipt.get("updated_at")):
        errors.append("updated_at must be an ISO-8601 timestamp with timezone")
    elif _valid_timestamp(receipt.get("created_at")):
        created_at = _parse_timestamp(receipt["created_at"])
        updated_at = _parse_timestamp(receipt["updated_at"])
        if created_at is not None and updated_at is not None and updated_at < created_at:
            errors.append("updated_at must not be earlier than created_at")

    evidence = receipt.get("evidence")
    if not isinstance(evidence, Mapping):
        errors.append("evidence must be an object")
    else:
        expected_evidence = {
            "manifest_path": "manifest.json",
            "manifest_sha256": manifest_sha256,
            "manifest_schema_version": manifest.get("schema_version"),
            "manifest_generated_at": manifest.get("generated_at"),
        }
        if dict(evidence) != expected_evidence:
            errors.append("evidence does not match the current manifest")

    manifest_bundles = manifest.get("bundles")
    expected_bundle_types = set(manifest_bundles) if isinstance(manifest_bundles, Mapping) else set()
    bundle_reviews = receipt.get("bundle_reviews")
    reviewed_count = 0
    accepted_count = 0
    reviewed_timestamps: list[datetime] = []
    if not isinstance(bundle_reviews, Mapping):
        errors.append("bundle_reviews must be an object")
        bundle_reviews = {}
    elif set(bundle_reviews) != expected_bundle_types:
        errors.append("bundle_reviews do not match manifest bundles")

    expected_review_fields = {
        "factual_grounding",
        "visual_review",
        "decision",
        "reviewer",
        "reviewed_at",
        "notes",
    }
    for bundle_type, value in bundle_reviews.items():
        if not isinstance(value, Mapping):
            errors.append(f"{bundle_type} review must be an object")
            continue
        if set(value) != expected_review_fields:
            errors.append(f"{bundle_type} review fields do not match the schema")
            continue

        factual = value.get("factual_grounding")
        visual = value.get("visual_review")
        decision = value.get("decision")
        if factual not in REVIEW_STATES:
            errors.append(f"{bundle_type} factual_grounding is invalid")
        if visual not in REVIEW_STATES:
            errors.append(f"{bundle_type} visual_review is invalid")

        pending = factual == "not_reviewed" and visual == "not_reviewed"
        partially_reviewed = (factual == "not_reviewed") != (visual == "not_reviewed")
        if partially_reviewed:
            errors.append(f"{bundle_type} review states must be recorded together")
        expected_decision = (
            "pending"
            if pending
            else "accepted"
            if factual == "passed" and visual == "passed"
            else "needs_revision"
        )
        if decision != expected_decision:
            errors.append(f"{bundle_type} decision is inconsistent with review states")

        if pending:
            if any(value.get(field) for field in ("reviewer", "reviewed_at", "notes")):
                errors.append(f"{bundle_type} pending review must not contain reviewer input")
            continue

        reviewed_count += 1
        if decision == "accepted":
            accepted_count += 1
        if not isinstance(value.get("reviewer"), str) or not value["reviewer"].strip():
            errors.append(f"{bundle_type} reviewer must not be empty")
        if not _valid_timestamp(value.get("reviewed_at")):
            errors.append(f"{bundle_type} reviewed_at must be an ISO-8601 timestamp with timezone")
        else:
            reviewed_at = _parse_timestamp(value["reviewed_at"])
            if reviewed_at is not None:
                reviewed_timestamps.append(reviewed_at)
        if not isinstance(value.get("notes"), str) or not value["notes"].strip():
            errors.append(f"{bundle_type} notes must not be empty")

    expected_status = _receipt_status(bundle_reviews)
    if receipt.get("status") != expected_status:
        errors.append("status is inconsistent with bundle decisions")

    receipt_created_at = _parse_timestamp(receipt.get("created_at"))
    receipt_updated_at = _parse_timestamp(receipt.get("updated_at"))
    if receipt_created_at is not None and receipt_updated_at is not None:
        expected_updated_at = max([receipt_created_at, *reviewed_timestamps])
        if receipt_updated_at != expected_updated_at:
            errors.append("updated_at must match the latest recorded review time")

    manifest_actions = manifest.get("external_actions")
    expected_actions = (
        {str(action): False for action in manifest_actions}
        if isinstance(manifest_actions, Mapping)
        else {}
    )
    if receipt.get("external_actions_authorized") != expected_actions:
        errors.append("external_actions_authorized must keep every action false")

    return {
        "ok": not errors,
        "status": receipt.get("status"),
        "completed": receipt.get("status") == "completed" and not errors,
        "bundle_count": len(expected_bundle_types),
        "reviewed_count": reviewed_count,
        "accepted_count": accepted_count,
        "errors": errors,
        "warnings": [
            "Human review receipts record document review only and do not authorize external actions."
        ],
    }
