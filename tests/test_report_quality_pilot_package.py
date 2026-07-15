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
from app.services.report_quality_pilot_receipt import (
    build_pilot_export_receipt,
    serialize_pilot_export_receipt,
)


def _package_inputs():
    artifacts = [
        {
            "artifact_id": f"rqa_{index}",
            "workflow_reference": {"tenant_id": "tenant-a"},
            "training_boundary": {
                "external_dataset_upload_authorized": False,
                "provider_fine_tune_api_call_authorized": False,
                "training_execution_authorized": False,
                "model_promotion_authorized": False,
            },
        }
        for index in range(1, 4)
    ]
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
    assert result["status"] == "verified"
    assert result["package_sha256"] == hashlib.sha256(package).hexdigest()
    assert result["package_size_bytes"] == len(package)
    assert result["tenant_id"] == "tenant-a"
    assert result["artifact_count"] == 3
    assert result["ordered_artifact_ids"] == ["rqa_1", "rqa_2", "rqa_3"]
    assert result["export_sha256"] == preview["export_sha256"]
    assert len(result["entries"]) == 2
    assert all(result["validation"].values())
    assert all(value is False for value in result["external_action_boundary"].values())
    assert result["persisted"] is False


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
