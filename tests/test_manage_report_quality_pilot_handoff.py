from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import zipfile
from pathlib import Path

import pytest

from app.services.report_quality_pilot_receipt import (
    build_pilot_export_receipt,
    serialize_pilot_export_receipt,
)
from app.services.report_quality_pilot_package import build_pilot_review_package


REPO_ROOT = Path(__file__).resolve().parents[1]
CREATE_PACK_PATH = REPO_ROOT / "scripts/create_report_quality_pilot_pack.py"
CREATE_SHEET_PATH = REPO_ROOT / "scripts/create_report_quality_review_sheet.py"
APPLY_PATH = REPO_ROOT / "scripts/apply_report_quality_review_decisions.py"
SYNC_PATH = REPO_ROOT / "scripts/sync_report_quality_pilot_pack.py"
HANDOFF_PATH = REPO_ROOT / "scripts/manage_report_quality_pilot_handoff.py"
SUMMARY_PATH = REPO_ROOT / "scripts/report_quality_pilot_handoff_summary.py"
ARTIFACT_TEMPLATE_PATH = (
    REPO_ROOT
    / "docs/specs/report_quality_learning/correction_artifact_template.json"
)


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _ready_artifact(artifact_id: str) -> dict:
    artifact = json.loads(ARTIFACT_TEMPLATE_PATH.read_text(encoding="utf-8"))
    artifact["artifact_id"] = artifact_id
    artifact["quality_baseline"]["overall_score"] = 0.88
    for dimension in artifact["quality_baseline"]["dimension_scores"]:
        artifact["quality_baseline"]["dimension_scores"][dimension] = 0.86
    artifact["correction"]["reviewer"] = "pilot-reviewer"
    artifact["correction"]["reviewed_at"] = "2026-07-14T10:00:00+09:00"
    for dimension in artifact["correction"]["rationale_by_dimension"]:
        artifact["correction"]["rationale_by_dimension"][dimension] = (
            f"{dimension} manual review rationale"
        )
    labels = artifact["learning_labels"]
    labels["accepted_for_learning"] = True
    labels["forbidden_terms_scan"] = "pass"
    labels["privacy_security_scan"] = "pass"
    labels["human_review_status"] = "accepted"
    artifact["after"]["final_output_reference"] = (
        f"report_workflow_snapshot:{artifact_id}"
    )
    return artifact


def _approve_and_sync(pack_dir: Path) -> Path:
    create_sheet = _load_module(CREATE_SHEET_PATH, "handoff_create_sheet")
    apply = _load_module(APPLY_PATH, "handoff_apply_review")
    sync = _load_module(SYNC_PATH, "handoff_sync_pack")
    create_sheet.create_report_quality_review_sheet(pack_dir=pack_dir)

    decisions_path = pack_dir / "review_decisions.handoff-approved.json"
    receipt_path = pack_dir / "handoff-ready-review-receipt.json"
    apply.create_review_decision_template(
        pack_dir=pack_dir,
        output_path=decisions_path,
    )
    applied = apply.apply_review_decisions(
        pack_dir=pack_dir,
        decisions_path=decisions_path,
        require_ready=True,
        receipt_path=receipt_path,
    )
    assert applied["ok"] is True

    synced = sync.sync_report_quality_pilot_pack(
        pack_dir=pack_dir,
        min_records=3,
        require_ready=True,
    )
    assert synced["ok"] is True
    return Path(synced["output_path"])


