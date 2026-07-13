from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from app.eval.human_review_receipt import (
    DRAFT_SCHEMA_VERSION,
    DRAFT_SCOPE,
    apply_human_review_draft,
    build_pending_human_review_receipt,
    record_bundle_review,
    validate_human_review_draft,
    validate_human_review_receipt,
)
from scripts.manage_finished_doc_human_review import _load_bundle_documents, main


MANIFEST_SHA256 = "a" * 64
CREATED_AT = "2026-07-13T10:00:00+00:00"


def _manifest() -> dict:
    return {
        "schema_version": "decisiondoc.finished_document_review.v3",
        "generated_at": CREATED_AT,
        "bundles": {
            "proposal_kr": {"markdown_docs": {}},
            "performance_plan_kr": {"markdown_docs": {}},
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


def _draft(*, receipt_sha256: str = "b" * 64, manifest_sha256: str = MANIFEST_SHA256) -> dict:
    return {
        "schema_version": DRAFT_SCHEMA_VERSION,
        "scope": DRAFT_SCOPE,
        "created_at": "2026-07-13T11:00:00+00:00",
        "source": {
            "receipt_path": "human_review_receipt.json",
            "receipt_sha256": receipt_sha256,
            "manifest_path": "manifest.json",
            "manifest_sha256": manifest_sha256,
        },
        "reviews": {
            bundle_type: {
                "factual_grounding": "passed",
                "visual_review": "passed",
                "reviewer": "Local reviewer",
                "notes": "Reviewed against local fictional evidence.",
            }
            for bundle_type in ("proposal_kr", "performance_plan_kr")
        },
        "external_actions_authorized": {
            "provider_api_execution": False,
            "production_service_resume": False,
        },
    }


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


def test_review_draft_is_source_bound_and_applies_review_without_authorizing_actions() -> None:
    receipt = _pending_receipt()
    draft = _draft()

    validation = validate_human_review_draft(
        draft,
        receipt,
        _manifest(),
        receipt_sha256="b" * 64,
        manifest_sha256=MANIFEST_SHA256,
    )
    assert validation["ok"] is True
    assert validation["review_count"] == 2

    updated = apply_human_review_draft(
        receipt,
        draft,
        _manifest(),
        receipt_sha256="b" * 64,
        manifest_sha256=MANIFEST_SHA256,
    )
    result = validate_human_review_receipt(
        updated,
        _manifest(),
        manifest_sha256=MANIFEST_SHA256,
    )
    assert result["completed"] is True
    assert all(value is False for value in updated["external_actions_authorized"].values())

    stale = deepcopy(draft)
    stale["source"]["receipt_sha256"] = "c" * 64
    stale_result = validate_human_review_draft(
        stale,
        receipt,
        _manifest(),
        receipt_sha256="b" * 64,
        manifest_sha256=MANIFEST_SHA256,
    )
    assert stale_result["ok"] is False
    assert "draft source does not match the current receipt and manifest" in stale_result["errors"]

    authorized = deepcopy(draft)
    authorized["external_actions_authorized"]["provider_api_execution"] = True
    action_result = validate_human_review_draft(
        authorized,
        receipt,
        _manifest(),
        receipt_sha256="b" * 64,
        manifest_sha256=MANIFEST_SHA256,
    )
    assert action_result["ok"] is False
    assert "draft must keep every external action unauthorized" in action_result["errors"]

    unknown_bundle = deepcopy(draft)
    unknown_bundle["reviews"] = {"unknown_bundle": draft["reviews"]["proposal_kr"]}
    unknown_result = validate_human_review_draft(
        unknown_bundle,
        receipt,
        _manifest(),
        receipt_sha256="b" * 64,
        manifest_sha256=MANIFEST_SHA256,
    )
    assert unknown_result["ok"] is False
    assert "draft reviews contain an unknown bundle" in unknown_result["errors"]

    partial = deepcopy(draft)
    partial["reviews"]["proposal_kr"]["notes"] = ""
    partial_result = validate_human_review_draft(
        partial,
        receipt,
        _manifest(),
        receipt_sha256="b" * 64,
        manifest_sha256=MANIFEST_SHA256,
    )
    assert partial_result["ok"] is False
    assert "proposal_kr notes must not be empty" in partial_result["errors"]

    no_op_receipt = apply_human_review_draft(
        receipt,
        draft,
        _manifest(),
        receipt_sha256="b" * 64,
        manifest_sha256=MANIFEST_SHA256,
    )
    no_op_draft = _draft(receipt_sha256="c" * 64)
    no_op_result = validate_human_review_draft(
        no_op_draft,
        no_op_receipt,
        _manifest(),
        receipt_sha256="c" * 64,
        manifest_sha256=MANIFEST_SHA256,
    )
    assert no_op_result["ok"] is False
    assert "proposal_kr draft review does not change the current receipt" in no_op_result["errors"]


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

    escaped_manifest = _manifest()
    escaped_manifest["bundles"]["proposal_kr"]["markdown_docs"] = {
        "proposal": "../outside.md",
    }
    with pytest.raises(ValueError, match="stay inside the evidence directory"):
        _load_bundle_documents(tmp_path, escaped_manifest)


def test_cli_applies_browser_review_draft_atomically(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(_manifest()), encoding="utf-8")
    receipt_path = tmp_path / "human_review_receipt.json"
    draft_path = tmp_path / "human_review_draft.json"

    assert main(["init", "--evidence-dir", str(tmp_path)]) == 0
    capsys.readouterr()
    original_receipt = receipt_path.read_bytes()
    draft = _draft(
        receipt_sha256=hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
        manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    )
    stale_draft = deepcopy(draft)
    stale_draft["source"]["receipt_sha256"] = "c" * 64
    draft_path.write_text(json.dumps(stale_draft), encoding="utf-8")
    assert main(["apply-draft", str(receipt_path), str(draft_path)]) == 1
    failure = json.loads(capsys.readouterr().out)
    assert "draft source does not match" in failure["error"]
    assert receipt_path.read_bytes() == original_receipt

    draft_path.write_text(json.dumps(draft), encoding="utf-8")

    assert main(["apply-draft", str(receipt_path), str(draft_path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "completed"
    assert result["draft_review_count"] == 2
    assert "검토 완료" in (tmp_path / "human_review.html").read_text(encoding="utf-8")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert all(value is False for value in receipt["external_actions_authorized"].values())
    assert not list(tmp_path.glob("*.tmp.*"))
