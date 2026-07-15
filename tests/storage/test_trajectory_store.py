import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from app.storage.trajectory_store import TrajectoryReviewConflictError, TrajectoryStore


def _sample_trajectory(trajectory_id: str = "trj_001") -> dict:
    return {
        "trajectory_id": trajectory_id,
        "task_type": "policy_planning_brief",
        "skill": {"name": "policy-planning", "version": "0.1.0"},
        "provider": "mock",
        "input": {
            "requirements": {
                "title": "보행자 안전 정책 기획 사업",
                "raw_attachment": "binary-like-data",
                "notes": "검토 메모",
            },
            "source_references": [{"id": "source-1"}],
        },
        "plan": ["승인 질문 분리", "근거 상태 정리"],
        "critique": ["승인 질문이 앞부분에 더 명확해야 함"],
        "revision_tasks": ["근거 상태와 운영 리스크를 분리"],
        "draft_output": "정책 기획 초안",
        "evidence_status": {"confirmed": ["source-1"], "assumptions": [], "gaps": [], "source_references": ["source-1"]},
        "qa": {"hard_gate_pass": True, "warnings": []},
    }


def _create_training_approval_chain(
    store: TrajectoryStore,
    trajectory_id: str,
) -> tuple[Path, dict, dict]:
    store.save(_sample_trajectory(trajectory_id), tenant_id="system")
    store.mark_reviewed(
        trajectory_id,
        tenant_id="system",
        accepted=True,
        reviewer="pm",
        quality_score=0.95,
    )
    export_path = store.export_sft_messages(tenant_id="system", min_records=1)
    assert export_path is not None
    manifest = store.freeze_sft_export(
        Path(export_path).name,
        tenant_id="system",
        reviewer="dataset-owner",
    )
    assert manifest is not None
    approval = store.approve_training_from_freeze(
        manifest["manifest_id"],
        tenant_id="system",
        approver="ml-owner",
        eval_plan={
            "suite": "document_ops_offline_eval",
            "required_metrics": {"schema_valid_rate": 1.0},
        },
    )
    assert approval is not None
    return Path(export_path), manifest, approval


def test_save_stores_tenant_scoped_redacted_jsonl(tmp_path: Path) -> None:
    store = TrajectoryStore(tmp_path)

    trajectory_id = store.save(_sample_trajectory(), tenant_id="alpha")

    assert trajectory_id == "trj_001"
    records = store.get_records(tenant_id="alpha")
    assert len(records) == 1
    assert records[0]["tenant_id"] == "alpha"
    assert records[0]["input"]["requirements"]["raw_attachment"] == "[redacted]"
    assert store.get_record("trj_001", tenant_id="alpha") == records[0]
    assert store.get_record("trj_001", tenant_id="beta") is None
    assert store.get_record("missing", tenant_id="alpha") is None
    assert store.get_records(tenant_id="beta") == []


def test_save_rejects_explicit_foreign_tenant_ownership(tmp_path: Path) -> None:
    store = TrajectoryStore(tmp_path)
    trajectory = _sample_trajectory("trj_foreign")
    trajectory["tenant_id"] = "beta"

    with pytest.raises(ValueError, match="does not match"):
        store.save(trajectory, tenant_id="alpha")

    assert store.get_records(tenant_id="alpha") == []


@pytest.mark.parametrize(
    "tenant_id",
    ["", " ", " alpha", "alpha ", ".", "..", "../beta", "alpha/beta", "alpha\\beta", "alpha\x00beta"],
)
def test_trajectory_store_rejects_unsafe_tenant_path_components(tmp_path: Path, tenant_id: str) -> None:
    store = TrajectoryStore(tmp_path)

    with pytest.raises(ValueError, match="Invalid tenant_id"):
        store.get_records(tenant_id=tenant_id)


def test_save_deduplicates_by_trajectory_id(tmp_path: Path) -> None:
    store = TrajectoryStore(tmp_path)

    store.save(_sample_trajectory("trj_dup"), tenant_id="system")
    store.save(_sample_trajectory("trj_dup"), tenant_id="system")

    assert len(store.get_records(tenant_id="system")) == 1


def test_independent_store_instances_serialize_concurrent_saves(tmp_path: Path) -> None:
    def save_one(index: int) -> str:
        store = TrajectoryStore(tmp_path)
        return store.save(_sample_trajectory(f"trj_concurrent_{index}"), tenant_id="alpha")

    with ThreadPoolExecutor(max_workers=8) as executor:
        trajectory_ids = list(executor.map(save_one, range(40)))

    records = TrajectoryStore(tmp_path).get_records(tenant_id="alpha")
    assert len(trajectory_ids) == 40
    assert {record["trajectory_id"] for record in records} == set(trajectory_ids)


