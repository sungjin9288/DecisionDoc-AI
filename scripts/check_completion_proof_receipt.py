#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_completion_readiness import (  # noqa: E402
    EXCLUDED_EXTERNAL_ACTIONS,
    MILESTONE_COMMANDS,
    write_json_artifact,
)


RECEIPT_SCHEMA_VERSION = "decisiondoc.completion_proof_receipt.v2"
CHECK_SCHEMA_VERSION = "decisiondoc.completion_proof_receipt_check.v2"
EXPECTED_SCOPE = "proof receipt only; documents approved external proof without executing additional external actions"
EXPECTED_FIELDS = {
    "schema_version",
    "scope",
    "milestone_id",
    "title",
    "status",
    "command",
    "executed_at_utc",
    "environment_boundary",
    "evidence_summary",
    "evidence_refs",
    "remaining_limitations",
    "secret_values_recorded",
    "excluded_external_actions",
}
MILESTONE_TITLES = {
    "M1": "Live provider proof",
    "M2": "G2B live procurement smoke",
    "M6": "Deployment and post-deploy smoke proof",
}
MILESTONE_EXECUTED_ACTIONS = {
    "M1": "provider API execution",
    "M2": "G2B live API execution",
    "M6": "AWS runtime execution",
}
MILESTONE_EXECUTION_COMMANDS = {
    "M1": set(MILESTONE_COMMANDS["M1"]),
    "M2": {
        "python3 scripts/run_stage_procurement_smoke.py --env-file .env.prod",
        "python3 scripts/run_stage_procurement_smoke.py",
    },
    "M6": {
        "python3 scripts/run_deployed_smoke.py --env-file .env.prod",
        "python3 scripts/run_deployed_smoke.py",
    },
}
ALLOWED_STATUSES = {"passed", "failed", "blocked"}
SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"AIza[0-9A-Za-z_-]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"ghp_[0-9A-Za-z_]{20,}"),
    re.compile(r"github_pat_[0-9A-Za-z_]{20,}"),
)
PLACEHOLDER_VALUES = {"TODO", "TBD", "REPLACE_ME", "your-value", "your-command"}
SAFE_EVIDENCE_IDENTIFIER = re.compile(r"^[A-Za-z0-9._-]+$")


def _load_json_object(path: Path) -> dict[str, object]:
    resolved = Path(path).expanduser()
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"completion proof receipt not found: {resolved}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"completion proof receipt is not valid JSON: {resolved}") from exc
    if not isinstance(payload, dict):
        raise ValueError("completion proof receipt must be a JSON object")
    return payload


def _require_string(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    text = value.strip()
    if text in PLACEHOLDER_VALUES or text.startswith("Replace with"):
        raise ValueError(f"{field} still contains a placeholder")
    return text


def _require_string_list(value: object, *, field: str, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    if not allow_empty and not value:
        raise ValueError(f"{field} must not be empty")
    result: list[str] = []
    for item in value:
        result.append(_require_string(item, field=field))
    return result


def _require_utc_timestamp(value: object) -> str:
    text = _require_string(value, field="executed_at_utc")
    if not text.endswith("Z"):
        raise ValueError("executed_at_utc must use UTC Z suffix")
    try:
        datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("executed_at_utc must be an ISO-8601 UTC timestamp") from exc
    return text


def _iter_strings(value: object):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _iter_strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _iter_strings(item)


def _assert_no_secret_values(payload: Mapping[str, object]) -> None:
    for text in _iter_strings(dict(payload)):
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                raise ValueError("receipt appears to contain a secret value")


def excluded_external_actions_for(milestone_id: str, command: str) -> list[str]:
    if command not in MILESTONE_EXECUTION_COMMANDS[milestone_id]:
        return list(EXCLUDED_EXTERNAL_ACTIONS)
    executed_action = MILESTONE_EXECUTED_ACTIONS[milestone_id]
    return [action for action in EXCLUDED_EXTERNAL_ACTIONS if action != executed_action]


def safe_evidence_host(value: str) -> str:
    return urlsplit(str(value or "").strip()).hostname or "configured"


def safe_evidence_identifier(value: str, *, fallback: str) -> str:
    normalized = str(value or "").strip()
    if SAFE_EVIDENCE_IDENTIFIER.fullmatch(normalized):
        return normalized
    parsed = urlsplit(normalized)
    if parsed.hostname:
        return f"url-host:{parsed.hostname}"
    return fallback


def build_execution_receipt(
    *,
    milestone_id: str,
    status: str,
    command: str,
    environment_boundary: str,
    evidence_summary: str,
    evidence_refs: Sequence[str],
    remaining_limitations: Sequence[str],
    executed_at_utc: str | None = None,
) -> dict[str, object]:
    if milestone_id not in MILESTONE_TITLES:
        raise ValueError(f"unknown milestone_id: {milestone_id}")
    timestamp = executed_at_utc or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    receipt = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "scope": EXPECTED_SCOPE,
        "milestone_id": milestone_id,
        "title": MILESTONE_TITLES[milestone_id],
        "status": status,
        "command": command,
        "executed_at_utc": timestamp,
        "environment_boundary": environment_boundary,
        "evidence_summary": evidence_summary,
        "evidence_refs": list(evidence_refs),
        "remaining_limitations": list(remaining_limitations),
        "secret_values_recorded": False,
        "excluded_external_actions": excluded_external_actions_for(milestone_id, command),
    }
    _validate_receipt(receipt)
    return receipt


def write_completion_proof_receipt(path: Path, receipt: Mapping[str, object]) -> Path:
    _validate_receipt(receipt)
    return write_json_artifact(path, receipt)


def _validate_receipt(payload: Mapping[str, object]) -> dict[str, object]:
    fields = set(payload)
    if fields != EXPECTED_FIELDS:
        raise ValueError(f"completion proof receipt fields drifted: {sorted(fields)}")
    if payload["schema_version"] != RECEIPT_SCHEMA_VERSION:
        raise ValueError("completion proof receipt schema_version mismatch")
    if payload["scope"] != EXPECTED_SCOPE:
        raise ValueError("completion proof receipt scope mismatch")

    milestone_id = _require_string(payload["milestone_id"], field="milestone_id")
    if milestone_id not in MILESTONE_TITLES:
        raise ValueError(f"unknown milestone_id: {milestone_id}")
    if payload["title"] != MILESTONE_TITLES[milestone_id]:
        raise ValueError("completion proof receipt title mismatch")

    status = _require_string(payload["status"], field="status")
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"completion proof receipt status is invalid: {status}")

    command = _require_string(payload["command"], field="command")
    if command not in MILESTONE_COMMANDS[milestone_id]:
        raise ValueError("completion proof receipt command is not an allowed milestone command")

    _require_utc_timestamp(payload["executed_at_utc"])
    _require_string(payload["environment_boundary"], field="environment_boundary")
    _require_string(payload["evidence_summary"], field="evidence_summary")
    evidence_refs = _require_string_list(payload["evidence_refs"], field="evidence_refs")
    remaining_limitations = _require_string_list(
        payload["remaining_limitations"],
        field="remaining_limitations",
        allow_empty=True,
    )

    if payload["secret_values_recorded"] is not False:
        raise ValueError("secret_values_recorded must be false")
    excluded_external_actions = excluded_external_actions_for(milestone_id, command)
    if payload["excluded_external_actions"] != excluded_external_actions:
        raise ValueError("excluded_external_actions drifted")
    _assert_no_secret_values(payload)
    return {
        "milestone_id": milestone_id,
        "status": status,
        "evidence_ref_count": len(evidence_refs),
        "remaining_limitation_count": len(remaining_limitations),
    }


