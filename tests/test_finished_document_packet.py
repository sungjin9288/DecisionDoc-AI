from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest

from app.eval.finished_document_packet import (
    PACKET_MANIFEST_PATH,
    build_finished_document_review_packet,
    verify_finished_document_review_packet,
)
from app.eval.human_review_receipt import (
    build_pending_human_review_receipt,
    record_bundle_review,
)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _write(path: Path, content: bytes, *, relative_to: Path) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return {
        "path": path.relative_to(relative_to).as_posix(),
        "size_bytes": len(content),
        "sha256": _sha256(content),
    }


def _review_evidence(tmp_path: Path) -> tuple[dict, dict]:
    quality_report = b"# Quality report\n"
    response_snapshot = b'{"provider":"mock"}\n'
    markdown = b"# Proposal\n\nReviewed content.\n"
    summary = b"<!doctype html><title>Human review</title>\n"

    quality_record = _write(tmp_path / "quality_report.md", quality_report, relative_to=tmp_path)
    response_record = _write(
        tmp_path / "proposal_kr/generate_response.json",
        response_snapshot,
        relative_to=tmp_path,
    )
    markdown_record = _write(
        tmp_path / "proposal_kr/markdown/proposal.md",
        markdown,
        relative_to=tmp_path,
    )
    (tmp_path / "human_review.html").write_bytes(summary)

    manifest = {
        "schema_version": "decisiondoc.finished_document_review.v3",
        "generated_at": "2026-07-13T10:00:00+00:00",
        "artifacts": {"quality_report": quality_record},
        "bundles": {
            "proposal_kr": {
                "title": "Proposal",
                "response_snapshot": response_record,
                "markdown_docs": {"proposal": markdown_record["path"]},
                "exports": {},
                "preview_files": {},
                "quality": {
                    "generated_markdown": {"proposal": markdown_record},
                },
            }
        },
        "external_actions": {
            "provider_api_execution": False,
            "production_service_resume": False,
        },
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    pending = build_pending_human_review_receipt(
        manifest,
        manifest_sha256=_sha256(manifest_path.read_bytes()),
    )
    completed = record_bundle_review(
        pending,
        bundle_type="proposal_kr",
        reviewer="Local reviewer",
        factual_grounding="passed",
        visual_review="passed",
        notes="Reviewed against the local fictional evidence.",
        reviewed_at="2026-07-13T11:00:00+00:00",
    )
    (tmp_path / "human_review_receipt.json").write_text(
        json.dumps(completed, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest, completed


def test_completed_review_packet_is_deterministic_and_self_verifying(tmp_path: Path) -> None:
    manifest, receipt = _review_evidence(tmp_path)

    first_packet, first_manifest = build_finished_document_review_packet(
        evidence_dir=tmp_path,
        manifest=manifest,
        receipt=receipt,
    )
    second_packet, second_manifest = build_finished_document_review_packet(
        evidence_dir=tmp_path,
        manifest=manifest,
        receipt=receipt,
    )

    assert first_packet == second_packet
    assert first_manifest == second_manifest
    validation = verify_finished_document_review_packet(first_packet)
    assert validation["ok"] is True
    assert validation["entry_count"] == first_manifest["summary"]["artifact_count"] + 1
    assert all(value is False for value in first_manifest["external_actions_authorized"].values())

    with zipfile.ZipFile(io.BytesIO(first_packet)) as archive:
        assert PACKET_MANIFEST_PATH in archive.namelist()
        assert "human_review_receipt.json" in archive.namelist()
        assert "human_review.html" in archive.namelist()


def test_review_packet_rejects_pending_receipt(tmp_path: Path) -> None:
    manifest, completed = _review_evidence(tmp_path)
    pending = build_pending_human_review_receipt(
        manifest,
        manifest_sha256=completed["evidence"]["manifest_sha256"],
    )
    (tmp_path / "human_review_receipt.json").write_text(
        json.dumps(pending, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="completed human review receipt"):
        build_finished_document_review_packet(
            evidence_dir=tmp_path,
            manifest=manifest,
            receipt=pending,
        )


def test_review_packet_rejects_source_tampering_and_path_escape(tmp_path: Path) -> None:
    manifest, receipt = _review_evidence(tmp_path)
    (tmp_path / "quality_report.md").write_text("tampered\n", encoding="utf-8")

    with pytest.raises(ValueError, match="size does not match manifest"):
        build_finished_document_review_packet(
            evidence_dir=tmp_path,
            manifest=manifest,
            receipt=receipt,
        )

    manifest["bundles"]["proposal_kr"]["markdown_docs"]["proposal"] = "../outside.md"
    with pytest.raises(ValueError, match="stay inside the evidence directory"):
        build_finished_document_review_packet(
            evidence_dir=tmp_path,
            manifest=manifest,
            receipt=receipt,
        )

    manifest["bundles"]["proposal_kr"]["markdown_docs"]["proposal"] = PACKET_MANIFEST_PATH
    with pytest.raises(ValueError, match="artifact path is reserved"):
        build_finished_document_review_packet(
            evidence_dir=tmp_path,
            manifest=manifest,
            receipt=receipt,
        )


def test_review_packet_verifier_detects_archive_entry_tampering(tmp_path: Path) -> None:
    manifest, receipt = _review_evidence(tmp_path)
    packet, _ = build_finished_document_review_packet(
        evidence_dir=tmp_path,
        manifest=manifest,
        receipt=receipt,
    )

    tampered = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(packet)) as source, zipfile.ZipFile(tampered, "w") as target:
        for info in source.infolist():
            content = source.read(info.filename)
            if info.filename == "quality_report.md":
                content = b"tampered\n"
            target.writestr(info, content)

    validation = verify_finished_document_review_packet(tampered.getvalue())
    assert validation["ok"] is False
    assert "packet artifact SHA256 is invalid: quality_report.md" in validation["errors"]

    with zipfile.ZipFile(io.BytesIO(packet)) as source:
        entries = {info.filename: source.read(info.filename) for info in source.infolist()}
    pending_receipt = json.loads(entries["human_review_receipt.json"])
    pending_receipt["status"] = "pending"
    pending_receipt["updated_at"] = pending_receipt["created_at"]
    pending_receipt["bundle_reviews"]["proposal_kr"] = {
        "factual_grounding": "not_reviewed",
        "visual_review": "not_reviewed",
        "decision": "pending",
        "reviewer": "",
        "reviewed_at": "",
        "notes": "",
    }
    pending_content = (json.dumps(pending_receipt, indent=2) + "\n").encode("utf-8")
    entries["human_review_receipt.json"] = pending_content
    packet_manifest = json.loads(entries[PACKET_MANIFEST_PATH])
    packet_manifest["source"]["receipt_sha256"] = _sha256(pending_content)
    for record in packet_manifest["artifacts"]:
        if record["path"] == "human_review_receipt.json":
            record["size_bytes"] = len(pending_content)
            record["sha256"] = _sha256(pending_content)
    entries[PACKET_MANIFEST_PATH] = (
        json.dumps(packet_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")

    semantic_tamper = io.BytesIO()
    with zipfile.ZipFile(semantic_tamper, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    semantic_validation = verify_finished_document_review_packet(semantic_tamper.getvalue())
    assert semantic_validation["ok"] is False
    assert "packet receipt is not a valid completed review" in semantic_validation["errors"]