def _reviewed_pack(tmp_path: Path) -> tuple[Path, Path]:
    create_pack = _load_module(CREATE_PACK_PATH, "handoff_create_pack")
    created = create_pack.create_report_quality_pilot_pack(
        batch_id="pilot-handoff",
        output_root=tmp_path,
        sample_count=3,
        reviewer="pilot-reviewer",
    )
    pack_dir = Path(created["output_dir"])
    for draft_path in sorted((pack_dir / "drafts").glob("*.json")):
        artifact = _ready_artifact(draft_path.stem)
        draft_path.write_text(
            json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return pack_dir, _approve_and_sync(pack_dir)


def _source_bound_reviewed_pack(tmp_path: Path) -> tuple[Path, Path]:
    create_pack = _load_module(CREATE_PACK_PATH, "handoff_create_source_pack")
    artifacts = [_ready_artifact(f"source_artifact_{index}") for index in range(1, 4)]
    source_jsonl = tmp_path / "source-ready.jsonl"
    source_jsonl.write_text(
        "\n".join(json.dumps(artifact, ensure_ascii=False) for artifact in artifacts) + "\n",
        encoding="utf-8",
    )
    source_sha256 = hashlib.sha256(source_jsonl.read_bytes()).hexdigest()
    receipt = build_pilot_export_receipt(
        preview={
            "filename": f"report_quality_pilot_artifacts_{source_sha256[:12]}.jsonl",
            "export_sha256": source_sha256,
            "ordered_artifact_ids": [artifact["artifact_id"] for artifact in artifacts],
        },
        tenant_id=artifacts[0]["workflow_reference"]["tenant_id"],
        request_id="source-handoff-request",
    )
    receipt_bytes = serialize_pilot_export_receipt(receipt)
    source_package_bytes, _ = build_pilot_review_package(
        jsonl=source_jsonl.read_text(encoding="utf-8"),
        receipt_bytes=receipt_bytes,
        preview={
            "filename": f"report_quality_pilot_artifacts_{source_sha256[:12]}.jsonl",
            "export_sha256": source_sha256,
            "ordered_artifact_ids": [artifact["artifact_id"] for artifact in artifacts],
        },
        tenant_id=artifacts[0]["workflow_reference"]["tenant_id"],
    )
    source_package = tmp_path / "source-package.zip"
    source_package.write_bytes(source_package_bytes)
    created = create_pack.create_report_quality_pilot_pack(
        batch_id="source-bound-handoff",
        output_root=tmp_path / "packs",
        source_package=source_package,
    )
    pack_dir = Path(created["output_dir"])
    return pack_dir, _approve_and_sync(pack_dir)


def _rewrite_zip(content: bytes, replacements: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(content)) as source, zipfile.ZipFile(
        output,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as target:
        for name in source.namelist():
            target.writestr(name, replacements.get(name, source.read(name)))
    return output.getvalue()


def _downgrade_to_v1(content: bytes) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(content)) as source:
        manifest = json.loads(source.read("handoff_manifest.json"))
        manifest["schema_version"] = "decisiondoc_report_quality_pilot_review_handoff.v1"
        manifest.pop("browser_summary")
        manifest["entries"] = [
            entry
            for entry in manifest["entries"]
            if entry["path"] != "HANDOFF_SUMMARY.html"
        ]
        manifest_bytes = (
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as target:
            for name in source.namelist():
                if name == "HANDOFF_SUMMARY.html":
                    continue
                target.writestr(
                    name,
                    manifest_bytes if name == "handoff_manifest.json" else source.read(name),
                )
    return output.getvalue()


def test_reviewed_pilot_handoff_is_deterministic_and_self_verifying(tmp_path):
    handoff = _load_module(HANDOFF_PATH, "reviewed_pilot_handoff_success")
    pack_dir, jsonl_path = _reviewed_pack(tmp_path)
    first_path = tmp_path / "handoff-first.zip"
    second_path = tmp_path / "handoff-second.zip"

    first = handoff.create_report_quality_pilot_handoff(
        pack_dir=pack_dir,
        jsonl_path=jsonl_path,
        output_path=first_path,
    )
    second = handoff.create_report_quality_pilot_handoff(
        pack_dir=pack_dir,
        jsonl_path=jsonl_path,
        output_path=second_path,
    )

    assert first["ok"] is True
    assert first["artifact_count"] == 3
    assert first["source_bound"] is False
    assert first["training_authorized"] is False
    assert first["summary_path"] == "HANDOFF_SUMMARY.md"
    assert first["browser_summary_path"] == "HANDOFF_SUMMARY.html"
    assert len(first["summary_sha256"]) == 64
    assert len(first["browser_summary_sha256"]) == 64
    assert first_path.read_bytes() == second_path.read_bytes()
    assert first["package_sha256"] == second["package_sha256"]
    assert handoff.verify_report_quality_pilot_handoff(first_path.read_bytes())["ok"] is True
    with zipfile.ZipFile(first_path) as archive:
        names = set(archive.namelist())
        manifest = json.loads(archive.read("handoff_manifest.json"))
        assert "handoff_manifest.json" in names
        assert "HANDOFF_SUMMARY.md" in names
        assert "HANDOFF_SUMMARY.html" in names
        assert "artifacts/ready_artifacts.jsonl" in names
        assert "review/human_review_manifest.json" in names
        assert len([name for name in names if name.startswith("drafts/")]) == 3
        summary = archive.read("HANDOFF_SUMMARY.md").decode("utf-8")
        assert "# Report Quality Pilot Review Handoff" in summary
        assert "pilot-reviewer" in summary
        assert "training execution: `not authorized`" in summary
        browser_summary = archive.read("HANDOFF_SUMMARY.html").decode("utf-8")
        assert browser_summary.startswith("<!doctype html>")
        assert "pilot-reviewer" in browser_summary
        assert "Training not authorized" in browser_summary
        assert "<script" not in browser_summary.lower()
        assert manifest["schema_version"] == "decisiondoc_report_quality_pilot_review_handoff.v2"
        html_entry = next(
            entry
            for entry in manifest["entries"]
            if entry["path"] == "HANDOFF_SUMMARY.html"
        )
        assert html_entry["media_type"] == "text/html; charset=utf-8"


def test_reviewed_pilot_handoff_browser_summary_escapes_evidence_values():
    summary = _load_module(SUMMARY_PATH, "reviewed_pilot_handoff_html_escaping")
    rendered = summary.render_report_quality_pilot_handoff_html(
        {
            "batch_id": '<img src=x onerror="alert(1)">',
            "artifact_count": 1,
            "jsonl": {"sha256": "jsonl-sha"},
            "review": {
                "manifest_sha256": "manifest-sha",
                "decision_receipt_sha256": "receipt-sha",
                "decision_file_sha256": "decision-sha",
            },
            "pack_binding": {"source_manifest": None},
        },
        {
            "artifacts": [
                {
                    "artifact_id": "artifact-1",
                    "reviewer": "<script>alert(1)</script>",
                    "reviewed_at": "2026-07-15T00:00:00+09:00",
                    "overall_score": 0.9,
                    "human_review_status": "accepted",
                    "ready_for_learning": True,
                }
            ]
        },
    )

    assert "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;" in rendered
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered
    assert "<script" not in rendered.lower()


def test_reviewed_pilot_handoff_verifier_accepts_previous_v1_package(tmp_path):
    handoff = _load_module(HANDOFF_PATH, "reviewed_pilot_handoff_v1_compatibility")
    pack_dir, jsonl_path = _reviewed_pack(tmp_path)
    package_path = tmp_path / "handoff-v2.zip"
    handoff.create_report_quality_pilot_handoff(
        pack_dir=pack_dir,
        jsonl_path=jsonl_path,
        output_path=package_path,
    )

    v1_package = _downgrade_to_v1(package_path.read_bytes())
    result = handoff.verify_report_quality_pilot_handoff(v1_package)

    assert result["ok"] is True
    assert result["browser_summary_path"] is None
    assert result["browser_summary_sha256"] is None
    browser_output = tmp_path / "v1-summary.html"
    with pytest.raises(ValueError, match="does not contain a browser summary"):
        handoff.write_verified_handoff_browser_summary(
            v1_package,
            output_path=browser_output,
        )
    assert not browser_output.exists()


def test_reviewed_pilot_handoff_preserves_source_bound_evidence(tmp_path):
    handoff = _load_module(HANDOFF_PATH, "reviewed_pilot_handoff_source_bound")
    pack_dir, jsonl_path = _source_bound_reviewed_pack(tmp_path)
    package_path = tmp_path / "source-bound-handoff.zip"

    created = handoff.create_report_quality_pilot_handoff(
        pack_dir=pack_dir,
        jsonl_path=jsonl_path,
        output_path=package_path,
    )
    verified = handoff.verify_report_quality_pilot_handoff(package_path.read_bytes())

    assert created["source_bound"] is True
    assert verified["source_bound"] is True
    with zipfile.ZipFile(package_path) as archive:
        names = set(archive.namelist())
        assert "source/SOURCE_MANIFEST.json" in names
        assert "source/SOURCE_EXPORT_RECEIPT.json" in names
        assert "source/SOURCE_PACKAGE_MANIFEST.json" in names


def test_reviewed_pilot_handoff_rejects_tamper_and_extra_entries(tmp_path):
    handoff = _load_module(HANDOFF_PATH, "reviewed_pilot_handoff_tamper")
    pack_dir, jsonl_path = _reviewed_pack(tmp_path)
    package_path = tmp_path / "handoff.zip"
    handoff.create_report_quality_pilot_handoff(
        pack_dir=pack_dir,
        jsonl_path=jsonl_path,
        output_path=package_path,
    )
    content = package_path.read_bytes()
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        draft_name = next(name for name in archive.namelist() if name.startswith("drafts/"))
        manifest = json.loads(archive.read("handoff_manifest.json"))
        review_manifest = json.loads(archive.read("review/human_review_manifest.json"))

    tampered_summary = _rewrite_zip(content, {"HANDOFF_SUMMARY.md": b"tampered\n"})
    with pytest.raises(ValueError, match="entry SHA-256 mismatch"):
        handoff.verify_report_quality_pilot_handoff(tampered_summary)

    false_summary = b"# False summary\n"
    false_summary_manifest = json.loads(json.dumps(manifest))
    false_summary_manifest["summary"]["sha256"] = hashlib.sha256(false_summary).hexdigest()
    for entry in false_summary_manifest["entries"]:
        if entry["path"] == "HANDOFF_SUMMARY.md":
            entry["sha256"] = hashlib.sha256(false_summary).hexdigest()
            entry["size_bytes"] = len(false_summary)
    semantically_tampered_summary = _rewrite_zip(
        content,
        {
            "HANDOFF_SUMMARY.md": false_summary,
            "handoff_manifest.json": (
                json.dumps(
                    false_summary_manifest,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            ).encode("utf-8"),
        },
    )
    with pytest.raises(ValueError, match="does not match the reviewed evidence"):
        handoff.verify_report_quality_pilot_handoff(semantically_tampered_summary)

    tampered_browser_summary = _rewrite_zip(
        content,
        {"HANDOFF_SUMMARY.html": b"<!doctype html><title>tampered</title>\n"},
    )
    with pytest.raises(ValueError, match="entry SHA-256 mismatch"):
        handoff.verify_report_quality_pilot_handoff(tampered_browser_summary)

    false_browser_summary = b"<!doctype html><title>False summary</title>\n"
    false_browser_manifest = json.loads(json.dumps(manifest))
    false_browser_sha256 = hashlib.sha256(false_browser_summary).hexdigest()
    false_browser_manifest["browser_summary"]["sha256"] = false_browser_sha256
    for entry in false_browser_manifest["entries"]:
        if entry["path"] == "HANDOFF_SUMMARY.html":
            entry["sha256"] = false_browser_sha256
            entry["size_bytes"] = len(false_browser_summary)
    semantically_tampered_browser_summary = _rewrite_zip(
        content,
        {
            "HANDOFF_SUMMARY.html": false_browser_summary,
            "handoff_manifest.json": (
                json.dumps(
                    false_browser_manifest,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            ).encode("utf-8"),
        },
    )
    with pytest.raises(ValueError, match="browser summary does not match"):
        handoff.verify_report_quality_pilot_handoff(
            semantically_tampered_browser_summary
        )

    tampered_draft = _rewrite_zip(content, {draft_name: b"{}\n"})
    with pytest.raises(ValueError, match="entry SHA-256 mismatch"):
        handoff.verify_report_quality_pilot_handoff(tampered_draft)

    manifest["external_action_boundary"]["training_execution_started"] = True
    tampered_manifest = _rewrite_zip(
        content,
        {
            "handoff_manifest.json": (
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            ).encode("utf-8")
        },
    )
    with pytest.raises(ValueError, match="external action boundary is invalid"):
        handoff.verify_report_quality_pilot_handoff(tampered_manifest)

    review_manifest["artifacts"].append("invalid-row")
    review_bytes = (
        json.dumps(review_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    manifest["review"]["manifest_sha256"] = hashlib.sha256(review_bytes).hexdigest()
    for entry in manifest["entries"]:
        if entry["path"] == "review/human_review_manifest.json":
            entry["sha256"] = hashlib.sha256(review_bytes).hexdigest()
            entry["size_bytes"] = len(review_bytes)
    malformed_review = _rewrite_zip(
        content,
        {
            "handoff_manifest.json": (
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            ).encode("utf-8"),
            "review/human_review_manifest.json": review_bytes,
        },
    )
    with pytest.raises(ValueError, match="must be a non-empty list of objects"):
        handoff.verify_report_quality_pilot_handoff(malformed_review)

    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(content)) as source, zipfile.ZipFile(output, "w") as target:
        for name in source.namelist():
            target.writestr(name, source.read(name))
        target.writestr("unexpected.json", b"{}")
    with pytest.raises(ValueError, match="membership does not match"):
        handoff.verify_report_quality_pilot_handoff(output.getvalue())


def test_reviewed_pilot_handoff_rejects_stale_or_unsafe_inputs(tmp_path):
    handoff = _load_module(HANDOFF_PATH, "reviewed_pilot_handoff_input_guards")
    pack_dir, jsonl_path = _reviewed_pack(tmp_path)

    first_draft = next((pack_dir / "drafts").glob("*.json"))
    first_draft.write_bytes(first_draft.read_bytes() + b" ")
    with pytest.raises(ValueError, match="human review manifest does not match"):
        handoff.create_report_quality_pilot_handoff(
            pack_dir=pack_dir,
            jsonl_path=jsonl_path,
            output_path=tmp_path / "stale.zip",
        )

    pack_dir, jsonl_path = _reviewed_pack(tmp_path / "fresh")
    jsonl_link = tmp_path / "ready-link.jsonl"
    jsonl_link.symlink_to(jsonl_path)
    with pytest.raises(ValueError, match="symlink reviewed pilot JSONL"):
        handoff.create_report_quality_pilot_handoff(
            pack_dir=pack_dir,
            jsonl_path=jsonl_link,
            output_path=tmp_path / "linked-input.zip",
        )

    existing_output = tmp_path / "existing.zip"
    existing_output.write_bytes(b"existing")
    with pytest.raises(ValueError, match="refusing to overwrite"):
        handoff.create_report_quality_pilot_handoff(
            pack_dir=pack_dir,
            jsonl_path=jsonl_path,
            output_path=existing_output,
        )

    output_target = tmp_path / "target.zip"
    output_link = tmp_path / "output-link.zip"
    output_link.symlink_to(output_target)
    with pytest.raises(ValueError, match="symlink handoff package outputs"):
        handoff.create_report_quality_pilot_handoff(
            pack_dir=pack_dir,
            jsonl_path=jsonl_path,
            output_path=output_link,
        )


def test_reviewed_pilot_handoff_writes_only_a_verified_summary(tmp_path):
    handoff = _load_module(HANDOFF_PATH, "reviewed_pilot_handoff_summary_output")
    pack_dir, jsonl_path = _reviewed_pack(tmp_path)
    package_path = tmp_path / "handoff.zip"
    handoff.create_report_quality_pilot_handoff(
        pack_dir=pack_dir,
        jsonl_path=jsonl_path,
        output_path=package_path,
    )
    package_bytes = package_path.read_bytes()
    summary_path = tmp_path / "handoff-summary.md"

    result = handoff.write_verified_handoff_summary(
        package_bytes,
        output_path=summary_path,
    )

    with zipfile.ZipFile(package_path) as archive:
        expected_summary = archive.read("HANDOFF_SUMMARY.md")
    assert summary_path.read_bytes() == expected_summary
    assert result["summary_output_path"] == str(summary_path)
    assert result["summary_sha256"] == hashlib.sha256(expected_summary).hexdigest()

    with pytest.raises(ValueError, match="refusing to overwrite"):
        handoff.write_verified_handoff_summary(
            package_bytes,
            output_path=summary_path,
        )
    with pytest.raises(ValueError, match="must use the .md extension"):
        handoff.write_verified_handoff_summary(
            package_bytes,
            output_path=tmp_path / "summary.txt",
        )

    summary_link = tmp_path / "summary-link.md"
    summary_link.symlink_to(tmp_path / "summary-target.md")
    with pytest.raises(ValueError, match="symlink handoff summary outputs"):
        handoff.write_verified_handoff_summary(
            package_bytes,
            output_path=summary_link,
        )

    tampered_package = _rewrite_zip(
        package_bytes,
        {"HANDOFF_SUMMARY.md": b"tampered\n"},
    )
    tampered_output = tmp_path / "tampered-summary.md"
    with pytest.raises(ValueError, match="entry SHA-256 mismatch"):
        handoff.write_verified_handoff_summary(
            tampered_package,
            output_path=tampered_output,
        )
    assert not tampered_output.exists()


def test_reviewed_pilot_handoff_writes_only_a_verified_browser_summary(tmp_path):
    handoff = _load_module(HANDOFF_PATH, "reviewed_pilot_handoff_browser_summary_output")
    pack_dir, jsonl_path = _reviewed_pack(tmp_path)
    package_path = tmp_path / "handoff.zip"
    handoff.create_report_quality_pilot_handoff(
        pack_dir=pack_dir,
        jsonl_path=jsonl_path,
        output_path=package_path,
    )
    package_bytes = package_path.read_bytes()
    browser_summary_path = tmp_path / "handoff-summary.html"

    result = handoff.write_verified_handoff_browser_summary(
        package_bytes,
        output_path=browser_summary_path,
    )

    with zipfile.ZipFile(package_path) as archive:
        expected_summary = archive.read("HANDOFF_SUMMARY.html")
    assert browser_summary_path.read_bytes() == expected_summary
    assert result["browser_summary_output_path"] == str(browser_summary_path)
    assert result["browser_summary_sha256"] == hashlib.sha256(expected_summary).hexdigest()

    with pytest.raises(ValueError, match="refusing to overwrite"):
        handoff.write_verified_handoff_browser_summary(
            package_bytes,
            output_path=browser_summary_path,
        )
    with pytest.raises(ValueError, match="must use the .html extension"):
        handoff.write_verified_handoff_browser_summary(
            package_bytes,
            output_path=tmp_path / "summary.txt",
        )

    summary_link = tmp_path / "summary-link.html"
    summary_link.symlink_to(tmp_path / "summary-target.html")
    with pytest.raises(ValueError, match="symlink handoff browser summary outputs"):
        handoff.write_verified_handoff_browser_summary(
            package_bytes,
            output_path=summary_link,
        )

    tampered_package = _rewrite_zip(
        package_bytes,
        {"HANDOFF_SUMMARY.html": b"tampered\n"},
    )
    tampered_output = tmp_path / "tampered-summary.html"
    with pytest.raises(ValueError, match="entry SHA-256 mismatch"):
        handoff.write_verified_handoff_browser_summary(
            tampered_package,
            output_path=tampered_output,
        )
    assert not tampered_output.exists()


def test_reviewed_pilot_handoff_finalize_needs_no_standalone_jsonl(tmp_path, monkeypatch):
    handoff = _load_module(HANDOFF_PATH, "reviewed_pilot_handoff_finalize")
    pack_dir, jsonl_path = _reviewed_pack(tmp_path)
    jsonl_path.unlink()
    package_path = tmp_path / "finalized-handoff.zip"
    temporary_jsonl_path = None
    sync_pack = handoff.sync_report_quality_pilot_pack

    def capture_temporary_jsonl(**kwargs):
        nonlocal temporary_jsonl_path
        temporary_jsonl_path = kwargs["output_path"]
        return sync_pack(**kwargs)

    monkeypatch.setattr(handoff, "sync_report_quality_pilot_pack", capture_temporary_jsonl)

    result = handoff.finalize_report_quality_pilot_handoff(
        pack_dir=pack_dir,
        output_path=package_path,
    )

    assert result["ok"] is True
    assert result["report_type"] == "report_quality_pilot_review_handoff_finalized"
    assert result["ready_sync"]["artifact_count"] == 3
    assert result["ready_sync"]["jsonl_sha256"] == result["jsonl_sha256"]
    assert result["ready_sync"]["review_manifest"]["sha256"] == result["review_manifest_sha256"]
    assert result["ready_sync"]["decision_receipt"]["sha256"] == result["decision_receipt_sha256"]
    assert "jsonl_path" not in result
    assert result["side_effect_boundary"]["retains_standalone_jsonl"] is False
    assert package_path.is_file()
    assert not list(pack_dir.glob("*-drafts.jsonl"))
    assert temporary_jsonl_path is not None
    assert not temporary_jsonl_path.exists()
    assert not temporary_jsonl_path.parent.exists()
    assert handoff.verify_report_quality_pilot_handoff(package_path.read_bytes())["ok"] is True


def test_reviewed_pilot_handoff_finalize_leaves_no_package_when_review_is_pending(tmp_path):
    handoff = _load_module(HANDOFF_PATH, "reviewed_pilot_handoff_finalize_pending")
    create_pack = _load_module(CREATE_PACK_PATH, "handoff_finalize_pending_pack")
    created = create_pack.create_report_quality_pilot_pack(
        batch_id="pilot-handoff-pending",
        output_root=tmp_path,
        sample_count=3,
        reviewer="pilot-reviewer",
    )
    package_path = tmp_path / "blocked-handoff.zip"

    with pytest.raises(ValueError, match="reviewed pilot finalization blocked"):
        handoff.finalize_report_quality_pilot_handoff(
            pack_dir=Path(created["output_dir"]),
            output_path=package_path,
        )

    assert not package_path.exists()


def test_reviewed_pilot_handoff_cli_finalize(tmp_path, capsys):
    handoff = _load_module(HANDOFF_PATH, "reviewed_pilot_handoff_cli_finalize")
    pack_dir, jsonl_path = _reviewed_pack(tmp_path)
    jsonl_path.unlink()
    package_path = tmp_path / "cli-finalized-handoff.zip"

    exit_code = handoff.main([
        "finalize",
        str(pack_dir),
        "--output",
        str(package_path),
        "--json",
    ])
    result = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert result["ok"] is True
    assert result["output_path"] == str(package_path)
    assert result["ready_sync"]["jsonl_sha256"] == result["jsonl_sha256"]
    assert result["training_authorized"] is False
    assert package_path.is_file()


def test_reviewed_pilot_handoff_cli_create_and_verify(tmp_path, capsys):
    handoff = _load_module(HANDOFF_PATH, "reviewed_pilot_handoff_cli")
    pack_dir, jsonl_path = _reviewed_pack(tmp_path)
    package_path = tmp_path / "cli-handoff.zip"

    create_exit = handoff.main([
        "create",
        str(pack_dir),
        "--jsonl",
        str(jsonl_path),
        "--output",
        str(package_path),
        "--json",
    ])
    created = json.loads(capsys.readouterr().out)
    summary_output = tmp_path / "cli-summary.md"
    verify_exit = handoff.main([
        "verify",
        str(package_path),
        "--summary-output",
        str(summary_output),
        "--json",
    ])
    verified = json.loads(capsys.readouterr().out)
    browser_summary_output = tmp_path / "cli-summary.html"
    browser_verify_exit = handoff.main([
        "verify",
        str(package_path),
        "--browser-summary-output",
        str(browser_summary_output),
        "--json",
    ])
    browser_verified = json.loads(capsys.readouterr().out)
    human_verify_exit = handoff.main(["verify", str(package_path)])
    human_output = capsys.readouterr().out
    with pytest.raises(SystemExit):
        handoff.main([
            "verify",
            str(package_path),
            "--summary-output",
            str(tmp_path / "both.md"),
            "--browser-summary-output",
            str(tmp_path / "both.html"),
        ])

    assert create_exit == 0
    assert verify_exit == 0
    assert browser_verify_exit == 0
    assert human_verify_exit == 0
    assert created["package_sha256"] == verified["package_sha256"]
    assert verified["artifact_count"] == 3
    assert verified["training_authorized"] is False
    assert verified["summary_output_path"] == str(summary_output)
    assert summary_output.is_file()
    assert browser_verified["browser_summary_output_path"] == str(browser_summary_output)
    assert browser_summary_output.is_file()
    assert "summary_path=HANDOFF_SUMMARY.md" in human_output
    assert f"summary_sha256={verified['summary_sha256']}" in human_output
