from __future__ import annotations

import copy
import json
from pathlib import Path

from scripts.validate_future_feature_gate import (
    RESULT_SCHEMA_VERSION,
    main,
    validate_future_feature_gate,
)


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT / "docs/samples/future_feature_gate/template.json"


def _template() -> dict[str, object]:
    return json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))


def _approved_record() -> dict[str, object]:
    record = copy.deepcopy(_template())
    record.update(
        {
            "gate_id": "review-summary-export",
            "title": "Reviewer summary export",
            "target_user": "A reviewer preparing a local decision handoff",
            "observed_problem": "The current handoff requires manual summary assembly.",
            "evidence": [
                {
                    "kind": "repository",
                    "reference": "docs/product_execution_plan.md:242",
                    "observation": "Feature admission currently depends on prose fields.",
                }
            ],
            "current_workaround": "The reviewer assembles the summary manually.",
            "desired_outcome": "Produce one inspectable local summary.",
            "acceptance_criteria": ["A focused test verifies deterministic output."],
            "affected_boundaries": ["documentation"],
            "authority_scope": {
                "review_only": True,
                "allowed_effects": ["local test artifacts"],
                "excluded_effects": ["provider calls"],
                "separate_approval_required_for": ["production deployment"],
            },
            "local_verification": [
                {
                    "command": "python3 -m pytest -q tests/test_review_summary.py",
                    "proves": "The local summary remains deterministic and review-only.",
                }
            ],
        }
    )
    record["decision"] = {
        "status": "approved",
        "rationale": "The observed problem and bounded local path justify implementation.",
        "decided_by": "repository-maintainer",
        "decided_at": "2026-09-04T05:30:00Z",
    }
    return record


def test_repository_template_is_valid_but_not_admitted() -> None:
    result = validate_future_feature_gate(_template())

    assert result["status"] == "passed"
    assert result["record_valid"] is True
    assert result["admitted_for_implementation"] is False
    assert result["decision_status"] == "draft"


def test_require_approved_distinguishes_valid_draft_from_admitted_record() -> None:
    draft = validate_future_feature_gate(_template(), require_approved=True)
    approved = validate_future_feature_gate(_approved_record(), require_approved=True)

    assert draft["status"] == "failed"
    assert draft["record_valid"] is True
    assert draft["errors"] == ["decision.status must be approved before implementation"]
    assert approved["status"] == "passed"
    assert approved["record_valid"] is True
    assert approved["admitted_for_implementation"] is True
    assert approved["decision_identity_verified"] is False
    assert approved["operational_authority_granted"] is False

    marker_record = _template()
    marker_record["decision"] = {
        "status": "approved",
        "rationale": "Changing status alone must not admit the template.",
        "decided_by": "repository-maintainer",
        "decided_at": "2026-09-04T05:30:00Z",
    }
    marker_result = validate_future_feature_gate(marker_record, require_approved=True)
    assert marker_result["record_valid"] is False
    assert "approved record must replace all draft template markers" in marker_result["errors"]

    invalid_timestamp = _approved_record()
    invalid_timestamp["decision"]["decided_at"] = "2026-09-04"
    invalid = validate_future_feature_gate(invalid_timestamp, require_approved=True)
    assert invalid["record_valid"] is False
    assert any("decided_at must use YYYY-MM-DDTHH:MM:SSZ" in error for error in invalid["errors"])


def test_validator_rejects_unknown_fields_and_incomplete_evidence() -> None:
    record = _approved_record()
    record["unexpected"] = True
    record["evidence"] = []
    record["affected_boundaries"] = ["storage", "storage"]

    result = validate_future_feature_gate(record, require_approved=True)

    assert result["status"] == "failed"
    assert result["record_valid"] is False
    assert "unexpected: Extra inputs are not permitted" in result["errors"]
    assert (
        "evidence: List should have at least 1 item after validation, not 0"
        in result["errors"]
    )
    assert "affected_boundaries: Value error, must not contain duplicate values" in result["errors"]
    assert "record must be valid before implementation" in result["errors"]


def test_cli_emits_deterministic_json_and_rejects_duplicate_keys(
    capsys, tmp_path: Path
) -> None:
    valid_path = tmp_path / "approved.json"
    valid_path.write_text(json.dumps(_approved_record()), encoding="utf-8")

    assert main([str(valid_path), "--require-approved", "--json"]) == 0
    first = capsys.readouterr().out
    assert main([str(valid_path), "--require-approved", "--json"]) == 0
    second = capsys.readouterr().out

    assert first == second
    success = json.loads(first)
    assert success["schema_version"] == RESULT_SCHEMA_VERSION
    assert success["decision_identity_verified"] is False
    assert success["operational_authority_granted"] is False

    duplicate_path = tmp_path / "duplicate.json"
    duplicate_path.write_text(
        '{"schema_version":"one","schema_version":"two"}',
        encoding="utf-8",
    )
    assert main([str(duplicate_path), "--json"]) == 1
    failure = json.loads(capsys.readouterr().out)
    assert failure["record_valid"] is False
    assert failure["errors"] == ["duplicate JSON key: schema_version"]

    non_finite_path = tmp_path / "non-finite.json"
    non_finite_path.write_text('{"value":NaN}', encoding="utf-8")
    assert main([str(non_finite_path), "--json"]) == 1
    failure = json.loads(capsys.readouterr().out)
    assert failure["errors"] == ["non-finite JSON value is not allowed: NaN"]
