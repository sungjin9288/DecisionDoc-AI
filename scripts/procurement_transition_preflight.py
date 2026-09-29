#!/usr/bin/env python3
"""Inspect an explicit offline state copy; never start the app or migrate data."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any, Sequence


if __name__ == "__main__":
    sys.dont_write_bytecode = True
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.storage.procurement_project_state import decode_project  # noqa: E402
from app.storage.procurement_store import ProcurementDecisionStore  # noqa: E402
from app.tenant import require_tenant_id  # noqa: E402


MAX_STATE_BYTES = 16 * 1024 * 1024


def _report(raw: bytes | None = None) -> dict[str, Any]:
    return {
        "schema_version": "procurement.transition_preflight.v1",
        "state_contract_status": "blocked",
        "input_sha256": hashlib.sha256(raw).hexdigest() if raw is not None else None,
        "input_size_bytes": len(raw) if raw is not None else None,
        "counts": None,
        "legacy_reader_compatible": None,
        "activation_allowed": False,
        "source_bytes_verified": False,
        "writes_performed": False,
        "issues": [],
    }


def inspect_state(raw: bytes, *, tenant_id: str) -> dict[str, Any]:
    """Validate the captured contract, not live sources, permissions or readiness."""
    require_tenant_id(tenant_id)
    report = _report(raw)
    try:
        rows = ProcurementDecisionStore._decode_records(raw.decode("utf-8"))
        # JSON's permissive NaN/Infinity support is not a persisted-state contract.
        json.dumps(rows, allow_nan=False)
    except (ValueError, UnicodeError, RecursionError):
        report["issues"].append({"code": "invalid_state_document"})
        return report

    counts = dict(projects=0, legacy_projects=0, v2_projects=0,
                  decisions=0, requirements=0, snapshot_references=0)
    project_ids: set[str] = set()
    decision_ids: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            report["issues"].append({"row_index": index, "code": "invalid_row"})
            continue
        if row.get("tenant_id") != tenant_id:
            report["issues"].append({"row_index": index, "code": "tenant_mismatch"})
            continue
        try:
            project = decode_project(row, tenant_id=tenant_id, project_id=row.get("project_id"))
        except (ValueError, TypeError, RecursionError):
            report["issues"].append({"row_index": index, "code": "invalid_project_state"})
            continue
        if project.project_id in project_ids:
            report["issues"].append({"row_index": index, "code": "duplicate_project"})
        project_ids.add(project.project_id)
        counts["projects"] += 1
        counts["v2_projects" if row.get("schema_version") == "procurement.project.v2"
               else "legacy_projects"] += 1
        for entry in project.entries:
            if entry.record.decision_id in decision_ids:
                report["issues"].append({"row_index": index, "code": "duplicate_decision"})
            decision_ids.add(entry.record.decision_id)
            counts["decisions"] += 1
            counts["requirements"] += len(entry.requirements)
            counts["snapshot_references"] += len(entry.record.source_snapshots)
    if not report["issues"]:
        report.update(state_contract_status="pass", counts=counts,
                      legacy_reader_compatible=counts["v2_projects"] == 0)
    return report


def _fingerprint(info: os.stat_result) -> tuple[int, ...]:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def read_state_file(path: Path) -> bytes:
    """Refuse leaf symlinks, special files, oversized input and observed drift."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_STATE_BYTES:
            raise ValueError("Unsupported state file")
        raw = stream.read(MAX_STATE_BYTES + 1)
        after = os.fstat(stream.fileno())
        current = path.stat(follow_symlinks=False)
        if (len(raw) > MAX_STATE_BYTES or len(raw) != before.st_size
                or _fingerprint(before) != _fingerprint(after)
                or _fingerprint(after) != _fingerprint(current)):
            raise ValueError("State file changed during inspection")
        return raw


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-file", required=True, type=Path,
                        help="Explicit offline procurement_decisions.json copy; no directory scan")
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--expected-sha256", help="Optional exact-byte input pin")
    args = parser.parse_args(argv)
    report = _report()
    try:
        require_tenant_id(args.tenant_id)
        if args.expected_sha256 is not None and not re.fullmatch(r"[a-f0-9]{64}", args.expected_sha256):
            raise ValueError("Invalid input hash")
    except ValueError:
        report["issues"].append({"code": "invalid_scope"})
    else:
        try:
            raw = read_state_file(args.state_file)
        except (OSError, ValueError):
            report["issues"].append({"code": "input_unavailable"})
        else:
            report = _report(raw)
            if args.expected_sha256 is not None and report["input_sha256"] != args.expected_sha256:
                report["issues"].append({"code": "input_hash_mismatch"})
            else:
                report = inspect_state(raw, tenant_id=args.tenant_id)
    print(json.dumps(report, ensure_ascii=True, sort_keys=True, indent=2))
    return 0 if report["state_contract_status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
