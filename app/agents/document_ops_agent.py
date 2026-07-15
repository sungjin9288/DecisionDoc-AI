"""DecisionDoc-native DocumentOps agent.

This module implements a small, governed agent loop inspired by Hermes-style
skills and trajectories without importing a broad external runtime.
"""
from __future__ import annotations

import json
import hashlib
import re
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from app.agents.schemas import (
    DocumentOpsDraftOutput,
    DocumentOpsRequest,
    DocumentOpsResult,
    DocumentOpsSkill,
    EvidenceStatus,
)
from app.agents.skill_registry import SkillRegistry
from app.evals.document_ops.gates import evaluate_document_ops_output
from app.evals.document_ops.rubric import DEFAULT_FORBIDDEN_TERMS
from app.providers.base import Provider, ProviderError
from app.tenant import require_tenant_id

if TYPE_CHECKING:
    from app.storage.trajectory_store import TrajectoryStore


class DocumentOpsAgent:
    """Run first-party document and policy-planning tasks through providers."""

    def __init__(
        self,
        *,
        provider: Provider | None = None,
        skill_registry: SkillRegistry | None = None,
        trajectory_store: "TrajectoryStore | None" = None,
        forbidden_terms: tuple[str, ...] = DEFAULT_FORBIDDEN_TERMS,
    ) -> None:
        self._provider = provider
        self._skill_registry = skill_registry or SkillRegistry.from_directory()
        self._trajectory_store = trajectory_store
        self._forbidden_terms = forbidden_terms

    @property
    def provider(self) -> Provider:
        if self._provider is None:
            from app.providers.factory import get_provider_for_capability

            self._provider = get_provider_for_capability("generation")
        return self._provider

    def run(self, request: DocumentOpsRequest, *, request_id: str, tenant_id: str) -> DocumentOpsResult:
        """Execute a single DocumentOps task.

        The current Phase 1 loop is deliberately narrow:
        select skill -> build prompt -> call provider.generate_raw -> validate
        provider JSON -> apply local QA -> optionally emit a compact trajectory.
        """
        tenant_id = require_tenant_id(tenant_id)
        skill = self._skill_registry.select(request.task_type, preferred_name=request.skill_name)
        prompt = self._build_prompt(request, skill)
        draft = self._generate_draft(prompt, request=request, skill=skill, request_id=request_id)
        qa = self._merge_qa(draft.qa, self._local_qa(draft, task_type=request.task_type))
        quality_warnings = list(qa.get("warnings", []))
        trajectory = self._build_trajectory(request, skill, draft, qa, request_id=request_id) if request.capture_trajectory else None
        if trajectory is not None and self._trajectory_store is not None:
            trajectory_id = self._trajectory_store.save(trajectory, tenant_id=tenant_id)
            trajectory["trajectory_id"] = trajectory_id
            trajectory["persisted"] = True
        return DocumentOpsResult(
            task_type=request.task_type,
            skill_name=skill.name,
            skill_version=skill.version,
            provider_name=self.provider.name,
            plan=draft.plan,
            critique=draft.critique,
            revision_tasks=draft.revision_tasks,
            draft=draft.draft,
            evidence_status=draft.evidence_status,
            qa=qa,
            quality_warnings=quality_warnings,
            trajectory=trajectory,
        )

    def _build_prompt(self, request: DocumentOpsRequest, skill: DocumentOpsSkill) -> str:
        payload = {
            "task_type": request.task_type,
            "requirements": request.requirements,
            "project_context": request.project_context,
            "source_summaries": request.source_summaries,
            "source_references": request.source_references,
        }
        return (
            "DecisionDoc DocumentOps Agent\n"
            "Return only valid JSON matching this schema:\n"
            "{"
            '"plan": ["..."], '
            '"critique": ["..."], '
            '"revision_tasks": ["..."], '
            '"draft": "...", '
            '"evidence_status": {'
            '"confirmed": ["..."], "assumptions": ["..."], "gaps": ["..."], "source_references": ["..."]'
            "}, "
            '"qa": {"hard_gate_pass": true, "warnings": []}'
            "}\n\n"
            "Write Korean content for plan, draft, and evidence_status values unless a source ID or product name must stay unchanged.\n"
            "For policy, public-sector, and operational planning tasks, explicitly cover 개인정보, 보안, 운영책임, 리스크, 로그/감사 where relevant.\n"
            "For develop_quality_improvement tasks, critique the current draft first, list concrete revision tasks, then return the improved draft without inventing missing evidence.\n"
            "Do not include keys outside the schema unless unavoidable.\n\n"
            f"Skill name: {skill.name}\n"
            f"Skill version: {skill.version}\n"
            f"Skill instructions:\n{skill.body}\n\n"
            f"Task payload JSON:\n{json.dumps(payload, ensure_ascii=False, sort_keys=True)}"
        )

    def _generate_draft(
        self,
        prompt: str,
        *,
        request: DocumentOpsRequest,
        skill: DocumentOpsSkill,
        request_id: str,
    ) -> DocumentOpsDraftOutput:
        try:
            raw = self.provider.generate_raw(prompt, request_id=request_id)
            return _parse_draft_output(raw)
        except ProviderError:
            raise
        except (NotImplementedError, json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
            return self._fallback_draft(request, skill, reason=f"agent_fallback:{exc.__class__.__name__}")

    def _fallback_draft(
        self,
        request: DocumentOpsRequest,
        skill: DocumentOpsSkill,
        *,
        reason: str = "agent_fallback:unknown",
    ) -> DocumentOpsDraftOutput:
        title = str(request.requirements.get("title") or request.project_context.get("title") or "의사결정 문서")
        goal = str(request.requirements.get("goal") or request.requirements.get("objective") or "승인 가능한 실행 방향 수립")
        source_refs = [
            str(item.get("id") or item.get("path") or item.get("title"))
            for item in request.source_references
            if item.get("id") or item.get("path") or item.get("title")
        ]
        gaps = ["공식 근거와 수치 출처 확인 필요"] if not source_refs else []
        warnings = [reason, *gaps]
        draft = (
            f"# {title}\n\n"
            f"## 핵심 판단\n{goal}을 달성하기 위해 문제 정의, 근거 상태, 실행 경로, 운영 책임을 분리해 검토합니다.\n\n"
            "## 제안 구조\n"
            "- 확인된 근거와 가정을 구분합니다.\n"
            "- 정책 논리와 실행 절차를 연결합니다.\n"
            "- 후속 승인자가 확인해야 할 TODO를 별도 표시합니다."
        )
        return DocumentOpsDraftOutput(
            plan=[
                "요구사항과 의사결정 목적을 분리합니다.",
                "확인된 근거, 가정, TODO를 구분합니다.",
                "정책 논리와 실행 경로를 검토 가능한 문서 구조로 정리합니다.",
            ],
            critique=[
                "Provider 응답을 구조화할 수 없어 로컬 fallback 초안을 사용했습니다.",
                "근거와 승인 질문은 사람 검토로 다시 확인해야 합니다.",
            ],
            revision_tasks=[
                "공식 source reference를 보강한 뒤 confirmed/assumption/TODO를 재분류합니다.",
                "승인자가 결정해야 할 질문과 운영 책임자를 명시합니다.",
            ],
            draft=draft,
            evidence_status=EvidenceStatus(
                confirmed=source_refs,
                assumptions=["현재 입력 요구사항은 초안 기준으로 유효하다고 가정"],
                gaps=gaps,
                source_references=source_refs,
            ),
            qa={
                "hard_gate_pass": False,
                "warnings": warnings,
                "fallback_used": True,
                "skill": skill.name,
            },
        )

    def _local_qa(self, draft: DocumentOpsDraftOutput, *, task_type: str = "") -> dict[str, Any]:
        gate = evaluate_document_ops_output(
            task_type=task_type,
            draft=draft.draft,
            plan=draft.plan,
            evidence_status=draft.evidence_status.model_dump(),
            qa=draft.qa,
            forbidden_terms=self._forbidden_terms,
        )
        return {
            "hard_gate_pass": gate.hard_gate_pass,
            "forbidden_terms": gate.forbidden_terms,
            "warnings": gate.warnings,
            "gate_issues": [issue.model_dump() for issue in gate.issues],
            "scores": gate.scores,
            "overall_score": gate.overall_score,
            "recommended_next_action": gate.recommended_next_action,
        }

    @staticmethod
    def _merge_qa(provider_qa: dict[str, Any], local_qa: dict[str, Any]) -> dict[str, Any]:
        warnings = [
            *provider_qa.get("warnings", []),
            *local_qa.get("warnings", []),
        ]
        hard_gate_pass = bool(provider_qa.get("hard_gate_pass", True)) and bool(local_qa.get("hard_gate_pass", True))
        return {
            **provider_qa,
            **local_qa,
            "warnings": warnings,
            "hard_gate_pass": hard_gate_pass,
        }

    def _build_trajectory(
        self,
        request: DocumentOpsRequest,
        skill: DocumentOpsSkill,
        draft: DocumentOpsDraftOutput,
        qa: dict[str, Any],
        *,
        request_id: str,
    ) -> dict[str, Any]:
        return {
            "trajectory_id": f"trj_{uuid.uuid4().hex}",
            "schema_version": "document_ops_trajectory_v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "request_id": request_id,
            "task_type": request.task_type,
            "skill": {"name": skill.name, "version": skill.version},
            "provider": self.provider.name,
            "input": _redact_for_trajectory(
                {
                    "requirements": request.requirements,
                    "project_context": request.project_context,
                    "source_summaries": request.source_summaries,
                    "source_references": request.source_references,
                }
            ),
            "requirements_keys": sorted(request.requirements.keys()),
            "source_summary_count": len(request.source_summaries),
            "source_reference_count": len(request.source_references),
            "plan": draft.plan,
            "critique": draft.critique,
            "revision_tasks": draft.revision_tasks,
            "evidence_status": draft.evidence_status.model_dump(),
            "draft_output": draft.draft,
            "qa": qa,
            "human_review_status": "pending",
            "human_feedback": {"accepted": False},
        }


_SENSITIVE_KEY_PARTS = ("raw", "attachment", "file_bytes", "base64", "document_text", "source_document")


def _redact_for_trajectory(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(part in lowered for part in _SENSITIVE_KEY_PARTS):
                redacted[key] = "[redacted]"
            else:
                redacted[key] = _redact_for_trajectory(item)
        return redacted
    if isinstance(value, list):
        return [_redact_for_trajectory(item) for item in value]
    if isinstance(value, str) and len(value) > 2000:
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
        return f"{value[:300]}...[redacted_long_text sha256={digest}]"
    return value


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)
_DRAFT_PAYLOAD_KEYS = ("output", "result", "document_ops", "response", "data")
_DRAFT_FIELD_ALIASES = ("draft", "draft_output", "final_output", "content", "body")
_CRITIQUE_FIELD_ALIASES = ("critique", "quality_critique", "review_findings", "issues")
_REVISION_TASK_FIELD_ALIASES = (
    "revision_tasks",
    "improvement_tasks",
    "rewrite_tasks",
    "next_revisions",
    "action_items",
)


def _parse_draft_output(raw: str) -> DocumentOpsDraftOutput:
    data = _load_json_object(raw)
    payload = _unwrap_draft_payload(data)
    normalized = _normalize_draft_payload(payload)
    return DocumentOpsDraftOutput.model_validate(normalized)


def _load_json_object(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    first_error: json.JSONDecodeError | None = None
    candidates = [text]
    candidates.extend(match.group(1).strip() for match in _JSON_FENCE_RE.finditer(text))
    object_candidate = _extract_first_json_object(text)
    if object_candidate:
        candidates.append(object_candidate)

    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError as exc:
            first_error = first_error or exc
            continue
        if isinstance(data, dict):
            return data
        raise TypeError("provider JSON root must be an object")

    if first_error is not None:
        raise first_error
    raise ValueError("provider response did not contain a JSON object")


def _extract_first_json_object(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for index, char in enumerate(text[start:], start=start):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _unwrap_draft_payload(data: dict[str, Any]) -> dict[str, Any]:
    for key in _DRAFT_PAYLOAD_KEYS:
        nested = data.get(key)
        if isinstance(nested, dict) and _looks_like_draft_payload(nested):
            return nested
    return data


def _looks_like_draft_payload(value: dict[str, Any]) -> bool:
    return any(
        key in value
        for key in (
            "plan",
            "evidence_status",
            "qa",
            *_DRAFT_FIELD_ALIASES,
            *_CRITIQUE_FIELD_ALIASES,
            *_REVISION_TASK_FIELD_ALIASES,
        )
    )


def _normalize_draft_payload(data: dict[str, Any]) -> dict[str, Any]:
    evidence_raw = data.get("evidence_status")
    evidence = evidence_raw if isinstance(evidence_raw, dict) else {}
    qa_raw = data.get("qa")
    qa = qa_raw if isinstance(qa_raw, dict) else {}
    return {
        "plan": _coerce_string_list(data.get("plan")),
        "critique": _coerce_string_list(_first_present(data, _CRITIQUE_FIELD_ALIASES)),
        "revision_tasks": _coerce_string_list(_first_present(data, _REVISION_TASK_FIELD_ALIASES)),
        "draft": _first_present_string(data, _DRAFT_FIELD_ALIASES),
        "evidence_status": {
            "confirmed": _coerce_string_list(
                _first_present(evidence, ("confirmed", "facts", "verified", "confirmed_claims"))
            ),
            "assumptions": _coerce_string_list(
                _first_present(evidence, ("assumptions", "assumed", "assumption", "hypotheses"))
            ),
            "gaps": _coerce_string_list(
                _first_present(evidence, ("gaps", "todo", "todos", "open_questions", "unknowns"))
            ),
            "source_references": _coerce_string_list(
                _first_present(
                    evidence,
                    ("source_references", "source_refs", "sources", "references"),
                    fallback=data.get("source_references") or data.get("sources"),
                )
            ),
        },
        "qa": _normalize_qa(qa),
    }


def _first_present(data: dict[str, Any], keys: tuple[str, ...], *, fallback: Any = None) -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, "", []):
            return value
    return fallback


def _first_present_string(data: dict[str, Any], keys: tuple[str, ...]) -> str:
    return _stringify(_first_present(data, keys))


def _coerce_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [text for item in value if (text := _stringify(item).strip())]
    text = _stringify(value).strip()
    return [text] if text else []


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("id", "title", "path", "name", "code", "message", "text"):
            item = value.get(key)
            if item:
                return str(item)
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _normalize_qa(qa: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(qa)
    if "warnings" in normalized and not isinstance(normalized["warnings"], list):
        normalized["warnings"] = _coerce_string_list(normalized["warnings"])
    return normalized
