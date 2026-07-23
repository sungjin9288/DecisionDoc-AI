"""app/storage/audit_store.py — Append-only ISMS compliance audit log.

Storage: data/tenants/{tenant_id}/audit_logs.jsonl
Format: one JSON object per line (JSONL), append-only.

CRITICAL: entries are NEVER deleted or modified — only appended.
Append commits use backend conditional create/CAS across workers.
The shared process lock reduces local contention without defining persistence authority.
"""
from __future__ import annotations

import csv
import io
import json
import os
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.storage.state_backend import StateBackend, StateBackendError, get_state_backend
from app.tenant import require_tenant_id

_audit_locks: dict[Path, threading.RLock] = {}
_audit_locks_guard = threading.Lock()
_MAX_APPEND_ATTEMPTS = 32
_AUDIT_CONTENT_TYPE = "application/x-ndjson; charset=utf-8"


class AuditStoreError(ValueError):
    """Raised when persisted audit evidence cannot be trusted."""


def _lock_for_path(path: Path) -> threading.RLock:
    with _audit_locks_guard:
        return _audit_locks.setdefault(path.resolve(), threading.RLock())


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AuditStoreError(f"Duplicate key in audit log entry: {key!r}")
        result[key] = value
    return result


def _inclusive_date_end(value: str) -> str:
    """Expand a date-only upper bound so that it includes the full UTC day."""
    if len(value) != 10:
        return value
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return value
    return f"{value}T23:59:59.999999+00:00"


def _safe_csv_cell(value: Any) -> Any:
    """Prevent spreadsheet software from evaluating user-controlled cells."""
    if not isinstance(value, str):
        return value
    if value.lstrip().startswith(("=", "+", "-", "@")):
        return f"'{value}"
    return value


# ── Constants ──────────────────────────────────────────────────────────────────

ACTION_TYPES: dict[str, str] = {
    # Document
    "doc.generate": "문서 생성",
    "doc.download": "문서 다운로드",
    "doc.edit": "문서 편집",
    "doc.delete": "문서 삭제",
    "doc.view": "문서 열람",
    # Procurement
    "procurement.import": "조달 공고 연결",
    "procurement.evaluate": "조달 적합도 평가",
    "procurement.recommend": "조달 권고안 생성",
    "procurement.review_packet_export": "조달 검토 패킷 내보내기",
    "procurement.review_started": "조달 패킷 검토 시작",
    "procurement.review_inbox_view": "조달 검토함 조회",
    "procurement.review_completed": "조달 패킷 검토 완료",
    "procurement.review_packet_download": "조달 원본 검토 패킷 다운로드",
    "procurement.reviewed_package_download": "조달 완료 패키지 다운로드",
    "procurement.override_reason": "조달 override 사유 기록",
    "procurement.remediation_link_copied": "조달 remediation 링크 공유",
    "procurement.remediation_link_opened": "조달 remediation 링크 열람",
    "procurement.downstream_resolved": "조달 override 이후 downstream 완료",
    "decision_council.run": "Decision Council 실행",
    "decision_council.handoff_used": "Decision Council handoff 반영 생성",
    # Report quality
    "report_quality.pilot_preview": "보고서 품질 파일럿 사전 검토",
    "report_quality.pilot_export": "보고서 품질 파일럿 내보내기",
    "report_quality.pilot_package": "보고서 품질 파일럿 검토 패키지",
    "report_quality.pilot_package_verify": "보고서 품질 파일럿 수신 패키지 검증",
    # DocumentOps
    "document_ops.trajectory_view": "DocumentOps 이력 상세 조회",
    "document_ops.trajectory_review": "DocumentOps 사람 검토",
    "document_ops.agent_run_operation_view": "DocumentOps Agent 실행 상태 조회",
    "document_ops.governance_view": "DocumentOps governance 조회",
    "document_ops.governance_handoff_download": "DocumentOps governance handoff 다운로드",
    # Approval
    "approval.create": "결재 요청",
    "approval.submit": "검토 요청",
    "approval.review": "검토 처리",
    "approval.approve": "결재 승인",
    "approval.reject": "결재 반려",
    # User
    "user.login": "로그인",
    "user.logout": "로그아웃",
    "user.login_fail": "로그인 실패",
    "user.create": "사용자 생성",
    "user.update": "사용자 수정",
    "user.deactivate": "사용자 비활성화",
    "user.password_change": "비밀번호 변경",
    # Access
    "access.blocked": "접근 차단",
    "access.unauthorized": "권한 없음",
    # System
    "system.export": "데이터 내보내기",
    "system.import": "데이터 가져오기",
    "system.config_change": "설정 변경",
}


