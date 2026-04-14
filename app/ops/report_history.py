from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def get_default_post_deploy_report_dir() -> Path:
    configured = os.getenv("DECISIONDOC_POST_DEPLOY_REPORT_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path(__file__).resolve().parents[2] / "reports" / "post-deploy"


def load_report_json(path: Path) -> dict[str, Any]:
    resolved = Path(path).expanduser()
    if not resolved.exists():
        raise FileNotFoundError(f"Report file not found: {resolved}")
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON report: {resolved}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Unexpected JSON payload: {resolved}")
    return payload


def resolve_report_index(report_dir: Path) -> tuple[dict[str, Any], Path]:
    resolved_dir = Path(report_dir).expanduser()
    index_path = resolved_dir / "index.json"
    if not index_path.exists():
        raise FileNotFoundError(f"Report index not found: {index_path}")
    payload = load_report_json(index_path)
    return payload, index_path


def resolve_named_report(report_dir: Path, report_file: str) -> tuple[dict[str, Any], Path]:
    requested = str(report_file or "").strip()
    if not requested:
        raise ValueError("Report file name is required.")
    report_name = Path(requested).name
    if report_name != requested or not report_name.endswith(".json"):
        raise ValueError(f"Invalid report file name: {report_file}")

    index_payload, index_path = resolve_report_index(report_dir)
    allowed_files = {
        str(index_payload.get("latest", "")).strip(),
        str(index_payload.get("latest_report", "")).strip(),
    }
    reports = index_payload.get("reports", [])
    if isinstance(reports, list):
        for entry in reports:
            if isinstance(entry, dict):
                allowed_files.add(str(entry.get("file", "")).strip())
    allowed_files = {item for item in allowed_files if item}
    if report_name not in allowed_files:
        raise FileNotFoundError(f"Report file not listed in index: {report_name}")

    resolved_path = Path(report_dir).expanduser() / report_name
    if not resolved_path.exists():
        raise FileNotFoundError(f"Report file not found: {resolved_path}")
    payload = load_report_json(resolved_path)
    payload.setdefault("report_file", report_name)
    payload.setdefault("report_index_file", str(index_path))
    return payload, resolved_path


def build_post_deploy_reports_payload(*, report_dir: Path, limit: int, latest: bool) -> dict[str, Any]:
    index_payload, index_path = resolve_report_index(report_dir)
    reports = list(index_payload.get("reports", []))
    if not reports:
        raise ValueError(f"No reports listed in index: {index_path}")

    normalized_limit = max(1, int(limit))
    payload: dict[str, Any] = {
        "report_dir": str(Path(report_dir).expanduser()),
        "index_file": str(index_path),
        "latest_report": index_payload.get("latest_report", "-"),
        "updated_at": index_payload.get("updated_at", "-"),
        "reports": [entry for entry in reports[:normalized_limit] if isinstance(entry, dict)],
    }
    if latest:
        latest_path = Path(report_dir).expanduser() / "latest.json"
        payload["latest_details"] = load_report_json(latest_path)
    return payload


def build_post_deploy_report_detail_payload(*, report_dir: Path, report_file: str) -> dict[str, Any]:
    payload, resolved_path = resolve_named_report(report_dir, report_file)
    return {
        "report_dir": str(Path(report_dir).expanduser()),
        "report_file": payload.get("report_file") or resolved_path.name,
        "report_path": str(resolved_path),
        "details": payload,
    }
