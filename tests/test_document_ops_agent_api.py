from __future__ import annotations

import json

from fastapi.testclient import TestClient


def _create_client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_PROVIDER_GENERATION", "")
    monkeypatch.setenv("DECISIONDOC_PROVIDER_ATTACHMENT", "")
    monkeypatch.setenv("DECISIONDOC_PROVIDER_VISUAL", "")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.setenv("DECISIONDOC_API_KEYS", "test-api-key")
    monkeypatch.setenv("DECISIONDOC_OPS_KEY", "test-ops-key")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)

    from app.main import create_app

    return TestClient(create_app())


def _api_headers() -> dict[str, str]:
    return {"X-DecisionDoc-Api-Key": "test-api-key"}


def _ops_headers() -> dict[str, str]:
    return {"X-DecisionDoc-Ops-Key": "test-ops-key"}


def _write_signoff_record(tmp_path, filename: str, record: dict) -> None:
    signoff_dir = tmp_path / "tenants" / "system" / "trajectory_reviewer_signoffs"
    signoff_dir.mkdir(parents=True, exist_ok=True)
    (signoff_dir / filename).write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")


def test_document_ops_run_requires_api_key(tmp_path, monkeypatch) -> None:
    client = _create_client(tmp_path, monkeypatch)

    response = client.post(
        "/api/agent/document-ops/run",
        json={"task_type": "policy_planning_brief", "requirements": {"title": "인증 검증"}},
    )

    assert response.status_code == 401