def check_completion_proof_receipt(path: Path) -> dict[str, object]:
    resolved = Path(path).expanduser()
    payload = _load_json_object(resolved)
    summary = _validate_receipt(payload)
    milestone_id = str(summary["milestone_id"])
    command = str(payload["command"])
    return {
        "schema_version": CHECK_SCHEMA_VERSION,
        "ok": True,
        "receipt_path": str(resolved),
        "receipt_schema_version": RECEIPT_SCHEMA_VERSION,
        "summary": summary,
        "external_actions_excluded": excluded_external_actions_for(milestone_id, command),
    }


def build_check_failure_result(path: Path, exc: Exception) -> dict[str, object]:
    return {
        "schema_version": CHECK_SCHEMA_VERSION,
        "ok": False,
        "receipt_path": str(Path(path).expanduser()),
        "error": str(exc),
    }


def build_template(milestone_id: str) -> dict[str, object]:
    if milestone_id not in MILESTONE_TITLES:
        raise ValueError(f"unknown milestone_id: {milestone_id}")
    command = MILESTONE_COMMANDS[milestone_id][0]
    return {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "scope": EXPECTED_SCOPE,
        "milestone_id": milestone_id,
        "title": MILESTONE_TITLES[milestone_id],
        "status": "blocked",
        "command": command,
        "executed_at_utc": "2026-07-09T00:00:00Z",
        "environment_boundary": "approved external proof environment; no secrets recorded",
        "evidence_summary": "Replace with pass/fail summary before checking this receipt.",
        "evidence_refs": [
            "Replace with a local receipt path, GitHub Actions URL, or smoke log path.",
        ],
        "remaining_limitations": [
            "Replace with any remaining external limitation, or use an empty list.",
        ],
        "secret_values_recorded": False,
        "excluded_external_actions": excluded_external_actions_for(milestone_id, command),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a no-secret DecisionDoc completion proof receipt.",
    )
    parser.add_argument("receipt_path", type=Path, nargs="?")
    parser.add_argument(
        "--print-template",
        choices=tuple(MILESTONE_TITLES),
        default=None,
        help="Print a safe JSON template for one completion milestone.",
    )
    parser.add_argument(
        "--write-result",
        action="store_true",
        help="Persist the check result JSON next to the receipt or --result-path.",
    )
    parser.add_argument("--result-path", type=Path, default=None)
    return parser.parse_args()


def _emit(result: Mapping[str, object], *, result_path: Path | None, write_result: bool, exit_code: int) -> int:
    if write_result:
        if result_path is None:
            raise ValueError("result_path is required when write_result is true")
        write_json_artifact(result_path, result)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return exit_code


def main() -> int:
    args = _parse_args()
    if args.print_template:
        print(json.dumps(build_template(args.print_template), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.receipt_path is None:
        result = build_check_failure_result(Path("<missing>"), ValueError("receipt_path is required"))
        return _emit(result, result_path=None, write_result=False, exit_code=1)
    check_result_path = args.result_path or (args.receipt_path.parent / "latest-proof-check.json")
    try:
        result = check_completion_proof_receipt(args.receipt_path)
    except Exception as exc:
        result = build_check_failure_result(args.receipt_path, exc)
        return _emit(result, result_path=check_result_path, write_result=args.write_result, exit_code=1)
    return _emit(result, result_path=check_result_path, write_result=args.write_result, exit_code=0)


if __name__ == "__main__":
    raise SystemExit(main())
