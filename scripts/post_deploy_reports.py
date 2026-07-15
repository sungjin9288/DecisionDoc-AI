"""Persist post-deploy reports and their bounded local history index."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from app.ops.report_history import (
    _apply_extracted_summary_fields,
    _extract_provider_route_summary,
    _extract_report_workflow_smoke_summary,
    _extract_smoke_failure_summary,
)


DEFAULT_REPORT_INDEX_LIMIT = 20


def _write_json_report(report_file: Path, payload: dict[str, Any]) -> None:
    resolved = Path(report_file).expanduser()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    temp_path = resolved.with_name(f"{resolved.name}.tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_path, resolved)


def resolve_report_targets(
    *,
    report_file: Path | None,
    report_dir: Path | None,
    started_at: datetime,
) -> tuple[Path | None, Path | None]:
    if report_file is not None and report_dir is not None:
        raise SystemExit("Use either --report-file or --report-dir, not both.")
    if report_dir is not None:
        resolved_dir = Path(report_dir).expanduser()
        timestamp = started_at.strftime("%Y%m%dT%H%M%SZ")
        return (
            resolved_dir / f"post-deploy-{timestamp}.json",
            resolved_dir / "latest.json",
        )
    if report_file is not None:
        return Path(report_file).expanduser(), None
    return None, None


def _normalize_index_error(value: Any, *, max_len: int = 160) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if len(text) <= max_len:
        return text
    return f"{text[: max_len - 3].rstrip()}..."


def _build_index_entry(*, report_file: Path, payload: dict[str, Any]) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "file": report_file.name,
        "status": payload.get("status"),
        "base_url": payload.get("base_url"),
        "started_at": payload.get("started_at"),
        "finished_at": payload.get("finished_at"),
        "skip_smoke": bool(payload.get("skip_smoke")),
    }
    error = _normalize_index_error(payload.get("error"))
    if error:
        entry["error"] = error
    entry["smoke_results_available"] = bool(payload.get("smoke_results_available"))
    entry["report_workflow_smoke_results_available"] = bool(
        payload.get("report_workflow_smoke_results_available")
    )
    entry.update(_extract_provider_route_summary(payload))
    entry.update(_extract_smoke_failure_summary(payload))
    entry.update(_extract_report_workflow_smoke_summary(payload))
    return entry


def _update_report_index(
    *,
    report_file: Path,
    latest_file: Path | None,
    payload: dict[str, Any],
    history_limit: int = DEFAULT_REPORT_INDEX_LIMIT,
) -> None:
    report_dir = report_file.parent
    index_file = report_dir / "index.json"
    index_payload: dict[str, Any] = {
        "updated_at": payload.get("finished_at") or payload.get("started_at"),
        "latest": latest_file.name if latest_file is not None else report_file.name,
        "latest_report": report_file.name,
        "reports": [],
    }
    if index_file.exists():
        try:
            loaded = json.loads(index_file.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                index_payload.update(
                    {
                        "updated_at": loaded.get(
                            "updated_at", index_payload["updated_at"]
                        ),
                        "latest": loaded.get("latest", index_payload["latest"]),
                        "latest_report": loaded.get(
                            "latest_report", index_payload["latest_report"]
                        ),
                        "reports": list(loaded.get("reports", [])),
                    }
                )
        except json.JSONDecodeError:
            pass

    reports = [
        entry
        for entry in index_payload.get("reports", [])
        if entry.get("file") != report_file.name
    ]
    reports.insert(0, _build_index_entry(report_file=report_file, payload=payload))
    index_payload["updated_at"] = payload.get("finished_at") or payload.get(
        "started_at"
    )
    index_payload["latest"] = (
        latest_file.name if latest_file is not None else report_file.name
    )
    index_payload["latest_report"] = report_file.name
    index_payload["reports"] = reports[:history_limit]
    _write_json_report(index_file, index_payload)


def persist_reports(
    *,
    payload: dict[str, Any],
    report_file: Path | None,
    latest_file: Path | None,
) -> None:
    _apply_extracted_summary_fields(payload)
    if report_file is not None:
        _write_json_report(report_file, payload)
    if latest_file is not None:
        _write_json_report(latest_file, payload)
    if report_file is not None and latest_file is not None:
        _update_report_index(
            report_file=report_file,
            latest_file=latest_file,
            payload=payload,
        )
