"""Quality correction artifact and develop-quality-improvement preview flows."""
from __future__ import annotations

import hmac
import json
from typing import Any

from app.services.report_quality_learning import (
    build_correction_artifact_from_snapshot,
    correction_artifact_fingerprint,
    validate_correction_artifact,
)
from app.storage.report_workflow_store import ReportWorkflowRecord


class ReportWorkflowQualityMixin:
    """Quality correction artifact preview/save/list/export plus develop-quality-improvement preview."""

    def preview_quality_correction_artifact(
        self,
        report_workflow_id: str,
        *,
        tenant_id: str,
        correction: dict[str, Any],
    ) -> dict[str, Any]:
        snapshot = self.build_export_snapshot(report_workflow_id, tenant_id=tenant_id)
        artifact = build_correction_artifact_from_snapshot(snapshot, correction)
        validation = validate_correction_artifact(artifact)
        return {
            "artifact": artifact,
            "validation": validation,
            "preview_fingerprint": correction_artifact_fingerprint(artifact),
            "persisted": False,
        }

    def save_quality_correction_artifact(
        self,
        report_workflow_id: str,
        *,
        tenant_id: str,
        correction: dict[str, Any],
        actor: str = "",
    ) -> dict[str, Any]:
        expected_fingerprint = str(correction.get("preview_fingerprint") or "").strip()
        if not expected_fingerprint:
            raise ValueError(
                "preview_fingerprint is required; preview the correction artifact before saving"
            )
        result = self.preview_quality_correction_artifact(
            report_workflow_id,
            tenant_id=tenant_id,
            correction=correction,
        )
        validation = result["validation"]
        if not validation["ok"] or not validation["ready_for_learning"]:
            errors = validation.get("errors") or ["correction artifact is not ready for learning"]
            raise ValueError("; ".join(str(item) for item in errors))
        if not hmac.compare_digest(expected_fingerprint, result["preview_fingerprint"]):
            raise ValueError(
                "preview_fingerprint does not match the current workflow and correction input; preview again"
            )
        if self._quality_correction_artifact_exists(
            report_workflow_id,
            tenant_id=tenant_id,
            artifact_id=result["artifact"]["artifact_id"],
        ):
            raise ValueError("this correction artifact has already been saved")
        rec = self.store.append_learning_artifact(
            report_workflow_id,
            kind="report_quality_correction_accepted",
            payload={
                "artifact": result["artifact"],
                "validation": validation,
                "preview_fingerprint": result["preview_fingerprint"],
            },
            actor=actor,
            tenant_id=tenant_id,
        )
        return {
            "report_workflow": rec,
            "artifact": result["artifact"],
            "validation": validation,
            "preview_fingerprint": result["preview_fingerprint"],
            "persisted": True,
        }

    def _quality_correction_artifact_exists(
        self,
        report_workflow_id: str,
        *,
        tenant_id: str,
        artifact_id: str,
    ) -> bool:
        record = self._require_record(report_workflow_id, tenant_id=tenant_id)
        for wrapper in record.learning_artifacts:
            payload = wrapper.get("payload") if isinstance(wrapper, dict) else None
            artifact = payload.get("artifact") if isinstance(payload, dict) else None
            if isinstance(artifact, dict) and artifact.get("artifact_id") == artifact_id:
                return True
        return False

    def preview_develop_quality_improvement(
        self,
        report_workflow_id: str,
        *,
        tenant_id: str,
        request_id: str,
        document_ops_service: Any,
        focus: str = "보고서 품질 개선",
        additional_notes: str = "",
        capture_trajectory: bool = False,
    ) -> dict[str, Any]:
        rec = self._require_record(report_workflow_id, tenant_id=tenant_id)
        if rec.planning is None and not rec.slides:
            raise ValueError("Develop 품질 개선 preview는 기획안 또는 장표 초안 생성 후 실행할 수 있습니다.")
        payload = self._build_develop_quality_payload(
            rec,
            focus=focus,
            additional_notes=additional_notes,
            capture_trajectory=capture_trajectory,
        )
        result = document_ops_service.run(
            payload,
            tenant_id=tenant_id,
            request_id=request_id,
        )
        return {
            "report_type": "report_workflow_develop_quality_preview",
            "persisted": False,
            "report_workflow": self._develop_quality_workflow_summary(rec),
            "document_ops_request": {
                "task_type": payload["task_type"],
                "skill_name": payload["skill_name"],
                "capture_trajectory": payload["capture_trajectory"],
                "source_reference_count": len(payload["source_references"]),
                "source_summary_count": len(payload["source_summaries"]),
            },
            "develop_result": result,
            "training_boundary": {
                "training_execution_authorized": False,
                "external_dataset_upload_authorized": False,
                "provider_fine_tune_api_call_authorized": False,
                "provider_job_started": False,
                "model_promotion_authorized": False,
            },
        }

    @staticmethod
    def _quality_correction_artifact_row(
        rec: ReportWorkflowRecord,
        wrapper: dict[str, Any],
        *,
        include_artifact: bool = False,
    ) -> dict[str, Any]:
        payload = wrapper.get("payload") if isinstance(wrapper.get("payload"), dict) else {}
        artifact = payload.get("artifact") if isinstance(payload.get("artifact"), dict) else {}
        validation = payload.get("validation") if isinstance(payload.get("validation"), dict) else {}
        if artifact and not validation:
            validation = validate_correction_artifact(artifact)
        workflow_reference = artifact.get("workflow_reference") if isinstance(artifact.get("workflow_reference"), dict) else {}
        document_profile = artifact.get("document_profile") if isinstance(artifact.get("document_profile"), dict) else {}
        quality_baseline = artifact.get("quality_baseline") if isinstance(artifact.get("quality_baseline"), dict) else {}
        correction = artifact.get("correction") if isinstance(artifact.get("correction"), dict) else {}
        learning_labels = artifact.get("learning_labels") if isinstance(artifact.get("learning_labels"), dict) else {}
        row = {
            "store_artifact_id": wrapper.get("artifact_id", ""),
            "artifact_id": validation.get("artifact_id") or artifact.get("artifact_id") or "",
            "kind": wrapper.get("kind", ""),
            "created_at": wrapper.get("created_at", ""),
            "actor": wrapper.get("actor", ""),
            "tenant_id": rec.tenant_id,
            "report_workflow_id": rec.report_workflow_id,
            "workflow_title": rec.title,
            "client": rec.client,
            "workflow_status": workflow_reference.get("workflow_status") or rec.status,
            "learning_opt_in": bool(workflow_reference.get("learning_opt_in", rec.learning_opt_in)),
            "document_type": document_profile.get("document_type", ""),
            "domain": document_profile.get("domain", ""),
            "language": document_profile.get("language", ""),
            "slide_count": document_profile.get("slide_count", rec.slide_count),
            "reviewer": correction.get("reviewer", ""),
            "reviewed_at": correction.get("reviewed_at", ""),
            "overall_score": quality_baseline.get("overall_score"),
            "task_types": list(learning_labels.get("task_types") or []),
            "skills": list(learning_labels.get("skills") or []),
            "confirmed_claim_count": len(learning_labels.get("confirmed_claims") or []),
            "validation_ok": bool(validation.get("ok", False)),
            "ready_for_learning": bool(validation.get("ready_for_learning", False)),
            "validation_errors": list(validation.get("errors") or []),
            "validation_warnings": list(validation.get("warnings") or []),
            "schema_version": artifact.get("schema_version", ""),
        }
        if include_artifact:
            row["artifact"] = artifact
        return row

    def _build_develop_quality_payload(
        self,
        rec: ReportWorkflowRecord,
        *,
        focus: str,
        additional_notes: str,
        capture_trajectory: bool,
    ) -> dict[str, Any]:
        draft = self._report_workflow_current_draft(rec)
        source_references = self._report_workflow_source_references(rec)
        source_summaries = self._report_workflow_source_summaries(rec)
        return {
            "task_type": "develop_quality_improvement",
            "skill_name": "develop-document-improver",
            "requirements": {
                "title": f"{rec.title} 품질 개선",
                "goal": str(focus or rec.goal or "보고서 품질 개선").strip(),
                "current_draft": draft,
                "draft": draft,
                "improvement_goal": str(focus or "보고서 품질 개선").strip(),
                "additional_notes": str(additional_notes or "").strip(),
                "workflow_status": rec.status,
                "client": rec.client,
                "audience": rec.audience,
            },
            "project_context": {
                "report_workflow_id": rec.report_workflow_id,
                "workflow_status": rec.status,
                "report_type": rec.report_type,
                "client": rec.client,
                "audience": rec.audience,
                "learning_opt_in": rec.learning_opt_in,
                "current_plan_version": rec.current_plan_version,
                "current_slide_version": rec.current_slide_version,
            },
            "source_summaries": source_summaries,
            "source_references": source_references,
            "capture_trajectory": capture_trajectory,
        }

    @staticmethod
    def _report_workflow_current_draft(rec: ReportWorkflowRecord) -> str:
        from app.services.report_workflow_service import ReportWorkflowService

        docs = ReportWorkflowService._approval_docs(rec)
        parts = [
            f"# Report Workflow 품질 개선 대상: {rec.title}",
            "",
            f"- 목표: {rec.goal}",
            f"- 고객/대상: {rec.client or 'n/a'} / {rec.audience or 'n/a'}",
            f"- 상태: {rec.status}",
            "",
        ]
        for doc in docs:
            markdown = str(doc.get("markdown") or "").strip()
            if markdown:
                parts.extend([f"## {doc.get('title') or doc.get('doc_type')}", markdown, ""])
        return "\n".join(parts).strip()

    @staticmethod
    def _report_workflow_source_references(rec: ReportWorkflowRecord) -> list[dict[str, str]]:
        refs = [
            {"id": f"report_workflow:{rec.report_workflow_id}", "title": rec.title},
        ]
        if rec.planning is not None:
            refs.append(
                {
                    "id": f"report_workflow:{rec.report_workflow_id}:planning:v{rec.current_plan_version}",
                    "title": f"{rec.title} planning v{rec.current_plan_version}",
                }
            )
        if rec.slides:
            refs.append(
                {
                    "id": f"report_workflow:{rec.report_workflow_id}:slides:v{rec.current_slide_version}",
                    "title": f"{rec.title} slides v{rec.current_slide_version}",
                }
            )
        for ref in rec.source_refs:
            label = str(ref or "").strip()
            if label:
                refs.append({"id": label, "title": label})
        seen: set[str] = set()
        deduped: list[dict[str, str]] = []
        for item in refs:
            if item["id"] in seen:
                continue
            seen.add(item["id"])
            deduped.append(item)
        return deduped

    @staticmethod
    def _report_workflow_source_summaries(rec: ReportWorkflowRecord) -> list[str]:
        summaries = [
            f"workflow_status={rec.status}",
            f"goal={rec.goal}",
        ]
        if rec.planning is not None:
            summaries.extend(
                [
                    f"planning.objective={rec.planning.objective}",
                    f"planning.executive_message={rec.planning.executive_message}",
                    "planning.quality_bar=" + " | ".join(rec.planning.quality_bar),
                ]
            )
        if rec.slides:
            summaries.append(
                "slides="
                + " | ".join(
                    f"{slide.page}. {slide.title}: {slide.body[:120]}"
                    for slide in sorted(rec.slides, key=lambda item: item.page)
                )
            )
        return [item for item in summaries if str(item or "").strip()]

    @staticmethod
    def _develop_quality_workflow_summary(rec: ReportWorkflowRecord) -> dict[str, Any]:
        return {
            "report_workflow_id": rec.report_workflow_id,
            "title": rec.title,
            "status": rec.status,
            "learning_opt_in": rec.learning_opt_in,
            "current_plan_version": rec.current_plan_version,
            "current_slide_version": rec.current_slide_version,
            "slide_count": len(rec.slides),
        }

    def list_quality_correction_artifacts(
        self,
        *,
        tenant_id: str,
        ready_only: bool = False,
        limit: int = 50,
        include_artifact: bool = False,
    ) -> dict[str, Any]:
        """List saved metadata-only quality correction artifacts for review/export."""
        clamped_limit = max(1, min(int(limit or 50), 200))
        rows: list[dict[str, Any]] = []
        for rec in self.store.list_by_tenant(tenant_id):
            for wrapper in rec.learning_artifacts:
                if not isinstance(wrapper, dict) or wrapper.get("kind") != "report_quality_correction_accepted":
                    continue
                row = self._quality_correction_artifact_row(rec, wrapper, include_artifact=include_artifact)
                rows.append(row)
        rows.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        ready_count = sum(1 for item in rows if item.get("ready_for_learning") is True)
        filtered = [item for item in rows if item.get("ready_for_learning") is True] if ready_only else rows
        limited = filtered[:clamped_limit]
        return {
            "report_type": "report_quality_correction_artifact_summary",
            "tenant_id": tenant_id,
            "ready_only": bool(ready_only),
            "limit": clamped_limit,
            "total_artifacts": len(rows),
            "ready_artifacts": ready_count,
            "not_ready_artifacts": len(rows) - ready_count,
            "returned": len(limited),
            "artifacts": limited,
            "training_boundary": {
                "external_dataset_upload_authorized": False,
                "provider_fine_tune_api_call_authorized": False,
                "provider_job_creation_authorized": False,
                "provider_job_polling_authorized": False,
                "training_execution_authorized": False,
                "model_promotion_authorized": False,
            },
        }

    def export_quality_correction_artifacts_jsonl(
        self,
        *,
        tenant_id: str,
        ready_only: bool = True,
        limit: int = 200,
    ) -> str:
        summary = self.list_quality_correction_artifacts(
            tenant_id=tenant_id,
            ready_only=ready_only,
            limit=limit,
            include_artifact=True,
        )
        lines = [
            json.dumps(item["artifact"], ensure_ascii=False, sort_keys=True)
            for item in summary["artifacts"]
            if isinstance(item.get("artifact"), dict) and item["artifact"]
        ]
        return "\n".join(lines) + ("\n" if lines else "")
