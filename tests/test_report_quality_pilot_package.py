from __future__ import annotations

import io
import hashlib
import json
import zipfile

import pytest

from app.services.report_quality_pilot_package import (
    PACKAGE_MANIFEST_NAME,
    build_pilot_review_package,
    summarize_pilot_review_package_verification,
    verify_pilot_review_package,
)
from app.services.report_quality_learning import (
    REQUIRED_DIMENSIONS,
    build_correction_artifact_from_snapshot,
)
from app.services.report_quality_pilot_receipt import (
    build_pilot_export_receipt,
    serialize_pilot_export_receipt,
)


def _ready_artifact(index: int, *, tenant_id: str = "tenant-a") -> dict:
    return build_correction_artifact_from_snapshot(
        {
            "tenant_id": tenant_id,
            "report_workflow_id": f"rw_{index}",
            "status": "final_approved",
            "export_version": 1,
            "report_type": "proposal_deck",
            "audience": "executive",
            "client": "public_sector",
            "learning": {"learning_opt_in": True},
        },
        {
            "reviewer": f"reviewer-{index}",
            "reviewed_at": "2026-07-15T09:00:00+09:00",
            "overall_score": 0.88,
            "dimension_scores": {dimension: 0.86 for dimension in REQUIRED_DIMENSIONS},
            "change_requests": [
                {
                    "target": "slide:1",
                    "issue": "근거와 결론의 연결이 약함",
                    "correction": "확인된 근거 다음에 결론을 배치함",
                    "rationale": "검토자가 판단 근거를 바로 확인할 수 있어야 함",
                }
            ],
            "rationale_by_dimension": {
                dimension: f"{dimension} 검토 완료"
                for dimension in REQUIRED_DIMENSIONS
            },
            "before_planning_summary": f"교정 전 기획 {index}",
            "after_planning_summary": f"교정 후 기획 {index}",
            "accepted_for_learning": True,
            "confirmed_claims": ["검토된 근거"],
            "assumed_claims": [],
            "todo_claims": [],
            "forbidden_terms_scan": "pass",
            "privacy_security_scan": "pass",
            "human_review_status": "accepted",
        },
        artifact_id=f"rqa_{index}",
    )


def _package_inputs():
    artifacts = [_ready_artifact(index) for index in range(1, 4)]
    artifacts[2]["learning_labels"].pop("confirmed_claims")
    artifacts[2]["learning_labels"].pop("assumed_claims")
    artifacts[2]["learning_labels"].pop("todo_claims")
    artifacts[2]["after"].pop("final_output_reference")
    jsonl = "".join(
        json.dumps(artifact, ensure_ascii=False, sort_keys=True) + "\n"
        for artifact in artifacts
    )
    export_sha256 = hashlib.sha256(jsonl.encode("utf-8")).hexdigest()
    preview = {
        "filename": f"report_quality_pilot_artifacts_{export_sha256[:12]}.jsonl",
        "export_sha256": export_sha256,
        "ordered_artifact_ids": [artifact["artifact_id"] for artifact in artifacts],
        "artifact_count": len(artifacts),
    }
    receipt = build_pilot_export_receipt(
        preview=preview,
        tenant_id="tenant-a",
        request_id="pilot-package-request-1234",
    )
    return jsonl, preview, serialize_pilot_export_receipt(receipt)


def test_pilot_review_package_is_deterministic_and_self_verifying():
    jsonl, preview, receipt_bytes = _package_inputs()

    first, first_manifest = build_pilot_review_package(
        jsonl=jsonl,
        receipt_bytes=receipt_bytes,
        preview=preview,
        tenant_id="tenant-a",
    )
    second, _ = build_pilot_review_package(
        jsonl=jsonl,
        receipt_bytes=receipt_bytes,
        preview=preview,
        tenant_id="tenant-a",
    )

    assert first == second
    assert verify_pilot_review_package(first) == first_manifest
    assert first_manifest["artifact_count"] == 3
    assert first_manifest["ordered_artifact_ids"] == ["rqa_1", "rqa_2", "rqa_3"]
    assert all(
        value is False
        for value in first_manifest["external_action_boundary"].values()
    )
    with zipfile.ZipFile(io.BytesIO(first)) as archive:
        assert sorted(archive.namelist()) == sorted(
            [
                PACKAGE_MANIFEST_NAME,
                preview["filename"],
                f"report_quality_pilot_receipt_{preview['export_sha256'][:12]}.json",
            ]
        )