def test_foreign_trajectory_drift_is_hidden_and_preserved_during_review(tmp_path: Path) -> None:
    store = TrajectoryStore(tmp_path)
    store.save(_sample_trajectory("trj_owned"), tenant_id="alpha")
    path = store._jsonl_path("alpha")
    foreign = _sample_trajectory("trj_foreign")
    foreign["tenant_id"] = "beta"
    path.write_text(
        path.read_text(encoding="utf-8") + json.dumps(foreign, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    assert [record["trajectory_id"] for record in store.get_records(tenant_id="alpha")] == ["trj_owned"]
    assert store.get_record("trj_foreign", tenant_id="alpha") is None
    assert store.get_stats(tenant_id="alpha")["total_records"] == 1

    reviewed = store.mark_reviewed(
        "trj_owned",
        tenant_id="alpha",
        accepted=True,
        reviewer="pm",
    )

    assert reviewed is not None
    raw_records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    preserved = next(record for record in raw_records if record["trajectory_id"] == "trj_foreign")
    assert preserved == foreign


def test_duplicate_trajectory_ids_fail_closed_across_declared_owners(tmp_path: Path) -> None:
    store = TrajectoryStore(tmp_path)
    store.save(_sample_trajectory("trj_duplicate_owner"), tenant_id="alpha")
    path = store._jsonl_path("alpha")
    foreign = _sample_trajectory("trj_duplicate_owner")
    foreign["tenant_id"] = "beta"
    path.write_text(
        path.read_text(encoding="utf-8") + json.dumps(foreign, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    assert store.get_records(tenant_id="alpha") == []
    assert store.get_record("trj_duplicate_owner", tenant_id="alpha") is None
    assert store.mark_reviewed(
        "trj_duplicate_owner",
        tenant_id="alpha",
        accepted=True,
        reviewer="pm",
    ) is None
    assert store.get_stats(tenant_id="alpha")["total_records"] == 0


def test_get_record_page_searches_filters_and_paginates_in_requested_order(tmp_path: Path) -> None:
    store = TrajectoryStore(tmp_path)
    for index in range(1, 6):
        trajectory = _sample_trajectory(f"trj_{index}")
        trajectory["request_id"] = f"req-{index}"
        trajectory["input"]["requirements"]["title"] = f"검토 기록 {index}"
        trajectory["task_type"] = "decision_brief" if index < 5 else "evidence_gap_review"
        store.save(trajectory, tenant_id="system")
    store.mark_reviewed(
        "trj_1",
        tenant_id="system",
        accepted=True,
        reviewer="oldest-reviewer",
        quality_score=0.91,
    )
    other_tenant = _sample_trajectory("trj_other_tenant")
    other_tenant["input"]["requirements"]["title"] = "검토 기록 2"
    store.save(other_tenant, tenant_id="other")

    first_page, total = store.get_record_page(tenant_id="system", offset=0, limit=2)
    second_page, _ = store.get_record_page(tenant_id="system", offset=2, limit=2)
    last_page, _ = store.get_record_page(tenant_id="system", offset=4, limit=2)
    filtered_page, filtered_total = store.get_record_page(
        tenant_id="system",
        task_type="decision_brief",
        offset=0,
        limit=2,
    )
    oldest_first, _ = store.get_record_page(tenant_id="system", order="oldest", offset=0, limit=2)
    oldest_second, _ = store.get_record_page(tenant_id="system", order="oldest", offset=2, limit=2)
    title_match, title_total = store.get_record_page(tenant_id="system", query="검토 기록 2")
    request_match, _ = store.get_record_page(tenant_id="system", query="REQ-3")
    reviewer_match, _ = store.get_record_page(tenant_id="system", query="OLDEST-REVIEWER")
    trajectory_match, _ = store.get_record_page(tenant_id="system", query="TRJ_4")
    task_match, _ = store.get_record_page(tenant_id="system", query="EVIDENCE_GAP_REVIEW")
    skill_match, _ = store.get_record_page(tenant_id="system", query="POLICY-PLANNING")
    provider_match, _ = store.get_record_page(tenant_id="system", query="MOCK")

    assert total == 5
    assert [item["trajectory_id"] for item in first_page] == ["trj_4", "trj_5"]
    assert [item["trajectory_id"] for item in second_page] == ["trj_2", "trj_3"]
    assert [item["trajectory_id"] for item in last_page] == ["trj_1"]
    assert filtered_total == 4
    assert [item["trajectory_id"] for item in filtered_page] == ["trj_3", "trj_4"]
    assert [item["trajectory_id"] for item in oldest_first] == ["trj_1", "trj_2"]
    assert [item["trajectory_id"] for item in oldest_second] == ["trj_3", "trj_4"]
    assert title_total == 1
    assert [item["trajectory_id"] for item in title_match] == ["trj_2"]
    assert [item["trajectory_id"] for item in request_match] == ["trj_3"]
    assert [item["trajectory_id"] for item in reviewer_match] == ["trj_1"]
    assert [item["trajectory_id"] for item in trajectory_match] == ["trj_4"]
    assert [item["trajectory_id"] for item in task_match] == ["trj_5"]
    assert len(skill_match) == 5
    assert len(provider_match) == 5
    with pytest.raises(ValueError, match="order must be"):
        store.get_record_page(tenant_id="system", order="unsupported")


def test_mark_reviewed_updates_human_feedback_and_stats(tmp_path: Path) -> None:
    store = TrajectoryStore(tmp_path)
    store.save(_sample_trajectory("trj_review"), tenant_id="system")

    updated = store.mark_reviewed(
        "trj_review",
        tenant_id="system",
        accepted=True,
        reviewer="pm",
        notes="승인본으로 학습 가능",
        quality_score=0.92,
    )

    assert updated is not None
    assert updated["human_review_status"] == "accepted"
    assert updated["human_feedback"]["quality_score"] == 0.92
    assert updated["human_feedback"]["review_version"] == 1
    stats = store.get_stats(tenant_id="system")
    assert stats["accepted_records"] == 1
    assert stats["pending_records"] == 0
    assert stats["per_task_count"]["policy_planning_brief"] == 1


def test_mark_reviewed_is_idempotent_and_preserves_changed_review_history(tmp_path: Path) -> None:
    store = TrajectoryStore(tmp_path)
    store.save(_sample_trajectory("trj_review_history"), tenant_id="system")

    first = store.mark_reviewed(
        "trj_review_history",
        tenant_id="system",
        accepted=True,
        expected_review_version=0,
        reviewer=" pm ",
        notes=" 승인 ",
        quality_score=0.92,
        metadata={"source_document": "sensitive", "review_round": 1},
    )
    repeated = store.mark_reviewed(
        "trj_review_history",
        tenant_id="system",
        accepted=True,
        expected_review_version=0,
        reviewer="pm",
        notes="승인",
        quality_score=0.92,
        metadata={"source_document": "sensitive", "review_round": 1},
    )

    assert first is not None
    assert repeated is not None
    assert repeated["human_feedback"] == first["human_feedback"]
    assert "human_review_history" not in repeated
    assert repeated["human_feedback"]["metadata"]["source_document"] == "[redacted]"

    with pytest.raises(TrajectoryReviewConflictError, match="expected version 0, current version 1"):
        store.mark_reviewed(
            "trj_review_history",
            tenant_id="system",
            accepted=False,
            expected_review_version=0,
            reviewer="qa-owner",
            notes="근거 보강 필요",
            quality_score=0.61,
        )

    changed = store.mark_reviewed(
        "trj_review_history",
        tenant_id="system",
        accepted=False,
        expected_review_version=1,
        reviewer="qa-owner",
        notes="근거 보강 필요",
        quality_score=0.61,
    )

    assert changed is not None
    assert changed["human_review_status"] == "rejected"
    assert changed["human_feedback"]["review_version"] == 2
    assert changed["human_review_history"] == [first["human_feedback"]]


def test_mark_reviewed_rejects_untraceable_input_without_mutating_record(tmp_path: Path) -> None:
    store = TrajectoryStore(tmp_path)
    store.save(_sample_trajectory("trj_invalid_review"), tenant_id="alpha")

    with pytest.raises(ValueError, match="reviewer identity is required"):
        store.mark_reviewed("trj_invalid_review", tenant_id="alpha", accepted=True, reviewer="anonymous")
    with pytest.raises(ValueError, match="quality_score must be between 0 and 1"):
        store.mark_reviewed("trj_invalid_review", tenant_id="alpha", accepted=True, reviewer="pm", quality_score=1.1)
    with pytest.raises(ValueError, match="JSON-compatible"):
        store.mark_reviewed(
            "trj_invalid_review",
            tenant_id="alpha",
            accepted=True,
            reviewer="pm",
            metadata={"labels": {"not-json"}},
        )

    assert store.mark_reviewed("trj_invalid_review", tenant_id="beta", accepted=True, reviewer="pm") is None
    record = store.get_records(tenant_id="alpha")[0]
    assert record["human_review_status"] == "pending"
    assert record["human_feedback"] == {"accepted": False}


def test_export_sft_messages_writes_only_accepted_records(tmp_path: Path) -> None:
    store = TrajectoryStore(tmp_path)
    store.save(_sample_trajectory("trj_accept"), tenant_id="system")
    store.save(_sample_trajectory("trj_pending"), tenant_id="system")
    store.save(_sample_trajectory("trj_rejected"), tenant_id="system")
    store.mark_reviewed("trj_accept", tenant_id="system", accepted=True, reviewer="pm", quality_score=0.95)
    store.mark_reviewed("trj_rejected", tenant_id="system", accepted=False, reviewer="pm", quality_score=0.4)

    export_path = store.export_sft_messages(tenant_id="system", min_records=1)

    assert export_path is not None
    path = Path(export_path)
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert [message["role"] for message in record["messages"]] == ["system", "user", "assistant"]
    assert record["metadata"]["trajectory_id"] == "trj_accept"
    assert record["metadata"]["reviewer"] == "pm"
    assert record["metadata"]["review_version"] == 1
    assert record["metadata"]["reviewed_at"]
    assistant_payload = json.loads(record["messages"][2]["content"])
    assert assistant_payload["draft"] == "정책 기획 초안"
    assert assistant_payload["critique"] == ["승인 질문이 앞부분에 더 명확해야 함"]
    assert assistant_payload["revision_tasks"] == ["근거 상태와 운영 리스크를 분리"]
    assert "raw_attachment" in record["messages"][1]["content"]
    assert "binary-like-data" not in record["messages"][1]["content"]
    assert store.get_stats(tenant_id="system")["export_count"] == 1

    exports = store.list_sft_exports(tenant_id="system")
    assert len(exports) == 1
    assert exports[0]["filename"] == path.name
    assert exports[0]["exists"] is True
    assert exports[0]["record_count"] == 1
    assert exports[0]["size_bytes"] > 0
    assert store.get_sft_export_path(path.name, tenant_id="system") == path.resolve()
    reviewed_exports = store.list_reviewed_sft_exports(tenant_id="system")
    assert len(reviewed_exports) == 1
    assert reviewed_exports[0]["filename"] == path.name
    assert reviewed_exports[0]["accepted_only"] is True
    assert len(reviewed_exports[0]["export_fingerprint"]) == 64
    assert len(reviewed_exports[0]["content_sha256"]) == 64
    assert reviewed_exports[0]["source_trajectory_ids"] == ["trj_accept"]
    assert store.get_reviewed_sft_export_path(path.name, tenant_id="system") == path.resolve()


def test_export_sft_messages_reuses_identical_dataset_fingerprint(tmp_path: Path) -> None:
    store = TrajectoryStore(tmp_path)
    store.save(_sample_trajectory("trj_idempotent_export"), tenant_id="system")
    store.mark_reviewed(
        "trj_idempotent_export",
        tenant_id="system",
        accepted=True,
        reviewer="pm",
        quality_score=0.95,
    )

    first = store.export_sft_messages(tenant_id="system", min_records=1)
    repeated = store.export_sft_messages(tenant_id="system", min_records=1)

    assert first is not None
    assert repeated == first
    assert store.get_stats(tenant_id="system")["export_count"] == 1
    assert len(store.list_sft_exports(tenant_id="system")) == 1

    with pytest.raises(ValueError, match="require provenance metadata"):
        store.export_sft_messages(tenant_id="system", min_records=1, include_metadata=False)

    without_metadata = store.export_sft_messages(
        tenant_id="system",
        min_records=1,
        accepted_only=False,
        include_metadata=False,
    )
    assert without_metadata is not None
    assert without_metadata != first
    assert store.get_stats(tenant_id="system")["export_count"] == 2


def test_foreign_top_level_metadata_blocks_mutation_without_overwrite(tmp_path: Path) -> None:
    store = TrajectoryStore(tmp_path)
    store.save(_sample_trajectory("trj_foreign_meta"), tenant_id="alpha")
    store.mark_reviewed(
        "trj_foreign_meta",
        tenant_id="alpha",
        accepted=True,
        reviewer="pm",
    )
    metadata_path = store._meta_path("alpha")
    foreign_metadata = {
        "tenant_id": "beta",
        "export_count": 7,
        "exports": [{"tenant_id": "beta", "filename": "sft_foreign.jsonl"}],
    }
    metadata_path.write_text(json.dumps(foreign_metadata, sort_keys=True), encoding="utf-8")
    original_bytes = metadata_path.read_bytes()

    assert store.get_stats(tenant_id="alpha")["export_count"] == 0
    assert store.list_sft_exports(tenant_id="alpha") == []
    with pytest.raises(ValueError, match="metadata tenant_id does not match"):
        store.export_sft_messages(tenant_id="alpha", min_records=1)

    assert metadata_path.read_bytes() == original_bytes


def test_foreign_export_metadata_is_hidden_and_preserved_on_append(tmp_path: Path) -> None:
    store = TrajectoryStore(tmp_path)
    store.save(_sample_trajectory("trj_export_one"), tenant_id="alpha")
    store.mark_reviewed("trj_export_one", tenant_id="alpha", accepted=True, reviewer="pm")
    first_export = store.export_sft_messages(tenant_id="alpha", min_records=1)
    assert first_export is not None

    metadata_path = store._meta_path("alpha")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    foreign_item = {
        "tenant_id": "beta",
        "filename": "sft_foreign.jsonl",
        "record_count": 99,
        "accepted_only": True,
        "include_metadata": True,
        "export_fingerprint": "foreign",
    }
    metadata["exports"].append(foreign_item)
    metadata_path.write_text(json.dumps(metadata, sort_keys=True), encoding="utf-8")

    store.save(_sample_trajectory("trj_export_two"), tenant_id="alpha")
    store.mark_reviewed("trj_export_two", tenant_id="alpha", accepted=True, reviewer="pm")
    second_export = store.export_sft_messages(tenant_id="alpha", min_records=1)

    assert second_export is not None
    assert second_export != first_export
    visible_filenames = {item["filename"] for item in store.list_sft_exports(tenant_id="alpha")}
    assert visible_filenames == {Path(first_export).name, Path(second_export).name}
    persisted = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert foreign_item in persisted["exports"]


def test_foreign_tenant_declared_inside_export_is_not_exposed(tmp_path: Path) -> None:
    store = TrajectoryStore(tmp_path)
    store.save(_sample_trajectory("trj_export_drift"), tenant_id="alpha")
    store.mark_reviewed("trj_export_drift", tenant_id="alpha", accepted=True, reviewer="pm")
    export_path_value = store.export_sft_messages(tenant_id="alpha", min_records=1)
    assert export_path_value is not None
    export_path = Path(export_path_value)
    record = json.loads(export_path.read_text(encoding="utf-8"))
    record["metadata"]["tenant_id"] = "beta"
    export_path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")

    assert store.list_sft_exports(tenant_id="alpha") == []
    assert store.list_reviewed_sft_exports(tenant_id="alpha") == []
    assert store.get_sft_export_path(export_path.name, tenant_id="alpha") is None
    assert store.inspect_sft_export_quality(export_path.name, tenant_id="alpha") is None


def test_accepted_export_blocks_legacy_review_without_reviewer_identity(tmp_path: Path) -> None:
    store = TrajectoryStore(tmp_path)
    trajectory = _sample_trajectory("trj_missing_reviewer")
    trajectory["human_review_status"] = "accepted"
    trajectory["human_feedback"] = {"accepted": True, "reviewer": "anonymous", "quality_score": 0.9}
    store.save(trajectory, tenant_id="system")

    preview = store.preview_sft_export(tenant_id="system", min_records=1)

    assert preview["would_export"] is False
    assert preview["blocker_summary"]["missing_reviewer"] == 1


def test_reviewed_sft_exports_exclude_unreviewed_export_metadata(tmp_path: Path) -> None:
    store = TrajectoryStore(tmp_path)
    store.save(_sample_trajectory("trj_pending"), tenant_id="system")

    export_path = store.export_sft_messages(
        tenant_id="system",
        min_records=1,
        accepted_only=False,
    )

    assert export_path is not None
    filename = Path(export_path).name
    assert store.list_sft_exports(tenant_id="system")[0]["filename"] == filename
    assert store.list_sft_exports(tenant_id="system")[0]["accepted_only"] is False
    assert store.list_reviewed_sft_exports(tenant_id="system") == []
    assert store.get_sft_export_path(filename, tenant_id="system") == Path(export_path).resolve()
    assert store.get_reviewed_sft_export_path(filename, tenant_id="system") is None


def test_preview_sft_export_reports_candidates_without_writing_file(tmp_path: Path) -> None:
    store = TrajectoryStore(tmp_path)
    blocked = _sample_trajectory("trj_blocked")
    blocked["qa"]["hard_gate_pass"] = False
    store.save(_sample_trajectory("trj_accept"), tenant_id="system")
    store.save(blocked, tenant_id="system")
    store.mark_reviewed("trj_accept", tenant_id="system", accepted=True, reviewer="pm", quality_score=0.95)
    store.mark_reviewed("trj_blocked", tenant_id="system", accepted=True, reviewer="pm", quality_score=0.7)

    preview = store.preview_sft_export(tenant_id="system", min_records=1, sample_limit=2)

    assert preview["dry_run"] is True
    assert preview["would_export"] is True
    assert preview["candidate_count"] == 2
    assert preview["eligible_count"] == 1
    assert preview["blocked_count"] == 1
    assert preview["blocker_summary"]["qa_hard_gate_failed"] == 1
    assert preview["quality_score_summary"]["avg"] == 0.95
    assert store.get_stats(tenant_id="system")["export_count"] == 0


def test_sft_quality_report_summarizes_schema_roles_evidence_and_blockers(tmp_path: Path) -> None:
    store = TrajectoryStore(tmp_path)
    blocked = _sample_trajectory("trj_blocked")
    blocked["qa"]["hard_gate_pass"] = False
    store.save(_sample_trajectory("trj_accept"), tenant_id="system")
    store.save(blocked, tenant_id="system")
    store.mark_reviewed("trj_accept", tenant_id="system", accepted=True, reviewer="pm", quality_score=0.95)
    store.mark_reviewed("trj_blocked", tenant_id="system", accepted=True, reviewer="pm", quality_score=0.7)

    report = store.report_sft_export_quality(tenant_id="system", min_records=1, sample_limit=2)

    assert report["report_type"] == "sft_export_candidate_quality"
    assert report["candidate_count"] == 2
    assert report["eligible_count"] == 1
    assert report["blocked_count"] == 1
    assert report["rejection_reason_summary"]["qa_hard_gate_failed"] == 1
    assert report["schema_valid_count"] == 1
    assert report["schema_invalid_count"] == 0
    assert report["role_sequence_summary"]["system,user,assistant"] == 1
    assert report["qa_summary"]["hard_gate_pass_count"] == 1
    assert report["qa_summary"]["quality_score_summary"]["avg"] == 0.95
    assert report["evidence_coverage"]["records_with_source_references"] == 1
    assert report["evidence_coverage"]["source_reference_coverage"] == 1.0
    assert report["provenance_coverage"]["complete_records"] == 1
    assert report["provenance_coverage"]["complete_rate"] == 1.0
    assert report["provenance_coverage"]["records_with_accepted_review"] == 1
    assert report["provenance_coverage"]["records_with_quality_score"] == 1
    assert report["ready_for_export"] is True
    assert report["ready_for_training"] is False
    assert "review_or_reject_blocked_trajectories_before_dataset_freeze" in report["recommendations"]


def test_sft_export_file_quality_report_validates_jsonl(tmp_path: Path) -> None:
    store = TrajectoryStore(tmp_path)
    store.save(_sample_trajectory("trj_accept"), tenant_id="system")
    store.mark_reviewed("trj_accept", tenant_id="system", accepted=True, reviewer="pm", quality_score=0.95)
    export_path = store.export_sft_messages(tenant_id="system", min_records=1)
    assert export_path is not None

    report = store.inspect_sft_export_quality(Path(export_path).name, tenant_id="system")

    assert report is not None
    assert report["report_type"] == "sft_export_file_quality"
    assert report["filename"] == Path(export_path).name
    assert report["jsonl_record_count"] == 1
    assert report["jsonl_line_count"] == 1
    assert report["schema_valid_count"] == 1
    assert report["schema_invalid_count"] == 0
    assert report["role_sequence_summary"]["system,user,assistant"] == 1
    assert report["evidence_coverage"]["records_with_source_references"] == 1
    assert report["provenance_coverage"]["complete_records"] == 1
    assert report["content_sha256_matches_metadata"] is True
    assert report["content_sha256"] == report["expected_content_sha256"]
    assert report["source_trajectory_ids"] == ["trj_accept"]
    assert report["ready_for_training"] is True


def test_sft_export_quality_rejects_malformed_user_payload_and_review_provenance(tmp_path: Path) -> None:
    store = TrajectoryStore(tmp_path)
    store.save(_sample_trajectory("trj_invalid_sft"), tenant_id="system")
    store.mark_reviewed(
        "trj_invalid_sft",
        tenant_id="system",
        accepted=True,
        reviewer="pm",
        quality_score=0.95,
    )
    export_path = store.export_sft_messages(tenant_id="system", min_records=1)
    assert export_path is not None
    path = Path(export_path)
    record = json.loads(path.read_text(encoding="utf-8"))
    record["messages"][1]["content"] = "not-json"
    record["metadata"].pop("reviewer")
    record["metadata"]["reviewed_at"] = "2026-07-14"
    record["metadata"]["quality_score"] = True
    path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")

    report = store.inspect_sft_export_quality(path.name, tenant_id="system")

    assert report is not None
    assert report["schema_invalid_count"] == 1
    issues = report["invalid_samples"][0]["issues"]
    assert "user_content_not_json" in issues
    assert "metadata_missing_reviewer" in issues
    assert "metadata_invalid_reviewed_at" in issues
    assert "metadata_invalid_quality_score" in issues
    assert report["provenance_coverage"]["complete_records"] == 0
    assert report["ready_for_training"] is False


def test_sft_export_quality_detects_checksum_mismatch_before_freeze(tmp_path: Path) -> None:
    store = TrajectoryStore(tmp_path)
    store.save(_sample_trajectory("trj_tampered_export"), tenant_id="system")
    store.mark_reviewed(
        "trj_tampered_export",
        tenant_id="system",
        accepted=True,
        reviewer="pm",
        quality_score=0.95,
    )
    export_path = store.export_sft_messages(tenant_id="system", min_records=1)
    assert export_path is not None
    path = Path(export_path)
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    report = store.inspect_sft_export_quality(path.name, tenant_id="system")

    assert report is not None
    assert report["schema_invalid_count"] == 0
    assert report["content_sha256_matches_metadata"] is False
    assert report["ready_for_training"] is False
    assert "regenerate_export_after_integrity_check" in report["recommendations"]
    with pytest.raises(ValueError, match="not ready for dataset freeze"):
        store.freeze_sft_export(path.name, tenant_id="system", reviewer="dataset-owner")


def test_freeze_sft_export_writes_manifest_and_metadata_without_training(tmp_path: Path) -> None:
    store = TrajectoryStore(tmp_path)
    store.save(_sample_trajectory("trj_accept"), tenant_id="system")
    store.mark_reviewed("trj_accept", tenant_id="system", accepted=True, reviewer="pm", quality_score=0.95)
    export_path = store.export_sft_messages(tenant_id="system", min_records=1)
    assert export_path is not None

    manifest = store.freeze_sft_export(
        Path(export_path).name,
        tenant_id="system",
        reviewer="dataset-owner",
        notes="Phase 9 freeze 검증",
    )

    assert manifest is not None
    assert manifest["schema_version"] == "document_ops_dataset_freeze_v1"
    assert manifest["manifest_id"].startswith("dsf_")
    assert manifest["export"]["filename"] == Path(export_path).name
    assert manifest["export"]["record_count"] == 1
    assert len(manifest["export"]["sha256"]) == 64
    assert len(manifest["quality_report"]["sha256"]) == 64
    assert manifest["quality_report"]["schema_invalid_count"] == 0
    assert manifest["review_gate"]["status"] == "approved_for_dataset_freeze"
    assert manifest["review_gate"]["reviewer"] == "dataset-owner"
    assert manifest["training_guard"]["training_allowed"] is False
    assert manifest["training_guard"]["training_started"] is False

    freezes = store.list_dataset_freezes(tenant_id="system")
    assert len(freezes) == 1
    assert freezes[0]["manifest_id"] == manifest["manifest_id"]
    assert freezes[0]["export_filename"] == Path(export_path).name
    assert freezes[0]["export_sha256"] == manifest["export"]["sha256"]
    assert len(freezes[0]["manifest_sha256"]) == 64
    assert freezes[0]["integrity_verified"] is True
    assert freezes[0]["training_allowed"] is False
    assert freezes[0]["exists"] is True
    assert freezes[0]["size_bytes"] > 0


def test_freeze_sft_export_rejects_training_allowed_flag(tmp_path: Path) -> None:
    store = TrajectoryStore(tmp_path)
    store.save(_sample_trajectory("trj_accept"), tenant_id="system")
    store.mark_reviewed("trj_accept", tenant_id="system", accepted=True, reviewer="pm", quality_score=0.95)
    export_path = store.export_sft_messages(tenant_id="system", min_records=1)
    assert export_path is not None

    with pytest.raises(ValueError, match="no-training-by-default"):
        store.freeze_sft_export(
            Path(export_path).name,
            tenant_id="system",
            reviewer="dataset-owner",
            training_allowed=True,
        )


def test_approve_training_from_freeze_records_dry_run_gate_without_provider_job(tmp_path: Path) -> None:
    store = TrajectoryStore(tmp_path)
    store.save(_sample_trajectory("trj_accept"), tenant_id="system")
    store.mark_reviewed("trj_accept", tenant_id="system", accepted=True, reviewer="pm", quality_score=0.95)
    export_path = store.export_sft_messages(tenant_id="system", min_records=1)
    assert export_path is not None
    manifest = store.freeze_sft_export(Path(export_path).name, tenant_id="system", reviewer="dataset-owner")
    assert manifest is not None

    approval = store.approve_training_from_freeze(
        manifest["manifest_id"],
        tenant_id="system",
        approver="ml-owner",
        notes="Phase 10 approval dry-run",
        eval_plan={
            "suite": "document_ops_offline_eval",
            "required_metrics": {"schema_valid_rate": 1.0, "source_reference_coverage": 1.0},
            "source_document": "sensitive-eval-note",
        },
    )

    assert approval is not None
    assert approval["schema_version"] == "document_ops_training_approval_v1"
    assert approval["approval_id"].startswith("tap_")
    assert approval["manifest"]["manifest_id"] == manifest["manifest_id"]
    assert approval["manifest"]["export_filename"] == Path(export_path).name
    assert approval["approval_gate"]["status"] == "approved_for_training_dry_run"
    assert approval["approval_gate"]["approver"] == "ml-owner"
    assert approval["approval_gate"]["freeze_reviewer"] == "dataset-owner"
    assert approval["eval_plan"]["source_document"] == "[redacted]"
    assert approval["execution_guard"]["dry_run"] is True
    assert approval["execution_guard"]["start_training_requested"] is False
    assert approval["execution_guard"]["provider_job_started"] is False
    assert approval["execution_guard"]["model_promotion_allowed"] is False

    approvals = store.list_training_approvals(tenant_id="system")
    assert len(approvals) == 1
    assert approvals[0]["approval_id"] == approval["approval_id"]
    assert approvals[0]["manifest_id"] == manifest["manifest_id"]
    assert approvals[0]["export_sha256"] == manifest["export"]["sha256"]
    assert approvals[0]["quality_report_sha256"] == manifest["quality_report"]["sha256"]
    assert len(approvals[0]["approval_sha256"]) == 64
    assert approvals[0]["integrity_verified"] is True
    assert approvals[0]["dry_run"] is True
    assert approvals[0]["provider_job_started"] is False
    assert approvals[0]["exists"] is True
    assert approvals[0]["size_bytes"] > 0


def test_training_readiness_summary_combines_freezes_approvals_and_eval_plan_without_training(tmp_path: Path) -> None:
    store = TrajectoryStore(tmp_path)
    store.save(_sample_trajectory("trj_accept"), tenant_id="system")
    store.mark_reviewed("trj_accept", tenant_id="system", accepted=True, reviewer="pm", quality_score=0.95)
    export_path = store.export_sft_messages(tenant_id="system", min_records=1)
    assert export_path is not None
    manifest = store.freeze_sft_export(Path(export_path).name, tenant_id="system", reviewer="dataset-owner")
    assert manifest is not None
    approval = store.approve_training_from_freeze(
        manifest["manifest_id"],
        tenant_id="system",
        approver="ml-owner",
        eval_plan={
            "suite": "document_ops_offline_eval",
            "required_metrics": {"schema_valid_rate": 1.0, "source_reference_coverage": 1.0},
        },
    )
    assert approval is not None

    summary = store.training_readiness_summary(tenant_id="system")

    assert summary["report_type"] == "document_ops_training_readiness"
    assert summary["read_only"] is True
    assert summary["training_execution_allowed"] is False
    assert summary["ready_for_training_execution"] is True
    assert summary["status"] == "ready_for_training_decision"
    assert summary["counts"]["reviewed_sft_exports"] == 1
    assert summary["counts"]["dataset_freezes"] == 1
    assert summary["counts"]["dry_run_training_approvals"] == 1
    assert summary["reviewed_export_count"] == 1
    assert summary["freeze_count"] == 1
    assert summary["dry_run_training_approval_count"] == 1
    assert summary["latest_reviewed_export"]["filename"] == Path(export_path).name
    assert summary["latest_dataset_freeze"]["manifest_id"] == manifest["manifest_id"]
    assert summary["latest_training_approval"]["approval_id"] == approval["approval_id"]
    assert summary["artifact_chain"]["consistent"] is True
    assert summary["artifact_chain"]["freeze_matches_latest_export"] is True
    assert summary["artifact_chain"]["approval_matches_latest_freeze"] is True
    assert summary["latest_export_quality"]["ready_for_training"] is True
    assert summary["eval_plan_coverage"]["approvals_with_eval_plan"] == 1
    assert summary["eval_plan_coverage"]["approvals_with_required_metrics"] == 1
    assert summary["eval_plan_coverage"]["latest"]["required_metric_count"] == 2
    assert summary["training_guard"]["no_training_started"] is True
    assert summary["training_guard"]["provider_job_started_count"] == 0
    assert summary["training_guard"]["model_promotion_allowed_count"] == 0
    assert summary["training_guard"]["external_upload_started"] is False
    assert summary["blockers"] == []
    assert summary["recommendations"] == ["review_latest_freeze_and_approval_before_explicit_training_execution"]


def test_training_readiness_requires_latest_export_freeze_and_approval_to_match(tmp_path: Path) -> None:
    store = TrajectoryStore(tmp_path)
    _create_training_approval_chain(store, "trj_chain_1")

    store.save(_sample_trajectory("trj_chain_2"), tenant_id="system")
    store.mark_reviewed(
        "trj_chain_2",
        tenant_id="system",
        accepted=True,
        reviewer="pm",
        quality_score=0.96,
    )
    latest_export = store.export_sft_messages(tenant_id="system", min_records=1)
    assert latest_export is not None

    export_mismatch = store.training_readiness_summary(tenant_id="system")

    assert export_mismatch["ready_for_training_execution"] is False
    assert export_mismatch["artifact_chain"]["freeze_matches_latest_export"] is False
    assert "latest_dataset_freeze_does_not_match_latest_export" in export_mismatch["blockers"]

    latest_manifest = store.freeze_sft_export(
        Path(latest_export).name,
        tenant_id="system",
        reviewer="dataset-owner",
    )
    assert latest_manifest is not None
    approval_mismatch = store.training_readiness_summary(tenant_id="system")

    assert approval_mismatch["artifact_chain"]["freeze_matches_latest_export"] is True
    assert approval_mismatch["artifact_chain"]["approval_matches_latest_freeze"] is False
    assert "latest_training_approval_does_not_match_latest_freeze" in approval_mismatch["blockers"]

    latest_approval = store.approve_training_from_freeze(
        latest_manifest["manifest_id"],
        tenant_id="system",
        approver="ml-owner",
        eval_plan={
            "suite": "document_ops_offline_eval",
            "required_metrics": {"schema_valid_rate": 1.0},
        },
    )
    assert latest_approval is not None
    ready = store.training_readiness_summary(tenant_id="system")

    assert ready["ready_for_training_execution"] is True
    assert ready["artifact_chain"]["consistent"] is True
    assert ready["blockers"] == []


def test_training_readiness_rejects_tampered_approval_artifact(tmp_path: Path) -> None:
    store = TrajectoryStore(tmp_path)
    _, _, approval = _create_training_approval_chain(store, "trj_tampered_approval")
    approval_meta = store.list_training_approvals(tenant_id="system")[0]
    approval_path = store._resolve_training_approval_path("system", approval_meta["approval_file"])
    assert approval_path is not None
    approval_path.write_text(
        approval_path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    summary = store.training_readiness_summary(tenant_id="system")

    assert summary["latest_training_approval"]["approval_id"] == approval["approval_id"]
    assert summary["latest_training_approval"]["integrity_verified"] is False
    assert summary["artifact_chain"]["approval_integrity_verified"] is False
    assert summary["ready_for_training_execution"] is False
    assert "latest_training_approval_integrity_failed" in summary["blockers"]


def test_training_readiness_hides_approval_artifact_with_foreign_tenant(tmp_path: Path) -> None:
    store = TrajectoryStore(tmp_path)
    _, _, approval = _create_training_approval_chain(store, "trj_foreign_approval")
    approval_meta = store.list_training_approvals(tenant_id="system")[0]
    approval_path = store._resolve_training_approval_path("system", approval_meta["approval_file"])
    assert approval_path is not None
    approval_record = json.loads(approval_path.read_text(encoding="utf-8"))
    approval_record["tenant_id"] = "other"
    approval_path.write_text(json.dumps(approval_record, sort_keys=True), encoding="utf-8")

    summary = store.training_readiness_summary(tenant_id="system")

    assert store.list_training_approvals(tenant_id="system") == []
    assert store._load_training_approval_by_file("system", approval_meta["approval_file"]) is None
    assert summary["latest_training_approval"] is None
    assert summary["ready_for_training_execution"] is False
    assert "no_dry_run_training_approval" in summary["blockers"]
    assert approval["approval_id"] not in json.dumps(summary, sort_keys=True)


def test_training_execution_plan_preview_builds_provider_agnostic_dry_run_spec(tmp_path: Path) -> None:
    store = TrajectoryStore(tmp_path)
    store.save(_sample_trajectory("trj_accept"), tenant_id="system")
    store.mark_reviewed("trj_accept", tenant_id="system", accepted=True, reviewer="pm", quality_score=0.95)
    export_path = store.export_sft_messages(tenant_id="system", min_records=1)
    assert export_path is not None
    manifest = store.freeze_sft_export(Path(export_path).name, tenant_id="system", reviewer="dataset-owner")
    assert manifest is not None
    store.approve_training_from_freeze(
        manifest["manifest_id"],
        tenant_id="system",
        approver="ml-owner",
        eval_plan={
            "suite": "document_ops_offline_eval",
            "required_metrics": {"schema_valid_rate": 1.0},
        },
    )

    preview = store.training_execution_plan_preview(
        tenant_id="system",
        provider="OpenAI Fine Tune!",
        base_model="gpt-test-base",
    )

    assert preview["report_type"] == "document_ops_training_execution_plan_preview"
    assert preview["dry_run"] is True
    assert preview["preview_only"] is True
    assert preview["read_only"] is True
    assert preview["training_execution_allowed"] is False
    assert preview["provider_api_calls_allowed"] is False
    assert preview["external_upload_allowed"] is False
    assert preview["provider_job_started"] is False
    assert preview["model_promotion_allowed"] is False
    assert preview["status"] == "ready_for_manual_execution_planning"
    assert preview["blockers"] == []
    assert preview["job_spec"]["provider"] == "OpenAI_Fine_Tune"
    assert preview["job_spec"]["base_model"] == "gpt-test-base"
    assert preview["job_spec"]["dataset"]["freeze_manifest_id"] == manifest["manifest_id"]
    assert preview["job_spec"]["dataset"]["export_filename"] == Path(export_path).name
    assert preview["job_spec"]["dataset"]["record_count"] == 1
    assert len(preview["job_spec"]["dataset"]["export_sha256"]) == 64
    assert preview["job_spec"]["evaluation"]["suite"] == "document_ops_offline_eval"
    assert preview["job_spec"]["evaluation"]["required_metrics"]["schema_valid_rate"] == 1.0
    assert {item["step"] for item in preview["job_spec"]["execution_steps"]} == {
        "validate_readiness",
        "upload_dataset",
        "create_provider_fine_tune_job",
        "monitor_training",
        "run_required_evals",
        "promote_model_candidate",
    }
    assert all(item["status"] != "started" for item in preview["job_spec"]["execution_steps"])


def test_training_execution_request_records_two_person_guard_without_side_effects(tmp_path: Path) -> None:
    store = TrajectoryStore(tmp_path)
    store.save(_sample_trajectory("trj_accept"), tenant_id="system")
    store.mark_reviewed("trj_accept", tenant_id="system", accepted=True, reviewer="pm", quality_score=0.95)
    export_path = store.export_sft_messages(tenant_id="system", min_records=1)
    assert export_path is not None
    manifest = store.freeze_sft_export(Path(export_path).name, tenant_id="system", reviewer="dataset-owner")
    assert manifest is not None
    approval = store.approve_training_from_freeze(
        manifest["manifest_id"],
        tenant_id="system",
        approver="ml-owner",
        eval_plan={"suite": "document_ops_offline_eval", "required_metrics": {"schema_valid_rate": 1.0}},
    )
    assert approval is not None

    request = store.request_training_execution_from_plan(
        tenant_id="system",
        requester="ops-owner",
        provider="openai",
        base_model="gpt-test-base",
        notes="record only",
    )

    assert request["schema_version"] == "document_ops_training_execution_request_v1"
    assert request["request_id"].startswith("ter_")
    assert request["plan_preview"]["dataset"]["freeze_manifest_id"] == manifest["manifest_id"]
    assert request["plan_preview"]["dataset"]["export_filename"] == Path(export_path).name
    assert request["plan_preview"]["evaluation"]["suite"] == "document_ops_offline_eval"
    assert request["request_gate"]["requester"] == "ops-owner"
    assert request["request_gate"]["prior_training_approver"] == "ml-owner"
    assert request["request_gate"]["prior_training_approval_id"] == approval["approval_id"]
    assert request["two_person_guard"]["required"] is True
    assert request["two_person_guard"]["satisfied"] is True
    assert request["execution_guard"]["training_execution_allowed"] is False
    assert request["execution_guard"]["external_upload_started"] is False
    assert request["execution_guard"]["provider_api_calls_allowed"] is False
    assert request["execution_guard"]["provider_job_started"] is False
    assert request["execution_guard"]["model_promotion_allowed"] is False

    requests = store.list_training_execution_requests(tenant_id="system")
    assert len(requests) == 1
    assert requests[0]["request_id"] == request["request_id"]
    assert requests[0]["manifest_id"] == manifest["manifest_id"]
    assert requests[0]["approval_id"] == approval["approval_id"]
    assert requests[0]["two_person_guard_satisfied"] is True
    assert requests[0]["training_execution_allowed"] is False
    assert requests[0]["provider_job_started"] is False
    assert requests[0]["external_upload_started"] is False
    assert requests[0]["provider_api_calls_allowed"] is False
    assert requests[0]["model_promotion_allowed"] is False
    assert len(requests[0]["request_sha256"]) == 64
    assert requests[0]["integrity_verified"] is True
    assert requests[0]["exists"] is True

    with pytest.raises(ValueError, match="different from dry-run training approver"):
        store.request_training_execution_from_plan(tenant_id="system", requester="ml-owner")
    with pytest.raises(ValueError, match="start_training"):
        store.request_training_execution_from_plan(tenant_id="system", requester="ops-owner", start_training=True)
    with pytest.raises(ValueError, match="no-upload"):
        store.request_training_execution_from_plan(tenant_id="system", requester="ops-owner", upload_dataset=True)
    with pytest.raises(ValueError, match="provider APIs"):
        store.request_training_execution_from_plan(tenant_id="system", requester="ops-owner", call_provider_api=True)


def test_pre_execution_audit_rejects_request_from_previous_artifact_chain(tmp_path: Path) -> None:
    store = TrajectoryStore(tmp_path)
    _, first_manifest, _ = _create_training_approval_chain(store, "trj_request_chain_1")
    request = store.request_training_execution_from_plan(
        tenant_id="system",
        requester="ops-owner",
        provider="openai",
        base_model="gpt-test-base",
    )
    _, latest_manifest, latest_approval = _create_training_approval_chain(store, "trj_request_chain_2")

    checklist = store.training_pre_execution_audit_checklist(
        tenant_id="system",
        provider="openai",
        base_model="gpt-test-base",
    )

    chain_item = next(item for item in checklist["checklist"] if item["id"] == "artifact_chain_consistent")
    assert request["plan_preview"]["dataset"]["freeze_manifest_id"] == first_manifest["manifest_id"]
    assert checklist["readiness_summary"]["artifact_chain"]["consistent"] is True
    assert chain_item["passed"] is False
    assert chain_item["evidence"]["request_integrity_verified"] is True
    assert chain_item["evidence"]["request_manifest_id"] == first_manifest["manifest_id"]
    assert chain_item["evidence"]["current_manifest_id"] == latest_manifest["manifest_id"]
    assert chain_item["evidence"]["current_approval_id"] == latest_approval["approval_id"]
    assert checklist["status"] == "blocked"
    assert "artifact_chain_consistent" in checklist["blockers"]


def test_training_pre_execution_audit_exports_human_review_packet_without_side_effects(tmp_path: Path) -> None:
    store = TrajectoryStore(tmp_path)
    store.save(_sample_trajectory("trj_accept"), tenant_id="system")
    store.mark_reviewed("trj_accept", tenant_id="system", accepted=True, reviewer="pm", quality_score=0.95)
    export_path = store.export_sft_messages(tenant_id="system", min_records=1)
    assert export_path is not None
    manifest = store.freeze_sft_export(Path(export_path).name, tenant_id="system", reviewer="dataset-owner")
    assert manifest is not None
    store.approve_training_from_freeze(
        manifest["manifest_id"],
        tenant_id="system",
        approver="ml-owner",
        eval_plan={"suite": "document_ops_offline_eval", "required_metrics": {"schema_valid_rate": 1.0}},
    )
    request = store.request_training_execution_from_plan(
        tenant_id="system",
        requester="ops-owner",
        provider="openai",
        base_model="gpt-test-base",
    )

    checklist = store.training_pre_execution_audit_checklist(
        tenant_id="system",
        provider="openai",
        base_model="gpt-test-base",
    )

    assert checklist["report_type"] == "document_ops_training_pre_execution_audit_checklist"
    assert checklist["status"] == "ready_for_human_pre_execution_review"
    assert checklist["training_execution_allowed"] is False
    assert checklist["provider_api_calls_allowed"] is False
    assert checklist["external_upload_allowed"] is False
    assert checklist["provider_job_started"] is False
    assert checklist["model_promotion_allowed"] is False
    assert checklist["latest_training_execution_request"]["request_id"] == request["request_id"]
    assert all(item["passed"] is True for item in checklist["checklist"] if item["severity"] == "required")
    assert checklist["human_review_packet"]["dataset"]["freeze_manifest_id"] == manifest["manifest_id"]

    audit = store.export_training_pre_execution_audit(
        tenant_id="system",
        auditor="compliance-owner",
        provider="openai",
        base_model="gpt-test-base",
        notes="final packet only",
    )

    assert audit["schema_version"] == "document_ops_training_pre_execution_audit_v1"
    assert audit["audit_id"].startswith("tea_")
    assert audit["audit_gate"]["auditor"] == "compliance-owner"
    assert audit["audit_gate"]["requester"] == "ops-owner"
    assert audit["audit_gate"]["prior_training_approver"] == "ml-owner"
    assert audit["audit_gate"]["separation_of_duties_satisfied"] is True
    assert audit["checklist_snapshot"]["status"] == "ready_for_human_pre_execution_review"
    assert audit["execution_guard"]["training_execution_allowed"] is False
    assert audit["execution_guard"]["external_upload_started"] is False
    assert audit["execution_guard"]["provider_api_calls_allowed"] is False
    assert audit["execution_guard"]["provider_job_started"] is False
    assert audit["execution_guard"]["model_promotion_allowed"] is False

    audits = store.list_training_pre_execution_audits(tenant_id="system")
    assert len(audits) == 1
    assert audits[0]["audit_id"] == audit["audit_id"]
    assert audits[0]["request_id"] == request["request_id"]
    assert audits[0]["manifest_id"] == manifest["manifest_id"]
    assert audits[0]["training_execution_allowed"] is False
    assert audits[0]["provider_job_started"] is False
    assert audits[0]["external_upload_started"] is False
    assert audits[0]["provider_api_calls_allowed"] is False
    assert audits[0]["model_promotion_allowed"] is False
    assert len(audits[0]["audit_sha256"]) == 64
    assert audits[0]["integrity_verified"] is True
    assert audits[0]["exists"] is True
    assert store.get_training_pre_execution_audit_path(audits[0]["audit_file"], tenant_id="system") is not None

    with pytest.raises(ValueError, match="different from training execution requester"):
        store.export_training_pre_execution_audit(tenant_id="system", auditor="ops-owner")
    with pytest.raises(ValueError, match="different from dry-run training approver"):
        store.export_training_pre_execution_audit(tenant_id="system", auditor="ml-owner")
    with pytest.raises(ValueError, match="start_training"):
        store.export_training_pre_execution_audit(tenant_id="system", auditor="compliance-owner", start_training=True)
    with pytest.raises(ValueError, match="no-upload"):
        store.export_training_pre_execution_audit(tenant_id="system", auditor="compliance-owner", upload_dataset=True)
    with pytest.raises(ValueError, match="provider APIs"):
        store.export_training_pre_execution_audit(tenant_id="system", auditor="compliance-owner", call_provider_api=True)


def test_training_governance_dashboard_summary_aggregates_all_gates_without_side_effects(tmp_path: Path) -> None:
    store = TrajectoryStore(tmp_path)
    store.save(_sample_trajectory("trj_accept"), tenant_id="system")
    store.mark_reviewed("trj_accept", tenant_id="system", accepted=True, reviewer="pm", quality_score=0.95)
    export_path = store.export_sft_messages(tenant_id="system", min_records=1)
    assert export_path is not None
    manifest = store.freeze_sft_export(Path(export_path).name, tenant_id="system", reviewer="dataset-owner")
    assert manifest is not None
    approval = store.approve_training_from_freeze(
        manifest["manifest_id"],
        tenant_id="system",
        approver="ml-owner",
        eval_plan={"suite": "document_ops_offline_eval", "required_metrics": {"schema_valid_rate": 1.0}},
    )
    request = store.request_training_execution_from_plan(
        tenant_id="system",
        requester="ops-owner",
        provider="openai",
        base_model="gpt-test-base",
    )
    audit = store.export_training_pre_execution_audit(
        tenant_id="system",
        auditor="compliance-owner",
        provider="openai",
        base_model="gpt-test-base",
    )

    summary = store.training_governance_dashboard_summary(
        tenant_id="system",
        provider="openai",
        base_model="gpt-test-base",
    )

    assert approval is not None
    assert summary["report_type"] == "document_ops_training_governance_dashboard_summary"
    assert summary["status"] == "governance_ready_for_human_review"
    assert summary["read_only"] is True
    assert summary["training_execution_allowed"] is False
    assert summary["provider_api_calls_allowed"] is False
    assert summary["external_upload_allowed"] is False
    assert summary["provider_job_started"] is False
    assert summary["model_promotion_allowed"] is False
    assert summary["counts"] == {
        "reviewed_sft_exports": 1,
        "dataset_freezes": 1,
        "dry_run_training_approvals": 1,
        "training_execution_requests": 1,
        "pre_execution_audit_exports": 1,
    }
    assert summary["latest"]["reviewed_sft_export"]["filename"] == Path(export_path).name
    assert summary["latest"]["dataset_freeze"]["manifest_id"] == manifest["manifest_id"]
    assert summary["latest"]["dry_run_training_approval"]["approval_id"] == approval["approval_id"]
    assert summary["latest"]["training_execution_request"]["request_id"] == request["request_id"]
    assert summary["latest"]["pre_execution_audit"]["audit_id"] == audit["audit_id"]
    assert summary["no_side_effects"] is True
    assert all(value == 0 for value in summary["guard_counts"].values())
    assert summary["blockers"] == []
    assert summary["readiness_status"] == "ready_for_training_decision"
    assert summary["plan_preview_status"] == "ready_for_manual_execution_planning"
    assert summary["audit_checklist_status"] == "ready_for_human_pre_execution_review"
    assert summary["audit_chain"]["matches_current_chain"] is True


def test_governance_dashboard_rejects_audit_from_previous_artifact_chain(tmp_path: Path) -> None:
    store = TrajectoryStore(tmp_path)
    _create_training_approval_chain(store, "trj_audit_chain_1")
    first_request = store.request_training_execution_from_plan(
        tenant_id="system",
        requester="ops-owner",
        provider="openai",
        base_model="gpt-test-base",
    )
    first_audit = store.export_training_pre_execution_audit(
        tenant_id="system",
        auditor="compliance-owner",
        provider="openai",
        base_model="gpt-test-base",
    )
    _, latest_manifest, _ = _create_training_approval_chain(store, "trj_audit_chain_2")
    latest_request = store.request_training_execution_from_plan(
        tenant_id="system",
        requester="ops-owner",
        provider="openai",
        base_model="gpt-test-base",
    )

    summary = store.training_governance_dashboard_summary(
        tenant_id="system",
        provider="openai",
        base_model="gpt-test-base",
    )

    assert first_request["request_id"] != latest_request["request_id"]
    assert summary["latest"]["pre_execution_audit"]["audit_id"] == first_audit["audit_id"]
    assert summary["audit_chain"]["integrity_verified"] is True
    assert summary["audit_chain"]["audit_request_id"] == first_request["request_id"]
    assert summary["audit_chain"]["current_request_id"] == latest_request["request_id"]
    assert summary["audit_chain"]["current_manifest_id"] == latest_manifest["manifest_id"]
    assert summary["audit_chain"]["matches_current_chain"] is False
    assert summary["status"] == "needs_attention"
    assert "latest_training_audit_does_not_match_current_chain" in summary["blockers"]


def test_approve_training_from_freeze_enforces_separate_approver_and_no_job(tmp_path: Path) -> None:
    store = TrajectoryStore(tmp_path)
    store.save(_sample_trajectory("trj_accept"), tenant_id="system")
    store.mark_reviewed("trj_accept", tenant_id="system", accepted=True, reviewer="pm", quality_score=0.95)
    export_path = store.export_sft_messages(tenant_id="system", min_records=1)
    assert export_path is not None
    manifest = store.freeze_sft_export(Path(export_path).name, tenant_id="system", reviewer="dataset-owner")
    assert manifest is not None
    eval_plan = {"suite": "document_ops_offline_eval"}

    with pytest.raises(ValueError, match="different from dataset freeze reviewer"):
        store.approve_training_from_freeze(
            manifest["manifest_id"],
            tenant_id="system",
            approver="dataset-owner",
            eval_plan=eval_plan,
        )

    with pytest.raises(ValueError, match="no-provider-job"):
        store.approve_training_from_freeze(
            manifest["manifest_id"],
            tenant_id="system",
            approver="ml-owner",
            eval_plan=eval_plan,
            start_training=True,
        )

    with pytest.raises(ValueError, match="dry_run=true"):
        store.approve_training_from_freeze(
            manifest["manifest_id"],
            tenant_id="system",
            approver="ml-owner",
            eval_plan=eval_plan,
            dry_run=False,
        )

    with pytest.raises(ValueError, match="Invalid manifest_id"):
        store.approve_training_from_freeze(
            "../bad",
            tenant_id="system",
            approver="ml-owner",
            eval_plan=eval_plan,
        )


def test_export_sft_messages_skips_blocked_records(tmp_path: Path) -> None:
    store = TrajectoryStore(tmp_path)
    blocked = _sample_trajectory("trj_blocked")
    blocked["plan"] = []
    store.save(_sample_trajectory("trj_accept"), tenant_id="system")
    store.save(blocked, tenant_id="system")
    store.mark_reviewed("trj_accept", tenant_id="system", accepted=True, reviewer="pm", quality_score=0.95)
    store.mark_reviewed("trj_blocked", tenant_id="system", accepted=True, reviewer="pm", quality_score=0.7)

    export_path = store.export_sft_messages(tenant_id="system", min_records=1)

    assert export_path is not None
    lines = [line for line in Path(export_path).read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 1
    assert json.loads(lines[0])["metadata"]["trajectory_id"] == "trj_accept"


def test_export_returns_none_when_min_records_not_met(tmp_path: Path) -> None:
    store = TrajectoryStore(tmp_path)
    store.save(_sample_trajectory("trj_pending"), tenant_id="system")

    assert store.export_sft_messages(tenant_id="system", min_records=1) is None


def test_export_download_path_requires_safe_metadata_filename(tmp_path: Path) -> None:
    store = TrajectoryStore(tmp_path)

    with pytest.raises(ValueError):
        store.get_sft_export_path("../secret.jsonl", tenant_id="system")
    with pytest.raises(ValueError):
        store.get_reviewed_sft_export_path("../secret.jsonl", tenant_id="system")

    assert store.get_sft_export_path("sft_policy_planning_brief_20260507T000000.jsonl", tenant_id="system") is None
    assert store.get_reviewed_sft_export_path("sft_policy_planning_brief_20260507T000000.jsonl", tenant_id="system") is None
