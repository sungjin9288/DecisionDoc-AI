from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from scripts.build_finished_doc_review_samples import (
    EVIDENCE_SCHEMA_VERSION,
    EXCLUDED_EXTERNAL_ACTIONS,
    run,
)


ROOT = Path(__file__).resolve().parents[1]
COMMITTED_EVIDENCE_DIR = ROOT / "docs/samples/bundle_quality_evidence/current"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _assert_evidence_files(root: Path, manifest: dict) -> None:
    for bundle in manifest["bundles"].values():
        response_snapshot = bundle["response_snapshot"]
        response_path = root / response_snapshot["path"]
        assert response_path.stat().st_size == response_snapshot["size_bytes"]
        assert _sha256(response_path) == response_snapshot["sha256"]

        golden = bundle["quality"]["canonical_golden_example"]
        golden_path = ROOT / golden["path"]
        assert golden_path.stat().st_size == golden["size_bytes"]
        assert _sha256(golden_path) == golden["sha256"]

        for generated in bundle["quality"]["generated_markdown"].values():
            generated_path = root / generated["path"]
            assert generated_path.stat().st_size == generated["size_bytes"]
            assert _sha256(generated_path) == generated["sha256"]

    for artifact in manifest["artifacts"].values():
        artifact_path = root / artifact["path"]
        assert artifact_path.stat().st_size == artifact["size_bytes"]
        assert _sha256(artifact_path) == artifact["sha256"]


def test_review_sample_builder_writes_mock_quality_evidence(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "openai")
    monkeypatch.setenv("DECISIONDOC_PROVIDER_GENERATION", "gemini")
    monkeypatch.setenv("DECISIONDOC_API_KEY", "existing-local-value")

    run_dir = run(
        tmp_path,
        ["proposal_kr", "performance_plan_kr"],
        [],
        run_name="current",
        mirror_latest=False,
    )

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == EVIDENCE_SCHEMA_VERSION
    assert manifest["status"] == "passed"
    assert manifest["execution_mode"] == {
        "provider": "mock",
        "storage": "temporary_local",
        "fixture_kind": "fictional",
    }
    assert manifest["summary"] == {
        "bundle_count": 2,
        "document_count": 6,
        "validator_pass_count": 2,
        "lint_pass_count": 2,
        "numeric_grounding_pass_count": 2,
        "unsupported_numeric_claim_count": 0,
    }
    assert manifest["external_actions"] == {action: False for action in EXCLUDED_EXTERNAL_ACTIONS}
    for bundle in manifest["bundles"].values():
        assert bundle["quality"]["validator_pass"] is True
        assert bundle["quality"]["lint_pass"] is True
        numeric_review = bundle["quality"]["numeric_grounding_review"]
        assert numeric_review["status"] == "passed"
        assert numeric_review["unsupported_count"] == 0
        assert numeric_review["scope"] == "literal_unit_bearing_numeric_coverage"
        assert numeric_review["proves_factual_truth"] is False
        assert bundle["quality"]["factual_grounding_verified"] is False
        assert bundle["quality"]["human_visual_review_completed"] is False
    _assert_evidence_files(run_dir, manifest)
    quality_report = (run_dir / "quality_report.md").read_text(encoding="utf-8")
    assert "Numeric coverage does not prove factual truth" in quality_report
    assert "Factual grounding and human visual review are not marked complete" in quality_report
    review_dashboard = (run_dir / "review.html").read_text(encoding="utf-8")
    assert "완성 문서 검토" in review_dashboard
    assert "수치 근거 확인" in review_dashboard
    assert "사람의 시각 검토" in review_dashboard
    assert "# 사업 이해" in review_dashboard
    assert "# 사업수행계획서" in review_dashboard
    assert not (tmp_path / "latest").exists()
    assert os.environ["DECISIONDOC_PROVIDER"] == "openai"
    assert os.environ["DECISIONDOC_PROVIDER_GENERATION"] == "gemini"
    assert os.environ["DECISIONDOC_API_KEY"] == "existing-local-value"


def test_committed_bundle_quality_evidence_matches_manifest() -> None:
    manifest = json.loads((COMMITTED_EVIDENCE_DIR / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["schema_version"] == EVIDENCE_SCHEMA_VERSION
    assert manifest["status"] == "passed"
    assert manifest["summary"]["bundle_count"] == 2
    assert manifest["summary"]["document_count"] == 6
    assert manifest["summary"]["validator_pass_count"] == 2
    assert manifest["summary"]["lint_pass_count"] == 2
    assert manifest["summary"]["numeric_grounding_pass_count"] == 2
    assert manifest["summary"]["unsupported_numeric_claim_count"] == 0
    assert all(value is False for value in manifest["external_actions"].values())
    _assert_evidence_files(COMMITTED_EVIDENCE_DIR, manifest)


def test_review_sample_builder_preserves_unrecognized_output_directory(tmp_path: Path) -> None:
    run_dir = tmp_path / "current"
    run_dir.mkdir()
    existing_file = run_dir / "keep.txt"
    existing_file.write_text("user-owned\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="refusing to replace an unrecognized output directory"):
        run(
            tmp_path,
            ["proposal_kr"],
            [],
            run_name="current",
            mirror_latest=False,
        )

    assert existing_file.read_text(encoding="utf-8") == "user-owned\n"
