#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_completion_readiness import (  # noqa: E402
    EXCLUDED_EXTERNAL_ACTIONS,
    MILESTONE_COMMANDS,
    SCHEMA_VERSION as READINESS_SCHEMA_VERSION,
    write_json_artifact,
)


CHECK_SCHEMA_VERSION = "decisiondoc.completion_readiness_check.v1"
DEFAULT_READINESS_RESULT_PATH = ROOT / "reports" / "completion-readiness" / "latest.json"
DEFAULT_CHECK_RESULT_NAME = "latest-check.json"
EXPECTED_SCOPE = "readiness only; no external proof executed"
EXPECTED_MILESTONE_IDS = ("M1", "M2", "M6")
MILESTONE_FIELDS = (
    "id",
    "title",
    "status",
    "missing_env",
    "missing_files",
    "blockers",
    "commands",
)
ALLOWED_STATUSES = {"blocked", "ready_to_execute"}
RESULT_PATH_REQUIRES_WRITE_RESULT_ERROR = (
    "--result-path requires --write-result for completion readiness check result persistence"
)


def _load_json_object(path: Path) -> dict[str, object]:
    resolved = Path(path).expanduser()
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"readiness result not found: {resolved}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"readiness result is not valid JSON: {resolved}") from exc
    if not isinstance(payload, dict):
        raise ValueError("readiness result must be a JSON object")
    return payload


def _require_list(value: object, *, field: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    return value


def _require_string_list(value: object, *, field: str) -> list[str]:
    items = _require_list(value, field=field)
    if not all(isinstance(item, str) and item for item in items):
        raise ValueError(f"{field} must contain non-empty strings")
    return list(items)


def _validate_milestone(raw_milestone: object, *, expected_id: str) -> dict[str, object]:
    if not isinstance(raw_milestone, dict):
        raise ValueError(f"milestone {expected_id} must be an object")
    fields = set(raw_milestone)
    expected_fields = set(MILESTONE_FIELDS)
    if fields != expected_fields:
        raise ValueError(f"milestone {expected_id} fields drifted: {sorted(fields)}")
    if raw_milestone["id"] != expected_id:
        raise ValueError(f"milestone id mismatch: expected {expected_id}, got {raw_milestone['id']}")
    if not isinstance(raw_milestone["title"], str) or not raw_milestone["title"]:
        raise ValueError(f"milestone {expected_id} title must be a non-empty string")
    status = raw_milestone["status"]
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"milestone {expected_id} status is invalid: {status}")
    missing_env = _require_string_list(raw_milestone["missing_env"], field=f"{expected_id}.missing_env")
    missing_files = _require_string_list(raw_milestone["missing_files"], field=f"{expected_id}.missing_files")
    blockers = _require_string_list(raw_milestone["blockers"], field=f"{expected_id}.blockers")
    commands = _require_string_list(raw_milestone["commands"], field=f"{expected_id}.commands")
    if commands != list(MILESTONE_COMMANDS[expected_id]):
        raise ValueError(f"milestone {expected_id} commands drifted")
    has_blockers = bool(missing_env or missing_files or blockers)
    if status == "ready_to_execute" and has_blockers:
        raise ValueError(f"milestone {expected_id} is ready but still lists blockers")
    if status == "blocked" and not has_blockers:
        raise ValueError(f"milestone {expected_id} is blocked without any missing input or blocker")
    return {
        "id": expected_id,
        "status": status,
        "missing_env_count": len(missing_env),
        "missing_files_count": len(missing_files),
        "blocker_count": len(blockers),
    }


def _validate_readiness_result(payload: Mapping[str, object]) -> list[dict[str, object]]:
    if payload.get("schema_version") != READINESS_SCHEMA_VERSION:
        raise ValueError("readiness result schema_version mismatch")
    if not isinstance(payload.get("ok"), bool):
        raise ValueError("readiness result ok must be a boolean")
    if payload.get("scope") != EXPECTED_SCOPE:
        raise ValueError("readiness result scope mismatch")
    external_actions = _require_string_list(
        payload.get("external_actions_excluded"),
        field="external_actions_excluded",
    )
    if external_actions != list(EXCLUDED_EXTERNAL_ACTIONS):
        raise ValueError("external_actions_excluded drifted")
    milestones = _require_list(payload.get("milestones"), field="milestones")
    if len(milestones) != len(EXPECTED_MILESTONE_IDS):
        raise ValueError("milestone count mismatch")
    milestone_summaries = [
        _validate_milestone(raw_milestone, expected_id=expected_id)
        for raw_milestone, expected_id in zip(milestones, EXPECTED_MILESTONE_IDS, strict=True)
    ]
    expected_ok = all(item["status"] == "ready_to_execute" for item in milestone_summaries)
    if payload["ok"] != expected_ok:
        raise ValueError("readiness result ok does not match milestone statuses")
    return milestone_summaries


def check_completion_readiness_result(path: Path) -> dict[str, object]:
    resolved = Path(path).expanduser()
    payload = _load_json_object(resolved)
    milestone_summaries = _validate_readiness_result(payload)
    return {
        "schema_version": CHECK_SCHEMA_VERSION,
        "ok": True,
        "readiness_result_path": str(resolved),
        "readiness_schema_version": READINESS_SCHEMA_VERSION,
        "milestones": milestone_summaries,
        "external_actions_excluded": list(EXCLUDED_EXTERNAL_ACTIONS),
    }


def build_check_failure_result(path: Path, exc: Exception) -> dict[str, object]:
    return {
        "schema_version": CHECK_SCHEMA_VERSION,
        "ok": False,
        "readiness_result_path": str(Path(path).expanduser()),
        "error": str(exc),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check a persisted DecisionDoc completion readiness JSON result.",
    )
    parser.add_argument(
        "readiness_result_path",
        type=Path,
        nargs="?",
        default=DEFAULT_READINESS_RESULT_PATH,
    )
    parser.add_argument(
        "--write-result",
        action="store_true",
        help="Persist the check result JSON next to the readiness result or --result-path.",
    )
    parser.add_argument(
        "--result-path",
        type=Path,
        default=None,
        help="Optional path for --write-result. Defaults to <readiness_result_dir>/latest-check.json.",
    )
    return parser.parse_args()


def _emit_result(
    result: Mapping[str, object],
    *,
    result_path: Path,
    write_result: bool,
    exit_code: int,
) -> int:
    if write_result:
        write_json_artifact(result_path, result)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return exit_code


def main() -> int:
    args = _parse_args()
    check_result_path = args.result_path or (args.readiness_result_path.parent / DEFAULT_CHECK_RESULT_NAME)
    if args.result_path is not None and not args.write_result:
        result = build_check_failure_result(
            args.readiness_result_path,
            ValueError(RESULT_PATH_REQUIRES_WRITE_RESULT_ERROR),
        )
        return _emit_result(result, result_path=check_result_path, write_result=False, exit_code=1)
    try:
        result = check_completion_readiness_result(args.readiness_result_path)
    except Exception as exc:
        result = build_check_failure_result(args.readiness_result_path, exc)
        return _emit_result(
            result,
            result_path=check_result_path,
            write_result=args.write_result,
            exit_code=1,
        )
    return _emit_result(result, result_path=check_result_path, write_result=args.write_result, exit_code=0)


if __name__ == "__main__":
    raise SystemExit(main())