def test_pilot_review_package_verification_summary_is_read_only_and_receiver_facing():
    jsonl, preview, receipt_bytes = _package_inputs()
    package, _ = build_pilot_review_package(
        jsonl=jsonl,
        receipt_bytes=receipt_bytes,
        preview=preview,
        tenant_id="tenant-a",
    )

    result = summarize_pilot_review_package_verification(package)

    assert result["report_type"] == "report_quality_pilot_review_package_verification"
    assert result["schema_version"] == "decisiondoc_report_quality_pilot_package_verification.v1"
    assert result["status"] == "verified"
    assert result["package_sha256"] == hashlib.sha256(package).hexdigest()
    assert result["package_size_bytes"] == len(package)
    assert result["tenant_id"] == "tenant-a"
    assert result["artifact_count"] == 3
    assert result["ordered_artifact_ids"] == ["rqa_1", "rqa_2", "rqa_3"]
    assert result["export_sha256"] == preview["export_sha256"]
    assert len(result["entries"]) == 2
    assert result["operator_summary"].startswith("검증된 correction artifact 3개")
    assert "사람 검토 결정" in result["next_review_action"]
    assert result["review_readiness"] == {
        "all_ready": True,
        "ready_artifact_count": 3,
        "blocked_artifact_count": 0,
    }
    assert [item["artifact_id"] for item in result["artifacts"]] == [
        "rqa_1",
        "rqa_2",
        "rqa_3",
    ]
    first = result["artifacts"][0]
    assert first["report_workflow_id"] == "rw_1"
    assert first["reviewer"] == "reviewer-1"
    assert first["ready_for_learning"] is True
    assert first["before_planning_summary"] == "교정 전 기획 1"
    assert first["after_planning_summary"] == "교정 후 기획 1"
    assert first["claim_counts"] == {"confirmed": 1, "assumed": 0, "todo": 0}
    assert len(first["change_requests"]) == 1
    third = result["artifacts"][2]
    assert third["claim_counts"] == {"confirmed": 0, "assumed": 0, "todo": 0}
    assert third["warnings"] == ["accepted artifact has no after.final_output_reference"]
    assert all(result["validation"].values())
    assert all(value is False for value in result["external_action_boundary"].values())
    assert result["persisted"] is False


def test_pilot_review_package_rejects_artifact_that_is_not_learning_ready():
    artifacts = [_ready_artifact(index) for index in range(1, 4)]
    artifacts[1]["learning_labels"]["human_review_status"] = "pending"
    jsonl = "".join(
        json.dumps(artifact, ensure_ascii=False, sort_keys=True) + "\n"
        for artifact in artifacts
    )
    export_sha256 = hashlib.sha256(jsonl.encode("utf-8")).hexdigest()
    preview = {
        "filename": f"report_quality_pilot_artifacts_{export_sha256[:12]}.jsonl",
        "export_sha256": export_sha256,
        "ordered_artifact_ids": [artifact["artifact_id"] for artifact in artifacts],
        "artifact_count": len(artifacts),
    }
    receipt = build_pilot_export_receipt(
        preview=preview,
        tenant_id="tenant-a",
        request_id="not-ready-package-request",
    )
    package, _ = build_pilot_review_package(
        jsonl=jsonl,
        receipt_bytes=serialize_pilot_export_receipt(receipt),
        preview=preview,
        tenant_id="tenant-a",
    )

    with pytest.raises(ValueError, match="artifact is not learning-ready: rqa_2"):
        verify_pilot_review_package(package)


def test_pilot_review_package_rejects_tampered_jsonl():
    jsonl, preview, receipt_bytes = _package_inputs()
    package, _ = build_pilot_review_package(
        jsonl=jsonl,
        receipt_bytes=receipt_bytes,
        preview=preview,
        tenant_id="tenant-a",
    )

    tampered = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(package)) as source, zipfile.ZipFile(tampered, "w") as target:
        for name in source.namelist():
            content = source.read(name)
            if name.endswith(".jsonl"):
                content += b"{}\n"
            target.writestr(name, content)

    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        verify_pilot_review_package(tampered.getvalue())