def test_document_ops_run_can_capture_and_list_trajectory(tmp_path, monkeypatch) -> None:
    client = _create_client(tmp_path, monkeypatch)

    response = client.post(
        "/api/agent/document-ops/run",
        headers=_api_headers(),
        json={
            "task_type": "policy_planning_brief",
            "requirements": {
                "title": "보행자 안전 정책 기획 사업",
                "goal": "운영 가능한 정책 보고서 기획",
                "raw_attachment": "binary-like-data",
            },
            "source_references": [{"id": "accident-report"}],
            "capture_trajectory": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["skill_name"] == "policy-planning"
    assert body["trajectory_saved"] is True
    assert body["trajectory_id"].startswith("trj_")
    assert body["qa"]["hard_gate_pass"] is True

    listed = client.get("/api/agent/document-ops/trajectories", headers=_api_headers())
    assert listed.status_code == 200
    trajectories = listed.json()["trajectories"]
    assert len(trajectories) == 1
    assert trajectories[0]["trajectory_id"] == body["trajectory_id"]
    assert trajectories[0]["input"]["requirements"]["raw_attachment"] == "[redacted]"


def test_document_ops_trajectory_list_paginates_from_newest_with_filtered_total(tmp_path, monkeypatch) -> None:
    client = _create_client(tmp_path, monkeypatch)
    created_ids: list[str] = []
    for index in range(5):
        task_type = "decision_brief" if index < 4 else "evidence_gap_review"
        response = client.post(
            "/api/agent/document-ops/run",
            headers=_api_headers(),
            json={
                "task_type": task_type,
                "requirements": {"title": f"이력 페이지 검증 {index + 1}"},
                "capture_trajectory": True,
            },
        )
        assert response.status_code == 200
        created_ids.append(response.json()["trajectory_id"])

    for trajectory_id in (created_ids[0], created_ids[-1]):
        reviewed = client.post(
            f"/api/agent/document-ops/trajectories/{trajectory_id}/review",
            headers=_api_headers(),
            json={"accepted": True, "reviewer": "pagination-reviewer"},
        )
        assert reviewed.status_code == 200

    first = client.get(
        "/api/agent/document-ops/trajectories",
        headers=_api_headers(),
        params={"offset": 0, "limit": 2},
    )
    second = client.get(
        "/api/agent/document-ops/trajectories",
        headers=_api_headers(),
        params={"offset": 2, "limit": 2},
    )
    last = client.get(
        "/api/agent/document-ops/trajectories",
        headers=_api_headers(),
        params={"offset": 4, "limit": 2},
    )
    past_end = client.get(
        "/api/agent/document-ops/trajectories",
        headers=_api_headers(),
        params={"offset": 5, "limit": 2},
    )
    filtered = client.get(
        "/api/agent/document-ops/trajectories",
        headers=_api_headers(),
        params={"task_type": "decision_brief", "offset": 0, "limit": 2},
    )
    accepted = client.get(
        "/api/agent/document-ops/trajectories",
        headers=_api_headers(),
        params={"human_review_status": "accepted", "offset": 0, "limit": 2},
    )
    accepted_evidence = client.get(
        "/api/agent/document-ops/trajectories",
        headers=_api_headers(),
        params={
            "task_type": "evidence_gap_review",
            "human_review_status": "accepted",
            "offset": 0,
            "limit": 2,
        },
    )

    assert first.status_code == 200
    first_body = first.json()
    assert first_body["total"] == 5
    assert first_body["offset"] == 0
    assert first_body["limit"] == 2
    assert first_body["returned"] == 2
    assert first_body["has_more"] is True
    assert [item["trajectory_id"] for item in first_body["trajectories"]] == created_ids[3:]
    assert [item["trajectory_id"] for item in second.json()["trajectories"]] == created_ids[1:3]
    assert second.json()["has_more"] is True
    assert [item["trajectory_id"] for item in last.json()["trajectories"]] == created_ids[:1]
    assert last.json()["returned"] == 1
    assert last.json()["has_more"] is False
    assert past_end.json()["trajectories"] == []
    assert past_end.json()["total"] == 5
    assert past_end.json()["returned"] == 0
    assert past_end.json()["has_more"] is False
    assert filtered.json()["total"] == 4
    assert [item["trajectory_id"] for item in filtered.json()["trajectories"]] == created_ids[2:4]
    assert accepted.json()["total"] == 2
    assert [item["trajectory_id"] for item in accepted.json()["trajectories"]] == [created_ids[0], created_ids[-1]]
    assert accepted_evidence.json()["total"] == 1
    assert accepted_evidence.json()["trajectories"][0]["trajectory_id"] == created_ids[-1]

    invalid = client.get(
        "/api/agent/document-ops/trajectories",
        headers=_api_headers(),
        params={"offset": -1, "limit": 2},
    )
    assert invalid.status_code == 422


def test_document_ops_run_supports_develop_quality_improvement(tmp_path, monkeypatch) -> None:
    client = _create_client(tmp_path, monkeypatch)

    response = client.post(
        "/api/agent/document-ops/run",
        headers=_api_headers(),
        json={
            "task_type": "develop_quality_improvement",
            "requirements": {
                "title": "정책 보고서 품질 개선",
                "draft": "현재 초안은 근거와 승인 질문이 섞여 있어 대표 검토 전 정리가 필요합니다.",
                "goal": "검토 가능한 품질 개선본 작성",
            },
            "source_references": [{"id": "draft-review-note"}],
            "capture_trajectory": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["skill_name"] == "develop-document-improver"
    assert body["critique"]
    assert body["revision_tasks"]
    assert "개선안" in body["draft"]
    assert body["qa"]["hard_gate_pass"] is True
    assert body["trajectory_saved"] is True
    assert body["trajectory"]["critique"] == body["critique"]
    assert body["trajectory"]["revision_tasks"] == body["revision_tasks"]


def test_document_ops_run_returns_actionable_gate_issues(tmp_path, monkeypatch) -> None:
    client = _create_client(tmp_path, monkeypatch)

    response = client.post(
        "/api/agent/document-ops/run",
        headers=_api_headers(),
        json={
            "task_type": "evidence_gap_review",
            "requirements": {"title": "근거 미확인 초안"},
        },
    )

    assert response.status_code == 200
    issues = response.json()["qa"]["gate_issues"]
    evidence_issue = next(issue for issue in issues if issue["code"] == "evidence_gap:no_confirmed_sources")
    assert evidence_issue["affected_field"] == "evidence_status.source_references"
    assert "공식 출처" in evidence_issue["remediation_hint"]


def test_document_ops_review_requires_traceable_reviewer_identity(tmp_path, monkeypatch) -> None:
    client = _create_client(tmp_path, monkeypatch)
    created = client.post(
        "/api/agent/document-ops/run",
        headers=_api_headers(),
        json={
            "task_type": "decision_brief",
            "requirements": {"title": "검토자 식별 검증"},
            "source_references": [{"id": "review-source"}],
            "capture_trajectory": True,
        },
    ).json()

    response = client.post(
        f"/api/agent/document-ops/trajectories/{created['trajectory_id']}/review",
        headers=_api_headers(),
        json={"accepted": True},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "reviewer identity is required."
    listed = client.get("/api/agent/document-ops/trajectories", headers=_api_headers()).json()
    assert listed["trajectories"][0]["human_review_status"] == "pending"


def test_document_ops_review_and_export_accepted_trajectory(tmp_path, monkeypatch) -> None:
    client = _create_client(tmp_path, monkeypatch)
    created = client.post(
        "/api/agent/document-ops/run",
        headers=_api_headers(),
        json={
            "task_type": "decision_brief",
            "skill_name": "decision-brief-builder",
            "requirements": {
                "title": "대표 승인 브리프",
                "decision_needed": "정책 기획안을 기준본으로 승인할지 결정",
            },
            "source_references": [{"id": "brief-source"}],
            "capture_trajectory": True,
        },
    ).json()

    reviewed = client.post(
        f"/api/agent/document-ops/trajectories/{created['trajectory_id']}/review",
        headers=_api_headers(),
        json={
            "accepted": True,
            "reviewer": "pm",
            "notes": "학습용 승인",
            "quality_score": 0.91,
        },
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["human_review_status"] == "accepted"
    first_feedback = reviewed.json()["human_feedback"]
    repeated_review = client.post(
        f"/api/agent/document-ops/trajectories/{created['trajectory_id']}/review",
        headers=_api_headers(),
        json={
            "accepted": True,
            "reviewer": "pm",
            "notes": "학습용 승인",
            "quality_score": 0.91,
        },
    )
    assert repeated_review.status_code == 200
    assert repeated_review.json()["human_feedback"] == first_feedback

    stats = client.get("/api/agent/document-ops/trajectories/stats", headers=_api_headers())
    assert stats.status_code == 200
    assert stats.json()["accepted_records"] == 1

    blocked_export = client.post(
        "/api/agent/document-ops/trajectories/export",
        headers=_api_headers(),
        json={"min_records": 1},
    )
    assert blocked_export.status_code == 401

    blocked_preview = client.post(
        "/api/agent/document-ops/trajectories/export/preview",
        headers=_api_headers(),
        json={"min_records": 1},
    )
    assert blocked_preview.status_code == 401

    blocked_quality_report = client.post(
        "/api/agent/document-ops/trajectories/export/quality-report",
        headers=_api_headers(),
        json={"min_records": 1},
    )
    assert blocked_quality_report.status_code == 401

    provenance_less_export = client.post(
        "/api/agent/document-ops/trajectories/export",
        headers=_ops_headers(),
        json={"min_records": 1, "include_metadata": False},
    )
    assert provenance_less_export.status_code == 400
    assert provenance_less_export.json()["detail"] == "Reviewed SFT exports require provenance metadata."

    preview = client.post(
        "/api/agent/document-ops/trajectories/export/preview",
        headers=_ops_headers(),
        json={"min_records": 1, "task_type": "decision_brief", "sample_limit": 1},
    )
    assert preview.status_code == 200
    preview_body = preview.json()
    assert preview_body["dry_run"] is True
    assert preview_body["would_export"] is True
    assert preview_body["eligible_count"] == 1
    assert preview_body["estimated_jsonl_lines"] == 1
    assert preview_body["sample_records"][0]["trajectory_id"] == created["trajectory_id"]

    quality_report = client.post(
        "/api/agent/document-ops/trajectories/export/quality-report",
        headers=_ops_headers(),
        json={"min_records": 1, "task_type": "decision_brief", "sample_limit": 1},
    )
    assert quality_report.status_code == 200
    quality_body = quality_report.json()
    assert quality_body["report_type"] == "sft_export_candidate_quality"
    assert quality_body["eligible_count"] == 1
    assert quality_body["schema_valid_count"] == 1
    assert quality_body["schema_invalid_count"] == 0
    assert quality_body["role_sequence_summary"]["system,user,assistant"] == 1
    assert quality_body["evidence_coverage"]["records_with_source_references"] == 1
    assert quality_body["ready_for_export"] is True

    exported = client.post(
        "/api/agent/document-ops/trajectories/export",
        headers=_ops_headers(),
        json={"min_records": 1, "task_type": "decision_brief"},
    )
    assert exported.status_code == 200
    assert exported.json()["exported"] is True
    filename = exported.json()["filename"]
    assert filename.endswith(".jsonl")

    repeated_export = client.post(
        "/api/agent/document-ops/trajectories/export",
        headers=_ops_headers(),
        json={"min_records": 1, "task_type": "decision_brief"},
    )
    assert repeated_export.status_code == 200
    assert repeated_export.json()["filename"] == filename

    blocked_list = client.get(
        "/api/agent/document-ops/trajectories/exports",
        headers=_api_headers(),
    )
    assert blocked_list.status_code == 401

    exports = client.get(
        "/api/agent/document-ops/trajectories/exports",
        headers=_ops_headers(),
    )
    assert exports.status_code == 200
    exports_body = exports.json()
    assert exports_body["total"] == 1
    assert exports_body["exports"][0]["filename"] == filename
    assert exports_body["exports"][0]["record_count"] == 1
    assert exports_body["exports"][0]["exists"] is True
    assert exports_body["exports"][0]["size_bytes"] > 0
    assert len(exports_body["exports"][0]["export_fingerprint"]) == 64
    assert exports_body["exports"][0]["source_trajectory_ids"] == [created["trajectory_id"]]

    blocked_reviewed_list = client.get(
        "/api/agent/document-ops/trajectories/reviewed-sft-exports",
        headers=_api_headers(),
    )
    assert blocked_reviewed_list.status_code == 401

    reviewed_exports = client.get(
        "/api/agent/document-ops/trajectories/reviewed-sft-exports",
        headers=_ops_headers(),
    )
    assert reviewed_exports.status_code == 200
    reviewed_exports_body = reviewed_exports.json()
    assert reviewed_exports_body["reviewed_only"] is True
    assert reviewed_exports_body["total"] == 1
    assert reviewed_exports_body["exports"][0]["filename"] == filename
    assert reviewed_exports_body["exports"][0]["accepted_only"] is True

    downloaded = client.get(
        f"/api/agent/document-ops/trajectories/exports/{filename}",
        headers=_ops_headers(),
    )
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"].startswith("application/x-ndjson")
    assert f'filename="{filename}"' in downloaded.headers["content-disposition"]
    assert b'"messages"' in downloaded.content
    assert b"brief-source" in downloaded.content

    reviewed_downloaded = client.get(
        f"/api/agent/document-ops/trajectories/reviewed-sft-exports/{filename}/download",
        headers=_ops_headers(),
    )
    assert reviewed_downloaded.status_code == 200
    assert reviewed_downloaded.headers["content-type"].startswith("application/x-ndjson")
    assert f'filename="{filename}"' in reviewed_downloaded.headers["content-disposition"]
    assert reviewed_downloaded.content == downloaded.content

    file_quality_report = client.get(
        f"/api/agent/document-ops/trajectories/exports/{filename}/quality-report",
        headers=_ops_headers(),
    )
    assert file_quality_report.status_code == 200
    file_quality_body = file_quality_report.json()
    assert file_quality_body["report_type"] == "sft_export_file_quality"
    assert file_quality_body["filename"] == filename
    assert file_quality_body["schema_valid_count"] == 1
    assert file_quality_body["schema_invalid_count"] == 0
    assert file_quality_body["provenance_coverage"]["complete_records"] == 1
    assert file_quality_body["content_sha256_matches_metadata"] is True
    assert file_quality_body["source_trajectory_ids"] == [created["trajectory_id"]]
    assert file_quality_body["ready_for_training"] is True

    blocked_freeze_list = client.get(
        "/api/agent/document-ops/trajectories/freezes",
        headers=_api_headers(),
    )
    assert blocked_freeze_list.status_code == 401

    blocked_freeze = client.post(
        f"/api/agent/document-ops/trajectories/exports/{filename}/freeze",
        headers=_api_headers(),
        json={"reviewer": "pm"},
    )
    assert blocked_freeze.status_code == 401

    blocked_training_freeze = client.post(
        f"/api/agent/document-ops/trajectories/exports/{filename}/freeze",
        headers=_ops_headers(),
        json={"reviewer": "pm", "training_allowed": True},
    )
    assert blocked_training_freeze.status_code == 400

    frozen = client.post(
        f"/api/agent/document-ops/trajectories/exports/{filename}/freeze",
        headers=_ops_headers(),
        json={"reviewer": "pm", "notes": "dataset freeze only", "sample_limit": 1},
    )
    assert frozen.status_code == 200
    frozen_body = frozen.json()
    assert frozen_body["schema_version"] == "document_ops_dataset_freeze_v1"
    assert frozen_body["export"]["filename"] == filename
    assert frozen_body["export"]["record_count"] == 1
    assert len(frozen_body["export"]["sha256"]) == 64
    assert len(frozen_body["quality_report"]["sha256"]) == 64
    assert frozen_body["review_gate"]["reviewer"] == "pm"
    assert frozen_body["training_guard"]["training_allowed"] is False
    assert frozen_body["training_guard"]["training_started"] is False

    freeze_list = client.get(
        "/api/agent/document-ops/trajectories/freezes",
        headers=_ops_headers(),
    )
    assert freeze_list.status_code == 200
    freeze_list_body = freeze_list.json()
    assert freeze_list_body["total"] == 1
    assert freeze_list_body["freezes"][0]["manifest_id"] == frozen_body["manifest_id"]
    assert freeze_list_body["freezes"][0]["export_filename"] == filename
    assert freeze_list_body["freezes"][0]["training_allowed"] is False
    assert freeze_list_body["freezes"][0]["exists"] is True

    blocked_training_approval_list = client.get(
        "/api/agent/document-ops/trajectories/training-approvals",
        headers=_api_headers(),
    )
    assert blocked_training_approval_list.status_code == 401

    blocked_training_approval = client.post(
        f"/api/agent/document-ops/trajectories/freezes/{frozen_body['manifest_id']}/training-approval",
        headers=_api_headers(),
        json={"approver": "ml-owner", "eval_plan": {"suite": "document_ops_offline_eval"}},
    )
    assert blocked_training_approval.status_code == 401

    same_reviewer_approval = client.post(
        f"/api/agent/document-ops/trajectories/freezes/{frozen_body['manifest_id']}/training-approval",
        headers=_ops_headers(),
        json={"approver": "pm", "eval_plan": {"suite": "document_ops_offline_eval"}},
    )
    assert same_reviewer_approval.status_code == 400

    start_training_approval = client.post(
        f"/api/agent/document-ops/trajectories/freezes/{frozen_body['manifest_id']}/training-approval",
        headers=_ops_headers(),
        json={
            "approver": "ml-owner",
            "eval_plan": {"suite": "document_ops_offline_eval"},
            "start_training": True,
        },
    )
    assert start_training_approval.status_code == 400

    training_approval = client.post(
        f"/api/agent/document-ops/trajectories/freezes/{frozen_body['manifest_id']}/training-approval",
        headers=_ops_headers(),
        json={
            "approver": "ml-owner",
            "notes": "dry-run approval gate",
            "eval_plan": {
                "suite": "document_ops_offline_eval",
                "required_metrics": {"schema_valid_rate": 1.0},
                "source_document": "sensitive-eval-note",
            },
        },
    )
    assert training_approval.status_code == 200
    training_approval_body = training_approval.json()
    assert training_approval_body["schema_version"] == "document_ops_training_approval_v1"
    assert training_approval_body["manifest"]["manifest_id"] == frozen_body["manifest_id"]
    assert training_approval_body["approval_gate"]["approver"] == "ml-owner"
    assert training_approval_body["eval_plan"]["source_document"] == "[redacted]"
    assert training_approval_body["execution_guard"]["dry_run"] is True
    assert training_approval_body["execution_guard"]["provider_job_started"] is False
    assert training_approval_body["execution_guard"]["model_promotion_allowed"] is False

    training_approval_list = client.get(
        "/api/agent/document-ops/trajectories/training-approvals",
        headers=_ops_headers(),
    )
    assert training_approval_list.status_code == 200
    training_approval_list_body = training_approval_list.json()
    assert training_approval_list_body["total"] == 1
    assert training_approval_list_body["training_approvals"][0]["approval_id"] == training_approval_body["approval_id"]
    assert training_approval_list_body["training_approvals"][0]["provider_job_started"] is False
    assert training_approval_list_body["training_approvals"][0]["exists"] is True

    blocked_training_readiness = client.get(
        "/api/agent/document-ops/trajectories/training-readiness",
        headers=_api_headers(),
    )
    assert blocked_training_readiness.status_code == 401

    training_readiness = client.get(
        "/api/agent/document-ops/trajectories/training-readiness",
        headers=_ops_headers(),
    )
    assert training_readiness.status_code == 200
    readiness_body = training_readiness.json()
    assert readiness_body["report_type"] == "document_ops_training_readiness"
    assert readiness_body["read_only"] is True
    assert readiness_body["training_execution_allowed"] is False
    assert readiness_body["ready_for_training_execution"] is True
    assert readiness_body["status"] == "ready_for_training_decision"
    assert readiness_body["counts"]["reviewed_sft_exports"] == 1
    assert readiness_body["counts"]["dataset_freezes"] == 1
    assert readiness_body["counts"]["dry_run_training_approvals"] == 1
    assert readiness_body["latest_reviewed_export"]["filename"] == filename
    assert readiness_body["latest_dataset_freeze"]["manifest_id"] == frozen_body["manifest_id"]
    assert readiness_body["latest_training_approval"]["approval_id"] == training_approval_body["approval_id"]
    assert readiness_body["eval_plan_coverage"]["approvals_with_required_metrics"] == 1
    assert readiness_body["latest_export_quality"]["ready_for_training"] is True
    assert readiness_body["training_guard"]["provider_job_started_count"] == 0
    assert readiness_body["training_guard"]["model_promotion_allowed_count"] == 0
    assert readiness_body["training_guard"]["external_upload_started"] is False
    assert readiness_body["blockers"] == []
    assert readiness_body["recommendations"] == ["review_latest_freeze_and_approval_before_explicit_training_execution"]

    blocked_training_plan = client.get(
        "/api/agent/document-ops/trajectories/training-plan/preview",
        headers=_api_headers(),
    )
    assert blocked_training_plan.status_code == 401

    training_plan = client.get(
        "/api/agent/document-ops/trajectories/training-plan/preview?provider=openai&base_model=gpt-test-base",
        headers=_ops_headers(),
    )
    assert training_plan.status_code == 200
    training_plan_body = training_plan.json()
    assert training_plan_body["report_type"] == "document_ops_training_execution_plan_preview"
    assert training_plan_body["dry_run"] is True
    assert training_plan_body["preview_only"] is True
    assert training_plan_body["training_execution_allowed"] is False
    assert training_plan_body["provider_api_calls_allowed"] is False
    assert training_plan_body["external_upload_allowed"] is False
    assert training_plan_body["provider_job_started"] is False
    assert training_plan_body["model_promotion_allowed"] is False
    assert training_plan_body["status"] == "ready_for_manual_execution_planning"
    assert training_plan_body["job_spec"]["provider"] == "openai"
    assert training_plan_body["job_spec"]["base_model"] == "gpt-test-base"
    assert training_plan_body["job_spec"]["dataset"]["freeze_manifest_id"] == frozen_body["manifest_id"]
    assert training_plan_body["job_spec"]["dataset"]["export_filename"] == filename
    assert training_plan_body["job_spec"]["evaluation"]["suite"] == "document_ops_offline_eval"
    assert training_plan_body["job_spec"]["execution_steps"][1]["step"] == "upload_dataset"
    assert training_plan_body["job_spec"]["execution_steps"][1]["status"] == "not_started"

    blocked_execution_request_list = client.get(
        "/api/agent/document-ops/trajectories/training-execution-requests",
        headers=_api_headers(),
    )
    assert blocked_execution_request_list.status_code == 401

    blocked_execution_request = client.post(
        "/api/agent/document-ops/trajectories/training-execution-requests",
        headers=_api_headers(),
        json={"requester": "ops-owner"},
    )
    assert blocked_execution_request.status_code == 401

    same_person_execution_request = client.post(
        "/api/agent/document-ops/trajectories/training-execution-requests",
        headers=_ops_headers(),
        json={"requester": "ml-owner"},
    )
    assert same_person_execution_request.status_code == 400

    start_training_execution_request = client.post(
        "/api/agent/document-ops/trajectories/training-execution-requests",
        headers=_ops_headers(),
        json={"requester": "ops-owner", "start_training": True},
    )
    assert start_training_execution_request.status_code == 400

    training_execution_request = client.post(
        "/api/agent/document-ops/trajectories/training-execution-requests",
        headers=_ops_headers(),
        json={
            "requester": "ops-owner",
            "provider": "openai",
            "base_model": "gpt-test-base",
            "notes": "record only",
        },
    )
    assert training_execution_request.status_code == 200
    training_execution_request_body = training_execution_request.json()
    assert training_execution_request_body["schema_version"] == "document_ops_training_execution_request_v1"
    assert training_execution_request_body["plan_preview"]["dataset"]["freeze_manifest_id"] == frozen_body["manifest_id"]
    assert training_execution_request_body["plan_preview"]["dataset"]["export_filename"] == filename
    assert training_execution_request_body["request_gate"]["requester"] == "ops-owner"
    assert training_execution_request_body["request_gate"]["prior_training_approver"] == "ml-owner"
    assert training_execution_request_body["two_person_guard"]["satisfied"] is True
    assert training_execution_request_body["execution_guard"]["training_execution_allowed"] is False
    assert training_execution_request_body["execution_guard"]["external_upload_started"] is False
    assert training_execution_request_body["execution_guard"]["provider_api_calls_allowed"] is False
    assert training_execution_request_body["execution_guard"]["provider_job_started"] is False
    assert training_execution_request_body["execution_guard"]["model_promotion_allowed"] is False

    training_execution_request_list = client.get(
        "/api/agent/document-ops/trajectories/training-execution-requests",
        headers=_ops_headers(),
    )
    assert training_execution_request_list.status_code == 200
    request_list_body = training_execution_request_list.json()
    assert request_list_body["total"] == 1
    assert request_list_body["training_execution_requests"][0]["request_id"] == training_execution_request_body["request_id"]
    assert request_list_body["training_execution_requests"][0]["two_person_guard_satisfied"] is True
    assert request_list_body["training_execution_requests"][0]["training_execution_allowed"] is False
    assert request_list_body["training_execution_requests"][0]["provider_job_started"] is False
    assert request_list_body["training_execution_requests"][0]["external_upload_started"] is False

    blocked_audit_checklist = client.get(
        "/api/agent/document-ops/trajectories/training-audit/checklist",
        headers=_api_headers(),
    )
    assert blocked_audit_checklist.status_code == 401

    audit_checklist = client.get(
        "/api/agent/document-ops/trajectories/training-audit/checklist?provider=openai&base_model=gpt-test-base",
        headers=_ops_headers(),
    )
    assert audit_checklist.status_code == 200
    audit_checklist_body = audit_checklist.json()
    assert audit_checklist_body["report_type"] == "document_ops_training_pre_execution_audit_checklist"
    assert audit_checklist_body["status"] == "ready_for_human_pre_execution_review"
    assert audit_checklist_body["training_execution_allowed"] is False
    assert audit_checklist_body["provider_api_calls_allowed"] is False
    assert audit_checklist_body["external_upload_allowed"] is False
    assert audit_checklist_body["provider_job_started"] is False
    assert audit_checklist_body["model_promotion_allowed"] is False
    assert audit_checklist_body["latest_training_execution_request"]["request_id"] == training_execution_request_body["request_id"]
    assert audit_checklist_body["human_review_packet"]["dataset"]["freeze_manifest_id"] == frozen_body["manifest_id"]

    blocked_audit_export = client.post(
        "/api/agent/document-ops/trajectories/training-audit/export",
        headers=_api_headers(),
        json={"auditor": "compliance-owner"},
    )
    assert blocked_audit_export.status_code == 401

    same_requester_audit = client.post(
        "/api/agent/document-ops/trajectories/training-audit/export",
        headers=_ops_headers(),
        json={"auditor": "ops-owner"},
    )
    assert same_requester_audit.status_code == 400

    start_training_audit = client.post(
        "/api/agent/document-ops/trajectories/training-audit/export",
        headers=_ops_headers(),
        json={"auditor": "compliance-owner", "start_training": True},
    )
    assert start_training_audit.status_code == 400

    audit_export = client.post(
        "/api/agent/document-ops/trajectories/training-audit/export",
        headers=_ops_headers(),
        json={
            "auditor": "compliance-owner",
            "provider": "openai",
            "base_model": "gpt-test-base",
            "notes": "final packet only",
        },
    )
    assert audit_export.status_code == 200
    audit_export_body = audit_export.json()
    assert audit_export_body["schema_version"] == "document_ops_training_pre_execution_audit_v1"
    assert audit_export_body["audit_gate"]["auditor"] == "compliance-owner"
    assert audit_export_body["audit_gate"]["requester"] == "ops-owner"
    assert audit_export_body["audit_gate"]["prior_training_approver"] == "ml-owner"
    assert audit_export_body["audit_gate"]["separation_of_duties_satisfied"] is True
    assert audit_export_body["execution_guard"]["training_execution_allowed"] is False
    assert audit_export_body["execution_guard"]["external_upload_started"] is False
    assert audit_export_body["execution_guard"]["provider_api_calls_allowed"] is False
    assert audit_export_body["execution_guard"]["provider_job_started"] is False
    assert audit_export_body["execution_guard"]["model_promotion_allowed"] is False

    audit_list = client.get(
        "/api/agent/document-ops/trajectories/training-audits",
        headers=_ops_headers(),
    )
    assert audit_list.status_code == 200
    audit_list_body = audit_list.json()
    assert audit_list_body["total"] == 1
    audit_file = audit_list_body["training_pre_execution_audits"][0]["audit_file"]
    assert audit_list_body["training_pre_execution_audits"][0]["audit_id"] == audit_export_body["audit_id"]
    assert audit_list_body["training_pre_execution_audits"][0]["training_execution_allowed"] is False
    assert audit_list_body["training_pre_execution_audits"][0]["provider_job_started"] is False
    assert audit_list_body["training_pre_execution_audits"][0]["external_upload_started"] is False

    downloaded_audit = client.get(
        f"/api/agent/document-ops/trajectories/training-audits/{audit_file}/download",
        headers=_ops_headers(),
    )
    assert downloaded_audit.status_code == 200
    assert downloaded_audit.headers["content-type"].startswith("application/json")
    assert audit_export_body["audit_id"].encode() in downloaded_audit.content

    blocked_governance_summary = client.get(
        "/api/agent/document-ops/trajectories/training-governance/summary",
        headers=_api_headers(),
    )
    assert blocked_governance_summary.status_code == 401

    governance_summary = client.get(
        "/api/agent/document-ops/trajectories/training-governance/summary?provider=openai&base_model=gpt-test-base",
        headers=_ops_headers(),
    )
    assert governance_summary.status_code == 200
    governance_body = governance_summary.json()
    assert governance_body["report_type"] == "document_ops_training_governance_dashboard_summary"
    assert governance_body["status"] == "governance_ready_for_human_review"
    assert governance_body["read_only"] is True
    assert governance_body["training_execution_allowed"] is False
    assert governance_body["provider_api_calls_allowed"] is False
    assert governance_body["external_upload_allowed"] is False
    assert governance_body["provider_job_started"] is False
    assert governance_body["model_promotion_allowed"] is False
    assert governance_body["counts"]["reviewed_sft_exports"] == 1
    assert governance_body["counts"]["dataset_freezes"] == 1
    assert governance_body["counts"]["dry_run_training_approvals"] == 1
    assert governance_body["counts"]["training_execution_requests"] == 1
    assert governance_body["counts"]["pre_execution_audit_exports"] == 1
    assert governance_body["latest"]["reviewed_sft_export"]["filename"] == filename
    assert governance_body["latest"]["dataset_freeze"]["manifest_id"] == frozen_body["manifest_id"]
    assert governance_body["latest"]["training_execution_request"]["request_id"] == training_execution_request_body["request_id"]
    assert governance_body["latest"]["pre_execution_audit"]["audit_id"] == audit_export_body["audit_id"]
    assert governance_body["no_side_effects"] is True
    assert all(value == 0 for value in governance_body["guard_counts"].values())
    assert governance_body["blockers"] == []

    blocked_adapter_contract = client.get(
        "/api/agent/document-ops/trajectories/training-provider-adapter/contract",
        headers=_api_headers(),
    )
    assert blocked_adapter_contract.status_code == 401

    adapter_contract = client.get(
        "/api/agent/document-ops/trajectories/training-provider-adapter/contract?provider=openai&base_model=gpt-test-base",
        headers=_ops_headers(),
    )
    assert adapter_contract.status_code == 200
    adapter_body = adapter_contract.json()
    assert adapter_body["report_type"] == "document_ops_training_provider_adapter_contract"
    assert adapter_body["provider"] == "openai"
    assert adapter_body["base_model"] == "gpt-test-base"
    assert adapter_body["adapter_status"] == "stub_only"
    assert adapter_body["execution_enabled"] is False
    assert adapter_body["training_execution_allowed"] is False
    assert adapter_body["provider_api_calls_allowed"] is False
    assert adapter_body["external_upload_allowed"] is False
    assert adapter_body["provider_job_started"] is False
    assert adapter_body["model_promotion_allowed"] is False
    assert "create_training_job" in adapter_body["adapter_contract"]["required_methods"]
    assert "upload_dataset" in adapter_body["adapter_contract"]["forbidden_in_stub"]

    blocked_rehearsal = client.get(
        "/api/agent/document-ops/trajectories/training-provider-adapter/rehearsal",
        headers=_api_headers(),
    )
    assert blocked_rehearsal.status_code == 401

    rehearsal = client.get(
        "/api/agent/document-ops/trajectories/training-provider-adapter/rehearsal?provider=openai&base_model=gpt-test-base",
        headers=_ops_headers(),
    )
    assert rehearsal.status_code == 200
    rehearsal_body = rehearsal.json()
    assert rehearsal_body["report_type"] == "document_ops_training_provider_execution_rehearsal"
    assert rehearsal_body["status"] == "rehearsal_ready"
    assert rehearsal_body["dry_run"] is True
    assert rehearsal_body["rehearsal_only"] is True
    assert rehearsal_body["training_execution_allowed"] is False
    assert rehearsal_body["provider_api_calls_allowed"] is False
    assert rehearsal_body["external_upload_allowed"] is False
    assert rehearsal_body["provider_job_started"] is False
    assert rehearsal_body["model_promotion_allowed"] is False
    assert rehearsal_body["artifact_references"]["dataset_freeze"]["manifest_id"] == frozen_body["manifest_id"]
    assert rehearsal_body["artifact_references"]["pre_execution_audit"]["audit_id"] == audit_export_body["audit_id"]
    assert all(item["side_effect"] is False for item in rehearsal_body["rehearsal_steps"])
    assert "create_provider_fine_tune_job" in {item["step"] for item in rehearsal_body["rehearsal_steps"]}

    invalid_download = client.get(
        "/api/agent/document-ops/trajectories/exports/bad.txt",
        headers=_ops_headers(),
    )
    assert invalid_download.status_code == 400

    invalid_reviewed_download = client.get(
        "/api/agent/document-ops/trajectories/reviewed-sft-exports/bad.txt/download",
        headers=_ops_headers(),
    )
    assert invalid_reviewed_download.status_code == 400

    missing_download = client.get(
        "/api/agent/document-ops/trajectories/exports/sft_decision_brief_20260507T000000.jsonl",
        headers=_ops_headers(),
    )
    assert missing_download.status_code == 404

    missing_reviewed_download = client.get(
        "/api/agent/document-ops/trajectories/reviewed-sft-exports/sft_decision_brief_20260507T000000.jsonl/download",
        headers=_ops_headers(),
    )
    assert missing_reviewed_download.status_code == 404


def test_document_ops_reviewer_signoff_summary_is_ops_key_read_only(tmp_path, monkeypatch) -> None:
    client = _create_client(tmp_path, monkeypatch)
    template_path = "tests/fixtures/document_ops/signoff_record_template.json"
    template = json.load(open(template_path, encoding="utf-8"))

    pending = json.loads(json.dumps(template))
    pending["report_type"] = "document_ops_phase25_pending_manual_reviewer_signoff_record_fixture"
    pending["status"] = "pending_manual_signoff"
    pending["signoff_record_id"] = "dsr_phase25pending"
    pending["created_at"] = "2026-05-08T12:00:00+09:00"
    _write_signoff_record(tmp_path, "phase25_pending_signoff.json", pending)

    completed = json.loads(json.dumps(template))
    completed["report_type"] = "document_ops_phase25_completed_manual_reviewer_signoff_record_fixture"
    completed["status"] = "manual_signoff_complete"
    completed["signoff_record_id"] = "dsr_phase25done"
    completed["created_at"] = "2026-05-08T12:10:00+09:00"
    completed["signoff_boundary"]["actual_reviewer_approval_recorded"] = True
    for key in completed["completion_rule"]:
        completed["completion_rule"][key] = True
    for reviewer in completed["required_reviewers"]:
        reviewer["reviewer_name"] = f"{reviewer['reviewer_role']} name"
        reviewer["reviewer_title_or_team"] = "DocumentOps governance review"
        reviewer["reviewed_at"] = "2026-05-08T12:15:00+09:00"
        reviewer["decision"] = "sign_off_ready_for_human_review"
        reviewer["notes"] = "Completed human review while preserving no-training boundary."
        for ack in reviewer["required_acknowledgements"]:
            reviewer["required_acknowledgements"][ack] = True
    _write_signoff_record(tmp_path, "phase25_completed_signoff.json", completed)

    blocked_summary = client.get(
        "/api/agent/document-ops/trajectories/reviewer-signoff/summary",
        headers=_api_headers(),
    )
    assert blocked_summary.status_code == 401

    blocked_download = client.get(
        "/api/agent/document-ops/trajectories/reviewer-signoff/summary/download",
        headers=_api_headers(),
    )
    assert blocked_download.status_code == 401

    summary = client.get(
        "/api/agent/document-ops/trajectories/reviewer-signoff/summary",
        headers=_ops_headers(),
    )
    assert summary.status_code == 200
    body = summary.json()
    records = {item["signoff_record_id"]: item for item in body["records"]}

    assert body["report_type"] == "document_ops_phase25_signoff_summary_endpoint"
    assert body["read_only"] is True
    assert body["record_directory_exists"] is True
    assert body["record_count"] == 2
    assert body["overall_status"] == "pending_manual_signoff_no_training_authorization"
    assert body["training_execution_allowed"] is False
    assert body["provider_api_calls_allowed"] is False
    assert body["external_upload_allowed"] is False
    assert body["provider_job_started"] is False
    assert body["model_promotion_allowed"] is False
    assert body["aggregate"]["completed_record_count"] == 1
    assert body["aggregate"]["pending_record_count"] == 1
    assert body["aggregate"]["boundary_violation_count"] == 0
    assert body["aggregate"]["all_protected_training_flags_false"] is True
    assert body["aggregate"]["training_execution_authorized"] is False
    assert body["aggregate"]["external_dataset_upload_authorized"] is False
    assert body["aggregate"]["provider_fine_tune_api_call_authorized"] is False
    assert body["aggregate"]["provider_job_creation_authorized"] is False
    assert body["aggregate"]["model_promotion_authorized"] is False
    assert all(value is False for value in body["side_effect_boundary"].values())

    assert records["dsr_phase25pending"]["filename"] == "phase25_pending_signoff.json"
    assert records["dsr_phase25pending"]["record_status"] == "pending_manual_signoff_no_training_authorization"
    assert records["dsr_phase25pending"]["reviewers_complete_count"] == 0
    assert records["dsr_phase25pending"]["pending_reviewer_count"] == 4
    assert records["dsr_phase25pending"]["completed_validation"]["valid"] is False
    assert records["dsr_phase25done"]["record_status"] == "manual_signoff_complete_no_training_authorization"
    assert records["dsr_phase25done"]["reviewers_complete_count"] == 4
    assert records["dsr_phase25done"]["pending_reviewer_count"] == 0
    assert records["dsr_phase25done"]["completed_validation"]["valid"] is True
    assert records["dsr_phase25done"]["boundary"]["actual_reviewer_approval_recorded"] is True
    assert records["dsr_phase25done"]["boundary"]["training_execution_authorized"] is False
    assert records["dsr_phase25done"]["boundary"]["provider_fine_tune_api_call_authorized"] is False
    assert all(item["complete"] is True for item in records["dsr_phase25done"]["reviewers"])

    downloaded = client.get(
        "/api/agent/document-ops/trajectories/reviewer-signoff/summary/download?limit=50",
        headers=_ops_headers(),
    )
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"].startswith("application/json")
    assert "attachment" in downloaded.headers["content-disposition"]
    assert "reviewer_signoff_summary_system_" in downloaded.headers["content-disposition"]
    assert downloaded.headers["content-disposition"].endswith('.json"')

    downloaded_body = downloaded.json()
    assert downloaded_body["report_type"] == "document_ops_phase27_reviewer_signoff_summary_export"
    assert downloaded_body["tenant_id"] == "system"
    assert downloaded_body["read_only"] is True
    assert downloaded_body["export_format"] == "json"
    assert downloaded_body["server_file_written"] is False
    assert downloaded_body["summary"]["record_count"] == 2
    assert downloaded_body["summary"]["overall_status"] == "pending_manual_signoff_no_training_authorization"
    assert all(value is False for value in downloaded_body["guard_flags"].values())
    assert all(value is False for value in downloaded_body["side_effect_boundary"].values())


def test_document_ops_unknown_task_returns_400(tmp_path, monkeypatch) -> None:
    client = _create_client(tmp_path, monkeypatch)

    response = client.post(
        "/api/agent/document-ops/run",
        headers=_api_headers(),
        json={"task_type": "unknown_task", "requirements": {"title": "Unknown"}},
    )

    assert response.status_code == 400
