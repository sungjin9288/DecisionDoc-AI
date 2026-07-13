from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from app.eval.human_review_receipt import (
    build_pending_human_review_receipt,
    record_bundle_review,
    validate_human_review_receipt,
)
from scripts.manage_finished_doc_human_review import main


MANIFEST_SHA256 = "a" * 64
CREATED_AT = "2026-07-13T10:00:00+00:00"


def _manifest() -> dict:
    return {
        "schema_version": "decisiondoc.finished_document_review.v3",
        "generated_at": CREATED_AT,
        "bundles": {
            "proposal_kr": {},
            "performance_plan_kr": {},
        },
        "external_actions": {
            "provider_api_execution": False,
            "production_service_resume": False,
        },
    }


def _pending_receipt() -> dict:
    return build_pending_human_review_receipt(
        _manifest(),
        manifest_sha256=MANIFEST_SHA256,
    )


def _record(
    receipt: dict,
    bundle_type: str,
    *,
    factual_grounding: str = "passed",
    visual_review: str = "passed",
) -> dict:
    return record_bundle_review(
        receipt,
        bundle_type=bundle_type,
        reviewer="Local reviewer",
        factual_grounding=factual_grounding,
        visual_review=visual_review,
        notes="Checked against the fictional request and rendered document.",
        reviewed_at="2026-07-13T11:00:00+00:00",
    )


def test_pending_receipt_validates_against_manifest() -> None:
    result = validate_human_review_receipt(
        _pending_receipt(),
        _manifest(),
        manifest_sha256=MANIFEST_SHA256,
    )

    assert result["ok"] is True
    assert result["status"] == "pending"
    assert result["completed"] is False
    assert result["bundle_count"] == 2
    assert result["reviewed_count"] == 0
    assert result["accepted_count"] == 0


def test_receipt_completes_only_after_every_bundle_is_accepted() -> None:
    first_review = _record(_pending_receipt(), "proposal_kr")
    first_result = validate_human_review_receipt(
        first_review,
        _manifest(),
        manifest_sha256=MANIFEST_SHA256,
    )
    assert first_result["ok"] is True
    assert first_result["status"] == "pending"
    assert first_result["accepted_count"] == 1

    completed = _record(first_review, "performance_plan_kr")
    completed_result = validate_human_review_receipt(
        completed,
        _manifest(),
        manifest_sha256=MANIFEST_SHA256,
    )
    assert completed_result["ok"] is True
    assert completed_result["status"] == "completed"
    assert completed_result["completed"] is True
    assert completed_result["accepted_count"] == 2


def test_needs_revision_prevents_receipt_completion() -> None:
    with pytest.raises(ValueError, match="earlier than the current receipt update time"):
        record_bundle_review(
            _pending_receipt(),
            bundle_type="proposal_kr",
            reviewer="Local reviewer",
            factual_grounding="passed",
            visual_review="passed",
            notes="Backdated review must be rejected.",
            reviewed_at="2026-07-13T09:00:00+00:00",
        )

    receipt = _record(
        _pending_receipt(),
        "proposal_kr",
        visual_review="needs_revision",
    )
    result = validate_human_review_receipt(
        receipt,
        _manifest(),
        manifest_sha256=MANIFEST_SHA256,
    )

    assert result["ok"] is True
    assert result["status"] == "needs_revision"
    assert result["completed"] is False


@pytest.mark.parametrize("field", ["reviewer", "notes"])
def test_record_review_requires_reviewer_authored_fields(field: str) -> None:
    arguments = {
        "bundle_type": "proposal_kr",
        "reviewer": "Local reviewer",
        "factual_grounding": "passed",
        "visual_review": "passed",
        "notes": "Reviewed.",
        "reviewed_at": "2026-07-13T11:00:00+00:00",
    }
    arguments[field] = " "

    with pytest.raises(ValueError, match=f"{field} must not be empty"):
        record_bundle_review(_pending_receipt(), **arguments)


def test_receipt_validation_rejects_manifest_or_authorization_tampering() -> None:
    with pytest.raises(ValueError, match="64-character hexadecimal digest"):
        build_pending_human_review_receipt(_manifest(), manifest_sha256="invalid")

    receipt = _pending_receipt()
    hash_result = validate_human_review_receipt(
        receipt,
        _manifest(),
        manifest_sha256="b" * 64,
    )
    assert hash_result["ok"] is False
    assert "evidence does not match the current manifest" in hash_result["errors"]

    tampered = deepcopy(receipt)
    tampered["external_actions_authorized"]["provider_api_execution"] = True
    action_result = validate_human_review_receipt(
        tampered,
        _manifest(),
        manifest_sha256=MANIFEST_SHA256,
    )
    assert action_result["ok"] is False
    assert "external_actions_authorized must keep every action false" in action_result["errors"]


def test_receipt_validation_rejects_partial_review_state() -> None:
    receipt = _pending_receipt()
    review = receipt["bundle_reviews"]["proposal_kr"]
    review.update(
        factual_grounding="passed",
        decision="needs_revision",
        reviewer="Local reviewer",
        reviewed_at="2026-07-13T11:00:00+00:00",
        notes="Only one review dimension was supplied.",
    )
    receipt["status"] = "needs_revision"
    receipt["updated_at"] = review["reviewed_at"]

    result = validate_human_review_receipt(
        receipt,
        _manifest(),
        manifest_sha256=MANIFEST_SHA256,
    )
    assert result["ok"] is False
    assert "proposal_kr review states must be recorded together" in result["errors"]


def test_cli_initializes_records_and_validates_receipt(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(_manifest()), encoding="utf-8")
    receipt_path = tmp_path / "human_review_receipt.json"
    summary_path = tmp_path / "human_review.html"

    assert main(["init", "--evidence-dir", str(tmp_path)]) == 0
    init_result = json.loads(capsys.readouterr().out)
    assert init_result["status"] == "pending"
    assert receipt_path.is_file()
    assert init_result["summary_path"] == str(summary_path.resolve())
    assert "검토 대기" in summary_path.read_text(encoding="utf-8")

    for bundle_type in ("proposal_kr", "performance_plan_kr"):
        assert main(
            [
                "record",
                str(receipt_path),
                "--bundle",
                bundle_type,
                "--reviewer",
                "Local reviewer",
                "--factual-grounding",
                "passed",
                "--visual-review",
                "passed",
                "--notes",
                "Reviewed against local fictional evidence.",
                "--reviewed-at",
                "2026-07-13T11:00:00+00:00",
            ]
        ) == 0
        capsys.readouterr()

    assert main(["validate", str(receipt_path)]) == 0
    validation = json.loads(capsys.readouterr().out)
    assert validation["status"] == "completed"
    assert validation["completed"] is True
    assert "검토 완료" in summary_path.read_text(encoding="utf-8")

    summary_path.unlink()
    assert main(["render", str(receipt_path)]) == 0
    render_result = json.loads(capsys.readouterr().out)
    assert render_result["summary_path"] == str(summary_path.resolve())
    assert "검토 완료" in summary_path.read_text(encoding="utf-8")
    assert not list(tmp_path.glob("*.tmp.*"))

    manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["evidence"]["manifest_sha256"] == manifest_hash
