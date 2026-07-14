"""app/storage/audit_store.py — Append-only ISMS compliance audit log.

Storage: data/tenants/{tenant_id}/audit_logs.jsonl
Format: one JSON object per line (JSONL), append-only.

CRITICAL: entries are NEVER deleted or modified — only appended.
Thread-safe via per-store file lock on append.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import os
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_log = logging.getLogger("decisiondoc.audit")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


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

    def __init__(self, tenant_id: str) -> None:
        data_dir = Path(os.getenv("DATA_DIR", "./data"))
        tenant_dir = data_dir / "tenants" / tenant_id
        tenant_dir.mkdir(parents=True, exist_ok=True)
        self._path = tenant_dir / "audit_logs.jsonl"
        self._tenant_id = tenant_id
        self._lock = threading.Lock()
        # Ensure file exists
        if not self._path.exists():
            self._path.touch()

    # ── internal helpers ───────────────────────────────────────────────────

    def _read_all(self) -> list[dict]:
        """Read all log entries, skipping corrupt lines."""
        entries: list[dict] = []
        try:
            content = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return entries

        corrupted = False
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                corrupted = True
                _log.warning("[AuditStore] Skipping corrupt line in %s", self._path)

        if corrupted:
            # Log a corruption event (best-effort, non-recursive)
            try:
                self.append(AuditLog(
                    log_id=str(uuid.uuid4()),
                    tenant_id=self._tenant_id,
                    timestamp=_now_iso(),
                    user_id="system",
                    username="system",
                    user_role="system",
                    ip_address="",
                    user_agent="",
                    action="system.config_change",
                    resource_type="system",
                    resource_id="",
                    resource_name="audit_log",
                    result="failure",
                    detail={"event": "audit_log_corruption_detected", "path": str(self._path)},
                    session_id="",
                ))
            except Exception:
                pass

        return entries

    # ── public API ─────────────────────────────────────────────────────────

    def append(self, log: AuditLog) -> None:
        """Thread-safe append of a single audit log entry."""
        line = json.dumps(asdict(log), ensure_ascii=False) + "\n"
        with self._lock:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(line)

    def query(
        self,
        tenant_id: str,
        filters: dict[str, Any] | None = None,
    ) -> list[dict]:
        """Return filtered log entries (max 1000), newest first.

        Filter keys: user_id, action, resource_type, result,
                     date_from (ISO), date_to (ISO), ip_address
        """
        return self.query_all(tenant_id, filters=filters)[:1000]

    def query_all(
        self,
        tenant_id: str,
        filters: dict[str, Any] | None = None,
    ) -> list[dict]:
        """Return all filtered log entries, newest first, without the query() cap."""
        filters = filters or {}
        entries = self._read_all()

        result: list[dict] = [e for e in entries if e.get("tenant_id") == tenant_id]
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
        tenant_id: str,
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
            if entry.get("tenant_id") != tenant_id:
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
        result = [e for e in entries if e.get("session_id") == session_id]
        result.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
        return result

    def get_user_activity(
        self,
        tenant_id: str,
        user_id: str,
        days: int = 30,
    ) -> list[dict]:
        """Return log entries for a user within the last *days* days."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        return self.query(tenant_id, filters={"user_id": user_id, "date_from": cutoff})

    def get_failed_logins(self, tenant_id: str, hours: int = 24) -> list[dict]:
        """Return failed login entries within the last *hours* hours."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        return self.query(
            tenant_id,
            filters={"action": "user.login_fail", "date_from": cutoff},
        )

    def export_csv(
        self,
        tenant_id: str,
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
            tenant_id,
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

    def get_stats(self, tenant_id: str, days: int = 30) -> dict:
        """Return summary statistics for the last *days* days."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        entries = self.query(tenant_id, filters={"date_from": cutoff})

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