# ── Data model ─────────────────────────────────────────────────────────────────


@dataclass
class AuditLog:
    log_id: str
    tenant_id: str
    timestamp: str            # ISO 8601 with microseconds
    user_id: str              # "system" if automated
    username: str
    user_role: str
    ip_address: str
    user_agent: str
    action: str               # one of ACTION_TYPES keys
    resource_type: str        # "document" | "approval" | "project" | "user" | "style" | "system"
    resource_id: str
    resource_name: str        # human-readable
    result: str               # "success" | "failure" | "blocked"
    detail: dict              # additional context
    session_id: str


# ── AuditStore ────────────────────────────────────────────────────────────────


class AuditStore:
    """Append-only, thread-safe JSONL audit log store scoped to a single tenant."""

    def __init__(
        self,
        tenant_id: str,
        *,
        data_dir: str | Path | None = None,
        backend: StateBackend | None = None,
    ) -> None:
        self._tenant_id = require_tenant_id(tenant_id)
        self._base = Path(data_dir or os.getenv("DATA_DIR", "./data"))
        self._backend = backend or get_state_backend(data_dir=self._base)
        self._relative_path = str(
            Path("tenants") / self._tenant_id / "audit_logs.jsonl"
        )
        self._path = self._base / self._relative_path
        self._lock = _lock_for_path(self._path)

    # ── internal helpers ───────────────────────────────────────────────────

    def _validate_entry(self, entry: object) -> dict[str, Any]:
        if not isinstance(entry, dict):
            raise AuditStoreError("Invalid audit log entry")

        required_nonempty = (
            "log_id",
            "tenant_id",
            "timestamp",
            "action",
            "resource_type",
            "result",
        )
        if any(
            not isinstance(entry.get(field), str) or not entry[field]
            for field in required_nonempty
        ):
            raise AuditStoreError("Invalid audit log identity")
        if entry["tenant_id"] != self._tenant_id:
            raise AuditStoreError("Audit log tenant does not match store tenant")
        if entry["result"] not in {"success", "failure", "blocked"}:
            raise AuditStoreError("Invalid audit log result")
        if not isinstance(entry.get("detail"), dict):
            raise AuditStoreError("Invalid audit log detail")

        string_fields = (
            "user_id",
            "username",
            "user_role",
            "ip_address",
            "user_agent",
            "resource_id",
            "resource_name",
            "session_id",
        )
        if any(not isinstance(entry.get(field), str) for field in string_fields):
            raise AuditStoreError("Invalid audit log field")
        return entry

    def _parse(self, raw: str) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        log_ids: set[str] = set()
        for line_number, line in enumerate(raw.splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line, object_pairs_hook=_unique_object)
                entry = self._validate_entry(entry)
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                raise AuditStoreError(
                    f"Invalid audit log entry at line {line_number}"
                ) from exc
            if entry["log_id"] in log_ids:
                raise AuditStoreError("Duplicate audit log identity")
            log_ids.add(entry["log_id"])
            entries.append(entry)

        return entries

    def _read_all(self) -> list[dict[str, Any]]:
        """Read all owned log entries without mutating audit evidence."""
        with self._lock:
            raw = self._read_raw()
            return self._parse(raw or "")

    # ── public API ─────────────────────────────────────────────────────────

    def append(self, log: AuditLog) -> None:
        """Thread-safe append of a single audit log entry."""
        entry = self._validate_entry(asdict(log))
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        with self._lock:
            for _ in range(_MAX_APPEND_ATTEMPTS):
                raw = self._read_raw()
                existing = self._parse(raw or "")
                if any(item["log_id"] == entry["log_id"] for item in existing):
                    raise AuditStoreError("Duplicate audit log identity")

                current = raw or ""
                separator = "" if not current or current.endswith("\n") else "\n"
                replacement = f"{current}{separator}{line}"
                if self._append_if_current(expected=raw, replacement=replacement):
                    return

        raise AuditStoreError(
            "Audit log changed too many times to append safely"
        )

    def _read_raw(self) -> str | None:
        try:
            return self._backend.read_text(self._relative_path)
        except (StateBackendError, UnicodeError) as exc:
            raise AuditStoreError("Invalid audit log state") from exc

    def _append_if_current(
        self,
        *,
        expected: str | None,
        replacement: str,
    ) -> bool:
        try:
            if expected is None:
                return self._backend.write_text_if_absent(
                    self._relative_path,
                    replacement,
                    content_type=_AUDIT_CONTENT_TYPE,
                )
            return self._backend.replace_text_if_equal(
                self._relative_path,
                expected=expected,
                replacement=replacement,
                content_type=_AUDIT_CONTENT_TYPE,
            )
        except StateBackendError as exc:
            if self._entry_was_committed(replacement):
                return True
            raise AuditStoreError("Failed to persist audit log") from exc

    def _entry_was_committed(self, replacement: str) -> bool:
        expected_entries = self._parse(replacement)
        expected_entry = expected_entries[-1]
        try:
            observed = self._backend.read_text(self._relative_path)
        except (StateBackendError, UnicodeError):
            return False
        if observed is None:
            return False
        try:
            observed_entries = self._parse(observed)
        except AuditStoreError:
            return False
        return any(entry == expected_entry for entry in observed_entries)

    def _owns(self, entry: dict[str, Any]) -> bool:
        return entry.get("tenant_id") == self._tenant_id

    def query(
        self,
        *,
        filters: dict[str, Any] | None = None,
    ) -> list[dict]:
        """Return filtered log entries (max 1000), newest first.

        Filter keys: user_id, action, resource_type, result,
                     date_from (ISO), date_to (ISO), ip_address
        """
        return self.query_all(filters=filters)[:1000]

    def query_all(
        self,
        *,
        filters: dict[str, Any] | None = None,
    ) -> list[dict]:
        """Return all filtered log entries, newest first, without the query() cap."""
        filters = filters or {}
        entries = self._read_all()

        result = [entry for entry in entries if self._owns(entry)]
        if filters.get("user_id"):
            result = [e for e in result if e.get("user_id") == filters["user_id"]]
        if filters.get("action"):
            result = [e for e in result if e.get("action") == filters["action"]]
        if filters.get("resource_type"):
            result = [e for e in result if e.get("resource_type") == filters["resource_type"]]
        if filters.get("result"):
            result = [e for e in result if e.get("result") == filters["result"]]
        if filters.get("ip_address"):
            result = [e for e in result if e.get("ip_address") == filters["ip_address"]]
        if filters.get("date_from"):
            result = [e for e in result if e.get("timestamp", "") >= filters["date_from"]]
        if filters.get("date_to"):
            date_to = _inclusive_date_end(str(filters["date_to"]))
            result = [e for e in result if e.get("timestamp", "") <= date_to]

        result.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
        return result

    def find_latest_entry(
        self,
        *,
        actions: tuple[str, ...] | list[str] | set[str] | None = None,
        resource_ids: tuple[str, ...] | list[str] | set[str] | None = None,
        detail_filters: dict[str, Any] | None = None,
        result: str | None = None,
    ) -> dict[str, Any] | None:
        """Return the newest matching entry without applying the query() 1000-row cap."""
        action_set = {str(value) for value in (actions or ()) if str(value)}
        resource_id_set = {str(value) for value in (resource_ids or ()) if str(value)}
        normalized_detail_filters = {
            str(key): value
            for key, value in (detail_filters or {}).items()
            if str(key).strip()
        }

        for entry in reversed(self._read_all()):
            if not self._owns(entry):
                continue
            if action_set and str(entry.get("action", "")) not in action_set:
                continue
            if result is not None and str(entry.get("result", "")) != result:
                continue
            if resource_id_set and str(entry.get("resource_id", "")) not in resource_id_set:
                continue
            if normalized_detail_filters:
                detail = entry.get("detail", {})
                if not isinstance(detail, dict):
                    continue
                if any(detail.get(key) != value for key, value in normalized_detail_filters.items()):
                    continue
            return entry
        return None

    def get_session_activity(self, session_id: str) -> list[dict]:
        """Return all log entries for a given session_id, newest first."""
        entries = self._read_all()
        result = [
            entry
            for entry in entries
            if self._owns(entry) and entry.get("session_id") == session_id
        ]
        result.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
        return result

    def get_user_activity(
        self,
        user_id: str,
        *,
        days: int = 30,
    ) -> list[dict]:
        """Return log entries for a user within the last *days* days."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        return self.query(filters={"user_id": user_id, "date_from": cutoff})

    def get_failed_logins(self, *, hours: int = 24) -> list[dict]:
        """Return failed login entries within the last *hours* hours."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        return self.query(
            filters={"action": "user.login_fail", "date_from": cutoff},
        )

    def export_csv(
        self,
        date_from: str,
        date_to: str,
        *,
        user_id: str | None = None,
        action: str | None = None,
        resource_type: str | None = None,
        result: str | None = None,
    ) -> str:
        """Return every matching log entry as an evidence-preserving CSV string."""
        entries = self.query_all(
            filters={
                "user_id": user_id,
                "action": action,
                "resource_type": resource_type,
                "result": result,
                "date_from": date_from,
                "date_to": date_to,
            },
        )
        output = io.StringIO()
        fieldnames = [
            "log_id", "tenant_id", "timestamp", "user_id", "username", "user_role",
            "ip_address", "action", "resource_type", "resource_id",
            "resource_name", "result", "session_id", "request_id",
            "pilot_sha256", "pilot_artifact_count", "pilot_preview_verified",
            "detail_json",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for entry in reversed(entries):  # chronological order for CSV
            detail = entry.get("detail")
            detail = detail if isinstance(detail, dict) else {}
            row = {
                **entry,
                "request_id": detail.get("request_id", ""),
                "pilot_sha256": detail.get("pilot_sha256", ""),
                "pilot_artifact_count": detail.get("pilot_artifact_count", ""),
                "pilot_preview_verified": detail.get("pilot_preview_verified", ""),
                "detail_json": json.dumps(
                    detail,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            }
            writer.writerow({key: _safe_csv_cell(value) for key, value in row.items()})
        return output.getvalue()

    def get_stats(self, *, days: int = 30) -> dict:
        """Return summary statistics for the last *days* days."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        entries = self.query(filters={"date_from": cutoff})

        by_action: dict[str, int] = {}
        by_user: dict[str, int] = {}
        by_resource: dict[str, int] = {}
        failed = 0
        blocked = 0

        for e in entries:
            action = e.get("action", "unknown")
            by_action[action] = by_action.get(action, 0) + 1

            username = e.get("username", "unknown")
            by_user[username] = by_user.get(username, 0) + 1

            res_type = e.get("resource_type", "unknown")
            by_resource[res_type] = by_resource.get(res_type, 0) + 1

            if e.get("result") == "failure":
                failed += 1
            elif e.get("result") == "blocked":
                blocked += 1

        # Top 10 resources by activity
        top_resources = sorted(by_resource.items(), key=lambda x: x[1], reverse=True)[:10]

        return {
            "total_actions": len(entries),
            "by_action_type": by_action,
            "by_user": by_user,
            "failed_count": failed,
            "blocked_count": blocked,
            "top_resources": [{"type": k, "count": v} for k, v in top_resources],
            "days": days,
        }
